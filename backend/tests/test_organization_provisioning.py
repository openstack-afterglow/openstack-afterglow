"""Configured OIDC organization consumers: real SQL and native role readback.

Signed IdP/native federation wires and domain creation are controlled doubles;
no live Keystone provisioning capability is claimed by these tests.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.auth_settings import AuthSettings
from app.models.organization_provisioning import OrganizationBinding
from app.services import domain_auth as auth
from app.services import domain_projects, organization_provisioning, project_service
from tests.test_domain_auth import ISSUER, configure_file_auth, oidc_fields, start
from tests.test_domain_auth import db as db
from tests.test_domain_auth import env as env
from tests.test_domain_auth import keystone_admin as keystone_admin
from tests.test_domain_auth import public_dns as public_dns
from tests.test_domain_auth import settings as settings
from tests.test_domain_auth import wire as wire
from tests.test_project_membership_roles import Membership, rid


@pytest.fixture
async def org_env(env, monkeypatch):
    env.keystone.catalog = Membership().catalog
    env.settings.auth = AuthSettings.model_validate(
        {
            "providers": {
                "org": oidc_fields(
                    organization={
                        "id": "stable-tenant-id",
                        "name": "Organization",
                        "manager_subjects": ["subject-1"],
                    }
                )
            }
        }
    )
    env.org_creates = []

    async def create_domain(**kwargs):
        # Exercise this service's exact interface/metadata while isolating the
        # parent's separately-tested quota/owner/projection bootstrap lifecycle.
        env.org_creates.append(kwargs)
        assert kwargs["mutation"][1] is env.keystone
        did = env.keystone.domains.create(
            name="native-org",
            enabled=True,
            afterglow_display_name=kwargs["name"],
            afterglow_domain_kind="organization",
            afterglow_created_by=kwargs["creator_id"],
            **kwargs["metadata"],
        ).id
        pid = env.keystone.projects.create(name="Default", domain=did, enabled=True, parent_id=None).id
        for role in ("manager", "project_owner", "project_reader"):
            env.keystone.roles.grant(rid(role), user=kwargs["creator_id"], project=pid)
        return {"id": did, "default_project_id": pid}

    monkeypatch.setattr(domain_projects, "create_domain", create_domain)
    monkeypatch.setattr(domain_projects, "_sync", AsyncMock())
    monkeypatch.setattr(domain_projects, "_invalidate", AsyncMock())
    env.wire.federation.native_users = env.keystone.user_rows
    return env


async def callback(env):
    state, browser = await start(env.wire.idp, "cfg:org")
    return await auth.complete_authorization("good-code", state, browser)


async def binding(env):
    async with env.db() as session:
        return (await session.execute(select(OrganizationBinding))).scalar_one()


def ordinary_subject(env, subject="ordinary-subject"):
    env.wire.idp.claims = {"sub": subject, "email": "ordinary@corp.example"}
    env.wire.federation.user_id = "ordinary-user"
    env.keystone.user_rows["ordinary-user"] = SimpleNamespace(
        id="ordinary-user",
        name="ordinary",
        email="ordinary@corp.example",
        domain_id="dom-a",
        enabled=True,
        federated=[{"idp_id": "idp-a", "protocols": [{"protocol_id": "openid", "unique_id": subject}]}],
        afterglow_external_identities=[{"issuer": ISSUER, "subject": subject}],
    )


async def test_manager_callback_creates_one_org_with_same_canonical_user(org_env):
    env = org_env
    first = await callback(env)
    saved = await binding(env)
    assert first.user_id == "fed-user" and first.domain_id == "dom-a"  # provider origin stays separate
    assert saved.status == "active" and saved.creator_user_id == first.user_id
    assert saved.binding_key == organization_provisioning.binding_key(ISSUER, "stable-tenant-id")
    assert len(env.keystone.user_rows) == 1 and len(env.org_creates) == 1
    project = domain_projects.default_project(saved.domain_id, ks=env.keystone)
    roles = project_service._direct_ids(env.keystone.role_assignments.list(project=project["id"]), first.user_id)
    assert roles == {rid("manager"), rid("project_owner"), rid("project_reader")}
    again = await callback(env)
    assert again.user_id == first.user_id and len(env.org_creates) == 1
    # Name/provider alias changes are not a second organization identity.
    provider = env.settings.auth.providers.pop("org")
    provider.organization.name = "Renamed"
    env.settings.auth.providers["renamed"] = provider
    state, browser = await start(env.wire.idp, "cfg:renamed")
    renamed = await auth.complete_authorization("good-code", state, browser)
    assert renamed.user_id == first.user_id and len(env.org_creates) == 1


async def test_ordinary_subject_joins_existing_org_as_reader_not_manager(org_env):
    env = org_env
    await callback(env)
    saved = await binding(env)
    ordinary_subject(env)
    login = await callback(env)
    project = domain_projects.default_project(saved.domain_id, ks=env.keystone)
    roles = project_service._direct_ids(env.keystone.role_assignments.list(project=project["id"]), login.user_id)
    assert roles == {rid("project_reader")}
    assert not domain_projects.has_manager(login.user_id, saved.domain_id, ks=env.keystone)
    assert len(env.org_creates) == 1 and (await binding(env)).status == "active"


async def test_email_host_never_bootstraps_first_manager(org_env):
    ordinary_subject(org_env)
    # Missing native tuple: attach would write if admission were decided too late.
    org_env.keystone.user_rows["ordinary-user"].federated = []
    with pytest.raises(auth.DomainAuthDenied) as denied:
        await callback(org_env)
    assert denied.value.code == "organization_manager_required"
    assert not org_env.org_creates and not org_env.wire.federation.calls and org_env.keystone.user_writes == []
    async with org_env.db() as session:
        assert (await session.execute(select(OrganizationBinding))).scalars().all() == []


async def test_changed_native_binding_denied_but_client_rotation_is_not_identity(org_env):
    env = org_env
    await callback(env)
    saved = await binding(env)
    env.keystone.domain_rows[saved.domain_id].afterglow_organization_id = "changed"
    with pytest.raises(auth.DomainAuthConflict) as changed:
        await callback(env)
    assert changed.value.code == "organization_binding_changed" and len(env.org_creates) == 1
    env.keystone.domain_rows[saved.domain_id].afterglow_organization_id = "stable-tenant-id"
    row = await auth._load_config_provider("dom-a", "cfg:org")
    row.client_id = "different-tenant-client"
    identity = auth.VerifiedIdentity("dev@corp.example", "unused", ISSUER, "subject-1")
    domain_id = await organization_provisioning.admit(
        row, identity, env.keystone.users.get("fed-user"), lease=row, ks=env.keystone, catalog=env.keystone.catalog
    )
    assert domain_id == saved.domain_id and len(env.org_creates) == 1


async def test_refresh_rechecks_configured_organization_even_outside_its_workspace(org_env):
    from app.api.identity import auth as auth_api

    await callback(org_env)
    saved = await binding(org_env)
    ordinary_subject(org_env)
    login = await callback(org_env)
    provider = await auth._load_config_provider("dom-a", "cfg:org")
    session = {
        "auth_method": "oidc",
        "identity_domain_id": "dom-a",
        "provider_id": provider.id,
        "provider_revision": provider.revision,
        "provider_domain_id": "dom-a",
        "login_email": login.login_email,
    }
    identity = {
        "user_id": login.user_id,
        "identity_domain_id": "dom-a",
        "domain_id": "dom-a",
        "email": login.login_email,
    }
    await auth_api._enforce_session_policy(session, identity)
    project = domain_projects.default_project(saved.domain_id, ks=org_env.keystone)
    org_env.keystone.roles.revoke(rid("project_reader"), user=login.user_id, project=project["id"])
    with pytest.raises(HTTPException) as denied:
        await auth_api._enforce_session_policy(session, identity)
    assert denied.value.status_code == 403


async def test_uncertain_native_create_is_never_replayed(org_env, monkeypatch):
    env = org_env
    original = domain_projects.create_domain

    async def committed_then_timeout(**kwargs):
        await original(**kwargs)
        raise HTTPException(503, "native_create_result_unknown")

    monkeypatch.setattr(domain_projects, "create_domain", committed_then_timeout)
    with pytest.raises(HTTPException):
        await callback(env)
    assert (await binding(env)).status == "uncertain"
    with pytest.raises(auth.DomainAuthUnavailable) as replay:
        await callback(env)
    assert replay.value.code == "organization_operation_uncertain" and len(env.org_creates) == 1


async def test_definite_predispatch_rejection_releases_creation_intent(org_env, monkeypatch):
    original = domain_projects.create_domain

    async def disabled(**kwargs):
        error = HTTPException(403, "organization_creation_disabled")
        error.native_create_dispatched = False
        raise error

    monkeypatch.setattr(domain_projects, "create_domain", disabled)
    with pytest.raises(HTTPException):
        await callback(org_env)
    async with org_env.db() as session:
        assert (await session.execute(select(OrganizationBinding))).scalars().all() == []
    monkeypatch.setattr(domain_projects, "create_domain", original)
    await callback(org_env)
    assert len(org_env.org_creates) == 1 and (await binding(org_env)).status == "active"


async def test_member_grant_failure_never_locks_entire_organization(org_env, monkeypatch):
    env = org_env
    await callback(env)
    ordinary_subject(env)
    original = domain_projects._ensure_reader
    monkeypatch.setattr(domain_projects, "_ensure_reader", AsyncMock(side_effect=HTTPException(503, "native_down")))
    with pytest.raises(HTTPException):
        await callback(env)
    assert (await binding(env)).status == "active"
    monkeypatch.setattr(domain_projects, "_ensure_reader", original)
    login = await callback(env)
    assert login.user_id == "ordinary-user" and len(env.org_creates) == 1


@pytest.mark.parametrize("boundary,error", [("organization", auth.DomainAuthDenied), ("user", auth.DomainAuthConflict)])
async def test_current_native_enabled_boundaries_are_authoritative(org_env, boundary, error):
    env = org_env
    await callback(env)
    saved = await binding(env)
    domain_id = saved.domain_id if boundary == "organization" else None
    target = env.keystone.domains.get(domain_id) if domain_id else env.keystone.users.get("fed-user")
    target.enabled = False
    calls = len(env.wire.federation.calls)
    with pytest.raises(error) as denied:
        await callback(env)
    if boundary == "organization":
        assert denied.value.code == "organization_disabled"
    assert len(env.wire.federation.calls) == calls


async def test_generic_common_provider_does_not_require_or_grant_origin_membership(env, monkeypatch):
    from app.services import account_identity

    configure_file_auth(env.settings)
    admission = AsyncMock(side_effect=AssertionError("Common provider origin is not membership authority"))
    monkeypatch.setattr(account_identity, "require_admission", admission)
    state, browser = await start(env.wire.idp, "cfg:corp")
    login = await auth.complete_authorization("good-code", state, browser)
    assert login.user_id == "fed-user" and not env.keystone.assignments
    admission.assert_not_awaited()


async def test_organization_config_edit_invalidates_pending_state_before_exchange(env):
    configure_file_auth(
        env.settings,
        providers={
            "corp": oidc_fields(
                organization={
                    "id": "stable-org",
                    "name": "First",
                    "manager_subjects": ["subject-1"],
                }
            )
        },
    )
    state, browser = await start(env.wire.idp, "cfg:corp")
    env.settings.auth.providers["corp"].organization.manager_subjects = ["different-subject"]
    before = len([request for request in env.wire.idp.requests if request.url.path == "/token"])
    with pytest.raises(auth.DomainAuthConflict) as stale:
        await auth.complete_authorization("good-code", state, browser)
    assert stale.value.code == "provider_changed"
    assert len([request for request in env.wire.idp.requests if request.url.path == "/token"]) == before


async def test_untracked_native_binding_is_not_adopted_or_duplicated(org_env):
    org_env.keystone.domains.create(
        name="untracked",
        enabled=True,
        afterglow_organization_binding=organization_provisioning.binding_key(ISSUER, "stable-tenant-id"),
    )
    with pytest.raises(auth.DomainAuthConflict) as unknown:
        await callback(org_env)
    assert unknown.value.code == "organization_binding_unknown" and not org_env.org_creates


async def test_org_disable_during_native_federation_revokes_unpublished_token(org_env, monkeypatch):
    await callback(org_env)
    saved = await binding(org_env)
    original = auth.keystone_federate

    async def disable_during_exchange(*args):
        result = await original(*args)
        org_env.keystone.domains.get(saved.domain_id).enabled = False
        return result

    monkeypatch.setattr(auth, "keystone_federate", disable_during_exchange)
    with pytest.raises(auth.DomainAuthDenied) as disabled:
        await callback(org_env)
    assert disabled.value.code == "organization_disabled"
    assert org_env.keystone.revoked == ["unscoped-fed"]


async def test_configured_organization_link_only_attaches_then_fresh_callback_provisions(org_env, monkeypatch):
    from app.services import keystone
    from tests.test_canonical_federation import proof, unbound

    env = org_env
    original = unbound(env)
    monkeypatch.setattr(keystone, "authenticate", Mock(return_value=proof()))
    state, browser = await start(env.wire.idp, "cfg:org")
    with pytest.raises(auth.AccountLinkRequired) as pending:
        await auth.complete_authorization("good-code", state, browser)
    linked = await auth.complete_account_link(
        pending.value.link_token, browser, username="dev", password="original-password"
    )
    assert linked == {"linked": True, "domain_id": "dom-a", "domain_name": "Alpha", "provider_id": "cfg:org"}
    assert not env.org_creates and not env.wire.federation.calls and not env.keystone.assignments
    assert original.default_project_id == "saved-native-preference" and original.domain_id == "dom-a"
    fresh = await callback(env)
    assert fresh.user_id == original.id and len(env.org_creates) == 1


async def test_existing_domain_configured_email_autojoin_adds_reader_only(org_env):
    env = org_env
    env.settings.auth = AuthSettings.model_validate(
        {
            "providers": {"corp": oidc_fields()},
            "default": {"auto_join_email_domains": {"corp": ["corp.example"]}},
        }
    )
    env.keystone.project_rows["default-a"] = SimpleNamespace(
        id="default-a", name="Default", domain_id="dom-a", enabled=True, parent_id=None
    )
    # Home membership is not autojoin: use a canonical user homed outside the origin.
    env.keystone.domain_rows["home-x"] = SimpleNamespace(id="home-x", name="Home", enabled=True)
    env.keystone.user_rows["fed-user"].domain_id = "home-x"
    state, browser = await start(env.wire.idp, "cfg:corp")
    login = await auth.complete_authorization("good-code", state, browser)
    roles = project_service._direct_ids(env.keystone.role_assignments.list(project="default-a"), login.user_id)
    assert roles == {rid("project_reader")} and not env.org_creates
    assert not domain_projects.has_manager(login.user_id, "dom-a", ks=env.keystone)


@pytest.fixture
def settler(org_env, monkeypatch):
    from app.services import keystone

    admins = {"system-admin"}
    monkeypatch.setattr(keystone, "_is_system_admin", lambda uid: uid in admins)
    monkeypatch.setattr(keystone, "_get_admin_ks_client", lambda: org_env.keystone)

    async def settle(row, **overrides):
        values = {"intent_id": row.intent_id, "native_calls_settled": True, "actor_user_id": "system-admin"}
        values.update(overrides)
        return await organization_provisioning.settle_binding(row.binding_key, **values)

    return settle


async def uncertain_after_native_create(env, monkeypatch, *, owner=True):
    original = domain_projects.create_domain

    async def committed_then_timeout(**kwargs):
        created = await original(**kwargs)
        if not owner:
            env.keystone.roles.revoke(
                rid("project_owner"), user=kwargs["creator_id"], project=created["default_project_id"]
            )
        raise HTTPException(503, "native_create_result_unknown")

    monkeypatch.setattr(domain_projects, "create_domain", committed_then_timeout)
    with pytest.raises(HTTPException):
        await callback(env)
    monkeypatch.setattr(domain_projects, "create_domain", original)
    return await binding(env)


async def test_settlement_accepts_complete_observed_org_without_replay(org_env, settler, monkeypatch):
    env = org_env
    row = await uncertain_after_native_create(env, monkeypatch)
    pending = await organization_provisioning.pending_bindings()
    observed = [
        did
        for did, domain in env.keystone.domain_rows.items()
        if getattr(domain, "afterglow_organization_intent", None) == row.intent_id
    ]
    assert row.domain_id is None and len(observed) == 1
    assert [item["native_candidates"] for item in pending["items"]] == [observed]
    assert "secret" not in str(pending).lower()
    for denied in ({"native_calls_settled": False}, {"actor_user_id": "fed-user"}, {"intent_id": "0" * 36}):
        with pytest.raises(auth.DomainAuthError):
            await settler(row, **denied)
    settled = await settler(row)
    assert settled["status"] == "active" and len(env.org_creates) == 1
    login = await callback(env)
    assert login.user_id == "fed-user" and len(env.org_creates) == 1


async def test_settlement_keeps_partial_org_fenced_and_never_deletes(org_env, settler, monkeypatch):
    env = org_env
    row = await uncertain_after_native_create(env, monkeypatch, owner=False)
    domains = dict(env.keystone.domain_rows)
    with pytest.raises(auth.DomainAuthConflict) as partial:
        await settler(row)
    assert partial.value.code == "organization_settlement_incomplete"
    assert (await binding(env)).status == "uncertain" and env.keystone.domain_rows == domains
    with pytest.raises(auth.DomainAuthUnavailable):
        await callback(env)
    assert len(env.org_creates) == 1


async def test_settlement_releases_only_observed_absent_creation(org_env, settler, monkeypatch):
    env = org_env

    async def lost_before_native(**kwargs):
        raise HTTPException(503, "connection_reset")

    monkeypatch.setattr(domain_projects, "create_domain", lost_before_native)
    with pytest.raises(HTTPException):
        await callback(env)
    row = await binding(env)
    assert row.status == "uncertain"
    released = await settler(row)
    assert released["status"] == "released"
    async with env.db() as session:
        assert (await session.execute(select(OrganizationBinding))).scalars().all() == []


async def test_staged_disabled_default_is_reported_incomplete_not_outage(org_env, settler, monkeypatch):
    env = org_env
    row = await uncertain_after_native_create(env, monkeypatch)
    domain_id = next(
        did
        for did, domain in env.keystone.domain_rows.items()
        if getattr(domain, "afterglow_organization_intent", None) == row.intent_id
    )
    domain_projects.default_project(domain_id, ks=env.keystone)  # complete before staging regression
    next(p for p in env.keystone.project_rows.values() if p.domain_id == domain_id).enabled = False
    with pytest.raises(auth.DomainAuthConflict) as partial:
        await settler(row)
    assert partial.value.code == "organization_settlement_incomplete"
    assert (await binding(env)).status == "uncertain"


async def test_settlement_http_routes_require_admin_confirmation_and_hide_secrets(org_env, settler, monkeypatch):
    import httpx
    from fastapi import FastAPI

    from app.api.deps import get_token_info, require_admin
    from app.api.identity import organization_bindings
    from tests.admin_gate import synthetic_verified_admin
    from tests.test_domain_auth import SECRET

    env = org_env
    row = await uncertain_after_native_create(env, monkeypatch, owner=False)
    app = FastAPI()
    app.include_router(organization_bindings.router, prefix="/api/v1/admin")
    actor = {"user_id": "system-admin", "is_system_admin": False}
    app.dependency_overrides[get_token_info] = lambda: actor
    app.dependency_overrides[require_admin] = synthetic_verified_admin
    settle_calls = []
    original = organization_provisioning.settle_binding

    async def observed(*args, **kwargs):
        settle_calls.append(kwargs)
        return await original(*args, **kwargs)

    monkeypatch.setattr(organization_provisioning, "settle_binding", observed)
    root = "/api/v1/admin/organization-bindings"
    path = f"{root}/{row.binding_key}/settle"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get(root)).status_code == 403
        assert (
            await client.post(path, json={"intent_id": row.intent_id, "native_calls_settled": True})
        ).status_code == 403
        actor["is_system_admin"] = True
        listed = await client.get(root)
        assert listed.status_code == 200 and listed.json()["items"][0]["binding_key"] == row.binding_key
        assert SECRET not in listed.text and "client_secret" not in listed.text and "token" not in listed.text
        for body in (
            {"intent_id": row.intent_id},
            {"intent_id": row.intent_id, "native_calls_settled": "true"},
            {"intent_id": row.intent_id, "native_calls_settled": True, "domain_id": "guess"},
        ):
            assert (await client.post(path, json=body)).status_code == 422
        assert (
            await client.post(
                f"{root}/not-a-key/settle", json={"intent_id": row.intent_id, "native_calls_settled": True}
            )
        ).status_code == 422
        assert settle_calls == []
        refused = await client.post(path, json={"intent_id": row.intent_id, "native_calls_settled": False})
        assert refused.status_code == 422 and refused.json()["code"] == "settlement_confirmation_required"
        partial = await client.post(path, json={"intent_id": row.intent_id, "native_calls_settled": True})
        assert partial.status_code == 409 and partial.json()["code"] == "organization_settlement_incomplete"
        assert SECRET not in partial.text
    assert (await binding(env)).status == "uncertain" and len(env.org_creates) == 1
