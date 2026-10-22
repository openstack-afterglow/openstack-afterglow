"""관리자 Notion 연동 설정 엔드포인트."""

import logging
from datetime import UTC

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_admin_os_conn, require_admin
from app.services import notion_sync

# FastAPI-free 인벤토리 유틸리티로 이동된 함수들 — 하위 호환을 위해 재export.
from app.services.openstack_inventory import collect_hypervisor_data, collect_instance_data

_logger = logging.getLogger(__name__)

router = APIRouter()


async def _require_notion_sync_enabled() -> None:
    from app.services.resource_policy_store import ResourcePolicyStorageUnavailable, get_runtime_setting

    try:
        enabled = await get_runtime_setting("notion.sync_enabled")
    except ResourcePolicyStorageUnavailable as exc:
        raise HTTPException(status_code=503, detail="Notion runtime setting storage is unavailable") from exc
    if enabled is not True:
        raise HTTPException(status_code=409, detail="Notion synchronization is disabled by the global runtime setting")


class NotionConfigRequest(BaseModel):
    api_key: str
    database_id: str
    enabled: bool = True
    interval_minutes: int = 30
    users_database_id: str = ""
    hypervisors_database_id: str = ""
    gpu_spec_database_id: str = ""


class NotionTargetCreateRequest(BaseModel):
    label: str = "기본"
    api_key: str
    database_id: str
    enabled: bool = True
    interval_minutes: int = 30
    users_database_id: str = ""
    hypervisors_database_id: str = ""
    gpu_spec_database_id: str = ""


class NotionTargetUpdateRequest(BaseModel):
    label: str | None = None
    api_key: str | None = None
    database_id: str | None = None
    enabled: bool | None = None
    interval_minutes: int | None = None
    users_database_id: str | None = None
    hypervisors_database_id: str | None = None
    gpu_spec_database_id: str | None = None


@router.get("/notion/config", dependencies=[Depends(require_admin)])
async def get_notion_config():
    """현재 Notion 연동 설정 조회."""
    config = await notion_sync.get_notion_config()
    if not config:
        return {"configured": False}
    return {
        "configured": True,
        "api_key_masked": notion_sync.mask_api_key(config.get("api_key", "")),
        "database_id": config.get("database_id", ""),
        "enabled": config.get("enabled", False),
        "interval_minutes": config.get("interval_minutes", 30),
        "last_sync": config.get("last_sync"),
        "users_database_id": config.get("users_database_id", ""),
        "hypervisors_database_id": config.get("hypervisors_database_id", ""),
        "hypervisors_last_sync": config.get("hypervisors_last_sync"),
        "gpu_spec_database_id": config.get("gpu_spec_database_id", ""),
        "gpu_spec_last_sync": config.get("gpu_spec_last_sync"),
    }


@router.post("/notion/config", dependencies=[Depends(require_admin)])
async def save_notion_config(req: NotionConfigRequest):
    """Notion 연동 설정 저장. 연결 검증 + DB 속성 자동 생성."""
    if req.interval_minutes < 1 or req.interval_minutes > 1440:
        raise HTTPException(status_code=400, detail="동기화 간격은 1~1440분 사이여야 합니다")

    ok, message = await notion_sync.validate_notion_config(req.api_key, req.database_id)
    if not ok:
        raise HTTPException(status_code=400, detail=message)

    try:
        await notion_sync.ensure_db_properties(req.api_key, req.database_id)
    except Exception as e:
        _logger.warning("Notion DB 속성 생성 실패: %s", e)
        _logger.warning("DB 속성 생성 실패: %s", e)

        raise HTTPException(status_code=400, detail="DB 속성 생성 실패")

    # 선택 DB 검증
    if req.users_database_id:
        ok_u, msg_u = await notion_sync.validate_notion_config(req.api_key, req.users_database_id)
        if not ok_u:
            raise HTTPException(status_code=400, detail=f"사용자 DB 오류: {msg_u}")

    if req.hypervisors_database_id:
        ok_h, msg_h = await notion_sync.validate_notion_config(req.api_key, req.hypervisors_database_id)
        if not ok_h:
            raise HTTPException(status_code=400, detail=f"하이퍼바이저 DB 오류: {msg_h}")
        try:
            await notion_sync.ensure_hypervisor_db_properties(req.api_key, req.hypervisors_database_id)
        except Exception as e:
            _logger.warning("Notion 하이퍼바이저 DB 속성 생성 실패: %s", e)
            _logger.warning("하이퍼바이저 DB 속성 생성 실패: %s", e)

            raise HTTPException(status_code=400, detail="하이퍼바이저 DB 속성 생성 실패")

    if req.gpu_spec_database_id:
        ok_g, msg_g = await notion_sync.validate_notion_config(req.api_key, req.gpu_spec_database_id)
        if not ok_g:
            raise HTTPException(status_code=400, detail=f"GPU spec DB 오류: {msg_g}")
        try:
            await notion_sync.ensure_gpu_spec_db_properties(req.api_key, req.gpu_spec_database_id)
        except Exception as e:
            _logger.warning("Notion GPU spec DB 속성 생성 실패: %s", e)
            _logger.warning("GPU spec DB 속성 생성 실패: %s", e)

            raise HTTPException(status_code=400, detail="GPU spec DB 속성 생성 실패")

    existing = await notion_sync.get_notion_config()
    last_sync = existing.get("last_sync") if existing else None
    hypervisors_last_sync = existing.get("hypervisors_last_sync") if existing else None
    gpu_spec_last_sync = existing.get("gpu_spec_last_sync") if existing else None

    await notion_sync.save_notion_config(
        {
            "api_key": req.api_key,
            "database_id": req.database_id,
            "enabled": req.enabled,
            "interval_minutes": req.interval_minutes,
            "last_sync": last_sync,
            "users_database_id": req.users_database_id,
            "hypervisors_database_id": req.hypervisors_database_id,
            "hypervisors_last_sync": hypervisors_last_sync,
            "gpu_spec_database_id": req.gpu_spec_database_id,
            "gpu_spec_last_sync": gpu_spec_last_sync,
        }
    )

    return {
        "status": "ok",
        "message": "설정이 저장되었습니다",
        "api_key_masked": notion_sync.mask_api_key(req.api_key),
    }


@router.delete("/notion/config", dependencies=[Depends(require_admin)])
async def delete_notion_config():
    """Notion 연동 설정 삭제."""
    await notion_sync.delete_notion_config()
    return {"status": "ok", "message": "Notion 연동이 비활성화되었습니다"}


@router.post("/notion/test", dependencies=[Depends(require_admin)])
async def test_notion_sync(conn=Depends(get_admin_os_conn)):
    """수동 Notion 동기화 1회 실행."""
    from datetime import datetime

    await _require_notion_sync_enabled()

    config = await notion_sync.get_notion_config()
    if not config:
        raise HTTPException(status_code=400, detail="Notion 설정이 없습니다. 먼저 설정을 저장하세요.")

    api_key = config["api_key"]
    database_id = config["database_id"]
    users_db_id = config.get("users_database_id", "")
    hypervisors_db_id = config.get("hypervisors_database_id", "")
    gpu_spec_db_id = config.get("gpu_spec_database_id", "")
    from app.database import is_db_available

    if is_db_available():
        try:
            from app.services import gpu_catalog

            await gpu_catalog.refresh_device_map_from_db()
        except Exception:
            _logger.warning(
                "Notion 테스트: GPU 카탈로그 DB overlay 갱신 실패 — 기존 device map으로 진행", exc_info=True
            )

    from app.api.identity.admin_gpu import build_alias_to_device_name_map, get_gpu_spec_list

    # 0. GPU spec 동기화 (정적 데이터, 페이지 생성/갱신)
    gpu_spec_stats = None
    gpu_name_to_page_id: dict[str, str] = {}
    if gpu_spec_db_id:
        try:
            gpu_specs = get_gpu_spec_list()
            gpu_spec_stats = await notion_sync.sync_gpu_specs_to_notion(api_key, gpu_spec_db_id, gpu_specs)
            config["gpu_spec_last_sync"] = datetime.now(UTC).isoformat()
            # 동기화 후 page_id 맵 구축 (인스턴스 relation 설정에 사용)
            gpu_name_to_page_id = await notion_sync.fetch_gpu_spec_page_ids_by_name(api_key, gpu_spec_db_id)
        except Exception:
            _logger.warning("Notion 테스트: GPU spec 동기화 실패", exc_info=True)

    # 1. 하이퍼바이저 데이터 수집 (GPU 정보 포함) → 동기화 → page_id 맵 구축
    host_to_page_id: dict[str, str] = {}
    hypervisor_stats = None
    hypervisors: list[dict] = []
    if hypervisors_db_id:
        try:
            hypervisors = await collect_hypervisor_data(gpu_name_to_page_id=gpu_name_to_page_id)
            hypervisor_stats = await notion_sync.sync_hypervisors_to_notion(api_key, hypervisors_db_id, hypervisors)
            config["hypervisors_last_sync"] = datetime.now(UTC).isoformat()
            # 동기화 후 page_id 맵 구축 (인스턴스 relation 설정에 사용)
            host_to_page_id = await notion_sync.fetch_hypervisor_page_ids_by_name(api_key, hypervisors_db_id)
        except Exception:
            _logger.warning("Notion 테스트: 하이퍼바이저 동기화 실패", exc_info=True)

    # 2. People DB에서 이메일 → page_id 맵 구축
    email_to_page_id: dict[str, str] = {}
    if users_db_id:
        email_to_page_id = await notion_sync.fetch_user_page_ids_by_email(api_key, users_db_id)

    # 3. 인스턴스 데이터 수집 (relation page_id 포함)
    try:
        instances = await collect_instance_data(
            email_to_page_id=email_to_page_id,
            host_to_page_id=host_to_page_id,
            gpu_name_to_page_id=gpu_name_to_page_id,
        )
    except Exception:
        _logger.warning("Notion 테스트: 데이터 수집 실패", exc_info=True)
        raise HTTPException(status_code=500, detail="OpenStack 데이터 수집 실패")

    # 4. GPU 사용량 집계 (하이퍼바이저 기반 가용량 + 할당 상태 인스턴스 기반 사용량)
    alias_to_device_name = build_alias_to_device_name_map()
    usage_by_gpu = notion_sync.build_gpu_usage_by_gpu(hypervisors, instances, alias_to_device_name)

    # 5. GPU spec DB에 집계 데이터 업데이트
    if gpu_spec_db_id:
        try:
            gpu_specs = get_gpu_spec_list()
            gpu_spec_stats = await notion_sync.sync_gpu_specs_to_notion(
                api_key, gpu_spec_db_id, gpu_specs, usage_by_gpu=usage_by_gpu
            )
            config["gpu_spec_last_sync"] = datetime.now(UTC).isoformat()
        except Exception:
            _logger.warning("Notion 테스트: GPU spec 집계 업데이트 실패", exc_info=True)

    # 6. 인스턴스 동기화
    try:
        stats = await notion_sync.sync_to_notion(api_key, database_id, instances)
    except Exception as e:
        _logger.warning("Notion 테스트: 동기화 실패", exc_info=True)
        _logger.warning("Notion 동기화 실패: %s", e)

        raise HTTPException(status_code=500, detail="Notion 동기화 실패")

    config["last_sync"] = datetime.now(UTC).isoformat()
    await notion_sync.save_notion_config(config)

    # 7. 한국어 마이그레이션 (1회만 실행)
    try:
        migrated = await notion_sync.migrate_instance_db_to_korean(api_key, database_id)
        if migrated:
            _logger.info("인스턴스 DB 한국어 마이그레이션 완료")
    except Exception:
        _logger.warning("Notion 테스트: 한국어 마이그레이션 실패", exc_info=True)

    messages = [f"인스턴스: {stats['created']}개 생성, {stats['updated']}개 갱신, {stats['archived']}개 아카이브"]
    if hypervisor_stats:
        messages.append(f"하이퍼바이저: {hypervisor_stats['created']}개 생성, {hypervisor_stats['updated']}개 갱신")
    if gpu_spec_stats:
        messages.append(f"GPU spec: {gpu_spec_stats['created']}개 생성, {gpu_spec_stats['updated']}개 갱신")

    return {
        "status": "ok",
        "message": " / ".join(messages),
        "stats": stats,
        "hypervisor_stats": hypervisor_stats,
        "gpu_spec_stats": gpu_spec_stats,
        "instance_count": len(instances),
        "gpu_usage_summary": {k: v["instance_count"] for k, v in usage_by_gpu.items()},
    }


# ---------------------------------------------------------------------------
# NotionTarget CRUD 엔드포인트 — 다중 연동 대상 관리
# ---------------------------------------------------------------------------


async def _validate_target_dbs(api_key: str, req_dict: dict) -> None:
    """연동 대상 DB들을 검증한다. 실패 시 HTTPException."""
    db_id = req_dict.get("database_id", "")
    if db_id:
        ok, msg = await notion_sync.validate_notion_config(api_key, db_id)
        if not ok:
            raise HTTPException(status_code=400, detail=msg)
        try:
            await notion_sync.ensure_db_properties(api_key, db_id)
        except Exception as e:
            _logger.warning("인스턴스 DB 속성 생성 실패: %s", e)

            raise HTTPException(status_code=400, detail="인스턴스 DB 속성 생성 실패")

    users_db = req_dict.get("users_database_id", "")
    if users_db:
        ok, msg = await notion_sync.validate_notion_config(api_key, users_db)
        if not ok:
            raise HTTPException(status_code=400, detail=f"사용자 DB 오류: {msg}")

    hypervisors_db = req_dict.get("hypervisors_database_id", "")
    if hypervisors_db:
        ok, msg = await notion_sync.validate_notion_config(api_key, hypervisors_db)
        if not ok:
            raise HTTPException(status_code=400, detail=f"하이퍼바이저 DB 오류: {msg}")
        try:
            await notion_sync.ensure_hypervisor_db_properties(api_key, hypervisors_db)
        except Exception as e:
            _logger.warning("하이퍼바이저 DB 속성 생성 실패: %s", e)

            raise HTTPException(status_code=400, detail="하이퍼바이저 DB 속성 생성 실패")

    gpu_spec_db = req_dict.get("gpu_spec_database_id", "")
    if gpu_spec_db:
        ok, msg = await notion_sync.validate_notion_config(api_key, gpu_spec_db)
        if not ok:
            raise HTTPException(status_code=400, detail=f"GPU spec DB 오류: {msg}")
        try:
            await notion_sync.ensure_gpu_spec_db_properties(api_key, gpu_spec_db)
        except Exception as e:
            _logger.warning("GPU spec DB 속성 생성 실패: %s", e)

            raise HTTPException(status_code=400, detail="GPU spec DB 속성 생성 실패")


@router.get("/notion/targets", dependencies=[Depends(require_admin)])
async def list_notion_targets():
    """Notion 연동 대상 목록 조회 (API key 마스킹)."""
    return await notion_sync.list_notion_targets()


@router.post("/notion/targets", dependencies=[Depends(require_admin)])
async def create_notion_target(req: NotionTargetCreateRequest):
    """새 Notion 연동 대상 추가 (연결 검증 포함)."""
    if req.interval_minutes < 1 or req.interval_minutes > 1440:
        raise HTTPException(status_code=400, detail="동기화 간격은 1~1440분 사이여야 합니다")

    await _validate_target_dbs(req.api_key, req.model_dump())
    target = await notion_sync.create_notion_target(req.model_dump())
    return target


@router.patch("/notion/targets/{target_id}", dependencies=[Depends(require_admin)])
async def update_notion_target(target_id: int, req: NotionTargetUpdateRequest):
    """Notion 연동 대상 수정."""
    data = {k: v for k, v in req.model_dump().items() if v is not None}
    if "interval_minutes" in data and (data["interval_minutes"] < 1 or data["interval_minutes"] > 1440):
        raise HTTPException(status_code=400, detail="동기화 간격은 1~1440분 사이여야 합니다")

    # api_key가 변경되거나 DB ID가 변경될 때 검증
    if "api_key" in data or any(k.endswith("database_id") for k in data):
        existing = await notion_sync.get_notion_target(target_id, include_api_key=True)
        if not existing:
            raise HTTPException(status_code=404, detail="연동 대상을 찾을 수 없습니다")
        effective_key = data.get("api_key") or existing["api_key"]
        merged = {**existing, **data}
        await _validate_target_dbs(effective_key, merged)

    result = await notion_sync.update_notion_target(target_id, data)
    if result is None:
        raise HTTPException(status_code=404, detail="연동 대상을 찾을 수 없습니다")
    return result


@router.delete("/notion/targets/{target_id}", dependencies=[Depends(require_admin)])
async def delete_notion_target(target_id: int):
    """Notion 연동 대상 삭제."""
    deleted = await notion_sync.delete_notion_target(target_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="연동 대상을 찾을 수 없습니다")
    return {"status": "ok", "message": "연동 대상이 삭제되었습니다"}


@router.post("/notion/targets/{target_id}/test", dependencies=[Depends(require_admin)])
async def test_notion_target_sync(target_id: int, conn=Depends(get_admin_os_conn)):
    """특정 연동 대상에 대해 수동 동기화 1회 실행."""
    from datetime import datetime

    await _require_notion_sync_enabled()

    target = await notion_sync.get_notion_target(target_id, include_api_key=True)
    if not target:
        raise HTTPException(status_code=404, detail="연동 대상을 찾을 수 없습니다")

    api_key = target["api_key"]
    database_id = target["database_id"]
    users_db_id = target.get("users_database_id", "")
    hypervisors_db_id = target.get("hypervisors_database_id", "")
    gpu_spec_db_id = target.get("gpu_spec_database_id", "")
    from app.database import is_db_available
    from app.services.gpu_inventory import resolve_alias_to_device_name

    if is_db_available():
        try:
            from app.services import gpu_catalog

            await gpu_catalog.refresh_device_map_from_db()
        except Exception:
            _logger.warning(
                "Notion target 테스트: GPU 카탈로그 DB overlay 갱신 실패 — 기존 device map으로 진행", exc_info=True
            )

    from app.api.identity.admin_gpu import build_alias_to_device_name_map, get_gpu_spec_list

    gpu_spec_stats = None
    gpu_name_to_page_id: dict[str, str] = {}
    if gpu_spec_db_id:
        try:
            gpu_specs = get_gpu_spec_list()
            gpu_spec_stats = await notion_sync.sync_gpu_specs_to_notion(api_key, gpu_spec_db_id, gpu_specs)
            gpu_name_to_page_id = await notion_sync.fetch_gpu_spec_page_ids_by_name(api_key, gpu_spec_db_id)
        except Exception:
            _logger.warning("Notion target 테스트: GPU spec 동기화 실패", exc_info=True)

    host_to_page_id: dict[str, str] = {}
    hypervisor_stats = None
    hypervisors: list[dict] = []
    if hypervisors_db_id:
        try:
            hypervisors = await collect_hypervisor_data(gpu_name_to_page_id=gpu_name_to_page_id)
            hypervisor_stats = await notion_sync.sync_hypervisors_to_notion(api_key, hypervisors_db_id, hypervisors)
            host_to_page_id = await notion_sync.fetch_hypervisor_page_ids_by_name(api_key, hypervisors_db_id)
        except Exception:
            _logger.warning("Notion target 테스트: 하이퍼바이저 동기화 실패", exc_info=True)

    email_to_page_id: dict[str, str] = {}
    if users_db_id:
        email_to_page_id = await notion_sync.fetch_user_page_ids_by_email(api_key, users_db_id)

    try:
        instances = await collect_instance_data(
            email_to_page_id=email_to_page_id,
            host_to_page_id=host_to_page_id,
            gpu_name_to_page_id=gpu_name_to_page_id,
        )
    except Exception:
        raise HTTPException(status_code=500, detail="OpenStack 데이터 수집 실패")

    # GPU 사용량 집계
    alias_to_device_name = build_alias_to_device_name_map()
    usage_by_gpu: dict[str, dict] = {}
    for h in hypervisors:
        for g in h.get("gpu_groups", []):
            device_name = g.get("device_name", "")
            if not device_name:
                continue
            if device_name not in usage_by_gpu:
                usage_by_gpu[device_name] = {
                    "total_cpu_used": 0,
                    "total_ram_used": 0,
                    "total_gpu_used": 0,
                    "instance_count": 0,
                    "gpu_available": 0,
                    "gpu_used": 0,
                    "gpu_remaining": 0,
                }
            usage_by_gpu[device_name]["gpu_available"] += g.get("total", 0)
    for inst in instances:
        gpu_display = inst.get("gpu_name", "")
        if not gpu_display or not inst.get("gpu_count"):
            continue
        canonical = resolve_alias_to_device_name(gpu_display, alias_to_device_name) or gpu_display
        if canonical not in usage_by_gpu:
            usage_by_gpu[canonical] = {
                "total_cpu_used": 0,
                "total_ram_used": 0,
                "total_gpu_used": 0,
                "instance_count": 0,
                "gpu_available": 0,
                "gpu_used": 0,
                "gpu_remaining": 0,
            }
        usage_by_gpu[canonical]["total_cpu_used"] += inst.get("vcpus", 0)
        usage_by_gpu[canonical]["total_ram_used"] += inst.get("ram_gb", 0)
        usage_by_gpu[canonical]["total_gpu_used"] += inst.get("gpu_count", 0)
        usage_by_gpu[canonical]["instance_count"] += 1
        usage_by_gpu[canonical]["gpu_used"] += inst.get("gpu_count", 0)
    for u in usage_by_gpu.values():
        u["gpu_remaining"] = u["gpu_available"] - u["gpu_used"]

    if gpu_spec_db_id:
        try:
            gpu_specs = get_gpu_spec_list()
            gpu_spec_stats = await notion_sync.sync_gpu_specs_to_notion(
                api_key, gpu_spec_db_id, gpu_specs, usage_by_gpu=usage_by_gpu
            )
        except Exception:
            _logger.warning("Notion target 테스트: GPU spec 집계 업데이트 실패", exc_info=True)

    try:
        stats = await notion_sync.sync_to_notion(api_key, database_id, instances)
    except Exception as e:
        _logger.warning("Notion 동기화 실패: %s", e)

        raise HTTPException(status_code=500, detail="Notion 동기화 실패")

    now_iso = datetime.now(UTC).isoformat()
    await notion_sync.update_notion_target(
        target_id,
        {
            "last_sync": now_iso,
            "hypervisors_last_sync": now_iso if hypervisors_db_id else None,
            "gpu_spec_last_sync": now_iso if gpu_spec_db_id else None,
        },
    )

    messages = [
        f"인스턴스: {stats['created']}개 생성, {stats['updated']}개 갱신, {stats.get('skipped', 0)}개 스킵, {stats['archived']}개 아카이브"
    ]
    if hypervisor_stats:
        messages.append(f"하이퍼바이저: {hypervisor_stats['created']}개 생성, {hypervisor_stats['updated']}개 갱신")
    if gpu_spec_stats:
        messages.append(f"GPU spec: {gpu_spec_stats['created']}개 생성, {gpu_spec_stats['updated']}개 갱신")

    return {
        "status": "ok",
        "message": " / ".join(messages),
        "stats": stats,
        "hypervisor_stats": hypervisor_stats,
        "gpu_spec_stats": gpu_spec_stats,
        "instance_count": len(instances),
    }
