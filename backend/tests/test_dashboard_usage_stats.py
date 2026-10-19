"""Phase 53k — /api/dashboard/usage-stats per-instance cpu_pct/ram_pct 검증."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_server(server_id: str, name: str = "test-vm", flavor_name: str = "cpu.4c_8g") -> MagicMock:
    s = MagicMock()
    s.id = server_id
    s.name = name
    s.status = "ACTIVE"
    s.flavor_id = None
    s.flavor_name = flavor_name
    s.created_at = "2024-01-01T00:00:00Z"
    return s


def _make_flavor(name: str = "cpu.4c_8g", vcpus: int = 4, ram: int = 8192, disk: int = 80) -> MagicMock:
    f = MagicMock()
    f.id = f"flavor-{name}"
    f.name = name
    f.vcpus = vcpus
    f.ram = ram
    f.disk = disk
    f.extra_specs = {}
    return f


# ---------------------------------------------------------------------------
# PromUnavailable — silent fallback, 200 응답 유지
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_usage_stats_prometheus_unavailable_fallback(client, mock_conn):
    """Prometheus 미가용 시 200 + cpu_pct/ram_pct는 None."""
    from app.services.prom_query import PromUnavailable

    uuid1 = "bbbb-2222"

    with (
        patch("app.api.common.dashboard.nova.list_servers", return_value=[_make_server(uuid1)]),
        patch("app.api.common.dashboard.nova.list_flavors", return_value=[_make_flavor()]),
        patch("app.api.common.dashboard.nova.get_project_usage", return_value={}),
        patch("app.api.common.dashboard.prom_query.query_instant_multi", side_effect=PromUnavailable("no prometheus")),
    ):
        resp = await client.get("/api/v1/dashboard/usage-stats?range=7d")

    assert resp.status_code == 200
    inst = resp.json()["top_instances"][0]
    assert inst["cpu_pct"] is None
    assert inst["ram_pct"] is None


# ---------------------------------------------------------------------------
# 일부 UUID만 결과 — 누락 인스턴스는 None
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_usage_stats_unknown_instance_returns_none(client, mock_conn):
    """PromQL 결과에 없는 UUID는 cpu_pct=None으로 반환된다."""
    uuid_known = "cccc-3333"
    uuid_unknown = "dddd-4444"
    cpu_results = [({"instance_id": uuid_known}, 30.0)]
    ram_results = [({"instance_id": uuid_known}, 50.0)]

    with (
        patch(
            "app.api.common.dashboard.nova.list_servers",
            return_value=[
                _make_server(uuid_known, name="vm-a"),
                _make_server(uuid_unknown, name="vm-b"),
            ],
        ),
        patch("app.api.common.dashboard.nova.list_flavors", return_value=[_make_flavor()]),
        patch("app.api.common.dashboard.nova.get_project_usage", return_value={}),
        patch(
            "app.api.common.dashboard.prom_query.query_instant_multi",
            new_callable=AsyncMock,
            side_effect=[cpu_results, ram_results],
        ),
    ):
        resp = await client.get("/api/v1/dashboard/usage-stats?range=7d")

    assert resp.status_code == 200
    by_id = {i["id"]: i for i in resp.json()["top_instances"]}
    assert by_id[uuid_known]["cpu_pct"] == 30.0
    assert by_id[uuid_unknown]["cpu_pct"] is None
    assert by_id[uuid_unknown]["ram_pct"] is None


# ---------------------------------------------------------------------------
# 빈 프로젝트 — PromQL 호출 없음
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_usage_stats_empty_project_skips_prometheus(client, mock_conn):
    """인스턴스가 없으면 query_instant_multi를 호출하지 않는다."""
    with (
        patch("app.api.common.dashboard.nova.list_servers", return_value=[]),
        patch("app.api.common.dashboard.nova.list_flavors", return_value=[]),
        patch("app.api.common.dashboard.nova.get_project_usage", return_value={}),
        patch("app.api.common.dashboard.prom_query.query_instant_multi", new_callable=AsyncMock) as mock_qr,
    ):
        resp = await client.get("/api/v1/dashboard/usage-stats?range=7d")

    assert resp.status_code == 200
    assert resp.json()["top_instances"] == []
    assert mock_qr.call_count == 0, f"빈 프로젝트에서 PromQL 호출 불필요, 실제: {mock_qr.call_count}"


@pytest.mark.asyncio
async def test_native_zero_cpu_survives_missing_memory_provider(client, mock_conn):
    from app.services.prom_query import PromUnavailable

    instance_id = "native-zero"
    native = {
        "status": "partial",
        "instances": {
            instance_id: {
                "cpu": {"series": [{"ts": 100, "value": 0}], "status": "available"},
                "memory": {"series": [], "status": "unavailable"},
            }
        },
    }
    with (
        patch("app.api.common.dashboard.nova.list_servers", return_value=[_make_server(instance_id)]),
        patch("app.api.common.dashboard.nova.list_flavors", return_value=[_make_flavor()]),
        patch("app.api.common.dashboard.nova.get_project_usage", return_value={}),
        patch("app.api.common.dashboard.native_telemetry.project_series", AsyncMock(return_value=native)),
        patch(
            "app.api.common.dashboard.prom_query.query_instant_multi", AsyncMock(side_effect=PromUnavailable("offline"))
        ),
    ):
        response = await client.get("/api/v1/dashboard/usage-stats")
    instance = response.json()["top_instances"][0]
    assert instance["cpu_pct"] == 0
    assert instance["cpu_source"] == "gnocchi"
    assert instance["cpu_status"] == "available"
    assert instance["ram_pct"] is None
    assert instance["ram_status"] == "unavailable"
    assert instance["ram_native_status"] == "unavailable"


@pytest.mark.asyncio
async def test_denied_native_and_failed_cpu_do_not_discard_measured_ram(client, mock_conn):
    from app.services.prom_query import PromUnavailable

    instance_id = "fallback-partial"
    with (
        patch("app.api.common.dashboard.nova.list_servers", return_value=[_make_server(instance_id)]),
        patch("app.api.common.dashboard.nova.list_flavors", return_value=[_make_flavor()]),
        patch("app.api.common.dashboard.nova.get_project_usage", return_value={}),
        patch(
            "app.api.common.dashboard.native_telemetry.project_series",
            AsyncMock(return_value={"status": "forbidden", "instances": {}}),
        ),
        patch(
            "app.api.common.dashboard.prom_query.query_instant_multi",
            AsyncMock(side_effect=[PromUnavailable("offline"), [({"instance_id": instance_id}, 0)]]),
        ),
    ):
        response = await client.get("/api/v1/dashboard/usage-stats")
    instance = response.json()["top_instances"][0]
    assert instance["cpu_pct"] is None
    assert instance["cpu_status"] == "unavailable"
    assert instance["ram_pct"] == 0
    assert instance["ram_source"] == "libvirt"
    assert instance["ram_native_status"] == "forbidden"
