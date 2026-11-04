"""보안 민감 데이터 마스킹 로그 유틸리티."""

from __future__ import annotations

import logging
import os
import re
import sys
from collections import deque
from inspect import getattr_static
from pathlib import Path
from types import TracebackType

_EXCEPTION_CAUSE_LIMIT = 8
_EXCEPTION_FRAME_LIMIT = 12
_EXCEPTION_TRACEBACK_LIMIT = 1024
_EXCEPTION_NAME_LIMIT = 128

_APPLICATION_SOURCE = str(Path(__file__).resolve().parents[1]) + os.sep
_TEST_SOURCE = str(Path(__file__).resolve().parents[2] / "tests") + os.sep

# Only source-controlled finite diagnostics may bypass generic string masking.
# Unknown values (including str subclasses) are omitted, not converted or logged.
DIAGNOSTIC_LOG_FIELDS: dict[str, frozenset[str]] = {
    "traffic_source": frozenset({"backend", "frontend"}),
    "failure_stage": frozenset({"redis_acquire", "aggregate"}),
    "stage_scope": frozenset({"client_initialization", "pool_connect_command_reply"}),
    "failure_reason": frozenset({"timeout", "connection", "capacity", "rejected", "unknown"}),
    "diagnostic_reason": frozenset(
        {
            "authority_rejected",
            "authentication_failed",
            "client_invalid",
            "resource_mismatch",
            "credential_unknown",
            "credential_reused",
            "credential_expired",
            "invalid_shape",
            "grant_inactive",
            "authority_invariant",
            "scope_invalid",
            "health_credential_missing",
            "health_credential_expired_or_unknown",
            "health_credential_instance_mismatch",
            "health_store_unavailable",
            "health_credential_record_invalid",
        }
    ),
}


def sanitize_diagnostic_field(field: str, value: object) -> str | None:
    """Admit exact plain strings from a field's closed operational vocabulary."""
    allowed = DIAGNOSTIC_LOG_FIELDS.get(field)
    return value if allowed is not None and type(value) is str and value in allowed else None


def log_file_directory(configured: str) -> Path:
    """Keep pytest file output separate, without inspecting test names or args.

    Detection affects only the file sink; application behavior and configured
    severity stay identical. PID directories also isolate parallel test workers.
    """
    directory = Path(configured)
    return directory / "pytest" / str(os.getpid()) if "pytest" in sys.modules else directory


def log_source(record: logging.LogRecord) -> dict:
    """Identify the emitting code without retaining absolute filesystem paths."""
    origin = "dependency"
    if record.pathname.startswith(_APPLICATION_SOURCE):
        origin = "application"
    elif record.pathname.startswith(_TEST_SOURCE):
        origin = "test"
    return {"origin": origin, "module": record.module, "function": record.funcName, "line": record.lineno}


def log_runtime() -> dict:
    """Collect only fixed runtime facts, never argv, test IDs or environment dumps."""
    environment = os.environ.get("AFTERGLOW_ENV", "").strip().lower()
    return {
        "environment": environment if environment in {"development", "test", "staging", "production"} else "other",
        "python": ".".join(str(part) for part in sys.version_info[:3]),
        "implementation": sys.implementation.name,
    }


def _mysql_error_code(exc: BaseException) -> int | None:
    """Read only known, already-loaded SQLAlchemy/PyMySQL DBAPI structures."""
    sqlalchemy = sys.modules.get("sqlalchemy.exc")
    wrapper = getattr_static(sqlalchemy, "DBAPIError", None) if sqlalchemy is not None else None
    if isinstance(wrapper, type) and isinstance(exc, wrapper):
        original = getattr_static(exc, "orig", None)
        if not isinstance(original, BaseException):
            return None
        exc = original
    driver = sys.modules.get("pymysql.err")
    driver_error = getattr_static(driver, "MySQLError", None) if driver is not None else None
    if not isinstance(driver_error, type) or not isinstance(exc, driver_error):
        return None
    args = BaseException.args.__get__(exc)
    if type(args) is tuple and args and type(args[0]) is int and 1000 <= args[0] <= 4999:
        return args[0]
    return None


def _exception_frames(tb: TracebackType | None) -> dict:
    frames: deque[dict] = deque(maxlen=_EXCEPTION_FRAME_LIMIT)
    scanned = 0
    while tb is not None and scanned < _EXCEPTION_TRACEBACK_LIMIT:
        frames.append({"function": tb.tb_frame.f_code.co_name[:_EXCEPTION_NAME_LIMIT], "line": tb.tb_lineno})
        tb = tb.tb_next
        scanned += 1
    metadata: dict = {"frames": list(frames)}
    if scanned > _EXCEPTION_FRAME_LIMIT or tb is not None:
        metadata["frames_truncated"] = True
    if tb is not None:
        metadata["traceback_truncated"] = True
    return metadata


def _exception_node(exc_type: type[BaseException], exc: BaseException | None, tb: TracebackType | None) -> dict:
    metadata = {"type": type.__getattribute__(exc_type, "__name__")[:_EXCEPTION_NAME_LIMIT], **_exception_frames(tb)}
    if exc is not None:
        error_code = _mysql_error_code(exc)
        if error_code is not None:
            metadata["error_code"] = error_code
        for key in ("status_code", "http_status", "status", "errno"):
            # Static lookup never evaluates provider properties or user-defined
            # conversions. OSError stores errno in a built-in slot, not __dict__.
            if key == "errno" and isinstance(exc, OSError):
                value = OSError.errno.__get__(exc)
            else:
                value = getattr_static(exc, key, None)
            low, high = (-(2**31), 2**31 - 1) if key == "errno" else (100, 599)
            if type(value) is int and low <= value <= high:
                metadata[key] = value
    return metadata


def exception_metadata(exc_info: tuple[type[BaseException], BaseException | None, TracebackType | None]) -> dict:
    """Return bounded structural diagnostics, never exception text or source.

    Each node has type (at most 128 characters), frames (last 12 visited
    {function, line} pairs), and optional plain-int status_code/http_status/status
    (100..599), errno (signed 32-bit), or known PyMySQL/SQLAlchemy DBAPI
    error_code (1000..4999). Properties and coercions are not used.
    frames_truncated marks omitted frames; traceback_truncated means the scan
    stopped at 1024 frames, so the innermost frame is not known.

    The outer node also has causes (up to 8 subsequent nodes, outer-to-inner)
    and root_cause (the terminal node, including itself for an unchained error).
    Explicit __cause__ wins over __context__, even with suppressed context.
    causes_truncated or cause_cycle makes root_cause null: no terminal root was
    established. Per-node traceback limits also apply to causes/root_cause.
    """
    exc_type, current, tb = exc_info
    metadata = _exception_node(exc_type, current, tb)
    causes: list[dict] = []
    metadata["causes"] = causes
    root = {key: value for key, value in metadata.items() if key != "causes"}
    seen = {id(current)}
    while current is not None:
        cause = BaseException.__cause__.__get__(current)
        if cause is None:
            cause = BaseException.__context__.__get__(current)
        if cause is None:
            break
        if id(cause) in seen:
            metadata["cause_cycle"] = True
            root = None
            break
        if len(causes) == _EXCEPTION_CAUSE_LIMIT:
            metadata["causes_truncated"] = True
            root = None
            break
        seen.add(id(cause))
        current = cause
        root = _exception_node(type(current), current, BaseException.__traceback__.__get__(current))
        causes.append(root)
    metadata["root_cause"] = root
    return metadata


# 정확 매칭 대상 필드명 (소문자 + 언더스코어 정규화)
_SENSITIVE_EXACT: frozenset[str] = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "token",
        "access_token",
        "refresh_token",
        "build_token",
        "report_token",
        "monitoring_sd_token",
        "x_auth_token",
        "ticket",
        "key",
        "cephx_key",
        "private_key",
        "api_key",
        "kubeconfig",
        "kube_config",
        "authorization",
        "cookie",
        "set_cookie",
        "headers",
        "body",
        "request_body",
        "credential",
        "credentials",
    }
)

# 필드명에 이 문자열이 포함되면 마스킹
_SENSITIVE_SUBSTR: tuple[str, ...] = (
    "password",
    "passwd",
    "secret",
    "token",
    "ticket",
    "private_key",
    "kubeconfig",
    "credential",
    "headers",
    "cookie",
    "body",
    "authorization",
    "api_key",
    "cephx_key",
    "kube_config",
)

# JWT/Bearer 패턴
_BEARER_RE = re.compile(r"((?:Bearer|Token)\s+)([A-Za-z0-9_./+=-]+)", re.IGNORECASE)
_JWT_RE = re.compile(r"(eyJ[A-Za-z0-9\-_]{4,}\.eyJ[A-Za-z0-9\-_]{4,})\.[A-Za-z0-9\-_]+")
_BASIC_RE = re.compile(r"(Basic\s+)[A-Za-z0-9+/=]+", re.IGNORECASE)
# Free-text assignments have no trustworthy value boundary (spaces, nested JSON,
# escaped quotes and multiline bodies are all possible). Drop the remaining text;
# callers can retain safe diagnostics in structured extra fields instead.
_SECRET_KEY_PATTERN = "|".join(re.escape(key).replace("_", "[_-]") for key in sorted(_SENSITIVE_EXACT))
_SECRET_SUBSTR_PATTERN = "|".join(re.escape(key).replace("_", "[_-]") for key in _SENSITIVE_SUBSTR)
_SECRET_ASSIGNMENT_RE = re.compile(
    rf"\b((?:{_SECRET_KEY_PATTERN})|[\w-]*(?:{_SECRET_SUBSTR_PATTERN})[\w-]*)"
    r"([\"']?\s*[=:]\s*).*",
    re.IGNORECASE | re.DOTALL,
)
_URL_USERINFO_RE = re.compile(r"(\b[a-z][a-z0-9+.-]*://)[^\s/]+@", re.IGNORECASE)
_PRIVATE_KEY_RE = re.compile(r"-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----", re.DOTALL)
# URL-encoded query keys also occur in HTTP/WebSocket exception diagnostics.
_QUERY_TICKET_RE = re.compile(
    r"((?:[?&]|%3f|%26)(?:amp;)?(?:t|%74)(?:i|%69)(?:c|%63)"
    r"(?:k|%6b)(?:e|%65)(?:t|%74)(?:=|%3d)).*",
    re.IGNORECASE | re.DOTALL,
)

# Ancestor logger levels do not constrain explicitly configured descendants.
# Clamp these namespaces at both root output handlers as well as logger setup.
WARNING_LOG_NAMESPACES = (
    "openstack",
    "urllib3",
    "keystoneauth1",
    "keystoneauth",
    "httpx",
    "httpcore",
    "requests",
    "urllib",
    "botocore",
    "boto3",
    "sqlalchemy.engine",
    "uvicorn.access",
    "aiosqlite",
    "asyncio",
    "stevedore",
)


def _normalize_key(key: str) -> str:
    return key.lower().replace("-", "_")


def is_sensitive(key: str) -> bool:
    """필드 이름이 민감 정보 키인지 판별."""
    k = _normalize_key(key)
    return k in _SENSITIVE_EXACT or any(s in k for s in _SENSITIVE_SUBSTR)


def mask_dict(d: dict, *, _depth: int = 3) -> dict:
    """Return recursively sanitized metadata, never unexamined deep values."""
    if _depth <= 0:
        return {"redacted": "***"}
    sanitized = {}
    for key, value in dict.items(d):
        if type(key) is str:
            sanitized[mask_str(key)] = "***" if is_sensitive(key) else sanitize_log_value(value, _depth=_depth - 1)
        elif key is None or type(key) in (bool, int, float):
            sanitized[str(key)] = sanitize_log_value(value, _depth=_depth - 1)
        else:
            # Dictionary keys can themselves be opaque credential objects.
            sanitized["<redacted>"] = "***"
    return sanitized


def sanitize_log_value(value: object, *, _depth: int = 3) -> object:
    """Bound recursion and never stringify opaque objects (requests, exceptions)."""
    if type(value) is str:
        return mask_str(value)
    if value is None or type(value) in (bool, int, float):
        return value
    if _depth <= 0:
        return "***"
    if type(value) is dict:
        return mask_dict(value, _depth=_depth)
    if type(value) in (list, tuple):
        return [sanitize_log_value(item, _depth=_depth - 1) for item in value]
    return "***"


def mask_str(msg: str) -> str:
    """Remove recognizable credentials from text after interpolation too."""
    msg = _PRIVATE_KEY_RE.sub("***", msg)
    msg = _BEARER_RE.sub(lambda m: m.group(1) + "***", msg)
    msg = _BASIC_RE.sub(lambda m: m.group(1) + "***", msg)
    msg = _JWT_RE.sub("***", msg)
    msg = _URL_USERINFO_RE.sub(lambda m: m.group(1) + "***@", msg)
    msg = _QUERY_TICKET_RE.sub(lambda m: m.group(1) + "***", msg)
    return _SECRET_ASSIGNMENT_RE.sub(lambda m: m.group(1) + m.group(2) + "***", msg)


class SensitiveDataFilter(logging.Filter):
    """로그 레코드에서 민감 데이터를 자동으로 마스킹하는 필터.

    - 메시지 문자열: JWT, Bearer 토큰 패턴 제거
    - extra 필드: 민감 키 이름 감지 후 값 마스킹
    """

    _SKIP_ATTRS: frozenset[str] = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__)

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno < logging.WARNING and any(
            record.name == namespace or record.name.startswith(namespace + ".") for namespace in WARNING_LOG_NAMESPACES
        ):
            return False
        if type(record.msg) is not str:
            record.msg = sanitize_log_value(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = mask_dict(record.args)
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    "***"
                    if isinstance(a, BaseException) or (type(a) is str and _looks_like_token(a))
                    else sanitize_log_value(a)
                    for a in record.args
                )
        # Mask the rendered message, not just the format string: split credential
        # assignments and Bearer placeholders otherwise evade the filter.
        record.msg = mask_str(record.getMessage())
        record.args = ()
        for attr in list(vars(record)):
            if type(attr) is not str:
                record.__dict__.pop(attr)
                record.__dict__["<redacted>"] = "***"
            elif attr in DIAGNOSTIC_LOG_FIELDS:
                value = sanitize_diagnostic_field(attr, record.__dict__[attr])
                if value is None:
                    record.__dict__.pop(attr)
                else:
                    record.__dict__[attr] = value
            elif attr not in self._SKIP_ATTRS:
                if mask_str(attr) != attr:
                    record.__dict__.pop(attr)
                    record.__dict__["<redacted>"] = "***"
                else:
                    setattr(record, attr, "***" if is_sensitive(attr) else sanitize_log_value(getattr(record, attr)))
        record.exc_text = None
        record.stack_info = None
        return True


def _looks_like_token(s: str) -> bool:
    """문자열이 토큰처럼 보이는지 휴리스틱 판별 (영숫자+특수문자만, 공백 없음)."""
    return bool(s) and " " not in s and re.fullmatch(r"[A-Za-z0-9\-_\.+/=]{20,}", s) is not None
