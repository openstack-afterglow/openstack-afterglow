"""Caller-token project discovery and rescope; no privileged inventory or credentials."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from app.services import keystone
from app.services.mcp_control_plane.sdk import gather_sdk, run_sdk


async def caller_membership_projects(conn: Any, owner_user_id: str) -> list[dict[str, str]]:
    from app.services.mcp_control_plane.authority import McpAuthorityError

    if getattr(conn, "_afterglow_user_id", None) != owner_user_id:
        raise McpAuthorityError("scoped connection does not match the MCP grant owner")
    token = getattr(conn, "_afterglow_token", None)
    if not isinstance(token, str) or not token:
        raise McpAuthorityError("caller Keystone token is unavailable")
    access = await run_sdk(conn.session.auth.get_access, conn.session)
    if access.user_id != owner_user_id:
        raise McpAuthorityError("authenticated connection does not match the MCP owner")
    identity_domain_id = getattr(access, "user_domain_id", None)
    domain_id = getattr(conn, "_afterglow_domain_id", None)
    if (
        not isinstance(identity_domain_id, str)
        or not identity_domain_id
        or not isinstance(domain_id, str)
        or not domain_id
    ):
        raise McpAuthorityError("authenticated domain is unavailable")
    if getattr(conn, "_afterglow_identity_domain_id", None) != identity_domain_id:
        raise McpAuthorityError("authenticated identity domain does not match the MCP owner")
    from app.config import get_settings

    # /auth/projects is the authenticated user's available scopes, including
    # effective group/inherited membership, not an administrator inventory.
    auth_url = get_settings().os_auth_url.rstrip("/")
    response = await run_sdk(
        conn.session.get, f"{auth_url}/auth/projects", headers={"X-Auth-Token": token}, authenticated=False
    )
    response.raise_for_status()
    projects = response.json().get("projects")
    if not isinstance(projects, list):
        raise McpAuthorityError("Keystone returned invalid project memberships")
    result = {}
    for project in projects:
        if not isinstance(project, dict):
            raise McpAuthorityError("Keystone returned invalid project memberships")
        if project.get("domain_id") != domain_id:
            continue
        project_id = project.get("id")
        if isinstance(project_id, str) and project_id and project.get("enabled", True):
            result[project_id] = {"id": project_id, "name": project.get("name") or project_id}
    return sorted(result.values(), key=lambda project: (project["name"], project["id"]))


@dataclass(frozen=True)
class _CallerScope:
    user_id: str
    token: str
    identity_domain_id: str
    domain_id: str
    project_id: str | None


async def _caller_scope(conn: Any, owner_user_id: str) -> _CallerScope:
    """Capture validated caller identity once, before independent preview workers."""
    from app.services.mcp_control_plane.authority import McpAuthorityError

    if getattr(conn, "_afterglow_user_id", None) != owner_user_id:
        raise McpAuthorityError("scoped connection does not match the MCP grant owner")
    token = getattr(conn, "_afterglow_token", None)
    if not isinstance(token, str) or not token:
        raise McpAuthorityError("caller Keystone token is unavailable")
    # Browser administrator connections can name logical target B while their
    # SDK token remains scoped to home A. Only authenticated scope permits reuse.
    access = await run_sdk(conn.session.auth.get_access, conn.session)
    if access.user_id != owner_user_id:
        raise McpAuthorityError("authenticated connection does not match the MCP owner")
    identity_domain_id = getattr(access, "user_domain_id", None)
    domain_id = getattr(conn, "_afterglow_domain_id", None)
    if (
        not isinstance(identity_domain_id, str)
        or not identity_domain_id
        or not isinstance(domain_id, str)
        or not domain_id
    ):
        raise McpAuthorityError("authenticated domain is unavailable")
    if getattr(conn, "_afterglow_identity_domain_id", None) != identity_domain_id:
        raise McpAuthorityError("authenticated identity domain does not match the MCP owner")
    return _CallerScope(owner_user_id, token, identity_domain_id, domain_id, access.project_id)


async def _validated_project_connection(scoped: Any, caller: _CallerScope, project_id: str) -> Any:
    from app.services.mcp_control_plane.authority import McpAuthorityError, _role_snapshot
    from app.services.project_service import get_project_delegation_roles

    access = await run_sdk(scoped.session.auth.get_access, scoped.session)
    if access.user_id != caller.user_id or access.project_id != project_id:
        raise McpAuthorityError("authenticated connection does not match the MCP target")
    if (
        access.user_domain_id != caller.identity_domain_id
        or getattr(access, "project_domain_id", None) != caller.domain_id
    ):
        raise McpAuthorityError("MCP project must belong to the selected working domain")
    names = list(access.role_names or ())
    role_ids = list(access.role_ids or ())
    if len(names) != len(role_ids) or any(not isinstance(role_id, str) or not role_id for role_id in role_ids):
        raise McpAuthorityError("Keystone token has invalid role identities")
    roles = _role_snapshot([{"id": role_id, "name": name} for role_id, name in zip(role_ids, names, strict=True)])
    authenticated = {role["id"]: role["name"] for role in roles}
    current_roles = await get_project_delegation_roles(project_id, caller.user_id)
    current_ids = {role["id"] for role in current_roles if authenticated.get(role["id"]) == role["name"]}
    delegated_roles = roles
    if authenticated.keys() - current_ids:
        # Only an actually stale token needs explicit roles. Otherwise keep
        # Keystone's token-default path, even if today's DAG has new children.
        delegatable_ids = {
            role["id"]
            for role in current_roles
            if role["id"] in current_ids and set(role["inherited_role_ids"]) <= current_ids
        }
        delegated_roles = _role_snapshot([role for role in roles if role["id"] in delegatable_ids])
    scoped._afterglow_user_id = caller.user_id
    scoped._afterglow_project_id = project_id
    scoped._afterglow_project_name = access.project_name or project_id
    scoped._afterglow_authenticated_project_id = project_id
    scoped._afterglow_token = access.auth_token
    scoped._afterglow_roles = delegated_roles
    scoped._afterglow_delegation_narrowed = len(delegated_roles) != len(roles)
    scoped._afterglow_is_system_admin = False
    scoped._afterglow_domain_id = caller.domain_id
    scoped._afterglow_identity_domain_id = caller.identity_domain_id
    return scoped


async def _independent_project_connection(
    caller: _CallerScope, project_id: str, *, api_timeout: float | None = None
) -> Any:
    scoped = await run_sdk(
        keystone.get_openstack_connection,
        caller.token,
        project_id,
        cancellation_cleanup=lambda created: created.close(),
        **({"api_timeout": api_timeout} if api_timeout is not None else {}),
    )
    try:
        return await _validated_project_connection(scoped, caller, project_id)
    except BaseException:
        await run_sdk(scoped.close, allow_after_cancel=True)
        raise


async def project_connection(conn: Any, owner_user_id: str, project_id: str) -> Any:
    """Intersect authenticated scope with current assignments; never elevate a stale token."""
    caller = await _caller_scope(conn, owner_user_id)
    if caller.project_id == project_id:
        return await _validated_project_connection(conn, caller, project_id)
    return await _independent_project_connection(caller, project_id)


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


_PREVIEW_POLICY_TIMEOUT = 5.0
_PREVIEW_PROJECT_TIMEOUT = 5.0
_PREVIEW_PROJECT_CONCURRENCY = 3


async def project_permission_preview(conn: Any, owner_user_id: str) -> list[dict[str, object]]:
    """Isolate unavailable rows and services using owned, independently scoped workers."""
    from app.services.service_authorization import service_permission_snapshot, service_policy_availability

    # Discovery remains authoritative: a failure is not an empty successful list.
    candidates = await caller_membership_projects(conn, owner_user_id)
    enabled = service_policy_availability()

    def unknown(project):
        return {
            **project,
            "can_write": None,
            "service_permissions": {service: [] for service in enabled},
            "service_errors": {service: "permission_check_unavailable" for service in enabled},
        }

    try:
        caller = await asyncio.wait_for(_caller_scope(conn, owner_user_id), timeout=_PREVIEW_PROJECT_TIMEOUT)
    except Exception:
        return [unknown(project) for project in candidates]
    slots = asyncio.Semaphore(_PREVIEW_PROJECT_CONCURRENCY)

    async def evaluate_owned(project):
        scoped = None
        try:
            # Never concurrently reuse even the current project's caller
            # connection/session. Only the validated immutable identity is shared.
            scoped = await asyncio.wait_for(
                _independent_project_connection(caller, project["id"], api_timeout=_PREVIEW_PROJECT_TIMEOUT),
                timeout=_PREVIEW_PROJECT_TIMEOUT,
            )
            permissions, errors = await service_permission_snapshot(
                {
                    "token": scoped._afterglow_token,
                    "user_id": owner_user_id,
                    "project_id": project["id"],
                    "connection_project_id": project["id"],
                    "is_system_admin": False,
                },
                timeout=_PREVIEW_POLICY_TIMEOUT,
            )
            if scoped._afterglow_delegation_narrowed:
                # Removed token roles must not masquerade as the future
                # restricted credential's independent service authority.
                errors = {
                    service: "permission_check_unavailable" for service in permissions if enabled.get(service, False)
                }
                permissions = {service: [] for service in permissions}
            return {
                **project,
                "can_write": bool({role["name"].casefold() for role in scoped._afterglow_roles} & {"admin", "member"}),
                "service_permissions": permissions,
                "service_errors": errors,
            }
        finally:
            if scoped is not None:
                await run_sdk(scoped.close, allow_after_cancel=True)

    async def evaluate(project):
        async with slots:
            try:
                return await evaluate_owned(project)
            except Exception:
                return unknown(project)

    # On cancellation, all workers drain their SDK threads and close their owned
    # connections before the request releases its concurrency/connection boundary.
    return await gather_sdk(*(evaluate(project) for project in candidates))


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
