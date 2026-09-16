"""
인스턴스 오케스트레이션 엔드포인트.

생성 순서:
  1. Manila access rule(A) 또는 신규 파일 스토리지(B)
  2. Cinder 부트 볼륨
  3. Cinder upper 볼륨
  4. cloud-init userdata 생성
  5. Nova 서버 생성

실패 시 역순 rollback.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    import openstack

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from openstack.exceptions import ConflictException, HttpException
from pydantic import BaseModel, field_validator

from app.api.common.activity_recorder import rec
from app.api.common.owner_check import assert_instance_owner
from app.api.deps import CacheMode, cache_mode, get_os_conn, get_token_info, require_admin
from app.config import get_settings
from app.models.compute import (
    AdminPasswordPrecheck,
    AdminPasswordRequest,
    AttachInterfaceRequest,
    AttachVolumeRequest,
    CloudInitSnippetLibrary,
    CreateCloudInitPresetRequest,
    CreateInstanceRequest,
    InstanceInfo,
    StorageAttachRequest,
    UpdateSecurityGroupsRequest,
    UpdateVolumeAttachmentRequest,
)
from app.models.progress import ProgressMessage, ProgressStep
from app.rate_limit import limiter
from app.services import cinder, cloudinit, glance, keystone, manila, neutron, nova, vm_cloud_init_library
from app.services import instance_orchestration as instance_orch
from app.services import libraries as lib_svc
from app.services.cache import (
    cached_call,
    invalidate,
    ttl_fast,
    ttl_normal,
    ttl_slow,
    ttl_static,
)
from app.services.cache import invalidation as cache_invalidation
from app.services.resource_policies import ResourcePolicyValidationError
from app.services.resource_policy_store import ResourcePolicyStorageUnavailable

logger = logging.getLogger(__name__)


async def _record_cloud_init_history_best_effort(token_info: dict, userdata: str | None) -> None:
    try:
        await vm_cloud_init_library.record_history(user_id=token_info["user_id"], content=userdata)
    except Exception:
        logger.warning("cloud-init 실행 이력 저장 실패", extra={"user_id": token_info.get("user_id")})


router = APIRouter()


async def _resolve_create_placement(
    req: CreateInstanceRequest,
    conn: openstack.connection.Connection,
    settings,
) -> tuple[CreateInstanceRequest, str, str]:
    """Resolve pre-create placement and surface expected policy failures safely."""
    try:
        if not req.network_id:
            resolved_net_id = await instance_orch.resolve_default_network(conn, settings)
            if resolved_net_id:
                req = req.model_copy(update={"network_id": resolved_net_id})
        compute_zone, volume_zone = await instance_orch.resolve_availability_zones(conn, req.availability_zone)
    except (ResourcePolicyStorageUnavailable, ResourcePolicyValidationError, RuntimeError) as exc:
        logger.warning("인스턴스 생성 배치 사전검증 실패: %s", exc)
        error = HTTPException(
            status_code=503,
            detail="인스턴스 배치 정책을 사용할 수 없습니다. 관리자에게 문의하세요.",
        )
        error._afterglow_safe_public_detail = True
        raise error from exc
    return req, compute_zone, volume_zone


class BulkActionRequest(BaseModel):
    """일괄 인스턴스 액션 요청 모델."""

    action: Literal["start", "stop", "delete", "reboot"]
    instance_ids: list[str]

    @field_validator("instance_ids")
    @classmethod
    def validate_count(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("최소 1개 이상 필요합니다")
        if len(v) > 50:
            raise ValueError("최대 50개 인스턴스만 처리 가능합니다")
        return v


def _resolve_names(servers: list, conn) -> list[dict]:
    """서버 목록에 flavor_name / image_name 을 resolve해서 반환."""
    flavors_by_id = {f.id: f.name for f in nova.list_flavors(conn)}
    images: dict = {}
    try:
        images = {img.id: img.name for img in glance.list_images(conn)}
    except Exception:
        pass
    result = []
    for s in servers:
        d = s.model_dump()
        # flavor_name: _server_to_info에서 original_name으로 이미 설정된 경우 유지,
        # 없으면 flavor_id로 lookup (구형 마이크로버전)
        if not d.get("flavor_name") and s.flavor_id:
            d["flavor_name"] = flavors_by_id.get(s.flavor_id)
        if s.image_id:
            d["image_name"] = images.get(s.image_id)
        else:
            image_name = None
            try:
                attachments = nova.list_volume_attachments(conn, s.id)
                boot_att = next((a for a in attachments if a.get("device") == "/dev/vda"), None)
                if boot_att:
                    meta = cinder.get_volume_image_metadata(conn, boot_att["volume_id"])
                    if meta:
                        image_name = meta.get("image_name")
            except Exception:
                pass
            d["image_name"] = image_name or "볼륨에서 부팅"
        result.append(d)
    return result


@router.get("", response_model=list[InstanceInfo])
async def list_instances(
    conn: openstack.connection.Connection = Depends(get_os_conn),
    cm: CacheMode = Depends(cache_mode),
):
    pid = conn._afterglow_project_id
    try:
        return await cached_call(
            f"afterglow:nova:{pid}:instances",
            ttl_fast(),
            lambda: _resolve_names(nova.list_servers(conn), conn),
            enabled=cm.enabled,
            refresh=cm.refresh,
        )
    except Exception as e:
        logger.error(f"인스턴스 목록 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="인스턴스 목록 조회 실패")


# 정적 path 라우트는 /{instance_id} 보다 먼저 등록 (FastAPI 매칭 순서)
@router.get("/availability-zones")
async def list_availability_zones(
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """사용 가능한 가용 영역 목록."""
    try:
        zones = await asyncio.to_thread(nova.list_availability_zones, conn)
        return zones
    except Exception:
        raise HTTPException(status_code=500, detail="가용 영역 조회 실패")


@router.get("/cloud-init/library", response_model=CloudInitSnippetLibrary)
async def list_cloud_init_library(token_info: dict = Depends(get_token_info)):
    try:
        return await vm_cloud_init_library.list_snippets(token_info["user_id"])
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/cloud-init/presets", status_code=201)
async def save_cloud_init_preset(
    req: CreateCloudInitPresetRequest,
    token_info: dict = Depends(get_token_info),
):
    try:
        preset = await vm_cloud_init_library.create_preset(
            user_id=token_info["user_id"],
            name=req.name,
            content=req.content,
        )
        await invalidate(f"afterglow:vm_cloud_init:{token_info['user_id']}")
        await cache_invalidation.invalidate_mutation_count("nova", token_info["project_id"])
        return preset
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=422 if isinstance(exc, ValueError) else 503, detail=str(exc)) from exc


@router.delete("/cloud-init/library/{snippet_id}", status_code=204)
async def delete_cloud_init_snippet(
    snippet_id: int,
    token_info: dict = Depends(get_token_info),
):
    try:
        await vm_cloud_init_library.delete_snippet(user_id=token_info["user_id"], snippet_id=snippet_id)
        await invalidate(f"afterglow:vm_cloud_init:{token_info['user_id']}")
        await cache_invalidation.invalidate_mutation_count("nova", token_info["project_id"])
    except vm_cloud_init_library.CloudInitSnippetNotFound as exc:
        raise HTTPException(status_code=404, detail="cloud-init 항목을 찾을 수 없습니다") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/{instance_id}", response_model=InstanceInfo)
async def get_instance(
    instance_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    pid = conn._afterglow_project_id
    try:
        server = await asyncio.to_thread(nova.get_server, conn, instance_id)
    except Exception:
        raise HTTPException(status_code=404, detail="인스턴스를 찾을 수 없습니다")
    # admin 외에는 본인 프로젝트의 인스턴스만 조회 가능 (RBAC 외 추가 방어선)
    assert_instance_owner(server, conn, token_info)
    try:
        return await cached_call(
            f"afterglow:nova:{pid}:instance:{instance_id}",
            ttl_fast(),
            lambda: _resolve_names([server], conn)[0],
        )
    except Exception:
        raise HTTPException(status_code=404, detail="인스턴스를 찾을 수 없습니다")


@router.post("", response_model=InstanceInfo, status_code=201)
@limiter.limit("5/minute")
async def create_instance(
    request: Request,
    req: CreateInstanceRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    """동기식 인스턴스 생성 (기존 방식)."""
    settings = get_settings()
    from app.services.instance_names import ensure_unique_instance_name

    try:
        req = req.model_copy(update={"name": await asyncio.to_thread(ensure_unique_instance_name, conn, req.name)})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    resolved_libs = lib_svc.resolve_with_deps(req.libraries)

    req, compute_availability_zone, volume_availability_zone = await _resolve_create_placement(
        req,
        conn,
        settings,
    )

    from app.services.flavor_eligibility import (
        FlavorEligibilityDenied,
        FlavorEligibilityUnavailable,
        admit_flavor,
        release_admission,
    )
    from app.services.gpu_quota import GpuQuotaDenied, GpuQuotaUnavailable

    flavors = await asyncio.to_thread(nova.list_flavors, conn)
    flavor = next((f for f in flavors if f.id == req.flavor_id), None)
    if flavor is None:
        raise HTTPException(status_code=400, detail="Invalid flavor ID")
    try:
        admission = await admit_flavor(conn, conn._afterglow_project_id, flavor)
    except (FlavorEligibilityDenied, GpuQuotaDenied) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (FlavorEligibilityUnavailable, GpuQuotaUnavailable) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    gpu_available = bool(admission.gpu_requested)

    # 수집된 리소스 (rollback 용)
    created_file_storage_ids: list[str] = []
    created_access_ids: list[tuple[str, str]] = []  # (file_storage_id, access_id)
    boot_volume_id: str | None = None
    boot_volume_was_provided: bool = False  # 기존 볼륨 사용 시 rollback 에서 삭제 금지
    upper_volume_id: str | None = None
    created_upper: bool = False  # 신규 생성 시에만 rollback에서 삭제
    server_id: str | None = None
    floating_ip_id: str | None = None

    try:
        # ------------------------------------------------------------------
        # 1. Manila: 파일 스토리지 및 access rule 준비
        # ------------------------------------------------------------------
        file_storages_info = []  # cloud-init 에 전달할 파일 스토리지 정보 목록

        if resolved_libs:
            if req.strategy == "prebuilt":
                file_storages_info = await _prepare_prebuilt_file_storages(
                    conn,
                    resolved_libs,
                    req.name,
                    created_access_ids,
                    network_id=req.network_id or "",
                    project_id=conn._afterglow_project_id,
                )
            else:
                file_storage_info = await _prepare_dynamic_file_storage(
                    conn,
                    req.name,
                    resolved_libs,
                    settings,
                    created_file_storage_ids,
                    created_access_ids,
                )
                file_storages_info = [file_storage_info]

        data_mounts_info: list[dict] = []
        if req.data_mounts:
            data_mounts_info = await _prepare_data_mounts(
                conn, req.data_mounts, req.name, created_access_ids, req.network_id or ""
            )

        # ------------------------------------------------------------------
        # 2. Cinder: 부트 볼륨 생성 또는 기존 볼륨 검증
        # ------------------------------------------------------------------
        if req.boot_volume_id:
            boot_vol = await asyncio.to_thread(cinder.get_volume, conn, req.boot_volume_id)
            if boot_vol.status != "available":
                raise HTTPException(400, f"부팅 볼륨 상태가 'available'이 아닙니다: {boot_vol.status}")
            if not boot_vol.bootable:
                raise HTTPException(400, "bootable=false 볼륨은 루트 디스크로 사용할 수 없습니다")
            boot_volume_id = req.boot_volume_id
            boot_volume_was_provided = True
        else:
            boot_vol = await asyncio.to_thread(
                cinder.create_volume_from_image,
                conn,
                f"{req.name}-boot",
                req.image_id,
                req.boot_volume_size_gb or settings.boot_volume_size_gb,
                volume_availability_zone,
            )
            boot_volume_id = boot_vol.id
            await asyncio.to_thread(
                cinder.rename_volume,
                conn,
                boot_volume_id,
                f"{req.name}-boot-{boot_volume_id[:8]}",
            )

        # ------------------------------------------------------------------
        # 3. Cinder: upper 볼륨 — 신규 생성 또는 기존(복구된) 볼륨 재사용
        # ------------------------------------------------------------------
        if resolved_libs:
            if req.existing_upper_volume_id:
                upper_volume_id = req.existing_upper_volume_id
                upper_vol = await asyncio.to_thread(cinder.get_volume, conn, upper_volume_id)
                if upper_vol.status != "available":
                    raise HTTPException(400, f"upper 볼륨 상태가 available이 아닙니다: {upper_vol.status}")
                created_upper = False
            else:
                upper_vol = await asyncio.to_thread(
                    cinder.create_empty_volume,
                    conn,
                    f"union-upper-{req.name}",
                    settings.upper_volume_size_gb,
                    volume_availability_zone,
                )
                upper_volume_id = upper_vol.id
                created_upper = True

        # ------------------------------------------------------------------
        # 4. cloud-init userdata 생성
        # ------------------------------------------------------------------
        # 헬스 리포트 토큰 발급 + userdata (libraries·GPU·data_mounts 있을 때만)
        project_id = conn._afterglow_project_id
        _health_id = ""
        _report_url = ""
        _health_token = ""
        userdata = None
        if resolved_libs or gpu_available or data_mounts_info:
            _health_id, _report_url, _health_token = await instance_orch.try_issue_health_token(project_id, settings)
            userdata = cloudinit.generate_userdata(
                libraries=resolved_libs,
                strategy=req.strategy,
                file_storages=file_storages_info,
                upper_device="/dev/vdb",  # Nova가 두 번째 블록으로 붙임
                ceph_monitors=settings.ceph_monitors,
                gpu_available=gpu_available,
                instance_id=_health_id if _health_token else "",
                report_url=_report_url if _health_token else "",
                report_token=_health_token,
                data_mounts=data_mounts_info,
                github_username=req.github_username,
            )

        userdata = cloudinit.compose_userdata(userdata, req.userdata, req.github_username)

        # ------------------------------------------------------------------
        # 5. Nova: 서버 생성
        # ------------------------------------------------------------------
        effective_sgs = await instance_orch.compute_effective_security_groups(
            conn,
            settings,
            project_id,
            resolved_libs,
            gpu_available,
            list(req.security_groups or []),
        )
        req = req.model_copy(update={"security_groups": effective_sgs})

        meta = instance_orch.build_instance_meta(
            resolved_libs,
            file_storages_info,
            upper_volume_id,
            req.scheduling,
            req.strategy or "none",
            _health_id if resolved_libs else "",
            _health_token,
        )
        if data_mounts_info:
            meta["union_data_share_ids"] = ",".join(dm["file_storage_id"] for dm in data_mounts_info)

        # upper 볼륨을 두 번째 블록 디바이스로 추가
        # (Nova block_device_mapping_v2 에 추가 볼륨 연결)
        server = await asyncio.to_thread(
            nova.create_server,
            conn,
            name=req.name,
            flavor_id=req.flavor_id,
            network_id=req.network_id,
            boot_volume_id=boot_volume_id,
            userdata=userdata,
            key_name=req.key_name,
            admin_pass=req.admin_pass,
            availability_zone=compute_availability_zone,
            metadata=meta,
            delete_boot_volume_on_termination=(
                False if boot_volume_was_provided else req.delete_boot_volume_on_termination
            ),
            security_groups=req.security_groups if req.security_groups else None,
        )
        server_id = server.id

        # upper 볼륨 attach (서버 생성 후, libraries 있을 때만)
        if upper_volume_id:
            await asyncio.to_thread(
                conn.compute.create_volume_attachment,
                server_id,
                volume_id=upper_volume_id,
            )

        # Floating IP 자동 생성 (tenant 네트워크 선택 시)
        if req.network_id:
            all_nets = await asyncio.to_thread(neutron.list_networks, conn)
            selected_net = next((n for n in all_nets if n.id == req.network_id), None)
            if selected_net and not selected_net.is_external:
                ext_net = next((n for n in all_nets if n.is_external), None)
                if ext_net:
                    fip = await asyncio.to_thread(neutron.create_floating_ip, conn, ext_net.id)
                    floating_ip_id = fip.id
                    await asyncio.to_thread(neutron.associate_floating_ip, conn, fip.id, server_id)

        await _record_cloud_init_history_best_effort(token_info, req.userdata)
        await rec(
            token_info,
            conn,
            resource_type="instance",
            action="instance.create",
            status="success",
            resource_id=server.id,
            resource_name=req.name,
        )
        await invalidate(f"afterglow:nova:{project_id}:instances")
        await cache_invalidation.invalidate_mutation_count("nova", project_id)
        return server

    except HTTPException:
        raise
    except Exception as e:
        error_detail = str(e)
        logger.error(f"인스턴스 생성 실패, rollback 시작: {error_detail}")

        import re as _re

        if not server_id:
            _m = _re.search(r"Server:([0-9a-f-]{36})", error_detail)
            if _m:
                server_id = _m.group(1)

        if server_id:
            try:
                srv = conn.compute.get_server(server_id)
                raw_fault = getattr(srv, "fault", None)
                if raw_fault:
                    fault_msg = (
                        raw_fault.get("message", "")
                        if isinstance(raw_fault, dict)
                        else getattr(raw_fault, "message", "")
                    )
                    if fault_msg:
                        error_detail = fault_msg
            except Exception:
                pass

        await instance_orch.rollback_instance(
            conn,
            server_id,
            boot_volume_id if not boot_volume_was_provided else None,
            upper_volume_id if created_upper else None,
            created_file_storage_ids,
            created_access_ids,
            floating_ip_id,
        )
        is_admin = token_info.get("is_system_admin", False)
        detail = (
            f"인스턴스 생성 실패: {error_detail}"
            if is_admin
            else "인스턴스 생성에 실패했습니다. 관리자에게 문의하세요."
        )
        await rec(
            token_info,
            conn,
            resource_type="instance",
            action="instance.create",
            status="failed",
            resource_name=req.name,
            error_message=error_detail[:500],
        )
        raise HTTPException(status_code=500, detail=detail)
    finally:
        try:
            await release_admission(admission)
        except Exception:
            logger.warning("GPU quota reservation release failed", exc_info=True)


@router.post("/async")
async def create_instance_async(
    req: CreateInstanceRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    """SSE로 진행 상황을 스트리밍하는 비동기 인스턴스 생성."""
    settings = get_settings()
    from app.services.instance_names import ensure_unique_instance_name

    try:
        req = req.model_copy(update={"name": await asyncio.to_thread(ensure_unique_instance_name, conn, req.name)})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    resolved_libs = lib_svc.resolve_with_deps(req.libraries)

    req, compute_availability_zone, volume_availability_zone = await _resolve_create_placement(
        req,
        conn,
        settings,
    )

    from app.services.flavor_eligibility import (
        FlavorEligibilityDenied,
        FlavorEligibilityUnavailable,
        admit_flavor,
        release_admission,
    )
    from app.services.gpu_quota import GpuQuotaDenied, GpuQuotaUnavailable

    sse_flavors = await asyncio.to_thread(nova.list_flavors, conn)
    sse_flavor = next((flavor for flavor in sse_flavors if flavor.id == req.flavor_id), None)
    if sse_flavor is None:
        raise HTTPException(status_code=400, detail="Invalid flavor ID")
    try:
        admission = await admit_flavor(conn, conn._afterglow_project_id, sse_flavor)
    except (FlavorEligibilityDenied, GpuQuotaDenied) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (FlavorEligibilityUnavailable, GpuQuotaUnavailable) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    gpu_available = bool(admission.gpu_requested)

    async def progress_generator():
        import time

        # 수집된 리소스 (rollback 용)
        created_file_storage_ids: list[str] = []
        created_access_ids: list[tuple[str, str]] = []
        boot_volume_id: str | None = None
        boot_volume_was_provided: bool = False  # 기존 볼륨 사용 시 rollback 에서 삭제 금지
        upper_volume_id: str | None = None
        created_upper: bool = False  # 신규 생성 시에만 rollback에서 삭제
        server_id: str | None = None
        floating_ip_id: str | None = None
        _start_time = time.monotonic()

        def send_progress(step: ProgressStep, progress: int, message: str, **extra):
            elapsed = round(time.monotonic() - _start_time, 1)
            msg = ProgressMessage(step=step, progress=progress, message=message, elapsed_seconds=elapsed, **extra)
            return f"data: {msg.model_dump_json()}\n\n"

        try:
            file_storages_info = []
            data_mounts_info: list[dict] = []
            userdata = None

            if resolved_libs or req.data_mounts:
                # Step 1: Manila 파일 스토리지 (0-20%)
                yield send_progress(ProgressStep.MANILA_PREPARING, 0, "파일 스토리지 준비 중...")
                if resolved_libs:
                    if req.strategy == "prebuilt":
                        file_storages_info = await _prepare_prebuilt_file_storages(
                            conn,
                            resolved_libs,
                            req.name,
                            created_access_ids,
                            network_id=req.network_id or "",
                            project_id=conn._afterglow_project_id,
                        )
                    else:
                        file_storage_info = await _prepare_dynamic_file_storage(
                            conn,
                            req.name,
                            resolved_libs,
                            settings,
                            created_file_storage_ids,
                            created_access_ids,
                        )
                        file_storages_info = [file_storage_info]
                if req.data_mounts:
                    data_mounts_info = await _prepare_data_mounts(
                        conn, req.data_mounts, req.name, created_access_ids, req.network_id or ""
                    )
                yield send_progress(ProgressStep.MANILA_PREPARING, 20, "파일 스토리지 준비 완료")
            # Step 2: Boot volume (20-45%)
            if req.boot_volume_id:
                yield send_progress(ProgressStep.BOOT_VOLUME_CREATING, 20, "기존 부팅 볼륨 검증 중...")
                boot_vol = await asyncio.to_thread(cinder.get_volume, conn, req.boot_volume_id)
                if boot_vol.status != "available":
                    raise HTTPException(400, f"부팅 볼륨 상태가 'available'이 아닙니다: {boot_vol.status}")
                if not boot_vol.bootable:
                    raise HTTPException(400, "bootable=false 볼륨은 루트 디스크로 사용할 수 없습니다")
                boot_volume_id = req.boot_volume_id
                boot_volume_was_provided = True
                yield send_progress(ProgressStep.BOOT_VOLUME_CREATING, 45, "부팅 볼륨 검증 완료")
            else:
                yield send_progress(ProgressStep.BOOT_VOLUME_CREATING, 20, "부트 볼륨 생성 중...")
                boot_vol = await asyncio.to_thread(
                    cinder.create_volume_from_image,
                    conn,
                    name=f"{req.name}-boot",
                    image_id=req.image_id,
                    size_gb=req.boot_volume_size_gb or settings.boot_volume_size_gb,
                    availability_zone=volume_availability_zone,
                )
                boot_volume_id = boot_vol.id
                await asyncio.to_thread(
                    cinder.rename_volume,
                    conn,
                    boot_volume_id,
                    f"{req.name}-boot-{boot_volume_id[:8]}",
                )
                yield send_progress(ProgressStep.BOOT_VOLUME_CREATING, 45, "부트 볼륨 생성 완료")

            if resolved_libs:
                # Step 3: Upper volume (45-60%) — 신규 생성 또는 기존(복구된) 볼륨 재사용
                if req.existing_upper_volume_id:
                    yield send_progress(ProgressStep.UPPER_VOLUME_CREATING, 45, "기존 upper 볼륨 검증 중...")
                    upper_volume_id = req.existing_upper_volume_id
                    upper_vol = await asyncio.to_thread(cinder.get_volume, conn, upper_volume_id)
                    if upper_vol.status != "available":
                        raise HTTPException(400, f"upper 볼륨 상태가 available이 아닙니다: {upper_vol.status}")
                    created_upper = False
                else:
                    yield send_progress(ProgressStep.UPPER_VOLUME_CREATING, 45, "Upper 볼륨 생성 중...")
                    upper_vol = await asyncio.to_thread(
                        cinder.create_empty_volume,
                        conn,
                        name=f"union-upper-{req.name}",
                        size_gb=settings.upper_volume_size_gb,
                        availability_zone=volume_availability_zone,
                    )
                    upper_volume_id = upper_vol.id
                    created_upper = True
                yield send_progress(ProgressStep.UPPER_VOLUME_CREATING, 60, "Upper 볼륨 준비 완료")

            # Step 4: cloud-init userdata 생성 (60-65%)
            # libraries 또는 GPU flavor 둘 중 하나라도 있으면 user-data 필요:
            # - libraries → OverlayFS + Manila 마운트 + 환경변수
            # - GPU only → NVIDIA 드라이버 + dcgm-exporter 설치 (libraries 없어도 필수)
            _sse_health_id = ""
            _sse_health_token = ""
            if resolved_libs or gpu_available or data_mounts_info:
                yield send_progress(ProgressStep.USERDATA_GENERATING, 60, "cloud-init 생성 중...")
                _sse_health_id, _sse_report_url, _sse_health_token = await instance_orch.try_issue_health_token(
                    conn._afterglow_project_id, settings
                )

                userdata = cloudinit.generate_userdata(
                    libraries=resolved_libs,
                    strategy=req.strategy or "none",
                    file_storages=file_storages_info,
                    upper_device="/dev/vdb",
                    ceph_monitors=settings.ceph_monitors,
                    gpu_available=gpu_available,
                    instance_id=_sse_health_id if _sse_health_token else "",
                    report_url=_sse_report_url if _sse_health_token else "",
                    report_token=_sse_health_token,
                    data_mounts=data_mounts_info,
                    github_username=req.github_username,
                )
                yield send_progress(ProgressStep.USERDATA_GENERATING, 65, "cloud-init 생성 완료")

            userdata = cloudinit.compose_userdata(userdata, req.userdata, req.github_username)

            # Step 5: Nova server (65-95%)
            yield send_progress(ProgressStep.SERVER_CREATING, 65, "Nova 서버 생성 중...")
            effective_sgs = await instance_orch.compute_effective_security_groups(
                conn,
                settings,
                conn._afterglow_project_id,
                resolved_libs,
                gpu_available,
                list(req.security_groups or []),
            )
            _sse_effective_sgs: list[str] | None = effective_sgs if effective_sgs else None

            meta = instance_orch.build_instance_meta(
                resolved_libs,
                file_storages_info,
                upper_volume_id,
                req.scheduling,
                req.strategy or "none",
                _sse_health_id if resolved_libs else "",
                _sse_health_token,
            )
            if data_mounts_info:
                meta["union_data_share_ids"] = ",".join(dm["file_storage_id"] for dm in data_mounts_info)

            server = await asyncio.to_thread(
                nova.create_server,
                conn,
                name=req.name,
                flavor_id=req.flavor_id,
                network_id=req.network_id,
                boot_volume_id=boot_volume_id,
                userdata=userdata,
                key_name=req.key_name,
                admin_pass=req.admin_pass,
                availability_zone=compute_availability_zone,
                metadata=meta,
                delete_boot_volume_on_termination=(
                    False if boot_volume_was_provided else req.delete_boot_volume_on_termination
                ),
                security_groups=_sse_effective_sgs,
            )
            server_id = server.id
            yield send_progress(ProgressStep.SERVER_CREATING, 95, "Nova 서버 생성 완료")

            # Step 6: Attach volumes (95-100%)
            yield send_progress(ProgressStep.ATTACHING_VOLUME, 95, "볼륨 연결 중...")
            if upper_volume_id:
                await asyncio.to_thread(
                    conn.compute.create_volume_attachment,
                    server_id,
                    volume_id=upper_volume_id,
                )
            # 새 볼륨 생성 후 연결
            for nv in req.new_volumes or []:
                nv_name = nv.name
                nv_size = nv.size_gb
                if not nv_name:
                    continue
                new_vol = await asyncio.to_thread(cinder.create_empty_volume, conn, nv_name, nv_size)
                await asyncio.to_thread(
                    conn.compute.create_volume_attachment,
                    server_id,
                    volume_id=new_vol.id,
                )
            # 추가 볼륨 연결
            for vol_id in req.additional_volume_ids or []:
                await asyncio.to_thread(conn.compute.create_volume_attachment, server_id, volume_id=vol_id)
            yield send_progress(ProgressStep.ATTACHING_VOLUME, 100, "볼륨 연결 완료")

            # Step 7: Floating IP (tenant 네트워크 선택 시)
            if req.network_id:
                all_nets = await asyncio.to_thread(neutron.list_networks, conn)
                selected_net = next((n for n in all_nets if n.id == req.network_id), None)
                if selected_net and not selected_net.is_external:
                    ext_net = next((n for n in all_nets if n.is_external), None)
                    if ext_net:
                        yield send_progress(
                            ProgressStep.FLOATING_IP_CREATING,
                            100,
                            "Floating IP 할당 중...",
                        )
                        fip = await asyncio.to_thread(neutron.create_floating_ip, conn, ext_net.id)
                        floating_ip_id = fip.id
                        await asyncio.to_thread(neutron.associate_floating_ip, conn, fip.id, server_id)
                        yield send_progress(
                            ProgressStep.FLOATING_IP_CREATING,
                            100,
                            "Floating IP 할당 완료",
                        )

            # Completed
            await _record_cloud_init_history_best_effort(token_info, req.userdata)
            yield send_progress(ProgressStep.COMPLETED, 100, "인스턴스 생성 완료", instance_id=server_id)
            await rec(
                token_info,
                conn,
                resource_type="instance",
                action="instance.create",
                status="success",
                resource_id=server_id,
                resource_name=req.name,
            )
            _pid = conn._afterglow_project_id
            await invalidate(f"afterglow:nova:{_pid}:instances")
            await cache_invalidation.invalidate_mutation_count("nova", _pid)

        except Exception as e:
            error_detail = str(e)
            logger.error(f"인스턴스 생성 실패, rollback 시작: {error_detail}")

            # wait_for_server 실패 시 server_id가 미설정 — 예외 메시지에서 추출
            import re as _re

            if not server_id:
                _m = _re.search(r"Server:([0-9a-f-]{36})", error_detail)
                if _m:
                    server_id = _m.group(1)

            # ERROR 상태 서버의 fault 메시지를 우선 사용
            if server_id:
                try:
                    srv = conn.compute.get_server(server_id)
                    raw_fault = getattr(srv, "fault", None)
                    if raw_fault:
                        fault_msg = (
                            raw_fault.get("message", "")
                            if isinstance(raw_fault, dict)
                            else getattr(raw_fault, "message", "")
                        )
                        if fault_msg:
                            error_detail = fault_msg
                except Exception:
                    pass

            # 비관리자에게는 상세 에러 숨김
            is_admin = token_info.get("is_system_admin", False)
            user_message = (
                f"인스턴스 생성 실패: {error_detail}"
                if is_admin
                else "인스턴스 생성에 실패했습니다. 관리자에게 문의하세요."
            )

            yield send_progress(
                ProgressStep.FAILED,
                0,
                user_message,
                error=error_detail if is_admin else "인스턴스 생성 실패",
            )
            await rec(
                token_info,
                conn,
                resource_type="instance",
                action="instance.create",
                status="failed",
                resource_name=req.name,
                error_message=error_detail[:500],
            )
            await instance_orch.rollback_instance(
                conn,
                server_id,
                boot_volume_id if not boot_volume_was_provided else None,
                upper_volume_id if created_upper else None,
                created_file_storage_ids,
                created_access_ids,
                floating_ip_id,
            )
        finally:
            try:
                await release_admission(admission)
            except Exception:
                logger.warning("GPU quota reservation release failed", exc_info=True)

    return StreamingResponse(
        progress_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.post("/bulk-action", status_code=200)
@limiter.limit("10/minute")
async def bulk_instance_action(
    request: Request,
    body: BulkActionRequest,
    conn=Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    """인스턴스 일괄 액션(start/stop/delete/reboot).

    - 각 인스턴스마다 소유권 검증(IDOR 방지) 후 처리.
    - 부분 성공 허용: per-id 결과 배열 반환.
    - 오류는 "처리 실패"로만 노출(404/403 구분 없음 — IDOR oracle 방지).
    """
    pid = conn._afterglow_project_id
    nova_fn_map = {
        "start": nova.start_server,
        "stop": nova.stop_server,
        "reboot": nova.reboot_server,
    }

    results: list[dict] = []
    for instance_id in body.instance_ids:
        # 소유권 검증 — 실패 시 generic error로 응답(IDOR oracle 방지)
        try:
            server = await asyncio.to_thread(nova.get_server, conn, instance_id)
            assert_instance_owner(server, conn, token_info)
        except Exception:
            results.append({"id": instance_id, "ok": False, "error": "처리 실패"})
            continue

        try:
            if body.action == "delete":
                await _bulk_delete_one(conn, token_info, server, instance_id, pid)
            else:
                nova_fn = nova_fn_map[body.action]
                await asyncio.to_thread(nova_fn, conn, instance_id)
                await invalidate(f"afterglow:nova:{pid}:instance:{instance_id}")
                await invalidate(f"afterglow:nova:{pid}:instances")
                await cache_invalidation.invalidate_mutation_count("nova", pid)
                await rec(
                    token_info,
                    conn,
                    resource_type="instance",
                    action=f"instance.{body.action}",
                    status="success",
                    resource_id=instance_id,
                )
            results.append({"id": instance_id, "ok": True})
        except Exception:
            results.append({"id": instance_id, "ok": False, "error": "처리 실패"})

    return {"results": results}


@router.delete("/{instance_id}", status_code=204)
@limiter.limit("5/minute")
async def delete_instance(
    request: Request,
    instance_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    pid = conn._afterglow_project_id
    try:
        server = await asyncio.to_thread(nova.get_server, conn, instance_id)
    except Exception:
        raise HTTPException(status_code=404, detail="인스턴스를 찾을 수 없습니다")
    assert_instance_owner(server, conn, token_info)

    upper_volume_id = server.union_upper_volume_id
    file_storage_ids = server.union_share_ids
    strategy = server.union_strategy
    health_id = (server.metadata or {}).get("union_health_id", "")

    # 헬스 토큰 폐기 (best-effort)
    if health_id:
        try:
            from app.services import instance_health as _ih_del

            await _ih_del.revoke_report_token_by_instance(health_id)
        except Exception:
            logger.warning("헬스 토큰 폐기 실패 (instance=%s)", instance_id)

    # Nova 서버 삭제
    await asyncio.to_thread(nova.delete_server, conn, instance_id)
    await invalidate(f"afterglow:nova:{pid}:instances")
    await invalidate(f"afterglow:nova:{pid}:instance:{instance_id}")
    await invalidate(f"afterglow:neutron:{pid}:port_mac_map")
    await cache_invalidation.invalidate_mutation_count("nova", pid)
    await rec(
        token_info,
        conn,
        resource_type="instance",
        action="instance.delete",
        status="success",
        resource_id=instance_id,
        resource_name=server.name,
    )

    # Strategy B: 전용 파일 스토리지 삭제
    if strategy == "dynamic":
        for file_storage_id in file_storage_ids:
            if file_storage_id:
                try:
                    await asyncio.to_thread(manila.delete_file_storage, conn, file_storage_id)
                except Exception as ex:
                    logger.warning(f"파일 스토리지 삭제 실패 {file_storage_id}: {ex}")

    # upper 볼륨 삭제
    if upper_volume_id:
        try:
            await asyncio.to_thread(cinder.delete_volume, conn, upper_volume_id)
        except Exception as ex:
            logger.warning(f"Upper 볼륨 삭제 실패: {ex}")

    # Strategy A(prebuilt): CephX access rule 정리 (best-effort, svc_conn 사용)
    # NFS CIDR rule은 프로젝트 수준 grant이므로 VM 삭제 시 회수하지 않음 (관리자 수동 revoke).
    if strategy != "dynamic":
        try:
            svc_conn_del = await asyncio.to_thread(keystone.get_service_project_connection)
            instance_name = server.name
            for file_storage_id in file_storage_ids:
                if not file_storage_id:
                    continue
                try:
                    access_rules = await asyncio.to_thread(manila.list_access_rules, svc_conn_del, file_storage_id)
                    for rule in access_rules:
                        if rule.get("access_type") == "cephx" and rule.get("access_to", "").startswith(
                            f"union-ro-{instance_name}-"
                        ):
                            await asyncio.to_thread(
                                manila.revoke_access_rule, svc_conn_del, file_storage_id, rule["id"]
                            )
                except Exception as ex:
                    logger.warning(f"prebuilt cephx rule 정리 실패 (share={file_storage_id}): {ex}")
        except Exception as ex:
            logger.warning(f"prebuilt access rule 정리 중 svc_conn 획득 실패: {ex}")

    # data mount CephX access rule 정리 (best-effort, user conn 사용)
    _data_share_meta = (server.metadata or {}).get("union_data_share_ids", "")
    if _data_share_meta and _data_share_meta != "none":
        _instance_name = server.name
        for _fsi in [s for s in _data_share_meta.split(",") if s]:
            try:
                _rules = await asyncio.to_thread(manila.list_access_rules, conn, _fsi)
                for _r in _rules:
                    _at = _r.get("access_to", "")
                    if _r.get("access_type") == "cephx" and (
                        _at.startswith(f"data-ro-{_instance_name}-") or _at.startswith(f"data-rw-{_instance_name}-")
                    ):
                        await asyncio.to_thread(manila.revoke_access_rule, conn, _fsi, _r["id"])
            except Exception as _ex:
                logger.warning(f"data mount cephx rule 정리 실패 (share={_fsi}): {_ex}")

    # Floating IP 정리 (해제 + 삭제)
    try:
        await asyncio.to_thread(neutron.cleanup_instance_fips, conn, instance_id)
    except Exception as ex:
        logger.warning(f"Floating IP 정리 실패: {ex}")


@router.post("/{instance_id}/start", status_code=204)
@limiter.limit("30/minute")
async def start_instance(
    request: Request,
    instance_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    await _simple_action(conn, token_info, instance_id, nova_fn=nova.start_server, action_name="instance.start")


@router.post("/{instance_id}/stop", status_code=204)
@limiter.limit("30/minute")
async def stop_instance(
    request: Request,
    instance_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    await _simple_action(conn, token_info, instance_id, nova_fn=nova.stop_server, action_name="instance.stop")


@router.post("/{instance_id}/reboot", status_code=204)
@limiter.limit("30/minute")
async def reboot_instance(
    request: Request,
    instance_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    await _simple_action(conn, token_info, instance_id, nova_fn=nova.reboot_server, action_name="instance.reboot")


@router.post("/{instance_id}/shelve", status_code=204)
@limiter.limit("30/minute")
async def shelve_instance(
    request: Request,
    instance_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    await _simple_action(conn, token_info, instance_id, nova_fn=nova.shelve_server, action_name="instance.shelve")


@router.post("/{instance_id}/unshelve", status_code=204)
@limiter.limit("30/minute")
async def unshelve_instance(
    request: Request,
    instance_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    await _simple_action(conn, token_info, instance_id, nova_fn=nova.unshelve_server, action_name="instance.unshelve")


@router.get("/{instance_id}/console")
async def get_console(
    instance_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    try:
        url = await asyncio.to_thread(nova.get_console_url, conn, instance_id)
        return {"url": url}
    except Exception:
        raise HTTPException(status_code=500, detail="작업 실패")


@router.get("/{instance_id}/log")
async def get_console_log(
    instance_id: str,
    length: int = Query(default=100, ge=0, le=100000),
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    try:
        output = await asyncio.to_thread(nova.get_console_output, conn, instance_id, length)
        return {"output": output}
    except Exception:
        raise HTTPException(status_code=500, detail="작업 실패")


@router.get("/{instance_id}/interfaces")
async def list_interfaces(
    instance_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    pid = conn._afterglow_project_id
    try:
        return await cached_call(
            f"afterglow:neutron:{pid}:ports:{instance_id}",
            ttl_normal(),
            lambda: neutron.list_instance_ports(conn, instance_id),
        )
    except Exception:
        raise HTTPException(status_code=500, detail="작업 실패")


@router.get("/{instance_id}/volumes")
async def list_instance_volumes(
    instance_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    pid = conn._afterglow_project_id

    def _fetch():
        attachments = nova.list_volume_attachments(conn, instance_id)
        result = []
        for a in attachments:
            try:
                vol = cinder.get_volume(conn, a["volume_id"])
                result.append({**a, "name": vol.name, "size": vol.size, "status": vol.status})
            except Exception:
                result.append(a)
        return result

    try:
        return await cached_call(f"afterglow:cinder:{pid}:vol_attach:{instance_id}", ttl_normal(), _fetch)
    except Exception:
        raise HTTPException(status_code=500, detail="작업 실패")


@router.post("/{instance_id}/volumes", status_code=201)
async def attach_volume_to_instance(
    instance_id: str,
    body: AttachVolumeRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    volume_id = body.volume_id
    pid = conn._afterglow_project_id
    try:
        result = await asyncio.to_thread(nova.attach_volume, conn, instance_id, volume_id)
        await invalidate(f"afterglow:cinder:{pid}:vol_attach:{instance_id}")
        await rec(
            token_info,
            conn,
            resource_type="instance",
            action="instance.attach_volume",
            status="success",
            resource_id=instance_id,
            extra={"volume_id": volume_id},
        )
        return result
    except Exception as e:
        await rec(
            token_info,
            conn,
            resource_type="instance",
            action="instance.attach_volume",
            status="failed",
            resource_id=instance_id,
            error_message=str(e)[:500],
            extra={"volume_id": volume_id},
        )
        raise HTTPException(status_code=500, detail="작업 실패")


@router.delete("/{instance_id}/volumes/{volume_id}", status_code=204)
async def detach_volume_from_instance(
    instance_id: str,
    volume_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    pid = conn._afterglow_project_id
    try:
        await asyncio.to_thread(nova.detach_volume, conn, instance_id, volume_id)
        await invalidate(f"afterglow:cinder:{pid}:vol_attach:{instance_id}")
        await rec(
            token_info,
            conn,
            resource_type="instance",
            action="instance.detach_volume",
            status="success",
            resource_id=instance_id,
            extra={"volume_id": volume_id},
        )
    except HttpException as e:
        await rec(
            token_info,
            conn,
            resource_type="instance",
            action="instance.detach_volume",
            status="failed",
            resource_id=instance_id,
            error_message=str(e)[:500],
        )
        raise HTTPException(status_code=e.http_status or 500, detail=e.message or str(e))
    except Exception as e:
        await rec(
            token_info,
            conn,
            resource_type="instance",
            action="instance.detach_volume",
            status="failed",
            resource_id=instance_id,
            error_message=str(e)[:500],
        )
        logger.error("볼륨 분리 실패", exc_info=True)
        raise HTTPException(status_code=500, detail="작업 실패")


@router.patch("/{instance_id}/volumes/{volume_id}", status_code=204)
async def update_volume_attachment(
    instance_id: str,
    volume_id: str,
    body: UpdateVolumeAttachmentRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    pid = conn._afterglow_project_id
    try:
        await asyncio.to_thread(
            nova.update_volume_attachment_delete_flag,
            conn,
            instance_id,
            volume_id,
            body.delete_on_termination,
        )
        await invalidate(f"afterglow:cinder:{pid}:vol_attach:{instance_id}")
    except HttpException as e:
        raise HTTPException(status_code=e.http_status or 500, detail=e.message or str(e))
    except Exception:
        logger.error("볼륨 연결 정보 업데이트 실패", exc_info=True)
        raise HTTPException(status_code=500, detail="작업 실패")


@router.get("/{instance_id}/security-groups")
async def list_instance_security_groups(
    instance_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    pid = conn._afterglow_project_id

    def _fetch():
        ports = neutron.list_instance_ports(conn, instance_id)
        all_sgs = neutron.list_security_groups(conn, project_id=pid)
        return {"ports": ports, "security_groups": all_sgs}

    try:
        return await cached_call(f"afterglow:neutron:{pid}:sgs:{instance_id}", ttl_slow(), _fetch)
    except Exception:
        raise HTTPException(status_code=500, detail="작업 실패")


@router.get("/{instance_id}/owner")
async def get_instance_owner(
    instance_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    pid = conn._afterglow_project_id

    def _fetch():
        server = nova.get_server(conn, instance_id)
        if not server.user_id:
            return {"display": "-"}
        try:
            user = keystone.get_user(conn, server.user_id)
            name = user["name"]
            email = user["email"]
            display = f"{name}({email})" if email else name
            return {"display": display, "name": name, "email": email}
        except Exception:
            return {"display": server.user_id}

    try:
        return await cached_call(f"afterglow:keystone:{pid}:owner:{instance_id}", ttl_static(), _fetch)
    except Exception:
        raise HTTPException(status_code=404, detail="인스턴스를 찾을 수 없습니다")


@router.post("/{instance_id}/interfaces", status_code=201)
async def attach_interface(
    instance_id: str,
    body: AttachInterfaceRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    net_id = body.net_id
    pid = conn._afterglow_project_id
    try:
        result = await asyncio.to_thread(nova.attach_interface, conn, instance_id, net_id)
        await invalidate(f"afterglow:neutron:{pid}:ports:{instance_id}")
        await invalidate(f"afterglow:neutron:{pid}:port_mac_map")
        await rec(
            token_info,
            conn,
            resource_type="instance",
            action="instance.attach_interface",
            status="success",
            resource_id=instance_id,
            extra={"net_id": net_id},
        )
        return result
    except Exception as e:
        await rec(
            token_info,
            conn,
            resource_type="instance",
            action="instance.attach_interface",
            status="failed",
            resource_id=instance_id,
            error_message=str(e)[:500],
        )
        raise HTTPException(status_code=500, detail="작업 실패")


@router.delete("/{instance_id}/interfaces/{port_id}", status_code=204)
async def detach_interface(
    instance_id: str,
    port_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    pid = conn._afterglow_project_id
    try:
        await asyncio.to_thread(nova.detach_interface, conn, instance_id, port_id)
        await invalidate(f"afterglow:neutron:{pid}:ports:{instance_id}")
        await invalidate(f"afterglow:neutron:{pid}:port_mac_map")
        await rec(
            token_info,
            conn,
            resource_type="instance",
            action="instance.detach_interface",
            status="success",
            resource_id=instance_id,
            extra={"port_id": port_id},
        )
    except Exception as e:
        await rec(
            token_info,
            conn,
            resource_type="instance",
            action="instance.detach_interface",
            status="failed",
            resource_id=instance_id,
            error_message=str(e)[:500],
        )
        raise HTTPException(status_code=500, detail="작업 실패")


@router.post("/{instance_id}/ports/{port_id}/security-groups")
async def update_port_security_groups(
    instance_id: str,
    port_id: str,
    body: UpdateSecurityGroupsRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    sg_ids = body.security_group_ids
    pid = conn._afterglow_project_id
    try:
        result = await asyncio.to_thread(neutron.update_port_security_groups, conn, port_id, sg_ids)
        await invalidate(f"afterglow:neutron:{pid}:sgs:{instance_id}")
        await rec(
            token_info,
            conn,
            resource_type="instance",
            action="instance.update_security_groups",
            status="success",
            resource_id=instance_id,
        )
        return result
    except Exception as e:
        await rec(
            token_info,
            conn,
            resource_type="instance",
            action="instance.update_security_groups",
            status="failed",
            resource_id=instance_id,
            error_message=str(e)[:500],
        )
        raise HTTPException(status_code=500, detail="작업 실패")


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------


async def _bulk_delete_one(
    conn,
    token_info: dict,
    server,
    instance_id: str,
    pid: str,
) -> None:
    """bulk-action DELETE용 인스턴스 삭제 (단건 delete_instance와 동일한 정리 수행)."""
    upper_volume_id = server.union_upper_volume_id
    file_storage_ids = server.union_share_ids
    strategy = server.union_strategy
    health_id = (server.metadata or {}).get("union_health_id", "")

    if health_id:
        try:
            from app.services import instance_health as _ih  # noqa: PLC0415

            await _ih.revoke_report_token_by_instance(health_id)
        except Exception:
            pass

    await asyncio.to_thread(nova.delete_server, conn, instance_id)
    await invalidate(f"afterglow:nova:{pid}:instances")
    await invalidate(f"afterglow:nova:{pid}:instance:{instance_id}")
    await invalidate(f"afterglow:neutron:{pid}:port_mac_map")
    await cache_invalidation.invalidate_mutation_count("nova", pid)
    await rec(
        token_info,
        conn,
        resource_type="instance",
        action="instance.delete",
        status="success",
        resource_id=instance_id,
        resource_name=server.name,
    )

    # Strategy B: 전용 파일 스토리지 삭제 (best-effort)
    if strategy == "dynamic":
        for fsi in file_storage_ids:
            if fsi:
                try:
                    await asyncio.to_thread(manila.delete_file_storage, conn, fsi)
                except Exception:
                    pass

    # upper 볼륨 삭제 (best-effort)
    if upper_volume_id:
        try:
            await asyncio.to_thread(cinder.delete_volume, conn, upper_volume_id)
        except Exception:
            pass

    # Strategy A(prebuilt): CephX access rule 정리 (best-effort)
    if strategy != "dynamic":
        try:
            svc_conn = await asyncio.to_thread(keystone.get_service_project_connection)
            for fsi in file_storage_ids:
                if not fsi:
                    continue
                try:
                    rules = await asyncio.to_thread(manila.list_access_rules, svc_conn, fsi)
                    for rule in rules:
                        if rule.get("access_type") == "cephx" and rule.get("access_to", "").startswith(
                            f"union-ro-{server.name}-"
                        ):
                            await asyncio.to_thread(manila.revoke_access_rule, svc_conn, fsi, rule["id"])
                except Exception:
                    pass
        except Exception:
            pass

    # data mount CephX access rule 정리 (best-effort)
    _data_meta = (server.metadata or {}).get("union_data_share_ids", "")
    if _data_meta and _data_meta != "none":
        for _fsi in [s for s in _data_meta.split(",") if s]:
            try:
                rules = await asyncio.to_thread(manila.list_access_rules, conn, _fsi)
                for r in rules:
                    at = r.get("access_to", "")
                    if r.get("access_type") == "cephx" and (
                        at.startswith(f"data-ro-{server.name}-") or at.startswith(f"data-rw-{server.name}-")
                    ):
                        await asyncio.to_thread(manila.revoke_access_rule, conn, _fsi, r["id"])
            except Exception:
                pass

    # Floating IP 정리 (best-effort)
    try:
        await asyncio.to_thread(neutron.cleanup_instance_fips, conn, instance_id)
    except Exception:
        pass


async def _simple_action(
    conn: openstack.connection.Connection,
    token_info: dict,
    instance_id: str,
    *,
    nova_fn: Callable,
    action_name: str,
) -> None:
    pid = conn._afterglow_project_id
    try:
        server = await asyncio.to_thread(nova.get_server, conn, instance_id)
    except Exception:
        raise HTTPException(status_code=404, detail="인스턴스를 찾을 수 없습니다")
    assert_instance_owner(server, conn, token_info)
    try:
        await asyncio.to_thread(nova_fn, conn, instance_id)
        await invalidate(f"afterglow:nova:{pid}:instance:{instance_id}")
        await invalidate(f"afterglow:nova:{pid}:instances")
        await cache_invalidation.invalidate_mutation_count("nova", pid)
        await rec(
            token_info,
            conn,
            resource_type="instance",
            action=action_name,
            status="success",
            resource_id=instance_id,
        )
    except Exception as e:
        await rec(
            token_info,
            conn,
            resource_type="instance",
            action=action_name,
            status="failed",
            resource_id=instance_id,
            error_message=str(e)[:500],
        )
        raise HTTPException(status_code=500, detail="작업 실패")


def _resolve_project_subnet_cidrs(conn, network_id: str) -> list[str]:
    """주어진 네트워크의 subnet CIDR 목록을 반환."""
    detail = neutron.get_network_detail(conn, network_id)
    return [s.cidr for s in (detail.subnet_details or []) if s.cidr]


async def _prepare_prebuilt_file_storages(
    conn,
    resolved_libs: list[str],
    instance_name: str,
    created_access_ids: list,
    network_id: str = "",
    project_id: str = "",
) -> list[dict]:
    """Strategy A: 사전 빌드된 read-only 파일 스토리지에 access rule 추가.

    Manila 작업은 service 프로젝트 conn으로 수행한다.
    prebuilt share는 service 프로젝트가 소유하므로 사용자 conn으로는 access rule을 만들 수 없다.
    NFS share는 IP 기반 access rule이 필요하므로 project의 subnet CIDR로 rule을 추가한다.
    """
    svc_conn = await asyncio.to_thread(keystone.get_service_project_connection)
    prebuilt_file_storages = await asyncio.to_thread(
        manila.list_file_storages,
        svc_conn,
        {"union_type": "prebuilt"},
        include_public=True,
    )
    # 동일 library_name의 share가 여러 개인 경우 union_built_at 기준 최신을 선택
    prebuilt_map = {}
    for s in prebuilt_file_storages:
        if s.library_name is None:
            continue
        existing = prebuilt_map.get(s.library_name)
        if existing is None or (s.built_at or "") > (existing.built_at or ""):
            prebuilt_map[s.library_name] = s

    # NFS share가 있을 경우 project subnet CIDR 미리 조회
    project_cidrs: list[str] = []
    if network_id:
        try:
            project_cidrs = await asyncio.to_thread(_resolve_project_subnet_cidrs, svc_conn, network_id)
        except Exception as e:
            logger.warning(f"Project subnet CIDR 조회 실패 (network={network_id}): {e}")

    file_storages_info = []
    for lib_id in list(reversed(resolved_libs)):
        file_storage = prebuilt_map.get(lib_id)
        if not file_storage:
            raise RuntimeError(
                f"사전 빌드 파일 스토리지 없음: {lib_id}. Strategy B를 사용하거나 관리자에게 문의하세요."
            )

        if file_storage.share_proto == "NFS":
            # NFS: 프로젝트 subnet CIDR 단위 IP access rule
            if not project_cidrs:
                raise RuntimeError(
                    f"NFS prebuilt share({lib_id}) 마운트를 위해 project subnet CIDR이 필요하지만 조회에 실패했습니다."
                )
            extra_meta = {"union_grant_project": project_id} if project_id else {}
            for cidr in project_cidrs:
                rule = await asyncio.to_thread(
                    manila.ensure_nfs_access_rule,
                    svc_conn,
                    file_storage.id,
                    cidr,
                    "ro",
                    True,
                    "sys",
                    extra_meta or None,
                )
                created_access_ids.append((file_storage.id, rule["access_id"]))

            export_paths = await asyncio.to_thread(manila.get_export_locations, svc_conn, file_storage.id)
            file_storages_info.append(
                {
                    "file_storage_id": file_storage.id,
                    "name": lib_id,
                    "share_proto": "NFS",
                    "export_path": "",
                    "cephx_id": "",
                    "cephx_key": "",
                    "nfs_export_location": export_paths[0]
                    if export_paths
                    else (file_storage.nfs_export_location or ""),
                    "mount_options": "hard,intr,noatime,nosuid,nodev,noexec,_netdev,timeo=10,retrans=3",
                }
            )
        else:
            # CephFS: CephX access rule (기존 로직)
            cephx_id = f"union-ro-{instance_name}-{lib_id}"
            # create_access_rule은 key 발급 실패 시 RuntimeError를 던지며 고아 rule을 자동 정리한다.
            rule = await asyncio.to_thread(manila.create_access_rule, svc_conn, file_storage.id, cephx_id, "ro")
            # access_id를 즉시 추적 → rollback 시 정리 보장
            created_access_ids.append((file_storage.id, rule["access_id"]))

            export_paths = await asyncio.to_thread(manila.get_export_locations, svc_conn, file_storage.id)
            if not export_paths:
                raise RuntimeError(
                    f"prebuilt share({lib_id}) export location을 찾을 수 없습니다. "
                    "share가 available 상태인지 확인하세요."
                )
            file_storages_info.append(
                {
                    "file_storage_id": file_storage.id,
                    "name": lib_id,
                    "share_proto": file_storage.share_proto,
                    "export_path": export_paths[0],
                    "cephx_id": cephx_id,
                    "cephx_key": rule["access_key"],
                    "nfs_export_location": file_storage.nfs_export_location or "",
                    "mount_options": "",
                }
            )
    return file_storages_info


async def _prepare_dynamic_file_storage(
    conn,
    instance_name: str,
    resolved_libs: list[str],
    settings,
    created_file_storage_ids: list,
    created_access_ids: list,
    share_proto: str = "CEPHFS",
    vm_ip_address: str = "",
) -> dict:
    """Strategy B: VM 전용 read-write 파일 스토리지 신규 생성.

    share_proto에 따라 CephFS 또는 NFS share를 생성한다.
    """
    from app.services.resource_policy_store import resolve_policy_snapshot

    policy_key = "manila.nfs_share_type" if share_proto.upper() == "NFS" else "manila.cephfs_share_type"
    policies = await resolve_policy_snapshot(conn=conn, keys=(policy_key,))
    share_type = policies[policy_key]["name"]
    share_network_id = ""
    if share_proto.upper() == "NFS":
        raise HTTPException(
            status_code=422,
            detail="NFS dynamic shares require a tenant-visible share network selected by the request",
        )

    file_storage = await asyncio.to_thread(
        manila.create_file_storage,
        conn,
        f"union-dyn-{instance_name}",
        settings.upper_volume_size_gb,
        share_network_id,
        share_type,
        share_proto,
        {
            "union_type": "dynamic",
            "union_instance": instance_name,
            "union_libraries": ",".join(resolved_libs),
            "union_share_proto": share_proto.upper(),
            "union_project_id": getattr(conn, "_afterglow_project_id", ""),
        },
    )
    created_file_storage_ids.append(file_storage.id)

    if share_proto.upper() == "NFS":
        # NFS: IP 기반 access rule
        if not vm_ip_address:
            raise HTTPException(status_code=503, detail="VM IP not yet allocated, retry shortly")
        access_to = vm_ip_address
        rule = await asyncio.to_thread(
            manila.ensure_nfs_access_rule,
            conn,
            file_storage.id,
            access_to,
            "rw",
            settings.manila_nfs_root_squash,
            settings.manila_nfs_sec_flavor,
        )
        created_access_ids.append((file_storage.id, rule["access_id"]))

        nfs_export = file_storage.nfs_export_location
        if not nfs_export:
            export_paths = await asyncio.to_thread(manila.get_export_locations, conn, file_storage.id)
            nfs_export = export_paths[0] if export_paths else ""

        return {
            "file_storage_id": file_storage.id,
            "name": "dynamic",
            "share_proto": "NFS",
            "export_path": "",
            "cephx_id": "",
            "cephx_key": "",
            "nfs_export_location": nfs_export,
            "mount_options": "hard,intr,noatime,nosuid,nodev,noexec,_netdev,timeo=10,retrans=3",
        }
    else:
        # CephFS: CephX access rule (기존 로직)
        cephx_id = f"union-rw-{instance_name}"
        rule = await asyncio.to_thread(manila.create_access_rule, conn, file_storage.id, cephx_id, "rw")
        created_access_ids.append((file_storage.id, rule["access_id"]))

        export_paths = await asyncio.to_thread(manila.get_export_locations, conn, file_storage.id)
        return {
            "file_storage_id": file_storage.id,
            "name": "dynamic",
            "share_proto": "CEPHFS",
            "export_path": export_paths[0] if export_paths else "",
            "cephx_id": cephx_id,
            "cephx_key": rule["access_key"],
            "nfs_export_location": "",
            "mount_options": "",
        }


async def _prepare_data_mounts(
    conn,
    data_mounts: list,
    instance_name: str,
    created_access_ids: list,
    network_id: str = "",
) -> list[dict]:
    """사용자 소유 Manila share를 VM 생성 시 직접 마운트하기 위한 access rule 준비.

    반환값: cloud-init 템플릿에 전달할 data_mounts 목록.
    """
    if not data_mounts:
        return []

    settings = get_settings()
    project_id = conn._afterglow_project_id
    project_cidrs: list[str] = []
    result = []

    for spec in data_mounts:
        share = await asyncio.to_thread(manila.get_file_storage, conn, spec.file_storage_id)

        share_project = share.project_id or ""
        if share_project != project_id and not share.is_public:
            raise HTTPException(
                status_code=403,
                detail=f"파일 스토리지 {spec.file_storage_id}에 대한 접근 권한이 없습니다.",
            )
        if share.status != "available":
            raise HTTPException(
                status_code=409,
                detail=f"파일 스토리지 {spec.file_storage_id}가 available 상태가 아닙니다: {share.status}",
            )

        access_level = "ro" if spec.read_only else "rw"

        if share.share_proto == "NFS":
            if not project_cidrs:
                if not network_id:
                    raise HTTPException(
                        status_code=400,
                        detail="NFS 파일 스토리지 마운트를 위해 network_id가 필요합니다.",
                    )
                try:
                    project_cidrs = await asyncio.to_thread(_resolve_project_subnet_cidrs, conn, network_id)
                except Exception as e:
                    raise HTTPException(status_code=503, detail=f"Subnet CIDR 조회 실패: {e}")
            if not project_cidrs:
                raise HTTPException(status_code=503, detail="Project subnet CIDR을 조회할 수 없습니다.")

            nfs_base = "hard,intr,noatime,nosuid,nodev,_netdev,timeo=10,retrans=3"
            mount_options = f"ro,{nfs_base}" if spec.read_only else nfs_base
            for cidr in project_cidrs:
                rule = await asyncio.to_thread(
                    manila.ensure_nfs_access_rule,
                    conn,
                    share.id,
                    cidr,
                    access_level,
                    settings.manila_nfs_root_squash,
                    settings.manila_nfs_sec_flavor,
                )
                created_access_ids.append((share.id, rule["access_id"]))

            nfs_export = share.nfs_export_location
            if not nfs_export:
                locs = await asyncio.to_thread(manila.get_export_locations, conn, share.id)
                nfs_export = locs[0] if locs else ""

            result.append(
                {
                    "file_storage_id": share.id,
                    "mount_point": spec.mount_point,
                    "share_proto": "NFS",
                    "nfs_export_location": nfs_export,
                    "export_path": "",
                    "cephx_id": "",
                    "cephx_key": "",
                    "mount_options": mount_options,
                    "read_only": spec.read_only,
                }
            )

        else:
            cephx_id = f"data-{access_level}-{instance_name}-{share.id[:8]}"
            rule = await asyncio.to_thread(manila.create_access_rule, conn, share.id, cephx_id, access_level)
            created_access_ids.append((share.id, rule["access_id"]))

            locs = await asyncio.to_thread(manila.get_export_locations, conn, share.id)
            if not locs:
                raise HTTPException(
                    status_code=503,
                    detail=f"파일 스토리지 {spec.file_storage_id} export location을 찾을 수 없습니다.",
                )

            result.append(
                {
                    "file_storage_id": share.id,
                    "mount_point": spec.mount_point,
                    "share_proto": share.share_proto,
                    "nfs_export_location": "",
                    "export_path": locs[0],
                    "cephx_id": cephx_id,
                    "cephx_key": rule["access_key"],
                    "mount_options": "",
                    "read_only": spec.read_only,
                }
            )

    return result


# ---------------------------------------------------------------------------
# Floating IP 자동 관리 엔드포인트
# ---------------------------------------------------------------------------


@router.post("/{instance_id}/floating-ip", response_model=dict)
async def assign_floating_ip(
    instance_id: str,
    port_id: str | None = Query(None, description="연결할 포트 ID (미지정 시 첫 번째 포트)"),
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    """인스턴스에 새 Floating IP를 자동 생성하고 연결한다."""
    pid = conn._afterglow_project_id
    try:
        # 1) 인스턴스 포트 조회 + 점유 체크
        ports = await asyncio.to_thread(lambda: list(conn.network.ports(device_id=instance_id)))
        if not ports:
            raise HTTPException(status_code=400, detail="인스턴스에 연결된 포트가 없습니다")
        used_port_ids = await asyncio.to_thread(lambda: {f.port_id for f in conn.network.ips() if f.port_id})
        if port_id:
            target_port = next((p for p in ports if p.id == port_id), None)
            if not target_port:
                raise HTTPException(status_code=404, detail="해당 인터페이스를 찾을 수 없습니다")
            if port_id in used_port_ids:
                raise HTTPException(
                    status_code=409,
                    detail="해당 인터페이스에 이미 Floating IP가 할당되어 있습니다",
                )
        else:
            available = [p for p in ports if p.id not in used_port_ids]
            if not available:
                raise HTTPException(
                    status_code=400,
                    detail="모든 인터페이스에 이미 Floating IP가 할당되어 있습니다",
                )
            target_port = available[0]
            port_id = target_port.id

        # 2) 인스턴스 서브넷 → 라우터 → 연결된 외부 네트워크 결정
        subnet_ids = {fi.get("subnet_id") for fi in (target_port.fixed_ips or []) if fi.get("subnet_id")}
        ext_net_id = await asyncio.to_thread(neutron.find_external_network_for_subnets, conn, subnet_ids)
        if not ext_net_id:
            raise HTTPException(
                status_code=422,
                detail=(
                    "이 인터페이스의 서브넷이 외부 네트워크와 라우터로 연결되어 있지 않습니다. "
                    "라우터로 외부 네트워크에 연결한 뒤 다시 시도하세요."
                ),
            )

        # 3) FIP 생성 + 연결 (race 발생 시 rollback)
        fip = await asyncio.to_thread(neutron.create_floating_ip, conn, ext_net_id)
        try:
            result = await asyncio.to_thread(neutron.associate_floating_ip, conn, fip.id, instance_id, port_id)
        except Exception as ex:
            try:
                await asyncio.to_thread(neutron.delete_floating_ip, conn, fip.id)
            except Exception:
                pass
            raise ex
        await invalidate(f"afterglow:neutron:{pid}:floating_ips")
        await rec(
            token_info,
            conn,
            resource_type="instance",
            action="instance.assign_floating_ip",
            status="success",
            resource_id=instance_id,
        )
        return {"id": result.id, "floating_ip_address": result.floating_ip_address}
    except HTTPException:
        raise
    except ConflictException as ex:
        logger.warning("Floating IP 할당 충돌: %s", ex)
        await rec(
            token_info,
            conn,
            resource_type="instance",
            action="instance.assign_floating_ip",
            status="failed",
            resource_id=instance_id,
            error_message=str(ex)[:500],
        )
        raise HTTPException(
            status_code=409,
            detail="해당 인터페이스에 이미 Floating IP가 할당되어 있습니다",
        )
    except Exception as ex:
        msg = str(ex)
        if "is not reachable from subnet" in msg or "not reachable from" in msg:
            logger.warning("Floating IP 할당 실패 (외부망 reachable 아님): %s", ex)
            await rec(
                token_info,
                conn,
                resource_type="instance",
                action="instance.assign_floating_ip",
                status="failed",
                resource_id=instance_id,
                error_message=msg[:500],
            )
            raise HTTPException(
                status_code=422,
                detail=(
                    "선택된 외부 네트워크가 인스턴스 서브넷에서 도달 불가능합니다. "
                    "라우터의 외부 게이트웨이 설정을 확인하세요."
                ),
            )
        logger.warning("Floating IP 할당 실패: %s", ex)
        await rec(
            token_info,
            conn,
            resource_type="instance",
            action="instance.assign_floating_ip",
            status="failed",
            resource_id=instance_id,
            error_message=msg[:500],
        )
        raise HTTPException(status_code=500, detail="Floating IP 할당 실패")


@router.delete("/{instance_id}/floating-ip", status_code=204)
async def release_floating_ip(
    instance_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    """인스턴스에 연결된 Floating IP를 해제하고 삭제한다."""
    pid = conn._afterglow_project_id
    try:
        await asyncio.to_thread(neutron.cleanup_instance_fips, conn, instance_id)
        await invalidate(f"afterglow:neutron:{pid}:floating_ips")
        await rec(
            token_info,
            conn,
            resource_type="instance",
            action="instance.release_floating_ip",
            status="success",
            resource_id=instance_id,
        )
    except Exception as ex:
        logger.warning("Floating IP 해제 실패: %s", ex)
        await rec(
            token_info,
            conn,
            resource_type="instance",
            action="instance.release_floating_ip",
            status="failed",
            resource_id=instance_id,
            error_message=str(ex)[:500],
        )
        raise HTTPException(status_code=500, detail="Floating IP 해제 실패")


@router.get("/{server_id}/admin-password/precheck", response_model=AdminPasswordPrecheck)
async def precheck_admin_password(
    server_id: str,
    _: None = Depends(require_admin),
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """관리자 패스워드 재설정 가능 여부를 사전 점검한다.
    QGA 지원 여부, 인스턴스 상태, os_admin_user를 반환.
    """
    try:
        s = await asyncio.to_thread(nova.get_server, conn, server_id)
    except Exception:
        raise HTTPException(status_code=404, detail="인스턴스를 찾을 수 없습니다")

    if s.status != "ACTIVE":
        return AdminPasswordPrecheck(
            supported=False,
            reason=f"인스턴스가 ACTIVE 상태가 아닙니다 (현재: {s.status})",
            server_status=s.status,
        )

    try:
        img_meta = await asyncio.to_thread(nova.get_server_image_meta, conn, server_id)
    except Exception:
        img_meta = {"qga_enabled": False, "os_admin_user": None, "image_id": None, "image_name": None}

    if not img_meta["qga_enabled"]:
        return AdminPasswordPrecheck(
            supported=False,
            reason="이미지에 QEMU Guest Agent(QGA)가 활성화되지 않았습니다. 이미지 메타데이터에 hw_qemu_guest_agent=yes 설정이 필요합니다.",
            os_admin_user=img_meta.get("os_admin_user"),
            server_status=s.status,
        )

    return AdminPasswordPrecheck(
        supported=True,
        os_admin_user=img_meta.get("os_admin_user"),
        server_status=s.status,
    )


@router.post("/{server_id}/admin-password", status_code=204)
async def set_admin_password(
    server_id: str,
    body: AdminPasswordRequest,
    token_info: dict = Depends(get_token_info),
    _: None = Depends(require_admin),
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """QEMU Guest Agent를 통해 인스턴스 관리자 계정의 패스워드를 재설정한다.
    이미지에 hw_qemu_guest_agent=yes + 게스트 내 QGA 데몬 실행 중이어야 동작.
    """
    try:
        s = await asyncio.to_thread(nova.get_server, conn, server_id)
    except Exception:
        raise HTTPException(status_code=404, detail="인스턴스를 찾을 수 없습니다")

    if s.status != "ACTIVE":
        raise HTTPException(
            status_code=409,
            detail=f"패스워드 변경은 ACTIVE 상태에서만 가능합니다 (현재: {s.status})",
        )

    img_meta = {"qga_enabled": False, "os_admin_user": None}
    try:
        img_meta = await asyncio.to_thread(nova.get_server_image_meta, conn, server_id)
    except Exception:
        pass

    if not img_meta["qga_enabled"]:
        raise HTTPException(
            status_code=409,
            detail="이미지에 QGA가 활성화되지 않아 패스워드 변경이 동작하지 않습니다. 이미지 메타데이터에 hw_qemu_guest_agent=yes 설정이 필요합니다.",
        )

    actor_id = token_info.get("user_id", "unknown")
    project_id = token_info.get("project_id", "unknown")
    logger.warning(
        "admin_password_reset server=%s actor=%s project=%s os_admin_user=%s",
        server_id,
        actor_id,
        project_id,
        img_meta.get("os_admin_user"),
    )

    try:
        await asyncio.to_thread(nova.change_server_password, conn, server_id, body.new_password)
        await rec(
            token_info,
            conn,
            resource_type="instance",
            action="instance.set_admin_password",
            status="success",
            resource_id=server_id,
        )
    except ConflictException as e:
        await rec(
            token_info,
            conn,
            resource_type="instance",
            action="instance.set_admin_password",
            status="failed",
            resource_id=server_id,
            error_message=str(e)[:500],
        )
        raise HTTPException(status_code=409, detail=f"Nova 패스워드 변경 충돌: {e}")
    except Exception as e:
        logger.warning("admin_password_reset 실패 server=%s: %s", server_id, e)
        await rec(
            token_info,
            conn,
            resource_type="instance",
            action="instance.set_admin_password",
            status="failed",
            resource_id=server_id,
            error_message=str(e)[:500],
        )
        raise HTTPException(status_code=500, detail="패스워드 변경 요청 실패")


# ---------------------------------------------------------------------------
# 파일 스토리지 연결 (실행 중 VM) — storage-attachments
# ---------------------------------------------------------------------------


@router.post("/{instance_id}/storage-attachments", response_model=dict)
async def attach_storage(
    instance_id: str,
    req: StorageAttachRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    """실행 중인 VM에 Manila 파일 스토리지 접근 규칙을 부여하고 마운트 명령을 반환한다."""
    import shlex as _shlex

    try:
        server = await asyncio.to_thread(nova.get_server, conn, instance_id)
    except Exception:
        raise HTTPException(status_code=404, detail="인스턴스를 찾을 수 없습니다")
    assert_instance_owner(server, conn, token_info)

    share = await asyncio.to_thread(manila.get_file_storage, conn, req.file_storage_id)
    project_id = conn._afterglow_project_id
    if (share.project_id or "") != project_id and not share.is_public:
        raise HTTPException(status_code=403, detail="파일 스토리지 접근 권한이 없습니다.")
    if share.status != "available":
        raise HTTPException(status_code=409, detail=f"파일 스토리지가 available 상태가 아닙니다: {share.status}")

    access_level = "ro" if req.read_only else "rw"
    settings = get_settings()

    if share.share_proto == "NFS":
        fixed_ip = next((ip.addr for ip in server.ip_addresses if ip.type == "fixed"), None)
        if not fixed_ip:
            raise HTTPException(
                status_code=409, detail="VM의 fixed IP를 찾을 수 없습니다. VM이 실행 중인지 확인하세요."
            )

        rule = await asyncio.to_thread(
            manila.ensure_nfs_access_rule,
            conn,
            share.id,
            fixed_ip,
            access_level,
            settings.manila_nfs_root_squash,
            settings.manila_nfs_sec_flavor,
        )

        nfs_export = share.nfs_export_location
        if not nfs_export:
            locs = await asyncio.to_thread(manila.get_export_locations, conn, share.id)
            nfs_export = locs[0] if locs else ""

        nfs_base = "hard,intr,noatime,nosuid,nodev,_netdev,timeo=10,retrans=3"
        mount_opts = f"ro,{nfs_base}" if req.read_only else nfs_base
        mount_command = (
            f"sudo mkdir -p {_shlex.quote(req.mount_point)} && "
            f"sudo mount -t nfs -o {mount_opts} {_shlex.quote(nfs_export)} {_shlex.quote(req.mount_point)}"
        )

        await asyncio.to_thread(
            conn.compute.set_server_metadata,
            instance_id,
            _merge_data_share_meta(server, share.id),
        )
        await invalidate(f"afterglow:nova:{project_id}:instance:{instance_id}")
        await cache_invalidation.invalidate_mutation_count("nova", project_id)

        return {
            "file_storage_id": share.id,
            "share_proto": "NFS",
            "mount_command": mount_command,
            "keyring_file": None,
            "keyring_path": None,
            "access_id": rule["access_id"],
        }

    else:
        cephx_id = f"data-{access_level}-{server.name}-{share.id[:8]}"
        rule = await asyncio.to_thread(manila.create_access_rule, conn, share.id, cephx_id, access_level)

        locs = await asyncio.to_thread(manila.get_export_locations, conn, share.id)
        export_path = locs[0] if locs else ""
        keyring_path = f"/etc/ceph/ceph.client.{cephx_id}.keyring"
        keyring_content = f"[client.{cephx_id}]\n    key = {rule['access_key']}\n"
        ceph_opts = f"name={cephx_id},secretfile={keyring_path},_netdev"
        if req.read_only:
            ceph_opts += ",ro"
        mount_command = (
            f"sudo mkdir -p {_shlex.quote(req.mount_point)} && "
            f"sudo bash -c 'cat > {_shlex.quote(keyring_path)} << EOF\n{keyring_content}EOF' && "
            f"sudo mount -t ceph {_shlex.quote(export_path)} {_shlex.quote(req.mount_point)} -o {_shlex.quote(ceph_opts)}"
        )

        await asyncio.to_thread(
            conn.compute.set_server_metadata,
            instance_id,
            _merge_data_share_meta(server, share.id),
        )
        await invalidate(f"afterglow:nova:{project_id}:instance:{instance_id}")
        await cache_invalidation.invalidate_mutation_count("nova", project_id)

        return {
            "file_storage_id": share.id,
            "share_proto": "CEPHFS",
            "mount_command": mount_command,
            "keyring_file": keyring_content,
            "keyring_path": keyring_path,
            "access_id": rule["access_id"],
        }


@router.get("/{instance_id}/storage-attachments", response_model=list)
async def list_storage_attachments(
    instance_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    """VM에 연결된 데이터 파일 스토리지 목록을 반환한다."""
    try:
        server = await asyncio.to_thread(nova.get_server, conn, instance_id)
    except Exception:
        raise HTTPException(status_code=404, detail="인스턴스를 찾을 수 없습니다")
    assert_instance_owner(server, conn, token_info)

    meta_val = (server.metadata or {}).get("union_data_share_ids", "")
    if not meta_val or meta_val == "none":
        return []

    result = []
    for fsi in [s for s in meta_val.split(",") if s]:
        try:
            share = await asyncio.to_thread(manila.get_file_storage, conn, fsi)
            result.append(
                {
                    "file_storage_id": share.id,
                    "name": share.name,
                    "share_proto": share.share_proto,
                    "status": share.status,
                }
            )
        except Exception:
            result.append({"file_storage_id": fsi, "name": None, "share_proto": None, "status": "unknown"})

    return result


@router.delete("/{instance_id}/storage-attachments/{file_storage_id}", status_code=204)
async def detach_storage(
    instance_id: str,
    file_storage_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    """VM에서 데이터 파일 스토리지 접근 규칙을 회수한다."""
    try:
        server = await asyncio.to_thread(nova.get_server, conn, instance_id)
    except Exception:
        raise HTTPException(status_code=404, detail="인스턴스를 찾을 수 없습니다")
    assert_instance_owner(server, conn, token_info)

    instance_name = server.name

    # CephX 규칙 정리
    try:
        rules = await asyncio.to_thread(manila.list_access_rules, conn, file_storage_id)
        for rule in rules:
            at = rule.get("access_to", "")
            if rule.get("access_type") == "cephx" and (
                at.startswith(f"data-ro-{instance_name}-") or at.startswith(f"data-rw-{instance_name}-")
            ):
                await asyncio.to_thread(manila.revoke_access_rule, conn, file_storage_id, rule["id"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Access rule 정리 실패: {e}")

    # NFS IP 규칙 정리 (VM fixed IP)
    fixed_ip = next((ip.addr for ip in server.ip_addresses if ip.type == "fixed"), None)
    if fixed_ip:
        try:
            rules = await asyncio.to_thread(manila.list_access_rules, conn, file_storage_id)
            for rule in rules:
                if rule.get("access_type") == "ip" and rule.get("access_to") == fixed_ip:
                    await asyncio.to_thread(manila.revoke_access_rule, conn, file_storage_id, rule["id"])
        except Exception as e:
            logger.warning(f"NFS IP rule 정리 실패 (share={file_storage_id}): {e}")

    # 메타데이터에서 제거
    try:
        meta_val = (server.metadata or {}).get("union_data_share_ids", "")
        ids = [s for s in meta_val.split(",") if s and s != file_storage_id] if meta_val and meta_val != "none" else []
        await asyncio.to_thread(
            conn.compute.set_server_metadata,
            instance_id,
            {"union_data_share_ids": ",".join(ids) if ids else "none"},
        )
    except Exception as e:
        logger.warning(f"union_data_share_ids 메타데이터 갱신 실패: {e}")

    _pid = conn._afterglow_project_id
    await invalidate(f"afterglow:nova:{_pid}:instance:{instance_id}")
    await cache_invalidation.invalidate_mutation_count("nova", _pid)


def _merge_data_share_meta(server, new_share_id: str) -> dict:
    """서버 메타데이터의 union_data_share_ids에 share_id를 추가한 dict 반환."""
    meta_val = (server.metadata or {}).get("union_data_share_ids", "")
    ids = [s for s in meta_val.split(",") if s] if meta_val and meta_val != "none" else []
    if new_share_id not in ids:
        ids.append(new_share_id)
    return {"union_data_share_ids": ",".join(ids)}
