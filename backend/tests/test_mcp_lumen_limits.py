"""Lumen HTTP shares the grant's Redis budgets and drains real SDK workers."""

from __future__ import annotations

import asyncio
import threading
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api import mcp_lumen
from app.services.mcp_control_plane import limits, registry
from app.services.mcp_control_plane.authentication import McpPrincipal
from app.services.mcp_control_plane.sdk import run_sdk

_BASE = "afterglow:mcp:limit:project-a:grant-a"
_SERVER = "12345678-1234-1234-1234-123456789abc"
_SECRET = "synthetic-bridge-secret"
_HEADERS = {"Authorization": "Bearer " + _SECRET}
_SNAPSHOT = {
    "grant_id": "grant-a",
    "user_id": "user-a",
    "project_id": "project-a",
    "credential_epoch": 1,
    "selection_generation": 1,
}


@pytest.fixture
async def bridge(monkeypatch):
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    settings = SimpleNamespace(
        lumen_mcp_service_token=_SECRET,
        service_mcp_enabled=True,
        mcp_read_rate_per_minute=100,
        mcp_mutation_rate_per_minute=100,
        mcp_concurrent_calls_per_grant=1,
    )
    principal = McpPrincipal(
        grant_id="grant-a",
        user_id="user-a",
        project_id="project-a",
        credential_epoch=1,
        scopes=frozenset({"mcp:read", "mcp:write"}),
        source="lumen",
        selection_generation=1,
    )
    events = []

    async def redis_client():
        return redis

    async def resolve_target(principal, project_id=None, *, write=False):
        return principal

    async def read_provider(context, arguments):
        events.append("read")
        return registry.CloudOverviewOutput(
            total_instances=1, active_instances=1, shutoff_instances=0, error_instances=0
        )

    async def preview_provider(context, arguments):
        events.append("preview")
        return registry.McpMutationPreview(
            resource_identity=_SERVER,
            current_state="ACTIVE",
            intended_transition="stop",
            dependent_resources=[],
            destructive=True,
            estimated_effect=None,
            fingerprint="a" * 64,
        )

    read_entry = replace(registry.entry_by_name("afterglow_cloud_overview_get"), handler=read_provider)
    mutation_entry = replace(registry.entry_by_name("afterglow_vm_action"), preview_builder=preview_provider)
    entries = {read_entry.name: read_entry, mutation_entry.name: mutation_entry}
    claim = AsyncMock(side_effect=AssertionError("Rejected execution reached the mutation ledger"))
    monkeypatch.setattr(mcp_lumen, "get_settings", lambda: settings)
    monkeypatch.setattr(limits, "get_settings", lambda: settings)
    monkeypatch.setattr(limits, "_get_redis", redis_client)
    monkeypatch.setattr(limits, "time", SimpleNamespace(time=lambda: 1234500))
    monkeypatch.setattr(mcp_lumen.lumen, "resolve_lumen_principal", AsyncMock(return_value=principal))
    monkeypatch.setattr(registry, "resolve_principal_target", resolve_target)
    monkeypatch.setattr(registry, "entry_by_name", entries.get)
    monkeypatch.setattr(mcp_lumen.ledger, "claim_mutation", claim)
    monkeypatch.setattr(mcp_lumen.ledger, "record_read_invocation", AsyncMock())
    app = FastAPI()
    app.include_router(mcp_lumen.router, prefix="/api/v1/mcp/lumen")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield SimpleNamespace(
            client=client,
            redis=redis,
            settings=settings,
            principal=principal,
            entries=entries,
            events=events,
            claim=claim,
        )
    await redis.close()


def _body(path):
    if path == "read":
        return {"snapshot": _SNAPSHOT, "name": "afterglow_cloud_overview_get", "arguments": {}}
    body = {"snapshot": _SNAPSHOT, "name": "afterglow_vm_action", "arguments": {"server_id": _SERVER, "action": "stop"}}
    if path == "mutation":
        body["idempotency_key"] = "fresh-mutation-key"
    return body


async def _call(bridge, path):
    endpoint = "preview" if path == "preview" else "execute"
    return await bridge.client.post(f"/api/v1/mcp/lumen/{endpoint}", json=_body(path), headers=_HEADERS)


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["preview", "read", "mutation"])
@pytest.mark.parametrize("boundary", ["full_slot", "rate", "redis_down"])
async def test_lumen_rejects_exhausted_or_unavailable_budget_before_provider_or_ledger(
    bridge, monkeypatch, path, boundary
):
    if boundary == "full_slot":
        await bridge.redis.sadd(f"{_BASE}:concurrency", "another-worker")
    elif boundary == "rate":
        effect = "external_mutation" if path == "mutation" else "read"
        await bridge.redis.set(f"{_BASE}:rate:{effect}:20575", 100)
    else:

        async def unavailable():
            raise OSError("Synthetic Redis outage")

        monkeypatch.setattr(limits, "_get_redis", unavailable)
    response = await _call(bridge, path)
    assert response.status_code == (503 if boundary == "redis_down" else 429)
    assert bridge.events == []
    bridge.claim.assert_not_awaited()
    if boundary == "full_slot":
        assert await bridge.redis.smembers(f"{_BASE}:concurrency") == {"another-worker"}


@pytest.mark.asyncio
async def test_preview_consumes_read_budget_without_consuming_mutation_budget(bridge):
    bridge.settings.mcp_read_rate_per_minute = 1
    first = await _call(bridge, "preview")
    assert first.status_code == 200
    assert first.json()["resource_identity"] == _SERVER
    assert (await _call(bridge, "preview")).status_code == 429
    assert bridge.events == ["preview"]
    assert await bridge.redis.get(f"{_BASE}:rate:read:20575") == "2"
    assert await bridge.redis.exists(f"{_BASE}:rate:external_mutation:20575") == 0
    assert await bridge.redis.exists(f"{_BASE}:concurrency") == 0


@pytest.mark.asyncio
async def test_bridge_holds_slot_until_cancelled_sdk_worker_drains(bridge):
    started, finish = threading.Event(), threading.Event()

    def worker():
        started.set()
        assert finish.wait(3)
        bridge.events.append("provider-finished")

    async def handler(context, arguments):
        await run_sdk(worker)
        return registry.CloudOverviewOutput(
            total_instances=1, active_instances=1, shutoff_instances=0, error_instances=0
        )

    name = "afterglow_cloud_overview_get"
    bridge.entries[name] = replace(bridge.entries[name], handler=handler)
    pending = asyncio.create_task(_call(bridge, "read"))
    try:
        async with asyncio.timeout(2):
            while not started.is_set():
                await asyncio.sleep(0.001)
        assert (await _call(bridge, "read")).status_code == 429
        pending.cancel()
        await asyncio.sleep(0.01)
        pending.cancel()
        await asyncio.sleep(0.01)
        assert not pending.done()
        assert await bridge.redis.scard(f"{_BASE}:concurrency") == 1
        assert bridge.events == []
    finally:
        finish.set()
        try:
            await pending
        except asyncio.CancelledError:
            pass
    assert bridge.events == ["provider-finished"]
    assert await bridge.redis.exists(f"{_BASE}:concurrency") == 0
    assert (await _call(bridge, "read")).status_code == 200
