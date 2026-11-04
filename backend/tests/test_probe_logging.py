"""Successful internal probes may be sampled; failures and metrics may not."""

import logging

import pytest
from fastapi import FastAPI
from fastapi.responses import Response
from httpx import ASGITransport, AsyncClient

from app.api.common.metrics import REQUEST_COUNT
from app.utils import request_logging
from app.utils.request_logging import ProbeCompletionLogMiddleware, ProbeLogSampler


def test_probe_window_counts_only_successes_and_keeps_boundary_failures():
    sampler = ProbeLogSampler()
    route = "/api/v1/health"
    assert sampler.observe("GET", route, 200, 0) == 1
    assert sampler.observe("GET", route, 200, 1) is None
    assert sampler.observe("GET", route, 503, 2) == 1
    assert sampler.observe("GET", route, 200, 59.999) is None
    assert sampler.observe("GET", route, 200, 60) == 3
    assert sampler.observe("GET", route, 401, 60.1) == 1
    assert sampler.observe("GET", route, 200, 60.2) is None
    assert sampler.observe("GET", route, 200, 120) == 2


def test_only_exact_probe_operations_are_sampled():
    sampler = ProbeLogSampler()
    for now in (0, 1, 2):
        assert sampler.observe("GET", "/api/v1/health/details", 200, now) == 1
        assert sampler.observe("POST", "/api/v1/health", 200, now) == 1
        assert sampler.observe("GET", "/api/v1/instances", 200, now) == 1
        assert sampler.observe("GET", "<unmatched>", 200, now) == 1
    assert sampler.observe("POST", "/api/v1/monitoring/traffic/events", 200, 0) == 1
    assert sampler.observe("POST", "/api/v1/monitoring/traffic/events", 200, 1) is None
    reports = "/api/v1/monitoring/host-observations/{host_id}/reports"
    assert sampler.observe("POST", reports, 202, 0) == 1
    assert sampler.observe("POST", reports, 202, 1) is None
    assert sampler.observe("POST", reports, 503, 2) == 1


@pytest.mark.asyncio
async def test_failed_probes_remain_visible_and_metrics_keep_unsampled_denominator(caplog, monkeypatch):
    from app import main

    monkeypatch.setattr(request_logging, "probe_log_sampler", ProbeLogSampler())
    api = FastAPI()
    api.middleware("http")(main.request_logging_middleware)
    api.add_middleware(ProbeCompletionLogMiddleware)

    @api.get("/api/v1/health")
    async def health(fail: bool = False):
        return Response(status_code=503 if fail else 200)

    success = REQUEST_COUNT.labels(method="GET", path="/api/v1/health", status="200")
    failure = REQUEST_COUNT.labels(method="GET", path="/api/v1/health", status="503")
    before_success, before_failure = success._value.get(), failure._value.get()
    with caplog.at_level(logging.DEBUG, logger="app.main"):
        async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
            statuses = [(await client.get("/api/v1/health")).status_code for _ in range(5)]
            statuses += [(await client.get("/api/v1/health?fail=true")).status_code for _ in range(2)]
    assert statuses == [200] * 5 + [503] * 2
    records = [record for record in caplog.records if record.name == "app.main" and record.msg == "request"]
    assert [record.status for record in records] == [200, 503, 503]
    assert [record.status for record in caplog.records if record.msg == "request diagnostic"] == [200, 503, 503]
    assert success._value.get() - before_success == 5
    assert failure._value.get() - before_failure == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["raised", "unfinished", "send_failure", "cancelled"])
async def test_success_headers_never_hide_a_failed_or_cancelled_probe_body(caplog, monkeypatch, failure):
    import asyncio
    from types import SimpleNamespace

    monkeypatch.setattr(request_logging, "probe_log_sampler", ProbeLogSampler())
    mode = "complete"
    waiting = asyncio.Event()
    secret = b"private-probe-body-canary"

    async def app(scope, _receive, send):
        scope["route"] = SimpleNamespace(path="/api/v1/health")
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": secret, "more_body": True})
        if mode == "raised":
            raise RuntimeError("private-exception-canary")
        if mode == "unfinished":
            return
        if mode == "cancelled":
            waiting.set()
            await asyncio.Event().wait()
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    async def receive():
        return {"type": "http.request", "body": b""}

    async def send(message):
        if mode == "send_failure" and message["type"] == "http.response.body" and not message.get("more_body", False):
            raise OSError("private-send-canary")

    middleware = ProbeCompletionLogMiddleware(app)

    def scope():
        return {"type": "http", "method": "GET", "state": {}}

    with caplog.at_level(logging.INFO, logger="app.main"):
        await middleware(scope(), receive, send)
        mode = failure
        if failure == "unfinished":
            await middleware(scope(), receive, send)
        elif failure == "cancelled":
            task = asyncio.create_task(middleware(scope(), receive, send))
            await waiting.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            with pytest.raises(RuntimeError if failure == "raised" else OSError):
                await middleware(scope(), receive, send)
    records = [record for record in caplog.records if record.name == "app.main" and record.msg == "request"]
    assert [(record.status, record.transport_completed) for record in records] == [(200, True), (200, False)]
    assert records[-1].levelno == logging.WARNING
    assert "private-" not in caplog.text
