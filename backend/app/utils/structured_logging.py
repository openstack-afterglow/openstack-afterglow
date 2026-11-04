"""API- and worker-safe structured logging without application entrypoint imports."""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from app.utils.log import (
    DIAGNOSTIC_LOG_FIELDS,
    WARNING_LOG_NAMESPACES,
    SensitiveDataFilter,
    exception_metadata,
    is_sensitive,
    log_file_directory,
    log_runtime,
    log_source,
    mask_str,
    sanitize_diagnostic_field,
    sanitize_log_value,
)

_STANDARD_LOG_KEYS = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__)
_ENTRYPOINTS = frozenset({"api", "worker", "unknown"})


class JSONFormatter(logging.Formatter):
    def __init__(self, *, file_scope: str = "runtime", entrypoint: str = "unknown") -> None:
        super().__init__()
        self._runtime = {
            **log_runtime(),
            "file_scope": file_scope if type(file_scope) is str and file_scope in {"runtime", "pytest"} else "runtime",
            "entrypoint": entrypoint if type(entrypoint) is str and entrypoint in _ENTRYPOINTS else "unknown",
        }

    def format(self, record: logging.LogRecord) -> str:
        entry: dict = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": mask_str(record.getMessage()),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_LOG_KEYS and key != "message":
                if key in DIAGNOSTIC_LOG_FIELDS:
                    diagnostic = sanitize_diagnostic_field(key, value)
                    if diagnostic is not None:
                        entry[key] = diagnostic
                else:
                    entry[key] = "***" if is_sensitive(key) else sanitize_log_value(value)
        entry["source"] = log_source(record)
        entry["process"] = {"pid": record.process}
        entry["runtime"] = self._runtime
        if record.exc_info and record.exc_info[0]:
            entry["exception"] = exception_metadata(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def setup_logging(*, entrypoint: str = "unknown") -> None:
    from app.config import get_settings
    from app.utils.daily_size_handler import DailySizeHandler

    cfg = get_settings()
    entrypoint = entrypoint if type(entrypoint) is str and entrypoint in _ENTRYPOINTS else "unknown"
    sensitive_filter = SensitiveDataFilter()
    directory = log_file_directory(cfg.log_directory)
    formatter = JSONFormatter(
        file_scope="pytest" if directory != Path(cfg.log_directory) else "runtime", entrypoint=entrypoint
    )
    root = logging.getLogger()
    root.handlers.clear()

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.addFilter(sensitive_filter)
    root.addHandler(stream_handler)
    if entrypoint == "api":
        # Request-only evidence imports API activity state on emission. Workers
        # have no request context and must not acquire those dependencies.
        from app.utils.auth_diagnostics import RequestDiagnosticHandler

        root.addHandler(RequestDiagnosticHandler())

    try:
        file_handler = DailySizeHandler(
            log_directory=directory,
            max_bytes=cfg.log_max_bytes,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        file_handler.addFilter(sensitive_filter)
        root.addHandler(file_handler)
    except OSError:
        pass  # Keep stream output when the configured directory cannot be opened.

    level = getattr(logging, cfg.log_level.upper(), logging.INFO)
    root.setLevel(level)
    # Application DEBUG must not enable third-party wire or SQL parameter dumps.
    logging.getLogger("app").setLevel(logging.DEBUG if cfg.debug else logging.NOTSET)
    if entrypoint == "worker":
        logging.getLogger("notion").setLevel(logging.DEBUG if cfg.debug else logging.NOTSET)
    for namespace in WARNING_LOG_NAMESPACES:
        logging.getLogger(namespace).setLevel(logging.WARNING)
    # Uvicorn can install non-propagating handlers before API initialization.
    for namespace in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(namespace)
        for handler in logger.handlers:
            handler.addFilter(sensitive_filter)
    logging.getLogger(__name__).debug(
        "logging configuration",
        extra={
            "application_level": "DEBUG" if cfg.debug else logging.getLevelName(level),
            "root_level": logging.getLevelName(level),
        },
    )
