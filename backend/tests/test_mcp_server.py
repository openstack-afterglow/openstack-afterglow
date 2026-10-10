from __future__ import annotations

import pytest

from app.config import get_settings


@pytest.fixture(autouse=True)
def isolated_runtime_authority(monkeypatch):
    from dataclasses import replace

    async def resolve(principal, project_id=None, *, write=False):
        return replace(
            principal, project_id=project_id or principal.project_id, owner_project_id=principal.anchor_project_id
        )

    monkeypatch.setattr("app.services.mcp_control_plane.registry.resolve_principal_target", resolve)


def test_mcp_routers_keep_paths_relative_to_their_mounts():
    from app.api.mcp import auth_router, root_router, router

    api_paths = {route.path for route in router.routes}
    auth_paths = {route.path for route in auth_router.routes}
    root_paths = {route.path for route in root_router.routes}

    assert {"/oauth/register", "/oauth/authorize", "/oauth/token", "/oauth/revoke"} <= api_paths
    assert "/mcp-oauth/consents/{ticket}" in auth_paths
    assert "/.well-known/oauth-protected-resource/{resource_path:path}" in root_paths
    assert all(not path.startswith("/api/") for path in api_paths | auth_paths | root_paths)


@pytest.mark.asyncio
async def test_public_oauth_routes_never_emit_cors_headers(client, monkeypatch):
    from app.api import mcp

    monkeypatch.setattr(mcp, "_require_enabled", lambda: None)
    origin = get_settings().cors_origin_list[0]

    preflight = await client.options(
        "/api/v1/mcp/oauth/token",
        headers={"Origin": origin, "Access-Control-Request-Method": "POST"},
    )
    assert preflight.status_code == 405
    assert not any(header.lower().startswith("access-control-allow-") for header in preflight.headers)

    cross_origin_post = await client.post(
        "/api/v1/mcp/oauth/token",
        headers={"Origin": origin, "Content-Type": "application/x-www-form-urlencoded"},
        content="grant_type=refresh_token&refresh_token=not-a-token&resource=https%3A%2F%2Fapi.example.test%2Fapi%2Fv1%2Fmcp",
    )
    assert cross_origin_post.status_code == 403
    assert not any(header.lower().startswith("access-control-allow-") for header in cross_origin_post.headers)


@pytest.mark.asyncio
async def test_oauth_metadata_publishes_exact_resource_and_issuer(client, monkeypatch):
    from types import SimpleNamespace

    from app.api import mcp

    monkeypatch.setattr(
        mcp,
        "get_settings",
        lambda: SimpleNamespace(service_mcp_enabled=True, public_api_base="https://api.example.test"),
    )

    protected = await client.get("/.well-known/oauth-protected-resource/api/v1/mcp")
    authorization = await client.get("/.well-known/oauth-authorization-server/api/v1/mcp/oauth")

    assert protected.json()["resource"] == "https://api.example.test/api/v1/mcp"
    assert protected.json()["authorization_servers"] == ["https://api.example.test/api/v1/mcp/oauth"]
    assert authorization.json()["issuer"] == "https://api.example.test/api/v1/mcp/oauth"


@pytest.mark.asyncio
async def test_oauth_metadata_uses_deployment_owned_public_mcp_url(client, monkeypatch):
    from types import SimpleNamespace

    from app.api import mcp

    monkeypatch.setattr(
        mcp,
        "get_settings",
        lambda: SimpleNamespace(
            service_mcp_enabled=True,
            public_api_base="https://api.example.test",
            mcp_public_url="https://mcp.example.test/control-plane/mcp",
        ),
    )

    protected = await client.get("/.well-known/oauth-protected-resource/control-plane/mcp")
    authorization = await client.get("/.well-known/oauth-authorization-server/control-plane/mcp/oauth")

    assert protected.json()["resource"] == "https://mcp.example.test/control-plane/mcp"
    assert (
        authorization.json()["authorization_endpoint"] == "https://mcp.example.test/control-plane/mcp/oauth/authorize"
    )


@pytest.mark.asyncio
async def test_configured_mcp_path_accepts_streamable_http_bearers(monkeypatch):
    from types import SimpleNamespace

    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.services.mcp_control_plane import transport

    settings = SimpleNamespace(
        service_mcp_enabled=True,
        public_api_base="",
        mcp_public_url="https://mcp.example.test/control-plane/mcp",
        mcp_request_max_bytes=1024 * 1024,
        secret_key="a" * 64,
    )
    monkeypatch.setattr(transport, "get_settings", lambda: settings)
    app = FastAPI()
    transport.install_mcp_route(app)
    await transport.start_mcp_transport()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://mcp.example.test") as ac:
            response = await ac.post(
                "/control-plane/mcp",
                headers={
                    "Host": "mcp.example.test",
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                },
                json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            )
    finally:
        await transport.stop_mcp_transport()

    assert response.status_code == 401
    assert response.headers["www-authenticate"].endswith(
        'resource_metadata="https://mcp.example.test/.well-known/oauth-protected-resource/control-plane/mcp"'
    )


@pytest.mark.asyncio
async def test_configured_mcp_oauth_alias_dispatches_only_configured_path(client, monkeypatch):
    from types import SimpleNamespace

    from starlette.responses import JSONResponse

    from app.api import mcp

    monkeypatch.setattr(
        mcp,
        "get_settings",
        lambda: SimpleNamespace(
            service_mcp_enabled=True,
            public_api_base="",
            mcp_public_url="https://mcp.example.test/control-plane/mcp",
        ),
    )

    async def register(_: object):
        return JSONResponse({"registered": True})

    monkeypatch.setattr(mcp, "oauth_register", register)
    accepted = await client.post("/control-plane/mcp/oauth/register")
    rejected = await client.post("/wrong-path/oauth/register")

    assert accepted.status_code == 200
    assert accepted.json() == {"registered": True}
    assert rejected.status_code == 404


@pytest.mark.asyncio
async def test_configured_mcp_oauth_paths_bypass_cors_for_allowed_origins(client, monkeypatch):
    from types import SimpleNamespace

    from app import main
    from app.api import mcp
    from app.services.mcp_control_plane import transport

    settings = SimpleNamespace(
        service_mcp_enabled=True,
        public_api_base="",
        mcp_public_url="https://mcp.example.test/control-plane/mcp",
    )
    monkeypatch.setattr(mcp, "get_settings", lambda: settings)
    monkeypatch.setattr(transport, "get_settings", lambda: settings)
    monkeypatch.setattr(main, "_get_allowed_origins", lambda: {"https://frontend.example.test"})

    responses = []
    for path in ("/api/v1/mcp/oauth/token", "/control-plane/mcp/oauth/token"):
        responses.extend(
            (
                await client.options(
                    path,
                    headers={"Origin": "https://frontend.example.test", "Access-Control-Request-Method": "POST"},
                ),
                await client.post(
                    path,
                    headers={
                        "Origin": "https://frontend.example.test",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    content="grant_type=refresh_token&refresh_token=not-a-token",
                ),
            )
        )

    assert [response.status_code for response in responses] == [405, 403, 405, 403]
    for response in responses:
        assert not any(header.lower().startswith("access-control-allow-") for header in response.headers)


def test_mcp_cors_paths_follow_canonical_transport_routes(monkeypatch):
    from types import SimpleNamespace

    from app import main
    from app.services.mcp_control_plane import transport

    monkeypatch.setattr(
        transport,
        "_urls",
        lambda: SimpleNamespace(resource="https://mcp.example.test/control-plane/mcp"),
    )

    assert main._is_mcp_no_cors_path("/api/v1/mcp")
    assert main._is_mcp_no_cors_path("/api/v1/mcp/oauth/token")
    assert main._is_mcp_no_cors_path("/control-plane/mcp")
    assert main._is_mcp_no_cors_path("/control-plane/mcp/oauth/token")
    assert not main._is_mcp_no_cors_path("/wrong-path/oauth/token")


@pytest.mark.asyncio
async def test_enabled_mcp_transport_requires_bearer_and_never_emits_cors(client, monkeypatch):
    from types import SimpleNamespace

    from app.services.mcp_control_plane import transport

    settings = SimpleNamespace(
        service_mcp_enabled=True,
        public_api_base="https://api.example.test",
        mcp_request_max_bytes=1024 * 1024,
        secret_key="a" * 64,
    )
    monkeypatch.setattr(transport, "get_settings", lambda: settings)
    await transport.start_mcp_transport()
    try:
        response = await client.post(
            "/api/v1/mcp",
            headers={
                "Host": "api.example.test",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        )
    finally:
        await transport.stop_mcp_transport()

    assert response.status_code == 401
    assert "resource_metadata" in response.headers["www-authenticate"]
    assert not any(header.lower().startswith("access-control-allow-") for header in response.headers)


@pytest.mark.asyncio
async def test_mcp_transport_is_disabled_and_never_redirects_trailing_slashes(client, monkeypatch):
    from types import SimpleNamespace

    from app.services.mcp_control_plane import transport

    monkeypatch.setattr(
        transport,
        "get_settings",
        lambda: SimpleNamespace(
            service_mcp_enabled=False,
            public_api_base="",
            mcp_public_url="",
        ),
    )
    exact = await client.get("/api/v1/mcp")
    trailing = await client.get("/api/v1/mcp/")

    assert exact.status_code == 404
    assert trailing.status_code == 404
    assert "location" not in exact.headers
    assert "location" not in trailing.headers


@pytest.mark.asyncio
async def test_mcp_transport_manager_restarts_cleanly_between_application_lifecycles():
    from app.services.mcp_control_plane import transport

    await transport.start_mcp_transport()
    assert transport._manager is not None
    await transport.stop_mcp_transport()
    assert transport._manager is None

    await transport.start_mcp_transport()
    assert transport._manager is not None
    await transport.stop_mcp_transport()


def test_mcp_tool_cursor_is_bound_to_grant_registry_and_enabled_services(monkeypatch):
    from types import SimpleNamespace

    from app.services.mcp_control_plane import transport
    from app.services.mcp_control_plane.authentication import McpPrincipal

    monkeypatch.setattr(transport, "get_settings", lambda: SimpleNamespace(secret_key="a" * 64))
    monkeypatch.setattr(transport, "enabled_service_fingerprint", lambda: "services-a")
    principal = McpPrincipal(
        grant_id="grant-a",
        user_id="user-a",
        project_id="project-a",
        credential_epoch=1,
        scopes=frozenset({"mcp:read"}),
        source="personal_token",
    )

    cursor = transport._tool_cursor(principal, 3)
    assert transport._tool_cursor_offset(principal, cursor) == 3

    monkeypatch.setattr(transport, "enabled_service_fingerprint", lambda: "services-b")
    with pytest.raises(ValueError, match="cursor"):
        transport._tool_cursor_offset(principal, cursor)


@pytest.mark.asyncio
async def test_mutation_rebuilds_ownership_preview_on_both_sides_of_send_boundary(monkeypatch):
    from app.services.mcp_control_plane import transport
    from app.services.mcp_control_plane.authentication import McpPrincipal
    from app.services.mcp_control_plane.ledger import McpInvocationError, MutationClaim
    from app.services.mcp_control_plane.registry import (
        ConsumerCloudContext,
        McpDomainArguments,
        McpDomainOutput,
        McpMutationPreview,
        RegistryEntry,
    )

    class Arguments(McpDomainArguments):
        resource_id: str

    class Output(McpDomainOutput):
        status: str

    async def handler(_: ConsumerCloudContext, __: Arguments) -> Output:
        return Output(status="accepted")

    async def preview(_: ConsumerCloudContext, arguments: Arguments) -> McpMutationPreview:
        return McpMutationPreview(
            resource_identity=arguments.resource_id,
            current_state="ACTIVE",
            intended_transition="stop",
            dependent_resources=[],
            destructive=False,
            estimated_effect=None,
            fingerprint="preview",
        )

    entry = RegistryEntry(
        name="afterglow_test_mutation",
        description="test mutation",
        arguments=Arguments,
        output=Output,
        minimum_scope="mcp:write",
        effect="external_mutation",
        service_flag=None,
        timeout_seconds=10,
        result_max_bytes=1024,
        handler=handler,
        preview_builder=preview,
    )
    calls: list[str] = []

    async def record_preview(context, *, arguments, **_kwargs):
        calls.append("preview")
        return await preview(context, arguments)

    async def claim(*_args, **_kwargs):
        calls.append("claim")
        return MutationClaim(state="claimed", invocation_id="invocation-a")

    async def authorize(*_args, **_kwargs):
        calls.append("authorize")

    async def run(*_args, **_kwargs):
        calls.append("dispatch")
        return Output(status="accepted")

    async def complete(*_args, **_kwargs):
        calls.append("complete")

    monkeypatch.setattr(transport, "entry_by_name", lambda name: entry if name == entry.name else None)
    monkeypatch.setattr(transport, "build_mutation_preview", record_preview)
    monkeypatch.setattr(transport, "claim_mutation", claim)
    monkeypatch.setattr(transport, "authorize_mutation_dispatch", authorize)
    monkeypatch.setattr(transport, "dispatch", run)
    monkeypatch.setattr(transport, "complete_mutation", complete)
    principal = McpPrincipal(
        grant_id="grant-a",
        user_id="user-a",
        project_id="project-a",
        credential_epoch=1,
        scopes=frozenset({"mcp:write"}),
        source="personal_token",
    )
    token = transport._current_principal.set(principal)
    try:
        with pytest.raises(McpInvocationError, match="idempotency"):
            await transport._call_tool(
                entry.name,
                {"resource_id": "vm-a", "idempotency_key": "short"},
            )
        assert calls == []
        result = await transport._call_tool(
            entry.name,
            {"resource_id": "vm-a", "idempotency_key": "call-0001"},
        )
        assert calls == ["claim", "preview", "authorize", "dispatch", "complete"]

        async def replay(*_args, **_kwargs):
            return MutationClaim(state="replay", invocation_id="invocation-a", result={"status": "accepted"})

        monkeypatch.setattr(transport, "claim_mutation", replay)
        calls.clear()
        replayed = await transport._call_tool(
            entry.name,
            {"resource_id": "vm-a", "idempotency_key": "call-0001"},
        )
        assert replayed == {"status": "accepted"}
        assert calls == []
    finally:
        transport._current_principal.reset(token)

    assert result == {"status": "accepted"}


@pytest.mark.asyncio
async def test_mutation_preview_failure_is_durably_failed_before_dispatch(monkeypatch):
    from app.services.mcp_control_plane import transport
    from app.services.mcp_control_plane.authentication import McpPrincipal
    from app.services.mcp_control_plane.ledger import MutationClaim
    from app.services.mcp_control_plane.registry import (
        ConsumerCloudContext,
        McpDomainArguments,
        McpDomainOutput,
        McpMutationPreview,
        RegistryEntry,
    )

    class Arguments(McpDomainArguments):
        resource_id: str

    class Output(McpDomainOutput):
        status: str

    async def handler(_: ConsumerCloudContext, __: Arguments) -> Output:
        return Output(status="accepted")

    async def preview(*_args, **_kwargs) -> McpMutationPreview:
        raise ValueError("resource is no longer actionable")

    entry = RegistryEntry(
        name="afterglow_test_preview_failure",
        description="test mutation",
        arguments=Arguments,
        output=Output,
        minimum_scope="mcp:write",
        effect="external_mutation",
        service_flag=None,
        timeout_seconds=10,
        result_max_bytes=1024,
        handler=handler,
        preview_builder=preview,
    )
    calls: list[str] = []

    async def claim(*_args, **_kwargs):
        calls.append("claim")
        return MutationClaim(state="claimed", invocation_id="invocation-a")

    async def fail(*_args, **_kwargs):
        calls.append("fail")

    async def forbidden(*_args, **_kwargs):
        raise AssertionError("dispatch authorization must not run after pre-dispatch failure")

    monkeypatch.setattr(transport, "entry_by_name", lambda name: entry if name == entry.name else None)
    monkeypatch.setattr(transport, "claim_mutation", claim)
    monkeypatch.setattr(transport, "build_mutation_preview", preview)
    monkeypatch.setattr(transport, "fail_pre_dispatch", fail)
    monkeypatch.setattr(transport, "authorize_mutation_dispatch", forbidden)
    monkeypatch.setattr(transport, "dispatch", forbidden)
    principal = McpPrincipal(
        grant_id="grant-a",
        user_id="user-a",
        project_id="project-a",
        credential_epoch=1,
        scopes=frozenset({"mcp:write"}),
        source="personal_token",
    )
    token = transport._current_principal.set(principal)
    try:
        with pytest.raises(ValueError, match="no longer actionable"):
            await transport._call_tool(
                entry.name,
                {"resource_id": "vm-a", "idempotency_key": "call-0002"},
            )
    finally:
        transport._current_principal.reset(token)

    assert calls == ["claim", "fail"]
