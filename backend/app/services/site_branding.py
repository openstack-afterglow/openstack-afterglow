from __future__ import annotations

import hashlib
from pathlib import PurePath
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings, get_settings
from app.database import get_session_factory, is_db_available, mark_db_unhealthy
from app.models.db import SiteBrandingAsset
from app.services.mcp_control_plane.oauth import McpOAuthError, canonical_mcp_resource_url

MAX_BRANDING_UPLOAD_BYTES = 1_048_576

BRANDING_SLOTS: dict[str, dict[str, str]] = {
    "logo_light": {
        "field": "logo_light_path",
        "label": "Dark-background login logo",
        "description": "Light logo shown on the default dark login background.",
    },
    "logo_dark": {
        "field": "logo_dark_path",
        "label": "Light-background login logo",
        "description": "Dark logo shown when the resolved UI theme is light.",
    },
}

_IMAGE_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)


class BrandingValidationError(ValueError):
    pass


class BrandingStorageUnavailable(RuntimeError):
    pass


def validate_branding_slot(slot: str) -> str:
    if slot not in BRANDING_SLOTS:
        allowed = ", ".join(sorted(BRANDING_SLOTS))
        raise BrandingValidationError(f"지원하지 않는 브랜딩 슬롯입니다: {slot}. 허용: {allowed}")
    return slot


def detect_raster_content_type(content: bytes) -> str:
    for prefix, content_type in _IMAGE_MAGIC:
        if content.startswith(prefix):
            return content_type
    if len(content) >= 12 and content[0:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    raise BrandingValidationError("PNG, JPEG, WebP, GIF 이미지 파일만 업로드할 수 있습니다")


def validate_branding_upload(content: bytes) -> str:
    if not content:
        raise BrandingValidationError("빈 파일은 업로드할 수 없습니다")
    if len(content) > MAX_BRANDING_UPLOAD_BYTES:
        raise BrandingValidationError("로고 파일은 1 MiB 이하여야 합니다")
    return detect_raster_content_type(content)


def safe_filename(filename: str | None, content_type: str) -> str:
    name = PurePath(filename or "logo").name.strip().replace("\x00", "")
    if name in {"", ".", ".."}:
        extension = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/webp": ".webp",
            "image/gif": ".gif",
        }.get(content_type, "")
        return f"logo{extension}"
    return name[:255]


def _normalized_http_origin(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return ""
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return ""
        host = parsed.hostname
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        port = parsed.port
    except ValueError:
        return ""
    netloc = host if port is None else f"{host}:{port}"
    return f"{parsed.scheme}://{netloc}"


def _asset_url(slot: str, asset: SiteBrandingAsset, settings: Settings) -> str:
    path = f"/api/v1/site-config/assets/{slot}?v={asset.sha256[:12]}"
    origin = _normalized_http_origin(settings.public_api_base)
    return f"{origin}{path}" if origin else path


def _mcp_url(settings: Settings) -> str:
    if settings.mcp_public_url:
        try:
            return canonical_mcp_resource_url(settings.mcp_public_url, production=False)
        except McpOAuthError:
            return ""
    return f"{settings.public_api_base.rstrip('/')}/api/v1/mcp" if settings.public_api_base else ""


def configured_public_site_config(settings: Settings | None = None) -> dict[str, Any]:
    s = settings or get_settings()
    return {
        "site_name": s.site_name,
        "site_description": s.site_description,
        "logo_path": s.logo_path,
        "logo_dark_path": s.logo_dark_path,
        "logo_light_path": s.logo_light_path,
        "favicon_path": s.favicon_path,
        "mcp_url": _mcp_url(s),
        "services": {
            "magnum": s.service_magnum_enabled,
            "manila": s.service_manila_enabled,
            "zun": s.service_zun_enabled,
            "cloud_shell": bool(s.service_cloud_shell_enabled and s.service_zun_enabled),
            "k3s": s.service_k3s_enabled,
            "trove": s.service_trove_enabled,
            "swift": s.service_swift_enabled,
            "barbican": s.service_barbican_enabled,
            "waygate": bool(s.service_waygate_enabled),
            "palimpsest": bool(s.service_palimpsest_enabled),
            "chat": bool(s.service_chat_enabled),
            "mcp": bool(s.service_mcp_enabled),
        },
    }


def _asset_summary(asset: SiteBrandingAsset | None, settings: Settings) -> dict[str, Any] | None:
    if asset is None:
        return None
    return {
        "slot": asset.slot,
        "filename": asset.filename,
        "content_type": asset.content_type,
        "size_bytes": asset.size_bytes,
        "sha256": asset.sha256,
        "url": _asset_url(asset.slot, asset, settings),
        "updated_at": asset.updated_at.isoformat(),
        "updated_by_user_id": asset.updated_by_user_id,
    }


async def _load_assets_by_slot() -> dict[str, SiteBrandingAsset]:
    if not is_db_available():
        return {}
    factory = get_session_factory()
    if factory is None:
        return {}
    async with factory() as session:
        rows = (
            (await session.execute(select(SiteBrandingAsset).where(SiteBrandingAsset.slot.in_(tuple(BRANDING_SLOTS)))))
            .scalars()
            .all()
        )
    return {row.slot: row for row in rows}


async def effective_public_site_config(settings: Settings | None = None) -> dict[str, Any]:
    s = settings or get_settings()
    result = configured_public_site_config(s)
    try:
        assets = await _load_assets_by_slot()
    except SQLAlchemyError:
        mark_db_unhealthy()
        return result
    for slot, asset in assets.items():
        field = BRANDING_SLOTS[slot]["field"]
        result[field] = _asset_url(slot, asset, s)
    return result


async def branding_admin_status(settings: Settings | None = None) -> dict[str, Any]:
    s = settings or get_settings()
    effective = await effective_public_site_config(s)
    assets: dict[str, dict[str, Any] | None] = {slot: None for slot in BRANDING_SLOTS}
    try:
        rows = await _load_assets_by_slot()
    except SQLAlchemyError:
        mark_db_unhealthy()
        rows = {}
    for slot in BRANDING_SLOTS:
        assets[slot] = _asset_summary(rows.get(slot), s)
    return {
        "slots": BRANDING_SLOTS,
        "effective": {
            "logo_path": effective["logo_path"],
            "logo_dark_path": effective["logo_dark_path"],
            "logo_light_path": effective["logo_light_path"],
        },
        "assets": assets,
    }


async def get_branding_asset(slot: str) -> SiteBrandingAsset | None:
    validate_branding_slot(slot)
    if not is_db_available():
        return None
    factory = get_session_factory()
    if factory is None:
        return None
    try:
        async with factory() as session:
            return (
                await session.execute(select(SiteBrandingAsset).where(SiteBrandingAsset.slot == slot))
            ).scalar_one_or_none()
    except SQLAlchemyError:
        mark_db_unhealthy()
        return None


def _require_session_factory():
    if not is_db_available():
        raise BrandingStorageUnavailable("DB를 사용할 수 없습니다")
    factory = get_session_factory()
    if factory is None:
        raise BrandingStorageUnavailable("DB 연결이 초기화되지 않았습니다")
    return factory


async def upsert_branding_asset(
    *,
    slot: str,
    filename: str | None,
    content: bytes,
    updated_by_user_id: str | None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    validate_branding_slot(slot)
    content_type = validate_branding_upload(content)
    digest = hashlib.sha256(content).hexdigest()
    stored_filename = safe_filename(filename, content_type)
    factory = _require_session_factory()

    try:
        async with factory() as session, session.begin():
            row = (
                await session.execute(select(SiteBrandingAsset).where(SiteBrandingAsset.slot == slot))
            ).scalar_one_or_none()
            if row is None:
                row = SiteBrandingAsset(slot=slot)
                session.add(row)
            row.filename = stored_filename
            row.content_type = content_type
            row.size_bytes = len(content)
            row.sha256 = digest
            row.content = content
            row.updated_by_user_id = updated_by_user_id
    except SQLAlchemyError as exc:
        mark_db_unhealthy()
        raise BrandingStorageUnavailable("브랜딩 로고를 저장할 수 없습니다") from exc
    return await branding_admin_status(settings)


async def delete_branding_asset(slot: str, settings: Settings | None = None) -> dict[str, Any]:
    validate_branding_slot(slot)
    factory = _require_session_factory()
    try:
        async with factory() as session, session.begin():
            row = (
                await session.execute(select(SiteBrandingAsset).where(SiteBrandingAsset.slot == slot))
            ).scalar_one_or_none()
            if row is not None:
                await session.delete(row)
    except SQLAlchemyError as exc:
        mark_db_unhealthy()
        raise BrandingStorageUnavailable("브랜딩 로고를 초기화할 수 없습니다") from exc
    return await branding_admin_status(settings)
