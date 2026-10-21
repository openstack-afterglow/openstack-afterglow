"""Read-only administrator inventory conditions; never an authorization cache."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Query

from app.api.deps import get_os_conn


def field(row, key):
    return row.get(key) if isinstance(row, dict) else getattr(row, key, None)


@dataclass(frozen=True)
class AdminResourceScope:
    project_ids: frozenset[str] | None = None

    def includes(self, row, owner_key="project_id") -> bool:
        if self.project_ids is None:
            return True
        owner = field(row, owner_key) or field(row, "tenant_id")
        return isinstance(owner, str) and owner in self.project_ids

    def filter(self, rows, owner_key="project_id"):
        return [row for row in rows if self.includes(row, owner_key)]


def resolve_scope(conn, domain_id: str | None, project_id: str | None) -> AdminResourceScope:
    if domain_id is None:
        return AdminResourceScope(frozenset([project_id]) if project_id else None)
    try:
        domain = conn.identity.get_domain(domain_id)
        if domain is None:
            raise HTTPException(404, "inventory_domain_not_found")
        if field(domain, "id") != domain_id:
            raise HTTPException(503, "inventory_directory_unverified")
        projects = list(conn.identity.projects(domain_id=domain_id))
        ids = set()
        seen = set()
        for project in projects:
            pid, did = field(project, "id"), field(project, "domain_id")
            if not isinstance(pid, str) or not pid or not isinstance(did, str) or not did or pid in seen:
                raise HTTPException(503, "inventory_directory_unverified")
            seen.add(pid)
            if did == domain_id:
                ids.add(pid)
        if project_id:
            ids.intersection_update([project_id])
        return AdminResourceScope(frozenset(ids))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, "inventory_directory_unavailable") from exc


async def admin_resource_scope(
    domain_id: str | None = Query(None, min_length=1),
    project_id: str | None = Query(None, min_length=1),
    conn=Depends(get_os_conn),
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
