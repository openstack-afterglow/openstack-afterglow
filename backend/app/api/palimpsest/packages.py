"""Project-fenced browser reads/control for the native Hub package registry."""

from __future__ import annotations

import json
import re
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from app.api.deps import _resolve_jwt_token_info, validate_keystone_id
from app.api.palimpsest.hub import _require_palimpsest_enabled
from app.api.palimpsest.package_protocol import PackageRoute, native_error
from app.services.service_proxy import package_member_request

router = APIRouter(route_class=PackageRoute)
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_NAMESPACE = re.compile(r"[a-z0-9]+(?:(?:[._]|__|-+)[a-z0-9]+)*\Z")
_PACKAGE = re.compile(r"[a-z0-9]+(?:(?:[._]|__|-+)[a-z0-9]+)*(?:/[a-z0-9]+(?:(?:[._]|__|-+)[a-z0-9]+)*)*\Z")
_TAG = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}\Z")


async def package_browser_identity(request: Request) -> dict:
    _require_palimpsest_enabled()
    authorization = request.headers.get("authorization", "")
    if (
        not authorization.startswith("Bearer ")
        or authorization[7:].startswith("ppk_v1_")
        or request.headers.get("x-auth-token")
        or len(request.headers.getlist("authorization")) != 1
    ):
        raise HTTPException(status_code=401, detail="A browser access JWT is required")
    try:
        info = await _resolve_jwt_token_info(
            request, authorization[7:], request.headers.get("x-project-id"), preserve_original=True
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Package identity validation is unavailable") from exc
    info["project_id"] = validate_keystone_id(info.get("project_id"))
    info["user_id"] = validate_keystone_id(info.get("user_id"))
    request.state.token_info = info
    return info


def checked_payload(response: Response, info: dict, namespace: str | None = None, *, keys: bool = False) -> dict:
    try:
        payload = json.loads(response.body)
        if not isinstance(payload, dict):
            raise ValueError
        if keys:
            if "key" in payload:
                if set(payload) != {"key", "secret"} or not isinstance(payload["secret"], str):
                    raise ValueError
            elif not isinstance(payload.get("items"), list) or {"secret", "secret_hash", "token"} & payload.keys():
                raise ValueError
        objects = [payload]
        if keys and "key" in payload:
            objects = [payload["key"]]
        elif "items" in payload:
            if not isinstance(payload["items"], list):
                raise ValueError
            objects.extend(payload["items"])
        for item in objects:
            if not isinstance(item, dict) or validate_keystone_id(item.get("project_id")) != info["project_id"]:
                raise ValueError
            if namespace is not None and item.get("namespace") != namespace:
                raise ValueError
            if keys and {"secret", "secret_hash", "token"} & item.keys():
                raise ValueError
            if keys and item is not payload and validate_keystone_id(item.get("owner_user_id")) != info["user_id"]:
                raise ValueError
        if keys and "key" in payload and validate_keystone_id(payload["key"].get("owner_user_id")) != info["user_id"]:
            raise ValueError
        return payload
    except (ValueError, TypeError, HTTPException) as exc:
        raise HTTPException(
            status_code=503, detail="Palimpsest Hub returned an inconsistent ownership response"
        ) from exc


def checked_context(response: Response, info: dict) -> dict:
    payload = checked_payload(response, info)
    if "namespace" not in payload or not isinstance(payload.get("project_name"), str):
        raise HTTPException(status_code=503, detail="Palimpsest Hub returned an invalid project context")
    capabilities = payload.get("capabilities")
    if not isinstance(capabilities, dict) or any(
        not isinstance(capabilities.get(key), bool) for key in ("packages_read", "packages_write", "keys_issue")
    ):
        raise HTTPException(status_code=503, detail="Palimpsest Hub returned invalid project capabilities")
    namespace = payload["namespace"]
    if namespace is not None and (
        not isinstance(namespace, str) or len(namespace) > 63 or not _NAMESPACE.fullmatch(namespace)
    ):
        raise HTTPException(status_code=503, detail="Palimpsest Hub returned an invalid namespace")
    if "package_authority" not in payload:
        raise HTTPException(status_code=503, detail="Palimpsest Hub reference authority is unavailable")
    authority = payload["package_authority"]
    if authority is None:
        # Explicitly unconfigured copy authority is not a guessed reference host.
        return payload
    try:
        if not isinstance(authority, str) or not re.fullmatch(r"[A-Za-z0-9.\[\]:-]{1,255}", authority):
            raise ValueError
        parsed = urlsplit("https://" + authority)
        if (
            parsed.netloc != authority
            or not parsed.hostname
            or parsed.path
            or parsed.query
            or parsed.fragment
            or parsed.username is not None
            or parsed.password is not None
            or (parsed.port is not None and not 1 <= parsed.port <= 65535)
        ):
            raise ValueError
    except ValueError as exc:
        raise HTTPException(status_code=503, detail="Palimpsest Hub reference authority is unavailable") from exc
    return payload


async def project_context(request: Request, info: dict) -> tuple[Response, dict | None]:
    response = await package_member_request(request, "/v1/projects/current")
    if response.status_code >= 400:
        return response, None
    payload = checked_context(response, info)
    namespace = payload["namespace"]
    requested = request.query_params.get("namespace")
    if requested is not None and requested != namespace:
        return native_error(403, "PROJECT_SCOPE_MISMATCH", "Namespace differs from the current project"), None
    return response, payload


async def current_namespace(request: Request, info: dict) -> tuple[str | None, Response | None]:
    response, context = await project_context(request, info)
    if context is None:
        return None, response
    namespace = context.get("namespace")
    if namespace is None:
        return None, native_error(409, "NAMESPACE_UNREGISTERED", "Register the current project's namespace first")
    return namespace, None


def read_query(request: Request, allowed: set[str], *, package_required: bool = False) -> dict[str, str]:
    if set(request.query_params) - allowed - {"namespace"}:
        raise HTTPException(status_code=422, detail="Unexpected package query parameter")
    if any(len(request.query_params.getlist(key)) != 1 for key in request.query_params):
        raise HTTPException(status_code=422, detail="Duplicate package query parameter")
    query = {key: value for key, value in request.query_params.items() if key in allowed}
    if package_required:
        package = query.get("package", "")
        if not _PACKAGE.fullmatch(package) or len(package) > 253:
            raise HTTPException(status_code=422, detail="A canonical package name is required")
    if "tag" in allowed and "tag" not in query:
        raise HTTPException(status_code=422, detail="A tag is required")
    if "tag" in query and not _TAG.fullmatch(query["tag"]):
        raise HTTPException(status_code=422, detail="Invalid tag")
    if "limit" in query and (not query["limit"].isdigit() or not 1 <= int(query["limit"]) <= 100):
        raise HTTPException(status_code=422, detail="Limit must be between 1 and 100")
    if "package_type" in query and query["package_type"] not in {"oci-image", "runtime-bundle"}:
        raise HTTPException(status_code=422, detail="Invalid package type")
    return query


@router.get("/context")
async def context(request: Request, info: dict = Depends(package_browser_identity)) -> Response:
    read_query(request, set())
    response, _ = await project_context(request, info)
    return response


@router.put("/namespace")
async def register_namespace(request: Request, info: dict = Depends(package_browser_identity)) -> Response:
    read_query(request, set())
    if "namespace" in request.query_params:
        raise HTTPException(status_code=422, detail="Namespace registration does not accept a namespace selector")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > 64:
            raise HTTPException(status_code=422, detail="Namespace registration takes an empty body")
        body.extend(chunk)
    if bytes(body).strip() not in {b"", b"{}"}:
        raise HTTPException(status_code=422, detail="Namespace registration takes an empty body")
    response = await package_member_request(request, f"/v1/projects/{info['project_id']}/namespace", method="PUT")
    if response.status_code < 400:
        payload = checked_context(response, info)
        if payload["namespace"] is None:
            raise HTTPException(status_code=503, detail="Palimpsest Hub did not register the namespace")
    return response


async def scoped_read(request: Request, info: dict, suffix: str, query: dict[str, str]) -> Response:
    namespace, failure = await current_namespace(request, info)
    if failure is not None:
        return failure
    if "package" in query and len(f"{namespace}/{query['package']}") > 255:
        raise HTTPException(status_code=422, detail="Package reference exceeds 255 characters")
    response = await package_member_request(request, f"/v1/projects/{namespace}/{suffix}", query=query)
    if response.status_code < 400:
        payload = checked_payload(response, info, namespace)
        if "package" in query:
            returned = payload.get("name") if suffix == "package" else payload.get("package")
            if returned != query["package"]:
                raise HTTPException(status_code=503, detail="Palimpsest Hub returned the wrong package")
            for item in payload.get("items", []):
                if item.get("package") != query["package"]:
                    raise HTTPException(status_code=503, detail="Palimpsest Hub returned the wrong package version")
        if suffix.startswith("versions/") and payload.get("root_digest") != suffix.split("/", 1)[1]:
            raise HTTPException(status_code=503, detail="Palimpsest Hub returned the wrong version")
        if suffix == "resolve" and (
            payload.get("tag") != query["tag"] or not _DIGEST.fullmatch(str(payload.get("digest", "")))
        ):
            raise HTTPException(status_code=503, detail="Palimpsest Hub returned the wrong tag resolution")
    return response


@router.get("")
async def inventory(request: Request, info: dict = Depends(package_browser_identity)) -> Response:
    return await scoped_read(request, info, "packages", read_query(request, {"limit", "cursor", "package_type"}))


@router.get("/detail")
async def detail(request: Request, info: dict = Depends(package_browser_identity)) -> Response:
    return await scoped_read(request, info, "package", read_query(request, {"package"}, package_required=True))


@router.get("/resolve")
async def resolve(request: Request, info: dict = Depends(package_browser_identity)) -> Response:
    return await scoped_read(request, info, "resolve", read_query(request, {"package", "tag"}, package_required=True))


@router.get("/versions")
async def versions(request: Request, info: dict = Depends(package_browser_identity)) -> Response:
    query = read_query(request, {"package", "limit", "cursor"}, package_required=True)
    return await scoped_read(request, info, "versions", query)


@router.get("/versions/{digest}")
async def version(digest: str, request: Request, info: dict = Depends(package_browser_identity)) -> Response:
    if not _DIGEST.fullmatch(digest):
        raise HTTPException(status_code=422, detail="Invalid version digest")
    query = read_query(request, {"package"}, package_required=True)
    return await scoped_read(request, info, f"versions/{digest}", query)


@router.get("/versions/{digest}/download")
async def download(digest: str, request: Request, info: dict = Depends(package_browser_identity)) -> Response:
    if not _DIGEST.fullmatch(digest):
        raise HTTPException(status_code=422, detail="Invalid version digest")
    query = read_query(request, {"package"}, package_required=True)
    namespace, failure = await current_namespace(request, info)
    if failure is not None:
        return failure
    path = f"/v1/projects/{namespace}/versions/{digest}"
    metadata = await package_member_request(request, path, query=query)
    if metadata.status_code >= 400:
        return metadata
    payload = checked_payload(metadata, info, namespace)
    if payload.get("root_digest") != digest or payload.get("package") != query["package"]:
        raise HTTPException(status_code=503, detail="Palimpsest Hub returned the wrong version")
    return await package_member_request(request, f"{path}/download", query=query, stream=True)
