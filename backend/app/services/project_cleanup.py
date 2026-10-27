"""Complete, redacted project inventory and ordinary single-resource deletion.

The deletion-check count remains the project deletion authority. This monitor
never cleans dependencies, forces state, suppresses missing resources or follows
provider-supplied URLs. Optional adapters share the same public result shape.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from copy import copy
from functools import partial
from typing import Any
from urllib.parse import quote

from fastapi import HTTPException
from openstack.proxy import Proxy

from app.services import project_deletion as inventory

CORE_KINDS = frozenset(
    {
        "instances",
        "server_groups",
        "volumes",
        "volume_snapshots",
        "volume_backups",
        "networks",
        "subnets",
        "routers",
        "ports",
        "floating_ips",
        "security_groups",
        "images",
        "child_projects",
    }
)
_NETWORK = {
    "networks": "network",
    "subnets": "subnet",
    "routers": "router",
    "ports": "port",
    "floating_ips": "ip",
    "security_groups": "security_group",
}
_STORAGE = {
    "volumes": ("volume", "os-vol-tenant-attr:tenant_id"),
    "volume_snapshots": ("snapshot", "os-extended-snapshot-attributes:project_id"),
    "volume_backups": ("backup", "os-backup-project-attr:project_id"),
}


def field(resource: Any, key: str) -> Any:
    # SDK Resource can have a stale Mapping snapshot after descriptor edits.
    from app.services.volume_transfers import field as native_field

    return native_field(resource, key)


def identifier(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value in {".", ".."}
        or any(char in value for char in "/\\?#%:")
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise HTTPException(422, "project_resource_identifier_invalid")
    return value


def _checked_request(request, *args, **kwargs):
    response = request(*args, **kwargs)
    response.raise_for_status()
    if not 200 <= response.status_code < 300:
        raise HTTPException(503, "project_resource_native_response_unverified")
    return response


def safe_proxy(proxy: Any) -> Any:
    adapter = copy(proxy)
    kwargs = {"skip_cache": True} if isinstance(proxy, Proxy) else {}
    adapter.request = partial(
        _checked_request,
        adapter.request,
        allow_reauth=False,
        connect_retries=0,
        status_code_retries=0,
        redirect=False,
        **kwargs,
    )
    return adapter


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, HTTPException):
        return exc
    status = (
        getattr(exc, "status_code", None)
        or getattr(exc, "http_status", None)
        or getattr(getattr(exc, "response", None), "status_code", None)
    )
    if status in (401, 403):
        return HTTPException(403, "project_resource_native_denied")
    if status == 404:
        return HTTPException(404, "project_resource_not_found")
    if status in (400, 409, 412, 422):
        return HTTPException(409, "project_resource_delete_conflict")
    return HTTPException(503, "project_resource_unavailable")


def _owners(kind: str) -> tuple[str, ...]:
    if kind == "images":
        return ("owner", "owner_id")
    if kind in _STORAGE:
        return ("project_id", "tenant_id", _STORAGE[kind][1])
    return ("project_id", "tenant_id")


def _owner(resource: Any, kind: str) -> str:
    values = {field(resource, key) for key in _owners(kind) if field(resource, key) not in (None, "")}
    if len(values) != 1 or not all(isinstance(value, str) for value in values):
        raise HTTPException(503, "project_resource_ownership_unverified")
    return next(iter(values))


def _result(project_id: str, kind: str, status: str, reason=None, resources=None) -> dict:
    rows = resources if resources is not None else []
    return {
        "project_id": project_id,
        "kind": kind,
        "status": status,
        "reason": reason,
        "resources": rows,
        "count": len(rows) if status == "ok" else None,
    }


def _optional():
    from app.services import project_cleanup_optional

    return project_cleanup_optional


def require_kind(kind: str) -> None:
    if kind not in CORE_KINDS and kind not in _optional().OPTIONAL_KINDS:
        raise HTTPException(422, "project_resource_kind_invalid")


def requires_project_scope(kind: str) -> bool:
    return kind not in CORE_KINDS and kind in _optional().REQUIRED_PROJECT_SCOPE_KINDS


def delete_project_native(proxy: Any, project_id: str) -> None:
    _delete_native(proxy, "/projects/" + quote(identifier(project_id), safe=""))


def _delete_native(proxy: Any, path: str) -> None:
    response = safe_proxy(proxy).delete(path)
    response.raise_for_status()
    if not 200 <= response.status_code < 300:
        raise HTTPException(503, "project_resource_delete_outcome_unverified")


def _read(conn: Any, project_id: str, kind: str):
    # SDK Resource.list follows provider next URLs. Reuse the guard's fixed-path
    # iterator instead: only marker/offset tokens may select another page.
    if kind == "instances":
        return inventory._raw_pages(
            safe_proxy(conn.compute), "/servers/detail", "servers", params={"all_tenants": True}
        )
    if kind == "server_groups":
        return inventory._raw_pages(
            safe_proxy(conn.compute),
            "/os-server-groups",
            "server_groups",
            params={"all_projects": True},
            offset=True,
            microversion="2.13",
        )
    if kind in _STORAGE:
        key = {"volumes": "volumes", "volume_snapshots": "snapshots", "volume_backups": "backups"}[kind]
        return inventory._raw_pages(
            safe_proxy(conn.block_storage),
            "/" + key + "/detail",
            key,
            params={"all_tenants": True},
            microversion="3.18" if kind == "volume_backups" else None,
        )
    if kind in _NETWORK:
        key = "floatingips" if kind == "floating_ips" else kind
        path = "/security-groups" if kind == "security_groups" else "/" + key
        return inventory._raw_pages(safe_proxy(conn.network), path, key, params={"project_id": project_id})
    if kind == "images":

        def images():
            proxy = safe_proxy(conn.image)
            for hidden in (False, True):
                yield from inventory._raw_pages(
                    proxy,
                    "/images",
                    "images",
                    params={"owner": project_id, "visibility": "all", "member_status": "all", "os_hidden": hidden},
                )

        return images()
    return inventory._raw_pages(safe_proxy(conn.identity), "/projects", "projects", params={"parent_id": project_id})


def list_resources(conn: Any, project_id: str, kind: str) -> dict:
    require_kind(kind)
    if kind not in CORE_KINDS:
        result = _optional().list_resources(conn, project_id, kind)
        return {**result, "project_id": project_id, "kind": kind}
    if not inventory._native_admin(conn):
        return _result(project_id, kind, "unavailable", "admin_authority_unverified")
    try:
        rows, seen = [], set()
        parent = conn.identity.get_project(project_id) if kind == "child_projects" else None
        if kind == "child_projects" and (field(parent, "id") != project_id or not field(parent, "domain_id")):
            raise HTTPException(503, "project_resource_ownership_unverified")
        for resource in _read(conn, project_id, kind):
            resource_id = identifier(field(resource, "id"))
            if resource_id in seen:
                raise HTTPException(503, "project_resource_inventory_unverified")
            seen.add(resource_id)
            if kind == "child_projects":
                if field(resource, "parent_id") != project_id:
                    raise HTTPException(503, "project_resource_ownership_unverified")
                if field(resource, "domain_id") != field(parent, "domain_id"):
                    raise HTTPException(503, "project_resource_ownership_unverified")
            elif _owner(resource, kind) != project_id:
                continue
            row = {"id": resource_id}
            for key in ("name", "status"):
                value = field(resource, key)
                if value is not None and not isinstance(value, str):
                    raise HTTPException(503, "project_resource_inventory_unverified")
                if value is not None:
                    row[key] = value
            rows.append(row)
        return _result(project_id, kind, "ok", resources=rows)
    except Exception:
        # A page/detail/ownership failure discards every row. Provider exception
        # bodies and descriptions never enter this public metadata projection.
        return _result(project_id, kind, "unavailable", "resource_check_failed")


def _detail(conn: Any, project_id: str, kind: str, resource_id: str):
    identifier(resource_id)
    if kind == "server_groups":
        response = safe_proxy(conn.compute).get("/os-server-groups/" + quote(resource_id, safe=""), microversion="2.13")
        response.raise_for_status()
        body = response.json()
        resource = body.get("server_group") if isinstance(body, dict) else None
    elif kind == "instances":
        resource = safe_proxy(conn.compute).get_server(resource_id)
    elif kind == "volume_backups":
        response = safe_proxy(conn.block_storage).get("/backups/" + quote(resource_id, safe=""), microversion="3.18")
        body = response.json()
        resource = body.get("backup") if isinstance(body, dict) else None
    elif kind in _STORAGE:
        resource = getattr(safe_proxy(conn.block_storage), "get_" + _STORAGE[kind][0])(resource_id)
    elif kind in _NETWORK:
        resource = getattr(safe_proxy(conn.network), "get_" + _NETWORK[kind])(resource_id)
    elif kind == "images":
        resource = safe_proxy(conn.image).get_image(resource_id)
    else:
        raise HTTPException(409, "project_resource_child_requires_project_guard")
    if resource is None:
        raise HTTPException(404, "project_resource_not_found")
    if field(resource, "id") != resource_id:
        raise HTTPException(503, "project_resource_identity_unverified")
    if _owner(resource, kind) != project_id:
        raise HTTPException(403, "project_resource_project_mismatch")
    return resource


def _source_volume(conn: Any, project_id: str, kind: str, resource: Any):
    parent_id = identifier(field(resource, "volume_id"))
    try:
        return _detail(conn, project_id, "volumes", parent_id)
    except Exception as exc:
        # Cinder backups deliberately survive deletion of their source volume.
        # Only an exact native 404 permits this branch; foreign/malformed or
        # denied parents stay failures. Durable source receipts are checked by
        # assert_deletion_safe even when this native source no longer exists.
        if kind == "volume_backups" and _error(exc).status_code == 404:
            return None
        raise


def _assert_native_unmanaged(resource: Any) -> None:
    metadata = field(resource, "metadata")
    if metadata is not None and not isinstance(metadata, Mapping):
        raise HTTPException(503, "project_resource_metadata_unverified")
    protected = (
        "afterglow_consume",
        "afterglow_catalog_consume",
        "afterglow_run_",
        "afterglow_build",
        "afterglow_share_grant_",
        "afterglow_managed_by",
        "afterglow_purpose",
        "afterglow_workspace",
        "afterglow_signature",
        "drover_",
        "union_",
        "layer_transport",
    )
    if any(str(key).startswith(protected) for key in metadata or {}):
        raise HTTPException(409, "project_resource_managed_cleanup_required")
    description = field(resource, "description")
    if isinstance(description, str):
        try:
            markers = json.loads(description)
        except (ValueError, TypeError):
            markers = None
        if isinstance(markers, dict) and any(str(key).startswith(protected) for key in markers):
            raise HTTPException(409, "project_resource_managed_cleanup_required")


async def assert_deletion_safe(conn: Any, project_id: str, kind: str, resource_id: str) -> None:
    """Read durable managed-resource bindings before ordinary native deletion."""
    if kind not in {"instances", "volumes", "volume_snapshots", "volume_backups", "ports"}:
        return
    try:
        resource = await asyncio.to_thread(_detail, conn, project_id, kind, resource_id)
        _assert_native_unmanaged(resource)
        if kind in _STORAGE:
            from app.services.volume_transfers import assert_unmanaged, assert_unmanaged_id

            if kind != "volumes":
                parent_id = identifier(field(resource, "volume_id"))
                resource = await asyncio.to_thread(_source_volume, conn, project_id, kind, resource)
                if resource is None:
                    await assert_unmanaged_id(parent_id, project_id)
                    return
            await assert_unmanaged(resource, project_id)
        elif kind == "instances":
            from app.services.layer_consume_resources import lookup_for_server
            from app.services.palimpsest_catalog_cleanup import lookup_catalog_consume

            if await lookup_for_server(resource_id, project_id):
                raise HTTPException(409, "project_resource_managed_cleanup_required")
            if await lookup_catalog_consume(resource_id, resource, {"project_id": project_id, "is_system_admin": True}):
                raise HTTPException(409, "project_resource_managed_cleanup_required")
        elif kind == "ports":
            from sqlalchemy import select

            from app.database import get_session_factory
            from app.models.db import LayerConsume

            factory = get_session_factory()
            if factory is None:
                raise HTTPException(503, "project_resource_ledger_unavailable")
            async with factory() as session:
                rows = (await session.execute(select(LayerConsume))).scalars().all()
                for row in rows:
                    if row.port_id == resource_id or any(
                        item.get("kind") == "port" and item.get("id") == resource_id for item in row.resources or []
                    ):
                        raise HTTPException(409, "project_resource_managed_cleanup_required")
                    if (
                        row.project_id == project_id
                        and row.cleanup_state != "complete"
                        and any(
                            item.get("kind") == "port"
                            and item.get("id") is None
                            and item.get("state") not in {"rejected", "not_sent"}
                            for item in row.resources or []
                        )
                    ):
                        raise HTTPException(503, "project_resource_ledger_unavailable")
    except Exception as exc:
        raise _error(exc) from None


def delete_resource(conn: Any, project_id: str, kind: str, resource_id: str) -> None:
    require_kind(kind)
    if kind not in CORE_KINDS:
        _optional().delete_resource(conn, project_id, kind, resource_id)
        return
    if not inventory._native_admin(conn):
        raise HTTPException(403, "project_resource_admin_authority_unverified")
    try:
        resource = _detail(conn, project_id, kind, resource_id)
        _assert_native_unmanaged(resource)
        path_id = quote(resource_id, safe="")
        if kind in _STORAGE:
            if kind == "volumes":
                attachments = field(resource, "attachments")
                if not isinstance(attachments, list) or attachments:
                    raise HTTPException(409, "project_resource_attached_or_unverified")
            if field(resource, "status") not in {"available", "error"}:
                raise HTTPException(409, "project_resource_state_conflict")
            if kind != "volumes":
                parent = _source_volume(conn, project_id, kind, resource)
                if parent is not None:
                    _assert_native_unmanaged(parent)
            proxy = conn.block_storage
            collection = {"volumes": "volumes", "volume_snapshots": "snapshots", "volume_backups": "backups"}[kind]
            path = "/" + collection + "/" + path_id
        elif kind in _NETWORK:
            if kind == "security_groups" and field(resource, "name") == "default":
                raise HTTPException(409, "project_resource_default_protected")
            if kind == "ports" and (field(resource, "device_id") or field(resource, "device_owner")):
                raise HTTPException(409, "project_resource_attached_or_unverified")
            if kind == "floating_ips" and field(resource, "port_id"):
                raise HTTPException(409, "project_resource_attached_or_unverified")
            proxy = conn.network
            collection = {"security_groups": "security-groups", "floating_ips": "floatingips"}.get(kind, kind)
            path = "/" + collection + "/" + path_id
        elif kind == "images":
            if field(resource, "is_protected") is not False:
                raise HTTPException(409, "project_resource_protected_or_unverified")
            proxy, path = conn.image, "/images/" + path_id
        else:
            proxy = conn.compute
            collection = "servers" if kind == "instances" else "os-server-groups"
            path = "/" + collection + "/" + path_id
        _delete_native(proxy, path)
    except Exception as exc:
        raise _error(exc) from None
