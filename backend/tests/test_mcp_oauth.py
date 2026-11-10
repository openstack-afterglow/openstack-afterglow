from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.api import mcp as mcp_api
from app.services.mcp_control_plane.oauth import (
    McpOAuthError,
    oauth_urls,
    pkce_s256,
    redirect_uri_matches,
    require_exact_resource,
    validate_pkce_s256,
    validate_redirect_uris,
    validate_scopes,
)
from app.services.mcp_control_plane.oauth_authority import McpOAuthAuthorityError, McpOAuthFailureReason


def test_oauth_urls_require_https_production_public_base():
    urls = oauth_urls("https://api.example.test/", production=True)

    assert urls.resource == "https://api.example.test/api/v1/mcp"
    assert urls.issuer == "https://api.example.test/api/v1/mcp/oauth"
    assert urls.protected_resource_metadata.endswith("/.well-known/oauth-protected-resource/api/v1/mcp")
    with pytest.raises(McpOAuthError, match="HTTPS"):
        oauth_urls("http://api.example.test", production=True)


def test_oauth_urls_support_deployment_owned_public_mcp_url():
    urls = oauth_urls(
        "",
        public_mcp_url="https://mcp.example.test/control-plane/mcp",
        production=True,
    )

    assert urls.resource == "https://mcp.example.test/control-plane/mcp"
    assert urls.public_api_base == "https://mcp.example.test"
    assert urls.issuer == "https://mcp.example.test/control-plane/mcp/oauth"
    assert urls.protected_resource_metadata == (
        "https://mcp.example.test/.well-known/oauth-protected-resource/control-plane/mcp"
    )
    assert urls.authorization_server_metadata == (
        "https://mcp.example.test/.well-known/oauth-authorization-server/control-plane/mcp/oauth"
    )


def test_resource_scope_and_pkce_are_exact_and_fail_closed():
    urls = oauth_urls("https://api.example.test", production=True)
    assert require_exact_resource(urls.resource, urls) == urls.resource
    with pytest.raises(McpOAuthError, match="exactly"):
        require_exact_resource(urls.resource + "/", urls)
    assert validate_scopes("mcp:read mcp:write") == ("mcp:read", "mcp:write")
    with pytest.raises(McpOAuthError, match="scope"):
        validate_scopes("mcp:write")

    verifier = "a" * 43
    challenge = pkce_s256(verifier)
    assert validate_pkce_s256(challenge, "S256") == challenge
    with pytest.raises(McpOAuthError, match="PKCE"):
        validate_pkce_s256(challenge, "plain")


@pytest.mark.asyncio
@pytest.mark.parametrize("client_id", [None, ""])
async def test_refresh_requires_client_before_any_storage_access(client_id):
    from app.services.mcp_control_plane.oauth_authority import McpOAuthAuthorityError, refresh_tokens

    urls = oauth_urls("https://api.example.test", production=True)

    def forbidden_factory():
        raise AssertionError("missing client_id must not touch token state")

    with pytest.raises(McpOAuthAuthorityError, match="client_id is required"):
        await refresh_tokens(
            forbidden_factory,
            refresh_token="synthetic-token",
            resource=urls.resource,
            urls=urls,
            scope=None,
            client_id=client_id,
        )


def test_redirect_registration_allows_ip_loopback_dynamic_port_and_exact_path_query_only():
    assert validate_redirect_uris(
        ["https://client.example.test/oauth/callback", "http://127.0.0.1/callback?flow=desktop"]
    ) == (
        "https://client.example.test/oauth/callback",
        "http://127.0.0.1/callback?flow=desktop",
    )
    assert redirect_uri_matches(
        "http://127.0.0.1/callback?flow=desktop", "http://127.0.0.1:41337/callback?flow=desktop"
    )
    assert redirect_uri_matches("http://[::1]/callback", "http://[::1]:41337/callback")
    assert not redirect_uri_matches("http://127.0.0.1/callback", "http://127.0.0.1/other")
    assert not redirect_uri_matches("http://127.0.0.1/callback?a=1", "http://127.0.0.1/callback?a=2")
    assert validate_redirect_uris(["http://localhost/callback"]) == ("http://localhost/callback",)
    assert redirect_uri_matches("http://localhost/callback", "http://localhost:53796/callback")
    with pytest.raises(McpOAuthError, match="loopback"):
        validate_redirect_uris(["http://example.test/callback"])
    with pytest.raises(McpOAuthError, match="credentials"):
        validate_redirect_uris(["http://127.0.0.1/callback#fragment"])
    with pytest.raises(McpOAuthError, match="loopback"):
        validate_redirect_uris(["https://*.example.test/callback"])
    with pytest.raises(McpOAuthError, match="credentials"):
        validate_redirect_uris(["https://user:pass@client.example.test/callback"])


@pytest.mark.asyncio
async def test_authenticated_consent_details_are_never_cacheable(monkeypatch):
    monkeypatch.setattr(mcp_api, "_require_enabled", lambda: None)
    monkeypatch.setattr(mcp_api, "_session_factory", lambda: object())
    monkeypatch.setattr(
        mcp_api,
        "load_consent_ticket",
        AsyncMock(
            return_value=SimpleNamespace(
                client_id="client-id",
                client_name="Example client",
                redirect_uri="https://client.example.test/callback",
                scopes=("mcp:read",),
                grant_deadline=datetime(2026, 8, 1, tzinfo=UTC),
            )
        ),
    )

    response = await mcp_api.get_oauth_consent(
        "ticket",
        token_info={"user_id": "user-a", "project_id": "project-a"},
    )

    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert b"client-id" in response.body
    import json

    assert json.loads(response.body)["ongoing_supported"] is True


def test_public_client_metadata_is_closed_to_public_oauth_contract():
    from app.services.mcp_control_plane.oauth_authority import (
        McpOAuthAuthorityError,
        _validate_public_client_metadata,
    )

    metadata = {
        "client_name": "Desktop MCP",
        "redirect_uris": ["https://client.example.test/callback"],
        "grant_types": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_method": "none",
        "client_secret": "ignored-by-callers-but-never-stored",
    }
    assert _validate_public_client_metadata(metadata) == {
        "client_id": None,
        "client_name": "Desktop MCP",
        "redirect_uris": ["https://client.example.test/callback"],
        "grant_types": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_method": "none",
    }
    with pytest.raises(McpOAuthAuthorityError, match="public"):
        _validate_public_client_metadata({**metadata, "token_endpoint_auth_method": "client_secret_post"})
    with pytest.raises(McpOAuthAuthorityError, match="authorization_code"):
        _validate_public_client_metadata({**metadata, "grant_types": ["authorization_code"]})


@pytest.mark.asyncio
async def test_dynamic_registration_uses_public_transport_and_never_stores_secrets(monkeypatch):
    from app.main import app

    added_clients = []

    class CapturingSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        def begin(self):
            return self

        def add(self, client):
            added_clients.append(client)

    monkeypatch.setattr(mcp_api, "_require_enabled", lambda: None)
    monkeypatch.setattr(mcp_api, "_session_factory", lambda: CapturingSession)
    registration = {
        "client_name": "Desktop MCP",
        "redirect_uris": ["https://client.example.test/callback"],
        "grant_types": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_method": "none",
        "client_secret": "never-store-this",
    }
    issued_before = int(datetime.now(UTC).timestamp())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/mcp/oauth/register", json=registration)
        rejected = await client.post("/api/v1/mcp/oauth/register", json={**registration, "client_id": "attacker-id"})
    issued_after = int(datetime.now(UTC).timestamp())

    assert response.status_code == 201
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    payload = response.json()
    assert payload["client_id"].startswith("afterglow-dcr-")
    assert issued_before <= payload["client_id_issued_at"] <= issued_after
    assert payload["client_id_expires_at"] > payload["client_id_issued_at"]
    assert payload["redirect_uris"] == registration["redirect_uris"]
    assert payload["grant_types"] == registration["grant_types"]
    assert payload["token_endpoint_auth_method"] == "none"
    assert "client_secret" not in payload
    assert len(added_clients) == 1
    assert added_clients[0].metadata_json == {
        "client_id": payload["client_id"],
        "client_name": "Desktop MCP",
        "redirect_uris": ["https://client.example.test/callback"],
        "grant_types": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_method": "none",
    }
    assert rejected.status_code == 400
    assert rejected.json()["error"] == "invalid_request"
    assert "client_id" in rejected.json()["error_description"]


@pytest.mark.asyncio
async def test_dynamic_registration_accepts_localhost_callback_and_rejects_bad_redirect_as_400(monkeypatch):
    from app.main import app

    added_clients = []

    class CapturingSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        def begin(self):
            return self

        def add(self, client):
            added_clients.append(client)

    monkeypatch.setattr(mcp_api, "_require_enabled", lambda: None)
    monkeypatch.setattr(mcp_api, "_session_factory", lambda: CapturingSession)
    claude_code_registration = {
        "client_name": "Claude Code",
        "redirect_uris": ["http://localhost:53796/callback"],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "scope": "mcp:read mcp:write",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        accepted = await client.post("/api/v1/mcp/oauth/register", json=claude_code_registration)
        rejected = await client.post(
            "/api/v1/mcp/oauth/register",
            json={**claude_code_registration, "redirect_uris": ["http://example.test/callback"]},
        )

    assert accepted.status_code == 201
    assert accepted.json()["redirect_uris"] == ["http://localhost:53796/callback"]
    assert len(added_clients) == 1
    assert rejected.status_code == 400
    assert rejected.json()["error"] == "invalid_request"
    assert "loopback" in rejected.json()["error_description"]


@pytest.mark.asyncio
async def test_token_and_revoke_reject_public_client_secrets_at_transport_boundary(monkeypatch):
    from app.main import app

    monkeypatch.setattr(mcp_api, "_require_enabled", lambda: None)
    exchange = AsyncMock()
    revoke = AsyncMock()
    monkeypatch.setattr(mcp_api, "exchange_authorization_code", exchange)
    monkeypatch.setattr(mcp_api, "revoke_oauth_token", revoke)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token_secret = await client.post(
            "/api/v1/mcp/oauth/token",
            data={"grant_type": "authorization_code", "client_secret": "secret"},
        )
        revoke_secret = await client.post(
            "/api/v1/mcp/oauth/revoke", data={"token": "token", "client_secret": "secret"}
        )
        token_basic = await client.post(
            "/api/v1/mcp/oauth/token",
            data={"grant_type": "authorization_code"},
            headers={"Authorization": "Basic Y2xpZW50OnNlY3JldA=="},
        )
        revoke_basic = await client.post(
            "/api/v1/mcp/oauth/revoke",
            data={"token": "token"},
            headers={"Authorization": "Basic Y2xpZW50OnNlY3JldA=="},
        )
        cross_origin = await client.post(
            "/api/v1/mcp/oauth/token",
            data={"grant_type": "authorization_code"},
            headers={"Origin": "https://attacker.example"},
        )

    for response in (token_secret, revoke_secret):
        assert response.status_code == 400
        assert response.json()["error"] == "invalid_client"
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["referrer-policy"] == "no-referrer"
    for response in (token_basic, revoke_basic):
        assert response.status_code == 401
        assert response.json()["error"] == "invalid_client"
        assert response.headers["www-authenticate"] == 'Basic realm="MCP OAuth"'
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["referrer-policy"] == "no-referrer"
    assert cross_origin.status_code == 403
    exchange.assert_not_awaited()
    revoke.assert_not_awaited()


@pytest.mark.parametrize(
    ("requested", "chosen", "expected"),
    [
        (["mcp:read"], None, ("read", ("mcp:read",))),
        (["mcp:read", "mcp:write"], None, ("manage", ("mcp:read", "mcp:write"))),
        (["mcp:read", "mcp:write"], "read", ("read", ("mcp:read",))),
    ],
)
def test_consent_access_choice_never_expands_requested_scope(requested, chosen, expected):
    from app.services.mcp_control_plane.oauth_authority import _consent_scopes

    assert _consent_scopes(requested, chosen) == expected


def test_read_only_oauth_request_cannot_approve_manage():
    from app.services.mcp_control_plane.oauth_authority import McpOAuthAuthorityError, _consent_scopes

    with pytest.raises(McpOAuthAuthorityError, match="may not expand"):
        _consent_scopes(["mcp:read"], "manage")


@pytest.mark.parametrize("value", ["true", "false", 0, 1, None, [], {}])
def test_ongoing_consent_requires_json_boolean(value):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        mcp_api.OAuthConsentApproval(ongoing=value)


def test_ongoing_consent_preserves_old_client_finite_default():
    assert mcp_api.OAuthConsentApproval().ongoing is False
    assert mcp_api.OAuthConsentApproval(ongoing=True).ongoing is True
    assert mcp_api.OAuthConsentApproval(ongoing=False).ongoing is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body,expected", [(None, False), ({}, False), ({"ongoing": False}, False), ({"ongoing": True}, True)]
)
async def test_consent_endpoint_forwards_only_explicit_ongoing_approval(monkeypatch, body, expected):
    from app.main import app

    approve = AsyncMock(
        return_value=SimpleNamespace(
            redirect_uri="https://client.example.test/callback",
            code="code",
            state="state",
            effective_ongoing=expected,
        )
    )
    monkeypatch.setattr(mcp_api, "_require_enabled", lambda: None)
    monkeypatch.setattr(mcp_api, "_require_browser_mutation", lambda request: None)
    monkeypatch.setattr(mcp_api, "_session_factory", lambda: object())
    monkeypatch.setattr(mcp_api, "_mark_transactional_audit", lambda: None)
    monkeypatch.setattr(mcp_api, "approve_consent_ticket", approve)
    monkeypatch.setitem(
        app.dependency_overrides,
        mcp_api.get_token_info,
        lambda: {"user_id": "owner", "project_id": "project", "roles": []},
    )
    monkeypatch.setitem(app.dependency_overrides, mcp_api.get_os_conn, lambda: object())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/auth/mcp-oauth/consents/ticket/approve", json=body)
    assert response.status_code == 200
    assert approve.await_args.kwargs["ongoing"] is expected
    assert response.json()["effective_ongoing"] is expected


@pytest.mark.parametrize(
    "source,ongoing,deadline,ceiling,expired",
    [
        ("oauth", False, None, None, True),
        ("oauth", True, None, None, True),
        ("oauth", True, None, {}, True),
        ("oauth", True, None, {"project": [{"id": "reader-id", "name": "reader"}]}, False),
        ("lumen", True, None, {"project": [{"id": "reader-id", "name": "reader"}]}, True),
        ("personal_token", False, None, None, False),
    ],
)
def test_unbounded_authority_requires_explicit_source_and_frozen_ceiling(source, ongoing, deadline, ceiling, expired):
    from app.services.mcp_control_plane.authority import grant_is_expired

    grant = SimpleNamespace(source=source, oauth_ongoing=ongoing, expires_at=deadline, issued_role_ceiling=ceiling)
    assert grant_is_expired(grant) is expired


def test_null_refresh_deadline_does_not_upgrade_finite_oauth():
    from app.services.mcp_control_plane.oauth_authority import _refresh_is_expired

    now = datetime.now(UTC)
    token = SimpleNamespace(expires_at=None)
    grant = SimpleNamespace(source="oauth", oauth_ongoing=False, expires_at=now)
    assert _refresh_is_expired(token, grant, now) is True


def test_consent_rejects_unknown_renewal_fields_instead_of_silent_downgrade():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        mcp_api.OAuthConsentApproval(continual=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", list(McpOAuthFailureReason))
async def test_token_operational_reasons_are_private_and_secret_free(monkeypatch, caplog, reason):
    from app.main import app
    from app.utils.log import SensitiveDataFilter
    from app.utils.structured_logging import JSONFormatter

    secret = "DO-NOT-LOG-secret-client-or-token"
    monkeypatch.setattr(mcp_api, "_require_enabled", lambda: None)
    monkeypatch.setattr(mcp_api, "_session_factory", lambda: object())
    monkeypatch.setattr(mcp_api, "_urls", lambda: oauth_urls("https://api.example.test", production=True))
    monkeypatch.setattr(
        mcp_api,
        "refresh_tokens",
        AsyncMock(side_effect=McpOAuthAuthorityError(secret, reason=reason)),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/mcp/oauth/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": secret,
                "client_id": secret,
                "resource": "https://private.example.test/" + secret,
            },
        )
    assert response.status_code == 400
    assert response.json() == {"error": "invalid_grant", "error_description": "OAuth grant is invalid"}
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "reason" not in response.headers
    assert secret not in caplog.text
    records = [record for record in caplog.records if record.name == "app.api.mcp"]
    sanitizer = SensitiveDataFilter()
    formatter = JSONFormatter()
    diagnostics = []
    for record in records:
        sanitizer.filter(record)
        serialized = formatter.format(record)
        assert secret not in serialized
        diagnostics.append(json.loads(serialized)["diagnostic_reason"])
    assert diagnostics == [reason.value]
    assert all(record.exc_info is None for record in records)


@pytest.mark.asyncio
async def test_token_malformed_form_has_bounded_reason_and_no_payload_logging(monkeypatch, caplog):
    from app.main import app

    monkeypatch.setattr(mcp_api, "_require_enabled", lambda: None)
    refresh = AsyncMock()
    monkeypatch.setattr(mcp_api, "refresh_tokens", refresh)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/mcp/oauth/token",
            content="grant_type=refresh_token&refresh_token=private-payload&refresh_token=duplicate-secret",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    assert response.status_code == 400
    assert response.json() == {"error": "invalid_grant", "error_description": "OAuth grant is invalid"}
    records = [record for record in caplog.records if record.name == "app.api.mcp"]
    assert [record.diagnostic_reason for record in records] == [McpOAuthFailureReason.INVALID_SHAPE.value]
    assert "private-payload" not in caplog.text
    assert "duplicate-secret" not in caplog.text
    refresh.assert_not_awaited()


@pytest.mark.parametrize("grant_types", [None, "authorization_code", [{}], ["authorization_code", None]])
def test_public_client_grant_types_must_be_a_string_list(grant_types):
    from app.services.mcp_control_plane.oauth_authority import (
        McpOAuthAuthorityError,
        _validate_public_client_metadata,
    )

    metadata = {
        "redirect_uris": ["https://client.example.test/callback"],
        "grant_types": grant_types,
        "token_endpoint_auth_method": "none",
    }
    with pytest.raises(McpOAuthAuthorityError, match="authorization_code and refresh_token"):
        _validate_public_client_metadata(metadata)


@pytest.mark.asyncio
async def test_consent_details_name_the_authorization_domain(monkeypatch):
    import json

    monkeypatch.setattr(mcp_api, "_require_enabled", lambda: None)
    monkeypatch.setattr(mcp_api, "_session_factory", lambda: object())
    monkeypatch.setattr(
        mcp_api,
        "load_consent_ticket",
        AsyncMock(
            return_value=SimpleNamespace(
                client_id="client-id",
                client_name="Codex",
                redirect_uri="http://localhost:53796/callback",
                scopes=("mcp:read",),
                grant_deadline=datetime(2026, 8, 1, tzinfo=UTC),
            )
        ),
    )

    response = await mcp_api.get_oauth_consent(
        "ticket",
        token_info={"user_id": "user-a", "project_id": "project-a", "domain_id": "domain-a", "domain_name": "DMS Lab"},
    )

    payload = json.loads(response.body)
    assert payload["domain_id"] == "domain-a"
    assert payload["domain_name"] == "DMS Lab"
