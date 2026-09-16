"""관리자용 cross-project 인스턴스 생성 엔드포인트."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import openstack

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.api.common.activity_recorder import rec
from app.api.deps import get_token_info, require_admin
from app.config import get_settings
from app.models import compute as compute_models
from app.models.compute import CreateInstanceRequest
from app.models.progress import ProgressMessage, ProgressStep
from app.services import cinder, cloudinit, keystone, neutron, nova, vm_cloud_init_library
from app.services import libraries as lib_svc
from app.services.instance_names import ensure_unique_instance_name

logger = logging.getLogger(__name__)
router = APIRouter()


class AdminCreateInstanceRequest(CreateInstanceRequest):
    """CreateInstanceRequest + 대상 프로젝트 ID."""

    project_id: str


# pydantic 2.11+ 는 크로스모듈 서브클래스의 forward ref(부모의 list["NewVolumeRequest"]·["DataMountSpec"] 등)를
# 서브클래스 모듈 네임스페이스에서 재해석한다. 부모가 정의된 compute 모듈 네임스페이스를 주입해 해소한다.
AdminCreateInstanceRequest.model_rebuild(_types_namespace=vars(compute_models))


def _make_admin_conn(project_id: str, user_id: str) -> openstack.connection.Connection:
    """admin 크리덴셜로 특정 프로젝트에 스코프된 conn을 생성하고 afterglow 속성을 설정."""
    conn = keystone.get_admin_connection_for_project(project_id)
    conn._afterglow_project_id = project_id
    conn._afterglow_token = ""
    conn._afterglow_user_id = user_id
    return conn


@router.get("/instances/flavors-for-project", dependencies=[Depends(require_admin)])
async def list_project_flavors_for_admin(
    project_id: str = Query(..., description="대상 프로젝트 ID"),
    count: int = Query(1, ge=1, le=100, description="동일 flavor 생성 수량"),
    token_info: dict = Depends(get_token_info),
):
    """Return target-project-visible flavors with target quota eligibility."""
    from app.services.flavor_eligibility import evaluate_project_flavors

    try:
        conn = await asyncio.to_thread(_make_admin_conn, project_id, token_info.get("user_id", ""))
        try:
            flavors = await asyncio.to_thread(nova.list_flavors, conn)
            return await evaluate_project_flavors(conn, project_id, flavors, count=count)
        finally:
            await asyncio.to_thread(conn.close)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="대상 프로젝트 Flavor 목록 조회 실패")


@router.get("/instances/networks-for-project", dependencies=[Depends(require_admin)])
async def list_project_networks_for_admin(
    project_id: str = Query(..., description="대상 프로젝트 ID"),
    token_info: dict = Depends(get_token_info),
):
    """특정 프로젝트의 네트워크 목록 (admin VM 생성 마법사용)."""
    try:
        conn = await asyncio.to_thread(_make_admin_conn, project_id, token_info.get("user_id", ""))
        try:
            return await asyncio.to_thread(neutron.list_networks, conn, project_id)
        finally:
            await asyncio.to_thread(conn.close)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="네트워크 목록 조회 실패")


@router.get("/instances/security-groups-for-project", dependencies=[Depends(require_admin)])
async def list_project_security_groups_for_admin(
    project_id: str = Query(..., description="대상 프로젝트 ID"),
    token_info: dict = Depends(get_token_info),
):
    """특정 프로젝트의 보안 그룹 목록 (admin VM 생성 마법사용)."""
    try:
        conn = await asyncio.to_thread(_make_admin_conn, project_id, token_info.get("user_id", ""))
        try:
            return await asyncio.to_thread(neutron.list_security_groups, conn, project_id)
        finally:
            await asyncio.to_thread(conn.close)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="보안 그룹 목록 조회 실패")


@router.get("/instances/volumes-for-project", dependencies=[Depends(require_admin)])
async def list_project_volumes_for_admin(
    project_id: str = Query(..., description="대상 프로젝트 ID"),
    bootable: bool = Query(False, description="부팅 가능 볼륨만 필터"),
    token_info: dict = Depends(get_token_info),
):
    """특정 프로젝트의 볼륨 목록 (admin VM 생성 마법사용)."""
    try:
        conn = await asyncio.to_thread(_make_admin_conn, project_id, token_info.get("user_id", ""))
        try:
            vols = await asyncio.to_thread(cinder.list_volumes, conn)
            if bootable:
                vols = [v for v in vols if v.bootable and v.status == "available"]
            return vols
        finally:
            await asyncio.to_thread(conn.close)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="볼륨 목록 조회 실패")


@router.post("/instances/async", dependencies=[Depends(require_admin)])
async def admin_create_instance_async(
    req: AdminCreateInstanceRequest,
    token_info: dict = Depends(get_token_info),
):
    """관리자용 cross-project SSE VM 생성.

    대상 프로젝트에 admin 크리덴셜로 스코프된 conn을 사용해 인스턴스를 생성한다.
    키페어는 user-scoped라 admin이 조회 불가 — key_name 미지정 시 콘솔 비밀번호 사용.
    """
    from app.api.compute.instances import (
        _prepare_dynamic_file_storage,
        _prepare_prebuilt_file_storages,
    )
    from app.services import instance_orchestration as instance_orch

    settings = get_settings()
    resolved_libs = lib_svc.resolve_with_deps(req.libraries)

    conn = await asyncio.to_thread(_make_admin_conn, req.project_id, token_info.get("user_id", ""))
    try:
        req = req.model_copy(update={"name": await asyncio.to_thread(ensure_unique_instance_name, conn, req.name)})
    except ValueError as exc:
        await asyncio.to_thread(conn.close)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        if not req.network_id:
            req = req.model_copy(update={"network_id": await instance_orch.resolve_default_network(conn, settings)})
        compute_availability_zone, volume_availability_zone = await instance_orch.resolve_availability_zones(
            conn, req.availability_zone
        )
    except Exception:
        await asyncio.to_thread(conn.close)
        raise

    from app.services.flavor_eligibility import (
        FlavorEligibilityDenied,
        FlavorEligibilityUnavailable,
        admit_flavor,
        release_admission,
    )
    from app.services.gpu_quota import GpuQuotaDenied, GpuQuotaUnavailable

    try:
        sse_flavors = await asyncio.to_thread(nova.list_flavors, conn)
        sse_flavor = next((flavor for flavor in sse_flavors if flavor.id == req.flavor_id), None)
        if sse_flavor is None:
            raise HTTPException(status_code=400, detail="Invalid flavor ID")
        admission = await admit_flavor(conn, req.project_id, sse_flavor)
    except (FlavorEligibilityDenied, GpuQuotaDenied) as exc:
        await asyncio.to_thread(conn.close)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (FlavorEligibilityUnavailable, GpuQuotaUnavailable) as exc:
        await asyncio.to_thread(conn.close)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except HTTPException:
        await asyncio.to_thread(conn.close)
        raise
    gpu_available = bool(admission.gpu_requested)

    async def progress_generator():
        import time

        created_file_storage_ids: list[str] = []
        created_access_ids: list[tuple[str, str]] = []
        boot_volume_id: str | None = None
        boot_volume_was_provided: bool = False
        upper_volume_id: str | None = None
        created_upper: bool = False
        server_id: str | None = None
        floating_ip_id: str | None = None
        _start_time = time.monotonic()

        def send_progress(step: ProgressStep, progress: int, message: str, **extra):
            elapsed = round(time.monotonic() - _start_time, 1)
            msg = ProgressMessage(step=step, progress=progress, message=message, elapsed_seconds=elapsed, **extra)
            return f"data: {msg.model_dump_json()}\n\n"

        try:
            file_storages_info = []
            _sse_health_id = ""
            _sse_health_token = ""

            if resolved_libs:
                yield send_progress(ProgressStep.MANILA_PREPARING, 0, "파일 스토리지 준비 중...")
                if req.strategy == "prebuilt":
                    file_storages_info = await _prepare_prebuilt_file_storages(
                        conn,
                        resolved_libs,
                        req.name,
                        created_access_ids,
                        network_id=req.network_id or "",
                        project_id=req.project_id,
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
                yield send_progress(ProgressStep.MANILA_PREPARING, 20, "파일 스토리지 준비 완료")

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

            if resolved_libs or gpu_available:
                yield send_progress(ProgressStep.USERDATA_GENERATING, 60, "cloud-init 생성 중...")
                import uuid as _uuid2

                _sse_health_id = str(_uuid2.uuid4())
                _sse_report_url = settings.instance_health_callback_base_url or ""
                if _sse_report_url:
                    try:
                        from app.services import instance_health as _ih2

                        _sse_health_token = await _ih2.issue_report_token(_sse_health_id, req.project_id)
                    except Exception:
                        logger.warning("SSE 헬스 토큰 발급 실패", exc_info=True)
                else:
                    _sse_report_url = ""

                userdata = cloudinit.generate_userdata(
                    libraries=resolved_libs,
                    strategy=req.strategy,
                    file_storages=file_storages_info,
                    upper_device="/dev/vdb",
                    ceph_monitors=settings.ceph_monitors,
                    gpu_available=gpu_available,
                    instance_id=_sse_health_id if _sse_health_token else "",
                    report_url=_sse_report_url if _sse_health_token else "",
                    report_token=_sse_health_token,
                    github_username=req.github_username,
                )
                yield send_progress(ProgressStep.USERDATA_GENERATING, 65, "cloud-init 생성 완료")
            else:
                userdata = None

            userdata = cloudinit.compose_userdata(userdata, req.userdata, req.github_username)

            yield send_progress(ProgressStep.SERVER_CREATING, 65, "Nova 서버 생성 중...")
            _sse_effective_sgs: list[str] | None = list(req.security_groups) if req.security_groups else None

            meta = {
                "union_libraries": ",".join(resolved_libs) if resolved_libs else "none",
                "union_strategy": req.strategy or "none",
                "union_share_ids": (
                    ",".join([s.get("file_storage_id", "") for s in file_storages_info])
                    if file_storages_info
                    else "none"
                ),
                "union_upper_volume_id": upper_volume_id or "none",
                "scheduling": req.scheduling,
            }
            if req.scheduling == "ha":
                meta["HA_Enabled"] = "True"
            if resolved_libs and _sse_health_token:
                meta["union_health_id"] = _sse_health_id

            server = await asyncio.to_thread(
                nova.create_server,
                conn,
                name=req.name,
                flavor_id=req.flavor_id,
                network_id=req.network_id,
                boot_volume_id=boot_volume_id,
                userdata=userdata,
                key_name=req.key_name or None,
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

            yield send_progress(ProgressStep.ATTACHING_VOLUME, 95, "볼륨 연결 중...")
            if upper_volume_id:
                await asyncio.to_thread(
                    conn.compute.create_volume_attachment,
                    server_id,
                    volume_id=upper_volume_id,
                )
            for nv in req.new_volumes or []:
                if not nv.name:
                    continue
                new_vol = await asyncio.to_thread(cinder.create_empty_volume, conn, nv.name, nv.size_gb)
                await asyncio.to_thread(
                    conn.compute.create_volume_attachment,
                    server_id,
                    volume_id=new_vol.id,
                )
            for vol_id in req.additional_volume_ids or []:
                await asyncio.to_thread(conn.compute.create_volume_attachment, server_id, volume_id=vol_id)
            yield send_progress(ProgressStep.ATTACHING_VOLUME, 100, "볼륨 연결 완료")

            if req.network_id:
                all_nets = await asyncio.to_thread(neutron.list_networks, conn)
                selected_net = next((n for n in all_nets if n.id == req.network_id), None)
                if selected_net and not selected_net.is_external:
                    ext_net = next((n for n in all_nets if n.is_external), None)
                    if ext_net:
                        yield send_progress(ProgressStep.FLOATING_IP_CREATING, 100, "Floating IP 할당 중...")
                        fip = await asyncio.to_thread(neutron.create_floating_ip, conn, ext_net.id)
                        floating_ip_id = fip.id
                        await asyncio.to_thread(neutron.associate_floating_ip, conn, fip.id, server_id)
                        yield send_progress(ProgressStep.FLOATING_IP_CREATING, 100, "Floating IP 할당 완료")

            try:
                await vm_cloud_init_library.record_history(user_id=token_info["user_id"], content=req.userdata)
            except Exception:
                logger.warning("cloud-init 실행 이력 저장 실패", extra={"user_id": token_info.get("user_id")})

            note = " (키페어 없음 — 콘솔 비밀번호 사용)" if not req.key_name else ""
            yield send_progress(
                ProgressStep.COMPLETED,
                100,
                f"인스턴스 생성 완료{note}",
                instance_id=server_id,
            )
            await rec(
                token_info,
                conn,
                resource_type="instance",
                action="instance.create",
                status="success",
                resource_id=server_id,
                resource_name=req.name,
            )

        except Exception as e:
            error_detail = str(e)
            logger.error("관리자 인스턴스 생성 실패, rollback 시작: %s", error_detail)

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

            yield send_progress(
                ProgressStep.FAILED,
                0,
                f"인스턴스 생성 실패: {error_detail}",
                error=error_detail,
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
            try:
                await asyncio.to_thread(conn.close)
            except Exception:
                pass

    return StreamingResponse(
        progress_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
