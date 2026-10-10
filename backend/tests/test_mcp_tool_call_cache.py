"""Exercise SDK cache refresh through the actual authenticated HTTP transport."""

from contextlib import asynccontextmanager

import httpx
import jsonschema
import pytest
from fastapi import FastAPI

from app.config import get_settings
from app.services.mcp_control_plane import registry, transport
from app.services.mcp_control_plane.authentication import McpAuthenticationError, McpPrincipal

READ_TOKEN = "mcp-afgl-" + "r" * 43
MANAGE_TOKEN = "mcp-afgl-" + "m" * 43


@pytest.fixture
def running_mcp(monkeypatch):
    settings = get_settings().model_copy(
        update={
            "service_mcp_enabled": True,
            "service_waygate_enabled": False,
            "mcp_public_url": "https://mcp.example.test/mcp",
            "mcp_default_page_size": 1,
            "secret_key": "s" * 64,
        }
    )
    monkeypatch.setattr(transport, "get_settings", lambda: settings)
    monkeypatch.setattr(registry, "get_settings", lambda: settings)
    monkeypatch.setattr(transport._server, "_tool_cache", {})
    # The real tool/schema remains unchanged; move it beyond the first public page.
    monkeypatch.setattr(
        transport, "enabled_entries", lambda principal: tuple(reversed(registry.enabled_entries(principal)))
    )
    principals = {
        READ_TOKEN: McpPrincipal(
            grant_id="read-grant",
            user_id="reader",
            project_id="project-a",
            credential_epoch=1,
            scopes=frozenset({"mcp:read"}),
            source="oauth",
        ),
        MANAGE_TOKEN: McpPrincipal(
            grant_id="manage-grant",
            user_id="manager",
            project_id="project-a",
            credential_epoch=1,
            scopes=frozenset({"mcp:read", "mcp:write"}),
            source="oauth",
        ),
    }

    async def authority(token, *, urls):
        if token not in principals:
            raise McpAuthenticationError("invalid test bearer")
        return principals[token]

    @asynccontextmanager
    async def no_redis_slot(*args, **kwargs):
        yield

    async def no_database_audit(*args, **kwargs):
        pass

    monkeypatch.setattr(transport, "verify_mcp_bearer", authority)
    monkeypatch.setattr(transport, "grant_call_slot", no_redis_slot)
    monkeypatch.setattr(transport, "record_read_invocation", no_database_audit)
    app = FastAPI()
    transport.install_mcp_route(app)

    @asynccontextmanager
    async def running():
        await transport.start_mcp_transport()
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="https://mcp.example.test"
            ) as client:
                yield client
        finally:
            await transport.stop_mcp_transport()

    return running


async def rpc(client, method, params, *, token=READ_TOKEN):
    response = await client.post(
        "/mcp",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-11-25",
        },
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
@pytest.mark.parametrize("list_first", [False, True], ids=["cold-client", "beyond-first-page"])
async def test_cold_tool_call_returns_real_capabilities_without_expanding_public_pages(running_mcp, list_first):
    async with running_mcp() as client:
        if list_first:
            first = (await rpc(client, "tools/list", {}))["result"]
            assert len(first["tools"]) == 1
            assert first["tools"][0]["name"] != "afterglow_capabilities_get"
        result = (await rpc(client, "tools/call", {"name": "afterglow_capabilities_get", "arguments": {}}))["result"]
        assert result.get("isError") is False, result
        payload = result["structuredContent"]
        assert payload["registry_version"] == registry.REGISTRY_VERSION
        assert {"compute", "storage", "network"} <= set(payload["enabled_domains"])
        assert "waygate" not in payload["enabled_domains"]
        page = (await rpc(client, "tools/list", {}))["result"]
        assert len(page["tools"]) == 1
        next_page = (await rpc(client, "tools/list", {"cursor": page["nextCursor"]}))["result"]
        assert len(next_page["tools"]) == 1
        assert page["tools"][0]["name"] != next_page["tools"][0]["name"]


@pytest.mark.asyncio
async def test_read_grant_cannot_invoke_mutation_after_manage_schema_cache_refresh(running_mcp, monkeypatch):
    mutations = []

    async def forbidden_claim(*args, **kwargs):
        mutations.append(kwargs)
        raise AssertionError("read grant reached the mutation ledger")

    monkeypatch.setattr(transport, "claim_mutation", forbidden_claim)
    arguments = {
        "server_id": "11111111-1111-4111-8111-111111111111",
        "action": "stop",
        "idempotency_key": "read-cannot-stop-0001",
    }
    jsonschema.validate(arguments, registry.entry_by_name("afterglow_vm_action").mcp_input_schema())
    async with running_mcp() as client:
        # Invalid input refreshes the actual SDK's manage-tool schemas without dispatch.
        warm = await rpc(client, "tools/call", {"name": "afterglow_vm_action", "arguments": {}}, token=MANAGE_TOKEN)
        assert warm["result"]["isError"] is True
        denied = await rpc(client, "tools/call", {"name": "afterglow_vm_action", "arguments": arguments})
        assert denied["result"]["isError"] is True
        assert denied["result"].get("structuredContent") is None
        assert mutations == []
