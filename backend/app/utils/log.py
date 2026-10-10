"""보안 민감 데이터 마스킹 로그 유틸리티."""

from __future__ import annotations

import logging
import re

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

# Ancestor logger levels do not constrain explicitly configured descendants.
# Clamp these namespaces at both root output handlers as well as logger setup.
WARNING_LOG_NAMESPACES = (
    "openstack",
    "urllib3",
    "keystoneauth1",
    "httpx",
    "httpcore",
    "requests",
    "urllib",
    "botocore",
    "boto3",
    "sqlalchemy.engine",
    "uvicorn.access",
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
