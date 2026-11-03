"""Copied source provenance and signed credentials must never enter shared caches."""

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_token_info
from app.api.lumen import proxy as proxy_module


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["assets/asset-a/download-link", "runs/run-a/sources/source-a"])
@pytest.mark.parametrize("denied", [False, True])
async def test_private_source_response_overrides_cache_policy(monkeypatch, path, denied):
    app = FastAPI()
    app.include_router(proxy_module.router, prefix="/api/v1/chat")

    async def principal(request: Request):
        if denied:
            raise HTTPException(status_code=403, detail="Current project permission was revoked")
        request.state.token_info = {"user_id": "user-a", "project_id": "project-a"}
        return request.state.token_info

    async def upstream(*args, **kwargs):
        return JSONResponse({"title": "Private project source"}, headers={"Cache-Control": "public, max-age=3600"})

    app.dependency_overrides[get_token_info] = principal
    monkeypatch.setattr(proxy_module, "proxy", upstream)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://app.example") as client:
        response = await client.get(f"/api/v1/chat/{path}")
    assert response.status_code == (403 if denied else 200)
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
