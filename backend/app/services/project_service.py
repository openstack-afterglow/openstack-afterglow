"""Domain-bound project creation and native role-graph membership management."""

import asyncio
import logging
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import HTTPException
from sqlalchemy import select

from app.models.db import ProjectRole
from app.services import activity, cache, identity_roles, keystone
from app.services.cache import keys
from app.services.service_permissions import ROLE_PRESETS, SERVICE_ROLE_GRADES

_logger = logging.getLogger(__name__)


async def invalidate_project_lists(user_id, domain_id):
    await cache.invalidate(keys.user_key(user_id, f"domain:{domain_id}:projects"))
    await cache.invalidate("afterglow:admin:projects:*")
    await cache.invalidate("afterglow:admin:project_names:*")


# ─── 프로젝트 생성 ────────────────────────────────────────────────────────────


@identity_roles._complete_mutation
async def create_project_for_user(
    name: str,
    description: str,
    user_id: str,
    username: str,
    domain_id: str,
) -> dict:
    """Create a project and explicitly grant its creator the existing owner role."""
    from app.config import get_settings
    from app.services import domain_projects

    settings = get_settings()
    from app.services.domain_scope import resolve_domain

    domain = await asyncio.to_thread(resolve_domain, domain_id)
    from app.services.domain_scope import assert_domain_resource

    assert_domain_resource(domain_id, domain["id"])
    from app.services import account_spaces

    if domain.get("kind") == "account":
        raise HTTPException(403, "account_domain_is_identity_only")
    if domain.get("kind") == "personal":
        if name:
            raise HTTPException(422, "personal_project_name_is_generated")
        if not await can_create_project(user_id, domain_id):
            raise HTTPException(403, "Personal project creation requires current personal membership")
        return await account_spaces.create_personal_project(user_id, description=description)
    if not name:
        raise HTTPException(422, "프로젝트 이름을 입력하세요")
    if not await can_create_project(user_id, domain["id"]):
        raise HTTPException(status_code=403, detail="Domain project creation capability required")
    if name.casefold() == "default":
        raise HTTPException(status_code=409, detail="Default is reserved for the domain authority project")

    conn = await _provider_call(keystone.get_admin_project_connection)
    try:
        async with identity_roles._graph_lock(conn) as lease:
            if not await can_create_project(user_id, domain["id"]):
                raise HTTPException(status_code=403, detail="Domain project creation capability required")
            ks = await _provider_call(keystone._get_admin_ks_client)
            catalog = await _provider_call(identity_roles.load_catalog, conn)
            _required_project_role(catalog, "project_owner", require_hierarchy=True)
            existing = await _provider_call(lambda: list(ks.projects.list(domain=domain["id"])))
            existing_ids = set()
            for item in existing:
                pid = identity_roles._field(item, "id")
                if (
                    not isinstance(pid, str)
                    or not pid
                    or pid in existing_ids
                    or identity_roles._field(item, "domain_id") != domain["id"]
                ):
                    raise identity_roles._unavailable("Domain project inventory is unavailable")
                existing_ids.add(pid)
            kwargs = {"name": name, "domain": domain["id"], "enabled": False}
            if description:
                kwargs["description"] = description
            native = await identity_roles._write(lease, ks.projects.create, **kwargs)
            project_id = identity_roles._created_id(native)
            if project_id in existing_ids:
                raise identity_roles._unavailable("Native creation did not return a new project")
            project = {
                "id": project_id,
                "name": identity_roles._field(native, "name") or "",
                "description": identity_roles._field(native, "description") or "",
            }
            try:
                staged = await _provider_call(ks.projects.get, project_id)
                if (
                    identity_roles._field(staged, "id") != project_id
                    or identity_roles._field(staged, "name") != name
                    or identity_roles._field(staged, "domain_id") != domain["id"]
                    or identity_roles._field(staged, "enabled") is not False
                ):
                    raise identity_roles._unavailable("Native project was not created in the disabled requested domain")
                await _grant_project_role(
                    project_id,
                    user_id,
                    "project_owner",
                    require_hierarchy=True,
                    _mutation=(lease, ks, catalog, [], []),
                )
                await domain_projects.sync_manager_access(domain["id"], mutation=(lease, ks, catalog))
                from app.services.domain_quotas import apply_project_defaults

                await apply_project_defaults(conn, domain["id"], project_id, lease=lease)
                await _verify_unique_owner(ks, catalog, project_id, user_id)
                staged = await _provider_call(ks.projects.get, project_id)
                if (
                    identity_roles._field(staged, "domain_id") != domain["id"]
                    or identity_roles._field(staged, "enabled") is not False
                ):
                    raise identity_roles._unavailable("Staged project could not be verified")
                if not await can_create_project(user_id, domain["id"]):
                    raise HTTPException(403, "Project creation capability was revoked before activation")
                await identity_roles._write(lease, ks.projects.update, project_id, enabled=True)
                enabled = await _provider_call(ks.projects.get, project_id)
                if identity_roles._field(enabled, "enabled") is not True:
                    raise identity_roles._unavailable("Project activation could not be verified")
            except Exception:
                # Do not delete an uncertain native result. Disabled projects remain
                # visible to administrators for explicit recovery, never blind retry.
                await invalidate_project_lists(user_id, domain["id"])
                raise
    finally:
        await asyncio.to_thread(conn.close)

    # (best-effort) monitoring SG 자동 생성
    try:
        if settings.monitoring_auto_sg_enabled and settings.monitoring_scrape_cidr:
            from app.services import neutron

            def _ensure_sgs():
                conn = keystone.get_admin_connection_for_project(project_id)
                try:
                    neutron.ensure_node_exporter_sg(
                        conn,
                        project_id,
                        settings.node_exporter_sg_name,
                        settings.monitoring_scrape_cidr,
                    )
                    neutron.ensure_dcgm_exporter_sg(
                        conn,
                        project_id,
                        settings.dcgm_exporter_sg_name,
                        settings.monitoring_scrape_cidr,
                    )
                finally:
                    conn.close()

            await asyncio.to_thread(_ensure_sgs)
    except Exception:
        _logger.warning("모니터링 SG 자동 생성 실패 (계속 진행)", exc_info=True)

    await activity.record(
        project_id=project_id,
        user_id=user_id,
        username=username,
        resource_type="project",
        action="project_create",
        status="success",
        resource_id=project_id,
        resource_name=name,
    )

    await invalidate_project_lists(user_id, domain["id"])
    return project


# Keystone project membership. ProjectRole is intentionally used only by the
# explicit legacy migration below; it never participates in authorization.
_PROJECT_GRADES = {
    "project_owner": "owner",
    "project_admin": "admin",
    "project_member": "member",
    "project_reader": "reader",
}


async def _provider_call(fn, *args, **kwargs):
    try:
        return await asyncio.to_thread(fn, *args, **kwargs)
    except Exception as exc:
        raise identity_roles._provider_error(exc) from exc


def _assignment_rows(ks, project_id, *, effective=False, user_id=None):
    query = {"project": project_id}
    if user_id is not None:
        query["user"] = user_id
    if effective:
        query["effective"] = True
    rows = list(ks.role_assignments.list(**query))
    for row in rows:
        scope = identity_roles._field(row, "scope", {})
        if identity_roles._field(identity_roles._field(scope, "project", {}), "id") != project_id:
            raise identity_roles._unavailable("Keystone returned assignments outside the requested project")
        if set(scope) - {"project", "OS-INHERIT:inherited_to"}:
            raise identity_roles._unavailable("Ambiguous project role assignment scope")
        if "OS-INHERIT:inherited_to" in scope and scope["OS-INHERIT:inherited_to"] != "projects":
            raise identity_roles._unavailable("Unknown inherited project role assignment")
        if _principal(row, "user") and _principal(row, "group"):
            raise identity_roles._unavailable("Ambiguous project assignment principal")
        if not isinstance(_principal(row, "role"), str) or not _principal(row, "role"):
            raise identity_roles._unavailable("Malformed project role assignment")
        for kind in ("user", "group"):
            principal_id = _principal(row, kind)
            if principal_id is not None and (not isinstance(principal_id, str) or not principal_id):
                raise identity_roles._unavailable("Malformed project assignment principal")
        if effective and not _principal(row, "user"):
            raise identity_roles._unavailable("Effective project assignment did not resolve its user")
        if not effective and not (_principal(row, "user") or _principal(row, "group")):
            raise identity_roles._unavailable("Project assignment did not resolve its principal")
        if user_id is not None and _principal(row, "user") != user_id:
            raise identity_roles._unavailable("Keystone returned assignments outside the requested user")
    return rows


def _principal(row, key):
    return identity_roles._field(identity_roles._field(row, key, {}), "id")


def _expanded_role_ids(rows, catalog, user_id):
    by_id = {role["id"]: role for role in catalog}
    canonical = {row["name"] for row in ROLE_PRESETS} | {"admin", "manager", "member", "reader"}
    bindings = {}
    for role in catalog:
        folded = role["name"].casefold()
        if role["domain_id"] is None and folded in canonical:
            bindings.setdefault(folded, []).append(role)
    result, active = set(), set()

    def visit(rid):
        if rid not in by_id:
            raise identity_roles._unavailable("Assigned role graph references an unknown role")
        if rid in active:
            raise identity_roles._unavailable("Assigned role graph contains a cycle")
        if rid in result:
            return
        role = by_id[rid]
        name = role["name"]
        if name.casefold() in canonical:
            matches = bindings.get(name.casefold(), ())
            if name != name.casefold() or role["domain_id"] is not None or len(matches) != 1 or matches[0]["id"] != rid:
                raise identity_roles._unavailable("Effective authority must bind a unique canonical global role ID")
        active.add(rid)
        for child in role["implied_role_ids"]:
            visit(child)
        active.remove(rid)
        result.add(rid)

    for row in rows:
        if _principal(row, "user") == user_id:
            visit(_principal(row, "role"))
    return result


def _access(rows, catalog, user_id):
    ids = _expanded_role_ids(rows, catalog, user_id)
    names = sorted(role["name"] for role in catalog if role["id"] in ids)
    if {"project_owner", "project_admin"} & set(names):
        safe = _managed_roles(catalog)
        for name in {"project_owner", "project_admin"} & set(names):
            matches = [row for row in catalog if row["domain_id"] is None and row["name"] == name]
            if len(matches) != 1 or matches[0]["id"] not in safe:
                raise identity_roles._unavailable("Project management role graph is unsafe")
    return {
        "is_owner": "project_owner" in names,
        "is_manager": bool({"project_owner", "project_admin"} & set(names)),
        "roles": names,
    }


async def get_project_access(project_id: str, user_id: str) -> dict:
    """Uncached trusted effective assignments are the sole management authority.

    Provider/graph failures are errors, never stale DB or token-role fallbacks.
    """
    ks = await _provider_call(keystone._get_admin_ks_client)
    catalog = await _provider_call(identity_roles._trusted_catalog)
    rows = await _provider_call(_assignment_rows, ks, project_id, effective=True)
    return _access(rows, catalog, user_id)


async def get_project_delegation_roles(project_id: str, user_id: str) -> list[dict]:
    """Current assignment/graph metadata only; never a credential-issuing connection."""
    ks = await _provider_call(keystone._get_admin_ks_client)
    catalog = await _provider_call(identity_roles._trusted_catalog)
    rows = await _provider_call(_assignment_rows, ks, project_id, effective=True, user_id=user_id)
    role_ids = _expanded_role_ids(rows, catalog, user_id)
    return [
        {"id": role["id"], "name": role["name"], "inherited_role_ids": role["inherited_role_ids"]}
        for role in catalog
        if role["id"] in role_ids
    ]


@asynccontextmanager
async def _membership_write(project_id):
    # Identity management uses the configured admin project, not a newly created
    # tenant where the service user has no assignment yet. Target scope is always
    # supplied explicitly to the trusted role-assignment API.
    conn = await _provider_call(keystone.get_admin_project_connection)
    try:
        async with identity_roles._graph_lock(conn) as lease:
            ks = await _provider_call(keystone._get_admin_ks_client)
            catalog = await _provider_call(identity_roles.load_catalog, conn)
            effective = await _provider_call(_assignment_rows, ks, project_id, effective=True)
            direct = await _provider_call(_assignment_rows, ks, project_id)
            yield lease, ks, catalog, effective, direct
    finally:
        await asyncio.to_thread(conn.close)


def _check_scope(project_id, token_info):
    if token_info.get("project_id") != project_id:
        raise HTTPException(status_code=403, detail="Membership changes require the current project")


async def _domain_access(
    project_id, token_info, domain_management=False, user_id=None, *, _allow_native_admin_removal=False
):
    """Resolve object boundaries and explicit live domain authority, never token claims."""
    from app.services.domain_scope import assert_domain_resource, domain_context

    domain_id = token_info.get("domain_id")
    if not domain_id:
        raise HTTPException(status_code=403, detail="An authoritative domain is required")
    ks = await _provider_call(keystone._get_admin_ks_client)
    project = await _provider_call(ks.projects.get, project_id)
    assert_domain_resource(domain_id, identity_roles._field(project, "domain_id"))
    if identity_roles._field(project, "enabled") is not True:
        raise HTTPException(status_code=403, detail="Project is disabled")
    if user_id:
        user = await _provider_call(ks.users.get, user_id)
        if not isinstance(identity_roles._field(user, "domain_id"), str):
            raise identity_roles._unavailable("Identity domain is unavailable")
    context = await _provider_call(domain_context, token_info["user_id"], domain_id)
    if context.get("domain_kind") == "personal":
        if identity_roles._field(project, "afterglow_personal_user_id") != token_info["user_id"]:
            raise HTTPException(403, "personal_project_owner_required")
        if user_id is not None and user_id != token_info["user_id"]:
            raise HTTPException(403, "personal_project_membership_is_private")
    if not domain_management:
        if not context["is_domain_manager"]:
            _check_scope(project_id, token_info)
        return context["is_domain_manager"]
    if not context["is_domain_manager"]:
        raise HTTPException(status_code=403, detail="Domain manager required")
    if user_id:
        from app.services.domain_iam import protected_user

        if await protected_user(
            user,
            domain_id,
            credentials=False,
            membership_project_id=project_id if _allow_native_admin_removal else None,
        ):
            raise HTTPException(status_code=403, detail="Privileged accounts are read-only in domain IAM")
    return True


def _authorize(project_id, token_info, effective, catalog, *, domain_authority=False):
    if not domain_authority:
        _check_scope(project_id, token_info)
    access = _access(effective, catalog, token_info["user_id"])
    if not access["is_manager"] and not domain_authority:
        raise HTTPException(status_code=403, detail="Project management role required")
    return access


def _direct_ids(rows, user_id):
    return {
        _principal(row, "role")
        for row in rows
        if _principal(row, "user") == user_id and not _group_ids(row) and not _inherited_assignment(row)
    }


def _group_ids(row):
    group_id = _principal(row, "group")
    if group_id:
        return {group_id}
    membership = identity_roles._field(identity_roles._field(row, "links", {}), "membership")
    if not membership:
        return set()
    if not isinstance(membership, str):
        raise identity_roles._unavailable("Malformed effective group assignment")
    parts = urlparse(membership).path.split("/")
    if "groups" not in parts or parts.index("groups") + 1 >= len(parts):
        raise identity_roles._unavailable("Malformed effective group assignment")
    return {parts[parts.index("groups") + 1]}


def _inherited_assignment(row):
    scope = identity_roles._field(row, "scope", {})
    links = identity_roles._field(row, "links", {})
    assignment = identity_roles._field(links, "assignment", "") or ""
    if not isinstance(assignment, str):
        raise identity_roles._unavailable("Malformed inherited assignment source")
    return bool(
        identity_roles._field(scope, "OS-INHERIT:inherited_to")
        or "/domains/" in assignment
        or "/OS-INHERIT/" in assignment
    )


async def _member(ks, user_id, catalog, effective, direct, domain_id):
    effective_ids = _expanded_role_ids(effective, catalog, user_id)
    direct_ids = _direct_ids(direct, user_id)
    if not direct_ids <= {row["id"] for row in catalog}:
        raise identity_roles._unavailable("Direct assignment role is absent from the current catalog")
    user = await _provider_call(ks.users.get, user_id)
    groups = set()
    inherited = False
    external = []
    for row in effective:
        if _principal(row, "user") == user_id:
            row_groups = _group_ids(row)
            row_inherited = _inherited_assignment(row)
            groups.update(row_groups)
            inherited = inherited or row_inherited
            if row_groups or row_inherited:
                external.append(row)
    group_names = []
    for gid in sorted(groups):
        group = await _provider_call(ks.groups.get, gid)
        group_names.append(identity_roles._field(group, "name") or gid)
    access = _access(effective, catalog, user_id)
    source = (
        "mixed"
        if direct_ids and (groups or inherited)
        else "direct"
        if direct_ids
        else "group"
        if groups
        else "inherited"
    )
    result = {
        "user_id": user_id,
        "username": identity_roles._field(user, "name") or "",
        "email": identity_roles._field(user, "email") or "",
        "domain_id": identity_roles._field(user, "domain_id"),
        "identity_read_only": identity_roles._field(user, "domain_id") != domain_id,
        "source": source,
        **access,
        "direct_role_ids": sorted(direct_ids),
        "effective_role_ids": sorted(effective_ids),
        "external_role_ids": sorted(_expanded_role_ids(external, catalog, user_id)),
    }
    if group_names:
        result["group_name"] = ", ".join(group_names)
    return result


async def list_members(project_id, token_info, *, domain_management=False):
    authority = await _domain_access(project_id, token_info, domain_management)
    ks = await _provider_call(keystone._get_admin_ks_client)
    catalog = await _provider_call(identity_roles._trusted_catalog)
    effective = await _provider_call(_assignment_rows, ks, project_id, effective=True)
    _authorize(project_id, token_info, effective, catalog, domain_authority=authority)
    direct = await _provider_call(_assignment_rows, ks, project_id)
    users = {_principal(row, "user") for row in effective + direct}
    users.discard(None)
    return {
        "items": [await _member(ks, uid, catalog, effective, direct, token_info["domain_id"]) for uid in sorted(users)]
    }


def _managed_roles(catalog):
    """Keep canonical grades bounded while preserving administrator custom edges."""
    definitions = {row["name"]: row for row in ROLE_PRESETS}
    by_id = {row["id"]: row for row in catalog}
    by_name = {}
    for row in catalog:
        if row["domain_id"] is None:
            by_name.setdefault(row["name"].casefold(), []).append(row)
    result = {}
    for name, definition in definitions.items():
        matches = by_name.get(name, [])
        if not matches:
            continue
        if len(matches) != 1 or matches[0]["name"] != name:
            raise identity_roles._unavailable("Managed role binding is ambiguous")
        row = matches[0]
        area, grade = definition["area"], definition["grade"]
        if name in _PROJECT_GRADES:
            order = ["project_owner", "project_admin", "project_member", "project_reader"]
            allowed = set(order[order.index(name) :]) | {"member", "reader"}
            if name == "project_reader":
                allowed.discard("member")
        else:
            grades = SERVICE_ROLE_GRADES.get(area, {})
            order = ["admin", "editor", "user", "reader"]
            if grade not in order or grade not in grades:
                continue
            if name != f"{area}_{grade}":
                # Fine-grained grants may acquire their own service's read-only
                # discovery bundle, never another use/write capability.
                allowed = {name}
                if grade != "reader":
                    allowed.add(f"{area}_reader")
                    allowed.update(grades.get("reader", ()))
            else:
                lower = order[order.index(grade) :]
                allowed = {f"{area}_{level}" for level in lower}
                allowed.update(leaf for level in lower for leaf in grades.get(level, ()))
        descendant_ids = row["inherited_role_ids"]
        descendants = {by_id[rid]["name"] for rid in descendant_ids}
        bounded_descendants = {
            name
            for name in descendants
            if name.casefold() in definitions or name.casefold() in identity_roles.CORE_NAMES
        }
        cyclic = any(
            rid == row["id"] or row["id"] in by_id[rid]["inherited_role_ids"] for rid in row["implied_role_ids"]
        )
        if row["system_only"] or cyclic or not bounded_descendants <= allowed:
            continue
        # Reject a domain-specific/duplicate descendant, even when its label is safe.
        if any(
            by_id[rid]["domain_id"] is not None or len(by_name.get(by_id[rid]["name"].casefold(), ())) != 1
            for rid in descendant_ids
        ):
            continue
        result[row["id"]] = {**row, "area": area, "grade": grade}
    return result


def _required_project_role(catalog, name, *, require_hierarchy=False):
    managed = _managed_roles(catalog)
    matches = [row for row in managed.values() if row["name"] == name]
    if len(matches) != 1:
        raise HTTPException(status_code=409, detail="Apply the safe project role preset before assigning membership")
    row = matches[0]
    if require_hierarchy:
        order = ["project_owner", "project_admin", "project_member", "project_reader"]
        expected = set(order[order.index(name) + 1 :]) | {"reader"}
        if name != "project_reader":
            expected.add("member")
        by_id = {item["id"]: item for item in catalog}
        descendants = {by_id[rid]["name"] for rid in row["inherited_role_ids"]}
        if not expected <= descendants:
            raise HTTPException(status_code=409, detail="Project role hierarchy is incomplete")
    return row


async def assignable_roles(project_id, token_info, *, domain_management=False):
    authority = await _domain_access(project_id, token_info, domain_management)
    ks = await _provider_call(keystone._get_admin_ks_client)
    catalog = await _provider_call(identity_roles._trusted_catalog)
    effective = await _provider_call(_assignment_rows, ks, project_id, effective=True)
    access = _authorize(project_id, token_info, effective, catalog, domain_authority=authority)
    roles = [
        *_managed_roles(catalog).values(),
        *({**row, "area": "legacy", "grade": "admin"} for row in catalog if row["name"].casefold() == "admin"),
    ]
    return {
        "roles": [
            row
            for row in roles
            if row["name"] != "project_owner" and (authority or access["is_owner"] or row["name"] != "project_admin")
        ],
        "is_owner": access["is_owner"],
        "can_manage_owners": False,
    }


@asynccontextmanager
async def _using_snapshot(snapshot):
    yield snapshot


@identity_roles._complete_mutation
async def replace_member_roles(
    project_id,
    user_id,
    role_ids,
    token_info,
    *,
    remove=False,
    domain_management=False,
    additive=False,
    _mutation=None,
    _before_write=None,
):
    authority = await _domain_access(project_id, token_info, domain_management, None if domain_management else user_id)
    mutation = _using_snapshot(_mutation) if _mutation is not None else _membership_write(project_id)
    async with mutation as (lease, ks, catalog, effective, direct):
        authority = await _domain_access(
            project_id, token_info, domain_management, None if domain_management else user_id
        )
        access = _authorize(project_id, token_info, effective, catalog, domain_authority=authority)
        target = _access(effective, catalog, user_id)
        if not target["roles"] and remove:
            raise HTTPException(status_code=404, detail="User is not an effective member of this project")
        if not remove:
            await _eligible_user(ks, token_info["domain_id"], user_id)
        if target["is_owner"] and not access["is_owner"] and not authority:
            raise HTTPException(status_code=403, detail="Only an owner may edit another owner's assignments")
        managed = _managed_roles(catalog)
        direct_ids = _direct_ids(direct, user_id)
        if not direct_ids <= {row["id"] for row in catalog}:
            raise identity_roles._unavailable("Direct assignment role is absent from the current catalog")
        native_admin_ids = {row["id"] for row in catalog if row["name"].casefold() == "admin"}
        removable = set(managed) | native_admin_ids
        current = direct_ids & removable
        requested = set(role_ids)
        if requested & native_admin_ids - direct_ids:
            raise HTTPException(status_code=422, detail="Native admin project grants are removal-only")
        if len(role_ids) != len(requested) or not requested <= set(managed) | direct_ids:
            raise HTTPException(
                status_code=422, detail="Select unique safe assignable role IDs; unrelated grants are read-only"
            )
        # Existing direct admin is removal-only; unrelated native/custom grants
        # remain immutable even when included in the full direct selection.
        desired = requested & removable
        if additive:
            desired |= current
        from app.services import domain_projects

        default = await _provider_call(domain_projects.default_project, token_info["domain_id"], ks=ks)
        from app.services.account_spaces import domain_kind

        domain = await _provider_call(ks.domains.get, token_info["domain_id"])
        personal = domain_kind(domain) == "personal"
        from app.services import account_spaces

        legacy_personal = personal and account_spaces._personal_member_role(catalog)["id"] not in direct_ids
        if personal and (remove or requested != {account_spaces._personal_member_role(catalog)["id"]}):
            raise HTTPException(403, "personal_project_roles_are_fixed")
        if (default is not None and default["id"] == project_id) or legacy_personal:
            # Organizational Default and established owner-based personal projects
            # retain their reader baseline. Native member grants remain untouched.
            baseline = _required_project_role(catalog, "project_reader", require_hierarchy=True)
            desired.add(baseline["id"])
        if domain_management:
            # Native-admin holders remain protected except for a locked,
            # exact admin-only revocation with every other grant unchanged.
            admin_only_removal = (
                bool(current - desired) and (current - desired) <= native_admin_ids and not (desired - current)
            )
            await _domain_access(
                project_id,
                token_info,
                domain_management,
                user_id,
                _allow_native_admin_removal=admin_only_removal,
            )
        for rid in desired - current:
            await _provider_call(domain_projects.assert_manager_assignment, project_id, rid, catalog=catalog, ks=ks)
        for rid in current - desired:
            if rid in native_admin_ids and identity_roles._manager_bearing_role(catalog, rid):
                await _provider_call(
                    domain_projects.assert_managers_remain,
                    ks=ks,
                    catalog=catalog,
                    project_id=project_id,
                    role_id=rid,
                    user_id=user_id,
                    remove_assignment=True,
                )
        for rid in desired:
            if rid in managed and managed[rid]["name"] in _PROJECT_GRADES:
                _required_project_role(catalog, managed[rid]["name"], require_hierarchy=True)
        protected = {rid for rid, row in managed.items() if row["name"] in {"project_owner", "project_admin"}}
        if not access["is_owner"] and not authority and (desired ^ current) & protected:
            raise HTTPException(status_code=403, detail="Only an owner may change project owner/admin grants")
        if any(identity_roles._owner_bearing_role(catalog, rid) for rid in desired ^ current):
            raise HTTPException(status_code=409, detail="Use explicit project ownership transfer")
        await identity_roles._session_ready({user_id} if current != desired else ())
        if _before_write is not None:
            await _before_write(sorted(desired - current))
        changed = False
        try:
            for rid in sorted(desired - current):
                changed = True
                await identity_roles._write(lease, ks.roles.grant, rid, user=user_id, project=project_id)
            for rid in sorted(current - desired):
                changed = True
                await identity_roles._write(lease, ks.roles.revoke, rid, user=user_id, project=project_id)
            if changed:
                await domain_projects.sync_manager_access(token_info["domain_id"], mutation=(lease, ks, catalog))
        finally:
            if changed:
                await invalidate_project_lists(user_id, token_info["domain_id"])
                await identity_roles._applied(
                    None,
                    catalog,
                    None,
                    {user_id},
                    token_info,
                    "project_member_remove" if remove else "project_member_roles",
                    {"project_id": project_id, "user_id": user_id},
                )
        fresh_effective = await _provider_call(_assignment_rows, ks, project_id, effective=True)
        fresh_direct = await _provider_call(_assignment_rows, ks, project_id)
        return await _member(ks, user_id, catalog, fresh_effective, fresh_direct, token_info["domain_id"])


@identity_roles._complete_mutation
async def _grant_project_role(project_id, user_id, name, *, require_hierarchy=False, _mutation=None):
    mutation = _using_snapshot(_mutation) if _mutation is not None else _membership_write(project_id)
    async with mutation as (lease, ks, catalog, effective, direct):
        role = _required_project_role(catalog, name, require_hierarchy=require_hierarchy)
        await _eligible_user(
            ks, identity_roles._field(await _provider_call(ks.projects.get, project_id), "domain_id"), user_id
        )
        if name == "project_owner":
            from app.services import project_ownership_journal as journal

            await journal.assert_resolved(project_id)
            state = await _ownership_state(ks, catalog, project_id)
            if state["status"] != "missing" and not (state["status"] == "unique" and state["owner_user_id"] == user_id):
                raise HTTPException(status_code=409, detail="Project ownership is already assigned or ambiguous")
        if role["id"] not in _direct_ids(direct, user_id):
            if name == "project_owner":
                await _write_initial_owner(ks, catalog, lease, project_id, user_id, role)
            else:
                await identity_roles._write(lease, ks.roles.grant, role["id"], user=user_id, project=project_id)
        if name == "project_owner":
            await _verify_unique_owner(ks, catalog, project_id, user_id)
        user = await _provider_call(ks.users.get, user_id)
        await invalidate_project_lists(user_id, identity_roles._field(user, "domain_id"))


@identity_roles._complete_mutation
async def migrate_legacy_managers(project_id, owner_user_id, token_info, session):
    if token_info.get("is_system_admin") is not True:
        raise HTTPException(status_code=403, detail="Verified system administrator required for legacy migration")
    if not owner_user_id:
        raise HTTPException(status_code=422, detail="Choose owner_user_id explicitly")
    await _domain_access(project_id, token_info, user_id=owner_user_id)
    async with _membership_write(project_id) as (lease, ks, catalog, effective, direct):
        owner = _required_project_role(catalog, "project_owner", require_hierarchy=True)
        from app.services import project_ownership_journal as journal

        await journal.assert_resolved(project_id)
        state = await _ownership_state(ks, catalog, project_id)
        if state["status"] != "missing" and not (
            state["status"] == "unique" and state["owner_user_id"] == owner_user_id
        ):
            raise HTTPException(status_code=409, detail="Resolve existing ownership through explicit transfer")
        admin = _required_project_role(catalog, "project_admin", require_hierarchy=True)
        result = await session.execute(
            select(ProjectRole)
            .where(ProjectRole.project_id == project_id, ProjectRole.role == "manager")
            .with_for_update()
        )
        rows = list(result.scalars().all())
        if not rows:
            raise HTTPException(status_code=409, detail="No legacy manager rows remain to migrate")
        users = {row.user_id for row in rows} | {owner_user_id}
        for uid in sorted(users):
            user = await _provider_call(ks.users.get, uid)
            from app.services.domain_scope import assert_domain_resource

            assert_domain_resource(token_info["domain_id"], identity_roles._field(user, "domain_id"))
            if not _access(effective, catalog, uid)["roles"]:
                raise HTTPException(
                    status_code=409,
                    detail="Every migrated manager and the chosen owner must be a verified effective project member",
                )
        for uid in sorted(users):
            role = owner if uid == owner_user_id else admin
            if role["id"] not in _direct_ids(direct, uid):
                if uid == owner_user_id:
                    await _write_initial_owner(ks, catalog, lease, project_id, uid, role)
                else:
                    await identity_roles._write(lease, ks.roles.grant, role["id"], user=uid, project=project_id)
        verified = await _provider_call(_assignment_rows, ks, project_id, effective=True)
        for uid in users:
            access = _access(verified, catalog, uid)
            if not access["is_manager"] or (uid == owner_user_id and not access["is_owner"]):
                raise identity_roles._unavailable(
                    "Migration assignments could not be verified; legacy rows were retained"
                )
        await _verify_unique_owner(ks, catalog, project_id, owner_user_id)
        await lease.assert_owned()
        for row in rows:
            await session.delete(row)
        await session.commit()
        for uid in users:
            await invalidate_project_lists(uid, token_info["domain_id"])
        return {
            "project_id": project_id,
            "owner_user_id": owner_user_id,
            "migrated_user_ids": sorted({row.user_id for row in rows}),
            "deleted_legacy_rows": len(rows),
        }


async def can_create_project(user_id: str, domain_id: str, *, operation=None) -> bool:
    """Exact native capability; callers may share only their current read phase."""
    from app.services.domain_scope import domain_context
    from app.services.native_operation import NativeOperation

    if operation is None:
        async with NativeOperation() as operation:
            return await can_create_project(user_id, domain_id, operation=operation)
    try:
        context = await operation.run(domain_context, user_id, domain_id, operation=operation)
        if context.get("domain_kind") == "personal":
            from app.services.account_spaces import personal_project

            project = await operation.run(personal_project, user_id, operation=operation)
            return project is not None and project.get("enabled") is True
        if context["is_domain_manager"]:
            return True
        ks = await operation.run(getattr, operation, "ks")
        catalog = await operation.run(operation.catalog)
        matches = [r for r in catalog if r["domain_id"] is None and r["name"].casefold() == "project_creator"]
        if not matches:
            return False
        if len(matches) != 1 or matches[0]["name"] != "project_creator":
            raise identity_roles._unavailable("Project creator role is ambiguous")
        creator = matches[0]["id"]
        exact = await operation.run(_creator_assignments, ks, catalog, domain_id, effective=True, user_id=user_id)
        return creator in _expanded_role_ids(exact, catalog, user_id)
    except Exception as exc:
        raise identity_roles._provider_error(exc) from exc


async def _eligible_user(ks, domain_id, user_id):
    from app.services.domain_projects import assert_membership

    await _provider_call(assert_membership, user_id, domain_id, ks=ks)
    user = await _provider_call(ks.users.get, user_id)
    if identity_roles._field(user, "id") != user_id or identity_roles._field(user, "enabled") is not True:
        raise HTTPException(status_code=403, detail="An enabled joined-domain user is required")
    return user


async def eligible_project_users(project_id, token_info):
    authority = await _domain_access(project_id, token_info)
    ks = await _provider_call(keystone._get_admin_ks_client)
    catalog = await _provider_call(identity_roles._trusted_catalog)
    effective = await _provider_call(_assignment_rows, ks, project_id, effective=True)
    _authorize(project_id, token_info, effective, catalog, domain_authority=authority)
    from app.services.domain_iam import directory_users
    from app.services.domain_scope import resolve_domain

    domain = await _provider_call(resolve_domain, token_info["domain_id"])
    if domain.get("kind") == "personal":
        users = [await _provider_call(ks.users.get, token_info["user_id"])]
    else:
        users = await directory_users(token_info["domain_id"])
    return [
        {
            "id": identity_roles._field(user, "id"),
            "name": identity_roles._field(user, "name") or "",
            "email": identity_roles._field(user, "email") or "",
            "domain_id": identity_roles._field(user, "domain_id"),
            "enabled": True,
        }
        for user in users
        if identity_roles._field(user, "enabled") is True
    ]


def _ownership_state_sync(ks, catalog, project_id):
    """Reconcile raw native provenance with effective owners; never pick a winner."""
    from app.services import domain_projects

    owner = _required_project_role(catalog, "project_owner", require_hierarchy=True)
    project = ks.projects.get(project_id)
    if identity_roles._field(project, "id") != project_id:
        raise identity_roles._unavailable("Project identity could not be verified")
    raw = list(ks.role_assignments.list())
    sources = domain_projects._sources(ks, project, catalog, raw)
    bearing = [
        s for s in sources if owner["id"] in {s["role_id"], *identity_roles._descendant_ids(catalog, s["role_id"])}
    ]
    effective = _assignment_rows(ks, project_id, effective=True)
    effective_users = {
        _principal(row, "user")
        for row in effective
        if owner["id"] in _expanded_role_ids([row], catalog, _principal(row, "user"))
    }
    source_users = {uid for s in bearing for uid in s["users"]}
    if effective_users != source_users:
        raise identity_roles._unavailable("Native project ownership provenance is inconsistent")
    owners = []
    for uid in sorted(source_users):
        user = ks.users.get(uid)
        user_sources = [s for s in bearing if uid in s["users"]]
        direct = all(s["user_id"] == uid and not s["inherited"] and s["role_id"] == owner["id"] for s in user_sources)
        owners.append(
            {
                "user_id": uid,
                "name": identity_roles._field(user, "name") or uid,
                "source": "direct" if direct else "group_or_inherited",
            }
        )
    unique = len(owners) == 1 and len(bearing) == 1 and owners[0]["source"] == "direct"
    return {
        "project_id": project_id,
        "owner_user_id": owners[0]["user_id"] if unique else None,
        "status": "unique" if unique else "conflict" if bearing else "missing",
        "owners": owners,
    }


async def _ownership_state(ks, catalog, project_id):
    return await _provider_call(_ownership_state_sync, ks, catalog, project_id)


async def _verify_unique_owner(ks, catalog, project_id, user_id):
    state = await _ownership_state(ks, catalog, project_id)
    if state["status"] != "unique" or state["owner_user_id"] != user_id:
        raise identity_roles._unavailable("Unique explicit project ownership could not be verified")
    return state


async def project_ownership(project_id, token_info):
    authority = await _domain_access(project_id, token_info)
    ks = await _provider_call(keystone._get_admin_ks_client)
    catalog = await _provider_call(identity_roles._trusted_catalog)
    effective = await _provider_call(_assignment_rows, ks, project_id, effective=True)
    _authorize(project_id, token_info, effective, catalog, domain_authority=authority)
    state = await _ownership_state(ks, catalog, project_id)
    project = await _provider_call(ks.projects.get, project_id)
    from app.services import project_ownership_journal as journal

    operation = await journal.get(project_id)
    unresolved = operation is not None and operation["status"] != "completed"
    blocked = unresolved and operation["status"] != "settled"
    sole = state["status"] == "unique" and state["owner_user_id"] == token_info["user_id"]
    from app.services import domain_projects

    default = await _provider_call(domain_projects.default_project, token_info["domain_id"], ks=ks)
    immutable = (
        identity_roles._field(project, "name", "").casefold() == "default"
        or bool(default and default["id"] == project_id)
        or identity_roles._field(project, "afterglow_personal_primary") is True
    )
    from app.services.domain_scope import resolve_domain

    personal = (await _provider_call(resolve_domain, token_info["domain_id"])).get("kind") == "personal"
    return {
        **state,
        "transfer_operation": operation,
        "can_transfer": not personal
        and not immutable
        and not blocked
        and (
            (state["status"] == "unique" and (authority or sole))
            or (unresolved and state["status"] == "missing" and authority)
        ),
        "can_delete": not immutable
        and not unresolved
        and (authority or (sole and await can_create_project(token_info["user_id"], token_info["domain_id"]))),
    }


@identity_roles._complete_mutation
async def transfer_project_ownership(project_id, user_id, token_info):
    authority = await _domain_access(project_id, token_info)
    async with _membership_write(project_id) as (lease, ks, catalog, effective, direct):
        authority = await _domain_access(project_id, token_info)
        from app.services import domain_projects
        from app.services import project_ownership_journal as journal

        project = await _provider_call(ks.projects.get, project_id)
        from app.services.account_spaces import domain_kind

        domain = await _provider_call(ks.domains.get, token_info["domain_id"])
        if domain_kind(domain) == "personal":
            raise HTTPException(403, "personal_project_ownership_is_private")
        await _provider_call(domain_projects.assert_default_immutable, project_id, delete=True, project=project, ks=ks)
        await _eligible_user(ks, token_info["domain_id"], user_id)
        state = await _ownership_state(ks, catalog, project_id)
        operation = await journal.get(project_id)
        if operation and operation["status"] in {"applying", "unknown"}:
            raise HTTPException(409, "project_ownership_native_operation_unresolved")
        if operation and operation["status"] == "settled":
            if operation["to_user_id"] != user_id or (
                not authority and operation["from_user_id"] != token_info["user_id"]
            ):
                raise HTTPException(409, "project_ownership_recovery_target_mismatch")
            old = operation["from_user_id"]
            if state["status"] == "conflict" or state["owner_user_id"] not in {None, old, user_id}:
                raise HTTPException(409, "Native ownership conflicts with settled transfer recovery")
        else:
            if state["status"] != "unique":
                raise HTTPException(409, "Project ownership is missing or conflicting; no grants were changed")
            old = state["owner_user_id"]
            if not authority and old != token_info["user_id"]:
                raise HTTPException(403, "Only the current sole owner or domain manager may transfer ownership")
            if old == user_id:
                raise HTTPException(409, "The selected user already owns this project")
        role = _required_project_role(catalog, "project_owner", require_hierarchy=True)
        await identity_roles._session_ready({old, user_id})
        operation = await journal.begin(project_id, token_info["domain_id"], old, user_id, lease=lease)
        succeeded = False
        try:
            if state["owner_user_id"] == old:
                await journal.phase(operation, "applying", "revoke", lease=lease)
                await identity_roles._write(lease, ks.roles.revoke, role["id"], user=old, project=project_id)
            state = await _ownership_state(ks, catalog, project_id)
            if state["status"] == "missing":
                await journal.phase(operation, "applying", "grant", lease=lease)
                await identity_roles._write(lease, ks.roles.grant, role["id"], user=user_id, project=project_id)
            await _verify_unique_owner(ks, catalog, project_id, user_id)
            operation = await journal.phase(operation, "completed", "verified", lease=lease)
            succeeded = True
        except Exception:
            # A readback cannot prove that a timed-out native request stopped.
            # Persist a fence; NEVER replay from current observations alone.
            await journal.phase(operation, "unknown", "native_outcome_unknown", lease=lease)
            raise
        finally:
            for uid in {old, user_id}:
                await invalidate_project_lists(uid, token_info["domain_id"])
            await identity_roles._applied(
                None,
                catalog,
                None,
                {old, user_id},
                token_info,
                "project_ownership_transfer",
                {"project_id": project_id, "operation_id": operation["id"]},
                status="success" if succeeded else "failed",
            )
        return {
            **await _verify_unique_owner(ks, catalog, project_id, user_id),
            "transfer_operation": operation,
            "can_transfer": authority,
            "can_delete": authority,
        }


async def project_deletion_check(project_id, token_info):
    ownership = await project_ownership(project_id, token_info)
    if not ownership["can_delete"]:
        raise HTTPException(403, "Project deletion requires a manager or creator with sole ownership")
    return await inspect_project_empty(project_id)


async def inspect_project_empty(project_id):
    """Trusted creation compensation uses the same exhaustive proof, no force."""
    from app.services import project_ownership_journal as journal
    from app.services.project_deletion import inspect_project_resources

    await journal.assert_resolved(project_id)
    conn = await _provider_call(keystone.get_admin_project_connection)
    try:
        check = await identity_roles._to_completion(_provider_call(inspect_project_resources, conn, project_id))
        ks = await _provider_call(keystone._get_admin_ks_client)
        check["resources"].append(
            await identity_roles._to_completion(_provider_call(inspect_child_projects, ks, project_id))
        )
        check["can_delete"] = all(
            row["status"] == "skipped" or (row["status"] == "ok" and row["count"] == 0) for row in check["resources"]
        )
        return check
    finally:
        await asyncio.to_thread(conn.close)


@identity_roles._complete_mutation
async def delete_empty_project(project_id, token_info):
    async with _membership_write(project_id) as (lease, ks, catalog, effective, direct):
        check = await project_deletion_check(project_id, token_info)
        if any(row["status"] == "unavailable" for row in check["resources"]):
            raise HTTPException(503, "Project resource inventory is unavailable; nothing was deleted")
        if not check["can_delete"]:
            raise HTTPException(409, "Project still owns resources or child projects")
        from app.services import domain_projects

        project = await _provider_call(ks.projects.get, project_id)
        await _provider_call(domain_projects.assert_default_immutable, project_id, delete=True, project=project, ks=ks)
        # Re-read live actor authority immediately before the destructive write.
        if not (await project_ownership(project_id, token_info))["can_delete"]:
            raise HTTPException(403, "Project deletion authority changed")
        try:
            await identity_roles._write(lease, ks.projects.delete, project_id)
        finally:
            from app.services.domain_scope import invalidate_authority

            await invalidate_authority()
            await invalidate_project_lists(token_info["user_id"], token_info["domain_id"])


def assert_user_ownership_mutation_safe(user_id, *, ks=None):
    """Generic identity disable/delete must not erase project ownership authority."""
    ks = ks or keystone._get_admin_ks_client()
    catalog = identity_roles._trusted_catalog()
    for row in ks.role_assignments.list(user=user_id, effective=True):
        from app.services import domain_projects

        meta = domain_projects._assignment(row, catalog, effective=True)
        if meta["user_id"] != user_id:
            raise identity_roles._unavailable("Identity ownership scope is unavailable")
        if meta["kind"] == "project" and identity_roles._owner_bearing_role(catalog, meta["role_id"]):
            raise HTTPException(409, "Transfer project ownership before disabling or deleting this identity")


def inspect_child_projects(ks, project_id):
    """Exhaust native children; unsupported or malformed results are unknown."""
    entry = {"kind": "child_projects", "service": "identity", "status": "ok", "count": 0, "samples": [], "reason": None}
    seen = set()
    try:
        for child in ks.projects.list(parent=project_id):
            cid = identity_roles._field(child, "id")
            if (
                not isinstance(cid, str)
                or not cid
                or cid in seen
                or identity_roles._field(child, "parent_id") != project_id
            ):
                raise ValueError("Unverified project hierarchy")
            seen.add(cid)
            entry["count"] += 1
            if len(entry["samples"]) < 5:
                entry["samples"].append({"id": cid})
    except Exception:
        entry.update(status="unavailable", count=None, reason="project_hierarchy_unavailable", samples=[])
    return entry


async def initialize_system_project_owner(project_id, user_id, domain_id, *, lease, ks, catalog, previous_project_ids):
    """Trusted admin create only: new disabled project establishes joined membership.

    Caller must capture the complete target-domain project IDs under this same
    graph lease before its single native create; never expose these inputs in a
    generic membership request. This does not authorize enablement or quotas.
    """
    from app.services.domain_scope import has_scope_authority

    await lease.assert_owned()
    if not isinstance(previous_project_ids, set) or project_id in previous_project_ids:
        raise HTTPException(409, "Initial ownership requires a proven newly created project")
    if not await _provider_call(has_scope_authority, user_id):
        raise HTTPException(403, "Current system administrator required for privileged project initialization")
    project = await _provider_call(ks.projects.get, project_id)
    if (
        identity_roles._field(project, "id") != project_id
        or identity_roles._field(project, "domain_id") != domain_id
        or identity_roles._field(project, "enabled") is not False
        or identity_roles._field(project, "name", "").casefold() == "default"
    ):
        raise HTTPException(409, "Initial ownership requires an exact newly created disabled ordinary project")
    user = await _provider_call(ks.users.get, user_id)
    if identity_roles._field(user, "id") != user_id or identity_roles._field(user, "enabled") is not True:
        raise HTTPException(403, "Enabled creator identity required")
    state = await _ownership_state(ks, catalog, project_id)
    from app.services import project_ownership_journal as journal

    await journal.assert_resolved(project_id)
    if state["status"] != "missing":
        raise HTTPException(409, "Initial ownership cannot replace existing or unresolved ownership")
    role = _required_project_role(catalog, "project_owner", require_hierarchy=True)
    await _write_initial_owner(ks, catalog, lease, project_id, user_id, role)
    await invalidate_project_lists(user_id, domain_id)


async def project_creators(domain_id, user_id):
    from app.services.domain_scope import domain_context

    context = await _provider_call(domain_context, user_id, domain_id)
    if not context["is_domain_manager"]:
        raise HTTPException(403, "Domain manager required to delegate project creation")
    ks = await _provider_call(keystone._get_admin_ks_client)
    catalog = await _provider_call(identity_roles._trusted_catalog)
    bindings = identity_roles._validate_preset_catalog(catalog)
    role = bindings.get("project_creator")
    result = {"domain_id": domain_id, "role": {"id": role["id"], "name": role["name"]} if role else None, "users": []}
    if role is None:
        return result
    effective = await _provider_call(_creator_assignments, ks, catalog, domain_id, effective=True)
    direct = await _provider_call(_creator_assignments, ks, catalog, domain_id)
    for uid in sorted({_principal(row, "user") for row in effective}):
        if role["id"] not in _expanded_role_ids(effective, catalog, uid):
            continue
        user = await _eligible_user(ks, domain_id, uid)
        explicit = role["id"] in _direct_ids(direct, uid)
        result["users"].append(
            {
                "id": uid,
                "name": identity_roles._field(user, "name") or uid,
                "email": identity_roles._field(user, "email") or "",
                "domain_id": identity_roles._field(user, "domain_id"),
                "enabled": True,
                "source": "direct" if explicit else "inherited",
                "direct": explicit,
            }
        )
    return result


@identity_roles._complete_mutation
async def change_project_creator(domain_id, user_id, enabled, actor_id):
    from app.services.domain_scope import domain_context

    conn = await _provider_call(keystone.get_admin_project_connection)
    try:
        async with identity_roles._graph_lock(conn) as lease:
            context = await _provider_call(domain_context, actor_id, domain_id)
            if not context["is_domain_manager"]:
                raise HTTPException(403, "Domain manager required to delegate project creation")
            ks = await _provider_call(keystone._get_admin_ks_client)
            catalog = await _provider_call(identity_roles.load_catalog, conn)
            role = identity_roles._validate_preset_catalog(catalog).get("project_creator")
            if role is None:
                raise HTTPException(409, "Explicit administrator project_creator preset setup required")
            await _eligible_user(ks, domain_id, user_id)
            direct = await _provider_call(_creator_assignments, ks, catalog, domain_id)
            present = role["id"] in _direct_ids(direct, user_id)
            if present != enabled:
                await identity_roles._session_ready({user_id})
                succeeded = False
                try:
                    method = ks.roles.grant if enabled else ks.roles.revoke
                    await identity_roles._write(lease, method, role["id"], user=user_id, domain=domain_id)
                    checked = await _provider_call(_creator_assignments, ks, catalog, domain_id)
                    if (role["id"] in _direct_ids(checked, user_id)) != enabled:
                        raise identity_roles._unavailable("Project creator delegation could not be verified")
                    succeeded = True
                finally:
                    await invalidate_project_lists(user_id, domain_id)
                    await identity_roles._applied(
                        None,
                        catalog,
                        None,
                        {user_id},
                        {"user_id": actor_id, "domain_id": domain_id},
                        "project_creator_grant" if enabled else "project_creator_revoke",
                        {"target_domain_id": domain_id, "target_user_id": user_id, "role_id": role["id"]},
                        status="success" if succeeded else "failed",
                    )
    finally:
        await asyncio.to_thread(conn.close)
    return await project_creators(domain_id, actor_id)


def _creator_assignments(ks, catalog, domain_id, *, effective=False, user_id=None):
    from app.services import domain_projects

    query = {"domain": domain_id}
    if effective:
        query["effective"] = True
    if user_id is not None:
        query["user"] = user_id
    result = []
    for row in ks.role_assignments.list(**query):
        meta = domain_projects._assignment(row, catalog, effective=effective)
        if (
            meta["kind"] != "domain"
            or meta["scope_id"] != domain_id
            or (user_id is not None and meta["user_id"] != user_id)
        ):
            raise identity_roles._unavailable("Project creator scope is unavailable")
        if not meta["inherited"]:
            result.append(row)
    return result


@identity_roles._complete_mutation
async def reconcile_project_ownership(project_id, operation_id, domain_id, token_info, *, native_calls_settled):
    from app.services import project_ownership_journal as journal
    from app.services.domain_scope import assert_domain_resource, has_scope_authority

    if native_calls_settled is not True:
        raise HTTPException(422, "Explicit native-call settlement confirmation required")
    async with _membership_write(project_id) as (lease, ks, catalog, effective, direct):
        if not await _provider_call(has_scope_authority, token_info["user_id"]):
            raise HTTPException(403, "Current system administrator required for transfer settlement")
        project = await _provider_call(ks.projects.get, project_id)
        assert_domain_resource(domain_id, identity_roles._field(project, "domain_id"))
        operation = await journal.get(project_id)
        if operation is None or operation["id"] != operation_id or operation["domain_id"] != domain_id:
            raise HTTPException(404, "Project ownership operation not found")
        state = await _ownership_state(ks, catalog, project_id)
        operation = await journal.reconcile(operation, state, lease=lease)
        await identity_roles._applied(
            None,
            catalog,
            None,
            {operation["from_user_id"], operation["to_user_id"]},
            token_info,
            "project_ownership_reconcile",
            {"project_id": project_id, "operation_id": operation_id},
        )
        return {**state, "transfer_operation": operation, "can_transfer": False, "can_delete": False}


async def _write_initial_owner(ks, catalog, lease, project_id, user_id, role):
    from app.services import project_ownership_journal as journal

    project = await _provider_call(ks.projects.get, project_id)
    operation = await journal.begin(
        project_id, identity_roles._field(project, "domain_id"), user_id, user_id, lease=lease
    )
    try:
        await journal.phase(operation, "applying", "initial_grant", lease=lease)
        await identity_roles._write(lease, ks.roles.grant, role["id"], user=user_id, project=project_id)
        await _verify_unique_owner(ks, catalog, project_id, user_id)
        await journal.phase(operation, "completed", "verified", lease=lease)
    except Exception:
        await journal.phase(operation, "unknown", "native_outcome_unknown", lease=lease)
        raise


async def assert_project_activation_safe(project_id, *, ks=None, catalog=None):
    """Do not enable a managed project whose initial ownership never completed."""
    from app.services import project_ownership_journal as journal

    await journal.assert_resolved(project_id)
    if await journal.get(project_id) is not None:
        ks = ks or await _provider_call(keystone._get_admin_ks_client)
        catalog = catalog or await _provider_call(identity_roles._trusted_catalog)
        state = await _ownership_state(ks, catalog, project_id)
        if state["status"] != "unique":
            raise HTTPException(409, "Managed project activation requires verified unique ownership")
