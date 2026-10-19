"""인스턴스 메트릭 요약 + 리사이즈 권장 엔드포인트 테스트."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.compute import FlavorInfo

_PROJECT_ID = "test-project-123"

_FAKE_INSTANCE = MagicMock(
    id="inst-1",
    name="vm-1",
    project_id=_PROJECT_ID,
    flavor_name="m1.large",
    flavor_id="flavor-large",
)

_OTHER_INSTANCE = MagicMock(
    id="inst-other",
    name="vm-other",
    project_id="other-project",
    flavor_name="m1.large",
    flavor_id="flavor-large",
)

_GPU_INSTANCE = MagicMock(
    id="inst-gpu",
    name="vm-gpu",
    project_id=_PROJECT_ID,
    flavor_name="gpu.small",
    flavor_id="flavor-gpu",
)

# 테스트용 플레이버 목록
_LARGE_FLAVOR = FlavorInfo(id="flavor-large", name="m1.large", vcpus=8, ram=16384, disk=50)
_SMALL_FLAVOR = FlavorInfo(id="flavor-small", name="m1.small", vcpus=2, ram=4096, disk=50)
_TINY_DISK_FLAVOR = FlavorInfo(id="flavor-tiny", name="m1.tiny", vcpus=1, ram=1024, disk=20)
_GPU_FLAVOR = FlavorInfo(id="flavor-gpu", name="gpu.small", vcpus=4, ram=8192, disk=50)

_DEFAULT_FLAVORS = [_LARGE_FLAVOR, _SMALL_FLAVOR, _TINY_DISK_FLAVOR, _GPU_FLAVOR]


@pytest.fixture(autouse=True)
def native_metrics(mock_conn):
    mock_conn._afterglow_authenticated_project_id = _PROJECT_ID
    with (
        patch(
            "app.api.compute.instance_metrics.native_telemetry.instance_series",
            new=AsyncMock(
                return_value={
                    metric: {"series": [], "status": "not_configured", "error": None}
                    for metric in ("cpu", "memory", "disk_read", "disk_write")
                }
            ),
        ) as instance,
        patch(
            "app.api.compute.instance_metrics.native_telemetry.project_series",
            new=AsyncMock(return_value={"status": "not_configured", "instances": {}}),
        ) as project,
        patch(
            "app.api.compute.instance_metrics.nova.list_servers",
            return_value=[
                _FAKE_INSTANCE,
                MagicMock(id="inst-2", project_id=_PROJECT_ID, flavor_name="m1.large"),
                _OTHER_INSTANCE,
            ],
        ),
    ):
        yield instance, project


def _instant(value: float, instance_id: str = "inst-1"):
    """query_instant_multi 반환값 형식."""
    return [({"instance_id": instance_id}, value)]


# ---------------------------------------------------------------------------
# metrics-summary 기본 동작
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_summary_returns_stats(client):
    """통계(min/avg/max)가 올바르게 반환되는지 확인."""
    with (
        patch("app.api.compute.instance_metrics.nova.get_server", return_value=_FAKE_INSTANCE),
        patch("app.api.compute.instance_metrics.nova.list_flavors", return_value=_DEFAULT_FLAVORS),
        patch(
            "app.api.compute.instance_metrics.query_instant_multi",
            new=AsyncMock(return_value=_instant(5.0)),
        ),
    ):
        resp = await client.get("/api/v1/instances/inst-1/metrics-summary?range=7d")
    assert resp.status_code == 200
    body = resp.json()
    assert body["monitoring_available"] is True
    assert "cpu" in body["stats"]
    assert body["stats"]["cpu"]["avg"] == 5.0
    assert body["stats"]["memory"]["avg"] == 5.0


@pytest.mark.anyio
async def test_summary_cpu_low_triggers_recommendation(client):
    """CPU 평균 < 10% → underutilized=True, reason에 cpu_avg<10 포함."""
    with (
        patch("app.api.compute.instance_metrics.nova.get_server", return_value=_FAKE_INSTANCE),
        patch("app.api.compute.instance_metrics.nova.list_flavors", return_value=_DEFAULT_FLAVORS),
        patch(
            "app.api.compute.instance_metrics.query_instant_multi",
            new=AsyncMock(return_value=_instant(5.0)),
        ),
    ):
        resp = await client.get("/api/v1/instances/inst-1/metrics-summary?range=7d")
    body = resp.json()
    rec = body["recommendation"]
    assert rec is not None
    assert rec["underutilized"] is True
    assert "cpu_avg<10" in rec["reason"]


@pytest.mark.anyio
async def test_summary_mem_low_triggers_recommendation(client):
    """메모리 평균 < 20%, CPU 정상(≥10%) → underutilized=True, reason에 mem_avg<20 포함."""
    # cpu_avg=15 (정상), mem_avg=12 (낮음)
    # query_instant_multi 호출 순서: 메트릭 4개 × avg/min/max 3종 = 12회
    # 모두 같은 측정값이지만 cpu=15, mem=12로 분기 필요 — return_value 로 통일 후
    # 별도 패치로 cpu 관련 결과만 15.0 반환
    call_counter = {"n": 0}

    async def _side(promql: str):
        call_counter["n"] += 1
        # cpu 식에는 "node_cpu" 또는 "libvirt_domain_info_cpu" 포함
        if "cpu" in promql and "memory" not in promql:
            return _instant(15.0)
        return _instant(12.0)

    with (
        patch("app.api.compute.instance_metrics.nova.get_server", return_value=_FAKE_INSTANCE),
        patch("app.api.compute.instance_metrics.nova.list_flavors", return_value=_DEFAULT_FLAVORS),
        patch("app.api.compute.instance_metrics.query_instant_multi", side_effect=_side),
    ):
        resp = await client.get("/api/v1/instances/inst-1/metrics-summary?range=7d")
    body = resp.json()
    rec = body["recommendation"]
    assert rec is not None
    assert rec["underutilized"] is True
    assert "mem_avg<20" in rec["reason"]


@pytest.mark.anyio
async def test_summary_no_recommendation_when_both_normal(client):
    """CPU ≥ 10%, RAM ≥ 20% → underutilized=False."""
    with (
        patch("app.api.compute.instance_metrics.nova.get_server", return_value=_FAKE_INSTANCE),
        patch("app.api.compute.instance_metrics.nova.list_flavors", return_value=_DEFAULT_FLAVORS),
        patch(
            "app.api.compute.instance_metrics.query_instant_multi",
            new=AsyncMock(return_value=_instant(50.0)),  # 50% — 높음
        ),
    ):
        resp = await client.get("/api/v1/instances/inst-1/metrics-summary?range=7d")
    body = resp.json()
    rec = body["recommendation"]
    assert rec is not None
    assert rec["underutilized"] is False


# ---------------------------------------------------------------------------
# 추천 플레이버 알고리즘
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_summary_suggested_flavor_excludes_disk_shrink(client):
    """추천 플레이버는 현재 플레이버보다 disk가 작으면 안 됨."""
    # _TINY_DISK_FLAVOR (disk=20) 는 cur_disk=50 미만 → 후보 제외
    # _SMALL_FLAVOR (disk=50, vcpus=2, ram=4096) 는 후보
    with (
        patch("app.api.compute.instance_metrics.nova.get_server", return_value=_FAKE_INSTANCE),
        patch("app.api.compute.instance_metrics.nova.list_flavors", return_value=_DEFAULT_FLAVORS),
        patch(
            "app.api.compute.instance_metrics.query_instant_multi",
            new=AsyncMock(return_value=_instant(5.0)),
        ),
    ):
        resp = await client.get("/api/v1/instances/inst-1/metrics-summary?range=7d")
    body = resp.json()
    rec = body["recommendation"]
    assert rec["underutilized"] is True
    suggested = rec["suggested_flavor"]
    assert suggested is not None
    assert suggested["disk"] >= 50  # 현재 disk 이상


@pytest.mark.anyio
async def test_summary_no_suggested_when_no_candidate(client):
    """더 작은 후보가 없으면 suggested_flavor=null."""
    # 현재 인스턴스가 이미 가장 작은 플레이버 사용
    smallest_instance = MagicMock(
        id="inst-small",
        name="vm-small",
        project_id=_PROJECT_ID,
        flavor_name="m1.small",
        flavor_id="flavor-small",
    )
    # m1.small보다 더 작고 disk≥50인 플레이버 없음
    with (
        patch("app.api.compute.instance_metrics.nova.get_server", return_value=smallest_instance),
        patch(
            "app.api.compute.instance_metrics.nova.list_flavors",
            return_value=[_SMALL_FLAVOR, _LARGE_FLAVOR, _GPU_FLAVOR],
        ),
        patch(
            "app.api.compute.instance_metrics.query_instant_multi",
            new=AsyncMock(return_value=_instant(5.0, "inst-small")),
        ),
    ):
        resp = await client.get("/api/v1/instances/inst-small/metrics-summary?range=7d")
    body = resp.json()
    rec = body["recommendation"]
    assert rec["underutilized"] is True
    assert rec["suggested_flavor"] is None


@pytest.mark.anyio
async def test_summary_gpu_instance_no_recommendation(client):
    """GPU 인스턴스는 권장 제외 (recommendation=null)."""
    with (
        patch("app.api.compute.instance_metrics.nova.get_server", return_value=_GPU_INSTANCE),
        patch(
            "app.api.compute.instance_metrics.query_instant_multi",
            new=AsyncMock(return_value=_instant(1.0, "inst-gpu")),
        ),
    ):
        resp = await client.get("/api/v1/instances/inst-gpu/metrics-summary?range=7d")
    body = resp.json()
    assert body["recommendation"] is None


# ---------------------------------------------------------------------------
# 권한 / 404
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_summary_unauthorized_other_project(client):
    """다른 프로젝트 인스턴스 → 403."""
    with patch("app.api.compute.instance_metrics.nova.get_server", return_value=_OTHER_INSTANCE):
        resp = await client.get("/api/v1/instances/inst-other/metrics-summary")
    assert resp.status_code == 403


@pytest.mark.anyio
async def test_summary_admin_can_access_any(admin_client):
    """관리자는 다른 프로젝트 인스턴스도 조회 가능."""
    with (
        patch("app.api.compute.instance_metrics.nova.get_server", return_value=_OTHER_INSTANCE),
        patch("app.api.compute.instance_metrics.nova.list_flavors", return_value=_DEFAULT_FLAVORS),
        patch(
            "app.api.compute.instance_metrics.query_instant_multi",
            new=AsyncMock(return_value=_instant(50.0, "inst-other")),
        ),
    ):
        resp = await admin_client.get("/api/v1/instances/inst-other/metrics-summary")
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_summary_instance_not_found(client):
    """인스턴스 없음 → 404."""
    with patch("app.api.compute.instance_metrics.nova.get_server", side_effect=Exception("not found")):
        resp = await client.get("/api/v1/instances/bad-id/metrics-summary")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Prometheus 불가 폴백
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_summary_prom_unavailable_returns_200(client):
    """No chosen measurements yields monitoring_available=false without a resize hint."""
    from app.services.prom_query import PromUnavailable

    with (
        patch("app.api.compute.instance_metrics.nova.get_server", return_value=_FAKE_INSTANCE),
        patch(
            "app.api.compute.instance_metrics.query_instant_multi",
            new=AsyncMock(side_effect=PromUnavailable("down")),
        ),
    ):
        resp = await client.get("/api/v1/instances/inst-1/metrics-summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["monitoring_available"] is False
    assert body["stats"] == {}
    assert body["recommendation"] is None


# ---------------------------------------------------------------------------
# libvirt 폴백
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_summary_libvirt_fallback(client):
    """Exporter fallback values remain useful when node measurements are absent."""

    async def _side(promql: str):
        if "libvirt" not in promql:
            return []
        return _instant(8.0)

    with (
        patch("app.api.compute.instance_metrics.nova.get_server", return_value=_FAKE_INSTANCE),
        patch("app.api.compute.instance_metrics.nova.list_flavors", return_value=_DEFAULT_FLAVORS),
        patch("app.api.compute.instance_metrics.query_instant_multi", side_effect=_side),
    ):
        resp = await client.get("/api/v1/instances/inst-1/metrics-summary")
    assert resp.status_code == 200
    assert resp.json()["stats"]["cpu"]["avg"] == 8.0
    assert resp.json()["stats"]["memory"]["avg"] == 8.0


# ---------------------------------------------------------------------------
# metrics-summary-batch
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_batch_returns_per_instance_data(client):
    """batch: project_id로 필터된 인스턴스 별 cpu_avg/mem_avg/underutilized 반환."""
    cpu_results = [({"instance_id": "inst-1"}, 5.0), ({"instance_id": "inst-2"}, 50.0)]
    mem_results = [({"instance_id": "inst-1"}, 15.0), ({"instance_id": "inst-2"}, 60.0)]

    call_count = {"n": 0}

    async def _side(promql: str):
        call_count["n"] += 1
        # 첫 호출(cpu_node), 세 번째 호출(cpu_lv) 는 cpu 관련
        if "cpu" in promql and "memory" not in promql and "libvirt" not in promql:
            return cpu_results
        if "memory" in promql and "libvirt" not in promql:
            return mem_results
        return []  # libvirt 폴백 — 이미 node 결과 있으므로 merge 안 됨

    with patch("app.api.compute.instance_metrics.query_instant_multi", side_effect=_side):
        resp = await client.get("/api/v1/instances/metrics-summary-batch")
    assert resp.status_code == 200
    body = resp.json()
    assert body["monitoring_available"] is True
    instances = body["instances"]
    assert "inst-1" in instances
    assert instances["inst-1"]["underutilized"] is True  # cpu<10 AND mem<20
    assert instances["inst-2"]["underutilized"] is False  # cpu=50, mem=60 — 정상


@pytest.mark.anyio
async def test_batch_invalid_project_id_returns_empty(client):
    """비정상 project_id 형식(주입 위험) 시 instances={} 반환, Prometheus 조회 안 함."""
    from app.api.deps import get_token_info
    from app.main import app

    async def _bad_token():
        return {
            "token": "test-token",
            "project_id": "../../etc/passwd",  # 주입 시도
            "user_id": "u1",
            "is_system_admin": False,
        }

    app.dependency_overrides[get_token_info] = _bad_token
    try:
        with patch(
            "app.api.compute.instance_metrics.query_instant_multi",
            new=AsyncMock(return_value=[]),
        ) as mock_q:
            resp = await client.get("/api/v1/instances/metrics-summary-batch")
        assert resp.status_code == 200
        assert resp.json()["instances"] == {}
        mock_q.assert_not_called()
    finally:
        app.dependency_overrides.pop(get_token_info, None)


@pytest.mark.anyio
async def test_batch_prom_unavailable_returns_200(client):
    """Without usable native or exporter data monitoring remains unavailable."""
    from app.services.prom_query import PromUnavailable

    with patch(
        "app.api.compute.instance_metrics.query_instant_multi",
        new=AsyncMock(side_effect=PromUnavailable("down")),
    ):
        resp = await client.get("/api/v1/instances/metrics-summary-batch")
    assert resp.status_code == 200
    body = resp.json()
    assert body["monitoring_available"] is False
    assert body["instances"] == {}


def _native(*values, status="available"):
    return {
        "series": [{"ts": 1700000000 + offset * 60, "value": value} for offset, value in enumerate(values)],
        "source": "gnocchi",
        "unit": "%",
        "status": status,
        "error": None,
    }


@pytest.mark.anyio
async def test_summary_native_measurements_survive_independent_exporter_outage(client, native_metrics):
    from app.services.prom_query import PromUnavailable

    instance, _ = native_metrics
    instance.return_value = {"cpu": _native(0.0, 2.0), "memory": _native(5.0, 10.0)}
    with (
        patch("app.api.compute.instance_metrics.nova.get_server", return_value=_FAKE_INSTANCE),
        patch("app.api.compute.instance_metrics.nova.list_flavors", return_value=_DEFAULT_FLAVORS),
        patch(
            "app.api.compute.instance_metrics.query_instant_multi", new=AsyncMock(side_effect=PromUnavailable("down"))
        ),
    ):
        response = await client.get("/api/v1/instances/inst-1/metrics-summary")
    assert response.status_code == 200
    body = response.json()
    assert body["monitoring_available"] is True
    assert body["stats"]["cpu"]["avg"] == 1.0
    assert body["stats"]["cpu"]["min"] == 0.0
    assert body["stats"]["cpu"]["max"] == 2.0
    assert body["stats"]["cpu"]["source"] == "gnocchi"
    assert body["stats"]["disk_read"]["avg"] is None
    assert body["recommendation"]["suggested_flavor"]["id"] == "flavor-small"


@pytest.mark.anyio
async def test_summary_unknown_memory_never_becomes_resize_advice(client, native_metrics):
    instance, _ = native_metrics
    instance.return_value = {"cpu": _native(0.0)}
    with (
        patch("app.api.compute.instance_metrics.nova.get_server", return_value=_FAKE_INSTANCE),
        patch("app.api.compute.instance_metrics.query_instant_multi", new=AsyncMock(return_value=[])),
    ):
        response = await client.get("/api/v1/instances/inst-1/metrics-summary")
    body = response.json()
    assert body["monitoring_available"] is True
    assert body["stats"]["cpu"]["avg"] == 0.0
    assert body["stats"]["memory"]["avg"] is None
    assert body["recommendation"] is None


@pytest.mark.anyio
async def test_summary_native_partial_memory_falls_back_without_discarding_cpu(client, native_metrics):
    instance, _ = native_metrics
    instance.return_value = {
        "cpu": _native(30.0, 40.0, status="partial"),
        "memory": {"status": "forbidden", "series": [], "error": "forbidden"},
    }
    with (
        patch("app.api.compute.instance_metrics.nova.get_server", return_value=_FAKE_INSTANCE),
        patch("app.api.compute.instance_metrics.query_instant_multi", new=AsyncMock(return_value=_instant(50.0))),
    ):
        response = await client.get("/api/v1/instances/inst-1/metrics-summary")
    stats = response.json()["stats"]
    assert stats["cpu"]["avg"] == 35.0
    assert stats["cpu"]["status"] == "partial"
    assert stats["memory"]["avg"] == 50.0
    assert stats["memory"]["native_status"] == "forbidden"
    assert stats["memory"]["source"] == "prometheus"
    assert response.json()["recommendation"] is None


@pytest.mark.anyio
@pytest.mark.parametrize("native_readable", [False, True])
async def test_readable_empty_provider_is_waiting_not_offline(client, native_metrics, native_readable):
    from app.services.prom_query import PromUnavailable

    instance, project = native_metrics
    if native_readable:
        instance.return_value = {
            metric: _native(status="not_collected") for metric in ("cpu", "memory", "disk_read", "disk_write")
        }
        project.return_value = {"status": "not_collected", "instances": {}}
    query = AsyncMock(side_effect=PromUnavailable("down")) if native_readable else AsyncMock(return_value=[])
    with (
        patch("app.api.compute.instance_metrics.nova.get_server", return_value=_FAKE_INSTANCE),
        patch("app.api.compute.instance_metrics.query_instant_multi", new=query),
    ):
        summary = await client.get("/api/v1/instances/inst-1/metrics-summary")
        batch = await client.get("/api/v1/instances/metrics-summary-batch")
    assert summary.status_code == batch.status_code == 200
    assert summary.json()["monitoring_available"] is True
    assert summary.json()["stats"]["cpu"]["avg"] is None
    assert summary.json()["recommendation"] is None
    assert batch.json()["monitoring_available"] is True
    assert batch.json()["instances"] == {}


@pytest.mark.anyio
async def test_project_summary_joins_native_and_fallback_only_to_canonical_owned_inventory(client, native_metrics):
    instance, project = native_metrics
    project.return_value = {
        "status": "partial",
        "instances": {
            "inst-1": {"cpu": _native(0.0)},
            "inst-other": {"cpu": _native(1.0), "memory": _native(2.0)},
            "stale-deleted-id": {"cpu": _native(1.0), "memory": _native(2.0)},
        },
    }
    fallback = [
        ({"instance_id": "inst-1"}, 50.0),
        ({"instance_id": "inst-other"}, 1.0),
        ({"instance_id": "stale-deleted-id"}, 1.0),
    ]
    with patch("app.api.compute.instance_metrics.query_instant_multi", new=AsyncMock(return_value=fallback)):
        response = await client.get("/api/v1/instances/metrics-summary-batch")
    assert response.status_code == 200
    instances = response.json()["instances"]
    assert set(instances) == {"inst-1"}
    assert instances["inst-1"]["cpu_avg"] == 0.0
    assert instances["inst-1"]["mem_avg"] == 50.0
    assert instances["inst-1"]["source"] == "mixed"
    assert instances["inst-1"]["stats"]["cpu"]["source"] == "gnocchi"
    assert instances["inst-1"]["stats"]["memory"]["source"] == "prometheus"
    assert "other-project" not in response.text
    project.assert_awaited_once()
    assert project.await_args.args[1] == _PROJECT_ID
    instance.assert_not_awaited()


@pytest.mark.anyio
async def test_project_native_coverage_survives_exporter_outage_and_unknown_memory_is_not_idle(client, native_metrics):
    from app.services.prom_query import PromUnavailable

    _, project = native_metrics
    project.return_value = {"status": "partial", "instances": {"inst-1": {"cpu": _native(0.0)}}}
    with patch(
        "app.api.compute.instance_metrics.query_instant_multi", new=AsyncMock(side_effect=PromUnavailable("down"))
    ):
        response = await client.get("/api/v1/instances/metrics-summary-batch")
    assert response.json()["monitoring_available"] is True
    row = response.json()["instances"]["inst-1"]
    assert row["cpu_avg"] == 0.0
    assert row["mem_avg"] is None
    assert row["underutilized"] is False


@pytest.mark.anyio
async def test_project_native_policy_denial_does_not_disable_exporter_monitoring(client, native_metrics):
    _, project = native_metrics
    project.return_value = {"status": "forbidden", "instances": {}}
    with patch("app.api.compute.instance_metrics.query_instant_multi", new=AsyncMock(return_value=_instant(50.0))):
        response = await client.get("/api/v1/instances/metrics-summary-batch")
    assert response.status_code == 200
    assert response.json()["monitoring_available"] is True
    row = response.json()["instances"]["inst-1"]
    assert row["cpu_avg"] == row["mem_avg"] == 50.0
    assert row["native_status"] == "forbidden"
    assert row["stats"]["cpu"]["native_status"] == "forbidden"


@pytest.mark.anyio
async def test_project_inventory_failure_prevents_unverified_native_query(client, native_metrics):
    _, project = native_metrics
    with patch(
        "app.api.compute.instance_metrics.nova.list_servers",
        side_effect=RuntimeError("https://user:password@nova.invalid/private-token"),
    ):
        response = await client.get("/api/v1/instances/metrics-summary-batch")
    assert response.status_code == 502
    project.assert_not_awaited()
    assert "password" not in response.text
    assert "private-token" not in response.text


@pytest.mark.anyio
@pytest.mark.parametrize("partial_metric", ["cpu", "memory"])
async def test_partial_low_usage_remains_visible_without_idle_or_resize_advice(client, native_metrics, partial_metric):
    instance, project = native_metrics
    metrics = {"cpu": _native(1.0, 3.0), "memory": _native(5.0, 10.0)}
    metrics[partial_metric]["status"] = "partial"
    instance.return_value = metrics
    project.return_value = {"status": "partial", "instances": {"inst-1": metrics}}
    with (
        patch("app.api.compute.instance_metrics.nova.get_server", return_value=_FAKE_INSTANCE),
        patch("app.api.compute.instance_metrics.nova.list_flavors") as flavors,
        patch("app.api.compute.instance_metrics.query_instant_multi", new=AsyncMock(return_value=[])),
    ):
        summary = await client.get("/api/v1/instances/inst-1/metrics-summary")
        batch = await client.get("/api/v1/instances/metrics-summary-batch")
    assert summary.status_code == batch.status_code == 200
    body = summary.json()
    assert body["monitoring_available"] is True
    assert body["stats"]["cpu"]["avg"] == 2.0
    assert body["stats"]["memory"]["avg"] == 7.5
    assert body["stats"][partial_metric]["status"] == "partial"
    assert body["recommendation"] is None
    flavors.assert_not_called()
    row = batch.json()["instances"]["inst-1"]
    assert row["cpu_avg"] == 2.0
    assert row["mem_avg"] == 7.5
    assert row["stats"][partial_metric]["status"] == "partial"
    assert row["underutilized"] is False


@pytest.mark.anyio
@pytest.mark.parametrize("authenticated_project_id", [None, "", "foreign-project"])
async def test_admin_selected_project_cannot_expand_actual_native_request_scope(
    admin_client, native_metrics, mock_conn, authenticated_project_id
):
    _, project = native_metrics
    mock_conn._afterglow_authenticated_project_id = authenticated_project_id
    project.return_value = {
        "status": "available",
        "instances": {"inst-1": {"cpu": _native(1.0), "memory": _native(5.0)}},
    }
    with patch("app.api.compute.instance_metrics.query_instant_multi", new=AsyncMock(return_value=_instant(50.0))):
        response = await admin_client.get("/api/v1/instances/metrics-summary-batch")
    assert response.status_code == 200
    project.assert_not_awaited()
    assert response.json()["monitoring_available"] is True
    row = response.json()["instances"]["inst-1"]
    assert row["cpu_avg"] == row["mem_avg"] == 50.0
    assert row["native_status"] == "forbidden"
    assert row["stats"]["cpu"]["source"] == "prometheus"
