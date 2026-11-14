"""Saved credential rejection is auth-local and its cache is only advisory."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import fakeredis.aioredis
import pytest
from keystoneauth1.exceptions import connection as keystone_connection
from keystoneauth1.exceptions import http
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import Timeout

from app.services.mcp_control_plane import connection, credential_state


def _failure(kind, chain):
    error = {
        "401": http.Unauthorized,
        "404": http.NotFound,
        "403": http.Forbidden,
        "502": http.BadGateway,
        "connection": ConnectionError,
        "keystone_connection": keystone_connection.ConnectFailure,
        "keystone_timeout": keystone_connection.ConnectTimeout,
        "requests_connection": RequestsConnectionError,
        "timeout": Timeout,
    }[kind]("synthetic-provider-secret")
    if chain != "direct":
        wrapper = RuntimeError("synthetic-wrapper-secret")
        if chain == "cause":
            wrapper.__cause__ = error
        else:
            wrapper.__context__ = error
        return wrapper
    return error


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["401", "404", "403", "502", "timeout"])
@pytest.mark.parametrize("chain", ["direct", "cause", "context"])
async def test_only_application_credential_auth_401_and_404_are_invalid(monkeypatch, kind, chain):
    failure = _failure(kind, chain)
    auth = SimpleNamespace(get_access=Mock(side_effect=failure))
    session = SimpleNamespace(session=SimpleNamespace(close=Mock()))
    monkeypatch.setattr(connection.v3, "ApplicationCredential", lambda **kwargs: auth)
    monkeypatch.setattr(connection.native_transport, "create_session", lambda **kwargs: session)
    monkeypatch.setattr(
        connection, "get_settings", lambda: SimpleNamespace(os_auth_url="https://identity.invalid", ssl_verify=True)
    )
    monkeypatch.setattr(connection, "_load_credential", AsyncMock(return_value=("credential", "synthetic-secret")))
    principal = SimpleNamespace(user_id="user", project_id="project")
    with pytest.raises(connection.McpConsumerConnectionError, match="^MCP cloud connection is unavailable$") as caught:
        async with connection.consumer_connection(principal):
            pytest.fail("Rejected authentication must not yield a connection")
    assert isinstance(caught.value, connection.McpCredentialInvalidError) == (kind in {"401", "404"})
    assert caught.value.__cause__ is failure
    session.session.close.assert_called_once_with()
    assert "secret" not in str(caught.value)


@pytest.mark.asyncio
async def test_resource_404_is_not_credential_rejection(monkeypatch):
    conn = SimpleNamespace(close=Mock())
    monkeypatch.setattr(connection, "_load_credential", AsyncMock(return_value=("credential", "synthetic-secret")))
    monkeypatch.setattr(connection, "_build_connection", lambda *args: conn)
    monkeypatch.setattr(connection, "_validate_current_roles", AsyncMock())
    failure = http.NotFound("Resource disappeared")
    with pytest.raises(http.NotFound) as caught:
        async with connection.consumer_connection(SimpleNamespace()):
            raise failure
    assert caught.value is failure
    assert not isinstance(caught.value, connection.McpCredentialInvalidError)
    conn.close.assert_called_once_with()


@pytest.mark.asyncio
async def test_credential_state_uses_full_grant_id_seven_day_ttl_and_exact_cleanup(monkeypatch):
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(credential_state.cache, "_get_redis", AsyncMock(return_value=redis))
    first, other = "12345678-first-grant", "12345678-other-grant"
    try:
        assert not await credential_state.is_invalid(first)
        await credential_state.mark_invalid(first)
        assert await credential_state.is_invalid(first)
        assert not await credential_state.is_invalid(other)
        assert 604799 <= await redis.ttl(f"afterglow:mcp:credential-invalid:{first}") <= 604800
        await credential_state.mark_invalid(other)
        await credential_state.clear_invalid(first)
        assert not await credential_state.is_invalid(first)
        assert await credential_state.is_invalid(other)
    finally:
        await redis.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["connect", "operation"])
async def test_credential_state_redis_failures_are_best_effort(monkeypatch, boundary):
    unavailable = ConnectionError("synthetic-redis-secret")
    redis = SimpleNamespace(
        set=AsyncMock(side_effect=unavailable),
        exists=AsyncMock(side_effect=unavailable),
        delete=AsyncMock(side_effect=unavailable),
    )
    getter = AsyncMock(side_effect=unavailable) if boundary == "connect" else AsyncMock(return_value=redis)
    monkeypatch.setattr(credential_state.cache, "_get_redis", getter)
    await credential_state.mark_invalid("grant")
    assert not await credential_state.is_invalid("grant")
    await credential_state.clear_invalid("grant")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outer", ["403", "502", "timeout", "connection", "keystone_connection", "keystone_timeout", "requests_connection"]
)
@pytest.mark.parametrize("order", ["transport_first", "rejection_first"])
async def test_auth_transport_or_other_http_failure_overrides_incidental_rejection(monkeypatch, outer, order):
    incidental = http.NotFound("Role not found")
    transport = _failure(outer, "direct")
    failure, nested = (transport, incidental) if order == "transport_first" else (incidental, transport)
    failure.__context__ = nested
    auth = SimpleNamespace(get_access=Mock(side_effect=failure))
    session = SimpleNamespace(session=SimpleNamespace(close=Mock()))
    monkeypatch.setattr(connection.v3, "ApplicationCredential", lambda **kwargs: auth)
    monkeypatch.setattr(connection.native_transport, "create_session", lambda **kwargs: session)
    monkeypatch.setattr(
        connection, "get_settings", lambda: SimpleNamespace(os_auth_url="https://identity.invalid", ssl_verify=True)
    )
    monkeypatch.setattr(connection, "_load_credential", AsyncMock(return_value=("credential", "synthetic-secret")))
    with pytest.raises(connection.McpConsumerConnectionError) as caught:
        async with connection.consumer_connection(SimpleNamespace()):
            pytest.fail("Authentication must fail")
    assert not isinstance(caught.value, connection.McpCredentialInvalidError)
    assert caught.value.__cause__ is failure
