"""Opt-in live Cloud Shell lifecycle against real Zun, Cinder, Keystone, and Redis."""

from __future__ import annotations

import json
import os
import secrets
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession

from app.main import app

pytestmark = pytest.mark.slow

LIVE_IDENTITY_ENV = "CLOUD_SHELL_LIVE_USER_IDENTITY"
LIVE_CONFIRM_ENV = "CLOUD_SHELL_LIVE_CONFIRM"
LIVE_CONFIRM_VALUE = "reset-disposable-home"


def require_disposable_live_identity(
    credentials: dict[str, str],
    environment: dict[str, str] | os._Environ[str] = os.environ,
) -> None:
    """Require explicit operator intent bound to the selected disposable user."""
    expected_identity = environment.get(LIVE_IDENTITY_ENV, "").strip()
    if not expected_identity:
        pytest.skip(f"{LIVE_IDENTITY_ENV} is required for destructive Cloud Shell live verification")
    if environment.get(LIVE_CONFIRM_ENV, "").strip() != LIVE_CONFIRM_VALUE:
        pytest.skip(
            f"{LIVE_CONFIRM_ENV}={LIVE_CONFIRM_VALUE} is required for destructive Cloud Shell live verification"
        )
    actual_identity = str(credentials.get("username") or "").strip()
    if expected_identity != actual_identity:
        pytest.fail(f"{LIVE_IDENTITY_ENV} does not match the selected integration user")


def require_empty_live_workspace(payload: dict[str, Any]) -> None:
    """Refuse to adopt or delete a workspace that predates this test run."""
    if payload.get("session_active"):
        pytest.fail("Disposable Cloud Shell identity already has an active session")
    if payload.get("workspace") != "absent":
        pytest.fail("Disposable Cloud Shell identity must start without a persistent workspace")


def _origin(settings: Any) -> str:
    if settings.frontend_base_url:
        return settings.frontend_base_url.rstrip("/")
    if settings.cors_origin_list:
        return settings.cors_origin_list[0].rstrip("/")
    pytest.skip("Cloud Shell live test requires a configured browser origin")


def _login(client: TestClient, credentials: dict[str, str]) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json=dict(credentials))
    assert response.status_code == 200
    payload = response.json()
    return {
        "Authorization": f"Bearer {payload['token']}",
        "X-Project-Id": str(payload["project_id"]),
    }


def _ticket(client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    response = client.post("/api/v1/cloud-shell/tickets", headers=headers)
    assert response.status_code == 201
    payload = response.json()
    assert payload["websocket_path"] == "/api/v1/cloud-shell/ws"
    return payload


def _receive_ready(websocket: WebSocketTestSession) -> None:
    phases: list[str] = []
    for _ in range(256):
        message = websocket.receive()
        if message["type"] == "websocket.close":
            pytest.fail(f"Cloud Shell closed before ready (code={message.get('code')})")
        text = message.get("text")
        if text is None:
            continue
        event = json.loads(text)
        if event.get("type") == "status":
            phases.append(str(event.get("phase", "")))
            continue
        if event.get("type") == "error":
            pytest.fail(f"Cloud Shell provisioning failed ({event.get('code', 'unknown')})")
        if event.get("type") == "ready":
            assert "provisioning" in phases
            assert "authorizing" in phases
            assert int(event["expires_at"]) > int(time.time())
            assert int(event["idle_timeout_seconds"]) >= 60
            return
    pytest.fail("Cloud Shell did not reach ready state")


def _receive_terminal_marker(websocket: WebSocketTestSession, marker: bytes) -> None:
    output = bytearray()
    for _ in range(512):
        message = websocket.receive()
        if message["type"] == "websocket.close":
            pytest.fail(f"Cloud Shell closed before command completion (code={message.get('code')})")
        binary = message.get("bytes")
        if binary is not None:
            output.extend(binary)
            if marker in output:
                return
            if len(output) > 256 * 1024:
                del output[: len(output) - 128 * 1024]
            continue
        text = message.get("text")
        if text is not None:
            event = json.loads(text)
            if event.get("type") in {"error", "exit"}:
                pytest.fail(f"Cloud Shell command interrupted ({event.get('code') or event.get('reason')})")
    pytest.fail("Cloud Shell command marker was not returned")


def _wait_until_inactive(client: TestClient, headers: dict[str, str]) -> None:
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        response = client.get("/api/v1/cloud-shell/workspace", headers=headers)
        assert response.status_code == 200
        if not response.json()["session_active"]:
            return
        time.sleep(1)
    pytest.fail("Cloud Shell session cleanup did not release the user lease")


def _open_shell(
    client: TestClient,
    headers: dict[str, str],
    origin: str,
) -> WebSocketTestSession:
    ticket = _ticket(client, headers)
    return client.websocket_connect(
        f"{ticket['websocket_path']}?ticket={ticket['ticket']}",
        headers={"Origin": origin},
        subprotocols=["binary"],
    )


def test_cloud_shell_approve_cli_close_home_reuse_and_reset(
    settings,
    user_credentials_fx,
):
    """Exercise the destructive live path only when the deployment enables Cloud Shell."""
    if not settings.service_cloud_shell_enabled:
        pytest.skip("services.cloud_shell=false")

    require_disposable_live_identity(user_credentials_fx)

    home_marker = secrets.token_hex(12)
    command_done = f"__AFTERGLOW_CLOUD_SHELL_COMMAND_{secrets.token_hex(8)}__"
    reuse_done = f"__AFTERGLOW_CLOUD_SHELL_REUSE_{secrets.token_hex(8)}__"

    with TestClient(app) as client:
        headers = _login(client, user_credentials_fx)
        origin = _origin(settings)

        initial = client.get("/api/v1/cloud-shell/workspace", headers=headers)
        assert initial.status_code == 200
        require_empty_live_workspace(initial.json())

        try:
            with _open_shell(client, headers, origin) as websocket:
                _receive_ready(websocket)
                command = (
                    "openstack token issue -f value -c id >/dev/null "
                    f"&& printf '%s' '{home_marker}' > \"$HOME/.afterglow-live\" "
                    f"&& printf '\\n%s\\n' '{command_done}'\r"
                )
                websocket.send_bytes(command.encode())
                _receive_terminal_marker(websocket, command_done.encode())

            _wait_until_inactive(client, headers)

            with _open_shell(client, headers, origin) as websocket:
                _receive_ready(websocket)
                command = (
                    f"test \"$(cat \"$HOME/.afterglow-live\")\" = '{home_marker}' && printf '\\n%s\\n' '{reuse_done}'\r"
                )
                websocket.send_bytes(command.encode())
                _receive_terminal_marker(websocket, reuse_done.encode())

            _wait_until_inactive(client, headers)

            reset = client.delete("/api/v1/cloud-shell/workspace", headers=headers)
            assert reset.status_code == 204
            workspace = client.get("/api/v1/cloud-shell/workspace", headers=headers)
            assert workspace.status_code == 200
            assert workspace.json()["workspace"] == "absent"
        finally:
            _wait_until_inactive(client, headers)
            workspace = client.get("/api/v1/cloud-shell/workspace", headers=headers)
            if workspace.status_code == 200 and workspace.json()["workspace"] != "absent":
                cleanup = client.delete("/api/v1/cloud-shell/workspace", headers=headers)
                assert cleanup.status_code == 204
