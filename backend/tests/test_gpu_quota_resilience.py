"""Focused unit tests for GPU quota resilience, classification, fallbacks, and mutation prevention."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.models.compute import CreateInstanceRequest, FlavorInfo, InstanceInfo
from app.services.gpu_inventory import is_gpu_flavor, require_gpu_quota


@pytest.fixture(autouse=True)
def _resolve_default_placement_policies(monkeypatch):
    """Keep tests independent of placement policy storage and network resolution."""

    async def resolve_zones(_conn, _requested_zone):
        return "", ""

    monkeypatch.setattr(
        "app.api.compute.instances.instance_orch.resolve_availability_zones",
        resolve_zones,
    )
    monkeypatch.setattr(
        "app.services.instance_orchestration.resolve_availability_zones",
        resolve_zones,
    )

    async def resolve_network(_conn, _settings):
        return None

    monkeypatch.setattr(
        "app.services.instance_orchestration.resolve_default_network",
        resolve_network,
    )
    monkeypatch.setattr(
        "app.api.compute.instances.instance_orch.resolve_default_network",
        resolve_network,
    )


async def _load_without_cache(_key, _ttl, loader, **_kwargs):
    return await loader()


def _make_volume(vol_id: str = "vol-boot-1") -> MagicMock:
    v = MagicMock()
    v.id = vol_id
    v.status = "available"
    v.bootable = True
    return v


def _make_server(server_id: str = "srv-123") -> InstanceInfo:
    return InstanceInfo(
        id=server_id,
        name="test-vm",
        status="BUILD",
        image_id="img-123",
        image_name="ubuntu-24.04",
        flavor_id="fl-1",
        flavor_name="test-flavor",
        ip_addresses=[],
        created_at="2026-01-01T00:00:00Z",
        metadata={},
        union_libraries=[],
        union_strategy=None,
        union_share_ids=[],
        union_upper_volume_id=None,
        key_name="mykey",
        user_id="user-123",
    )


def test_is_gpu_flavor_classification():
    # 1. Nonstandard GPU flavor name with PCI alias extra specs
    f1 = FlavorInfo(
        id="fl-1",
        name="nvidia-a100-custom-name",
        vcpus=8,
        ram=16384,
        disk=100,
        extra_specs={"pci_passthrough:alias": "gpu-a100:1"},
    )
    assert is_gpu_flavor(f1) is True
    assert f1.is_gpu is True

    # 2. Dict flavor with PCI alias
    f2 = {
        "id": "fl-2",
        "name": "accelerated-node",
        "extra_specs": {"pci_passthrough:alias": "rtx3090:2"},
    }
    assert is_gpu_flavor(f2) is True

    # 3. Non-GPU PCI alias (e.g. audio device)
    f3 = {
        "id": "fl-3",
        "name": "audio-workstation",
        "extra_specs": {"pci_passthrough:alias": "audio-card:1"},
    }
    assert is_gpu_flavor(f3) is False

    # 4. Flavor with :category extra spec containing gpu
    f4 = {
        "id": "fl-4",
        "name": "custom-compute",
        "extra_specs": {":category": "gpu_workload"},
    }
    assert is_gpu_flavor(f4) is True

    # 5. Flavor name starting with gpu.
    f5 = FlavorInfo(id="fl-5", name="gpu.4c_8g", vcpus=4, ram=8192, disk=50, extra_specs={})
    assert is_gpu_flavor(f5) is True
    assert f5.is_gpu is True

    # 6. Non-GPU flavor
    f6 = FlavorInfo(id="fl-6", name="m1.medium", vcpus=2, ram=4096, disk=20, extra_specs={})
    assert is_gpu_flavor(f6) is False
    assert f6.is_gpu is False
    assert is_gpu_flavor({"name": "accelerated-node", "extra_specs": {"pci_passthrough:alias": "RTX3090"}})
    assert not is_gpu_flavor({"name": "network-node", "extra_specs": {"pci_passthrough:alias": "sriov_nic:1"}})


@pytest.mark.asyncio
async def test_flavor_filter_enforces_no_count_gpu_alias_and_ignores_non_gpu_pci(client, mock_conn):
    cpu_flavor = FlavorInfo(id="fl-cpu", name="m1.medium", vcpus=2, ram=4096, disk=20, extra_specs={})
    denied_gpu = FlavorInfo(
        id="fl-denied",
        name="accelerated-denied",
        vcpus=8,
        ram=16384,
        disk=100,
        extra_specs={"pci_passthrough:alias": "RTX3090"},
    )
    allowed_gpu = FlavorInfo(
        id="fl-allowed",
        name="accelerated-allowed",
        vcpus=8,
        ram=16384,
        disk=100,
        extra_specs={"pci_passthrough:alias": "sriov_nic:1,H100"},
    )

    compute_quota = {
        "instances": {"limit": 10, "in_use": 1},
        "cores": {"limit": 20, "in_use": 2},
        "ram": {"limit": 32768, "in_use": 4096},
    }
    gpu_statuses = [
        {"project_id": "proj-123", "gpu_type": "RTX3090", "limit": 0, "in_use": 0, "available": 0},
        {"project_id": "proj-123", "gpu_type": "H100", "limit": 1, "in_use": 0, "available": 1},
    ]

    with (
        patch(
            "app.api.compute.flavors.nova.list_flavors",
            return_value=[cpu_flavor, denied_gpu, allowed_gpu],
        ),
        patch("app.api.compute.flavors.cache.cached_call", new=_load_without_cache),
        patch("app.services.nova.get_project_quota", return_value=compute_quota),
        patch("app.services.gpu_quota.get_effective_gpu_quota_status", return_value=gpu_statuses),
    ):
        response = await client.get("/api/v1/flavors")

    assert response.status_code == 200
    items = response.json()
    assert [f["id"] for f in items] == ["fl-cpu", "fl-denied", "fl-allowed"]
    by_id = {f["id"]: f["eligibility"] for f in items}
    assert by_id["fl-cpu"]["selectable"] is True
    assert by_id["fl-allowed"]["selectable"] is True
    assert by_id["fl-denied"]["selectable"] is False
    assert by_id["fl-denied"]["blockers"][0]["code"] == "gpu_insufficient"


@pytest.mark.asyncio
async def test_require_gpu_quota_forwards_dict_extra_specs():
    conn = MagicMock()
    conn._afterglow_project_id = "proj-123"
    flavor = {
        "name": "accelerated-node",
        "extra_specs": {"pci_passthrough:alias": "sriov_nic:1,RTX3090:1"},
    }
    with patch("app.services.gpu_quota.check_gpu_quota") as mock_check:
        assert await require_gpu_quota(conn, flavor) is True

    mock_check.assert_awaited_once_with(conn, "proj-123", {"RTX3090": 1})


@pytest.mark.asyncio
async def test_cpu_flavor_bypasses_gpu_quota_check():
    """CPU-only flavor must bypass Afterglow GPU quota checks completely."""
    from app.api.compute.instances import create_instance

    conn = MagicMock()
    conn._afterglow_project_id = "proj-123"

    cpu_flavor = FlavorInfo(
        id="fl-cpu",
        name="m1.medium",
        vcpus=2,
        ram=4096,
        disk=20,
        extra_specs={},
    )

    req = CreateInstanceRequest(
        name="test-cpu-vm",
        flavor_id="fl-cpu",
        image_id="img-123",
        libraries=[],
    )

    # Direct unit test of require_gpu_quota
    with patch("app.services.gpu_quota.check_gpu_quota") as mock_check:
        res = await require_gpu_quota(conn, cpu_flavor)
    assert res is False
    mock_check.assert_not_awaited()

    # Route / endpoint level execution test
    with (
        patch("app.api.compute.instances.nova.list_flavors", return_value=[cpu_flavor]),
        patch("app.services.gpu_quota.check_gpu_quota") as mock_check,
        patch("app.services.instance_names.ensure_unique_instance_name", return_value="test-cpu-vm"),
        patch("app.api.compute.instances._resolve_create_placement", return_value=(req, "nova", "nova")),
        patch("app.api.compute.instances.cinder.create_volume_from_image", return_value=_make_volume()) as mock_cinder,
        patch("app.api.compute.instances.cinder.rename_volume"),
        patch("app.api.compute.instances.nova.create_server", return_value=_make_server()) as mock_nova,
        patch("app.api.compute.instances.neutron.list_networks", return_value=[]),
        patch("app.api.compute.instances.instance_orch.compute_effective_security_groups", AsyncMock(return_value=[])),
        patch("app.api.compute.instances.instance_orch.build_instance_meta", return_value={}),
        patch("app.api.compute.instances.instance_orch.try_issue_health_token", AsyncMock(return_value=("", "", ""))),
        patch("app.api.compute.instances.rec", AsyncMock()),
        patch("app.api.compute.instances.invalidate", AsyncMock()),
        patch("app.api.compute.instances.cache_invalidation.invalidate_mutation_count", AsyncMock()),
    ):
        result = await create_instance(
            request=MagicMock(),
            req=req,
            conn=conn,
            token_info={"token": "t", "project_id": "proj-123"},
        )
        assert result.id == "srv-123"
        mock_check.assert_not_awaited()
        mock_cinder.assert_called_once()
        mock_nova.assert_called_once()


@pytest.mark.asyncio
async def test_gpu_quota_allow_reaches_mutation_boundary():
    """GPU quota check affirmative decision allows request to reach resource mutation steps."""
    from app.api.compute.instances import create_instance

    conn = MagicMock()
    conn._afterglow_project_id = "proj-123"

    gpu_flavor = FlavorInfo(
        id="fl-gpu",
        name="gpu.4c_8g",
        vcpus=4,
        ram=8192,
        disk=50,
        extra_specs={"pci_passthrough:alias": "gpu-a100:1"},
    )

    req = CreateInstanceRequest(
        name="test-gpu-vm",
        flavor_id="fl-gpu",
        image_id="img-123",
        libraries=[],
    )

    with (
        patch("app.api.compute.instances.nova.list_flavors", return_value=[gpu_flavor]),
        patch("app.services.gpu_quota.check_gpu_quota") as mock_check,
        patch("app.services.instance_names.ensure_unique_instance_name", return_value="test-gpu-vm"),
        patch("app.api.compute.instances._resolve_create_placement", return_value=(req, "nova", "nova")),
        patch("app.api.compute.instances.cinder.create_volume_from_image", return_value=_make_volume()) as mock_cinder,
        patch("app.api.compute.instances.cinder.rename_volume"),
        patch("app.api.compute.instances.nova.create_server", return_value=_make_server()) as mock_nova,
        patch("app.api.compute.instances.neutron.list_networks", return_value=[]),
        patch("app.api.compute.instances.instance_orch.compute_effective_security_groups", AsyncMock(return_value=[])),
        patch("app.api.compute.instances.instance_orch.build_instance_meta", return_value={}),
        patch("app.api.compute.instances.instance_orch.try_issue_health_token", AsyncMock(return_value=("", "", ""))),
        patch("app.api.compute.instances.rec", AsyncMock()),
        patch("app.api.compute.instances.invalidate", AsyncMock()),
        patch("app.api.compute.instances.cache_invalidation.invalidate_mutation_count", AsyncMock()),
    ):
        result = await create_instance(
            request=MagicMock(),
            req=req,
            conn=conn,
            token_info={"token": "t", "project_id": "proj-123"},
        )
        assert result.id == "srv-123"
        mock_check.assert_called_once_with(conn, "proj-123", {"GPUA100": 1})
        mock_cinder.assert_called_once()
        mock_nova.assert_called_once()


@pytest.mark.asyncio
async def test_nonstandard_flavor_name_gpu_quota_checked():
    """Nonstandard flavor name with GPU PCI alias is quota-checked locally."""
    from app.api.compute.instances import create_instance

    conn = MagicMock()
    conn._afterglow_project_id = "proj-123"

    nonstandard_gpu_flavor = FlavorInfo(
        id="fl-custom",
        name="custom-compute-node-xl",
        vcpus=16,
        ram=32768,
        disk=100,
        extra_specs={"pci_passthrough:alias": "nvidia-h100:1"},
    )

    req = CreateInstanceRequest(
        name="test-nonstandard-vm",
        flavor_id="fl-custom",
        image_id="img-123",
        libraries=[],
    )

    from app.services.gpu_quota import GpuQuotaDenied

    with (
        patch("app.api.compute.instances.nova.list_flavors", return_value=[nonstandard_gpu_flavor]),
        patch(
            "app.services.gpu_quota.check_gpu_quota", side_effect=GpuQuotaDenied("H100 GPU quota limit reached")
        ) as mock_check,
        patch("app.services.instance_names.ensure_unique_instance_name", return_value="test-nonstandard-vm"),
        patch("app.api.compute.instances._resolve_create_placement", return_value=(req, "nova", "nova")),
        patch("app.api.compute.instances._prepare_prebuilt_file_storages") as mock_manila,
        patch("app.api.compute.instances.cinder.create_volume_from_image") as mock_cinder,
        patch("app.api.compute.instances.nova.create_server") as mock_nova,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await create_instance(
                request=MagicMock(),
                req=req,
                conn=conn,
                token_info={"token": "t", "project_id": "proj-123"},
            )
        assert exc_info.value.status_code == 409
        assert "H100 GPU quota limit reached" in exc_info.value.detail
        mock_check.assert_called_once_with(conn, "proj-123", {"NVIDIAH100": 1})
        mock_manila.assert_not_called()
        mock_cinder.assert_not_called()
        mock_nova.assert_not_called()


@pytest.mark.asyncio
async def test_sync_instance_creation_gpu_quota_denial_prevents_mutation():
    from app.api.compute.instances import create_instance

    conn = MagicMock()
    conn._afterglow_project_id = "proj-123"

    gpu_flavor = FlavorInfo(
        id="fl-gpu",
        name="custom-gpu-flavor",
        vcpus=4,
        ram=8192,
        disk=50,
        extra_specs={"pci_passthrough:alias": "gpu-a100:1"},
    )

    req = CreateInstanceRequest(
        name="test-gpu-vm",
        flavor_id="fl-gpu",
        image_id="img-123",
        libraries=[],
    )

    from app.services.gpu_quota import GpuQuotaDenied

    with (
        patch("app.api.compute.instances.nova.list_flavors", return_value=[gpu_flavor]),
        patch("app.services.gpu_quota.check_gpu_quota", side_effect=GpuQuotaDenied("GPU quota limit exceeded")),
        patch("app.services.instance_names.ensure_unique_instance_name", return_value="test-gpu-vm"),
        patch("app.api.compute.instances._resolve_create_placement", return_value=(req, "nova", "nova")),
        patch("app.api.compute.instances._prepare_prebuilt_file_storages") as mock_manila,
        patch("app.api.compute.instances.cinder.create_volume_from_image") as mock_cinder,
        patch("app.api.compute.instances.nova.create_server") as mock_nova,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await create_instance(
                request=MagicMock(),
                req=req,
                conn=conn,
                token_info={"token": "t", "project_id": "proj-123"},
            )
        assert exc_info.value.status_code == 409
        assert "GPU quota limit exceeded" in exc_info.value.detail
        mock_manila.assert_not_called()
        mock_cinder.assert_not_called()
        mock_nova.assert_not_called()


@pytest.mark.asyncio
async def test_sync_instance_creation_gpu_quota_malformed_returns_503_and_no_mutation():
    from app.api.compute.instances import create_instance

    conn = MagicMock()
    conn._afterglow_project_id = "proj-123"

    gpu_flavor = FlavorInfo(
        id="fl-gpu",
        name="gpu.4c_8g",
        vcpus=4,
        ram=8192,
        disk=50,
    )

    req = CreateInstanceRequest(
        name="test-gpu-vm",
        flavor_id="fl-gpu",
        image_id="img-123",
        libraries=[],
    )

    from app.services.gpu_quota import GpuQuotaUnavailable

    with (
        patch("app.api.compute.instances.nova.list_flavors", return_value=[gpu_flavor]),
        patch(
            "app.services.gpu_quota.check_gpu_quota",
            side_effect=GpuQuotaUnavailable("GPU quota 서비스에 접근할 수 없습니다"),
        ),
        patch("app.services.instance_names.ensure_unique_instance_name", return_value="test-gpu-vm"),
        patch("app.api.compute.instances._resolve_create_placement", return_value=(req, "nova", "nova")),
        patch("app.api.compute.instances._prepare_prebuilt_file_storages") as mock_manila,
        patch("app.api.compute.instances.cinder.create_volume_from_image") as mock_cinder,
        patch("app.api.compute.instances.nova.create_server") as mock_nova,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await create_instance(
                request=MagicMock(),
                req=req,
                conn=conn,
                token_info={"token": "t", "project_id": "proj-123"},
            )
        assert exc_info.value.status_code == 503
        assert "GPU quota 서비스에 접근할 수 없습니다" in exc_info.value.detail
        mock_manila.assert_not_called()
        mock_cinder.assert_not_called()
        mock_nova.assert_not_called()


@pytest.mark.asyncio
async def test_sync_instance_creation_gpu_quota_authority_unavailable_returns_503_and_no_mutation():
    """Unavailable Afterglow quota authority yields 503 and prevents mutation."""
    from app.api.compute.instances import create_instance

    conn = MagicMock()
    conn._afterglow_project_id = "proj-123"

    gpu_flavor = FlavorInfo(
        id="fl-gpu",
        name="gpu.4c_8g",
        vcpus=4,
        ram=8192,
        disk=50,
        extra_specs={"pci_passthrough:alias": "gpu-a100:1"},
    )

    req = CreateInstanceRequest(
        name="test-gpu-vm",
        flavor_id="fl-gpu",
        image_id="img-123",
        libraries=[],
    )

    from app.services.gpu_quota import GpuQuotaUnavailable

    with (
        patch("app.api.compute.instances.nova.list_flavors", return_value=[gpu_flavor]),
        patch(
            "app.services.gpu_quota.check_gpu_quota",
            side_effect=GpuQuotaUnavailable("GPU quota 서비스에 접근할 수 없습니다"),
        ),
        patch("app.services.instance_names.ensure_unique_instance_name", return_value="test-gpu-vm"),
        patch("app.api.compute.instances._resolve_create_placement", return_value=(req, "nova", "nova")),
        patch("app.api.compute.instances._prepare_prebuilt_file_storages") as mock_manila,
        patch("app.api.compute.instances.cinder.create_volume_from_image") as mock_cinder,
        patch("app.api.compute.instances.nova.create_server") as mock_nova,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await create_instance(
                request=MagicMock(),
                req=req,
                conn=conn,
                token_info={"token": "t", "project_id": "proj-123"},
            )
        assert exc_info.value.status_code == 503
        assert "GPU quota 서비스에 접근할 수 없습니다" in exc_info.value.detail
        mock_manila.assert_not_called()
        mock_cinder.assert_not_called()
        mock_nova.assert_not_called()


@pytest.mark.asyncio
async def test_tenant_async_quota_denial_returns_409_before_streaming(client, mock_conn):
    """Tenant GPU quota denial is an HTTP precondition failure."""
    gpu_flavor = FlavorInfo(
        id="fl-gpu",
        name="gpu.4c_8g",
        vcpus=4,
        ram=8192,
        disk=50,
        extra_specs={"pci_passthrough:alias": "gpu-a100:1"},
    )

    payload = {
        "name": "tenant-sse-vm",
        "image_id": "img-123",
        "flavor_id": "fl-gpu",
        "libraries": [],
        "boot_volume_size_gb": 50,
    }

    from app.services.gpu_quota import GpuQuotaDenied

    with (
        patch("app.api.compute.instances.nova.list_flavors", return_value=[gpu_flavor]),
        patch("app.services.gpu_quota.check_gpu_quota", side_effect=GpuQuotaDenied("Tenant GPU quota exceeded")),
        patch("app.services.instance_names.ensure_unique_instance_name", return_value="tenant-sse-vm"),
        patch("app.api.compute.instances._prepare_prebuilt_file_storages") as mock_manila,
        patch("app.api.compute.instances.cinder.create_volume_from_image") as mock_cinder,
        patch("app.api.compute.instances.nova.create_server") as mock_nova,
    ):
        resp = await client.post("/api/v1/instances/async", json=payload)

    assert resp.status_code == 409
    assert resp.json()["detail"] == "Tenant GPU quota exceeded"
    mock_manila.assert_not_called()
    mock_cinder.assert_not_called()
    mock_nova.assert_not_called()


@pytest.mark.asyncio
async def test_tenant_async_quota_unavailable_returns_503_before_streaming(client, mock_conn):
    """Tenant quota authority unavailability is an HTTP precondition failure."""
    gpu_flavor = FlavorInfo(
        id="fl-gpu",
        name="gpu.4c_8g",
        vcpus=4,
        ram=8192,
        disk=50,
        extra_specs={"pci_passthrough:alias": "gpu-a100:1"},
    )

    payload = {
        "name": "tenant-sse-vm",
        "image_id": "img-123",
        "flavor_id": "fl-gpu",
        "libraries": [],
        "boot_volume_size_gb": 50,
    }

    from app.services.gpu_quota import GpuQuotaUnavailable

    with (
        patch("app.api.compute.instances.nova.list_flavors", return_value=[gpu_flavor]),
        patch("app.services.gpu_quota.check_gpu_quota", side_effect=GpuQuotaUnavailable("GPU quota timeout")),
        patch("app.services.instance_names.ensure_unique_instance_name", return_value="tenant-sse-vm"),
        patch("app.api.compute.instances._prepare_prebuilt_file_storages") as mock_manila,
        patch("app.api.compute.instances.cinder.create_volume_from_image") as mock_cinder,
        patch("app.api.compute.instances.nova.create_server") as mock_nova,
    ):
        resp = await client.post("/api/v1/instances/async", json=payload)

    assert resp.status_code == 503
    assert resp.json()["detail"] == "내부 서버 오류"
    mock_manila.assert_not_called()
    mock_cinder.assert_not_called()
    mock_nova.assert_not_called()


@pytest.mark.asyncio
async def test_admin_async_quota_denial_returns_409_before_streaming(admin_client, mock_conn):
    """Admin target GPU quota denial is an HTTP precondition failure."""
    gpu_flavor = FlavorInfo(
        id="fl-gpu",
        name="gpu.4c_8g",
        vcpus=4,
        ram=8192,
        disk=50,
        extra_specs={"pci_passthrough:alias": "gpu-a100:1"},
    )

    payload = {
        "name": "admin-sse-vm",
        "image_id": "img-123",
        "flavor_id": "fl-gpu",
        "project_id": "target-proj-abc",
        "libraries": [],
    }

    from app.services.gpu_quota import GpuQuotaDenied

    with (
        patch("app.api.identity.admin_instances.keystone.get_admin_connection_for_project", return_value=mock_conn),
        patch("app.api.identity.admin_instances.nova.list_flavors", return_value=[gpu_flavor]),
        patch(
            "app.services.gpu_quota.check_gpu_quota",
            side_effect=GpuQuotaDenied("Admin target project GPU quota exceeded"),
        ),
        patch("app.services.instance_names.ensure_unique_instance_name", return_value="admin-sse-vm"),
        patch("app.api.compute.instances._prepare_prebuilt_file_storages") as mock_manila,
        patch("app.api.identity.admin_instances.cinder.create_volume_from_image") as mock_cinder,
        patch("app.api.identity.admin_instances.nova.create_server") as mock_nova,
    ):
        resp = await admin_client.post("/api/v1/admin/instances/async", json=payload)

    assert resp.status_code == 409
    assert resp.json()["detail"] == "Admin target project GPU quota exceeded"
    mock_manila.assert_not_called()
    mock_cinder.assert_not_called()
    mock_nova.assert_not_called()


@pytest.mark.asyncio
async def test_admin_async_quota_unavailable_returns_503_before_streaming(admin_client, mock_conn):
    """Admin target quota authority unavailability is an HTTP precondition failure."""
    gpu_flavor = FlavorInfo(
        id="fl-gpu",
        name="gpu.4c_8g",
        vcpus=4,
        ram=8192,
        disk=50,
        extra_specs={"pci_passthrough:alias": "gpu-a100:1"},
    )

    payload = {
        "name": "admin-sse-vm",
        "image_id": "img-123",
        "flavor_id": "fl-gpu",
        "project_id": "target-proj-abc",
        "libraries": [],
    }

    from app.services.gpu_quota import GpuQuotaUnavailable

    with (
        patch("app.api.identity.admin_instances.keystone.get_admin_connection_for_project", return_value=mock_conn),
        patch("app.api.identity.admin_instances.nova.list_flavors", return_value=[gpu_flavor]),
        patch("app.services.gpu_quota.check_gpu_quota", side_effect=GpuQuotaUnavailable("Admin connection failed")),
        patch("app.services.instance_names.ensure_unique_instance_name", return_value="admin-sse-vm"),
        patch("app.api.compute.instances._prepare_prebuilt_file_storages") as mock_manila,
        patch("app.api.identity.admin_instances.cinder.create_volume_from_image") as mock_cinder,
        patch("app.api.identity.admin_instances.nova.create_server") as mock_nova,
    ):
        resp = await admin_client.post("/api/v1/admin/instances/async", json=payload)

    assert resp.status_code == 503
    assert resp.json()["detail"] == "내부 서버 오류"
    mock_manila.assert_not_called()
    mock_cinder.assert_not_called()
    mock_nova.assert_not_called()


@pytest.mark.asyncio
async def test_flavors_list_marks_gpu_flavors_unavailable_when_quota_authority_unavailable():
    from app.api.compute.flavors import list_flavors

    conn = MagicMock()
    conn._afterglow_project_id = "proj-123"

    all_flavors = [
        FlavorInfo(id="f1", name="m1.small", vcpus=1, ram=2048, disk=10),
        FlavorInfo(
            id="f2", name="custom-a100", vcpus=8, ram=16384, disk=100, extra_specs={"pci_passthrough:alias": "a100:1"}
        ),
        FlavorInfo(id="f3", name="gpu.4c_8g", vcpus=4, ram=8192, disk=50),
    ]

    with (
        patch("app.api.compute.flavors.nova.list_flavors", return_value=all_flavors),
        patch("app.services.gpu_quota.get_effective_gpu_quotas", side_effect=Exception("Local service unreachable")),
        patch("app.api.compute.flavors.cache.cached_call", new=AsyncMock(side_effect=_load_without_cache)),
    ):
        flavors = await list_flavors(conn=conn, cm=MagicMock(enabled=False))

    assert [flavor.id for flavor in flavors] == ["f1", "f2", "f3"]
    for flavor in flavors[1:]:
        assert flavor.eligibility is not None
        assert flavor.eligibility.selectable is False
        assert [blocker.code for blocker in flavor.eligibility.blockers] == ["gpu_quota_unavailable"]


@pytest.mark.asyncio
async def test_gpu_available_fallback_when_quota_authority_unavailable():
    from app.api.common.dashboard import get_gpu_available

    conn = MagicMock()
    cache_mode = MagicMock(enabled=False)

    fake_placement_data = {
        "gpu_types": [{"device_name": "RTX 3090", "vendor": "NVIDIA", "total": 4, "used": 1, "available": 3}],
        "summary": {"total": 4, "used": 1, "available": 3},
    }

    settings = MagicMock(gpu_available_visible=True)
    with (
        patch("app.api.common.dashboard.get_settings", return_value=settings),
        patch("app.api.common.dashboard.cached_call", new=AsyncMock(return_value=fake_placement_data)),
        patch(
            "app.services.gpu_quota.get_effective_gpu_quota_status", side_effect=Exception("Local service unreachable")
        ),
    ):
        result = await get_gpu_available(conn=conn, cm=cache_mode)
        assert result["gpu_types"] == []
        assert result["summary"] == {"total": 0, "used": 0, "available": 0}
        assert result["available"] is False
