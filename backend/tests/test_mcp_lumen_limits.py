"""Lumen HTTP shares the grant's Redis budgets and drains real SDK workers."""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from keystoneauth1.exceptions import http

from app.api import mcp_lumen
from app.services.mcp_control_plane import connection, credential_state, limits, registry
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
    monkeypatch.setattr(credential_state.cache, "_get_redis", redis_client)
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


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["read", "mutation_preview", "mutation_dispatch", "preview"])
@pytest.mark.parametrize("failure_kind", ["invalid", "403", "502", "timeout", "resource404"])
async def test_lumen_execute_observes_only_invalid_credentials_and_preserves_failure_response(
    bridge, monkeypatch, caplog, path, failure_kind
):
    bridge.principal = replace(
        bridge.principal,
        grant_id="a1234567-1234-1234-1234-123456789abc",
        project_id="b1234567-1234-1234-1234-123456789abc",
        user_id="c1234567-1234-1234-1234-123456789abc",
    )
    mcp_lumen.lumen.resolve_lumen_principal.return_value = bridge.principal
    if failure_kind == "invalid":
        failure = ValueError("MCP provider data is unavailable")
        invalid = connection.McpCredentialInvalidError("MCP cloud connection is unavailable")
        invalid.__cause__ = http.NotFound("synthetic-credential-secret")
        failure.__cause__ = invalid
    else:
        failure = {
            "403": http.Forbidden,
            "502": http.BadGateway,
            "timeout": TimeoutError,
            "resource404": http.NotFound,
        }[failure_kind]("synthetic-provider-secret")

    async def reject(*args, **kwargs):
        raise failure

    actual_path = "mutation" if path.startswith("mutation") else path
    if path == "read":
        entry = bridge.entries["afterglow_cloud_overview_get"]
        bridge.entries[entry.name] = replace(entry, handler=reject)
    else:
        entry = bridge.entries["afterglow_vm_action"]
        bridge.entries[entry.name] = replace(
            entry, **({"handler": reject} if path == "mutation_dispatch" else {"preview_builder": reject})
        )
    bridge.claim.side_effect = None
    bridge.claim.return_value = SimpleNamespace(state="claimed", invocation_id="invocation-a")
    failed = AsyncMock()
    complete = AsyncMock()
    monkeypatch.setattr(mcp_lumen.ledger, "fail_pre_dispatch", failed)
    monkeypatch.setattr(mcp_lumen.ledger, "authorize_mutation_dispatch", AsyncMock(return_value=bridge.principal))
    monkeypatch.setattr(mcp_lumen.ledger, "complete_mutation", complete)
    with caplog.at_level(logging.WARNING, logger=mcp_lumen.__name__):
        response = await _call(bridge, actual_path)
    assert response.status_code == (422 if path == "preview" else 502)
    assert response.json() == {
        "detail": "MCP mutation preview is unavailable" if path == "preview" else "MCP tool execution failed"
    }
    observed = failure_kind == "invalid" and path != "preview"
    assert await credential_state.is_invalid(bridge.principal.grant_id) is observed
    assert not await credential_state.is_invalid(bridge.principal.grant_id[:8])
    records = [record for record in caplog.records if getattr(record, "event", None) == "mcp_credential_invalid"]
    assert len(records) == int(observed)
    if observed:
        record = records[0]
        assert record.levelno == logging.WARNING
        assert record.getMessage() == "mcp_credential_invalid"
        assert (record.grant_id, record.project_id, record.user_id) == ("a1234567", "b1234567", "c1234567")
        assert bridge.principal.grant_id not in repr(record.__dict__)
        assert bridge.principal.project_id not in repr(record.__dict__)
        assert bridge.principal.user_id not in repr(record.__dict__)
        assert record.exc_info is None
        assert "secret" not in repr(record.__dict__)
    if path == "mutation_preview":
        failed.assert_awaited_once()
        complete.assert_not_awaited()
    elif path == "mutation_dispatch":
        complete.assert_awaited_once()
        assert complete.call_args.kwargs["error"] == "MCP mutation outcome is unknown after dispatch authorization"


@pytest.mark.asyncio
async def test_lumen_invalid_execute_keeps_response_and_warning_when_state_redis_is_down(bridge, monkeypatch, caplog):
    failure = connection.McpCredentialInvalidError("MCP cloud connection is unavailable")

    async def reject(*args, **kwargs):
        raise failure

    entry = bridge.entries["afterglow_cloud_overview_get"]
    bridge.entries[entry.name] = replace(entry, handler=reject)
    monkeypatch.setattr(
        credential_state.cache, "_get_redis", AsyncMock(side_effect=ConnectionError("synthetic-redis-secret"))
    )
    with caplog.at_level(logging.WARNING, logger=mcp_lumen.__name__):
        response = await _call(bridge, "read")
    assert response.status_code == 502
    assert response.json() == {"detail": "MCP tool execution failed"}
    records = [record for record in caplog.records if getattr(record, "event", None) == "mcp_credential_invalid"]
    assert len(records) == 1
    assert "secret" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["read", "mutation_replay", "mutation_failed"])
async def test_lumen_success_and_ledger_failure_responses_do_not_observe_credentials(bridge, caplog, path):
    if path != "read":
        bridge.claim.side_effect = None
        bridge.claim.return_value = SimpleNamespace(
            state="replay" if path == "mutation_replay" else "failed",
            result={"accepted": True},
            error="Previously failed",
        )
    with caplog.at_level(logging.WARNING, logger=mcp_lumen.__name__):
        response = await _call(bridge, "read" if path == "read" else "mutation")
    assert response.status_code == (409 if path == "mutation_failed" else 200)
    if path == "read":
        assert response.json() == {
            "total_instances": 1,
            "active_instances": 1,
            "shutoff_instances": 0,
            "error_instances": 0,
        }
    elif path == "mutation_replay":
        assert response.json() == {"accepted": True}
    else:
        assert response.json() == {"detail": "MCP mutation is unavailable"}
    assert not await credential_state.is_invalid(bridge.principal.grant_id)
    assert not any(getattr(record, "event", None) == "mcp_credential_invalid" for record in caplog.records)
