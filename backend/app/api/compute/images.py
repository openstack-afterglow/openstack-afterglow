from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import openstack
import asyncio
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from app.api.common.activity_recorder import rec
from app.api.deps import CacheMode, cache_mode, get_os_conn, get_token_info
from app.config import get_settings
from app.models.compute import ImageDetail, ImageInfo
from app.rate_limit import limiter
from app.services import glance, image_verification
from app.services.cache import cached_call, invalidate, ttl_static
from app.services.image_refs import ImageReferenceError, image_reference_fields, normalize_image_reference

router = APIRouter()
_logger = logging.getLogger(__name__)


class UpdateImageRequest(BaseModel):
    name: str | None = None
    os_distro: str | None = None
    os_type: str | None = None
    min_disk: int | None = None
    min_ram: int | None = None
    visibility: str | None = None


class UpdatePropertiesRequest(BaseModel):
    """이미지 임의 메타데이터 추가/수정/삭제."""

    set: dict[str, str] | None = None
    remove: list[str] | None = None


@router.get("", response_model=list[ImageInfo])
async def list_images(
    conn: openstack.connection.Connection = Depends(get_os_conn), cm: CacheMode = Depends(cache_mode)
):
    pid = conn._afterglow_project_id
    raw = await cached_call(
        f"afterglow:glance:{pid}:images",
        ttl_static(),
        lambda: [
            img.model_dump(exclude={"verification_status", "verified_at"}) for img in glance.list_images(conn, pid)
        ],
        enabled=cm.enabled,
        refresh=cm.refresh,
    )
    return await image_verification.enrich([ImageInfo.model_validate(item) for item in raw])


@router.post("", status_code=201)
@limiter.limit("3/minute")
async def upload_image(
    request: Request,
    file: UploadFile = File(...),
    name: str = Form(...),
    disk_format: str = Form("raw"),
    visibility: str = Form("private"),
    os_distro: str | None = Form(None),
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    """이미지 파일 업로드 (multipart/form-data). raw / qcow2 / vmdk 등 주요 포맷 지원."""
    pid = conn._afterglow_project_id
    if disk_format not in glance._ALLOWED_DISK_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 disk_format입니다. 허용: {sorted(glance._ALLOWED_DISK_FORMATS)}",
        )
    if visibility not in {"private", "public", "shared", "community"}:
        raise HTTPException(status_code=400, detail="visibility 값이 올바르지 않습니다")
    is_admin = token_info.get("is_system_admin", False)
    if visibility in {"public", "community"} and not is_admin:
        raise HTTPException(status_code=403, detail="public/community 가시성은 시스템 관리자만 설정할 수 있습니다")
    if not (name or "").strip():
        raise HTTPException(status_code=400, detail="이미지 이름이 비어 있습니다")
    try:
        normalized_name = normalize_image_reference(name)
    except ImageReferenceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    settings = get_settings()
    max_bytes = settings.app_max_upload_gb * 1024**3
    incoming_size = getattr(file, "size", None)
    if incoming_size is not None and incoming_size > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"파일이 최대 허용 크기({settings.app_max_upload_gb}GB)를 초과합니다",
        )

    props: dict = {}
    if os_distro:
        props["os_distro"] = os_distro

    try:
        img = await asyncio.to_thread(
            glance.create_image,
            conn,
            name=normalized_name,
            disk_format=disk_format,
            visibility=visibility,
            data=file.file,
            properties=props or None,
        )
    except Exception as e:
        await rec(
            token_info,
            conn,
            resource_type="image",
            action="create",
            status="failed",
            error_message=str(e)[:500],
        )
        raise HTTPException(status_code=500, detail=f"이미지 업로드 실패: {e}") from e

    try:
        await invalidate(f"afterglow:glance:{pid}:images")
        await rec(
            token_info,
            conn,
            resource_type="image",
            action="create",
            resource_id=img.id,
        )
    except Exception:
        _logger.warning("Uploaded image %s cache/audit update failed", img.id, exc_info=True)
    verification_status = "unverified"
    verified_at = None
    verification_message = None
    if is_admin:
        # SDK direct PUT completes before return; the returned resource may still
        # be queued, so fetch the post-upload Glance digest before approval.
        try:
            current = await asyncio.to_thread(glance.get_image, conn, img.id)
            await image_verification.set_verification(current, verified=True, actor_id=token_info["user_id"])
            projected = (await image_verification.enrich([current]))[0]
            verification_status = projected.verification_status
            verified_at = projected.verified_at
            if verification_status != "verified":
                verification_message = (
                    "이미지는 업로드되었지만 검증 상태를 확인하지 못했습니다. 상세 상태를 다시 확인하세요."
                )
        except Exception:
            _logger.warning("Uploaded image %s created without verification", img.id, exc_info=True)
            verification_status = "unavailable"
            verification_message = (
                "이미지는 업로드되었지만 관리자 검증을 기록하지 못했습니다. 상세 상태를 확인하고 다시 승인하세요."
            )
    else:
        projected = (await image_verification.enrich([ImageInfo(id=img.id, name=normalized_name, status=img.status)]))[
            0
        ]
        verification_status = projected.verification_status
    display_name, repository, tag = image_reference_fields(getattr(img, "name", None))
    return {
        "id": img.id,
        "name": display_name,
        "repository": repository,
        "tag": tag,
        "status": img.status,
        "disk_format": img.disk_format,
        "verification_status": verification_status,
        "verified_at": verified_at,
        "verification_message": verification_message,
    }


@router.get("/{image_id}", response_model=ImageDetail)
async def get_image_detail(
    image_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    try:
        image = await asyncio.to_thread(glance.get_image, conn, image_id)
    except Exception:
        raise HTTPException(status_code=404, detail="이미지를 찾을 수 없습니다")
    return (await image_verification.enrich([image]))[0]


@router.delete("/{image_id}", status_code=204)
async def delete_image(
    image_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    try:
        await asyncio.to_thread(glance.delete_image, conn, image_id)
    except Exception:
        raise HTTPException(status_code=500, detail="이미지 삭제 실패")
    try:
        await invalidate(f"afterglow:glance:{getattr(conn, '_afterglow_project_id', None)}:images")
    except Exception:
        _logger.warning("Deleted image %s cache invalidation failed", image_id, exc_info=True)
    try:
        await image_verification.remove_deleted_image(image_id)
    except image_verification.VerificationUnavailable:
        _logger.warning("Deleted image %s retained an inaccessible verification row", image_id)


@router.patch("/{image_id}", response_model=ImageInfo)
async def update_image(
    image_id: str,
    req: UpdateImageRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    normalized_name = None
    if req.name is not None:
        try:
            normalized_name = normalize_image_reference(req.name)
        except ImageReferenceError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        result = await asyncio.to_thread(
            glance.update_image_metadata,
            conn,
            image_id,
            normalized_name,
            req.os_distro,
            req.os_type,
            req.min_disk,
            req.min_ram,
            req.visibility,
        )
        await invalidate(f"afterglow:glance:{getattr(conn, '_afterglow_project_id', None)}:images")
        return (await image_verification.enrich([result]))[0]
    except Exception:
        raise HTTPException(status_code=500, detail="이미지 메타데이터 수정 실패")


@router.patch("/{image_id}/properties", response_model=ImageDetail)
async def update_image_properties(
    image_id: str,
    req: UpdatePropertiesRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    """이미지 임의 properties 추가/수정/삭제. 소유자 또는 시스템 관리자만 가능."""
    try:
        img = await asyncio.to_thread(conn.image.get_image, image_id)
    except Exception:
        raise HTTPException(status_code=404, detail="이미지를 찾을 수 없습니다")
    is_admin = token_info.get("is_system_admin", False)
    if not is_admin and img.owner != conn._afterglow_project_id:
        raise HTTPException(status_code=403, detail="본인 소유 이미지만 수정할 수 있습니다")
    try:
        result = await asyncio.to_thread(
            glance.update_image_properties,
            conn,
            image_id,
            req.set,
            req.remove,
        )
        await invalidate(f"afterglow:glance:{conn._afterglow_project_id}:images")
        return (await image_verification.enrich([result]))[0]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"properties 수정 실패: {e}")


# ---------------------------------------------------------------------------
# 이미지 멤버 (공유 프로젝트 관리)
# ---------------------------------------------------------------------------


class AddMemberRequest(BaseModel):
    member: str  # project_id


@router.post("/{image_id}/deactivate", status_code=200)
async def deactivate_own_image(
    image_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """본인 프로젝트가 소유한 이미지를 비활성화."""
    try:
        img = await asyncio.to_thread(conn.image.get_image, image_id)
    except Exception:
        raise HTTPException(status_code=404, detail="이미지를 찾을 수 없습니다")
    if img.owner != conn._afterglow_project_id:
        raise HTTPException(status_code=403, detail="본인 소유 이미지만 변경할 수 있습니다")
    try:
        await asyncio.to_thread(glance.deactivate_image, conn, image_id)
        return {"status": "deactivated"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"비활성화 실패: {e}")


@router.post("/{image_id}/reactivate", status_code=200)
async def reactivate_own_image(
    image_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """본인 프로젝트가 소유한 이미지를 활성화."""
    try:
        img = await asyncio.to_thread(conn.image.get_image, image_id)
    except Exception:
        raise HTTPException(status_code=404, detail="이미지를 찾을 수 없습니다")
    if img.owner != conn._afterglow_project_id:
        raise HTTPException(status_code=403, detail="본인 소유 이미지만 변경할 수 있습니다")
    try:
        await asyncio.to_thread(glance.reactivate_image, conn, image_id)
        return {"status": "active"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"활성화 실패: {e}")


# ---------------------------------------------------------------------------
# 이미지 멤버 (공유 프로젝트 관리)
# ---------------------------------------------------------------------------


@router.get("/{image_id}/members")
async def list_image_members(
    image_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """이미지 공유 멤버(프로젝트) 목록 조회."""
    try:
        return await asyncio.to_thread(glance.list_image_members, conn, image_id)
    except Exception:
        raise HTTPException(status_code=500, detail="멤버 목록 조회 실패")


@router.post("/{image_id}/members", status_code=201)
async def add_image_member(
    image_id: str,
    req: AddMemberRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """이미지에 공유 프로젝트 추가."""
    try:
        return await asyncio.to_thread(glance.add_image_member, conn, image_id, req.member)
    except Exception:
        raise HTTPException(status_code=500, detail="멤버 추가 실패")


@router.delete("/{image_id}/members/{member_id}", status_code=204)
async def remove_image_member(
    image_id: str,
    member_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """이미지에서 공유 프로젝트 삭제."""
    try:
        await asyncio.to_thread(glance.remove_image_member, conn, image_id, member_id)
    except Exception:
        raise HTTPException(status_code=500, detail="멤버 삭제 실패")
