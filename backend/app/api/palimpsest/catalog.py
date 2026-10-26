"""Exact native catalog reads and caller-project managed environment admission."""

from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.api.deps import require_admin
from app.api.palimpsest.packages import package_browser_identity, package_browser_request
from app.services import palimpsest_catalog as service
from app.services import palimpsest_catalog_consume as consumption

router = APIRouter()
admin_router = APIRouter()


class Origin(BaseModel):
    kind: Literal["build", "image-export", "registered", "unknown"]
    source: Literal[
        "hub-build", "dockerfile-inline", "github-dockerfile", "recipe", "glance", "upload-or-import", "unknown"
    ]
    evidence: Literal["recorded", "unrecorded"]
    build_id: str | None
    job_id: str | None
    revision: str | None


class Layer(BaseModel):
    id: str
    name: str
    blob_digest: str | None
    parent_id: str | None
    parent_digest: str | None
    kind: str
    arch: str | None
    ubuntu_base: str | None
    size_bytes: int | None = Field(ge=0)
    created_at: str | None
    project_id: str | None
    visibility: Literal["public", "site", "project", "shared", "private"]
    chain_complete: bool
    origin: Origin


class LayerPage(BaseModel):
    source: Literal["managed", "hub"]
    items: list[Layer]
    offset: int = Field(ge=0)
    has_more: bool
    next_offset: int | None


class LayerDetail(Layer):
    ancestors: list[Layer]
    children: list[Layer]
    children_has_more: bool
    bundles: list[str]


class Asset(BaseModel):
    id: str
    name: str
    kind: Literal["layer-bundle", "cloud-image"]
    blob_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    chain_id: str | None
    arch: str | None
    ubuntu_base: str | None
    size_bytes: int | None = Field(ge=0)
    created_at: str | None
    visibility: Literal["public", "site", "project", "shared"]
    layer_count: int = Field(ge=0)
    chain_complete: bool
    download_allowed: bool
    base_image_digest: str | None
    local_supported: bool
    local_reason: str | None


class AssetPage(BaseModel):
    items: list[Asset]
    offset: int = Field(ge=0)
    has_more: bool
    next_offset: int | None


class ConsumeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    flavor_id: str
    network_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._-]+$")
    key_name: str | None = None
    ssh_public_key: str | None = None
    server_name: str = Field(min_length=1, max_length=128)
    ssh_username: str | None = None

    @model_validator(mode="after")
    def validate_existing_consume_fields(self):
        from app.api.union.layer_ops import LayerConsumeRequest

        checked = LayerConsumeRequest(profile_name="catalog", **self.model_dump(exclude={"revision"}))
        for name in ("flavor_id", "key_name", "ssh_public_key", "server_name", "ssh_username"):
            setattr(self, name, getattr(checked, name))
        return self


def no_store(payload, *, status_code=200):
    return JSONResponse(payload, status_code=status_code, headers={"cache-control": "private, no-store"})


def query(request, allowed):
    if set(request.query_params) - allowed or any(
        len(request.query_params.getlist(k)) != 1 for k in request.query_params
    ):
        raise HTTPException(422, "Unexpected or duplicate catalog query parameter")


def checked_native(response, schema, *, offset=None, limit=None, identity=None):
    if response.status_code >= 400:
        return response
    try:
        result = schema.model_validate(json.loads(response.body), strict=True).model_dump()
        if offset is not None:
            if result["offset"] != offset or len(result["items"]) > limit:
                raise ValueError
            if schema is AssetPage:
                next_offset = result["next_offset"]
                if result["has_more"]:
                    if type(next_offset) is not int or not offset < next_offset <= offset + limit:
                        raise ValueError
                elif next_offset is not None:
                    raise ValueError
            else:
                expected = offset + len(result["items"]) if result["has_more"] else None
                if result["next_offset"] != expected or (result["has_more"] and not result["items"]):
                    raise ValueError
        if schema is LayerPage and result["source"] != "hub":
            raise ValueError
        if identity is not None and result["id"] != identity:
            raise ValueError
        return no_store(result)
    except (ValidationError, TypeError, ValueError) as exc:
        raise HTTPException(503, "Palimpsest Hub returned an invalid catalog response") from exc


async def admin_identity(request: Request):
    from app.api.deps import _resolve_jwt_token_info

    authorization = request.headers.get("authorization", "")
    if (
        not authorization.startswith("Bearer ")
        or authorization[7:].startswith("ppk_v1_")
        or request.headers.get("x-auth-token")
        or len(request.headers.getlist("authorization")) != 1
    ):
        raise HTTPException(401, "A browser access JWT is required")
    info = await _resolve_jwt_token_info(
        request, authorization[7:], request.headers.get("x-project-id"), preserve_original=True
    )
    info = await require_admin(info)
    request.state.token_info = info
    return info


async def admin_native_read(request, path, *, query=None):
    """Bounded original-human transport; projectless system scope stays projectless."""
    from app.api.palimpsest.hub import _require_palimpsest_enabled

    _require_palimpsest_enabled()
    from app.services.service_proxy import _configured_internal_endpoint, _package_endpoint, _package_request

    info = request.state.token_info
    if info.get("_live_system_admin") is not True or not info.get("token"):
        raise HTTPException(403, "Fresh human system authority is required")
    headers = {"x-auth-token": info["token"], "accept": "application/json"}
    project = info.get("connection_project_id", info.get("project_id"))
    if project:
        headers["x-project-id"] = project
    return await _package_request(
        request,
        path,
        endpoint=_package_endpoint(_configured_internal_endpoint("palimpsest")),
        headers=headers,
        method="GET",
        query=query,
        stream=False,
        forward_body=False,
    )


@admin_router.get("")
async def admin_catalog(
    request: Request,
    source: Literal["managed", "hub"] = "managed",
    q: str = Query("", max_length=128),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    info: dict = Depends(admin_identity),
):
    query(request, {"source", "q", "offset", "limit"})
    if source == "managed":
        return no_store(await service.managed_layers(q, offset, limit))
    response = await admin_native_read(
        request, "/v1/admin/catalog/layers", query={"q": q, "offset": str(offset), "limit": str(limit)}
    )
    return checked_native(response, LayerPage, offset=offset, limit=limit)


@admin_router.get("/{identity}")
async def admin_detail(
    request: Request, identity: str, source: Literal["managed", "hub"] = "managed", info: dict = Depends(admin_identity)
):
    query(request, {"source"})
    if source == "managed":
        return no_store(await service.managed_detail(identity))
    from app.services.palimpsest_digest import normalize_digest

    if normalize_digest(identity) != identity:
        raise HTTPException(422, "Hub layer ID must be a canonical SHA-256 digest")
    response = await admin_native_read(request, f"/v1/admin/catalog/layers/{identity}")
    return checked_native(response, LayerDetail, identity=identity)


@router.get("/assets")
async def assets(
    request: Request,
    q: str = Query("", max_length=128),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    info: dict = Depends(package_browser_identity),
):
    query(request, {"q", "offset", "limit"})
    response = await package_browser_request(
        request, "/v1/catalog/assets", query={"q": q, "offset": str(offset), "limit": str(limit)}
    )
    return checked_native(response, AssetPage, offset=offset, limit=limit)


@router.get("/environments")
async def environments(
    request: Request,
    q: str = Query("", max_length=128),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    info: dict = Depends(package_browser_identity),
):
    query(request, {"q", "offset", "limit"})
    from app.services.palimpsest_authorization import authorize_current_package_request

    await authorize_current_package_request(request, "/v1/catalog/assets", info)
    await consumption.require_action(info, "packages:inventory")
    return no_store(await service.environments(q, offset, limit))


# Static tracking route precedes the dynamic environment ID route.
@router.get("/environments/consumes/{consume_id}")
async def consume_status(request: Request, consume_id: int, info: dict = Depends(package_browser_identity)):
    query(request, set())
    from app.services.palimpsest_authorization import authorize_current_package_request

    await authorize_current_package_request(request, "/v1/catalog/assets", info)
    await consumption.require_action(info, "packages:inventory")
    return no_store(await service.consume_status(consume_id, info["project_id"]))


async def cleanup_identity(request: Request):
    """Native caller cleanup survives service disablement or leaf revocation."""
    from app.api.deps import _resolve_jwt_token_info, validate_keystone_id

    authorization = request.headers.get("authorization", "")
    if (
        not authorization.startswith("Bearer ")
        or authorization[7:].startswith("ppk_v1_")
        or request.headers.get("x-auth-token")
        or len(request.headers.getlist("authorization")) != 1
    ):
        raise HTTPException(401, "A browser access JWT is required")
    info = await _resolve_jwt_token_info(
        request, authorization[7:], request.headers.get("x-project-id"), preserve_original=True
    )
    info["project_id"] = validate_keystone_id(info.get("project_id"))
    info["user_id"] = validate_keystone_id(info.get("user_id"))
    request.state.token_info = info
    return info


@router.delete("/environments/consumes/{consume_id}")
async def cleanup_environment(request: Request, consume_id: int, info: dict = Depends(cleanup_identity)):
    query(request, set())
    from app.api.deps import get_os_conn
    from app.services.palimpsest_catalog_cleanup import cleanup_consume

    await consumption.current_writer(info)
    scope = get_os_conn(request, info)
    conn = await anext(scope)
    try:
        return no_store(await cleanup_consume(conn, consume_id, info))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(409, "Catalog cleanup remains uncertain; durable tracking is retained") from exc
    finally:
        await scope.aclose()


@router.post("/environments/{profile_id}/consume", status_code=202)
async def consume(
    request: Request, profile_id: int, spec: ConsumeRequest, info: dict = Depends(package_browser_identity)
):
    query(request, set())
    if profile_id <= 0:
        raise HTTPException(422, "Environment ID must be positive")
    return no_store(await consumption.admit(request, info, profile_id, spec), status_code=202)
