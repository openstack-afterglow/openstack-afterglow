"""Pass-through ASGI observation: no buffering, body reads, headers or URL retention."""

import time
from uuid import uuid4

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import get_settings
from app.models.traffic_analytics import TrafficEvent
from app.rate_limit import _get_real_ip
from app.services.traffic_analytics import record_event, route_category

EXCLUDED = ("/api/v1/monitoring/traffic", "/api/v1/admin/monitoring/traffic")


class TrafficAnalyticsMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        path = scope.get("path", "")
        if (
            scope["type"] != "http"
            or not get_settings().traffic_analytics.enabled
            or any(path == prefix or path.startswith(prefix + "/") for prefix in EXCLUDED)
        ):
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        at = time.time()
        request_bytes = 0
        response_bytes = 0
        request_complete = False
        response_complete = False
        status = 500

        async def observed_receive() -> Message:
            nonlocal request_bytes, request_complete
            message = await receive()
            if message["type"] == "http.request":
                request_bytes += len(message.get("body", b""))
                if not message.get("more_body", False):
                    request_complete = True
            return message

        async def observed_send(message: Message):
            nonlocal response_bytes, response_complete, status
            await send(message)
            if message["type"] == "http.response.start":
                status = message["status"]
            elif message["type"] == "http.response.body":
                response_bytes += len(message.get("body", b""))
                if not message.get("more_body", False):
                    response_complete = True

        try:
            await self.app(scope, observed_receive, observed_send)
        finally:
            # ASGI exceptions/cancellation must propagate unchanged. Analytics must
            # not replace a successful response or mask an application's exception.
            try:
                route = scope.get("route")
                client_ip = _get_real_ip(Request(scope))
                try:
                    import ipaddress

                    client_ip = str(ipaddress.ip_address(client_ip))
                except ValueError:
                    client_ip = None
                event = TrafficEvent(
                    id=uuid4(),
                    at=at,
                    status=status,
                    route=route_category(getattr(route, "path", None), "backend"),
                    client_ip=client_ip,
                    request_bytes=request_bytes if request_complete and request_bytes <= 2**40 else None,
                    response_bytes=response_bytes if response_complete and response_bytes <= 2**40 else None,
                    latency_ms=min((time.perf_counter() - started) * 1000, 86_400_000),
                )
                await record_event(event, "backend")
            except Exception:
                # Never log event data or change request behavior on metrics failure.
                pass
