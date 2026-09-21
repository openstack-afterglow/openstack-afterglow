"""libraries=[] 시 Manila·upper 볼륨 미호출 회귀 테스트 (sync + SSE)."""

import base64
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.compute import InstanceInfo
from app.services import cloudinit
from app.services.resource_policies import ResourcePolicyValidationError


@pytest.fixture(autouse=True)
def _resolve_default_placement_policies(monkeypatch):
    """Keep no-library flow tests independent of placement policy storage."""

    async def resolve_zones(_conn, _requested_zone):
        return "", ""

    monkeypatch.setattr(
        "app.api.compute.instances.instance_orch.resolve_availability_zones",
        resolve_zones,
    )


def _make_flavor(is_gpu: bool = False):
    f = MagicMock()
    f.id = "flavor-1"
    f.is_gpu = is_gpu
    f.extra_specs = {}
    return f


def _make_volume(vol_id: str = "vol-1"):
    v = MagicMock()
    v.id = vol_id
    v.status = "available"
    v.bootable = True
    return v


def _make_server(server_id: str = "srv-abc") -> InstanceInfo:
    return InstanceInfo(
        id=server_id,
        name="test-no-libs",
        status="BUILD",
        image_id="img-abc",
        image_name="ubuntu-24.04",
        flavor_id="flavor-1",
        flavor_name="m1.medium",
        ip_addresses=[],
        created_at="2026-01-01T00:00:00Z",
        metadata={},
        union_libraries=[],
        union_strategy=None,
        union_share_ids=[],
        union_upper_volume_id=None,
        key_name="mykey",
        user_id="test-user-123",
    )


PAYLOAD = {
    "name": "test-no-libs",
    "image_id": "img-abc",
    "flavor_id": "flavor-1",
    "libraries": [],
    "network_id": "net-1",
    "key_name": "mykey",
    "boot_volume_size_gb": 50,
    "delete_boot_volume_on_termination": False,
}


@pytest.mark.asyncio
async def test_async_placement_policy_failure_returns_safe_503(client):
    with (
        patch("app.services.instance_names.ensure_unique_instance_name", return_value="test-no-libs"),
        patch(
            "app.api.compute.instances.instance_orch.resolve_availability_zones",
            new_callable=AsyncMock,
            side_effect=ResourcePolicyValidationError(
                "required resource policies are not configured: cinder.default_volume_availability_zone"
            ),
        ),
    ):
        resp = await client.post("/api/v1/instances/async", json=PAYLOAD)

    assert resp.status_code == 503
    assert resp.json() == {
        "detail": "인스턴스 배치 정책을 사용할 수 없습니다. 관리자에게 문의하세요.",
    }


@pytest.mark.asyncio
async def test_sync_no_libraries_skips_manila_and_upper(client, mock_conn):
    """sync: libraries=[] 이면 Manila share·upper 볼륨을 생성하지 않는다."""
    with (
        patch("app.api.compute.instances.nova.list_flavors", return_value=[_make_flavor()]),
        patch(
            "app.api.compute.instances.cinder.create_volume_from_image",
            return_value=_make_volume("boot-vol"),
        ),
        patch("app.api.compute.instances.cinder.rename_volume", return_value=None),
        patch("app.api.compute.instances.nova.create_server", return_value=_make_server()) as mock_create_server,
        patch("app.api.compute.instances.neutron.list_networks", return_value=[]),
        patch(
            "app.api.compute.instances.instance_orch.resolve_default_network",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.api.compute.instances.instance_orch.compute_effective_security_groups",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.api.compute.instances.instance_orch.try_issue_health_token",
            new_callable=AsyncMock,
            return_value=("", "", ""),
        ) as mock_health_token,
        patch("app.api.compute.instances.rec", new_callable=AsyncMock),
        patch("app.api.compute.instances.invalidate", new_callable=AsyncMock),
        patch(
            "app.api.compute.instances.cache_invalidation.invalidate_mutation_count",
            new_callable=AsyncMock,
        ),
        patch("app.api.compute.instances.manila.create_file_storage") as mock_manila,
        patch("app.api.compute.instances.cinder.create_empty_volume") as mock_upper,
    ):
        resp = await client.post("/api/v1/instances", json=PAYLOAD)

    assert resp.status_code == 201, resp.text
    mock_manila.assert_not_called()
    mock_upper.assert_not_called()
    mock_health_token.assert_not_called()
    metadata = mock_create_server.call_args.kwargs["metadata"]
    assert not any(key.startswith("union_") for key in metadata)


@pytest.mark.asyncio
async def test_sse_no_libraries_skips_manila_and_upper(client, mock_conn):
    """SSE: libraries=[] 이면 Manila share·upper 볼륨을 생성하지 않는다."""
    with (
        patch("app.api.compute.instances.nova.list_flavors", return_value=[_make_flavor()]),
        patch(
            "app.api.compute.instances.cinder.create_volume_from_image",
            return_value=_make_volume("boot-vol"),
        ),
        patch("app.api.compute.instances.cinder.rename_volume", return_value=None),
        patch("app.api.compute.instances.nova.create_server", return_value=_make_server()) as mock_create_server,
        patch("app.api.compute.instances.neutron.list_networks", return_value=[]),
        patch(
            "app.api.compute.instances.instance_orch.resolve_default_network",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.api.compute.instances.instance_orch.compute_effective_security_groups",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.api.compute.instances.instance_orch.try_issue_health_token",
            new_callable=AsyncMock,
            return_value=("", "", ""),
        ) as mock_health_token,
        patch("app.api.compute.instances.rec", new_callable=AsyncMock),
        patch("app.api.compute.instances.invalidate", new_callable=AsyncMock),
        patch(
            "app.api.compute.instances.cache_invalidation.invalidate_mutation_count",
            new_callable=AsyncMock,
        ),
        patch("app.api.compute.instances.manila.create_file_storage") as mock_manila,
        patch("app.api.compute.instances.cinder.create_empty_volume") as mock_upper,
    ):
        resp = await client.post("/api/v1/instances/async", json=PAYLOAD)

    assert resp.status_code == 200, resp.text
    assert "text/event-stream" in resp.headers.get("content-type", "")
    mock_manila.assert_not_called()
    mock_upper.assert_not_called()
    mock_health_token.assert_not_called()
    metadata = mock_create_server.call_args.kwargs["metadata"]
    assert not any(key.startswith("union_") for key in metadata)

    events = [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")]
    steps = [e.get("step") for e in events]
    assert "completed" in steps, f"completed 이벤트 없음: {steps}"


@pytest.mark.asyncio
async def test_sse_gpu_only_generates_gpu_userdata_without_layer_state(client, mock_conn):
    admission = SimpleNamespace(gpu_requested={"GPU": 1})
    with (
        patch("app.api.compute.instances.nova.list_flavors", return_value=[_make_flavor()]),
        patch("app.services.flavor_eligibility.admit_flavor", new_callable=AsyncMock, return_value=admission),
        patch("app.services.flavor_eligibility.release_admission", new_callable=AsyncMock),
        patch(
            "app.api.compute.instances.cinder.create_volume_from_image",
            return_value=_make_volume("boot-vol"),
        ),
        patch("app.api.compute.instances.cinder.rename_volume", return_value=None),
        patch("app.api.compute.instances.nova.create_server", return_value=_make_server()) as mock_create_server,
        patch("app.api.compute.instances.neutron.list_networks", return_value=[]),
        patch(
            "app.api.compute.instances.instance_orch.resolve_default_network",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.api.compute.instances.instance_orch.compute_effective_security_groups",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.api.compute.instances.instance_orch.try_issue_health_token",
            new_callable=AsyncMock,
            return_value=("health-id", "https://health.example", "health-token"),
        ) as mock_health_token,
        patch(
            "app.api.compute.instances.cloudinit.generate_userdata", wraps=cloudinit.generate_userdata
        ) as mock_generate,
        patch("app.api.compute.instances.rec", new_callable=AsyncMock),
        patch("app.api.compute.instances.invalidate", new_callable=AsyncMock),
        patch(
            "app.api.compute.instances.cache_invalidation.invalidate_mutation_count",
            new_callable=AsyncMock,
        ),
    ):
        resp = await client.post("/api/v1/instances/async", json=PAYLOAD)

    assert resp.status_code == 200, resp.text
    mock_generate.assert_called_once()
    mock_health_token.assert_not_called()
    create_kwargs = mock_create_server.call_args.kwargs
    rendered = base64.b64decode(create_kwargs["userdata"]).decode()
    assert "datacenter-gpu-manager-exporter" in rendered
    assert "/opt/union/overlay_setup.sh" not in rendered
    assert not any(key.startswith("union_") for key in create_kwargs["metadata"])


@pytest.mark.asyncio
async def test_sync_data_mount_only_has_no_layer_health_or_metadata(client, mock_conn):
    mount_info = {
        "file_storage_id": "share-data",
        "share_proto": "NFS",
        "nfs_export_location": "10.0.0.2:/data",
        "mount_point": "/mnt/data",
        "mount_options": "ro,nosuid,nodev,noexec",
    }
    payload = {**PAYLOAD, "data_mounts": [{"file_storage_id": "share-data", "mount_point": "/mnt/data"}]}
    with (
        patch("app.api.compute.instances.nova.list_flavors", return_value=[_make_flavor()]),
        patch(
            "app.api.compute.instances.cinder.create_volume_from_image",
            return_value=_make_volume("boot-vol"),
        ),
        patch("app.api.compute.instances.cinder.rename_volume", return_value=None),
        patch("app.api.compute.instances.nova.create_server", return_value=_make_server()) as mock_create_server,
        patch("app.api.compute.instances.neutron.list_networks", return_value=[]),
        patch(
            "app.api.compute.instances.instance_orch.resolve_default_network",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.api.compute.instances.instance_orch.compute_effective_security_groups",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch("app.api.compute.instances._prepare_data_mounts", new_callable=AsyncMock, return_value=[mount_info]),
        patch(
            "app.api.compute.instances.instance_orch.try_issue_health_token",
            new_callable=AsyncMock,
            return_value=("health-id", "https://health.example", "health-token"),
        ) as mock_health_token,
        patch("app.api.compute.instances.rec", new_callable=AsyncMock),
        patch("app.api.compute.instances.invalidate", new_callable=AsyncMock),
        patch(
            "app.api.compute.instances.cache_invalidation.invalidate_mutation_count",
            new_callable=AsyncMock,
        ),
    ):
        resp = await client.post("/api/v1/instances", json=payload)

    assert resp.status_code == 201, resp.text
    mock_health_token.assert_not_called()
    create_kwargs = mock_create_server.call_args.kwargs
    rendered = base64.b64decode(create_kwargs["userdata"]).decode()
    assert "afterglow-data-mounts.service" in rendered
    assert "/opt/union/overlay_setup.sh" not in rendered
    assert not any(key.startswith("union_") for key in create_kwargs["metadata"])
    assert create_kwargs["metadata"]["afterglow_data_share_ids"] == "share-data"
