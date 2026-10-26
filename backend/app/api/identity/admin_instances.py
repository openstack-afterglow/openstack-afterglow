"""관리자용 cross-project 인스턴스 생성 엔드포인트."""

from __future__ import annotations

import asyncio
import logging
import secrets
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    import openstack

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from openstack.exceptions import HttpException, ResourceNotFound
from openstack.resource import Resource

from app.api.common.activity_recorder import rec
from app.api.compute.instance_metrics import _PrivateMetricsRoute
from app.api.deps import get_admin_os_conn, get_os_conn, get_token_info, require_admin
from app.config import get_settings
from app.models import compute as compute_models
from app.models.compute import (
    AdminPasswordRequest,
    AttachInterfaceRequest,
    AttachVolumeRequest,
    CreateInstanceRequest,
    InstanceInfo,
    StorageAttachRequest,
    UpdateSecurityGroupsRequest,
    UpdateVolumeAttachmentRequest,
)
from app.models.progress import ProgressMessage, ProgressStep
from app.models.storage import ExtendVolumeRequest
from app.services import cinder, cloudinit, keystone, manila, neutron, nova, vm_cloud_init_library
from app.services import instance_orchestration as instance_orch
from app.services.cache import invalidate
from app.services.cache import invalidation as cache_invalidation
from app.services.instance_names import ensure_unique_instance_name
from app.services.instance_password import (
    PASSWORD_METADATA_ERROR,
    PASSWORD_PROVISIONING_ERROR,
    WINDOWS_PASSWORD_CONFLICT,
    WINDOWS_PASSWORD_UNSUPPORTED,
    preflight_password,
)
from app.services.ssh_access import github_ssh_metadata
from app.services.volume_protection import register_volume_protection, rollback_volume_protection

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_admin)])
metrics_router = APIRouter(route_class=_PrivateMetricsRoute)


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
    conn._afterglow_authenticated_project_id = project_id
    conn._afterglow_token = ""
    conn._afterglow_user_id = user_id
    conn._afterglow_is_system_admin = True
    return conn


@router.get("/instances/flavors-for-project", dependencies=[Depends(require_admin)])
async def list_project_flavors_for_admin(
    project_id: str = Query(..., description="대상 프로젝트 ID"),
    count: int = Query(1, ge=1, le=100, description="동일 flavor 생성 수량"),
    availability_zone: str | None = None,
    capacity: Literal["create"] | None = Query(None, description="create: 단일 VM 생성용 같은 호스트 용량 포함"),
    token_info: dict = Depends(get_token_info),
):
    """Return target-project-visible flavors with target quota eligibility."""
    from app.services.flavor_eligibility import evaluate_project_flavors

    try:
        conn = await asyncio.to_thread(_make_admin_conn, project_id, token_info.get("user_id", ""))
        try:
            flavors = await asyncio.to_thread(nova.list_flavors, conn)
            return await evaluate_project_flavors(
                conn,
                project_id,
                flavors,
                count=count,
                check_capacity=capacity == "create",
                availability_zone=availability_zone,
                fresh_capacity=capacity == "create",
            )
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
    from app.api.compute.instances import _verify_github_ssh

    settings = get_settings()
    # Preserve the ordinary GitHub-only path without creating a target connection.
    if req.admin_pass is None:
        req = await _verify_github_ssh(req, token_info=token_info)

    try:
        conn = await asyncio.to_thread(_make_admin_conn, req.project_id, token_info.get("user_id", ""))
    except Exception:
        if req.admin_pass is not None:
            raise HTTPException(status_code=500, detail=PASSWORD_PROVISIONING_ERROR) from None
        raise

    async def close_preflight_connection():
        try:
            await asyncio.to_thread(conn.close)
        except Exception:
            if req.admin_pass is None:
                raise
            logger.warning("Admin password request connection close failed")

    try:
        sse_flavors = await asyncio.to_thread(nova.list_flavors, conn)
        sse_flavor = next((flavor for flavor in sse_flavors if flavor.id == req.flavor_id), None)
        if sse_flavor is None:
            raise HTTPException(status_code=400, detail="Invalid flavor ID")
    except Exception:
        await close_preflight_connection()
        if req.admin_pass is not None:
            raise HTTPException(status_code=400, detail=PASSWORD_PROVISIONING_ERROR) from None
        raise

    try:
        password_plan = await asyncio.to_thread(preflight_password, conn, req)
    except HTTPException as exc:
        await close_preflight_connection()
        if exc.detail not in (PASSWORD_METADATA_ERROR, WINDOWS_PASSWORD_CONFLICT, WINDOWS_PASSWORD_UNSUPPORTED):
            raise HTTPException(status_code=400, detail=PASSWORD_PROVISIONING_ERROR) from None
        raise
    except Exception:
        await close_preflight_connection()
        raise HTTPException(status_code=400, detail=PASSWORD_PROVISIONING_ERROR) from None

    try:
        if req.admin_pass is not None:
            req = await _verify_github_ssh(req, token_info=token_info)
        req = req.model_copy(update={"name": await asyncio.to_thread(ensure_unique_instance_name, conn, req.name)})
        if not req.network_id:
            req = req.model_copy(update={"network_id": await instance_orch.resolve_default_network(conn, settings)})
        compute_availability_zone, volume_availability_zone = await instance_orch.resolve_availability_zones(
            conn, req.availability_zone
        )
    except Exception as exc:
        await close_preflight_connection()
        if req.admin_pass is not None:
            raise HTTPException(
                status_code=exc.status_code if isinstance(exc, HTTPException) else 400,
                detail=PASSWORD_PROVISIONING_ERROR,
                headers=exc.headers if isinstance(exc, HTTPException) else None,
            ) from None
        if isinstance(exc, ValueError):
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        raise

    from app.services.flavor_eligibility import (
        FlavorEligibilityDenied,
        FlavorEligibilityUnavailable,
        admit_flavor,
        release_admission,
    )
    from app.services.gpu_quota import GpuQuotaDenied, GpuQuotaUnavailable

    try:
        # Password metadata and incompatible options have been rejected before
        # quota reservations or any boot-volume/server mutation.
        admission = await admit_flavor(conn, req.project_id, sse_flavor, availability_zone=compute_availability_zone)
    except (FlavorEligibilityDenied, GpuQuotaDenied) as exc:
        await close_preflight_connection()
        detail = PASSWORD_PROVISIONING_ERROR if req.admin_pass is not None else str(exc)
        raise HTTPException(status_code=409, detail=detail) from None
    except (FlavorEligibilityUnavailable, GpuQuotaUnavailable) as exc:
        await close_preflight_connection()
        detail = PASSWORD_PROVISIONING_ERROR if req.admin_pass is not None else str(exc)
        raise HTTPException(status_code=503, detail=detail) from None
    except HTTPException as exc:
        await close_preflight_connection()
        if req.admin_pass is not None:
            raise HTTPException(
                status_code=exc.status_code, detail=PASSWORD_PROVISIONING_ERROR, headers=exc.headers
            ) from None
        raise
    except Exception:
        await close_preflight_connection()
        if req.admin_pass is not None:
            raise HTTPException(status_code=400, detail=PASSWORD_PROVISIONING_ERROR) from None
        raise
    gpu_available = bool(admission.gpu_requested)

    async def progress_generator():
        import time

        boot_volume_id: str | None = None
        boot_volume_was_provided: bool = False
        server_id: str | None = None
        floating_ip_id: str | None = None
        protection_registration_id: str | None = None
        created_volume_ids: list[str] = []
        _start_time = time.monotonic()

        def send_progress(step: ProgressStep, progress: int, message: str, **extra):
            elapsed = round(time.monotonic() - _start_time, 1)
            msg = ProgressMessage(step=step, progress=progress, message=message, elapsed_seconds=elapsed, **extra)
            return f"data: {msg.model_dump_json()}\n\n"

        try:
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

            userdata = None
            if not password_plan.windows and gpu_available:
                yield send_progress(ProgressStep.USERDATA_GENERATING, 60, "cloud-init 생성 중...")
                userdata = cloudinit.generate_userdata(
                    libraries=[],
                    strategy="none",
                    file_storages=[],
                    upper_device="",
                    ceph_monitors=settings.ceph_monitors,
                    gpu_available=gpu_available,
                    github_username=req.github_username,
                )
                yield send_progress(ProgressStep.USERDATA_GENERATING, 65, "cloud-init 생성 완료")

            if not password_plan.windows:
                userdata = cloudinit.compose_userdata(userdata, req.userdata, req.github_username)

            yield send_progress(ProgressStep.SERVER_CREATING, 65, "Nova 서버 생성 중...")
            _sse_effective_sgs: list[str] | None = list(req.security_groups) if req.security_groups else None

            meta = github_ssh_metadata(req.github_username)
            server = await asyncio.to_thread(
                nova.create_server,
                conn,
                name=req.name,
                flavor_id=req.flavor_id,
                network_id=req.network_id,
                boot_volume_id=boot_volume_id,
                userdata=userdata,
                key_name=req.key_name or None,
                admin_pass=password_plan.nova_admin_pass(req.admin_pass),
                config_drive=password_plan.config_drive,
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
            for nv in req.new_volumes or []:
                if not nv.name:
                    continue
                new_vol = await asyncio.to_thread(cinder.create_empty_volume, conn, nv.name, nv.size_gb)
                created_volume_ids.append(new_vol.id)
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

            if req.auto_snapshot or req.auto_backup:
                protection_registration_id = secrets.token_hex(24)
                await register_volume_protection(
                    conn,
                    conn._afterglow_project_id,
                    boot_volume_id,
                    auto_snapshot=req.auto_snapshot,
                    auto_backup=req.auto_backup,
                    registration_id=protection_registration_id,
                )

            if not password_plan.windows:
                try:
                    await vm_cloud_init_library.record_history(user_id=token_info["user_id"], content=req.userdata)
                except Exception:
                    logger.warning("cloud-init 실행 이력 저장 실패", extra={"user_id": token_info.get("user_id")})

            # ACTIVE confirms Nova readiness, not Windows first-boot completion.
            note = " (키페어 없음 — 콘솔 비밀번호 사용)" if not req.key_name and not password_plan.windows else ""
            await rec(
                token_info,
                conn,
                resource_type="instance",
                action="instance.create",
                status="success",
                resource_id=server_id,
                resource_name=req.name,
            )
            yield send_progress(
                ProgressStep.COMPLETED,
                100,
                f"인스턴스 생성 완료{note}",
                instance_id=server_id,
            )

        except Exception as e:
            raw_error = str(e)
            error_detail = PASSWORD_PROVISIONING_ERROR if req.admin_pass is not None else raw_error
            logger.error("관리자 인스턴스 생성 실패, rollback 시작: %s", error_detail)

            import re as _re

            if not server_id:
                _m = _re.search(r"Server:([0-9a-f-]{36})", raw_error)
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

            if req.admin_pass is not None:
                error_detail = PASSWORD_PROVISIONING_ERROR

            if protection_registration_id is not None:
                try:
                    await rollback_volume_protection(
                        conn._afterglow_project_id, boot_volume_id, protection_registration_id
                    )
                except Exception:
                    logger.error("Volume protection policy compensation failed")
            await instance_orch.rollback_instance(
                conn,
                server_id,
                boot_volume_id if not boot_volume_was_provided else None,
                None,
                [],
                [],
                floating_ip_id,
                safe_error_message=PASSWORD_PROVISIONING_ERROR if req.admin_pass is not None else None,
                additional_volume_ids=created_volume_ids,
            )

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
        finally:
            try:
                await release_admission(admission)
            except Exception:
                logger.warning("GPU quota reservation release failed", exc_info=req.admin_pass is None)
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


# These routes never rescope the fixed executor or mutate its logical caller metadata.
def _field(resource, key, default=None):
    if isinstance(resource, Resource):
        return getattr(resource, key, default)
    return resource.get(key, default) if isinstance(resource, dict) else getattr(resource, key, default)


def _exact(resource, resource_id: str, project_id: str | None = None):
    if not isinstance(resource_id, str) or not resource_id or _field(resource, "id") != resource_id:
        raise HTTPException(status_code=409, detail="리소스 식별자가 일치하지 않습니다")
    owners = [_field(resource, key) for key in ("project_id", "tenant_id")]
    owners = [owner for owner in owners if owner is not None and owner != ""]
    if not owners or any(not isinstance(owner, str) or not owner for owner in owners):
        raise HTTPException(status_code=409, detail="리소스 소유 프로젝트를 확인할 수 없습니다")
    if len(set(owners)) != 1 or (project_id is not None and owners[0] != project_id):
        raise HTTPException(status_code=409, detail="리소스 소유 프로젝트가 일치하지 않습니다")
    return resource


def _server(conn, instance_id: str):
    try:
        raw = conn.compute.get_server(instance_id)
    except ResourceNotFound as exc:
        raise HTTPException(status_code=404, detail="인스턴스를 찾을 수 없습니다") from exc
    except HttpException as exc:
        raise HTTPException(status_code=403 if exc.status_code == 403 else 502, detail="인스턴스 조회 실패") from exc
    _exact(raw, instance_id)
    return nova._server_to_info(raw)


def _ports(conn, server):
    ports = list(conn.network.ports(device_id=server.id, project_id=server.project_id))
    for port in ports:
        _exact(port, _field(port, "id"), server.project_id)
        if _field(port, "device_id") != server.id:
            raise HTTPException(status_code=409, detail="포트가 인스턴스에 연결되어 있지 않습니다")
    return ports


def _port_info(port):
    return {
        "id": port.id,
        "network_id": port.network_id,
        "mac_address": port.mac_address,
        "fixed_ips": port.fixed_ips or [],
        "security_group_ids": port.security_group_ids or [],
        "status": port.status,
    }


def _attached_volumes(conn, server):
    result = []
    for attachment in nova.list_volume_attachments(conn, server.id):
        if attachment.get("server_id") != server.id:
            raise HTTPException(status_code=409, detail="볼륨 연결의 인스턴스가 일치하지 않습니다")
        volume_id = attachment.get("volume_id")
        volume = _exact(conn.block_storage.get_volume(volume_id), volume_id, server.project_id)
        if not any(_field(item, "server_id") == server.id for item in (_field(volume, "attachments") or [])):
            raise HTTPException(status_code=409, detail="볼륨이 인스턴스에 연결되어 있지 않습니다")
        result.append({**attachment, "name": volume.name, "size": volume.size, "status": volume.status})
    return result


def _groups(conn, server, ports):
    groups = list(conn.network.security_groups(project_id=server.project_id))
    for group in groups:
        _exact(group, _field(group, "id"), server.project_id)
    by_id = {group.id: group for group in groups}
    for port in ports:
        for group_id in port.security_group_ids or []:
            if group_id not in by_id:
                by_id[group_id] = _exact(conn.network.get_security_group(group_id), group_id, server.project_id)
    return [neutron._sg_to_dict(group) for group in by_id.values()]


def _floating_ips(conn, server, ports):
    result = []
    for port in ports:
        for floating_ip in conn.network.ips(port_id=port.id, project_id=server.project_id):
            _exact(floating_ip, _field(floating_ip, "id"), server.project_id)
            if floating_ip.port_id != port.id:
                raise HTTPException(status_code=409, detail="Floating IP의 포트가 일치하지 않습니다")
            result.append(neutron._fip_to_info(floating_ip))
    return result


async def _invalidate_detail(server):
    for pattern in (
        f"afterglow:nova:{server.project_id}:*",
        f"afterglow:neutron:{server.project_id}:*",
        f"afterglow:cinder:{server.project_id}:*",
        "afterglow:admin:instances*",
    ):
        await invalidate(pattern)
    for service in ("nova", "neutron", "cinder"):
        await cache_invalidation.invalidate_mutation_count(service, server.project_id)


async def _audit_instance_mutation(
    request: Request,
    instance_id: str,
    conn=Depends(get_admin_os_conn),
    token_info: dict = Depends(require_admin),
):
    """Record actor workspace and native target separately, without request bodies/secrets."""
    server = None
    status = "failed"
    try:
        try:
            server = await asyncio.to_thread(_server, conn, instance_id)
        except HTTPException as exc:
            if exc.status_code != 404 or request.scope["route"].name != "delete_admin_instance":
                raise
            # The exact delete handler alone can resume a durable catalog
            # cleanup; it must independently prove native server absence.
        yield
        status = "success"
    finally:
        await rec(
            token_info,
            conn,
            resource_type="instance",
            action=f"admin.{request.scope['route'].name}",
            status=status,
            resource_id=instance_id,
            resource_name=server.name if server else None,
            extra={"target_project_id": server.project_id if server else None},
        )


@router.get("/instances/{instance_id}", response_model=InstanceInfo, dependencies=[Depends(require_admin)])
async def get_admin_instance(instance_id: str, conn=Depends(get_admin_os_conn)):
    from app.api.compute.instances import _resolve_instance_detail

    def fetch():
        server = _server(conn, instance_id)
        # The shared resolver reads boot-volume metadata: fence it before resolving.
        _attached_volumes(conn, server)
        return _resolve_instance_detail(server, conn)

    return await asyncio.to_thread(fetch)


@router.get("/instances/{instance_id}/interfaces", dependencies=[Depends(require_admin)])
async def get_admin_instance_interfaces(instance_id: str, conn=Depends(get_admin_os_conn)):
    return await asyncio.to_thread(lambda: [_port_info(port) for port in _ports(conn, _server(conn, instance_id))])


@router.get("/instances/{instance_id}/volumes", dependencies=[Depends(require_admin)])
async def get_admin_instance_volumes(instance_id: str, conn=Depends(get_admin_os_conn)):
    return await asyncio.to_thread(lambda: _attached_volumes(conn, _server(conn, instance_id)))


@router.get("/instances/{instance_id}/available-volumes", dependencies=[Depends(require_admin)])
async def get_admin_instance_available_volumes(instance_id: str, conn=Depends(get_admin_os_conn)):
    def fetch():
        server = _server(conn, instance_id)
        volumes = list(conn.block_storage.volumes(details=True, all_projects=True, project_id=server.project_id))
        for volume in volumes:
            _exact(volume, _field(volume, "id"), server.project_id)
        return [cinder._vol_to_info(volume) for volume in volumes if volume.status == "available"]

    return await asyncio.to_thread(fetch)


@router.get("/instances/{instance_id}/security-groups", dependencies=[Depends(require_admin)])
async def get_admin_instance_security_groups(instance_id: str, conn=Depends(get_admin_os_conn)):
    def fetch():
        server = _server(conn, instance_id)
        ports = _ports(conn, server)
        return {"ports": [_port_info(port) for port in ports], "security_groups": _groups(conn, server, ports)}

    return await asyncio.to_thread(fetch)


@router.get("/instances/{instance_id}/floating-ips", dependencies=[Depends(require_admin)])
async def get_admin_instance_floating_ips(instance_id: str, conn=Depends(get_admin_os_conn)):
    def fetch():
        server = _server(conn, instance_id)
        return _floating_ips(conn, server, _ports(conn, server))

    return await asyncio.to_thread(fetch)


@router.get("/instances/{instance_id}/networks", dependencies=[Depends(require_admin)])
async def get_admin_instance_networks(instance_id: str, conn=Depends(get_admin_os_conn)):
    def fetch():
        server = _server(conn, instance_id)
        ports = _ports(conn, server)
        networks = {network.id: network for network in conn.network.networks(project_id=server.project_id)}
        for network in networks.values():
            _exact(network, network.id, server.project_id)
        for port in ports:
            if port.network_id not in networks:
                network = conn.network.get_network(port.network_id)
                _exact(network, port.network_id)
                # A native shared network may own a tenant's positively owned port.
                if network.project_id != server.project_id and _field(network, "is_shared") is not True:
                    raise HTTPException(status_code=409, detail="연결된 네트워크의 소유권을 확인할 수 없습니다")
                networks[network.id] = network
        return [neutron._net_to_info(network) for network in networks.values()]

    return await asyncio.to_thread(fetch)


@router.get("/instances/{instance_id}/owner", dependencies=[Depends(require_admin)])
async def get_admin_instance_owner(instance_id: str, conn=Depends(get_admin_os_conn)):
    def fetch():
        server = _server(conn, instance_id)
        if not server.user_id:
            return {"display": "-"}
        user = keystone.get_user(conn, server.user_id)
        if user.get("id") != server.user_id:
            raise HTTPException(status_code=409, detail="인스턴스 생성자 식별자가 일치하지 않습니다")
        name, email = user.get("name") or server.user_id, user.get("email") or ""
        return {"display": f"{name}({email})" if email else name, "name": name, "email": email}

    return await asyncio.to_thread(fetch)


@router.get("/instances/{instance_id}/console", dependencies=[Depends(require_admin)])
async def get_admin_instance_console(instance_id: str, conn=Depends(get_admin_os_conn)):
    await asyncio.to_thread(_server, conn, instance_id)
    return {"url": await asyncio.to_thread(nova.get_console_url, conn, instance_id)}


@router.get("/instances/{instance_id}/log", dependencies=[Depends(require_admin)])
async def get_admin_instance_log(
    instance_id: str, length: int = Query(100, ge=0, le=100000), conn=Depends(get_admin_os_conn)
):
    await asyncio.to_thread(_server, conn, instance_id)
    return {"output": await asyncio.to_thread(nova.get_console_output, conn, instance_id, length)}


@router.get("/instances/{instance_id}/resize-flavors", dependencies=[Depends(require_admin)])
async def get_admin_instance_resize_flavors(instance_id: str, conn=Depends(get_admin_os_conn)):
    from app.api.compute.instances import _resize_current_flavor, _resize_target_blockers
    from app.services.flavor_eligibility import evaluate_project_flavors, is_flavor_frontend_visible

    server = await asyncio.to_thread(_server, conn, instance_id)
    if server.status not in {"ACTIVE", "SHUTOFF"}:
        raise HTTPException(status_code=409, detail="현재 상태에서는 리사이즈할 수 없습니다")
    flavors = await asyncio.to_thread(nova._list_flavors, conn, project_id=server.project_id)
    current = _resize_current_flavor(server, flavors)
    evaluated = await evaluate_project_flavors(
        conn,
        server.project_id,
        [flavor for flavor in flavors if is_flavor_frontend_visible(flavor)],
        current_flavor=current,
    )
    for flavor in evaluated:
        blockers = _resize_target_blockers(flavor, current, image_backed=bool(server.image_id))
        if blockers:
            flavor.eligibility = flavor.eligibility.model_copy(
                update={"selectable": False, "blockers": [*flavor.eligibility.blockers, *blockers]}
            )
    return evaluated


@router.get("/instances/{instance_id}/admin-password/precheck", dependencies=[Depends(require_admin)])
async def get_admin_instance_password_precheck(
    instance_id: str, conn=Depends(get_admin_os_conn), token_info: dict = Depends(require_admin)
):
    from app.api.compute.instances import precheck_admin_password

    server = await asyncio.to_thread(_server, conn, instance_id)
    await asyncio.to_thread(_attached_volumes, conn, server)
    return await precheck_admin_password(instance_id, token_info, conn)


@router.post(
    "/instances/{instance_id}/admin-password", status_code=204, dependencies=[Depends(_audit_instance_mutation)]
)
async def set_admin_instance_password(
    instance_id: str,
    body: AdminPasswordRequest,
    conn=Depends(get_admin_os_conn),
    token_info: dict = Depends(require_admin),
):
    from app.api.compute.instances import set_admin_password

    server = await asyncio.to_thread(_server, conn, instance_id)
    await asyncio.to_thread(_attached_volumes, conn, server)
    await set_admin_password(instance_id, body, token_info, conn)


@metrics_router.get("/instances/{instance_id}/metrics-batch", dependencies=[Depends(require_admin)])
async def get_admin_instance_metrics(
    instance_id: str,
    response: Response,
    metrics: str = Query(...),
    range: Literal["15m", "1h", "6h", "24h", "7d"] = "1h",
    conn=Depends(get_admin_os_conn),
    caller_conn=Depends(get_os_conn),
):
    from app.api.compute.instance_metrics import _metric_keys, instance_metrics_batch

    response.headers["Cache-Control"] = "no-store"
    keys = _metric_keys(metrics)
    server = await asyncio.to_thread(_server, conn, instance_id)
    return await instance_metrics_batch(server, keys, range, caller_conn)


@metrics_router.get("/instances/{instance_id}/metrics-summary", dependencies=[Depends(require_admin)])
async def get_admin_instance_metrics_summary(
    instance_id: str,
    response: Response,
    range: Literal["15m", "1h", "6h", "24h", "7d"] = "7d",
    conn=Depends(get_admin_os_conn),
    caller_conn=Depends(get_os_conn),
):
    from app.api.compute.instance_metrics import instance_metrics_summary

    response.headers["Cache-Control"] = "no-store"
    server = await asyncio.to_thread(_server, conn, instance_id)
    return await instance_metrics_summary(server, range, caller_conn, flavor_conn=conn)


@router.post("/instances/{instance_id}/start", status_code=204, dependencies=[Depends(_audit_instance_mutation)])
async def start_admin_instance(instance_id: str, conn=Depends(get_admin_os_conn)):
    await _admin_action(conn, instance_id, "start")


@router.post("/instances/{instance_id}/stop", status_code=204, dependencies=[Depends(_audit_instance_mutation)])
async def stop_admin_instance(instance_id: str, conn=Depends(get_admin_os_conn)):
    await _admin_action(conn, instance_id, "stop")


@router.post("/instances/{instance_id}/reboot", status_code=204, dependencies=[Depends(_audit_instance_mutation)])
async def reboot_admin_instance(instance_id: str, conn=Depends(get_admin_os_conn)):
    await _admin_action(conn, instance_id, "reboot")


@router.post("/instances/{instance_id}/shelve", status_code=204, dependencies=[Depends(_audit_instance_mutation)])
async def shelve_admin_instance(instance_id: str, conn=Depends(get_admin_os_conn)):
    await _admin_action(conn, instance_id, "shelve")


@router.post("/instances/{instance_id}/unshelve", status_code=204, dependencies=[Depends(_audit_instance_mutation)])
async def unshelve_admin_instance(instance_id: str, conn=Depends(get_admin_os_conn)):
    await _admin_action(conn, instance_id, "unshelve")


async def _admin_action(conn, instance_id, action):
    server = await asyncio.to_thread(_server, conn, instance_id)
    await asyncio.to_thread(getattr(nova, f"{action}_server"), conn, instance_id)
    await _invalidate_detail(server)


@router.post("/instances/{instance_id}/volumes", status_code=201, dependencies=[Depends(_audit_instance_mutation)])
async def attach_admin_instance_volume(instance_id: str, body: AttachVolumeRequest, conn=Depends(get_admin_os_conn)):
    server = await asyncio.to_thread(_server, conn, instance_id)
    volume = await asyncio.to_thread(conn.block_storage.get_volume, body.volume_id)
    _exact(volume, body.volume_id, server.project_id)
    result = await asyncio.to_thread(nova.attach_volume, conn, instance_id, body.volume_id)
    await _invalidate_detail(server)
    return result


async def _attached_volume(conn, instance_id, volume_id):
    server = await asyncio.to_thread(_server, conn, instance_id)
    attachments = await asyncio.to_thread(_attached_volumes, conn, server)
    if not any(item["volume_id"] == volume_id for item in attachments):
        raise HTTPException(status_code=409, detail="인스턴스에 연결된 볼륨이 아닙니다")
    return server


@router.delete(
    "/instances/{instance_id}/volumes/{volume_id}", status_code=204, dependencies=[Depends(_audit_instance_mutation)]
)
async def detach_admin_instance_volume(instance_id: str, volume_id: str, conn=Depends(get_admin_os_conn)):
    server = await _attached_volume(conn, instance_id, volume_id)
    await asyncio.to_thread(nova.detach_volume, conn, instance_id, volume_id)
    await _invalidate_detail(server)


@router.patch(
    "/instances/{instance_id}/volumes/{volume_id}", status_code=204, dependencies=[Depends(_audit_instance_mutation)]
)
async def update_admin_instance_volume(
    instance_id: str, volume_id: str, body: UpdateVolumeAttachmentRequest, conn=Depends(get_admin_os_conn)
):
    server = await _attached_volume(conn, instance_id, volume_id)
    await asyncio.to_thread(
        nova.update_volume_attachment_delete_flag, conn, instance_id, volume_id, body.delete_on_termination
    )
    await _invalidate_detail(server)


@router.post("/instances/{instance_id}/interfaces", status_code=201, dependencies=[Depends(_audit_instance_mutation)])
async def attach_admin_instance_interface(
    instance_id: str, body: AttachInterfaceRequest, conn=Depends(get_admin_os_conn)
):
    server = await asyncio.to_thread(_server, conn, instance_id)
    network = await asyncio.to_thread(conn.network.get_network, body.net_id)
    _exact(network, body.net_id)
    if network.project_id != server.project_id and _field(network, "is_shared") is not True:
        raise HTTPException(status_code=409, detail="대상 프로젝트의 네트워크가 아닙니다")
    result = await asyncio.to_thread(nova.attach_interface, conn, instance_id, body.net_id)
    await _invalidate_detail(server)
    return result


async def _attached_port(conn, instance_id, port_id):
    server = await asyncio.to_thread(_server, conn, instance_id)
    ports = await asyncio.to_thread(_ports, conn, server)
    port = next((port for port in ports if port.id == port_id), None)
    if port is None:
        raise HTTPException(status_code=409, detail="인스턴스에 연결된 포트가 아닙니다")
    return server, port


@router.delete(
    "/instances/{instance_id}/interfaces/{port_id}", status_code=204, dependencies=[Depends(_audit_instance_mutation)]
)
async def detach_admin_instance_interface(instance_id: str, port_id: str, conn=Depends(get_admin_os_conn)):
    server, _ = await _attached_port(conn, instance_id, port_id)
    await asyncio.to_thread(nova.detach_interface, conn, instance_id, port_id)
    await _invalidate_detail(server)


@router.post(
    "/instances/{instance_id}/ports/{port_id}/security-groups", dependencies=[Depends(_audit_instance_mutation)]
)
async def update_admin_instance_groups(
    instance_id: str, port_id: str, body: UpdateSecurityGroupsRequest, conn=Depends(get_admin_os_conn)
):
    server, _ = await _attached_port(conn, instance_id, port_id)
    for group_id in body.security_group_ids:
        group = await asyncio.to_thread(conn.network.get_security_group, group_id)
        _exact(group, group_id, server.project_id)
    result = await asyncio.to_thread(neutron.update_port_security_groups, conn, port_id, body.security_group_ids)
    await _invalidate_detail(server)
    return result


@router.post("/instances/{instance_id}/floating-ip", dependencies=[Depends(_audit_instance_mutation)])
async def assign_admin_instance_floating_ip(
    instance_id: str, port_id: str = Query(...), conn=Depends(get_admin_os_conn)
):
    server, port = await _attached_port(conn, instance_id, port_id)
    subnet_ids = {item["subnet_id"] for item in (port.fixed_ips or []) if item.get("subnet_id")}
    for subnet_id in subnet_ids:
        subnet = await asyncio.to_thread(conn.network.get_subnet, subnet_id)
        _exact(subnet, subnet_id)
        if _field(subnet, "network_id") != port.network_id:
            raise HTTPException(status_code=409, detail="포트 서브넷의 네트워크가 일치하지 않습니다")
    external_id = await asyncio.to_thread(neutron.find_external_network_for_subnets, conn, subnet_ids)
    if not external_id:
        raise HTTPException(status_code=422, detail="외부 네트워크 연결을 확인할 수 없습니다")
    floating_ip = await asyncio.to_thread(
        conn.network.create_ip, floating_network_id=external_id, project_id=server.project_id, port_id=port.id
    )
    _exact(floating_ip, _field(floating_ip, "id"), server.project_id)
    if floating_ip.port_id != port.id:
        raise HTTPException(status_code=409, detail="Floating IP의 포트가 일치하지 않습니다")
    await _invalidate_detail(server)
    return neutron._fip_to_info(floating_ip)


@router.delete(
    "/instances/{instance_id}/floating-ips/{floating_ip_id}",
    status_code=204,
    dependencies=[Depends(_audit_instance_mutation)],
)
async def release_admin_instance_floating_ip(instance_id: str, floating_ip_id: str, conn=Depends(get_admin_os_conn)):
    server = await asyncio.to_thread(_server, conn, instance_id)
    ports = await asyncio.to_thread(_ports, conn, server)
    floating_ip = await asyncio.to_thread(conn.network.get_ip, floating_ip_id)
    _exact(floating_ip, floating_ip_id, server.project_id)
    if floating_ip.port_id not in {port.id for port in ports}:
        raise HTTPException(status_code=409, detail="인스턴스에 연결된 Floating IP가 아닙니다")
    await asyncio.to_thread(conn.network.delete_ip, floating_ip_id, ignore_missing=False)
    await _invalidate_detail(server)


async def _storage_context(conn, instance_id, share_id=None):
    from app.api.compute import instances

    server = await asyncio.to_thread(_server, conn, instance_id)
    grants = instances._storage_grants(server)
    share_ids = {share_id} if share_id else set(grants)
    if not share_id:
        share_ids.update(
            item for item in instances._data_share_metadata_value(server).split(",") if item and item != "none"
        )
    for current_id in share_ids:
        share = await asyncio.to_thread(manila.get_file_storage, conn, current_id)
        _exact(share, current_id, server.project_id)
        if share.share_network_id:
            body = await asyncio.to_thread(manila.get_client(conn).get, f"share-networks/{share.share_network_id}")
            network = body.get("share_network", body)
            _exact(network, share.share_network_id, server.project_id)
    return server


@router.get("/instances/{instance_id}/storage-attachments", dependencies=[Depends(require_admin)])
async def get_admin_instance_storage(
    instance_id: str, conn=Depends(get_admin_os_conn), token_info: dict = Depends(require_admin)
):
    from app.api.compute.instances import list_storage_attachments

    await _storage_context(conn, instance_id)
    return await list_storage_attachments(instance_id, conn, token_info)


@router.get("/instances/{instance_id}/file-storage", dependencies=[Depends(require_admin)])
async def get_admin_instance_storage_catalog(instance_id: str, conn=Depends(get_admin_os_conn)):
    server = await asyncio.to_thread(_server, conn, instance_id)
    shares = await asyncio.to_thread(manila.list_file_storages, conn, all_tenants=True)
    shares = [share for share in shares if share.project_id == server.project_id]
    for share in shares:
        _exact(share, share.id, server.project_id)
    return shares


@router.post("/instances/{instance_id}/storage-attachments", dependencies=[Depends(_audit_instance_mutation)])
async def attach_admin_instance_storage(
    instance_id: str,
    req: StorageAttachRequest,
    response: Response,
    conn=Depends(get_admin_os_conn),
    token_info: dict = Depends(require_admin),
):
    from app.api.compute.instances import attach_storage

    server = await _storage_context(conn, instance_id, req.file_storage_id)
    result = await attach_storage(instance_id, req, response, conn, token_info)
    await _invalidate_detail(server)
    # Administrator inspection must not disclose another project's CephX credential.
    return {key: value for key, value in result.items() if key not in {"secret", "access_key"}}


@router.post(
    "/instances/{instance_id}/storage-attachments/{file_storage_id}/connection-info",
    dependencies=[Depends(_audit_instance_mutation)],
)
async def get_admin_instance_storage_connection(
    instance_id: str,
    file_storage_id: str,
    response: Response,
    conn=Depends(get_admin_os_conn),
    token_info: dict = Depends(require_admin),
):
    from app.api.compute.instances import storage_connection_info

    await _storage_context(conn, instance_id, file_storage_id)
    result = await storage_connection_info(instance_id, file_storage_id, response, conn, token_info)
    return {key: value for key, value in result.items() if key not in {"secret", "access_key"}}


@router.delete(
    "/instances/{instance_id}/storage-attachments/{file_storage_id}",
    status_code=204,
    dependencies=[Depends(_audit_instance_mutation)],
)
async def detach_admin_instance_storage(
    instance_id: str, file_storage_id: str, conn=Depends(get_admin_os_conn), token_info: dict = Depends(require_admin)
):
    from app.api.compute.instances import detach_storage

    server = await _storage_context(conn, instance_id, file_storage_id)
    await detach_storage(instance_id, file_storage_id, conn, token_info)
    await _invalidate_detail(server)


@router.delete("/instances/{instance_id}", status_code=204, dependencies=[Depends(_audit_instance_mutation)])
async def delete_admin_instance(
    instance_id: str, conn=Depends(get_admin_os_conn), token_info: dict = Depends(require_admin)
):
    from app.api.compute.instances import _bulk_delete_one
    from app.services.layer_consume_resources import lookup_for_server

    try:
        server = await _storage_context(conn, instance_id)
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
        from app.services.palimpsest_catalog_cleanup import recover_missing_instance

        if await recover_missing_instance(conn, instance_id, token_info):
            return
        raise
    block_ids = await lookup_for_server(
        instance_id, server.project_id, require_block=(server.metadata or {}).get("layer_transport") == "block"
    )
    if block_ids:
        raise HTTPException(
            status_code=409, detail="블록 계층 인스턴스 삭제에는 소유 프로젝트의 정리 작업이 필요합니다"
        )
    await asyncio.to_thread(_attached_volumes, conn, server)
    ports = await asyncio.to_thread(_ports, conn, server)
    await asyncio.to_thread(_floating_ips, conn, server, ports)
    if server.union_upper_volume_id:
        volume = await asyncio.to_thread(conn.block_storage.get_volume, server.union_upper_volume_id)
        _exact(volume, server.union_upper_volume_id, server.project_id)
    for share_id in server.union_share_ids:
        share = await asyncio.to_thread(manila.get_file_storage, conn, share_id)
        _exact(share, share_id, server.project_id)
    await _bulk_delete_one(conn, token_info, server, instance_id, server.project_id)
    await _invalidate_detail(server)


@router.get("/instances/{instance_id}/volumes/{volume_id}", dependencies=[Depends(require_admin)])
async def get_admin_instance_volume(instance_id: str, volume_id: str, conn=Depends(get_admin_os_conn)):
    server = await _attached_volume(conn, instance_id, volume_id)
    volume = await asyncio.to_thread(conn.block_storage.get_volume, volume_id)
    _exact(volume, volume_id, server.project_id)
    return cinder._vol_to_info(volume)


@router.post("/instances/{instance_id}/volumes/{volume_id}/extend", dependencies=[Depends(_audit_instance_mutation)])
async def extend_admin_instance_volume(
    instance_id: str, volume_id: str, body: ExtendVolumeRequest, conn=Depends(get_admin_os_conn)
):
    server = await _attached_volume(conn, instance_id, volume_id)
    try:
        result = await asyncio.to_thread(
            cinder._extend_volume_for_project, conn, volume_id, body.new_size, server.project_id
        )
    except cinder.VolumeExtensionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    await _invalidate_detail(server)
    return result


router.include_router(metrics_router)
