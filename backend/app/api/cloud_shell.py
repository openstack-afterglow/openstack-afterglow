"""Global Cloud Shell workspace, approval ticket, and binary terminal relay API."""

from __future__ import annotations

import asyncio
import json
import time
from contextlib import suppress
from typing import Any
from urllib.parse import urlsplit

import websockets
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from websockets.exceptions import ConnectionClosed

from app.api.deps import get_token_info, require_project_write
from app.config import get_settings
from app.rate_limit import limiter
from app.services import cloud_shell, zun

router = APIRouter()

MAX_BINARY_FRAME_BYTES = 64 * 1024
MAX_CONTROL_FRAME_BYTES = 2 * 1024
BOOTSTRAP_BUFFER_BYTES = 64 * 1024


class WorkspaceStatusResponse(BaseModel):
    workspace: str
    home_size_gib: int
    session_active: bool
    session_in_project: bool


class TicketResponse(BaseModel):
    ticket: str
    websocket_path: str
    expires_at: int


def _http_error(exc: cloud_shell.CloudShellError) -> HTTPException:
    if isinstance(exc, cloud_shell.CloudShellConflict):
        status_code = 409
    elif isinstance(exc, cloud_shell.CloudShellUnauthorized):
        status_code = 401
    else:
        status_code = 503
    return HTTPException(status_code=status_code, detail={"code": exc.code, "message": exc.detail})


@router.get("/workspace", response_model=WorkspaceStatusResponse)
async def get_workspace(token_info: dict[str, Any] = Depends(get_token_info)):
    try:
        return await cloud_shell.workspace_status(token_info)
    except cloud_shell.CloudShellError as exc:
        raise _http_error(exc)


@router.post("/tickets", response_model=TicketResponse, status_code=201)
@limiter.limit("5/minute")
async def create_ticket(request: Request, token_info: dict[str, Any] = Depends(require_project_write)):
    await cloud_shell.record_audit(token_info, action="cloud_shell.start", status="started")
    try:
        return await cloud_shell.issue_cloud_shell_ticket(token_info)
    except cloud_shell.CloudShellError as exc:
        await cloud_shell.record_audit(
            token_info,
            action="cloud_shell.start",
            status="failed",
            error_code=exc.code,
        )
        raise _http_error(exc)


@router.delete("/workspace", status_code=204)
async def delete_workspace(token_info: dict[str, Any] = Depends(require_project_write)):
    await cloud_shell.record_audit(token_info, action="cloud_shell.reset", status="started")
    try:
        await cloud_shell.reset_workspace(token_info)
    except cloud_shell.CloudShellError as exc:
        await cloud_shell.record_audit(
            token_info,
            action="cloud_shell.reset",
            status="failed",
            error_code=exc.code,
        )
        raise _http_error(exc)
    await cloud_shell.record_audit(token_info, action="cloud_shell.reset", status="success")
    return Response(status_code=204)


def _canonical_origin(value: str) -> tuple[str, str, int | None] | None:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        return None
    return parsed.scheme, (parsed.hostname or "").lower(), port


def _origin_allowed(origin: str | None) -> bool:
    if not origin:
        return False
    requested = _canonical_origin(origin)
    if requested is None:
        return False
    settings = get_settings()
    allowed = {_canonical_origin(value) for value in settings.cors_origin_list}
    if settings.frontend_base_url:
        allowed.add(_canonical_origin(settings.frontend_base_url))
    return requested in allowed


async def _send_event(websocket: WebSocket, event_type: str, **payload: Any) -> None:
    await websocket.send_text(json.dumps({"type": event_type, **payload}, separators=(",", ":"), sort_keys=True))


async def _close(websocket: WebSocket, code: int, reason: str) -> None:
    with suppress(RuntimeError):
        await websocket.close(code=code, reason=reason[:120])


async def _wait_for_marker(upstream: Any, marker: bytes) -> None:
    buffered = bytearray()
    while marker not in buffered:
        frame = await asyncio.wait_for(upstream.recv(), timeout=15)
        if not isinstance(frame, bytes):
            raise cloud_shell.CloudShellUnavailable(
                "upstream_protocol", "Cloud Shell upstream did not negotiate binary frames"
            )
        buffered.extend(frame)
        if cloud_shell.BOOTSTRAP_ERROR_MARKER in buffered:
            raise cloud_shell.CloudShellUnavailable("bootstrap_failed", "Cloud Shell credential bootstrap failed")
        if len(buffered) > BOOTSTRAP_BUFFER_BYTES:
            raise cloud_shell.CloudShellUnavailable(
                "bootstrap_protocol", "Cloud Shell bootstrap output exceeded its bound"
            )


class _ResizeDebouncer:
    def __init__(self, runtime: cloud_shell.CloudShellRuntime) -> None:
        self.runtime = runtime
        self.pending: tuple[int, int] | None = None
        self.task: asyncio.Task[None] | None = None

    def submit(self, cols: int, rows: int) -> None:
        self.pending = (cols, rows)
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        await asyncio.sleep(0.075)
        while self.pending is not None:
            cols, rows = self.pending
            self.pending = None
            await asyncio.to_thread(
                zun.resize_exec_session,
                self.runtime.connection,
                self.runtime.container_id,
                exec_id=self.runtime.exec_session.exec_id,
                cols=cols,
                rows=rows,
            )
            if self.pending is not None:
                await asyncio.sleep(0.075)

    async def close(self) -> None:
        if self.task is None:
            return
        self.task.cancel()
        with suppress(asyncio.CancelledError):
            await self.task


async def _relay_terminal(
    websocket: WebSocket,
    upstream: Any,
    runtime: cloud_shell.CloudShellRuntime,
) -> None:
    last_activity = [time.monotonic()]
    last_heartbeat = [time.monotonic()]
    resize = _ResizeDebouncer(runtime)

    async def browser_to_upstream() -> None:
        while True:
            message = await websocket.receive()
            message_type = message.get("type")
            if message_type == "websocket.disconnect":
                return
            binary = message.get("bytes")
            text = message.get("text")
            if binary is not None:
                if len(binary) > MAX_BINARY_FRAME_BYTES:
                    await _close(websocket, 1009, "terminal frame too large")
                    return
                last_activity[0] = time.monotonic()
                await upstream.send(binary)
                continue
            if text is None or len(text.encode("utf-8")) > MAX_CONTROL_FRAME_BYTES:
                await _close(websocket, 1002, "invalid control frame")
                return
            try:
                control = json.loads(text)
            except (TypeError, ValueError):
                await _close(websocket, 1002, "invalid control frame")
                return
            if not isinstance(control, dict):
                await _close(websocket, 1002, "invalid control frame")
                return
            if control.get("type") == "ping":
                await _send_event(websocket, "status", phase="ready")
                continue
            if control.get("type") != "resize":
                await _close(websocket, 1002, "unknown control frame")
                return
            cols = control.get("cols")
            rows = control.get("rows")
            if (
                isinstance(cols, bool)
                or isinstance(rows, bool)
                or not isinstance(cols, int)
                or not isinstance(rows, int)
                or not 20 <= cols <= 500
                or not 5 <= rows <= 200
                or set(control) != {"type", "cols", "rows"}
            ):
                await _close(websocket, 1002, "invalid terminal size")
                return
            resize.submit(cols, rows)

    async def upstream_to_browser() -> None:
        while True:
            frame = await upstream.recv()
            if not isinstance(frame, bytes):
                raise cloud_shell.CloudShellUnavailable(
                    "upstream_protocol", "Cloud Shell upstream sent a non-binary frame"
                )
            last_activity[0] = time.monotonic()
            for offset in range(0, len(frame), MAX_BINARY_FRAME_BYTES):
                await websocket.send_bytes(frame[offset : offset + MAX_BINARY_FRAME_BYTES])

    async def monitor() -> None:
        settings = get_settings()
        while True:
            await asyncio.sleep(1)
            now_monotonic = time.monotonic()
            if int(time.time()) >= runtime.expires_at:
                await _send_event(websocket, "exit", reason="session_expired")
                await _close(websocket, 4419, "Cloud Shell session expired")
                return
            if now_monotonic - last_activity[0] >= settings.cloud_shell_idle_timeout_seconds:
                await _send_event(websocket, "warning", reason="idle_timeout")
                await _send_event(websocket, "exit", reason="idle_timeout")
                await _close(websocket, 4408, "Cloud Shell idle timeout")
                return
            if now_monotonic - last_heartbeat[0] >= cloud_shell.HEARTBEAT_INTERVAL_SECONDS:
                if not await cloud_shell.refresh_heartbeat(runtime.lease):
                    await _send_event(websocket, "error", code="coordination_lost")
                    await _close(websocket, 4500, "Cloud Shell coordination lost")
                    return
                last_heartbeat[0] = now_monotonic

    tasks = {
        asyncio.create_task(browser_to_upstream()),
        asyncio.create_task(upstream_to_browser()),
        asyncio.create_task(monitor()),
    }
    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        for task in done:
            task.result()
    finally:
        await resize.close()


@router.websocket("/ws")
async def cloud_shell_ws(websocket: WebSocket, ticket: str = Query(...)) -> None:
    await websocket.accept()
    if not _origin_allowed(websocket.headers.get("origin")):
        await _close(websocket, 4403, "origin not allowed")
        return

    lease: cloud_shell.CloudShellLease | None = None
    runtime: cloud_shell.CloudShellRuntime | None = None
    upstream: Any = None
    token_info: dict[str, Any] | None = None
    release_lease = True
    try:
        lease = await cloud_shell.consume_cloud_shell_ticket(ticket)
        token_info = {
            "user_id": lease.user_id,
            "username": lease.username,
            "project_id": lease.project_id,
        }

        async def report(phase: str) -> None:
            await _send_event(websocket, "status", phase=phase)

        await report("provisioning")
        runtime = await cloud_shell.provision_session(lease, report)
        await report("authorizing")
        upstream = await websockets.connect(
            runtime.exec_session.websocket_url,
            subprotocols=["binary"],
            open_timeout=15,
            close_timeout=5,
            max_size=MAX_BINARY_FRAME_BYTES,
            ping_interval=20,
            ping_timeout=20,
        )
        await _wait_for_marker(upstream, cloud_shell.BOOTSTRAP_READY_MARKER)
        await upstream.send(cloud_shell.bootstrap_payload(lease))
        await _wait_for_marker(upstream, cloud_shell.BOOTSTRAP_OK_MARKER)
        await _send_event(
            websocket,
            "ready",
            expires_at=runtime.expires_at,
            idle_timeout_seconds=get_settings().cloud_shell_idle_timeout_seconds,
        )
        await cloud_shell.record_audit(token_info, action="cloud_shell.start", status="success")
        await _relay_terminal(websocket, upstream, runtime)
    except cloud_shell.CloudShellConflict as exc:
        release_lease = not exc.retain_active
        await _send_event(websocket, "error", code=exc.code)
        await _close(websocket, 4410, exc.detail)
    except cloud_shell.CloudShellUnauthorized as exc:
        release_lease = not exc.retain_active
        await _send_event(websocket, "error", code=exc.code)
        await _close(websocket, 4401, exc.detail)
    except (WebSocketDisconnect, ConnectionClosed):
        pass
    except cloud_shell.CloudShellError as exc:
        release_lease = not exc.retain_active
        await _send_event(websocket, "error", code=exc.code)
        await _close(websocket, 4500, exc.detail)
    except Exception:
        await _send_event(websocket, "error", code="terminal_failed")
        await _close(websocket, 4500, "Cloud Shell terminal failed")
    finally:
        if upstream is not None:
            with suppress(Exception):
                await upstream.close()
        cleanup_ok = True
        if runtime is not None:
            cleanup_ok = await cloud_shell.cleanup_session(runtime)
            release_lease = False
        elif lease is not None and release_lease:
            await cloud_shell.abandon_lease(lease)
        if token_info is not None:
            await cloud_shell.record_audit(
                token_info,
                action="cloud_shell.end",
                status="success" if cleanup_ok else "failed",
                error_code=None if cleanup_ok else "cleanup_pending",
            )
