"""Task-bound SQL authority and non-replayable provider submission journals.

SQL admits work; Redis membership fences execution. Journals never expire and
are not a queue: an intent with no accepted result is observed, never replayed.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from app.services.work_dispatcher import DispatcherUnavailable
from app.services.work_dispatcher import checkpoint as lease_checkpoint

TERMINAL = frozenset({"complete", "error", "timeout", "cancelled"})
_PREFIX = "afterglow:builds:journal"


class SubmissionUnknown(RuntimeError):
    """An earlier submission may have reached the provider; do not issue CREATE."""


@dataclass
class Binding:
    redis: object
    member: str
    lease: object
    allow_complete: bool = False
    consumer_id: int | None = None
    cancel_cleanup: bool = False


_binding: ContextVar[Binding | None] = ContextVar("build_work", default=None)


def current_binding() -> Binding:
    binding = _binding.get()
    if binding is None:
        raise DispatcherUnavailable("build execution requires an owned durable target")
    return binding


@asynccontextmanager
async def bind(redis, member: str, lease, *, cancel_cleanup: bool = False):
    token = _binding.set(Binding(redis, member, lease, cancel_cleanup=cancel_cleanup))
    try:
        await checkpoint()
        yield current_binding()
    finally:
        _binding.reset(token)


async def assert_current() -> None:
    from app.database import get_session_factory
    from app.models.db import LayerBuild, LayerConsume, LayerImportJob, LibraryBuild

    binding = current_binding()
    factory = get_session_factory()
    if factory is None:
        raise DispatcherUnavailable("build database is unavailable")
    kind, identity = binding.member.split(":", 1)
    model = {"library": LibraryBuild, "import": LayerImportJob, "layer": LayerBuild}[kind]
    try:
        async with factory() as session:
            row = await session.get(model, int(identity))
            cancellation_cleanup = (
                row is not None
                and binding.cancel_cleanup
                and row.status == "cancelled"
                and (row.resource_snapshot or {}).get("cancel_cleanup") == "pending"
            )
            if row is None or (
                row.status in TERMINAL
                and not cancellation_cleanup
                and not (binding.allow_complete and row.status == "complete")
            ):
                raise DispatcherUnavailable("build is no longer runnable")
            if binding.cancel_cleanup and not cancellation_cleanup:
                raise DispatcherUnavailable("cancellation cleanup authority changed")
            if binding.consumer_id is not None:
                if kind != "import" or row.consume_id != binding.consumer_id:
                    raise DispatcherUnavailable("consumer is outside its import authority")
                consumer = await session.get(LayerConsume, binding.consumer_id)
                if consumer is None or consumer.status in {"active", "error", "deleted", "cancelled"}:
                    raise DispatcherUnavailable("consumer is no longer runnable")
    except DispatcherUnavailable:
        raise
    except Exception as exc:
        raise DispatcherUnavailable("build database authority is unavailable") from exc


async def checkpoint() -> None:
    await lease_checkpoint()
    binding = current_binding()
    await binding.lease.check()
    await assert_current()


async def drain(task):
    """Drain SDK/runtime resources; cancellation wins over a late SDK failure."""
    cancelled = False
    while True:
        try:
            result = await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
            if task.done():
                # Retrieving the result consumes any late exception, but it
                # cannot turn owner revocation into an application failure.
                try:
                    task.result()
                except BaseException:
                    pass
                raise
        except BaseException:
            if cancelled:
                raise asyncio.CancelledError from None
            raise
        else:
            if cancelled:
                raise asyncio.CancelledError
            return result


def _guarded_sync(caller, loop, check_sql: bool, fn, *args, **kwargs):
    from concurrent.futures import CancelledError as FutureCancelledError

    from app.services.work_dispatcher import checkpoint_sync

    # Executor queueing is another ownership boundary. SQL may have been
    # cancelled while this call waited for a thread; the SDK thread must not
    # treat its earlier async checkpoint as permission to issue CREATE.
    if caller is not None and caller.cancelling():
        raise asyncio.CancelledError
    checkpoint_sync()
    if check_sql:
        try:
            asyncio.run_coroutine_threadsafe(checkpoint(), loop).result()
        except FutureCancelledError:
            raise asyncio.CancelledError from None
    if caller is not None and caller.cancelling():
        raise asyncio.CancelledError
    checkpoint_sync()
    return fn(*args, **kwargs)


async def run_sync(fn, *args, **kwargs):
    await checkpoint()
    result = await drain(
        asyncio.create_task(
            asyncio.to_thread(
                _guarded_sync,
                asyncio.current_task(),
                asyncio.get_running_loop(),
                True,
                fn,
                *args,
                **kwargs,
            )
        )
    )
    await checkpoint()
    return result


async def cleanup_sync(fn, *args, **kwargs):
    """Drain resource close only; this does not grant provider mutation authority."""
    return await drain(asyncio.create_task(asyncio.to_thread(fn, *args, **kwargs)))


async def cleanup_owned(fn, *args, **kwargs):
    """Terminal cleanup still requires the current execution lease, not row liveness."""
    await current_binding().lease.check()
    result = await drain(
        asyncio.create_task(
            asyncio.to_thread(
                _guarded_sync,
                asyncio.current_task(),
                asyncio.get_running_loop(),
                False,
                fn,
                *args,
                **kwargs,
            )
        )
    )
    await current_binding().lease.check()
    return result


async def _redis_call(fn, *args, **kwargs):
    try:
        return await fn(*args, **kwargs)
    except Exception as exc:
        raise DispatcherUnavailable("build journal authority is unavailable") from exc


async def journal_get() -> dict:
    binding = current_binding()
    raw = await _redis_call(binding.redis.get, f"{_PREFIX}:{binding.member}")
    return json.loads(raw) if raw else {}


async def journal_update(**fields) -> None:
    binding = current_binding()
    key = f"{_PREFIX}:{binding.member}"
    while True:
        await binding.lease.check()
        raw = await _redis_call(binding.redis.get, key)
        value = json.loads(raw) if raw else {}
        value.update(fields)
        updated = await _redis_call(
            binding.redis.eval,
            """
            if redis.call('GET', KEYS[1]) ~= ARGV[1] then return -1 end
            if (redis.call('GET', KEYS[2]) or '') ~= ARGV[2] then return 0 end
            redis.call('SET', KEYS[2], ARGV[3])
            return 1
            """,
            2,
            binding.lease.key,
            key,
            binding.lease.owner,
            raw or "",
            json.dumps(value),
        )
        if updated == 1:
            return
        if updated == -1:
            raise DispatcherUnavailable("build journal ownership was lost")


async def submission_get(step: str) -> dict | None:
    binding = current_binding()
    raw = await _redis_call(binding.redis.get, f"{_PREFIX}:{binding.member}:submit:{step}")
    return json.loads(raw) if raw else None


def _identity(result):
    if isinstance(result, dict):
        return result
    if isinstance(result, (str, int, float, bool, list)) or result is None:
        return result
    return {"id": result.id}


async def submit(step: str, fn, *args, **kwargs):
    """Persist intent before a no-retry CREATE and retain late accepted results.

    Callers must observe an existing accepted ID with GET, not reconstruct the
    CREATE return value or allocate again. An ambiguous result is fail-closed.
    """
    from app.services.layer_consume_resources import REJECTED_CREATE_STATUSES, _create_once

    await checkpoint()
    binding = current_binding()
    if binding.cancel_cleanup:
        raise DispatcherUnavailable("cancellation cleanup cannot submit new resources")
    key = f"{_PREFIX}:{binding.member}:submit:{step}"
    if not await _redis_call(binding.redis.set, key, json.dumps({"state": "submitting"}), nx=True):
        raise SubmissionUnknown(f"{step} was already submitted; observe its durable result")
    await checkpoint()
    caller = asyncio.current_task()
    loop = asyncio.get_running_loop()

    async def execute():
        try:
            result = await asyncio.to_thread(_guarded_sync, caller, loop, True, _create_once, fn, *args, **kwargs)
        except BaseException as exc:
            status = (
                getattr(exc, "status_code", None)
                or getattr(exc, "http_status", None)
                or getattr(getattr(exc, "response", None), "status_code", None)
            )
            rejected = (
                status in REJECTED_CREATE_STATUSES
                and isinstance(exc, Exception)
                and not isinstance(exc, DispatcherUnavailable)
            )
            outcome = {"state": "rejected", "response_status": status} if rejected else {"state": "unknown"}
            await _redis_call(binding.redis.set, key, json.dumps(outcome))
            if not isinstance(exc, Exception) or isinstance(exc, DispatcherUnavailable) or rejected:
                raise
            raise SubmissionUnknown(f"{step} acceptance is unknown; observe the provider") from exc
        # Record even if the caller was cancelled or lost its lease while draining.
        try:
            accepted = json.dumps({"state": "accepted", "result": _identity(result)})
        except Exception as exc:
            await _redis_call(binding.redis.set, key, json.dumps({"state": "unknown"}))
            raise SubmissionUnknown(f"{step} returned an unrecordable identity; observe the provider") from exc
        await _redis_call(binding.redis.set, key, accepted)
        return result

    result = await drain(asyncio.create_task(execute()))
    await checkpoint()
    return result
