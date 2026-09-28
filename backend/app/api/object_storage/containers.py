from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import openstack
import asyncio
import contextlib
import json
import logging
import queue as _queue_module
import secrets
import time
import urllib.parse

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.deps import CacheMode, cache_mode, get_os_conn, get_token_info
from app.models.storage import (
    BulkDeleteRequest,
    CopyObjectRequest,
    CreateContainerRequest,
    CreateDirectoryRequest,
    MoveObjectRequest,
    RenameObjectRequest,
)
from app.services import cache
from app.services.cache import invalidation, keys
from app.services.swift import InvalidObjectMove

router = APIRouter()
_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 휴지통 Redis 헬퍼 (소프트 삭제 버킷 추적)
# ---------------------------------------------------------------------------


def _trash_containers_key(pid: str) -> str:
    """프로젝트별 소프트 삭제 버킷을 저장하는 Redis sorted-set 키."""
    return f"afterglow:swift-trash:{pid}:containers"


async def _mark_container_deleted(pid: str, name: str, epoch: int, retention_days: int) -> None:
    """Redis sorted-set에 소프트 삭제 컨테이너 등록 (score = 삭제 epoch)."""
    from app.services.cache import _get_redis  # type: ignore[attr-defined]

    try:
        r = await _get_redis()
        tk = _trash_containers_key(pid)
        await r.zadd(tk, {name: float(epoch)})
        # TTL: 보관 기간 + 7일 여유
        await r.expire(tk, (retention_days + 7) * 86400)
    except Exception:
        _logger.warning("소프트 삭제 마킹 Redis 실패 pid=%s name=%s", pid, name, exc_info=True)


async def _unmark_container_deleted(pid: str, name: str) -> None:
    """Redis sorted-set에서 소프트 삭제 마킹 제거."""
    from app.services.cache import _get_redis  # type: ignore[attr-defined]

    try:
        r = await _get_redis()
        await r.zrem(_trash_containers_key(pid), name)
    except Exception:
        _logger.warning("소프트 삭제 마킹 제거 Redis 실패 pid=%s name=%s", pid, name, exc_info=True)


async def _get_deleted_containers(pid: str) -> dict[str, int]:
    """소프트 삭제된 컨테이너 {name: epoch} 딕셔너리 반환."""
    from app.services.cache import _get_redis  # type: ignore[attr-defined]

    try:
        r = await _get_redis()
        members = await r.zrange(_trash_containers_key(pid), 0, -1, withscores=True)
        result: dict[str, int] = {}
        for m, s in members:
            key_str = m.decode() if isinstance(m, bytes) else str(m)
            result[key_str] = int(s)
        return result
    except Exception:
        _logger.debug("소프트 삭제 목록 Redis 조회 실패 pid=%s", pid, exc_info=True)
        return {}


async def _is_container_deleted(pid: str, name: str) -> int | None:
    """컨테이너가 소프트 삭제 중이면 epoch 반환, 아니면 None."""
    from app.services.cache import _get_redis  # type: ignore[attr-defined]

    try:
        r = await _get_redis()
        score = await r.zscore(_trash_containers_key(pid), name)
        return int(score) if score is not None else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 휴지통 복구·영구삭제 요청 모델
# ---------------------------------------------------------------------------


class RestoreObjectRequest(BaseModel):
    trash_key: str


class RestoreContainerRequest(BaseModel):
    pass  # 이름은 URL path에서 수신


_EOF = object()


class _QueueIO:
    """async producer → sync consumer bridge: read(n) blocks until queue has enough data."""

    def __init__(self, q: _queue_module.Queue[object]) -> None:
        self._q = q
        self._buf = bytearray()
        self._done = False

    def read(self, n: int = -1) -> bytes:
        while not self._done and (n < 0 or len(self._buf) < n):
            item = self._q.get()
            if item is _EOF:
                self._done = True
                break
            self._buf.extend(item)  # type: ignore[arg-type]
        if n < 0 or len(self._buf) <= n:
            data = bytes(self._buf)
            self._buf = bytearray()
        else:
            data = bytes(self._buf[:n])
            del self._buf[:n]
        return data


async def _drain_to_queue(stream, q: _queue_module.Queue[object]) -> None:
    try:
        async for chunk in stream:
            await asyncio.to_thread(q.put, chunk)
    finally:
        try:
            await asyncio.to_thread(q.put, _EOF)
        except BaseException:
            pass


def _sanitize_object_name(name: str) -> str:
    """object key 정규화. 다음을 제거:

    - ASCII 제어문자 (0x00-0x1F) 와 DEL (0x7F)
    - path traversal segment (`.`, `..`)
    - leading/trailing slash, 연속 slash
    - max 1024자
    """
    # 1) 제어문자 + DEL + NUL 제거
    name = "".join(c for c in name if ord(c) >= 0x20 and ord(c) != 0x7F)
    # 2) segment-level 정규화: 빈/`.`/`..` segment 제거
    parts = [p for p in name.split("/") if p and p not in (".", "..")]
    name = "/".join(parts).strip() or "unnamed"
    return name[:1024]


# ---------------------------------------------------------------------------
# 계정 메타데이터
# ---------------------------------------------------------------------------


@router.get("/account")
async def get_object_storage_account(
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """현재 계정의 Swift 오브젝트 스토리지 사용량 메타데이터."""
    from app.services import swift

    try:
        return await asyncio.to_thread(swift.get_account_metadata, conn)
    except Exception:
        raise HTTPException(status_code=500, detail="오브젝트 스토리지 계정 정보 조회 실패")


# ---------------------------------------------------------------------------
# 컨테이너 목록 / 생성
# ---------------------------------------------------------------------------


async def _list_all_projects_containers(
    admin_token: str,
    include_quarantine: bool = False,
    include_trash: bool = False,
    include_deleted: bool = False,
) -> list[dict]:
    """모든 프로젝트로 fan-out 해서 Swift 컨테이너 집계 (asyncio.gather 병렬).

    include_quarantine=True 시 `*-quarantine` 버킷도 포함 (admin UI 모니터링 용).
    include_trash=True 시 `*-trash` 버킷도 포함.
    include_deleted=True 시 소프트 삭제 컨테이너에 is_deleted/deleted_at 필드 포함.
    프로젝트당 ~700ms × 9개 = 7초 sequential 동작을 ~1초 이내로 단축.
    Semaphore(8) 로 Keystone/RGW 동시 부하 제한.
    """
    from app.services import keystone, swift
    from app.services.swift import _is_unauthorized

    projects = await asyncio.to_thread(keystone.list_projects, admin_token)
    semaphore = asyncio.Semaphore(8)

    async def _one(p: dict) -> list[dict]:
        pid = p.get("id")
        if not pid:
            return []
        async with semaphore:
            try:
                sub_conn = await asyncio.to_thread(keystone.get_admin_connection_for_project, pid)
            except Exception as e:
                if _is_unauthorized(e):
                    _logger.info("프로젝트 %s 권한 없음 — skip", pid)
                else:
                    _logger.warning("프로젝트 %s connection 실패: %s", pid, e)
                return []
            try:
                containers = await asyncio.to_thread(swift.list_containers, sub_conn, include_quarantine, include_trash)
            except Exception as e:
                if _is_unauthorized(e):
                    _logger.info("프로젝트 %s 권한 없음 — skip", pid)
                else:
                    _logger.warning("프로젝트 %s 의 Swift 컨테이너 조회 실패: %s", pid, e)
                containers = []
            finally:
                with contextlib.suppress(Exception):
                    await asyncio.to_thread(sub_conn.close)

            # 소프트 삭제 정보 주석 처리 (캐시 뮤테이션 방지: 새 dict 복사본 생성)
            if containers:
                deleted_map = await _get_deleted_containers(pid)
                if include_deleted:
                    annotated = []
                    for c in containers:
                        epoch = deleted_map.get(c["name"])
                        if epoch:
                            annotated.append({**c, "is_deleted": True, "deleted_at": epoch})
                        else:
                            annotated.append(c)
                    containers = annotated
                else:
                    containers = [c for c in containers if c["name"] not in deleted_map]

            return [{**c, "project_id": pid, "project_name": p.get("name", "")} for c in containers]

    results = await asyncio.gather(*[_one(p) for p in projects])
    return [item for sublist in results for item in sublist]


@router.get("")
async def list_object_storage_containers(
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
    all_projects: bool = Query(False, description="admin 전용: 모든 프로젝트 버킷"),
    include_quarantine: bool = Query(False, description="admin 전용: *-quarantine 버킷 포함"),
    include_trash: bool = Query(False, description="admin 전용: *-trash 버킷 포함"),
    include_deleted: bool = Query(False, description="소프트 삭제 버킷 포함 (복구 대기 중인 버킷)"),
    cm: CacheMode = Depends(cache_mode),
):
    """Swift 오브젝트 스토리지 컨테이너 목록.

    all_projects/include_quarantine/include_trash 는 시스템 admin 전용.
    include_deleted 는 인증된 사용자 모두 사용 가능 (자신의 삭제 대기 버킷 조회).
    """
    from app.services import swift

    is_admin = token_info.get("is_system_admin", False)

    if (include_quarantine or include_trash) and not is_admin:
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")

    if all_projects:
        if not is_admin:
            raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
        try:
            return await _list_all_projects_containers(
                token_info["token"], include_quarantine, include_trash, include_deleted
            )
        except Exception:
            _logger.exception("관리자 Swift 버킷 전체 조회 실패")
            raise HTTPException(status_code=500, detail="오브젝트 스토리지 컨테이너 목록 조회 실패")

    pid = conn._afterglow_project_id
    # 파라미터 조합마다 별도 캐시 항목 사용
    cache_parts = []
    if include_quarantine:
        cache_parts.append("q")
    if include_trash:
        cache_parts.append("t")
    cache_sub = "|".join(cache_parts) or None
    key = keys.project_key("swift", pid, "containers", sub=cache_sub)
    try:
        containers = await cache.cached_call(
            key,
            cache.ttl_normal(),
            lambda: swift.list_containers(conn, include_quarantine, include_trash),
            enabled=cm.enabled,
            refresh=cm.refresh,
        )
    except Exception:
        raise HTTPException(status_code=500, detail="오브젝트 스토리지 컨테이너 목록 조회 실패")

    # 소프트 삭제 상태 주석 처리 (Redis 조회, 캐싱 미적용 — 상태 변경이 즉시 반영되어야 함)
    # 주의: 캐시된 dict 를 직접 변경하지 않도록 새 dict 복사본을 생성한다.
    deleted_map = await _get_deleted_containers(pid)
    if include_deleted:
        result = []
        for c in containers:
            epoch = deleted_map.get(c["name"])
            if epoch:
                result.append({**c, "is_deleted": True, "deleted_at": epoch})
            else:
                result.append(c)
        return result
    else:
        return [c for c in containers if c["name"] not in deleted_map]


@router.post("", status_code=201)
async def create_object_storage_container(
    req: CreateContainerRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """오브젝트 스토리지 컨테이너(버킷) 생성.

    이름 검증: bucket_naming.validate_bucket_name 으로 시스템 예약어 / S3 형식
    위반 차단. 위반 시 400 + 한국어 사유.
    소프트 삭제 대기 중인 동명 버킷이 있으면 409 반환 (복구 또는 영구 삭제 후 재생성 가능).
    """
    from app.services import swift
    from app.services.bucket_naming import validate_bucket_name

    try:
        validate_bucket_name(req.name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    pid = conn._afterglow_project_id
    # 소프트 삭제 대기 중인 동명 버킷 충돌 확인
    existing_epoch = await _is_container_deleted(pid, req.name)
    if existing_epoch is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"'{req.name}' 버킷은 삭제 대기 중입니다. 휴지통에서 복구하거나 영구 삭제 후 재생성할 수 있습니다."
            ),
        )

    try:
        result = await asyncio.to_thread(swift.create_container, conn, req.name)
    except Exception:
        _logger.exception("Swift 컨테이너 생성 실패: name=%s", req.name)
        raise HTTPException(status_code=500, detail="컨테이너 생성 실패")

    await cache.invalidate(f"afterglow:swift:{pid}:*")
    await invalidation.invalidate_mutation_count("swift", pid)
    return result


# ---------------------------------------------------------------------------
# 개별 컨테이너 — 상세 / 삭제
# ---------------------------------------------------------------------------


@router.get("/{container_name}")
async def get_object_storage_container(
    container_name: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    cm: CacheMode = Depends(cache_mode),
):
    """컨테이너 메타데이터(오브젝트 수, 바이트 등) 조회."""
    from app.services import swift

    pid = conn._afterglow_project_id
    key = keys.project_key("swift", pid, "containers", sub=container_name)
    try:
        return await cache.cached_call(
            key,
            cache.ttl_slow(),
            lambda: swift.get_container_metadata(conn, container_name),
            enabled=cm.enabled,
            refresh=cm.refresh,
        )
    except Exception:
        raise HTTPException(status_code=404, detail="컨테이너를 찾을 수 없습니다")


@router.delete("/{container_name}", status_code=204)
async def delete_object_storage_container(
    container_name: str,
    permanent: bool = Query(False, description="true 시 즉시 영구 삭제. 기본값은 30일 보관 후 자동 삭제."),
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """오브젝트 스토리지 컨테이너 삭제.

    기본(permanent=false): 소프트 삭제 — 설정된 보관 기간(기본 30일) 동안 복구 가능.
    permanent=true: 즉시 영구 삭제 (복구 불가).
    """
    from app.config import get_settings
    from app.services import swift

    pid = conn._afterglow_project_id

    if permanent:
        # 하드 삭제: 기존 동작 유지
        try:
            await asyncio.to_thread(swift.delete_container, conn, container_name)
        except Exception:
            raise HTTPException(status_code=500, detail="컨테이너 삭제 실패")
        # 혹시 소프트 삭제 마킹이 있었으면 제거
        await _unmark_container_deleted(pid, container_name)
    else:
        # 소프트 삭제: 메타데이터 마킹 + Redis 등록
        epoch = int(time.time())
        settings = get_settings()
        retention_days = settings.os_trash_retention_days
        try:
            await asyncio.to_thread(swift.soft_delete_container_metadata, conn, container_name, epoch)
        except Exception:
            _logger.warning("컨테이너 소프트 삭제 메타 설정 실패: %s", container_name, exc_info=True)
        await _mark_container_deleted(pid, container_name, epoch, retention_days)
        _logger.info("컨테이너 소프트 삭제: name=%s pid=%s", container_name, pid)

    await cache.invalidate(f"afterglow:swift:{pid}:*")
    await invalidation.invalidate_mutation_count("swift", pid)


# ---------------------------------------------------------------------------
# 오브젝트 목록 / 업로드
# ---------------------------------------------------------------------------


@router.get("/{container_name}/objects")
async def list_objects(
    container_name: str,
    prefix: str = Query(default=""),
    delimiter: str = Query(default="/"),
    conn: openstack.connection.Connection = Depends(get_os_conn),
    cm: CacheMode = Depends(cache_mode),
):
    """컨테이너 내 오브젝트 목록.

    delimiter="/"(기본값)를 사용하면 현재 prefix의 직속 파일과 서브디렉토리만 반환한다.
    delimiter=""로 요청하면 모든 오브젝트를 flat하게 반환한다.
    """
    from app.services import swift

    pid = conn._afterglow_project_id
    # prefix / delimiter 조합마다 별도 캐시 항목. 모두 afterglow:swift:{pid}:* 로 무효화됨.
    key = keys.project_key("swift", pid, "objects", sub=f"{container_name}:{prefix}:{delimiter}")
    try:
        return await cache.cached_call(
            key,
            cache.ttl_fast(),
            lambda: swift.list_objects(conn, container_name, prefix, delimiter),
            enabled=cm.enabled,
            refresh=cm.refresh,
        )
    except Exception:
        raise HTTPException(status_code=500, detail="오브젝트 목록 조회 실패")


@router.post("/{container_name}/objects", status_code=201)
async def upload_object(
    container_name: str,
    file: UploadFile,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """오브젝트 업로드 (multipart/form-data). 1 GiB 초과 시 Swift SLO 자동 적용."""
    from app.services import swift

    # 파일 크기 확인 (file.size가 없으면 seek으로 계산)
    if file.size is not None:
        file_size = file.size
    else:
        await file.seek(0, 2)
        file_size = await file.tell()
        await file.seek(0)

    try:
        object_name = _sanitize_object_name(file.filename or "unnamed")
        content_type = file.content_type or ""
        # file.file (SpooledTemporaryFile)을 직접 전달해 스트리밍 업로드
        result = await asyncio.to_thread(
            swift.upload_object,
            conn,
            container_name,
            object_name,
            file.file,
            content_type,
            file_size,
        )
    except HTTPException:
        raise
    except Exception:
        _logger.exception("오브젝트 업로드 실패: container=%s name=%s", container_name, file.filename)
        raise HTTPException(status_code=500, detail="오브젝트 업로드 실패")

    pid = conn._afterglow_project_id
    await cache.invalidate(f"afterglow:swift:{pid}:*")
    await invalidation.invalidate_mutation_count("swift", pid)
    return result


@router.put("/{container_name}/objects/{object_name:path}", status_code=201)
async def upload_object_stream(
    container_name: str,
    object_name: str,
    request: Request,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """streaming PUT — disk spool 없이 raw body 를 Swift 에 직접 forward.

    헤더: Content-Length (필수), Content-Type (선택).
    Content-Length > 1 GiB 이면 Swift SLO 자동 적용.
    """
    from app.services import swift

    cl = request.headers.get("content-length")
    if cl is None:
        raise HTTPException(status_code=411, detail="Content-Length 헤더 필수")
    try:
        file_size = int(cl)
    except ValueError:
        raise HTTPException(status_code=400, detail="Content-Length 값이 올바르지 않습니다")
    from app.config import get_settings as _get_settings

    _max_gb = _get_settings().app_max_upload_gb
    if _max_gb > 0 and file_size > _max_gb * 1024**3:
        raise HTTPException(
            status_code=413,
            detail=f"파일 크기는 {_max_gb} GB를 초과할 수 없습니다",
        )

    content_type = request.headers.get("content-type", "application/octet-stream")
    sanitized_name = _sanitize_object_name(object_name)

    _q: _queue_module.Queue[object] = _queue_module.Queue(maxsize=4)
    drain_task = asyncio.create_task(_drain_to_queue(request.stream(), _q))
    try:
        result = await asyncio.to_thread(
            swift.upload_object,
            conn,
            container_name,
            sanitized_name,
            _QueueIO(_q),
            content_type,
            file_size,
        )
    except HTTPException:
        raise
    except Exception as _exc:
        import openstack.exceptions as _oe

        if isinstance(_exc, _oe.HttpException):
            _detail = getattr(_exc, "details", None) or getattr(_exc, "message", None) or str(_exc)
            _sc = getattr(_exc, "status_code", None) or 500
            _sc = int(_sc) if isinstance(_sc, (int, str)) and str(_sc).isdigit() else 500
            _sc = _sc if 400 <= _sc < 600 else 500
            _logger.error(
                "스트리밍 업로드 swift 오류: container=%s name=%s status=%d detail=%s",
                container_name,
                sanitized_name,
                _sc,
                _detail,
            )
            raise HTTPException(status_code=_sc, detail=f"swift 오류: {_detail}")
        _logger.exception("스트리밍 업로드 실패: container=%s name=%s", container_name, sanitized_name)
        raise HTTPException(status_code=500, detail=f"오브젝트 업로드 실패: {type(_exc).__name__}: {_exc}")
    finally:
        drain_task.cancel()
        while not _q.empty():
            try:
                _q.get_nowait()
            except _queue_module.Empty:
                break
        with contextlib.suppress(asyncio.CancelledError):
            await drain_task

    pid = conn._afterglow_project_id
    await cache.invalidate(f"afterglow:swift:{pid}:*")
    await invalidation.invalidate_mutation_count("swift", pid)
    return result


# ---------------------------------------------------------------------------
# 개별 오브젝트 — 다운로드 / 삭제 / 메타데이터
# (오브젝트 이름에 '/' 포함 가능 → :path 타입 사용)
# ---------------------------------------------------------------------------


def _make_content_disposition(disposition: str, object_name: str) -> str:
    """RFC 5987 형식의 Content-Disposition 값 생성. 한글 파일명을 올바르게 처리."""
    raw_name = object_name.split("/")[-1]
    quoted = urllib.parse.quote(raw_name, safe="")
    ascii_fallback = raw_name.encode("ascii", "replace").decode("ascii").replace("?", "_")
    return f"{disposition}; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quoted}"


async def _resolve_swift_conn(
    dl_token: str | None,
    container_name: str,
    object_name: str,
) -> openstack.connection.Connection:
    """단발 다운로드 토큰으로 OpenStack 연결을 반환."""
    from app.services import keystone as ks
    from app.services.cache import _get_redis

    if dl_token:
        r = await _get_redis()
        payload_str = await r.getdel(f"dl-token:{dl_token}")
        if payload_str is None:
            raise HTTPException(status_code=403, detail="유효하지 않거나 만료된 다운로드 토큰입니다")
        payload = json.loads(payload_str)
        if payload["container_name"] != container_name or payload["object_name"] != object_name:
            raise HTTPException(status_code=403, detail="토큰이 요청한 리소스와 일치하지 않습니다")
        return await asyncio.to_thread(ks.get_openstack_connection, payload["openstack_token"], payload["project_id"])

    raise HTTPException(
        status_code=403, detail="다운로드 토큰이 필요합니다. /download-token 엔드포인트를 먼저 호출하세요."
    )


@router.post("/{container_name}/objects/{object_name:path}/download-token", status_code=200)
async def issue_download_token(
    container_name: str,
    object_name: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """단발 다운로드 토큰 발급 (TTL 60초, 1회 사용). 브라우저 네이티브 다운로더 지원."""
    from app.services.cache import _get_redis

    token = secrets.token_urlsafe(32)
    payload = json.dumps(
        {
            "openstack_token": conn._afterglow_token,
            "project_id": conn._afterglow_project_id,
            "container_name": container_name,
            "object_name": object_name,
        }
    )
    r = await _get_redis()
    await r.set(f"dl-token:{token}", payload, ex=60)

    encoded_container = urllib.parse.quote(container_name, safe="")
    encoded_object = "/".join(urllib.parse.quote(p, safe="") for p in object_name.split("/"))
    url = f"/api/v1/object-storage/{encoded_container}/objects/{encoded_object}/download?token={token}"
    return {"url": url, "expires_in": 60}


@router.get("/{container_name}/objects/{object_name:path}/download")
async def download_object(
    container_name: str,
    object_name: str,
    dl_token: str | None = Query(None, alias="token"),
):
    """오브젝트 스트리밍 다운로드. 단발 토큰(?token=) 인증."""
    from app.services import swift

    conn = await _resolve_swift_conn(dl_token, container_name, object_name)
    try:
        chunks, content_type, content_length = await asyncio.to_thread(
            swift.stream_object, conn, container_name, object_name
        )
        headers: dict[str, str] = {
            "Content-Disposition": _make_content_disposition("attachment", object_name),
        }
        if content_length:
            headers["Content-Length"] = str(content_length)

        sentinel = object()

        def _next_chunk():
            return next(chunks, sentinel)

        async def _iter():
            while True:
                chunk = await asyncio.to_thread(_next_chunk)
                if chunk is sentinel:
                    break
                yield chunk

        return StreamingResponse(_iter(), media_type=content_type, headers=headers)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=404, detail="오브젝트를 찾을 수 없습니다")
    finally:
        await asyncio.to_thread(conn.close)


@router.delete("/{container_name}/objects/{object_name:path}", status_code=204)
async def delete_object(
    container_name: str,
    object_name: str,
    permanent: bool = Query(False, description="true 시 즉시 영구 삭제. 기본값은 휴지통으로 이동."),
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """오브젝트 삭제.

    기본(permanent=false): 소프트 삭제 — {container}-trash 버킷으로 이동, 보관 기간 내 복구 가능.
    permanent=true: 즉시 영구 삭제 (복구 불가).
    """
    from app.services import swift

    pid = conn._afterglow_project_id
    try:
        if permanent:
            await asyncio.to_thread(swift.delete_object, conn, container_name, object_name)
        else:
            await asyncio.to_thread(swift.soft_delete_object, conn, container_name, object_name)
    except Exception:
        raise HTTPException(status_code=500, detail="오브젝트 삭제 실패")

    await cache.invalidate(f"afterglow:swift:{pid}:*")
    await invalidation.invalidate_mutation_count("swift", pid)


@router.get("/{container_name}/objects/{object_name:path}/metadata")
async def get_object_metadata(
    container_name: str,
    object_name: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """오브젝트 상세 메타데이터."""
    from app.services import swift

    try:
        return await asyncio.to_thread(swift.get_object_metadata, conn, container_name, object_name)
    except Exception:
        raise HTTPException(status_code=404, detail="오브젝트를 찾을 수 없습니다")


@router.get("/{container_name}/objects/{object_name:path}/preview")
async def preview_object(
    container_name: str,
    object_name: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """오브젝트 인라인 미리보기 (Content-Disposition: inline)."""
    from app.services import swift

    try:
        chunks, content_type, content_length = await asyncio.to_thread(
            swift.stream_object, conn, container_name, object_name
        )
        headers: dict[str, str] = {
            "Content-Disposition": _make_content_disposition("inline", object_name),
        }
        if content_length:
            headers["Content-Length"] = str(content_length)

        sentinel = object()

        def _next_chunk():
            return next(chunks, sentinel)

        async def _iter():
            while True:
                chunk = await asyncio.to_thread(_next_chunk)
                if chunk is sentinel:
                    break
                yield chunk

        return StreamingResponse(_iter(), media_type=content_type, headers=headers)
    except Exception:
        raise HTTPException(status_code=404, detail="오브젝트를 찾을 수 없습니다")


# ---------------------------------------------------------------------------
# 일괄 삭제
# ---------------------------------------------------------------------------


@router.post("/{container_name}/objects/bulk-delete", status_code=200)
async def bulk_delete_objects(
    container_name: str,
    body: BulkDeleteRequest,
    permanent: bool = Query(False, description="true 시 즉시 영구 삭제. 기본값은 휴지통으로 이동."),
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """오브젝트 일괄 삭제.

    recursive=True이면 디렉토리(`/`로 끝나는) 하위 전체를 삭제한다.
    permanent=false(기본): 휴지통으로 이동. permanent=true: 즉시 영구 삭제.
    반환: {"deleted": [...], "failed": [{"name": ..., "error": ...}]}
    """
    from app.services import swift

    try:
        if permanent:
            result = await asyncio.to_thread(
                swift.bulk_delete_objects, conn, container_name, body.objects, body.recursive
            )
            result = {"deleted": result.get("deleted", []), "failed": result.get("failed", [])}
        else:
            result = await asyncio.to_thread(
                swift.bulk_soft_delete_objects, conn, container_name, body.objects, body.recursive
            )
            result = {"deleted": result.get("moved", []), "failed": result.get("failed", [])}
    except Exception:
        raise HTTPException(status_code=500, detail="일괄 삭제 실패")

    pid = conn._afterglow_project_id
    await cache.invalidate(f"afterglow:swift:{pid}:*")
    await invalidation.invalidate_mutation_count("swift", pid)
    return result


# ---------------------------------------------------------------------------
# 디렉토리 / 복사 / 이동 / 이름 변경
# ---------------------------------------------------------------------------


@router.post("/{container_name}/objects/directory", status_code=201)
async def create_directory(
    container_name: str,
    body: CreateDirectoryRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """가상 디렉토리 생성."""
    from app.services import swift

    try:
        result = await asyncio.to_thread(swift.create_directory, conn, container_name, body.path)
    except Exception:
        _logger.exception("디렉토리 생성 실패: container=%s path=%s", container_name, body.path)
        raise HTTPException(status_code=500, detail="디렉토리 생성 실패")

    pid = conn._afterglow_project_id
    await cache.invalidate(f"afterglow:swift:{pid}:*")
    await invalidation.invalidate_mutation_count("swift", pid)
    return result


@router.post("/{container_name}/objects/copy", status_code=200)
async def copy_object(
    container_name: str,
    body: CopyObjectRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """오브젝트 복사."""
    from app.services import swift

    dest_container = body.dest_container or container_name
    try:
        result = await asyncio.to_thread(
            swift.copy_object, conn, container_name, body.source, dest_container, body.destination
        )
    except Exception:
        _logger.exception("오브젝트 복사 실패: %s -> %s", body.source, body.destination)
        raise HTTPException(status_code=500, detail="오브젝트 복사 실패")

    pid = conn._afterglow_project_id
    await cache.invalidate(f"afterglow:swift:{pid}:*")
    await invalidation.invalidate_mutation_count("swift", pid)
    return result


@router.post("/{container_name}/objects/move", status_code=200)
async def move_object(
    container_name: str,
    body: MoveObjectRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """오브젝트 이동.

    destination이 "/"로 끝나는 디렉토리 경로인 경우 원본 파일명을 자동으로 추가한다.
    예: source="a/b.txt", destination="folder/" → dest_name="folder/b.txt"
    """
    from app.services import swift

    dest_container = body.dest_container or container_name
    dest_name = body.destination
    # 디렉토리 경로로 이동할 경우 원본 파일명 유지
    if dest_name.endswith("/"):
        original_filename = body.source.rsplit("/", 1)[-1]
        dest_name = dest_name + original_filename
    try:
        result = await asyncio.to_thread(
            swift.move_object, conn, container_name, body.source, dest_container, dest_name
        )
    except InvalidObjectMove as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        _logger.exception("오브젝트 이동 실패: %s -> %s", body.source, body.destination)
        raise HTTPException(status_code=500, detail="오브젝트 이동 실패")

    pid = conn._afterglow_project_id
    await cache.invalidate(f"afterglow:swift:{pid}:*")
    await invalidation.invalidate_mutation_count("swift", pid)
    return result


@router.post("/{container_name}/objects/rename", status_code=200)
async def rename_object(
    container_name: str,
    body: RenameObjectRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """오브젝트 이름 변경."""
    from app.services import swift

    try:
        result = await asyncio.to_thread(swift.rename_object, conn, container_name, body.source, body.new_name)
    except InvalidObjectMove as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        _logger.exception("오브젝트 이름 변경 실패: %s -> %s", body.source, body.new_name)
        raise HTTPException(status_code=500, detail="오브젝트 이름 변경 실패")

    pid = conn._afterglow_project_id
    await cache.invalidate(f"afterglow:swift:{pid}:*")
    await invalidation.invalidate_mutation_count("swift", pid)
    return result


# ---------------------------------------------------------------------------
# 휴지통 — 오브젝트 단위
# ---------------------------------------------------------------------------


@router.get("/{container_name}/trash", status_code=200)
async def list_trash(
    container_name: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """버킷 휴지통({container}-trash)의 오브젝트 목록.

    각 항목에 trash_key, original_name, deleted_at(epoch_seconds) 포함.
    """
    from app.services import swift

    try:
        return await asyncio.to_thread(swift.list_trash_objects, conn, container_name)
    except Exception:
        _logger.exception("휴지통 목록 조회 실패: container=%s", container_name)
        raise HTTPException(status_code=500, detail="휴지통 목록 조회 실패")


@router.post("/{container_name}/trash/restore", status_code=200)
async def restore_trash_object(
    container_name: str,
    body: RestoreObjectRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """휴지통 오브젝트를 원본 버킷으로 복구.

    body: {"trash_key": "{epoch}/{uuid8}/{original_name}"}
    """
    from app.services import swift

    try:
        result = await asyncio.to_thread(swift.restore_trash_object, conn, container_name, body.trash_key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        _logger.exception("휴지통 오브젝트 복구 실패: container=%s key=%s", container_name, body.trash_key)
        raise HTTPException(status_code=500, detail="오브젝트 복구 실패")

    pid = conn._afterglow_project_id
    await cache.invalidate(f"afterglow:swift:{pid}:*")
    await invalidation.invalidate_mutation_count("swift", pid)
    return result


@router.delete("/{container_name}/trash/{trash_key:path}", status_code=204)
async def purge_trash_object(
    container_name: str,
    trash_key: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """휴지통 오브젝트를 영구 삭제 (복구 불가)."""
    from app.services import swift

    try:
        await asyncio.to_thread(swift.purge_trash_object, conn, container_name, trash_key)
    except Exception:
        _logger.exception("휴지통 오브젝트 영구 삭제 실패: container=%s key=%s", container_name, trash_key)
        raise HTTPException(status_code=500, detail="영구 삭제 실패")

    pid = conn._afterglow_project_id
    await cache.invalidate(f"afterglow:swift:{pid}:*")
    await invalidation.invalidate_mutation_count("swift", pid)


# ---------------------------------------------------------------------------
# 휴지통 — 버킷(컨테이너) 단위
# ---------------------------------------------------------------------------


@router.get("/trash/containers", status_code=200)
async def list_deleted_containers(
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """소프트 삭제 대기 중인 버킷 목록 (복구 가능한 버킷).

    Redis sorted-set 기반으로 빠르게 반환.
    """
    from app.services import swift

    pid = conn._afterglow_project_id
    deleted_map = await _get_deleted_containers(pid)
    if not deleted_map:
        return []

    # Swift 기본 목록 조회 후 소프트 삭제 항목만 필터
    try:
        all_containers = await asyncio.to_thread(swift.list_containers, conn, False, False)
    except Exception:
        all_containers = []

    container_map = {c["name"]: c for c in all_containers}
    result = []
    for name, epoch in deleted_map.items():
        base = container_map.get(name, {"name": name, "count": 0, "bytes": 0})
        result.append({**base, "is_deleted": True, "deleted_at": epoch})
    return result


@router.post("/trash/containers/{container_name}/restore", status_code=200)
async def restore_deleted_container(
    container_name: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """소프트 삭제된 버킷을 복구 (목록에서 다시 보이도록)."""
    from app.services import swift

    pid = conn._afterglow_project_id

    # 소프트 삭제 상태인지 확인
    epoch = await _is_container_deleted(pid, container_name)
    if epoch is None:
        raise HTTPException(status_code=404, detail="삭제 대기 중인 버킷을 찾을 수 없습니다")

    try:
        await asyncio.to_thread(swift.restore_container_metadata, conn, container_name)
    except Exception:
        _logger.warning("컨테이너 복구 메타 해제 실패: %s", container_name, exc_info=True)

    await _unmark_container_deleted(pid, container_name)

    await cache.invalidate(f"afterglow:swift:{pid}:*")
    await invalidation.invalidate_mutation_count("swift", pid)

    return {"name": container_name, "restored": True}


@router.delete("/trash/containers/{container_name}", status_code=204)
async def purge_deleted_container(
    container_name: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """소프트 삭제된 버킷을 영구 삭제 (내용물 포함, 복구 불가)."""
    from app.services import swift

    pid = conn._afterglow_project_id

    # 소프트 삭제 상태인지 확인
    epoch = await _is_container_deleted(pid, container_name)
    if epoch is None:
        raise HTTPException(status_code=404, detail="삭제 대기 중인 버킷을 찾을 수 없습니다")

    try:
        await asyncio.to_thread(swift.delete_container, conn, container_name)
    except Exception:
        _logger.exception("소프트 삭제 버킷 영구 삭제 실패: %s", container_name)
        raise HTTPException(status_code=500, detail="버킷 영구 삭제 실패")

    await _unmark_container_deleted(pid, container_name)

    await cache.invalidate(f"afterglow:swift:{pid}:*")
    await invalidation.invalidate_mutation_count("swift", pid)
