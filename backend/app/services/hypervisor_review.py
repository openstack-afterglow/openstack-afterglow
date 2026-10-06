"""Short-lived host review tickets and caller/cloud-scoped mutation exclusion."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import secrets
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime, timedelta

from anyio import CancelScope
from fastapi import HTTPException

from app.services.cache import _get_redis
from app.services.ws_ticket import WebSocketTicketError, compare_delete, consume_ticket, issue_ticket

_logger = logging.getLogger(__name__)
REVIEW_TTL_SECONDS = 300
_LOCK_TTL_SECONDS = 120
_TICKET_KIND = "hypervisor-removal"
_RENEW_LOCK = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('EXPIRE', KEYS[1], ARGV[2])
end
return 0
"""


def cloud_identity(conn) -> str:
    endpoint = conn.compute.get_endpoint()
    if not isinstance(endpoint, str) or not endpoint:
        raise HTTPException(status_code=503, detail="Nova 연결을 확인할 수 없습니다")
    return hashlib.sha256(endpoint.rstrip("/").encode()).hexdigest()


def _uptime_key(conn, hypervisor_id: str) -> str:
    host_key = hashlib.sha256(hypervisor_id.encode()).hexdigest()
    return f"afterglow:hypervisor-uptime:{cloud_identity(conn)}:{host_key}"


async def remember_uptime(conn, hypervisor_id: str, service_id: str, value: str, host_time: str | None) -> str:
    """Keep an actual observed sample, never a liveness or removal safety verdict."""
    observed_at = datetime.now(UTC).isoformat()
    try:
        redis = await _get_redis()
        await redis.setex(
            _uptime_key(conn, hypervisor_id),
            30 * 24 * 60 * 60,
            json.dumps({"service_id": service_id, "value": value, "host_time": host_time, "observed_at": observed_at}),
        )
    except Exception:
        _logger.warning("호스트 업타임 관측값 저장 실패: %s", hypervisor_id)
    return observed_at


async def enrich_uptime(conn, report: dict) -> None:
    uptime = report["uptime"]
    if uptime["status"] == "available" and uptime.get("value"):
        observed_at = await remember_uptime(
            conn, report["hypervisor_id"], report["service"]["id"], uptime["value"], uptime.get("host_time")
        )
        report["uptime"] = {**uptime, "source": "live", "observed_at": observed_at}
        return
    report["uptime"] = {**uptime, "source": "unavailable", "observed_at": None}
    try:
        redis = await _get_redis()
        raw = await redis.get(_uptime_key(conn, report["hypervisor_id"]))
        sample = json.loads(raw) if raw else None
        if (
            isinstance(sample, dict)
            and sample.get("service_id") == report["service"]["id"]
            and isinstance(sample.get("value"), str)
            and sample["value"]
            and isinstance(sample.get("observed_at"), str)
        ):
            report["uptime"] = {
                "status": "unavailable",
                "source": "last_observed",
                "value": sample["value"],
                "host_time": sample.get("host_time"),
                "observed_at": sample["observed_at"],
            }
    except Exception:
        _logger.warning("호스트 이전 업타임 관측값 조회 실패: %s", report["hypervisor_id"])


def _caller_context(conn, token_info: dict) -> dict:
    user_id, project_id = token_info.get("user_id"), token_info.get("project_id")
    if not isinstance(user_id, str) or not user_id or not isinstance(project_id, str) or not project_id:
        raise HTTPException(status_code=403, detail="승인자의 사용자·프로젝트를 확인할 수 없습니다")
    return {"user_id": user_id, "project_id": project_id, "cloud": cloud_identity(conn)}


async def issue_review(conn, token_info: dict, report: dict, fingerprint: str) -> tuple[str, str]:
    expires = datetime.now(UTC) + timedelta(seconds=REVIEW_TTL_SECONDS)
    payload = {
        **_caller_context(conn, token_info),
        "hypervisor_id": report["hypervisor_id"],
        "hostname": report["hostname"],
        "service_id": report["service"]["id"],
        "fingerprint": fingerprint,
        "checked_at": report["checked_at"],
        "checks": report["checks"],
        "expires_at": expires.timestamp(),
    }
    try:
        ticket = await issue_ticket(_TICKET_KIND, payload, ttl_seconds=REVIEW_TTL_SECONDS)
    except WebSocketTicketError:
        raise HTTPException(status_code=503, detail="제거 승인 정보를 저장할 수 없습니다") from None
    return ticket, expires.isoformat()


def assert_review_current(review: dict) -> None:
    if review.get("expires_at", 0) <= datetime.now(UTC).timestamp():
        raise HTTPException(status_code=409, detail="점검 승인이 만료되었습니다. 다시 점검하세요")


async def consume_review(conn, token_info: dict, hypervisor_id: str, ticket: str) -> dict:
    try:
        payload = await consume_ticket(ticket, expected_kind=_TICKET_KIND)
    except WebSocketTicketError:
        raise HTTPException(status_code=503, detail="제거 승인 정보를 확인할 수 없습니다") from None
    if payload is None:
        raise HTTPException(status_code=409, detail="점검 승인이 만료되었거나 이미 사용되었습니다. 다시 점검하세요")
    assert_review_current(payload)
    context = _caller_context(conn, token_info)
    if (
        any(payload.get(key) != value for key, value in context.items())
        or payload.get("hypervisor_id") != hypervisor_id
    ):
        raise HTTPException(status_code=409, detail="점검 승인의 사용자·프로젝트·호스트가 일치하지 않습니다")
    return payload


class HostOperationLease:
    def __init__(self, redis, key: str, owner: str):
        self.redis, self.key, self.owner = redis, key, owner
        self.lost = False

    async def assert_owned(self) -> None:
        try:
            value = await self.redis.get(self.key)
        except Exception:
            self.lost = True
            raise HTTPException(status_code=503, detail="호스트 작업 잠금을 확인할 수 없습니다") from None
        if isinstance(value, bytes):
            value = value.decode()
        if self.lost or not isinstance(value, str) or not hmac.compare_digest(value, self.owner):
            raise HTTPException(status_code=409, detail="호스트 작업 잠금이 만료되었습니다. 다시 점검하세요")

    async def renew(self) -> None:
        while True:
            await asyncio.sleep(_LOCK_TTL_SECONDS / 3)
            try:
                renewed = await self.redis.eval(_RENEW_LOCK, 1, self.key, self.owner, _LOCK_TTL_SECONDS)
                if int(renewed or 0) != 1:
                    self.lost = True
                    return
            except Exception:
                self.lost = True
                return


@asynccontextmanager
async def host_operation_lock(conn, hypervisor_id: str):
    host_key = hashlib.sha256(hypervisor_id.encode()).hexdigest()
    key = f"afterglow:hypervisor-operation:{cloud_identity(conn)}:{host_key}"
    owner = secrets.token_hex(24)
    try:
        redis = await _get_redis()
        acquired = await redis.set(key, owner, nx=True, ex=_LOCK_TTL_SECONDS)
    except Exception:
        raise HTTPException(status_code=503, detail="호스트 작업 잠금을 확보할 수 없습니다") from None
    if not acquired:
        raise HTTPException(status_code=409, detail="이 호스트의 다른 운영 작업이 진행 중입니다")
    lease = HostOperationLease(redis, key, owner)
    renewal = asyncio.create_task(lease.renew())
    try:
        yield lease
    finally:
        with CancelScope(shield=True):
            renewal.cancel()
            with suppress(asyncio.CancelledError):
                await renewal
            try:
                await compare_delete(key, owner)
            except WebSocketTicketError:
                _logger.warning("호스트 작업 잠금 해제 실패: %s", hypervisor_id)


async def host_work(fn, *args):
    """Do not release a host lock while a cancelled request's SDK thread still runs."""
    work = asyncio.create_task(asyncio.to_thread(fn, *args))
    try:
        return await asyncio.shield(work)
    except asyncio.CancelledError:
        # FastAPI middleware uses level cancellation: every unshielded await can
        # be cancelled again, even after the first CancelledError was caught.
        with CancelScope(shield=True):
            while not work.done():
                try:
                    await asyncio.shield(work)
                except asyncio.CancelledError:
                    continue
                except Exception:
                    break
            with suppress(Exception):
                work.result()
        raise
