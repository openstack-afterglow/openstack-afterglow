"""관리자 대시보드 전용 엔드포인트 (Phase 50c).

A-1: GET  /admin/notifications        — 6종 알림 요약
A-2: GET  /admin/instances/health     — 인스턴스 상태 이상 목록
A-4: POST /admin/instances/bulk-action — 배치 동작 (ActivityLog 자동 기록)
A-6: GET  /admin/floating-ips/pool-stats — FIP 풀별 통계
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    import openstack

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.common.activity_recorder import rec
from app.api.deps import CacheMode, cache_mode, get_os_conn, get_token_info, require_admin
from app.services.cache import cached_call, ttl_fast, ttl_normal
from app.services.image_refs import normalize_image_reference
from app.services.keystone import get_drover_proxy

_logger = logging.getLogger(__name__)
router = APIRouter()

BulkAction = Literal["start", "stop", "reboot", "hard-reboot", "snapshot"]


# ---------------------------------------------------------------------------
# A-1  GET /admin/notifications
# ---------------------------------------------------------------------------


@router.get("/notifications", dependencies=[Depends(require_admin)])
async def get_admin_notifications(
    conn: openstack.connection.Connection = Depends(get_os_conn),
    cm: CacheMode = Depends(cache_mode),
):
    """관리자 알림 6종 (오류 인스턴스 / 높은 CPU 호스트 / k3s 대기 등)."""
    notifications: list[dict] = []

    # 오류 인스턴스 수집 (all-tenants)
    try:

        def _error_servers():
            endpoint = conn.compute.get_endpoint()
            resp = conn.session.get(
                f"{endpoint}/servers/detail",
                params={"all_tenants": "1", "status": "ERROR", "limit": "50"},
            )
            return resp.json().get("servers", [])

        error_servers = await asyncio.to_thread(_error_servers)
        if error_servers:
            notifications.append(
                {
                    "type": "error",
                    "severity": "high",
                    "message": f"오류 상태 인스턴스 {len(error_servers)}개",
                    "count": len(error_servers),
                }
            )
    except Exception:
        _logger.debug("error_servers 조회 실패", exc_info=True)

    # 하이퍼바이저 가용 리소스 부족 경고
    try:

        def _hypervisors():
            hvs = list(conn.compute.hypervisors(details=True))
            low = []
            for h in hvs:
                total_ram = getattr(h, "memory_size", 0) or 0
                free_ram = getattr(h, "memory_free", 0) or 0
                if total_ram > 0 and (free_ram / total_ram) < 0.1:
                    low.append(getattr(h, "name", str(h.id)))
            return low

        low_ram_hosts = await cached_call(
            "afterglow:admin:notifications:low_ram",
            ttl_fast(),
            _hypervisors,
            enabled=cm.enabled,
            refresh=cm.refresh,
        )
        if low_ram_hosts:
            notifications.append(
                {
                    "type": "resource",
                    "severity": "warning",
                    "message": f"RAM 10% 미만 호스트 {len(low_ram_hosts)}개",
                    "count": len(low_ram_hosts),
                    "hosts": low_ram_hosts[:5],
                }
            )
    except Exception:
        _logger.debug("hypervisor 알림 조회 실패", exc_info=True)

    # K3s pending/error state is authoritative in Drover.
    try:
        from app.config import get_settings

        if get_settings().service_k3s_enabled:

            async def _k3s_pending():
                return await asyncio.to_thread(
                    get_drover_proxy(conn).admin_clusters,
                    status="CREATE_IN_PROGRESS,UPDATE_IN_PROGRESS,ERROR",
                )

            pending = await cached_call(
                "afterglow:admin:notifications:k3s_pending",
                ttl_normal(),
                _k3s_pending,
                enabled=cm.enabled,
                refresh=cm.refresh,
            )
            if pending:
                notifications.append(
                    {
                        "type": "k3s",
                        "severity": "info",
                        "message": f"대기/오류 k3s 클러스터 {len(pending)}개",
                        "count": len(pending),
                        "available": True,
                    }
                )
    except Exception:
        _logger.debug("Drover k3s 알림 조회 실패", exc_info=True)
        if get_settings().service_k3s_enabled:
            notifications.append(
                {
                    "type": "k3s",
                    "severity": "warning",
                    "message": "Drover 클러스터를 불러오지 못했습니다",
                    "count": 0,
                    "available": False,
                }
            )
    # FIP 풀 고갈 경고
    try:

        def _fip_pool():
            pools: dict[str, dict] = {}
            for ip in conn.network.ips(all_projects=True):
                pool = getattr(ip, "floating_network_id", "unknown")
                if pool not in pools:
                    pools[pool] = {"total": 0, "in_use": 0}
                pools[pool]["total"] += 1
                if ip.port_id:
                    pools[pool]["in_use"] += 1
            return [p for p in pools.values() if p["total"] > 0 and (p["in_use"] / p["total"]) > 0.9]

        exhausted = await cached_call(
            "afterglow:admin:notifications:fip_pool",
            ttl_normal(),
            _fip_pool,
            enabled=cm.enabled,
            refresh=cm.refresh,
        )
        if exhausted:
            notifications.append(
                {
                    "type": "network",
                    "severity": "warning",
                    "message": f"Floating IP 풀 90% 이상 소진 {len(exhausted)}개",
                    "count": len(exhausted),
                }
            )
    except Exception:
        _logger.debug("FIP 풀 알림 조회 실패", exc_info=True)

    return {"notifications": notifications, "total": len(notifications)}


# ---------------------------------------------------------------------------
# A-2  GET /admin/instances/health
# ---------------------------------------------------------------------------


def _is_gpu_flavor(flavor: dict) -> bool:
    """서버 응답의 embedded flavor dict 에서 GPU 여부 판별.

    마이크로버전 2.47+ 응답: original_name + extra_specs 포함.
    기본 2.1 응답: id + links 만 → id fallback.
    """
    extra_specs = flavor.get("extra_specs") or {}
    alias = extra_specs.get("pci_passthrough:alias", "")
    if alias:
        for entry in alias.split(","):
            entry = entry.strip()
            if ":" not in entry:
                continue
            dev, _num = entry.rsplit(":", 1)
            if "audio" in dev.lower():
                continue
            return True
    if "gpu" in (extra_specs.get(":category", "") or "").lower():
        return True
    name = (flavor.get("original_name") or flavor.get("id") or "").lower()
    return "gpu" in name or name.startswith("g1.")


@router.get("/instances/health", dependencies=[Depends(require_admin)])
async def get_instances_health(
    conn: openstack.connection.Connection = Depends(get_os_conn),
    cm: CacheMode = Depends(cache_mode),
):
    """전체 인스턴스 상태 집계 (total/active/error/with_alerts/gpu_count) + ERROR 목록."""
    try:

        def _collect():
            endpoint = conn.compute.get_endpoint()
            resp = conn.session.get(
                f"{endpoint}/servers/detail",
                params={"all_tenants": "1", "limit": "200"},
                headers={"OpenStack-API-Version": "compute 2.53"},
            )
            servers = resp.json().get("servers", [])

            total = len(servers)
            active_count = 0
            error_count = 0
            gpu_count = 0
            error_items: list[dict] = []

            for s in servers:
                status = (s.get("status") or "").upper()
                if status == "ACTIVE":
                    active_count += 1
                elif status == "ERROR":
                    error_count += 1
                    error_items.append(
                        {
                            "id": s["id"],
                            "name": s.get("name") or "",
                            "project_id": s.get("tenant_id") or "",
                            "host": s.get("OS-EXT-SRV-ATTR:host") or "",
                            "status": status,
                            "reason": "오류 상태",
                        }
                    )
                # SHELVED/SHELVED_OFFLOADED는 실제 호스트 할당이 없으므로 GPU 카운트 제외
                if _is_gpu_flavor(s.get("flavor") or {}) and status in (
                    "ACTIVE",
                    "SHUTOFF",
                    "PAUSED",
                    "SUSPENDED",
                    "RESIZE",
                ):
                    gpu_count += 1

            return {
                "total": total,
                "active": active_count,
                "error": error_count,
                "with_alerts": error_count,  # Prometheus 미사용 시 ERROR 수로 polyfill
                "gpu_count": gpu_count,
                "items": error_items,
                "count": len(error_items),
            }

        result = await cached_call(
            "afterglow:admin:instances_health",
            ttl_fast(),
            _collect,
            enabled=cm.enabled,
            refresh=cm.refresh,
        )
    except Exception:
        raise HTTPException(status_code=500, detail="인스턴스 상태 조회 실패")

    return result


# ---------------------------------------------------------------------------
# A-4  POST /admin/instances/bulk-action
# ---------------------------------------------------------------------------


class BulkActionRequest(BaseModel):
    instance_ids: list[str]
    action: BulkAction
    snapshot_name: str | None = None


@router.post("/instances/bulk-action", dependencies=[Depends(require_admin)])
async def bulk_instance_action(
    body: BulkActionRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    """여러 인스턴스에 동일 동작 적용. 각 동작당 ActivityLog 자동 기록."""
    if not body.instance_ids:
        raise HTTPException(status_code=400, detail="instance_ids가 비어 있습니다")
    if len(body.instance_ids) > 50:
        raise HTTPException(status_code=400, detail="한 번에 최대 50개까지 처리 가능합니다")

    results: list[dict] = []

    for instance_id in body.instance_ids:
        status = "success"
        error_msg = None
        try:
            await asyncio.to_thread(_apply_action, conn, instance_id, body.action, body.snapshot_name)
        except Exception as exc:
            status = "failed"
            error_msg = str(exc)
            _logger.warning("bulk-action %s 실패 instance=%s: %s", body.action, instance_id, exc)

        # ActivityLog 기록 (성공/실패 모두)
        await rec(
            token_info,
            conn,
            resource_type="instance",
            action=f"bulk_{body.action}",
            status=status,
            resource_id=instance_id,
            error_message=error_msg,
        )
        results.append({"id": instance_id, "status": status, "error": error_msg})

    success = sum(1 for r in results if r["status"] == "success")
    return {"results": results, "success": success, "failed": len(results) - success}


def _apply_action(
    conn: openstack.connection.Connection,
    instance_id: str,
    action: str,
    snapshot_name: str | None,
) -> None:
    server = conn.compute.get_server(instance_id)
    if action == "start":
        conn.compute.start_server(server)
    elif action == "stop":
        conn.compute.stop_server(server)
    elif action == "reboot":
        conn.compute.reboot_server(server, reboot_type="SOFT")
    elif action == "hard-reboot":
        conn.compute.reboot_server(server, reboot_type="HARD")
    elif action == "snapshot":
        name = normalize_image_reference(snapshot_name or f"snapshot-{instance_id[:8]}")
        conn.compute.create_server_image(server, name=name)
    else:
        raise ValueError(f"알 수 없는 action: {action}")


# ---------------------------------------------------------------------------
# A-6  GET /admin/floating-ips/pool-stats
# ---------------------------------------------------------------------------


@router.get("/floating-ips/pool-stats", dependencies=[Depends(require_admin)])
async def get_fip_pool_stats(
    conn: openstack.connection.Connection = Depends(get_os_conn),
    cm: CacheMode = Depends(cache_mode),
):
    """Floating IP 네트워크(풀)별 in_use / total / util% 통계."""
    try:

        def _collect():
            pools: dict[str, dict] = {}

            # 외부 네트워크 목록
            for net in conn.network.networks(is_router_external=True):
                pools[net.id] = {
                    "network_id": net.id,
                    "network_name": net.name or net.id,
                    "total": 0,
                    "in_use": 0,
                    "available": 0,
                }

            # FIP 수집 (all projects)
            for ip in conn.network.ips(all_projects=True):
                pool_id = getattr(ip, "floating_network_id", None)
                if not pool_id:
                    continue
                if pool_id not in pools:
                    pools[pool_id] = {
                        "network_id": pool_id,
                        "network_name": pool_id,
                        "total": 0,
                        "in_use": 0,
                        "available": 0,
                    }
                pools[pool_id]["total"] += 1
                if ip.port_id:
                    pools[pool_id]["in_use"] += 1

            for p in pools.values():
                p["available"] = p["total"] - p["in_use"]
                p["util_pct"] = round(p["in_use"] / p["total"] * 100, 1) if p["total"] > 0 else 0.0

            return list(pools.values())

        items = await cached_call(
            "afterglow:admin:fip_pool_stats",
            ttl_normal(),
            _collect,
            enabled=cm.enabled,
            refresh=cm.refresh,
        )
    except Exception:
        raise HTTPException(status_code=500, detail="FIP 풀 통계 조회 실패")

    return {"pools": items, "count": len(items)}
