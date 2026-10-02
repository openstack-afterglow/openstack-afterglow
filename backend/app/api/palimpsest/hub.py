"""BFF Proxy router for extracted Palimpsest Hub service routes."""

import re

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from app.api.deps import get_token_info
from app.api.palimpsest.package_protocol import PackageRoute, native_error
from app.config import get_settings
from app.services.service_proxy import package_key_proxy, proxy, proxy_unauthenticated

router = APIRouter(route_class=PackageRoute)

_PROXY_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]

# Only established pre-package Hub families may use ordinary browser rescope.
# Native project/key/cache control belongs to the dedicated browser BFF or ppk gateway.
_LEGACY_ROUTE_ROOTS = frozenset({"health", "layers", "images", "image-exports", "uploads", "bundles", "builds"})


def _require_palimpsest_enabled() -> None:
    if not get_settings().service_palimpsest_enabled:
        raise HTTPException(status_code=503, detail="palimpsest 서비스를 사용할 수 없습니다")


@router.api_route(
    "/image-exports/{export_id}/download",
    methods=["GET"],
    dependencies=[Depends(_require_palimpsest_enabled)],
)
async def proxy_palimpsest_token_download(export_id: str, request: Request) -> Response:
    if request.headers.get("authorization", "").lower().startswith("bearer ppk_v1_"):
        return native_error(403, "ACTION_DENIED", "Package keys cannot access export tickets")
    return await proxy_unauthenticated("palimpsest", request, f"/v1/image-exports/{export_id}/download")


@router.api_route(
    "",
    methods=_PROXY_METHODS,
    dependencies=[Depends(_require_palimpsest_enabled)],
)
@router.api_route(
    "/{path:path}",
    methods=_PROXY_METHODS,
    dependencies=[Depends(_require_palimpsest_enabled)],
)
async def proxy_palimpsest_hub(path: str = "", *, request: Request) -> Response:
    authorization = request.headers.get("authorization", "")
    if len(request.headers.getlist("authorization")) > 1:
        raise HTTPException(status_code=401, detail="Ambiguous authorization credentials")
    if authorization.lower().startswith("bearer ppk_v1_"):
        if len(request.headers.getlist("authorization")) != 1 or request.headers.get("x-auth-token"):
            return native_error(401, "AUTH_REQUIRED", "Ambiguous package credentials")
        if not _key_route_allowed(request.method, path):
            return native_error(403, "ACTION_DENIED", "Package keys cannot access this Hub route")
        return await package_key_proxy(request, f"/v1/{path}")
    if request.headers.get("x-auth-token"):
        raise HTTPException(status_code=401, detail="Keystone credentials are not accepted by this gateway")
    segments = path.split("/")
    if path and (segments[0] not in _LEGACY_ROUTE_ROOTS or any(segment in {".", ".."} for segment in segments)):
        return native_error(403, "ACTION_DENIED", "Native Hub routes require dedicated package credentials")
    await get_token_info(request, authorization=authorization, x_project_id=request.headers.get("x-project-id"))
    upstream_path = "/v1/" if not path else f"/v1/{path}"
    return await proxy("palimpsest", request, upstream_path)


_NAMESPACE = r"[a-z0-9]+(?:(?:[._]|__|-+)[a-z0-9]+)*"
_DIGEST = r"sha256:[0-9a-f]{64}"
_SESSION = r"[0-9a-f]{32}|[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}"
_KEY_ROUTES = (
    ({"GET"}, r"auth/me"),
    ({"GET"}, rf"projects/{_NAMESPACE}/(?:packages|package|versions|resolve)"),
    ({"GET"}, rf"projects/{_NAMESPACE}/versions/{_DIGEST}(?:/download|/blobs/{_DIGEST})?"),
    ({"POST"}, rf"projects/{_NAMESPACE}/uploads"),
    ({"GET", "PATCH", "PUT", "DELETE"}, rf"projects/{_NAMESPACE}/uploads/(?:{_SESSION})"),
    ({"GET"}, rf"projects/{_NAMESPACE}/cache/(?:resolve|archives/{_DIGEST})"),
    ({"POST"}, rf"projects/{_NAMESPACE}/cache/uploads"),
    ({"GET", "PATCH", "PUT", "DELETE"}, rf"projects/{_NAMESPACE}/cache/uploads/(?:{_SESSION})"),
)


def _key_route_allowed(method: str, path: str) -> bool:
    return any(method in methods and re.fullmatch(pattern, path) for methods, pattern in _KEY_ROUTES)
