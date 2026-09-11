from __future__ import annotations

import asyncio
import itertools
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

import httpx
from drover_sdk import register as register_drover
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.common.activity_recorder import rec
from app.api.deps import CacheMode, cache_mode, get_os_conn, get_token_info, require_admin
from app.config import get_settings
from app.models.storage import (
    AdminNetworkDetail,
    AdminSubnetDetail,
    AdminTopologyData,
    FileStorageDeleteDiagnostic,
    FileStorageForceDeleteResult,
    FileStorageInfo,
    TopologyInstance,
    VolumeDeleteDiagnostic,
    VolumeDeleteRecoveryResult,
)
from app.services import (
    instance_recovery,
    keystone,
    library_builder,
    manila,
    neutron,
    nova,
    trove,
    volume_delete_recovery,
)
from app.services import libraries as lib_svc
from app.services.cache import cached_call, invalidate, ttl_fast, ttl_normal, ttl_slow
from app.services.cache import invalidation as cache_invalidation
from app.services.octavia import get_topology_lbs

# FastAPI-free 인벤토리 유틸리티로 이동됨 — admin.py 내부 호출 + 하위 호환 재export.
from app.services.openstack_inventory import _fetch_hypervisors_raw
from app.utils.version import read_app_version

if TYPE_CHECKING:
    import openstack

_logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/file-storage", response_model=list[FileStorageInfo], dependencies=[Depends(require_admin)])
async def list_admin_file_storages(conn: openstack.connection.Connection = Depends(get_os_conn)):
    """모든 Union 관련 파일 스토리지 목록 (prebuilt + dynamic)."""
    return manila.list_file_storages(conn)


@router.post("/file-storage/build", status_code=202, dependencies=[Depends(require_admin)])
async def trigger_build(
    library_id: str,
    auto_install: bool = Query(False, description="Cloud-init VM으로 자동 패키지 설치"),
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """
    사전 빌드 파일 스토리지 생성 트리거.
    auto_install=true: Cloud-init VM으로 자동 패키지 설치 (빌더 설정 필요)
    auto_install=false: 빈 파일 스토리지 생성만 (수동 설치 필요)
    """
    settings = get_settings()
    try:
        lib = lib_svc.get_by_id(library_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"알 수 없는 라이브러리: {library_id}")

    existing = manila.list_file_storages(
        conn,
        metadata_filter={
            "union_type": "prebuilt",
            "union_library": library_id,
        },
    )
    if existing:
        raise HTTPException(status_code=409, detail=f"이미 존재하는 사전 빌드 파일 스토리지: {existing[0].id}")

    if auto_install:
        try:
            result = await library_builder.queue_build(library_id)
            return result
        except RuntimeError as e:
            msg = str(e)
            status_code = 409 if "이미" in msg else 400
            raise HTTPException(status_code=status_code, detail=msg)

    file_storage = manila.create_file_storage(
        conn,
        name=f"union-prebuilt-{library_id}",
        size_gb=20,
        share_network_id=settings.os_manila_share_network_id,
        share_type=settings.os_manila_share_type,
        metadata={
            "union_type": "prebuilt",
            "union_library": library_id,
            "union_version": lib.version,
            "union_status": "building",
        },
    )
    return {"file_storage_id": file_storage.id, "status": "building", "library": library_id}


@router.get("/file-storage/builds", dependencies=[Depends(require_admin)])
async def list_active_builds():
    """빌드 목록 조회 (DB 기반, 인메모리 캐시 병합)."""
    from app.database import get_session_factory, is_db_available

    result: list[dict] = []
    if is_db_available():
        try:
            from sqlalchemy import select

            from app.models.db import LibraryBuild

            factory = get_session_factory()
            if factory:
                async with factory() as session:
                    rows = (
                        (await session.execute(select(LibraryBuild).order_by(LibraryBuild.created_at.desc()).limit(20)))
                        .scalars()
                        .all()
                    )
                    for r in rows:
                        result.append(
                            {
                                "id": r.id,
                                "library_id": r.library_id,
                                "file_storage_id": r.file_storage_id,
                                "server_id": r.server_id,
                                "status": r.status,
                                "progress_step": r.progress_step,
                                "progress_pct": r.progress_pct,
                                "error_message": r.error_message,
                                "started_at": r.started_at.isoformat() + "Z" if r.started_at else None,
                                "completed_at": r.completed_at.isoformat() + "Z" if r.completed_at else None,
                            }
                        )
        except Exception:
            pass
    if not result:
        # DB 사용 불가 시 인메모리 폴백
        return library_builder.get_active_builds()
    return result


# ---------------------------------------------------------------------------
# 관리자 전용 엔드포인트
# ---------------------------------------------------------------------------


def _fetch_overview_hypervisors(conn) -> dict:
    """하이퍼바이저 집계 데이터 수집."""
    try:
        data = _fetch_hypervisors_raw(conn)
        return {
            "host_count": len(data) or 1,
            "used_vcpus": sum(h.get("vcpus_used", 0) or 0 for h in data),
            "total_ram_mb": sum(h.get("memory_mb", 0) or 0 for h in data),
            "used_ram_mb": sum(h.get("memory_mb_used", 0) or 0 for h in data),
            "running_vms": sum(h.get("running_vms", 0) or 0 for h in data),
            "total_vcpus": sum(h.get("vcpus", 0) or 0 for h in data),
        }
    except Exception:
        _logger.warning("하이퍼바이저 집계 실패", exc_info=True)
        return {
            "host_count": 0,
            "used_vcpus": 0,
            "total_ram_mb": 0,
            "used_ram_mb": 0,
            "running_vms": 0,
            "total_vcpus": 0,
        }


def _fetch_overview_disk(conn) -> dict:
    """클러스터 등록 Cinder 풀 총용량 vs (볼륨 + 이미지) 사용량."""
    from app.services.cinder import list_storage_pools
    from app.services.glance import get_total_image_bytes

    total_disk = 0.0
    try:
        for p in list_storage_pools(conn):
            total_disk += p.get("total_capacity_gb", 0) or 0
    except Exception:
        pass

    used_disk = 0.0
    try:
        for v in conn.block_storage.volumes(all_projects=True):
            used_disk += v.size or 0
    except Exception:
        pass

    try:
        used_disk += round(get_total_image_bytes(conn) / (1024**3), 2)
    except Exception:
        pass

    return {"used_disk": round(used_disk, 2), "total_disk": round(total_disk, 2)}


def _fetch_overview_placement(conn) -> dict:
    """Placement API에서 물리 코어 수 및 allocation_ratio 수집."""
    physical_vcpus = 0
    allowed_vcpus_total = 0
    try:
        placement_ep = conn.placement.get_endpoint()
        rps_resp = conn.session.get(f"{placement_ep}/resource_providers")
        rps = rps_resp.json().get("resource_providers", [])
        for rp in rps:
            inv_resp = conn.session.get(f"{placement_ep}/resource_providers/{rp['uuid']}/inventories")
            vcpu_inv = inv_resp.json().get("inventories", {}).get("VCPU", {})
            inv_total = vcpu_inv.get("total", 0)
            inv_ratio = vcpu_inv.get("allocation_ratio", 1.0)
            physical_vcpus += inv_total
            allowed_vcpus_total += int(inv_total * inv_ratio)
    except Exception:
        _logger.warning("Placement API CPU 조회 실패", exc_info=True)
    return {"physical_vcpus": physical_vcpus, "allowed_vcpus": allowed_vcpus_total}


def _fetch_overview_servers(conn) -> dict:
    """Nova 서버 목록에서 GPU 인스턴스 수 + 상태별 집계."""
    gpu_instances = 0
    instance_stats = {"total": 0, "active": 0, "shutoff": 0, "error": 0, "other": 0}
    try:
        _ep = conn.compute.get_endpoint()
        _params = {"all_tenants": "1", "limit": "1000"}
        _resp = conn.session.get(
            f"{_ep}/servers/detail",
            params=_params,
            headers={"OpenStack-API-Version": "compute 2.53"},
        )
        for s in _resp.json().get("servers", []):
            flavor = s.get("flavor") or {}
            fname = (flavor.get("original_name") or flavor.get("id") or "").lower()
            instance_stats["total"] += 1
            st = (s.get("status") or "").upper()
            if st == "ACTIVE":
                instance_stats["active"] += 1
            elif st == "SHUTOFF":
                instance_stats["shutoff"] += 1
            elif st == "ERROR":
                instance_stats["error"] += 1
            else:
                instance_stats["other"] += 1
            # SHELVED/SHELVED_OFFLOADED는 실제 호스트 할당이 없으므로 GPU 사용량에서 제외
            if "gpu" in fname and st in ("ACTIVE", "SHUTOFF", "PAUSED", "SUSPENDED", "RESIZE"):
                gpu_instances += 1
    except Exception:
        _logger.warning("서버 집계 실패", exc_info=True)
    return {"gpu_instances": gpu_instances, "instance_stats": instance_stats}


def _fetch_overview_containers(conn) -> int:
    """Zun 컨테이너 수 수집."""
    if not get_settings().service_zun_enabled:
        return 0
    try:
        from app.services.zun import list_containers_admin

        return len(list_containers_admin(conn))
    except Exception:
        return 0


def _fetch_overview_file_storage(conn) -> int:
    """Manila 파일 스토리지 수 수집."""
    if not get_settings().service_manila_enabled:
        return 0
    try:
        return len(manila.list_file_storages(conn, all_tenants=True))
    except Exception:
        return 0


def _fetch_overview_database_instances(conn) -> int:
    """Trove DB 인스턴스 수 수집."""
    if not get_settings().service_trove_enabled:
        return 0
    try:
        from app.services.trove import count_instances

        return count_instances(conn)
    except Exception:
        return 0


def _fetch_overview_object_storage(conn) -> int:
    """Swift 오브젝트 스토리지 컨테이너 수 수집 — admin scope cross-project 합산.

    swift 계정은 프로젝트별로 분리되므로 admin 본인 프로젝트의 conn.object_store만
    보면 다른 프로젝트의 버킷이 누락된다. admin 토큰으로 fan-out 해서 모든 프로젝트의
    버킷 수를 합산해야 admin overview 의 의미와 맞다.
    """
    if not get_settings().service_swift_enabled:
        return 0
    try:
        from app.services.swift import count_containers_all_projects

        admin_token = getattr(conn, "_afterglow_token", "") or ""
        if not admin_token:
            return 0
        return count_containers_all_projects(admin_token)
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# 통합 모니터링 카운터 — admin scope cross-project 보장
# ---------------------------------------------------------------------------


def _count_volume_snapshots(conn) -> int:
    try:
        return sum(1 for _ in conn.block_storage.snapshots(details=False, all_projects=True))
    except Exception:
        return 0


def _count_volume_backups(conn) -> int:
    try:
        return sum(1 for _ in conn.block_storage.backups(details=False, all_projects=True))
    except Exception:
        return 0


def _count_share_snapshots(conn) -> int:
    if not get_settings().service_manila_enabled:
        return 0
    try:
        return len(manila.list_share_snapshots(conn, all_tenants=True))
    except Exception:
        return 0


def _count_images(conn) -> int:
    try:
        return sum(1 for _ in conn.image.images())
    except Exception:
        return 0


def _count_subnets(conn) -> int:
    try:
        return sum(1 for _ in conn.network.subnets())
    except Exception:
        return 0


def _count_security_groups(conn) -> int:
    try:
        return sum(1 for _ in conn.network.security_groups())
    except Exception:
        return 0


def _count_load_balancers(conn) -> tuple[int, int]:
    """(total, active) 반환. Octavia 엔드포인트 부재 환경은 try/except로 자동 0."""
    try:
        lbs = list(conn.load_balancer.load_balancers())
    except Exception:
        return 0, 0
    total = len(lbs)
    active = sum(1 for lb in lbs if (getattr(lb, "provisioning_status", "") or "") == "ACTIVE")
    return total, active


def _count_database_instances_admin(conn) -> int:
    """Trove /mgmt/instances로 cross-project 합산. service flag 가드."""
    if not get_settings().service_trove_enabled:
        return 0
    try:
        from app.services.trove import list_instances_admin_all_projects

        return len(list_instances_admin_all_projects(conn))
    except Exception:
        return 0


def _count_identity_users_projects() -> tuple[int, int]:
    """admin Keystone client로 (user_count, project_count) 반환."""
    try:
        from app.services.keystone import _get_admin_ks_client

        ks = _get_admin_ks_client()
        users = len(ks.users.list())
        projects = len(ks.projects.list())
        return users, projects
    except Exception:
        return 0, 0


@router.get("/overview", dependencies=[Depends(require_admin)])
async def admin_overview(
    conn: openstack.connection.Connection = Depends(get_os_conn), cm: CacheMode = Depends(cache_mode)
):
    """하이퍼바이저 및 전체 리소스 집계."""
    try:

        def _collect():
            with ThreadPoolExecutor(max_workers=8) as executor:
                f_hyp = executor.submit(_fetch_overview_hypervisors, conn)
                f_disk = executor.submit(_fetch_overview_disk, conn)
                f_cpu = executor.submit(_fetch_overview_placement, conn)
                f_srv = executor.submit(_fetch_overview_servers, conn)
                f_ctr = executor.submit(_fetch_overview_containers, conn)
                f_fs = executor.submit(_fetch_overview_file_storage, conn)
                f_db = executor.submit(_fetch_overview_database_instances, conn)
                f_os = executor.submit(_fetch_overview_object_storage, conn)

            hyp = f_hyp.result(timeout=15)
            disk = f_disk.result(timeout=15)
            cpu = f_cpu.result(timeout=15)
            srv = f_srv.result(timeout=15)
            ctr = f_ctr.result(timeout=15)
            fs = f_fs.result(timeout=15)
            db = f_db.result(timeout=15)
            os_count = f_os.result(timeout=15)

            # Placement 실패 시 hypervisor 데이터로 fallback
            physical_vcpus = cpu["physical_vcpus"]
            allowed_vcpus = cpu["allowed_vcpus"]
            if physical_vcpus == 0 and hyp["total_vcpus"] > 0:
                physical_vcpus = hyp["total_vcpus"]
                allowed_vcpus = hyp["total_vcpus"]

            return {
                "hypervisor_count": hyp["host_count"],
                "running_vms": hyp["running_vms"],
                "gpu_instances": srv["gpu_instances"],
                "instance_stats": srv["instance_stats"],
                "vcpus": {"total": physical_vcpus, "allowed": allowed_vcpus, "used": hyp["used_vcpus"]},
                "ram_gb": {"total": round(hyp["total_ram_mb"] / 1024, 1), "used": round(hyp["used_ram_mb"] / 1024, 1)},
                "disk_gb": {"total": disk["total_disk"], "used": disk["used_disk"]},
                "containers_count": ctr,
                "file_storage_count": fs,
                "database_instances_count": db,
                "object_storage_containers_count": os_count,
            }

        return await cached_call(
            "afterglow:admin:overview", ttl_normal(), _collect, enabled=cm.enabled, refresh=cm.refresh
        )
    except Exception:
        _logger.warning("admin overview 조회 실패", exc_info=True)
        raise HTTPException(status_code=500, detail="개요 조회 실패")


def _collect_storage_block(conn) -> dict:
    """Cinder 볼륨 통계 (cross-project)."""
    try:
        vol_ep = conn.block_storage.get_endpoint()
        vol_resp = conn.session.get(
            f"{vol_ep}/volumes/detail",
            params={"all_tenants": "1", "limit": "1000"},
        )
        volumes = vol_resp.json().get("volumes", [])
        vol_by_status: dict = {}
        total_gb = 0
        for v in volumes:
            s = v.get("status", "unknown")
            vol_by_status[s] = vol_by_status.get(s, 0) + 1
            total_gb += v.get("size", 0)
        return {"volume_count": len(volumes), "volume_by_status": vol_by_status, "total_gb": total_gb}
    except Exception:
        return {"volume_count": 0, "volume_by_status": {}, "total_gb": 0}


def _collect_network_block(conn) -> dict:
    """Neutron 핵심 카운트 (cross-project)."""
    try:
        nets = list(conn.network.networks())
        routers = list(conn.network.routers())
        fips = list(conn.network.ips())
        ports = list(conn.network.ports())
        fip_active = sum(1 for f in fips if f.status == "ACTIVE")
        router_active = sum(1 for r in routers if r.status == "ACTIVE")
        return {
            "network_count": len(nets),
            "router_count": len(routers),
            "router_active": router_active,
            "floatingip_count": len(fips),
            "floatingip_active": fip_active,
            "port_count": len(ports),
        }
    except Exception:
        return {
            "network_count": 0,
            "router_count": 0,
            "router_active": 0,
            "floatingip_count": 0,
            "floatingip_active": 0,
            "port_count": 0,
        }


@router.get("/monitoring/summary", dependencies=[Depends(require_admin)])
async def get_monitoring_summary(
    conn: openstack.connection.Connection = Depends(get_os_conn), cm: CacheMode = Depends(cache_mode)
):
    """분야별 통합 모니터링 요약 — Compute/Storage/Network/Containers/Data Services/Identity.

    모든 카운트는 admin scope에서 cross-project 합산.
    Trove/Manila/Octavia/Swift는 service_*_enabled 플래그로 가드.
    """

    async def _collect() -> dict:
        # 1차: 동기 SDK 호출들을 ThreadPool 병렬로 (asyncio.to_thread + gather)
        (
            hyp_data,
            srv_data,
            storage_block,
            network_block,
            zun_count,
            file_storage_count,
            volume_snapshot_count,
            volume_backup_count,
            share_snapshot_count,
            image_count,
            subnet_count,
            security_group_count,
            lb_pair,
            db_instance_count,
            identity_pair,
        ) = await asyncio.gather(
            asyncio.to_thread(_fetch_hypervisors_raw, conn),
            asyncio.to_thread(_fetch_overview_servers, conn),
            asyncio.to_thread(_collect_storage_block, conn),
            asyncio.to_thread(_collect_network_block, conn),
            asyncio.to_thread(_fetch_overview_containers, conn),
            asyncio.to_thread(_fetch_overview_file_storage, conn),
            asyncio.to_thread(_count_volume_snapshots, conn),
            asyncio.to_thread(_count_volume_backups, conn),
            asyncio.to_thread(_count_share_snapshots, conn),
            asyncio.to_thread(_count_images, conn),
            asyncio.to_thread(_count_subnets, conn),
            asyncio.to_thread(_count_security_groups, conn),
            asyncio.to_thread(_count_load_balancers, conn),
            asyncio.to_thread(_count_database_instances_admin, conn),
            asyncio.to_thread(_count_identity_users_projects),
        )

        # Drover owns the authoritative cross-project cluster inventory.
        k3s_available = True
        try:
            clusters = await asyncio.to_thread(register_drover(conn).admin_clusters)
        except Exception:
            clusters = []
            k3s_available = False
        k3s_total = len(clusters)
        k3s_active = sum(1 for c in clusters if (c.get("status") or "") == "ACTIVE")

        hyp_up = sum(1 for h in hyp_data if h.get("state") == "up")
        result: dict = {
            "compute": {
                "hypervisors_total": len(hyp_data),
                "hypervisors_up": hyp_up,
                "vcpus_used": sum(h.get("vcpus_used", 0) or 0 for h in hyp_data),
                "vcpus_total": sum(h.get("vcpus", 0) or 0 for h in hyp_data),
                "memory_used_mb": sum(h.get("memory_mb_used", 0) or 0 for h in hyp_data),
                "memory_total_mb": sum(h.get("memory_mb", 0) or 0 for h in hyp_data),
                "running_vms": sum(h.get("running_vms", 0) or 0 for h in hyp_data),
                "instance_stats": srv_data.get("instance_stats", {}),
                "gpu_instances": srv_data.get("gpu_instances", 0),
            },
            "storage": {
                **storage_block,
                "file_storage_count": file_storage_count,
                "volume_snapshot_count": volume_snapshot_count,
                "volume_backup_count": volume_backup_count,
                "share_snapshot_count": share_snapshot_count,
                "image_count": image_count,
            },
            "network": {
                **network_block,
                "subnet_count": subnet_count,
                "security_group_count": security_group_count,
                "load_balancer_count": lb_pair[0],
                "load_balancer_active": lb_pair[1],
            },
            "containers": {
                "zun_count": zun_count,
                "k3s_count": k3s_total,
                "k3s_active": k3s_active,
                "k3s_available": k3s_available,
            },
            "data_services": {
                "database_instance_count": db_instance_count,
            },
            "identity": {
                "user_count": identity_pair[0],
                "project_count": identity_pair[1],
            },
        }
        return result

    try:
        return await cached_call(
            "afterglow:admin:monitoring", ttl_normal(), _collect, enabled=cm.enabled, refresh=cm.refresh
        )
    except Exception:
        _logger.warning("monitoring summary 조회 실패", exc_info=True)
        raise HTTPException(status_code=500, detail="모니터링 요약 조회 실패")


@router.get("/hypervisors", dependencies=[Depends(require_admin)])
async def list_hypervisors(
    conn: openstack.connection.Connection = Depends(get_os_conn), cm: CacheMode = Depends(cache_mode)
):
    """컴퓨트 하이퍼바이저 목록."""
    try:

        def _list():
            data = _fetch_hypervisors_raw(conn)
            # Placement API에서 allocation_ratio 수집 (root RP만)
            ratios: dict[str, dict] = {}
            try:
                placement_ep = conn.placement.get_endpoint()
                rps_resp = conn.session.get(f"{placement_ep}/resource_providers")
                for rp in rps_resp.json().get("resource_providers", []):
                    if rp.get("parent_provider_uuid"):  # child RP(GPU 등) 건너뜀
                        continue
                    inv_resp = conn.session.get(f"{placement_ep}/resource_providers/{rp['uuid']}/inventories")
                    invs = inv_resp.json().get("inventories", {})
                    ratios[rp["uuid"]] = {
                        "vcpu": invs.get("VCPU", {}).get("allocation_ratio", 1.0),
                        "memory": invs.get("MEMORY_MB", {}).get("allocation_ratio", 1.0),
                    }
            except Exception:
                _logger.warning("Placement allocation_ratio 조회 실패", exc_info=True)
            return [
                {
                    "id": h.get("id", ""),
                    "name": h.get("hypervisor_hostname", ""),
                    "state": h.get("state", ""),
                    "status": h.get("status", ""),
                    "hypervisor_type": h.get("hypervisor_type", ""),
                    "vcpus": h.get("vcpus", 0) or 0,
                    "vcpus_used": h.get("vcpus_used", 0) or 0,
                    "vcpus_allowed": int((h.get("vcpus", 0) or 0) * ratios.get(h.get("id", ""), {}).get("vcpu", 1.0)),
                    "memory_size_mb": h.get("memory_mb", 0) or 0,
                    "memory_used_mb": h.get("memory_mb_used", 0) or 0,
                    "memory_allowed_mb": int(
                        (h.get("memory_mb", 0) or 0) * ratios.get(h.get("id", ""), {}).get("memory", 1.0)
                    ),
                    "local_disk_gb": h.get("local_gb", 0) or 0,
                    "local_disk_used_gb": h.get("local_gb_used", 0) or 0,
                    "running_vms": h.get("running_vms", 0) or 0,
                    "cpu_model": nova.extract_cpu_model(h),
                }
                for h in data
            ]

        return await cached_call(
            "afterglow:admin:hypervisors", ttl_normal(), _list, enabled=cm.enabled, refresh=cm.refresh
        )
    except Exception:
        _logger.warning("hypervisors 조회 실패", exc_info=True)
        raise HTTPException(status_code=500, detail="하이퍼바이저 조회 실패")


@router.get("/hypervisors/{hypervisor_id}", dependencies=[Depends(require_admin)])
async def get_hypervisor_detail(hypervisor_id: str, conn: openstack.connection.Connection = Depends(get_os_conn)):
    """하이퍼바이저 상세 정보 + 해당 호스트의 VM 목록."""
    try:

        def _get():
            endpoint = conn.compute.get_endpoint()
            resp = conn.session.get(
                f"{endpoint}/os-hypervisors/{hypervisor_id}",
                headers={"OpenStack-API-Version": "compute 2.53"},
            )
            h = resp.json().get("hypervisor", {})
            hostname = h.get("hypervisor_hostname", "")
            servers = []
            if hostname:
                try:
                    srv_resp = conn.session.get(
                        f"{endpoint}/servers/detail",
                        params={"all_tenants": "1", "host": hostname, "limit": "200"},
                        headers={"OpenStack-API-Version": "compute 2.53"},
                    )
                    for s in srv_resp.json().get("servers", []):
                        servers.append(
                            {
                                "id": s.get("id", ""),
                                "name": s.get("name", ""),
                                "status": s.get("status", ""),
                                "project_id": s.get("tenant_id", "") or s.get("project_id", ""),
                                "flavor": (s.get("flavor") or {}).get("original_name", ""),
                            }
                        )
                except Exception:
                    pass
            svc = h.get("service") or {}
            # uptime 조회
            uptime_str = ""
            host_time_str = ""
            try:
                ut_resp = conn.session.get(
                    f"{endpoint}/os-hypervisors/{hypervisor_id}/uptime",
                    headers={"OpenStack-API-Version": "compute 2.53"},
                )
                ut_data = ut_resp.json().get("hypervisor", {})
                uptime_str = ut_data.get("uptime", "")
                host_time_str = ut_data.get("host_time", "")
            except Exception:
                pass
            # Placement에서 allocation_ratio 조회
            vcpu_ratio = 1.0
            mem_ratio = 1.0
            try:
                placement_ep = conn.placement.get_endpoint()
                inv_resp = conn.session.get(f"{placement_ep}/resource_providers/{hypervisor_id}/inventories")
                invs = inv_resp.json().get("inventories", {})
                vcpu_ratio = invs.get("VCPU", {}).get("allocation_ratio", 1.0)
                mem_ratio = invs.get("MEMORY_MB", {}).get("allocation_ratio", 1.0)
            except Exception:
                pass
            vcpus_total = h.get("vcpus", 0) or 0
            mem_total = h.get("memory_mb", 0) or 0
            return {
                "id": h.get("id", ""),
                "hypervisor_hostname": hostname,
                "state": h.get("state", ""),
                "status": h.get("status", ""),
                "hypervisor_type": h.get("hypervisor_type", ""),
                "hypervisor_version": h.get("hypervisor_version", 0),
                "host_ip": h.get("host_ip", ""),
                "host_time": host_time_str,
                "uptime": uptime_str,
                "service_host": svc.get("host", ""),
                "vcpus": vcpus_total,
                "vcpus_used": h.get("vcpus_used", 0) or 0,
                "vcpus_allowed": int(vcpus_total * vcpu_ratio),
                "memory_mb": mem_total,
                "memory_mb_used": h.get("memory_mb_used", 0) or 0,
                "memory_allowed_mb": int(mem_total * mem_ratio),
                "local_gb": h.get("local_gb", 0) or 0,
                "local_gb_used": h.get("local_gb_used", 0) or 0,
                "running_vms": h.get("running_vms", 0) or 0,
                "cpu_info": h.get("cpu_info"),
                "cpu_model": nova.extract_cpu_model(h),
                "servers": servers,
            }

        return await asyncio.to_thread(_get)
    except Exception:
        _logger.warning("하이퍼바이저 상세 조회 실패", exc_info=True)
        raise HTTPException(status_code=500, detail="하이퍼바이저 상세 조회 실패")


@router.get("/all-instances", dependencies=[Depends(require_admin)])
async def list_all_instances(
    limit: int = Query(default=20, ge=1, le=100),
    marker: str | None = Query(default=None),
    project_id: str | None = Query(default=None),
    host: str | None = Query(default=None),
    status: str | None = Query(default=None),
    name: str | None = Query(default=None),
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """전체 프로젝트의 인스턴스 목록 (페이지네이션)."""
    try:

        def _list():
            endpoint = conn.compute.get_endpoint()
            params: dict = {"all_tenants": "1", "limit": str(limit)}
            if marker:
                params["marker"] = marker
            if project_id:
                params["tenant_id"] = project_id
            if host:
                params["host"] = host
            if status:
                params["status"] = status
            if name:
                params["name"] = ".*" + re.escape(name) + ".*"
            resp = conn.session.get(
                f"{endpoint}/servers/detail",
                params=params,
                headers={"OpenStack-API-Version": "compute 2.53"},
            )
            servers = resp.json().get("servers", [])
            items = []
            for s in servers[:limit]:
                fault_info = None
                if (s.get("status") or "").upper() == "ERROR":
                    fault = s.get("fault") or {}
                    if isinstance(fault, dict) and fault.get("message"):
                        fault_info = fault.get("message", "")
                server_host = s.get("OS-EXT-SRV-ATTR:host") or s.get("host")
                flavor = s.get("flavor") or {}
                items.append(
                    {
                        "id": s.get("id", ""),
                        "name": s.get("name") or "",
                        "status": s.get("status") or "",
                        "project_id": s.get("tenant_id") or s.get("project_id"),
                        "user_id": s.get("user_id"),
                        "flavor": flavor.get("original_name") or flavor.get("id") or "",
                        "host": server_host,
                        "created_at": s.get("created"),
                        "fault": fault_info,
                    }
                )
            next_marker = items[-1]["id"] if len(items) == limit else None
            return {"items": items, "next_marker": next_marker, "count": len(items)}

        return await asyncio.to_thread(_list)
    except Exception:
        raise HTTPException(status_code=500, detail="전체 인스턴스 조회 실패")


@router.get("/volumes/status-summary", dependencies=[Depends(require_admin)])
async def get_volume_status_summary(
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """전체 프로젝트의 Cinder 볼륨 상태별 개수."""
    try:

        def _collect():
            counts: dict[str, int] = {}
            total = 0
            for volume in conn.block_storage.volumes(details=True, all_projects=True):
                status = (getattr(volume, "status", None) or "unknown").lower()
                counts[status] = counts.get(status, 0) + 1
                total += 1
            return {
                "total": total,
                "statuses": [
                    {"status": status, "count": count}
                    for status, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
                ],
            }

        return await asyncio.to_thread(_collect)
    except Exception:
        _logger.warning("볼륨 상태 요약 조회 실패", exc_info=True)
        raise HTTPException(status_code=500, detail="볼륨 상태 요약 조회 실패")


@router.get("/all-volumes", dependencies=[Depends(require_admin)])
async def list_all_volumes(
    limit: int = Query(default=20, ge=1, le=100),
    marker: str | None = Query(default=None),
    project_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    name: str | None = Query(default=None),
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """전체 프로젝트의 볼륨 목록 (페이지네이션)."""
    try:

        def _list():
            kwargs: dict = {"details": True, "all_projects": True, "limit": limit}
            if marker:
                kwargs["marker"] = marker
            if project_id:
                kwargs["project_id"] = project_id
            if status:
                kwargs["status"] = status
            if name:
                kwargs["name~"] = name
            items = [
                {
                    "id": v.id,
                    "name": v.name or "",
                    "status": v.status or "",
                    "size": v.size,
                    "project_id": getattr(v, "project_id", None),
                    "created_at": str(v.created_at) if getattr(v, "created_at", None) else None,
                }
                for v in itertools.islice(conn.block_storage.volumes(**kwargs), limit)
            ]
            next_marker = items[-1]["id"] if len(items) == limit else None
            return {"items": items, "next_marker": next_marker, "count": len(items)}

        return await asyncio.to_thread(_list)
    except Exception:
        raise HTTPException(status_code=500, detail="전체 볼륨 조회 실패")


@router.get("/all-containers", dependencies=[Depends(require_admin)])
async def list_all_containers(
    conn: openstack.connection.Connection = Depends(get_os_conn), cm: CacheMode = Depends(cache_mode)
):
    """전체 프로젝트의 컨테이너 목록 (Zun)."""
    if not get_settings().service_zun_enabled:
        return []
    from app.services.zun import ZunServiceUnavailable, list_containers_admin

    try:
        return await cached_call(
            "afterglow:admin:containers",
            ttl_normal(),
            lambda: list_containers_admin(conn),
            enabled=cm.enabled,
            refresh=cm.refresh,
        )
    except ZunServiceUnavailable:
        return []
    except Exception:
        raise HTTPException(status_code=500, detail="컨테이너 조회 실패")


@router.get("/containers/{container_id}", dependencies=[Depends(require_admin)])
async def get_admin_container(
    container_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """관리자용 컨테이너 단건 조회."""
    if not get_settings().service_zun_enabled:
        raise HTTPException(status_code=503, detail="Zun 서비스가 비활성화되어 있습니다")
    from app.services.zun import ZunServiceUnavailable, get_container

    try:
        return await asyncio.to_thread(get_container, conn, container_id)
    except ZunServiceUnavailable:
        raise HTTPException(status_code=503, detail="컨테이너 서비스를 사용할 수 없습니다")
    except Exception:
        raise HTTPException(status_code=404, detail="컨테이너를 찾을 수 없습니다")


@router.get("/containers/{container_id}/logs", dependencies=[Depends(require_admin)])
async def get_admin_container_logs(
    container_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """관리자용 컨테이너 로그 조회."""
    if not get_settings().service_zun_enabled:
        raise HTTPException(status_code=503, detail="Zun 서비스가 비활성화되어 있습니다")
    from app.services.zun import ZunServiceUnavailable, get_container_logs

    try:
        logs = await asyncio.to_thread(get_container_logs, conn, container_id)
        return {"logs": logs}
    except ZunServiceUnavailable:
        raise HTTPException(status_code=503, detail="컨테이너 서비스를 사용할 수 없습니다")
    except Exception:
        raise HTTPException(status_code=404, detail="컨테이너를 찾을 수 없습니다")


@router.post("/containers/{container_id}/start", dependencies=[Depends(require_admin)])
async def start_admin_container(
    container_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """관리자용 컨테이너 시작."""
    if not get_settings().service_zun_enabled:
        raise HTTPException(status_code=503, detail="Zun 서비스가 비활성화되어 있습니다")
    from app.services import zun as _zun

    try:
        await asyncio.to_thread(_zun.start_container, conn, container_id)
        return {"status": "started"}
    except Exception:
        _logger.warning("컨테이너 시작 실패: %s", container_id, exc_info=True)
        raise HTTPException(status_code=500, detail="컨테이너 시작 실패")


@router.post("/containers/{container_id}/stop", dependencies=[Depends(require_admin)])
async def stop_admin_container(
    container_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """관리자용 컨테이너 중지."""
    if not get_settings().service_zun_enabled:
        raise HTTPException(status_code=503, detail="Zun 서비스가 비활성화되어 있습니다")
    from app.services import zun as _zun

    try:
        await asyncio.to_thread(_zun.stop_container, conn, container_id)
        return {"status": "stopped"}
    except Exception:
        _logger.warning("컨테이너 중지 실패: %s", container_id, exc_info=True)
        raise HTTPException(status_code=500, detail="컨테이너 중지 실패")


@router.delete("/containers/{container_id}", status_code=204, dependencies=[Depends(require_admin)])
async def delete_admin_container(
    container_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """관리자용 컨테이너 삭제."""
    if not get_settings().service_zun_enabled:
        raise HTTPException(status_code=503, detail="Zun 서비스가 비활성화되어 있습니다")
    from app.services import zun as _zun

    try:
        await asyncio.to_thread(_zun.delete_container, conn, container_id)
    except Exception:
        _logger.warning("컨테이너 삭제 실패: %s", container_id, exc_info=True)
        raise HTTPException(status_code=500, detail="컨테이너 삭제 실패")


@router.get("/all-file-storages", dependencies=[Depends(require_admin)])
async def list_all_file_storages(
    conn: openstack.connection.Connection = Depends(get_os_conn), cm: CacheMode = Depends(cache_mode)
):
    """전체 프로젝트의 파일 스토리지 목록 (Manila)."""
    if not get_settings().service_manila_enabled:
        return []
    try:
        return await cached_call(
            "afterglow:admin:file_storages",
            ttl_normal(),
            lambda: manila.list_file_storages(conn, None, True),
            enabled=cm.enabled,
            refresh=cm.refresh,
        )
    except Exception:
        raise HTTPException(status_code=500, detail="파일 스토리지 조회 실패")


@router.get(
    "/file-storage/{file_storage_id}/delete-diagnostics",
    response_model=FileStorageDeleteDiagnostic,
    dependencies=[Depends(require_admin)],
)
async def get_file_storage_delete_diagnostics(
    file_storage_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """관리자용 Manila share 삭제 실패 진단."""
    try:
        return await asyncio.to_thread(manila.diagnose_file_storage_delete_issue, conn, file_storage_id)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail="파일 스토리지를 찾을 수 없습니다")
        _logger.warning("파일 스토리지 삭제 진단 실패: %s", file_storage_id, exc_info=True)
        raise HTTPException(status_code=500, detail="파일 스토리지 삭제 진단 실패")
    except Exception:
        _logger.warning("파일 스토리지 삭제 진단 실패: %s", file_storage_id, exc_info=True)
        raise HTTPException(status_code=500, detail="파일 스토리지 삭제 진단 실패")


@router.post(
    "/file-storage/{file_storage_id}/force-delete",
    response_model=FileStorageForceDeleteResult,
    status_code=202,
    dependencies=[Depends(require_admin)],
)
async def force_delete_file_storage(
    file_storage_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    """관리자용 Manila share 강제 삭제."""
    diagnostic: FileStorageDeleteDiagnostic | None = None
    try:
        diagnostic = await asyncio.to_thread(manila.diagnose_file_storage_delete_issue, conn, file_storage_id)
    except Exception:
        _logger.info("파일 스토리지 강제 삭제 전 진단 실패: %s", file_storage_id, exc_info=True)

    try:
        status = await asyncio.to_thread(manila.force_delete_file_storage, conn, file_storage_id)
        await invalidate("afterglow:admin:file_storages")
        await invalidate("afterglow:manila:*:file_storages")
        try:
            await rec(
                token_info,
                conn,
                resource_type="file_storage",
                action="file_storage.force_delete",
                status="success",
                resource_id=file_storage_id,
                extra={"result": status, "diagnostic": diagnostic.root_cause_code if diagnostic else None},
            )
        except Exception:
            pass
        return FileStorageForceDeleteResult(
            file_storage_id=file_storage_id,
            status=status,
            diagnostic=diagnostic,
        )
    except httpx.HTTPStatusError as e:
        try:
            await rec(
                token_info,
                conn,
                resource_type="file_storage",
                action="file_storage.force_delete",
                status="failed",
                resource_id=file_storage_id,
                extra={"status_code": e.response.status_code},
            )
        except Exception:
            pass
        _logger.warning("파일 스토리지 강제 삭제 실패: %s", file_storage_id, exc_info=True)
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"파일 스토리지 강제 삭제 실패: {manila.format_error_message(e)}",
        )
    except Exception:
        try:
            await rec(
                token_info,
                conn,
                resource_type="file_storage",
                action="file_storage.force_delete",
                status="failed",
                resource_id=file_storage_id,
            )
        except Exception:
            pass
        _logger.warning("파일 스토리지 강제 삭제 실패: %s", file_storage_id, exc_info=True)
        raise HTTPException(status_code=500, detail="파일 스토리지 강제 삭제 실패")


@router.get("/topology", response_model=AdminTopologyData, dependencies=[Depends(require_admin)])
async def admin_topology(
    conn: openstack.connection.Connection = Depends(get_os_conn), cm: CacheMode = Depends(cache_mode)
):
    """전체 프로젝트의 네트워크/라우터/인스턴스 토폴로지 (네트워크에 provider 세그먼트 메타 포함)."""

    def _fetch():
        topo = neutron.get_topology(conn, include_provider=True)

        # Neutron compute 포트에서 (device_id, ip) → {network_id, port_id, mac_address} 인덱스 구축
        port_index = neutron.build_compute_port_index(conn)

        # Trove DB 인스턴스 IP 집합 (전체 프로젝트, 1회 조회).
        # Trove 미배포/조회 실패는 정상 → 전부 is_database=False.
        try:
            db_ips = trove.topology_database_ips(conn, all_projects=True)
        except Exception:
            _logger.debug("Trove 토폴로지 IP 조회 실패 — is_database 표시 생략", exc_info=True)
            db_ips = set()

        def _ip_entry(server_id: str, net_name: str, addr: dict) -> dict:
            port = port_index.get((server_id, addr["addr"]), {})
            return {
                "addr": addr["addr"],
                "type": addr.get("OS-EXT-IPS:type", ""),
                "network_name": net_name,
                "network_id": port.get("network_id"),
                "port_id": port.get("port_id"),
                "mac_addr": port.get("mac_address"),
            }

        instances = []
        for s in conn.compute.servers(details=True, all_projects=True):
            addresses = getattr(s, "addresses", {}) or {}
            flavor = getattr(s, "flavor", None)
            image = getattr(s, "image", None)
            ip_entries = [_ip_entry(s.id, net_name, addr) for net_name, addrs in addresses.items() for addr in addrs]
            instances.append(
                TopologyInstance(
                    id=s.id,
                    name=s.name or "",
                    status=s.status or "",
                    project_id=getattr(s, "project_id", None) or getattr(s, "tenant_id", None),
                    network_names=list(set(addresses.keys())),
                    ip_addresses=ip_entries,
                    flavor_name=flavor.get("original_name") if isinstance(flavor, dict) else None,
                    image_id=image.get("id") if isinstance(image, dict) else None,
                    # fixed IP 가 Trove IP 집합에 속하면 DB 인스턴스. floating IP 우연 일치는 제외.
                    is_database=any(e.get("type") == "fixed" and e.get("addr") in db_ips for e in ip_entries),
                )
            )
        topo.instances = instances
        topo.load_balancers = get_topology_lbs(
            conn,
            project_id=None,
            instances=[inst.model_dump() for inst in instances],
        )
        return topo.model_dump()

    try:
        return await cached_call(
            "afterglow:admin:topology", ttl_normal(), _fetch, enabled=cm.enabled, refresh=cm.refresh
        )
    except HTTPException:
        raise
    except Exception:
        _logger.exception("토폴로지 조회 실패")
        raise HTTPException(status_code=500, detail="토폴로지 조회 실패")


@router.get("/timeseries/{resource_type}", dependencies=[Depends(require_admin)])
async def get_timeseries(
    resource_type: str,
    range: str = Query(default="7d", pattern="^(1d|2d|7d|30d)$"),
):
    """리소스 유형별 시계열 스냅샷 반환."""
    from app.services import timeseries

    valid = {"instances", "volumes", "file_storage", "networks", "library_usage"}
    if resource_type not in valid:
        raise HTTPException(status_code=400, detail=f"resource_type은 {valid} 중 하나여야 합니다")
    return await timeseries.get_timeseries(resource_type, range)


@router.get("/all-networks", dependencies=[Depends(require_admin)])
async def list_all_networks(
    conn: openstack.connection.Connection = Depends(get_os_conn), cm: CacheMode = Depends(cache_mode)
):
    """전체 프로젝트의 네트워크 목록."""
    try:
        return await cached_call(
            "afterglow:admin:networks",
            ttl_normal(),
            lambda: neutron.list_networks(conn, None),
            enabled=cm.enabled,
            refresh=cm.refresh,
        )
    except Exception:
        raise HTTPException(status_code=500, detail="네트워크 목록 조회 실패")


@router.get("/all-loadbalancers", dependencies=[Depends(require_admin)])
async def list_all_loadbalancers(
    conn: openstack.connection.Connection = Depends(get_os_conn), cm: CacheMode = Depends(cache_mode)
):
    """전체 프로젝트의 로드밸런서 목록."""
    from app.services import octavia

    try:
        return await cached_call(
            "afterglow:admin:loadbalancers",
            ttl_normal(),
            lambda: octavia.list_load_balancers(conn, project_id=None),
            enabled=cm.enabled,
            refresh=cm.refresh,
        )
    except Exception:
        raise HTTPException(status_code=500, detail="로드밸런서 목록 조회 실패")


@router.get("/all-floating-ips", dependencies=[Depends(require_admin)])
async def list_all_floating_ips(
    conn: openstack.connection.Connection = Depends(get_os_conn), cm: CacheMode = Depends(cache_mode)
):
    """전체 프로젝트의 Floating IP 목록."""
    try:
        return await cached_call(
            "afterglow:admin:floating_ips",
            ttl_fast(),
            lambda: neutron.list_floating_ips(conn, None),
            enabled=cm.enabled,
            refresh=cm.refresh,
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Floating IP 목록 조회 실패")


@router.get("/all-routers", dependencies=[Depends(require_admin)])
async def list_all_routers(
    conn: openstack.connection.Connection = Depends(get_os_conn), cm: CacheMode = Depends(cache_mode)
):
    """전체 프로젝트의 라우터 목록."""
    try:
        return await cached_call(
            "afterglow:admin:routers",
            ttl_normal(),
            lambda: neutron.list_routers(conn, None),
            enabled=cm.enabled,
            refresh=cm.refresh,
        )
    except Exception:
        raise HTTPException(status_code=500, detail="라우터 목록 조회 실패")


@router.get("/all-ports", dependencies=[Depends(require_admin)])
async def list_all_ports(
    conn: openstack.connection.Connection = Depends(get_os_conn),
    limit: int = Query(default=20, ge=1, le=100),
    marker: str | None = Query(default=None),
    project_id: str | None = Query(default=None),
):
    """전체 프로젝트의 포트 목록 (페이지네이션)."""
    try:

        def _list():
            kwargs: dict = {"limit": limit}
            if marker:
                kwargs["marker"] = marker
            if project_id:
                kwargs["project_id"] = project_id
            items = []
            for p in conn.network.ports(**kwargs):
                items.append(
                    {
                        "id": p.id,
                        "name": p.name or "",
                        "status": p.status or "",
                        "network_id": p.network_id,
                        "device_owner": p.device_owner or "",
                        "device_id": p.device_id or "",
                        "mac_address": p.mac_address or "",
                        "fixed_ips": p.fixed_ips or [],
                        "project_id": getattr(p, "project_id", None),
                    }
                )
                if len(items) >= limit:
                    break
            next_marker = items[-1]["id"] if len(items) == limit else None
            return {"items": items, "next_marker": next_marker, "count": len(items)}

        return await asyncio.to_thread(_list)
    except Exception:
        raise HTTPException(status_code=500, detail="포트 목록 조회 실패")


class CreatePortRequest(BaseModel):
    network_id: str
    name: str = ""
    project_id: str | None = None
    fixed_ip: str | None = None


@router.post("/ports", dependencies=[Depends(require_admin)], status_code=201)
async def create_port(
    req: CreatePortRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """포트 생성 (관리자)."""
    try:

        def _create():
            kwargs: dict = {"network_id": req.network_id}
            if req.name:
                kwargs["name"] = req.name
            if req.project_id:
                kwargs["project_id"] = req.project_id
            if req.fixed_ip:
                kwargs["fixed_ips"] = [{"ip_address": req.fixed_ip}]
            p = conn.network.create_port(**kwargs)
            return {
                "id": p.id,
                "name": p.name or "",
                "status": p.status or "",
                "network_id": p.network_id,
                "device_owner": p.device_owner or "",
                "device_id": p.device_id or "",
                "mac_address": p.mac_address or "",
                "fixed_ips": p.fixed_ips or [],
                "project_id": getattr(p, "project_id", None),
            }

        return await asyncio.to_thread(_create)
    except Exception as e:
        _logger.warning("포트 생성 실패: %s", e)

        raise HTTPException(status_code=400, detail="포트 생성 실패")


@router.get("/overview/projects", dependencies=[Depends(require_admin)])
async def admin_overview_projects(
    conn: openstack.connection.Connection = Depends(get_os_conn), cm: CacheMode = Depends(cache_mode)
):
    """프로젝트별 리소스 사용량 및 쿼터."""
    try:

        def _collect():
            # 프로젝트별 GPU 인스턴스 수 집계
            gpu_by_project: dict = {}
            try:
                endpoint = conn.compute.get_endpoint()
                params = {"all_tenants": "1", "limit": "1000"}
                resp = conn.session.get(
                    f"{endpoint}/servers/detail",
                    params=params,
                    headers={"OpenStack-API-Version": "compute 2.53"},
                )
                for s in resp.json().get("servers", []):
                    # SHELVED/SHELVED_OFFLOADED는 실제 호스트 할당이 없으므로 제외
                    st = (s.get("status") or "").upper()
                    if st not in ("ACTIVE", "SHUTOFF", "PAUSED", "SUSPENDED", "RESIZE"):
                        continue
                    pid = s.get("tenant_id") or s.get("project_id") or ""
                    fname = (s.get("flavor") or {}).get("original_name") or ""
                    if "gpu" in fname.lower():
                        gpu_by_project[pid] = gpu_by_project.get(pid, 0) + 1
            except Exception:
                pass

            compute_endpoint = conn.compute.get_endpoint()
            bs_endpoint = conn.block_storage.get_endpoint()
            projects = list(conn.identity.projects())

            def _fetch_project_quota(p) -> dict:
                pid = p.id
                row: dict = {
                    "project_id": pid,
                    "project_name": p.name or "",
                    "cpu": {"used": 0, "quota": -1},
                    "ram_mb": {"used": 0, "quota": -1},
                    "instances": {"used": 0, "quota": -1},
                    "disk_gb": {"used": 0, "quota": -1},
                    "gpu_instances": gpu_by_project.get(pid, 0),
                }
                try:
                    cq_resp = conn.session.get(f"{compute_endpoint}/os-quota-sets/{pid}/detail")
                    qs = cq_resp.json().get("quota_set", {})
                    cores = qs.get("cores", {})
                    ram = qs.get("ram", {})
                    instances = qs.get("instances", {})
                    row["cpu"] = {"used": cores.get("in_use", 0), "quota": cores.get("limit", -1)}
                    row["ram_mb"] = {"used": ram.get("in_use", 0), "quota": ram.get("limit", -1)}
                    row["instances"] = {"used": instances.get("in_use", 0), "quota": instances.get("limit", -1)}
                except Exception:
                    pass
                try:
                    bq_resp = conn.session.get(f"{bs_endpoint}/os-quota-sets/{pid}", params={"usage": "true"})
                    bqs = bq_resp.json().get("quota_set", {})
                    gb = bqs.get("gigabytes", {})
                    gb_used = gb.get("in_use", 0) if isinstance(gb, dict) else 0
                    gb_limit = gb.get("limit", -1) if isinstance(gb, dict) else -1
                    row["disk_gb"] = {"used": gb_used, "quota": gb_limit}
                except Exception:
                    pass
                return row

            with ThreadPoolExecutor(max_workers=8) as executor:
                futures = [executor.submit(_fetch_project_quota, p) for p in projects]
            result = []
            for f in futures:
                try:
                    result.append(f.result(timeout=15))
                except Exception:
                    pass
            return result

        return await cached_call(
            "afterglow:admin:overview_projects", ttl_slow(), _collect, enabled=cm.enabled, refresh=cm.refresh
        )
    except Exception:
        _logger.warning("프로젝트별 리소스 조회 실패", exc_info=True)
        raise HTTPException(status_code=500, detail="프로젝트별 리소스 조회 실패")


# ===========================================================================
# 볼륨 관리 (관리자)
# ===========================================================================


@router.get("/volumes/{volume_id}", dependencies=[Depends(require_admin)])
async def get_admin_volume(volume_id: str, conn: openstack.connection.Connection = Depends(get_os_conn)):
    """볼륨 상세 조회 (관리자)."""
    try:

        def _get():
            v = conn.block_storage.get_volume(volume_id)
            return {
                "id": v.id,
                "name": v.name or "",
                "status": v.status or "",
                "size": v.size or 0,
                "volume_type": v.volume_type or "",
                "project_id": getattr(v, "project_id", None) or getattr(v, "os-vol-tenant-attr:tenant_id", None),
                "attachments": [dict(a) for a in (v.attachments or [])],
                "created_at": str(v.created_at) if v.created_at else None,
                "description": v.description or "",
                "bootable": getattr(v, "is_bootable", None),
                "encrypted": getattr(v, "is_encrypted", None),
                "multiattach": getattr(v, "is_multiattach", None),
                "metadata": dict(v.metadata or {}),
            }

        return await asyncio.to_thread(_get)
    except Exception:
        _logger.warning("볼륨 상세 조회 실패", exc_info=True)
        raise HTTPException(status_code=500, detail="볼륨 상세 조회 실패")


class UpdateVolumeRequest(BaseModel):
    name: str | None = None
    description: str | None = None


class ExtendVolumeRequest(BaseModel):
    new_size: int  # GB


class ResetVolumeStatusRequest(BaseModel):
    status: str = "available"


@router.patch("/volumes/{volume_id}", dependencies=[Depends(require_admin)])
async def update_volume(
    volume_id: str,
    req: UpdateVolumeRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """볼륨 이름/설명 수정."""

    def _update():
        kwargs: dict = {}
        if req.name is not None:
            kwargs["name"] = req.name
        if req.description is not None:
            kwargs["description"] = req.description
        try:
            v = conn.block_storage.update_volume(volume_id, **kwargs)
            return {
                "id": v.id,
                "name": v.name or "",
                "status": v.status or "",
                "size": v.size,
            }
        except Exception as e:
            _logger.warning("볼륨 수정 실패: %s", e)

            raise HTTPException(status_code=400, detail="볼륨 수정 실패")

    try:
        return await asyncio.to_thread(_update)
    except HTTPException:
        raise


_ERROR_STATUSES = {"error", "deleting", "error_deleting", "error_extending", "error_restoring", "error_managing"}


async def _invalidate_volume_recovery_caches(project_id: str | None) -> None:
    if project_id:
        await invalidate(f"afterglow:cinder:{project_id}:volumes*")
        await invalidate(f"afterglow:cinder:{project_id}:vol_attach:*")
        await cache_invalidation.invalidate_mutation_count("cinder", project_id)
    else:
        await invalidate("afterglow:cinder:*:volumes*")
        await invalidate("afterglow:cinder:*:vol_attach:*")
    await invalidate("afterglow:admin:overview*")
    await invalidate("afterglow:admin:monitoring*")


@router.get(
    "/volumes/{volume_id}/delete-diagnostics",
    response_model=VolumeDeleteDiagnostic,
    dependencies=[Depends(require_admin)],
)
async def get_volume_delete_diagnostics(
    volume_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """볼륨 삭제 실패 원인을 진단한다 (관리자)."""
    try:
        return await asyncio.to_thread(
            volume_delete_recovery.diagnose_volume_delete_issue,
            conn,
            volume_id,
            keystone.get_admin_connection_for_project,
        )
    except Exception:
        _logger.warning("볼륨 삭제 진단 실패: %s", volume_id, exc_info=True)
        raise HTTPException(status_code=500, detail="볼륨 삭제 진단 실패")


@router.post(
    "/volumes/{volume_id}/recover-delete",
    response_model=VolumeDeleteRecoveryResult,
    dependencies=[Depends(require_admin)],
)
async def recover_delete_volume(
    volume_id: str,
    verify_timeout_seconds: int = Query(default=30, ge=0, le=120),
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    """error_deleting 볼륨의 삭제 복구를 진단→실행→검증한다 (관리자)."""
    try:
        result = await asyncio.to_thread(
            volume_delete_recovery.recover_delete_volume,
            conn,
            volume_id,
            keystone.get_admin_connection_for_project,
            verify_timeout_seconds=verify_timeout_seconds,
        )
        if result.status in {"deleted", "already_deleted", "delete_submitted"}:
            await _invalidate_volume_recovery_caches(result.diagnostic.project_id)
        try:
            await rec(
                token_info,
                conn,
                resource_type="volume",
                action="volume.recover_delete",
                status="success" if result.status in {"deleted", "already_deleted", "delete_submitted"} else "failed",
                resource_id=volume_id,
                error_message=result.status if result.status in {"blocked", "failed"} else None,
                extra={
                    "result": result.status,
                    "verified_deleted": result.verified_deleted,
                    "root_cause": result.diagnostic.root_cause_code,
                    "steps": [step.model_dump() for step in result.steps],
                },
            )
        except Exception:
            pass
        return result
    except Exception:
        try:
            await rec(
                token_info,
                conn,
                resource_type="volume",
                action="volume.recover_delete",
                status="failed",
                resource_id=volume_id,
            )
        except Exception:
            pass
        _logger.warning("볼륨 삭제 복구 실패: %s", volume_id, exc_info=True)
        raise HTTPException(status_code=500, detail="볼륨 삭제 복구 실패")


@router.delete("/volumes/{volume_id}", dependencies=[Depends(require_admin)], status_code=204)
async def delete_volume(
    volume_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """볼륨 삭제. error* 상태이면 force-delete로 자동 폴백하여 Cinder DB를 정리한다."""
    from openstack.exceptions import ResourceNotFound

    from app.services import cinder

    def _delete():
        try:
            v = conn.block_storage.get_volume(volume_id)
        except ResourceNotFound:
            return  # 이미 없음 → 204

        status = (getattr(v, "status", "") or "").lower()
        attachments = list(getattr(v, "attachments", []) or [])

        if status in _ERROR_STATUSES and not attachments:
            # 1) 상태를 error로 리셋하여 일반 delete 경로를 열어 둠
            try:
                cinder.reset_volume_status(conn, volume_id, "error")
            except Exception:
                _logger.warning("reset_volume_status 실패: %s", volume_id, exc_info=True)
            # 2) 일반 delete 시도 (error 상태면 Ceph NotFound→DB 정리)
            try:
                conn.block_storage.delete_volume(volume_id, ignore_missing=True)
                return
            except Exception:
                _logger.info("일반 delete 실패, force_delete 폴백: %s", volume_id, exc_info=True)
            # 3) 최후 수단: os-force_delete
            try:
                cinder.force_delete_volume(conn, volume_id)
            except Exception as e:
                _logger.warning("force_delete 실패: %s %s", volume_id, e, exc_info=True)
                raise HTTPException(status_code=400, detail=f"볼륨 강제 삭제 실패: {e}")
            return

        try:
            conn.block_storage.delete_volume(volume_id, ignore_missing=True)
        except Exception as e:
            _logger.warning("볼륨 삭제 실패: %s", e)
            raise HTTPException(status_code=400, detail=f"볼륨 삭제 실패: {e}")

    try:
        await asyncio.to_thread(_delete)
    except HTTPException:
        raise


@router.post("/volumes/{volume_id}/force-delete", dependencies=[Depends(require_admin)], status_code=204)
async def force_delete_admin_volume(
    volume_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """볼륨을 강제 삭제한다. status 무관, attachments 있으면 거부."""
    from openstack.exceptions import ResourceNotFound

    from app.services import cinder

    def _force_delete():
        try:
            v = conn.block_storage.get_volume(volume_id)
        except ResourceNotFound:
            return
        if list(getattr(v, "attachments", []) or []):
            raise HTTPException(status_code=409, detail="attached 볼륨은 강제 삭제할 수 없습니다. 먼저 detach 하세요.")
        try:
            cinder.reset_volume_status(conn, volume_id, "error")
        except Exception:
            _logger.warning("reset_volume_status 실패: %s", volume_id, exc_info=True)
        try:
            conn.block_storage.delete_volume(volume_id, ignore_missing=True)
            return
        except Exception:
            _logger.info("일반 delete 실패, force_delete 폴백: %s", volume_id, exc_info=True)
        try:
            cinder.force_delete_volume(conn, volume_id)
        except Exception as e:
            _logger.warning("force_delete 실패: %s %s", volume_id, e, exc_info=True)
            raise HTTPException(status_code=400, detail=f"볼륨 강제 삭제 실패: {e}")

    try:
        await asyncio.to_thread(_force_delete)
    except HTTPException:
        raise


@router.post("/volumes/{volume_id}/extend", dependencies=[Depends(require_admin)])
async def extend_volume(
    volume_id: str,
    req: ExtendVolumeRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """볼륨 용량 확장."""

    def _extend():
        try:
            conn.block_storage.extend_volume(volume_id, req.new_size)
            return {"status": "extending"}
        except Exception as e:
            _logger.warning("볼륨 확장 실패: %s", e)

            raise HTTPException(status_code=400, detail="볼륨 확장 실패")

    try:
        return await asyncio.to_thread(_extend)
    except HTTPException:
        raise


@router.post("/volumes/{volume_id}/reset-status", dependencies=[Depends(require_admin)])
async def reset_volume_status(
    volume_id: str,
    req: ResetVolumeStatusRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """볼륨 상태 초기화."""

    def _reset():
        try:
            conn.block_storage.reset_volume_status(volume_id, req.status)
            return {"status": req.status}
        except Exception as e:
            _logger.warning("볼륨 상태 초기화 실패: %s", e)

            raise HTTPException(status_code=400, detail="볼륨 상태 초기화 실패")

    try:
        return await asyncio.to_thread(_reset)
    except HTTPException:
        raise


class LiveMigrateRequest(BaseModel):
    host: str | None = None
    block_migration: str = "auto"


class ColdMigrateRequest(BaseModel):
    host: str | None = None


class EvacuateRequest(BaseModel):
    host: str | None = None
    on_shared_storage: bool = False


@router.get("/compute-hosts", dependencies=[Depends(require_admin)])
async def list_compute_hosts(
    server_id: str | None = Query(None),
    cpu_filter: bool = Query(True),
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """마이그레이션 가능한 컴퓨트 호스트 목록.

    server_id가 주어지면 해당 인스턴스의 현재 호스트를 소스로 삼아 소스 자신을 제외한다.
    cpu_filter=true(기본)이면 동일 CPU 모델 호스트만 반환(라이브 마이그레이션용).
    cpu_filter=false이면 CPU 모델 무관 전체 반환(콜드 마이그레이션용).
    """
    try:
        source_host: str | None = None
        if server_id:
            try:
                srv = await asyncio.to_thread(conn.compute.get_server, server_id)
                source_host = getattr(srv, "compute_host", None)
            except Exception:
                pass
        return await asyncio.to_thread(nova.list_compute_hosts, conn, source_host, cpu_filter)
    except Exception:
        raise HTTPException(status_code=500, detail="컴퓨트 호스트 목록 조회 실패")


@router.post("/instances/{server_id}/live-migrate", dependencies=[Depends(require_admin)])
async def live_migrate_instance(
    server_id: str,
    req: LiveMigrateRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """인스턴스 라이브 마이그레이션."""
    try:
        await asyncio.to_thread(nova.live_migrate_server, conn, server_id, req.host, req.block_migration)
        return {"status": "migrating"}
    except Exception as e:
        _logger.warning("라이브 마이그레이션 실패: %s", e)
        raise HTTPException(status_code=400, detail=nova._extract_os_error(e))


@router.post("/instances/{server_id}/cold-migrate", dependencies=[Depends(require_admin)])
async def cold_migrate_instance(
    server_id: str,
    req: ColdMigrateRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """인스턴스 콜드 마이그레이션. host를 지정하면 해당 호스트로 이동한다."""
    try:
        await asyncio.to_thread(nova.cold_migrate_server, conn, server_id, req.host)
        return {"status": "migrating"}
    except Exception as e:
        _logger.warning("콜드 마이그레이션 실패: %s", e)
        raise HTTPException(status_code=400, detail=nova._extract_os_error(e))


@router.post("/instances/{server_id}/evacuate", dependencies=[Depends(require_admin)])
async def evacuate_instance(
    server_id: str,
    req: EvacuateRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """호스트 장애 인스턴스 강제 이주(evacuate).

    host가 지정되면 해당 호스트로, 생략하면 Nova 스케줄러가 자동 선택한다.
    """
    try:
        await asyncio.to_thread(nova.evacuate_server, conn, server_id, req.host, req.on_shared_storage)
        return {"status": "evacuating"}
    except Exception as e:
        _logger.warning("evacuate 실패: %s", e)
        raise HTTPException(status_code=400, detail=nova._extract_os_error(e))


@router.get("/instances/{server_id}/migration-status", dependencies=[Depends(require_admin)])
async def get_migration_status(
    server_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """인스턴스의 현재 호스트 + 진행 중 마이그레이션 상태 조회.

    MIGRATING 중이면 source→dest·메모리 진행률을 포함한다.
    실패 시 실패 사유를 포함한다. 폴링용으로 설계됨(예외는 fail-soft).
    """
    return await asyncio.to_thread(nova.get_server_migration_status, conn, server_id)


@router.post("/instances/{server_id}/live-migrate/abort", dependencies=[Depends(require_admin)])
async def abort_live_migration(
    server_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """진행 중 라이브 마이그레이션 중단."""
    try:
        await asyncio.to_thread(nova.abort_live_migration, conn, server_id)
        return {"status": "aborted"}
    except Exception as e:
        _logger.warning("라이브 마이그레이션 중단 실패: %s", e)
        raise HTTPException(status_code=400, detail=nova._extract_os_error(e))


@router.post("/instances/{server_id}/live-migrate/force-complete", dependencies=[Depends(require_admin)])
async def force_complete_live_migration(
    server_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """진행 중 라이브 마이그레이션 강제 완료."""
    try:
        await asyncio.to_thread(nova.force_complete_live_migration, conn, server_id)
        return {"status": "force-completed"}
    except Exception as e:
        _logger.warning("라이브 마이그레이션 강제 완료 실패: %s", e)
        raise HTTPException(status_code=400, detail=nova._extract_os_error(e))


@router.post("/instances/{server_id}/confirm-resize", dependencies=[Depends(require_admin)])
async def confirm_resize_instance(
    server_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """콜드 마이그레이션 후 리사이즈 확인."""
    try:
        await asyncio.to_thread(nova.confirm_resize_server, conn, server_id)
        return {"status": "confirmed"}
    except Exception as e:
        _logger.warning("리사이즈 확인 실패: %s", e)

        raise HTTPException(status_code=400, detail="리사이즈 확인 실패")


class ResizeRequest(BaseModel):
    flavor_id: str


@router.post("/instances/{server_id}/resize", dependencies=[Depends(require_admin)])
async def resize_instance(
    server_id: str,
    req: ResizeRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    """인스턴스 플레이버 변경 (cold resize). 완료 후 confirm-resize 또는 revert-resize 필요."""
    try:
        await asyncio.to_thread(nova.resize_server, conn, server_id, req.flavor_id)
        project_id = token_info.get("project_id", "")
        await invalidate(f"afterglow:nova:{project_id}:instances:*")
        return {"status": "resizing"}
    except Exception as e:
        _logger.warning("리사이즈 실패: %s", e)
        raise HTTPException(status_code=400, detail="리사이즈 실패")


@router.post("/instances/{server_id}/revert-resize", dependencies=[Depends(require_admin)])
async def revert_resize_instance(
    server_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    """리사이즈 취소 — VERIFY_RESIZE 상태에서 이전 플레이버로 복귀."""
    try:
        await asyncio.to_thread(nova.revert_resize_server, conn, server_id)
        project_id = token_info.get("project_id", "")
        await invalidate(f"afterglow:nova:{project_id}:instances:*")
        return {"status": "reverting"}
    except Exception as e:
        _logger.warning("리사이즈 취소 실패: %s", e)
        raise HTTPException(status_code=400, detail="리사이즈 취소 실패")


# ---------------------------------------------------------------------------
# 인스턴스 복구 (관리자 전용)
# ---------------------------------------------------------------------------


@router.get("/instances/{server_id}/recovery-analysis", dependencies=[Depends(require_admin)])
async def get_recovery_analysis(
    server_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """ERROR 인스턴스 진단 — 안전 검사 5종 + 시나리오 판정 + 복구 권장 단계 반환.

    ERROR 상태가 아닌 경우에도 200을 반환하며 checks의 is_error_state 항목에 반영된다.
    """
    try:
        return await asyncio.to_thread(instance_recovery.analyze_error_instance, conn, server_id)
    except Exception as e:
        _logger.warning("복구 분석 실패: %s", e)
        raise HTTPException(status_code=500, detail="복구 분석 중 오류가 발생했습니다")


@router.post("/instances/{server_id}/recover", dependencies=[Depends(require_admin)])
async def recover_instance(
    server_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    """ERROR 인스턴스 복구 실행.

    실행 직전 안전 검사를 서버측에서 재수행한다(fail-closed).
    auto_executable=False이면 409를 반환하고 아무 작업도 수행하지 않는다.
    성공·실패 모두 활동 기록에 남긴다.
    """
    try:
        result = await asyncio.to_thread(instance_recovery.execute_recovery, conn, server_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        _logger.warning("복구 실행 실패: %s", e)
        raise HTTPException(status_code=500, detail="복구 실행 중 오류가 발생했습니다")

    status = "success" if result.get("executed") else "error"
    try:
        await rec(
            token_info,
            conn,
            resource_type="instance",
            action="recover",
            status=status,
            resource_id=server_id,
            extra={"scenario": result.get("scenario"), "steps": result.get("steps")},
        )
    except Exception:
        pass  # 활동 기록 실패는 복구 결과에 영향을 주지 않는다

    return result


class VolumeTransferRequest(BaseModel):
    target_project_id: str


@router.post("/volumes/{volume_id}/transfer", dependencies=[Depends(require_admin)])
async def transfer_volume(
    volume_id: str,
    req: VolumeTransferRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """볼륨을 다른 프로젝트로 이전 (관리자 전용)."""
    try:

        def _transfer():
            bs_endpoint = conn.block_storage.get_endpoint()
            # 1. 이전 생성
            create_resp = conn.session.post(
                f"{bs_endpoint}/os-volume-transfer",
                json={"transfer": {"name": f"admin-transfer-{volume_id[:8]}", "volume_id": volume_id}},
            )
            transfer = create_resp.json().get("transfer", {})
            transfer_id = transfer.get("id")
            auth_key = transfer.get("auth_key")
            if not transfer_id or not auth_key:
                raise Exception("이전 생성 실패: transfer_id 또는 auth_key를 받지 못했습니다")
            # 2. 대상 프로젝트 범위로 이전 수락
            accept_resp = conn.session.post(
                f"{bs_endpoint}/os-volume-transfer/{transfer_id}/accept",
                json={"accept": {"auth_key": auth_key}},
                endpoint_override=None,
                headers={"X-Project-Id": req.target_project_id},
            )
            result = accept_resp.json().get("transfer", {})
            return {"status": "transferred", "volume_id": result.get("volume_id", volume_id)}

        return await asyncio.to_thread(_transfer)
    except Exception as e:
        _logger.warning("볼륨 이전 실패", exc_info=True)
        _logger.warning("볼륨 이전 실패: %s", e)

        raise HTTPException(status_code=400, detail="볼륨 이전 실패")


# ===========================================================================
# 네트워크 관리 (관리자)
# ===========================================================================


class CreateNetworkRequest(BaseModel):
    name: str
    is_external: bool = False
    is_shared: bool = False
    cidr: str | None = None
    enable_dhcp: bool = True


class UpdateNetworkRequest(BaseModel):
    name: str | None = None
    is_shared: bool | None = None


class CreateRouterRequest(BaseModel):
    name: str
    external_network_id: str | None = None


class UpdateRouterRequest(BaseModel):
    name: str | None = None
    external_network_id: str | None = None


class CreateFloatingIpRequest(BaseModel):
    floating_network_id: str


class UpdatePortRequest(BaseModel):
    name: str | None = None


@router.get("/networks/{network_id}", dependencies=[Depends(require_admin)], response_model=AdminNetworkDetail)
async def get_admin_network(network_id: str, conn: openstack.connection.Connection = Depends(get_os_conn)):
    """네트워크 상세 조회 (관리자)."""
    try:
        return await asyncio.to_thread(neutron.get_admin_network_detail, conn, network_id)
    except Exception:
        raise HTTPException(status_code=404, detail="네트워크를 찾을 수 없습니다")


@router.get("/subnets/{subnet_id}", dependencies=[Depends(require_admin)], response_model=AdminSubnetDetail)
async def get_admin_subnet(subnet_id: str, conn: openstack.connection.Connection = Depends(get_os_conn)):
    """서브넷 상세 조회 (관리자)."""
    from openstack.exceptions import HttpException, NotFoundException, ResourceNotFound

    try:
        return await asyncio.to_thread(neutron.get_admin_subnet_detail, conn, subnet_id)
    except (NotFoundException, ResourceNotFound):
        raise HTTPException(status_code=404, detail="서브넷을 찾을 수 없습니다")
    except HttpException as exc:
        status_code = getattr(exc, "status_code", None) or 500
        if status_code >= 500:
            _logger.error("OpenStack upstream error fetching subnet detail for %s: %s", subnet_id, exc, exc_info=True)
            raise HTTPException(status_code=status_code, detail="OpenStack service error")
        raise HTTPException(status_code=status_code, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        _logger.error("Unexpected error fetching admin subnet detail for %s: %s", subnet_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail="서브넷 상세 조회 실패")


@router.post("/networks", dependencies=[Depends(require_admin)], status_code=201)
async def create_network(
    req: CreateNetworkRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """네트워크 생성 (선택적으로 서브넷 포함)."""

    def _create():
        try:
            net_kwargs: dict = {
                "name": req.name,
                "is_router_external": req.is_external,
                "is_shared": req.is_shared,
            }
            n = conn.network.create_network(**net_kwargs)
            if req.cidr:
                conn.network.create_subnet(
                    network_id=n.id,
                    name=f"{req.name}-subnet",
                    cidr=req.cidr,
                    ip_version=4,
                    is_dhcp_enabled=req.enable_dhcp,
                )
            return {
                "id": n.id,
                "name": n.name or "",
                "status": n.status or "",
                "is_external": bool(n.is_router_external),
                "is_shared": bool(n.is_shared),
                "subnets": n.subnet_ids or [],
            }
        except Exception as e:
            _logger.warning("네트워크 생성 실패: %s", e)

            raise HTTPException(status_code=400, detail="네트워크 생성 실패")

    try:
        return await asyncio.to_thread(_create)
    except HTTPException:
        raise


@router.put("/networks/{network_id}", dependencies=[Depends(require_admin)])
async def update_network(
    network_id: str,
    req: UpdateNetworkRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """네트워크 수정."""

    def _update():
        kwargs: dict = {}
        if req.name is not None:
            kwargs["name"] = req.name
        if req.is_shared is not None:
            kwargs["is_shared"] = req.is_shared
        try:
            n = conn.network.update_network(network_id, **kwargs)
            return {
                "id": n.id,
                "name": n.name or "",
                "status": n.status or "",
                "is_external": bool(n.is_router_external),
                "is_shared": bool(n.is_shared),
            }
        except Exception as e:
            _logger.warning("네트워크 수정 실패: %s", e)

            raise HTTPException(status_code=400, detail="네트워크 수정 실패")

    try:
        return await asyncio.to_thread(_update)
    except HTTPException:
        raise


@router.delete("/networks/{network_id}", dependencies=[Depends(require_admin)], status_code=204)
async def delete_network(
    network_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """네트워크 삭제."""

    def _delete():
        try:
            conn.network.delete_network(network_id, ignore_missing=True)
        except Exception as e:
            _logger.warning("네트워크 삭제 실패: %s", e)

            raise HTTPException(status_code=400, detail="네트워크 삭제 실패")

    try:
        await asyncio.to_thread(_delete)
    except HTTPException:
        raise


@router.post("/floating-ips", dependencies=[Depends(require_admin)], status_code=201)
async def create_floating_ip(
    req: CreateFloatingIpRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """Floating IP 생성."""

    def _create():
        try:
            fip = conn.network.create_ip(floating_network_id=req.floating_network_id)
            return {
                "id": fip.id,
                "floating_ip_address": fip.floating_ip_address or "",
                "fixed_ip_address": fip.fixed_ip_address,
                "status": fip.status or "",
                "port_id": fip.port_id,
                "project_id": getattr(fip, "project_id", None),
            }
        except Exception as e:
            _logger.warning("Floating IP 생성 실패: %s", e)

            raise HTTPException(status_code=400, detail="Floating IP 생성 실패")

    try:
        return await asyncio.to_thread(_create)
    except HTTPException:
        raise


@router.delete("/floating-ips/{fip_id}", dependencies=[Depends(require_admin)], status_code=204)
async def delete_floating_ip(
    fip_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """Floating IP 삭제."""

    def _delete():
        try:
            conn.network.delete_ip(fip_id, ignore_missing=True)
        except Exception as e:
            _logger.warning("Floating IP 삭제 실패: %s", e)

            raise HTTPException(status_code=400, detail="Floating IP 삭제 실패")

    try:
        await asyncio.to_thread(_delete)
    except HTTPException:
        raise


@router.post("/routers", dependencies=[Depends(require_admin)], status_code=201)
async def create_router(
    req: CreateRouterRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """라우터 생성."""

    def _create():
        try:
            kwargs: dict = {"name": req.name}
            if req.external_network_id:
                kwargs["external_gateway_info"] = {"network_id": req.external_network_id}
            r = conn.network.create_router(**kwargs)
            return {
                "id": r.id,
                "name": r.name or "",
                "status": r.status or "",
                "external_gateway_network_id": (r.external_gateway_info or {}).get("network_id"),
                "project_id": getattr(r, "project_id", None),
            }
        except Exception as e:
            _logger.warning("라우터 생성 실패: %s", e)

            raise HTTPException(status_code=400, detail="라우터 생성 실패")

    try:
        return await asyncio.to_thread(_create)
    except HTTPException:
        raise


@router.put("/routers/{router_id}", dependencies=[Depends(require_admin)])
async def update_router(
    router_id: str,
    req: UpdateRouterRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """라우터 수정."""

    def _update():
        kwargs: dict = {}
        if req.name is not None:
            kwargs["name"] = req.name
        if req.external_network_id is not None:
            kwargs["external_gateway_info"] = {"network_id": req.external_network_id} if req.external_network_id else {}
        try:
            r = conn.network.update_router(router_id, **kwargs)
            return {
                "id": r.id,
                "name": r.name or "",
                "status": r.status or "",
                "external_gateway_network_id": (r.external_gateway_info or {}).get("network_id"),
            }
        except Exception as e:
            _logger.warning("라우터 수정 실패: %s", e)

            raise HTTPException(status_code=400, detail="라우터 수정 실패")

    try:
        return await asyncio.to_thread(_update)
    except HTTPException:
        raise


@router.delete("/routers/{router_id}", dependencies=[Depends(require_admin)], status_code=204)
async def delete_router(
    router_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """라우터 삭제."""

    def _delete():
        try:
            conn.network.delete_router(router_id, ignore_missing=True)
        except Exception as e:
            _logger.warning("라우터 삭제 실패: %s", e)

            raise HTTPException(status_code=400, detail="라우터 삭제 실패")

    try:
        await asyncio.to_thread(_delete)
    except HTTPException:
        raise


@router.put("/ports/{port_id}", dependencies=[Depends(require_admin)])
async def update_port(
    port_id: str,
    req: UpdatePortRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """포트 수정 (이름)."""

    def _update():
        kwargs: dict = {}
        if req.name is not None:
            kwargs["name"] = req.name
        try:
            p = conn.network.update_port(port_id, **kwargs)
            return {
                "id": p.id,
                "name": p.name or "",
                "status": p.status or "",
                "device_owner": p.device_owner or "",
            }
        except Exception as e:
            _logger.warning("포트 수정 실패: %s", e)

            raise HTTPException(status_code=400, detail="포트 수정 실패")

    try:
        return await asyncio.to_thread(_update)
    except HTTPException:
        raise


@router.delete("/ports/{port_id}", dependencies=[Depends(require_admin)], status_code=204)
async def delete_port(
    port_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """포트 삭제."""

    def _delete():
        try:
            conn.network.delete_port(port_id, ignore_missing=True)
        except Exception as e:
            _logger.warning("포트 삭제 실패: %s", e)

            raise HTTPException(status_code=400, detail="포트 삭제 실패")

    try:
        await asyncio.to_thread(_delete)
    except HTTPException:
        raise


# ===========================================================================
# GPU Quota 관리 (관리자)
# ===========================================================================


class GpuQuotaRequest(BaseModel):
    gpu_type: str  # PCI alias (예: "RTX3090")
    limit: int  # -1 = 무제한


@router.get("/gpu-aliases", dependencies=[Depends(require_admin)])
async def get_gpu_aliases():
    """클러스터의 모든 GPU PCI alias 목록 반환 (flavor + Placement API 통합, admin connection 사용)."""
    from app.services.gpu_inventory import get_all_gpu_aliases

    aliases = await get_all_gpu_aliases()
    return {"aliases": aliases}


@router.get("/gpu-quotas/defaults", dependencies=[Depends(require_admin)])
async def get_default_gpu_quotas(conn: openstack.connection.Connection = Depends(get_os_conn)):
    """전체 프로젝트 기본 GPU quota 조회."""
    try:
        from app.services.gpu_quota import DEFAULT_PROJECT_ID, get_project_gpu_quotas

        return await get_project_gpu_quotas(conn, DEFAULT_PROJECT_ID)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="GPU quota 서비스를 사용할 수 없습니다") from exc


@router.put("/gpu-quotas/defaults", dependencies=[Depends(require_admin)])
async def set_default_gpu_quota(req: GpuQuotaRequest, conn: openstack.connection.Connection = Depends(get_os_conn)):
    """전체 프로젝트 기본 GPU quota 설정 (upsert)."""
    try:
        from app.services.gpu_quota import DEFAULT_PROJECT_ID, set_project_gpu_quota

        quota = await set_project_gpu_quota(conn, DEFAULT_PROJECT_ID, req.gpu_type, req.limit)
        await invalidate("afterglow:nova:*:flavors")
        return quota
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="GPU quota 서비스를 사용할 수 없습니다") from exc


@router.delete("/gpu-quotas/defaults/{gpu_type}", dependencies=[Depends(require_admin)], status_code=204)
async def delete_default_gpu_quota(gpu_type: str, conn: openstack.connection.Connection = Depends(get_os_conn)):
    """전체 프로젝트 기본 GPU quota 삭제 (기본값 0으로 복귀)."""
    try:
        from app.services.gpu_quota import DEFAULT_PROJECT_ID, delete_project_gpu_quota

        await delete_project_gpu_quota(conn, DEFAULT_PROJECT_ID, gpu_type)
        await invalidate("afterglow:nova:*:flavors")
    except Exception as exc:
        raise HTTPException(status_code=503, detail="GPU quota 서비스를 사용할 수 없습니다") from exc


@router.get("/gpu-quotas/{project_id}", dependencies=[Depends(require_admin)])
async def get_gpu_quotas(project_id: str, conn: openstack.connection.Connection = Depends(get_os_conn)):
    """프로젝트의 GPU quota 목록 + 현재 사용량 조회."""
    try:
        from app.services.gpu_quota import get_effective_gpu_quota_status

        return await get_effective_gpu_quota_status(conn, project_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="GPU quota 서비스를 사용할 수 없습니다") from exc


@router.put("/gpu-quotas/{project_id}", dependencies=[Depends(require_admin)])
async def set_gpu_quota(
    project_id: str, req: GpuQuotaRequest, conn: openstack.connection.Connection = Depends(get_os_conn)
):
    """프로젝트의 GPU quota 설정 (upsert)."""
    try:
        from app.services.gpu_quota import set_project_gpu_quota

        quota = await set_project_gpu_quota(conn, project_id, req.gpu_type, req.limit)
        await invalidate(f"afterglow:nova:{project_id}:flavors")
        return quota
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="GPU quota 서비스를 사용할 수 없습니다") from exc


@router.delete("/gpu-quotas/{project_id}/{gpu_type}", dependencies=[Depends(require_admin)], status_code=204)
async def delete_gpu_quota(
    project_id: str, gpu_type: str, conn: openstack.connection.Connection = Depends(get_os_conn)
):
    """프로젝트의 특정 GPU quota 삭제 (기본값으로 폴백)."""
    try:
        from app.services.gpu_quota import delete_project_gpu_quota

        await delete_project_gpu_quota(conn, project_id, gpu_type)
        await invalidate(f"afterglow:nova:{project_id}:flavors")
    except Exception as exc:
        raise HTTPException(status_code=503, detail="GPU quota 서비스를 사용할 수 없습니다") from exc


# ===========================================================================
# 시스템 버전 정보
# ===========================================================================

_admin_start_time: float = __import__("time").time()


_backend_version: str = read_app_version()


@router.get("/version", dependencies=[Depends(require_admin)])
async def admin_version():
    """플랫폼 버전, 런타임, 의존성, Git 정보 반환."""
    import importlib.metadata
    import platform
    import subprocess
    import time

    # 의존성 버전
    deps: dict = {}
    for pkg in ("fastapi", "openstacksdk", "python-keystoneclient", "pydantic", "uvicorn"):
        try:
            deps[pkg] = importlib.metadata.version(pkg)
        except importlib.metadata.PackageNotFoundError:
            deps[pkg] = None

    # Git 정보 (Docker 환경에서는 없을 수 있음)
    def _git(args: list[str]) -> str | None:
        try:
            result = subprocess.run(
                ["git"] + args,
                capture_output=True,
                text=True,
                timeout=3,
                cwd="/app",
            )
            return result.stdout.strip() or None
        except Exception:
            return None

    git_commit = _git(["rev-parse", "--short", "HEAD"])
    git_tag = _git(["describe", "--tags", "--abbrev=0"])
    git_branch = _git(["rev-parse", "--abbrev-ref", "HEAD"])

    return {
        "platform": {
            "backend_version": _backend_version,
        },
        "runtime": {
            "python_version": platform.python_version(),
            "uptime_seconds": int(time.time() - _admin_start_time),
        },
        "dependencies": deps,
        "git": {
            "commit": git_commit,
            "tag": git_tag,
            "branch": git_branch,
        },
    }
