from __future__ import annotations

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
    with pytest.raises(McpOAuthError, match="IP-literal"):
        validate_redirect_uris(["http://localhost/callback"])
    with pytest.raises(McpOAuthError, match="credentials"):
        validate_redirect_uris(["http://127.0.0.1/callback#fragment"])
    with pytest.raises(McpOAuthError, match="IP-literal"):
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
