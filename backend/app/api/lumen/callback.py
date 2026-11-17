"""Unauthenticated proxy for browser-facing Lumen MCP OAuth callback."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from app.services.service_proxy import proxy_passthrough

router = APIRouter()
_NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


@router.get("/mcp-oauth/callback")
async def proxy_lumen_mcp_oauth_callback(*, request: Request) -> Response:
    try:
        response = await proxy_passthrough("lumen", request, "/v1/mcp-oauth/callback", forward_cookie=True)
    except HTTPException as exc:
        exc.headers = {**(exc.headers or {}), **_NO_STORE}
        raise
    response.headers.update(_NO_STORE)
    return response
