"""Sample only successful, fixed internal probes; retain every failure and business request."""

from __future__ import annotations

import logging
import re
import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send

# These exact source-owned route templates are operational traffic, never a URL
# prefix supplied by a caller. Request metrics still observe every invocation.
_SAMPLED_OPERATIONS = frozenset(
    {
        ("GET", "/api/v1/health"),
        ("HEAD", "/api/v1/health"),
        ("POST", "/api/v1/monitoring/traffic/events"),
        ("GET", "/api/v1/monitoring/host-observations/{host_id}/jobs"),
        ("HEAD", "/api/v1/monitoring/host-observations/{host_id}/jobs"),
        ("POST", "/api/v1/monitoring/host-observations/{host_id}/reports"),
    }
)
_SAMPLE_SECONDS = 60.0


class ProbeLogSampler:
    """Bounded per-process sampling, with explicit counts and no client identity."""

    def __init__(self) -> None:
        self._windows: dict[tuple[str, str], tuple[float, int]] = {}

    def observe(self, method: str, route: str, status: int, now: float) -> int | None:
        """Return observed successes in a sample, 1 for unsampled, None to omit.

        Unflushed successes can be lost on process termination: these samples are
        not a durable request counter. Failures neither consume nor reset a
        successful-probe window. The metrics path remains unsampled.
        """
        key = (method, route)
        if key not in _SAMPLED_OPERATIONS or not 200 <= status < 300:
            return 1
        last, count = self._windows.get(key, (now - _SAMPLE_SECONDS, 0))
        count += 1
        if now - last < _SAMPLE_SECONDS:
            self._windows[key] = (last, count)
            return None
        self._windows[key] = (now, 0)
        return count


probe_log_sampler = ProbeLogSampler()


def is_successful_probe(method: str, route: str | None, status: int) -> bool:
    return (method, route) in _SAMPLED_OPERATIONS and 200 <= status < 300


def log_request(
    logger: logging.Logger,
    method: str,
    route: str,
    status: int,
    duration_ms: float,
    request_id: str | None,
    *,
    sample_count: int = 1,
    transport_completed: bool | None = None,
) -> None:
    if not isinstance(request_id, str) or not re.fullmatch(r"req-[a-f0-9]{32}", request_id):
        request_id = None
    metadata = {
        "method": method,
        "path": route,
        "status": status,
        "duration_ms": round(duration_ms, 2),
        "log_sample_count": sample_count,
        "request_id": request_id,
    }
    if transport_completed is not None:
        metadata["transport_completed"] = transport_completed
    logger.log(logging.WARNING if transport_completed is False else logging.INFO, "request", extra=metadata)
    if logger.isEnabledFor(logging.DEBUG):
        outcome = (
            "transport_incomplete"
            if transport_completed is False
            else "server_error"
            if status >= 500
            else "client_error"
            if status >= 400
            else "completed"
        )
        logger.debug(
            "request diagnostic", extra={**metadata, "route_matched": route != "<unmatched>", "outcome": outcome}
        )


class ProbeCompletionLogMiddleware:
    """Sample fixed successful probes only after the ASGI send fully completes."""

    def __init__(self, app: ASGIApp):
        self.app = app
        self.logger = logging.getLogger("app.main")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        status = 500
        sent_final_body = False
        returned = False

        async def observe(message: Message) -> None:
            nonlocal status, sent_final_body
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                sent_final_body = True

        try:
            await self.app(scope, receive, observe)
            returned = True
        finally:
            method = scope.get("method", "")
            route = getattr(scope.get("route"), "path", None)
            if is_successful_probe(method, route, status):
                completed = returned and sent_final_body
                count = probe_log_sampler.observe(method, route, status, time.monotonic()) if completed else 1
                if count is not None:
                    state = scope.get("state", {})
                    request_id = state.get("request_id") or state.get("experience_request_id")
                    log_request(
                        self.logger,
                        method,
                        route,
                        status,
                        (time.perf_counter() - started) * 1000,
                        request_id,
                        sample_count=count,
                        transport_completed=completed,
                    )
