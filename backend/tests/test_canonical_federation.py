"""Canonical linking consumers with signed IdP wire, native directory doubles,
real endpoints/JWT/Redis; no live native attachment capability is asserted."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from urllib.parse import quote

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from pydantic import ValidationError
from sqlalchemy import select

from app.models.auth_settings import AuthSettings
from app.models.domain_iam import DomainEnrollment
from app.models.domain_quotas import DomainQuotaPolicy
from app.models.enrollment_policy import EnrollmentPolicy, SignupRequest
from app.services import domain_auth as svc
from app.services import jwt_service, keystone, session_store
from tests.test_domain_auth import CLIENT_ID, ISSUER, SECRET, oidc_fields, start
from tests.test_domain_auth import api as api
from tests.test_domain_auth import db as db
from tests.test_domain_auth import env as env
from tests.test_domain_auth import keystone_admin as keystone_admin
from tests.test_domain_auth import public_dns as public_dns
from tests.test_domain_auth import settings as settings
from tests.test_domain_auth import wire as wire


@pytest.fixture
async def external_env(env, monkeypatch):
    """Real enrollment/approval SQL and native grant readback; quota wire isolated."""
    from app.services import (
        domain_iam,
        domain_projects,
        domain_scope,
        enrollment_policy,
        identity_roles,
        project_service,
    )
    from tests.test_project_membership_roles import Membership

    env.keystone.user_rows.clear()
    env.keystone.catalog = Membership().catalog
    for did, pid in (("dom-a", "default-a"), ("dom-b", "default-b")):
        env.keystone.project_rows[pid] = SimpleNamespace(
            id=pid, name="Default", domain_id=did, enabled=True, parent_id=None
        )
    env.settings.os_username = "operational-admin"
    env.settings.service_manila_enabled = False
    env.settings.auth = AuthSettings.model_validate({"default": {"auto_join_email_domains": {}}})
    monkeypatch.setattr(domain_iam, "get_settings", lambda: env.settings)
    monkeypatch.setattr(enrollment_policy, "get_settings", lambda: env.settings)
    monkeypatch.setattr(enrollment_policy, "get_session_factory", lambda: env.db)
    monkeypatch.setattr(identity_roles, "_applied", AsyncMock())
    monkeypatch.setattr(project_service, "invalidate_project_lists", AsyncMock())
    monkeypatch.setattr(domain_scope, "invalidate_authority", AsyncMock())
    monkeypatch.setattr(
        project_service,
        "inspect_project_empty",
        AsyncMock(return_value={"can_delete": False, "resources": [{"status": "unavailable", "count": None}]}),
    )
    async with env.db() as session:
        session.add(
            EnrollmentPolicy(
                id=1,
                revision=1,
                public_signup_enabled=False,
                approval_mode="auto",
                personal_quotas={"instances": 0},
                updated_by_user_id="reviewer",
                updated_at=datetime.now(UTC),
            )
        )
        await session.commit()

    env.quota_applications = []

    async def apply_quotas(did, pid, lease):
        await lease.assert_owned()
        # Verify policy seeding and fail-closed activation ordering rather than
        # mocking the entire personal-account lifecycle or its role graph.
        async with env.db() as session:
            quota = await session.get(DomainQuotaPolicy, did)
            assert quota.ceilings == quota.defaults == {"instances": 0}
        assert env.keystone.projects.get(pid).enabled is False
        assert env.keystone.users.get("new-user").enabled is False
        env.quota_applications.append((did, pid))

    monkeypatch.setattr(domain_projects, "apply_default_quotas", apply_quotas)
    env.wire.federation.user_id = "new-user"
    env.wire.federation.native_users = env.keystone.user_rows
    return env


async def external_provider(env, kind="oidc", domain_id="dom-a"):
    fields = (
        oidc_fields()
        if kind == "oidc"
        else {
            "name": "GitHub",
            "kind": "github",
            "client_id": CLIENT_ID,
            "client_secret": SECRET,
            "keystone_idp_id": "idp-a",
            "keystone_protocol_id": "github",
        }
    )
    provider = await svc.create_provider(domain_id, actor_user_id="manager", fields=fields)
    env.settings.auth.default.auto_join_email_domains[provider["id"]] = ["corp.example"]
    return provider


async def set_approval_mode(env, mode):
    async with env.db() as session:
        policy = await session.get(EnrollmentPolicy, 1)
        policy.approval_mode = mode
        await session.commit()


@pytest.fixture
def external_api(external_env, monkeypatch):
    from app.api.identity import domain_auth as routes
    from app.rate_limit import limiter

    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(routes.public_router, prefix="/api/v1/auth")
    validate = Mock(side_effect=AssertionError("Unfinished enrollment must not validate native tokens"))
    monkeypatch.setattr(keystone, "validate_token", validate)
    return SimpleNamespace(
        client=httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="https://api.example.com",
            headers={"Origin": "https://cloud.example.com", "Sec-Fetch-Site": "same-site"},
        ),
        validate=validate,
    )


async def external_callback(client, env, provider):
    begun = await client.post(f"/api/v1/auth/domains/dom-a/providers/{provider['id']}/authorize")
    assert begun.status_code == 200, begun.text
    state = env.wire.idp.remember(begun.json()["authorize_url"])
    return await client.post("/api/v1/auth/providers/callback", json={"code": "good-code", "state": state})


@pytest.mark.parametrize("kind", ["oidc", "github"])
async def test_external_personal_home_and_reader_only_org_survive_fresh_auth(external_env, kind):
    from app.services import domain_projects, project_service
    from tests.test_project_membership_roles import rid

    env = external_env
    provider = await external_provider(env, kind)
    state, browser = await start(env.wire.idp, provider["id"])
    first = await svc.complete_authorization("good-code", state, browser)
    user = env.keystone.users.get(first.user_id)
    home = user.domain_id
    assert first.domain_id == "dom-a" and home not in {"dom-a", "dom-b"}
    assert user.enabled is True and user.afterglow_local_password is False
    assert not hasattr(user, "password")
    assert all("password" not in fields for _, _, fields in env.keystone.user_writes)
    personal = domain_projects.default_project(home, ks=env.keystone)
    assert personal["enabled"] is True
    assert project_service._direct_ids(env.keystone.role_assignments.list(project=personal["id"]), user.id) == {
        rid("manager"),
        rid("project_owner"),
        rid("project_reader"),
    }
    assert project_service._direct_ids(env.keystone.role_assignments.list(project="default-a"), user.id) == {
        rid("project_reader"),
    }
    domain_projects.assert_membership(user.id, "dom-a", ks=env.keystone)
    assert domain_projects.has_manager(user.id, home, ks=env.keystone)
    assert not domain_projects.has_manager(user.id, "dom-a", ks=env.keystone)
    assert env.quota_applications == [(home, personal["id"])]

    # Approval and admission changes cannot reapprove or move an existing link.
    await set_approval_mode(env, "admin")
    env.settings.auth.default.auto_join_email_domains.clear()
    state, browser = await start(env.wire.idp, provider["id"])
    again = await svc.complete_authorization("good-code", state, browser)
    assert again.user_id == first.user_id and again.domain_id == "dom-a"
    assert user.domain_id == home and len(env.keystone.domain_writes) == 1

    # A personal home is not authority to enter a different organization.
    other = await external_provider(env, kind, "dom-b")
    env.settings.auth.default.auto_join_email_domains.clear()
    state, browser = await start(env.wire.idp, other["id"], "dom-b")
    exchanges = len(env.wire.federation.calls)
    with pytest.raises(svc.DomainAuthDenied) as denied:
        await svc.complete_authorization("good-code", state, browser)
    assert denied.value.code == "invitation_required"
    assert len(env.wire.federation.calls) == exchanges
    # Model separately accepted invitation authority with an actual native grant.
    env.keystone.roles.grant(rid("project_reader"), user=user.id, project="default-b")
    state, browser = await start(env.wire.idp, other["id"], "dom-b")
    joined = await svc.complete_authorization("good-code", state, browser)
    assert joined.user_id == first.user_id and joined.domain_id == "dom-b"
    assert user.domain_id == home and len(env.keystone.user_rows) == 1
    async with env.db() as session:
        enrollment = (await session.execute(select(DomainEnrollment))).scalar_one()
        assert enrollment.status == "accepted" and enrollment.identity_domain_id == home
        assert enrollment.personal_quotas == {"instances": 0}
        assert (await session.execute(select(SignupRequest))).scalars().all() == []


@pytest.mark.parametrize("kind", ["oidc", "github"])
@pytest.mark.parametrize("decision", ["pending", "rejected"])
async def test_external_approval_denial_has_no_account_exchange_or_session(external_env, external_api, kind, decision):
    env = external_env
    provider = await external_provider(env, kind)
    await set_approval_mode(env, "admin")
    async with external_api.client as client:
        pending = await external_callback(client, env, provider)
        assert pending.status_code == 403 and pending.json()["code"] == "signup_approval_pending"
        async with env.db() as session:
            request = (await session.execute(select(SignupRequest))).scalar_one()
            assert request.source == kind and request.domain_id == "dom-a" and request.provider_id == provider["id"]
            request.status = decision
            if decision == "rejected":
                request.reviewed_at = datetime.now(UTC)
                request.reviewed_by_user_id = "reviewer"
            await session.commit()
        denied = await external_callback(client, env, provider)
        assert denied.status_code == 403 and denied.json()["code"] == "signup_approval_" + decision
        assert not {"access_token", "refresh_token", "user_id"} & denied.json().keys()
        assert client.cookies.get(svc.STATE_COOKIE) is None
    assert env.keystone.user_rows == {} and env.keystone.user_writes == []
    assert env.keystone.domain_writes == [] and env.keystone.project_writes == []
    assert env.wire.federation.calls == [] and env.quota_applications == []
    external_api.validate.assert_not_called()
    assert await (await svc._redis()).keys("afterglow:refresh:*") == []
    async with env.db() as session:
        assert (await session.execute(select(DomainEnrollment))).scalars().all() == []
        assert len((await session.execute(select(SignupRequest))).scalars().all()) == 1


@pytest.mark.parametrize("kind", ["oidc", "github"])
async def test_approved_external_fresh_auth_consumes_exact_request_after_personal_creation(external_env, kind):
    env = external_env
    provider = await external_provider(env, kind)
    await set_approval_mode(env, "admin")
    state, browser = await start(env.wire.idp, provider["id"])
    with pytest.raises(svc.DomainAuthDenied) as pending:
        await svc.complete_authorization("good-code", state, browser)
    assert pending.value.code == "signup_approval_pending"
    async with env.db() as session:
        request = (await session.execute(select(SignupRequest))).scalar_one()
        request.status = "approved"
        request.reviewed_at = datetime.now(UTC)
        request.reviewed_by_user_id = "reviewer"
        request_id = request.id
        await session.commit()
    state, browser = await start(env.wire.idp, provider["id"])
    login = await svc.complete_authorization("good-code", state, browser)
    assert env.keystone.users.get(login.user_id).domain_id != "dom-a"
    async with env.db() as session:
        request = await session.get(SignupRequest, request_id)
        assert request.status == "consumed" and request.consumed_by_user_id == login.user_id
    state, browser = await start(env.wire.idp, provider["id"])
    again = await svc.complete_authorization("good-code", state, browser)
    assert again.user_id == login.user_id and len(env.keystone.domain_writes) == 1


async def test_external_quota_uncertainty_cannot_exchange_or_issue_session(external_env, external_api, monkeypatch):
    from app.services import domain_projects

    env = external_env
    provider = await external_provider(env)

    async def unavailable(*args, **kwargs):
        raise HTTPException(503, "synthetic quota application unconfirmed")

    monkeypatch.setattr(domain_projects, "apply_default_quotas", unavailable)
    async with external_api.client as client:
        failed = await external_callback(client, env, provider)
        assert failed.status_code == 503
        assert not {"access_token", "refresh_token", "user_id"} & failed.json().keys()
    assert env.wire.federation.calls == []
    external_api.validate.assert_not_called()
    assert await (await svc._redis()).keys("afterglow:refresh:*") == []
    assert all(not user.enabled for user in env.keystone.user_rows.values())
    async with env.db() as session:
        enrollment = (await session.execute(select(DomainEnrollment))).scalar_one()
        assert enrollment.status in {"failed", "recovery_required"}


@pytest.mark.parametrize("kind", ["oidc", "github"])
async def test_active_external_recovery_identity_cannot_bypass_finalization_on_fresh_auth(
    external_env, external_api, monkeypatch, kind
):
    from app.services import domain_iam, identity_roles

    env = external_env
    provider = await external_provider(env, kind)
    # Fail after user activation and all confirmed grants, then leave those
    # effects unresolved. Native enabled=True is not the SQL commit boundary.
    monkeypatch.setattr(identity_roles, "_applied", AsyncMock(side_effect=RuntimeError("late finalization failed")))
    compensate = AsyncMock(return_value=False)
    monkeypatch.setattr(domain_iam, "_compensate", compensate)
    async with external_api.client as client:
        failed = await external_callback(client, env, provider)
        assert failed.status_code == 503
        compensate.assert_awaited_once()
        user = env.keystone.users.get("new-user")
        assert user.enabled is True and user.afterglow_local_password is False
        async with env.db() as session:
            enrollment = (await session.execute(select(DomainEnrollment))).scalar_one()
            assert enrollment.status == "recovery_required"
            assert enrollment.user_id == user.id and enrollment.identity_domain_id == user.domain_id
            assert enrollment.token_hash == user.afterglow_enrollment_id
        # A fresh provider proof resolves this same active, stable native link.
        # It must still stop before admission, attachment or native federation.
        retried = await external_callback(client, env, provider)
        assert retried.status_code == 503
        assert retried.json()["code"] == "external_enrollment_unconfirmed"
        assert not {"access_token", "refresh_token", "user_id"} & retried.json().keys()
        assert client.cookies.get(svc.STATE_COOKIE) is None
    assert len(env.keystone.domain_writes) == 1
    assert len([write for write in env.keystone.user_writes if write[0] == "create"]) == 1
    assert env.wire.federation.calls == []
    external_api.validate.assert_not_called()
    assert await (await svc._redis()).keys("afterglow:refresh:*") == []


@pytest.mark.parametrize("mutation", ["native_response", "directory_home"])
async def test_existing_external_canonical_home_is_immutable_during_exchange(external_env, monkeypatch, mutation):
    env = external_env
    provider = await external_provider(env)
    state, browser = await start(env.wire.idp, provider["id"])
    login = await svc.complete_authorization("good-code", state, browser)
    user = env.keystone.users.get(login.user_id)
    home = user.domain_id
    original = svc.keystone_federate

    async def changed_home(row, bearer):
        token, native = await original(row, bearer)
        if mutation == "native_response":
            native["domain"] = {"id": "dom-a"}
        else:
            user.domain_id = "dom-a"
        return token, native

    monkeypatch.setattr(svc, "keystone_federate", changed_home)
    state, browser = await start(env.wire.idp, provider["id"])
    with pytest.raises(svc.DomainAuthDenied) as denied:
        await svc.complete_authorization("good-code", state, browser)
    assert denied.value.code == "canonical_subject_mismatch"
    assert env.keystone.revoked == ["unscoped-fed"]
    if mutation == "native_response":
        assert user.domain_id == home


def unbound(env):
    user = env.keystone.user_rows["fed-user"]
    user.afterglow_external_identities = []
    user.federated = []
    user.default_project_id = "saved-native-preference"
    return user


def proof(**overrides):
    return {
        "token": "password-proof",
        "user_id": "fed-user",
        "username": "dev",
        "identity_domain_id": "dom-a",
        "domain_id": "dom-a",
        "email": "Dev@corp.example",
        **overrides,
    }


async def authenticated_session(env, auth_method="password"):
    from time import time

    env.settings.session_timeout_seconds = 3600
    await session_store.store_session(
        "link-origin",
        "authenticated-native",
        "",
        "fed-user",
        int(time()) + 1800,
        auth_method=auth_method,
        domain_id="dom-a",
        identity_domain_id="dom-a",
    )
    return {
        "user_id": "fed-user",
        "identity_domain_id": "dom-a",
        "token": "authenticated-native",
        "refresh_jti": "link-origin",
    }


async def collision(env):
    provider = await svc.create_provider("dom-a", actor_user_id="manager", fields=oidc_fields())
    state, browser = await start(env.wire.idp, provider["id"])
    with pytest.raises(svc.AccountLinkRequired) as caught:
        await svc.complete_authorization("good-code", state, browser)
    return provider, caught.value.link_token, browser


async def test_admission_configuration_is_exact_inherited_and_provider_selected(env):
    provider = await svc.create_provider("dom-a", actor_user_id="manager", fields=oidc_fields())
    env.settings.auth = AuthSettings.model_validate(
        {
            "default": {
                "allow_providers": [provider["id"]],
                "auto_join_email_domains": {provider["id"]: ["CORP.example.", "bücher.example"]},
            },
            "domain": {"dom-b": {"auto_join_email_domains": {}}},
            "public_signup_enabled": True,
            "signup_email_domains": ["CORP.example"],
        }
    )
    assert env.settings.auth.signup_email_domains == ["corp.example"]
    assert await svc.provider_auto_join_allowed("dom-a", provider["id"], "a@CORP.example")
    assert await svc.provider_auto_join_allowed("dom-a", provider["id"], "a@bücher.example")
    for email in ("a@sub.corp.example", "a@corp.example.evil", "a@other.example"):
        assert not await svc.provider_auto_join_allowed("dom-a", provider["id"], email)
    assert not await svc.provider_auto_join_allowed("dom-b", provider["id"], "a@corp.example")
    env.settings.auth.default.allow_providers = []
    assert not await svc.provider_auto_join_allowed("dom-a", provider["id"], "a@corp.example")


@pytest.mark.parametrize("domains", [["*.example.com"], ["@example.com"], ["localhost"]])
def test_invalid_admission_domains_are_rejected_without_network(domains):
    with pytest.raises(ValidationError):
        AuthSettings.model_validate({"default": {"auto_join_email_domains": {"unknown": domains}}})


async def test_link_confirms_attachment_without_login_then_fresh_callback_issues_session(api, env, monkeypatch):
    user = unbound(env)
    authenticate = Mock(return_value=proof())
    monkeypatch.setattr(keystone, "authenticate", authenticate)
    provider = await svc.create_provider("dom-a", actor_user_id="manager", fields=oidc_fields())
    async with api.client as client:
        begun = await client.post(f"/api/v1/auth/domains/dom-a/providers/{provider['id']}/authorize")
        state = env.wire.idp.remember(begun.json()["authorize_url"])
        browser = client.cookies.get(svc.STATE_COOKIE)
        result = await client.post("/api/v1/auth/providers/callback", json={"code": "good-code", "state": state})
        assert result.status_code == 409
        assert result.json()["code"] == "account_link_required" and result.json()["domain_id"] == "dom-a"
        ticket = result.json()["link_token"]
        assert client.cookies.get(svc.STATE_COOKIE) == browser
        assert result.headers["referrer-policy"] == "no-referrer"
        assert env.wire.federation.calls == [] and env.keystone.user_writes == []
        raw = await (await svc._redis()).get("afterglow:domain_auth:link:" + svc._digest(ticket))
        assert "bearer" not in raw and "subject-1" not in raw
        # A saved association must not depend on the subsequent native login exchange.
        env.wire.federation.status = 503
        linked = await client.post(
            "/api/v1/auth/providers/link",
            json={"link_token": ticket, "username": "dev", "password": "original-password"},
        )
        assert linked.status_code == 200, linked.text
        assert linked.json() == {
            "linked": True,
            "domain_id": "dom-a",
            "domain_name": "Alpha",
            "provider_id": provider["id"],
        }
        assert env.wire.federation.calls == []
        assert api.native_validations == [] and api.native_preparations == []
        assert await (await svc._redis()).keys("afterglow:refresh:*") == []
        assert (await svc.list_providers("dom-a"))[0]["verified"] is False
        assert client.cookies.get(svc.STATE_COOKIE) is None
        authenticate.assert_called_once()
        assert {
            key: authenticate.call_args.kwargs[key] for key in ("username", "password", "project_name", "domain_name")
        } == {"username": "dev", "password": "original-password", "project_name": "", "domain_name": "dom-a"}
        assert user.afterglow_local_password is True
        assert user.default_project_id == "saved-native-preference"
        assert len(env.keystone.user_rows) == 1
        fields = env.keystone.user_writes[-1][2]
        assert not {"password", "name", "domain", "email", "default_project_id"} & fields.keys()
        assert fields["federated"][0]["protocols"] == [{"protocol_id": "openid", "unique_id": "subject-1"}]
        assert "password-proof" in env.keystone.revoked
        replay = await client.post(
            "/api/v1/auth/providers/link",
            json={"link_token": ticket, "username": "dev", "password": "original-password"},
        )
        assert replay.status_code == 401 and replay.json()["code"] == "invalid_link_token"
        env.wire.federation.status = 201
        begun = await client.post(f"/api/v1/auth/domains/dom-a/providers/{provider['id']}/authorize")
        fresh_state = env.wire.idp.remember(begun.json()["authorize_url"])
        signed_in = await client.post(
            "/api/v1/auth/providers/callback", json={"code": "good-code", "state": fresh_state}
        )
        assert signed_in.status_code == 200, signed_in.text
        assert signed_in.json()["user_id"] == "fed-user"
        assert signed_in.json()["identity_domain_id"] == "dom-a"
        assert signed_in.json()["domain_id"] == "dom-a" and signed_in.json()["project_id"] == "default-a"
        claims = jwt_service.verify_refresh(signed_in.json()["refresh_token"])
        saved = await session_store.get_session(claims["jti"])
        assert saved["provider_domain_id"] == "dom-a"
        assert (await svc.list_providers("dom-a"))[0]["verified"] is True


async def test_link_does_not_confirm_an_attachment_that_native_readback_did_not_persist(api, env, monkeypatch):
    user = unbound(env)
    monkeypatch.setattr(keystone, "authenticate", Mock(return_value=proof()))
    provider = await svc.create_provider("dom-a", actor_user_id="manager", fields=oidc_fields())
    # Native accepted the request but did not persist the external association.
    monkeypatch.setattr(env.keystone.users, "update", lambda uid, **fields: env.keystone.user_rows[uid])
    async with api.client as client:
        begun = await client.post(f"/api/v1/auth/domains/dom-a/providers/{provider['id']}/authorize")
        state = env.wire.idp.remember(begun.json()["authorize_url"])
        pending = await client.post("/api/v1/auth/providers/callback", json={"code": "good-code", "state": state})
        linked = await client.post(
            "/api/v1/auth/providers/link",
            json={"link_token": pending.json()["link_token"], "username": "dev", "password": "original-password"},
        )
        assert linked.status_code == 503 and linked.json()["code"] == "native_attachment_unconfirmed"
        assert "linked" not in linked.json() and client.cookies.get(svc.STATE_COOKIE) is None
        assert user.federated == [] and user.afterglow_external_identities == []
        assert env.wire.federation.calls == [] and api.native_validations == []
        assert await (await svc._redis()).keys("afterglow:refresh:*") == []


@pytest.mark.parametrize("failure", ["browser", "subject", "revision"])
async def test_link_proof_binding_fails_before_any_native_write(env, monkeypatch, failure):
    unbound(env)
    provider, ticket, browser = await collision(env)
    authenticate = Mock(return_value=proof(user_id="unrelated" if failure == "subject" else "fed-user"))
    monkeypatch.setattr(keystone, "authenticate", authenticate)
    if failure == "revision":
        await svc.update_provider("dom-a", provider["id"], actor_user_id="manager", fields={"client_id": "changed"})
    with pytest.raises(svc.DomainAuthError) as caught:
        await svc.complete_account_link(
            ticket, "wrong-browser" if failure == "browser" else browser, username="dev", password="original-password"
        )
    assert (
        caught.value.code
        == {"browser": "invalid_link_token", "subject": "account_proof_mismatch", "revision": "provider_changed"}[
            failure
        ]
    )
    assert env.keystone.user_writes == [] and env.wire.federation.calls == []
    if failure != "subject":
        authenticate.assert_not_called()


async def test_expired_link_ticket_is_not_an_email_login_fallback(env, monkeypatch):
    unbound(env)
    _, ticket, browser = await collision(env)
    await (await svc._redis()).delete("afterglow:domain_auth:link:" + svc._digest(ticket))
    authenticate = Mock()
    monkeypatch.setattr(keystone, "authenticate", authenticate)
    with pytest.raises(svc.DomainAuthUnauthenticated) as caught:
        await svc.complete_account_link(ticket, browser, username="dev", password="original-password")
    assert caught.value.code == "invalid_link_token"
    authenticate.assert_not_called()
    assert env.keystone.user_writes == []


async def test_authenticated_external_only_proof_endpoint(api, env, monkeypatch):
    from app.api.deps import get_token_info

    user = unbound(env)
    user.afterglow_local_password = False
    original_validate = keystone.validate_token
    monkeypatch.setattr(
        keystone,
        "validate_token",
        lambda token, *args, **kwargs: (
            proof(token="authenticated-native")
            if token == "authenticated-native"
            else original_validate(token, *args, **kwargs)
        ),
    )
    origin = await authenticated_session(env, "oidc")
    api.app.dependency_overrides[get_token_info] = lambda: origin
    provider = await svc.create_provider("dom-a", actor_user_id="manager", fields=oidc_fields())
    async with api.client as client:
        begun = await client.post(f"/api/v1/auth/domains/dom-a/providers/{provider['id']}/authorize")
        state = env.wire.idp.remember(begun.json()["authorize_url"])
        pending = await client.post("/api/v1/auth/providers/callback", json={"code": "good-code", "state": state})
        linked = await client.post(
            "/api/v1/auth/providers/link/authenticated", json={"link_token": pending.json()["link_token"]}
        )
        assert linked.status_code == 200, linked.text
        assert linked.json() == {
            "linked": True,
            "domain_id": "dom-a",
            "domain_name": "Alpha",
            "provider_id": provider["id"],
        }
        assert user.afterglow_local_password is False and env.wire.federation.calls == []
        assert "authenticated-native" not in env.keystone.revoked


async def test_duplicate_email_is_ambiguous_before_native_provisioning(env):
    user = unbound(env)
    env.keystone.user_rows["duplicate"] = SimpleNamespace(
        id="duplicate", name="copy", email=user.email.lower(), domain_id="dom-b", enabled=True
    )
    provider = await svc.create_provider("dom-a", actor_user_id="manager", fields=oidc_fields())
    state, browser = await start(env.wire.idp, provider["id"])
    with pytest.raises(svc.DomainAuthConflict) as caught:
        await svc.complete_authorization("good-code", state, browser)
    assert caught.value.code == "account_ambiguous"
    assert env.keystone.user_writes == [] and env.wire.federation.calls == []


@pytest.mark.parametrize("admit", [False, True])
async def test_new_external_native_creation_requires_explicit_admission(external_env, admit):
    env = external_env
    provider = await external_provider(env)
    if not admit:
        env.settings.auth.default.auto_join_email_domains.clear()
    state, browser = await start(env.wire.idp, provider["id"])
    if not admit:
        with pytest.raises(svc.DomainAuthDenied) as caught:
            await svc.complete_authorization("good-code", state, browser)
        assert caught.value.code == "invitation_required"
        assert env.keystone.user_writes == [] and env.wire.federation.calls == []
    else:
        result = await svc.complete_authorization("good-code", state, browser)
        assert result.user_id == "new-user"
        user = env.keystone.user_rows["new-user"]
        assert user.afterglow_local_password is False
        assert user.afterglow_external_identities == [{"issuer": ISSUER, "subject": "subject-1"}]
        assert "password" not in env.keystone.user_writes[0][2]
        assert user.domain_id != "dom-a"
        assert env.quota_applications


@pytest.mark.parametrize(
    "mapped_user",
    [
        {"name": "{0}"},
        {"id": "{0}", "email": "{1}"},
        {"id": "{0}", "type": "local"},
    ],
)
async def test_unsafe_native_mapping_is_rejected_before_any_provisioning(env, mapped_user):
    env.keystone.mapping_rules = [{"local": [{"user": mapped_user}], "remote": [{"type": "OIDC-preferred_username"}]}]
    provider = await svc.create_provider("dom-a", actor_user_id="manager", fields=oidc_fields())
    state, browser = await start(env.wire.idp, provider["id"])
    with pytest.raises(svc.DomainAuthUnavailable) as caught:
        await svc.complete_authorization("good-code", state, browser)
    assert caught.value.code == "native_mapping_unsafe"
    assert env.keystone.user_writes == [] and env.wire.federation.calls == []


async def test_explicit_proof_migrates_legacy_tuple_using_exact_native_quoted_subject(env, monkeypatch):
    user = unbound(env)
    user.federated = [{"idp_id": "idp-a", "protocols": [{"protocol_id": "openid", "unique_id": "old-username"}]}]
    env.wire.idp.claims["sub"] = "stable:subject /한글"
    _, ticket, browser = await collision(env)
    monkeypatch.setattr(keystone, "authenticate", Mock(return_value=proof()))
    result = await svc.complete_account_link(ticket, browser, username="dev", password="original-password")
    assert result["linked"] is True and result["domain_id"] == "dom-a"
    assert user.federated[0]["protocols"][0]["unique_id"] == quote("stable:subject /한글")
    assert user.afterglow_external_identities == [{"issuer": ISSUER, "subject": "stable:subject /한글"}]


async def test_fresh_native_login_after_link_keeps_subject_authoritative_and_revokes_mismatch(env, monkeypatch):
    unbound(env)
    _, ticket, browser = await collision(env)
    monkeypatch.setattr(keystone, "authenticate", Mock(return_value=proof()))
    await svc.complete_account_link(ticket, browser, username="dev", password="original-password")
    provider = (await svc.list_providers("dom-a"))[0]
    state, browser = await start(env.wire.idp, provider["id"])
    env.wire.federation.user_id = "unexpected-shadow"
    with pytest.raises(svc.DomainAuthDenied) as caught:
        await svc.complete_authorization("good-code", state, browser)
    assert caught.value.code == "canonical_subject_mismatch"
    assert "unscoped-fed" in env.keystone.revoked
    assert not any(kind == "create" for kind, _, _ in env.keystone.user_writes)


async def test_email_change_in_native_mapper_is_rejected_and_token_revoked(env, monkeypatch):
    provider = await svc.create_provider("dom-a", actor_user_id="manager", fields=oidc_fields())
    original_federate = svc.keystone_federate

    async def unsafe_native(row, bearer):
        result = await original_federate(row, bearer)
        env.keystone.user_rows["fed-user"].email = "unexpected@corp.example"
        return result

    monkeypatch.setattr(svc, "keystone_federate", unsafe_native)
    state, browser = await start(env.wire.idp, provider["id"])
    with pytest.raises(svc.DomainAuthDenied) as caught:
        await svc.complete_authorization("good-code", state, browser)
    assert caught.value.code == "canonical_email_mismatch"
    assert env.keystone.revoked == ["unscoped-fed"]


async def test_autojoin_does_not_bootstrap_owner_for_unprepared_existing_domain(env):
    env.keystone.user_rows.clear()
    provider = await svc.create_provider("dom-a", actor_user_id="manager", fields=oidc_fields())
    env.settings.auth = AuthSettings.model_validate(
        {"default": {"auto_join_email_domains": {provider["id"]: ["corp.example"]}}}
    )
    state, browser = await start(env.wire.idp, provider["id"])
    with pytest.raises(svc.DomainAuthConflict) as caught:
        await svc.complete_authorization("good-code", state, browser)
    assert caught.value.code == "domain_default_required"
    assert env.keystone.user_writes == [] and env.wire.federation.calls == []


async def test_configured_auto_admission_adds_only_default_reader_after_canonical_proof(env, monkeypatch):
    from fastapi import HTTPException

    from app.services import domain_projects

    user = unbound(env)
    user.domain_id = "dom-b"
    env.wire.federation.domain_id = "dom-b"
    provider, ticket, browser = await collision(env)
    env.settings.auth = AuthSettings.model_validate(
        {"default": {"auto_join_email_domains": {provider["id"]: ["corp.example"]}}}
    )
    granted = []

    def membership(uid, did, **kwargs):
        if not granted:
            raise HTTPException(403, "domain_membership_denied")

    async def reader(lease, ks, catalog, pid, uid):
        granted.append((pid, uid))

    async def sync(*args, **kwargs):
        return None

    monkeypatch.setattr(domain_projects, "assert_membership", membership)
    monkeypatch.setattr(domain_projects, "default_project", lambda did, **_: {"id": "prepared-default"})
    monkeypatch.setattr(domain_projects, "_ensure_reader", reader)
    monkeypatch.setattr(domain_projects, "_sync", sync)
    monkeypatch.setattr(
        keystone, "authenticate", Mock(return_value=proof(identity_domain_id="dom-b", domain_id="dom-b"))
    )
    result = await svc.complete_account_link(ticket, browser, username="dev", password="original-password")
    assert result["linked"] is True and result["domain_id"] == "dom-a" and user.domain_id == "dom-b"
    assert granted == [("prepared-default", "fed-user")]
    assert not any(kind == "create" for kind, _, _ in env.keystone.user_writes)


async def test_password_link_honors_existing_canonical_account_lock(api, env, monkeypatch):
    import time

    from app.services import login_guard

    unbound(env)
    provider = await svc.create_provider("dom-a", actor_user_id="manager", fields=oidc_fields())
    authenticate = Mock()
    monkeypatch.setattr(keystone, "authenticate", authenticate)
    redis = await svc._redis()
    await redis.set(login_guard._lock_key("dev", "dom-a"), str(time.time() + 60), ex=60)
    async with api.client as client:
        begun = await client.post(f"/api/v1/auth/domains/dom-a/providers/{provider['id']}/authorize")
        state = env.wire.idp.remember(begun.json()["authorize_url"])
        collision_result = await client.post(
            "/api/v1/auth/providers/callback", json={"code": "good-code", "state": state}
        )
        linked = await client.post(
            "/api/v1/auth/providers/link",
            json={
                "link_token": collision_result.json()["link_token"],
                "username": "dev",
                "password": "original-password",
            },
        )
        assert linked.status_code == 429 and "Retry-After" in linked.headers
    authenticate.assert_not_called()
    assert env.keystone.user_writes == [] and env.wire.federation.calls == []


@pytest.mark.parametrize("rejection", ["password", "authorization", "transport"])
async def test_password_link_counts_only_real_native_password_rejections(env, monkeypatch, rejection):
    from fastapi import HTTPException
    from keystoneauth1.exceptions.http import Unauthorized

    from app.services import login_guard

    unbound(env)
    _, ticket, browser = await collision(env)
    error = {
        "password": keystone.PasswordRejected(message="Rejected password"),
        "authorization": Unauthorized(message="Disabled account"),
        "transport": HTTPException(503, "Native transport unavailable"),
    }[rejection]
    monkeypatch.setattr(keystone, "authenticate", Mock(side_effect=error))
    with pytest.raises((svc.DomainAuthUnauthenticated, HTTPException)):
        await svc.complete_account_link(ticket, browser, username="dev", password="incorrect")
    count = await (await svc._redis()).get(login_guard._fail_key("dev", "dom-a"))
    assert (int(count) if count else 0) == (1 if rejection == "password" else 0)


async def test_password_link_clears_guard_only_after_exact_canonical_proof(env, monkeypatch):
    from app.services import login_guard

    unbound(env)
    provider, ticket, browser = await collision(env)
    redis = await svc._redis()
    fail_key = login_guard._fail_key("dev", "dom-a")
    await redis.set(fail_key, 1, ex=60)
    authenticate = Mock(return_value=proof(user_id="unrelated"))
    monkeypatch.setattr(keystone, "authenticate", authenticate)
    with pytest.raises(svc.DomainAuthDenied):
        await svc.complete_account_link(ticket, browser, username="dev", password="original-password")
    assert int(await redis.get(fail_key)) == 1
    state, browser = await start(env.wire.idp, provider["id"])
    with pytest.raises(svc.AccountLinkRequired) as pending:
        await svc.complete_authorization("good-code", state, browser)
    authenticate.return_value = proof()
    await svc.complete_account_link(pending.value.link_token, browser, username="dev", password="original-password")
    assert await redis.get(fail_key) is None


@pytest.mark.parametrize(
    "extra_local",
    [
        {"group": {"id": "privileged-native-group"}},
        {"projects": [{"name": "Default", "roles": [{"name": "admin"}]}]},
    ],
)
async def test_native_mapping_cannot_grant_roles_outside_configured_admission(env, extra_local):
    env.keystone.mapping_rules = [{"local": [{"user": {"id": "{0}"}}, extra_local], "remote": [{"type": "OIDC-sub"}]}]
    provider = await svc.create_provider("dom-a", actor_user_id="manager", fields=oidc_fields())
    state, browser = await start(env.wire.idp, provider["id"])
    with pytest.raises(svc.DomainAuthUnavailable) as caught:
        await svc.complete_authorization("good-code", state, browser)
    assert caught.value.code == "native_mapping_unsafe"
    assert env.keystone.user_writes == [] and env.wire.federation.calls == []


@pytest.mark.parametrize(
    "incomplete",
    [
        {"links": {"next": "https://native.test/v3/users?marker=more"}},
        {"links": {"next": None}, "truncated": True},
        {"links": {"next": None}, "limited": True},
        {"links": None},
    ],
)
async def test_federation_incomplete_native_inventory_cannot_provision_or_link(env, incomplete):
    provider = await svc.create_provider("dom-a", actor_user_id="manager", fields=oidc_fields())
    unbound(env)
    # SDK list() normally discards these collection-level completeness signals.
    env.keystone.users.client = SimpleNamespace(
        get=lambda url: (None, {"users": [{"id": "fed-user", "domain_id": "dom-a"}], **incomplete})
    )
    state, browser = await start(env.wire.idp, provider["id"])
    with pytest.raises(svc.DomainAuthUnavailable) as caught:
        await svc.complete_authorization("good-code", state, browser)
    assert caught.value.status_code == 503
    assert env.keystone.user_writes == [] and env.wire.federation.calls == []


@pytest.mark.parametrize(
    "incomplete",
    [
        {"links": {"next": "/users?marker=more"}},
        {"links": {}, "truncated": True},
        {"links": {}, "limited": True},
    ],
)
async def test_link_rechecks_inventory_completeness_after_password_proof(env, monkeypatch, incomplete):
    unbound(env)
    _, ticket, browser = await collision(env)
    authenticate = Mock(return_value=proof())
    monkeypatch.setattr(keystone, "authenticate", authenticate)
    env.keystone.users.client = SimpleNamespace(get=lambda url: (None, {"users": [], **incomplete}))
    with pytest.raises(svc.DomainAuthUnavailable) as caught:
        await svc.complete_account_link(ticket, browser, username="dev", password="original-password")
    assert caught.value.status_code == 503
    authenticate.assert_called_once()
    assert env.keystone.user_writes == [] and env.wire.federation.calls == []


async def test_native_list_projection_is_hydrated_before_email_and_stable_subject_resolution(env):
    provider = await svc.create_provider("dom-a", actor_user_id="manager", fields=oidc_fields())
    # Collection omits email, native federated tuples, and custom issuer metadata;
    # exact GET still owns all three, so this must neither create nor issue a link.
    env.keystone.users.client = SimpleNamespace(
        get=lambda url: (None, {"users": [{"id": "fed-user", "domain_id": "dom-a"}], "links": {"next": None}})
    )
    state, browser = await start(env.wire.idp, provider["id"])
    result = await svc.complete_authorization("good-code", state, browser)
    assert result.user_id == "fed-user"
    assert env.keystone.user_writes == []
    assert len(env.wire.federation.calls) == 1


async def test_hydrated_duplicate_email_blocks_provisioning_when_lists_omit_email(env):
    user = unbound(env)
    env.keystone.user_rows["duplicate"] = SimpleNamespace(
        id="duplicate", domain_id="dom-b", name="duplicate", enabled=True, email=user.email.lower()
    )
    env.keystone.users.client = SimpleNamespace(
        get=lambda url: (
            None,
            {
                "users": [{"id": uid, "domain_id": user.domain_id} for uid, user in env.keystone.user_rows.items()],
                "links": {"next": None},
            },
        )
    )
    provider = await svc.create_provider("dom-a", actor_user_id="manager", fields=oidc_fields())
    state, browser = await start(env.wire.idp, provider["id"])
    with pytest.raises(svc.DomainAuthConflict) as caught:
        await svc.complete_authorization("good-code", state, browser)
    assert caught.value.code == "account_ambiguous"
    assert env.keystone.user_writes == [] and env.wire.federation.calls == []


@pytest.mark.parametrize("incomplete", ["next", "truncated", "limited", "missing_links"])
def test_password_selection_refuses_partial_inventory_before_native_attempt(keystone_admin, incomplete):
    from app.services.account_identity import password_account
    from app.services.native_operation import NativeOperation

    calls = []

    def collection(url):
        calls.append(url)
        body = {"users": [{"id": "fed-user", "domain_id": "dom-a"}], "links": {"next": None}}
        if incomplete == "next":
            body["links"]["next"] = "/users?marker=hidden-duplicate"
        elif incomplete == "missing_links":
            del body["links"]
        else:
            body[incomplete] = True
        return None, body

    keystone_admin.users.client = SimpleNamespace(get=collection)
    operation = NativeOperation()
    operation._ks = keystone_admin
    with pytest.raises(svc.DomainAuthUnavailable):
        password_account("dev", operation=operation)
    assert calls == ["/users"]
    assert keystone_admin.user_writes == []


@pytest.mark.parametrize("revoked", ["password", "native", "application"])
async def test_recovery_before_link_lease_prevents_persistent_attachment(env, monkeypatch, revoked):
    from contextlib import asynccontextmanager

    from keystoneauth1.exceptions.http import Unauthorized

    from app.services import domain_iam

    unbound(env)
    _, ticket, browser = await collision(env)
    origin = await authenticated_session(env)
    live = True

    def native_proof(*args, **kwargs):
        if not live:
            raise keystone.PasswordRejected(message="Recovered credential")
        return proof(token="authenticated-native")

    monkeypatch.setattr(keystone, "authenticate", native_proof)
    monkeypatch.setattr(keystone, "validate_token", native_proof)
    guard = domain_iam._iam_write

    @asynccontextmanager
    async def recovered_first():
        nonlocal live
        async with guard() as resources:
            if revoked == "application":
                await session_store.delete_session("link-origin")
            else:
                live = False
            yield resources

    monkeypatch.setattr(domain_iam, "_iam_write", recovered_first)
    values = (
        {"username": "dev", "password": "original-password"} if revoked == "password" else {"authenticated": origin}
    )
    with pytest.raises((svc.DomainAuthUnauthenticated, Unauthorized)):
        await svc.complete_account_link(ticket, browser, **values)
    assert env.keystone.user_writes == [] and env.wire.federation.calls == []


async def test_password_origin_authenticated_link_preserves_legacy_local_recovery(env, monkeypatch):
    from app.services import account_recovery

    user = unbound(env)
    _, ticket, browser = await collision(env)
    origin = await authenticated_session(env)
    monkeypatch.setattr(keystone, "validate_token", lambda *args, **kwargs: proof(token="authenticated-native"))
    await svc.complete_account_link(ticket, browser, authenticated=origin)
    assert getattr(user, "afterglow_local_password", None) is True
    assert await account_recovery._eligible(user, env.keystone, [])
