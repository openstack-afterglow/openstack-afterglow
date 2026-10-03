"""Structured API and background-operation logging must never echo user input."""

import logging
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from app.main import (
    _JSONFormatter,
    app,
    request_logging_middleware,
    sanitized_http_exception_handler,
    unhandled_exception_handler,
)
from app.services.layer_build import run_layer_build


@pytest.mark.asyncio
async def test_request_completion_has_template_and_no_input_on_success_or_failure(caplog):
    secret = "dont-log-this-password"
    api = FastAPI()
    api.middleware("http")(request_logging_middleware)
    api.add_exception_handler(HTTPException, sanitized_http_exception_handler)
    api.add_exception_handler(Exception, unhandled_exception_handler)

    @api.get("/items/{item_id}")
    async def get_item(item_id: str):
        return {"id": item_id}

    @api.get("/bad/{item_id}")
    async def bad(item_id: str):
        raise HTTPException(400, detail=secret)

    @api.post("/fail/{item_id}")
    async def fail(item_id: str):
        raise RuntimeError(secret)

    with caplog.at_level(logging.INFO):
        async with AsyncClient(
            transport=ASGITransport(app=api, raise_app_exceptions=False), base_url="http://test"
        ) as client:
            requests = (
                await client.get(f"/items/{secret}?access_token={secret}"),
                await client.get(f"/bad/{secret}?access_token={secret}"),
                await client.post(f"/fail/{secret}?access_token={secret}", json={"password": secret}),
                await client.get(f"/unknown/{secret}?access_token={secret}"),
            )

    assert [response.status_code for response in requests] == [200, 400, 500, 404]
    records = [r for r in caplog.records if r.name == "app.main" and r.msg == "request"]
    assert [(r.path, r.status) for r in records] == [
        ("/items/{item_id}", 200),
        ("/bad/{item_id}", 400),
        ("/fail/{item_id}", 500),
        ("<unmatched>", 404),
    ]
    assert all(r.levelno == logging.INFO and r.duration_ms >= 0 for r in records)
    assert secret not in "\n".join(_JSONFormatter().format(record) for record in caplog.records)


@pytest.mark.asyncio
async def test_health_request_is_logged(caplog):
    with caplog.at_level(logging.INFO):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert any(r.msg == "request" and r.path == "/api/v1/health" and r.status == 200 for r in caplog.records)


@pytest.mark.asyncio
async def test_build_execution_info_and_debug_are_bounded_and_sanitized(caplog):
    secret = "secret-index-credential"

    async def run():
        with patch("app.services.layer_build._update_build_db", new_callable=AsyncMock):
            await run_layer_build(
                build_db_id=123,
                layer_name=secret,
                kind="pip",
                python_version=None,
                pip_packages=[secret],
                pip_index_url=f"https://{secret}@example.test/simple",
                parent_artifact_id=None,
            )

    with caplog.at_level(logging.INFO):
        await run()
    events = [r for r in caplog.records if r.name == "app.services.layer_build" and r.msg == "execution"]
    assert [(r.state, getattr(r, "result", None)) for r in events] == [("started", None), ("completed", "failed")]
    assert not any(r.msg == "execution metadata" for r in caplog.records)
    assert secret not in "\n".join(_JSONFormatter().format(r) for r in caplog.records)

    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        await run()
    metadata = [r for r in caplog.records if r.name == "app.services.layer_build" and r.msg == "execution metadata"]
    assert [(r.state, r.query) for r in metadata] == [
        ("validating", "recipe_contract"),
        ("completed", "recipe_contract"),
    ]
    assert metadata[0].pip_package_count == 1
    assert metadata[-1].result == "failed"
    assert secret not in "\n".join(_JSONFormatter().format(r) for r in caplog.records)
