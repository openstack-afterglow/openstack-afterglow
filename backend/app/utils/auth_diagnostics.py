"""Credential-free auth timing; stage/operation labels must be source literals.

Native synchronous code can use ``with authentication_step("native_lookup")``.
Context variables propagate through asyncio.to_thread; never pass user data as labels.
"""

import logging
import sys
from contextlib import contextmanager
from contextvars import ContextVar
from time import perf_counter
from uuid import uuid4

_logger = logging.getLogger(__name__)
_context: ContextVar[tuple[str, str] | None] = ContextVar("authentication_diagnostics", default=None)


@contextmanager
def authentication_operation(operation: str):
    """Start a server-correlated operation; reset even on cancellation/failure."""
    token = _context.set((operation[:64], uuid4().hex))
    try:
        yield
    finally:
        _context.reset(token)


@contextmanager
def authentication_step(stage: str):
    """Time a literal stage, logging structural failures even without DEBUG.

    A standalone step gets a temporary server-generated correlation. Both sync
    native calls and async callers (using ordinary ``with``) share this API.
    Exceptions are always re-raised unchanged; no arguments or values are logged.
    """
    context = _context.get()
    token = None
    if context is None:
        context = ("authentication", uuid4().hex)
        token = _context.set(context)
    caller = sys._getframe(2)
    fields = {
        "auth_operation": context[0],
        "auth_correlation": context[1],
        "auth_stage": stage[:64],
        "auth_function": caller.f_code.co_name[:64],
        "auth_line": caller.f_lineno,
    }
    del caller
    started = perf_counter()
    try:
        _logger.debug("Authentication diagnostic", extra={**fields, "outcome": "start"})
        try:
            yield
        except BaseException as exc:
            _logger.warning(
                "Authentication diagnostic",
                extra={**fields, "outcome": "failure", "duration_ms": round((perf_counter() - started) * 1000, 3)},
                exc_info=(type(exc), exc, exc.__traceback__),
            )
            raise
        else:
            _logger.debug(
                "Authentication diagnostic",
                extra={**fields, "outcome": "complete", "duration_ms": round((perf_counter() - started) * 1000, 3)},
            )
    finally:
        if token is not None:
            _context.reset(token)
