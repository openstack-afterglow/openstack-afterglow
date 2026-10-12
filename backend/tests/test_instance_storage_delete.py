"""Instance deletion cannot erase live managed Manila authorization tracking."""

import hashlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.models.compute import InstanceInfo

INSTANCE = "11111111-2222-4333-8444-555555555555"
SHARE = "01234567-89ab-4cde-8fab-0123456789ab"
RULE = "12345678-1234-4234-8234-123456789abc"
KEY = "afterglow_share_grant_" + hashlib.sha256(SHARE.encode()).hexdigest()


@pytest.fixture
def deletion(monkeypatch):
    server = InstanceInfo(id=INSTANCE, name="mutable-name", status="SHUTOFF", project_id="test-project-123")
    grant = {"s": SHARE, "i": RULE, "t": "ip", "a": "10.0.0.5", "l": "rw", "m": True}
    server.metadata = {KEY: json.dumps(grant, separators=(",", ":"))}
    rule = {
        "id": RULE,
        "share_id": SHARE,
        "access_type": "ip",
        "access_to": "10.0.0.5",
        "access_level": "rw",
        "state": "active",
        "metadata": {"afterglow_instance_id": INSTANCE},
    }
    env = SimpleNamespace(server=server, grant=grant, rules=[rule], pending=False, deleted=False, native_events=[])
    share = SimpleNamespace(id=SHARE, project_id="test-project-123", share_proto="NFS")

    def exact(_conn, share_id, rule_id):
        return next((item for item in env.rules if item["id"] == rule_id), None)

    def revoke(_conn, share_id, rule_id):
        env.native_events.append("revoke")
        if env.pending:
            env.rules[0]["state"] = "denying"
        else:
            env.rules[:] = [item for item in env.rules if item["id"] != rule_id]

    def delete(_conn, server_id):
        env.native_events.append("delete")
        env.deleted = True

    monkeypatch.setattr("app.api.compute.instances.nova.get_server", lambda *_: server)
    monkeypatch.setattr("app.api.compute.instances.nova.delete_server", delete)
    monkeypatch.setattr("app.api.compute.instances.manila.get_file_storage", lambda *_: share)
    monkeypatch.setattr("app.api.compute.instances.manila.get_access_rule", exact)
    monkeypatch.setattr("app.api.compute.instances.manila.revoke_access_rule", revoke)
    monkeypatch.setattr("app.api.compute.instances.keystone.get_service_project_connection", lambda: None)
    monkeypatch.setattr("app.api.compute.instances.neutron.cleanup_instance_fips", lambda *_: None)
    monkeypatch.setattr("app.api.compute.instances.rec", AsyncMock())
    return env


async def _delete(client, bulk):
    if bulk:
        return await client.post("/api/v1/instances/bulk-action", json={"instance_ids": [INSTANCE], "action": "delete"})
    return await client.delete(f"/api/v1/instances/{INSTANCE}")


@pytest.mark.asyncio
@pytest.mark.parametrize("bulk", [False, True])
async def test_delete_revokes_exact_managed_grant_before_erasing_server(client, deletion, bulk):
    unrelated = {
        "id": "unrelated",
        "share_id": SHARE,
        "access_type": "ip",
        "access_to": "10.0.0.0/24",
        "access_level": "rw",
        "state": "active",
    }
    deletion.rules.append(unrelated)
    response = await _delete(client, bulk)
    assert response.status_code == (200 if bulk else 204)
    if bulk:
        assert response.json()["results"][0]["ok"] is True
    assert deletion.native_events == ["revoke", "delete"]
    assert deletion.rules == [unrelated]


@pytest.mark.asyncio
@pytest.mark.parametrize("bulk", [False, True])
async def test_pending_rule_denial_keeps_server_and_tracking(client, deletion, bulk):
    deletion.pending = True
    response = await _delete(client, bulk)
    assert response.status_code == (200 if bulk else 409)
    if bulk:
        assert response.json()["results"][0]["ok"] is False
    assert deletion.deleted is False
    assert deletion.rules[0]["state"] == "denying"
    assert KEY in deletion.server.metadata


@pytest.mark.asyncio
@pytest.mark.parametrize("bulk", [False, True])
async def test_changed_managed_rule_owner_blocks_server_delete(client, deletion, bulk):
    deletion.rules[0]["metadata"]["afterglow_instance_id"] = "another-instance"
    response = await _delete(client, bulk)
    assert response.status_code == (200 if bulk else 409)
    if bulk:
        assert response.json()["results"][0]["ok"] is False
    assert deletion.native_events == []
    assert KEY in deletion.server.metadata


@pytest.mark.asyncio
@pytest.mark.parametrize("bulk", [False, True])
async def test_unmanaged_and_legacy_name_grants_are_not_revoked(client, deletion, bulk):
    deletion.grant["m"] = False
    deletion.server.metadata = {KEY: json.dumps(deletion.grant), "afterglow_data_share_ids": SHARE}
    response = await _delete(client, bulk)
    assert response.status_code == (200 if bulk else 204)
    assert deletion.native_events == ["delete"]
    assert deletion.rules[0]["id"] == RULE


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["delete", "bulk", "detach"])
async def test_absent_exact_rule_allows_cleanup_after_share_deletion(client, deletion, mock_conn, monkeypatch, action):
    deletion.rules.clear()

    def missing_share(*_args):
        request = httpx.Request("GET", f"https://synthetic-manila.invalid/shares/{SHARE}")
        response = httpx.Response(404, request=request)
        raise httpx.HTTPStatusError("share deleted", request=request, response=response)

    monkeypatch.setattr("app.api.compute.instances.manila.get_file_storage", missing_share)
    if action == "detach":
        response = await client.delete(f"/api/v1/instances/{INSTANCE}/storage-attachments/{SHARE}")
        assert response.status_code == 204
        mock_conn.compute.delete_server_metadata.assert_called_once_with(INSTANCE, [KEY])
        assert deletion.native_events == []
    else:
        response = await _delete(client, action == "bulk")
        assert response.status_code == (200 if action == "bulk" else 204)
        if action == "bulk":
            assert response.json()["results"][0]["ok"] is True
        assert deletion.native_events == ["delete"]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [403, 503])
async def test_uncertain_exact_rule_absence_preserves_server(client, deletion, monkeypatch, status):
    def denied_rule(*_args):
        request = httpx.Request("GET", f"https://synthetic-manila.invalid/share-access-rules/{RULE}")
        response = httpx.Response(status, request=request)
        raise httpx.HTTPStatusError("rule unavailable", request=request, response=response)

    monkeypatch.setattr("app.api.compute.instances.manila.get_access_rule", denied_rule)
    response = await _delete(client, False)
    assert response.status_code == 502
    assert deletion.native_events == []
    assert KEY in deletion.server.metadata
