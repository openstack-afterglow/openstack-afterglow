"""Exact native Hub browser action gates; package credentials remain native.

The central browser guard supplies a current, project-bound principal. Native
Hub still validates the original token, protected identities, ownership, key
scope and action ceilings. No service leaf grants global builder/GC authority.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Mapping

from fastapi import HTTPException, Request

from app.services.service_permissions import require_service_permission, service_permissions

_INVENTORY = "palimpsest-inventory_reader"
_DOWNLOAD = "palimpsest-download_user"
_PUBLISH = "palimpsest-publish_editor"
_KEYS_EDITOR = "palimpsest-keys_editor"
_KEYS_ADMIN = "palimpsest-keys_admin"
_NAMESPACE = r"[a-z0-9]+(?:(?:[._]|__|-+)[a-z0-9]+)*"
_DIGEST = r"sha256:[0-9a-f]{64}"
_ID = r"(?:[0-9a-f]{32}|[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})"

# Methods are native operations, not a read/write heuristic: upload status is
# publish authority, whereas POST /bundles exports bytes and requires download.
_LEGACY = (
    ({"GET"}, rf"/(?:layers|images|image-exports)|/layers/{_DIGEST}(?:/ancestors)?|/image-exports/{_ID}", _INVENTORY),
    ({"GET"}, rf"/layers/{_DIGEST}/blob|/image-exports/{_ID}/blob", _DOWNLOAD),
    ({"POST"}, rf"/bundles|/image-exports/{_ID}/download-token", _DOWNLOAD),
    ({"POST"}, r"/uploads|/bundles/import|/image-exports", _PUBLISH),
    ({"GET", "PATCH", "PUT", "DELETE"}, rf"/uploads/{_ID}", _PUBLISH),
    ({"DELETE"}, rf"/image-exports/{_ID}", _PUBLISH),
)
_PACKAGE = (
    ({"PUT"}, rf"/projects/{_ID}/namespace", (_PUBLISH,)),
    ({"GET"}, rf"/projects/{_NAMESPACE}/(?:packages|package|versions|resolve)", (_INVENTORY,)),
    ({"GET"}, rf"/projects/{_NAMESPACE}/versions/{_DIGEST}", (_INVENTORY,)),
    # Native version downloads also read the inventory manifest.
    ({"GET"}, rf"/projects/{_NAMESPACE}/versions/{_DIGEST}/(?:download|blobs/{_DIGEST})", (_INVENTORY, _DOWNLOAD)),
    ({"GET"}, rf"/projects/{_NAMESPACE}/cache/(?:resolve|archives/{_DIGEST})", (_DOWNLOAD,)),
    ({"POST"}, rf"/projects/{_NAMESPACE}/(?:uploads|cache/uploads)", (_PUBLISH,)),
    ({"GET", "PATCH", "PUT", "DELETE"}, rf"/projects/{_NAMESPACE}/(?:uploads|cache/uploads)/{_ID}", (_PUBLISH,)),
    ({"POST"}, rf"/projects/{_NAMESPACE}/keys", (_KEYS_EDITOR,)),
    ({"DELETE"}, rf"/projects/{_NAMESPACE}/keys/{_ID}", (_KEYS_ADMIN,)),
)
_SYSTEM = (
    ({"GET", "POST"}, r"/builds"),
    ({"GET"}, rf"/builds/{_ID}"),
    ({"DELETE"}, rf"/layers/{_DIGEST}"),
)


def _matches(method: str, path: str, methods: set[str], pattern: str) -> bool:
    return method in methods and re.fullmatch(pattern, path) is not None


def _package_principal(principal: Mapping) -> None:
    roles = {role.casefold() for role in principal.get("roles", ()) if isinstance(role, str)}
    if (
        roles & {"admin", "manager", "service"}
        or principal.get("is_system_admin")
        or principal.get("system_scope")
        or principal.get("domain_scope")
        or principal.get("connection_project_id", principal.get("project_id")) != principal.get("project_id")
    ):
        raise HTTPException(
            status_code=403, detail="Administrative or service identities cannot authorize package access"
        )


async def _verified_system_admin(principal: Mapping) -> bool:
    from app.services import keystone

    # Afterglow's compatibility admin-project policy is not a native global
    # builder/GC grant. Recheck the explicit system role for these exceptions.
    return (
        principal.get("is_system_admin") is True
        and bool(principal.get("user_id"))
        and await asyncio.to_thread(keystone._has_system_admin_role, principal["user_id"])
    )


async def authorize_palimpsest_request(request: Request, upstream_path: str, principal: Mapping) -> None:
    """Authorize a known browser leaf using current effective service roles.

    Machine/package bearers must never enter this function. The parent's browser
    authentication/current-membership gate owns principal construction.
    """
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer ppk_v1_"):
        raise HTTPException(status_code=403, detail="Package credentials require native action and owner validation")
    if not upstream_path.startswith("/v1/") or "?" in upstream_path or "#" in upstream_path:
        raise HTTPException(status_code=403, detail="Unknown Palimpsest browser operation")
    path = upstream_path[3:]
    method = request.method
    if any(_matches(method, path, methods, pattern) for methods, pattern in _SYSTEM):
        if not await _verified_system_admin(principal):
            raise HTTPException(status_code=403, detail="Verified system administrator authority is required")
        return
    for methods, pattern, leaf in _LEGACY:
        if _matches(method, path, methods, pattern):
            # Only the native legacy inventory/download exceptions allow verified
            # system operators; publishing and package/key controls never do.
            if leaf in {_INVENTORY, _DOWNLOAD} and await _verified_system_admin(principal):
                return
            _package_principal(principal)
            require_service_permission(principal, leaf)
            return
    _package_principal(principal)
    if method == "GET" and path in {"/", "/health", "/projects/current"}:
        if not service_permissions(principal)["palimpsest"]:
            raise HTTPException(status_code=403, detail="Current Palimpsest service authority is required")
        return
    if method == "GET" and re.fullmatch(rf"/projects/{_NAMESPACE}/keys", path):
        permissions = service_permissions(principal)["palimpsest"]
        if not {_KEYS_EDITOR, _KEYS_ADMIN}.intersection(permissions):
            raise HTTPException(status_code=403, detail="Key editor or admin authority is required")
        return
    for methods, pattern, leaves in _PACKAGE:
        if _matches(method, path, methods, pattern):
            require_service_permission(principal, *leaves)
            return
    # There are no standalone native tag/manifest/publish/buildcache routes.
    # Tag publication happens on package upload finalization; cache has its own
    # resolve/archive/upload leaves. Future routes must be classified explicitly.
    raise HTTPException(status_code=403, detail="Unknown Palimpsest browser operation")


async def authorize_current_package_request(
    request: Request, upstream_path: str, info: dict, *, method: str | None = None
) -> None:
    """Guard custom non-proxy browser I/O without exchanging the original token.

    These paths bypass the central proxy. Re-read the existing trusted effective
    assignment graph on every I/O; never use JWT/session roles as a downgrade
    fallback. Original token/protected-subject ceilings remain enforced by Hub.
    """
    from app.services import keystone
    from app.services.project_service import get_project_access

    access = await get_project_access(info["project_id"], info["user_id"])
    system_admin = await asyncio.to_thread(keystone._is_system_admin, info["user_id"])
    principal = {**info, "roles": access["roles"], "is_system_admin": system_admin}
    scope = {**request.scope, "method": method or request.method}
    await authorize_palimpsest_request(Request(scope), upstream_path, principal)
