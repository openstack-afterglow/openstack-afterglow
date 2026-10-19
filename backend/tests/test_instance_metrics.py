"""인스턴스 메트릭 엔드포인트 테스트."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_PROJECT_ID = "test-project-123"

_FAKE_INSTANCE = MagicMock(
    id="inst-1",
    name="vm-1",
    project_id=_PROJECT_ID,
    flavor_name="m1.large",
    ip_addresses=[MagicMock(addr="10.0.0.1", type="fixed")],
)

_OTHER_INSTANCE = MagicMock(
    id="inst-other",
    name="vm-other",
    project_id="other-project",
    flavor_name="m1.large",
    ip_addresses=[MagicMock(addr="10.0.0.9", type="fixed")],
)

_GPU_INSTANCE = MagicMock(
    id="inst-gpu",
    name="vm-gpu",
    project_id=_PROJECT_ID,
    flavor_name="gpu.small",
    ip_addresses=[MagicMock(addr="10.0.0.2", type="fixed")],
)

_FAKE_SERIES = [{"ts": 1700000000, "value": 42.0}, {"ts": 1700000030, "value": 45.0}]


@pytest.fixture(autouse=True)
def native_metrics():
    """Existing exporter scenarios run independently of native deployment."""
    from app.api.compute.instance_metrics import _VALID_METRICS

    with patch(
        "app.api.compute.instance_metrics.native_telemetry.instance_series",
        new=AsyncMock(
            return_value={
                metric: {"series": [], "status": "not_configured", "error": None} for metric in _VALID_METRICS
            }
        ),
    ) as native:
        yield native


@pytest.mark.anyio
async def test_metrics_returns_series(client):
    with (
        patch("app.api.compute.instance_metrics.nova.get_server", return_value=_FAKE_INSTANCE),
        patch("app.api.compute.instance_metrics.query_range", new=AsyncMock(return_value=_FAKE_SERIES)),
    ):
        resp = await client.get("/api/v1/instances/inst-1/metrics?metric=cpu&range=1h")
    assert resp.status_code == 200
    body = resp.json()
    assert body["metric"] == "cpu"
    assert body["range"] == "1h"
    assert len(body["series"]) == 2
    assert body["series"][0]["value"] == 42.0


@pytest.mark.anyio
async def test_metrics_empty_series(client):
    with (
        patch("app.api.compute.instance_metrics.nova.get_server", return_value=_FAKE_INSTANCE),
        patch("app.api.compute.instance_metrics.query_range", new=AsyncMock(return_value=[])),
    ):
        resp = await client.get("/api/v1/instances/inst-1/metrics?metric=memory&range=15m")
    assert resp.status_code == 200
    assert resp.json()["series"] == []


@pytest.mark.anyio
async def test_metrics_unauthorized_other_project(client):
    with patch("app.api.compute.instance_metrics.nova.get_server", return_value=_OTHER_INSTANCE):
        resp = await client.get("/api/v1/instances/inst-other/metrics?metric=cpu&range=1h")
    assert resp.status_code == 403


@pytest.mark.anyio
async def test_metrics_admin_can_query_any(admin_client):
    with (
        patch("app.api.compute.instance_metrics.nova.get_server", return_value=_OTHER_INSTANCE),
        patch("app.api.compute.instance_metrics.query_range", new=AsyncMock(return_value=_FAKE_SERIES)),
    ):
        resp = await admin_client.get("/api/v1/instances/inst-other/metrics?metric=cpu&range=1h")
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_metrics_instance_not_found(client):
    with patch("app.api.compute.instance_metrics.nova.get_server", side_effect=Exception("not found")):
        resp = await client.get("/api/v1/instances/bad-id/metrics?metric=cpu&range=1h")
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_metrics_invalid_metric(client):
    resp = await client.get("/api/v1/instances/inst-1/metrics?metric=invalid_xyz&range=1h")
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_metrics_prom_unavailable(client):
    from app.services.prom_query import PromUnavailable

    with (
        patch("app.api.compute.instance_metrics.nova.get_server", return_value=_FAKE_INSTANCE),
        patch("app.api.compute.instance_metrics.query_range", new=AsyncMock(side_effect=PromUnavailable("conn error"))),
    ):
        resp = await client.get("/api/v1/instances/inst-1/metrics?metric=cpu&range=1h")
    assert resp.status_code == 503


@pytest.mark.anyio
async def test_metrics_gpu_on_non_gpu_instance(client):
    with patch("app.api.compute.instance_metrics.nova.get_server", return_value=_FAKE_INSTANCE):
        resp = await client.get("/api/v1/instances/inst-1/metrics?metric=gpu_util&range=1h")
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_metrics_gpu_on_gpu_instance(client):
    with (
        patch("app.api.compute.instance_metrics.nova.get_server", return_value=_GPU_INSTANCE),
        patch("app.api.compute.instance_metrics.query_range", new=AsyncMock(return_value=_FAKE_SERIES)),
    ):
        resp = await client.get("/api/v1/instances/inst-gpu/metrics?metric=gpu_util&range=1h")
    assert resp.status_code == 200


def test_step_calculation():
    from app.services.prom_query import calc_step

    assert calc_step(900) == 15  # 15m → 900/100=9 → max(15,9)=15
    assert calc_step(3600) == 36  # 1h  → 3600/100=36
    assert calc_step(86400) == 864  # 24h → 86400/100=864


# ---------------------------------------------------------------------------
# batch 엔드포인트
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_batch_returns_all_requested_metrics(client):
    """요청한 메트릭 키 모두 응답에 포함되어야 한다."""
    fake = [{"ts": 1700000000, "value": 10.0}]
    with (
        patch("app.api.compute.instance_metrics.nova.get_server", return_value=_FAKE_INSTANCE),
        patch("app.api.compute.instance_metrics.query_range", new=AsyncMock(return_value=fake)),
    ):
        resp = await client.get("/api/v1/instances/inst-1/metrics-batch?metrics=cpu,memory&range=1h")
    assert resp.status_code == 200
    body = resp.json()
    assert "cpu" in body["metrics"]
    assert "memory" in body["metrics"]
    assert body["metrics"]["cpu"]["series"][0]["value"] == 10.0
    assert body["metrics"]["cpu"]["error"] is None


@pytest.mark.anyio
async def test_batch_per_metric_error_capsulated(client):
    """한 메트릭이 PromUnavailable 이어도 다른 메트릭은 정상 반환되어야 한다."""
    from app.services.prom_query import PromUnavailable

    fake = [{"ts": 1700000000, "value": 5.0}]
    call_count = 0

    async def _side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise PromUnavailable("timeout")
        return fake

    with (
        patch("app.api.compute.instance_metrics.nova.get_server", return_value=_FAKE_INSTANCE),
        patch("app.api.compute.instance_metrics.query_range", new=AsyncMock(side_effect=_side_effect)),
    ):
        resp = await client.get("/api/v1/instances/inst-1/metrics-batch?metrics=cpu,memory&range=1h")
    assert resp.status_code == 200
    body = resp.json()
    # 첫 번째 메트릭 에러 캡슐화 — 전체 응답은 200
    errors = [v["error"] for v in body["metrics"].values() if v["error"]]
    oks = [v for v in body["metrics"].values() if not v["error"] and v["series"]]
    assert len(errors) == 1
    assert len(oks) == 1


@pytest.mark.anyio
async def test_batch_skips_gpu_on_non_gpu(client):
    """non-GPU 인스턴스에 gpu_util 요청 시 silent skip (키 누락)."""
    with (
        patch("app.api.compute.instance_metrics.nova.get_server", return_value=_FAKE_INSTANCE),
        patch("app.api.compute.instance_metrics.query_range", new=AsyncMock(return_value=[])),
    ):
        resp = await client.get("/api/v1/instances/inst-1/metrics-batch?metrics=cpu,gpu_util&range=1h")
    assert resp.status_code == 200
    body = resp.json()
    assert "cpu" in body["metrics"]
    assert "gpu_util" not in body["metrics"]


@pytest.mark.anyio
async def test_batch_invalid_metric_returns_422(client):
    """알 수 없는 메트릭 키 포함 시 422."""
    resp = await client.get("/api/v1/instances/inst-1/metrics-batch?metrics=cpu,xyz_unknown&range=1h")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# libvirt-exporter 폴백 테스트
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_instance_metrics_cpu_fallback_to_libvirt(client):
    """node_exporter 빈 시계열 → libvirt 폴백 호출 → 시계열 반환."""
    libvirt_series = [{"ts": 1700000000, "value": 35.0}]

    async def _side_effect(expr: str, **kwargs):
        if "node_cpu_seconds_total" in expr:
            return []
        return libvirt_series

    with (
        patch("app.api.compute.instance_metrics.nova.get_server", return_value=_FAKE_INSTANCE),
        patch("app.api.compute.instance_metrics.query_range", new=AsyncMock(side_effect=_side_effect)),
    ):
        resp = await client.get("/api/v1/instances/inst-1/metrics?metric=cpu&range=1h")

    assert resp.status_code == 200
    assert resp.json()["series"] == libvirt_series


@pytest.mark.anyio
async def test_instance_metrics_memory_fallback(client):
    """메모리 node_exporter 빈 → libvirt memory_stats_used_percent 폴백."""
    libvirt_series = [{"ts": 1700000000, "value": 68.5}]

    async def _side_effect(expr: str, **kwargs):
        if "node_memory_MemAvailable_bytes" in expr:
            return []
        return libvirt_series

    with (
        patch("app.api.compute.instance_metrics.nova.get_server", return_value=_FAKE_INSTANCE),
        patch("app.api.compute.instance_metrics.query_range", new=AsyncMock(side_effect=_side_effect)),
    ):
        resp = await client.get("/api/v1/instances/inst-1/metrics?metric=memory&range=1h")

    assert resp.status_code == 200
    assert resp.json()["series"] == libvirt_series


@pytest.mark.anyio
async def test_instance_metrics_network_rx_fallback(client):
    """network_rx node_exporter 빈 → libvirt interface_stats 폴백."""
    libvirt_series = [{"ts": 1700000000, "value": 1024.0}]

    async def _side_effect(expr: str, **kwargs):
        if "node_network_receive_bytes_total" in expr:
            return []
        return libvirt_series

    with (
        patch("app.api.compute.instance_metrics.nova.get_server", return_value=_FAKE_INSTANCE),
        patch("app.api.compute.instance_metrics.query_range", new=AsyncMock(side_effect=_side_effect)),
    ):
        resp = await client.get("/api/v1/instances/inst-1/metrics?metric=network_rx&range=1h")

    assert resp.status_code == 200
    assert resp.json()["series"] == libvirt_series


@pytest.mark.anyio
async def test_instance_metrics_disk_read_fallback(client):
    """disk_read node_exporter 빈 → libvirt block_stats 폴백."""
    libvirt_series = [{"ts": 1700000000, "value": 512.0}]

    async def _side_effect(expr: str, **kwargs):
        if "node_disk_read_bytes_total" in expr:
            return []
        return libvirt_series

    with (
        patch("app.api.compute.instance_metrics.nova.get_server", return_value=_FAKE_INSTANCE),
        patch("app.api.compute.instance_metrics.query_range", new=AsyncMock(side_effect=_side_effect)),
    ):
        resp = await client.get("/api/v1/instances/inst-1/metrics?metric=disk_read&range=1h")

    assert resp.status_code == 200
    assert resp.json()["series"] == libvirt_series


@pytest.mark.anyio
async def test_instance_metrics_both_empty_returns_empty_series(client):
    """node_exporter + libvirt 모두 빈 시계열 → 빈 배열, 500 금지."""
    with (
        patch("app.api.compute.instance_metrics.nova.get_server", return_value=_FAKE_INSTANCE),
        patch("app.api.compute.instance_metrics.query_range", new=AsyncMock(return_value=[])),
    ):
        resp = await client.get("/api/v1/instances/inst-1/metrics?metric=cpu&range=1h")

    assert resp.status_code == 200
    assert resp.json()["series"] == []


def test_metric_instance_id_rejects_promql_label_injection():
    from fastapi import HTTPException

    from app.api.compute.instance_metrics import _metric_instance_id

    server = MagicMock(id='safe"} or vector(1) or instance_id="x', project_id=_PROJECT_ID)
    with pytest.raises(HTTPException) as error:
        _metric_instance_id(server)
    assert error.value.status_code == 502


@pytest.mark.anyio
@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/instances/request-id/metrics?metric=cpu&range=1h",
        "/api/v1/instances/request-id/metrics-batch?metrics=cpu&range=1h",
        "/api/v1/instances/request-id/metrics-summary",
    ],
)
async def test_metric_routes_reject_untrusted_nova_id_before_prometheus_query(client, path):
    bad_server = MagicMock(
        id='safe"} or vector(1) or instance_id="x',
        project_id=_PROJECT_ID,
        flavor_name="m1.large",
    )
    with (
        patch("app.api.compute.instance_metrics._resolve_server", return_value=bad_server),
        patch("app.api.compute.instance_metrics.query_range", new=AsyncMock()) as query,
        patch("app.api.compute.instance_metrics._fetch_stat_with_fallback", new=AsyncMock()) as stats,
    ):
        response = await client.get(path)

    assert response.status_code == 502
    query.assert_not_awaited()
    stats.assert_not_awaited()


def _native(series, *, status="available"):
    return {"series": series, "source": "gnocchi", "unit": "%", "status": status, "error": None}


@pytest.mark.anyio
async def test_native_zero_uses_authorized_canonical_server_without_exporters(client, native_metrics):
    from app.services.prom_query import PromUnavailable

    native_metrics.return_value = {"cpu": _native([{"ts": 1700000000, "value": 0.0}])}
    with (
        patch("app.api.compute.instance_metrics.nova.get_server", return_value=_FAKE_INSTANCE),
        patch("app.api.compute.instance_metrics.query_range", new=AsyncMock(side_effect=PromUnavailable("down"))),
    ):
        response = await client.get("/api/v1/instances/request-alias/metrics?metric=cpu")
    assert response.status_code == 200
    result = response.json()
    assert result["series"] == [{"ts": 1700000000, "value": 0.0}]
    assert result["source"] == "gnocchi"
    assert result["unit"] == "%"
    assert result["status"] == result["native_status"] == "available"
    assert result["error"] is None
    assert native_metrics.await_args.args[1] is _FAKE_INSTANCE


@pytest.mark.anyio
async def test_batch_selects_native_and_fallback_independently(client, native_metrics):
    native_metrics.return_value = {
        "cpu": _native(_FAKE_SERIES, status="partial"),
        "memory": {"series": [], "status": "forbidden", "error": "forbidden"},
        "disk_read_iops": _native([{"ts": 1700000000, "value": 3.0}]),
    }
    fallback = [{"ts": 1700000030, "value": 67.0}]
    with (
        patch("app.api.compute.instance_metrics.nova.get_server", return_value=_FAKE_INSTANCE),
        patch("app.api.compute.instance_metrics.query_range", new=AsyncMock(return_value=fallback)),
    ):
        response = await client.get(
            "/api/v1/instances/inst-1/metrics-batch?metrics=cpu,memory,disk_read_iops,memory_resident"
        )
    assert response.status_code == 200
    metrics = response.json()["metrics"]
    assert metrics["cpu"]["series"] == _FAKE_SERIES  # No exporter samples mixed into native history.
    assert metrics["cpu"]["status"] == "partial"
    assert metrics["memory"]["series"] == fallback
    assert metrics["memory"]["source"] == "prometheus"
    assert metrics["memory"]["status"] == "available"
    assert metrics["memory"]["native_status"] == "forbidden"
    assert metrics["memory"]["error"] is None
    assert metrics["disk_read_iops"]["unit"] == "request/s"
    assert metrics["memory_resident"]["series"] == []
    assert metrics["memory_resident"]["status"] == "not_collected"
    assert metrics["memory_resident"]["unit"] == "MiB"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "metric,unit",
    [
        ("disk_write_iops", "request/s"),
        ("network_rx_packets", "packet/s"),
        ("network_tx_packets", "packet/s"),
        ("memory_resident", "MiB"),
        ("disk_allocation", "B"),
        ("memory_swap_in", "MiB/s"),
        ("memory_swap_out", "MiB/s"),
    ],
)
async def test_additional_native_metrics_are_readable_without_exporter_fabrication(
    client, native_metrics, metric, unit
):
    native_metrics.return_value = {metric: _native([{"ts": 1700000000, "value": 0.0}])}
    with (
        patch("app.api.compute.instance_metrics.nova.get_server", return_value=_FAKE_INSTANCE),
        patch(
            "app.api.compute.instance_metrics.query_range",
            new=AsyncMock(side_effect=AssertionError("native-only metric")),
        ),
    ):
        response = await client.get(f"/api/v1/instances/inst-1/metrics?metric={metric}")
    assert response.status_code == 200
    assert response.json()["series"][0]["value"] == 0.0
    assert response.json()["unit"] == unit


@pytest.mark.anyio
@pytest.mark.parametrize("suffix", ["metrics?metric=cpu", "metrics-batch?metrics=cpu", "metrics-summary"])
async def test_native_queries_never_precede_canonical_nova_authorization(client, native_metrics, suffix):
    with patch("app.api.compute.instance_metrics.nova.get_server", return_value=_OTHER_INSTANCE):
        response = await client.get(f"/api/v1/instances/inst-other/{suffix}")
    assert response.status_code == 403
    native_metrics.assert_not_awaited()


@pytest.mark.anyio
async def test_provider_failures_do_not_expose_credential_bearing_exception_bodies(client, native_metrics):
    from app.services.prom_query import PromUnavailable

    secret = "https://user:password@telemetry.invalid/?token=private-token"
    native_metrics.side_effect = RuntimeError(secret)
    with (
        patch("app.api.compute.instance_metrics.nova.get_server", return_value=_FAKE_INSTANCE),
        patch("app.api.compute.instance_metrics.query_range", new=AsyncMock(side_effect=PromUnavailable(secret))),
    ):
        response = await client.get("/api/v1/instances/inst-1/metrics-batch?metrics=cpu")
        single = await client.get("/api/v1/instances/inst-1/metrics?metric=cpu")
    assert response.status_code == 200
    assert response.json()["metrics"]["cpu"]["error"] == "prometheus_unavailable"
    assert response.json()["metrics"]["cpu"]["native_status"] == "unavailable"
    assert single.status_code == 503
    assert "password" not in response.text + single.text
    assert "private-token" not in response.text + single.text


@pytest.mark.anyio
async def test_readable_native_without_samples_is_not_an_exporter_outage(client, native_metrics):
    from app.services.prom_query import PromUnavailable

    native_metrics.return_value = {"cpu": {"series": [], "status": "not_collected", "error": None}}
    with (
        patch("app.api.compute.instance_metrics.nova.get_server", return_value=_FAKE_INSTANCE),
        patch("app.api.compute.instance_metrics.query_range", new=AsyncMock(side_effect=PromUnavailable("down"))),
    ):
        response = await client.get("/api/v1/instances/inst-1/metrics?metric=cpu")
    assert response.status_code == 200
    assert response.json()["series"] == []
    assert response.json()["status"] == response.json()["native_status"] == "not_collected"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "suffix",
    [
        "inst-1/metrics?metric=cpu",
        "inst-1/metrics-batch?metrics=cpu",
        "inst-1/metrics-summary",
        "metrics-summary-batch",
    ],
)
@pytest.mark.parametrize("denied", [False, True])
async def test_metrics_responses_are_not_cacheable_including_errors(client, suffix, denied):
    server = _OTHER_INSTANCE if denied else _FAKE_INSTANCE
    with (
        patch("app.api.compute.instance_metrics.nova.get_server", return_value=server),
        patch(
            "app.api.compute.instance_metrics.nova.list_servers",
            side_effect=RuntimeError("denied") if denied else None,
            return_value=[_FAKE_INSTANCE],
        ),
        patch("app.api.compute.instance_metrics.query_range", new=AsyncMock(return_value=[])),
        patch("app.api.compute.instance_metrics.query_instant_multi", new=AsyncMock(return_value=[])),
        patch(
            "app.api.compute.instance_metrics.native_telemetry.project_series",
            new=AsyncMock(
                return_value={
                    "status": "not_configured",
                    "instances": {},
                }
            ),
        ),
    ):
        response = await client.get(f"/api/v1/instances/{suffix}")
    assert response.status_code == (502 if denied and suffix == "metrics-summary-batch" else 403 if denied else 200)
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.anyio
async def test_metrics_validation_errors_are_not_cacheable(client):
    response = await client.get("/api/v1/instances/inst-1/metrics?metric=invalid")
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.anyio
@pytest.mark.parametrize("batch", [False, True])
async def test_nonfinite_exporter_values_do_not_break_metrics_json(client, batch):
    series = [
        {"ts": 1700000000, "value": float("nan")},
        {"ts": 1700000030, "value": float("inf")},
        {"ts": 1700000060, "value": float("-inf")},
        {"ts": 1700000090, "value": 0.0},
    ]
    with (
        patch("app.api.compute.instance_metrics.nova.get_server", return_value=_FAKE_INSTANCE),
        patch("app.api.compute.instance_metrics.query_range", new=AsyncMock(return_value=series)),
    ):
        suffix = "metrics-batch?metrics=cpu" if batch else "metrics?metric=cpu"
        response = await client.get(f"/api/v1/instances/inst-1/{suffix}")
    assert response.status_code == 200
    metric = response.json()["metrics"]["cpu"] if batch else response.json()
    assert metric["series"] == [{"ts": 1700000090, "value": 0.0}]


@pytest.mark.anyio
async def test_nonfinite_node_samples_can_use_finite_libvirt_fallback(client):
    results = [[{"ts": 1700000000, "value": float("nan")}], _FAKE_SERIES]
    with (
        patch("app.api.compute.instance_metrics.nova.get_server", return_value=_FAKE_INSTANCE),
        patch("app.api.compute.instance_metrics.query_range", new=AsyncMock(side_effect=results)),
    ):
        response = await client.get("/api/v1/instances/inst-1/metrics?metric=cpu")
    assert response.status_code == 200
    assert response.json()["series"] == _FAKE_SERIES
