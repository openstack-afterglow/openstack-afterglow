"""Structured API and background-operation logging must never echo user input."""

import io
import json
import logging
import os
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from app.main import (
    _JSONFormatter,
    _setup_logging,
    app,
    request_logging_middleware,
    sanitized_http_exception_handler,
    unhandled_exception_handler,
)
from app.services.layer_build import run_layer_build


@pytest.mark.asyncio
async def test_request_completion_has_template_and_no_input_on_success_or_failure(caplog):
    secret = "dont-log-this-password"
    api = FastAPI()
    api.middleware("http")(request_logging_middleware)
    api.add_exception_handler(HTTPException, sanitized_http_exception_handler)
    api.add_exception_handler(Exception, unhandled_exception_handler)

    @api.get("/items/{item_id}")
    async def get_item(item_id: str):
        return {"id": item_id}

    @api.get("/bad/{item_id}")
    async def bad(item_id: str):
        raise HTTPException(400, detail=secret)

    @api.post("/fail/{item_id}")
    async def fail(item_id: str):
        raise RuntimeError(secret)

    with caplog.at_level(logging.INFO):
        async with AsyncClient(
            transport=ASGITransport(app=api, raise_app_exceptions=False), base_url="http://test"
        ) as client:
            requests = (
                await client.get(f"/items/{secret}?access_token={secret}"),
                await client.get(f"/bad/{secret}?access_token={secret}"),
                await client.post(f"/fail/{secret}?access_token={secret}", json={"password": secret}),
                await client.get(f"/unknown/{secret}?access_token={secret}"),
            )

    assert [response.status_code for response in requests] == [200, 400, 500, 404]
    records = [r for r in caplog.records if r.name == "app.main" and r.msg == "request"]
    assert [(r.path, r.status) for r in records] == [
        ("/items/{item_id}", 200),
        ("/bad/{item_id}", 400),
        ("/fail/{item_id}", 500),
        ("<unmatched>", 404),
    ]
    assert all(r.levelno == logging.INFO and r.duration_ms >= 0 for r in records)
    assert secret not in "\n".join(_JSONFormatter().format(record) for record in caplog.records)


@pytest.mark.asyncio
async def test_health_request_is_logged(caplog):
    with caplog.at_level(logging.INFO):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert any(r.msg == "request" and r.path == "/api/v1/health" and r.status == 200 for r in caplog.records)


@pytest.mark.asyncio
async def test_build_execution_info_and_debug_are_bounded_and_sanitized(caplog):
    secret = "secret-index-credential"

    async def run():
        with patch("app.services.layer_build._update_build_db", new_callable=AsyncMock):
            await run_layer_build(
                build_db_id=123,
                layer_name=secret,
                kind="pip",
                python_version=None,
                pip_packages=[secret],
                pip_index_url=f"https://{secret}@example.test/simple",
                parent_artifact_id=None,
            )

    with caplog.at_level(logging.INFO):
        await run()
    events = [r for r in caplog.records if r.name == "app.services.layer_build" and r.msg == "execution"]
    assert [(r.state, getattr(r, "result", None)) for r in events] == [("started", None), ("completed", "failed")]
    assert not any(r.msg == "execution metadata" for r in caplog.records)
    assert secret not in "\n".join(_JSONFormatter().format(r) for r in caplog.records)

    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        await run()
    metadata = [r for r in caplog.records if r.name == "app.services.layer_build" and r.msg == "execution metadata"]
    assert [(r.state, r.query) for r in metadata] == [
        ("validating", "recipe_contract"),
        ("completed", "recipe_contract"),
    ]
    assert metadata[0].pip_package_count == 1
    assert metadata[-1].result == "failed"
    assert secret not in "\n".join(_JSONFormatter().format(r) for r in caplog.records)


@pytest.fixture
def configured_logging(tmp_path, monkeypatch):
    """Use real configuration and both real output handlers, restoring log state."""
    from app import config

    root = logging.getLogger()
    previous_handlers = root.handlers[:]
    previous_level = root.level
    previous_levels = {
        name: logger.level for name, logger in root.manager.loggerDict.items() if isinstance(logger, logging.Logger)
    }
    previous_sources = config._LOADED_CONFIG_SOURCES[:]
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "_config_candidates", lambda: [tmp_path / "afterglow.conf"])
    stream = io.StringIO()

    def configure(default_debug="true", env_debug=None, log_level="INFO"):
        content = f'[logging]\nlog_level = "{log_level}"\nlog_directory = "logs"\n'
        if default_debug is not None:
            content += f"[DEFAULT]\ndebug = {default_debug}\n"
        (tmp_path / "afterglow.conf").write_text(content, encoding="utf-8")
        if env_debug is not None:
            os.environ["DEBUG"] = env_debug
        config.get_settings.cache_clear()
        config.load_raw_toml.cache_clear()
        logging.getLogger("app.main").setLevel(logging.NOTSET)
        monkeypatch.setattr("sys.stderr", stream)
        _setup_logging()
        return stream, tmp_path / "logs"

    with patch.dict(
        os.environ,
        {
            "AFTERGLOW_ENV": "development",
            "SECRET_KEY": "6ea4d2fb7c1e9d035a18be4f2740317c9d08ab72f3c46e901bf67ad5041c8ef2",
        },
        clear=True,
    ):
        try:
            yield configure
        finally:
            for handler in root.handlers:
                handler.close()
            root.handlers[:] = previous_handlers
            root.setLevel(previous_level)
            for name, logger in root.manager.loggerDict.copy().items():
                if isinstance(logger, logging.Logger):
                    logger.setLevel(previous_levels.get(name, logging.NOTSET))
            config.get_settings.cache_clear()
            config.load_raw_toml.cache_clear()
            config._LOADED_CONFIG_SOURCES[:] = previous_sources


@pytest.mark.parametrize(
    ("toml_debug", "env_debug", "log_level", "debug_emitted", "root_info_emitted"),
    [
        ("true", None, "INFO", True, True),
        ("false", None, "INFO", False, True),
        (None, None, "INFO", False, True),
        ("true", "false", "INFO", False, True),
        ("false", "true", "INFO", True, True),
        (None, None, "DEBUG", True, True),
        ("false", None, "WARNING", False, False),
        ("true", None, "WARNING", True, False),
    ],
)
def test_configured_debug_controls_actual_application_output(
    configured_logging, toml_debug, env_debug, log_level, debug_emitted, root_info_emitted
):
    stream, directory = configured_logging(toml_debug, env_debug, log_level)
    logger = logging.getLogger("app.main")
    logger.debug("consumer diagnostic", extra={"decision": "completed"})
    logging.getLogger("diagnostic_consumer").info("root consumer info")
    for namespace in ("openstack", "keystoneauth1", "urllib3", "httpx", "httpcore", "botocore", "sqlalchemy.engine"):
        logging.getLogger(namespace).debug("raw-wire-secret")

    outputs = [stream.getvalue(), "".join(path.read_text() for path in directory.glob("backend-*.log"))]
    for output in outputs:
        events = [json.loads(line) for line in output.splitlines()]
        diagnostics = [event for event in events if event["message"] == "consumer diagnostic"]
        assert bool(diagnostics) is debug_emitted
        assert any(event["message"] == "root consumer info" for event in events) is root_info_emitted
        assert "raw-wire-secret" not in output
        if diagnostics:
            assert diagnostics[0]["level"] == "DEBUG"
            assert diagnostics[0]["decision"] == "completed"
            assert diagnostics[0]["source"]["function"] == "test_configured_debug_controls_actual_application_output"
            assert diagnostics[0]["source"]["line"] > 0


def test_emitted_diagnostics_redact_nested_credentials_and_exception_text(configured_logging):
    stream, directory = configured_logging()
    logger = logging.getLogger("app.main")
    secret = "short-sensitive-value"

    class OpaqueCredential:
        def __str__(self):
            return secret

    try:
        raise RuntimeError(secret)
    except RuntimeError as exc:
        logger.debug(
            "decision failed: %s password=%s Authorization: Bearer %s endpoint=https://%s@example.test",
            exc,
            secret,
            secret,
            secret,
            exc_info=True,
            stack_info=True,
            extra={
                "credentials": secret,
                "headers": {"Authorization": secret},
                "request_body": secret,
                "metadata": {
                    "items": [{"cookie": secret, "safe_count": 2}],
                    "deep": {"a": {"b": {"password": secret}}},
                    "opaque": OpaqueCredential(),
                    "note": f"api_key={secret}",
                },
            },
        )

    for output in (stream.getvalue(), "".join(path.read_text() for path in directory.glob("backend-*.log"))):
        assert secret not in output
        event = next(json.loads(line) for line in output.splitlines() if "decision failed" in line)
        assert event["credentials"] == "***"
        assert event["headers"] == "***"
        assert event["request_body"] == "***"
        assert event["exception"]["type"] == "RuntimeError"
        assert event["exception"]["frames"]
        assert all(set(frame) == {"function", "line"} for frame in event["exception"]["frames"])


@pytest.mark.asyncio
async def test_debug_request_diagnostics_use_only_safe_route_and_outcome_metadata(configured_logging):
    stream, directory = configured_logging()
    secret = "request-credential-must-not-appear"
    api = FastAPI()
    api.middleware("http")(request_logging_middleware)
    api.add_exception_handler(HTTPException, sanitized_http_exception_handler)
    api.add_exception_handler(Exception, unhandled_exception_handler)

    @api.post("/debug/{item_id}")
    async def failing_request(item_id: str):
        raise RuntimeError(secret)

    @api.get("/denied/{item_id}")
    async def denied_request(item_id: str):
        raise HTTPException(403, detail="denied")

    @api.get("/ok/{item_id}")
    async def ok_request(item_id: str):
        return {"ok": True}

    async with AsyncClient(
        transport=ASGITransport(app=api, raise_app_exceptions=False), base_url="http://test"
    ) as client:
        failed = await client.post(
            f"/debug/{secret}?api_key={secret}",
            headers={"Authorization": f"Bearer {secret}", "Cookie": f"session={secret}"},
            json={"password": secret},
        )
        denied = await client.get(f"/denied/{secret}")
        missing = await client.get(f"/unmatched/{secret}")
        completed = await client.get(f"/ok/{secret}")
    assert [failed.status_code, denied.status_code, missing.status_code, completed.status_code] == [500, 403, 404, 200]
    assert failed.json() == {"detail": "내부 서버 오류"}
    assert "text/html" not in failed.headers["content-type"]
    assert app.debug is False
    for output in (stream.getvalue(), "".join(path.read_text() for path in directory.glob("backend-*.log"))):
        assert secret not in output
        events = [json.loads(line) for line in output.splitlines()]
        diagnostics = [event for event in events if event["message"] == "request diagnostic"]
        assert [(event["path"], event["outcome"], event["route_matched"]) for event in diagnostics] == [
            ("/debug/{item_id}", "server_error", True),
            ("/denied/{item_id}", "client_error", True),
            ("<unmatched>", "client_error", False),
            ("/ok/{item_id}", "completed", True),
        ]
        assert all(event["level"] == "DEBUG" and event["duration_ms"] >= 0 for event in diagnostics)
        assert all(not ({"headers", "body", "query", "token", "exception"} & set(event)) for event in diagnostics)


@pytest.mark.parametrize(
    ("template", "credential"),
    [
        ("Bearer %s", "abc"),
        ("Basic %s", "dXNlcjpwYXNz"),
        ("password=%s", "p4ss"),
        ("client_secret='%s'", "two word credential"),
        ("https://user:%s@example.test", "p4ss"),
        ("jwt=%s", "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.signature"),
        ("%s", "-----BEGIN " + "PRIVATE KEY-----\nfake-test-key\n-----END " + "PRIVATE KEY-----"),
        ("cephx_key=%s", "short-ceph-key"),
        ("kube-config=%s", "short-config"),
        ("key=%s", "short-key"),
        ("HTTP_AUTHORIZATION=%s", "short-auth"),
        ("db_api_key=%s", "short-api-key"),
        ("body=%s", '{"nested": {"value": "short-body-value"}}'),
        ("headers=%s", '{"X-Custom": "short-header-value"}'),
        ("password=%s", "two unquoted words"),
        ("password=%s", '"escaped \\"quoted\\" credential"'),
        ("request_body=%s", "multiline\nshort-body-value"),
    ],
)
def test_debug_credentials_are_fully_redacted_in_both_outputs(configured_logging, template, credential):
    stream, directory = configured_logging()
    logging.getLogger("app.main").debug(template, credential)
    for output in (stream.getvalue(), "".join(path.read_text() for path in directory.glob("backend-*.log"))):
        assert credential not in output
        events = [json.loads(line) for line in output.splitlines()]
        assert "***" in events[-1]["message"]
        if template.endswith("=%s"):
            assert events[-1]["message"] == template.replace("%s", "***")


@pytest.mark.parametrize(
    "namespace",
    [
        "openstack",
        "keystoneauth1",
        "urllib3",
        "httpx",
        "httpcore",
        "requests",
        "urllib",
        "botocore",
        "boto3",
        "sqlalchemy.engine",
        "uvicorn.access",
    ],
)
def test_wire_descendants_remain_warning_clamped_in_both_outputs(configured_logging, namespace):
    stream, directory = configured_logging(log_level="DEBUG")
    wire = logging.getLogger(namespace + ".explicit_debug_consumer")
    wire.setLevel(logging.DEBUG)
    wire.debug("raw wire debug must not appear")
    wire.info("raw wire info must not appear")
    wire.warning("safe wire warning")
    logging.getLogger("app.main").debug("safe application diagnostic")
    unrelated = logging.getLogger(namespace + "_consumer")
    unrelated.setLevel(logging.DEBUG)
    unrelated.debug("safe unrelated diagnostic")

    for output in (stream.getvalue(), "".join(path.read_text() for path in directory.glob("backend-*.log"))):
        messages = [json.loads(line)["message"] for line in output.splitlines()]
        assert "raw wire debug must not appear" not in messages
        assert "raw wire info must not appear" not in messages
        assert "safe wire warning" in messages
        assert "safe application diagnostic" in messages
        assert "safe unrelated diagnostic" in messages


def test_opaque_keys_and_builtin_subclasses_never_invoke_representation(configured_logging):
    stream, directory = configured_logging()

    class OpaqueCredential:
        def __str__(self):
            pytest.fail("opaque credential string conversion must not run")

        def __repr__(self):
            pytest.fail("opaque credential representation must not run")

    class CredentialString(str):
        __str__ = OpaqueCredential.__str__
        __repr__ = OpaqueCredential.__repr__

    class CredentialNumber(int):
        __str__ = OpaqueCredential.__str__
        __repr__ = OpaqueCredential.__repr__

    logger = logging.getLogger("app.main")
    logger.debug(
        "opaque diagnostic %s %s",
        CredentialString("hidden-string-value"),
        CredentialNumber(123),
        extra={
            OpaqueCredential(): "hidden-extra-key-value",
            "Bearer " + "hidden-extra-name-value": "hidden-extra-value",
            "HTTP_AUTHORIZATION": "hidden-authorization-value",
            "db_api_key": "hidden-api-key-value",
            "metadata": {OpaqueCredential(): "hidden-key-value", "opaque": OpaqueCredential(), "safe_count": 2},
        },
    )
    logger.debug(CredentialString("hidden-message-value"))
    for output in (stream.getvalue(), "".join(path.read_text() for path in directory.glob("backend-*.log"))):
        assert "hidden-" not in output
        events = [json.loads(line) for line in output.splitlines()]
        event = next(event for event in events if event["message"].startswith("opaque diagnostic"))
        assert event["message"] == "opaque diagnostic *** ***"
        assert event["metadata"] == {"<redacted>": "***", "opaque": "***", "safe_count": 2}
        assert event["<redacted>"] == "***"
        assert event["HTTP_AUTHORIZATION"] == "***"
        assert event["db_api_key"] == "***"
        assert events[-1]["message"] == "***"


def test_exception_frames_are_bounded_without_messages_causes_or_source(configured_logging):
    stream, directory = configured_logging()
    secret = "exception-cause-and-message-must-not-appear"

    def fail(depth):
        if depth:
            return fail(depth - 1)
        try:
            raise ValueError(secret)
        except ValueError as cause:
            raise RuntimeError(secret) from cause

    try:
        fail(20)
    except RuntimeError:
        logging.getLogger("app.main").debug("bounded failure", exc_info=True, stack_info=True)

    for output in (stream.getvalue(), "".join(path.read_text() for path in directory.glob("backend-*.log"))):
        assert secret not in output
        event = next(json.loads(line) for line in output.splitlines() if "bounded failure" in line)
        assert set(event["exception"]) == {"type", "frames"}
        assert event["exception"]["type"] == "RuntimeError"
        assert len(event["exception"]["frames"]) == 12
        assert all(set(frame) == {"function", "line"} for frame in event["exception"]["frames"])
