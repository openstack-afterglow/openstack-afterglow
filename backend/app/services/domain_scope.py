"""Live Keystone domain and scope boundaries shared by authentication and IAM.

The working domain is authorized independently of the immutable identity domain.
Project-token role names never prove domain or system authority.

Native reads may be shared only through an explicitly supplied operation. Omitted
operations keep sensitive guards request-fresh, outside every global read cache.
"""

from __future__ import annotations

from fastapi import HTTPException
from keystoneauth1.exceptions.http import NotFound, Unauthorized
from keystoneclient.exceptions import NotFound as ClientNotFound

from app.services import domain_display, identity_roles, keystone


def _id(value) -> str:
    return identity_roles._field(value, "id", "")


def _domain_row(ks, name_or_id, operation):
    if operation is not None and (id(ks.domains), name_or_id) in operation.reads:
        return operation.get("domains", name_or_id)
    try:
        return ks.domains.get(name_or_id)
    except (NotFound, ClientNotFound):
        domains = (
            operation.read(("domain_scope", "domains"), lambda: list(ks.domains.list()))
            if operation is not None
            else ks.domains.list()
        )
        matches = [d for d in domains if domain_display.display_name(d) == name_or_id]
        if len(matches) > 1:
            raise HTTPException(409, "Domain display name is ambiguous; use the domain ID")
        if not matches:
            raise HTTPException(status_code=404, detail="Domain not found")
        return matches[0]


def resolve_domain(name_or_id: str, *, operation=None) -> dict:
    if not isinstance(name_or_id, str) or not name_or_id.strip():
        raise HTTPException(status_code=400, detail="An explicit domain is required")
    try:
        ks = operation.ks if operation is not None else keystone._get_admin_ks_client()
        domain = (
            operation.read(("domain_scope", "domain", name_or_id), _domain_row, ks, name_or_id, operation)
            if operation is not None
            else _domain_row(ks, name_or_id, None)
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Domain directory is unavailable") from exc
    did, name = _id(domain), domain_display.display_name(domain)
    if not isinstance(did, str) or not did or not isinstance(name, str) or not name:
        raise HTTPException(status_code=503, detail="Domain identity is unavailable")
    if name_or_id not in {did, name}:
        raise HTTPException(status_code=503, detail="Domain directory returned a different identity")
    if identity_roles._field(domain, "enabled") is not True:
        raise HTTPException(status_code=403, detail="Domain is disabled")
    if operation is not None:
        # Aliases have their own resolution key; only canonical IDs seed exact reads.
        operation.read((id(ks.domains), did), lambda: domain)
    from app.services.account_spaces import domain_kind

    return {"id": did, "name": name, "enabled": True, "kind": domain_kind(domain)}


def assert_domain_resource(domain_id: str, resource_domain_id: str) -> None:
    if (
        not isinstance(domain_id, str)
        or not domain_id
        or not isinstance(resource_domain_id, str)
        or not resource_domain_id
        or domain_id != resource_domain_id
    ):
        raise HTTPException(status_code=403, detail="Resource is outside the current domain")


def assert_project_domain(domain_id: str, project_id: str, *, operation=None) -> None:
    if not project_id:
        raise HTTPException(status_code=403, detail="A project scope is required")
    try:
        project = (
            operation.get("projects", project_id)
            if operation is not None
            else keystone._get_admin_ks_client().projects.get(project_id)
        )
    except (NotFound, ClientNotFound) as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Project directory is unavailable") from exc
    if _id(project) != project_id:
        raise HTTPException(status_code=503, detail="Project identity does not match")
    assert_domain_resource(domain_id, identity_roles._field(project, "domain_id"))
    if identity_roles._field(project, "enabled") is not True:
        raise HTTPException(status_code=403, detail="Project is disabled")


def has_scope_authority(user_id: str, *, domain_id: str | None = None, operation=None) -> bool:
    """Resolve exact-scope native grants through the actual trusted role-ID DAG.

    Keystone's effective assignment path omits system grants. For system scope,
    use raw user/group grants and the user's native group memberships instead.
    Project/domain grants and malformed or unattributable rows never authorize.
    """
    if not user_id:
        return False
    if domain_id:
        from app.services.domain_projects import has_manager

        return has_manager(user_id, domain_id, **({"operation": operation} if operation is not None else {}))
    try:
        ks = operation.ks if operation is not None else keystone._get_admin_ks_client()
        user_grants = (
            operation.read(
                ("domain_scope", "system_user_grants", user_id),
                lambda: list(ks.role_assignments.list(user=user_id, system="all")),
            )
            if operation is not None
            else ks.role_assignments.list(user=user_id, system="all")
        )
        rows = [(row, "user", user_id) for row in user_grants]
        groups = (
            operation.read(("domain_scope", "user_groups", user_id), lambda: list(ks.groups.list(user=user_id)))
            if operation is not None
            else ks.groups.list(user=user_id)
        )
        group_ids = set()
        for group in groups:
            gid = _id(group)
            if not isinstance(gid, str) or not gid:
                raise ValueError("System grant group membership is unresolved")
            group_ids.add(gid)
        for gid in sorted(group_ids):
            grants = (
                operation.read(
                    ("domain_scope", "system_group_grants", gid),
                    lambda gid=gid: list(ks.role_assignments.list(group=gid, system="all")),
                )
                if operation is not None
                else ks.role_assignments.list(group=gid, system="all")
            )
            rows.extend((row, "group", gid) for row in grants)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Role assignments are unavailable") from exc
    exact = []
    for row, principal, principal_id in rows:
        scope = identity_roles._field(row, "scope", {})
        if not isinstance(scope, dict):
            continue
        system = scope.get("system")
        matches = (
            set(scope) == {"system"} and isinstance(system, dict) and set(system) == {"all"} and system["all"] is True
        )
        if identity_roles._field(row, "group" if principal == "user" else "user") is not None:
            continue
        if matches and _id(identity_roles._field(row, principal, {})) == principal_id:
            exact.append(row)
    if not exact:
        return False
    try:
        catalog = operation.catalog() if operation is not None else identity_roles._trusted_catalog()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Assigned role graph is unavailable") from exc
    by_id = {role["id"]: role for role in catalog}
    names = {"admin"}
    targets = set()
    for name in names:
        matches = [role for role in catalog if role["name"].casefold() == name and role["domain_id"] is None]
        if not matches:
            continue
        if len(matches) != 1 or matches[0]["name"] != name:
            raise HTTPException(status_code=503, detail="Authority requires a unique canonical global role")
        targets.add(matches[0]["id"])
    for row in exact:
        rid = _id(identity_roles._field(row, "role", {}))
        if rid not in by_id:
            raise HTTPException(status_code=503, detail="Assigned role graph is unavailable")
        expanded = {rid, *by_id[rid]["inherited_role_ids"]}
        for role_id in expanded:
            role = by_id[role_id]
            if not role_eligible(role, domain_id):
                raise HTTPException(status_code=503, detail="Role graph crosses its authority domain")
            if role["name"].casefold() in names and role_id not in targets:
                raise HTTPException(status_code=503, detail="Authority role is not canonical")
        if targets.intersection(expanded):
            return True
    return False


def role_eligible(role: dict, domain_id: str | None) -> bool:
    """Global roles and roles owned by this exact domain are selectable."""
    return role.get("domain_id") is None or bool(domain_id and role.get("domain_id") == domain_id)


def domain_context(user_id: str, domain_id: str, *, operation=None) -> dict:
    from app.services.native_operation import NativeOperation

    if operation is None:
        with NativeOperation() as operation:
            return domain_context(user_id, domain_id, operation=operation)
    domain = resolve_domain(domain_id, operation=operation)
    # Context arguments must be canonical IDs, not an alias accepted by resolve.
    assert_domain_resource(domain_id, domain["id"])
    if domain.get("kind") == "account":
        raise HTTPException(403, "account_domain_is_identity_only")
    try:
        user = keystone.get_identity_user(user_id, **({"operation": operation} if operation is not None else {}))
    except (Unauthorized, NotFound, ClientNotFound) as exc:
        raise HTTPException(status_code=401, detail="Identity is disabled or unavailable; log in again") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Identity directory is unavailable") from exc
    from app.services import domain_projects

    identity_domain = resolve_domain(user["domain_id"], operation=operation)
    context = {"operation": operation} if operation is not None else {}
    try:
        domain_projects.assert_membership(user_id, domain_id, **context)
    except HTTPException as exc:
        if exc.status_code != 403 or not has_scope_authority(user_id, operation=operation):
            raise
    return {
        "identity_domain_id": identity_domain["id"],
        "identity_domain_name": identity_domain["name"],
        "domain_id": domain["id"],
        "domain_name": domain["name"],
        "domain_kind": domain.get("kind", "legacy"),
        "is_domain_manager": domain_projects.has_manager(user_id, domain["id"], **context),
    }


def assert_token_context(
    info: dict,
    *,
    user_id: str,
    domain_id: str,
    project_id: str,
    identity_domain_id: str | None = None,
    operation=None,
) -> None:
    """Fence every exchange result before publishing a token or rotating a session."""
    if not user_id or info.get("user_id") != user_id or info.get("project_id", "") != project_id:
        raise HTTPException(status_code=403, detail="Keystone token subject or project does not match")
    assert_domain_resource(domain_id, info.get("domain_id"))
    if identity_domain_id is not None:
        assert_domain_resource(identity_domain_id, info.get("identity_domain_id"))
    if project_id:
        assert_project_domain(domain_id, project_id, operation=operation)


async def invalidate_authority(*, operation=None) -> None:
    """Fence scope caches after native mutations, never durable role visibility.

    Clearing all three small namespaces covers effective group/role graph changes
    without guessing their holders; no credentials or persistent settings change.
    """
    from app.services.cache import invalidate

    if operation is not None:
        operation.invalidate()

    for pattern in (
        "afterglow:identity:domain-context:*",
        "afterglow:identity:system-admin:*",
        "afterglow:identity:project-domain:*",
    ):
        await invalidate(pattern)
