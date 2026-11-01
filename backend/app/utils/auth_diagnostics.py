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

_STAGES = frozenset(
    [
        "request",
        "resolve",
        "password_method_policy",
        "authenticate",
        "password_policy",
        "domain_metadata",
        "session_publication",
        "native_exchange",
        "domain_preparation",
        "domain_context",
        "login_access",
        "default_project",
        "native_projects",
        "session_lookup",
        "federated_login",
        "session_policy",
        "domain_resolution",
        "login_guard",
        "native_identity_subject",
        "native_domain_authority",
        "native_project_authority",
        "native_system_authority",
        "native_domain_resolution",
        "native_password_exchange",
        "native_password_subject",
        "native_session_exchange",
        "native_lookup",
    ]
)
_ERROR_TYPES = frozenset(
    {
        "HTTPException",
        "RequestValidationError",
        "DomainAuthDenied",
        "DomainAuthError",
        "Unauthorized",
        "PasswordRejected",
        "RuntimeError",
        "ValueError",
        "TimeoutError",
        "ConnectionError",
        "CancelledError",
    }
)


def safe_error_type(exc: BaseException) -> str:
    name = type(exc).__name__
    return name if name in _ERROR_TYPES else "Exception"


def _capture_stage(stage: str, status: str, started: float, exc: BaseException | None = None) -> None:
    from app.services.activity import _audit_ctx

    holder = _audit_ctx.get()
    if holder is None or holder.get("closed") or stage not in _STAGES:
        return
    stages = holder.setdefault("stages", [])
    if len(stages) >= 64:
        holder["stages_truncated"] = True
        return
    metadata = {"stage": stage, "duration_ms": round((perf_counter() - started) * 1000, 3)}
    if exc is not None:
        metadata["error_type"] = safe_error_type(exc)
        code = getattr(exc, "status_code", None)
        if isinstance(code, int) and 400 <= code <= 599:
            metadata["error_code"] = f"http_{code}"
    stages.append((status, metadata))


class RequestDiagnosticHandler(logging.Handler):
    """Bounded request-only warning/error evidence, without formatting messages."""

    def __init__(self):
        super().__init__(logging.WARNING)

    def emit(self, record: logging.LogRecord) -> None:
        from app.services.activity import _audit_ctx

        if not record.name.startswith("app.") or record.name in {
            "app.services.activity",
            "app.utils.auth_diagnostics",
            "app.api.common.interactions",
        }:
            return
        holder = _audit_ctx.get()
        if holder is None or holder.get("closed"):
            return
        stages = holder.setdefault("stages", [])
        if len(stages) >= 64:
            holder["stages_truncated"] = True
            return
        # No getMessage(), args, message, pathname, locals or exception value.
        import re

        metadata = {
            "stage": "application_error" if record.levelno >= logging.ERROR else "application_warning",
            "severity": "CRITICAL"
            if record.levelno >= logging.CRITICAL
            else "ERROR"
            if record.levelno >= logging.ERROR
            else "WARNING",
        }
        if re.fullmatch(r"app\.[A-Za-z0-9_.]{1,100}", record.name):
            metadata["logger"] = record.name
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", record.funcName or ""):
            metadata["function"] = record.funcName
        if isinstance(record.lineno, int) and 0 < record.lineno <= 10000000:
            metadata["line"] = record.lineno
        if record.exc_info and isinstance(record.exc_info[1], BaseException):
            metadata["error_type"] = safe_error_type(record.exc_info[1])
        stages.append(("failed", metadata))


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
            _capture_stage(stage, "failed", started, exc)
            _logger.warning(
                "Authentication diagnostic",
                extra={**fields, "outcome": "failure", "duration_ms": round((perf_counter() - started) * 1000, 3)},
                exc_info=(type(exc), exc, exc.__traceback__),
            )
            raise
        else:
            _capture_stage(stage, "success", started)
            _logger.debug(
                "Authentication diagnostic",
                extra={**fields, "outcome": "complete", "duration_ms": round((perf_counter() - started) * 1000, 3)},
            )
    finally:
        if token is not None:
            _context.reset(token)
