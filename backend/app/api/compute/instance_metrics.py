"""Authorized instance telemetry, preferring native measurements per metric."""

from __future__ import annotations

import asyncio
import math
import re
import time
from typing import Literal, get_args

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.deps import get_os_conn, get_token_info
from app.services import native_telemetry, nova
from app.services.prom_query import (
    PromBadQuery,
    PromUnavailable,
    calc_step,
    is_safe_label_value,
    query_instant_multi,
    query_range,
)


class _PrivateMetricsRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def private_response(request: Request):
            try:
                response = await handler(request)
            except StarletteHTTPException as exc:
                exc.headers = {**(exc.headers or {}), "Cache-Control": "no-store"}
                raise
            except RequestValidationError as exc:
                response = await request_validation_exception_handler(request, exc)
            response.headers["Cache-Control"] = "no-store"
            return response

        return private_response


router = APIRouter(route_class=_PrivateMetricsRoute)

_RANGE_SECONDS: dict[str, int] = {
    "15m": 900,
    "1h": 3600,
    "6h": 21600,
    "24h": 86400,
    "7d": 604800,
}

MetricKey = Literal[
    "cpu",
    "memory",
    "network_rx",
    "network_tx",
    "disk_read",
    "disk_write",
    "gpu_util",
    "gpu_mem",
    "disk_read_iops",
    "disk_write_iops",
    "network_rx_packets",
    "network_tx_packets",
    "memory_resident",
    "disk_allocation",
    "memory_swap_in",
    "memory_swap_out",
]

_VALID_METRICS: frozenset[str] = frozenset(get_args(MetricKey))
_GPU_METRICS: frozenset[str] = frozenset({"gpu_util", "gpu_mem"})
_PROM_METRICS = frozenset({"cpu", "memory", "network_rx", "network_tx", "disk_read", "disk_write"}) | _GPU_METRICS
_UNITS = {
    "cpu": "%",
    "memory": "%",
    "network_rx": "B/s",
    "network_tx": "B/s",
    "disk_read": "B/s",
    "disk_write": "B/s",
    "gpu_util": "%",
    "gpu_mem": "%",
    "disk_read_iops": "request/s",
    "disk_write_iops": "request/s",
    "network_rx_packets": "packet/s",
    "network_tx_packets": "packet/s",
    "memory_resident": "MiB",
    "disk_allocation": "B",
    "memory_swap_in": "MiB/s",
    "memory_swap_out": "MiB/s",
}
_NATIVE_STATUSES = frozenset({"available", "partial", "not_configured", "forbidden", "unavailable", "not_collected"})
_READABLE_STATUSES = frozenset({"available", "partial", "not_collected"})

# metrics-summary에서 집계할 메트릭 목록 (네트워크 제외)
_SUMMARY_METRICS: tuple[str, ...] = ("cpu", "memory", "disk_read", "disk_write")

# 권장 플레이버 산출 시 최대 사용량 대비 여유율
_RECOMMEND_HEADROOM: float = 1.3


def _build_expr(metric: str, instance_id: str) -> str:
    # kolla-ansible OpenStack SD 가 부여한 라벨 — instance_id (UUID) 가 unique key.
    # job 필터를 두지 않아 internal/external 두 job 모두 커버한다.
    sel = f'instance_id="{instance_id}"'
    exclude_ifaces = r"lo|veth.*|docker.*|cni.*"
    if metric == "cpu":
        return f'100 - (avg by (instance_id) (rate(node_cpu_seconds_total{{{sel},mode="idle"}}[2m])) * 100)'
    if metric == "memory":
        return f"(1 - node_memory_MemAvailable_bytes{{{sel}}} / node_memory_MemTotal_bytes{{{sel}}}) * 100"
    if metric == "network_rx":
        return f'sum by (instance_id) (rate(node_network_receive_bytes_total{{{sel},device!~"{exclude_ifaces}"}}[2m]))'
    if metric == "network_tx":
        return f'sum by (instance_id) (rate(node_network_transmit_bytes_total{{{sel},device!~"{exclude_ifaces}"}}[2m]))'
    if metric == "disk_read":
        return f"sum by (instance_id) (rate(node_disk_read_bytes_total{{{sel}}}[2m]))"
    if metric == "disk_write":
        return f"sum by (instance_id) (rate(node_disk_written_bytes_total{{{sel}}}[2m]))"
    if metric == "gpu_util":
        return f"avg by (instance_id) (DCGM_FI_DEV_GPU_UTIL{{{sel}}})"
    if metric == "gpu_mem":
        return f"avg by (instance_id) (DCGM_FI_DEV_FB_USED{{{sel}}} / DCGM_FI_DEV_FB_TOTAL{{{sel}}}) * 100"
    raise ValueError(f"unknown metric: {metric}")


def _build_libvirt_expr(metric: str, instance_id: str) -> str | None:
    """libvirt-exporter 기반 폴백 PromQL. node_exporter 미노출 인스턴스(테넌트망 격리)용.

    domain 라벨(instance-XXXXXXXX) → libvirt_domain_openstack_info 조인 → instance_id(UUID).
    GPU 메트릭은 DCGM 전용이므로 None 반환.
    """
    iid = f'instance_id="{instance_id}"'
    join = f"* on (instance, domain) group_left(instance_id) libvirt_domain_openstack_info{{{iid}}}"
    if metric == "cpu":
        # cpu_time_seconds 는 누적 counter — vCPU 수로 나눠 0-100% 정규화
        return (
            f"(sum by (instance_id) (rate(libvirt_domain_info_cpu_time_seconds_total[2m]) {join})"
            f" / sum by (instance_id) (libvirt_domain_info_virtual_cpus {join})) * 100"
        )
    if metric == "memory":
        # virtio-balloon 통계가 활성화된 인스턴스에서만 유효
        return f"avg by (instance_id) (libvirt_domain_memory_stats_used_percent {join})"
    if metric == "network_rx":
        return f"sum by (instance_id) (rate(libvirt_domain_interface_stats_receive_bytes_total[2m]) {join})"
    if metric == "network_tx":
        return f"sum by (instance_id) (rate(libvirt_domain_interface_stats_transmit_bytes_total[2m]) {join})"
    if metric == "disk_read":
        return f"sum by (instance_id) (rate(libvirt_domain_block_stats_read_bytes_total[2m]) {join})"
    if metric == "disk_write":
        return f"sum by (instance_id) (rate(libvirt_domain_block_stats_write_bytes_total[2m]) {join})"
    return None  # gpu_util, gpu_mem — DCGM 전용, libvirt 대체 불가


def _resolve_server(conn, instance_id: str):
    try:
        return nova.get_server(conn, instance_id)
    except Exception:
        raise HTTPException(status_code=404, detail="인스턴스를 찾을 수 없습니다")


def _authorize(server, token_info: dict) -> None:
    caller_project = token_info.get("project_id", "")
    is_admin = token_info.get("is_system_admin", False)
    if not is_admin and server.project_id != caller_project:
        raise HTTPException(status_code=403, detail="해당 인스턴스에 접근 권한이 없습니다")


def _metric_instance_id(server) -> str:
    instance_id = getattr(server, "id", None)
    if not is_safe_label_value(instance_id):
        raise HTTPException(status_code=502, detail="인스턴스 메트릭 식별자가 유효하지 않습니다")
    return instance_id


def _is_gpu(server) -> bool:
    return (server.flavor_name or "").lower().startswith("gpu.")


def _finite_series(series: list[dict]) -> list[dict]:
    return [
        {"ts": point["ts"], "value": point["value"]}
        for point in series
        if isinstance(point.get("ts"), (int, float))
        and math.isfinite(point["ts"])
        and isinstance(point.get("value"), (int, float))
        and math.isfinite(point["value"])
    ]


def _native_result(metric: str, result: dict | None, *, default_status: str = "not_collected") -> dict:
    """Keep provider failures as safe codes, never upstream exception text."""
    result = result or {}
    status = result.get("status", default_status)
    if status not in _NATIVE_STATUSES:
        status = "unavailable"
    series = _finite_series(result.get("series", [])) if status in {"available", "partial"} else []
    if not series and status in {"available", "partial"}:
        status = "not_collected"
    return {
        "series": series,
        "source": "gnocchi",
        "unit": _UNITS[metric],
        "status": status,
        "native_status": status,
        "error": f"native_{status}" if result.get("error") else None,
    }


async def _native_instance_series(conn, server, metrics: list[str], *, start_ts: int, end_ts: int, step_s: int) -> dict:
    try:
        return await native_telemetry.instance_series(
            conn, server, metrics, start_ts=start_ts, end_ts=end_ts, step_s=step_s
        )
    except Exception:
        # Native discovery/policy failure must not disable independent exporters.
        return {metric: {"status": "unavailable", "error": "native_unavailable"} for metric in metrics}


async def _metric_series(
    metric: str, instance_id: str, native: dict | None, *, start_ts: int, end_ts: int, step_s: int
) -> dict:
    result = _native_result(metric, native)
    if result["series"] or metric not in _PROM_METRICS:
        return result
    try:
        series = await query_range(_build_expr(metric, instance_id), start_ts=start_ts, end_ts=end_ts, step_s=step_s)
        series = _finite_series(series)
        if not series:
            lv_expr = _build_libvirt_expr(metric, instance_id)
            if lv_expr:
                series = await query_range(lv_expr, start_ts=start_ts, end_ts=end_ts, step_s=step_s)
                series = _finite_series(series)
        return {
            **result,
            "series": series,
            "source": "prometheus" if series else None,
            "status": "available" if series else "not_collected",
            "error": None,
        }
    except (PromUnavailable, PromBadQuery) as exc:
        return {
            **result,
            "series": [],
            "source": "gnocchi" if result["native_status"] in _READABLE_STATUSES else None,
            "status": "not_collected" if result["native_status"] in _READABLE_STATUSES else "unavailable",
            "error": "prometheus_unavailable" if isinstance(exc, PromUnavailable) else "bad_query",
        }


# ---------------------------------------------------------------------------
# 단일 메트릭 엔드포인트 (deprecated — batch 엔드포인트 사용 권장)
# ---------------------------------------------------------------------------


@router.get("/{instance_id}/metrics")
async def get_instance_metrics(
    instance_id: str,
    metric: MetricKey = Query(...),
    range: Literal["15m", "1h", "6h", "24h", "7d"] = Query("1h"),
    conn=Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
) -> dict:
    """Return one native-first metric with exporter fallback and provenance."""
    server = _resolve_server(conn, instance_id)
    _authorize(server, token_info)
    metric_instance_id = _metric_instance_id(server)

    if metric in _GPU_METRICS and not _is_gpu(server):
        raise HTTPException(status_code=400, detail="GPU 메트릭은 GPU 인스턴스에서만 조회 가능합니다")

    range_s = _RANGE_SECONDS[range]
    end_ts = int(time.time())
    start_ts = end_ts - range_s
    step_s = calc_step(range_s)

    native = await _native_instance_series(conn, server, [metric], start_ts=start_ts, end_ts=end_ts, step_s=step_s)
    result = await _metric_series(
        metric, metric_instance_id, native.get(metric), start_ts=start_ts, end_ts=end_ts, step_s=step_s
    )
    if result["status"] == "unavailable" and result["error"] == "prometheus_unavailable":
        raise HTTPException(status_code=503, detail="prometheus_unavailable")
    if result["status"] == "unavailable" and result["error"] == "bad_query":
        raise HTTPException(status_code=500, detail="bad_query")
    return {"instance_id": instance_id, "metric": metric, "range": range, **result}


# ---------------------------------------------------------------------------
# Batch 메트릭 엔드포인트 — Nova/권한 1회, 메트릭별 폴백
# ---------------------------------------------------------------------------


@router.get("/{instance_id}/metrics-batch")
async def get_instance_metrics_batch(
    instance_id: str,
    metrics: str = Query(..., description="쉼표 구분 메트릭 키: cpu,memory,network_rx,..."),
    range: Literal["15m", "1h", "6h", "24h", "7d"] = Query("1h"),
    conn=Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
) -> dict:
    """Resolve/authorize once; choose a single provider independently per metric."""
    keys = list(dict.fromkeys(k.strip() for k in metrics.split(",") if k.strip()))
    if not keys:
        raise HTTPException(status_code=422, detail="metrics 파라미터가 비어있습니다")
    invalid = [k for k in keys if k not in _VALID_METRICS]
    if invalid:
        raise HTTPException(status_code=422, detail=f"알 수 없는 메트릭: {invalid}")

    server = _resolve_server(conn, instance_id)
    _authorize(server, token_info)
    metric_instance_id = _metric_instance_id(server)

    # GPU 메트릭은 GPU 인스턴스만 — batch 에서는 422 대신 silent skip
    if not _is_gpu(server):
        keys = [k for k in keys if k not in _GPU_METRICS]

    range_s = _RANGE_SECONDS[range]
    end_ts = int(time.time())
    start_ts = end_ts - range_s
    step_s = calc_step(range_s)

    native = (
        await _native_instance_series(conn, server, keys, start_ts=start_ts, end_ts=end_ts, step_s=step_s)
        if keys
        else {}
    )
    results = await asyncio.gather(
        *(
            _metric_series(k, metric_instance_id, native.get(k), start_ts=start_ts, end_ts=end_ts, step_s=step_s)
            for k in keys
        )
    )
    return {
        "instance_id": instance_id,
        "range": range,
        "metrics": dict(zip(keys, results, strict=True)),
    }


# ---------------------------------------------------------------------------
# 통계 요약 헬퍼
# ---------------------------------------------------------------------------


def _subquery_expr(stat: str, base_expr: str, range_s: int, step_s: int) -> str:
    """avg/min/max_over_time 서브쿼리 instant PromQL 생성."""
    return f"{stat}_over_time(({base_expr})[{range_s}s:{step_s}s])"


async def _fetch_stat(base_expr: str, range_s: int, step_s: int) -> dict[str, float | None]:
    """avg/min/max 3종 병렬 instant 쿼리 → {avg, min, max: float|None}."""

    async def _one(stat: str) -> float | None:
        results = await query_instant_multi(_subquery_expr(stat, base_expr, range_s, step_s))
        value = results[0][1] if results else None
        return value if value is not None and math.isfinite(value) else None

    avg_v, min_v, max_v = await asyncio.gather(_one("avg"), _one("min"), _one("max"))
    return {"avg": avg_v, "min": min_v, "max": max_v}


async def _fetch_stat_with_fallback(
    metric: str, instance_id: str, range_s: int, step_s: int
) -> dict[str, float | None]:
    """node_exporter 우선, avg=None이면 libvirt 폴백."""
    result = await _fetch_stat(_build_expr(metric, instance_id), range_s, step_s)
    if result["avg"] is None:
        lv_expr = _build_libvirt_expr(metric, instance_id)
        if lv_expr:
            result = await _fetch_stat(lv_expr, range_s, step_s)
    return result


def _series_stats(result: dict) -> dict:
    values = [point["value"] for point in result["series"]]
    return {
        "avg": sum(values) / len(values) if values else None,
        "min": min(values) if values else None,
        "max": max(values) if values else None,
        **{key: result[key] for key in ("source", "unit", "status", "native_status", "error")},
    }


async def _metric_stats(metric: str, instance_id: str, native: dict | None, range_s: int, step_s: int) -> dict:
    result = _native_result(metric, native)
    if result["series"]:
        return _series_stats(result)
    try:
        stats = await _fetch_stat_with_fallback(metric, instance_id, range_s, step_s)
        measured = stats["avg"] is not None
        return {
            **stats,
            "source": "prometheus" if measured else None,
            "unit": _UNITS[metric],
            "status": "available" if measured else "not_collected",
            "native_status": result["native_status"],
            "error": None,
        }
    except (PromUnavailable, PromBadQuery) as exc:
        return {
            **_series_stats(result),
            "source": "gnocchi" if result["native_status"] in _READABLE_STATUSES else None,
            "status": "not_collected" if result["native_status"] in _READABLE_STATUSES else "unavailable",
            "error": "prometheus_unavailable" if isinstance(exc, PromUnavailable) else "bad_query",
        }


# ---------------------------------------------------------------------------
# 목록 배지용 일괄 요약 엔드포인트 (literal 경로 — instances_router 보다 먼저 등록됨)
# ---------------------------------------------------------------------------


@router.get("/metrics-summary-batch")
async def get_metrics_summary_batch(
    conn=Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
) -> dict:
    """Project-scoped native summaries with bounded project-wide PromQL fallback."""
    project_id = token_info.get("project_id", "")

    # PromQL 라벨 값 주입 방어 — project_id 형식 화이트리스트 검증
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", project_id):
        return {"range": "7d", "monitoring_available": False, "instances": {}}

    range_s = _RANGE_SECONDS["7d"]
    step_s = calc_step(range_s)
    # Canonical Nova ownership is established before any native resource search.
    try:
        servers = nova.list_servers(conn)
    except Exception:
        raise HTTPException(status_code=502, detail="instance_inventory_unavailable")
    authorized_ids = {
        server.id for server in servers if server.project_id == project_id and is_safe_label_value(server.id)
    }
    if not authorized_ids:
        return {"range": "7d", "monitoring_available": False, "instances": {}}
    end_ts = int(time.time())
    if getattr(conn, "_afterglow_authenticated_project_id", None) != project_id:
        # An admin/system credential must not enumerate a selected foreign project.
        # Keep the independently authorized project exporter fallback available.
        native = {"status": "forbidden", "instances": {}}
    else:
        try:
            native = await native_telemetry.project_series(
                conn,
                project_id,
                ["cpu", "memory"],
                start_ts=end_ts - range_s,
                end_ts=end_ts,
                step_s=step_s,
            )
        except Exception:
            native = {"status": "unavailable", "instances": {}}
    native_status = native.get("status", "unavailable")
    if native_status not in _NATIVE_STATUSES:
        native_status = "unavailable"
    monitoring_available = native_status in _READABLE_STATUSES
    missing_status = native_status if native_status not in {"available", "partial"} else "not_collected"
    native_instances = native.get("instances", {})
    summaries = {
        iid: {
            metric: _series_stats(
                _native_result(metric, native_instances.get(iid, {}).get(metric), default_status=missing_status)
            )
            for metric in ("cpu", "memory")
        }
        for iid in authorized_ids
    }
    pid = project_id

    cpu_expr_node = (
        f"avg_over_time((100 - avg by (instance_id) "
        f'(rate(node_cpu_seconds_total{{project_id="{pid}",mode="idle"}}[2m])) * 100)'
        f"[{range_s}s:{step_s}s])"
    )
    mem_expr_node = (
        f'avg_over_time(((1 - node_memory_MemAvailable_bytes{{project_id="{pid}"}}'
        f' / node_memory_MemTotal_bytes{{project_id="{pid}"}}) * 100)'
        f"[{range_s}s:{step_s}s])"
    )
    cpu_expr_lv = (
        f"avg_over_time(((sum by (instance_id) (rate(libvirt_domain_info_cpu_time_seconds_total[2m])"
        f' * on (instance, domain) group_left(instance_id) libvirt_domain_openstack_info{{project_id="{pid}"}}))'
        f" / (sum by (instance_id) (libvirt_domain_info_virtual_cpus"
        f' * on (instance, domain) group_left(instance_id) libvirt_domain_openstack_info{{project_id="{pid}"}})))'
        f" * 100)[{range_s}s:{step_s}s])"
    )
    mem_expr_lv = (
        f"avg_over_time((avg by (instance_id) (libvirt_domain_memory_stats_used_percent"
        f' * on (instance, domain) group_left(instance_id) libvirt_domain_openstack_info{{project_id="{pid}"}})'
        f")[{range_s}s:{step_s}s])"
    )

    async def _fallback(metric: str, node_expr: str, lv_expr: str) -> None:
        nonlocal monitoring_available
        missing = [iid for iid in authorized_ids if summaries[iid][metric]["avg"] is None]
        if not missing:
            return

        # Always bounded by metric/provider count, never by number of servers.
        async def _query(expr: str) -> tuple[list, str | None]:
            try:
                return await query_instant_multi(expr), None
            except (PromUnavailable, PromBadQuery) as exc:
                return [], "prometheus_unavailable" if isinstance(exc, PromUnavailable) else "bad_query"

        (node, node_error), (libvirt, lv_error) = await asyncio.gather(_query(node_expr), _query(lv_expr))
        monitoring_available = monitoring_available or node_error is None or lv_error is None
        measured = {}
        for labels, value in [*node, *libvirt]:
            iid = labels.get("instance_id")
            if iid in authorized_ids and math.isfinite(value):
                measured.setdefault(iid, value)  # node wins, including a real zero
        for iid in missing:
            value = measured.get(iid)
            native_readable = summaries[iid][metric]["native_status"] in _READABLE_STATUSES
            readable = native_readable or node_error is None or lv_error is None
            summaries[iid][metric].update(
                {
                    "avg": value,
                    "source": "prometheus" if value is not None else "gnocchi" if native_readable else None,
                    "status": "available" if value is not None else "not_collected" if readable else "unavailable",
                    "error": None if value is not None else node_error or lv_error,
                }
            )

    await asyncio.gather(
        _fallback("cpu", cpu_expr_node, cpu_expr_lv),
        _fallback("memory", mem_expr_node, mem_expr_lv),
    )
    instances = {}
    for iid, stats in summaries.items():
        cpu_avg, mem_avg = stats["cpu"]["avg"], stats["memory"]["avg"]
        if cpu_avg is None and mem_avg is None:
            continue
        sources = {stat["source"] for stat in stats.values() if stat["avg"] is not None}
        instances[iid] = {
            "cpu_avg": cpu_avg,
            "mem_avg": mem_avg,
            "underutilized": (
                stats["cpu"]["status"] == "available"
                and stats["memory"]["status"] == "available"
                and cpu_avg is not None
                and mem_avg is not None
                and (cpu_avg < 10 or mem_avg < 20)
            ),
            "source": next(iter(sources)) if len(sources) == 1 else "mixed",
            "native_status": native_status,
            "stats": stats,
        }
    return {"range": "7d", "monitoring_available": monitoring_available, "instances": instances}


# ---------------------------------------------------------------------------
# 인스턴스별 통계 요약 + 리사이즈 권장
# ---------------------------------------------------------------------------


@router.get("/{instance_id}/metrics-summary")
async def get_instance_metrics_summary(
    instance_id: str,
    range: Literal["15m", "1h", "6h", "24h", "7d"] = Query("7d"),
    conn=Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
) -> dict:
    """인스턴스 리소스 사용량 통계(min/avg/max) + 저사용 리사이즈 권장.

    반환: {
      instance_id, range, monitoring_available,
      stats: { cpu/memory/disk_read/disk_write: { min, avg, max } },
      recommendation: { underutilized, reason, current_flavor, suggested_flavor } | null
    }
    """
    server = _resolve_server(conn, instance_id)
    _authorize(server, token_info)
    metric_instance_id = _metric_instance_id(server)

    range_s = _RANGE_SECONDS[range]
    step_s = calc_step(range_s)

    end_ts = int(time.time())
    native = await _native_instance_series(
        conn, server, list(_SUMMARY_METRICS), start_ts=end_ts - range_s, end_ts=end_ts, step_s=step_s
    )
    stat_results = await asyncio.gather(
        *(_metric_stats(metric, metric_instance_id, native.get(metric), range_s, step_s) for metric in _SUMMARY_METRICS)
    )
    stats = dict(zip(_SUMMARY_METRICS, stat_results, strict=True))
    monitoring_available = any(
        stat["status"] in _READABLE_STATUSES or stat["native_status"] in _READABLE_STATUSES for stat in stats.values()
    )

    # 권장 판단 (GPU 인스턴스 제외)
    recommendation = None
    if not _is_gpu(server):
        cpu_avg = stats["cpu"]["avg"]
        mem_avg = stats["memory"]["avg"]

        # Incomplete capacity coverage can understate usage even with surviving samples.
        if (
            stats["cpu"]["status"] == "available"
            and stats["memory"]["status"] == "available"
            and cpu_avg is not None
            and mem_avg is not None
        ):
            underutilized = cpu_avg < 10 or mem_avg < 20
            if underutilized:
                reason_parts = []
                if cpu_avg is not None and cpu_avg < 10:
                    reason_parts.append("cpu_avg<10")
                if mem_avg is not None and mem_avg < 20:
                    reason_parts.append("mem_avg<20")

                all_flavors = nova.list_flavors(conn)
                cur_flavor = next((f for f in all_flavors if f.id == server.flavor_id), None)

                current_flavor_info = None
                suggested_flavor_info = None

                if cur_flavor:
                    current_flavor_info = {
                        "id": cur_flavor.id,
                        "name": cur_flavor.name,
                        "vcpus": cur_flavor.vcpus,
                        "ram": cur_flavor.ram,
                        "disk": cur_flavor.disk,
                    }

                    cpu_max = stats["cpu"]["max"]
                    mem_max = stats["memory"]["max"]

                    # max 통계 없으면 추천 플레이버를 산출할 수 없음 (권장 문구만)
                    if cpu_max is not None and mem_max is not None:
                        need_vcpus = max(
                            1,
                            math.ceil(cur_flavor.vcpus * cpu_max / 100 * _RECOMMEND_HEADROOM),
                        )
                        need_ram_mb = max(
                            512,
                            math.ceil(cur_flavor.ram * mem_max / 100 * _RECOMMEND_HEADROOM),
                        )
                        candidates = [
                            f
                            for f in all_flavors
                            if not f.is_gpu
                            and f.disk >= cur_flavor.disk  # Nova resize: 디스크 축소 불가
                            and f.vcpus <= cur_flavor.vcpus
                            and f.ram <= cur_flavor.ram
                            and (f.vcpus < cur_flavor.vcpus or f.ram < cur_flavor.ram)
                            and f.vcpus >= need_vcpus
                            and f.ram >= need_ram_mb
                        ]
                        if candidates:
                            best = min(candidates, key=lambda f: (f.vcpus, f.ram, f.disk))
                            suggested_flavor_info = {
                                "id": best.id,
                                "name": best.name,
                                "vcpus": best.vcpus,
                                "ram": best.ram,
                                "disk": best.disk,
                            }

                recommendation = {
                    "underutilized": True,
                    "reason": ",".join(reason_parts),
                    "current_flavor": current_flavor_info,
                    "suggested_flavor": suggested_flavor_info,
                }
            else:
                recommendation = {
                    "underutilized": False,
                    "reason": None,
                    "current_flavor": None,
                    "suggested_flavor": None,
                }

    return {
        "instance_id": instance_id,
        "range": range,
        "monitoring_available": monitoring_available,
        "stats": stats if monitoring_available else {},
        "recommendation": recommendation,
    }
