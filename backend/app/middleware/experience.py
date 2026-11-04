"""ASGI transport evidence, without reading bodies or resolving any principal."""

from datetime import UTC, datetime
from uuid import uuid4

from anyio import CancelScope
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.services.experience_context import (
    _REQUEST_ID,
    capture_experience_context,
    capture_request_context,
    emit_experience,
    experience_enabled,
    experience_scope,
)

_EXCLUDED = (
    "/api/v1/activity",
    "/api/v1/admin/experiences",
    "/api/v1/monitoring/traffic",
    "/api/v1/admin/monitoring/traffic",
)


class ExperienceMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if (
            scope["type"] != "http"
            or not experience_enabled()
            or any(scope.get("path", "").startswith(path) for path in _EXCLUDED)
        ):
            await self.app(scope, receive, send)
            return
        started_at = datetime.now(UTC)
        request = Request(scope)
        existing = getattr(request.state, "request_id", None)
        request_id = existing if isinstance(existing, str) and _REQUEST_ID.fullmatch(existing) else "req-" + uuid4().hex
        context = capture_request_context(request, request_id, None)
        if context is None:
            await self.app(scope, receive, send)
            return
        request.state.experience_request_id = request_id
        finished = False
        completed = False
        status_code = None

        async def observed_send(message: Message):
            nonlocal finished, request_id, status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = list(message.get("headers", []))
                actual = next(
                    (
                        value.decode("ascii", errors="ignore")
                        for key, value in headers
                        if key.lower() == b"x-request-id"
                    ),
                    None,
                )
                if actual is not None and _REQUEST_ID.fullmatch(actual):
                    request_id = actual
                    context["request_id"] = actual
                elif actual is None:
                    captured = capture_experience_context()
                    request_id = captured["request_id"] if captured and captured.get("request_id") else request_id
                    headers.append((b"x-request-id", request_id.encode("ascii")))
                    message = {**message, "headers": headers}
            await send(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                finished = True

        with experience_scope(context, request=request):
            try:
                await self.app(scope, receive, observed_send)
                completed = True
            finally:
                completed_at = datetime.now(UTC)
                # Final actor is the already verified dependency/audit state.
                final = capture_experience_context()
                if final is not None:
                    final["request_id"] = request_id
                with CancelScope(shield=True):
                    await emit_experience(
                        final, "request.started", stage="request", status="observed", occurred_at=started_at
                    )
                    transport_complete = completed and finished and status_code is not None
                    status = (
                        "failed"
                        if transport_complete and status_code >= 400
                        else "observed"
                        if transport_complete
                        else "outcome_unknown"
                    )
                    await emit_experience(
                        final,
                        "request.completed",
                        stage="request",
                        status=status,
                        reason="transport_complete" if transport_complete else "transport_incomplete",
                        occurred_at=completed_at,
                        http_status=status_code,
                    )
