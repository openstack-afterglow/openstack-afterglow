"""Safe inference and successful SDK initialization evidence boundaries."""

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.services.mcp_control_plane import clients, transport
from app.services.mcp_control_plane.authentication import McpAuthenticationError
from tests.test_mcp_tool_call_cache import READ_TOKEN
from tests.test_mcp_tool_call_cache import running_mcp as _running_mcp

running_mcp = _running_mcp
_BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0) Chrome/130.0 Safari/537.36 Edg/130.0"
_PARAMS = {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "Codex", "version": "1.2"}}


@pytest.mark.parametrize(
    "name,ua,product,kind,source,browser,os_name",
    [
        ("Claude Code", _BROWSER_UA, "Claude Code", "agent", "client_info", "Edge", "Windows"),
        ("Codex", None, "Codex", "agent", "client_info", None, None),
        ("Cursor", None, "Cursor", "agent", "client_info", None, None),
        ("VS Code", None, "VS Code", "agent", "client_info", None, None),
        ("MCP Python SDK", _BROWSER_UA, "MCP Python SDK", "sdk", "client_info", "Edge", "Windows"),
        ("MCP TypeScript SDK", None, "MCP TypeScript SDK", "sdk", "client_info", None, None),
        ("unrecognized-client", _BROWSER_UA, "Edge", "browser", "user_agent", "Edge", "Windows"),
        (
            "browser-bridge",
            "Mozilla/5.0 (Linux; Android) Chrome/130.0 Safari/537.36",
            "Chrome",
            "browser",
            "user_agent",
            "Chrome",
            "Android",
        ),
        ("bridge", "Mozilla/5.0 (iPhone) Safari/600.1", "Safari", "browser", "user_agent", "Safari", "iOS"),
        ("bridge", "Mozilla/5.0 (Macintosh) Firefox/130.0", "Firefox", "browser", "user_agent", "Firefox", "macOS"),
        ("Googlebot", _BROWSER_UA, "Googlebot", "bot", "client_info", "Edge", "Windows"),
        ("bridge", "Googlebot/2.1 Chrome/130.0", "Googlebot", "bot", "user_agent", "Chrome", None),
        ("somebot", _BROWSER_UA, None, "bot", "client_info", "Edge", "Windows"),
        ("unrecognized-client", "custom/1.0", None, "unknown", "client_info", None, None),
        ("Codexevil", None, None, "unknown", "client_info", None, None),
        (None, None, None, "unknown", "unknown", None, None),
    ],
)
def test_inference_preserves_provenance_and_true_unknown(name, ua, product, kind, source, browser, os_name):
    evidence = clients.client_observation({"name": name, "version": "1.0"}, ua)
    assert evidence == {
        "client_name": name,
        "client_version": "1.0",
        "product": product,
        "kind": kind,
        "identity_source": source,
        "browser": browser,
        "os": os_name,
    }


@pytest.mark.parametrize(
    "poison",
    [
        "mcp-afgl-" + "x" * 43,
        "Bearer secret",
        "https://example.test/private?token=secret",
        "<script>alert(1)</script>",
        "user@example.test",
        "evil\nCodex",
        "\u202eCodex",
        "x" * 101,
        {"name": "Codex"},
        ["Codex"],
        "api_key=private",
        "sk-afgl-" + "x" * 43,
    ],
)
def test_secret_bearing_metadata_is_not_retained_or_repaired(poison):
    evidence = clients.client_observation({"name": poison, "version": poison, "token": "secret"}, _BROWSER_UA)
    assert evidence["client_name"] is None
    assert evidence["client_version"] is None
    assert evidence["product"] is None
    assert evidence["kind"] == "unknown"
    assert evidence["identity_source"] == "unknown"
    assert set(evidence) == {"client_name", "client_version", "product", "kind", "identity_source", "browser", "os"}
    assert "secret" not in json.dumps(evidence)


def test_bounds_and_user_agent_privacy():
    assert (
        clients.client_observation({"name": "A " * 49 + "AB", "version": "1." + "0" * 30}, None)["client_name"]
        is not None
    )
    evidence = clients.client_observation({"name": "Codex", "version": "1." + "0" * 31}, "secret " * 400)
    assert evidence["client_version"] is None
    assert evidence["browser"] is None and evidence["os"] is None
    assert (
        clients.client_observation({"name": "custom", "version": "1"}, "Chrome/1\r\nAuthorization: secret")["kind"]
        == "unknown"
    )


def test_multiple_clients_deduplicate_refresh_first_seen_and_evict_oldest():
    now = datetime(2026, 10, 12, tzinfo=UTC)
    records = None
    for index in range(12):
        evidence = clients.client_observation({"name": f"client-{index}", "version": "1"}, None)
        records = clients.merge_client_observation(records, evidence, now=now + timedelta(seconds=index))
    assert len(records) == 10
    assert [item["client_name"] for item in records] == [f"client-{index}" for index in range(2, 12)]
    first = records[0]["first_seen_at"]
    records = clients.merge_client_observation(
        records, clients.client_observation({"name": "client-2", "version": "1"}, None), now=now + timedelta(seconds=20)
    )
    assert len(records) == 10
    assert records[-1]["first_seen_at"] == first
    assert records[-1]["last_seen_at"] == (now + timedelta(seconds=20)).isoformat()
    assert [item["client_name"] for item in records].count("client-2") == 1
    records = clients.merge_client_observation(
        records, clients.client_observation({"name": "client-2", "version": "2"}, None), now=now + timedelta(seconds=21)
    )
    assert len(records) == 10
    assert records[0]["client_name"] == "client-4"
    assert records[-1]["client_version"] == "2"


def test_projection_is_exact_allowlist_and_handles_legacy_or_poisoned_json():
    assert clients.public_client_observations(None) == []
    assert clients.public_client_observations({"token": "secret"}) == []
    item = {
        "client_name": "Bearer secret",
        "client_version": {},
        "product": "secret",
        "kind": [],
        "identity_source": {},
        "browser": "secret",
        "os": [],
        "digest": "secret",
        "token": "secret",
        "first_seen_at": "2026-10-12T00:00:00Z",
        "last_seen_at": "2026-10-12T00:00:01Z",
    }
    projected = clients.public_client_observations([None, {}, item])[0]
    assert "secret" not in json.dumps(projected)
    assert projected["kind"] == "unknown" and projected["identity_source"] == "unknown"
    assert set(projected) == {
        "client_name",
        "client_version",
        "product",
        "kind",
        "identity_source",
        "browser",
        "os",
        "first_seen_at",
        "last_seen_at",
    }
    assert clients.public_client_observations([{**item, "last_seen_at": "invalid"}]) == []
    assert clients.public_client_observations([{**item, "last_seen_at": "2026-10-11T00:00:00Z"}]) == []


async def _initialize(client, *, payload=None, token=READ_TOKEN):
    headers = {"Accept": "application/json, text/event-stream", "User-Agent": _BROWSER_UA}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    return await client.post(
        "/mcp", headers=headers, json=payload or {"jsonrpc": "2.0", "id": 7, "method": "initialize", "params": _PARAMS}
    )


@pytest.mark.asyncio
async def test_actual_sdk_initializes_and_records_only_successful_authenticated_requests(running_mcp, monkeypatch):
    observed = []

    async def observe(principal, evidence):
        observed.append((principal, evidence))

    monkeypatch.setattr(transport, "record_client_observation", observe)
    async with running_mcp() as client:
        missing = await _initialize(client, token=None)
        invalid = await _initialize(client, token="unsigned-token")
        malformed = await _initialize(client, payload={"jsonrpc": "2.0", "id": 7, "method": "initialize", "params": {}})
        invalid_info = await _initialize(
            client,
            payload={
                "jsonrpc": "2.0",
                "id": 7,
                "method": "initialize",
                "params": {**_PARAMS, "clientInfo": {"name": [], "version": "1"}},
            },
        )
        assert missing.status_code == invalid.status_code == 401
        assert malformed.status_code != 200 or "error" in malformed.json()
        assert invalid_info.status_code != 200 or "error" in invalid_info.json()
        assert observed == []
        success = await _initialize(client)
    assert success.status_code == 200, success.text
    assert success.json()["result"]["serverInfo"]["name"] == "afterglow-consumer-mcp"
    assert len(observed) == 1
    assert observed[0][0].grant_id == "read-grant"
    assert observed[0][1]["product"] == "Codex"
    assert observed[0][1]["identity_source"] == "client_info"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error,status",
    [
        (clients.McpClientObservationUnavailable("private storage details"), 503),
        (McpAuthenticationError("revoked epoch"), 401),
    ],
)
async def test_store_failure_replaces_success_before_any_sdk_headers_escape(running_mcp, monkeypatch, error, status):
    async def fail(*_args):
        raise error

    monkeypatch.setattr(transport, "record_client_observation", fail)
    async with running_mcp() as client:
        response = await _initialize(client)
    assert response.status_code == status
    assert "result" not in response.json()
    assert "private storage details" not in response.text
    assert "mcp-session-id" not in response.headers


@pytest.mark.asyncio
async def test_sdk_failure_after_provisional_headers_records_nothing(running_mcp, monkeypatch):
    observed = []

    async def observe(*args):
        observed.append(args)

    async def broken_sdk(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": [(b"x-sdk-provisional", b"yes")]})
        raise RuntimeError("SDK failed after start")

    monkeypatch.setattr(transport, "record_client_observation", observe)
    async with running_mcp() as client:
        monkeypatch.setattr(transport, "_manager", SimpleNamespace(handle_request=broken_sdk))
        response = await _initialize(client)
    assert response.status_code == 503
    assert "x-sdk-provisional" not in response.headers
    assert observed == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sdk_body,status",
    [
        ({"jsonrpc": "2.0", "id": 7, "error": {"code": -32602, "message": "Invalid params"}}, 200),
        ({"jsonrpc": "2.0", "id": 7, "result": {}}, 503),
        (
            {
                "jsonrpc": "2.0",
                "id": 8,
                "result": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "serverInfo": {"name": "test", "version": "1"},
                },
            },
            503,
        ),
    ],
)
async def test_sdk_errors_or_invalid_success_never_create_identity(running_mcp, monkeypatch, sdk_body, status):
    observed = []

    async def observe(*args):
        observed.append(args)

    async def sdk_response(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": json.dumps(sdk_body).encode()})

    monkeypatch.setattr(transport, "record_client_observation", observe)
    async with running_mcp() as client:
        monkeypatch.setattr(transport, "_manager", SimpleNamespace(handle_request=sdk_response))
        response = await _initialize(client)
    assert response.status_code == status
    assert observed == []


@pytest.mark.asyncio
async def test_missing_real_store_fails_initialize_closed(running_mcp, monkeypatch):
    monkeypatch.setattr(clients, "get_session_factory", lambda: None)
    async with running_mcp() as client:
        response = await _initialize(client)
    assert response.status_code == 503
    assert "result" not in response.json()


@pytest.mark.asyncio
async def test_valid_sdk_metadata_poisoning_retains_only_unknown_safe_evidence(running_mcp, monkeypatch):
    observed = []

    async def observe(principal, evidence):
        observed.append(evidence)

    monkeypatch.setattr(transport, "record_client_observation", observe)
    poison = "mcp-afgl-" + "x" * 43
    params = {
        **_PARAMS,
        "clientInfo": {"name": poison, "version": poison, "title": poison, "websiteUrl": "https://secret.example.test"},
        "_meta": {"secret": poison},
    }
    async with running_mcp() as client:
        response = await _initialize(
            client, payload={"jsonrpc": "2.0", "id": 7, "method": "initialize", "params": params}
        )
    assert response.status_code == 200, response.text
    assert len(observed) == 1
    assert observed[0]["client_name"] is None and observed[0]["client_version"] is None
    assert observed[0]["kind"] == "unknown"
    assert poison not in json.dumps(observed)
    assert "secret.example.test" not in json.dumps(observed)
