"""Authenticated proxy for browser-facing Waygate API routes."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from app.api.deps import get_token_info
from app.services.service_proxy import proxy

router = APIRouter(dependencies=[Depends(get_token_info)])

_PROXY_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]


@router.api_route("", methods=_PROXY_METHODS)
@router.api_route("/{path:path}", methods=_PROXY_METHODS)
async def proxy_waygate(path: str = "", *, request: Request) -> Response:
    upstream_path = "/v1/" if not path else f"/v1/{path}"
    return await proxy("waygate", request, upstream_path)
