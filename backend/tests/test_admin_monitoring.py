"""Admin /monitoring/summary 통합 모니터링 단위 테스트.

Drover 카운트 버그(0 하드코딩) 수정 + 누락 리소스(스냅샷/백업/LB/SG/서브넷/이미지/DB/Identity) 통합.
"""

from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import patch_redis_cache_miss


def _setup_conn() -> MagicMock:
    """기본 mock conn — 모든 SDK 이터레이터가 빈 결과 반환."""
    conn = MagicMock()
    conn.compute.get_endpoint.return_value = "https://nova"
    conn.block_storage.get_endpoint.return_value = "https://cinder"
    conn.session.get.return_value.json.return_value = {"volumes": []}
    conn.network.networks.return_value = []
    conn.network.routers.return_value = []
    conn.network.ips.return_value = []
    conn.network.ports.return_value = []
    conn.network.subnets.return_value = []
    conn.network.security_groups.return_value = []
    conn.image.images.return_value = []
    conn.block_storage.snapshots.return_value = []
    conn.block_storage.backups.return_value = []
    conn.load_balancer.load_balancers.return_value = []
    return conn


def _drover(clusters: list[dict]) -> MagicMock:
    proxy = MagicMock()
    proxy.admin_clusters.return_value = clusters
    return proxy


@pytest.mark.asyncio
async def test_monitoring_summary_includes_k3s_active(admin_client, monkeypatch):
    """k3s 클러스터 mock 1대 ACTIVE → k3s_count == 1, k3s_active == 1 (Drover 버그 수정)."""
    patch_redis_cache_miss(monkeypatch)
    conn = _setup_conn()
    cluster = {"id": "c1", "name": "dms-cloud", "status": "ACTIVE"}
    with (
        patch("app.api.identity.admin.get_os_conn", return_value=conn),
        patch("app.api.identity.admin.get_drover_proxy", return_value=_drover([cluster])),
        patch("app.api.identity.admin._fetch_hypervisors_raw", return_value=[]),
        patch(
            "app.api.identity.admin._fetch_overview_servers",
            return_value={"instance_stats": {}, "gpu_instances": 0},
        ),
        patch("app.api.identity.admin._fetch_overview_containers", return_value=0),
        patch("app.api.identity.admin._fetch_overview_file_storage", return_value=0),
        patch("app.api.identity.admin._count_database_instances_admin", return_value=0),
        patch("app.api.identity.admin._count_identity_users_projects", return_value=(0, 0)),
    ):
        # admin_client는 의존성 오버라이드로 conn을 주입하므로, 위 patch는 직접 호출되는 함수만 감싼다.
        from app.api.deps import get_os_conn
        from app.main import app

        async def override():
            yield conn

        app.dependency_overrides[get_os_conn] = override
        try:
            resp = await admin_client.get("/api/v1/admin/monitoring/summary")
        finally:
            app.dependency_overrides.pop(get_os_conn, None)

    assert resp.status_code == 200
    body = resp.json()
    assert body["containers"]["k3s_count"] == 1
    assert body["containers"]["k3s_active"] == 1
    assert body["containers"]["k3s_available"] is True


@pytest.mark.asyncio
async def test_monitoring_summary_k3s_zero_when_empty(admin_client, monkeypatch):
    """k3s 클러스터 0대 → k3s_count == 0, k3s_active == 0."""
    patch_redis_cache_miss(monkeypatch)
    conn = _setup_conn()
    with (
        patch("app.api.identity.admin.get_drover_proxy", return_value=_drover([])),
        patch("app.api.identity.admin._fetch_hypervisors_raw", return_value=[]),
        patch(
            "app.api.identity.admin._fetch_overview_servers",
            return_value={"instance_stats": {}, "gpu_instances": 0},
        ),
        patch("app.api.identity.admin._fetch_overview_containers", return_value=0),
        patch("app.api.identity.admin._fetch_overview_file_storage", return_value=0),
        patch("app.api.identity.admin._count_database_instances_admin", return_value=0),
        patch("app.api.identity.admin._count_identity_users_projects", return_value=(0, 0)),
    ):
        from app.api.deps import get_os_conn
        from app.main import app

        async def override():
            yield conn

        app.dependency_overrides[get_os_conn] = override
        try:
            resp = await admin_client.get("/api/v1/admin/monitoring/summary")
        finally:
            app.dependency_overrides.pop(get_os_conn, None)
    assert resp.status_code == 200
    body = resp.json()
    assert body["containers"]["k3s_count"] == 0
    assert body["containers"]["k3s_active"] == 0


@pytest.mark.asyncio
async def test_monitoring_summary_marks_drover_unavailable(admin_client, monkeypatch):
    patch_redis_cache_miss(monkeypatch)
    conn = _setup_conn()
    with (
        patch("app.api.identity.admin.get_drover_proxy", side_effect=RuntimeError("catalog unavailable")),
        patch("app.api.identity.admin._fetch_hypervisors_raw", return_value=[]),
        patch(
            "app.api.identity.admin._fetch_overview_servers",
            return_value={"instance_stats": {}, "gpu_instances": 0},
        ),
        patch("app.api.identity.admin._fetch_overview_containers", return_value=0),
        patch("app.api.identity.admin._fetch_overview_file_storage", return_value=0),
        patch("app.api.identity.admin._count_database_instances_admin", return_value=0),
        patch("app.api.identity.admin._count_identity_users_projects", return_value=(0, 0)),
    ):
        from app.api.deps import get_os_conn
        from app.main import app

        async def override():
            yield conn

        app.dependency_overrides[get_os_conn] = override
        try:
            resp = await admin_client.get("/api/v1/admin/monitoring/summary")
        finally:
            app.dependency_overrides.pop(get_os_conn, None)

    assert resp.status_code == 200
    assert resp.json()["containers"] == {
        "zun_count": 0,
        "k3s_count": 0,
        "k3s_active": 0,
        "k3s_available": False,
    }


@pytest.mark.asyncio
async def test_monitoring_summary_includes_new_groups(admin_client, monkeypatch):
    """응답에 신규 그룹 data_services / identity 키가 존재."""
    patch_redis_cache_miss(monkeypatch)
    conn = _setup_conn()
    with (
        patch("app.api.identity.admin.get_drover_proxy", return_value=_drover([])),
        patch("app.api.identity.admin._fetch_hypervisors_raw", return_value=[]),
        patch(
            "app.api.identity.admin._fetch_overview_servers",
            return_value={"instance_stats": {}, "gpu_instances": 0},
        ),
        patch("app.api.identity.admin._fetch_overview_containers", return_value=0),
        patch("app.api.identity.admin._fetch_overview_file_storage", return_value=0),
        patch("app.api.identity.admin._count_database_instances_admin", return_value=3),
        patch("app.api.identity.admin._count_identity_users_projects", return_value=(7, 2)),
    ):
        from app.api.deps import get_os_conn
        from app.main import app

        async def override():
            yield conn

        app.dependency_overrides[get_os_conn] = override
        try:
            resp = await admin_client.get("/api/v1/admin/monitoring/summary")
        finally:
            app.dependency_overrides.pop(get_os_conn, None)
    assert resp.status_code == 200
    body = resp.json()
    assert "data_services" in body
    assert body["data_services"]["database_instance_count"] == 3
    assert "identity" in body
    assert body["identity"]["user_count"] == 7
    assert body["identity"]["project_count"] == 2

    # 누락 리소스 카운터들이 응답에 포함되는지 (값은 0이어도 키는 있어야 함)
    assert "volume_snapshot_count" in body["storage"]
    assert "volume_backup_count" in body["storage"]
    assert "share_snapshot_count" in body["storage"]
    assert "image_count" in body["storage"]
    assert "subnet_count" in body["network"]
    assert "security_group_count" in body["network"]
    assert "load_balancer_count" in body["network"]
    assert "load_balancer_active" in body["network"]


@pytest.mark.asyncio
async def test_monitoring_summary_handles_per_resource_failure(admin_client, monkeypatch):
    """각 카운터 함수가 예외를 던져도 다른 카운터는 정상 — 0 fallback."""
    patch_redis_cache_miss(monkeypatch)
    conn = _setup_conn()
    # network.subnets만 예외, 나머지는 정상
    conn.network.subnets.side_effect = RuntimeError("subnet API down")
    with (
        patch(
            "app.api.identity.admin.get_drover_proxy",
            return_value=_drover([{"status": "ACTIVE"}, {"status": "CREATING"}]),
        ),
        patch("app.api.identity.admin._fetch_hypervisors_raw", return_value=[]),
        patch(
            "app.api.identity.admin._fetch_overview_servers",
            return_value={"instance_stats": {}, "gpu_instances": 0},
        ),
        patch("app.api.identity.admin._fetch_overview_containers", return_value=0),
        patch("app.api.identity.admin._fetch_overview_file_storage", return_value=0),
        patch("app.api.identity.admin._count_database_instances_admin", return_value=0),
        patch("app.api.identity.admin._count_identity_users_projects", return_value=(0, 0)),
    ):
        from app.api.deps import get_os_conn
        from app.main import app

        async def override():
            yield conn

        app.dependency_overrides[get_os_conn] = override
        try:
            resp = await admin_client.get("/api/v1/admin/monitoring/summary")
        finally:
            app.dependency_overrides.pop(get_os_conn, None)
    assert resp.status_code == 200
    body = resp.json()
    assert body["network"]["subnet_count"] == 0  # fallback
    assert body["containers"]["k3s_count"] == 2  # 다른 카운터는 정상
    assert body["containers"]["k3s_active"] == 1


@pytest.mark.asyncio
async def test_monitoring_summary_async_collect_works_with_cached_call(monkeypatch):
    """_collect가 async로 변환된 후에도 cached_call이 정상 동작하는지 (간접 — iscoroutinefunction 분기)."""
    from app.services.cache import cached_call

    async def my_collect():
        return {"ok": True}

    patch_redis_cache_miss(monkeypatch)
    result = await cached_call("test:key", 60, my_collect)
    assert result == {"ok": True}
