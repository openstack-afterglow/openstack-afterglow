from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def bridge_app():
    from app.api.mcp_lumen import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/mcp/lumen")
    return app


@pytest.mark.asyncio
async def test_lumen_bridge_rejects_missing_or_wrong_workload_secret(bridge_app, monkeypatch):
    from app.api import mcp_lumen

    monkeypatch.setattr(mcp_lumen, "get_settings", lambda: SimpleNamespace(lumen_mcp_service_token="bridge-secret"))
    async with AsyncClient(transport=ASGITransport(bridge_app), base_url="http://test") as client:
        missing = await client.post("/api/v1/mcp/lumen/snapshot", json={"user_id": "u", "project_id": "p"})
        wrong = await client.post(
            "/api/v1/mcp/lumen/snapshot",
            json={"user_id": "u", "project_id": "p"},
            headers={"Authorization": "Bearer wrong"},
        )

    assert missing.status_code == 401
    assert wrong.status_code == 401


@pytest.mark.asyncio
async def test_lumen_bridge_returns_only_opaque_snapshot_and_closed_registry(bridge_app, monkeypatch):
    from app.api import mcp_lumen

    snapshot = mcp_lumen.lumen.LumenGrantSnapshot(
        grant_id="grant", user_id="u", project_id="p", credential_epoch=2, selection_generation=3
    )
    principal = SimpleNamespace()
    entry = SimpleNamespace(
        name="compute_list_servers",
        description="List servers",
        effect="read",
        input_schema=lambda: {"type": "object", "properties": {}},
    )
    monkeypatch.setattr(
        mcp_lumen,
        "get_settings",
        lambda: SimpleNamespace(lumen_mcp_service_token="bridge-secret", service_mcp_enabled=True),
    )
    monkeypatch.setattr(mcp_lumen.lumen, "selected_lumen_snapshot", lambda **_: _return(snapshot))
    monkeypatch.setattr(mcp_lumen.lumen, "resolve_lumen_principal", lambda _: _return(principal))
    monkeypatch.setattr(mcp_lumen.registry, "enabled_entries", lambda _: (entry,))
    monkeypatch.setattr(mcp_lumen.registry, "enabled_service_fingerprint", lambda: "a" * 64)

    async with AsyncClient(transport=ASGITransport(bridge_app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/mcp/lumen/snapshot",
            json={"user_id": "u", "project_id": "p"},
            headers={"Authorization": "Bearer bridge-secret"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "snapshot": {
            "grant_id": "grant",
            "user_id": "u",
            "project_id": "p",
            "credential_epoch": 2,
            "selection_generation": 3,
        },
        "entries": [
            {
                "name": "compute_list_servers",
                "description": "List servers",
                "input_schema": {"type": "object", "properties": {}},
                "effect": "read",
            }
        ],
        "service_fingerprint": "a" * 64,
    }


@pytest.mark.asyncio
async def test_lumen_bridge_records_reads_with_lumen_source(monkeypatch):
    from app.api import mcp_lumen

    snapshot = SimpleNamespace()
    principal = SimpleNamespace()
    entry = SimpleNamespace(effect="read", name="compute_list_servers", allowed_for=lambda _: True)
    recorded = AsyncMock()

    monkeypatch.setattr(mcp_lumen.lumen, "frozen_snapshot", lambda _: snapshot)
    monkeypatch.setattr(mcp_lumen.lumen, "resolve_lumen_principal", lambda _: _return(principal))
    monkeypatch.setattr(mcp_lumen.registry, "entry_by_name", lambda _: entry)
    monkeypatch.setattr(
        mcp_lumen.registry, "parse_entry_arguments", lambda *_: SimpleNamespace(model_dump=lambda **_: {})
    )
    monkeypatch.setattr(
        mcp_lumen.registry, "bind_entry_target", lambda principal, *, entry, arguments: _return((principal, arguments))
    )
    monkeypatch.setattr(mcp_lumen.registry, "ConsumerCloudContext", lambda **_: object())
    monkeypatch.setattr(mcp_lumen.registry, "dispatch", AsyncMock(return_value={"servers": []}))
    monkeypatch.setattr(mcp_lumen.registry, "output_payload", lambda *_: {"servers": []})
    monkeypatch.setattr(mcp_lumen.ledger, "record_read_invocation", recorded)

    response = await mcp_lumen.execute(
        mcp_lumen._ExecuteRequest(snapshot={}, name="compute_list_servers", arguments={}),
        None,
    )

    assert response == {"servers": []}
    recorded.assert_awaited_once_with(principal, entry=entry, arguments={}, status="succeeded", source="lumen")


@pytest.mark.asyncio
async def test_lumen_bridge_mutation_uses_lumen_ledger_source(monkeypatch):
    from app.api import mcp_lumen

    snapshot = SimpleNamespace()
    principal = SimpleNamespace()
    entry = SimpleNamespace(effect="external_mutation", name="compute_delete_server", allowed_for=lambda _: True)
    claim = SimpleNamespace(state="replay", result={"status": "accepted"}, error=None)
    claim_mutation = AsyncMock(return_value=claim)

    monkeypatch.setattr(mcp_lumen.lumen, "frozen_snapshot", lambda _: snapshot)
    monkeypatch.setattr(mcp_lumen.lumen, "resolve_lumen_principal", lambda _: _return(principal))
    monkeypatch.setattr(mcp_lumen.registry, "entry_by_name", lambda _: entry)
    monkeypatch.setattr(
        mcp_lumen.registry, "parse_entry_arguments", lambda *_: SimpleNamespace(model_dump=lambda **_: {})
    )
    monkeypatch.setattr(
        mcp_lumen.registry, "bind_entry_target", lambda principal, *, entry, arguments: _return((principal, arguments))
    )
    monkeypatch.setattr(mcp_lumen.registry, "ConsumerCloudContext", lambda **_: object())
    monkeypatch.setattr(mcp_lumen.ledger, "validate_idempotency_key", lambda _: "lumen-idempotency-key")
    monkeypatch.setattr(mcp_lumen.ledger, "claim_mutation", claim_mutation)

    response = await mcp_lumen.execute(
        mcp_lumen._ExecuteRequest(
            snapshot={}, name="compute_delete_server", arguments={}, idempotency_key="lumen-idempotency-key"
        ),
        None,
    )

    assert response == {"status": "accepted"}
    claim_mutation.assert_awaited_once_with(
        principal,
        entry=entry,
        arguments={},
        idempotency_key="lumen-idempotency-key",
        source="lumen",
    )


async def _return(value):
    return value
