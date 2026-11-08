"""Authenticated proxy for browser-facing Waygate API routes."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from app.api.deps import get_token_info
from app.services.service_proxy import proxy

router = APIRouter(dependencies=[Depends(get_token_info)])

_PROXY_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]
# Provisioning writes create a Trust, a VM and ports; observed 25-33s. Reads keep the 30s default.
_WRITE_READ_TIMEOUT = 55.0
_READ_ONLY_METHODS = {"GET", "HEAD", "OPTIONS"}


@router.api_route("", methods=_PROXY_METHODS)
@router.api_route("/{path:path}", methods=_PROXY_METHODS)
async def proxy_waygate(path: str = "", *, request: Request) -> Response:
    upstream_path = "/v1/" if not path else f"/v1/{path}"
    read_timeout = None if request.method in _READ_ONLY_METHODS else _WRITE_READ_TIMEOUT
    return await proxy("waygate", request, upstream_path, read_timeout=read_timeout)
