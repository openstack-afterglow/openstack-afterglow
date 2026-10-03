"""Browser-scoped realtime session tickets and bounded Lumen WebSocket relay."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

import httpx
import websockets
from fastapi import APIRouter, Depends, Header, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field
from websockets.exceptions import ConnectionClosed

from app.api.cloud_shell import _origin_allowed
from app.api.deps import get_token_info
from app.config import get_settings
from app.services import service_proxy, ws_ticket

router = APIRouter()
_MAX_FRAME_BYTES = 64 * 1024


class SessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_id: str = Field(min_length=1, max_length=190)
    provider_id: int | str | None = None
    voice: str | None = Field(default=None, max_length=100)
    instructions: str | None = Field(default=None, max_length=4096)
    max_duration_seconds: int = Field(default=300, ge=10, le=900)


@router.post("/realtime/sessions", status_code=201)
async def create_session(
    payload: SessionRequest,
    idempotency_key: UUID = Header(alias="Idempotency-Key"),
    principal: dict = Depends(get_token_info),
):
    logical_project = principal["project_id"]
    connection_project = principal.get("connection_project_id") or logical_project
    endpoint = await asyncio.to_thread(
        service_proxy._get_internal_endpoint, principal["token"], connection_project, "lumen"
    )
    if not endpoint:
        raise HTTPException(status_code=503, detail="Realtime service unavailable")
    try:
        url = service_proxy.join_version_aware_url(endpoint, "/v1/chat/realtime/sessions")
    except ValueError as exc:
        raise HTTPException(status_code=503, detail="Realtime service unavailable") from exc
    headers = {
        "x-auth-token": principal["token"],
        "x-project-id": connection_project,
        "Idempotency-Key": str(idempotency_key),
    }
    if logical_project != connection_project:
        headers["x-target-project-id"] = logical_project
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(20.0, connect=5.0), verify=get_settings().ssl_verify
        ) as client:
            response = await client.post(url, headers=headers, json=payload.model_dump())
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail="Realtime service unavailable") from exc
    if response.status_code >= 400:
        try:
            error = response.json().get("detail", "Realtime admission failed")
        except (ValueError, AttributeError):
            error = "Realtime admission failed"
        raise HTTPException(status_code=response.status_code, detail=error)
    try:
        data = response.json()
        session_id = str(UUID(data["session_id"]))
        connect_token = data["connect_token"]
        if not isinstance(connect_token, str) or len(connect_token) < 32:
            raise ValueError
        ttl = min(60, int(data["expires_in_seconds"]))
        if ttl <= 0:
            raise ValueError("realtime session expired")
        result = {
            "session_id": session_id,
            "status": data["status"],
            "model_name": data["model_name"],
            "provider_type": data["provider_type"],
            "expires_in_seconds": ttl,
            "expires_at": (datetime.now(UTC) + timedelta(seconds=ttl)).isoformat(),
        }
        ticket = await ws_ticket.issue_ticket(
            "chat-realtime",
            {
                "session_id": session_id,
                "connect_token": connect_token,
                "user_id": principal["user_id"],
                "project_id": logical_project,
            },
            ttl_seconds=ttl,
            revoke_scope=logical_project,
        )
    except (ValueError, KeyError, TypeError, ws_ticket.WebSocketTicketError) as exc:
        raise HTTPException(status_code=503, detail="Realtime ticket unavailable") from exc
    return {**result, "ticket": ticket, "websocket_path": "/api/v1/chat/realtime/ws"}


@router.websocket("/realtime/ws")
async def relay(websocket: WebSocket):
    if not _origin_allowed(websocket.headers.get("origin")):
        await websocket.close(code=4403)
        return
    ticket = websocket.query_params.get("ticket", "")
    try:
        payload = await ws_ticket.consume_ticket(ticket, expected_kind="chat-realtime")
    except ws_ticket.WebSocketTicketError:
        await websocket.close(code=1013)
        return
    if payload is None:
        await websocket.close(code=4401)
        return
    try:
        session_id = str(UUID(payload["session_id"]))
        token = payload["connect_token"]
        if not isinstance(token, str) or len(token) < 32:
            raise ValueError
        endpoint = await service_proxy.resolve_service_endpoint("lumen")
        if not endpoint:
            raise ValueError
        url = service_proxy.join_version_aware_url(endpoint, f"/v1/chat/realtime/sessions/{session_id}/ws")
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError
        ws_url = urlunsplit(("wss" if parsed.scheme == "https" else "ws", parsed.netloc, parsed.path, "", ""))
    except (ValueError, KeyError, TypeError):
        await websocket.close(code=1013)
        return
    try:
        async with websockets.connect(
            ws_url,
            additional_headers={"x-realtime-token": token},
            max_size=_MAX_FRAME_BYTES,
            open_timeout=10,
            close_timeout=5,
        ) as upstream:
            await websocket.accept()

            async def browser_to_lumen():
                while True:
                    frame = await websocket.receive_text()
                    if len(frame.encode("utf-8")) > _MAX_FRAME_BYTES:
                        raise ValueError("Realtime frame too large")
                    await upstream.send(frame)

            async def lumen_to_browser():
                async for frame in upstream:
                    if not isinstance(frame, str) or len(frame.encode("utf-8")) > _MAX_FRAME_BYTES:
                        raise ValueError("Realtime frame too large")
                    await websocket.send_text(frame)

            tasks = {asyncio.create_task(browser_to_lumen()), asyncio.create_task(lumen_to_browser())}
            try:
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED, timeout=960)
                for task in done:
                    with suppress(WebSocketDisconnect, ConnectionClosed):
                        task.result()
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
    except (ConnectionClosed, WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception:
        with suppress(RuntimeError):
            await websocket.close(code=1011)
    else:
        with suppress(RuntimeError):
            await websocket.close(code=1000)
