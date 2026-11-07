"""Server-Timing: total, authentication and handler phases are exposed without leaking data."""

import re
from unittest.mock import patch

import pytest
from fastapi import Depends, FastAPI, HTTPException, Response
from httpx import ASGITransport, AsyncClient

from app.api import deps
from app.main import request_logging_middleware


def _app() -> FastAPI:
    app = FastAPI()
    app.middleware("http")(request_logging_middleware)

    @app.get("/authed")
    async def authed(response: Response, info: dict = Depends(deps.get_token_info)):
        response.headers["Server-Timing"] = "inventories;dur=3.50"
        return {"user": info["user_id"]}

    @app.get("/open")
    async def open_route():
        return {"ok": True}

    return app


async def _get(path: str, headers: dict | None = None):
    async with AsyncClient(transport=ASGITransport(app=_app()), base_url="http://test") as ac:
        return await ac.get(path, headers=headers or {})


def _metrics(header: str) -> dict[str, float]:
    return {name: float(value) for name, value in re.findall(r"([a-z]+);dur=([0-9.]+)", header)}


@pytest.mark.asyncio
async def test_authenticated_response_splits_total_auth_and_handler_timing():
    async def resolve(*_args, **_kwargs):
        return {"user_id": "u1"}

    with patch.object(deps, "_resolve_jwt_token_info", resolve):
        response = await _get("/authed", {"Authorization": "Bearer jwt"})

    assert response.status_code == 200
    header = response.headers["Server-Timing"]
    assert [name for name, _ in re.findall(r"([a-z]+);dur=([0-9.]+)", header)] == ["app", "auth", "inventories"]
    metrics = _metrics(header)
    assert metrics["inventories"] == 3.5
    assert 0 <= metrics["auth"] <= metrics["app"]


@pytest.mark.asyncio
async def test_rejected_authentication_still_reports_its_cost():
    async def resolve(*_args, **_kwargs):
        raise HTTPException(status_code=401, detail="expired")

    with patch.object(deps, "_resolve_jwt_token_info", resolve):
        response = await _get("/authed", {"Authorization": "Bearer jwt"})

    assert response.status_code == 401
    assert set(_metrics(response.headers["Server-Timing"])) == {"app", "auth"}


@pytest.mark.asyncio
async def test_route_without_authentication_reports_only_the_total():
    response = await _get("/open")
    assert set(_metrics(response.headers["Server-Timing"])) == {"app"}
