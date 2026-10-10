"""Refresh JTI → {keystone_token, project_id, user_id, exp, started_at} 세션 저장소.

키 스킴: afterglow:refresh:{jti}
TTL: refresh JWT 만료까지 남은 초 (exp - now)

access JWT의 rjti 필드가 이 키를 가리킨다.
started_at은 최초 로그인 시각이며 refresh/rescope의 원자적 회전에도 유지한다.
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
_TOUCH_THROTTLE_SECONDS = 60  # last_ip/fp 갱신 최소 간격 (Redis 쓰기 폭증 방지)
_SENSITIVE_KEYS = {"keystone_token"}  # list_user_sessions에서 제거할 민감 필드

_logger = logging.getLogger(__name__)

_UPDATE_TOKEN_SCRIPT = """
local raw = redis.call('GET', KEYS[1])
if not raw then return nil end
local data = cjson.decode(raw)
if data['keystone_token'] == ARGV[1] then
    return nil
end
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
if old['user_id'] ~= replacement['user_id'] or old['blacklisted'] == true then
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
for _, field in ipairs({'origin_ip', 'origin_fp', 'device_type', 'os', 'auth_method'}) do
    replacement[field] = old[field] or ''
end
redis.call('SETEX', KEYS[2], ARGV[2], cjson.encode(replacement))
redis.call('DEL', KEYS[1])
redis.call('SREM', KEYS[3], ARGV[3])
redis.call('SADD', KEYS[3], ARGV[4])
local ttl = redis.call('TTL', KEYS[3])
if ttl < tonumber(ARGV[2]) then redis.call('EXPIRE', KEYS[3], ARGV[2]) end
return 1
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
) -> bool:
    """Store a login or atomically replace an active previous refresh record.

    A replacement returns False when the previous record was consumed, expired,
    revoked or blacklisted. Its original login lifetime and origin are preserved.
    """
    r = await _get_redis()
    now = int(datetime.now(UTC).timestamp())
    ttl = max(exp - now, 1)
    data = json.dumps(
        {
            "keystone_token": keystone_token,
            "project_id": project_id,
            "user_id": user_id,
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
            )
        )
    async with r.pipeline() as pipe:
        pipe.setex(_key(jti), ttl, data)
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


async def delete_session(jti: str) -> None:
    """refresh JTI 세션 삭제. 로그아웃·토큰 회전 시 호출."""
    r = await _get_redis()
    raw = await r.get(_key(jti))
    if raw:
        try:
            sess = json.loads(raw)
            uid = sess.get("user_id", "")
            if uid:
                await r.srem(_user_index_key(uid), jti)
        except Exception:
            pass
    await r.delete(_key(jti))


async def update_session_token(jti: str, new_keystone_token: str) -> None:
    """세션의 keystone_token을 새 토큰으로 갱신. TTL은 기존 값 유지.

    validate_token이 POST /v3/auth/tokens으로 새 Keystone 토큰을 발급할 때 호출.
    원본 토큰이 만료되기 전에 세션을 갱신해 1시간 TTL 문제를 방지.
    """
    r = await _get_redis()
    await r.eval(_UPDATE_TOKEN_SCRIPT, 1, _key(jti), new_keystone_token)


async def revoke_user_sessions(user_id: str, *, revoke_keystone: bool = True) -> int:
    """사용자의 모든 refresh 세션을 즉시 삭제.

    revoke_keystone=True(기본)이면 각 세션의 Keystone 토큰도 폐기한다
    (DELETE /v3/auth/tokens). best-effort — 개별 실패는 warning 후 계속.

    admin role 박탈, 전체 로그아웃 등 강제 로그아웃 시 호출.

    Returns:
        삭제된 세션 수
    """
    r = await _get_redis()
    index_key = _user_index_key(user_id)
    raw_jtis = await r.smembers(index_key)
    if not raw_jtis:
        return 0
    jtis = [j.decode() if isinstance(j, bytes) else j for j in raw_jtis]

    # Keystone 직접 폐기 (삭제 전에 토큰 수집)
    if revoke_keystone:
        from app.services import keystone  # 순환 임포트 방지용 지연 임포트

        ks_tokens: list[str] = []
        for jti in jtis:
            raw = await r.get(_key(jti))
            if raw:
                try:
                    sess = json.loads(raw)
                    tok = sess.get("keystone_token", "")
                    if tok:
                        ks_tokens.append(tok)
                except Exception:
                    pass

        # 각 Keystone 토큰 폐기 (best-effort — 실패해도 Redis 삭제는 진행)
        for tok in ks_tokens:
            try:
                await asyncio.to_thread(keystone.revoke_token, tok)
            except Exception:
                _logger.warning("revoke_user_sessions: Keystone revoke 실패 (user_id=%s)", user_id, exc_info=True)

    keys = [_key(jti) for jti in jtis] + [index_key]
    await r.delete(*keys)
    return len(jtis)


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
    """소유권 확인 후 개별 세션 삭제.

    jti가 user_id의 세션 인덱스에 없으면 False 반환 — 호출자는 404로 응답한다.
    소유권이 확인되면 Keystone 토큰도 폐기(best-effort) 후 세션 삭제 → True 반환.

    보안: 인덱스 통과 후 세션 데이터의 user_id를 재검증하여 stale/오염된
    Redis 인덱스로 인해 타인의 세션을 삭제하는 것을 방지한다.
    """
    r = await _get_redis()
    is_member = await r.sismember(_user_index_key(user_id), jti)
    if not is_member:
        return False

    # raw를 한 번만 읽어 소유권 재검증 + Keystone revoke에 재사용
    raw = await r.get(_key(jti))
    sess: dict | None = None
    if raw:
        try:
            sess = json.loads(raw)
        except Exception:
            pass

    # 소유권 이중 검증: 인덱스뿐만 아니라 세션 데이터의 user_id도 확인
    if sess is not None and sess.get("user_id") != user_id:
        _logger.warning(
            "delete_session_owned: 인덱스-데이터 user_id 불일치 "
            "(index_user=%s, data_user=%s, jti=%s) — Redis 인덱스 오염 의심",
            user_id,
            sess.get("user_id"),
            jti,
        )
        return False

    if revoke_keystone and sess is not None:
        ks_token = sess.get("keystone_token", "")
        if ks_token:
            from app.services import keystone  # 순환 임포트 방지용 지연 임포트

            try:
                await asyncio.to_thread(keystone.revoke_token, ks_token)
            except Exception:
                _logger.warning("delete_session_owned: Keystone revoke 실패 (jti=%s)", jti, exc_info=True)

    await delete_session(jti)
    return True


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
