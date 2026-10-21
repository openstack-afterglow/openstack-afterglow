from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import openstack
import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from app.api.common.admin_resource_scope import resolve_scope
from app.api.common.owner_check import assert_resource_owner
from app.api.deps import CacheMode, cache_mode, get_os_conn, get_token_info, require_admin
from app.models.database import (
    CreateBackupRequest,
    CreateDatabaseRequest,
    CreateDbInstanceRequest,
    CreateUserRequest,
    DbAutoBackupConfigRequest,
    RestoreFromBackupRequest,
)
from app.services import cache
from app.services.cache import invalidation, keys

_logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Floating IP 자동 할당 헬퍼
# ---------------------------------------------------------------------------


def _attach_fip_to_instance_sync(conn, instance_id: str) -> dict:
    """인스턴스 IP → port → 외부 네트워크 → FIP 생성/할당. 동기 함수.

    반환: {"floating_ip_address": str, "floating_ip_id": str, "port_id": str}
    실패 시 RuntimeError.
    """
    from app.services import neutron, trove

    inst = trove.get_instance(conn, instance_id)
    ip = inst.get("ip")
    if not ip:
        raise RuntimeError("인스턴스에 IP가 아직 할당되지 않았습니다 (BUILD 중)")

    # IP 매칭으로 port 찾기 (Trove backend server 의 port 는 사용자 네트워크에 attach)
    target_port = None
    for p in conn.network.ports():
        for fi in p.fixed_ips or []:
            if fi.get("ip_address") == ip:
                target_port = p
                break
        if target_port:
            break
    if not target_port:
        raise RuntimeError(f"IP {ip} 에 대응하는 포트를 찾을 수 없습니다")

    # 외부 네트워크 자동 탐색 (router → external_gateway_info)
    subnet_ids = {fi.get("subnet_id") for fi in (target_port.fixed_ips or []) if fi.get("subnet_id")}
    ext_net_id = neutron.find_external_network_for_subnets(conn, subnet_ids)
    if not ext_net_id:
        raise RuntimeError("연결된 라우터의 외부 네트워크를 찾을 수 없습니다")

    # 기존 FIP 가 이미 이 port 에 연결되어있으면 재할당 안 함
    for f in conn.network.ips():
        if getattr(f, "port_id", None) == target_port.id:
            return {
                "floating_ip_address": f.floating_ip_address,
                "floating_ip_id": f.id,
                "port_id": target_port.id,
            }

    fip = neutron.create_floating_ip(conn, ext_net_id)
    neutron.associate_floating_ip(conn, fip.id, instance_id, port_id=target_port.id)
    return {
        "floating_ip_address": fip.floating_ip_address,
        "floating_ip_id": fip.id,
        "port_id": target_port.id,
    }


async def _run_attach_fip_bg(project_id: str, instance_id: str, max_wait_seconds: int = 600) -> None:
    """신규 인스턴스의 IP 할당 대기 후 FIP 자동 할당 (best-effort)."""
    try:
        from app.services import trove
        from app.services.keystone import get_admin_connection_for_project

        conn = await asyncio.to_thread(get_admin_connection_for_project, project_id)

        # IP 폴링: 5초 간격, 최대 max_wait_seconds
        ip = ""
        for _ in range(max_wait_seconds // 5):
            try:
                inst = await asyncio.to_thread(trove.get_instance, conn, instance_id)
                if inst.get("ip"):
                    ip = inst["ip"]
                    break
                if inst.get("status") in ("ERROR", "FAILED"):
                    _logger.warning("FIP 자동 할당 중단: 인스턴스 %s 상태 %s", instance_id, inst.get("status"))
                    return
            except Exception:
                pass
            await asyncio.sleep(5)

        if not ip:
            _logger.warning("FIP 자동 할당 타임아웃: 인스턴스 %s IP 미할당", instance_id)
            return

        result = await asyncio.to_thread(_attach_fip_to_instance_sync, conn, instance_id)
        _logger.info("FIP 자동 할당 완료 instance=%s fip=%s", instance_id, result["floating_ip_address"])
    except Exception:
        _logger.warning("FIP 자동 할당 실패 instance=%s", instance_id, exc_info=True)


async def _assert_db_instance_owner(
    conn: openstack.connection.Connection,
    instance_id: str,
    token_info: dict,
):
    """Trove 인스턴스 owner 검증 — sub-resource (databases/users/backups) 도
    instance_id 가 caller-owned 면 간접적으로 보호된다."""
    try:
        inst = await asyncio.to_thread(conn.database.get_instance, instance_id)
    except Exception:
        raise HTTPException(status_code=404, detail="DB 인스턴스를 찾을 수 없습니다")
    assert_resource_owner(inst, conn, token_info, not_found_detail="DB 인스턴스를 찾을 수 없습니다")


# ---------------------------------------------------------------------------
# 플레이버 / 데이터스토어 (인스턴스 생성에 필요한 메타데이터)
# ---------------------------------------------------------------------------


@router.get("/flavors")
async def list_db_flavors(
    conn: openstack.connection.Connection = Depends(get_os_conn),
    cm: CacheMode = Depends(cache_mode),
):
    """DB 플레이버 목록."""
    from app.services import trove

    pid = getattr(conn, "_afterglow_project_id", "unknown")
    key = keys.project_key("trove", pid, "flavors")
    try:
        return await cache.cached_call(
            key, cache.ttl_static(), lambda: trove.list_flavors(conn), enabled=cm.enabled, refresh=cm.refresh
        )
    except Exception:
        raise HTTPException(status_code=500, detail="DB 플레이버 목록 조회 실패")


@router.get("/datastores")
async def list_datastores(
    conn: openstack.connection.Connection = Depends(get_os_conn),
    cm: CacheMode = Depends(cache_mode),
):
    """데이터스토어(MySQL, MariaDB, PostgreSQL 등) 및 버전 목록."""
    from app.services import trove

    pid = getattr(conn, "_afterglow_project_id", "unknown")
    key = keys.project_key("trove", pid, "datastores")
    try:
        return await cache.cached_call(
            key, cache.ttl_static(), lambda: trove.list_datastores(conn), enabled=cm.enabled, refresh=cm.refresh
        )
    except Exception:
        raise HTTPException(status_code=500, detail="데이터스토어 목록 조회 실패")


@router.get("/configurations")
async def list_db_configurations(
    conn: openstack.connection.Connection = Depends(get_os_conn),
    cm: CacheMode = Depends(cache_mode),
):
    """DB Configuration group 목록."""
    from app.services import trove

    pid = getattr(conn, "_afterglow_project_id", "unknown")
    key = keys.project_key("trove", pid, "configurations")
    try:
        return await cache.cached_call(
            key, cache.ttl_slow(), lambda: trove.list_configurations(conn), enabled=cm.enabled, refresh=cm.refresh
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Configuration group 목록 조회 실패")


@router.get("/volume-types")
async def list_db_volume_types(
    conn: openstack.connection.Connection = Depends(get_os_conn),
    cm: CacheMode = Depends(cache_mode),
):
    """볼륨 타입 목록 (DB 생성 폼용)."""
    from app.services import cinder

    pid = getattr(conn, "_afterglow_project_id", "unknown")
    key = keys.project_key("cinder", pid, "volume-types")
    try:
        return await cache.cached_call(
            key, cache.ttl_static(), lambda: cinder.list_volume_types(conn), enabled=cm.enabled, refresh=cm.refresh
        )
    except Exception:
        raise HTTPException(status_code=500, detail="볼륨 타입 목록 조회 실패")


# ---------------------------------------------------------------------------
# 백업 (인스턴스 ID 없는 전역 목록 / 삭제 / 복원)
# ---------------------------------------------------------------------------


async def _assert_db_backup_owner(
    conn: openstack.connection.Connection,
    backup_id: str,
    token_info: dict,
):
    """Trove backup owner 검증."""
    try:
        bk = await asyncio.to_thread(conn.database.get_backup, backup_id)
    except Exception:
        raise HTTPException(status_code=404, detail="백업을 찾을 수 없습니다")
    assert_resource_owner(bk, conn, token_info, not_found_detail="백업을 찾을 수 없습니다")


@router.get("/backups")
async def list_all_backups(
    conn: openstack.connection.Connection = Depends(get_os_conn),
    cm: CacheMode = Depends(cache_mode),
):
    """현재 프로젝트의 전체 DB 백업 목록 (인스턴스 무관). 복원 폼 등에서 사용.

    conn 이 project-scoped 이므로 별도 owner 체크 불필요 (Trove 가 tenant 필터링).
    """
    from app.services import trove

    pid = getattr(conn, "_afterglow_project_id", "unknown")
    key = keys.project_key("trove", pid, "backups")
    try:
        return await cache.cached_call(
            key, cache.ttl_slow(), lambda: trove.list_backups(conn), enabled=cm.enabled, refresh=cm.refresh
        )
    except Exception:
        raise HTTPException(status_code=500, detail="백업 목록 조회 실패")


@router.delete("/backups/{backup_id}", status_code=204)
async def delete_backup(
    backup_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    """백업 삭제."""
    from app.services import trove

    await _assert_db_backup_owner(conn, backup_id, token_info)
    try:
        await asyncio.to_thread(trove.delete_backup, conn, backup_id)
    except Exception:
        raise HTTPException(status_code=500, detail="백업 삭제 실패")
    pid = getattr(conn, "_afterglow_project_id", "unknown")
    await cache.invalidate(f"afterglow:trove:{pid}:*")
    await invalidation.invalidate_mutation_count("trove", pid)


@router.post("/restore", status_code=201)
async def restore_from_backup(
    req: RestoreFromBackupRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    """백업에서 새 인스턴스 복원."""
    from app.services import trove

    await _assert_db_backup_owner(conn, req.backup_id, token_info)
    try:
        result = await asyncio.to_thread(
            trove.create_instance,
            conn,
            req.name,
            req.flavor_id,
            req.volume_size,
            "",
            "",
            None,
            None,
            req.backup_id,
        )
    except Exception:
        raise HTTPException(status_code=500, detail="백업 복원 실패")
    pid = getattr(conn, "_afterglow_project_id", "unknown")
    await cache.invalidate(f"afterglow:trove:{pid}:*")
    await invalidation.invalidate_mutation_count("trove", pid)
    return result


# ---------------------------------------------------------------------------
# 인스턴스 목록 / 생성
# ---------------------------------------------------------------------------


@router.get("")
async def list_database_instances(
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
    all_projects: bool = Query(False, description="admin 전용: 모든 프로젝트 DB 인스턴스"),
    cm: CacheMode = Depends(cache_mode),
    domain_id: str | None = Query(None, min_length=1),
    project_id: str | None = Query(None, min_length=1),
):
    """Trove DB 인스턴스 목록. all_projects=true 는 시스템 admin 전용."""
    from app.services import trove

    if all_projects:
        await require_admin(token_info)
        scope = await asyncio.to_thread(resolve_scope, conn, domain_id, project_id)
        try:
            rows = await asyncio.to_thread(trove.list_instances_admin_all_projects, conn)
            return scope.filter(rows)
        except Exception:
            _logger.exception("관리자 DB 인스턴스 전체 조회 실패")
            raise HTTPException(status_code=500, detail="DB 인스턴스 목록 조회 실패")
    if domain_id is not None or project_id is not None:
        raise HTTPException(403, "Administrator inventory conditions require all_projects")

    pid = getattr(conn, "_afterglow_project_id", "unknown")
    key = keys.project_key("trove", pid, "instances")
    try:
        return await cache.cached_call(
            key, cache.ttl_normal(), lambda: trove.list_instances(conn), enabled=cm.enabled, refresh=cm.refresh
        )
    except Exception:
        raise HTTPException(status_code=500, detail="DB 인스턴스 목록 조회 실패")


@router.post("", status_code=201)
async def create_database_instance(
    req: CreateDbInstanceRequest,
    background_tasks: BackgroundTasks,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """DB 인스턴스 생성. is_public=True 면 백그라운드에서 floating IP 자동 할당 시도."""
    from app.services import trove

    try:
        users_raw = [u.model_dump(exclude_none=True) for u in req.users] if req.users else None
        instance = await asyncio.to_thread(
            trove.create_instance,
            conn,
            req.name,
            req.flavor_id,
            req.volume_size,
            req.datastore_type,
            req.datastore_version,
            req.databases or None,
            users_raw,
            req.restore_backup_id,
            req.availability_zone,
            req.volume_type,
            req.nics or None,
            req.locality,
            req.configuration_id,
            req.replica_of,
            req.replica_count,
        )
        if req.is_public or req.allowed_cidrs:
            try:
                await asyncio.to_thread(
                    trove.set_instance_access,
                    conn,
                    instance["id"],
                    req.is_public,
                    req.allowed_cidrs,
                )
            except Exception:
                _logger.warning("Trove set_instance_access 실패 instance=%s", instance["id"], exc_info=True)
        # is_public 시 floating IP 자동 할당 (best-effort, BUILD 완료 대기)
        if req.is_public:
            project_id = getattr(conn, "_afterglow_project_id", None)
            if project_id:
                background_tasks.add_task(_run_attach_fip_bg, project_id, instance["id"])
        pid = getattr(conn, "_afterglow_project_id", "unknown")
        await cache.invalidate(f"afterglow:trove:{pid}:*")
        await invalidation.invalidate_mutation_count("trove", pid)
        return instance
    except RuntimeError as e:
        _logger.exception(
            "DB 인스턴스 생성 실패: name=%s, datastore=%s/%s", req.name, req.datastore_type, req.datastore_version
        )
        raise HTTPException(status_code=502, detail=str(e))
    except Exception:
        _logger.exception(
            "DB 인스턴스 생성 실패: name=%s, datastore=%s/%s", req.name, req.datastore_type, req.datastore_version
        )
        raise HTTPException(status_code=500, detail="DB 인스턴스 생성 실패")


# ---------------------------------------------------------------------------
# 개별 인스턴스 — 상세 / 삭제 / 액션
# ---------------------------------------------------------------------------


@router.get("/{instance_id}")
async def get_database_instance(
    instance_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
    cm: CacheMode = Depends(cache_mode),
):
    """DB 인스턴스 상세. deleted=1 인 경우 404."""
    from app.services import trove

    await _assert_db_instance_owner(conn, instance_id, token_info)
    pid = getattr(conn, "_afterglow_project_id", "unknown")
    key = keys.project_key("trove", pid, "instances", sub=instance_id)
    try:
        inst = await cache.cached_call(
            key,
            cache.ttl_normal(),
            lambda: trove.get_instance(conn, instance_id),
            enabled=cm.enabled,
            refresh=cm.refresh,
        )
    except Exception:
        raise HTTPException(status_code=404, detail="DB 인스턴스를 찾을 수 없습니다")
    if inst.get("deleted"):
        raise HTTPException(status_code=404, detail="DB 인스턴스를 찾을 수 없습니다")
    return inst


@router.delete("/{instance_id}", status_code=204)
async def delete_database_instance(
    instance_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    """DB 인스턴스 삭제."""
    from app.services import trove

    await _assert_db_instance_owner(conn, instance_id, token_info)
    try:
        await asyncio.to_thread(trove.delete_instance, conn, instance_id)
    except Exception:
        raise HTTPException(status_code=500, detail="DB 인스턴스 삭제 실패")
    pid = getattr(conn, "_afterglow_project_id", "unknown")
    await cache.invalidate(f"afterglow:trove:{pid}:*")
    await invalidation.invalidate_mutation_count("trove", pid)


@router.post("/{instance_id}/restart", status_code=204)
async def restart_database_instance(
    instance_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    """DB 인스턴스 재시작."""
    from app.services import trove

    await _assert_db_instance_owner(conn, instance_id, token_info)
    try:
        await asyncio.to_thread(trove.restart_instance, conn, instance_id)
    except Exception:
        raise HTTPException(status_code=500, detail="DB 인스턴스 재시작 실패")
    pid = getattr(conn, "_afterglow_project_id", "unknown")
    await cache.invalidate(f"afterglow:trove:{pid}:*")
    await invalidation.invalidate_mutation_count("trove", pid)


@router.post("/{instance_id}/root")
async def enable_root_user(
    instance_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    """root 유저 활성화. {name, password} 반환."""
    from app.services import trove

    await _assert_db_instance_owner(conn, instance_id, token_info)
    try:
        result = await asyncio.to_thread(trove.enable_root, conn, instance_id)
    except Exception:
        raise HTTPException(status_code=500, detail="root 유저 활성화 실패")
    pid = getattr(conn, "_afterglow_project_id", "unknown")
    await cache.invalidate(f"afterglow:trove:{pid}:*")
    await invalidation.invalidate_mutation_count("trove", pid)
    return result


# ---------------------------------------------------------------------------
# 데이터베이스 서브리소스
# ---------------------------------------------------------------------------


@router.get("/{instance_id}/databases")
async def list_instance_databases(
    instance_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
    cm: CacheMode = Depends(cache_mode),
):
    """인스턴스 내 데이터베이스 목록."""
    from app.services import trove

    await _assert_db_instance_owner(conn, instance_id, token_info)
    pid = getattr(conn, "_afterglow_project_id", "unknown")
    key = keys.project_key("trove", pid, f"instances:{instance_id}:databases")
    try:
        return await cache.cached_call(
            key,
            cache.ttl_normal(),
            lambda: trove.list_databases(conn, instance_id),
            enabled=cm.enabled,
            refresh=cm.refresh,
        )
    except Exception:
        raise HTTPException(status_code=500, detail="데이터베이스 목록 조회 실패")


@router.post("/{instance_id}/databases", status_code=201)
async def create_instance_database(
    instance_id: str,
    req: CreateDatabaseRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    """인스턴스 내 데이터베이스 생성."""
    from app.services import trove

    await _assert_db_instance_owner(conn, instance_id, token_info)
    try:
        await asyncio.to_thread(trove.create_database, conn, instance_id, req.name, req.character_set, req.collate)
    except Exception:
        _logger.exception("DB 생성 실패 instance=%s name=%s", instance_id, req.name)
        raise HTTPException(status_code=500, detail="데이터베이스 생성 실패")
    pid = getattr(conn, "_afterglow_project_id", "unknown")
    await cache.invalidate(f"afterglow:trove:{pid}:*")
    await invalidation.invalidate_mutation_count("trove", pid)
    return {"name": req.name}


@router.delete("/{instance_id}/databases/{db_name}", status_code=204)
async def delete_instance_database(
    instance_id: str,
    db_name: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    """인스턴스 내 데이터베이스 삭제."""
    from app.services import trove

    await _assert_db_instance_owner(conn, instance_id, token_info)
    try:
        await asyncio.to_thread(trove.delete_database, conn, instance_id, db_name)
    except Exception:
        raise HTTPException(status_code=500, detail="데이터베이스 삭제 실패")
    pid = getattr(conn, "_afterglow_project_id", "unknown")
    await cache.invalidate(f"afterglow:trove:{pid}:*")
    await invalidation.invalidate_mutation_count("trove", pid)


# ---------------------------------------------------------------------------
# 유저 서브리소스
# ---------------------------------------------------------------------------


@router.get("/{instance_id}/users")
async def list_instance_users(
    instance_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
    cm: CacheMode = Depends(cache_mode),
):
    """인스턴스 내 유저 목록."""
    from app.services import trove

    await _assert_db_instance_owner(conn, instance_id, token_info)
    pid = getattr(conn, "_afterglow_project_id", "unknown")
    key = keys.project_key("trove", pid, f"instances:{instance_id}:users")
    try:
        return await cache.cached_call(
            key, cache.ttl_normal(), lambda: trove.list_users(conn, instance_id), enabled=cm.enabled, refresh=cm.refresh
        )
    except Exception:
        raise HTTPException(status_code=500, detail="유저 목록 조회 실패")


@router.post("/{instance_id}/users", status_code=201)
async def create_instance_user(
    instance_id: str,
    req: CreateUserRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    """인스턴스 내 유저 생성."""
    from app.services import trove

    await _assert_db_instance_owner(conn, instance_id, token_info)
    try:
        await asyncio.to_thread(
            trove.create_user,
            conn,
            instance_id,
            req.name,
            req.password,
            req.host,
            req.databases or None,
        )
    except Exception:
        _logger.exception("DB 유저 생성 실패 instance=%s name=%s host=%s", instance_id, req.name, req.host)
        raise HTTPException(status_code=500, detail="유저 생성 실패")
    pid = getattr(conn, "_afterglow_project_id", "unknown")
    await cache.invalidate(f"afterglow:trove:{pid}:*")
    await invalidation.invalidate_mutation_count("trove", pid)
    return {"name": req.name, "host": req.host}


@router.delete("/{instance_id}/users/{username}", status_code=204)
async def delete_instance_user(
    instance_id: str,
    username: str,
    host: str = Query("%", description="유저 host (예: '%', 'localhost'). Trove identity 는 name@host."),
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    """인스턴스 내 유저 삭제 (host 로 동명 유저 구분)."""
    from app.services import trove

    await _assert_db_instance_owner(conn, instance_id, token_info)
    try:
        await asyncio.to_thread(trove.delete_user, conn, instance_id, username, host)
    except Exception:
        _logger.exception("DB 유저 삭제 실패 instance=%s name=%s host=%s", instance_id, username, host)
        raise HTTPException(status_code=500, detail="유저 삭제 실패")
    pid = getattr(conn, "_afterglow_project_id", "unknown")
    await cache.invalidate(f"afterglow:trove:{pid}:*")
    await invalidation.invalidate_mutation_count("trove", pid)


# ---------------------------------------------------------------------------
# Floating IP — 수동 할당 / 해제
# ---------------------------------------------------------------------------


@router.post("/{instance_id}/floating-ip", status_code=201)
async def attach_floating_ip(
    instance_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    """인스턴스에 floating IP 자동 할당 (라우터 외부 네트워크 자동 탐색).

    이미 FIP 가 할당된 port 면 기존 FIP 정보를 반환 (멱등).
    """
    await _assert_db_instance_owner(conn, instance_id, token_info)
    try:
        result = await asyncio.to_thread(_attach_fip_to_instance_sync, conn, instance_id)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        _logger.exception("Floating IP 할당 실패 instance=%s", instance_id)
        raise HTTPException(status_code=500, detail="Floating IP 할당 실패")
    pid = getattr(conn, "_afterglow_project_id", "unknown")
    await cache.invalidate(f"afterglow:trove:{pid}:*")
    await invalidation.invalidate_mutation_count("trove", pid)
    return result


@router.delete("/{instance_id}/floating-ip", status_code=204)
async def detach_floating_ip(
    instance_id: str,
    delete: bool = Query(False, description="true 면 FIP 도 함께 삭제 (기본: dissociate 만)"),
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    """인스턴스에 연결된 floating IP 를 해제 (옵션: 삭제까지).

    FIP 가 없으면 404 반환 — UI 가 "이미 해제됨" 상태로 잘못 인식하는 것을 방지.
    """
    from app.services import neutron, trove

    await _assert_db_instance_owner(conn, instance_id, token_info)
    pid = getattr(conn, "_afterglow_project_id", "unknown")
    try:
        inst = await asyncio.to_thread(trove.get_instance, conn, instance_id)
        ip = inst.get("ip")
        if not ip:
            raise HTTPException(status_code=400, detail="인스턴스에 IP가 아직 할당되지 않았습니다")

        target_port_id = None
        for p in await asyncio.to_thread(lambda: list(conn.network.ports())):
            for fi in p.fixed_ips or []:
                if fi.get("ip_address") == ip:
                    target_port_id = p.id
                    break
            if target_port_id:
                break
        if not target_port_id:
            raise HTTPException(status_code=404, detail=f"IP {ip} 에 대응하는 포트를 찾을 수 없습니다")

        for f in await asyncio.to_thread(lambda: list(conn.network.ips())):
            if getattr(f, "port_id", None) == target_port_id:
                if delete:
                    await asyncio.to_thread(neutron.delete_floating_ip, conn, f.id)
                else:
                    await asyncio.to_thread(neutron.disassociate_floating_ip, conn, f.id)
                await cache.invalidate(f"afterglow:trove:{pid}:*")
                await invalidation.invalidate_mutation_count("trove", pid)
                return
        raise HTTPException(status_code=404, detail="이 인스턴스에 연결된 floating IP가 없습니다")
    except HTTPException:
        raise
    except Exception:
        _logger.exception("Floating IP 해제 실패 instance=%s", instance_id)
        raise HTTPException(status_code=500, detail="Floating IP 해제 실패")


# ---------------------------------------------------------------------------
# 백업 서브리소스
# ---------------------------------------------------------------------------


@router.get("/{instance_id}/backups")
async def list_instance_backups(
    instance_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
    cm: CacheMode = Depends(cache_mode),
):
    """인스턴스 백업 목록."""
    from app.services import trove

    await _assert_db_instance_owner(conn, instance_id, token_info)
    pid = getattr(conn, "_afterglow_project_id", "unknown")
    key = keys.project_key("trove", pid, f"instances:{instance_id}:backups")
    try:
        return await cache.cached_call(
            key, cache.ttl_slow(), lambda: trove.list_backups(conn, instance_id), enabled=cm.enabled, refresh=cm.refresh
        )
    except Exception:
        raise HTTPException(status_code=500, detail="백업 목록 조회 실패")


@router.post("/{instance_id}/backups", status_code=201)
async def create_instance_backup(
    instance_id: str,
    req: CreateBackupRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    """인스턴스 백업 생성."""
    from app.services import trove

    await _assert_db_instance_owner(conn, instance_id, token_info)
    try:
        result = await asyncio.to_thread(trove.create_backup, conn, instance_id, req.name, req.description)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="백업 생성 실패")
    pid = getattr(conn, "_afterglow_project_id", "unknown")
    await cache.invalidate(f"afterglow:trove:{pid}:*")
    await invalidation.invalidate_mutation_count("trove", pid)
    return result


# ---------------------------------------------------------------------------
# 자동 백업 설정
# ---------------------------------------------------------------------------


@router.get("/{instance_id}/auto-backup")
async def get_instance_auto_backup(
    instance_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    """인스턴스 자동 백업 설정 조회."""
    from app.services import db_auto_backup

    await _assert_db_instance_owner(conn, instance_id, token_info)
    pid = getattr(conn, "_afterglow_project_id", "unknown")
    cfg = await db_auto_backup.get_db_auto_backup_config(pid, instance_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail="자동 백업 설정이 없습니다")
    return cfg


@router.put("/{instance_id}/auto-backup", status_code=200)
async def set_instance_auto_backup(
    instance_id: str,
    req: DbAutoBackupConfigRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    """인스턴스 자동 백업 활성화 또는 설정 갱신."""
    from app.services import db_auto_backup

    await _assert_db_instance_owner(conn, instance_id, token_info)
    pid = getattr(conn, "_afterglow_project_id", "unknown")
    cfg = await db_auto_backup.enable_db_auto_backup(pid, instance_id, req.max_daily, req.max_weekly, req.max_monthly)
    return cfg


@router.delete("/{instance_id}/auto-backup", status_code=204)
async def delete_instance_auto_backup(
    instance_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    """인스턴스 자동 백업 비활성화."""
    from app.services import db_auto_backup

    await _assert_db_instance_owner(conn, instance_id, token_info)
    pid = getattr(conn, "_afterglow_project_id", "unknown")
    await db_auto_backup.disable_db_auto_backup(pid, instance_id)
