"""Browser-scoped realtime session tickets and bounded Lumen WebSocket relay."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import Literal
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

import httpx
import websockets
from fastapi import APIRouter, Depends, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field, model_validator
from websockets.exceptions import ConnectionClosed

from app.api.cloud_shell import _origin_allowed
from app.api.deps import get_token_info
from app.config import get_settings
from app.services import service_proxy, ws_ticket
from app.services.lumen_ingress import attach_lumen_ingress
from app.services.service_authorization import authorize_service_request

router = APIRouter()
_MAX_FRAME_BYTES = 64 * 1024
# Native Lumen's UTF-8 JSON message cap for an admitted image session (both directions).
_MAX_IMAGE_FRAME_BYTES = 2 * 1024 * 1024
# Lumen's application outcomes (4000-4999) and these standard codes reach the browser;
# anything else, including an abnormal upstream drop, becomes a generic 1011.
_RELAYED_CLOSE_CODES = frozenset({1000, 1001, 1008, 1011})
# RFC 6455 caps a close reason at 123 bytes of UTF-8.
_MAX_CLOSE_REASON_BYTES = 123


class _FrameTooLarge(ValueError):
    pass


def _exceeds_frame_limit(frame: str, limit: int) -> bool:
    return len(frame) > limit or (not frame.isascii() and len(frame.encode("utf-8")) > limit)


def _browser_close(code: int | None, reason: str) -> tuple[int, str]:
    """Bound Lumen's close code and reason; never relay unknown codes or their text."""
    if code is None or not (code in _RELAYED_CLOSE_CODES or 4000 <= code <= 4999):
        return 1011, ""
    return code, reason.encode()[:_MAX_CLOSE_REASON_BYTES].decode("utf-8", "ignore")


class SessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_id: str | None = Field(default=None, min_length=1, max_length=190)
    model_row_id: int | None = Field(default=None, strict=True, ge=1, le=2**63 - 1)
    provider_id: int | str | None = None
    kind: Literal["conversation", "transcription", "translation", "live"] = "conversation"
    voice: str | None = Field(default=None, max_length=100)
    instructions: str | None = Field(default=None, max_length=4096)
    output_language: str | None = Field(default=None, pattern=r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})?$")
    reasoning_effort: Literal["minimal", "low", "medium", "high", "xhigh"] | None = None
    max_duration_seconds: int = Field(default=300, ge=10, le=900)

    @model_validator(mode="after")
    def validate_session(self) -> SessionRequest:
        if self.model_id is None and self.model_row_id is None:
            raise ValueError("model_id or model_row_id is required")
        if self.kind == "translation":
            if self.output_language is None or self.voice is not None or self.instructions is not None:
                raise ValueError("Translation requires only an output language")
        elif self.output_language is not None:
            raise ValueError("Only translation accepts an output language")
        if self.kind != "conversation" and self.reasoning_effort is not None:
            raise ValueError("Only conversation accepts a reasoning effort")
        return self


@router.post("/realtime/sessions", status_code=201)
async def create_session(
    payload: SessionRequest,
    request: Request,
    idempotency_key: UUID = Header(alias="Idempotency-Key"),
    principal: dict = Depends(get_token_info),
):
    await authorize_service_request("lumen", request, "/v1/chat/realtime/sessions")
    logical_project = principal["project_id"]
    connection_project = principal.get("connection_project_id", logical_project)
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
    settings = get_settings()
    attach_lumen_ingress(headers, secret=settings.service_lumen_ingress_secret, method="POST", url=url)
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=5.0), verify=settings.ssl_verify) as client:
            # Older Lumen versions forbid newer optional keys even when null.
            optional = {"model_id", "model_row_id", "output_language", "reasoning_effort"}
            body = payload.model_dump(exclude={name for name in optional if getattr(payload, name) is None})
            response = await client.post(url, headers=headers, json=body)
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
        image_input = (
            payload.kind == "conversation"
            and data.get("realtime_image_input") is True
            and data.get("max_client_frame_bytes") == _MAX_IMAGE_FRAME_BYTES
        )
        result = {
            "session_id": session_id,
            "status": data["status"],
            "model_name": data["model_name"],
            "provider_type": data["provider_type"],
            "expires_in_seconds": ttl,
            "expires_at": (datetime.now(UTC) + timedelta(seconds=ttl)).isoformat(),
            "realtime_image_input": image_input,
        }
        ticket = await ws_ticket.issue_ticket(
            "chat-realtime",
            {
                "session_id": session_id,
                "connect_token": connect_token,
                "user_id": principal["user_id"],
                "project_id": logical_project,
                "realtime_image_input": image_input,
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
        frame_limit = _MAX_IMAGE_FRAME_BYTES if payload.get("realtime_image_input") is True else _MAX_FRAME_BYTES
    except (ValueError, KeyError, TypeError):
        await websocket.close(code=1013)
        return
    # Lumen's close frame, set only once the upstream side has ended.
    upstream_close: tuple[int | None, str] | None = None
    try:
        async with websockets.connect(
            ws_url,
            additional_headers={"x-realtime-token": token},
            max_size=frame_limit,
            # Enforce the size limit on the original message, not a truncated decompression result.
            compression=None,
            open_timeout=10,
            close_timeout=5,
        ) as upstream:
            await websocket.accept()

            async def browser_to_lumen():
                while True:
                    frame = await websocket.receive_text()
                    if _exceeds_frame_limit(frame, frame_limit):
                        raise _FrameTooLarge
                    await upstream.send(frame)

            async def lumen_to_browser():
                try:
                    async for frame in upstream:
                        if not isinstance(frame, str):
                            raise ValueError("Unexpected binary realtime frame")
                        if _exceeds_frame_limit(frame, frame_limit):
                            raise _FrameTooLarge
                        await websocket.send_text(frame)
                except ConnectionClosed as exc:
                    if exc.sent and exc.sent.code == 1009:
                        raise _FrameTooLarge from exc
                    raise

            lumen_task = asyncio.create_task(lumen_to_browser())
            tasks = {asyncio.create_task(browser_to_lumen()), lumen_task}
            try:
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED, timeout=960)
                for task in done:
                    try:
                        task.result()
                    except ConnectionClosed as exc:
                        upstream_close = (exc.rcvd.code, exc.rcvd.reason) if exc.rcvd else (None, "")
                    except WebSocketDisconnect:
                        pass
                    else:
                        if task is lumen_task:
                            # Iteration ends quietly on a normal close; the frame stays on the connection.
                            upstream_close = (upstream.close_code, upstream.close_reason or "")
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
    except _FrameTooLarge:
        with suppress(RuntimeError):
            await websocket.close(code=1009)
    except (ConnectionClosed, WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception:
        with suppress(RuntimeError):
            await websocket.close(code=1011)
    else:
        code, reason = _browser_close(*upstream_close) if upstream_close else (1000, "")
        with suppress(RuntimeError):
            await websocket.close(code=code, reason=reason)
