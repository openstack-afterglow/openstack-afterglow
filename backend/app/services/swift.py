"""Swift / Ceph RGW (Object Storage) 서비스 래퍼.

openstacksdk의 conn.object_store 프록시를 사용.
서비스가 없거나 오류 시 빈 목록/기본값을 반환하여 optional 서비스로 동작.

주의: Swift "컨테이너"는 오브젝트 스토리지 버킷을 의미.
Zun "컨테이너"와 혼동 방지를 위해 변수/응답 키에 object_storage_ 접두어 사용.
"""

from __future__ import annotations

import concurrent.futures
import contextlib
import logging
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

_logger = logging.getLogger(__name__)


def _get_swift_endpoint(conn) -> str | None:
    """afterglow.conf swift_endpoint 오버라이드가 있으면 반환, 없으면 None."""
    from app.config import get_settings

    settings = get_settings()
    endpoint = getattr(settings, "os_swift_endpoint", "")
    if endpoint:
        return endpoint.rstrip("/")
    return None


def _is_account_not_found(exc: Exception) -> bool:
    """Ceph RGW에서 Swift 계정이 초기화되지 않은 경우 404를 반환하는지 확인."""
    from openstack.exceptions import ResourceNotFound

    return isinstance(exc, ResourceNotFound) or (hasattr(exc, "status_code") and getattr(exc, "status_code", 0) == 404)


def _is_unauthorized(exc: Exception) -> bool:
    """Keystone/Swift 401 Unauthorized 검사.

    admin fan-out 시 일부 프로젝트에 admin role 이 없으면 Keystone rescope 가
    Unauthorized raise. traceback 출력하지 않고 info 로 swallow 하기 위해 분기.
    """
    try:
        from keystoneauth1.exceptions.http import Unauthorized

        if isinstance(exc, Unauthorized):
            return True
    except ImportError:
        pass
    status = getattr(exc, "http_status", None) or getattr(exc, "status_code", None)
    return status == 401


def _apply_endpoint_override(conn) -> None:
    """swift_endpoint 오버라이드가 설정된 경우 openstacksdk object_store proxy에 적용."""
    override = _get_swift_endpoint(conn)
    if override:
        conn.object_store._endpoint_override = override
        _logger.debug("Swift endpoint override 적용: %s", override)


def list_containers(
    conn,
    include_quarantine: bool = False,
    include_trash: bool = False,
) -> list[dict]:
    """현재 계정의 오브젝트 스토리지 컨테이너(버킷) 목록 반환.

    include_quarantine=True 시 `*-quarantine` 버킷도 포함하고 결과에
    `is_quarantine: True` 필드 표시. admin 모니터링 용도.
    include_trash=True 시 `*-trash` 버킷도 포함하고 결과에
    `is_trash: True` 필드 표시. admin 모니터링 용도.
    `_segments` 는 항상 숨김(원본 bytes 에 합산).
    소프트 삭제(is_deleted) 마킹은 호출자(API handler)가 Redis 조회 후 처리한다.
    """
    _apply_endpoint_override(conn)
    try:
        project_id = getattr(conn, "_afterglow_project_id", "unknown")
        try:
            endpoint = conn.object_store.get_endpoint()
        except Exception:
            endpoint = "(resolve failed)"
        _logger.info("Swift list_containers: project_id=%s endpoint=%s", project_id, endpoint)

        # SLO segment 컨테이너({name}_segments)는 사용자 목록에서 숨기고,
        # 그 bytes 는 원본 컨테이너에 합산해서 표시.
        all_containers = list(conn.object_store.containers())
        seg_bytes_by_origin: dict[str, int] = {}
        for c in all_containers:
            cname = c.name or ""
            if cname.endswith("_segments"):
                origin = cname[: -len("_segments")]
                seg_bytes_by_origin[origin] = seg_bytes_by_origin.get(origin, 0) + (getattr(c, "bytes", 0) or 0)

        result = []
        for c in all_containers:
            cname = c.name or ""
            if cname.endswith("_segments"):
                continue
            is_quarantine = cname.endswith("-quarantine")
            if is_quarantine and not include_quarantine:
                continue
            is_trash = cname.endswith("-trash")
            if is_trash and not include_trash:
                continue
            base_bytes = getattr(c, "bytes", 0) or 0
            entry = {
                "name": cname,
                "count": getattr(c, "count", 0) or 0,
                "bytes": base_bytes + seg_bytes_by_origin.get(cname, 0),
            }
            if is_quarantine:
                entry["is_quarantine"] = True
            if is_trash:
                entry["is_trash"] = True
            result.append(entry)
        _logger.info(
            "Swift 컨테이너 목록 조회: %d개 (quarantine=%s, trash=%s)",
            len(result),
            include_quarantine,
            include_trash,
        )
        return result
    except Exception as exc:
        if _is_account_not_found(exc):
            _logger.info("Swift 계정 미초기화 (404) — 빈 목록 반환")
        elif _is_unauthorized(exc):
            _logger.info("Swift 401 Unauthorized — 권한 없음, 빈 목록 반환")
        else:
            _logger.warning("Swift 컨테이너 목록 조회 실패", exc_info=True)
        return []


def count_containers(conn, *, timeout: float | int | None = None) -> int:
    """현재 계정의 오브젝트 스토리지 컨테이너 수 반환."""
    _apply_endpoint_override(conn)
    try:
        kwargs: dict[str, Any] = {"connect_retries": 0, "raise_exc": True}
        if timeout is not None:
            kwargs["timeout"] = timeout
        resp = conn.object_store.head("/", **kwargs)
        headers = getattr(resp, "headers", {}) or {}
        val = None
        if hasattr(headers, "get"):
            val = headers.get("X-Account-Container-Count")
            if val is None:
                val = headers.get("x-account-container-count")
        if val is not None:
            try:
                return int(val)
            except (ValueError, TypeError):
                return 0
        return 0
    except Exception as exc:
        if not _is_account_not_found(exc):
            _logger.debug("Swift 컨테이너 수 조회 실패", exc_info=True)
        return 0


def count_containers_all_projects(
    admin_token: str,
    *,
    per_request_timeout: float = 2.0,
    total_budget: float = 8.0,
    max_workers: int = 8,
) -> int:
    """admin 토큰으로 모든 프로젝트 fan-out 해서 swift 컨테이너 총 수 반환.

    admin overview의 cross-project 카운트 용도. swift 계정은 프로젝트별로 분리되므로
    admin 본인 프로젝트의 conn.object_store만 보면 0이 나올 수 있어 fan-out 필요.
    한 프로젝트가 401/404여도 해당 프로젝트만 0으로 처리하고 나머지는 합산한다.
    타임아웃 발생 시 부분합 대신 0을 반환한다.
    """
    from app.services import keystone

    try:
        projects = keystone.list_projects(admin_token)
    except Exception:
        _logger.warning("admin 프로젝트 목록 조회 실패", exc_info=True)
        return 0

    project_ids = [p["id"] for p in projects if isinstance(p, dict) and p.get("id")]
    if not project_ids:
        return 0

    def _count_for_project(pid: str) -> int:
        sub_conn = None
        try:
            sub_conn = keystone.get_admin_connection_for_project(pid)
            if hasattr(sub_conn, "session") and sub_conn.session is not None:
                sub_conn.session.timeout = per_request_timeout
            return count_containers(sub_conn, timeout=per_request_timeout)
        except Exception as exc:
            if not _is_unauthorized(exc):
                _logger.debug("프로젝트 %s connection 실패", pid, exc_info=True)
            return 0
        finally:
            if sub_conn is not None:
                with contextlib.suppress(Exception):
                    sub_conn.close()

    workers = min(max(1, max_workers), len(project_ids))
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
    try:
        futures = [executor.submit(_count_for_project, pid) for pid in project_ids]
        done, not_done = concurrent.futures.wait(futures, timeout=total_budget)

        if not_done:
            _logger.warning(
                "Swift all-project 카운트 타임아웃 (budget=%s, pending=%d/%d)",
                total_budget,
                len(not_done),
                len(futures),
            )
            for f in not_done:
                f.cancel()
            return 0

        total = 0
        for f in futures:
            total += f.result()
        return total
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def get_account_metadata(conn, *, strict: bool = False) -> dict:
    """Return current-account usage metadata.

    A missing account is represented as empty usage. With ``strict=True``, all
    other provider failures are propagated so callers can fail closed.
    """
    _apply_endpoint_override(conn)
    try:
        meta = conn.object_store.get_account_metadata()
        result = {
            "container_count": int(getattr(meta, "account_container_count", 0) or 0),
            "object_count": int(getattr(meta, "account_object_count", 0) or 0),
            "bytes_used": int(getattr(meta, "account_bytes_used", 0) or 0),
        }
        _logger.info(
            "Swift 계정 메타데이터: containers=%d objects=%d bytes=%d",
            result["container_count"],
            result["object_count"],
            result["bytes_used"],
        )
        return result
    except Exception as exc:
        if _is_account_not_found(exc):
            _logger.info("Swift 계정 미초기화 (404) — 기본값 반환")
            return {"container_count": 0, "object_count": 0, "bytes_used": 0}
        if strict:
            raise
        _logger.warning("Swift 계정 메타데이터 조회 실패", exc_info=True)
        return {"container_count": 0, "object_count": 0, "bytes_used": 0}


# ---------------------------------------------------------------------------
# 컨테이너 CRUD
# ---------------------------------------------------------------------------


def _ensure_account(conn) -> bool:
    """Ceph RGW Swift 계정이 없으면 POST로 초기화 시도. 성공 시 True."""
    try:
        resp = conn.object_store.post("/", headers={"Content-Length": "0"})
        sc = getattr(resp, "status_code", 0)
        if sc in (200, 201, 202, 204):
            _logger.info("Swift 계정 초기화 성공: status=%d", sc)
            return True
        _logger.warning("Swift 계정 초기화 응답: status=%d", sc)
    except Exception:
        _logger.debug("Swift 계정 POST 초기화 실패", exc_info=True)
    # PUT fallback
    try:
        resp = conn.object_store.put("/", headers={"Content-Length": "0"})
        sc = getattr(resp, "status_code", 0)
        if sc in (200, 201, 202, 204):
            _logger.info("Swift 계정 PUT 초기화 성공: status=%d", sc)
            return True
        _logger.warning("Swift 계정 PUT 초기화 응답: status=%d", sc)
    except Exception:
        _logger.debug("Swift 계정 PUT 초기화 실패", exc_info=True)
    return False


def create_container(conn, name: str) -> dict:
    """오브젝트 스토리지 컨테이너를 생성하고 메타데이터를 반환.

    Ceph RGW 환경에서 계정이 미초기화 상태이면 자동으로 계정을 초기화한 뒤
    컨테이너 생성을 재시도한다.

    생성 시 caller project_id 를 X-Container-Meta-Owner-Project-Id 메타로 부착해
    향후 admin/operator 도구가 컨테이너 owner 를 식별·검증할 수 있도록 한다
    (defense-in-depth — 실제 RBAC 는 Swift account 모델이 담당).
    """
    _apply_endpoint_override(conn)
    owner_pid = getattr(conn, "_afterglow_project_id", None) or ""
    try:
        c = conn.object_store.create_container(name=name)
        if owner_pid:
            try:
                conn.object_store.set_container_metadata(c.name or name, owner_project_id=owner_pid)
            except Exception:
                _logger.warning("컨테이너 owner metadata 부착 실패: name=%s", name, exc_info=True)
        return {"name": c.name or name, "count": 0, "bytes": 0}
    except Exception as sdk_err:
        if not _is_account_not_found(sdk_err):
            raise
        _logger.warning("SDK create_container 실패 (404), 계정 초기화 후 재시도")

        # 1차: 계정 초기화 시도
        _ensure_account(conn)

        # 2차: raw PUT으로 컨테이너 생성 재시도
        try:
            headers = {"Content-Length": "0"}
            if owner_pid:
                headers["X-Container-Meta-Owner-Project-Id"] = owner_pid
            resp = conn.object_store.put(f"/{name}", headers=headers)
            sc = getattr(resp, "status_code", 0)
            if sc in (201, 202, 204):
                _logger.info("Swift 컨테이너 생성 성공 (계정 초기화 후): status=%d", sc)
                return {"name": name, "count": 0, "bytes": 0}
            _logger.error("Swift 컨테이너 raw PUT 실패: status=%d", sc)
        except Exception:
            _logger.warning("raw PUT 자체 실패", exc_info=True)

        # 3차: SDK 재시도 (계정 초기화 성공 시 작동할 수 있음)
        try:
            c = conn.object_store.create_container(name=name)
            if owner_pid:
                try:
                    conn.object_store.set_container_metadata(c.name or name, owner_project_id=owner_pid)
                except Exception:
                    _logger.warning("컨테이너 owner metadata 부착 실패: name=%s", name, exc_info=True)
            _logger.info("Swift 컨테이너 SDK 재시도 성공")
            return {"name": c.name or name, "count": 0, "bytes": 0}
        except Exception:
            _logger.debug("SDK 재시도도 실패", exc_info=True)

        raise sdk_err


def delete_container(conn, name: str) -> None:
    """오브젝트 스토리지 컨테이너를 삭제 (내용물 + SLO segments 캐스케이드).

    동작:
    1. 원본 컨테이너 내부의 모든 객체 삭제 (SLO manifest 는 delete_object 내부에서
       ?multipart-manifest=delete 경로로 segments 자동 정리)
    2. 원본 컨테이너 자체 삭제
    3. {name}_segments 컨테이너가 남아 있으면 비우고 삭제 (orphan segment quota leak 방지)
    """
    _apply_endpoint_override(conn)

    # 1. 원본 컨테이너 비우기
    try:
        for o in conn.object_store.objects(name):
            obj_name = o.name or ""
            try:
                delete_object(conn, name, obj_name)
            except Exception:
                _logger.warning("객체 삭제 실패 container=%s name=%s", name, obj_name, exc_info=True)
    except Exception:
        _logger.debug("컨테이너 객체 목록 조회 실패: %s", name, exc_info=True)

    # 2. 원본 컨테이너 삭제
    conn.object_store.delete_container(name, ignore_missing=False)

    # 3. _segments 컨테이너 정리 (SLO 분할 파일의 orphan 방지)
    seg_name = f"{name}_segments"
    try:
        for o in conn.object_store.objects(seg_name):
            obj_name = o.name or ""
            try:
                conn.object_store.delete_object(obj_name, container=seg_name, ignore_missing=True)
            except Exception:
                _logger.warning("SLO segment 삭제 실패 container=%s name=%s", seg_name, obj_name, exc_info=True)
        conn.object_store.delete_container(seg_name, ignore_missing=True)
        _logger.info("SLO segments 컨테이너 정리: %s", seg_name)
    except Exception:
        # segments 가 없는 경우(SLO 미사용 버킷) 정상
        _logger.debug("SLO segments 정리 스킵 또는 부재: %s", seg_name, exc_info=True)


def get_container_metadata(conn, name: str) -> dict:
    """컨테이너 메타데이터(오브젝트 수, 바이트 등) 반환.

    bytes 에는 SLO segment 컨테이너({name}_segments)의 bytes_used 도 합산.
    Swift 의 bytes_used 는 SLO 매니페스트 JSON 크기만 잡으므로 segment 합계를 더해
    실제 사용량을 반영한다.
    """
    _apply_endpoint_override(conn)
    meta = conn.object_store.get_container_metadata(name)
    base_bytes = int(getattr(meta, "bytes_used", 0) or 0)

    seg_bytes = 0
    try:
        seg_meta = conn.object_store.get_container_metadata(f"{name}_segments")
        seg_bytes = int(getattr(seg_meta, "bytes_used", 0) or 0)
    except Exception:
        # segments 컨테이너가 없는 경우(SLO 미사용 버킷) 정상 동작
        pass

    return {
        "name": meta.name or name,
        "count": getattr(meta, "object_count", 0) or 0,
        "bytes": base_bytes + seg_bytes,
        "read_acl": getattr(meta, "read_ACL", "") or "",
        "write_acl": getattr(meta, "write_ACL", "") or "",
    }


# ---------------------------------------------------------------------------
# 오브젝트 CRUD
# ---------------------------------------------------------------------------


def _enrich_slo_sizes(conn, container: str, results: list[dict], prefix: str = "") -> None:
    """SLO 매니페스트 객체의 bytes 를 segments 합계로 교체.

    Swift LIST 는 SLO 매니페스트의 실제 저장 크기(JSON 수 KB)를 반환한다.
    Ceph RGW 는 SLO 미들웨어처럼 listing bytes 를 보정해주지 않으므로,
    {container}_segments 컨테이너를 한 번 LIST 하여 segment 들을 합산한 뒤
    원본 객체의 bytes 를 덮어쓴다.
    """
    seg_container = f"{container}_segments"
    name_to_total: dict[str, int] = {}
    try:
        kwargs: dict = {}
        if prefix:
            kwargs["prefix"] = prefix
        for seg in conn.object_store.objects(seg_container, **kwargs):
            seg_name = getattr(seg, "name", "") or ""
            slash = seg_name.rfind("/")
            if slash == -1:
                continue
            idx_part = seg_name[slash + 1 :]
            # segment 명명 규약: <original_name>/<idx:08d>
            if len(idx_part) != 8 or not idx_part.isdigit():
                continue
            original = seg_name[:slash]
            size = int(getattr(seg, "size", None) or getattr(seg, "content_length", 0) or 0)
            name_to_total[original] = name_to_total.get(original, 0) + size
    except Exception:
        # _segments 컨테이너 없음 또는 LIST 실패 — 원본 사이즈 유지
        return

    if not name_to_total:
        return

    for r in results:
        if r["name"] in name_to_total:
            r["bytes"] = name_to_total[r["name"]]


def list_objects(conn, container: str, prefix: str = "", delimiter: str = "") -> list[dict]:
    """컨테이너 내 오브젝트 목록 반환.

    delimiter="/"를 사용하면 현재 prefix 바로 아래 파일/폴더만 반환한다.
    폴더(subdir)는 {"name": "folder/", "is_dir": True}로 반환된다.
    SLO 매니페스트는 segments 합산으로 bytes 를 보정한다.
    """
    _apply_endpoint_override(conn)
    try:
        kwargs = {}
        if prefix:
            kwargs["prefix"] = prefix
        if delimiter:
            kwargs["delimiter"] = delimiter
        results = []
        seen_subdirs: set[str] = set()
        for o in conn.object_store.objects(container, **kwargs):
            # delimiter 사용 시 Swift는 subdir pseudo-directory 엔트리를 반환
            subdir = getattr(o, "subdir", None)
            if subdir:
                seen_subdirs.add(subdir)
                results.append(
                    {
                        "name": subdir,
                        "bytes": 0,
                        "content_type": "application/directory",
                        "last_modified": "",
                        "etag": "",
                        "is_dir": True,
                    }
                )
            else:
                name = o.name or ""
                # subdir 엔트리와 동일한 directory marker 오브젝트는 중복 제외
                if name in seen_subdirs:
                    continue
                # 명시적 directory marker 오브젝트 (trailing slash + application/directory)
                ct = getattr(o, "content_type", "") or ""
                is_dir = name.endswith("/") and ct in ("application/directory", "")
                results.append(
                    {
                        "name": name,
                        "bytes": getattr(o, "size", None) or getattr(o, "content_length", 0) or 0,
                        "content_type": ct,
                        "last_modified": str(getattr(o, "last_modified_at", "") or ""),
                        "etag": getattr(o, "etag", "") or "",
                        "is_dir": is_dir,
                    }
                )
        _enrich_slo_sizes(conn, container, results, prefix=prefix)
        return results
    except Exception:
        _logger.debug("Swift 오브젝트 목록 조회 실패 container=%s", container, exc_info=True)
        return []


# Ceph RGW 단일 PUT 한계(rgw_max_put_size 기본 5 GiB) 직전까지 단일 객체로 저장.
# 5 GiB 이하는 _segments 컨테이너를 만들지 않음 → Horizon 에 segment 버킷 미노출.
_SLO_SEGMENT_SIZE = 5 * 1024 * 1024 * 1024  # 5 GiB — 이 크기 초과 시 Swift SLO 수동 분할


class _LimitedReader:
    """file-like wrapper: read() 가 최대 limit 바이트까지만 반환."""

    def __init__(self, source, limit: int) -> None:
        self._source = source
        self._remaining = limit

    def read(self, size: int = -1) -> bytes:
        if self._remaining <= 0:
            return b""
        if size < 0 or size > self._remaining:
            size = self._remaining
        chunk = self._source.read(size)
        self._remaining -= len(chunk)
        return chunk


def _ensure_segment_container(conn, container_name: str) -> None:
    """SLO segments 컨테이너가 없으면 생성."""
    try:
        conn.object_store.create_container(name=container_name)
        _logger.debug("SLO segment 컨테이너 생성: %s", container_name)
    except Exception:
        pass  # 이미 존재하거나 계정 초기화 불필요


def _upload_slo(
    conn,
    container: str,
    name: str,
    data,
    content_type: str,
    content_length: int,
) -> dict:
    """1 GiB 초과 파일을 Swift SLO(Static Large Object)로 수동 분할 업로드.

    openstacksdk create_object 는 data= 가 file-like 일 때 use_slo/segment_size 를
    무시하고 단일 PUT 을 보내므로, Swift HTTP API 를 직접 호출하여 SLO 를 구현한다.
    segments 는 {container}_segments/{name}/{idx:08d} 경로에 저장된다.
    """
    import json
    import math
    import urllib.parse

    proxy = conn.object_store
    seg_container = f"{container}_segments"
    _ensure_segment_container(conn, seg_container)

    ct = content_type or "application/octet-stream"
    num_segments = math.ceil(content_length / _SLO_SEGMENT_SIZE)
    segments = []

    for idx in range(num_segments):
        seg_size = min(_SLO_SEGMENT_SIZE, content_length - idx * _SLO_SEGMENT_SIZE)
        seg_name = f"{name}/{idx:08d}"
        seg_path = "/" + urllib.parse.quote(seg_container, safe="") + "/" + urllib.parse.quote(seg_name, safe="/")
        _logger.info(
            "SLO segment %d/%d 업로드 시작: size=%d path=%s",
            idx + 1,
            num_segments,
            seg_size,
            seg_path,
        )
        resp = proxy.put(
            seg_path,
            data=_LimitedReader(data, seg_size),
            headers={"Content-Length": str(seg_size), "Content-Type": ct},
        )
        etag = resp.headers.get("etag", "").strip('"')
        segments.append(
            {
                "path": f"/{seg_container}/{seg_name}",
                "etag": etag,
                "size_bytes": seg_size,
            }
        )
        _logger.info("SLO segment %d/%d 완료: etag=%s", idx + 1, num_segments, etag)

    manifest_path = (
        "/"
        + urllib.parse.quote(container, safe="")
        + "/"
        + urllib.parse.quote(name, safe="/")
        + "?multipart-manifest=put"
    )
    _logger.info("SLO manifest PUT: path=%s segments=%d", manifest_path, len(segments))
    proxy.put(
        manifest_path,
        data=json.dumps(segments).encode(),
        headers={"Content-Type": ct},
    )
    _logger.info("SLO 업로드 완료: container=%s name=%s bytes=%d", container, name, content_length)
    return {
        "name": name,
        "container": container,
        "bytes": content_length,
        "etag": "",
    }


def upload_object(conn, container: str, name: str, data, content_type: str = "", content_length: int = 0) -> dict:
    """오브젝트를 업로드하고 메타데이터를 반환.

    data: bytes 또는 file-like object (read() 메서드 지원).
    1 GiB 초과 파일은 Swift SLO(Static Large Object)로 수동 분할 업로드된다.
    segments 는 {container}_segments 컨테이너에 저장되고, manifest 만 원본 컨테이너에 남는다.
    """
    from app.config import get_settings

    _apply_endpoint_override(conn)

    settings = get_settings()
    proxy = conn.object_store
    original_timeout = getattr(proxy, "timeout", None)
    proxy.timeout = settings.os_swift_upload_timeout
    try:
        if content_length and content_length > _SLO_SEGMENT_SIZE:
            return _upload_slo(conn, container, name, data, content_type, content_length)
        kwargs: dict = {"data": data}
        if content_type:
            kwargs["content_type"] = content_type
        if content_length:
            kwargs["content_length"] = content_length
        obj = proxy.create_object(container, name, **kwargs)
        actual_bytes = content_length if content_length else (len(data) if isinstance(data, bytes) else 0)
        return {
            "name": obj.name or name,
            "container": container,
            "bytes": actual_bytes,
            "etag": getattr(obj, "etag", "") or "",
        }
    finally:
        proxy.timeout = original_timeout


def stream_object(conn, container: str, name: str) -> tuple[Iterator[bytes], str, int]:
    """오브젝트를 스트리밍으로 반환. (chunk_iterator, content_type, content_length)"""
    _apply_endpoint_override(conn)
    # 메타데이터 먼저 가져오기
    meta = conn.object_store.get_object_metadata(name, container=container)
    content_type = getattr(meta, "content_type", None) or "application/octet-stream"
    content_length = int(getattr(meta, "content_length", 0) or 0)
    chunks = conn.object_store.stream_object(name, container=container, chunk_size=65536)
    return chunks, content_type, content_length


def delete_object(conn, container: str, name: str) -> None:
    """오브젝트를 삭제.

    trailing '/'가 있는 이름(디렉토리 마커)은 openstacksdk urljoin이 '/'를 strip하므로
    raw DELETE를 사용한다.
    SLO manifest 는 ?multipart-manifest=delete 로 segments 까지 함께 정리하여 quota 누수를 방지한다.
    """
    import urllib.parse

    _apply_endpoint_override(conn)
    if name.endswith("/"):
        encoded = "/" + urllib.parse.quote(container, safe="") + "/" + urllib.parse.quote(name, safe="/")
        conn.object_store.delete(encoded)
        return

    # SLO manifest 여부 확인 — segments quota 누수 방지
    is_slo = False
    try:
        meta = conn.object_store.get_object_metadata(name, container=container)
        is_slo = bool(
            getattr(meta, "is_static_large_object", None)
            or str(getattr(meta, "x_static_large_object", "") or "").lower() == "true"
        )
    except Exception:
        pass

    if is_slo:
        encoded = (
            "/"
            + urllib.parse.quote(container, safe="")
            + "/"
            + urllib.parse.quote(name, safe="/")
            + "?multipart-manifest=delete"
        )
        conn.object_store.delete(encoded)
    else:
        conn.object_store.delete_object(name, ignore_missing=False, container=container)


def get_object_metadata(conn, container: str, name: str) -> dict:
    """오브젝트 상세 메타데이터 반환.

    Upload inspection 결과는 S3 user metadata 로 기록되며 Swift API 에서는
    소문자 `X-Object-Meta-*` 키로 노출된다. 없으면 빈 문자열이다.
    """
    _apply_endpoint_override(conn)
    meta = conn.object_store.get_object_metadata(name, container=container)
    custom = getattr(meta, "metadata", None) or {}
    return {
        "name": meta.name or name,
        "container": container,
        "bytes": int(getattr(meta, "content_length", 0) or 0),
        "content_type": getattr(meta, "content_type", "") or "",
        "last_modified": str(getattr(meta, "last_modified_at", "") or ""),
        "etag": getattr(meta, "etag", "") or "",
        "content_encoding": getattr(meta, "content_encoding", "") or "",
        "content_disposition": getattr(meta, "content_disposition", "") or "",
        "delete_at": str(getattr(meta, "delete_at", "") or ""),
        "sha256": str(custom.get("sha256", "") or ""),
        "detected_content_type": str(custom.get("detected-content-type", "") or ""),
    }


# ---------------------------------------------------------------------------
# 디렉토리 / 복사 / 이동 / 이름 변경
# ---------------------------------------------------------------------------


def bulk_delete_objects(conn, container: str, names: list[str], recursive: bool = False) -> dict:
    """여러 오브젝트를 삭제한다.

    recursive=True이면 디렉토리(`/`로 끝나는) 하위 오브젝트 전체를 삭제한다.
    반환: {"deleted": [...], "failed": [{"name": ..., "error": ...}, ...]}
    """
    _apply_endpoint_override(conn)
    deleted: list[str] = []
    failed: list[dict] = []

    for name in names:
        if name.endswith("/") and recursive:
            # 디렉토리 하위 전체 나열 후 삭제
            try:
                children = list_objects(conn, container, prefix=name, delimiter="")
            except Exception as e:
                failed.append({"name": name, "error": str(e)})
                continue
            for child in children:
                child_name = child["name"]
                if child_name == name:
                    continue  # directory marker 자체는 나중에 삭제
                try:
                    delete_object(conn, container, child_name)
                    deleted.append(child_name)
                except Exception as e:
                    failed.append({"name": child_name, "error": str(e)})
        # directory marker 또는 일반 파일 삭제
        try:
            delete_object(conn, container, name)
            deleted.append(name)
        except Exception as e:
            failed.append({"name": name, "error": str(e)})

    return {"deleted": deleted, "failed": failed}


def create_directory(conn, container: str, path: str) -> dict:
    """가상 디렉토리(빈 오브젝트 + trailing slash)를 생성한다.

    openstacksdk의 create_object는 utils.urljoin에서 trailing /를 strip하므로
    raw PUT을 사용하여 trailing /를 보존한다.
    """
    import urllib.parse

    _apply_endpoint_override(conn)
    dir_name = path.rstrip("/") + "/"
    encoded_path = "/" + urllib.parse.quote(container, safe="") + "/" + urllib.parse.quote(dir_name, safe="/")
    conn.object_store.put(
        encoded_path,
        headers={"Content-Type": "application/directory", "Content-Length": "0"},
    )
    return {"name": dir_name, "container": container}


def copy_object(
    conn,
    container: str,
    source: str,
    dest_container: str,
    dest_name: str,
    extra_headers: dict | None = None,
) -> dict:
    """오브젝트를 복사한다 (Swift X-Copy-From 헤더 사용).

    extra_headers: COPY 요청에 추가로 보낼 헤더 (예: X-Object-Meta-* 메타데이터).
    """
    import urllib.parse

    from app.config import get_settings

    _apply_endpoint_override(conn)
    proxy = conn.object_store
    # 대용량 파일 복사를 위해 upload_timeout 적용
    settings = get_settings()
    upload_timeout = settings.os_swift_upload_timeout
    original_timeout = getattr(proxy, "timeout", None)
    proxy.timeout = upload_timeout
    # 한글 등 non-ASCII 문자를 URL-encode 하여 latin-1 인코딩 문제 방지
    encoded_src = "/" + urllib.parse.quote(container, safe="") + "/" + urllib.parse.quote(source, safe="/")
    encoded_dest = "/" + urllib.parse.quote(dest_container, safe="") + "/" + urllib.parse.quote(dest_name, safe="/")
    headers = {"X-Copy-From": encoded_src, "Content-Length": "0"}
    if extra_headers:
        headers.update(extra_headers)
    try:
        proxy.put(encoded_dest, headers=headers)
    finally:
        proxy.timeout = original_timeout
    return {
        "source": source,
        "destination": dest_name,
        "source_container": container,
        "dest_container": dest_container,
    }


def move_object(
    conn,
    container: str,
    source: str,
    dest_container: str,
    dest_name: str,
) -> dict:
    """오브젝트를 이동한다 (copy + delete).

    source가 디렉토리(trailing '/')이면 하위 파일 전체를 재귀적으로 복사 후 삭제한다.
    """
    if source.endswith("/"):
        # 디렉토리: 하위 파일 전체 나열 후 복사
        children = list_objects(conn, container, prefix=source, delimiter="")
        # directory marker 자체도 포함하여 복사
        copy_object(conn, container, source, dest_container, dest_name)
        for child in children:
            child_name = child["name"]
            if child_name == source:
                continue
            new_child_name = dest_name + child_name[len(source) :]
            copy_object(conn, container, child_name, dest_container, new_child_name)
        # 원본 삭제 (하위 파일 먼저, 마커 나중)
        for child in children:
            if child["name"] != source:
                delete_object(conn, container, child["name"])
        delete_object(conn, container, source)
        return {
            "source": source,
            "destination": dest_name,
            "source_container": container,
            "dest_container": dest_container,
        }
    result = copy_object(conn, container, source, dest_container, dest_name)
    delete_object(conn, container, source)
    return result


def rename_object(conn, container: str, old_name: str, new_name: str) -> dict:
    """오브젝트 이름을 변경한다 (같은 컨테이너 내 move)."""
    return move_object(conn, container, old_name, container, new_name)


# ---------------------------------------------------------------------------
# 휴지통 (오브젝트 소프트 삭제)
# ---------------------------------------------------------------------------

# 휴지통 버킷 접미사
TRASH_SUFFIX = "-trash"


def _trash_container_name(container: str) -> str:
    """원본 버킷 이름에서 휴지통 버킷 이름 반환."""
    return f"{container}{TRASH_SUFFIX}"


def _ensure_trash_container(conn, container: str) -> None:
    """휴지통 버킷이 없으면 생성. 이미 있으면 no-op."""
    trash_name = _trash_container_name(container)
    _apply_endpoint_override(conn)
    try:
        conn.object_store.get_container_metadata(trash_name)
    except Exception:
        # 존재하지 않으면 생성
        try:
            create_container(conn, trash_name)
        except Exception:
            _logger.warning("휴지통 버킷 생성 실패: %s", trash_name, exc_info=True)
            raise


def soft_delete_object(conn, container: str, name: str) -> dict:
    """오브젝트를 휴지통 버킷({container}-trash)으로 이동 (소프트 삭제).

    휴지통 키 형식: {epoch_seconds}/{uuid8}/{original_name}
    이 형식을 통해 purge 루프가 오브젝트별 HEAD 없이 이름만으로 만료 여부를 판정할 수 있다.

    디렉토리(trailing '/')의 경우 move_object 의 재귀 로직을 재사용하여 하위 파일
    전체를 휴지통으로 이동한다 — copy+delete 를 단순 호출하면 하위 파일이 원본 버킷에
    고아로 남는 버그가 발생한다.
    """
    import time
    import urllib.parse
    import uuid as _uuid

    _ensure_trash_container(conn, container)

    epoch = int(time.time())
    uid = _uuid.uuid4().hex[:8]
    trash_key = f"{epoch}/{uid}/{name}"
    trash_container = _trash_container_name(container)

    if name.endswith("/"):
        # 디렉토리: move_object 가 하위 파일 전체를 재귀 COPY+DELETE 처리
        move_object(conn, container, name, trash_container, trash_key)
    else:
        # HTTP 헤더는 Latin-1 범위만 허용 — 한글 등 non-ASCII 값은 URL-encode
        extra_meta: dict[str, str] = {
            "X-Object-Meta-Orig-Name": urllib.parse.quote(name, safe="/"),
            "X-Object-Meta-Orig-Container": urllib.parse.quote(container, safe=""),
            "X-Object-Meta-Deleted-At": str(epoch),
        }
        copy_object(conn, container, name, trash_container, trash_key, extra_headers=extra_meta)
        delete_object(conn, container, name)

    _logger.info(
        "오브젝트 소프트 삭제: container=%s name=%s → trash_key=%s",
        container,
        name,
        trash_key,
    )
    return {
        "trash_key": trash_key,
        "original_name": name,
        "deleted_at": epoch,
        "container": container,
        "trash_container": trash_container,
    }


def bulk_soft_delete_objects(conn, container: str, names: list[str], recursive: bool = False) -> dict:
    """여러 오브젝트를 휴지통으로 이동.

    recursive=True 이면 디렉토리 하위 전체를 소프트 삭제한다.
    반환: {"moved": [...], "failed": [...]}
    """
    moved: list[str] = []
    failed: list[dict] = []

    for name in names:
        if name.endswith("/") and recursive:
            try:
                children = list_objects(conn, container, prefix=name, delimiter="")
            except Exception as e:
                failed.append({"name": name, "error": str(e)})
                continue
            for child in children:
                child_name = child["name"]
                if child_name == name:
                    continue
                try:
                    soft_delete_object(conn, container, child_name)
                    moved.append(child_name)
                except Exception as e:
                    failed.append({"name": child_name, "error": str(e)})
        try:
            soft_delete_object(conn, container, name)
            moved.append(name)
        except Exception as e:
            failed.append({"name": name, "error": str(e)})

    return {"moved": moved, "failed": failed}


def list_trash_objects(conn, container: str) -> list[dict]:
    """휴지통 버킷의 오브젝트 목록 반환.

    각 항목에 trash_key, original_name, deleted_at(epoch_seconds) 필드 포함.
    """
    trash_container = _trash_container_name(container)
    try:
        objects = list_objects(conn, trash_container, delimiter="")
    except Exception:
        return []

    result = []
    for obj in objects:
        key = obj.get("name", "")
        # 키 형식: {epoch}/{uuid8}/{original_name}
        parts = key.split("/", 2)
        if len(parts) < 3:
            _logger.debug("휴지통 키 형식 불일치, 건너뜀: %s", key)
            continue
        epoch_str, _uid, orig_name = parts
        try:
            deleted_at = int(epoch_str)
        except ValueError:
            deleted_at = 0
        result.append(
            {
                **obj,
                "trash_key": key,
                "original_name": orig_name,
                "deleted_at": deleted_at,
            }
        )
    return result


def restore_trash_object(conn, container: str, trash_key: str) -> dict:
    """휴지통 오브젝트를 원본 버킷으로 복구.

    원본 버킷에 동명 파일이 이미 있으면 '(복구됨)' 접미사를 붙인다.
    """
    trash_container = _trash_container_name(container)

    parts = trash_key.split("/", 2)
    if len(parts) < 3:
        raise ValueError(f"잘못된 휴지통 키 형식: {trash_key}")
    orig_name = parts[2]

    # 동명 충돌 확인
    _apply_endpoint_override(conn)
    dest_name = orig_name
    try:
        conn.object_store.get_object_metadata(orig_name, container=container)
        # 동명 파일 존재 — 접미사 추가
        if "." in orig_name.rsplit("/", 1)[-1]:
            base, dot, ext = orig_name.rpartition(".")
            dest_name = f"{base}-(복구됨).{ext}"
        else:
            dest_name = f"{orig_name}-(복구됨)"
    except Exception:
        pass  # 원본 없음 — 그대로 복구

    move_object(conn, trash_container, trash_key, container, dest_name)

    _logger.info(
        "오브젝트 복구: trash_key=%s → container=%s name=%s",
        trash_key,
        container,
        dest_name,
    )
    return {
        "restored_name": dest_name,
        "original_name": orig_name,
        "container": container,
    }


def purge_trash_object(conn, container: str, trash_key: str) -> None:
    """휴지통 오브젝트를 영구 삭제."""
    trash_container = _trash_container_name(container)
    delete_object(conn, trash_container, trash_key)
    _logger.info("오브젝트 영구 삭제 (휴지통): container=%s key=%s", container, trash_key)


def purge_expired_trash_objects(conn, container: str, retention_days: int) -> dict:
    """만료된 휴지통 오브젝트를 모두 영구 삭제.

    retention_days 경과한 오브젝트만 삭제한다.
    반환: {"purged": [trash_key, ...], "failed": [...]}
    """
    import time

    cutoff = int(time.time()) - retention_days * 86400
    objects = list_trash_objects(conn, container)
    purged: list[str] = []
    failed: list[dict] = []

    for obj in objects:
        if obj.get("deleted_at", 0) <= cutoff:
            key = obj["trash_key"]
            try:
                purge_trash_object(conn, container, key)
                purged.append(key)
            except Exception as e:
                failed.append({"trash_key": key, "error": str(e)})

    return {"purged": purged, "failed": failed}


# ---------------------------------------------------------------------------
# 버킷 소프트 삭제 (컨테이너 레벨)
# ---------------------------------------------------------------------------

_CONTAINER_DELETED_META_KEY = "afterglow-deleted-at"


def soft_delete_container_metadata(conn, name: str, epoch: int) -> None:
    """컨테이너에 삭제 타임스탬프 메타데이터 부착 (소프트 삭제 마킹).

    실제 데이터 이동은 없음. 격리용 연산 비용 zero.
    """
    _apply_endpoint_override(conn)
    # openstacksdk set_container_metadata: kwarg key → X-Container-Meta-{key}
    # 'afterglow_deleted_at' → 'X-Container-Meta-Afterglow-Deleted-At'
    conn.object_store.set_container_metadata(name, afterglow_deleted_at=str(epoch))
    _logger.info("컨테이너 소프트 삭제 마킹: name=%s deleted_at=%d", name, epoch)


def restore_container_metadata(conn, name: str) -> None:
    """컨테이너에서 삭제 타임스탬프 메타데이터 제거 (복구 마킹)."""
    _apply_endpoint_override(conn)
    conn.object_store.set_container_metadata(name, afterglow_deleted_at="")
    _logger.info("컨테이너 소프트 삭제 마킹 해제: name=%s", name)


def get_container_deleted_at(conn, name: str) -> int | None:
    """컨테이너의 소프트 삭제 타임스탬프 반환. 소프트 삭제 아니면 None."""
    _apply_endpoint_override(conn)
    try:
        meta = conn.object_store.get_container_metadata(name)
        # openstacksdk는 X-Container-Meta-Afterglow-Deleted-At을
        # x_container_meta_afterglow_deleted_at 속성으로 노출
        for attr in (
            "x_container_meta_afterglow_deleted_at",
            "afterglow_deleted_at",
        ):
            v = getattr(meta, attr, None)
            if v:
                try:
                    return int(v)
                except (ValueError, TypeError):
                    pass
        # metadata dict fallback (openstacksdk 버전에 따라 다를 수 있음)
        md = getattr(meta, "metadata", None) or {}
        for key in ("afterglow-deleted-at", "Afterglow-Deleted-At"):
            v = md.get(key)
            if v:
                try:
                    return int(v)
                except (ValueError, TypeError):
                    pass
    except Exception:
        _logger.debug("컨테이너 메타데이터 조회 실패: %s", name, exc_info=True)
    return None
