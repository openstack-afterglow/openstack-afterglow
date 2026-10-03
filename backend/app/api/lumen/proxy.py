"""Authenticated proxy for browser-facing Lumen API routes."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from app.api.deps import get_token_info
from app.services.service_proxy import proxy

router = APIRouter(dependencies=[Depends(get_token_info)])

_PROXY_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]


@router.api_route("", methods=_PROXY_METHODS)
@router.api_route("/{path:path}", methods=_PROXY_METHODS)
async def proxy_lumen(path: str = "", *, request: Request) -> Response:
    if path == "models":
        upstream_path = "/v1/chat/models"
    elif path in {
        "images/generations",
        "images/edits",
        "audio/speech",
        "audio/transcriptions",
    }:
        upstream_path = f"/v1/chat/{path}"
    else:
        upstream_path = "/v1" if not path else f"/v1/{path}"
    if path in {"audio/speech", "audio/transcriptions"}:
        # Native audio waits for a durable run before its first response byte.
        return await proxy("lumen", request, upstream_path, read_timeout=310.0)
    return await proxy("lumen", request, upstream_path)
