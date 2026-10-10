"""Caller-token project discovery and rescope; no privileged inventory or credentials."""

from __future__ import annotations

import asyncio
from typing import Any

from app.services import keystone


async def caller_membership_projects(conn: Any, owner_user_id: str) -> list[dict[str, str]]:
    from app.services.mcp_control_plane.authority import McpAuthorityError

    if getattr(conn, "_afterglow_user_id", None) != owner_user_id:
        raise McpAuthorityError("scoped connection does not match the MCP grant owner")
    token = getattr(conn, "_afterglow_token", None)
    if not isinstance(token, str) or not token:
        raise McpAuthorityError("caller Keystone token is unavailable")
    access = await asyncio.to_thread(conn.session.auth.get_access, conn.session)
    if access.user_id != owner_user_id:
        raise McpAuthorityError("authenticated connection does not match the MCP owner")
    from app.config import get_settings

    # /auth/projects is the authenticated user's available scopes, including
    # effective group/inherited membership, not an administrator inventory.
    auth_url = get_settings().os_auth_url.rstrip("/")
    response = await asyncio.to_thread(
        conn.session.get, f"{auth_url}/auth/projects", headers={"X-Auth-Token": token}, authenticated=False
    )
    response.raise_for_status()
    projects = response.json().get("projects")
    if not isinstance(projects, list):
        raise McpAuthorityError("Keystone returned invalid project memberships")
    result = {}
    for project in projects:
        project_id = project.get("id")
        if isinstance(project_id, str) and project_id and project.get("enabled", True):
            result[project_id] = {"id": project_id, "name": project.get("name") or project_id}
    return sorted(result.values(), key=lambda project: (project["name"], project["id"]))


async def project_connection(conn: Any, owner_user_id: str, project_id: str) -> Any:
    """Authenticate the actual caller and verify both returned token scope and roles."""
    from app.services.mcp_control_plane.authority import McpAuthorityError, _role_snapshot

    if getattr(conn, "_afterglow_user_id", None) != owner_user_id:
        raise McpAuthorityError("scoped connection does not match the MCP grant owner")
    token = getattr(conn, "_afterglow_token", None)
    if not isinstance(token, str) or not token:
        raise McpAuthorityError("caller Keystone token is unavailable")
    # Browser administrator connections can name logical target B while their
    # SDK token remains scoped to home A. Only authenticated scope permits reuse.
    access = await asyncio.to_thread(conn.session.auth.get_access, conn.session)
    if access.user_id != owner_user_id:
        raise McpAuthorityError("authenticated connection does not match the MCP owner")
    current = access.project_id == project_id
    scoped = conn if current else await asyncio.to_thread(keystone.get_openstack_connection, token, project_id)
    try:
        if not current:
            access = await asyncio.to_thread(scoped.session.auth.get_access, scoped.session)
        if access.user_id != owner_user_id or access.project_id != project_id:
            raise McpAuthorityError("authenticated connection does not match the MCP target")
        roles = _role_snapshot(list(access.role_names or ()))
        scoped._afterglow_user_id = owner_user_id
        scoped._afterglow_project_id = project_id
        scoped._afterglow_project_name = access.project_name or project_id
        scoped._afterglow_authenticated_project_id = project_id
        scoped._afterglow_token = access.auth_token
        scoped._afterglow_roles = roles
        scoped._afterglow_is_system_admin = False
        return scoped
    except BaseException:
        if scoped is not conn:
            await asyncio.to_thread(scoped.close)
        raise


async def project_candidates(
    conn: Any,
    owner_user_id: str,
    owner_project_id: str,
    project_scope: str = "current",
    project_ids: list[str] | None = None,
) -> list[dict[str, str]]:
    from app.services.mcp_control_plane.authority import McpAuthorityError

    if project_scope not in {"current", "selected", "all"}:
        raise McpAuthorityError("project scope must be current, selected or all")
    if project_scope == "current":
        if project_ids and project_ids != [owner_project_id]:
            raise McpAuthorityError("current scope only allows the current project")
        candidates = [{"id": owner_project_id, "name": owner_project_id}]
    else:
        memberships = await caller_membership_projects(conn, owner_user_id)
        if project_scope == "all":
            if project_ids:
                raise McpAuthorityError("all scope cannot include selected project IDs")
            candidates = memberships
        else:
            if not project_ids or len(project_ids) != len(set(project_ids)):
                raise McpAuthorityError("selected scope requires unique project IDs")
            by_id = {project["id"]: project for project in memberships}
            if any(project_id not in by_id for project_id in project_ids):
                raise McpAuthorityError("selected project is not an enabled caller membership")
            candidates = [by_id[project_id] for project_id in project_ids]
    if not candidates:
        raise McpAuthorityError("no enabled caller project memberships are available")
    return candidates


async def resolve_project_scope(
    conn: Any,
    owner_user_id: str,
    owner_project_id: str,
    roles: object,
    project_scope: str = "current",
    project_ids: list[str] | None = None,
    access_level: str = "read",
) -> list[dict[str, object]]:
    from app.services.mcp_control_plane.authority import _prepare_connection_projects, close_project_authority

    projects = await _prepare_connection_projects(
        conn, owner_user_id, owner_project_id, roles, project_scope, project_ids, access_level
    )
    try:
        return [project.metadata() for project in projects]
    finally:
        await close_project_authority(projects)
