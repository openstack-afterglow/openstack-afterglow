"""Refresh JTI → immutable identity, working-domain session with atomic family revocation.

키 스킴: afterglow:refresh:{jti}
TTL: refresh JWT 만료까지 남은 초 (exp - now)

access JWT의 rjti 필드가 이 키를 가리킨다.
started_at은 최초 로그인 시각이며 refresh/rescope의 원자적 회전에도 유지한다.
Only an explicit previous_domain_id compare permits a working-domain switch;
identity_domain_id always remains the original authentication namespace.
Family aliases resolve only revocation targets; access/refresh always require the
current JTI's own record, so rotation never makes an old credential reusable.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import UTC, datetime

from app.services.cache import _get_redis

_PREFIX = "afterglow:refresh:"
_USER_INDEX_PREFIX = "afterglow:user-sessions:"
_FAMILY_PREFIX = "afterglow:session-family:"
_FAMILY_ALIAS_PREFIX = "afterglow:refresh-family:"
_TOUCH_THROTTLE_SECONDS = 60  # last_ip/fp 갱신 최소 간격 (Redis 쓰기 폭증 방지)
_SENSITIVE_KEYS = {"keystone_token", "family_id"}  # internal authority, never session-list metadata

_logger = logging.getLogger(__name__)

_UPDATE_TOKEN_SCRIPT = """
local raw = redis.call('GET', KEYS[1])
if not raw then return 0 end
local data = cjson.decode(raw)
if data['blacklisted'] == true then return 0 end
if ARGV[2] ~= '' and data['keystone_token'] ~= ARGV[2] then return 0 end
if data['keystone_token'] == ARGV[1] then return 1 end
data['keystone_token'] = ARGV[1]
local pttl = redis.call('PTTL', KEYS[1])
local new_raw = cjson.encode(data)
if pttl > 0 then
    redis.call('SET', KEYS[1], new_raw, 'PX', pttl)
elseif pttl == -1 then
    redis.call('SET', KEYS[1], new_raw)
end
return 1
"""

_BLACKLIST_SCRIPT = """
local raw = redis.call('GET', KEYS[1])
if not raw then return nil end
local data = cjson.decode(raw)
if data['blacklisted'] == true and data['blacklist_reason'] == ARGV[1] then
    return nil
end
data['blacklisted'] = true
data['blacklist_reason'] = ARGV[1]
local pttl = redis.call('PTTL', KEYS[1])
local new_raw = cjson.encode(data)
if pttl > 0 then
    redis.call('SET', KEYS[1], new_raw, 'PX', pttl)
elseif pttl == -1 then
    redis.call('SET', KEYS[1], new_raw)
end
return 1
"""

_TOUCH_SEEN_SCRIPT = """
local raw = redis.call('GET', KEYS[1])
if not raw then return nil end
local data = cjson.decode(raw)
local now = tonumber(ARGV[3])
local throttle = tonumber(ARGV[4])
local last_seen = tonumber(data['last_seen'] or 0)
if data['last_ip'] == ARGV[1] and data['last_fp'] == ARGV[2] and (now - last_seen) < throttle then
    return nil
end
data['last_ip'] = ARGV[1]
data['last_fp'] = ARGV[2]
data['last_seen'] = now
local pttl = redis.call('PTTL', KEYS[1])
local new_raw = cjson.encode(data)
if pttl > 0 then
    redis.call('SET', KEYS[1], new_raw, 'PX', pttl)
elseif pttl == -1 then
    redis.call('SET', KEYS[1], new_raw)
end
return 1
"""

_START_SESSION_SCRIPT = """
local raw = redis.call('GET', KEYS[1])
if not raw then return nil end
local data = cjson.decode(raw)
if not data['started_at'] then
    -- Preserve the old timeout marker when migrating an existing session.
    local legacy = tonumber(redis.call('GET', KEYS[2]))
    local issued = tonumber(ARGV[1])
    data['started_at'] = legacy and math.min(legacy, issued) or issued
    local pttl = redis.call('PTTL', KEYS[1])
    if pttl <= 0 then return nil end
    redis.call('SET', KEYS[1], cjson.encode(data), 'PX', pttl)
end
return tostring(data['started_at'])
"""

_ROTATE_SESSION_SCRIPT = """
local raw = redis.call('GET', KEYS[1])
if not raw then return 0 end
local old = cjson.decode(raw)
local replacement = cjson.decode(ARGV[1])
local identity = old['identity_domain_id']
-- Pre-multidomain records belong to their old domain, never the requested target.
if not identity or identity == '' then identity = old['domain_id'] end
if old['user_id'] ~= replacement['user_id'] or old['blacklisted'] == true
    or not old['domain_id'] or old['domain_id'] == ''
    or replacement['domain_id'] == ''
    or old['domain_id'] ~= ARGV[7]
    or identity ~= replacement['identity_domain_id'] then
    return 0
end
local start = tonumber(old['started_at'])
if not start or tonumber(ARGV[5]) >= start + tonumber(ARGV[6]) then
    redis.call('DEL', KEYS[1])
    redis.call('SREM', KEYS[3], ARGV[3])
    return 0
end
-- The current record, not a snapshot read before Keystone validation, owns
-- the immutable login origin and absolute lifetime.
replacement['started_at'] = start
replacement['identity_domain_id'] = identity
for _, field in ipairs({'origin_ip', 'origin_fp', 'device_type', 'os', 'auth_method', 'provider_id', 'provider_revision', 'provider_domain_id', 'login_email'}) do
    replacement[field] = old[field] or ''
end
local family = old['family_id'] or ARGV[3]
local family_key = 'afterglow:session-family:' .. family
local current = redis.call('GET', family_key)
if current and current ~= ARGV[3] then return 0 end
replacement['family_id'] = family
redis.call('SETEX', family_key, ARGV[2], ARGV[4])
redis.call('SETEX', 'afterglow:refresh-family:' .. ARGV[3], ARGV[2], family)
redis.call('SETEX', 'afterglow:refresh-family:' .. ARGV[4], ARGV[2], family)
redis.call('SETEX', KEYS[2], ARGV[2], cjson.encode(replacement))
redis.call('DEL', KEYS[1])
redis.call('SREM', KEYS[3], ARGV[3])
redis.call('SADD', KEYS[3], ARGV[4])
local ttl = redis.call('TTL', KEYS[3])
if ttl < tonumber(ARGV[2]) then redis.call('EXPIRE', KEYS[3], ARGV[2]) end
return 1
"""


_REVOKE_USER_SCRIPT = """
local jtis = redis.call('SMEMBERS', KEYS[1])
local deleted = {}
for _, jti in ipairs(jtis) do
    local key = 'afterglow:refresh:' .. jti
    local raw = redis.call('GET', key)
    if raw then
        local data = cjson.decode(raw)
        if data['user_id'] == ARGV[1] then
            table.insert(deleted, raw)
            redis.call('DEL', key)
            local family = data['family_id'] or jti
            local family_key = 'afterglow:session-family:' .. family
            if redis.call('GET', family_key) == jti then redis.call('DEL', family_key) end
        end
    end
end
redis.call('DEL', KEYS[1])
return deleted
"""

_DELETE_SESSION_SCRIPT = """
local requested = ARGV[1]
local raw = redis.call('GET', KEYS[1])
local family = redis.call('GET', KEYS[2]) or requested
if raw then family = cjson.decode(raw)['family_id'] or requested end
local family_key = 'afterglow:session-family:' .. family
local current = redis.call('GET', family_key) or requested
raw = redis.call('GET', 'afterglow:refresh:' .. current)
if not raw then
    if ARGV[2] ~= '' then
        local index = 'afterglow:user-sessions:' .. ARGV[2]
        if redis.call('SISMEMBER', index, requested) == 1 then
            redis.call('SREM', index, requested)
            return {1, ''}
        end
    end
    return {0, ''}
end
local data = cjson.decode(raw)
local user_id = data['user_id']
if not user_id or (ARGV[2] ~= '' and user_id ~= ARGV[2]) then return {0, ''} end
if (data['family_id'] or current) ~= family then return {0, ''} end
local index = 'afterglow:user-sessions:' .. user_id
if ARGV[2] ~= '' and redis.call('SISMEMBER', index, current) ~= 1 then return {0, ''} end
redis.call('DEL', 'afterglow:refresh:' .. current, family_key)
redis.call('SREM', index, current)
return {1, raw}
"""


def _key(jti: str) -> str:
    return f"{_PREFIX}{jti}"


def _user_index_key(user_id: str) -> str:
    return f"{_USER_INDEX_PREFIX}{user_id}"


async def store_session(
    jti: str,
    keystone_token: str,
    project_id: str,
    user_id: str,
    exp: int,
    auth_method: str = "password",
    origin_ip: str = "",
    origin_fp: str = "",
    device_type: str = "",
    os: str = "",
    started_at: float | None = None,
    previous_jti: str | None = None,
    timeout_seconds: int | None = None,
    domain_id: str = "",
    provider_id: str = "",
    provider_revision: int | None = None,
    provider_domain_id: str = "",
    login_email: str = "",
    identity_domain_id: str = "",
    previous_domain_id: str | None = None,
    target_project_id: str | None = None,
    target_project_name: str = "",
) -> bool:
    """Store a login or atomically replace an active previous refresh record.

    A replacement returns False when the previous record was consumed, expired,
    revoked, blacklisted, or has a different subject/identity. Ordinary rotation
    requires the same working domain; an authenticated switch must explicitly
    compare previous_domain_id with the latest old record. The old record owns
    the immutable identity, login lifetime, origin, and authentication metadata.
    Legacy callers omitting identity_domain_id use domain_id for the new record;
    legacy stored records normalize identity only from their own old domain_id.
    """
    r = await _get_redis()
    now = int(datetime.now(UTC).timestamp())
    ttl = max(exp - now, 1)
    data = json.dumps(
        {
            "keystone_token": keystone_token,
            "project_id": project_id,
            "target_project_id": target_project_id,
            "target_project_name": target_project_name,
            "user_id": user_id,
            "family_id": jti,
            "domain_id": domain_id,
            "identity_domain_id": identity_domain_id or domain_id,
            "provider_id": provider_id,
            "provider_revision": provider_revision,
            "provider_domain_id": provider_domain_id,
            "login_email": login_email,
            "exp": exp,
            "started_at": now if started_at is None else started_at,
            "auth_method": auth_method,
            # 출처 바인딩 필드 (최초 로그인 시 설정, 회전 너머 그대로 운반)
            "origin_ip": origin_ip,
            "origin_fp": origin_fp,
            # 마지막 사용 위치 (매 요청마다 쓰로틀 갱신)
            "last_ip": origin_ip,
            "last_fp": origin_fp,
            "last_seen": now,
            # 블랙리스트 (출처 불일치 자동 차단 또는 수동 플래그)
            "blacklisted": False,
            "blacklist_reason": "",
            # 기기 정보 (coarse 요약 — raw UA 미저장)
            "device_type": device_type,
            "os": os,
        }
    )
    if previous_jti is not None:
        if timeout_seconds is None or timeout_seconds <= 0:
            raise ValueError("Session rotation requires a positive absolute timeout")
        return bool(
            await r.eval(
                _ROTATE_SESSION_SCRIPT,
                3,
                _key(previous_jti),
                _key(jti),
                _user_index_key(user_id),
                data,
                ttl,
                previous_jti,
                jti,
                now,
                timeout_seconds,
                domain_id if previous_domain_id is None else previous_domain_id,
            )
        )
    async with r.pipeline() as pipe:
        pipe.setex(_key(jti), ttl, data)
        pipe.setex(f"{_FAMILY_PREFIX}{jti}", ttl, jti)
        pipe.sadd(_user_index_key(user_id), jti)
        pipe.expire(_user_index_key(user_id), ttl)
        await pipe.execute()
    return True


async def ensure_session_started_at(jti: str, project_id: str, issued_at: float) -> float | None:
    """Persist an existing session's start once without extending its Redis TTL."""
    r = await _get_redis()
    token_hash = hashlib.sha256(jti.encode()).hexdigest()
    legacy_key = f"afterglow:session_start:{token_hash}:{project_id or 'noscope'}"
    started_at = await r.eval(_START_SESSION_SCRIPT, 2, _key(jti), legacy_key, issued_at)
    return None if started_at is None else float(started_at)


async def get_session(jti: str) -> dict | None:
    """refresh JTI로 세션 데이터 조회. 없으면 None."""
    r = await _get_redis()
    raw = await r.get(_key(jti))
    if raw is None:
        return None
    return json.loads(raw)


async def _delete_family(jti: str, user_id: str = "") -> tuple[bool, dict | None]:
    r = await _get_redis()
    removed, raw = await r.eval(_DELETE_SESSION_SCRIPT, 2, _key(jti), f"{_FAMILY_ALIAS_PREFIX}{jti}", jti, user_id)
    return bool(removed), json.loads(raw) if raw else None


async def delete_session(jti: str) -> dict | None:
    """Invalidate the family and return its current native subject for revocation."""
    _, session = await _delete_family(jti)
    return session


async def update_session_token(jti: str, new_keystone_token: str, *, expected_token: str = "") -> bool:
    """Persist verified unscoped proof without recreating/overwriting a session.

    CAS prevents an in-flight access validation replacing a newer proof. Redis
    serialization preserves origin, lifetime, family and blacklist fields.
    """
    r = await _get_redis()
    return bool(await r.eval(_UPDATE_TOKEN_SCRIPT, 1, _key(jti), new_keystone_token, expected_token))


async def revoke_user_sessions(user_id: str, *, revoke_keystone: bool = True, strict_keystone: bool = False) -> int:
    """Atomically delete every current family and capture its native token.

    Lua shares Redis serialization with rotation. Native revocation happens only
    after the browser credentials are gone; a slow provider cannot orphan a new
    JTI or block Redis's atomic decision. Strict callers observe provider failure
    after every captured token has been attempted; removed families stay removed.
    """
    r = await _get_redis()
    deleted = await r.eval(_REVOKE_USER_SCRIPT, 1, _user_index_key(user_id), user_id)
    native_failed = False
    if revoke_keystone:
        from app.services import keystone

        for raw in deleted:
            token = json.loads(raw).get("keystone_token")
            if token:
                try:
                    await asyncio.to_thread(keystone.revoke_token, token)
                except Exception:
                    native_failed = True
                    _logger.warning("Native token revocation failed after atomic session removal", exc_info=True)
    if native_failed and strict_keystone:
        raise RuntimeError("Native token revocation failed after atomic session removal")
    return len(deleted)


async def blacklist_session(jti: str, reason: str = "") -> None:
    """세션을 블랙리스트에 등록. 이후 인증 게이트에서 즉시 차단된다.

    TTL은 기존 값 유지 — 세션이 만료되면 자동 제거.
    이미 삭제된 세션이면 no-op.
    """
    r = await _get_redis()
    await r.eval(_BLACKLIST_SCRIPT, 1, _key(jti), reason)


def session_seen_needs_touch(session: dict, ip: str, fp: str, *, now: int | None = None) -> bool:
    """Redis EVAL 전에 이미 읽은 세션으로 last_seen 갱신 필요 여부를 판정한다."""
    if session.get("last_ip") != ip or session.get("last_fp") != fp:
        return True
    try:
        last_seen = int(session.get("last_seen", 0))
    except (TypeError, ValueError):
        return True
    current = now if now is not None else int(datetime.now(UTC).timestamp())
    return current - last_seen >= _TOUCH_THROTTLE_SECONDS


async def touch_session_seen(jti: str, ip: str, fp: str) -> None:
    """last_ip / last_fp / last_seen 갱신 (마지막 사용 위치 추적).

    쓰로틀: ip·fp가 동일하고 last_seen이 60초 이내면 스킵 (Redis 쓰기 폭증 방지).
    """
    r = await _get_redis()
    now = int(datetime.now(UTC).timestamp())
    await r.eval(_TOUCH_SEEN_SCRIPT, 1, _key(jti), ip, fp, str(now), str(_TOUCH_THROTTLE_SECONDS))


async def delete_session_owned(user_id: str, jti: str, *, revoke_keystone: bool = True) -> bool:
    """Revoke the owned login family even if the listed JTI rotated meanwhile."""
    removed, session = await _delete_family(jti, user_id)
    if removed and session is not None and revoke_keystone:
        token = session.get("keystone_token")
        if token:
            from app.services import keystone

            try:
                await asyncio.to_thread(keystone.revoke_token, token)
            except Exception:
                _logger.warning("Native token revocation failed after atomic family removal", exc_info=True)
    return removed


async def list_user_sessions(user_id: str) -> list[dict]:
    """사용자의 활성 세션 목록 반환 (keystone_token 등 민감 필드 제거).

    user-index SET + 각 세션 JSON 조회. 만료된 스테일 항목은 인덱스에서 정리.
    셀프서비스 (/api/v1/auth/sessions) 및 관리자 (/api/v1/admin/users/{id}/sessions) 공용.
    """
    r = await _get_redis()
    index_key = _user_index_key(user_id)
    raw_jtis = await r.smembers(index_key)
    if not raw_jtis:
        return []
    jtis = [j.decode() if isinstance(j, bytes) else j for j in raw_jtis]
    sessions: list[dict] = []
    stale: list[str] = []
    for jti in jtis:
        raw = await r.get(_key(jti))
        if raw is None:
            stale.append(jti)
            continue
        try:
            sess = json.loads(raw)
            safe = {k: v for k, v in sess.items() if k not in _SENSITIVE_KEYS}
            safe["jti"] = jti
            sessions.append(safe)
        except Exception:
            stale.append(jti)
    # 스테일 인덱스 정리 (fire-and-forget)
    if stale:
        try:
            await r.srem(index_key, *stale)
        except Exception:
            pass
    return sessions
