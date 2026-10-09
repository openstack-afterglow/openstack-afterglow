from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api.identity import mcp_access
from app.models.mcp_authority import (
    McpDelegatedGrant,
    McpLumenSelection,
    McpOAuthAuthorizationRequest,
    McpOAuthClient,
    McpOAuthCode,
    McpOAuthToken,
    McpOAuthTokenFamily,
    McpOwnerLock,
    McpPersonalToken,
    McpToolInvocation,
)
from app.services import k3s_crypto
from app.services.mcp_control_plane import connection as mcp_connection
from app.services.mcp_control_plane import lumen as mcp_lumen
from app.services.mcp_control_plane.authority import (
    PERSONAL_TOKEN_PREFIX,
    _as_utc,
    _grant_expiry,
    _new_personal_token,
    create_restricted_application_credential,
    delete_and_confirm_application_credential,
    grant_scopes,
    list_personal_tokens,
)
from app.services.mcp_control_plane.crypto import decrypt_application_credential, encrypt_application_credential


@pytest.fixture
def mcp_key(monkeypatch):
    monkeypatch.setattr(
        k3s_crypto,
        "get_settings",
        lambda: type("Settings", (), {"k3s_kubeconfig_encryption_key": "a" * 64})(),
    )


def test_mcp_credential_ciphertext_is_grant_bound_without_legacy_fallback(mcp_key):
    ciphertext = encrypt_application_credential(
        "keystone-secret", grant_id="grant-a", owner_user_id="user-a", owner_project_id="project-a"
    )

    assert ciphertext.startswith("mcp-ac1:")
    assert (
        decrypt_application_credential(
            ciphertext, grant_id="grant-a", owner_user_id="user-a", owner_project_id="project-a"
        )
        == "keystone-secret"
    )
    with pytest.raises(ValueError, match="invalid"):
        decrypt_application_credential(
            ciphertext, grant_id="grant-b", owner_user_id="user-a", owner_project_id="project-a"
        )
    with pytest.raises(ValueError, match="invalid"):
        decrypt_application_credential(
            "v3:legacy", grant_id="grant-a", owner_user_id="user-a", owner_project_id="project-a"
        )


def test_personal_tokens_have_required_prefix_entropy_and_scopes():
    token = _new_personal_token()

    assert token.startswith(PERSONAL_TOKEN_PREFIX)
    assert re.fullmatch(r"mcp-afgl-[A-Za-z0-9_-]{43}", token)
    assert grant_scopes("read") == ("mcp:read",)
    assert grant_scopes("manage") == ("mcp:read", "mcp:write")
    with pytest.raises(Exception, match="read or manage"):
        grant_scopes("write")


def test_lumen_frozen_snapshot_is_strict_and_opaque():
    snapshot = mcp_lumen.LumenGrantSnapshot(
        grant_id="grant-opaque",
        user_id="user-a",
        project_id="project-a",
        credential_epoch=7,
        selection_generation=11,
    )
    payload = mcp_lumen.snapshot_payload(snapshot)

    assert mcp_lumen.frozen_snapshot(payload) == snapshot
    assert mcp_lumen.frozen_snapshot(None) is None
    with pytest.raises(mcp_lumen.McpLumenAuthorityError, match="snapshot is invalid"):
        mcp_lumen.frozen_snapshot({**payload, "extra": "rejected"})


@pytest.mark.parametrize("microsecond", [0, 123456])
@pytest.mark.parametrize(
    "offset", [None, 0, 330, -420], ids=["configured-default", "utc", "positive-offset", "negative-offset"]
)
def test_restricted_credential_creation_uses_exact_scoped_connection(monkeypatch, microsecond, offset):
    import requests
    from keystoneauth1 import session, token_endpoint
    from openstack.connection import Connection
    from oslo_utils import timeutils

    now = datetime(2026, 10, 8, 10, 0, 0, microsecond, tzinfo=UTC)
    supplied = None if offset is None else (now + timedelta(days=1)).astimezone(timezone(timedelta(minutes=offset)))
    deadline = _grant_expiry(expires_at=supplied, now=now)
    sent = []

    def send(_session, request, **kwargs):
        if request.method == "GET":
            assert request.url.rstrip("/") == "https://keystone.example.test/v3"
            response = requests.Response()
            response.status_code = 200
            response.request = request
            response.headers["Content-Type"] = "application/json"
            response._content = json.dumps(
                {
                    "version": {
                        "id": "v3.14",
                        "status": "stable",
                        "links": [{"rel": "self", "href": "https://keystone.example.test/v3/"}],
                    }
                }
            ).encode()
            return response
        sent.append(request)
        credential = json.loads(request.body)["application_credential"]
        timestamp = credential["expires_at"]
        # Keystone2025.2 parse_expiration_date adds Z before its installed oslo parser.
        parsed = timeutils.parse_isotime(timestamp if timestamp.endswith("Z") else timestamp + "Z")
        assert parsed.astimezone(UTC) == deadline
        assert timestamp.endswith("Z")
        assert credential["unrestricted"] is False
        assert credential["roles"] == [{"name": "member"}]
        assert request.method == "POST"
        assert request.url == "https://keystone.example.test/v3/users/user-a/application_credentials"
        response = requests.Response()
        response.status_code = 201
        response.request = request
        response.headers["Content-Type"] = "application/json"
        response._content = json.dumps(
            {"application_credential": {**credential, "id": "credential-id", "secret": "credential-secret"}}
        ).encode()
        return response

    monkeypatch.setattr(requests.Session, "send", send)
    auth = token_endpoint.Token(endpoint="https://keystone.example.test/v3", token="owner-project-token")
    conn = Connection(
        session=session.Session(auth=auth),
        identity_endpoint_override="https://keystone.example.test/v3",
        identity_api_version="3",
    )
    conn._afterglow_user_id = "user-a"
    conn._afterglow_project_id = "project-a"
    try:
        created = create_restricted_application_credential(
            conn,
            owner_user_id="user-a",
            owner_project_id="project-a",
            upstream_name="afterglow-mcp-grant-a",
            expires_at=deadline if supplied is None else supplied,
            roles=[{"name": "member"}],
        )
    finally:
        conn.close()

    assert created == {"id": "credential-id", "secret": "credential-secret"}
    assert len(sent) == 1


def test_orphan_cleanup_deletes_only_the_exact_deterministic_credential_name():
    class Identity:
        def __init__(self):
            self.credential = SimpleNamespace(id="credential-id", name="afterglow-mcp-grant-a")
            self.deleted: list[tuple[str, str]] = []

        def find_application_credential(self, user_id, name_or_id, *, ignore_missing):
            assert user_id == "user-a"
            credential = self.credential
            if credential and name_or_id in {credential.id, credential.name}:
                return credential
            return None

        def delete_application_credential(self, user_id, credential_id, *, ignore_missing):
            self.deleted.append((user_id, credential_id))
            if self.credential and credential_id == self.credential.id:
                self.credential = None

    identity = Identity()
    conn = SimpleNamespace(identity=identity)

    assert delete_and_confirm_application_credential(
        conn,
        owner_user_id="user-a",
        application_credential_id=None,
        upstream_credential_name="afterglow-mcp-grant-a",
    )
    assert identity.deleted == [("user-a", "credential-id")]


def test_orphan_cleanup_rejects_a_nonmatching_credential_name():
    class Identity:
        def find_application_credential(self, user_id, name_or_id, *, ignore_missing):
            return SimpleNamespace(id="credential-id", name="afterglow-mcp-other-grant")

        def delete_application_credential(self, user_id, credential_id, *, ignore_missing):
            raise AssertionError("a nonmatching credential must not be deleted")

    assert not delete_and_confirm_application_credential(
        SimpleNamespace(identity=Identity()),
        owner_user_id="user-a",
        application_credential_id=None,
        upstream_credential_name="afterglow-mcp-grant-a",
    )


def test_mcp_orm_registers_every_delegated_authority_table():
    table_names = {
        McpDelegatedGrant.__tablename__,
        McpPersonalToken.__tablename__,
        McpLumenSelection.__tablename__,
        McpOwnerLock.__tablename__,
        McpOAuthClient.__tablename__,
        McpOAuthAuthorizationRequest.__tablename__,
        McpOAuthCode.__tablename__,
        McpOAuthTokenFamily.__tablename__,
        McpOAuthToken.__tablename__,
        McpToolInvocation.__tablename__,
    }

    assert table_names <= set(McpDelegatedGrant.metadata.tables)


def test_browser_mcp_mutations_require_allowed_origin_but_reads_do_not(monkeypatch):
    settings = SimpleNamespace(
        service_mcp_enabled=True,
        frontend_base_url="https://app.example.test",
        public_api_base="https://api.example.test",
        cors_origin_list=("https://app.example.test",),
    )
    monkeypatch.setattr(mcp_access, "get_settings", lambda: settings)
    read_request = Request({"type": "http", "headers": []})
    mcp_access._require_mcp_enabled()

    valid_mutation = Request(
        {
            "type": "http",
            "headers": [(b"origin", b"https://app.example.test"), (b"sec-fetch-site", b"same-site")],
        }
    )
    mcp_access._require_browser_mutation(valid_mutation)

    invalid_mutation = Request(
        {
            "type": "http",
            "headers": [(b"origin", b"https://attacker.example"), (b"sec-fetch-site", b"same-site")],
        }
    )
    with pytest.raises(HTTPException, match="same-site"):
        mcp_access._require_browser_mutation(invalid_mutation)

    assert read_request.headers.get("origin") is None


def test_mariadb_naive_deadlines_are_normalized_to_utc():
    naive = __import__("datetime").datetime(2026, 7, 27, 12, 0, 0)

    assert _as_utc(naive).tzinfo is __import__("datetime").UTC


def test_consumer_connection_uses_only_the_grant_application_credential(monkeypatch):
    captured = {}

    class FakeConnection:
        def __init__(self, **kwargs):
            captured["connection"] = kwargs

    class FakeSession:
        def __init__(self, **kwargs):
            captured["session"] = kwargs

    class FakeCredential:
        def __init__(self, **kwargs):
            captured["credential"] = kwargs

    import openstack

    monkeypatch.setattr(mcp_connection.v3, "ApplicationCredential", FakeCredential)
    monkeypatch.setattr(mcp_connection.ks_session, "Session", FakeSession)
    monkeypatch.setattr(openstack.connection, "Connection", FakeConnection)
    monkeypatch.setattr(
        mcp_connection,
        "get_settings",
        lambda: SimpleNamespace(
            os_auth_url="https://keystone.example.test/v3",
            os_region_name="RegionOne",
            os_interface="public",
            ssl_verify=True,
        ),
    )
    principal = SimpleNamespace(project_id="project-a", user_id="user-a")

    conn = mcp_connection._build_connection("credential-id", "credential-secret", principal)

    assert conn._afterglow_project_id == "project-a"
    assert conn._afterglow_user_id == "user-a"
    assert conn._afterglow_is_system_admin is False
    assert captured["credential"] == {
        "auth_url": "https://keystone.example.test/v3",
        "application_credential_id": "credential-id",
        "application_credential_secret": "credential-secret",
        "project_id": "project-a",
    }
    assert captured["connection"]["app_name"] == "afterglow-consumer-mcp"


def test_lumen_default_clear_route_precedes_dynamic_token_delete_route():
    paths = [getattr(route, "path", "") for route in mcp_access.router.routes]

    assert paths.index("/mcp-tokens/lumen-default") < paths.index("/mcp-tokens/{token_id}")


@pytest.mark.asyncio
async def test_personal_token_listing_marks_only_selected_lumen_default():
    grant_a = SimpleNamespace(
        id="grant-a",
        display_name="first",
        source="personal_token",
        access_level="read",
        status="active",
        issued_at=None,
        expires_at=__import__("datetime").datetime(2026, 8, 1, tzinfo=__import__("datetime").UTC),
        last_used_at=None,
        revoked_at=None,
    )
    grant_b = SimpleNamespace(**{**grant_a.__dict__, "id": "grant-b", "display_name": "second"})
    token_a = SimpleNamespace(
        id="token-a", visible_prefix="mcp-afgl-first", issued_at=grant_a.expires_at, last_used_at=None
    )
    token_b = SimpleNamespace(
        id="token-b", visible_prefix="mcp-afgl-second", issued_at=grant_b.expires_at, last_used_at=None
    )

    class Result:
        def all(self):
            return [(grant_a, token_a), (grant_b, token_b)]

    class Session:
        async def scalar(self, _):
            return "grant-b"

        async def execute(self, _):
            return Result()

    result = await list_personal_tokens(Session(), owner_user_id="user-a", owner_project_id="project-a")

    assert [token["is_lumen_default"] for token in result] == [False, True]
    assert mcp_access.McpTokenView.model_validate(result[1]).is_lumen_default is True


@pytest.mark.asyncio
async def test_lumen_ledger_requires_the_frozen_selection_generation():
    from app.services.mcp_control_plane import ledger
    from app.services.mcp_control_plane.authentication import McpPrincipal

    class Session:
        def __init__(self, selection):
            self.selection = selection

        async def get(self, _model, _identity, *, with_for_update):
            assert with_for_update is True
            return self.selection

    principal = McpPrincipal(
        grant_id="grant-a",
        user_id="user-a",
        project_id="project-a",
        credential_epoch=2,
        scopes=frozenset({"mcp:read", "mcp:write"}),
        source="lumen",
        selection_generation=7,
    )
    owner_lock = SimpleNamespace(lumen_selection_generation=7)
    selection = SimpleNamespace(grant_id="grant-a")

    await ledger._validate_lumen_selection(Session(selection), principal, owner_lock=owner_lock, source="lumen")

    owner_lock.lumen_selection_generation = 8
    with pytest.raises(ledger.McpInvocationError, match="selection changed"):
        await ledger._validate_lumen_selection(Session(selection), principal, owner_lock=owner_lock, source="lumen")


@pytest.mark.asyncio
async def test_mounted_mcp_token_endpoint_returns_the_one_time_plaintext_token(client, monkeypatch):
    expires_at = datetime.now(UTC) + timedelta(days=30)
    settings = SimpleNamespace(
        service_mcp_enabled=True,
        frontend_base_url="https://app.example.test",
        public_api_base="https://api.example.test",
        cors_origin_list=("https://app.example.test",),
    )
    issued = SimpleNamespace(
        token_id="token-id",
        grant_id="grant-id",
        access_level="read",
        token="mcp-afgl-one-time-secret",
        expires_at=expires_at,
    )
    captured = {}

    async def issue(*args, **kwargs):
        captured.update(kwargs)
        return issued

    monkeypatch.setattr(mcp_access, "get_settings", lambda: settings)
    monkeypatch.setattr(mcp_access, "_session_factory", lambda: object())
    monkeypatch.setattr(mcp_access, "issue_personal_token", issue)

    response = await client.post(
        "/api/v1/auth/mcp-tokens",
        json={"name": "Desktop client", "access_level": "read"},
        headers={"Origin": "https://app.example.test", "Sec-Fetch-Site": "same-site"},
    )

    assert response.status_code == 201
    assert response.json()["token"] == "mcp-afgl-one-time-secret"
    assert captured["display_name"] == "Desktop client"
    assert captured["access_level"] == "read"
