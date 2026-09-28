"""관리자 이미지 관리 엔드포인트."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import openstack
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.deps import get_os_conn, get_token_info, require_admin
from app.models.compute import ImageDetail, ImageInfo
from app.services import glance, image_verification
from app.services.image_refs import ImageReferenceError, image_reference_fields, normalize_image_reference

_logger = logging.getLogger(__name__)

router = APIRouter()


class AdminUpdateImageRequest(BaseModel):
    name: str | None = None
    os_distro: str | None = None
    os_type: str | None = None
    min_disk: int | None = None
    min_ram: int | None = None
    visibility: str | None = None


class AdminUpdatePropertiesRequest(BaseModel):
    """이미지 임의 메타데이터 추가/수정/삭제."""

    set: dict[str, str] | None = None
    remove: list[str] | None = None


class VerificationRequest(BaseModel):
    verified: bool


def _serialize_image(img) -> dict:
    display_name, repository, tag = image_reference_fields(getattr(img, "name", None))
    return {
        "id": img.id,
        "name": display_name,
        "repository": repository,
        "tag": tag,
        "status": img.status or "",
        "size": img.size or 0,
        "min_disk": img.min_disk or 0,
        "min_ram": img.min_ram or 0,
        "disk_format": img.disk_format or "",
        "os_distro": getattr(img, "os_distro", None) or glance._guess_distro(display_name),
        "visibility": img.visibility or "private",
        "owner": img.owner or "",
        "created_at": str(img.created_at) if img.created_at else None,
        "protected": getattr(img, "is_protected", False),
        "os_hash_algo": getattr(img, "hash_algo", None),
        "os_hash_value": getattr(img, "hash_value", None),
    }


@router.get("/images", dependencies=[Depends(require_admin)])
async def list_admin_images(
    conn: openstack.connection.Connection = Depends(get_os_conn),
    limit: int = Query(default=20, ge=1, le=100),
    marker: str | None = Query(default=None),
    search: str | None = Query(default=None),
    visibility: str | None = Query(default=None),
):
    """전체 이미지 목록 (페이지네이션).

    `search` 가 있으면 전체 이미지를 가져와 case-insensitive substring 필터링 후
    marker 기반 페이지네이션을 수동 처리한다.
    `visibility` 가 있으면 Glance 서버에서 필터링한다.
    """
    try:

        def _list_paged():
            kwargs: dict = {}
            if marker:
                kwargs["marker"] = marker
            if visibility:
                kwargs["visibility"] = visibility
            items: list[dict] = []
            for img in conn.image.images(**kwargs):
                items.append(_serialize_image(img))
                if len(items) >= limit:
                    break
            next_marker = items[-1]["id"] if len(items) == limit else None
            return {"items": items, "next_marker": next_marker, "count": len(items)}

        def _list_search():
            needle = (search or "").lower()
            matched: list[dict] = []
            glance_kwargs: dict = {}
            if visibility:
                glance_kwargs["visibility"] = visibility
            for img in conn.image.images(**glance_kwargs):
                item = _serialize_image(img)
                name = item["name"].lower()
                if needle and needle not in name:
                    continue
                matched.append(item)
            # marker 기반 슬라이싱 (marker = 직전 페이지 마지막 항목 id)
            start = 0
            if marker:
                for i, item in enumerate(matched):
                    if item["id"] == marker:
                        start = i + 1
                        break
            page = matched[start : start + limit]
            has_more = (start + limit) < len(matched)
            next_marker = page[-1]["id"] if page and has_more else None
            return {"items": page, "next_marker": next_marker, "count": len(page)}

        result = await asyncio.to_thread(_list_search if search else _list_paged)
        result["items"] = [
            image.model_dump()
            for image in await image_verification.enrich([ImageInfo.model_validate(item) for item in result["items"]])
        ]
        return result
    except Exception:
        _logger.warning("관리자 이미지 목록 조회 실패", exc_info=True)
        raise HTTPException(status_code=500, detail="이미지 목록 조회 실패")


@router.get("/images/{image_id}", dependencies=[Depends(require_admin)])
async def get_admin_image(
    image_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """이미지 상세 조회."""
    try:
        image = await asyncio.to_thread(glance.get_image, conn, image_id)
    except Exception:
        raise HTTPException(status_code=404, detail="이미지를 찾을 수 없습니다")
    return (await image_verification.enrich([image]))[0]


@router.put("/images/{image_id}/verification", response_model=ImageDetail, dependencies=[Depends(require_admin)])
async def set_admin_image_verification(
    image_id: str,
    req: VerificationRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    try:
        image = await asyncio.to_thread(glance.get_image, conn, image_id)
    except Exception:
        raise HTTPException(status_code=404, detail="이미지를 찾을 수 없습니다")
    try:
        await image_verification.set_verification(image, verified=req.verified, actor_id=token_info["user_id"])
    except image_verification.ImageNotVerifiable as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except image_verification.VerificationUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return (await image_verification.enrich([image]))[0]


@router.patch("/images/{image_id}", dependencies=[Depends(require_admin)])
async def update_admin_image(
    image_id: str,
    req: AdminUpdateImageRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """이미지 메타데이터 수정."""
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
        return (await image_verification.enrich([result]))[0]
    except Exception as e:
        _logger.warning("이미지 수정 실패: %s", e)

        raise HTTPException(status_code=400, detail="이미지 수정 실패")


@router.patch("/images/{image_id}/properties", dependencies=[Depends(require_admin)], response_model=ImageDetail)
async def update_admin_image_properties(
    image_id: str,
    req: AdminUpdatePropertiesRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """이미지 임의 properties 추가/수정/삭제 (관리자)."""
    try:
        result = await asyncio.to_thread(
            glance.update_image_properties,
            conn,
            image_id,
            req.set,
            req.remove,
        )
        return (await image_verification.enrich([result]))[0]
    except Exception as e:
        _logger.warning("이미지 properties 수정 실패 image=%s: %s", image_id, e)
        raise HTTPException(status_code=400, detail=f"properties 수정 실패: {e}")


@router.delete("/images/{image_id}", dependencies=[Depends(require_admin)], status_code=204)
async def delete_admin_image(
    image_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """이미지 삭제."""
    try:
        await asyncio.to_thread(glance.delete_image, conn, image_id)
    except Exception as e:
        _logger.warning("이미지 삭제 실패: %s", e)

        raise HTTPException(status_code=400, detail="이미지 삭제 실패")
    try:
        await image_verification.remove_deleted_image(image_id)
    except image_verification.VerificationUnavailable:
        _logger.warning("Deleted image %s retained an inaccessible verification row", image_id)


@router.post("/images/{image_id}/deactivate", dependencies=[Depends(require_admin)], status_code=200)
async def deactivate_admin_image(
    image_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """이미지 비활성화 (deactivated 상태)."""
    try:
        await asyncio.to_thread(glance.deactivate_image, conn, image_id)
        return {"status": "deactivated"}
    except Exception as e:
        _logger.warning("이미지 비활성화 실패: %s", e)

        raise HTTPException(status_code=400, detail="이미지 비활성화 실패")


@router.post("/images/{image_id}/reactivate", dependencies=[Depends(require_admin)], status_code=200)
async def reactivate_admin_image(
    image_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """이미지 활성화 (active 상태)."""
    try:
        await asyncio.to_thread(glance.reactivate_image, conn, image_id)
        return {"status": "active"}
    except Exception as e:
        _logger.warning("이미지 활성화 실패: %s", e)

        raise HTTPException(status_code=400, detail="이미지 활성화 실패")
