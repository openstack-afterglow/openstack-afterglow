"""Read-only administrator inventory conditions; never an authorization cache."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Query
from openstack.exceptions import ResourceNotFound

from app.api.common.errors import public_service_error
from app.api.deps import get_admin_os_conn
from app.services.domain_display import display_name


def field(row, key):
    return row.get(key) if isinstance(row, dict) else getattr(row, key, None)


@dataclass(frozen=True)
class AdminResourceScope:
    project_ids: frozenset[str] | None = None
    domain_id: str | None = None

    def includes(self, row, owner_key="project_id") -> bool:
        if self.project_ids is None:
            return True
        owner = owner_id(row) if owner_key == "project_id" else field(row, owner_key)
        return isinstance(owner, str) and owner in self.project_ids

    def filter(self, rows, owner_key="project_id"):
        return [row for row in rows if self.includes(row, owner_key)]


def resolve_scope(conn, domain_id: str | None, project_id: str | None) -> AdminResourceScope:
    if domain_id is None:
        return AdminResourceScope(frozenset([project_id]) if project_id else None)
    try:
        try:
            domain = conn.identity.get_domain(domain_id)
        except ResourceNotFound as exc:
            raise HTTPException(404, "inventory_domain_not_found") from exc
        if domain is None:
            raise HTTPException(404, "inventory_domain_not_found")
        if field(domain, "id") != domain_id:
            raise public_service_error(503, "inventory_directory_unverified")
        projects = list(conn.identity.projects(domain_id=domain_id))
        ids = set()
        seen = set()
        for project in projects:
            pid, did = field(project, "id"), field(project, "domain_id")
            if not isinstance(pid, str) or not pid or not isinstance(did, str) or not did or pid in seen:
                raise public_service_error(503, "inventory_directory_unverified")
            seen.add(pid)
            if did == domain_id:
                ids.add(pid)
        if project_id:
            ids.intersection_update([project_id])
        return AdminResourceScope(frozenset(ids), domain_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise public_service_error(503, "inventory_directory_unavailable") from exc


async def admin_resource_scope(
    domain_id: str | None = Query(None, min_length=1),
    project_id: str | None = Query(None, min_length=1),
    conn=Depends(get_admin_os_conn),
) -> AdminResourceScope:
    if domain_id is None:
        return resolve_scope(conn, None, project_id)
    return await asyncio.to_thread(resolve_scope, conn, domain_id, project_id)


def page(rows, limit: int, marker: str | None):
    start = 0
    if marker:
        indexes = [index for index, row in enumerate(rows) if field(row, "id") == marker]
        if not indexes:
            raise HTTPException(400, "inventory_marker_outside_scope")
        start = indexes[0] + 1
    items = rows[start : start + limit]
    return {
        "items": items,
        "count": len(items),
        "next_marker": field(items[-1], "id") if items and start + limit < len(rows) else None,
    }


def owner_id(row) -> str | None:
    value = field(row, "project_id") or field(row, "tenant_id") or field(row, "os-vol-tenant-attr:tenant_id")
    return value if isinstance(value, str) and value else None


@dataclass(frozen=True)
class InventoryDirectory:
    projects: dict
    domains: dict

    def owner(self, row) -> dict:
        pid = owner_id(row)
        project = self.projects.get(pid)
        did = field(project, "domain_id") if project is not None else None
        domain = self.domains.get(did)
        return {
            "project_id": pid,
            "project_name": field(project, "name") if project is not None else None,
            "domain_id": did,
            "domain_name": field(domain, "name") if domain is not None else None,
            "owner_status": "unknown_owner"
            if pid is None
            else "deleted_project"
            if project is None
            else "deleted_domain"
            if domain is None
            else "known",
        }


def inventory_directory(conn) -> InventoryDirectory:
    """Fresh complete native ownership directory; outages never become empty totals."""
    try:
        collections = []
        for kind in ("projects", "domains"):
            indexed = {}
            for row in getattr(conn.identity, kind)():
                rid = field(row, "id")
                if not isinstance(rid, str) or not rid or rid in indexed:
                    raise public_service_error(503, "inventory_directory_unverified")
                if kind == "projects":
                    did = field(row, "domain_id")
                    if not isinstance(did, str) or not did:
                        raise public_service_error(503, "inventory_directory_unverified")
                if kind == "domains":
                    row = {"id": rid, "name": display_name(row)}
                indexed[rid] = row
            collections.append(indexed)
        return InventoryDirectory(*collections)
    except HTTPException:
        raise
    except Exception as exc:
        raise public_service_error(503, "inventory_directory_unavailable") from exc


def domain_totals(directory: InventoryDirectory, servers, volumes, scope: AdminResourceScope) -> list[dict]:
    from app.api.identity.admin_dashboard import _is_gpu_flavor

    groups = {}

    def group(row, owner=None):
        owner = directory.owner(row) if owner is None else owner
        key = (owner["owner_status"], owner["domain_id"], owner["project_id"] if owner["domain_id"] is None else None)
        if key not in groups:
            groups[key] = {
                "domain_id": owner["domain_id"],
                "domain_name": owner["domain_name"],
                "owner_status": owner["owner_status"],
                "project_ids": set(),
                "instances": 0,
                "vcpus": 0,
                "ram_mb": 0,
                "gpu_instances": 0,
                "volumes": 0,
                "volume_gb": 0,
                "attached_volumes": 0,
                "attached_gb": 0,
                "available_volumes": 0,
                "available_gb": 0,
            }
        result = groups[key]
        if owner["project_id"]:
            result["project_ids"].add(owner["project_id"])
        return result

    for did, domain in directory.domains.items():
        if scope.project_ids is None or scope.domain_id == did:
            group(
                {},
                {"domain_id": did, "domain_name": field(domain, "name"), "owner_status": "known", "project_id": None},
            )
    for pid in directory.projects:
        if scope.project_ids is None or pid in scope.project_ids:
            group({"project_id": pid})

    for server in servers:
        result = group(server)
        result["instances"] += 1
        flavor = field(server, "flavor") or {}
        for source, target in (("vcpus", "vcpus"), ("ram", "ram_mb")):
            value = field(flavor, source)
            if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
                result[target] = None
            elif result[target] is not None:
                result[target] += value
        if not flavor.get("original_name") and not flavor.get("extra_specs"):
            result["gpu_instances"] = None
        elif result["gpu_instances"] is not None:
            result["gpu_instances"] += int(_is_gpu_flavor(flavor))
    for volume in volumes:
        result = group(volume)
        size = field(volume, "size")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise public_service_error(503, "inventory_volume_capacity_unverified")
        result["volumes"] += 1
        result["volume_gb"] += size
        if field(volume, "attachments") or str(field(volume, "status") or "").lower() == "in-use":
            result["attached_volumes"] += 1
            result["attached_gb"] += size
        if str(field(volume, "status") or "").lower() == "available":
            result["available_volumes"] += 1
            result["available_gb"] += size
    for result in groups.values():
        result["project_ids"] = sorted(result["project_ids"])
        result["project_count"] = len(result["project_ids"])
    return sorted(groups.values(), key=lambda row: (row["domain_id"] or "", row["owner_status"], row["project_ids"]))
