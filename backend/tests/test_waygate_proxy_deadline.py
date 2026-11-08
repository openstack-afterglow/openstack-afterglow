"""Waygate provisioning writes outlive the generic 30s upstream read deadline."""

import pytest
from starlette.requests import Request

from app.api.waygate import proxy as waygate_proxy


def _request(method: str) -> Request:
    return Request({"type": "http", "method": method, "path": "/", "headers": [], "query_string": b""})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "expected"),
    [
        ("GET", None),
        ("HEAD", None),
        ("OPTIONS", None),
        ("POST", 55.0),
        ("PATCH", 55.0),
        ("PUT", 55.0),
        ("DELETE", 55.0),
    ],
)
async def test_only_writes_get_the_extended_upstream_deadline(monkeypatch, method, expected):
    seen = {}

    async def fake_proxy(service, request, upstream_path, *, read_timeout=None):
        seen.update(service=service, path=upstream_path, read_timeout=read_timeout)
        return "ok"

    monkeypatch.setattr(waygate_proxy, "proxy", fake_proxy)
    assert await waygate_proxy.proxy_waygate("servers", request=_request(method)) == "ok"
    assert seen == {"service": "waygate", "path": "/v1/servers", "read_timeout": expected}
