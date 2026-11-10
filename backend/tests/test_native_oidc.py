"""Digest-pinned native federation with signed OIDC and the real callback router."""

from __future__ import annotations

import copy
import hashlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from keystoneauth1.exceptions.http import Unauthorized
from keystoneclient.exceptions import NotFound

from app.services import account_identity, account_spaces, native_oidc
from app.services import domain_auth as svc
from tests.test_domain_auth import ISSUER, configure_file_auth, oidc_fields, start
from tests.test_domain_auth import api as api
from tests.test_domain_auth import db as db
from tests.test_domain_auth import env as env
from tests.test_domain_auth import keystone_admin as keystone_admin
from tests.test_domain_auth import public_dns as public_dns
from tests.test_domain_auth import settings as settings
from tests.test_domain_auth import wire as wire
from tests.test_project_membership_roles import Membership, rid

# Exact reviewed schema 2.0 document: application code contains no operator IDs.
REFERENCE_MAPPING = {
    "schema_version": "2.0",
    "rules": [
        {
            "local": [
                {
                    "user": {
                        "type": "ephemeral",
                        "name": "{0}",
                        "email": "{1}",
                        "domain": {"id": "3b24b0e94b1d46c9941d515b8c2d397b"},
                    },
                    "projects": [
                        {
                            "name": "{0}-project",
                            "domain": {"id": "4661cc1ff17044bfa43f87ded1d8d53f"},
                            "roles": [{"name": "member"}],
                        },
                        {
                            "name": "Default",
                            "domain": {"id": "3de8d34d778e423ab7a92a4992378583"},
                            "roles": [{"name": "reader"}],
                        },
                    ],
                },
                {"groups": "{2}", "domain": {"id": "3de8d34d778e423ab7a92a4992378583"}},
            ],
            "remote": [
                {"type": "OIDC-preferred_username"},
                {"type": "OIDC-email"},
                {"type": "OIDC-groups_direct"},
                {"type": "OIDC-email_verified", "any_one_of": ["true"]},
            ],
        }
    ],
}


def digest(mapping):
    return hashlib.sha256(json.dumps(mapping, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def configure_native(env, *, mapping=None):
    """Reusable signed Wire/Keystone setup; no live credentials or cloud writes."""
    mapping = copy.deepcopy(REFERENCE_MAPPING if mapping is None else mapping)
    local = mapping["rules"][0]["local"][0]
    account_id = local["user"]["domain"]["id"]
    personal_id = local["projects"][0]["domain"]["id"]
    config = {
        "mode": "ephemeral",
        "mapping_id": "reviewed-mapping",
        "sha256": digest(mapping),
        "account_domain_id": account_id,
        "personal_domain_id": personal_id,
    }
    configure_file_auth(env.settings, providers={"native": oidc_fields(native_mapping=config)}, default=["native"])
    ks = env.keystone
    ks.domain_rows[account_id] = SimpleNamespace(id=account_id, name="Accounts", enabled=True)
    ks.domain_rows[personal_id] = SimpleNamespace(id=personal_id, name="Personal", enabled=True)
    if account_id != "dom-accounts":
        ks.domain_rows.pop("dom-accounts", None)
    if personal_id != "dom-personal":
        ks.domain_rows.pop("dom-personal", None)
    ks.idps["idp-a"].remote_ids = [ISSUER]
    ks.federation.mappings.get = lambda _: SimpleNamespace(id=config["mapping_id"], **mapping)
    protocol = SimpleNamespace(id="openid", mapping_id=config["mapping_id"])
    listed_protocols = [SimpleNamespace(**vars(protocol), remote_id_attribute="HTTP_OIDC_ISS")]
    ks.federation.protocols.get = lambda *_: protocol
    ks.federation.protocols.list = lambda _: listed_protocols
    user = ks.user_rows["fed-user"]
    user.domain_id = account_id
    user.federated = [{"idp_id": "idp-a", "protocols": [{"protocol_id": "openid", "unique_id": "dev"}]}]
    user.afterglow_external_identities = [{"issuer": ISSUER, "subject": "subject-1"}]
    ks.catalog = Membership().catalog
    project = SimpleNamespace(
        id="personal-fed-user",
        name=local["projects"][0]["name"].format("dev"),
        domain_id=personal_id,
        enabled=True,
        parent_id=None,
    )
    ks.project_rows[project.id] = project
    ks.assignments = []
    ks.roles.grant(rid("member"), user=user.id, project=project.id)
    env.wire.idp.claims["preferred_username"] = "dev"
    env.wire.federation.native_users = ks.user_rows
    return SimpleNamespace(
        env=env,
        config=config,
        mapping=mapping,
        protocol=protocol,
        listed_protocols=listed_protocols,
        user=user,
        project=project,
    )


@pytest.fixture
def native_env(env):
    # Generic IDs exercise config-driven behavior independently of operator IDs.
    mapping = copy.deepcopy(REFERENCE_MAPPING)
    local = mapping["rules"][0]["local"]
    local[0]["user"]["domain"]["id"] = "dom-accounts"
    local[0]["projects"][0]["domain"]["id"] = "dom-personal"
    local[0]["projects"][1]["domain"]["id"] = "dom-a"
    local[1]["domain"]["id"] = "dom-a"
    return configure_native(env, mapping=mapping)


async def test_exact_reviewed_mapping_accepts_configured_native_pins(env):
    fixture = configure_native(env)
    row = await svc._load_provider("dom-a", "cfg:native")
    descriptor = svc._require_native_mapping(env.keystone, row)
    assert descriptor.project_template == "{0}-project"
    assert descriptor.account_domain_id == fixture.config["account_domain_id"]
    assert descriptor.sha256 == digest(REFERENCE_MAPPING)


@pytest.mark.parametrize(
    "drift", ["rule", "schema", "issuer", "mapping", "remote", "list-mapping", "duplicate", "truncated"]
)
async def test_native_pin_drift_rejects_503(native_env, drift):
    fixture = native_env
    ks = fixture.env.keystone
    row = await svc._load_provider("dom-a", "cfg:native")
    if drift == "rule":
        fixture.mapping["rules"][0]["local"][0]["projects"][1]["roles"] = [{"name": "admin"}]
    elif drift == "schema":
        fixture.mapping["schema_version"] = "1.0"
    elif drift == "issuer":
        ks.idps["idp-a"].remote_ids.append("https://another.example.com")
    elif drift == "mapping":
        fixture.protocol.mapping_id = "another-mapping"
    elif drift == "remote":
        fixture.listed_protocols[0].remote_id_attribute = "HTTP_OTHER_ISS"
    elif drift == "list-mapping":
        fixture.listed_protocols[0].mapping_id = "another-mapping"
    elif drift == "duplicate":
        fixture.listed_protocols.append(fixture.listed_protocols[0])
    else:

        class Truncated(list):
            truncated = True

        ks.federation.protocols.list = lambda _: Truncated(fixture.listed_protocols)
    with pytest.raises(svc.DomainAuthUnavailable) as denied:
        svc._require_native_mapping(ks, row)
    assert denied.value.status_code == 503 and denied.value.code == "native_mapping_unsafe"


async def test_native_signed_login_adopts_without_creating_users_or_grants(native_env):
    fixture = native_env
    ks = fixture.env.keystone
    assignments = copy.deepcopy(ks.assignments)
    state, binding = await start(fixture.env.wire.idp, "cfg:native")
    login = await svc.complete_authorization("good-code", state, binding)
    assert login.user_id == fixture.user.id and login.provider_id == "cfg:native"
    assert fixture.project.afterglow_personal_user_id == fixture.user.id
    assert fixture.project.afterglow_personal_primary is True
    assert ks.user_writes == [] and ks.assignments == assignments
    assert [write[0] for write in ks.project_writes] == ["update"]
    assert len(fixture.env.wire.federation.calls) == 1


@pytest.mark.parametrize("drift", [False, True], ids=["native-success", "digest-drift-503"])
async def test_api_native_callback_signed_wire(api, native_env, drift):
    fixture = native_env
    # Reuse real auth router/session fixture, keeping its native scoped target.
    api.personal["name"] = fixture.project.name
    if drift:
        fixture.mapping["rules"][0]["remote"][2]["type"] = "OIDC-other-groups"
    async with api.client as client:
        begun = await client.post("/api/v1/auth/domains/dom-a/providers/cfg:native/authorize")
        assert begun.status_code == 200, begun.text
        state = fixture.env.wire.idp.remember(begun.json()["authorize_url"])
        response = await client.post("/api/v1/auth/providers/callback", json={"code": "good-code", "state": state})
        assert response.status_code == (503 if drift else 200), response.text
        if drift:
            assert response.json()["code"] == "native_mapping_unsafe"
            assert fixture.env.wire.federation.calls == []
        else:
            assert response.json()["identity_domain_id"] == "dom-accounts"
            assert response.json()["project_id"] == fixture.project.id


@pytest.mark.parametrize("failure", ["foreign", "ambiguous", "disabled", "owner", "admin", "group"])
async def test_native_personal_candidate_authority_denied(native_env, failure):
    fixture = native_env
    ks = fixture.env.keystone
    if failure == "foreign":
        fixture.project.domain_id = "dom-b"
    elif failure == "ambiguous":
        ks.project_rows["second"] = SimpleNamespace(**{**vars(fixture.project), "id": "second"})
    elif failure == "disabled":
        fixture.project.enabled = False
    elif failure == "owner":
        fixture.project.afterglow_personal_user_id = "other-user"
        fixture.project.afterglow_personal_primary = True
    elif failure == "admin":
        ks.roles.grant(rid("admin"), user=fixture.user.id, project=fixture.project.id)
    else:
        ks.group_rows["shared-group"] = SimpleNamespace(id="shared-group", name="shared", domain_id="dom-accounts")
        ks.group_members["shared-group"] = {fixture.user.id}
        ks.roles.grant(rid("member"), group="shared-group", project=fixture.project.id)
    with pytest.raises((svc.DomainAuthUnavailable, HTTPException)) as denied:
        native_oidc.personal_project(fixture.user.id, ks=ks)
    assert denied.value.status_code == 503
    assert ks.project_writes == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("domain_id", "dom-b"),
        ("enabled", False),
        ("afterglow_service_identity", True),
        ("afterglow_identity_kind", "service"),
        ("name", "another-name"),
        ("federated", [{"idp_id": "other", "protocols": [{"protocol_id": "openid", "unique_id": "dev"}]}]),
    ],
)
async def test_false_native_user_is_not_shadow_filtered(native_env, field, value):
    user = copy.deepcopy(native_env.user)
    setattr(user, field, value)
    assert native_oidc._native_user(user) is False


async def test_password_shadow_filter_preserves_explicit_password_accounts(native_env, monkeypatch):
    fixture = native_env
    local = SimpleNamespace(
        id="password-user", name="dev", email=fixture.user.email, enabled=True, domain_id="dom-accounts"
    )
    fixture.env.keystone.user_rows[local.id] = local
    monkeypatch.setattr(account_identity, "_account_users", lambda *_args, **_kwargs: [fixture.user, local])
    operation = SimpleNamespace(
        ks=fixture.env.keystone, get=lambda kind, uid: getattr(fixture.env.keystone, kind).get(uid)
    )
    assert account_identity.password_account("dev", operation=operation)["id"] == local.id
    fixture.user.afterglow_local_password = True
    with pytest.raises(svc.DomainAuthConflict):
        account_identity.password_account("dev", operation=operation)
    monkeypatch.setattr(account_identity, "_account_users", lambda *_args, **_kwargs: [fixture.user])
    assert account_identity.password_account("dev", operation=operation)["id"] == fixture.user.id
    fixture.user.afterglow_local_password = False
    with pytest.raises(Unauthorized):
        account_identity.password_account("dev", operation=operation)


@pytest.mark.parametrize("projection", ["core-names", "missing-names"])
@pytest.mark.parametrize("state", ["local", "explicit-shadow-password", "disabled", "changed-home"])
async def test_password_native_inventory_preserves_exact_candidate_authority(native_env, projection, state):
    from app.services.native_operation import NativeOperation

    fixture, ks = native_env, native_env.env.keystone
    local = SimpleNamespace(
        id="password-user", name="dev", email="local@example.invalid", enabled=True, domain_id="dom-accounts"
    )
    ks.user_rows[local.id] = local
    rows = [
        {"id": user.id, "domain_id": user.domain_id, **({"name": user.name} if projection == "core-names" else {})}
        for user in (fixture.user, local)
    ]
    # Collection core names may narrow candidates; credential/federation extras
    # belong only to exact GET. Both duplicate names must survive narrowing.
    ks.users.client = SimpleNamespace(get=lambda _: (None, {"users": rows, "links": {"next": None}}))
    if state == "explicit-shadow-password":
        fixture.user.afterglow_local_password = True
    elif state == "disabled":
        local.enabled = False
    elif state == "changed-home":
        local.domain_id = "dom-b"
    with NativeOperation() as operation:
        operation._ks = ks
        if state == "local":
            assert account_identity.password_account("dev", operation=operation) == {
                "id": local.id,
                "name": local.name,
                "domain_id": "dom-accounts",
            }
        else:
            error = {
                "explicit-shadow-password": svc.DomainAuthConflict,
                "disabled": Unauthorized,
                "changed-home": svc.DomainAuthUnavailable,
            }[state]
            with pytest.raises(error):
                account_identity.password_account("dev", operation=operation)
    assert ks.user_writes == []


@pytest.mark.parametrize("local_password", [False, True])
async def test_password_email_alias_hydrates_federation_and_casefold_collisions(native_env, local_password):
    from app.services.native_operation import NativeOperation

    fixture, ks = native_env, native_env.env.keystone
    fixture.user.afterglow_local_password = local_password
    local = SimpleNamespace(
        id="password-user", name="local-name", email=fixture.user.email.upper(), enabled=True, domain_id="dom-accounts"
    )
    ks.user_rows[local.id] = local
    ks.users.client = SimpleNamespace(
        get=lambda _: (
            None,
            {
                "users": [{"id": u.id, "domain_id": u.domain_id, "name": u.name} for u in (fixture.user, local)],
                "links": {"next": None},
            },
        )
    )
    with NativeOperation() as operation:
        operation._ks = ks
        if local_password:
            with pytest.raises(svc.DomainAuthConflict) as ambiguous:
                account_identity.password_account(local.email.swapcase(), operation=operation)
            assert ambiguous.value.code == "account_ambiguous"
        else:
            assert account_identity.password_account(local.email.swapcase(), operation=operation)["id"] == local.id
    assert ks.user_writes == []


@pytest.mark.parametrize(
    "failure", [None, "digest", "mapping", "remote", "duplicate", "truncated", "unavailable", "foreign-idp"]
)
async def test_alias_only_native_shadow_requires_complete_pinned_transport(native_env, monkeypatch, failure):
    fixture = native_env
    ks = fixture.env.keystone
    fixture.user.federated[0]["protocols"][0]["protocol_id"] = "transport-alias"
    alias = SimpleNamespace(
        id="transport-alias", mapping_id=fixture.config["mapping_id"], remote_id_attribute="HTTP_OIDC_ISS"
    )
    fixture.listed_protocols.append(alias)
    if failure == "digest":
        fixture.mapping["rules"][0]["local"][0]["projects"][1]["name"] = "changed"
    elif failure == "mapping":
        alias.mapping_id = "foreign-mapping"
    elif failure == "remote":
        alias.remote_id_attribute = "HTTP_OTHER_ISS"
    elif failure == "duplicate":
        fixture.listed_protocols.append(alias)
    elif failure == "truncated":

        class Incomplete(list):
            links = {"next": "another-page"}

        monkeypatch.setattr(ks.federation.protocols, "list", lambda _: Incomplete(fixture.listed_protocols))
    elif failure == "unavailable":

        def unavailable(_):
            raise ConnectionError("native unavailable")

        monkeypatch.setattr(ks.federation.protocols, "list", unavailable)
    elif failure == "foreign-idp":
        fixture.user.federated[0]["idp_id"] = "foreign-idp"

        def unexpected_read(_):
            pytest.fail("Unrelated federation associations must not cause native reads")

        monkeypatch.setattr(ks.federation.protocols, "list", unexpected_read)
        monkeypatch.setattr(ks.federation.mappings, "get", unexpected_read)
    local = SimpleNamespace(
        id="local-user", name="dev", email=fixture.user.email, enabled=True, domain_id="dom-accounts"
    )
    ks.user_rows[local.id] = local
    monkeypatch.setattr(account_identity, "_account_users", lambda *_args, **_kwargs: [fixture.user, local])
    operation = SimpleNamespace(ks=ks, get=lambda kind, uid: getattr(ks, kind).get(uid))
    if failure is None:
        assert native_oidc._native_user(fixture.user, ks=ks) is True
        assert account_identity.password_account("dev", operation=operation)["id"] == local.id
        assert native_oidc.personal_project(fixture.user.id, ks=ks)["id"] == fixture.project.id
    else:
        assert native_oidc._native_user(fixture.user, ks=ks) is False
        with pytest.raises(svc.DomainAuthConflict):
            account_identity.password_account("dev", operation=operation)
    # Explicit password ownership bypasses shadow detection, even for a proven alias.
    fixture.user.afterglow_local_password = True
    with pytest.raises(svc.DomainAuthConflict):
        account_identity.password_account("dev", operation=operation)


@pytest.mark.parametrize("conditional", [False, True], ids=["numbered-predecessor", "conditional-not-numbered"])
async def test_personal_template_placeholder_rejects_conditional_predecessor(native_env, conditional):
    fixture = native_env
    rule = fixture.mapping["rules"][0]
    predecessor = {"type": "OIDC-other"}
    if conditional:
        predecessor["any_one_of"] = ["allowed"]
    rule["remote"].insert(0, predecessor)
    rule["local"][0]["user"]["name"] = "{1}"
    rule["local"][0]["projects"][0]["name"] = "{1}-project"
    fixture.config["sha256"] = digest(fixture.mapping)
    configure_file_auth(
        fixture.env.settings, providers={"native": oidc_fields(native_mapping=fixture.config)}, default=["native"]
    )
    row = await svc._load_provider("dom-a", "cfg:native")
    if conditional:
        with pytest.raises(svc.DomainAuthUnavailable) as denied:
            svc._require_native_mapping(fixture.env.keystone, row)
        assert denied.value.status_code == 503 and denied.value.code == "native_mapping_unsafe"
    else:
        assert svc._require_native_mapping(fixture.env.keystone, row).project_template == "{0}-project"


async def test_existing_password_name_and_primary_are_preserved(native_env):
    fixture = native_env
    fixture.user.name = "local-password-name"
    fixture.user.afterglow_local_password = True
    fixture.project.name = "older-personal-primary"
    fixture.project.afterglow_personal_user_id = fixture.user.id
    fixture.project.afterglow_personal_primary = True
    snapshot = copy.deepcopy(vars(fixture.user))
    state, binding = await start(fixture.env.wire.idp, "cfg:native")
    login = await svc.complete_authorization("good-code", state, binding)
    assert login.username == "local-password-name"
    assert vars(fixture.user) == snapshot and fixture.env.keystone.project_writes == []
    assert account_spaces.personal_project(fixture.user.id, ks=fixture.env.keystone)["name"] == "older-personal-primary"


async def test_deleted_password_primary_recovers_signed_username_project(native_env):
    fixture = native_env
    fixture.user.name = "different-local-name"
    fixture.user.afterglow_local_password = True
    fixture.user.federated[0]["protocols"][0]["unique_id"] = "different-local-name"
    snapshot = copy.deepcopy(vars(fixture.user))
    state, binding = await start(fixture.env.wire.idp, "cfg:native")
    login = await svc.complete_authorization("good-code", state, binding)
    assert login.username == fixture.user.name and vars(fixture.user) == snapshot
    assert fixture.project.afterglow_personal_user_id == fixture.user.id
    assert fixture.project.name == "dev-project"


async def test_native_project_template_is_mapping_derived(env):
    mapping = copy.deepcopy(REFERENCE_MAPPING)
    mapping["rules"][0]["local"][0]["projects"][0]["name"] = "workspace-{0}-home"
    fixture = configure_native(env, mapping=mapping)
    assert native_oidc.personal_project(fixture.user.id, ks=env.keystone)["name"] == "workspace-dev-home"


@pytest.mark.parametrize("failure", ["service", "subject", "email", "domain", "native-provider"])
async def test_native_identity_readback_rejects_and_revokes(native_env, failure):
    fixture = native_env
    if failure == "service":
        fixture.user.afterglow_service_identity = True
    elif failure == "subject":
        fixture.user.afterglow_external_identities[0]["subject"] = "other-subject"
    elif failure == "email":
        fixture.user.email = "other@corp.example"
    elif failure == "domain":
        fixture.user.domain_id = "dom-b"
    else:
        fixture.env.wire.federation.idp_id = "other-idp"
    state, binding = await start(fixture.env.wire.idp, "cfg:native")
    with pytest.raises(svc.DomainAuthUnavailable):
        await svc.complete_authorization("good-code", state, binding)
    assert fixture.env.keystone.revoked == ["unscoped-fed"]


async def test_native_pin_revision_invalidates_pending_authorization(native_env):
    fixture = native_env
    state, binding = await start(fixture.env.wire.idp, "cfg:native")
    before = await svc._load_provider("dom-a", "cfg:native")
    config = {**fixture.config, "sha256": "0" * 64}
    configure_file_auth(
        fixture.env.settings, providers={"native": oidc_fields(native_mapping=config)}, default=["native"]
    )
    after = await svc._load_provider("dom-a", "cfg:native")
    assert before.revision != after.revision
    with pytest.raises(svc.DomainAuthConflict) as denied:
        await svc.complete_authorization("good-code", state, binding)
    assert denied.value.code == "provider_changed" and fixture.env.wire.federation.calls == []


async def test_legacy_account_confirmation_rejects_native_mode_switch(native_env, monkeypatch):
    fixture = native_env
    configure_file_auth(fixture.env.settings, providers={"native": oidc_fields()}, default=["native"])
    row = await svc._load_provider("dom-a", "cfg:native")
    identity = svc.VerifiedIdentity("Dev@corp.example", "verified-bearer", ISSUER, "subject-1")
    browser = "browser-binding-value"
    ticket = await svc._entry_ticket(row, identity, fixture.user, browser, ks=fixture.env.keystone)
    configure_file_auth(
        fixture.env.settings, providers={"native": oidc_fields(native_mapping=fixture.config)}, default=["native"]
    )
    with pytest.raises(svc.DomainAuthConflict) as denied:
        await svc.complete_account_entry(ticket, browser, action="connect")
    assert denied.value.code == "provider_changed"
    assert fixture.env.keystone.user_writes == [] and fixture.env.wire.federation.calls == []


async def test_unconfigured_native_helpers_do_not_enroll(env):
    configure_file_auth(env.settings, default=["corp"])
    assert native_oidc._native_user(env.keystone.user_rows["fed-user"]) is False
    assert native_oidc.personal_project("fed-user", ks=env.keystone) is None


@pytest.mark.parametrize("username", ["", None, [], "bad\nname"])
async def test_native_username_must_come_from_signed_oidc_claim(native_env, username):
    fixture = native_env
    fixture.env.wire.idp.claims["preferred_username"] = username
    state, binding = await start(fixture.env.wire.idp, "cfg:native")
    with pytest.raises(svc.DomainAuthUnavailable) as denied:
        await svc.complete_authorization("good-code", state, binding)
    assert denied.value.code == "native_mapping_unsafe"
    assert fixture.env.wire.federation.calls == []


async def test_same_issuer_legacy_provider_is_not_implicitly_opted_in(native_env):
    fixture = native_env
    configure_file_auth(
        fixture.env.settings,
        providers={"native": oidc_fields(native_mapping=fixture.config), "legacy": oidc_fields()},
        default=["native", "legacy"],
    )
    row = await svc._load_provider("dom-a", "cfg:legacy")
    assert getattr(row, "_native_mapping", None) is None
    with pytest.raises(svc.DomainAuthUnavailable) as denied:
        svc._require_native_mapping(fixture.env.keystone, row)
    assert denied.value.code == "native_mapping_unsafe"


@pytest.mark.parametrize("failure", [None, "pending", "uncertain", "old-exists", "old-unreadable", "unowned"])
async def test_deleted_primary_receipt_retirement_is_narrow(native_env, monkeypatch, failure):
    fixture = native_env
    ks = fixture.env.keystone
    fixture.project.afterglow_personal_user_id = fixture.user.id
    fixture.project.afterglow_personal_primary = True
    intent = SimpleNamespace(
        status="accepted",
        primary=True,
        primary_user_id=fixture.user.id,
        user_id=fixture.user.id,
        project_creation_uncertain=False,
        identity_domain_id="dom-accounts",
        personal_domain_id="dom-personal",
        personal_project_id="deleted-primary",
        personal_project_name="historical-name",
        personal_quotas={"instances": 3},
        token_hash="historical-token",
    )
    if failure == "pending":
        intent.status = "pending"
    elif failure == "uncertain":
        intent.project_creation_uncertain = True
    elif failure == "unowned":
        del fixture.project.afterglow_personal_user_id
        del fixture.project.afterglow_personal_primary
    original_get = ks.projects.get

    def read_project(pid):
        if pid != "deleted-primary":
            return original_get(pid)
        if failure == "old-exists":
            return SimpleNamespace(id=pid)
        if failure == "old-unreadable":
            raise ConnectionError("native unavailable")
        raise NotFound()

    monkeypatch.setattr(ks.projects, "get", read_project)
    snapshot = copy.deepcopy(vars(intent))
    project = {key: getattr(fixture.project, key) for key in ("id", "name", "domain_id", "enabled")}
    lease, session = SimpleNamespace(assert_owned=AsyncMock()), SimpleNamespace(commit=AsyncMock())
    if failure == "old-unreadable":
        with pytest.raises(HTTPException) as denied:
            await native_oidc.retire_deleted_primary_intent(intent, project, ks=ks, lease=lease, session=session)
        assert denied.value.status_code == 503
    else:
        retired = await native_oidc.retire_deleted_primary_intent(intent, project, ks=ks, lease=lease, session=session)
        assert retired is (failure is None)
    if failure is None:
        snapshot.update(status="cancelled", primary_user_id=None)
        session.commit.assert_awaited_once()
        lease.assert_owned.assert_awaited_once()
    else:
        session.commit.assert_not_awaited()
    assert vars(intent) == snapshot


# Keystone returns a local account (no OS-FEDERATION block) when a `local` rule matched. Only the pinned
# mapping's own local rule for this exact email and literal name, in the Accounts domain, may pass.
LOCAL_RULE_MAPPING = {
    "schema_version": "2.0",
    "rules": [
        {
            "local": [{"user": {"type": "local", "name": "linked-user", "domain": {"id": "dom-accounts"}}}],
            "remote": [
                {"type": "OIDC-email", "any_one_of": ["linked@example.test"]},
                {"type": "OIDC-email_verified", "any_one_of": ["true"]},
            ],
        },
        {
            "local": [{"user": {"type": "ephemeral", "name": "{0}", "email": "{1}", "domain": {"id": "dom-accounts"}}}],
            "remote": [{"type": "OIDC-preferred_username"}, {"type": "OIDC-email"}],
        },
    ],
}
LOCAL_DESCRIPTOR = SimpleNamespace(
    account_domain_id="dom-accounts", idp_id="gitlab", protocol_id="openid", mapping_id="sso_oidc_mapping"
)


def _local_ks(mapping=LOCAL_RULE_MAPPING):
    return SimpleNamespace(
        federation=SimpleNamespace(mappings=SimpleNamespace(get=lambda _: SimpleNamespace(**mapping)))
    )


def _local_native(**overrides):
    native = {"id": "local-user-id", "name": "linked-user", "domain": {"id": "dom-accounts"}}
    native.update(overrides)
    return native


def test_local_identity_accepts_only_the_pinned_local_rule_for_this_email_and_name():
    identity = SimpleNamespace(email="linked@example.test")
    assert native_oidc._local_identity_reason(_local_native(), identity, LOCAL_DESCRIPTOR, _local_ks()) is None


@pytest.mark.parametrize(
    "native_overrides, email, reason",
    [
        ({"name": "someone-else"}, "linked@example.test", "local_rule_not_matched"),
        ({"domain": {"id": "dom-personal"}}, "linked@example.test", "user_domain_not_accounts"),
        ({}, "other@example.test", "local_rule_not_matched"),
        ({}, "linked@example.test", None),
    ],
    ids=["wrong-name", "foreign-domain", "email-not-in-rule", "control-match"],
)
def test_local_identity_rejects_mismatches_with_a_server_side_reason(native_overrides, email, reason):
    identity = SimpleNamespace(email=email)
    native = _local_native(**native_overrides)
    assert native_oidc._local_identity_reason(native, identity, LOCAL_DESCRIPTOR, _local_ks()) == reason


def test_ephemeral_rule_never_authorizes_a_local_account_result():
    # Only a `local`-typed user clause can explain a local token; an ephemeral clause with the same name cannot.
    mapping = {
        "schema_version": "2.0",
        "rules": [
            {
                "local": [{"user": {"type": "ephemeral", "name": "linked-user", "domain": {"id": "dom-accounts"}}}],
                "remote": [{"type": "OIDC-email", "any_one_of": ["linked@example.test"]}],
            }
        ],
    }
    identity = SimpleNamespace(email="linked@example.test")
    reason = native_oidc._local_identity_reason(_local_native(), identity, LOCAL_DESCRIPTOR, _local_ks(mapping))
    assert reason == "local_rule_not_matched"


@pytest.fixture
def local_federate(monkeypatch):
    """federate() doubles: Keystone returns a local-account token (no OS-FEDERATION block) for the local rule."""
    from app.services import account_spaces, organization_provisioning
    from app.services import domain_auth as svc

    descriptor = SimpleNamespace(
        issuer=ISSUER,
        idp_id="gitlab",
        protocol_id="openid",
        mapping_id="sso_oidc_mapping",
        account_domain_id="dom-accounts",
        personal_domain_id="dom-personal",
        project_template="{0}-project",
    )
    user = SimpleNamespace(
        id="local-user-id",
        name="linked-user",
        domain_id="dom-accounts",
        enabled=True,
        email="linked@example.test",
        afterglow_external_identities=[{"issuer": ISSUER, "subject": "subject-1"}],
        afterglow_service_identity=None,
        afterglow_identity_kind="human",
    )
    monkeypatch.setattr(svc, "require_provider", AsyncMock())
    monkeypatch.setattr(svc, "_require_native_mapping", lambda ks, row: descriptor)
    monkeypatch.setattr(svc, "_revoke_quietly", AsyncMock())
    monkeypatch.setattr(organization_provisioning, "require_current", AsyncMock())

    def no_template_lookup(*_args, **_kwargs):
        raise AssertionError("a local-linked login must not look up the mapped <username>-project template")

    monkeypatch.setattr(account_spaces, "personal_project", no_template_lookup)
    ks = SimpleNamespace(
        federation=SimpleNamespace(mappings=SimpleNamespace(get=lambda _: SimpleNamespace(**LOCAL_RULE_MAPPING))),
        users=SimpleNamespace(get=lambda _uid: user),
    )
    return SimpleNamespace(descriptor=descriptor, ks=ks, user=user, svc=svc)


def _local_identity():
    return SimpleNamespace(
        issuer=ISSUER,
        username="gitlab-user",
        email="linked@example.test",
        subject="subject-1",
        bearer="id-token",
    )


async def test_federate_links_a_local_rule_account_without_template_lookup(local_federate, monkeypatch):
    svc = local_federate.svc
    native = {"id": "local-user-id", "name": "linked-user", "domain": {"id": "dom-accounts"}}
    monkeypatch.setattr(svc, "keystone_federate", AsyncMock(return_value=("tok", native)))
    lease = SimpleNamespace(assert_owned=AsyncMock())
    login = await native_oidc.federate(
        SimpleNamespace(id="cfg:native", revision=1, kind="oidc"),
        _local_identity(),
        {"id": "dom-login", "name": "dmslab"},
        ks=local_federate.ks,
        lease=lease,
        catalog=None,
        descriptor=local_federate.descriptor,
    )
    assert login.user_id == "local-user-id" and login.unscoped_token == "tok"
    assert lease.assert_owned.await_count >= 1
    svc._revoke_quietly.assert_not_awaited()


@pytest.mark.parametrize(
    "native, email",
    [
        ({"id": "local-user-id", "name": "someone-else", "domain": {"id": "dom-accounts"}}, "linked@example.test"),
        ({"id": "local-user-id", "name": "linked-user", "domain": {"id": "dom-personal"}}, "linked@example.test"),
        ({"id": "local-user-id", "name": "linked-user", "domain": {"id": "dom-accounts"}}, "unlisted@example.test"),
    ],
    ids=["wrong-name", "foreign-domain", "email-not-in-rule"],
)
async def test_federate_rejects_a_local_result_the_pinned_rule_does_not_authorize(
    local_federate, monkeypatch, native, email
):
    svc = local_federate.svc
    monkeypatch.setattr(svc, "keystone_federate", AsyncMock(return_value=("tok", native)))
    lease = SimpleNamespace(assert_owned=AsyncMock())
    identity = _local_identity()
    identity.email = email
    with pytest.raises(svc.DomainAuthUnavailable) as denied:
        await native_oidc.federate(
            SimpleNamespace(id="cfg:native", revision=1, kind="oidc"),
            identity,
            {"id": "dom-login", "name": "dmslab"},
            ks=local_federate.ks,
            lease=lease,
            catalog=None,
            descriptor=local_federate.descriptor,
        )
    assert denied.value.status_code == 503 and denied.value.code == "native_mapping_unsafe"
    svc._revoke_quietly.assert_awaited_once_with("tok")
