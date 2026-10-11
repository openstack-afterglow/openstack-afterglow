from __future__ import annotations

from datetime import UTC, datetime, timedelta
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
@pytest.mark.parametrize("access_level", ["read", "manage"])
async def test_lumen_bridge_refuses_implicit_grants_and_pre_cutover_frozen_snapshots(
    bridge_app, monkeypatch, access_level
):
    from app.api import mcp_lumen

    grant = SimpleNamespace(
        id="legacy-grant",
        owner_user_id="u",
        owner_project_id="p",
        source="lumen",
        status="active",
        access_level=access_level,
        project_scope="current",
        consented_at=None,
        approved_projects=[{"id": "p", "name": "Project", "roles": ["member"], "can_write": True}],
        credential_epoch=2,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        application_credential_id="credential",
        credential_ciphertext="server-only-ciphertext",
        cleanup_pending=False,
    )
    row = (SimpleNamespace(grant_id=grant.id), grant, None, SimpleNamespace(lumen_selection_generation=3))

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def execute(self, statement):
            return SimpleNamespace(one_or_none=lambda: row)

    monkeypatch.setattr(mcp_lumen.lumen, "get_session_factory", lambda: Session)
    monkeypatch.setattr(
        mcp_lumen,
        "get_settings",
        lambda: SimpleNamespace(lumen_mcp_service_token="bridge-secret", service_mcp_enabled=True),
    )
    monkeypatch.setattr(mcp_lumen.registry, "enabled_service_fingerprint", lambda: "a" * 64)
    monkeypatch.setattr(mcp_lumen.registry, "enabled_entries", lambda _: ())
    dispatch = AsyncMock(side_effect=AssertionError("unconsented grant reached provider dispatch"))
    preview = AsyncMock(side_effect=AssertionError("unconsented grant reached preview"))
    claim = AsyncMock(side_effect=AssertionError("unconsented grant reached mutation claim"))
    monkeypatch.setattr(mcp_lumen.registry, "dispatch", dispatch)
    monkeypatch.setattr(mcp_lumen.registry, "build_mutation_preview", preview)
    monkeypatch.setattr(mcp_lumen.ledger, "claim_mutation", claim)
    frozen = {
        "grant_id": grant.id,
        "user_id": "u",
        "project_id": "p",
        "credential_epoch": 2,
        "selection_generation": 3,
    }
    async with AsyncClient(transport=ASGITransport(bridge_app), base_url="http://test") as client:
        headers = {"Authorization": "Bearer bridge-secret"}
        implicit = await client.post(
            "/api/v1/mcp/lumen/snapshot", json={"user_id": "u", "project_id": "p"}, headers=headers
        )
        assert implicit.status_code == 200
        assert implicit.json() == {"snapshot": None, "entries": [], "service_fingerprint": "a" * 64}
        for endpoint in ("preview", "execute"):
            rejected = await client.post(
                f"/api/v1/mcp/lumen/{endpoint}",
                json={"snapshot": frozen, "name": "afterglow_vm_action", "arguments": {}},
                headers=headers,
            )
            assert rejected.status_code == 403
        grant.consented_at = datetime.now(UTC)
        approved = await client.post(
            "/api/v1/mcp/lumen/snapshot", json={"user_id": "u", "project_id": "p"}, headers=headers
        )
        assert approved.status_code == 200
        assert approved.json()["snapshot"] == frozen
    dispatch.assert_not_awaited()
    preview.assert_not_awaited()
    claim.assert_not_awaited()


async def _return(value):
    return value
