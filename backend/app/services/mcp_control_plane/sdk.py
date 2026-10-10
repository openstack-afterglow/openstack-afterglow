"""Keep synchronous cloud workers owned until their actual completion."""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

import anyio


class McpSdkDispatchCancelled(ValueError):
    """A canceled/expired MCP call must not begin another provider mutation."""


@dataclass
class _SdkCall:
    deadline: float | None = None
    canceled: threading.Event = field(default_factory=threading.Event)

    def check_dispatch(self) -> None:
        if self.canceled.is_set() or (self.deadline is not None and time.monotonic() >= self.deadline):
            raise McpSdkDispatchCancelled("MCP cloud dispatch deadline expired or call was canceled")


_current_call: ContextVar[_SdkCall | None] = ContextVar("mcp_sdk_call", default=None)


@contextmanager
def sdk_deadline(seconds: float) -> Iterator[None]:
    """Share a deadline/cancellation fence with context-copied SDK threads."""
    call = _SdkCall(deadline=time.monotonic() + seconds)
    token = _current_call.set(call)
    try:
        yield
    finally:
        call.canceled.set()
        _current_call.reset(token)


def check_mutation_dispatch() -> None:
    """Fence the final provider call after potentially slow owner/state reads.

    This cannot roll back a request already sent to a provider. Such a worker
    must finish before its connection and concurrency slot can be released.
    """
    call = _current_call.get()
    if call is not None:
        call.check_dispatch()


async def _drain(task: asyncio.Task[Any]) -> None:
    # AnyIO transport cancellation is level-triggered; protect cleanup from it
    # as well as repeated asyncio task cancellation, without canceling the thread.
    with anyio.CancelScope(shield=True):
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if not task.cancelled():
            task.exception()  # retrieve failures; caller cancellation stays authoritative


async def run_sdk[Result](
    function: Callable[..., Result],
    /,
    *args: Any,
    cancellation_cleanup: Callable[[Result], Any] | None = None,
    allow_after_cancel: bool = False,
    **kwargs: Any,
) -> Result:
    """Offload an SDK call without abandoning its thread on timeout/disconnect.

    Timeout responses may wait for the bounded provider request to settle. This
    preserves the slot and connection while its outcome remains uncertain.
    """
    call = _current_call.get() or _SdkCall()

    def invoke() -> Result:
        token = _current_call.set(call)
        try:
            if not allow_after_cancel:
                call.check_dispatch()
            return function(*args, **kwargs)
        finally:
            _current_call.reset(token)

    task = asyncio.create_task(asyncio.to_thread(invoke))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        call.canceled.set()
        await _drain(task)
        if cancellation_cleanup is not None and not task.cancelled() and task.exception() is None:
            cleanup = asyncio.create_task(asyncio.to_thread(cancellation_cleanup, task.result()))
            await _drain(cleanup)
        raise


async def gather_sdk(*calls: Awaitable[Any]) -> list[Any]:
    """Settle every owned parallel SDK call before allowing connection cleanup."""
    tasks = [asyncio.create_task(call) for call in calls]
    try:
        return await asyncio.gather(*tasks, return_exceptions=True)
    except asyncio.CancelledError:
        # gather can surface cancellation after the first child drains while
        # another child still owns the connection; explicitly settle them all.
        for task in tasks:
            await _drain(task)
        raise
