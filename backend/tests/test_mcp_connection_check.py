"""Personal MCP connection check and origin-root MCP resource, through the real protocol stack.

The browser endpoint runs the real MCP SDK client against the real Afterglow
Streamable HTTP server (ASGI in-process instead of a socket). Only the grant
authority, rate-limit slot and tool registry are replaced by fakes.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from app import main
from app.api import mcp as mcp_api
from app.api.identity import mcp_access
from app.config import get_settings
from app.services.mcp_control_plane import transport, verification
from app.services.mcp_control_plane.authentication import McpAuthenticationError, McpPrincipal
from app.services.site_branding import configured_public_site_config

ROOT_RESOURCE = "https://mcp.example.test"
OWN_TOKEN = "mcp-afgl-" + "o" * 43
FOREIGN_USER_TOKEN = "mcp-afgl-" + "f" * 43
OTHER_PROJECT_TOKEN = "mcp-afgl-" + "p" * 43
REVOKED_TOKEN = "mcp-afgl-" + "r" * 43
BROWSER_HEADERS = {"Origin": "https://app.example.test", "Sec-Fetch-Site": "same-site"}
VERIFY_PATH = "/api/v1/auth/mcp-tokens/verify"


def _principal(user_id: str, project_id: str) -> McpPrincipal:
    return McpPrincipal(
        grant_id=f"grant-{user_id}-{project_id}",
        user_id=user_id,
        project_id=project_id,
        credential_epoch=1,
        scopes=frozenset({"mcp:read"}),
        source="personal_token",
    )


# conftest.make_token_info: user test-user-123 in project test-project-123.
GRANTS = {
    OWN_TOKEN: _principal("test-user-123", "test-project-123"),
    FOREIGN_USER_TOKEN: _principal("someone-else", "test-project-123"),
    OTHER_PROJECT_TOKEN: _principal("test-user-123", "another-project"),
}


class _Tool:
    effect = "read"

    def __init__(self, index: int) -> None:
        self.name = f"tool_{index}"
        self.description = f"read-only tool {index}"

    def mcp_input_schema(self) -> dict:
        return {"type": "object", "properties": {}}

    def output_schema(self) -> None:
        return None


class _Recorder:
    """ASGI wrapper recording every request that reaches the network boundary."""

    def __init__(self, app) -> None:
        self.app = app
        self.requests: list[dict] = []

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        messages, body = [], b""
        while True:
            message = await receive()
            messages.append(message)
            body += message.get("body", b"")
            if not message.get("more_body"):
                break
        payload = json.loads(body) if body else None
        self.requests.append(
            {
                "host": dict(scope["headers"]).get(b"host", b"").decode(),
                "path": scope["path"],
                "headers": {key.decode().lower(): value.decode() for key, value in scope["headers"]},
                "rpc": payload.get("method") if isinstance(payload, dict) else None,
            }
        )

        async def replay():
            return messages.pop(0) if messages else {"type": "http.disconnect"}

        await self.app(scope, replay, send)


@pytest.fixture
def root_mcp(monkeypatch):
    settings = SimpleNamespace(
        service_mcp_enabled=True,
        public_api_base="https://api.example.test",
        mcp_public_url=f"{ROOT_RESOURCE}/",
        mcp_oauth_consent_url="",
        frontend_base_url="https://app.example.test",
        cors_origin_list=("https://app.example.test",),
        mcp_request_max_bytes=1024 * 1024,
        mcp_default_page_size=2,
        secret_key="s" * 64,
    )
    for module in (transport, mcp_api, mcp_access):
        monkeypatch.setattr(module, "get_settings", lambda: settings)
    monkeypatch.setattr(mcp_access, "_session_factory", lambda: object())

    authority = SimpleNamespace(audiences=[], server_rejects=False)

    async def local_authority(raw_token: str, *, urls):
        authority.audiences.append(("local", urls.resource))
        if raw_token not in GRANTS:
            raise McpAuthenticationError("MCP bearer token is invalid")
        return GRANTS[raw_token]

    async def server_authority(raw_token: str, *, urls):
        authority.audiences.append(("server", urls.resource))
        if authority.server_rejects or raw_token not in GRANTS:
            raise McpAuthenticationError("MCP bearer token is invalid")
        return GRANTS[raw_token]

    @asynccontextmanager
    async def no_slot(_principal, *, effect):
        assert effect == "read"
        yield

    monkeypatch.setattr(verification, "verify_mcp_bearer", local_authority)
    monkeypatch.setattr(transport, "verify_mcp_bearer", server_authority)
    monkeypatch.setattr(transport, "grant_call_slot", no_slot)
    monkeypatch.setattr(transport, "enabled_entries", lambda _principal: [_Tool(index) for index in range(5)])
    monkeypatch.setattr(transport, "enabled_service_fingerprint", lambda: "services")

    mcp_app = FastAPI()
    transport.install_mcp_route(mcp_app)
    recorder = _Recorder(mcp_app)
    monkeypatch.setattr(verification, "_network_transport", lambda: httpx.ASGITransport(app=recorder))
    return SimpleNamespace(settings=settings, authority=authority, recorder=recorder, app=mcp_app)


@pytest.fixture
def running_transport():
    @asynccontextmanager
    async def running():
        # AnyIO cancel scopes must enter and exit in the same test task.
        await transport.start_mcp_transport()
        try:
            yield
        finally:
            await transport.stop_mcp_transport()

    return running


@pytest.mark.asyncio
async def test_owner_key_completes_real_handshake_at_the_origin_root(client, root_mcp, running_transport):
    async with running_transport():
        response = await client.post(VERIFY_PATH, json={"token": OWN_TOKEN}, headers=BROWSER_HEADERS)

    assert response.status_code == 200, response.text
    assert response.json() == {
        "endpoint": ROOT_RESOURCE,
        "protocol_version": "2025-11-25",
        "server_name": "afterglow-consumer-mcp",
        "server_version": "1.0",
        "tool_count": 5,
    }
    assert response.headers["cache-control"] == "no-store"
    assert OWN_TOKEN not in response.text

    requests = root_mcp.recorder.requests
    # Complete pagination (2 + 2 + 1) and never a tool execution.
    assert [request["rpc"] for request in requests] == [
        "initialize",
        "notifications/initialized",
        "tools/list",
        "tools/list",
        "tools/list",
    ]
    for request in requests:
        assert (request["host"], request["path"]) == ("mcp.example.test", "/")
        assert request["headers"]["authorization"] == f"Bearer {OWN_TOKEN}"
        # The browser session never crosses to the MCP resource; only the PAT does.
        assert "cookie" not in request["headers"]
        assert "x-auth-token" not in request["headers"]
    # Both the local ownership check and the served transport bind the root audience.
    assert set(root_mcp.authority.audiences) == {("local", ROOT_RESOURCE), ("server", ROOT_RESOURCE)}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {"token": FOREIGN_USER_TOKEN},
        {"token": OTHER_PROJECT_TOKEN},
        {"token": REVOKED_TOKEN},
        {"token": "oauth-access-token-not-a-personal-key"},
        {"token": OWN_TOKEN, "endpoint": "https://attacker.example.test"},
        {"token": OWN_TOKEN + "x" * 200},
    ],
    ids=["foreign-user", "other-project", "revoked-or-expired", "non-pat", "caller-url", "oversized"],
)
async def test_non_owned_or_malformed_keys_never_reach_the_network(client, root_mcp, body):
    response = await client.post(VERIFY_PATH, json=body, headers=BROWSER_HEADERS)

    assert response.status_code == 400
    assert response.headers["cache-control"] == "no-store"
    assert body["token"] not in response.text
    assert root_mcp.recorder.requests == []


@pytest.mark.asyncio
async def test_cross_site_requests_cannot_drive_a_connection_check(client, root_mcp):
    response = await client.post(
        VERIFY_PATH,
        json={"token": OWN_TOKEN},
        headers={"Origin": "https://attacker.example.test", "Sec-Fetch-Site": "cross-site"},
    )

    assert response.status_code == 403
    assert root_mcp.recorder.requests == []
    assert root_mcp.authority.audiences == []


@pytest.mark.asyncio
async def test_redirecting_endpoint_is_never_followed_with_the_key(client, root_mcp, monkeypatch):
    async def redirect(scope, receive, send):
        await send(
            {
                "type": "http.response.start",
                "status": 307,
                "headers": [(b"location", b"https://collector.example.test/steal")],
            }
        )
        await send({"type": "http.response.body", "body": b""})

    redirector = _Recorder(redirect)
    monkeypatch.setattr(verification, "_network_transport", lambda: httpx.ASGITransport(app=redirector))

    response = await client.post(VERIFY_PATH, json={"token": OWN_TOKEN}, headers=BROWSER_HEADERS)

    assert response.status_code == 502
    assert response.json()["code"] == "redirect"
    assert [request["host"] for request in redirector.requests] == ["mcp.example.test"]
    assert "collector.example.test" not in response.text
    assert OWN_TOKEN not in response.text


@pytest.mark.asyncio
async def test_served_endpoint_rejection_is_reported_without_upstream_detail(client, root_mcp, running_transport):
    root_mcp.authority.server_rejects = True

    async with running_transport():
        response = await client.post(VERIFY_PATH, json={"token": OWN_TOKEN}, headers=BROWSER_HEADERS)

    assert response.status_code == 502
    assert response.json() == {"detail": "MCP endpoint rejected the personal key", "code": "rejected"}
    assert [request["rpc"] for request in root_mcp.recorder.requests] == ["initialize"]


@pytest.mark.asyncio
async def test_origin_root_resource_serves_discovery_oauth_and_challenge(
    client, root_mcp, running_transport, monkeypatch
):
    protected = await client.get("/.well-known/oauth-protected-resource")
    assert protected.status_code == 200
    assert protected.json()["resource"] == ROOT_RESOURCE
    assert protected.json()["authorization_servers"] == [f"{ROOT_RESOURCE}/oauth"]

    authorization = await client.get("/.well-known/oauth-authorization-server/oauth")
    assert authorization.json()["issuer"] == f"{ROOT_RESOURCE}/oauth"
    assert authorization.json()["token_endpoint"] == f"{ROOT_RESOURCE}/oauth/token"

    # The unauthenticated MCP challenge at "/" points clients at the root metadata.
    async with (
        running_transport(),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=root_mcp.app), base_url=ROOT_RESOURCE) as mcp,
    ):
        challenge = await mcp.post(
            "/",
            headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        )
    assert challenge.status_code == 401
    assert challenge.headers["www-authenticate"] == (
        f'Bearer resource_metadata="{ROOT_RESOURCE}/.well-known/oauth-protected-resource"'
    )

    class _NoRows:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

        async def scalar(self, _statement):
            return None

    monkeypatch.setattr(mcp_api, "_session_factory", lambda: _NoRows)

    async def exchange(resource: str) -> str:
        response = await client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": "code",
                "client_id": "client",
                "redirect_uri": "http://127.0.0.1/callback",
                "resource": resource,
                "code_verifier": "v" * 43,
            },
        )
        return response.json()["error_description"]

    # WHATWG URL clients send the origin-root resource with "/"; both forms are the same
    # resource and pass the audience gate, while any other resource is refused.
    assert await exchange(ROOT_RESOURCE) == "authorization code is invalid"
    assert await exchange(f"{ROOT_RESOURCE}/") == "authorization code is invalid"
    assert await exchange(f"{ROOT_RESOURCE}/api/v1/mcp") == "resource must exactly match this MCP server"

    monkeypatch.setattr(main, "_get_allowed_origins", lambda: {"https://app.example.test"})
    preflight = await client.options(
        "/oauth/token",
        headers={"Origin": "https://app.example.test", "Access-Control-Request-Method": "POST"},
    )
    assert not any(header.lower().startswith("access-control-allow-") for header in preflight.headers)


@pytest.mark.asyncio
async def test_root_aliases_and_metadata_stay_closed_for_the_default_resource(client, root_mcp):
    root_mcp.settings.mcp_public_url = ""

    assert (await client.get("/.well-known/oauth-protected-resource")).status_code == 404
    assert (await client.post("/oauth/token", data={"grant_type": "refresh_token"})).status_code == 404
    default = await client.get("/.well-known/oauth-protected-resource/api/v1/mcp")
    assert default.json()["resource"] == "https://api.example.test/api/v1/mcp"


@pytest.mark.asyncio
async def test_published_connector_url_is_the_served_resource(client, root_mcp):
    explicit = get_settings().model_copy(update={"mcp_public_url": root_mcp.settings.mcp_public_url})
    protected = await client.get("/.well-known/oauth-protected-resource")

    assert configured_public_site_config(explicit)["mcp_url"] == protected.json()["resource"] == ROOT_RESOURCE
