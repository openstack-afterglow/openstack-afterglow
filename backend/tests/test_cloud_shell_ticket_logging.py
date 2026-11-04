"""Sanitize the actual Uvicorn websocket record shape and structured metadata."""

import io
import logging
from types import SimpleNamespace

import pytest

from app.utils.log import SensitiveDataFilter, mask_dict, mask_str


@pytest.mark.parametrize("suffix", ["[accepted]", "403", "500"])
@pytest.mark.parametrize("scheme", ["", "ws://localhost", "wss://cloud.example.test"])
@pytest.mark.parametrize("key", ["ticket", "TICKET", "%74%69%63%6b%65%74", "t%69cket"])
def test_uvicorn_websocket_accept_reject_shape_never_renders_query_ticket(suffix, scheme, key):
    ticket = "opaque-single-use-shell-ticket-value"
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.addFilter(SensitiveDataFilter())
    handler.setFormatter(logging.Formatter("%(name)s %(message)s %(x_auth_token)s"))
    # Uvicorn uses its error logger, not the access logger, for all websocket
    # accept/reject variants. Production must attach the filter to its handler.
    record = logging.LogRecord(
        "uvicorn.error",
        logging.INFO,
        __file__,
        1,
        '%s - "WebSocket %s" ' + suffix,
        ("127.0.0.1:12345", f"{scheme}/api/v1/cloud-shell/ws?{key}={ticket}"),
        None,
    )
    record.x_auth_token = "native-keystone-token-secret"
    handler.handle(record)
    rendered = output.getvalue()
    assert ticket not in rendered
    assert "native-keystone-token-secret" not in rendered
    assert "uvicorn.error" in rendered
    assert "/api/v1/cloud-shell/ws?" in rendered


def test_query_ticket_and_native_tokens_are_redacted_together_in_metadata():
    ticket = "single-use-secret"
    token = "native-token-secret"
    values = mask_dict(
        {
            "url": f"wss://cloud.example.test/api/v1/cloud-shell/ws?ticket={ticket}&token={token}",
            "ticket": ticket,
            "shell_ticket": ticket,
            "x-auth-token": token,
            "safe": "container_unavailable",
        }
    )
    assert ticket not in repr(values)
    assert token not in repr(values)
    assert values["safe"] == "container_unavailable"
    assert values["ticket"] == values["shell_ticket"] == values["x-auth-token"] == "***"


@pytest.mark.parametrize(
    "url",
    [
        "wss://cloud.example.test/api/v1/cloud-shell/ws?ticket=secret",
        "wss://cloud.example.test/api/v1/cloud-shell/ws?x=1&ticket=secret",
        "wss://cloud.example.test/api/v1/cloud-shell/ws?x=1&amp;ticket=secret",
        "wss://cloud.example.test/api/v1/cloud-shell/ws%3F%74icket%3Dsecret",
    ],
)
def test_free_text_and_encoded_websocket_urls_do_not_disclose_ticket(url):
    assert "secret" not in mask_str("connection failed " + url)


def test_noncredential_diagnostic_strings_are_unchanged():
    assert mask_str("Cloud Shell container unavailable") == "Cloud Shell container unavailable"
    assert mask_str("a ticket to ride") == "a ticket to ride"


def test_application_setup_filters_uvicorn_nonpropagating_handlers(monkeypatch, tmp_path):
    from app import config
    from app.utils.structured_logging import setup_logging

    root = logging.getLogger()
    root_handlers = root.handlers[:]
    root_level = root.level
    previous_levels = {
        name: logger.level for name, logger in root.manager.loggerDict.items() if isinstance(logger, logging.Logger)
    }
    names = ("uvicorn", "uvicorn.error", "uvicorn.access")
    loggers = {name: logging.getLogger(name) for name in names}
    previous = {
        name: (logger.handlers[:], logger.propagate, logger.disabled, logger.filters[:])
        for name, logger in loggers.items()
    }
    outputs = {name: io.StringIO() for name in names}
    handlers = {name: logging.StreamHandler(outputs[name]) for name in names}
    monkeypatch.setattr(
        config,
        "get_settings",
        lambda: SimpleNamespace(
            log_directory=str(tmp_path / "logs"),
            log_max_bytes=1048576,
            log_level="INFO",
            debug=False,
        ),
    )
    try:
        for name, logger in loggers.items():
            logger.handlers = [handlers[name]]
            logger.propagate = False
            logger.disabled = False
            logger.filters = []
            logger.setLevel(logging.INFO)
        setup_logging(entrypoint="api")
        # Exercise own handlers first, then Uvicorn's actual default route:
        # uvicorn.error -> uvicorn, whose handler does not propagate to root.
        for name, logger in loggers.items():
            logger.warning(
                '%s - "WebSocket %s" 403', "127.0.0.1:12345", "/api/v1/cloud-shell/ws?ticket=owned-handler-secret"
            )
            assert "owned-handler-secret" not in outputs[name].getvalue()
            assert "/api/v1/cloud-shell/ws?ticket=" in outputs[name].getvalue()
        loggers["uvicorn.error"].handlers = []
        loggers["uvicorn.error"].propagate = True
        loggers["uvicorn.error"].info(
            '%s - "WebSocket %s" [accepted]',
            "127.0.0.1:12345",
            "/api/v1/cloud-shell/ws?ticket=default-handler-secret",
        )
        assert "default-handler-secret" not in outputs["uvicorn"].getvalue()
    finally:
        for handler in root.handlers[:]:
            if handler not in root_handlers:
                handler.close()
        root.handlers = root_handlers
        root.setLevel(root_level)
        for name, (saved_handlers, propagate, disabled, filters) in previous.items():
            logger = loggers[name]
            logger.handlers = saved_handlers
            logger.propagate = propagate
            logger.disabled = disabled
            logger.filters = filters
        for name, level in previous_levels.items():
            logging.getLogger(name).setLevel(level)
        for handler in handlers.values():
            handler.close()
