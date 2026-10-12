"""
인스턴스 오케스트레이션 엔드포인트.

생성 순서:
  1. 선택한 데이터 스토리지의 Manila access rule
  2. Cinder 부트 볼륨
  3. GPU 및 데이터 마운트용 cloud-init userdata
  4. Nova 서버 생성

실패 시 역순 rollback.
"""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Literal
from uuid import UUID

if TYPE_CHECKING:
    import openstack

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from openstack.exceptions import ConflictException, HttpException
from pydantic import BaseModel, field_validator

from app.api.common.activity_recorder import rec
from app.api.common.owner_check import assert_instance_owner, assert_project_resource_owner
from app.api.deps import (
    CacheMode,
    cache_mode,
    get_os_conn,
    get_os_conn_write,
    get_token_info,
    require_project_write,
)
from app.config import get_settings
from app.models.compute import (
    AdminPasswordPrecheck,
    AdminPasswordRequest,
    AttachInterfaceRequest,
    AttachVolumeRequest,
    CloudInitSnippetLibrary,
    CreateCloudInitPresetRequest,
    CreateInstanceRequest,
    FlavorInfo,
    FlavorQuotaBlocker,
    GitHubSshLookupRequest,
    GitHubSshProfile,
    GitHubSshUserHistory,
    InstanceInfo,
    StorageAttachRequest,
    UpdateSecurityGroupsRequest,
    UpdateVolumeAttachmentRequest,
)
from app.models.progress import ProgressMessage, ProgressStep
from app.rate_limit import limiter
from app.services import cinder, cloudinit, github_ssh, glance, keystone, manila, neutron, nova, vm_cloud_init_library
from app.services import instance_orchestration as instance_orch
from app.services.cache import (
    cached_call,
    invalidate,
    ttl_fast,
    ttl_normal,
    ttl_slow,
    ttl_static,
)
from app.services.cache import invalidation as cache_invalidation
from app.services.instance_password import PASSWORD_PROVISIONING_ERROR, preflight_password
from app.services.resource_policies import ResourcePolicyValidationError
from app.services.resource_policy_store import ResourcePolicyStorageUnavailable
from app.services.ssh_access import github_ssh_metadata

logger = logging.getLogger(__name__)


async def _record_cloud_init_history_best_effort(token_info: dict, userdata: str | None) -> None:
    try:
        await vm_cloud_init_library.record_history(user_id=token_info["user_id"], content=userdata)
    except Exception:
        logger.warning("cloud-init 실행 이력 저장 실패", extra={"user_id": token_info.get("user_id")})


def _github_http_exception(exc: Exception, *, not_found_status: int = 422) -> HTTPException:
    if isinstance(exc, github_ssh.GitHubSshRateLimited):
        headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after is not None else None
        return HTTPException(status_code=429, detail=str(exc), headers=headers)
    if isinstance(exc, github_ssh.GitHubSshNotFound):
        return HTTPException(status_code=not_found_status, detail=str(exc))
    if isinstance(exc, github_ssh.GitHubSshInvalid):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=503, detail=str(exc))


async def _verify_github_ssh(req: CreateInstanceRequest, *, token_info: dict) -> CreateInstanceRequest:
    if not req.github_username:
        return req
    try:
        profile = await github_ssh.verify_and_record(
            user_id=token_info["user_id"],
            username=req.github_username,
        )
    except (github_ssh.GitHubSshInvalid, github_ssh.GitHubSshUnavailable) as exc:
        raise _github_http_exception(exc) from exc
    return req.model_copy(update={"github_username": str(profile["login"])})


router = APIRouter()

_DATA_SHARE_METADATA_KEY = "afterglow_data_share_ids"
_LEGACY_DATA_SHARE_METADATA_KEY = "union_data_share_ids"


def _data_share_metadata_value(server) -> str:
    """Read the current data-mount metadata key with legacy VM fallback."""
    metadata = server.metadata or {}
    return metadata.get(_DATA_SHARE_METADATA_KEY, metadata.get(_LEGACY_DATA_SHARE_METADATA_KEY, ""))


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
    token_info: dict = Depends(require_project_write),
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
    token_info: dict = Depends(require_project_write),
):
    try:
        await vm_cloud_init_library.delete_snippet(user_id=token_info["user_id"], snippet_id=snippet_id)
        await invalidate(f"afterglow:vm_cloud_init:{token_info['user_id']}")
        await cache_invalidation.invalidate_mutation_count("nova", token_info["project_id"])
    except vm_cloud_init_library.CloudInitSnippetNotFound as exc:
        raise HTTPException(status_code=404, detail="cloud-init 항목을 찾을 수 없습니다") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/github-users/history", response_model=list[GitHubSshUserHistory])
async def list_github_ssh_history(token_info: dict = Depends(get_token_info)):
    try:
        return await github_ssh.list_history(user_id=token_info["user_id"])
    except github_ssh.GitHubSshUnavailable as exc:
        raise _github_http_exception(exc) from exc


@router.post("/github-users/lookup", response_model=GitHubSshProfile)
@limiter.limit("10/minute")
async def lookup_github_ssh_user(
    request: Request,
    req: GitHubSshLookupRequest,
    token_info: dict = Depends(require_project_write),
):
    try:
        return await github_ssh.verify_and_record(user_id=token_info["user_id"], username=req.username)
    except (github_ssh.GitHubSshInvalid, github_ssh.GitHubSshUnavailable) as exc:
        raise _github_http_exception(exc, not_found_status=404) from exc


def _resolve_instance_detail(server, conn) -> dict:
    detail = _resolve_names([server], conn)[0]
    try:
        boot_metadata = nova.get_server_image_meta(conn, server.id)
    except Exception:
        boot_metadata = {}
    detail["os_type"] = boot_metadata.get("os_type")
    if not detail.get("image_id"):
        detail["image_name"] = boot_metadata.get("image_name") or "볼륨에서 부팅"
    return detail


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
            lambda: _resolve_instance_detail(server, conn),
        )
    except Exception:
        raise HTTPException(status_code=404, detail="인스턴스를 찾을 수 없습니다")


class InstanceResizeRequest(BaseModel):
    flavor_id: str


_RESIZABLE_STATUSES = frozenset({"ACTIVE", "SHUTOFF"})


async def _owned_resize_server(conn, token_info: dict, instance_id: str):
    try:
        server = await asyncio.to_thread(nova.get_server, conn, instance_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="인스턴스를 찾을 수 없습니다") from exc
    assert_project_resource_owner(server, conn, token_info, not_found_detail="인스턴스를 찾을 수 없습니다")
    return server


def _resize_current_flavor(server, flavors: list[FlavorInfo]) -> FlavorInfo:
    current = next((flavor for flavor in flavors if flavor.id == server.flavor_id), None)
    if current is None and not server.flavor_id and server.flavor_name:
        matches = [flavor for flavor in flavors if flavor.name == server.flavor_name]
        current = matches[0] if len(matches) == 1 else None
    if current is None:
        raise HTTPException(status_code=409, detail="현재 플레이버를 확인할 수 없습니다")
    return current


def _resize_target_blockers(target: FlavorInfo, current: FlavorInfo, *, image_backed: bool) -> list[FlavorQuotaBlocker]:
    blockers = []
    if target.id == current.id:
        blockers.append(FlavorQuotaBlocker(code="same_flavor"))
    if image_backed and target.disk < current.disk:
        blockers.append(FlavorQuotaBlocker(code="disk_shrink"))
    return blockers


async def _invalidate_resized_instance(project_id: str, instance_id: str) -> None:
    await invalidate(f"afterglow:nova:{project_id}:instance:{instance_id}")
    await invalidate(f"afterglow:nova:{project_id}:instances")
    await cache_invalidation.invalidate_mutation_count("nova", project_id)


@router.get("/{instance_id}/resize-flavors", response_model=list[FlavorInfo])
async def list_instance_resize_flavors(
    instance_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    from app.services.flavor_eligibility import evaluate_project_flavors, is_flavor_frontend_visible

    server = await _owned_resize_server(conn, token_info, instance_id)
    if server.status.upper() not in _RESIZABLE_STATUSES:
        raise HTTPException(status_code=409, detail="현재 상태에서는 리사이즈할 수 없습니다")
    flavors = await asyncio.to_thread(nova.list_flavors, conn)
    current = _resize_current_flavor(server, flavors)
    visible = [flavor for flavor in flavors if is_flavor_frontend_visible(flavor)]
    evaluated = await evaluate_project_flavors(
        conn, server.project_id or conn._afterglow_project_id, visible, current_flavor=current
    )
    for flavor in evaluated:
        blockers = _resize_target_blockers(flavor, current, image_backed=bool(server.image_id))
        if blockers:
            flavor.eligibility = flavor.eligibility.model_copy(
                update={"selectable": False, "blockers": [*flavor.eligibility.blockers, *blockers]}
            )
    return evaluated


@router.post("/{instance_id}/resize")
async def resize_owned_instance(
    instance_id: str,
    req: InstanceResizeRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn_write),
    token_info: dict = Depends(require_project_write),
):
    from app.services.flavor_eligibility import (
        FlavorEligibilityDenied,
        FlavorEligibilityUnavailable,
        is_flavor_frontend_visible,
        require_flavor_eligible,
    )

    server = await _owned_resize_server(conn, token_info, instance_id)
    if server.status.upper() not in _RESIZABLE_STATUSES:
        raise HTTPException(status_code=409, detail="현재 상태에서는 리사이즈할 수 없습니다")
    flavors = await asyncio.to_thread(nova.list_flavors, conn)
    current = _resize_current_flavor(server, flavors)
    target = next(
        (flavor for flavor in flavors if flavor.id == req.flavor_id and is_flavor_frontend_visible(flavor)), None
    )
    if target is None:
        raise HTTPException(status_code=400, detail="Invalid flavor ID")
    blockers = _resize_target_blockers(target, current, image_backed=bool(server.image_id))
    if blockers:
        raise HTTPException(status_code=409, detail=", ".join(blocker.code for blocker in blockers))
    project_id = server.project_id or conn._afterglow_project_id
    try:
        await require_flavor_eligible(conn, project_id, target, current_flavor=current)
    except FlavorEligibilityDenied as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except FlavorEligibilityUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    try:
        await asyncio.to_thread(nova.resize_server, conn, instance_id, target.id)
    except Exception as exc:
        logger.warning("Instance resize failed: %s", exc)
        raise HTTPException(status_code=400, detail="리사이즈 실패") from exc
    await _invalidate_resized_instance(project_id, instance_id)
    return {"status": "resizing"}


async def _finish_owned_resize(conn, token_info: dict, instance_id: str, *, confirm: bool) -> dict:
    server = await _owned_resize_server(conn, token_info, instance_id)
    if server.status.upper() != "VERIFY_RESIZE":
        raise HTTPException(status_code=409, detail="리사이즈 확인 대기 상태가 아닙니다")
    try:
        await asyncio.to_thread(nova.confirm_resize_server if confirm else nova.revert_resize_server, conn, instance_id)
    except Exception as exc:
        logger.warning("Instance resize %s failed: %s", "confirmation" if confirm else "revert", exc)
        raise HTTPException(status_code=400, detail="리사이즈 처리 실패") from exc
    await _invalidate_resized_instance(server.project_id or conn._afterglow_project_id, instance_id)
    return {"status": "confirmed" if confirm else "reverting"}


@router.post("/{instance_id}/confirm-resize")
async def confirm_owned_resize(
    instance_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn_write),
    token_info: dict = Depends(require_project_write),
):
    return await _finish_owned_resize(conn, token_info, instance_id, confirm=True)


@router.post("/{instance_id}/revert-resize")
async def revert_owned_resize(
    instance_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn_write),
    token_info: dict = Depends(require_project_write),
):
    return await _finish_owned_resize(conn, token_info, instance_id, confirm=False)


@router.post("", response_model=InstanceInfo, status_code=201)
@limiter.limit("5/minute")
async def create_instance(
    request: Request,
    req: CreateInstanceRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn_write),
    token_info: dict = Depends(require_project_write),
):
    """동기식 인스턴스 생성 (기존 방식)."""
    settings = get_settings()
    if req.admin_pass is None:
        req = await _verify_github_ssh(req, token_info=token_info)

    from app.services.instance_names import ensure_unique_instance_name

    try:
        req = req.model_copy(update={"name": await asyncio.to_thread(ensure_unique_instance_name, conn, req.name)})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    from app.services.flavor_eligibility import (
        FlavorEligibilityDenied,
        FlavorEligibilityUnavailable,
        admit_flavor,
        release_admission,
    )
    from app.services.gpu_quota import GpuQuotaDenied, GpuQuotaUnavailable

    password_plan = await asyncio.to_thread(preflight_password, conn, req)
    if req.admin_pass is not None:
        req = await _verify_github_ssh(req, token_info=token_info)
    req, compute_availability_zone, volume_availability_zone = await _resolve_create_placement(
        req,
        conn,
        settings,
    )
    flavors = await asyncio.to_thread(nova.list_flavors, conn)
    flavor = next((f for f in flavors if f.id == req.flavor_id), None)
    if flavor is None:
        raise HTTPException(status_code=400, detail="Invalid flavor ID")
    try:
        admission = await admit_flavor(
            conn, conn._afterglow_project_id, flavor, availability_zone=compute_availability_zone
        )
    except (FlavorEligibilityDenied, GpuQuotaDenied) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (FlavorEligibilityUnavailable, GpuQuotaUnavailable) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    gpu_available = bool(admission.gpu_requested)

    # 수집된 리소스 (rollback 용)
    created_access_ids: list[tuple[str, str]] = []  # (file_storage_id, access_id)
    boot_volume_id: str | None = None
    boot_volume_was_provided: bool = False  # 기존 볼륨 사용 시 rollback 에서 삭제 금지
    server_id: str | None = None
    floating_ip_id: str | None = None

    try:
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
        # 4. cloud-init userdata 생성
        # ------------------------------------------------------------------
        project_id = conn._afterglow_project_id
        userdata = None
        if not password_plan.windows and (gpu_available or data_mounts_info):
            userdata = cloudinit.generate_userdata(
                libraries=[],
                strategy="none",
                file_storages=[],
                upper_device="",
                ceph_monitors=settings.ceph_monitors,
                gpu_available=gpu_available,
                data_mounts=data_mounts_info,
                github_username=req.github_username,
            )

        if not password_plan.windows:
            userdata = cloudinit.compose_userdata(userdata, req.userdata, req.github_username)

        # ------------------------------------------------------------------
        # 5. Nova: 서버 생성
        # ------------------------------------------------------------------
        effective_sgs = await instance_orch.compute_effective_security_groups(
            conn,
            settings,
            project_id,
            gpu_available,
            list(req.security_groups or []),
        )
        req = req.model_copy(update={"security_groups": effective_sgs})

        meta = github_ssh_metadata(req.github_username)

        if data_mounts_info:
            meta[_DATA_SHARE_METADATA_KEY] = ",".join(dm["file_storage_id"] for dm in data_mounts_info)

        server = await asyncio.to_thread(
            nova.create_server,
            conn,
            name=req.name,
            flavor_id=req.flavor_id,
            network_id=req.network_id,
            boot_volume_id=boot_volume_id,
            userdata=userdata,
            key_name=req.key_name,
            admin_pass=password_plan.nova_admin_pass(req.admin_pass),
            config_drive=password_plan.config_drive,
            availability_zone=compute_availability_zone,
            metadata=meta,
            delete_boot_volume_on_termination=(
                False if boot_volume_was_provided else req.delete_boot_volume_on_termination
            ),
            security_groups=req.security_groups if req.security_groups else None,
        )
        server_id = server.id

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

        if not password_plan.windows:
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

    except Exception as e:
        if isinstance(e, HTTPException) and req.admin_pass is None:
            raise
        error_detail = str(e)

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
        if req.admin_pass is not None:
            error_detail = PASSWORD_PROVISIONING_ERROR
        logger.error("인스턴스 생성 실패, rollback 시작: %s", error_detail)

        await instance_orch.rollback_instance(
            conn,
            server_id,
            boot_volume_id if not boot_volume_was_provided else None,
            None,
            [],
            created_access_ids,
            floating_ip_id,
            safe_error_message=PASSWORD_PROVISIONING_ERROR if req.admin_pass is not None else None,
        )
        is_admin = token_info.get("is_system_admin", False)
        detail = (
            PASSWORD_PROVISIONING_ERROR
            if req.admin_pass is not None
            else (
                f"인스턴스 생성 실패: {error_detail}"
                if is_admin
                else "인스턴스 생성에 실패했습니다. 관리자에게 문의하세요."
            )
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
        raise HTTPException(
            status_code=e.status_code if isinstance(e, HTTPException) else 500,
            detail=detail,
            headers=e.headers if isinstance(e, HTTPException) else None,
        ) from None
    finally:
        try:
            await release_admission(admission)
        except Exception:
            logger.warning("GPU quota reservation release failed", exc_info=True)


@router.post("/async")
async def create_instance_async(
    req: CreateInstanceRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn_write),
    token_info: dict = Depends(require_project_write),
):
    """SSE로 진행 상황을 스트리밍하는 비동기 인스턴스 생성."""
    settings = get_settings()
    if req.admin_pass is None:
        req = await _verify_github_ssh(req, token_info=token_info)
    from app.services.instance_names import ensure_unique_instance_name

    try:
        req = req.model_copy(update={"name": await asyncio.to_thread(ensure_unique_instance_name, conn, req.name)})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    from app.services.flavor_eligibility import (
        FlavorEligibilityDenied,
        FlavorEligibilityUnavailable,
        admit_flavor,
        release_admission,
    )
    from app.services.gpu_quota import GpuQuotaDenied, GpuQuotaUnavailable

    password_plan = await asyncio.to_thread(preflight_password, conn, req)
    if req.admin_pass is not None:
        req = await _verify_github_ssh(req, token_info=token_info)
    req, compute_availability_zone, volume_availability_zone = await _resolve_create_placement(
        req,
        conn,
        settings,
    )
    sse_flavors = await asyncio.to_thread(nova.list_flavors, conn)
    sse_flavor = next((flavor for flavor in sse_flavors if flavor.id == req.flavor_id), None)
    if sse_flavor is None:
        raise HTTPException(status_code=400, detail="Invalid flavor ID")
    try:
        admission = await admit_flavor(
            conn, conn._afterglow_project_id, sse_flavor, availability_zone=compute_availability_zone
        )
    except (FlavorEligibilityDenied, GpuQuotaDenied) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (FlavorEligibilityUnavailable, GpuQuotaUnavailable) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    gpu_available = bool(admission.gpu_requested)

    async def progress_generator():
        import time

        # 수집된 리소스 (rollback 용)
        created_access_ids: list[tuple[str, str]] = []
        boot_volume_id: str | None = None
        boot_volume_was_provided: bool = False  # 기존 볼륨 사용 시 rollback 에서 삭제 금지
        server_id: str | None = None
        floating_ip_id: str | None = None
        _start_time = time.monotonic()

        def send_progress(step: ProgressStep, progress: int, message: str, **extra):
            elapsed = round(time.monotonic() - _start_time, 1)
            msg = ProgressMessage(step=step, progress=progress, message=message, elapsed_seconds=elapsed, **extra)
            return f"data: {msg.model_dump_json()}\n\n"

        try:
            data_mounts_info: list[dict] = []
            userdata = None

            if req.data_mounts:
                # Data mounts retain their own Manila preparation stage.
                yield send_progress(ProgressStep.MANILA_PREPARING, 0, "파일 스토리지 준비 중...")
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

            # Linux GPU/data-mount bootstrap must never run for Windows password provisioning.
            if not password_plan.windows and (gpu_available or data_mounts_info):
                yield send_progress(ProgressStep.USERDATA_GENERATING, 60, "cloud-init 생성 중...")
                userdata = cloudinit.generate_userdata(
                    libraries=[],
                    strategy="none",
                    file_storages=[],
                    upper_device="",
                    ceph_monitors=settings.ceph_monitors,
                    gpu_available=gpu_available,
                    data_mounts=data_mounts_info,
                    github_username=req.github_username,
                )
                yield send_progress(ProgressStep.USERDATA_GENERATING, 65, "cloud-init 생성 완료")

            if not password_plan.windows:
                userdata = cloudinit.compose_userdata(userdata, req.userdata, req.github_username)

            # Step 5: Nova server (65-95%)
            yield send_progress(ProgressStep.SERVER_CREATING, 65, "Nova 서버 생성 중...")
            effective_sgs = await instance_orch.compute_effective_security_groups(
                conn,
                settings,
                conn._afterglow_project_id,
                gpu_available,
                list(req.security_groups or []),
            )
            _sse_effective_sgs: list[str] | None = effective_sgs if effective_sgs else None

            meta = github_ssh_metadata(req.github_username)

            if data_mounts_info:
                meta[_DATA_SHARE_METADATA_KEY] = ",".join(dm["file_storage_id"] for dm in data_mounts_info)

            server = await asyncio.to_thread(
                nova.create_server,
                conn,
                name=req.name,
                flavor_id=req.flavor_id,
                network_id=req.network_id,
                boot_volume_id=boot_volume_id,
                userdata=userdata,
                key_name=req.key_name,
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

            # Step 6: Attach volumes (95-100%)
            yield send_progress(ProgressStep.ATTACHING_VOLUME, 95, "볼륨 연결 중...")
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
            if not password_plan.windows:
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
            if req.admin_pass is not None:
                error_detail = PASSWORD_PROVISIONING_ERROR
            logger.error("인스턴스 생성 실패, rollback 시작: %s", error_detail)

            # 비관리자에게는 상세 에러 숨김
            is_admin = token_info.get("is_system_admin", False)
            user_message = (
                PASSWORD_PROVISIONING_ERROR
                if req.admin_pass is not None
                else (
                    f"인스턴스 생성 실패: {error_detail}"
                    if is_admin
                    else "인스턴스 생성에 실패했습니다. 관리자에게 문의하세요."
                )
            )

            yield send_progress(
                ProgressStep.FAILED,
                0,
                user_message,
                error=error_detail if is_admin or req.admin_pass is not None else "인스턴스 생성 실패",
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
                None,
                [],
                created_access_ids,
                floating_ip_id,
                safe_error_message=PASSWORD_PROVISIONING_ERROR if req.admin_pass is not None else None,
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
    conn: openstack.connection.Connection = Depends(get_os_conn_write),
    token_info: dict = Depends(require_project_write),
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
    conn: openstack.connection.Connection = Depends(get_os_conn_write),
    token_info: dict = Depends(require_project_write),
):
    pid = conn._afterglow_project_id
    try:
        server = await asyncio.to_thread(nova.get_server, conn, instance_id)
    except Exception:
        raise HTTPException(status_code=404, detail="인스턴스를 찾을 수 없습니다")
    assert_instance_owner(server, conn, token_info)

    # Revoke only proven instance-managed grants before deleting their tracking.
    for share_id, grant in _storage_grants(server).items():
        if grant["m"]:
            await _revoke_storage_grant(conn, instance_id, share_id, grant, token_info)

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
    for share_id, grant in _storage_grants(server).items():
        if grant["m"]:
            await _revoke_storage_grant(conn, instance_id, share_id, grant, token_info)

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
    require_project_write(token_info)
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


async def _password_server(conn: openstack.connection.Connection, server_id: str, token_info: dict) -> InstanceInfo:
    try:
        server = await asyncio.to_thread(nova.get_server, conn, server_id)
    except HttpException as exc:
        status = exc.status_code if exc.status_code in (403, 404) else 502
        raise HTTPException(status_code=status, detail="인스턴스 조회 실패") from None
    except Exception:
        raise HTTPException(status_code=502, detail="인스턴스 조회 실패") from None

    assert_project_resource_owner(server, conn, token_info, not_found_detail="인스턴스를 찾을 수 없습니다")
    if token_info.get("is_system_admin") is not True:
        creator_id = server.user_id
        caller_id = token_info.get("user_id")
        if not creator_id or not caller_id or creator_id != caller_id:
            raise HTTPException(
                status_code=403,
                detail="인스턴스 생성자 본인 또는 시스템 관리자만 패스워드를 변경할 수 있습니다",
            )
    return server


@router.get("/{server_id}/admin-password/precheck", response_model=AdminPasswordPrecheck)
async def precheck_admin_password(
    server_id: str,
    token_info: dict = Depends(get_token_info),
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """인스턴스 패스워드 재설정 가능 여부를 사전 점검한다.
    생성자 본인 또는 시스템 관리자 권한이 필요하며,
    QGA 지원 여부, 인스턴스 상태, os_admin_user를 반환.
    """
    s = await _password_server(conn, server_id, token_info)

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
    conn: openstack.connection.Connection = Depends(get_os_conn_write),
):
    """QEMU Guest Agent를 통해 인스턴스 관리자 계정의 패스워드를 재설정한다.
    생성자 본인 또는 시스템 관리자만 호출 가능하며,
    이미지에 hw_qemu_guest_agent=yes + 게스트 내 QGA 데몬 실행 중이어야 동작.
    """
    s = await _password_server(conn, server_id, token_info)

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
        await asyncio.to_thread(nova.change_server_password, conn, server_id, body.new_password.get_secret_value())
        await rec(
            token_info,
            conn,
            resource_type="instance",
            action="instance.set_admin_password",
            status="success",
            resource_id=server_id,
        )
    except Exception as exc:
        status = (
            exc.status_code
            if isinstance(exc, HttpException) and exc.status_code in (400, 401, 403, 404, 409, 501, 503)
            else 502
        )
        # SDK error bodies can echo adminPass; never expose or persist exception text.
        logger.warning("admin_password_reset failed server=%s status=%s", server_id, status)
        await rec(
            token_info,
            conn,
            resource_type="instance",
            action="instance.set_admin_password",
            status="failed",
            resource_id=server_id,
            error_message=f"Nova password change request failed (HTTP {status})",
        )
        raise HTTPException(status_code=status, detail="Nova 패스워드 변경 요청 실패") from None


# ---------------------------------------------------------------------------
# Manila access authorization only — no guest mounting or command execution.
# ---------------------------------------------------------------------------

_STORAGE_GRANT_PREFIX = "afterglow_share_grant_"
_STORAGE_RULE_OWNER = "afterglow_instance_id"


def _storage_grant_key(share_id: str) -> str:
    return _STORAGE_GRANT_PREFIX + hashlib.sha256(share_id.encode()).hexdigest()


def _storage_grants(server) -> dict[str, dict]:
    grants = {}
    for key, value in (server.metadata or {}).items():
        if not key.startswith(_STORAGE_GRANT_PREFIX):
            continue
        try:
            grant = json.loads(value)
            if (
                not isinstance(grant, dict)
                or set(grant) != {"s", "i", "t", "a", "l", "m"}
                or not all(isinstance(grant[k], str) and grant[k] for k in ("s", "i", "t", "a", "l"))
                or not isinstance(grant["m"], bool)
                or grant["t"] not in {"ip", "cephx"}
                or grant["l"] not in {"ro", "rw"}
                or key != _storage_grant_key(grant["s"])
            ):
                raise ValueError
            grants[grant["s"]] = grant
        except (ValueError, TypeError):
            raise HTTPException(status_code=409, detail="스토리지 접근 연결 메타데이터가 올바르지 않습니다") from None
    return grants


async def _storage_server(conn, instance_id: str, token_info: dict):
    try:
        server = await asyncio.to_thread(nova.get_server, conn, instance_id)
    except Exception:
        raise HTTPException(status_code=404, detail="인스턴스를 찾을 수 없습니다") from None
    assert_project_resource_owner(server, conn, token_info, not_found_detail="인스턴스를 찾을 수 없습니다")
    return server


async def _storage_share(conn, share_id: str, token_info: dict):
    try:
        share = await asyncio.to_thread(manila.get_file_storage, conn, share_id)
    except Exception:
        raise HTTPException(status_code=502, detail="파일 스토리지를 조회할 수 없습니다") from None
    # Public visibility is not share management authority.
    assert_project_resource_owner(share, conn, token_info, not_found_detail="파일 스토리지 관리 권한이 없습니다")
    if share.share_proto not in {"NFS", "CEPHFS"}:
        raise HTTPException(status_code=422, detail="NFS 또는 CephFS 접근 규칙만 지원합니다")
    return share


def _storage_target(server, instance_id: str, share_proto: str, fixed_ip: str | None) -> tuple[str, str]:
    if share_proto == "CEPHFS":
        if fixed_ip:
            raise HTTPException(status_code=422, detail="CephFS는 fixed IP 대신 인스턴스 CephX ID를 사용합니다")
        try:
            return "cephx", "afterglow-" + UUID(instance_id).hex
        except ValueError:
            raise HTTPException(status_code=422, detail="인스턴스 UUID가 올바르지 않습니다") from None
    addresses = set()
    for address in server.ip_addresses:
        if address.type == "fixed":
            try:
                addresses.add(str(ipaddress.ip_address(address.addr)))
            except ValueError:
                continue
    if fixed_ip is None:
        if len(addresses) != 1:
            raise HTTPException(status_code=409, detail="인스턴스의 정확한 fixed IP를 선택하세요")
        return "ip", next(iter(addresses))
    try:
        selected = str(ipaddress.ip_address(fixed_ip))
    except ValueError:
        raise HTTPException(status_code=422, detail="CIDR이 아닌 정확한 fixed IP를 선택하세요") from None
    if selected not in addresses:
        raise HTTPException(status_code=409, detail="선택한 IP가 현재 인스턴스의 fixed IP가 아닙니다")
    return "ip", selected


def _storage_rule_matches(rule: dict, grant: dict, instance_id: str) -> bool:
    return (
        rule.get("id") == grant["i"]
        and rule.get("access_type") == grant["t"]
        and rule.get("access_to") == grant["a"]
        and rule.get("access_level") == grant["l"]
        and (not grant["m"] or (rule.get("metadata") or {}).get(_STORAGE_RULE_OWNER) == instance_id)
    )


async def _storage_rules(conn, share_id: str) -> list[dict]:
    try:
        return await asyncio.to_thread(manila.list_access_rules, conn, share_id, strict=True)
    except Exception:
        raise HTTPException(status_code=502, detail="스토리지 접근 규칙을 조회할 수 없습니다") from None


async def _storage_connection_info(
    conn, share, grant: dict | None, rule: dict | None, *, association_state: str | None = None
):
    network_id = share.share_network_id
    network = None
    if network_id:
        network = await asyncio.to_thread(manila.get_share_network, conn, network_id)
    # Whitelist inspectable fields. Never serialize a provider access-rule dict.
    return {
        "file_storage_id": share.id,
        "name": share.name,
        "share_proto": share.share_proto,
        "status": share.status,
        "access_id": rule.get("id") if rule else (grant["i"] if grant else None),
        "access_type": rule.get("access_type") if rule else (grant["t"] if grant else None),
        "access_to": rule.get("access_to") if rule else (grant["a"] if grant else None),
        "access_level": rule.get("access_level") if rule else (grant["l"] if grant else None),
        "state": rule.get("state", "unknown") if rule else ("missing" if grant else "untracked"),
        "association_state": association_state or ("tracked" if grant else "untracked"),
        "managed": bool(grant and grant["m"]),
        "exports": list(share.export_locations),
        "share_network_id": network_id,
        "share_network": network,
    }


async def _invalidate_storage_instance(conn, instance_id: str) -> None:
    project_id = conn._afterglow_project_id
    await invalidate(f"afterglow:nova:{project_id}:instance:{instance_id}")
    await cache_invalidation.invalidate_mutation_count("nova", project_id)


@router.post("/{instance_id}/storage-attachments", response_model=dict)
async def attach_storage(
    instance_id: str,
    req: StorageAttachRequest,
    response: Response,
    conn: openstack.connection.Connection = Depends(get_os_conn_write),
    token_info: dict = Depends(get_token_info),
):
    """Authorize an exact Manila target; acceptance is not an active rule or guest mount."""
    require_project_write(token_info)
    response.headers["Cache-Control"] = "no-store"
    server = await _storage_server(conn, instance_id, token_info)
    share = await _storage_share(conn, req.file_storage_id, token_info)
    if share.status != "available":
        raise HTTPException(status_code=409, detail="파일 스토리지가 available 상태가 아닙니다")
    access_type, access_to = _storage_target(server, instance_id, share.share_proto, req.fixed_ip)
    level = "ro" if req.read_only else "rw"
    grant = _storage_grants(server).get(share.id)
    rules = await _storage_rules(conn, share.id)
    created = False
    if grant:
        if (grant["t"], grant["a"], grant["l"]) != (access_type, access_to, level):
            raise HTTPException(status_code=409, detail="기존 접근 규칙의 대상 또는 권한을 변경할 수 없습니다")
        rule = next((r for r in rules if r.get("id") == grant["i"]), None)
        if not rule or not _storage_rule_matches(rule, grant, instance_id):
            raise HTTPException(status_code=409, detail="추적 중인 접근 규칙이 없거나 변경되었습니다")
    else:
        # Reserve a UUID-sized provider rule ID before any allow mutation.
        candidate = {"s": share.id, "i": "0" * 36, "t": access_type, "a": access_to, "l": level, "m": True}
        if len(json.dumps(candidate, separators=(",", ":"), ensure_ascii=True).encode()) > 256:
            raise HTTPException(status_code=422, detail="접근 연결이 Nova 메타데이터 제한을 초과합니다")
        matching = [r for r in rules if r.get("access_type") == access_type and r.get("access_to") == access_to]
        if matching:
            if len(matching) != 1 or matching[0].get("access_level") != level:
                raise HTTPException(status_code=409, detail="기존 접근 규칙의 권한이 요청과 일치하지 않습니다")
            rule = matching[0]
            if (rule.get("metadata") or {}).get(_STORAGE_RULE_OWNER):
                raise HTTPException(status_code=409, detail="이 접근 규칙은 다른 연결에서 관리됩니다")
        else:
            metadata = {_STORAGE_RULE_OWNER: instance_id}
            if access_type == "ip":
                settings = get_settings()
                metadata.update(
                    manila._build_nfs_access_metadata(
                        settings.manila_nfs_root_squash,
                        settings.manila_nfs_sec_flavor,
                    )
                )
            try:
                rule = await asyncio.to_thread(
                    manila.create_access_rule,
                    conn,
                    share.id,
                    access_to,
                    level,
                    access_type=access_type,
                    metadata=metadata,
                    wait_for_key=False,
                )
            except Exception:
                raise HTTPException(
                    status_code=502, detail="스토리지 접근 허용 요청 실패; 제공자 상태를 확인하세요"
                ) from None
            created = True
        grant = {"s": share.id, "i": rule["id"], "t": access_type, "a": access_to, "l": level, "m": created}
        value = json.dumps(grant, separators=(",", ":"), ensure_ascii=True)
        if len(value.encode()) > 256:
            raise HTTPException(status_code=502, detail="접근 규칙 연결이 Nova 메타데이터 제한을 초과합니다")
        try:
            await asyncio.to_thread(
                conn.compute.set_server_metadata, instance_id, **{_storage_grant_key(share.id): value}
            )
        except Exception:
            # Do not report success or delete on an ambiguous metadata write failure.
            raise HTTPException(
                status_code=502, detail="접근 규칙 연결 기록 실패; 제공자 규칙과 메타데이터를 확인하세요"
            ) from None
    await _invalidate_storage_instance(conn, instance_id)
    try:
        result = await _storage_connection_info(conn, share, grant, rule)
    except Exception:
        raise HTTPException(
            status_code=502, detail="접근 규칙은 요청되었으나 연결 정보를 조회하지 못했습니다"
        ) from None
    if created and access_type == "cephx" and rule.get("state") == "active" and rule.get("access_key"):
        result["secret"] = {"type": "cephx_key", "value": rule["access_key"]}
    return result


@router.get("/{instance_id}/storage-attachments", response_model=list)
async def list_storage_attachments(
    instance_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    """Inspect actual rule state without access keys; legacy mount metadata is untracked."""
    server = await _storage_server(conn, instance_id, token_info)
    grants = _storage_grants(server)
    legacy = _data_share_metadata_value(server)
    share_ids = list(dict.fromkeys([*grants, *(s for s in legacy.split(",") if s and s != "none")]))
    result = []
    for share_id in share_ids:
        grant = grants.get(share_id)
        try:
            share = await _storage_share(conn, share_id, token_info)
            rules = await _storage_rules(conn, share_id) if grant else []
            rule = next((r for r in rules if r.get("id") == grant["i"]), None) if grant else None
            mismatch = rule and not _storage_rule_matches(rule, grant, instance_id)
            result.append(
                await _storage_connection_info(
                    conn, share, grant, rule, association_state="mismatch" if mismatch else None
                )
            )
        except Exception:
            result.append(
                {
                    "file_storage_id": share_id,
                    "name": None,
                    "share_proto": None,
                    "status": "unknown",
                    "access_id": grant["i"] if grant else None,
                    "access_type": grant["t"] if grant else None,
                    "access_to": grant["a"] if grant else None,
                    "access_level": grant["l"] if grant else None,
                    "state": "unknown",
                    "association_state": "unknown",
                    "managed": bool(grant and grant["m"]),
                    "exports": [],
                    "share_network_id": None,
                    "share_network": None,
                }
            )
    return result


@router.post("/{instance_id}/storage-attachments/{file_storage_id}/connection-info", response_model=dict)
async def storage_connection_info(
    instance_id: str,
    file_storage_id: str,
    response: Response,
    conn: openstack.connection.Connection = Depends(get_os_conn_write),
    token_info: dict = Depends(get_token_info),
):
    """Explicit authorized retrieval of a transient Ceph key; never return it from GET."""
    require_project_write(token_info)
    response.headers["Cache-Control"] = "no-store"
    server = await _storage_server(conn, instance_id, token_info)
    grant = _storage_grants(server).get(file_storage_id)
    if not grant or not grant["m"]:
        raise HTTPException(status_code=409, detail="이 인스턴스의 관리 접근 규칙이 아닙니다")
    share = await _storage_share(conn, file_storage_id, token_info)
    rules = await _storage_rules(conn, file_storage_id)
    rule = next((r for r in rules if r.get("id") == grant["i"]), None)
    if not rule or not _storage_rule_matches(rule, grant, instance_id):
        raise HTTPException(status_code=409, detail="추적 중인 접근 규칙이 없거나 변경되었습니다")
    try:
        result = await _storage_connection_info(conn, share, grant, rule)
    except Exception:
        raise HTTPException(status_code=502, detail="연결 정보를 조회할 수 없습니다") from None
    if (
        share.status == "available"
        and rule.get("state") == "active"
        and grant["t"] == "cephx"
        and rule.get("access_key")
    ):
        result["secret"] = {"type": "cephx_key", "value": rule["access_key"]}
    return result


async def _revoke_storage_grant(conn, instance_id: str, share_id: str, grant: dict, token_info: dict) -> None:
    """Shared exact managed-rule lifecycle for revoke and instance deletion cleanup."""
    if not grant["m"]:
        raise HTTPException(status_code=409, detail="기존 외부 접근 규칙은 이 인스턴스에서 회수할 수 없습니다")
    try:
        rule = await asyncio.to_thread(manila.get_access_rule, conn, share_id, grant["i"])
    except Exception:
        raise HTTPException(status_code=502, detail="정확한 접근 규칙을 조회할 수 없습니다") from None
    if not rule:
        return
    # Exact rule 404 already proves cleanup; a deleted parent must not block it.
    # Existing rules still require current share management authority before denial.
    await _storage_share(conn, share_id, token_info)
    if not _storage_rule_matches(rule, grant, instance_id):
        raise HTTPException(status_code=409, detail="접근 규칙 소유권 또는 대상이 변경되었습니다")
    if rule.get("state") not in {"denying", "queued_to_deny"}:
        try:
            await asyncio.to_thread(manila.revoke_access_rule, conn, share_id, grant["i"])
        except Exception:
            raise HTTPException(status_code=502, detail="접근 규칙 회수 요청 실패") from None
    try:
        remaining = await asyncio.to_thread(manila.get_access_rule, conn, share_id, grant["i"])
    except Exception:
        raise HTTPException(status_code=502, detail="접근 규칙 회수 완료를 확인할 수 없습니다") from None
    if remaining is not None:
        raise HTTPException(
            status_code=409, detail="접근 규칙 회수가 아직 완료되지 않았습니다; 상태를 확인 후 다시 시도하세요"
        )


@router.delete("/{instance_id}/storage-attachments/{file_storage_id}", status_code=204)
async def detach_storage(
    instance_id: str,
    file_storage_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn_write),
    token_info: dict = Depends(get_token_info),
):
    """Revoke only the exact tracked managed rule, never infer ownership from names/IPs."""
    require_project_write(token_info)
    server = await _storage_server(conn, instance_id, token_info)
    grant = _storage_grants(server).get(file_storage_id)
    if not grant:
        raise HTTPException(status_code=409, detail="이 인스턴스에서 추적하는 접근 규칙이 없습니다")
    await _revoke_storage_grant(conn, instance_id, file_storage_id, grant, token_info)
    try:
        await asyncio.to_thread(conn.compute.delete_server_metadata, instance_id, [_storage_grant_key(file_storage_id)])
    except Exception:
        raise HTTPException(status_code=502, detail="규칙 회수 후 연결 기록 제거 실패; 다시 시도하세요") from None
    await _invalidate_storage_instance(conn, instance_id)
