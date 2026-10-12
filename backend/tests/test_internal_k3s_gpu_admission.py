"""HTTP consumer tests with real flavor visibility, GPU quota, and usage logic.

Only the canonical service connection, native compute API, and effective-quota
DB boundary are stubbed; no cloud or database calls leave this process.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from openstack.compute.v2.flavor import Flavor
from openstack.exceptions import ForbiddenException, ResourceNotFound

from app.main import app
from app.services.gpu_quota import GpuQuotaUnavailable

ADMISSION_URL = "/api/v1/internal/k3s/gpu-admission"
ADMISSION_HEADERS = {"X-Afterglow-K3s-Admission-Token": "test-admission-secret"}
REQUEST_PROJECT = "project-1"
SERVICE_PROJECT = "service-project"
ADMISSION_BODY = {"project_id": REQUEST_PROJECT, "flavor_id": "accelerated-flavor"}


def _gpu_server(project_id, count=1, *, tenant_id=None):
    return SimpleNamespace(
        project_id=project_id,
        tenant_id=tenant_id,
        status="ACTIVE",
        flavor={"original_name": "accelerated-node", "extra_specs": {"pci_passthrough:alias": f"RTX3090:{count}"}},
    )


@pytest.fixture
async def admission_client(monkeypatch):
    monkeypatch.setenv("K3S_GPU_ADMISSION_TOKEN", "test-admission-secret")
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client
    finally:
        get_settings.cache_clear()


@pytest.fixture
def admission_cloud(monkeypatch):
    from app.api import internal_k3s
    from app.services import gpu_quota

    compute = MagicMock(spec=["get_flavor", "fetch_flavor_extra_specs", "get_flavor_access", "servers"])
    flavor = Flavor(
        id=ADMISSION_BODY["flavor_id"],
        name="accelerated-node",
        is_public=True,
        extra_specs={"pci_passthrough:alias": "RTX3090:1"},
    )
    compute.get_flavor.return_value = flavor
    compute.fetch_flavor_extra_specs.return_value = flavor
    compute.get_flavor_access.return_value = []
    compute.servers.return_value = []
    conn = SimpleNamespace(
        compute=compute,
        close=MagicMock(),
        current_project_id=SERVICE_PROJECT,
        _afterglow_authenticated_project_id=SERVICE_PROJECT,
        _afterglow_project_id=SERVICE_PROJECT,
    )
    factory = AsyncMock(return_value=conn)
    quotas = {REQUEST_PROJECT: {"RTX3090": 1}, SERVICE_PROJECT: {"RTX3090": 0}}

    async def effective_quotas(_conn, project_id, *, session=None):
        return quotas.get(project_id, {})

    effective = AsyncMock(side_effect=effective_quotas)
    monkeypatch.setattr(internal_k3s, "get_service_project_connection", factory)
    monkeypatch.setattr(gpu_quota, "get_effective_gpu_quotas", effective)
    return SimpleNamespace(conn=conn, factory=factory, effective=effective, quotas=quotas, flavor=flavor)


def _assert_service_scope_preserved(cloud):
    cloud.factory.assert_awaited_once_with()
    assert cloud.conn.current_project_id == SERVICE_PROJECT
    assert cloud.conn._afterglow_authenticated_project_id == SERVICE_PROJECT
    assert cloud.conn._afterglow_project_id == SERVICE_PROJECT
    cloud.conn.close.assert_called_once_with()


def _assert_no_cloud_work(cloud):
    cloud.factory.assert_not_awaited()
    assert cloud.conn.compute.mock_calls == []
    cloud.effective.assert_not_awaited()
    cloud.conn.close.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("credential", [None, "invalid", "   ", "비밀"])
async def test_gpu_admission_rejects_credentials_before_cloud_work(admission_client, admission_cloud, credential):
    headers = {} if credential is None else {"X-Afterglow-K3s-Admission-Token": credential.encode("utf-8")}
    response = await admission_client.post(ADMISSION_URL, json=ADMISSION_BODY, headers=headers)

    assert response.status_code == 401
    _assert_no_cloud_work(admission_cloud)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("body", "status"),
    [
        ({"project_id": "../project", "flavor_id": "flavor-1"}, 400),
        ({"project_id": REQUEST_PROJECT, "flavor_id": "../flavor"}, 400),
        ({"project_id": "", "flavor_id": "flavor-1"}, 400),
        ({"project_id": REQUEST_PROJECT, "flavor_id": ""}, 400),
        ({"project_id": "p" * 65, "flavor_id": "flavor-1"}, 400),
        ({"project_id": REQUEST_PROJECT}, 422),
        ({"project_id": None, "flavor_id": "flavor-1"}, 422),
        ({"project_id": REQUEST_PROJECT, "flavor_id": []}, 422),
    ],
)
async def test_gpu_admission_rejects_malformed_request_before_cloud_work(
    admission_client, admission_cloud, body, status
):
    response = await admission_client.post(ADMISSION_URL, json=body, headers=ADMISSION_HEADERS)

    assert response.status_code == status
    _assert_no_cloud_work(admission_cloud)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("requested_usage", "requested_quota", "service_quota", "status"),
    [(1, 2, 0, 200), (2, 2, 100, 409), (0, 0, 100, 409)],
)
async def test_gpu_admission_uses_only_requested_project_usage_and_quota(
    admission_client, admission_cloud, requested_usage, requested_quota, service_quota, status
):
    cloud = admission_cloud
    cloud.quotas[REQUEST_PROJECT] = {"RTX3090": requested_quota}
    cloud.quotas[SERVICE_PROJECT] = {"RTX3090": service_quota}
    cloud.conn.compute.servers.return_value = [
        _gpu_server(SERVICE_PROJECT, 50),
        _gpu_server("other-project", 50),
        *([_gpu_server(REQUEST_PROJECT, requested_usage)] if requested_usage else []),
    ]

    response = await admission_client.post(ADMISSION_URL, json=ADMISSION_BODY, headers=ADMISSION_HEADERS)

    assert response.status_code == status
    if status == 200:
        assert response.json() == {"gpu_required": True}
    else:
        detail = response.json()["detail"]
        assert f"project {REQUEST_PROJECT}" in detail
        assert f"limit={requested_quota}, in_use={requested_usage}, requested=1" in detail
    cloud.effective.assert_awaited_once_with(cloud.conn, REQUEST_PROJECT, session=None)
    cloud.conn.compute.get_flavor.assert_called_once_with(ADMISSION_BODY["flavor_id"])
    cloud.conn.compute.servers.assert_called_once_with(details=True, all_projects=True, project_id=REQUEST_PROJECT)
    cloud.conn.compute.get_flavor_access.assert_not_called()
    _assert_service_scope_preserved(cloud)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("public", "access", "status"),
    [
        (True, [], 200),
        (False, [{"tenant_id": REQUEST_PROJECT}], 200),
        (False, [{"project_id": REQUEST_PROJECT}], 200),
        (False, [], 400),
        (False, [{"tenant_id": SERVICE_PROJECT}], 400),
        (False, [{"tenant_id": "other-project"}], 400),
    ],
    ids=["public", "shared-tenant-id", "shared-project-id", "unshared", "service-only", "other-only"],
)
async def test_gpu_admission_checks_native_visibility_for_requested_project(
    admission_client, admission_cloud, public, access, status
):
    cloud = admission_cloud
    # Native get_flavor omits extra specs by default; visibility must precede fetching them.
    cloud.conn.compute.get_flavor.return_value = Flavor(
        id=ADMISSION_BODY["flavor_id"], name="accelerated-node", is_public=public, extra_specs={}
    )
    cloud.flavor.is_public = public
    cloud.conn.compute.get_flavor_access.return_value = access

    response = await admission_client.post(ADMISSION_URL, json=ADMISSION_BODY, headers=ADMISSION_HEADERS)

    assert response.status_code == status
    if public:
        cloud.conn.compute.get_flavor_access.assert_not_called()
    else:
        cloud.conn.compute.get_flavor_access.assert_called_once_with(ADMISSION_BODY["flavor_id"])
    if status == 200:
        assert response.json() == {"gpu_required": True}
        cloud.conn.compute.fetch_flavor_extra_specs.assert_called_once_with(cloud.conn.compute.get_flavor.return_value)
        cloud.effective.assert_awaited_once_with(cloud.conn, REQUEST_PROJECT, session=None)
        cloud.conn.compute.servers.assert_called_once_with(details=True, all_projects=True, project_id=REQUEST_PROJECT)
    else:
        assert response.json()["detail"] == "Flavor not found"
        cloud.conn.compute.fetch_flavor_extra_specs.assert_not_called()
        cloud.effective.assert_not_awaited()
        cloud.conn.compute.servers.assert_not_called()
    _assert_service_scope_preserved(cloud)


@pytest.mark.asyncio
@pytest.mark.parametrize("not_found", [False, True], ids=["none", "native-404"])
async def test_gpu_admission_missing_flavor_does_not_consult_quota(admission_client, admission_cloud, not_found):
    cloud = admission_cloud
    if not_found:
        cloud.conn.compute.get_flavor.side_effect = ResourceNotFound("missing flavor")
    else:
        cloud.conn.compute.get_flavor.return_value = None

    response = await admission_client.post(ADMISSION_URL, json=ADMISSION_BODY, headers=ADMISSION_HEADERS)

    assert response.status_code == 400
    assert response.json()["detail"] == "Flavor not found"
    cloud.conn.compute.get_flavor_access.assert_not_called()
    cloud.conn.compute.fetch_flavor_extra_specs.assert_not_called()
    cloud.effective.assert_not_awaited()
    cloud.conn.compute.servers.assert_not_called()
    _assert_service_scope_preserved(cloud)


@pytest.mark.asyncio
async def test_gpu_admission_connection_failure_fails_closed(admission_client, admission_cloud):
    cloud = admission_cloud
    cloud.factory.side_effect = RuntimeError("service authentication unavailable")

    response = await admission_client.post(ADMISSION_URL, json=ADMISSION_BODY, headers=ADMISSION_HEADERS)

    assert response.status_code == 503
    cloud.factory.assert_awaited_once_with()
    assert cloud.conn.compute.mock_calls == []
    cloud.effective.assert_not_awaited()
    cloud.conn.close.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["flavor", "acl", "acl-generator", "metadata", "metadata-404"])
async def test_gpu_admission_native_flavor_failures_fail_closed(admission_client, admission_cloud, boundary):
    cloud = admission_cloud
    compute = cloud.conn.compute
    if boundary == "flavor":
        compute.get_flavor.side_effect = ForbiddenException("flavor lookup forbidden")
    elif boundary.startswith("acl"):
        cloud.flavor.is_public = False
        if boundary == "acl":
            compute.get_flavor_access.side_effect = ForbiddenException("ACL lookup forbidden")
        else:

            def incomplete_acl(_flavor_id):
                yield {"tenant_id": REQUEST_PROJECT}
                raise ForbiddenException("ACL pagination forbidden")

            compute.get_flavor_access.side_effect = incomplete_acl
    else:
        cloud.flavor.extra_specs = {}
        compute.fetch_flavor_extra_specs.side_effect = (
            ResourceNotFound("extra specs disappeared")
            if boundary == "metadata-404"
            else RuntimeError("metadata failed")
        )

    response = await admission_client.post(ADMISSION_URL, json=ADMISSION_BODY, headers=ADMISSION_HEADERS)

    assert response.status_code == 503
    cloud.effective.assert_not_awaited()
    compute.servers.assert_not_called()
    _assert_service_scope_preserved(cloud)


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["query", "query-generator", "missing-owner", "usage-flavor"])
async def test_gpu_admission_usage_inventory_failures_fail_closed(admission_client, admission_cloud, boundary):
    cloud = admission_cloud
    compute = cloud.conn.compute
    if boundary == "query":
        compute.servers.side_effect = ForbiddenException("cross-project listing forbidden")
    elif boundary == "query-generator":

        def incomplete_inventory(**_kwargs):
            yield _gpu_server(REQUEST_PROJECT)
            raise ForbiddenException("server pagination forbidden")

        compute.servers.side_effect = incomplete_inventory
    elif boundary == "missing-owner":
        compute.servers.return_value = [_gpu_server(None)]
    else:
        compute.servers.return_value = [
            SimpleNamespace(project_id=REQUEST_PROJECT, tenant_id=None, status="ACTIVE", flavor={"id": "legacy-flavor"})
        ]
        compute.get_flavor.side_effect = [cloud.flavor, ResourceNotFound("usage flavor metadata unavailable")]

    response = await admission_client.post(ADMISSION_URL, json=ADMISSION_BODY, headers=ADMISSION_HEADERS)

    assert response.status_code == 503
    cloud.effective.assert_awaited_once_with(cloud.conn, REQUEST_PROJECT, session=None)
    compute.servers.assert_called_once_with(details=True, all_projects=True, project_id=REQUEST_PROJECT)
    _assert_service_scope_preserved(cloud)


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [GpuQuotaUnavailable("quota DB unavailable"), RuntimeError("quota query failed")])
async def test_gpu_admission_effective_quota_failures_fail_closed(admission_client, admission_cloud, error):
    cloud = admission_cloud
    cloud.effective.side_effect = error

    response = await admission_client.post(ADMISSION_URL, json=ADMISSION_BODY, headers=ADMISSION_HEADERS)

    assert response.status_code == 503
    cloud.effective.assert_awaited_once_with(cloud.conn, REQUEST_PROJECT, session=None)
    cloud.conn.compute.servers.assert_not_called()
    _assert_service_scope_preserved(cloud)


@pytest.mark.asyncio
async def test_gpu_admission_cpu_flavor_works_without_gpu_quota(admission_client, admission_cloud):
    cloud = admission_cloud
    cpu = Flavor(id="cpu-flavor", name="m1.medium", is_public=True, extra_specs={})
    cloud.conn.compute.get_flavor.return_value = cpu
    cloud.conn.compute.fetch_flavor_extra_specs.return_value = cpu
    cloud.quotas[REQUEST_PROJECT] = {}
    cloud.effective.side_effect = GpuQuotaUnavailable("quota DB unavailable")
    cloud.conn.compute.servers.side_effect = ForbiddenException("GPU inventory unavailable")

    response = await admission_client.post(
        ADMISSION_URL,
        json={"project_id": REQUEST_PROJECT, "flavor_id": "cpu-flavor"},
        headers=ADMISSION_HEADERS,
    )

    assert response.status_code == 200
    assert response.json() == {"gpu_required": False}
    cloud.conn.compute.get_flavor.assert_called_once_with("cpu-flavor")
    cloud.conn.compute.fetch_flavor_extra_specs.assert_called_once_with(cpu)
    cloud.effective.assert_not_awaited()
    cloud.conn.compute.servers.assert_not_called()
    _assert_service_scope_preserved(cloud)
