"""compute/flavors.py 엔드포인트 단위 테스트."""

import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import CacheMode
from app.main import app
from app.models.compute import FlavorInfo
from app.services.cache import ttl_static
from app.services.nova import get_project_quota as read_native_compute_quota

pytestmark = pytest.mark.usefixtures("available_flavor_capacity")


@pytest.mark.asyncio
async def test_list_flavors_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/flavors")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_flavors_success(client, mock_conn):
    """nova.list_flavors 결과를 정상 반환한다."""

    async def mock_cached_call(key, ttl, fn, *, refresh=False, **kw):
        return await fn()

    with (
        patch("app.api.compute.flavors.nova.list_flavors", return_value=[]),
        patch("app.services.cache.cached_call", new=mock_cached_call),
    ):
        resp = await client.get("/api/v1/flavors")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_list_flavors_excludes_afterglow_hidden_flavors_before_eligibility(client, mock_conn):
    async def mock_cached_call(key, ttl, fn, *, refresh=False, **kw):
        return await fn()

    visible = FlavorInfo(id="visible", name="user.small", vcpus=1, ram=1024, disk=10)
    hidden = FlavorInfo(
        id="hidden",
        name="amphora",
        vcpus=1,
        ram=1024,
        disk=5,
        extra_specs={"afterglow:frontend_visible": "false"},
    )
    evaluator = AsyncMock(side_effect=lambda _conn, _pid, flavors, **_kwargs: list(flavors))
    with (
        patch("app.api.compute.flavors.nova.list_flavors", return_value=[visible, hidden]),
        patch("app.services.cache.cached_call", new=mock_cached_call),
        patch("app.services.flavor_eligibility.evaluate_project_flavors", evaluator),
    ):
        resp = await client.get("/api/v1/flavors")

    assert resp.status_code == 200
    assert [item["id"] for item in resp.json()] == ["visible"]
    assert [flavor.id for flavor in evaluator.await_args.args[2]] == ["visible"]


@pytest.mark.asyncio
async def test_list_flavors_uses_static_ttl(client, mock_conn):
    """캐시 TTL이 ttl_static() (300s)으로 호출되어야 한다."""
    captured = {}

    async def mock_cached_call(key, ttl, fn, *, refresh=False, **kw):
        captured["key"] = key
        captured["ttl"] = ttl
        return await fn()

    with (
        patch("app.api.compute.flavors.nova.list_flavors", return_value=[]),
        patch("app.services.cache.cached_call", new=mock_cached_call),
    ):
        resp = await client.get("/api/v1/flavors")

    assert resp.status_code == 200
    assert "flavors" in captured.get("key", "")
    assert "nova" in captured.get("key", "")
    assert captured.get("ttl") == ttl_static()


@pytest.mark.asyncio
async def test_list_flavors_cache_bypass(client, mock_conn):
    """?refresh=true 쿼리스트링이 cached_call에 refresh=True로 전달되어야 한다."""
    captured = {}

    async def mock_cached_call(key, ttl, fn, *, refresh=False, **kw):
        captured["refresh"] = refresh
        return await fn()

    with (
        patch("app.api.compute.flavors.nova.list_flavors", return_value=[]),
        patch("app.services.cache.cached_call", new=mock_cached_call),
    ):
        resp = await client.get("/api/v1/flavors?refresh=true")

    assert resp.status_code == 200
    assert captured.get("refresh") is True


@pytest.mark.asyncio
async def test_list_flavors_rehydrates_cached_dict_payload(client, mock_conn):
    """A Redis cache hit returns dicts; GPU flavors must survive eligibility evaluation."""
    from app.services.cache import _make_serializable

    cpu = FlavorInfo(id="fl-cpu", name="cpu.2c_4g", vcpus=2, ram=4096, disk=20)
    gpu = FlavorInfo(
        id="fl-gpu",
        name="gpu.3090_8c_32g",
        vcpus=8,
        ram=32768,
        disk=100,
        extra_specs={"pci_passthrough:alias": "RTX-3090:1"},
    )
    cached_payload = json.loads(json.dumps(_make_serializable([cpu, gpu])))
    compute_quota = {
        "instances": {"limit": 10, "in_use": 0},
        "cores": {"limit": 64, "in_use": 0},
        "ram": {"limit": 262144, "in_use": 0},
    }
    gpu_status = [{"project_id": "proj-123", "gpu_type": "RTX3090", "limit": -1, "in_use": 0, "available": -1}]

    with (
        patch("app.services.cache.cached_call", new=AsyncMock(return_value=cached_payload)),
        patch("app.services.nova.get_project_quota", return_value=compute_quota),
        patch("app.services.nova.project_flavor_visibility", return_value={"fl-cpu": True, "fl-gpu": True}),
        patch("app.services.gpu_quota.get_effective_gpu_quota_status", new=AsyncMock(return_value=gpu_status)),
    ):
        resp = await client.get("/api/v1/flavors?cache=true")

    assert resp.status_code == 200
    items = resp.json()
    assert [item["id"] for item in items] == ["fl-cpu", "fl-gpu"]
    by_id = {item["id"]: item for item in items}
    assert by_id["fl-gpu"]["extra_specs"] == {"pci_passthrough:alias": "RTX-3090:1"}
    assert by_id["fl-gpu"]["eligibility"]["selectable"] is True
    assert by_id["fl-gpu"]["eligibility"]["blockers"] == []
    # Cached payloads already carry extra_specs; no per-flavor Nova refetch is allowed.
    mock_conn.compute.get_flavor.assert_not_called()


@pytest.mark.asyncio
async def test_list_flavors_propagates_evaluator_failure_instead_of_hiding_gpu(mock_conn):
    """An evaluator crash must surface, never degrade into a silently GPU-free list."""
    from app.api.compute.flavors import list_flavors

    gpu = FlavorInfo(
        id="fl-gpu",
        name="gpu.3090_8c_32g",
        vcpus=8,
        ram=32768,
        disk=100,
        extra_specs={"pci_passthrough:alias": "RTX-3090:1"},
    )
    mock_conn._afterglow_project_id = "proj-123"

    async def _load_without_cache(_key, _ttl, loader, **_kwargs):
        return await loader()

    with (
        patch("app.api.compute.flavors.nova.list_flavors", return_value=[gpu]),
        patch("app.api.compute.flavors.cache.cached_call", new=_load_without_cache),
        patch(
            "app.services.flavor_eligibility.evaluate_project_flavors",
            new=AsyncMock(side_effect=RuntimeError("eligibility evaluation failed")),
        ),
        pytest.raises(RuntimeError, match="eligibility evaluation failed"),
    ):
        await list_flavors(conn=mock_conn, cm=CacheMode(enabled=False, refresh=False))


@pytest.mark.asyncio
async def test_cached_public_catalog_cannot_leak_now_private_flavor_without_native_access(client, mock_conn):
    from types import SimpleNamespace

    mock_conn._afterglow_project_id = "target-project"
    mock_conn._afterglow_is_system_admin = True
    mock_conn.compute.flavors.return_value = [SimpleNamespace(id="formerly-public", is_public=False)]
    mock_conn.compute.get_flavor_access.return_value = [{"tenant_id": "service-project"}]
    cached = FlavorInfo(id="formerly-public", name="private.gpu", vcpus=2, ram=4096, disk=0).model_dump()
    with patch("app.services.cache.cached_call", AsyncMock(return_value=[cached])):
        response = await client.get("/api/v1/flavors?cache=true")
    assert response.status_code == 200
    assert response.json() == []
    mock_conn.compute.get_flavor_access.assert_called_once_with("formerly-public")


@pytest.mark.parametrize("gpu", [False, True])
@pytest.mark.parametrize("granted", [False, True])
@pytest.mark.parametrize("public", [False, True])
def test_admin_catalog_uses_actual_target_native_access_not_service_project(mock_conn, granted, public, gpu):
    from types import SimpleNamespace

    from app.services import nova

    mock_conn._afterglow_project_id = "target-project"
    mock_conn._afterglow_is_system_admin = True
    mock_conn.compute.flavors.return_value = [
        SimpleNamespace(
            id="flavor",
            name="shape",
            vcpus=2,
            ram=4096,
            disk=0,
            is_public=public,
            extra_specs={"pci_passthrough:alias": "RTX3090:1"} if gpu else {},
        )
    ]
    mock_conn.compute.get_flavor_access.return_value = [
        {"tenant_id": "target-project" if granted else "service-project"}
    ]
    assert [flavor.id for flavor in nova.list_flavors(mock_conn)] == (["flavor"] if public or granted else [])
    if public:
        mock_conn.compute.get_flavor_access.assert_not_called()


def test_personal_member_token_for_system_human_keeps_native_visible_private_choices(mock_conn):
    from types import SimpleNamespace

    from app.services import nova

    mock_conn._afterglow_project_id = "personal-project"
    mock_conn._afterglow_is_system_admin = True
    mock_conn._afterglow_compute_admin = False
    mock_conn.compute.flavors.return_value = [
        SimpleNamespace(
            id="private",
            name="native-visible",
            vcpus=2,
            ram=4096,
            disk=0,
            is_public=False,
            extra_specs={"afterglow:frontend_visible": "true"},
        )
    ]
    mock_conn.compute.get_flavor_access.side_effect = RuntimeError("Member token cannot read administrative ACL")
    assert [row.id for row in nova.list_flavors(mock_conn)] == ["private"]


def test_private_catalog_acl_failure_cannot_fall_back_to_administrator_visibility(mock_conn):
    from types import SimpleNamespace

    from app.services import nova

    mock_conn._afterglow_project_id = "target"
    mock_conn._afterglow_compute_admin = True
    mock_conn.compute.flavors.return_value = [SimpleNamespace(id="private", is_public=False)]
    mock_conn.compute.get_flavor_access.side_effect = RuntimeError("native access unavailable")
    with pytest.raises(RuntimeError, match="native access unavailable"):
        nova.list_flavors(mock_conn)


def test_flavor_metadata_failure_cannot_turn_gpu_demand_into_cpu(mock_conn):
    from types import SimpleNamespace

    from app.services import nova

    mock_conn.compute.flavors.return_value = [SimpleNamespace(id="unknown", is_public=True, extra_specs={})]
    mock_conn.compute.fetch_flavor_extra_specs.side_effect = RuntimeError("native metadata unavailable")
    with pytest.raises(RuntimeError, match="native metadata unavailable"):
        nova.list_flavors(mock_conn)


def test_target_quota_failure_never_uses_administrator_service_project_limits(mock_conn):
    mock_conn._afterglow_authenticated_project_id = "service-project"
    mock_conn.session.get.side_effect = RuntimeError("quota unavailable")
    with pytest.raises(ValueError, match="target project usage is unavailable"):
        read_native_compute_quota(mock_conn, "target-project", strict=True)
    mock_conn.compute.get_limits.assert_not_called()


def test_strict_native_quota_preserves_reservations(mock_conn):
    quota = {key: {"limit": 8, "in_use": 2, "reserved": 3} for key in ("instances", "cores", "ram")}
    mock_conn.session.get.return_value.json.return_value = {"quota_set": quota}
    assert read_native_compute_quota(mock_conn, "target-project", strict=True) == quota


@pytest.mark.asyncio
@pytest.mark.parametrize("public", [False, True])
@pytest.mark.parametrize("gpu", [False, True])
@pytest.mark.parametrize("granted", [False, True])
@pytest.mark.parametrize("headroom", [False, True])
async def test_admin_target_catalog_native_access_and_uniform_quota_matrix(
    admin_client, mock_conn, public, gpu, granted, headroom
):
    from types import SimpleNamespace

    native = SimpleNamespace(
        id="matrix",
        name="shape",
        vcpus=2,
        ram=4096,
        disk=0,
        is_public=public,
        extra_specs={"pci_passthrough:alias": "RTX3090:1"} if gpu else {},
    )
    mock_conn._afterglow_project_id = "target-project"
    mock_conn._afterglow_authenticated_project_id = "service-project"
    mock_conn._afterglow_is_system_admin = True
    mock_conn.compute.flavors.return_value = [native]
    mock_conn.compute.fetch_flavor_extra_specs.return_value = native
    mock_conn.compute.get_flavor_access.return_value = [
        {"tenant_id": "target-project" if granted else "service-project"}
    ]
    quota = {key: {"limit": -1 if headroom else 0, "in_use": 0} for key in ("instances", "cores", "ram")}
    statuses = [{"gpu_type": "RTX3090", "limit": 1 if headroom else 0, "available": 1 if headroom else 0}]
    with (
        patch("app.api.identity.admin_instances._make_admin_conn", return_value=mock_conn),
        patch("app.services.nova.get_project_quota", return_value=quota) as read_quota,
        patch("app.services.gpu_quota.get_effective_gpu_quota_status", AsyncMock(return_value=statuses)) as read_gpu,
    ):
        response = await admin_client.get("/api/v1/admin/instances/flavors-for-project?project_id=target-project")
    assert response.status_code == 200
    rows = response.json()
    if not public and not granted:
        assert rows == []
        read_quota.assert_not_called()
        read_gpu.assert_not_awaited()
    else:
        assert [row["id"] for row in rows] == ["matrix"]
        assert rows[0]["eligibility"]["selectable"] is headroom
        read_quota.assert_called_once_with(mock_conn, "target-project", strict=True)
        if gpu:
            read_gpu.assert_awaited_once_with(mock_conn, "target-project")
    mock_conn.close.assert_called_once()
