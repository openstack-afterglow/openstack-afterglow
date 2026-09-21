from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from pydantic import BaseModel

from app.api.deps import get_token_info, require_admin
from app.config import get_settings
from app.services.site_branding import (
    MAX_BRANDING_UPLOAD_BYTES,
    BrandingStorageUnavailable,
    BrandingValidationError,
    branding_admin_status,
    delete_branding_asset,
    effective_public_site_config,
    get_branding_asset,
    upsert_branding_asset,
)

router = APIRouter()


class SiteServicesResponse(BaseModel):
    magnum: bool
    manila: bool
    zun: bool
    cloud_shell: bool
    k3s: bool
    trove: bool
    swift: bool
    barbican: bool
    waygate: bool
    chat: bool
    mcp: bool
    palimpsest: bool


class PublicSiteConfigResponse(BaseModel):
    site_name: str
    site_description: str
    logo_path: str
    logo_dark_path: str
    logo_light_path: str
    favicon_path: str
    services: SiteServicesResponse
    mcp_url: str = ""


class BrandingSlotResponse(BaseModel):
    field: str
    label: str
    description: str


class BrandingAssetResponse(BaseModel):
    slot: str
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    url: str
    updated_at: str
    updated_by_user_id: str | None


class BrandingStatusResponse(BaseModel):
    slots: dict[str, BrandingSlotResponse]
    effective: dict[str, str]
    assets: dict[str, BrandingAssetResponse | None]


@router.get("", response_model=PublicSiteConfigResponse)
async def get_site_config():
    """사이트 표시 이름 및 설명 반환 (인증 불필요)."""
    return await effective_public_site_config(get_settings())


@router.get("/assets/{slot}")
async def get_site_branding_asset(slot: str, v: str | None = None):
    try:
        asset = await get_branding_asset(slot)
    except BrandingValidationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if asset is None:
        raise HTTPException(status_code=404, detail="브랜딩 로고를 찾을 수 없습니다")
    versioned = bool(v) and asset.sha256.startswith(v)
    if v is not None and not versioned:
        raise HTTPException(status_code=404, detail="브랜딩 로고 버전이 일치하지 않습니다")
    cache_control = "public, max-age=31536000, immutable" if versioned else "public, max-age=60"
    return Response(
        content=asset.content,
        media_type=asset.content_type,
        headers={
            "Cache-Control": cache_control,
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/admin/branding", response_model=BrandingStatusResponse, dependencies=[Depends(require_admin)])
async def get_site_branding_status():
    return await branding_admin_status(get_settings())


@router.post("/admin/branding/{slot}", response_model=BrandingStatusResponse, dependencies=[Depends(require_admin)])
async def upload_site_branding_asset(
    slot: str,
    file: UploadFile = File(...),
    token_info: dict = Depends(get_token_info),
):
    content = await file.read(MAX_BRANDING_UPLOAD_BYTES + 1)
    try:
        return await upsert_branding_asset(
            slot=slot,
            filename=file.filename,
            content=content,
            updated_by_user_id=token_info.get("user_id"),
            settings=get_settings(),
        )
    except BrandingValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except BrandingStorageUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.delete("/admin/branding/{slot}", response_model=BrandingStatusResponse, dependencies=[Depends(require_admin)])
async def reset_site_branding_asset(slot: str):
    try:
        return await delete_branding_asset(slot, get_settings())
    except BrandingValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except BrandingStorageUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
