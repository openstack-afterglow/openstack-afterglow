"""Opaque, single-use WebSocket tickets backed by atomic Redis consumption."""

from __future__ import annotations

import json
import re
import secrets
import time
from dataclasses import dataclass
from typing import Any, Literal

from app.services.cache import _get_redis

_TICKET_PREFIX = "afterglow:ws-ticket"
_INDEX_PREFIX = "afterglow:ws-ticket-index"
_TICKET_RE = re.compile(r"[A-Za-z0-9_-]{32,128}")
_ATOMIC_GET_DELETE = """
local value = redis.call('GET', KEYS[1])
if value then
  redis.call('DEL', KEYS[1])
end
return value
"""
_ATOMIC_RESERVED_ISSUE = """
if redis.call('EXISTS', KEYS[2]) == 1 or redis.call('EXISTS', KEYS[3]) == 1 then
  return 0
end
if not redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2], 'NX') then
  return 0
end
redis.call('SET', KEYS[2], ARGV[3], 'EX', ARGV[2])
return 1
"""
_ATOMIC_RESERVED_CONSUME = """
local raw = redis.call('GET', KEYS[1])
if not raw then
  return {0, ''}
end
local ok, envelope = pcall(cjson.decode, raw)
if not ok or envelope['kind'] ~= ARGV[1] then
  redis.call('DEL', KEYS[1])
  return {3, ''}
end
if redis.call('GET', KEYS[2]) ~= ARGV[2] then
  redis.call('DEL', KEYS[1])
  return {3, ''}
end
if redis.call('EXISTS', KEYS[3]) == 1 then
  redis.call('DEL', KEYS[1], KEYS[2])
  return {2, ''}
end
redis.call('DEL', KEYS[1], KEYS[2])
redis.call('SET', KEYS[3], ARGV[3], 'EX', ARGV[4], 'NX')
return {1, raw}
"""
_COMPARE_DELETE = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""
_COORDINATION_KEY_RE = re.compile(r"afterglow:[A-Za-z0-9:_-]{1,240}")


@dataclass(frozen=True)
class ReservedTicketResult:
    status: Literal["ok", "missing", "conflict", "invalid"]
    payload: dict[str, Any] | None = None


class WebSocketTicketError(RuntimeError):
    """Ticket storage, validation, or atomic-consumption failure."""


def _ticket_key(ticket: str) -> str:
    if _TICKET_RE.fullmatch(ticket) is None:
        raise WebSocketTicketError("invalid WebSocket ticket")
    return f"{_TICKET_PREFIX}:{ticket}"


def _index_key(kind: str, scope: str) -> str:
    if not kind or not scope or ":" in kind or ":" in scope:
        raise WebSocketTicketError("invalid WebSocket ticket index")
    return f"{_INDEX_PREFIX}:{kind}:{scope}"


def _coordination_key(value: str) -> str:
    if _COORDINATION_KEY_RE.fullmatch(value) is None:
        raise WebSocketTicketError("invalid WebSocket coordination key")
    return value


def _decode_envelope(raw: Any, *, expected_kind: str) -> dict[str, Any] | None:
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        envelope = json.loads(raw)
        payload = envelope["payload"]
        if envelope.get("kind") != expected_kind or not isinstance(payload, dict):
            return None
        return payload
    except (KeyError, TypeError, ValueError, UnicodeDecodeError):
        return None


async def issue_ticket(
    kind: str,
    payload: dict[str, Any],
    *,
    ttl_seconds: int,
    revoke_scope: str | None = None,
) -> str:
    """Store an opaque ticket; optionally index it for project-wide revocation."""
    if not kind or ":" in kind or ttl_seconds <= 0:
        raise WebSocketTicketError("invalid WebSocket ticket parameters")
    envelope = json.dumps(
        {"kind": kind, "issued_at": int(time.time()), "payload": payload},
        separators=(",", ":"),
        sort_keys=True,
    )
    try:
        redis = await _get_redis()
        for _ in range(3):
            ticket = secrets.token_urlsafe(32)
            key = _ticket_key(ticket)
            created = await redis.set(key, envelope, ex=ttl_seconds, nx=True)
            if not created:
                continue
            if revoke_scope is not None:
                index = _index_key(kind, revoke_scope)
                try:
                    async with redis.pipeline(transaction=True) as pipe:
                        pipe.sadd(index, key)
                        pipe.expire(index, ttl_seconds + 5)
                        await pipe.execute()
                except Exception:
                    await redis.delete(key)
                    raise
            return ticket
    except WebSocketTicketError:
        raise
    except Exception as exc:
        raise WebSocketTicketError("WebSocket ticket storage unavailable") from exc
    raise WebSocketTicketError("unable to allocate WebSocket ticket")


async def issue_reserved_ticket(
    kind: str,
    payload: dict[str, Any],
    *,
    ttl_seconds: int,
    reservation_key: str,
    active_key: str,
) -> str | None:
    """Atomically issue a ticket and reserve a caller-wide singleton slot."""
    reservation_key = _coordination_key(reservation_key)
    active_key = _coordination_key(active_key)
    if not kind or ":" in kind or ttl_seconds <= 0:
        raise WebSocketTicketError("invalid WebSocket ticket parameters")
    envelope = json.dumps(
        {"kind": kind, "issued_at": int(time.time()), "payload": payload},
        separators=(",", ":"),
        sort_keys=True,
    )
    try:
        redis = await _get_redis()
        for _ in range(3):
            ticket = secrets.token_urlsafe(32)
            created = await redis.eval(
                _ATOMIC_RESERVED_ISSUE,
                3,
                _ticket_key(ticket),
                reservation_key,
                active_key,
                envelope,
                ttl_seconds,
                ticket,
            )
            if int(created or 0) == 1:
                return ticket
            if await redis.exists(reservation_key) or await redis.exists(active_key):
                return None
    except WebSocketTicketError:
        raise
    except Exception as exc:
        raise WebSocketTicketError("WebSocket ticket storage unavailable") from exc
    raise WebSocketTicketError("unable to allocate WebSocket ticket")


async def peek_ticket(ticket: str, *, expected_kind: str) -> dict[str, Any] | None:
    """Read ticket metadata without consuming it; only an atomic transition may activate it."""
    try:
        redis = await _get_redis()
        raw = await redis.get(_ticket_key(ticket))
    except WebSocketTicketError:
        raise
    except Exception as exc:
        raise WebSocketTicketError("WebSocket ticket storage unavailable") from exc
    return _decode_envelope(raw, expected_kind=expected_kind) if raw is not None else None


async def consume_reserved_ticket(
    ticket: str,
    *,
    expected_kind: str,
    reservation_key: str,
    active_key: str,
    active_value: str,
    active_ttl_seconds: int,
) -> ReservedTicketResult:
    """Atomically consume a reserved ticket and promote its slot to active."""
    reservation_key = _coordination_key(reservation_key)
    active_key = _coordination_key(active_key)
    if active_ttl_seconds <= 0:
        raise WebSocketTicketError("invalid active ticket TTL")
    try:
        redis = await _get_redis()
        result = await redis.eval(
            _ATOMIC_RESERVED_CONSUME,
            3,
            _ticket_key(ticket),
            reservation_key,
            active_key,
            expected_kind,
            ticket,
            active_value,
            active_ttl_seconds,
        )
    except WebSocketTicketError:
        raise
    except Exception as exc:
        raise WebSocketTicketError("WebSocket ticket storage unavailable") from exc
    if not isinstance(result, (list, tuple)) or len(result) != 2:
        raise WebSocketTicketError("WebSocket ticket transition returned malformed data")
    status = int(result[0])
    if status == 0:
        return ReservedTicketResult("missing")
    if status == 2:
        return ReservedTicketResult("conflict")
    if status == 3:
        return ReservedTicketResult("invalid")
    payload = _decode_envelope(result[1], expected_kind=expected_kind)
    return ReservedTicketResult("ok", payload) if payload is not None else ReservedTicketResult("invalid")


async def compare_delete(key: str, expected_value: str) -> bool:
    """Delete a coordination key only when it still belongs to the caller."""
    try:
        redis = await _get_redis()
        deleted = await redis.eval(_COMPARE_DELETE, 1, _coordination_key(key), expected_value)
        return int(deleted or 0) == 1
    except WebSocketTicketError:
        raise
    except Exception as exc:
        raise WebSocketTicketError("WebSocket coordination storage unavailable") from exc


async def consume_ticket(ticket: str, *, expected_kind: str) -> dict[str, Any] | None:
    """Atomically consume one ticket and return its validated payload."""
    key = _ticket_key(ticket)
    try:
        redis = await _get_redis()
        raw = await redis.eval(_ATOMIC_GET_DELETE, 1, key)
    except WebSocketTicketError:
        raise
    except Exception as exc:
        raise WebSocketTicketError("WebSocket ticket storage unavailable") from exc
    if raw is None:
        return None
    payload = _decode_envelope(raw, expected_kind=expected_kind)
    if payload is None:
        return None

    scope = payload.get("project_id")
    if isinstance(scope, str) and scope:
        try:
            await redis.srem(_index_key(expected_kind, scope), key)
        except Exception:
            # Consumption already succeeded. A stale index member cannot replay the ticket.
            pass
    return payload


async def revoke_tickets(*, kind: str, scope: str) -> None:
    """Delete every currently indexed ticket for one security scope."""
    index = _index_key(kind, scope)
    try:
        redis = await _get_redis()
        members = await redis.smembers(index)
        keys = [member.decode("utf-8") if isinstance(member, bytes) else str(member) for member in members]
        if keys:
            await redis.delete(*keys)
        await redis.delete(index)
    except Exception as exc:
        raise WebSocketTicketError("WebSocket ticket revocation unavailable") from exc
