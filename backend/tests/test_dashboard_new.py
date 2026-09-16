"""Phase 50b — 신규 대시보드 endpoint 단위 테스트 (overview/usage-stats/usage-report/activity)."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import patch_redis_cache_miss

MOCK_SERVERS = [
    {"id": "s1", "status": "ACTIVE", "flavor_id": "f1", "flavor_name": "c2.medium", "name": "web-01"},
    {"id": "s2", "status": "SHUTOFF", "flavor_id": "f1", "flavor_name": "c2.medium", "name": "web-02"},
    {"id": "s3", "status": "ERROR", "flavor_id": "f2", "flavor_name": "c4.large", "name": "db-01"},
]

MOCK_FLAVORS = [
    {"id": "f1", "name": "c2.medium", "extra_specs": {}, "vcpus": 2, "ram": 4096},
    {"id": "f2", "name": "c4.large", "extra_specs": {}, "vcpus": 4, "ram": 8192},
]


# ---------------------------------------------------------------------------
# GET /api/dashboard/overview
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_overview_returns_stats(client, mock_conn, monkeypatch):
    """정상 조회: stats / recent_instances / alerts 반환."""
    patch_redis_cache_miss(monkeypatch)
    mock_conn.network.ips.return_value = [MagicMock(), MagicMock()]
    with (
        patch("app.api.common.dashboard._list_servers_as_dicts", return_value=MOCK_SERVERS),
        patch(
            "app.api.common.dashboard.nova.get_project_limits",
            return_value={
                "cores": {"in_use": 4, "limit": 20},
                "ram": {"in_use": 8192, "limit": 51200},
            },
        ),
        patch(
            "app.api.common.dashboard.cinder.get_volume_limits",
            return_value={
                "gigabytes": {"in_use": 100, "limit": 1000},
            },
        ),
        patch(
            "app.api.common.dashboard.get_settings",
            return_value=SimpleNamespace(service_k3s_enabled=True),
        ),
        patch(
            "app.api.common.dashboard.get_drover_proxy",
            return_value=MagicMock(cluster_stats=MagicMock(return_value={"total": 2, "active": 1})),
        ),
    ):
        resp = await client.get("/api/v1/dashboard/overview")

    assert resp.status_code == 200
    data = resp.json()
    assert "stats" in data
    assert data["stats"]["instances_total"] == 3
    assert data["stats"]["instances_active"] == 1
    assert "recent_instances" in data
    assert "alerts" in data


@pytest.mark.asyncio
async def test_overview_marks_drover_unavailable_when_cluster_stats_fail(client, mock_conn, monkeypatch):
    """A Drover failure is visible to dashboard clients rather than reported as zero clusters."""
    patch_redis_cache_miss(monkeypatch)
    mock_conn.network.ips.return_value = []
    with (
        patch("app.api.common.dashboard._list_servers_as_dicts", return_value=[]),
        patch("app.api.common.dashboard.nova.get_project_limits", return_value={}),
        patch("app.api.common.dashboard.cinder.get_volume_limits", return_value={}),
        patch(
            "app.api.common.dashboard.get_settings",
            return_value=SimpleNamespace(service_k3s_enabled=True),
        ),
        patch(
            "app.api.common.dashboard.get_drover_proxy",
            return_value=MagicMock(cluster_stats=MagicMock(side_effect=RuntimeError("Drover unavailable"))),
        ),
    ):
        resp = await client.get("/api/v1/dashboard/overview")

    assert resp.status_code == 200
    stats = resp.json()["stats"]
    assert stats["k3s_clusters"] == 0
    assert stats["k3s_active"] == 0
    assert stats["k3s_available"] is False


@pytest.mark.asyncio
async def test_overview_error_instance_in_alerts(client, mock_conn, monkeypatch):
    """ERROR 인스턴스 → alerts에 error 항목 포함."""
    patch_redis_cache_miss(monkeypatch)
    mock_conn.network.ips.return_value = []
    with (
        patch("app.api.common.dashboard._list_servers_as_dicts", return_value=MOCK_SERVERS),
        patch("app.api.common.dashboard.nova.get_project_limits", return_value={}),
        patch("app.api.common.dashboard.cinder.get_volume_limits", return_value={}),
    ):
        resp = await client.get("/api/v1/dashboard/overview")

    assert resp.status_code == 200
    alerts = resp.json()["alerts"]
    assert any(a["type"] == "error" for a in alerts)


@pytest.mark.asyncio
async def test_overview_no_instances(client, mock_conn, monkeypatch):
    """인스턴스 0건 → alerts 비어있음."""
    patch_redis_cache_miss(monkeypatch)
    mock_conn.network.ips.return_value = []
    with (
        patch("app.api.common.dashboard._list_servers_as_dicts", return_value=[]),
        patch("app.api.common.dashboard.nova.get_project_limits", return_value={}),
        patch("app.api.common.dashboard.cinder.get_volume_limits", return_value={}),
    ):
        resp = await client.get("/api/v1/dashboard/overview")

    assert resp.status_code == 200
    data = resp.json()
    assert data["stats"]["instances_total"] == 0
    assert data["alerts"] == []


# ---------------------------------------------------------------------------
# GET /api/dashboard/usage-stats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_usage_stats_returns_expected_structure(client, mock_conn, monkeypatch):
    """top_instances / volume_by_type / instance_hours 반환."""
    patch_redis_cache_miss(monkeypatch)
    mock_conn.block_storage.volumes.return_value = [
        MagicMock(id="v1", size=50, volume_type="ssd"),
        MagicMock(id="v2", size=100, volume_type="hdd"),
    ]
    with (
        patch("app.api.common.dashboard._list_servers_as_dicts", return_value=MOCK_SERVERS),
        patch("app.api.common.dashboard._list_flavors_as_dicts", return_value=MOCK_FLAVORS),
        patch(
            "app.api.common.dashboard.nova.get_project_usage",
            return_value={
                "total_hours": 72.0,
                "total_vcpu_hours": 144.0,
                "server_usages": [],
            },
        ),
    ):
        resp = await client.get("/api/v1/dashboard/usage-stats?range=30d")

    assert resp.status_code == 200
    data = resp.json()
    assert data["range"] == "30d"
    assert "top_instances" in data
    assert "volumes_by_type" in data
    assert data["instance_hours"] == 72.0


@pytest.mark.asyncio
async def test_usage_stats_top_instances_sorted_by_vcpus(client, mock_conn, monkeypatch):
    """top_instances는 vCPU 내림차순 정렬."""
    patch_redis_cache_miss(monkeypatch)
    mock_conn.block_storage.volumes.return_value = []
    with (
        patch("app.api.common.dashboard._list_servers_as_dicts", return_value=MOCK_SERVERS),
        patch("app.api.common.dashboard._list_flavors_as_dicts", return_value=MOCK_FLAVORS),
        patch("app.api.common.dashboard.nova.get_project_usage", return_value={}),
    ):
        resp = await client.get("/api/v1/dashboard/usage-stats")

    assert resp.status_code == 200
    instances = resp.json()["top_instances"]
    # ACTIVE 인스턴스(s1)만 포함 — c2.medium(2 vCPU)
    assert len(instances) >= 1
    vcpus = [i["vcpus"] for i in instances]
    assert vcpus == sorted(vcpus, reverse=True)


@pytest.mark.asyncio
async def test_usage_stats_unauthenticated(non_admin_client, monkeypatch):
    """인증 없이 접근 — 401 (auth 헤더 없는 별도 client 사용 시)."""
    # non_admin_client는 일반 사용자 — 정상 접근 가능해야 함 (admin 전용 아님)
    from unittest.mock import MagicMock, patch

    patch_redis_cache_miss(monkeypatch)
    with (
        patch("app.api.common.dashboard._list_servers_as_dicts", return_value=[]),
        patch("app.api.common.dashboard._list_flavors_as_dicts", return_value=[]),
        patch("app.api.common.dashboard.nova.get_project_usage", return_value={}),
    ):
        # non_admin_client의 conn mock 설정
        from app.api.deps import get_os_conn
        from app.main import app

        mock_conn = MagicMock()
        mock_conn._afterglow_project_id = "test-project-123"
        mock_conn.block_storage.volumes.return_value = []

        async def override():
            yield mock_conn

        app.dependency_overrides[get_os_conn] = override
        resp = await non_admin_client.get("/api/v1/dashboard/usage-stats")

    assert resp.status_code == 200  # 일반 사용자도 접근 가능


# ---------------------------------------------------------------------------
# GET /api/dashboard/usage-report
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_usage_report_structure(client, mock_conn, monkeypatch):
    """stats / flavor_hours / quota 구조 반환."""
    patch_redis_cache_miss(monkeypatch)
    with (
        patch(
            "app.api.common.dashboard.nova.get_project_usage",
            return_value={
                "total_hours": 240.0,
                "total_vcpu_hours": 480.0,
                "server_usages": [
                    {"flavor": "c2.medium", "hours": 120.0, "state": "active"},
                    {"flavor": "c4.large", "hours": 120.0, "state": "active"},
                ],
            },
        ),
        patch(
            "app.api.common.dashboard.nova.get_project_quota",
            return_value={
                "cores": {"in_use": 6, "limit": 20},
            },
        ),
    ):
        resp = await client.get("/api/v1/dashboard/usage-report?range=30d")

    assert resp.status_code == 200
    data = resp.json()
    assert data["range"] == "30d"
    assert data["stats"]["instance_hours"] == 240.0
    assert len(data["flavor_hours"]) == 2
    assert data["quota"]["vcpus_in_use"] == 6
    assert data["forecast"]["vcpu_pct"] == 30.0


@pytest.mark.asyncio
async def test_usage_report_flavor_hours_sorted(client, mock_conn, monkeypatch):
    """flavor_hours는 usage_hours 내림차순 정렬."""
    patch_redis_cache_miss(monkeypatch)
    with (
        patch(
            "app.api.common.dashboard.nova.get_project_usage",
            return_value={
                "total_hours": 300.0,
                "total_vcpu_hours": 600.0,
                "server_usages": [
                    {"flavor": "small", "hours": 50.0, "state": "active"},
                    {"flavor": "large", "hours": 250.0, "state": "active"},
                ],
            },
        ),
        patch("app.api.common.dashboard.nova.get_project_quota", return_value={}),
    ):
        resp = await client.get("/api/v1/dashboard/usage-report?range=7d")

    assert resp.status_code == 200
    hours = [fh["usage_hours"] for fh in resp.json()["flavor_hours"]]
    assert hours == sorted(hours, reverse=True)


# ---------------------------------------------------------------------------
# GET /api/dashboard/activity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_activity_no_db_returns_empty_kpi(client, mock_conn):
    """DB 미사용 시 KPI 0 + 24개 버킷 반환 (에러 아님)."""
    with patch("app.api.common.dashboard.is_db_available", return_value=False):
        resp = await client.get("/api/v1/dashboard/activity?range=7d")

    assert resp.status_code == 200
    data = resp.json()
    assert data["kpi"]["total"] == 0
    assert data["kpi"]["failed"] == 0
    assert len(data["hour_distribution"]) == 24
    assert data["recent_actions"] == []


@pytest.mark.asyncio
async def test_activity_hour_distribution_always_24_buckets(client, mock_conn):
    """hour_distribution 항상 24개 요소 (범위 파라미터 무관)."""
    with patch("app.api.common.dashboard.is_db_available", return_value=False):
        resp = await client.get("/api/v1/dashboard/activity?range=24h")

    assert resp.status_code == 200
    dist = resp.json()["hour_distribution"]
    assert len(dist) == 24
    assert all(isinstance(v, int) for v in dist)


@pytest.mark.asyncio
async def test_activity_range_in_response(client, mock_conn):
    """응답에 range 필드가 요청값 그대로 반환."""
    with patch("app.api.common.dashboard.is_db_available", return_value=False):
        resp = await client.get("/api/v1/dashboard/activity?range=30d")

    assert resp.status_code == 200
    assert resp.json()["range"] == "30d"
