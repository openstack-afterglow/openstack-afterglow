"""Project monitoring selection, measurement semantics and caller-bound native data."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_trend_prometheus_unavailable_returns_empty(client, mock_conn):
    """No native telemetry and offline Prometheus must not fabricate measurements."""
    from app.services.prom_query import PromUnavailable

    with patch("app.api.common.dashboard.prom_query.query_range", new_callable=AsyncMock) as mock_qr:
        mock_qr.side_effect = PromUnavailable("연결 실패")
        resp = await client.get("/api/v1/dashboard/metrics/trend")

    assert resp.status_code == 200
    data = resp.json()
    assert data["monitoring_available"] is False
    assert data["vcpu"]["data"] == []
    assert data["vcpu"]["available"] is False


@pytest.mark.asyncio
async def test_trend_partial_failure_returns_available_series(client, mock_conn):
    """일부 쿼리만 성공 시 성공한 시계열만 data 포함."""
    from app.services.prom_query import PromUnavailable

    fake_vcpu = [{"ts": 1000, "value": 10.0}]

    call_count = 0

    async def _side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return fake_vcpu
        raise PromUnavailable("no data")

    with patch("app.api.common.dashboard.prom_query.query_range", side_effect=_side_effect):
        resp = await client.get("/api/v1/dashboard/metrics/trend")

    assert resp.status_code == 200
    data = resp.json()
    assert data["vcpu"]["available"] is True
    assert data["memory"]["available"] is False
    assert data["monitoring_available"] is True


def _native_metric(values, unit="%"):
    return {
        "series": [{"ts": 100 + index * 60, "value": value} for index, value in enumerate(values)],
        "source": "gnocchi",
        "status": "available",
        "error": None,
        "unit": unit,
    }


def _native_project():
    return {
        "source": "gnocchi",
        "status": "available",
        "error": None,
        "truncated": False,
        "instances": {
            "small": {
                "cpu": _native_metric([20, 0]),
                "vcpus": _native_metric([1, 1], "vcpu"),
                "memory": _native_metric([20, 0]),
                "network_rx": _native_metric([1024, 0], "B/s"),
                "network_tx": _native_metric([1024, 0], "B/s"),
            },
            "large": {
                "cpu": _native_metric([80, 0]),
                "vcpus": _native_metric([3, 3], "vcpu"),
                "memory": _native_metric([40, 0]),
                "network_rx": _native_metric([2048, 0], "B/s"),
                "network_tx": _native_metric([4096, 0], "B/s"),
            },
        },
    }


@pytest.mark.asyncio
async def test_native_project_cpu_is_weighted_and_storage_keeps_guest_filesystem_semantics(client):
    with (
        patch("app.api.common.dashboard.native_telemetry.project_series", AsyncMock(return_value=_native_project())),
        patch("app.api.common.dashboard.prom_query.query_range", AsyncMock(return_value=[{"ts": 100, "value": 71}])),
    ):
        response = await client.get("/api/v1/dashboard/metrics/trend?range=24h")
    assert response.status_code == 200
    body = response.json()
    assert body["vcpu"]["data"] == [65, 0]
    assert body["memory"]["data"] == [30, 0]
    assert body["network"]["data"] == [8, 0]
    assert body["network"]["unit"] == "KiB/s"
    assert body["vcpu"]["source"] == "gnocchi"
    assert body["storage"]["data"] == [71]
    assert body["storage"]["source"] == "prometheus"
    assert body["storage"]["unit"] == "%"
    assert body["monitoring_available"] is True
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
async def test_missing_native_denominator_and_memory_report_partial_not_zero(client):
    observed = _native_project()
    observed["instances"]["large"]["vcpus"]["series"] = []
    observed["instances"]["large"]["memory"]["series"] = []
    with (
        patch("app.api.common.dashboard.native_telemetry.project_series", AsyncMock(return_value=observed)),
        patch("app.api.common.dashboard.prom_query.query_range", AsyncMock(return_value=[])),
    ):
        response = await client.get("/api/v1/dashboard/metrics/trend?range=24h")
    body = response.json()
    assert body["vcpu"]["data"] == [20, 0]
    assert body["vcpu"]["status"] == "partial"
    assert body["memory"]["data"] == [20, 0]
    assert body["memory"]["status"] == "partial"


@pytest.mark.asyncio
async def test_warm_project_cache_does_not_replay_denied_native_measurements(client):
    denied = {"source": "gnocchi", "status": "forbidden", "error": "gnocchi_forbidden", "instances": {}}
    with (
        patch(
            "app.api.common.dashboard.native_telemetry.project_series",
            AsyncMock(side_effect=[_native_project(), denied]),
        ),
        patch("app.api.common.dashboard.prom_query.query_range", AsyncMock(return_value=[{"ts": 100, "value": 90}])),
    ):
        first = await client.get("/api/v1/dashboard/metrics/trend?range=24h&cache=true")
        second = await client.get("/api/v1/dashboard/metrics/trend?range=24h&cache=true")
    assert first.json()["vcpu"]["data"] == [65, 0]
    assert second.json()["vcpu"]["data"] == [90]
    assert second.json()["vcpu"]["source"] == "libvirt"
    assert second.json()["vcpu"]["native_status"] == "forbidden"
