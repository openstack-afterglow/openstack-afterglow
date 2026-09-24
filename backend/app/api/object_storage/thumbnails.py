"""Authenticated thumbnail endpoint for the object browser grid."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import openstack

from fastapi import APIRouter, Depends, HTTPException, Response

from app.api.deps import get_os_conn
from app.services import cache, thumbnails

router = APIRouter(tags=["object-storage"])
_logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = thumbnails.CACHE_TTL_SECONDS
_BROWSER_CACHE_SECONDS = 3600


@router.get("/{container_name}/objects/{object_name:path}/thumbnail")
async def get_object_thumbnail(
    container_name: str,
    object_name: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
) -> Response:
    """Render a bounded WebP preview of an image or PDF the caller can already read."""
    from app.services import swift

    try:
        meta = await asyncio.to_thread(swift.get_object_metadata, conn, container_name, object_name)
    except Exception:
        raise HTTPException(status_code=404, detail="오브젝트를 찾을 수 없습니다")

    content_type = (meta.get("content_type") or "").split(";", 1)[0].strip().lower()
    size = int(meta.get("bytes") or 0)
    if content_type not in thumbnails.THUMBNAILABLE_TYPES:
        raise HTTPException(status_code=415, detail="미리보기를 지원하지 않는 형식입니다")
    if size > thumbnails.MAX_SOURCE_BYTES:
        raise HTTPException(status_code=413, detail="미리보기 생성 크기 제한(64MB)을 초과했습니다")

    etag = str(meta.get("etag") or "")
    identity = hashlib.sha256(f"{container_name}\0{object_name}\0{etag}".encode()).hexdigest()
    key = cache.keys.project_key("swift", conn._afterglow_project_id, "thumbnail", sub=identity)

    cached = None
    try:
        redis = await cache._get_redis()
        cached = await redis.get(key)
    except Exception:
        _logger.warning("thumbnail 캐시 조회 실패", exc_info=True)
        redis = None
    if cached:
        return _webp_response(base64.b64decode(cached), etag)

    data = await asyncio.to_thread(_read_object, conn, container_name, object_name)
    if data is None:
        raise HTTPException(status_code=413, detail="미리보기 생성 크기 제한(64MB)을 초과했습니다")
    thumbnail = await asyncio.to_thread(thumbnails.render_thumbnail, data, content_type)
    if thumbnail is None:
        raise HTTPException(status_code=422, detail="미리보기를 생성할 수 없습니다")

    if redis is not None:
        try:
            await redis.set(key, base64.b64encode(thumbnail).decode(), ex=_CACHE_TTL_SECONDS)
        except Exception:
            _logger.warning("thumbnail 캐시 저장 실패", exc_info=True)
    return _webp_response(thumbnail, etag)


def _read_object(conn, container_name: str, object_name: str) -> bytes | None:
    from app.services import swift

    chunks, _content_type, _length = swift.stream_object(conn, container_name, object_name)
    buffer = bytearray()
    for chunk in chunks:
        buffer.extend(chunk)
        if len(buffer) > thumbnails.MAX_SOURCE_BYTES:
            return None
    return bytes(buffer)


def _webp_response(payload: bytes, etag: str) -> Response:
    headers = {"Cache-Control": f"private, max-age={_BROWSER_CACHE_SECONDS}"}
    if etag:
        headers["ETag"] = f'"{etag}"'
    return Response(content=payload, media_type="image/webp", headers=headers)
