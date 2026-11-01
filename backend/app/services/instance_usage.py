"""Instance usage policy stored only in Nova metadata.

Redis holds renewable, expiring operation locks, never a schedule or its revision.
Native users able to edit server metadata can also edit this policy; this is not
an enforcement boundary against independent Nova metadata writers.
"""

from __future__ import annotations

import asyncio
import calendar
import hashlib
import secrets
from collections.abc import Mapping
from contextlib import asynccontextmanager, suppress
from copy import copy
from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi import HTTPException
from pydantic import ValidationError

from app.models.instance_usage import (
    UsageScheduleExtension,
    UsageScheduleInfo,
    UsageScheduleRequest,
    UsageScheduleUpdate,
    aware_timestamp,
    metadata_text,
)
from app.services.cache import _get_redis
from app.services.gpu_inventory import is_gpu_flavor

METADATA_PREFIX = "afterglow_usage_"
LEASE_SECONDS = 90
_REQUIRED = frozenset(
    {"version", "starts_at", "expires_at", "action", "delete_volumes", "reason", "revision", "state", "source"}
)
_OPTIONAL = frozenset({"last_error", "extended_at", "extended_by"})
_RENEW = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('expire', KEYS[1], ARGV[2])
end
return 0
"""
_RELEASE = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
"""


def _field(value, key, default=None):
    return value.get(key, default) if isinstance(value, Mapping) else getattr(value, key, default)


def _clock(now=None):
    # Browser datetime round-trips must not accidentally shorten a default expiry.
    return aware_timestamp(now if now is not None else datetime.now(UTC)).replace(microsecond=0)


def calendar_month_after(value: datetime) -> datetime:
    value = _clock(value)
    year, month = (value.year + 1, 1) if value.month == 12 else (value.year, value.month + 1)
    return value.replace(year=year, month=month, day=min(value.day, calendar.monthrange(year, month)[1]))


def requires_schedule(flavor) -> bool:
    """Additive designation cannot disable GPU or automatic CPU/RAM criteria."""
    specs = _field(flavor, "extra_specs", {}) or {}
    if not isinstance(specs, Mapping):
        specs = {}

    def amount(name):
        raw = _field(flavor, name, 0)
        if isinstance(raw, bool):
            return 0
        try:
            return int(raw) if isinstance(raw, (int, str)) else 0
        except (ValueError, TypeError):
            return 0

    designated = str(specs.get("afterglow:usage_schedule_required", "")).strip().lower() in {"true", "1", "yes", "on"}
    return bool(is_gpu_flavor(flavor) or amount("vcpus") >= 12 or amount("ram") >= 65536 or designated)


def _metadata(*, now, expires_at, request, source):
    return {
        METADATA_PREFIX + "version": "1",
        METADATA_PREFIX + "starts_at": now.isoformat(),
        METADATA_PREFIX + "expires_at": expires_at.isoformat(),
        METADATA_PREFIX + "action": request.expiry_action,
        METADATA_PREFIX + "delete_volumes": "true" if request.delete_volumes else "false",
        METADATA_PREFIX + "reason": request.reason,
        METADATA_PREFIX + "revision": secrets.token_hex(16),
        METADATA_PREFIX + "state": "active",
        METADATA_PREFIX + "source": source,
    }


def creation_metadata(flavor, request: UsageScheduleRequest | None, *, now: datetime | None = None) -> dict[str, str]:
    if request is None:
        if requires_schedule(flavor):
            raise HTTPException(422, "This flavor requires an explicit usage schedule")
        return {}
    if not isinstance(request, UsageScheduleRequest):
        raise HTTPException(422, "Invalid usage schedule")
    clock = _clock(now)
    expiry = request.expires_at or calendar_month_after(clock)
    if expiry <= clock:
        raise HTTPException(422, "Usage schedule expiry must be in the future")
    if expiry > calendar_month_after(clock) and not request.reason:
        raise HTTPException(422, "An initial schedule beyond one calendar month requires a reason")
    return _metadata(now=clock, expires_at=expiry, request=request, source="created")


def adoption_metadata(*, now: datetime | None = None) -> dict[str, str]:
    clock = _clock(now)
    return _metadata(
        now=clock, expires_at=calendar_month_after(clock), request=UsageScheduleRequest(), source="adopted"
    )


def _owned_metadata(server):
    raw = _field(server, "metadata", {})
    if not isinstance(raw, Mapping):
        raise HTTPException(409, "Native usage schedule metadata is invalid")
    return {key: value for key, value in raw.items() if isinstance(key, str) and key.startswith(METADATA_PREFIX)}


def parse_schedule(server) -> UsageScheduleInfo | None:
    owned = _owned_metadata(server)
    if not owned:
        return None
    values = {key[len(METADATA_PREFIX) :]: value for key, value in owned.items()}
    try:
        if not _REQUIRED.issubset(values) or set(values) - (_REQUIRED | _OPTIONAL):
            raise ValueError("Incomplete or unsupported native usage schedule")
        for value in values.values():
            metadata_text(value)
        if values["version"] != "1" or values["delete_volumes"] not in {"true", "false"}:
            raise ValueError("Unsupported native usage schedule version or consent")
        return UsageScheduleInfo(
            instance_id=_field(server, "id"),
            starts_at=values["starts_at"],
            expires_at=values["expires_at"],
            expiry_action=values["action"],
            delete_volumes=values["delete_volumes"] == "true",
            reason=values["reason"],
            revision=values["revision"],
            state=values["state"],
            source=values["source"],
            last_error=values.get("last_error") or None,
            extended_at=values.get("extended_at") or None,
            extended_by=values.get("extended_by") or None,
        )
    except (ValueError, TypeError, ValidationError, OverflowError):
        raise HTTPException(409, "Native usage schedule metadata is invalid; it was not reset") from None


def require_creation_schedule_current(metadata: Mapping, *, now: datetime | None = None) -> None:
    """Revalidate frozen enrollment immediately before the first Nova create."""
    schedule = parse_schedule({"id": "pending-instance", "metadata": metadata})
    if schedule is None:
        return
    if schedule.state != "active" or schedule.source != "created":
        raise HTTPException(422, "Instance creation requires its original active creation schedule")
    if aware_timestamp(schedule.expires_at) <= _clock(now):
        raise HTTPException(422, "Usage schedule expired while preparing creation; select a future expiry")


def require_resume_schedule(server, *, now: datetime | None = None) -> None:
    """Manual start/unshelve cannot resume an expired or uncertain native policy."""
    schedule = parse_schedule(server)
    if schedule is None:
        return
    if schedule.state != "active":
        raise HTTPException(409, "Extend the usage schedule before resuming this instance")
    if aware_timestamp(schedule.expires_at) <= _clock(now):
        raise HTTPException(409, "Usage schedule has expired; extend it before resuming this instance")


async def _drain(work):
    """Repeated cancellation must not free a lease while an SDK write runs."""
    while not work.done():
        try:
            await asyncio.shield(work)
        except asyncio.CancelledError:
            continue
        except Exception:
            break
    if not work.cancelled():
        with suppress(Exception):
            work.result()


async def sdk_call(fn, *args, **kwargs):
    work = asyncio.create_task(asyncio.to_thread(fn, *args, **kwargs))
    try:
        return await asyncio.shield(work)
    except asyncio.CancelledError:
        await _drain(work)
        raise


def safe_compute_proxy(conn):
    """Copy the adapter, never modify a shared connection/session retry policy."""
    proxy = copy(conn.compute)
    native_request = proxy.request

    def request(url, method, **kwargs):
        kwargs.update(redirect=False, allow_reauth=False, connect_retries=0, status_code_retries=0)
        response = native_request(url, method, **kwargs)
        status = getattr(response, "status_code", None)
        if isinstance(status, int) and 300 <= status < 400:
            raise HTTPException(502, "Native usage response was redirected and could not be verified")
        if method.upper() in {"POST", "PUT", "PATCH", "DELETE"} and (
            not isinstance(status, int) or isinstance(status, bool) or not 200 <= status < 300
        ):
            raise HTTPException(502, "Native usage operation was not confirmed; it must not be replayed")
        return response

    proxy.request = request
    return proxy


def require_server_scope(conn, server, instance_id=None) -> str:
    project = getattr(conn, "_afterglow_project_id", None)
    authenticated = getattr(conn, "_afterglow_authenticated_project_id", project)
    actual = _field(server, "project_id") or _field(server, "tenant_id")
    identifier = _field(server, "id")
    if not isinstance(project, str) or not project or authenticated != project:
        raise HTTPException(403, "A verified project-scoped connection is required")
    if not isinstance(identifier, str) or not identifier or (instance_id is not None and identifier != instance_id):
        raise HTTPException(502, "Native instance identity could not be verified")
    if actual != project or any(
        value is not None and value != project for value in (_field(server, "project_id"), _field(server, "tenant_id"))
    ):
        raise HTTPException(403, "Instance does not belong to the authenticated project")
    return project


async def _cloud_scope(conn):
    try:
        endpoint = await sdk_call(conn.endpoint_for, "identity")
        if not isinstance(endpoint, str) or not endpoint.strip():
            raise ValueError("No stable identity endpoint")
        return hashlib.sha256(endpoint.rstrip("/").encode("utf-8")).hexdigest()
    except Exception:
        raise HTTPException(503, "Usage schedule cloud coordination is unavailable") from None


class UsageLease:
    def __init__(self, redis, key, owner, cloud, project_id, instance_id):
        self.redis, self.key, self.owner = redis, key, owner
        self.cloud, self.project_id, self.instance_id = cloud, project_id, instance_id
        self.lost = False

    async def current(self) -> bool:
        if self.lost:
            return False
        try:
            result = await self.redis.eval(_RENEW, 1, self.key, self.owner, LEASE_SECONDS)
            if int(result or 0) != 1:
                self.lost = True
        except Exception:
            self.lost = True
        return not self.lost

    async def renew(self):
        while True:
            await asyncio.sleep(LEASE_SECONDS / 3)
            if not await self.current():
                return


@asynccontextmanager
async def usage_lease(conn, project_id, instance_id, *, redis=None):
    if getattr(conn, "_afterglow_project_id", None) != project_id or not project_id or not instance_id:
        raise HTTPException(403, "Usage schedule project scope is invalid")
    cloud = await _cloud_scope(conn)
    digest = hashlib.sha256(f"{cloud}\0{project_id}\0{instance_id}".encode()).hexdigest()
    key, owner = f"afterglow:instance_usage:lease:{digest}", secrets.token_hex(24)
    try:
        client = redis if redis is not None else await _get_redis()
        acquired = await client.set(key, owner, nx=True, ex=LEASE_SECONDS)
    except Exception:
        yield None
        return
    if not acquired:
        yield None
        return
    lease = UsageLease(client, key, owner, cloud, project_id, instance_id)
    renewal = asyncio.create_task(lease.renew())
    try:
        yield lease
    finally:

        async def release():
            renewal.cancel()
            with suppress(asyncio.CancelledError):
                await renewal
            with suppress(Exception):
                await client.eval(_RELEASE, 1, key, owner)

        cleanup = asyncio.create_task(release())
        try:
            await asyncio.shield(cleanup)
        except asyncio.CancelledError:
            await _drain(cleanup)
            raise


def _native_server_identity(server):
    identifier = _field(server, "id")
    project = _field(server, "project_id") or _field(server, "tenant_id")
    if not isinstance(identifier, str) or not identifier or not isinstance(project, str) or not project:
        raise HTTPException(502, "Native instance ownership could not be verified")
    if any(
        value is not None and value != project for value in (_field(server, "project_id"), _field(server, "tenant_id"))
    ):
        raise HTTPException(502, "Native instance ownership is inconsistent")
    return identifier, project


@asynccontextmanager
async def volume_mutation_lease(conn, server, *, redis=None):
    """Fence attachment/termination-flag edits against native expiry operations.

    Caller authorizes access first; an authorized fixed administrator executor may
    authenticate to a different project. Lock ownership derives only from exact
    native server identity, never a caller-provided flag or logical project tag.
    Callers must use sdk_call and check current() before each native mutation.
    The temporary scope adapter is coordination-only: it neither relabels native
    credentials nor supplies an SDK executor. All native reads use original conn.
    """
    identifier, project = _native_server_identity(server)
    coordination = SimpleNamespace(_afterglow_project_id=project, endpoint_for=conn.endpoint_for)
    async with usage_lease(coordination, project, identifier, redis=redis) as lease:
        if lease is None:
            raise HTTPException(409, "Instance volume operation is busy or coordination is unavailable")
        try:
            fresh = await sdk_call(safe_compute_proxy(conn).get_server, identifier)
        except Exception:
            raise HTTPException(502, "Native instance could not be read before volume mutation") from None
        if _native_server_identity(fresh) != (identifier, project):
            raise HTTPException(502, "Native instance ownership changed before volume mutation")
        schedule = parse_schedule(fresh)
        if schedule is not None and schedule.state not in {"active", "blocked"}:
            raise HTTPException(409, "A native expiry operation fences instance volume mutations")
        if not await lease.current():
            raise HTTPException(409, "Instance volume operation lease is no longer current")
        yield lease


async def _assert_lease(conn, server, lease):
    project = require_server_scope(conn, server)
    if (
        lease is None
        or lease.project_id != project
        or lease.instance_id != _field(server, "id")
        or lease.cloud != await _cloud_scope(conn)
        or not await lease.current()
    ):
        raise HTTPException(409, "Usage schedule operation lease is no longer current")


async def write_schedule_metadata(conn, server, changes: dict, *, lease):
    """Merge only owned keys; exact native pre/readback fences stale or partial data."""
    await _assert_lease(conn, server, lease)
    if not changes or any(not isinstance(key, str) or not key.startswith(METADATA_PREFIX) for key in changes):
        raise HTTPException(422, "Only usage schedule metadata can be changed")
    try:
        for value in changes.values():
            metadata_text(value)
    except ValueError:
        raise HTTPException(422, "Invalid usage schedule metadata value") from None
    # Partial/corrupt native metadata must never be repaired through adoption.
    parse_schedule(server)
    expected = _owned_metadata(server)
    if expected and any(METADATA_PREFIX + key in changes for key in ("version", "starts_at", "source")):
        raise HTTPException(409, "An enrolled usage schedule cannot be enrolled again")
    combined = {**expected, **changes}
    parse_schedule({"id": _field(server, "id"), "metadata": combined})
    identifier = _field(server, "id")
    submitted = False
    try:
        proxy = safe_compute_proxy(conn)
        fresh = await sdk_call(proxy.get_server, identifier)
        require_server_scope(conn, fresh, identifier)
        if _owned_metadata(fresh) != expected:
            raise HTTPException(409, "Usage schedule changed; reload before continuing")
        await _assert_lease(conn, fresh, lease)
        submitted = True
        await sdk_call(proxy.set_server_metadata, identifier, **changes)
        refreshed = await sdk_call(proxy.get_server, identifier)
        require_server_scope(conn, refreshed, identifier)
        await _assert_lease(conn, refreshed, lease)
        observed = _owned_metadata(refreshed)
        if observed != combined:
            raise ValueError("Native metadata readback differs")
        # Nova's metadata POST must preserve keys outside this feature as well.
        unrelated = {k: v for k, v in _field(fresh, "metadata", {}).items() if not k.startswith(METADATA_PREFIX)}
        actual = _field(refreshed, "metadata", {})
        if any(actual.get(k) != v for k, v in unrelated.items()):
            raise ValueError("Unrelated metadata changed during native write")
        parse_schedule(refreshed)
        return refreshed
    except asyncio.CancelledError:
        raise
    except HTTPException as exc:
        if not submitted and exc.status_code == 409:
            raise
        raise HTTPException(502, "Native usage schedule write could not be verified; reload before retrying") from None
    except Exception:
        raise HTTPException(502, "Native usage schedule write could not be verified; reload before retrying") from None


async def _update_locked(conn, server, request, *, user_id, now, lease, extension_only=False):
    identifier = _field(server, "id")
    try:
        fresh = await sdk_call(safe_compute_proxy(conn).get_server, identifier)
    except Exception:
        raise HTTPException(502, "Native usage schedule could not be read") from None
    require_server_scope(conn, fresh, identifier)
    schedule = parse_schedule(fresh)
    if schedule is None:
        raise HTTPException(409, "This instance has no native usage schedule")
    if schedule.revision != request.revision:
        raise HTTPException(409, "Usage schedule changed; reload before continuing")
    if schedule.state not in {"active", "blocked", "complete"}:
        raise HTTPException(409, "A native expiry operation may already be executing")
    clock = _clock(now)
    previous = aware_timestamp(schedule.expires_at)
    expiry = request.expires_at if request.expires_at is not None else previous
    if expiry < previous:
        raise HTTPException(422, "Usage schedule expiry cannot be shortened")
    extending = expiry > previous
    if extension_only and not extending:
        raise HTTPException(422, "An extension must move expiry forward")
    if extending and (expiry <= clock or not request.reason):
        raise HTTPException(422, "An extension requires a future expiry and a reason")
    if schedule.state in {"blocked", "complete"} and (not extending or expiry <= clock):
        raise HTTPException(409, "Resuming a completed or blocked schedule requires a future extension")
    try:
        actor = metadata_text(user_id)
        if not actor or actor != actor.strip():
            raise ValueError("Invalid actor")
    except ValueError:
        raise HTTPException(422, "A valid extension actor is required") from None
    action = request.expiry_action if "expiry_action" in request.model_fields_set else schedule.expiry_action
    delete_volumes = request.delete_volumes if "delete_volumes" in request.model_fields_set else schedule.delete_volumes
    if delete_volumes and action != "delete":
        raise HTTPException(422, "Clear volume deletion consent before selecting shelve")
    changes = {
        METADATA_PREFIX + "expires_at": expiry.isoformat(),
        METADATA_PREFIX + "action": action,
        METADATA_PREFIX + "delete_volumes": "true" if delete_volumes else "false",
        METADATA_PREFIX + "revision": secrets.token_hex(16),
        METADATA_PREFIX + "state": "active",
        METADATA_PREFIX + "last_error": "",
    }
    if request.reason:
        changes[METADATA_PREFIX + "reason"] = request.reason
    if extending:
        changes.update({METADATA_PREFIX + "extended_at": clock.isoformat(), METADATA_PREFIX + "extended_by": actor})
    refreshed = await write_schedule_metadata(conn, fresh, changes, lease=lease)
    return parse_schedule(refreshed)


async def update_schedule(
    conn, server, request: UsageScheduleUpdate, *, user_id: str, now=None, redis=None
) -> UsageScheduleInfo:
    project = require_server_scope(conn, server)
    async with usage_lease(conn, project, _field(server, "id"), redis=redis) as lease:
        if lease is None:
            raise HTTPException(409, "Usage schedule is busy or coordination is unavailable")
        return await _update_locked(conn, server, request, user_id=user_id, now=now, lease=lease)


async def extend_schedule(
    conn, server, request: UsageScheduleExtension, *, user_id: str, now=None, redis=None
) -> UsageScheduleInfo:
    project = require_server_scope(conn, server)
    async with usage_lease(conn, project, _field(server, "id"), redis=redis) as lease:
        if lease is None:
            raise HTTPException(409, "Usage schedule is busy or coordination is unavailable")
        update = UsageScheduleUpdate(expires_at=request.expires_at, reason=request.reason, revision=request.revision)
        return await _update_locked(conn, server, update, user_id=user_id, now=now, lease=lease, extension_only=True)
