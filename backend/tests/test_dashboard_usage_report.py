"""/api/v1/dashboard/usage-report quota, forecast and cache contracts."""

from datetime import UTC, date, datetime, timedelta
from unittest.mock import patch

import pytest

from app.api.common.dashboard import _allocation_series, _linear_forecast
from app.services import cinder, nova
from tests.conftest import patch_redis_cache_miss, patch_usage_report_deps

NOW = datetime.now(UTC)


def _server(instance_id: str, flavor: str, *, vcpus: int, memory_mb: int, hours: float, **extra) -> dict:
    return {
        "instance_id": instance_id,
        "name": f"vm-{instance_id}",
        "flavor": flavor,
        "vcpus": vcpus,
        "memory_mb": memory_mb,
        "local_gb": 20,
        "hours": hours,
        "state": "active",
        "started_at": (NOW - timedelta(days=60)).isoformat(),
        "ended_at": None,
        "uptime": int(hours * 3600),
        **extra,
    }


def _usage(*servers: dict) -> dict:
    return {
        "total_hours": sum(s["hours"] for s in servers),
        "total_vcpus_usage": sum(s["hours"] * s["vcpus"] for s in servers),
        "total_memory_mb_usage": sum(s["hours"] * s["memory_mb"] for s in servers),
        "total_local_gb_usage": 0.0,
        "server_usages": list(servers),
    }


COMPUTE_QUOTA = {
    "instances": {"in_use": 2, "limit": 10},
    "cores": {"in_use": 4, "limit": 20},
    "ram": {"in_use": 8192, "limit": 51200},
}
VOLUME_QUOTA = {"volumes": {"in_use": 3, "limit": 10}, "gigabytes": {"in_use": 100, "limit": 1000}}


@pytest.mark.asyncio
async def test_usage_report_forecast_structure(client, monkeypatch):
    patch_redis_cache_miss(monkeypatch)
    with patch_usage_report_deps(
        usage=_usage(_server("s1", "c2.medium", vcpus=4, memory_mb=8192, hours=100.0)),
        quota=COMPUTE_QUOTA,
        volume_quota=VOLUME_QUOTA,
    ):
        resp = await client.get("/api/v1/dashboard/usage-report?range=30d")

    assert resp.status_code == 200
    forecast = resp.json()["forecast"]
    assert (forecast["window_days"], forecast["horizon_days"]) == (7, 30)
    assert set(forecast) >= {"vcpus", "ram_mb", "volume_gb", "gpu"}
    for key in ("vcpus", "ram_mb", "volume_gb"):
        assert 0 <= forecast[key]["current_pct"] <= 100
    assert forecast["vcpus"]["current_pct"] == 20.0
    assert forecast["ram_mb"]["current_pct"] == 16.0
    assert forecast["volume_gb"]["current_pct"] == 10.0
    assert len(forecast["vcpus"]["series"]) == 30
    assert forecast["vcpus"]["trend_available"] is True
    assert forecast["vcpus"]["slope_per_day"] == 0.0
    # Cinder has no allocation history: current use only.
    assert forecast["volume_gb"]["trend_available"] is False
    assert forecast["volume_gb"]["series"] == []
    assert forecast["gpu"] == {}


@pytest.mark.asyncio
async def test_usage_report_unlimited_and_zero_limits_have_no_percentage(client, monkeypatch):
    patch_redis_cache_miss(monkeypatch)
    with patch_usage_report_deps(
        usage=_usage(_server("s1", "c2.medium", vcpus=2, memory_mb=4096, hours=10.0)),
        quota={"cores": {"in_use": 6, "limit": -1}, "ram": {"in_use": 4096, "limit": 0}},
        volume_quota=VOLUME_QUOTA,
    ):
        resp = await client.get("/api/v1/dashboard/usage-report")

    assert resp.status_code == 200
    forecast = resp.json()["forecast"]
    for key in ("vcpus", "ram_mb"):
        assert forecast[key]["current_pct"] is None
        assert forecast[key]["projected_pct"] is None
        assert forecast[key]["days_to_limit"] is None
    assert resp.json()["quota"]["vcpus"] == {"in_use": 6, "limit": -1}


@pytest.mark.asyncio
async def test_usage_report_quota_block(client, monkeypatch):
    patch_redis_cache_miss(monkeypatch)
    with patch_usage_report_deps(quota=COMPUTE_QUOTA, volume_quota=VOLUME_QUOTA):
        resp = await client.get("/api/v1/dashboard/usage-report")

    assert resp.status_code == 200
    quota = resp.json()["quota"]
    assert set(quota) == {
        "compute_available",
        "storage_available",
        "instances",
        "vcpus",
        "ram_mb",
        "volume_gb",
        "volumes",
        "gpu",
        "gpu_available",
    }
    assert quota["compute_available"] is True
    assert quota["storage_available"] is True
    assert quota["instances"] == {"in_use": 2, "limit": 10}
    assert quota["ram_mb"] == {"in_use": 8192, "limit": 51200}
    assert quota["volume_gb"] == {"in_use": 100, "limit": 1000}
    assert quota["volumes"] == {"in_use": 3, "limit": 10}


@pytest.mark.asyncio
async def test_usage_report_gpu_flavor_hours_and_type_forecast(client, monkeypatch):
    patch_redis_cache_miss(monkeypatch)
    flavors = [
        {
            "id": "g1",
            "name": "gpu.8c_64g_a10",
            "vcpus": 8,
            "ram": 65536,
            "extra_specs": {"pci_passthrough:alias": "a10:1"},
        }
    ]
    with patch_usage_report_deps(
        usage=_usage(
            _server("s1", "gpu.8c_64g_a10", vcpus=8, memory_mb=65536, hours=48.0),
            _server("s2", "c2.medium", vcpus=2, memory_mb=4096, hours=10.0),
        ),
        quota=COMPUTE_QUOTA,
        volume_quota=VOLUME_QUOTA,
        flavors=flavors,
        gpu=[
            {"project_id": "p", "gpu_type": "A10", "limit": 2, "in_use": 1, "available": 1},
            {"project_id": "p", "gpu_type": "H100", "limit": 0, "in_use": 0, "available": 0},
        ],
    ):
        resp = await client.get("/api/v1/dashboard/usage-report?range=7d")

    assert resp.status_code == 200
    data = resp.json()
    by_flavor = {f["flavor"]: f for f in data["flavor_hours"]}
    assert by_flavor["gpu.8c_64g_a10"]["gpu_count"] == 1
    assert by_flavor["gpu.8c_64g_a10"]["gpu_hours"] == 48.0
    assert by_flavor["gpu.8c_64g_a10"]["vcpu_hours"] == 384.0
    assert by_flavor["c2.medium"]["gpu_count"] == 0
    assert data["stats"]["gpu_hours"] == 48.0
    # Types with no limit and no use are hidden from the forecast panel.
    assert data["quota"]["gpu"] == [{"gpu_type": "A10", "in_use": 1, "limit": 2}]
    assert data["forecast"]["gpu"]["A10"]["series"] == [1.0] * 7
    assert data["forecast"]["gpu"]["A10"]["current_pct"] == 50.0
    assert [row["instance_id"] for row in data["instance_usage"]] == ["s1", "s2"]


@pytest.mark.asyncio
async def test_usage_report_gpu_failure_is_explicit(client, monkeypatch):
    patch_redis_cache_miss(monkeypatch)
    with patch_usage_report_deps(quota=COMPUTE_QUOTA, volume_quota=VOLUME_QUOTA, gpu=RuntimeError("db down")):
        resp = await client.get("/api/v1/dashboard/usage-report")

    assert resp.status_code == 200
    data = resp.json()
    assert data["quota"]["gpu_available"] is False
    assert data["quota"]["gpu"] == []
    assert data["forecast"]["gpu"] == {}


@pytest.mark.asyncio
async def test_usage_report_compute_quota_failure_is_not_unlimited(client, monkeypatch):
    patch_redis_cache_miss(monkeypatch)
    with patch_usage_report_deps(quota=RuntimeError("nova down"), volume_quota=VOLUME_QUOTA):
        resp = await client.get("/api/v1/dashboard/usage-report")

    assert resp.status_code == 200
    data = resp.json()
    assert data["quota"]["compute_available"] is False
    assert data["quota"]["vcpus"] == {"in_use": 0, "limit": 0}
    assert data["forecast"]["vcpus"]["current_pct"] is None
    assert data["quota"]["storage_available"] is True


@pytest.mark.asyncio
async def test_usage_report_block_storage_quota_failure(client, monkeypatch):
    patch_redis_cache_miss(monkeypatch)
    with patch_usage_report_deps(quota=COMPUTE_QUOTA, volume_quota=RuntimeError("cinder down")):
        resp = await client.get("/api/v1/dashboard/usage-report")

    assert resp.status_code == 200
    data = resp.json()
    assert data["quota"]["storage_available"] is False
    assert data["quota"]["volume_gb"] == {"in_use": 0, "limit": 0}
    assert data["quota"]["compute_available"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("service", ["nova", "cinder"])
@pytest.mark.parametrize("malformed", ["empty", "missing_usage"])
async def test_usage_report_rejects_incomplete_raw_quota(client, mock_conn, monkeypatch, service, malformed):
    patch_redis_cache_miss(monkeypatch)
    is_compute = service == "nova"
    quota = COMPUTE_QUOTA if is_compute else VOLUME_QUOTA
    raw = {key: dict(value) for key, value in quota.items()}
    if malformed == "empty":
        raw = {}
    else:
        del raw["cores" if is_compute else "gigabytes"]["in_use"]
    mock_conn.session.get.return_value.json.return_value = {"quota_set": raw}
    adapter = nova.get_project_quota if is_compute else cinder.get_volume_quota
    method = "get_project_quota" if is_compute else "get_volume_quota"
    with patch_usage_report_deps(quota=COMPUTE_QUOTA, volume_quota=VOLUME_QUOTA):
        with patch(f"app.api.common.dashboard.{service}.{method}", new=adapter):
            response = await client.get("/api/v1/dashboard/usage-report")

    assert response.status_code == 200
    data = response.json()
    availability = "compute_available" if is_compute else "storage_available"
    unaffected = "storage_available" if is_compute else "compute_available"
    resource = "vcpus" if is_compute else "volume_gb"
    assert data["quota"][availability] is False
    assert data["quota"][unaffected] is True
    assert data["quota"][resource] == {"in_use": 0, "limit": 0}
    assert data["forecast"][resource]["current_pct"] is None


@pytest.mark.asyncio
async def test_usage_report_90d_range_queries_ninety_days(client, monkeypatch):
    patch_redis_cache_miss(monkeypatch)
    with patch_usage_report_deps(quota=COMPUTE_QUOTA, volume_quota=VOLUME_QUOTA):
        resp = await client.get("/api/v1/dashboard/usage-report?range=90d")

    assert resp.status_code == 200
    data = resp.json()
    assert date.fromisoformat(data["end"]) - date.fromisoformat(data["start"]) == timedelta(days=90)
    assert len(data["forecast"]["vcpus"]["series"]) == 90


# ---------------------------------------------------------------------------
# Cache-Control 헤더 (요청 폭주 방지)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_usage_report_cache_control_header(client, monkeypatch):
    """응답에 Cache-Control: private, max-age=60 헤더 포함 — 클라이언트 캐시 유도."""
    patch_redis_cache_miss(monkeypatch)
    with patch_usage_report_deps():
        resp = await client.get("/api/v1/dashboard/usage-report")

    assert resp.status_code == 200
    cc = resp.headers.get("cache-control", "")
    assert "private" in cc
    assert "max-age=60" in cc


@pytest.mark.asyncio
async def test_usage_report_cache_control_present_on_different_ranges(client, monkeypatch):
    """range 파라미터 무관하게 Cache-Control 헤더 항상 포함."""
    patch_redis_cache_miss(monkeypatch)
    with patch_usage_report_deps():
        for range_val in ("7d", "30d", "90d"):
            resp = await client.get(f"/api/v1/dashboard/usage-report?range={range_val}")
            assert resp.status_code == 200
            assert "max-age=60" in resp.headers.get("cache-control", ""), f"range={range_val} missing Cache-Control"


# ---------------------------------------------------------------------------
# Forecast helpers
# ---------------------------------------------------------------------------


def test_allocation_series_counts_rows_alive_at_each_sample():
    base = datetime(2026, 9, 1, tzinfo=UTC)
    samples = [base + timedelta(days=i) for i in range(5)]
    rows = [
        {"started": base - timedelta(days=3), "ended": None, "weight": 2},
        {"started": base - timedelta(days=1), "ended": base + timedelta(days=2, hours=1), "weight": 4},
        {"started": None, "ended": None, "weight": 100},
    ]

    assert _allocation_series(rows, samples, lambda row: row["weight"]) == [6.0, 6.0, 6.0, 2.0, 2.0]


def test_linear_forecast_projects_growth_and_days_to_limit():
    forecast = _linear_forecast([10, 10, 12, 12, 14, 14, 16], in_use=16, limit=32, has_rows=True)

    assert forecast["current_pct"] == 50.0
    assert forecast["slope_per_day"] == 1.0
    assert forecast["projected_pct"] == 100.0
    assert forecast["days_to_limit"] == 16
    assert forecast["trend_available"] is True


def test_linear_forecast_uses_only_recent_window():
    # An old spike outside the seven-day window must not flatten the recent growth.
    forecast = _linear_forecast([50, 50, 0, 1, 2, 3, 4, 5, 6], in_use=6, limit=100, has_rows=True)

    assert forecast["slope_per_day"] == 1.0
    assert forecast["days_to_limit"] == 94


def test_linear_forecast_flat_series_never_reaches_limit():
    forecast = _linear_forecast([8] * 7, in_use=8, limit=16, has_rows=True)

    assert forecast["slope_per_day"] == 0.0
    assert forecast["projected_pct"] == 50.0
    assert forecast["days_to_limit"] is None


def test_linear_forecast_at_or_over_limit_is_zero_days():
    assert _linear_forecast([16] * 7, in_use=16, limit=16, has_rows=True)["days_to_limit"] == 0


def test_linear_forecast_without_rows_has_no_trend():
    forecast = _linear_forecast([0.0] * 7, in_use=4, limit=20, has_rows=False)

    assert forecast["trend_available"] is False
    assert forecast["slope_per_day"] is None
    assert forecast["projected_pct"] is None
    assert forecast["days_to_limit"] is None
    assert forecast["current_pct"] == 20.0
