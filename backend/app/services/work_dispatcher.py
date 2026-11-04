"""Redis membership, eligible assignments and renewable background-work fences.

WorkDispatcher.publish defaults to stable pending-owner target scheduling (Cinder
uses its original namespace and timings). Explicit roles advertise capabilities;
publish(..., rebalance=True) redistributes only when live membership changes.
Use work_lease around claimed work, checkpoint before later async mutations, and
run_sync for blocking SDK calls. Cancellation drains SDK threads before releasing
ownership. Request-bound calls outside a work_lease are intentionally unfenced.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import secrets
import socket
import threading
import time
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager, contextmanager, suppress
from contextvars import ContextVar

from anyio import CancelScope, current_effective_deadline
from anyio.lowlevel import checkpoint as scope_checkpoint

MEMBER_SECONDS = 45
LEADER_SECONDS = 45
HEARTBEAT_SECONDS = 10

# All liveness decisions happen within Redis, not against controller wall clocks.
_CLOCK = """
local clock = redis.call('TIME')
local now = tonumber(clock[1]) + tonumber(clock[2]) / 1000000
"""
_LIVE = (
    _CLOCK
    + """
local score = redis.call('ZSCORE', KEYS[1], ARGV[1])
local live = score and tonumber(score) > now
  and redis.call('HGET', KEYS[2], ARGV[1]) == ARGV[2]
"""
)
_HEARTBEAT = (
    _LIVE
    + """
if ARGV[7] == 'join' then
  if score and tonumber(score) > now then return 0 end
elseif not live then
  return 0
end
local expired = redis.call('ZRANGEBYSCORE', KEYS[1], '-inf', now)
for _, worker in ipairs(expired) do
  redis.call('DEL', ARGV[5] .. ':dispatch:ready:' .. worker)
  redis.call('HDEL', KEYS[2], worker)
  redis.call('HDEL', KEYS[4], worker)
end
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now)
redis.call('ZADD', KEYS[1], now + tonumber(ARGV[3]), ARGV[1])
redis.call('HSET', KEYS[2], ARGV[1], ARGV[2])
redis.call('HSET', KEYS[4], ARGV[1], ARGV[6])
redis.call('EXPIRE', KEYS[4], tonumber(ARGV[3]) * 2)
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[3]) * 2)
redis.call('EXPIRE', KEYS[2], tonumber(ARGV[3]) * 2)
local leader = redis.call('GET', KEYS[3])
local leader_score = leader and redis.call('ZSCORE', KEYS[1], leader)
if leader and (not leader_score or tonumber(leader_score) <= now) then
  redis.call('DEL', KEYS[3])
  leader = false
end
if not leader then
  redis.call('SET', KEYS[3], ARGV[1], 'NX', 'EX', ARGV[4])
elseif leader == ARGV[1] then
  redis.call('EXPIRE', KEYS[3], ARGV[4])
end
return 1
"""
)
_IS_LEADER = (
    _LIVE
    + """
if live and redis.call('GET', KEYS[3]) == ARGV[1] then return 1 end
return 0
"""
)
_PUBLISH = (
    _LIVE
    + """
if not live or redis.call('GET', KEYS[3]) ~= ARGV[1] then return 0 end
-- Delete every previous owner's queue, including owners no longer in members.
local cleared = {}
local function clear_ready(worker)
  if not cleared[worker] then
    redis.call('DEL', ARGV[3] .. ':dispatch:ready:' .. worker)
    cleared[worker] = true
  end
end
local previous = redis.call('HGETALL', KEYS[4])
local owners = {}
for i = 1, #previous, 2 do
  owners[previous[i]] = previous[i + 1]
  clear_ready(previous[i + 1])
end
local expired = redis.call('ZRANGEBYSCORE', KEYS[1], '-inf', now)
for _, worker in ipairs(expired) do
  clear_ready(worker)
  redis.call('HDEL', KEYS[2], worker)
  redis.call('HDEL', KEYS[5], worker)
end
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now)
local workers = redis.call('ZRANGE', KEYS[1], 0, -1)
table.sort(workers)
local topology = {}
local capabilities = {}
for _, worker in ipairs(workers) do
  local raw = redis.call('HGET', KEYS[5], worker) or '*'
  table.insert(topology, {worker, raw, redis.call('HGET', KEYS[2], worker)})
  capabilities[worker] = raw == '*' and true or cjson.decode(raw)
end
local signature = cjson.encode(topology)
local rebalance = ARGV[5] == '1' and redis.call('GET', KEYS[6]) ~= signature
if ARGV[5] == '1' then
  redis.call('SET', KEYS[6], signature, 'EX', ARGV[4])
end
local function eligible(worker, member)
  local roles = capabilities[worker]
  if roles == true then return true end
  if not roles then return false end
  for _, role in ipairs(roles) do
    if role == member then return true end
  end
  return false
end
local counts = {}
for _, worker in ipairs(workers) do counts[worker] = 0 end
for _, worker in ipairs(workers) do
  clear_ready(worker)
end
redis.call('DEL', KEYS[4])
local unique = {}
local members = {}
for i = 6, #ARGV do
  if not unique[ARGV[i]] then
    unique[ARGV[i]] = true
    table.insert(members, ARGV[i])
  end
end
table.sort(members)
-- Keep a live owner's pending/active work when faster peers finish. Reassigning
-- the shrinking runnable list on every poll would let them steal later submits.
local assigned = {}
for _, member in ipairs(members) do
  local worker = owners[member]
  if not rebalance and worker and counts[worker] ~= nil and eligible(worker, member) then
    assigned[member] = worker
    counts[worker] = counts[worker] + 1
  end
end
for _, member in ipairs(members) do
  local worker = assigned[member]
  if not worker then
    for _, candidate in ipairs(workers) do
      if eligible(candidate, member) and (not worker or counts[candidate] < counts[worker]) then
        worker = candidate
      end
    end
    if worker then counts[worker] = counts[worker] + 1 end
  end
  if worker then
    local ready = ARGV[3] .. ':dispatch:ready:' .. worker
    redis.call('HSET', KEYS[4], member, worker)
    redis.call('SADD', ready, member)
    redis.call('EXPIRE', ready, ARGV[4])
  end
end
-- A crashed leader is replaced only after its membership expires and a survivor
-- heartbeats and scans. Keep live owners' assignments across that gap; every
-- lease check still requires the owner's own live membership and token.
redis.call('EXPIRE', KEYS[4], tonumber(ARGV[4]) * 2)
return 1
"""
)
_PENDING = (
    _LIVE
    + """
if not live then return 0 end
return redis.call('SCARD', KEYS[3])
"""
)
_CLAIM = (
    _LIVE
    + """
if not live then return false end
-- At most the initial set size is inspected. Busy/stale hints are discarded,
-- never spun on, and are reconstructed by the next authoritative leader scan.
local count = redis.call('SCARD', KEYS[3])
for i = 1, count do
  local member = redis.call('SPOP', KEYS[3])
  if not member then return false end
  if redis.call('HGET', KEYS[4], member) == ARGV[1] then
    local lease = ARGV[3] .. ':lease:' .. member
    if redis.call('SET', lease, ARGV[4], 'NX', 'EX', ARGV[5]) then
      return {member, ARGV[4]}
    end
  end
end
return false
"""
)
_AVAILABLE_ROLES = (
    _LIVE
    + """
if not live then return {} end
local available = {}
local result = {}
for _, worker in ipairs(redis.call('ZRANGEBYSCORE', KEYS[1], '(' .. now, '+inf')) do
  local raw = redis.call('HGET', KEYS[3], worker)
  if raw and raw ~= '*' then
    for _, role in ipairs(cjson.decode(raw)) do
      if not available[role] then
        available[role] = true
        table.insert(result, role)
      end
    end
  end
end
table.sort(result)
return result
"""
)
_ASSIGNED = (
    _LIVE
    + """
if live and redis.call('HGET', KEYS[3], ARGV[3]) == ARGV[1] then return 1 end
return 0
"""
)
_LEASE_CHECK = (
    _LIVE
    + """
if live and redis.call('HGET', KEYS[3], ARGV[3]) == ARGV[1]
  and redis.call('GET', KEYS[4]) == ARGV[4] then return 1 end
return 0
"""
)
_LEASE_RENEW = (
    _LIVE
    + """
if redis.call('GET', KEYS[4]) ~= ARGV[4] then return {0, 0} end
-- Retain the old token through cancellation/drain even after assignment loss.
-- A new assignee must wait until the old SDK call has actually returned.
redis.call('EXPIRE', KEYS[4], ARGV[5])
if live and redis.call('HGET', KEYS[3], ARGV[3]) == ARGV[1] then return {1, 1} end
return {0, 1}
"""
)
_LEASE_RELEASE = """
if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) end
return 0
"""

_LEAVE = """
if redis.call('HGET', KEYS[2], ARGV[1]) ~= ARGV[2] then return 0 end
redis.call('ZREM', KEYS[1], ARGV[1])
redis.call('HDEL', KEYS[2], ARGV[1])
redis.call('HDEL', KEYS[5], ARGV[1])
redis.call('DEL', KEYS[4])
if redis.call('GET', KEYS[3]) == ARGV[1] then redis.call('DEL', KEYS[3]) end
return 1
"""


class DispatcherUnavailable(RuntimeError):
    """This incarnation must leave/rejoin rather than execute without a fence."""


def _text(value) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)


class WorkDispatcher:
    """One non-reusable process incarnation; Redis errors permanently fail closed.

    roles=None accepts arbitrary targets. An explicit tuple accepts only those
    roles; available_roles returns the union advertised by live participants.
    """

    def __init__(self, redis, prefix: str, *, worker_id: str | None = None, roles: tuple[str, ...] | None = None):
        self.redis = redis
        self.prefix = prefix
        self.worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}:{secrets.token_hex(16)}"
        self._incarnation = secrets.token_hex(24)
        self.roles = tuple(sorted(set(roles))) if roles is not None else None
        self._roles_key = f"{prefix}:dispatch:roles"
        self._topology_key = f"{prefix}:dispatch:role-members"
        self._members_key = f"{prefix}:dispatch:members"
        self._incarnations_key = f"{prefix}:dispatch:incarnations"
        self._leader_key = f"{prefix}:dispatch:leader"
        self._assignments_key = f"{prefix}:dispatch:assignments"
        self._ready_key = f"{prefix}:dispatch:ready:{self.worker_id}"
        self._heartbeat_task: asyncio.Task | None = None
        self._entered = False
        self._active = False
        self.lost = False
        self._work_tokens: set[str] = set()
        self._member_deadline = 0.0

    async def __aenter__(self) -> WorkDispatcher:
        if self._entered:
            raise RuntimeError("A work dispatcher incarnation cannot be reused")
        self._entered = True
        try:
            joined = await self._heartbeat(join=True)
            if not joined:
                raise DispatcherUnavailable("Work dispatcher identity is already live")
            self._active = True
            self._heartbeat_task = asyncio.create_task(self._renew())
            return self
        except BaseException as exc:
            self.lost = True
            await self._leave()
            if isinstance(exc, Exception) and not isinstance(exc, DispatcherUnavailable):
                raise DispatcherUnavailable("Work dispatcher registration failed") from exc
            raise

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        self._active = False
        with CancelScope(shield=True):
            if self._heartbeat_task is not None:
                self._heartbeat_task.cancel()
                with suppress(asyncio.CancelledError):
                    await self._heartbeat_task
            await self._leave()

    async def _leave(self) -> None:
        # Cleanup is ownership-fenced even if a join's reply was lost or a test
        # supplies the same worker label for a replacement incarnation.
        with CancelScope(shield=True):
            with suppress(Exception):
                await self.redis.eval(
                    _LEAVE,
                    5,
                    self._members_key,
                    self._incarnations_key,
                    self._leader_key,
                    self._ready_key,
                    self._roles_key,
                    self.worker_id,
                    self._incarnation,
                )

    async def _heartbeat(self, *, join: bool = False) -> bool:
        started = time.monotonic()
        result = bool(
            await self.redis.eval(
                _HEARTBEAT,
                4,
                self._members_key,
                self._incarnations_key,
                self._leader_key,
                self._roles_key,
                self.worker_id,
                self._incarnation,
                MEMBER_SECONDS,
                LEADER_SECONDS,
                self.prefix,
                json.dumps(self.roles) if self.roles is not None else "*",
                "join" if join else "renew",
            )
        )
        if result:
            self._member_deadline = started + MEMBER_SECONDS
        return result and time.monotonic() < self._member_deadline

    async def _renew(self) -> None:
        while True:
            await asyncio.sleep(HEARTBEAT_SECONDS)
            try:
                if self.lost or not await self._heartbeat():
                    self.lost = True
                    return
            except Exception:
                self.lost = True
                return

    async def _eval(self, script: str, keys: list[str], *args):
        if not self._active or self.lost:
            raise DispatcherUnavailable("Work dispatcher membership is unavailable")
        try:
            async with asyncio.timeout(max(0, self._member_deadline - time.monotonic())):
                result = await self.redis.eval(script, len(keys), *keys, self.worker_id, self._incarnation, *args)
        except Exception as exc:
            self.lost = True
            raise DispatcherUnavailable("Work dispatcher coordination failed") from exc
        # A heartbeat or context exit can revoke this incarnation while Redis
        # is completing a claim. Never hand that late lease to a new SDK cycle;
        # its Redis TTL remains the authoritative fallback.
        if not self._active or self.lost:
            raise DispatcherUnavailable("Work dispatcher membership was lost during coordination")
        return result

    async def is_leader(self) -> bool:
        return bool(await self._eval(_IS_LEADER, [self._members_key, self._incarnations_key, self._leader_key]))

    async def available_roles(self) -> list[str]:
        """Return explicitly advertised roles of server-time live participants."""
        result = await self._eval(_AVAILABLE_ROLES, [self._members_key, self._incarnations_key, self._roles_key])
        return [_text(role) for role in result]

    async def is_assigned(self, target: str) -> bool:
        """Fence membership, incarnation and current assignment atomically."""
        return bool(
            await self._eval(_ASSIGNED, [self._members_key, self._incarnations_key, self._assignments_key], target)
        )

    async def publish(self, runnable: list[str], *, rebalance: bool = False) -> bool:
        """Publish targets; opt-in role rebalance occurs only on topology change."""
        return bool(
            await self._eval(
                _PUBLISH,
                [
                    self._members_key,
                    self._incarnations_key,
                    self._leader_key,
                    self._assignments_key,
                    self._roles_key,
                    self._topology_key,
                ],
                self.prefix,
                MEMBER_SECONDS,
                "1" if rebalance else "0",
                *runnable,
            )
        )

    async def pending(self) -> int:
        return int(await self._eval(_PENDING, [self._members_key, self._incarnations_key, self._ready_key]))

    async def claim(self, lease_seconds: int) -> tuple[str, str] | None:
        if lease_seconds <= 0:
            raise ValueError("Work lease duration must be positive")
        claimed = await self._eval(
            _CLAIM,
            [self._members_key, self._incarnations_key, self._ready_key, self._assignments_key],
            self.prefix,
            secrets.token_hex(24),
            lease_seconds,
        )
        return (_text(claimed[0]), _text(claimed[1])) if claimed else None


_logger = logging.getLogger(__name__)
_current_lease: ContextVar[WorkLease | None] = ContextVar("background_work_lease", default=None)


class _DeferredCancellation:
    __slots__ = ("task", "pending")

    def __init__(self, task):
        self.task = task
        self.pending = True

    def expire(self):
        self.pending = False


_deferred_cancellation: ContextVar[_DeferredCancellation | None] = ContextVar("deferred_sdk_cancel", default=None)


def _defer_cancellation() -> None:
    current = asyncio.current_task()
    if current is not None:
        marker = _DeferredCancellation(current)
        _deferred_cancellation.set(marker)
        current.cancel()
        # Once the loop resumes, the pending cancellation can be delivered.
        # Retained Task.cancelling() counts are not evidence of a new request.
        asyncio.get_running_loop().call_soon(marker.expire)


async def _settle(task: asyncio.Task) -> bool:
    """Wait for actual completion; return whether this caller was cancelled meanwhile."""
    current = asyncio.current_task()
    requests = current.cancelling() if current is not None else 0
    interrupted = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            # A request made just before entry is delivered here with the same
            # count. A cancelled child alone must not cancel its owner.
            interrupted = interrupted or (current is not None and current.cancelling() > 0)
        except Exception:
            pass
    if not task.cancelled():
        task.exception()  # Retrieved: the owner reports or intentionally discards it.
    return interrupted or (current is not None and current.cancelling() > requests)


async def drain_task(task: asyncio.Task) -> bool:
    """Retain ownership through actual completion, even under level cancellation."""
    with CancelScope(shield=True):
        return await _settle(task)


class WorkLease:
    """A claimed token, independently renewed until work and cleanup drain.

    revoked is irreversible. Renewal retains only this token during drain; it
    never restores permission to start SDK work after assignment/membership loss.
    """

    def __init__(self, dispatcher: WorkDispatcher, member: str, owner: str, seconds: int):
        self.dispatcher = dispatcher
        self.member = member
        self.owner = owner
        self.seconds = seconds
        self.key = f"{dispatcher.prefix}:lease:{member}"
        self.revoked = asyncio.Event()
        self._revoked = False
        self._loop = asyncio.get_running_loop()
        self._thread_id = threading.get_ident()
        self._deadline = time.monotonic() + seconds
        self.experience_context = None
        self.experience_operation_id = None
        self.experience_lease_lost = False

    def revoke(self) -> None:
        """Revoke immediately from either the event loop or a guarded SDK thread."""
        self._revoked = True
        if threading.get_ident() == self._thread_id:
            self.revoked.set()
        else:
            self._loop.call_soon_threadsafe(self.revoked.set)

    def _keys(self):
        dispatcher = self.dispatcher
        return [dispatcher._members_key, dispatcher._incarnations_key, dispatcher._assignments_key, self.key]

    async def check(self) -> None:
        """Raise before new work if membership, assignment or token is lost."""
        if self._revoked or self.revoked.is_set() or time.monotonic() >= self._deadline:
            if time.monotonic() >= self._deadline:
                self.experience_lease_lost = True
            self.revoke()
            raise DispatcherUnavailable("Background work lease was revoked")
        try:
            current = await self.dispatcher._eval(_LEASE_CHECK, self._keys(), self.member, self.owner)
        except BaseException:
            self.revoke()
            raise
        if not current or self._revoked or self.revoked.is_set() or time.monotonic() >= self._deadline:
            if not current or time.monotonic() >= self._deadline:
                self.experience_lease_lost = True
            self.revoke()
            raise DispatcherUnavailable("Background work ownership is unavailable")

    async def _renew_once(self) -> None:
        dispatcher = self.dispatcher
        started = time.monotonic()
        try:
            async with asyncio.timeout(min(self.seconds / 3, HEARTBEAT_SECONDS)):
                current, retained = await dispatcher.redis.eval(
                    _LEASE_RENEW,
                    4,
                    *self._keys(),
                    dispatcher.worker_id,
                    dispatcher._incarnation,
                    self.member,
                    self.owner,
                    self.seconds,
                )
            if retained:
                self._deadline = started + self.seconds
            if (
                not current
                or not retained
                or dispatcher.lost
                or not dispatcher._active
                or time.monotonic() >= self._deadline
            ):
                self.experience_lease_lost = True
                self.revoke()
        except Exception:
            dispatcher.lost = True
            self.revoke()

    async def _renew(self) -> None:
        while True:
            await asyncio.sleep(min(HEARTBEAT_SECONDS, self.seconds / 3))
            await self._renew_once()


@asynccontextmanager
async def work_lease(dispatcher: WorkDispatcher, member: str, owner: str, *, seconds: int = 90):
    """Adopt a claim once, fence descendants, and release only after their drain.

    Caller must cancel/await child tasks before leaving this context. Ownership
    checks are task-local and inherited by children, not by unrelated requests.
    """
    if seconds <= 0:
        raise ValueError("Work lease duration must be positive")
    if owner in dispatcher._work_tokens:
        raise DispatcherUnavailable("Work claim is already executing")
    dispatcher._work_tokens.add(owner)
    lease = WorkLease(dispatcher, member, owner, seconds)
    renewal = None
    guard = None
    try:
        await lease.check()
        await lease._renew_once()
        await lease.check()
        renewal = asyncio.create_task(lease._renew())
        guard = _current_lease.set(lease)
        yield lease
    finally:
        was_revoked = lease.revoked.is_set()
        lease.revoke()
        if guard is not None:
            _current_lease.reset(guard)
        interrupted = False
        if renewal is not None:
            renewal.cancel()
            interrupted = await drain_task(renewal)
        # Nothing executed under a rejected adoption, so releasing this exact
        # token is safe and shortens handoff; a replacement token is untouched.
        release = asyncio.create_task(dispatcher.redis.eval(_LEASE_RELEASE, 1, lease.key, owner))
        interrupted = await drain_task(release) or interrupted
        dispatcher._work_tokens.discard(owner)
        from app.services.experience_context import emit_experience_cleanup

        interrupted = (
            await emit_experience_cleanup(
                lease.experience_context,
                "worker.state_changed",
                stage="cleanup",
                status="observed",
                operation_id=lease.experience_operation_id,
                reason="lease_lost" if lease.experience_lease_lost else "unknown" if was_revoked else None,
            )
            or interrupted
        )
        if interrupted:
            raise asyncio.CancelledError


def bind_worker_experience(context, operation_id=None) -> None:
    """Attach only an explicitly restored source record to its current lease."""
    lease = _current_lease.get()
    if lease is not None:
        lease.experience_context = context
        lease.experience_operation_id = operation_id


@contextmanager
def worker_experience_scope(context, operation_id=None):
    """Bind one delivery without attributing the rest of a long-lived role to it."""
    lease = _current_lease.get()
    previous = (lease.experience_context, lease.experience_operation_id) if lease is not None else None
    bind_worker_experience(context, operation_id)
    try:
        yield
    finally:
        if lease is not None:
            lease.experience_context, lease.experience_operation_id = previous


async def checkpoint() -> None:
    """Fence new work, including cancellation deferred to deliver a completed ID."""
    if current_effective_deadline() == -math.inf:
        # A shielded diagnostic can hold an anyio scope's level cancellation until
        # its owner resumes; deliver it before another SDK mutation can start.
        await scope_checkpoint()
    deferred = _deferred_cancellation.get()
    if deferred is not None and deferred.pending and deferred.task is asyncio.current_task():
        # Deliver the already armed cancellation once, before a new SDK task.
        # Raising a second synthetic cancellation would leave the armed one
        # waiting to interrupt the caller's next cleanup await.
        await asyncio.sleep(0)
    lease = _current_lease.get()
    if lease is not None:
        await lease.check()


def checkpoint_sync() -> None:
    """Thread-local fast fence for later mutations within a compound SDK function.

    No Redis I/O is performed in the SDK thread. Independent async renewal and
    monitoring revoke the inherited lease; conservative monotonic deadlines fail
    closed if replies stall. Async callers must use checkpoint for fresh Redis
    membership/assignment/token authority before beginning each SDK operation.
    """
    lease = _current_lease.get()
    if lease is not None:
        dispatcher = lease.dispatcher
        now = time.monotonic()
        if (
            lease._revoked
            or lease.revoked.is_set()
            or dispatcher.lost
            or not dispatcher._active
            or now >= lease._deadline
            or now >= dispatcher._member_deadline
        ):
            lease.revoke()
            raise DispatcherUnavailable("Background SDK work was revoked")


def _invoke(fn, args, kwargs):
    checkpoint_sync()
    return fn(*args, **kwargs)


async def _run_sync(fn, args, kwargs, *, stage, experience=None):
    from app.services.experience_context import (
        capture_experience_context,
        emit_experience,
        emit_experience_cleanup,
        fork_experience_call,
    )

    await checkpoint()
    lease = _current_lease.get()
    context = experience
    if context is None:
        context = lease.experience_context if lease is not None else capture_experience_context()
    context = fork_experience_call(context)
    operation_id = lease.experience_operation_id if lease is not None else None
    operation = asyncio.create_task(asyncio.to_thread(_invoke, fn, args, kwargs))
    logging_start = True
    try:
        await emit_experience(context, "stage.started", stage=stage, status="running", operation_id=operation_id)
        logging_start = False
        result = await asyncio.shield(operation)
        interrupted = await emit_experience_cleanup(
            context, "stage.completed", stage=stage, status="observed", operation_id=operation_id
        )
        if interrupted:
            # The call already returned: let its owner record the native ID
            # before cancellation resurfaces at the owner's next await.
            _defer_cancellation()
        return result
    except asyncio.CancelledError:
        if lease is not None:
            lease.revoke()
        if operation.done():
            if logging_start and not operation.cancelled() and operation.exception() is None:
                result = operation.result()
                await emit_experience_cleanup(
                    context, "stage.completed", stage=stage, status="observed", operation_id=operation_id
                )
                _defer_cancellation()
                return result
            if not operation.cancelled():
                operation.exception()
            raise
        await emit_experience_cleanup(
            context,
            "stage.completed",
            stage=stage,
            status="cancel_requested",
            operation_id=operation_id,
            reason="aborted",
        )
        await drain_task(operation)
        await emit_experience_cleanup(
            context,
            "stage.completed",
            stage=stage + ".drain",
            status="observed",
            operation_id=operation_id,
            reason="aborted",
        )
        raise
    except Exception:
        # Even an unexpected diagnostic failure cannot abandon a started call.
        interrupted = await drain_task(operation)
        interrupted = (
            await emit_experience_cleanup(
                context,
                "stage.completed",
                stage=stage,
                status="outcome_unknown",
                operation_id=operation_id,
                reason="unknown",
            )
            or interrupted
        )
        if interrupted:
            if lease is not None:
                lease.revoke()
            await emit_experience_cleanup(
                context,
                "stage.completed",
                stage=stage,
                status="cancel_requested",
                operation_id=operation_id,
                reason="aborted",
            )
            await emit_experience_cleanup(
                context,
                "stage.completed",
                stage=stage + ".drain",
                status="observed",
                operation_id=operation_id,
                reason="aborted",
            )
            raise asyncio.CancelledError from None
        raise


async def run_sync(fn, *args, **kwargs):
    """Fence and drain a generic blocking call; do not imply provider mutation.

    Resource factories must use open_connection so a cancelled result is closed.
    Cleanup must use close_connection (or another unfenced shielded drain).
    """
    return await _run_sync(fn, args, kwargs, stage="blocking")


async def run_native(fn, *args, experience=None, **kwargs):
    """Explicit native SDK boundary using the same blocking-call drain engine."""
    return await _run_sync(fn, args, kwargs, stage="native", experience=experience)


async def close_connection(conn) -> None:
    """Always close and drain, including after fence loss or cancellation."""
    operation = asyncio.create_task(asyncio.to_thread(conn.close))
    try:
        await asyncio.shield(operation)
    except asyncio.CancelledError:
        await drain_task(operation)
        raise


async def open_connection(factory, *args, **kwargs):
    """Fence SDK acquisition and close any result not transferred to the caller."""
    await checkpoint()
    operation = asyncio.create_task(asyncio.to_thread(_invoke, factory, args, kwargs))
    conn = None
    try:
        conn = await asyncio.shield(operation)
        await checkpoint()
        return conn
    except BaseException:
        lease = _current_lease.get()
        if lease is not None:
            lease.revoke()
        interrupted = False
        if conn is None:
            interrupted = await drain_task(operation)
            if not operation.cancelled() and operation.exception() is None:
                conn = operation.result()
        if conn is not None:
            close = asyncio.create_task(asyncio.to_thread(conn.close))
            interrupted = await drain_task(close) or interrupted
        if interrupted:
            raise asyncio.CancelledError from None
        raise


async def _run_role(dispatcher, member, owner, factory):
    async with work_lease(dispatcher, member, owner) as lease:
        operation = asyncio.create_task(factory(), name=f"background:{member}")
        revoked = asyncio.create_task(lease.revoked.wait())
        try:
            done, _ = await asyncio.wait((operation, revoked), return_when=asyncio.FIRST_COMPLETED)
            if operation in done:
                operation.result()
        finally:
            interrupted = False
            for child in (operation, revoked):
                if not child.done():
                    child.cancel()
                interrupted = await drain_task(child) or interrupted
            if interrupted:
                raise asyncio.CancelledError


async def run_roles(
    roles: dict[str, Callable[[], Awaitable[None]]],
    *,
    prefix: str = "afterglow:background:api",
    redis=None,
    worker_id=None,
    poll_seconds: float = 5,
) -> None:
    """Run one independent loop child per eligible assigned role until shutdown.

    A late join or leave rebalances roles; unaffected ownership remains stable
    between topology changes. Revoked children drain with renewable token held
    before another child can claim it. Redis loss drains before leave/rejoin.
    """
    if poll_seconds <= 0:
        raise ValueError("Role polling interval must be positive")
    while True:
        try:
            connection = redis
            if connection is None:
                from app.services.cache import _get_redis

                connection = await _get_redis()
            async with WorkDispatcher(connection, prefix, worker_id=worker_id, roles=tuple(roles)) as dispatcher:
                children: dict[str, asyncio.Task] = {}
                try:
                    while True:
                        if await dispatcher.is_leader():
                            await dispatcher.publish(await dispatcher.available_roles(), rebalance=True)
                        for member, child in list(children.items()):
                            if child.done():
                                try:
                                    child.result()
                                except asyncio.CancelledError:
                                    pass
                                except Exception:
                                    _logger.warning("Background role stopped (%s)", member, exc_info=True)
                                del children[member]
                            elif not child.cancelling() and not await dispatcher.is_assigned(member):
                                # Keep tracking the draining child without blocking
                                # publication or monitoring other independent roles.
                                child.cancel()
                        for _ in range(await dispatcher.pending()):
                            claim = await dispatcher.claim(90)
                            if claim is None:
                                break
                            member, owner = claim
                            if member in children:
                                # A completing child can release its token before
                                # its Task becomes done. Never overwrite that child.
                                await dispatcher.redis.eval(_LEASE_RELEASE, 1, f"{prefix}:lease:{member}", owner)
                                continue
                            children[member] = asyncio.create_task(_run_role(dispatcher, member, owner, roles[member]))
                        await asyncio.sleep(poll_seconds)
                finally:
                    interrupted = False
                    for child in children.values():
                        if not child.done() and not child.cancelling():
                            child.cancel()
                    for child in children.values():
                        interrupted = await drain_task(child) or interrupted
                    if interrupted:
                        raise asyncio.CancelledError
        except asyncio.CancelledError:
            raise
        except Exception:
            _logger.warning("Background role coordination unavailable", exc_info=True)
        await asyncio.sleep(poll_seconds)
