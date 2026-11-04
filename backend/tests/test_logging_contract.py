"""Structured API and background-operation logging must never echo user input."""

import io
import json
import logging
import os
import sys
from types import TracebackType
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, HTTPException, Request
from httpx import ASGITransport, AsyncClient

from app.main import (
    app,
    request_logging_middleware,
    sanitized_http_exception_handler,
    unhandled_exception_handler,
)
from app.services.layer_build import run_layer_build
from app.utils.log import DIAGNOSTIC_LOG_FIELDS
from app.utils.structured_logging import JSONFormatter, setup_logging


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
    assert secret not in "\n".join(JSONFormatter().format(record) for record in caplog.records)


@pytest.mark.asyncio
async def test_build_execution_info_and_debug_are_bounded_and_sanitized(caplog, monkeypatch, tmp_path):
    from fakeredis.aioredis import FakeRedis
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.db import LayerArtifact, LayerBuild
    from app.services import build_work

    secret = "secret-index-credential"
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'build-logging.sqlite'}")
    async with engine.begin() as connection:
        for model in (LayerBuild, LayerArtifact):
            await connection.run_sync(lambda sync, model=model: model.__table__.create(sync))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr("app.database.get_session_factory", lambda: factory)
    recipe = {
        "layer_name": secret,
        "kind": "pip",
        "python_version": None,
        "pip_packages": [secret],
        "pip_index_url": f"https://{secret}@example.test/simple",
        "parent_artifact_id": None,
    }
    async with factory() as session:
        row = LayerBuild(
            layer_name=secret,
            kind="pip",
            share_id="",
            status="queued",
            build_token="b" * 32,
            resource_snapshot={"build_input": recipe},
        )
        session.add(row)
        await session.commit()
        build_id = row.id
    redis = FakeRedis(decode_responses=True)

    class Lease:
        async def check(self):
            return None

    async def run():
        # The terminal write is stubbed so the same queued SQL row replays at DEBUG.
        with patch("app.services.layer_build._update_build_db", new_callable=AsyncMock):
            async with build_work.bind(redis, f"layer:{build_id}", Lease()):
                await run_layer_build(build_id)

    try:
        with caplog.at_level(logging.INFO, logger="app.services.layer_build"):
            await run()
        events = [r for r in caplog.records if r.name == "app.services.layer_build" and r.msg == "execution"]
        assert [(r.state, getattr(r, "result", None)) for r in events] == [("started", None), ("completed", "failed")]
        assert not any(r.msg == "execution metadata" for r in caplog.records)
        assert secret not in "\n".join(JSONFormatter().format(r) for r in caplog.records)

        caplog.clear()
        with caplog.at_level(logging.DEBUG, logger="app.services.layer_build"):
            await run()
        metadata = [r for r in caplog.records if r.name == "app.services.layer_build" and r.msg == "execution metadata"]
        assert [(r.state, r.query) for r in metadata] == [
            ("validating", "recipe_contract"),
            ("completed", "recipe_contract"),
        ]
        assert metadata[0].pip_package_count == 1
        assert metadata[-1].result == "failed"
        assert secret not in "\n".join(JSONFormatter().format(r) for r in caplog.records)
    finally:
        await redis.close()
        await engine.dispose()


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
    uvicorn_loggers = [logging.getLogger(name) for name in ("uvicorn", "uvicorn.error", "uvicorn.access")]
    previous_uvicorn = [(logger, logger.handlers[:], logger.propagate) for logger in uvicorn_loggers]
    previous_sources = config._LOADED_CONFIG_SOURCES[:]
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "_config_candidates", lambda: [tmp_path / "afterglow.conf"])
    stream = io.StringIO()

    def configure(default_debug="true", env_debug=None, log_level="INFO"):
        log_directory = tmp_path / "logs"
        content = f'[logging]\nlog_level = "{log_level}"\nlog_directory = "{log_directory.as_posix()}"\n'
        if default_debug is not None:
            content += f"[DEFAULT]\ndebug = {default_debug}\n"
        (tmp_path / "afterglow.conf").write_text(content, encoding="utf-8")
        if env_debug is not None:
            os.environ["DEBUG"] = env_debug
        config.get_settings.cache_clear()
        config.load_raw_toml.cache_clear()
        logging.getLogger("app.main").setLevel(logging.NOTSET)
        # These assertions exercise Afterglow's two root outputs, not Uvicorn's
        # non-propagating text handlers left by earlier in-process TCP tests.
        # AccessFormatter requires a native five-argument HTTP access record;
        # an arbitrary descendant warning is intentionally not such a record.
        for logger in uvicorn_loggers:
            logger.handlers = []
            logger.propagate = True
        monkeypatch.setattr("sys.stderr", stream)
        setup_logging(entrypoint="api")
        from app.utils.daily_size_handler import DailySizeHandler

        directory = next(
            handler.log_directory for handler in logging.getLogger().handlers if isinstance(handler, DailySizeHandler)
        )
        return stream, directory

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
            for logger, handlers, propagate in previous_uvicorn:
                logger.handlers = handlers
                logger.propagate = propagate
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
    for namespace in (
        "openstack",
        "keystoneauth1",
        "keystoneauth",
        "urllib3",
        "httpx",
        "httpcore",
        "botocore",
        "sqlalchemy.engine",
    ):
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


def test_root_output_fixture_isolates_uvicorn_access_formatter(configured_logging):
    from uvicorn.logging import AccessFormatter, DefaultFormatter

    native_output = io.StringIO()
    for name, formatter in (
        ("uvicorn", DefaultFormatter("%(levelprefix)s %(message)s")),
        ("uvicorn.access", AccessFormatter('%(client_addr)s - "%(request_line)s" %(status_code)s')),
    ):
        handler = logging.StreamHandler(native_output)
        handler.setFormatter(formatter)
        logger = logging.getLogger(name)
        logger.handlers = [handler]
        logger.propagate = False

    stream, directory = configured_logging(log_level="DEBUG")
    logging.getLogger("uvicorn.access.explicit_debug_consumer").warning("safe wire warning")
    unrelated = logging.getLogger("uvicorn.access_consumer")
    unrelated.setLevel(logging.DEBUG)
    unrelated.debug("safe unrelated diagnostic")

    assert native_output.getvalue() == ""
    for output in (stream.getvalue(), "".join(path.read_text() for path in directory.glob("backend-*.log"))):
        messages = [json.loads(line)["message"] for line in output.splitlines()]
        assert "safe wire warning" in messages
        assert "safe unrelated diagnostic" in messages


@pytest.mark.parametrize(
    "namespace",
    [
        "openstack",
        "keystoneauth1",
        "keystoneauth",
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


def test_exception_frames_retain_innermost_failure_without_text_or_source(configured_logging):
    stream, directory = configured_logging()
    secret = "exception-cause-and-message-must-not-appear"

    def innermost_failure():
        raise ValueError(secret)

    def fail(depth):
        if depth:
            return fail(depth - 1)
        return innermost_failure()

    try:
        fail(30)
    except ValueError:
        logging.getLogger("app.main").debug("bounded failure", exc_info=True, stack_info=True)

    for output in (stream.getvalue(), "".join(path.read_text() for path in directory.glob("backend-*.log"))):
        assert secret not in output
        event = next(json.loads(line) for line in output.splitlines() if "bounded failure" in line)
        metadata = event["exception"]
        assert set(metadata) == {"type", "frames", "frames_truncated", "causes", "root_cause"}
        assert metadata["type"] == "ValueError"
        assert metadata["causes"] == []
        assert len(metadata["frames"]) == 12
        assert metadata["frames_truncated"] is True
        assert all(set(frame) == {"function", "line"} for frame in metadata["frames"])
        assert metadata["frames"][-1] == {
            "function": "innermost_failure",
            "line": innermost_failure.__code__.co_firstlineno + 1,
        }
        assert metadata["root_cause"] == {
            key: value for key, value in metadata.items() if key not in {"causes", "root_cause"}
        }


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [503, 400, 500])
async def test_main_handlers_emit_translated_root_diagnostics_to_console_and_file(configured_logging, status):
    stream, directory = configured_logging()
    assert any(handler.stream is sys.stderr for handler in logging.getLogger().handlers)
    secret = "translated-provider-credential-must-not-appear"
    api = FastAPI()
    api.add_exception_handler(HTTPException, sanitized_http_exception_handler)
    api.add_exception_handler(Exception, unhandled_exception_handler)

    class ProviderFailure(Exception):
        http_status = 502

    failure = OSError(5, secret, secret)
    failure.status = 504

    def innermost_failure():
        raise failure

    def deep_call(depth):
        if depth:
            return deep_call(depth - 1)
        return innermost_failure()

    def provider_call():
        try:
            deep_call(30)
        except OSError as cause:
            translated = ProviderFailure(secret)
            translated.status_code = 502
            raise translated from cause

    @api.get("/translated/{item_id}")
    async def translated_request(item_id: str):
        try:
            provider_call()
        except ProviderFailure:
            if status == 500:
                raise RuntimeError(secret) from None
            raise HTTPException(status, detail=secret) from None

    async with AsyncClient(
        transport=ASGITransport(app=api, raise_app_exceptions=False), base_url="http://test"
    ) as client:
        response = await client.get(f"/translated/{secret}?api_key={secret}")
    assert response.status_code == status
    if status >= 500:
        assert response.json() == {"detail": "내부 서버 오류"}

    for output in (stream.getvalue(), "".join(path.read_text() for path in directory.glob("backend-*.log"))):
        assert secret not in output
        events = [json.loads(line) for line in output.splitlines()]
        event = next(event for event in events if event["message"] in {"HTTP error", "Unhandled exception"})
        assert event["level"] == ("WARNING" if status == 400 else "ERROR")
        assert event["path"] == "/translated/{item_id}"
        metadata = event["exception"]
        assert metadata["type"] == ("RuntimeError" if status == 500 else "HTTPException")
        if status != 500:
            assert metadata["status_code"] == status
        assert [cause["type"] for cause in metadata["causes"]] == ["ProviderFailure", "OSError"]
        assert metadata["causes"][0]["status_code"] == 502
        assert metadata["causes"][0]["http_status"] == 502
        root = metadata["root_cause"]
        assert root == metadata["causes"][-1]
        assert root["type"] == "OSError"
        assert root["errno"] == 5
        assert root["status"] == 504
        assert root["frames_truncated"] is True
        assert len(root["frames"]) == 12
        assert root["frames"][-1] == {
            "function": "innermost_failure",
            "line": innermost_failure.__code__.co_firstlineno + 1,
        }
        assert not ({"causes_truncated", "cause_cycle", "traceback_truncated"} & set(metadata))
        assert not ({"message", "detail", "source", "locals", "filename", "chain"} & set(root))


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 503, None])
async def test_main_handlers_capture_passed_exception_outside_except(configured_logging, status):
    stream, directory = configured_logging()
    failure = (
        RuntimeError("passed-exception-secret") if status is None else HTTPException(status, "passed-exception-secret")
    )

    def passed_failure():
        raise failure

    try:
        passed_failure()
    except Exception as caught:
        error = caught
    assert sys.exc_info() == (None, None, None)
    request = Request({"type": "http", "method": "GET", "path": "/outside"})
    handler = unhandled_exception_handler if status is None else sanitized_http_exception_handler
    response = await handler(request, error)
    assert response.status_code == (500 if status is None else status)
    for output in (stream.getvalue(), "".join(path.read_text() for path in directory.glob("backend-*.log"))):
        assert "passed-exception-secret" not in output
        event = next(json.loads(line) for line in output.splitlines() if '"exception":' in line)
        assert event["exception"]["type"] == type(error).__name__
        assert event["exception"]["frames"][-1]["function"] == "passed_failure"


def test_exception_numeric_metadata_uses_only_bounded_plain_ints(configured_logging):
    stream, directory = configured_logging()

    class OpaqueNumber:
        def __str__(self):
            pytest.fail("exception metadata must not stringify values")

        __repr__ = __str__
        __int__ = __str__
        __index__ = __str__

    class CredentialNumber(int):
        __str__ = OpaqueNumber.__str__
        __repr__ = OpaqueNumber.__str__

    class ProviderFailure(Exception):
        def __str__(self):
            pytest.fail("exception text must not be rendered")

    keys = ("status_code", "http_status", "status", "errno")
    cases = [
        (100, set(keys)),
        (599, set(keys)),
        (0, {"errno"}),
        (600, {"errno"}),
        (-(2**31), {"errno"}),
        (2**31 - 1, {"errno"}),
        (-(2**31) - 1, set()),
        (2**31, set()),
        (10**100, set()),
        (True, set()),
        (False, set()),
        (503.0, set()),
        ("503", set()),
        ("numeric-credential-must-not-appear", set()),
        (CredentialNumber(503), set()),
        (OpaqueNumber(), set()),
        (None, set()),
    ]
    logger = logging.getLogger("app.main")
    for index, (value, _) in enumerate(cases):
        error = ProviderFailure("numeric-credential-must-not-appear")
        for key in keys:
            setattr(error, key, value)
        logger.error("numeric failure", extra={"case": index}, exc_info=(type(error), error, None))

    class PropertyFailure(Exception):
        @property
        def status_code(self):
            pytest.fail("exception metadata must not evaluate provider properties")

        http_status = status_code
        status = status_code
        errno = status_code

    error = PropertyFailure()
    logger.error("property failure", exc_info=(type(error), error, None))
    for output in (stream.getvalue(), "".join(path.read_text() for path in directory.glob("backend-*.log"))):
        assert "numeric-credential-must-not-appear" not in output
        events = [json.loads(line) for line in output.splitlines()]
        numeric_events = [event for event in events if event["message"] == "numeric failure"]
        assert len(numeric_events) == len(cases)
        for event in numeric_events:
            value, expected_keys = cases[event["case"]]
            metadata = event["exception"]
            assert set(metadata) & set(keys) == expected_keys
            assert all(metadata[key] == value and type(metadata[key]) is int for key in expected_keys)
            assert metadata["root_cause"] == {
                key: item for key, item in metadata.items() if key not in {"causes", "root_cause"}
            }
        property_event = next(event for event in events if event["message"] == "property failure")
        assert not (set(property_event["exception"]) & set(keys))


@pytest.mark.parametrize("link", ["__cause__", "__context__"])
@pytest.mark.parametrize("length", [1, 2])
def test_exception_cycles_are_bounded_without_claiming_a_root(configured_logging, link, length):
    stream, directory = configured_logging()
    errors = [RuntimeError("cycle-credential-must-not-appear") for _ in range(length)]
    for index, error in enumerate(errors):
        setattr(error, link, errors[(index + 1) % length])
        error.__suppress_context__ = True
    logging.getLogger("app.main").error("cyclic failure", exc_info=(type(errors[0]), errors[0], None))
    for output in (stream.getvalue(), "".join(path.read_text() for path in directory.glob("backend-*.log"))):
        assert "cycle-credential-must-not-appear" not in output
        event = next(json.loads(line) for line in output.splitlines() if "cyclic failure" in line)
        metadata = event["exception"]
        assert metadata["cause_cycle"] is True
        assert metadata["root_cause"] is None
        assert len(metadata["causes"]) == length - 1
        assert "causes_truncated" not in metadata
    for error in errors:
        setattr(error, link, None)


@pytest.mark.parametrize("cause_count", [0, 8, 9, 100])
def test_exception_chain_limits_and_explicit_cause_precedence(configured_logging, cause_count):
    stream, directory = configured_logging()
    error = RuntimeError("chain-credential-must-not-appear")
    current = error
    for _ in range(cause_count):
        current.__cause__ = ValueError("chain-credential-must-not-appear")
        current.__context__ = TypeError("ignored-context-credential-must-not-appear")
        current = current.__cause__
    logging.getLogger("app.main").error("long chain failure", exc_info=(type(error), error, None))
    for output in (stream.getvalue(), "".join(path.read_text() for path in directory.glob("backend-*.log"))):
        assert "credential-must-not-appear" not in output
        event = next(json.loads(line) for line in output.splitlines() if "long chain failure" in line)
        metadata = event["exception"]
        assert len(metadata["causes"]) == min(cause_count, 8)
        assert all(cause["type"] == "ValueError" for cause in metadata["causes"])
        assert metadata.get("causes_truncated", False) is (cause_count > 8)
        if cause_count > 8:
            assert metadata["root_cause"] is None
        else:
            assert metadata["root_cause"]["type"] == ("ValueError" if cause_count else "RuntimeError")


def test_exception_traceback_scan_and_names_are_bounded(configured_logging):
    stream, directory = configured_logging()
    error_type = type("Provider" + "x" * 1000, (Exception,), {})
    error = error_type("traceback-credential-must-not-appear")
    try:
        raise error
    except Exception as caught:
        tb = caught.__traceback__
    for _ in range(1024):
        tb = TracebackType(tb, tb.tb_frame, tb.tb_lasti, tb.tb_lineno)
    logging.getLogger("app.main").error("scan limited failure", exc_info=(type(error), error, tb))
    for output in (stream.getvalue(), "".join(path.read_text() for path in directory.glob("backend-*.log"))):
        assert "traceback-credential-must-not-appear" not in output
        event = next(json.loads(line) for line in output.splitlines() if "scan limited failure" in line)
        metadata = event["exception"]
        assert len(metadata["type"]) == 128
        assert len(metadata["frames"]) == 12
        assert metadata["frames_truncated"] is True
        assert metadata["traceback_truncated"] is True
        assert metadata["root_cause"]["traceback_truncated"] is True


def test_pytest_file_destination_is_separate_and_metadata_is_safe(configured_logging, tmp_path, monkeypatch):
    secret = "runtime-secret-must-not-appear"
    monkeypatch.setattr(sys, "argv", ["pytest", "--password", secret])
    monkeypatch.setenv("PYTEST_CURRENT_TEST", secret)
    monkeypatch.setenv("AFTERGLOW_ENV", secret)
    stream, directory = configured_logging()
    logging.getLogger("app.main").warning("consumer failure", extra={"source": secret, "runtime": secret})
    assert directory == tmp_path / "logs" / "pytest" / str(os.getpid())
    assert not list((tmp_path / "logs").glob("backend-*.log"))
    for output in (stream.getvalue(), "".join(path.read_text() for path in directory.glob("backend-*.log"))):
        assert secret not in output
        event = next(json.loads(line) for line in output.splitlines() if "consumer failure" in line)
        assert event["source"]["origin"] == "test"
        assert event["source"]["function"] == "test_pytest_file_destination_is_separate_and_metadata_is_safe"
        assert event["source"]["line"] > 0
        assert event["process"] == {"pid": os.getpid()}
        assert event["runtime"]["environment"] == "other"
        assert event["runtime"]["file_scope"] == "pytest"
        assert event["runtime"]["entrypoint"] == "api"
        assert set(event["runtime"]) == {"environment", "python", "implementation", "file_scope", "entrypoint"}


def test_normal_file_destination_preserves_configured_directory(tmp_path, monkeypatch):
    from app.utils.log import log_file_directory

    with monkeypatch.context() as context:
        context.delitem(sys.modules, "pytest")
        assert log_file_directory(str(tmp_path)) == tmp_path


@pytest.mark.parametrize("namespace", ["aiosqlite", "asyncio", "stevedore"])
def test_dependency_noise_is_bounded_without_hiding_failures(configured_logging, namespace):
    stream, directory = configured_logging(log_level="DEBUG")
    # An explicitly configured child must not bypass the output-handler policy.
    dependency = logging.getLogger(namespace + ".consumer")
    dependency.setLevel(logging.DEBUG)
    dependency.debug("dependency debug containing SQL parameters")
    dependency.info("dependency informational detail")
    dependency.warning("dependency warning remains visible")
    dependency.error("dependency failure remains visible")
    logging.getLogger("app.main").debug("application debug remains visible")
    for output in (stream.getvalue(), "".join(path.read_text() for path in directory.glob("backend-*.log"))):
        messages = [json.loads(line)["message"] for line in output.splitlines()]
        assert "dependency debug containing SQL parameters" not in messages
        assert "dependency informational detail" not in messages
        assert "dependency warning remains visible" in messages
        assert "dependency failure remains visible" in messages
        assert "application debug remains visible" in messages


@pytest.mark.parametrize("code", [1054, 1146, 2003, 1000, 4999])
def test_mysql_error_codes_survive_without_sql_or_driver_text(configured_logging, code):
    from pymysql.err import OperationalError
    from sqlalchemy.exc import OperationalError as SQLAlchemyOperationalError

    stream, directory = configured_logging()
    secret = "database-secret-must-not-appear"
    driver = OperationalError(code, secret)
    wrapper = SQLAlchemyOperationalError("SELECT " + secret, {"password": secret}, driver)
    logger = logging.getLogger("app.main")
    for error in (driver, wrapper):
        logger.error("database operation failed", exc_info=(type(error), error, None))
    for output in (stream.getvalue(), "".join(path.read_text() for path in directory.glob("backend-*.log"))):
        assert secret not in output
        events = [json.loads(line) for line in output.splitlines() if "database operation failed" in line]
        assert len(events) == 2
        assert all(event["exception"]["error_code"] == code for event in events)


def test_mysql_error_code_rejects_unsupported_values_and_properties(configured_logging):
    from pymysql.err import OperationalError
    from sqlalchemy.exc import OperationalError as SQLAlchemyOperationalError

    stream, directory = configured_logging()
    secret = "unsupported-database-secret"

    class IntSubclass(int):
        def __str__(self):
            pytest.fail("numeric driver values must not be converted")

    class PropertyWrapper(SQLAlchemyOperationalError):
        @property
        def orig(self):
            pytest.fail("driver metadata must not evaluate orig properties")

    error = PropertyWrapper.__new__(PropertyWrapper)
    BaseException.__init__(error, secret)
    cases = [
        RuntimeError(1054, secret),
        SQLAlchemyOperationalError("SELECT " + secret, {"password": secret}, RuntimeError(1054, secret)),
        OperationalError(True, secret),
        OperationalError(IntSubclass(1054), secret),
        OperationalError("1054", secret),
        OperationalError(999, secret),
        OperationalError(5000, secret),
        error,
    ]
    logger = logging.getLogger("app.main")
    for case in cases:
        logger.error("unsupported database failure", exc_info=(type(case), case, None))
    for output in (stream.getvalue(), "".join(path.read_text() for path in directory.glob("backend-*.log"))):
        assert secret not in output
        events = [json.loads(line) for line in output.splitlines() if "unsupported database failure" in line]
        assert len(events) == len(cases)
        assert all("error_code" not in event["exception"] for event in events)


@pytest.mark.parametrize(
    ("field", "value"),
    [(field, value) for field, values in DIAGNOSTIC_LOG_FIELDS.items() for value in sorted(values)],
)
def test_finite_diagnostic_fields_survive_both_json_output_paths(configured_logging, field, value):
    stream, directory = configured_logging()
    secret = "closed-diagnostic-secret-must-not-appear"
    record = logging.LogRecord(
        "app.main", logging.WARNING, __file__, 1, "closed diagnostic password=" + secret, (), None
    )
    record.__dict__[field] = value
    direct = json.loads(JSONFormatter().format(record))
    assert direct[field] == value
    assert secret not in json.dumps(direct)
    logging.getLogger("app.main").warning(
        "closed diagnostic password=%s", secret, extra={field: value, "password": secret}
    )
    for output in (stream.getvalue(), "".join(path.read_text() for path in directory.glob("backend-*.log"))):
        assert secret not in output
        event = next(json.loads(line) for line in output.splitlines() if "closed diagnostic" in line)
        assert event[field] == value
        assert event["password"] == "***"


@pytest.mark.parametrize("field", sorted(DIAGNOSTIC_LOG_FIELDS))
@pytest.mark.parametrize("bad_kind", ["unknown", "credential", "subclass", "object", "integer", "mapping"])
def test_unknown_diagnostic_values_are_omitted_without_conversion(configured_logging, field, bad_kind):
    stream, directory = configured_logging()
    secret = "unadmitted-diagnostic-secret"

    class HostileString(str):
        def __str__(self):
            pytest.fail("diagnostic string subclasses must not be converted")

        def __hash__(self):
            pytest.fail("diagnostic string subclasses must not be hashed")

        def __eq__(self, other):
            pytest.fail("diagnostic string subclasses must not be compared")

    class Opaque:
        def __str__(self):
            pytest.fail("diagnostic objects must not be converted")

    value = {
        "unknown": "new_unreviewed_reason",
        "credential": secret,
        "subclass": HostileString(next(iter(DIAGNOSTIC_LOG_FIELDS[field]))),
        "object": Opaque(),
        "integer": 1054,
        "mapping": {"password": secret},
    }[bad_kind]
    record = logging.LogRecord("app.main", logging.WARNING, __file__, 1, "unadmitted diagnostic", (), None)
    record.__dict__[field] = value
    direct = json.loads(JSONFormatter().format(record))
    assert field not in direct
    assert secret not in json.dumps(direct)
    logging.getLogger("app.main").warning("unadmitted diagnostic", extra={field: value})
    for output in (stream.getvalue(), "".join(path.read_text() for path in directory.glob("backend-*.log"))):
        assert secret not in output
        event = next(json.loads(line) for line in output.splitlines() if "unadmitted diagnostic" in line)
        assert field not in event


def test_diagnostic_vocabulary_covers_oauth_enum_and_health_default():
    from app.services.instance_health import HealthStoreUnavailable
    from app.services.mcp_control_plane.oauth_authority import McpOAuthFailureReason

    assert {reason.value for reason in McpOAuthFailureReason} <= DIAGNOSTIC_LOG_FIELDS["diagnostic_reason"]
    assert HealthStoreUnavailable().reason in DIAGNOSTIC_LOG_FIELDS["diagnostic_reason"]


def test_diagnostic_vocabulary_covers_actual_traffic_classifier_and_stage_outputs(configured_logging, monkeypatch):
    import time
    from typing import get_args, get_type_hints

    from app.services import traffic_analytics as traffic

    stream, directory = configured_logging()
    monkeypatch.setattr(traffic, "_failure_log_at", {})
    secret = "producer-diagnostic-secret-must-not-appear"
    errors = [
        TimeoutError(secret),
        traffic.RedisTimeoutError(secret),
        ConnectionError(secret),
        OSError(secret),
        traffic.RedisConnectionError(secret),
        traffic.MaxConnectionsError(secret),
        traffic.OutOfMemoryError(secret),
        traffic.AuthenticationError(secret),
        traffic.AuthorizationError(secret),
        traffic.ResponseError(secret),
        RuntimeError(secret),
    ]
    reasons = {traffic._failure_reason(error) for error in errors}
    assert reasons <= DIAGNOSTIC_LOG_FIELDS["failure_reason"]
    producer_types = get_type_hints(traffic._log_failure)
    sources = get_args(producer_types["source"])
    stages = get_args(producer_types["stage"])
    assert sources and stages
    assert set(sources) <= DIAGNOSTIC_LOG_FIELDS["traffic_source"]
    assert set(stages) <= DIAGNOSTIC_LOG_FIELDS["failure_stage"]
    for source in sources:
        for stage in stages:
            for reason in reasons:
                traffic._log_failure(source, stage, reason, time.monotonic())
    for output in (stream.getvalue(), "".join(path.read_text() for path in directory.glob("backend-*.log"))):
        assert secret not in output
        events = [json.loads(line) for line in output.splitlines()]
        events = [event for event in events if event["logger"] == traffic.__name__]
        assert len(events) == len(sources) * len(stages) * len(reasons)
        for event in events:
            assert event["traffic_source"] in sources
            assert event["failure_stage"] in stages
            assert event["failure_reason"] in reasons
            assert event["stage_scope"] in DIAGNOSTIC_LOG_FIELDS["stage_scope"]


@pytest.mark.parametrize(
    ("entrypoint", "expected"),
    [
        ("api", "api"),
        ("worker", "worker"),
        ("unknown", "unknown"),
        ("private-entrypoint-secret", "unknown"),
        (None, "unknown"),
    ],
)
def test_formatter_entrypoint_is_explicit_and_closed(entrypoint, expected, monkeypatch):
    secret = "private-entrypoint-secret"
    monkeypatch.setenv("AFTERGLOW_ENTRYPOINT", secret)
    monkeypatch.setattr(sys, "argv", ["worker", secret])
    record = logging.LogRecord("app.test", logging.INFO, __file__, 1, "runtime classification", (), None)
    payload = JSONFormatter(entrypoint=entrypoint).format(record)
    assert json.loads(payload)["runtime"]["entrypoint"] == expected
    assert json.loads(JSONFormatter().format(record))["runtime"]["entrypoint"] == "unknown"
    assert secret not in payload


def test_importing_worker_preserves_api_handlers_audit_and_runtime(configured_logging):
    import importlib.util

    from app import notion_worker
    from app.services.activity import _audit_ctx
    from app.utils.auth_diagnostics import RequestDiagnosticHandler

    stream, directory = configured_logging()
    root = logging.getLogger()
    handlers = root.handlers[:]
    previous_level = root.level
    assert any(isinstance(handler, RequestDiagnosticHandler) for handler in handlers)
    # Execute the module's import boundary in a separate namespace: no reload of
    # shared worker globals, no CLI startup, and no business task execution.
    spec = importlib.util.spec_from_file_location("worker_import_probe", notion_worker.__file__)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert root.handlers == handlers
    assert root.level == previous_level
    holder = {"stages": []}
    context = _audit_ctx.set(holder)
    try:
        logging.getLogger("app.services.import_probe").warning("api import diagnostic")
    finally:
        _audit_ctx.reset(context)
    assert any(item["stage"] == "application_warning" for _, item in holder["stages"])
    for output in (stream.getvalue(), "".join(path.read_text() for path in directory.glob("backend-*.log"))):
        event = next(json.loads(line) for line in output.splitlines() if "api import diagnostic" in line)
        assert event["runtime"]["entrypoint"] == "api"
