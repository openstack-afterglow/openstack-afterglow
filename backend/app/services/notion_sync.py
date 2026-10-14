"""
Notion Database 동기화 서비스.

OpenStack 인스턴스 목록을 Notion DB에 주기적으로 동기화한다.
각 인스턴스가 하나의 행(페이지)으로 관리된다.
DB의 실제 속성 타입을 읽어 그에 맞는 형식으로 데이터를 전송한다.
"""

import asyncio
import hashlib
import json
import logging
import re
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC

import httpx

from app.services.work_dispatcher import DispatcherUnavailable

_worker_policy = ContextVar("notion_worker_policy", default=None)


@contextmanager
def worker_policy(check):
    """Install a task-local current-policy/output fence for background sync."""
    token = _worker_policy.set(check)
    try:
        yield
    finally:
        _worker_policy.reset(token)


async def worker_checkpoint() -> None:
    from app.services.work_dispatcher import checkpoint

    await checkpoint()
    check = _worker_policy.get()
    if check is not None:
        await check()


async def _drained_parallel(coroutines) -> None:
    # TaskGroup waits for every HTTP child on cancellation before its owner can
    # release the target/output lease or close the database.
    try:
        async with asyncio.TaskGroup() as group:
            for coroutine in coroutines:
                group.create_task(coroutine)
    except BaseExceptionGroup as exc:
        if exc.subgroup(DispatcherUnavailable) is not None:
            raise DispatcherUnavailable("Notion parallel work lost ownership") from exc
        raise


_logger = logging.getLogger(__name__)

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
REDIS_CONFIG_KEY = "afterglow:notion:config"

_UPDATE_REDIS_TIMESTAMPS = """
local raw = redis.call('GET', KEYS[1])
if raw ~= ARGV[1] then return 0 end
local config = cjson.decode(raw)
if config.enabled ~= true then return 0 end
local stamps = cjson.decode(ARGV[2])
for field, value in pairs(stamps) do config[field] = value end
redis.call('SET', KEYS[1], cjson.encode(config), 'KEEPTTL')
return 1
"""

# 속성 이름 → 인스턴스 데이터 키 매핑 (한국어 속성명 기준)
# DB에 이 이름의 속성이 있으면 해당 데이터를 채운다.
# relation 타입: 값은 page_id 문자열 (비어있으면 relation 해제)
FIELD_MAP: dict[str, str] = {
    "사용자": "user_page_id",  # relation → People DB
    "오픈스택 리소스": "hypervisor_page_id",  # relation → Hypervisor DB
    "팀": "project_name",
    "플레이버": "flavor_name",
    "CPU (c)": "vcpus",
    "MEM (G)": "ram_gb",
    "GPU": "gpu_name",
    "GPU 개수": "gpu_count",
    "GPU map": "gpu_spec_page_id",  # relation → GPU Spec DB
    "고정 IP": "fixed_ip",
    "유동 IP": "floating_ip",
    "인스턴스 ID": "instance_id",
    "상태": "status",
    "생성된 날짜": "created_at",
}

# 한국어 이전 전 영문 속성명도 지원 (마이그레이션 전 기존 DB 호환)
_FIELD_MAP_LEGACY: dict[str, str] = {
    "user": "user_page_id",
    "openstack resource": "hypervisor_page_id",
    "team": "project_name",
    "flavor": "flavor_name",
    "fixed ip": "fixed_ip",
    "floating ip": "floating_ip",
    "instance id": "instance_id",
    "status": "status",
    "GPU spec": "gpu_spec_page_id",  # 이전 칼럼명 호환 (→ "GPU map"으로 변경됨)
}

# OpenStack 상태값 → 한국어 번역
STATUS_KO: dict[str, str] = {
    "ACTIVE": "실행 중",
    "SHUTOFF": "종료",
    "PAUSED": "일시정지",
    "SUSPENDED": "일시중단",
    "ERROR": "오류",
    "BUILDING": "생성 중",
    "DELETED": "삭제됨",
    "SHELVED": "보류",
    "SHELVED_OFFLOADED": "보류(오프로드)",
    "RESIZE": "크기 변경 중",
    "VERIFY_RESIZE": "크기 변경 확인",
    "MIGRATING": "마이그레이션 중",
    "REBOOT": "재시작 중",
}

# OpenStack statuses that still consume allocated host/GPU resources.
# Keep this in sync with GPU quota/admin dashboard accounting.
RESOURCE_ALLOCATED_INSTANCE_STATUSES: frozenset[str] = frozenset({"ACTIVE", "SHUTOFF", "PAUSED", "SUSPENDED", "RESIZE"})


def is_resource_allocated_status(status: str | None) -> bool:
    """Return whether a Nova instance status still consumes host/GPU resources."""
    return (status or "").upper() in RESOURCE_ALLOCATED_INSTANCE_STATUSES


def build_gpu_usage_by_gpu(
    hypervisors: list[dict],
    instances: list[dict],
    alias_to_device_name: dict[str, str],
) -> dict[str, dict]:
    """Build GPU Spec usage buckets from hypervisor capacity and allocated instances."""
    from app.services.gpu_inventory import resolve_alias_to_device_name

    def _empty_bucket() -> dict:
        return {
            "total_cpu_used": 0,
            "total_ram_used": 0,
            "total_gpu_used": 0,
            "instance_count": 0,
            "gpu_available": 0,
            "gpu_used": 0,
            "gpu_remaining": 0,
        }

    usage_by_gpu: dict[str, dict] = {}

    for hypervisor in hypervisors:
        for gpu_group in hypervisor.get("gpu_groups", []):
            device_name = gpu_group.get("device_name", "")
            if not device_name:
                continue
            usage_by_gpu.setdefault(device_name, _empty_bucket())["gpu_available"] += gpu_group.get("total", 0)

    for inst in instances:
        if not is_resource_allocated_status(inst.get("status")):
            continue
        gpu_display = inst.get("gpu_name", "")
        gpu_count = inst.get("gpu_count", 0)
        if not gpu_display or not gpu_count:
            continue
        canonical = resolve_alias_to_device_name(gpu_display, alias_to_device_name) or gpu_display
        bucket = usage_by_gpu.setdefault(canonical, _empty_bucket())
        bucket["total_cpu_used"] += inst.get("vcpus", 0)
        bucket["total_ram_used"] += inst.get("ram_gb", 0)
        bucket["total_gpu_used"] += gpu_count
        bucket["instance_count"] += 1
        bucket["gpu_used"] += gpu_count

    for usage in usage_by_gpu.values():
        usage["gpu_remaining"] = usage["gpu_available"] - usage["gpu_used"]

    return usage_by_gpu


# ensure_db_properties에서 누락된 속성을 생성할 때의 기본 타입
# relation 속성은 자동 생성 불가 (이미 DB에 존재해야 함)
DEFAULT_PROPERTY_TYPES: dict[str, str] = {
    "팀": "select",
    "플레이버": "rich_text",
    "CPU (c)": "number",
    "MEM (G)": "number",
    "GPU": "rich_text",
    "GPU 개수": "number",
    "고정 IP": "rich_text",
    "유동 IP": "rich_text",
    "인스턴스 ID": "rich_text",
    "상태": "select",
    "생성된 날짜": "date",
}

# Notion DB 속성명 한국어 마이그레이션 매핑 (영문 → 한국어)
_KO_MIGRATION_MAP: dict[str, str] = {
    "user": "사용자",
    "openstack resource": "오픈스택 리소스",
    "team": "팀",
    "flavor": "플레이버",
    "fixed ip": "고정 IP",
    "floating ip": "유동 IP",
    "instance id": "인스턴스 ID",
    "status": "상태",
}

REDIS_MIGRATION_KEY = "afterglow:notion:migration_v1"


def _headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# Rate Limiter — Notion API 초당 3회 제한 준수
# ---------------------------------------------------------------------------


class _NotionRateLimiter:
    """Token bucket 기반 rate limiter. Notion API 평균 3 req/s 제한에 맞춘다."""

    def __init__(self, rate: float = 3.0) -> None:
        self._rate = rate
        self._max_tokens = rate
        self._tokens: float = rate
        self._last_refill: float = 0.0
        self._lock: asyncio.Lock | None = None

    async def acquire(self) -> None:
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            now = asyncio.get_event_loop().time()
            if self._last_refill == 0.0:
                self._last_refill = now
            elapsed = now - self._last_refill
            self._tokens = min(self._max_tokens, self._tokens + elapsed * self._rate)
            self._last_refill = now

            if self._tokens >= 1.0:
                self._tokens -= 1.0
            else:
                wait = (1.0 - self._tokens) / self._rate
                self._tokens = 0.0
                await asyncio.sleep(wait)


_rate_limiter = _NotionRateLimiter()
_concurrency_sem: asyncio.Semaphore | None = None


def _get_concurrency_sem() -> asyncio.Semaphore:
    global _concurrency_sem
    if _concurrency_sem is None:
        _concurrency_sem = asyncio.Semaphore(5)
    return _concurrency_sem


async def _notion_request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    api_key: str,
    *,
    json: dict | None = None,
    max_retries: int = 5,
) -> "httpx.Response":
    """Rate limiting + 429 재시도 처리를 포함한 Notion API 요청 헬퍼."""
    call = getattr(client, method.lower())
    last_resp = None
    for attempt in range(max_retries + 1):
        await _rate_limiter.acquire()
        async with _get_concurrency_sem():
            kwargs: dict = {"headers": _headers(api_key)}
            if json is not None:
                kwargs["json"] = json
            await worker_checkpoint()
            resp = await call(url, **kwargs)
        if resp.status_code != 429:
            return resp
        last_resp = resp
        retry_after_str = resp.headers.get("Retry-After", "")
        try:
            wait = float(retry_after_str)
        except (ValueError, TypeError):
            wait = min(2**attempt, 60)
        _logger.warning(
            "Notion rate limited (429), %ds 후 재시도 (attempt %d/%d)",
            int(wait),
            attempt + 1,
            max_retries,
        )
        await asyncio.sleep(wait)
    return last_resp  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# DB 설정/검증
# ---------------------------------------------------------------------------


async def validate_notion_config(api_key: str, database_id: str) -> tuple[bool, str]:
    """Notion DB 접근 가능 여부를 확인한다."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await _notion_request(client, "GET", f"{NOTION_API_BASE}/databases/{database_id}", api_key)
        if resp.status_code == 200:
            return True, "연결 성공"
        body = resp.json()
        msg = body.get("message", resp.text)
        if resp.status_code == 401:
            return False, f"인증 실패: API Key를 확인하세요 — {msg}"
        if resp.status_code == 404:
            return (
                False,
                "Database를 찾을 수 없습니다. ID를 확인하고, Integration에 DB 접근 권한이 있는지 확인하세요.",
            )
        return False, f"Notion API 오류 ({resp.status_code}): {msg}"
    except httpx.TimeoutException:
        return False, "Notion API 응답 시간 초과"
    except Exception as e:
        return False, f"연결 오류: {e}"


async def _get_db_schema(client: httpx.AsyncClient, api_key: str, database_id: str) -> dict:
    """DB의 전체 속성 스키마를 반환한다. {속성이름: {type, ...}}"""
    resp = await _notion_request(client, "GET", f"{NOTION_API_BASE}/databases/{database_id}", api_key)
    resp.raise_for_status()
    return resp.json().get("properties", {})


def _find_title_prop(schema: dict) -> str:
    """스키마에서 title 타입 속성 이름을 반환."""
    for name, defn in schema.items():
        if defn.get("type") == "title":
            return name
    return "Name"


async def ensure_db_properties(api_key: str, database_id: str) -> None:
    """DB에 필요한 속성이 없으면 자동 생성한다. relation 타입은 생략."""
    async with httpx.AsyncClient(timeout=15) as client:
        schema = await _get_db_schema(client, api_key, database_id)
        existing = set(schema.keys())

        missing: dict = {}
        for prop_name, prop_type in DEFAULT_PROPERTY_TYPES.items():
            if prop_name not in existing:
                if prop_type == "number":
                    missing[prop_name] = {"number": {}}
                elif prop_type == "rich_text":
                    missing[prop_name] = {"rich_text": {}}

        if not missing:
            return

        patch_resp = await _notion_request(
            client,
            "PATCH",
            f"{NOTION_API_BASE}/databases/{database_id}",
            api_key,
            json={"properties": missing},
        )
        patch_resp.raise_for_status()
        _logger.info("Notion DB 속성 %d개 자동 생성: %s", len(missing), list(missing.keys()))


# ---------------------------------------------------------------------------
# 인스턴스 데이터 → Notion properties 변환 (DB 속성 타입에 맞게)
# ---------------------------------------------------------------------------


def _format_value(prop_type: str, value) -> dict | None:
    """DB 속성 타입에 맞는 Notion property value를 생성한다."""
    if prop_type == "title":
        return {"title": [{"text": {"content": str(value)}}]} if value else {"title": []}
    elif prop_type == "rich_text":
        return {"rich_text": [{"text": {"content": str(value)}}]} if value else {"rich_text": []}
    elif prop_type == "number":
        try:
            return {"number": int(value) if value else 0}
        except (ValueError, TypeError):
            return {"number": 0}
    elif prop_type == "select":
        return {"select": {"name": str(value)}} if value else {"select": None}
    elif prop_type == "multi_select":
        items = str(value).split(", ") if value else []
        return {"multi_select": [{"name": v.strip()} for v in items if v.strip()]}
    elif prop_type == "url":
        return {"url": str(value) if value else None}
    elif prop_type == "email":
        return {"email": str(value) if value else None}
    elif prop_type == "phone_number":
        return {"phone_number": str(value) if value else None}
    elif prop_type == "checkbox":
        return {"checkbox": bool(value)}
    elif prop_type == "date":
        if value:
            return {"date": {"start": str(value)}}
        return {"date": None}
    elif prop_type == "relation":
        # value: page_id 문자열, page_id 리스트, 또는 빈 값(relation 해제)
        if not value:
            return {"relation": []}
        if isinstance(value, str):
            return {"relation": [{"id": value}]}
        if isinstance(value, list):
            return {"relation": [{"id": pid} for pid in value if pid]}
        return {"relation": []}
    else:
        # 지원하지 않는 타입은 건너뛴다 (people, formula, rollup 등)
        return None


def _build_instance_properties(schema: dict, title_prop: str, inst: dict) -> dict:
    """인스턴스 dict를 DB 스키마에 맞는 Notion page properties로 변환."""
    props: dict = {}

    # title 속성
    props[title_prop] = _format_value("title", inst.get("name", ""))

    # 나머지 속성: DB에 존재하고 FIELD_MAP(또는 레거시 맵)에 매핑이 있는 것만
    for prop_name, prop_def in schema.items():
        if prop_name == title_prop:
            continue
        data_key = FIELD_MAP.get(prop_name) or _FIELD_MAP_LEGACY.get(prop_name)
        if data_key is None:
            continue  # 매핑 없는 속성은 건너뛴다
        prop_type = prop_def.get("type", "")
        value = inst.get(data_key, "")
        # 상태값 한국어 번역 (select 타입이고 data_key가 status인 경우)
        if data_key == "status" and prop_type == "select" and value:
            value = STATUS_KO.get(str(value).upper(), value)
        formatted = _format_value(prop_type, value)
        if formatted is not None:
            props[prop_name] = formatted

    return props


# ---------------------------------------------------------------------------
# 동기화 로직
# ---------------------------------------------------------------------------


async def _fetch_all_pages(client: httpx.AsyncClient, api_key: str, database_id: str) -> list[dict]:
    """DB의 모든 페이지를 가져온다 (페이지네이션 처리)."""
    pages: list[dict] = []
    has_more = True
    start_cursor = None

    while has_more:
        body: dict = {"page_size": 100}
        if start_cursor:
            body["start_cursor"] = start_cursor

        resp = await _notion_request(
            client,
            "POST",
            f"{NOTION_API_BASE}/databases/{database_id}/query",
            api_key,
            json=body,
        )
        if resp.status_code != 200:
            _logger.error("Notion DB query 실패 (%d): %s", resp.status_code, resp.text)
            resp.raise_for_status()

        data = resp.json()
        pages.extend(data.get("results", []))
        has_more = data.get("has_more", False)
        start_cursor = data.get("next_cursor")

    return pages


def _extract_rich_text(page: dict, prop_name: str) -> str:
    """페이지에서 rich_text 속성의 plain_text를 추출한다."""
    prop = page.get("properties", {}).get(prop_name, {})
    prop_type = prop.get("type", "")
    if prop_type == "title":
        arr = prop.get("title", [])
    elif prop_type == "rich_text":
        arr = prop.get("rich_text", [])
    else:
        return ""
    return arr[0].get("plain_text", "") if arr else ""


async def sync_to_notion(api_key: str, database_id: str, instances: list[dict]) -> dict:
    """인스턴스 목록을 Notion DB에 동기화한다. 결과 통계 반환."""
    stats = {"created": 0, "updated": 0, "archived": 0, "errors": 0, "skipped": 0}

    _redis = None
    try:
        from app.services.cache import _get_redis

        _redis = await _get_redis()
    except Exception:
        pass

    async with httpx.AsyncClient(timeout=30) as client:
        # DB 스키마 읽기
        schema = await _get_db_schema(client, api_key, database_id)
        title_prop = _find_title_prop(schema)

        # 기존 페이지 조회 → {instance_id: page_id} 맵
        existing_pages = await _fetch_all_pages(client, api_key, database_id)
        # 한국어 속성명과 영문 레거시 속성명 모두 지원
        instance_id_prop = (
            "인스턴스 ID" if "인스턴스 ID" in schema else ("instance id" if "instance id" in schema else "")
        )
        has_instance_id_prop = bool(instance_id_prop)
        page_map: dict[str, str] = {}
        for page in existing_pages:
            if has_instance_id_prop:
                key = _extract_rich_text(page, instance_id_prop)
            else:
                key = _extract_rich_text(page, title_prop)
            if key:
                page_map[key] = page["id"]

        seen_keys = set()

        async def _upsert(inst: dict) -> None:
            inst_id = inst.get("instance_id", "")
            name = inst.get("name", "")
            match_key = inst_id if has_instance_id_prop else name
            if not match_key:
                return
            seen_keys.add(match_key)
            properties = _build_instance_properties(schema, title_prop, inst)

            try:
                if match_key in page_map:
                    # dedup: 이전과 동일한 데이터면 PATCH 생략
                    _prop_hash = hashlib.sha256(json.dumps(properties, sort_keys=True).encode()).hexdigest()
                    _redis_key = f"afterglow:notion:hash:{database_id}:{match_key}"
                    if _redis is not None:
                        try:
                            if await _redis.get(_redis_key) == _prop_hash:
                                stats["skipped"] += 1
                                return
                        except Exception:
                            pass
                    resp = await _notion_request(
                        client,
                        "PATCH",
                        f"{NOTION_API_BASE}/pages/{page_map[match_key]}",
                        api_key,
                        json={"properties": properties},
                    )
                    if resp.status_code < 400 and _redis is not None:
                        try:
                            await _redis.set(_redis_key, _prop_hash, ex=86400)
                        except Exception:
                            pass
                else:
                    resp = await _notion_request(
                        client,
                        "POST",
                        f"{NOTION_API_BASE}/pages",
                        api_key,
                        json={
                            "parent": {"database_id": database_id},
                            "properties": properties,
                        },
                    )

                if resp.status_code >= 400:
                    _logger.warning(
                        "Notion 페이지 동기화 실패 (instance=%s, status=%d): %s",
                        name,
                        resp.status_code,
                        resp.text,
                    )
                    stats["errors"] += 1
                else:
                    stats["updated" if match_key in page_map else "created"] += 1

            except DispatcherUnavailable:
                raise
            except Exception as e:
                _logger.warning("Notion 페이지 동기화 실패 (instance=%s): %s", name, e)
                stats["errors"] += 1

        await _drained_parallel(_upsert(inst) for inst in instances)

        # Notion에만 있고 OpenStack에 없는 페이지 → openstack resource relation 해제 후 아카이브
        resource_prop_name = (
            "오픈스택 리소스"
            if "오픈스택 리소스" in schema
            else ("openstack resource" if "openstack resource" in schema else "")
        )
        has_resource_prop = bool(resource_prop_name)

        async def _archive(key: str, page_id: str) -> None:
            try:
                body: dict = {"archived": True}
                if has_resource_prop:
                    body["properties"] = {resource_prop_name: {"relation": []}}
                resp = await _notion_request(
                    client,
                    "PATCH",
                    f"{NOTION_API_BASE}/pages/{page_id}",
                    api_key,
                    json=body,
                )
                if resp.status_code < 400:
                    stats["archived"] += 1
                else:
                    stats["errors"] += 1
            except DispatcherUnavailable:
                raise
            except Exception as e:
                _logger.warning("Notion 페이지 아카이브 실패 (key=%s): %s", key, e)
                stats["errors"] += 1

        to_archive = [(k, pid) for k, pid in page_map.items() if k not in seen_keys]
        if to_archive:
            await _drained_parallel(_archive(k, pid) for k, pid in to_archive)

    _logger.info(
        "Notion 동기화 완료: created=%d updated=%d archived=%d errors=%d",
        stats["created"],
        stats["updated"],
        stats["archived"],
        stats["errors"],
    )
    return stats


# ---------------------------------------------------------------------------
# GPU 이름 추출 헬퍼
# ---------------------------------------------------------------------------


def _gpu_info_from_flavor(flavor_name: str, extra_specs: dict) -> tuple[str, int]:
    """플레이버에서 (GPU 이름, GPU 개수) 를 추출한다."""
    alias = extra_specs.get("pci_passthrough:alias", "")
    if alias:
        gpu_name = ""
        count = 0
        for entry in alias.split(","):
            entry = entry.strip()
            if ":" not in entry:
                continue
            dev, num = entry.rsplit(":", 1)
            if "audio" in dev.lower():
                continue
            if not gpu_name:
                gpu_name = dev
            try:
                count += int(num)
            except ValueError:
                count += 1
        if count > 0:
            return gpu_name, count

    # 이름 기반 fallback: gpu.3090_8c_16g → "3090"
    m = re.match(r"^gpu\.([^_]+)", flavor_name)
    if m:
        return m.group(1), 1

    return "", 0


# ---------------------------------------------------------------------------
# Config helpers — DB 우선, Redis fallback
# ---------------------------------------------------------------------------


def _row_to_dict(row) -> dict:
    """NotionConfig ORM row → API 호환 dict."""
    from app.services.k3s_crypto import decrypt_notion_config

    api_key = ""
    try:
        api_key = decrypt_notion_config(row.api_key_encrypted)
    except Exception:
        _logger.warning("Notion API key 복호화 실패")

    def _iso(dt) -> str | None:
        if dt is None:
            return None
        return dt.isoformat() if hasattr(dt, "isoformat") else str(dt)

    return {
        "api_key": api_key,
        "database_id": row.database_id or "",
        "enabled": bool(row.enabled),
        "interval_minutes": row.interval_minutes or 30,
        "last_sync": _iso(row.last_sync),
        "users_database_id": row.users_database_id or "",
        "hypervisors_database_id": row.hypervisors_database_id or "",
        "hypervisors_last_sync": _iso(row.hypervisors_last_sync),
        "gpu_spec_database_id": row.gpu_spec_database_id or "",
        "gpu_spec_last_sync": _iso(row.gpu_spec_last_sync),
    }


async def _redis_get() -> dict | None:
    """Redis에서 직접 읽기 (fallback 전용)."""
    from app.services.cache import _get_redis

    try:
        r = await _get_redis()
        raw = await r.get(REDIS_CONFIG_KEY)
        if not raw:
            return None
        return json.loads(raw)
    except Exception:
        return None


def _parse_dt(val) -> "object | None":
    """문자열 또는 datetime을 timezone-aware datetime으로 변환."""
    from datetime import datetime

    if not val:
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(val).replace(tzinfo=UTC)
    except Exception:
        return None


async def get_notion_config() -> dict | None:
    from sqlalchemy import select

    from app.database import get_session_factory, is_db_available
    from app.models.db import NotionConfig

    if is_db_available():
        try:
            factory = get_session_factory()
            async with factory() as session:
                result = await session.execute(select(NotionConfig).where(NotionConfig.id == 1))
                row = result.scalar_one_or_none()
                if row is not None:
                    return _row_to_dict(row)
        except Exception:
            _logger.warning("Notion 설정 DB 읽기 실패, Redis fallback", exc_info=True)

    return await _redis_get()


async def save_notion_config(config: dict) -> None:
    from datetime import datetime

    from sqlalchemy import select

    from app.database import get_session_factory, is_db_available
    from app.models.db import NotionConfig
    from app.services.k3s_crypto import encrypt_notion_config

    if is_db_available():
        try:
            encrypted = encrypt_notion_config(config["api_key"])
            factory = get_session_factory()
            async with factory() as session:
                result = await session.execute(select(NotionConfig).where(NotionConfig.id == 1))
                row = result.scalar_one_or_none()
                if row is None:
                    row = NotionConfig(id=1, api_key_encrypted=encrypted)
                    session.add(row)
                else:
                    row.api_key_encrypted = encrypted

                row.database_id = config.get("database_id") or ""
                row.enabled = bool(config.get("enabled", False))
                row.interval_minutes = int(config.get("interval_minutes") or 30)
                row.users_database_id = config.get("users_database_id") or None
                row.hypervisors_database_id = config.get("hypervisors_database_id") or None
                row.gpu_spec_database_id = config.get("gpu_spec_database_id") or None
                row.last_sync = _parse_dt(config.get("last_sync"))
                row.hypervisors_last_sync = _parse_dt(config.get("hypervisors_last_sync"))
                row.gpu_spec_last_sync = _parse_dt(config.get("gpu_spec_last_sync"))
                row.updated_at = datetime.now(UTC)
                await worker_checkpoint()
                await session.commit()
            return
        except DispatcherUnavailable:
            raise
        except Exception:
            _logger.warning("Notion 설정 DB 저장 실패, Redis fallback", exc_info=True)

    # Redis fallback
    from app.services.cache import _get_redis

    r = await _get_redis()
    await worker_checkpoint()
    await r.set(REDIS_CONFIG_KEY, json.dumps(config))


async def update_notion_config_timestamps(timestamps: dict) -> None:
    """Update result columns in the actual legacy store without rewriting policy."""
    from sqlalchemy import select, update

    from app.database import get_session_factory, is_db_available
    from app.models.db import NotionConfig
    from app.services.cache import _get_redis

    if is_db_available():
        try:
            values = {field: _parse_dt(value) for field, value in timestamps.items()}
            async with get_session_factory()() as session:
                await worker_checkpoint()
                result = await session.execute(
                    update(NotionConfig).where(NotionConfig.id == 1, NotionConfig.enabled.is_(True)).values(**values)
                )
                await worker_checkpoint()
                if result.rowcount:
                    await session.commit()
                    return
                existing = await session.execute(select(NotionConfig.id).where(NotionConfig.id == 1))
                if existing.scalar_one_or_none() is not None:
                    raise DispatcherUnavailable("Legacy SQL config is no longer enabled")
        except DispatcherUnavailable:
            raise
        except Exception:
            _logger.warning("Notion timestamp SQL write failed; checking Redis legacy authority", exc_info=True)

    redis = await _get_redis()
    raw = await redis.get(REDIS_CONFIG_KEY)
    if raw is None:
        raise DispatcherUnavailable("Legacy Notion config was removed")
    await worker_checkpoint()
    if not await redis.eval(_UPDATE_REDIS_TIMESTAMPS, 1, REDIS_CONFIG_KEY, raw, json.dumps(timestamps)):
        raise DispatcherUnavailable("Legacy Redis policy changed before timestamp update")


async def delete_notion_config() -> None:
    from sqlalchemy import delete as sa_delete

    from app.database import get_session_factory, is_db_available
    from app.models.db import NotionConfig

    if is_db_available():
        try:
            factory = get_session_factory()
            async with factory() as session:
                await session.execute(sa_delete(NotionConfig).where(NotionConfig.id == 1))
                await session.commit()
        except Exception:
            _logger.warning("Notion 설정 DB 삭제 실패", exc_info=True)

    # Redis도 함께 정리
    try:
        from app.services.cache import _get_redis

        r = await _get_redis()
        await r.delete(REDIS_CONFIG_KEY)
    except Exception:
        pass


def mask_api_key(key: str) -> str:
    if len(key) <= 10:
        return "****"
    return key[:7] + "****" + key[-4:]


# ---------------------------------------------------------------------------
# 하이퍼바이저 동기화
# ---------------------------------------------------------------------------

# 실제 Hypervisor DB 컬럼명에 맞춘 매핑
HYPERVISOR_FIELD_MAP: dict[str, str] = {
    "core": "vcpus",
    "사용중인 core": "vcpus_used",
    "ram": "memory_size_gb",
    "사용중인 ram": "memory_used_gb",
    "GPU": "gpu_spec_page_ids",  # relation (list) → GPU Spec DB
    "GPU 갯수": "gpu_total",  # number — 해당 호스트의 전체 GPU 수
}

HYPERVISOR_DEFAULT_PROPERTY_TYPES: dict[str, str] = {
    "core": "number",
    "사용중인 core": "number",
    "ram": "number",
    "사용중인 ram": "number",
}


async def ensure_hypervisor_db_properties(api_key: str, database_id: str) -> None:
    """하이퍼바이저 DB에 필요한 속성이 없으면 자동 생성한다."""
    async with httpx.AsyncClient(timeout=15) as client:
        schema = await _get_db_schema(client, api_key, database_id)
        existing = set(schema.keys())

        missing: dict = {}
        for prop_name, prop_type in HYPERVISOR_DEFAULT_PROPERTY_TYPES.items():
            if prop_name not in existing:
                if prop_type == "number":
                    missing[prop_name] = {"number": {}}
                elif prop_type == "rich_text":
                    missing[prop_name] = {"rich_text": {}}

        if not missing:
            return

        patch_resp = await _notion_request(
            client,
            "PATCH",
            f"{NOTION_API_BASE}/databases/{database_id}",
            api_key,
            json={"properties": missing},
        )
        patch_resp.raise_for_status()
        _logger.info(
            "Notion 하이퍼바이저 DB 속성 %d개 자동 생성: %s",
            len(missing),
            list(missing.keys()),
        )


async def sync_hypervisors_to_notion(api_key: str, database_id: str, hypervisors: list[dict]) -> dict:
    """하이퍼바이저 목록을 Notion DB에 동기화한다. 결과 통계 반환."""
    stats = {"created": 0, "updated": 0, "archived": 0, "errors": 0}

    async with httpx.AsyncClient(timeout=30) as client:
        schema = await _get_db_schema(client, api_key, database_id)
        title_prop = _find_title_prop(schema)

        existing_pages = await _fetch_all_pages(client, api_key, database_id)
        page_map: dict[str, str] = {}
        for page in existing_pages:
            key = _extract_rich_text(page, title_prop)
            if key:
                page_map[key] = page["id"]

        seen_keys: set[str] = set()

        async def _upsert(h: dict) -> None:
            name = h.get("name", "")
            if not name:
                return
            seen_keys.add(name)

            props: dict = {title_prop: _format_value("title", name)}
            for prop_name, prop_def in schema.items():
                if prop_name == title_prop:
                    continue
                data_key = HYPERVISOR_FIELD_MAP.get(prop_name)
                if data_key is None:
                    continue
                prop_type = prop_def.get("type", "")
                formatted = _format_value(prop_type, h.get(data_key, ""))
                if formatted is not None:
                    props[prop_name] = formatted

            try:
                if name in page_map:
                    resp = await _notion_request(
                        client,
                        "PATCH",
                        f"{NOTION_API_BASE}/pages/{page_map[name]}",
                        api_key,
                        json={"properties": props},
                    )
                else:
                    resp = await _notion_request(
                        client,
                        "POST",
                        f"{NOTION_API_BASE}/pages",
                        api_key,
                        json={
                            "parent": {"database_id": database_id},
                            "properties": props,
                        },
                    )
                if resp.status_code >= 400:
                    _logger.warning(
                        "Notion 하이퍼바이저 동기화 실패 (%s, %d): %s",
                        name,
                        resp.status_code,
                        resp.text,
                    )
                    stats["errors"] += 1
                else:
                    stats["updated" if name in page_map else "created"] += 1
            except DispatcherUnavailable:
                raise
            except Exception as e:
                _logger.warning("Notion 하이퍼바이저 동기화 실패 (%s): %s", name, e)
                stats["errors"] += 1

        await _drained_parallel(_upsert(h) for h in hypervisors)

        async def _archive(key: str, page_id: str) -> None:
            try:
                resp = await _notion_request(
                    client,
                    "PATCH",
                    f"{NOTION_API_BASE}/pages/{page_id}",
                    api_key,
                    json={"archived": True},
                )
                stats["archived" if resp.status_code < 400 else "errors"] += 1
            except DispatcherUnavailable:
                raise
            except Exception as e:
                _logger.warning("Notion 하이퍼바이저 아카이브 실패 (%s): %s", key, e)
                stats["errors"] += 1

        to_archive = [(k, pid) for k, pid in page_map.items() if k not in seen_keys]
        if to_archive:
            await _drained_parallel(_archive(k, pid) for k, pid in to_archive)

    _logger.info(
        "Notion 하이퍼바이저 동기화 완료: created=%d updated=%d archived=%d errors=%d",
        stats["created"],
        stats["updated"],
        stats["archived"],
        stats["errors"],
    )
    return stats


# ---------------------------------------------------------------------------
# GPU Spec 동기화
# ---------------------------------------------------------------------------

GPU_SPEC_FIELD_MAP: dict[str, str] = {
    "vendor_id": "vendor_id",
    "device_id": "device_id",
    "is_audio": "is_audio",
    "vendor_name": "vendor_name",
    "총 사용 CPU": "total_cpu_used",
    "총 사용 RAM (G)": "total_ram_used",
    "총 사용 GPU": "total_gpu_used",
    "인스턴스 수": "instance_count",
    "사용 가능": "gpu_available",  # number — 하이퍼바이저 전체 GPU 총합
    "사용중인 GPU": "gpu_used",  # number — 인스턴스가 사용 중인 GPU 수
    "남은 GPU": "gpu_remaining",  # number — 사용 가능 - 사용중인
}

GPU_SPEC_DEFAULT_PROPERTY_TYPES: dict[str, str] = {
    "vendor_id": "rich_text",
    "device_id": "rich_text",
    "is_audio": "checkbox",
    "vendor_name": "rich_text",
    "총 사용 CPU": "number",
    "총 사용 RAM (G)": "number",
    "총 사용 GPU": "number",
    "인스턴스 수": "number",
}


async def ensure_gpu_spec_db_properties(api_key: str, database_id: str) -> None:
    """GPU spec DB에 필요한 속성이 없으면 자동 생성한다."""
    async with httpx.AsyncClient(timeout=15) as client:
        schema = await _get_db_schema(client, api_key, database_id)
        existing = set(schema.keys())

        missing: dict = {}
        for prop_name, prop_type in GPU_SPEC_DEFAULT_PROPERTY_TYPES.items():
            if prop_name not in existing:
                if prop_type == "rich_text":
                    missing[prop_name] = {"rich_text": {}}
                elif prop_type == "checkbox":
                    missing[prop_name] = {"checkbox": {}}
                elif prop_type == "number":
                    missing[prop_name] = {"number": {}}

        if not missing:
            return

        patch_resp = await _notion_request(
            client,
            "PATCH",
            f"{NOTION_API_BASE}/databases/{database_id}",
            api_key,
            json={"properties": missing},
        )
        patch_resp.raise_for_status()
        _logger.info(
            "Notion GPU spec DB 속성 %d개 자동 생성: %s",
            len(missing),
            list(missing.keys()),
        )


async def sync_gpu_specs_to_notion(
    api_key: str,
    database_id: str,
    gpu_specs: list[dict],
    usage_by_gpu: dict[str, dict] | None = None,
) -> dict:
    """GPU spec 목록을 Notion DB에 동기화한다.

    usage_by_gpu: {GPU이름: {total_cpu_used, total_ram_used, total_gpu_used, instance_count}}
    인스턴스 수집 후 집계된 리소스 사용량을 함께 기록한다.
    """
    stats = {"created": 0, "updated": 0, "archived": 0, "errors": 0}
    usage_by_gpu = usage_by_gpu or {}

    async with httpx.AsyncClient(timeout=30) as client:
        schema = await _get_db_schema(client, api_key, database_id)
        title_prop = _find_title_prop(schema)

        existing_pages = await _fetch_all_pages(client, api_key, database_id)
        page_map: dict[str, str] = {}
        for page in existing_pages:
            key = _extract_rich_text(page, title_prop)
            if key:
                page_map[key] = page["id"]

        seen_keys: set[str] = set()

        async def _upsert(spec: dict) -> None:
            name = spec.get("name", "")
            if not name:
                return
            seen_keys.add(name)

            # spec에 집계 데이터 병합 (usage_by_gpu에 해당 GPU가 있으면)
            spec_with_usage = dict(spec)
            if name in usage_by_gpu:
                spec_with_usage.update(usage_by_gpu[name])
            else:
                # 사용 중인 인스턴스가 없으면 0으로 초기화
                spec_with_usage.setdefault("total_cpu_used", 0)
                spec_with_usage.setdefault("total_ram_used", 0)
                spec_with_usage.setdefault("total_gpu_used", 0)
                spec_with_usage.setdefault("instance_count", 0)
                spec_with_usage.setdefault("gpu_available", 0)
                spec_with_usage.setdefault("gpu_used", 0)
                spec_with_usage.setdefault("gpu_remaining", 0)

            props: dict = {title_prop: _format_value("title", name)}
            for prop_name, prop_def in schema.items():
                if prop_name == title_prop:
                    continue
                data_key = GPU_SPEC_FIELD_MAP.get(prop_name)
                if data_key is None:
                    continue
                prop_type = prop_def.get("type", "")
                formatted = _format_value(prop_type, spec_with_usage.get(data_key, ""))
                if formatted is not None:
                    props[prop_name] = formatted

            try:
                if name in page_map:
                    resp = await _notion_request(
                        client,
                        "PATCH",
                        f"{NOTION_API_BASE}/pages/{page_map[name]}",
                        api_key,
                        json={"properties": props},
                    )
                else:
                    resp = await _notion_request(
                        client,
                        "POST",
                        f"{NOTION_API_BASE}/pages",
                        api_key,
                        json={
                            "parent": {"database_id": database_id},
                            "properties": props,
                        },
                    )
                if resp.status_code >= 400:
                    _logger.warning(
                        "Notion GPU spec 동기화 실패 (%s, %d): %s",
                        name,
                        resp.status_code,
                        resp.text,
                    )
                    stats["errors"] += 1
                else:
                    stats["updated" if name in page_map else "created"] += 1
            except DispatcherUnavailable:
                raise
            except Exception as e:
                _logger.warning("Notion GPU spec 동기화 실패 (%s): %s", name, e)
                stats["errors"] += 1

        await _drained_parallel(_upsert(spec) for spec in gpu_specs)

        async def _archive(key: str, page_id: str) -> None:
            try:
                resp = await _notion_request(
                    client,
                    "PATCH",
                    f"{NOTION_API_BASE}/pages/{page_id}",
                    api_key,
                    json={"archived": True},
                )
                stats["archived" if resp.status_code < 400 else "errors"] += 1
            except DispatcherUnavailable:
                raise
            except Exception as e:
                _logger.warning("Notion GPU spec 아카이브 실패 (%s): %s", key, e)
                stats["errors"] += 1

        to_archive = [(k, pid) for k, pid in page_map.items() if k not in seen_keys]
        if to_archive:
            await _drained_parallel(_archive(k, pid) for k, pid in to_archive)

    _logger.info(
        "Notion GPU spec 동기화 완료: created=%d updated=%d archived=%d errors=%d",
        stats["created"],
        stats["updated"],
        stats["archived"],
        stats["errors"],
    )
    return stats


# ---------------------------------------------------------------------------
# 사용자 DB 조회 (이메일 → page_id 매핑)
# ---------------------------------------------------------------------------


async def fetch_user_page_ids_by_email(api_key: str, users_database_id: str) -> dict[str, str]:
    """People DB에서 이메일(lower) → Notion page_id 맵을 반환한다 (조회 전용).

    인스턴스 DB의 'user' relation 속성에 설정할 page_id를 얻기 위해 사용한다.
    """
    email_to_page_id: dict[str, str] = {}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            pages = await _fetch_all_pages(client, api_key, users_database_id)
            for page in pages:
                props = page.get("properties", {})
                # 이메일: "이메일" 속성 (email 또는 rich_text 타입)
                email_prop = props.get("이메일", {})
                email = ""
                if email_prop.get("type") == "email":
                    email = email_prop.get("email", "") or ""
                elif email_prop.get("type") == "rich_text":
                    arr = email_prop.get("rich_text", [])
                    email = arr[0].get("plain_text", "") if arr else ""
                if email:
                    email_to_page_id[email.lower()] = page["id"]
    except DispatcherUnavailable:
        raise
    except Exception:
        _logger.warning("People DB 이메일 조회 실패", exc_info=True)
        if _worker_policy.get() is not None:
            raise
    return email_to_page_id


async def fetch_hypervisor_page_ids_by_name(api_key: str, hypervisors_database_id: str) -> dict[str, str]:
    """Hypervisor DB에서 이름(title) → Notion page_id 맵을 반환한다.

    인스턴스 DB의 'openstack resource' relation 속성에 설정할 page_id를 얻기 위해 사용한다.
    하이퍼바이저 동기화 완료 후 호출해야 한다.
    """
    name_to_page_id: dict[str, str] = {}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            schema = await _get_db_schema(client, api_key, hypervisors_database_id)
            title_prop = _find_title_prop(schema)
            pages = await _fetch_all_pages(client, api_key, hypervisors_database_id)
            for page in pages:
                name = _extract_rich_text(page, title_prop)
                if name:
                    name_to_page_id[name] = page["id"]
    except DispatcherUnavailable:
        raise
    except Exception:
        _logger.warning("Hypervisor DB 이름 조회 실패", exc_info=True)
        if _worker_policy.get() is not None:
            raise
    return name_to_page_id


async def fetch_gpu_spec_page_ids_by_name(api_key: str, gpu_spec_database_id: str) -> dict[str, str]:
    """GPU Spec DB에서 GPU 이름(title) → Notion page_id 맵을 반환한다.

    인스턴스 DB의 'GPU spec' relation 속성에 설정할 page_id를 얻기 위해 사용한다.
    GPU spec 동기화 완료 후 호출해야 한다.
    """
    name_to_page_id: dict[str, str] = {}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            schema = await _get_db_schema(client, api_key, gpu_spec_database_id)
            title_prop = _find_title_prop(schema)
            pages = await _fetch_all_pages(client, api_key, gpu_spec_database_id)
            for page in pages:
                name = _extract_rich_text(page, title_prop)
                if name:
                    name_to_page_id[name] = page["id"]
    except DispatcherUnavailable:
        raise
    except Exception:
        _logger.warning("GPU Spec DB 이름 조회 실패", exc_info=True)
        if _worker_policy.get() is not None:
            raise
    return name_to_page_id


async def migrate_instance_db_to_korean(api_key: str, database_id: str) -> bool:
    """인스턴스 Notion DB의 속성명을 영문에서 한국어로 일괄 변경한다.

    Redis에 마이그레이션 완료 플래그를 저장하여 1회만 실행된다.
    반환값: 마이그레이션이 실행되었으면 True, 이미 완료된 상태면 False.
    """
    from app.services.cache import _get_redis

    try:
        r = await _get_redis()
        if await r.get(REDIS_MIGRATION_KEY):
            return False  # 이미 완료됨
    except Exception:
        _logger.warning("마이그레이션 플래그 확인 실패 — 마이그레이션 생략", exc_info=True)
        return False

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            schema = await _get_db_schema(client, api_key, database_id)
            existing_names = set(schema.keys())

            rename_payload: dict = {}
            for old_name, new_name in _KO_MIGRATION_MAP.items():
                if old_name in existing_names and new_name not in existing_names:
                    rename_payload[old_name] = {"name": new_name}

            if rename_payload:
                resp = await _notion_request(
                    client,
                    "PATCH",
                    f"{NOTION_API_BASE}/databases/{database_id}",
                    api_key,
                    json={"properties": rename_payload},
                )
                resp.raise_for_status()
                _logger.info(
                    "인스턴스 DB 속성 한국어 마이그레이션 완료: %s",
                    {k: v["name"] for k, v in rename_payload.items()},
                )
            else:
                _logger.info("인스턴스 DB 한국어 마이그레이션: 변경할 속성 없음 (이미 완료됨)")

        # 완료 플래그 저장 (7일 TTL)
        try:
            r = await _get_redis()
            await r.set(REDIS_MIGRATION_KEY, "1", ex=60 * 60 * 24 * 7)
        except Exception:
            _logger.warning("마이그레이션 완료 플래그 저장 실패", exc_info=True)

        return True

    except DispatcherUnavailable:
        raise
    except Exception:
        _logger.warning("인스턴스 DB 한국어 마이그레이션 실패", exc_info=True)
        return False


# ---------------------------------------------------------------------------
# NotionTarget CRUD — 다중 연동 대상 관리
# ---------------------------------------------------------------------------


def _target_to_dict(row, include_api_key: bool = False) -> dict:
    """NotionTarget ORM row → dict."""
    from app.services.k3s_crypto import decrypt_notion_config

    api_key_raw = ""
    try:
        api_key_raw = decrypt_notion_config(row.api_key_encrypted)
    except Exception:
        _logger.warning("Notion target API key 복호화 실패 (id=%s)", row.id)

    def _iso(dt) -> str | None:
        if dt is None:
            return None
        return dt.isoformat() if hasattr(dt, "isoformat") else str(dt)

    return {
        "id": row.id,
        "label": row.label,
        "api_key": api_key_raw if include_api_key else mask_api_key(api_key_raw),
        "database_id": row.database_id or "",
        "users_database_id": row.users_database_id or "",
        "hypervisors_database_id": row.hypervisors_database_id or "",
        "gpu_spec_database_id": row.gpu_spec_database_id or "",
        "enabled": bool(row.enabled),
        "interval_minutes": row.interval_minutes or 30,
        "last_sync": _iso(row.last_sync),
        "hypervisors_last_sync": _iso(row.hypervisors_last_sync),
        "gpu_spec_last_sync": _iso(row.gpu_spec_last_sync),
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


async def list_notion_targets(include_api_key: bool = False) -> list[dict]:
    """모든 NotionTarget 목록 반환."""
    from sqlalchemy import select

    from app.database import get_session_factory, is_db_available
    from app.models.db import NotionTarget

    if not is_db_available():
        return []
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(select(NotionTarget).order_by(NotionTarget.id))
        rows = result.scalars().all()
        return [_target_to_dict(r, include_api_key=include_api_key) for r in rows]


async def get_notion_target(target_id: int, include_api_key: bool = False) -> dict | None:
    """단일 NotionTarget 반환."""
    from sqlalchemy import select

    from app.database import get_session_factory, is_db_available
    from app.models.db import NotionTarget

    if not is_db_available():
        return None
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(select(NotionTarget).where(NotionTarget.id == target_id))
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return _target_to_dict(row, include_api_key=include_api_key)


async def create_notion_target(data: dict) -> dict:
    """새 NotionTarget 생성."""
    from app.database import get_session_factory, is_db_available
    from app.models.db import NotionTarget
    from app.services.k3s_crypto import encrypt_notion_config

    if not is_db_available():
        raise RuntimeError("DB를 사용할 수 없습니다")

    encrypted = encrypt_notion_config(data["api_key"])
    factory = get_session_factory()
    async with factory() as session:
        row = NotionTarget(
            label=data.get("label") or "기본",
            api_key_encrypted=encrypted,
            database_id=data.get("database_id") or "",
            users_database_id=data.get("users_database_id") or None,
            hypervisors_database_id=data.get("hypervisors_database_id") or None,
            gpu_spec_database_id=data.get("gpu_spec_database_id") or None,
            enabled=bool(data.get("enabled", True)),
            interval_minutes=int(data.get("interval_minutes") or 30),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return _target_to_dict(row)


async def update_notion_target(target_id: int, data: dict) -> dict | None:
    """NotionTarget 업데이트. 성공 시 dict, 없으면 None."""
    from datetime import datetime

    from sqlalchemy import select

    from app.database import get_session_factory, is_db_available
    from app.models.db import NotionTarget
    from app.services.k3s_crypto import encrypt_notion_config

    if not is_db_available():
        return None

    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(select(NotionTarget).where(NotionTarget.id == target_id))
        row = result.scalar_one_or_none()
        if row is None:
            return None

        if data.get("api_key"):
            row.api_key_encrypted = encrypt_notion_config(data["api_key"])
        if "label" in data and data["label"] is not None:
            row.label = data["label"]
        if "database_id" in data:
            row.database_id = data["database_id"] or ""
        if "users_database_id" in data:
            row.users_database_id = data["users_database_id"] or None
        if "hypervisors_database_id" in data:
            row.hypervisors_database_id = data["hypervisors_database_id"] or None
        if "gpu_spec_database_id" in data:
            row.gpu_spec_database_id = data["gpu_spec_database_id"] or None
        if "enabled" in data and data["enabled"] is not None:
            row.enabled = bool(data["enabled"])
        if "interval_minutes" in data and data["interval_minutes"] is not None:
            row.interval_minutes = int(data["interval_minutes"])
        if "last_sync" in data:
            row.last_sync = _parse_dt(data["last_sync"])
        if "hypervisors_last_sync" in data:
            row.hypervisors_last_sync = _parse_dt(data["hypervisors_last_sync"])
        if "gpu_spec_last_sync" in data:
            row.gpu_spec_last_sync = _parse_dt(data["gpu_spec_last_sync"])

        row.updated_at = datetime.now(UTC)
        await worker_checkpoint()
        await session.commit()
        await session.refresh(row)
        return _target_to_dict(row)


async def delete_notion_target(target_id: int) -> bool:
    """NotionTarget 삭제. 성공 시 True."""
    from sqlalchemy import delete as sa_delete

    from app.database import get_session_factory, is_db_available
    from app.models.db import NotionTarget

    if not is_db_available():
        return False

    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(sa_delete(NotionTarget).where(NotionTarget.id == target_id))
        await session.commit()
        return (result.rowcount or 0) > 0
