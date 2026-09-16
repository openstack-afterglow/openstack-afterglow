import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Response

from app.api import internal_k3s
from app.models.db import K3sProvisioningIntent


class _Result:
    def __init__(self, row):
        self.row = row

    def scalar_one_or_none(self):
        return self.row


class _Session:
    def __init__(self, row=None):
        self.row = row
        self.added = []
        self.commits = 0

    async def execute(self, _query):
        return _Result(self.row)

    def add(self, row):
        self.added.append(row)
        self.row = row

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        return None


def _request(**overrides):
    values = {
        "idempotency_key": "stampede.cluster.node.0",
        "project_id": "project-1",
        "cluster_id": "cluster-1",
        "nodegroup_id": "nodegroup-1",
        "name": "cluster-agent-01",
        "flavor_id": "flavor-1",
        "image_id": "image-1",
        "network_id": "network-1",
        "boot_volume_size_gb": 30,
        "volume_availability_zone": "nova",
        "metadata": {"drover.cluster_id": "cluster-1"},
        "config_drive": False,
    }
    values.update(overrides)
    return internal_k3s.K3sProvisioningIntentRequest(**values)


@pytest.mark.asyncio
async def test_create_intent_persists_only_non_secret_spec(monkeypatch):
    monkeypatch.setenv("K3S_PROVISIONING_TOKEN", "provisioning-secret")
    from app.config import get_settings

    get_settings.cache_clear()
    session = _Session()
    response = Response(status_code=201)
    result = await internal_k3s.create_k3s_provisioning_intent(_request(), response, "provisioning-secret", session)

    assert response.status_code == 201
    assert result["state"] == "pending"
    assert session.commits == 1
    row = session.added[0]
    assert row.resource_metadata == {"drover.cluster_id": "cluster-1"}
    assert not hasattr(row, "userdata")
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_submit_intent_passes_base64_bootstrap_without_persisting(monkeypatch):
    row = K3sProvisioningIntent(
        idempotency_key="stampede.cluster.node.0",
        request_hash="request-hash",
        project_id="project-1",
        cluster_id="cluster-1",
        nodegroup_id="nodegroup-1",
        name="cluster-agent-01",
        flavor_id="flavor-1",
        image_id="image-1",
        network_id="network-1",
        boot_volume_size_gb=30,
        volume_availability_zone="nova",
        resource_metadata={"drover.cluster_id": "cluster-1"},
        config_drive=False,
        state="pending",
    )
    session = _Session(row)
    conn = MagicMock()
    flavor = SimpleNamespace(id="flavor-1", extra_specs={})
    volume = SimpleNamespace(id="volume-1")
    server = SimpleNamespace(id="server-1")
    create_server = MagicMock(return_value=server)
    userdata = base64.b64encode(b"bootstrap token must stay transient").decode()

    monkeypatch.setattr(internal_k3s, "get_admin_connection_for_project", MagicMock(return_value=conn))
    monkeypatch.setattr(internal_k3s, "_require_provisioning_token", lambda _token: None)
    monkeypatch.setattr(internal_k3s.nova, "list_flavors", MagicMock(return_value=[flavor]))
    monkeypatch.setattr(internal_k3s, "require_gpu_quota", AsyncMock(return_value=False))
    monkeypatch.setattr(internal_k3s.cinder, "create_volume_from_image", MagicMock(return_value=volume))
    monkeypatch.setattr(internal_k3s.nova, "create_server", create_server)

    result = await internal_k3s.submit_k3s_provisioning_intent(
        internal_k3s.K3sProvisioningSubmitRequest(userdata=userdata),
        row.idempotency_key,
        "unused-direct-call-token",
        session,
    )

    assert result == {"state": "succeeded", "server_id": "server-1", "volume_id": "volume-1", "name": row.name}
    assert row.state == "succeeded"
    assert row.server_id == "server-1"
    assert row.boot_volume_id == "volume-1"
    assert create_server.call_args.kwargs["userdata"] == userdata
    assert not hasattr(row, "userdata")
    conn.close.assert_called_once_with()


@pytest.mark.asyncio
async def test_recover_submitting_intent_records_server_by_metadata(monkeypatch):
    row = K3sProvisioningIntent(
        idempotency_key="stampede.cluster.node.0",
        request_hash="request-hash",
        project_id="project-1",
        cluster_id="cluster-1",
        nodegroup_id="nodegroup-1",
        name="cluster-agent-01",
        flavor_id="flavor-1",
        image_id="image-1",
        network_id="network-1",
        boot_volume_size_gb=30,
        volume_availability_zone="nova",
        state="submitting",
    )
    session = _Session(row)
    conn = MagicMock()
    conn.compute.servers.return_value = [
        SimpleNamespace(id="server-1", metadata={"afterglow:k3s-provisioning-intent": row.idempotency_key})
    ]
    monkeypatch.setattr(internal_k3s, "get_admin_connection_for_project", MagicMock(return_value=conn))

    result = await internal_k3s._recover_submitting_intent(session, row)

    assert result == {"state": "succeeded", "server_id": "server-1", "volume_id": None, "name": row.name}
    assert row.state == "succeeded"
    assert row.server_id == "server-1"
    conn.close.assert_called_once_with()
