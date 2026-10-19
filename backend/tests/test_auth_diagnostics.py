"""Real auth boundaries must emit useful diagnostics without retaining request secrets."""

from __future__ import annotations

import asyncio
import io
import json
import logging
import math
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID

import pytest
from fastapi import APIRouter, FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from keystoneauth1.exceptions.http import Unauthorized

from app import config
from app.api.identity import auth
from app.api.identity import domain_auth as domain_routes
from app.main import _setup_logging, app
from app.models.auth import LoginRequest
from app.services.domain_auth import DomainAuthDenied
from app.utils.auth_diagnostics import authentication_operation, authentication_step

_BODY_SECRET = "body-credential-never-log-74ed"
_QUERY_SECRET = "query-credential-never-log-27ab"
_HEADER_SECRET = "header-credential-never-log-9abc"
_CAUSE_SECRET = "cause-credential-never-log-f134"
_NATIVE_SECRET = "native-credential-never-log-a783"
_CLIENT_CORRELATION = "11111111111141118111111111111111"
_SECRETS = (_BODY_SECRET, _QUERY_SECRET, _HEADER_SECRET, _CAUSE_SECRET, _NATIVE_SECRET, _CLIENT_CORRELATION)


@pytest.fixture
def diagnostic_logging(tmp_path, monkeypatch):
    """Exercise production handlers/filter/formatter without leaking logging state."""
    root = logging.getLogger()
    previous_handlers = root.handlers[:]
    previous_level = root.level
    previous_disable = root.manager.disable
    previous_loggers = {
        name: (logger.level, logger.handlers[:], logger.propagate, logger.disabled)
        for name, logger in root.manager.loggerDict.copy().items()
        if isinstance(logger, logging.Logger)
    }
    stream = io.StringIO()
    directory = tmp_path / "auth-logs"
    settings = config.get_settings()

    def configure(*, debug=True):
        logging.disable(logging.NOTSET)
        for name, logger in root.manager.loggerDict.copy().items():
            if isinstance(logger, logging.Logger) and (name == "app" or name.startswith("app.")):
                logger.setLevel(logging.NOTSET)
                logger.handlers[:] = []
                logger.propagate = True
                logger.disabled = False
        isolated = settings.model_copy(update={"debug": debug, "log_level": "INFO", "log_directory": str(directory)})
        monkeypatch.setattr("sys.stderr", stream)
        with patch.object(config, "get_settings", return_value=isolated):
            _setup_logging()

        def outputs():
            for handler in root.handlers:
                handler.flush()
            files = sorted(directory.glob("backend-*.log"))
            assert files, "The production file handler must emit an actual log file"
            return (stream.getvalue(), "".join(path.read_text(encoding="utf-8") for path in files))

        return outputs

    try:
        yield configure
    finally:
        for handler in root.handlers:
            if handler not in previous_handlers:
                handler.close()
        root.handlers[:] = previous_handlers
        root.setLevel(previous_level)
        logging.disable(previous_disable)
        for name, logger in root.manager.loggerDict.copy().items():
            if not isinstance(logger, logging.Logger):
                continue
            level, handlers, propagate, disabled = previous_loggers.get(name, (logging.NOTSET, [], True, False))
            logger.setLevel(level)
            logger.handlers[:] = handlers
            logger.propagate = propagate
            logger.disabled = disabled


def _events(output):
    for secret in _SECRETS:
        assert secret not in output
    return [json.loads(line) for line in output.splitlines()]


def _diagnostics(events):
    rows = [event for event in events if event["logger"] == "app.utils.auth_diagnostics"]
    assert rows
    for row in rows:
        assert row["auth_operation"]
        assert row["auth_stage"]
        correlation = row["auth_correlation"]
        assert isinstance(correlation, str) and UUID(hex=correlation).hex == correlation
        assert correlation != _CLIENT_CORRELATION
        assert row["outcome"] in {"start", "complete", "failure"}
        assert not ({"body", "query", "headers", "url", "input", "locals"} & row.keys())
        if row["outcome"] == "start":
            assert row["level"] == "DEBUG"
            assert "duration_ms" not in row
        else:
            duration = row["duration_ms"]
            assert isinstance(duration, (int, float)) and not isinstance(duration, bool)
            assert math.isfinite(duration) and duration >= 0
        if row["outcome"] == "failure":
            assert row["level"] == "WARNING"
            assert row["exception"]["type"]
            assert row["exception"]["frames"]
            assert all(set(frame) == {"function", "line"} for frame in row["exception"]["frames"])
        elif row["outcome"] == "complete":
            assert row["level"] == "DEBUG"
            assert "exception" not in row
    return rows


def _assert_no_store(response):
    assert response.headers["cache-control"] == "no-store, private"
    assert response.headers["pragma"] == "no-cache"


def _request_headers():
    return {
        "Authorization": f"Bearer {_HEADER_SECRET}",
        "Cookie": f"credential={_HEADER_SECRET}",
        "User-Agent": _HEADER_SECRET,
        "X-Request-ID": _CLIENT_CORRELATION,
        "X-Correlation-ID": _CLIENT_CORRELATION,
        "Traceparent": f"00-{_CLIENT_CORRELATION}-1111111111111111-01",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["http", "domain", "validation"])
async def test_auth_route_handled_failures_preserve_response_and_log_exception(diagnostic_logging, failure):
    outputs = diagnostic_logging()
    api = FastAPI()
    router = APIRouter(route_class=auth.AuthRoute)

    @router.post("/login")
    async def login(req: LoginRequest):
        try:
            raise RuntimeError(_CAUSE_SECRET)
        except RuntimeError as cause:
            if failure == "http":
                raise HTTPException(401, "Rejected credentials", headers={"WWW-Authenticate": "Bearer"}) from cause
            raise DomainAuthDenied("Domain policy rejected login", code="policy_denied") from cause

    api.include_router(router, prefix="/auth")
    body = {"username": _BODY_SECRET, "password": _BODY_SECRET}
    if failure == "validation":
        body["username"] = [_BODY_SECRET]
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
        response = await client.post(f"/auth/login?credential={_QUERY_SECRET}", json=body, headers=_request_headers())

    expected = {
        "http": (401, {"detail": "Rejected credentials"}, "HTTPException"),
        "domain": (403, {"detail": "Domain policy rejected login", "code": "policy_denied"}, "DomainAuthDenied"),
        "validation": (422, {"detail": "Invalid authentication input"}, "RequestValidationError"),
    }
    status, payload, exception_type = expected[failure]
    assert response.status_code == status
    assert response.json() == payload
    if failure == "http":
        assert response.headers["www-authenticate"] == "Bearer"
    _assert_no_store(response)
    for output in outputs():
        rows = _diagnostics(_events(output))
        failures = [row for row in rows if row["auth_stage"] == "request" and row["outcome"] == "failure"]
        assert failures
        assert all(row["auth_operation"] == "login" for row in rows)
        assert any(row["exception"]["type"] == exception_type for row in failures)
        assert len({row["auth_correlation"] for row in rows}) == 1
        assert not any(row["auth_stage"] == "request" and row["outcome"] == "complete" for row in rows)


@pytest.fixture
async def login_boundaries(monkeypatch, auth_directory, native_auth):
    """Keep canonical account lookup, native validation, JWT and session logic real."""
    auth_directory.users[native_auth.user_id].update(name=_BODY_SECRET, default_project_id="test-project-123")
    native_auth.token = _NATIVE_SECRET
    native_auth.password = _BODY_SECRET
    directory = auth.keystone._get_admin_ks_client()
    global_users = Mock(wraps=directory.users.list)
    home_reads = Mock(wraps=directory.domains.get)
    monkeypatch.setattr(directory.users, "list", global_users)
    monkeypatch.setattr(directory.domains, "get", home_reads)
    monkeypatch.setattr(auth.login_guard, "check_locked", AsyncMock())
    monkeypatch.setattr(auth.login_guard, "record_failure", AsyncMock())
    monkeypatch.setattr(auth.login_guard, "record_success", AsyncMock())
    monkeypatch.setattr(auth, "_prewarm_dashboard", AsyncMock())
    monkeypatch.setattr(auth, "record_project_access", AsyncMock())
    monkeypatch.setattr(auth.activity_svc, "record", AsyncMock())
    monkeypatch.setenv("TOKEN_IP_BINDING_MODE", "off")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield SimpleNamespace(
            client=client, native=native_auth, directory=directory, global_users=global_users, home_reads=home_reads
        )


async def _login(client):
    return await client.post(
        f"/api/v1/auth/login?credential={_QUERY_SECRET}",
        json={"username": _BODY_SECRET, "password": _BODY_SECRET},
        headers=_request_headers(),
    )


@pytest.mark.asyncio
async def test_real_login_success_emits_stage_durations_and_server_correlation(diagnostic_logging, login_boundaries):
    outputs = diagnostic_logging()
    first = await _login(login_boundaries.client)
    second = await _login(login_boundaries.client)
    for response in (first, second):
        assert response.status_code == 200
        payload = response.json()
        assert payload["user_id"] == "test-user-123"
        assert payload["project_id"] == "test-project-123"
        assert payload["token"].count(".") == 2
        assert payload["refresh_token"].count(".") == 2
        _assert_no_store(response)
    assert any(not call.args and not call.kwargs for call in login_boundaries.global_users.call_args_list)
    assert any(call.args == ("default",) for call in login_boundaries.home_reads.call_args_list)
    for output in outputs():
        rows = _diagnostics(_events(output))
        assert all(row["auth_operation"] == "login" for row in rows)
        completed = [row for row in rows if row["outcome"] == "complete"]
        expected_stages = {
            "request",
            "resolve",
            "authenticate",
            "domain_preparation",
            "native_exchange",
            "session_publication",
        }
        correlations = {row["auth_correlation"] for row in rows}
        assert len(correlations) == 2
        for correlation in correlations:
            stages = {row["auth_stage"] for row in completed if row["auth_correlation"] == correlation}
            assert expected_stages <= stages
        assert not any(row["outcome"] == "failure" for row in rows)


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["global_inventory", "exact_user", "exact_home"])
async def test_login_directory_failures_are_logged_without_password_attempt(
    diagnostic_logging, login_boundaries, monkeypatch, boundary
):
    outputs = diagnostic_logging()

    def unavailable(*args, **kwargs):
        raise ConnectionError(_CAUSE_SECRET)

    directory = login_boundaries.directory
    manager, method = {
        "global_inventory": (directory.users, "list"),
        "exact_user": (directory.users, "get"),
        "exact_home": (directory.domains, "get"),
    }[boundary]
    monkeypatch.setattr(manager, method, unavailable)
    response = await _login(login_boundaries.client)
    assert response.status_code == 503
    assert "token" not in response.json() and "refresh_token" not in response.json()
    assert _CAUSE_SECRET not in response.text
    _assert_no_store(response)
    login_boundaries.native.password_exchange.assert_not_called()
    login_boundaries.native.token_exchange.assert_not_called()
    for output in outputs():
        rows = _diagnostics(_events(output))
        assert all(row["auth_operation"] == "login" for row in rows)
        assert any(row["auth_stage"] == "resolve" and row["outcome"] == "failure" for row in rows)
        assert any(row["auth_stage"] == "request" and row["outcome"] == "failure" for row in rows)
        assert not any(row["auth_stage"] == "authenticate" for row in rows)


@pytest.mark.asyncio
async def test_info_level_real_login_failure_retains_structural_warning(diagnostic_logging, login_boundaries):
    outputs = diagnostic_logging(debug=False)

    def reject(**kwargs):
        try:
            raise RuntimeError(_CAUSE_SECRET)
        except RuntimeError as cause:
            raise Unauthorized(_BODY_SECRET) from cause

    login_boundaries.native.password_exchange.side_effect = reject
    response = await _login(login_boundaries.client)
    assert response.status_code == 401
    login_boundaries.native.password_exchange.assert_called_once()
    login_boundaries.native.token_exchange.assert_not_called()
    assert response.json() == {"detail": "인증 실패"}
    _assert_no_store(response)
    for output in outputs():
        rows = _diagnostics(_events(output))
        assert all(row["outcome"] == "failure" and row["level"] == "WARNING" for row in rows)
        authentication_failures = [row for row in rows if row["auth_stage"] == "authenticate"]
        assert authentication_failures
        assert all(row["exception"]["type"] == "PasswordRejected" for row in authentication_failures)
        assert any(
            any(cause["type"] == "Unauthorized" for cause in row["exception"]["causes"])
            for row in authentication_failures
        )
        assert any(row["exception"]["root_cause"]["type"] == "RuntimeError" for row in authentication_failures)
        assert any(
            row["auth_stage"] == "request"
            and row["exception"]["type"] == "HTTPException"
            and any(cause["type"] == "PasswordRejected" for cause in row["exception"]["causes"])
            for row in rows
        )
        assert all(row["auth_operation"] == "login" for row in rows)
        assert len({row["auth_correlation"] for row in rows}) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["native_exchange", "session_publication"])
async def test_real_login_translated_failures_keep_stage_and_no_store(
    diagnostic_logging, login_boundaries, monkeypatch, boundary
):
    outputs = diagnostic_logging()

    def unavailable(*args, **kwargs):
        try:
            raise ValueError(_CAUSE_SECRET)
        except ValueError as cause:
            raise RuntimeError(_NATIVE_SECRET) from cause

    if boundary == "native_exchange":
        native_token_access = login_boundaries.native.token_exchange.side_effect

        def unavailable_project(**kwargs):
            # Root-token validation during project inventory must succeed; fail
            # only the selected project's exchange at the intended boundary.
            if kwargs.get("project_id"):
                return unavailable(**kwargs)
            return native_token_access(**kwargs)

        login_boundaries.native.token_exchange.side_effect = unavailable_project
    else:
        monkeypatch.setattr(auth.session_store, "store_session", AsyncMock(side_effect=unavailable))
    response = await _login(login_boundaries.client)
    assert response.status_code == 503
    if boundary == "native_exchange":
        assert any(
            call.kwargs.get("project_id") == "test-project-123"
            for call in login_boundaries.native.token_exchange.call_args_list
        )
    expected_detail = {
        "native_exchange": "Native session exchange is unavailable",
        "session_publication": "Session publication is unavailable",
    }
    assert response.json() == {"detail": expected_detail[boundary]}
    _assert_no_store(response)
    assert _NATIVE_SECRET not in response.text
    assert _CAUSE_SECRET not in response.text
    for output in outputs():
        rows = _diagnostics(_events(output))
        failed = [row for row in rows if row["outcome"] == "failure"]
        assert any(row["auth_stage"] == boundary for row in failed)
        assert any(
            row["exception"]["type"] == "HTTPException" and row["exception"]["root_cause"]["type"] == "ValueError"
            for row in failed
            if row["auth_stage"] == boundary
        )
        assert any(row["auth_stage"] == "request" for row in failed)
        assert all(row["auth_operation"] == "login" for row in rows)
        assert len({row["auth_correlation"] for row in rows}) == 1


@pytest.mark.asyncio
async def test_native_exchange_preserves_rejection_translation_with_diagnostics(diagnostic_logging, monkeypatch):
    outputs = diagnostic_logging()

    def rejected(*args, **kwargs):
        raise Unauthorized(_NATIVE_SECRET)

    monkeypatch.setattr(auth.keystone, "validate_token", rejected)
    with authentication_operation("refresh_token"):
        with pytest.raises(HTTPException) as failure:
            await auth._exchange_native_scope(_NATIVE_SECRET, "test-project-123")
    assert failure.value.status_code == 401
    assert isinstance(failure.value.__cause__, Unauthorized)
    for output in outputs():
        rows = _diagnostics(_events(output))
        assert any(row["auth_stage"] == "native_exchange" and row["outcome"] == "failure" for row in rows)
        assert all(row["auth_operation"] == "refresh_token" for row in rows)


@pytest.mark.asyncio
async def test_refresh_validation_uses_endpoint_operation_not_path_or_client_ids(diagnostic_logging):
    outputs = diagnostic_logging()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/auth/refresh?credential={_QUERY_SECRET}",
            json={"refresh_token": [_BODY_SECRET]},
            headers=_request_headers(),
        )
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid authentication input"}
    _assert_no_store(response)
    for output in outputs():
        rows = _diagnostics(_events(output))
        assert all(row["auth_operation"] == "refresh_token" for row in rows)
        assert any(row["auth_stage"] == "request" and row["outcome"] == "failure" for row in rows)


@pytest.mark.asyncio
async def test_nested_thread_and_parallel_operations_preserve_and_reset_context(diagnostic_logging):
    outputs = diagnostic_logging()
    first_started = asyncio.Event()
    release_first = asyncio.Event()

    def native_stage():
        with authentication_step("native_exchange"):
            return None

    async def login_operation():
        with authentication_operation("login"), authentication_step("request"):
            first_started.set()
            await release_first.wait()
            await asyncio.to_thread(native_stage)
            with authentication_operation("refresh_token"), authentication_step("session_publication"):
                pass
            with authentication_step("domain_preparation"):
                pass

    async def refresh_operation():
        await first_started.wait()
        try:
            with authentication_operation("refresh_token"), authentication_step("request"):
                await asyncio.to_thread(native_stage)
        finally:
            release_first.set()

    await asyncio.gather(login_operation(), refresh_operation())
    with authentication_operation("logout"), authentication_step("request"):
        pass
    for output in outputs():
        rows = _diagnostics(_events(output))
        by_operation = {
            operation: {row["auth_correlation"] for row in rows if row["auth_operation"] == operation}
            for operation in ("login", "refresh_token", "logout")
        }
        assert len(by_operation["login"]) == len(by_operation["logout"]) == 1
        assert len(by_operation["refresh_token"]) == 2
        assert by_operation["login"].isdisjoint(by_operation["refresh_token"] | by_operation["logout"])
        assert by_operation["refresh_token"].isdisjoint(by_operation["logout"])
        for operation in ("login", "refresh_token"):
            assert any(row["auth_operation"] == operation and row["auth_stage"] == "native_exchange" for row in rows)
        restored = [row for row in rows if row["auth_stage"] == "domain_preparation"]
        assert restored and all(row["auth_correlation"] in by_operation["login"] for row in restored)


@pytest.mark.asyncio
async def test_cancelled_operation_logs_failure_and_does_not_contaminate_next_operation(diagnostic_logging):
    outputs = diagnostic_logging()
    cancelled = asyncio.CancelledError(_CAUSE_SECRET)
    with pytest.raises(asyncio.CancelledError) as failure:
        with authentication_operation("login"), authentication_step("request"):
            raise cancelled
    assert failure.value is cancelled
    with authentication_step("resolve"):
        pass
    with authentication_step("authenticate"):
        pass
    with authentication_operation("refresh_token"), authentication_step("request"):
        pass
    for output in outputs():
        rows = _diagnostics(_events(output))
        failed = [row for row in rows if row["outcome"] == "failure"]
        assert any(row["exception"]["type"] == "CancelledError" for row in failed)
        login_ids = {row["auth_correlation"] for row in rows if row["auth_operation"] == "login"}
        refresh_ids = {row["auth_correlation"] for row in rows if row["auth_operation"] == "refresh_token"}
        assert login_ids.isdisjoint(refresh_ids)
        standalone_ids = {row["auth_correlation"] for row in rows if row["auth_operation"] == "authentication"}
        assert len(standalone_ids) == 2
        assert standalone_ids.isdisjoint(login_ids | refresh_ids)
        assert all(row["outcome"] != "failure" for row in rows if row["auth_operation"] == "authentication")
        assert any(row["auth_operation"] == "refresh_token" and row["outcome"] == "complete" for row in rows)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["validation", "policy"])
async def test_domain_resolution_uses_real_guard_and_safe_failure_stage(diagnostic_logging, monkeypatch, failure):
    outputs = diagnostic_logging(debug=False)

    async def denied(name):
        try:
            raise RuntimeError(_CAUSE_SECRET)
        except RuntimeError as cause:
            raise DomainAuthDenied("Domain policy rejected login", code="policy_denied") from cause

    resolve = AsyncMock(side_effect=denied)
    monkeypatch.setattr(domain_routes.svc, "resolve_login_domain", resolve)
    name = "" if failure == "validation" else _BODY_SECRET
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/auth/domains/resolve",
            params={"name": name, "credential": _QUERY_SECRET},
            headers=_request_headers(),
        )
    if failure == "validation":
        assert response.status_code == 422
        assert response.json() == {"detail": "identity_invalid_input", "code": "identity_invalid_input"}
        resolve.assert_not_awaited()
    else:
        assert response.status_code == 403
        assert response.json() == {"detail": "Domain policy rejected login", "code": "policy_denied"}
        resolve.assert_awaited_once_with(_BODY_SECRET)
    _assert_no_store(response)
    for output in outputs():
        rows = _diagnostics(_events(output))
        assert all(row["auth_operation"] == "resolve_domain" and row["outcome"] == "failure" for row in rows)
        assert len({row["auth_correlation"] for row in rows}) == 1
        assert any(row["auth_stage"] == "request" for row in rows)
        if failure == "policy":
            assert any(
                row["auth_stage"] == "domain_resolution" and row["exception"]["root_cause"]["type"] == "RuntimeError"
                for row in rows
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("policy_denied", [False, True])
async def test_federated_login_correlates_sibling_stages_and_handled_policy_failures(
    diagnostic_logging, login_boundaries, monkeypatch, policy_denied
):
    outputs = diagnostic_logging(debug=not policy_denied)
    svc = domain_routes.svc
    settings = config.get_settings().model_copy(
        update={"frontend_base_url": "http://test", "public_api_base": "http://test"}
    )
    monkeypatch.setattr(svc, "get_settings", lambda: settings)
    monkeypatch.setattr(
        svc,
        "complete_authorization",
        AsyncMock(
            return_value=svc.FederatedLogin(
                unscoped_token=_NATIVE_SECRET,
                user_id=login_boundaries.native.user_id,
                username=_BODY_SECRET,
                domain_id="default",
                domain_name="Default",
                provider_id="provider",
                provider_revision=1,
                provider_kind="oidc",
                login_email="actual@example.test",
            )
        ),
    )

    async def require_provider(*args, **kwargs):
        if policy_denied:
            try:
                raise RuntimeError(_CAUSE_SECRET)
            except RuntimeError as cause:
                raise DomainAuthDenied("Federated policy rejected login", code="policy_denied") from cause

    monkeypatch.setattr(svc, "require_provider", require_provider)
    monkeypatch.setattr(svc, "mark_provider_verified", AsyncMock())
    revoked = AsyncMock()
    monkeypatch.setattr(svc, "_revoke_quietly", revoked)
    response = await login_boundaries.client.post(
        f"/api/v1/auth/providers/callback?credential={_QUERY_SECRET}",
        json={"code": _BODY_SECRET, "state": _CLIENT_CORRELATION + _BODY_SECRET},
        headers=_request_headers(),
    )
    _assert_no_store(response)
    assert _NATIVE_SECRET not in response.text
    if policy_denied:
        assert response.status_code == 403
        assert response.json() == {"detail": "Federated policy rejected login", "code": "policy_denied"}
        revoked.assert_awaited_once_with(_NATIVE_SECRET)
    else:
        assert response.status_code == 200
        payload = response.json()
        assert payload["user_id"] == login_boundaries.native.user_id
        assert payload["project_id"] == "test-project-123"
        assert payload["token"].count(".") == 2
        claims = auth.jwt_service.verify_refresh(payload["refresh_token"])
        session = await auth.session_store.get_session(claims["jti"])
        assert session["auth_method"] == "federated"
        assert session["provider_domain_id"] == session["identity_domain_id"] == "default"
        revoked.assert_not_awaited()
    for output in outputs():
        rows = _diagnostics(_events(output))
        assert all(row["auth_operation"] == "provider_callback" for row in rows)
        assert len({row["auth_correlation"] for row in rows}) == 1
        if policy_denied:
            assert any(row["auth_stage"] == "session_policy" for row in rows)
            assert all(row["outcome"] == "failure" for row in rows)
            assert all(row["exception"]["root_cause"]["type"] == "RuntimeError" for row in rows)
        else:
            completed = {row["auth_stage"] for row in rows if row["outcome"] == "complete"}
            assert {
                "request",
                "federated_login",
                "resolve",
                "native_exchange",
                "session_policy",
                "domain_preparation",
                "session_publication",
            } <= completed
            assert not any(row["outcome"] == "failure" for row in rows)
