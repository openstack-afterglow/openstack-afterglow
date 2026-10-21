"""Default-project authority, native read-only projection and domain membership.

Reads never provision roles or projects. Native writes share the identity role
lease; Keystone remains authoritative, including external group/inference grants.
Operation-local observations are discarded before leased guards and after writes.
Login skips mutation only after proving the direct reader and full projection.
Role changes invalidate validation snapshots, never durable login families/proof.
The projection is derived access, not an independent domain membership grant.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from contextlib import asynccontextmanager

from fastapi import HTTPException

from app.services import account_spaces, cache, domain_display, identity_roles, keystone

_field = identity_roles._field
_PROJECTION_PREFIX = "afterglow-default-managers-"
_PROJECTION_MARKER = "afterglow:default-manager-reader:v1:"


def _unavailable():
    return HTTPException(503, "domain_default_authority_unavailable")


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except HTTPException:
        raise
    except Exception as exc:
        raise identity_roles._provider_error(exc) from exc


def _client(ks):
    return ks if ks is not None else _call(keystone._get_admin_ks_client)


def _read_context(ks, reads=None, operation=None):
    if operation is not None:
        return _call(getattr, operation, "ks"), operation.reads
    return _client(ks), {} if reads is None else reads


def _raw(ks, catalog, *, reads=None, operation=None):
    ks, reads = _read_context(ks, reads, operation)
    key = ("domain_projects", "raw", id(catalog))
    if key not in reads:
        # Keep the complete graph: a filtered login-user query cannot prove
        # provenance for every legitimate/effective manager.
        rows = list(_call(ks.role_assignments.list))
        reads[key] = [_assignment(row, catalog) for row in rows]
    return reads[key]


def _group_users(ks, group_id, *, reads=None, operation=None):
    ks, reads = _read_context(ks, reads, operation)
    key = ("group_users", group_id)
    if key not in reads:
        users = set()
        for user in _call(ks.users.list, group=group_id):
            uid = _field(user, "id")
            if not isinstance(uid, str) or not uid:
                raise _unavailable()
            users.add(uid)
        reads[key] = users
    return reads[key]


def _catalog(ks, *, operation=None):
    if operation is not None:
        return _call(operation.catalog)
    return _call(
        identity_roles._catalog, list(_call(ks.roles.list)), list(_call(ks.inference_rules.list_inference_roles))
    )


def _canonical(catalog, name):
    matches = [r for r in catalog if r["domain_id"] is None and r["name"].casefold() == name]
    if len(matches) != 1 or matches[0]["name"] != name:
        raise _unavailable()
    return matches[0]


def _roles(catalog):
    from app.services.project_service import _required_project_role

    manager = _canonical(catalog, "manager")
    reader = _canonical(catalog, "reader")
    baseline = _required_project_role(catalog, "project_reader", require_hierarchy=True)
    if reader["id"] not in identity_roles._descendant_ids(catalog, baseline["id"]):
        raise _unavailable()
    return manager, baseline


def _exact(manager, object_id, *, reads=None, operation=None):
    reads = operation.reads if operation is not None else reads
    key = (id(manager), object_id)
    if reads is not None and key in reads:
        return reads[key]
    row = _call(manager.get, object_id)
    if _field(row, "id") != object_id:
        raise _unavailable()
    if reads is not None:
        reads[key] = row
    return row


def _enabled(row):
    value = _field(row, "enabled", _field(row, "is_enabled"))
    if not isinstance(value, bool):
        raise _unavailable()
    return value


def _active_user(ks, user_id, *, authenticated=False, reads=None, operation=None):
    ks, reads = _read_context(ks, reads, operation)
    user = _exact(ks.users, user_id, reads=reads)
    home = _field(user, "domain_id")
    if not isinstance(home, str) or not home:
        raise _unavailable()
    if not _enabled(user):
        if authenticated:
            raise HTTPException(401, "User disabled")
        return None
    if not _enabled(_exact(ks.domains, home, reads=reads)):
        if authenticated:
            raise HTTPException(403, "domain_membership_denied")
        return None
    return user


def default_project(domain_id, *, ks=None, operation=None, reads=None):
    """Find the unique canonical Default; a legacy domain is not bootstrapped."""
    ks, reads = _read_context(ks, reads, operation)
    key = ("domain_projects", "default", domain_id)
    if key in reads:
        return reads[key]
    domain = _exact(ks.domains, domain_id, reads=reads)
    if account_spaces.domain_kind(domain) in {"account", "personal"}:
        reads[key] = None
        return None
    matches = []
    list_key = ("domain_projects", "project_list", domain_id)
    if list_key not in reads:
        reads[list_key] = list(_call(ks.projects.list, domain=domain_id))
    for row in reads[list_key]:
        if _field(row, "domain_id") != domain_id:
            raise _unavailable()
        name = _field(row, "name")
        if not isinstance(name, str):
            raise _unavailable()
        if name.casefold() == "default":
            if (
                name != "Default"
                or not isinstance(_field(row, "id"), str)
                or not _field(row, "id").strip()
                or not _enabled(row)
            ):
                raise _unavailable()
            matches.append({"id": _field(row, "id"), "name": name, "domain_id": domain_id, "enabled": True})
    if len(matches) > 1:
        raise _unavailable()
    reads[key] = matches[0] if matches else None
    return reads[key]


def _assignment(row, catalog, *, effective=False):
    """Validate the source subject/scope and role identity before using it."""
    role = _field(_field(row, "role"), "id")
    if role not in {r["id"] for r in catalog}:
        raise _unavailable()
    scope = _field(row, "scope")
    if not isinstance(scope, Mapping):
        raise _unavailable()
    kinds = set(scope) & {"project", "domain", "system"}
    if len(kinds) != 1 or set(scope) - {"project", "domain", "system", "OS-INHERIT:inherited_to"}:
        raise _unavailable()
    kind = next(iter(kinds))
    inherited = "OS-INHERIT:inherited_to" in scope
    if inherited and (kind == "system" or scope["OS-INHERIT:inherited_to"] != "projects"):
        raise _unavailable()
    if kind == "system":
        if not isinstance(scope[kind], Mapping) or set(scope[kind]) != {"all"} or scope[kind]["all"] is not True:
            raise _unavailable()
        scope_id = "all"
    else:
        scope_id = _field(scope[kind], "id")
        if not isinstance(scope_id, str) or not scope_id:
            raise _unavailable()
    user, group = (_field(_field(row, p), "id") for p in ("user", "group"))
    if effective:
        if not isinstance(user, str) or not user or group is not None:
            raise _unavailable()
    elif bool(user) == bool(group):
        raise _unavailable()
    if any(p is not None and (not isinstance(p, str) or not p) for p in (user, group)):
        raise _unavailable()
    return {
        "role_id": role,
        "kind": kind,
        "scope_id": scope_id,
        "inherited": inherited,
        "user_id": user,
        "group_id": group,
    }


def _effective(ks, project_id, catalog, *, reads=None, operation=None):
    ks, reads = _read_context(ks, reads, operation)
    key = ("domain_projects", "effective_project", project_id, id(catalog))
    if key not in reads:
        rows = list(_call(ks.role_assignments.list, project=project_id, effective=True))
        for row in rows:
            meta = _assignment(row, catalog, effective=True)
            if meta["kind"] != "project" or meta["scope_id"] != project_id:
                raise _unavailable()
        reads[key] = rows
    return reads[key]


def _manager_users(ks, project, catalog, *, reads=None, raw=None, operation=None):
    from app.services.project_service import _expanded_role_ids

    ks, reads = _read_context(ks, reads, operation)
    key = ("domain_projects", "managers", project["id"], id(catalog))
    if key in reads:
        return reads[key]
    manager = _canonical(catalog, "manager")["id"]
    rows = _effective(ks, project["id"], catalog, reads=reads)
    users = {_field(_field(row, "user"), "id") for row in rows}
    native_project = _exact(ks.projects, project["id"], reads=reads)
    sources = _sources(ks, native_project, catalog, raw, exclude_projection=True, reads=reads)
    legitimate = {
        uid
        for source in sources
        if manager in {source["role_id"]} | identity_roles._descendant_ids(catalog, source["role_id"])
        for uid in source["users"]
    }
    effective = {uid for uid in users if manager in _expanded_role_ids(rows, catalog, uid)}
    active = {uid for uid in effective | legitimate if _active_user(ks, uid, reads=reads)}
    effective &= active
    legitimate &= active
    if effective != legitimate:
        raise _unavailable()
    reads[key] = effective
    return effective


def has_manager(user_id, domain_id, *, ks=None, catalog=None, operation=None):
    ks, reads = _read_context(ks, operation=operation)
    if not _active_user(ks, user_id, reads=reads) or not _enabled(_exact(ks.domains, domain_id, reads=reads)):
        return False
    project = default_project(domain_id, ks=ks, reads=reads)
    if project is None:
        return False
    catalog = catalog if catalog is not None else _catalog(ks, operation=operation)
    return user_id in _manager_users(ks, project, catalog, reads=reads)


def _projection(domain_id, ks, *, reads=None, operation=None):
    ks, reads = _read_context(ks, reads, operation)
    key = ("domain_projects", "projection", domain_id)
    if key in reads:
        return reads[key]
    matches = []
    name = _PROJECTION_PREFIX + domain_id
    marker = _PROJECTION_MARKER + domain_id
    for group in _call(ks.groups.list, domain=domain_id):
        if _field(group, "domain_id") != domain_id:
            raise _unavailable()
        if _field(group, "name") == name or _field(group, "description") == marker:
            if (
                _field(group, "name") != name
                or _field(group, "description") != marker
                or not isinstance(_field(group, "id"), str)
                or not _field(group, "id")
            ):
                raise _unavailable()
            matches.append(group)
    if len(matches) > 1:
        raise _unavailable()
    reads[key] = matches[0] if matches else None
    return reads[key]


def is_projection_group(group_id, *, ks=None):
    ks = _client(ks)
    return _is_projection_group(_exact(ks.groups, group_id))


def _is_projection_group(group):
    name, description = _field(group, "name", ""), _field(group, "description", "")
    if not isinstance(name, str) or not isinstance(description, str):
        raise _unavailable()
    return name.startswith(_PROJECTION_PREFIX) or description.startswith(_PROJECTION_MARKER)


def assert_not_projection_group(group_id, *, ks=None):
    if is_projection_group(group_id, ks=ks):
        raise HTTPException(403, "domain_manager_projection_is_private")


def assert_projection_attributes(attrs):
    """Reserve projection identity attributes on generic group create/update."""
    if not isinstance(attrs, Mapping):
        raise HTTPException(422, "domain_group_attributes_invalid")
    name, description = attrs.get("name"), attrs.get("description")
    if (isinstance(name, str) and name.startswith(_PROJECTION_PREFIX)) or (
        isinstance(description, str) and description.startswith(_PROJECTION_MARKER)
    ):
        raise HTTPException(403, "domain_manager_projection_is_private")


def _ancestors(ks, project, *, reads=None, operation=None):
    ks, reads = _read_context(ks, reads, operation)
    key = ("domain_projects", "ancestors", _field(project, "id"))
    if key in reads:
        return reads[key]
    result, pending = set(), _field(project, "parent_id")
    domain_id = _field(project, "domain_id")
    if not isinstance(domain_id, str) or not domain_id:
        raise _unavailable()
    # Keystone represents the domain as the root project parent.
    while pending is not None and pending != domain_id:
        if not isinstance(pending, str) or not pending or pending in result or pending == _field(project, "id"):
            raise _unavailable()
        parent = _exact(ks.projects, pending, reads=reads)
        if _field(parent, "domain_id") != domain_id:
            raise _unavailable()
        result.add(pending)
        pending = _field(parent, "parent_id")
    reads[key] = result
    return result


def _sources(ks, project, catalog, raw=None, *, exclude_projection=False, reads=None, operation=None):
    """Reconstruct native provenance; reuse reads only within this operation."""
    ks, reads = _read_context(ks, reads, operation)
    key = ("domain_projects", "sources", _field(project, "id"), exclude_projection, id(catalog))
    if key in reads:
        return reads[key]
    graph = _raw(ks, catalog, reads=reads) if raw is None else [_assignment(row, catalog) for row in raw]
    ancestors = _ancestors(ks, project, reads=reads)
    result = []
    for meta in graph:
        applies = (
            meta["kind"] == "project"
            and (
                (meta["scope_id"] == _field(project, "id") and not meta["inherited"])
                or (meta["scope_id"] in ancestors and meta["inherited"])
            )
        ) or (meta["kind"] == "domain" and meta["scope_id"] == _field(project, "domain_id") and meta["inherited"])
        if not applies:
            continue
        if meta["group_id"]:
            group = _exact(ks.groups, meta["group_id"], reads=reads)
            if exclude_projection and _is_projection_group(group):
                continue
            users = _group_users(ks, meta["group_id"], reads=reads)
        else:
            users = {meta["user_id"]}
        result.append({**meta, "users": users})
    reads[key] = result
    return result


def _personal_owner(sources, catalog, user_id):
    owner_id = _canonical(catalog, "project_owner")["id"]
    owner_source = None
    for source in sources:
        if not identity_roles._owner_bearing_role(catalog, source["role_id"]):
            continue
        if owner_source is not None:
            return False
        owner_source = source
    return bool(
        owner_source is not None
        and owner_source["role_id"] == owner_id
        and owner_source["kind"] == "project"
        and not owner_source["inherited"]
        and not owner_source["group_id"]
        and owner_source["user_id"] == user_id
        and user_id in owner_source["users"]
    )


def _personal_member(sources, catalog, user_id, project_id):
    member = account_spaces._personal_member_role(catalog)
    if any(source["role_id"] == member["id"] for source in sources):
        return account_spaces._member_sources(sources, catalog, user_id, project_id)
    # Established owner-based projects keep their original grants and boundary.
    return _personal_owner(sources, catalog, user_id)


def accessible_domains(user_id, *, ks=None, operation=None):
    ks, reads = _read_context(ks, operation=operation)
    user = _active_user(ks, user_id, authenticated=True, reads=reads)
    return _accessible_domains(ks, user_id, user, reads, operation=operation)


def _accessible_domains(ks, user_id, user, reads, *, operation=None):
    key = ("domain_projects", "accessible_domains", user_id)
    if key in reads:
        return reads[key]
    catalog = _catalog(ks, operation=operation)
    home_id = _field(user, "domain_id")
    home = _exact(ks.domains, home_id, reads=reads)
    home_kind = account_spaces.domain_kind(home)
    domains = {}
    if home_kind not in {"account", "personal"}:
        domains[home_id] = {"id": home_id, "name": domain_display.display_name(home), "kind": home_kind}
    _raw(ks, catalog, reads=reads)
    effective_key = ("domain_projects", "effective_user", user_id, id(catalog))
    if effective_key not in reads:
        rows = list(_call(ks.role_assignments.list, user=user_id, effective=True))
        parsed = [_assignment(row, catalog, effective=True) for row in rows]
        if any(meta["user_id"] != user_id for meta in parsed):
            raise _unavailable()
        reads[effective_key] = parsed
    project_ids = {meta["scope_id"] for meta in reads[effective_key] if meta["kind"] == "project"}
    for project_id in sorted(project_ids):
        project = _exact(ks.projects, project_id, reads=reads)
        domain_id = _field(project, "domain_id")
        if not isinstance(domain_id, str) or not domain_id:
            raise _unavailable()
        domain = _exact(ks.domains, domain_id, reads=reads)
        if not _enabled(project) or not _enabled(domain):
            continue
        kind = account_spaces.domain_kind(domain)
        if kind == "account" or (kind == "personal" and _field(project, "afterglow_personal_user_id") != user_id):
            continue
        sources = _sources(ks, project, catalog, exclude_projection=kind != "personal", reads=reads)
        if kind == "personal" and not _personal_member(sources, catalog, user_id, project_id):
            continue
        if any(user_id in source["users"] for source in sources):
            domains[domain_id] = {"id": domain_id, "name": domain_display.display_name(domain), "kind": kind}
    # The effective sources above already include current Default managers.
    if any(not isinstance(d["name"], str) or not d["name"] for d in domains.values()):
        raise _unavailable()
    reads[key] = sorted(domains.values(), key=lambda d: (d["name"], d["id"]))
    return reads[key]


def assert_membership(user_id, domain_id, *, ks=None, operation=None):
    ks, reads = _read_context(ks, operation=operation)
    user = _active_user(ks, user_id, authenticated=True, reads=reads)
    target = _exact(ks.domains, domain_id, reads=reads)
    kind = account_spaces.domain_kind(target)
    if kind == "account":
        raise HTTPException(403, "account_domain_is_identity_only")
    if domain_id == _field(user, "domain_id") and kind != "personal":
        # Legacy identity homes remain accessible; reserved account/personal do not infer membership.
        home = target
        name = domain_display.display_name(home)
        if not isinstance(name, str) or not name:
            raise _unavailable()
        return
    if domain_id not in {d["id"] for d in _accessible_domains(ks, user_id, user, reads, operation=operation)}:
        raise HTTPException(403, "domain_membership_denied")


def assert_project_membership(user_id, project_id, *, ks=None, operation=None):
    """Reject stale projection-only project access after external manager revoke."""
    ks, reads = _read_context(ks, operation=operation)
    _active_user(ks, user_id, authenticated=True, reads=reads)
    project = _exact(ks.projects, project_id, reads=reads)
    domain_id = _field(project, "domain_id")
    if not isinstance(domain_id, str) or not domain_id:
        raise _unavailable()
    domain = _exact(ks.domains, domain_id, reads=reads)
    kind = account_spaces.domain_kind(domain)
    if kind == "account" or (kind == "personal" and _field(project, "afterglow_personal_user_id") != user_id):
        raise HTTPException(403, "project_membership_denied")
    if not _enabled(project) or not _enabled(domain):
        raise HTTPException(403, "project_membership_denied")
    catalog = _catalog(ks, operation=operation)
    rows = _effective(ks, project_id, catalog, reads=reads)
    if not any(_field(_field(row, "user"), "id") == user_id for row in rows):
        raise HTTPException(403, "project_membership_denied")
    sources = _sources(ks, project, catalog, exclude_projection=kind != "personal", reads=reads)
    if kind == "personal":
        if not _personal_member(sources, catalog, user_id, project_id):
            raise HTTPException(403, "personal_project_member_required")
        return
    if any(user_id in source["users"] for source in sources):
        return
    default = default_project(domain_id, ks=ks, reads=reads)
    if default is None or user_id not in _manager_users(ks, default, catalog, reads=reads):
        raise HTTPException(403, "project_membership_denied")


def assert_manager_assignment(project_id, role_id, *, catalog=None, ks=None):
    ks = _client(ks)
    catalog = catalog if catalog is not None else _catalog(ks)
    manager = _canonical(catalog, "manager")["id"]
    if manager not in {role_id} | identity_roles._descendant_ids(catalog, role_id):
        return
    project = _exact(ks.projects, project_id)
    default = default_project(_field(project, "domain_id"), ks=ks)
    if default is None or default["id"] != project_id:
        raise HTTPException(422, "manager_requires_default_project")


def assert_default_immutable(project_id, *, attrs=None, delete=False, ks=None, project=None):
    if project is None:
        ks = _client(ks)
        project = _exact(ks.projects, project_id)
    elif _field(project, "id") != project_id:
        raise _unavailable()
    attrs = attrs or {}
    if _field(project, "afterglow_personal_user_id") and "name" in attrs and attrs["name"] != _field(project, "name"):
        raise HTTPException(422, "personal_project_name_is_generated")
    if _field(project, "afterglow_personal_primary") is True and (
        delete or attrs.get("enabled") is False or attrs.get("is_enabled") is False
    ):
        raise HTTPException(422, "personal_primary_project_is_immutable")
    name = _field(project, "name", "")
    if not isinstance(name, str):
        raise _unavailable()
    if name.casefold() != "default":
        if "name" in attrs and attrs["name"].casefold() == "default":
            raise HTTPException(422, "domain_default_is_immutable")
        return
    if delete or any(
        key in attrs and attrs[key] != expected
        for key, expected in (
            ("name", "Default"),
            ("enabled", True),
            ("is_enabled", True),
            ("domain_id", _field(project, "domain_id")),
            ("domain", _field(project, "domain_id")),
            ("parent_id", _field(project, "parent_id")),
        )
    ):
        raise HTTPException(422, "domain_default_is_immutable")


def assert_managers_remain(
    *,
    ks=None,
    catalog=None,
    user_id=None,
    disabled_user_ids=(),
    disabled_domain_id=None,
    group_id=None,
    remove_group_user_id=None,
    delete_group=False,
    project_id=None,
    role_id=None,
    remove_assignment=False,
    prior_id=None,
    implied_id=None,
    remove_edge=False,
    changed_domain_id=None,
):
    """Simulate source grants, group membership and role graph before a write.

    The raw-source reconstruction must agree with Keystone's effective managers;
    a provider that omits provenance cannot silently authorize last-manager loss.
    Returns domains whose projection must be resynchronized under the same lease.
    """
    if catalog is None:
        ks = _client(ks)
        catalog = _catalog(ks)
    changed_catalog = catalog
    if prior_id is not None or implied_id is not None:
        if prior_id is None or implied_id is None:
            raise _unavailable()
        identity_roles._role(catalog, prior_id)
        identity_roles._role(catalog, implied_id)
        inferences = []
        for row in catalog:
            children = set(row["implied_role_ids"])
            if row["id"] == prior_id:
                if remove_edge:
                    children.discard(implied_id)
                else:
                    children.add(implied_id)
            inferences.append({"prior_role": {"id": row["id"]}, "implies": [{"id": rid} for rid in children]})
        changed_catalog = identity_roles._catalog(catalog, inferences)
        if any(r["domain_id"] is None and r["name"].casefold() == "project_reader" for r in catalog):
            _roles(changed_catalog)
        if not any(r["domain_id"] is None and r["name"].casefold() == "manager" for r in catalog):
            return set()
    manager = _canonical(catalog, "manager")["id"]
    disabled = set(disabled_user_ids)
    affected = set()
    changed_roles = {
        r["id"]: {r["id"]} | identity_roles._descendant_ids(changed_catalog, r["id"]) for r in changed_catalog
    }
    old_roles = {r["id"]: {r["id"]} | identity_roles._descendant_ids(catalog, r["id"]) for r in catalog}
    if prior_id is not None and (
        {rid for rid, roles in old_roles.items() if manager in roles}
        == {rid for rid, roles in changed_roles.items() if manager in roles}
    ):
        return set()
    ks = _client(ks)
    raw = list(_call(ks.role_assignments.list))
    # An inference addition cannot turn an existing domain/system/ordinary project
    # grant into a newly minted manager outside Default.
    if prior_id is not None and not remove_edge:
        for row in raw:
            meta = _assignment(row, catalog)
            if manager in changed_roles[meta["role_id"]] and manager not in old_roles[meta["role_id"]]:
                if meta["kind"] != "project" or meta["inherited"]:
                    raise HTTPException(422, "manager_requires_default_project")
                assert_manager_assignment(meta["scope_id"], meta["role_id"], catalog=changed_catalog, ks=ks)
    if group_id is not None and not delete_group and remove_group_user_id is None and not remove_assignment:
        for row in raw:
            meta = _assignment(row, catalog)
            if meta["group_id"] == group_id and manager in old_roles[meta["role_id"]]:
                if meta["kind"] != "project" or meta["inherited"]:
                    raise HTTPException(422, "manager_requires_default_project")
                assert_manager_assignment(meta["scope_id"], meta["role_id"], catalog=catalog, ks=ks)
    for domain in _call(ks.domains.list):
        domain_id = _field(domain, "id")
        if not isinstance(domain_id, str) or not domain_id:
            raise _unavailable()
        if not _enabled(domain):
            continue
        project = default_project(domain_id, ks=ks)
        if project is None:
            continue
        if prior_id is not None:
            _roles(changed_catalog)
        native_project = _exact(ks.projects, project["id"])
        sources = _sources(ks, native_project, catalog, raw)
        if group_id is not None and any(source["group_id"] == group_id for source in sources):
            affected.add(domain_id)
        if project_id == project["id"] or prior_id is not None:
            affected.add(domain_id)
        current, retained = set(), set()
        for source in sources:
            for uid in source["users"]:
                if manager in old_roles[source["role_id"]]:
                    account_snapshot = _exact(ks.users, uid)
                    if uid == user_id or _field(account_snapshot, "domain_id") == changed_domain_id:
                        affected.add(domain_id)
                account = _active_user(ks, uid)
                if not account:
                    continue
                if manager in old_roles[source["role_id"]]:
                    current.add(uid)
                removed = (
                    uid in disabled
                    or _field(account, "domain_id") == disabled_domain_id
                    or (source["group_id"] == group_id and (delete_group or uid == remove_group_user_id))
                    or (
                        remove_assignment
                        and source["kind"] == "project"
                        and not source["inherited"]
                        and source["scope_id"] == project_id
                        and source["role_id"] == role_id
                        and (
                            (user_id is not None and source["user_id"] == user_id)
                            or (group_id is not None and source["group_id"] == group_id)
                        )
                    )
                )
                if not removed and manager in changed_roles[source["role_id"]]:
                    retained.add(uid)
        effective = _manager_users(ks, project, catalog)
        if current != effective:
            raise _unavailable()
        if current != retained:
            affected.add(domain_id)
            if current and not retained:
                raise HTTPException(409, "last_domain_manager")
    return affected


@asynccontextmanager
async def _mutation(*, ks=None, snapshot=None):
    if snapshot is not None:
        lease, ks, catalog = snapshot
        await lease.assert_owned()
        yield lease, ks, catalog
        return
    from app.services.native_operation import NativeOperation

    owned = NativeOperation() if ks is None else None
    conn = None
    try:
        conn = await asyncio.to_thread(_call, keystone.get_admin_project_connection)
        async with identity_roles._graph_lock(conn) as lease:
            if owned is not None:
                ks = await asyncio.to_thread(getattr, owned, "ks")
            catalog = await asyncio.to_thread(identity_roles.load_catalog, conn)
            yield lease, ks, catalog
    finally:
        try:
            if conn is not None:
                await asyncio.to_thread(conn.close)
        finally:
            if owned is not None:
                await asyncio.to_thread(owned.close)


async def _invalidate(domain_id, users=()):
    from app.services.domain_scope import invalidate_authority
    from app.services.project_service import invalidate_project_lists

    await invalidate_authority()
    for uid in sorted(users):
        await invalidate_project_lists(uid, domain_id)
    # Validation keys are credential/project-bound, not indexed by user.
    await cache.invalidate("afterglow:session:*")


async def _sync(domain_id, lease, ks, catalog, *, created_groups=None, staged_project=None):
    domain = await asyncio.to_thread(_exact, ks.domains, domain_id)
    if account_spaces.domain_kind(domain) in {"account", "personal"}:
        return
    if staged_project is None:
        project = await asyncio.to_thread(default_project, domain_id, ks=ks)
    else:
        staged = await asyncio.to_thread(_exact, ks.projects, staged_project["id"])
        if _field(staged, "name") != "Default" or _field(staged, "domain_id") != domain_id or _enabled(staged):
            raise _unavailable()
        project = staged_project
    if project is None:
        return
    _, reader = _roles(catalog)
    managers = await asyncio.to_thread(_manager_users, ks, project, catalog)
    group = await asyncio.to_thread(_projection, domain_id, ks)
    if group is None:
        existing_groups = {_field(g, "id") for g in await asyncio.to_thread(ks.groups.list, domain=domain_id)}
        created = await identity_roles._write(
            lease,
            ks.groups.create,
            name=_PROJECTION_PREFIX + domain_id,
            domain=domain_id,
            description=_PROJECTION_MARKER + domain_id,
        )
        if (
            not isinstance(_field(created, "id"), str)
            or not _field(created, "id")
            or _field(created, "id") in existing_groups
        ):
            raise _unavailable()
        group = await asyncio.to_thread(_projection, domain_id, ks)
        if group is None or _field(group, "id") != _field(created, "id"):
            raise _unavailable()
        if created_groups is not None:
            created_groups.append(_field(created, "id"))
    gid = _field(group, "id")
    members = set()
    for user in await asyncio.to_thread(ks.users.list, group=gid):
        uid = _field(user, "id")
        if not isinstance(uid, str) or not uid:
            raise _unavailable()
        members.add(uid)
    grants = list(await asyncio.to_thread(ks.role_assignments.list, group=gid))
    wanted = {
        "role_id": reader["id"],
        "kind": "domain",
        "scope_id": domain_id,
        "inherited": True,
        "user_id": None,
        "group_id": gid,
    }
    parsed = [_assignment(row, catalog) for row in grants]
    if any(row != wanted for row in parsed):
        # Never trust or erase a tampered managed group with foreign/stronger grants.
        raise _unavailable()
    changed = members != managers or not parsed
    if changed:
        await identity_roles._session_ready(members | managers)
    try:
        for uid in sorted(members - managers):
            await identity_roles._write(lease, ks.users.remove_from_group, uid, gid)
        for uid in sorted(managers - members):
            await identity_roles._write(lease, ks.users.add_to_group, uid, gid)
        if not parsed:
            await identity_roles._write(
                lease, ks.roles.grant, reader["id"], group=gid, domain=domain_id, os_inherit_extension_inherited=True
            )
        checked_members = {_field(u, "id") for u in await asyncio.to_thread(ks.users.list, group=gid)}
        checked_grants = [_assignment(r, catalog) for r in await asyncio.to_thread(ks.role_assignments.list, group=gid)]
        if checked_members != managers or checked_grants != [wanted]:
            raise _unavailable()
    finally:
        if changed:
            await _invalidate(domain_id, members | managers)


@identity_roles._complete_mutation
async def sync_manager_access(domain_id, *, mutation=None):
    if mutation is None:
        async with _mutation() as (lease, ks, catalog):
            await _sync(domain_id, lease, ks, catalog)
    else:
        if isinstance(mutation, Mapping):
            lease, ks, catalog = (mutation[key] for key in ("lease", "ks", "catalog"))
        else:
            lease, ks, catalog = mutation[:3]
        await _sync(domain_id, lease, ks, catalog)


def _login_access_current(user_id, domain_id, project, *, operation):
    """Prove the entire projection, never just the login subject's access."""
    ks, reads = _read_context(None, operation=operation)
    catalog = _catalog(ks, operation=operation)
    _, reader = _roles(catalog)
    wanted_direct = {
        "role_id": reader["id"],
        "kind": "project",
        "scope_id": project["id"],
        "inherited": False,
        "user_id": user_id,
        "group_id": None,
    }
    if wanted_direct not in _raw(ks, catalog, reads=reads):
        return False
    managers = _manager_users(ks, project, catalog, reads=reads)
    group = _projection(domain_id, ks, reads=reads)
    if group is None:
        return False
    gid = _field(group, "id")
    wanted_projection = {
        "role_id": reader["id"],
        "kind": "domain",
        "scope_id": domain_id,
        "inherited": True,
        "user_id": None,
        "group_id": gid,
    }
    key = ("domain_projects", "projection_grants", gid, id(catalog))
    if key not in reads:
        grants = [_assignment(row, catalog) for row in _call(ks.role_assignments.list, group=gid)]
        if any(row != wanted_projection for row in grants):
            raise _unavailable()
        reads[key] = grants
    return reads[key] == [wanted_projection] and _group_users(ks, gid, reads=reads) == managers


@identity_roles._complete_mutation
async def ensure_login_access(user_id, domain_id, *, operation=None):
    from app.services.native_operation import NativeOperation

    owned = operation is None
    operation = NativeOperation() if owned else operation
    try:
        domain = await operation.run(operation.get, "domains", domain_id)
        kind = account_spaces.domain_kind(domain)
        if kind == "account":
            raise HTTPException(403, "account_domain_is_identity_only")
        if kind == "personal":
            await operation.run(assert_membership, user_id, domain_id, operation=operation)
            return
        await asyncio.to_thread(assert_membership, user_id, domain_id, operation=operation)
        project = await asyncio.to_thread(default_project, domain_id, operation=operation)
        if project is not None and await asyncio.to_thread(
            _login_access_current, user_id, domain_id, project, operation=operation
        ):
            return
        # Reuse credentials, never the observations that prompted this repair.
        ks = await asyncio.to_thread(getattr, operation, "ks")
        operation.invalidate()
        try:
            async with _mutation(ks=ks) as (lease, ks, catalog):
                await asyncio.to_thread(assert_membership, user_id, domain_id, ks=ks)
                project = await asyncio.to_thread(default_project, domain_id, ks=ks)
                if project is None:
                    await _bootstrap(domain_id, user_id, lease, ks, catalog, grant_manager=False)
                else:
                    _roles(catalog)
                    await _ensure_reader(lease, ks, catalog, project["id"], user_id)
                    await _sync(domain_id, lease, ks, catalog)
        finally:
            operation.invalidate()
    finally:
        if owned:
            await asyncio.to_thread(operation.close)


async def _ensure_reader(lease, ks, catalog, project_id, user_id):
    from app.services.project_service import _assignment_rows, _direct_ids

    _, reader = _roles(catalog)
    rows = await asyncio.to_thread(_assignment_rows, ks, project_id)
    if reader["id"] not in _direct_ids(rows, user_id):
        await identity_roles._write(lease, ks.roles.grant, reader["id"], user=user_id, project=project_id)
        rows = await asyncio.to_thread(_assignment_rows, ks, project_id)
        if reader["id"] not in _direct_ids(rows, user_id):
            raise _unavailable()
        project = await asyncio.to_thread(_exact, ks.projects, project_id)
        await _invalidate(_field(project, "domain_id"), {user_id})


async def apply_default_quotas(domain_id, project_id, lease):
    from app.services.domain_quotas import apply_project_defaults

    conn = await asyncio.to_thread(keystone.get_admin_project_connection)
    try:
        await apply_project_defaults(conn, domain_id, project_id, lease=lease)
    finally:
        await asyncio.to_thread(conn.close)


async def _bootstrap(domain_id, creator_id, lease, ks, catalog, *, grant_manager):
    from app.services import project_ownership_journal as journal
    from app.services.project_service import (
        _assignment_rows,
        _direct_ids,
        _ownership_state,
        _required_project_role,
        _verify_unique_owner,
        _write_initial_owner,
    )

    if await asyncio.to_thread(_active_user, ks, creator_id) is None:
        raise HTTPException(403, "domain_creator_disabled")
    manager, _ = _roles(catalog)
    owner = _required_project_role(catalog, "project_owner", require_hierarchy=True)
    if await asyncio.to_thread(default_project, domain_id, ks=ks) is not None:
        raise HTTPException(409, "domain_default_already_exists")
    existing = {_field(p, "id") for p in await asyncio.to_thread(ks.projects.list, domain=domain_id)}
    created = await identity_roles._write(
        lease,
        ks.projects.create,
        name="Default",
        domain=domain_id,
        enabled=False,
        description="Domain default read-only landing project",
    )
    pid = _field(created, "id")
    if not isinstance(pid, str) or not pid or pid in existing:
        raise _unavailable()
    created_groups = []
    try:
        staged = await asyncio.to_thread(_exact, ks.projects, pid)
        if _field(staged, "name") != "Default" or _field(staged, "domain_id") != domain_id or _enabled(staged):
            raise _unavailable()
        project = {"id": pid, "name": "Default", "domain_id": domain_id, "enabled": False}
        state = await _ownership_state(ks, catalog, pid)
        if state["status"] != "missing":
            raise HTTPException(409, "domain_default_owner_conflict")
        await _write_initial_owner(ks, catalog, lease, pid, creator_id, owner)
        if grant_manager:
            await identity_roles._write(lease, ks.roles.grant, manager["id"], user=creator_id, project=pid)
        await _ensure_reader(lease, ks, catalog, pid, creator_id)
        await _sync(domain_id, lease, ks, catalog, created_groups=created_groups, staged_project=project)
        await apply_default_quotas(domain_id, pid, lease)
        await _verify_unique_owner(ks, catalog, pid, creator_id)
        rows = await asyncio.to_thread(_assignment_rows, ks, pid)
        required = {owner["id"], _roles(catalog)[1]["id"]}
        if grant_manager:
            required.add(manager["id"])
        if not required <= _direct_ids(rows, creator_id):
            raise _unavailable()
        if grant_manager and creator_id not in await asyncio.to_thread(_manager_users, ks, project, catalog):
            raise _unavailable()
        # Keystone permits grants on a disabled project, but rejects project
        # creation under a disabled ancestor. Only activate after all grants and
        # projection readbacks succeed beneath the enabled empty domain.
        await identity_roles._write(lease, ks.projects.update, pid, enabled=True)
        verified = await asyncio.to_thread(default_project, domain_id, ks=ks)
        if verified is None or verified["id"] != pid:
            raise _unavailable()
        await _verify_unique_owner(ks, catalog, pid, creator_id)
        if grant_manager and creator_id not in await asyncio.to_thread(_manager_users, ks, verified, catalog):
            raise _unavailable()
        return verified
    except Exception:
        ownership = await journal.get(pid)
        if ownership is not None and ownership["status"] != "completed":
            # The grant may still be running remotely. Keep its exact disabled
            # project and durable intent for explicit settled reconciliation.
            raise
        try:
            for gid in created_groups:
                group = await asyncio.to_thread(_exact, ks.groups, gid)
                if (
                    _field(group, "domain_id") != domain_id
                    or _field(group, "description") != _PROJECTION_MARKER + domain_id
                    or _field(group, "name") != _PROJECTION_PREFIX + domain_id
                ):
                    raise _unavailable()
                grants = await asyncio.to_thread(ks.role_assignments.list, group=gid)
                for row in grants:
                    meta = _assignment(row, catalog)
                    if (
                        meta["kind"] != "domain"
                        or meta["scope_id"] != domain_id
                        or not meta["inherited"]
                        or meta["role_id"] != _roles(catalog)[1]["id"]
                        or meta["group_id"] != gid
                    ):
                        raise _unavailable()
                await identity_roles._write(lease, ks.groups.delete, gid)
                if gid in {_field(g, "id") for g in await asyncio.to_thread(ks.groups.list, domain=domain_id)}:
                    raise _unavailable()
            current = await asyncio.to_thread(_exact, ks.projects, pid)
            if _field(current, "domain_id") != domain_id or _field(current, "name") != "Default":
                raise _unavailable()
            grants = await asyncio.to_thread(ks.role_assignments.list, project=pid)
            for row in grants:
                meta = _assignment(row, catalog)
                if (
                    meta["kind"] != "project"
                    or meta["scope_id"] != pid
                    or meta["user_id"] != creator_id
                    or meta["group_id"] is not None
                    or meta["inherited"]
                    or meta["role_id"]
                    not in {owner["id"], _roles(catalog)[1]["id"]} | ({manager["id"]} if grant_manager else set())
                ):
                    raise _unavailable()
            await identity_roles._write(lease, ks.projects.delete, pid)
            if pid in {_field(p, "id") for p in await asyncio.to_thread(ks.projects.list, domain=domain_id)}:
                raise _unavailable()
        except Exception as cleanup_error:
            raise HTTPException(503, "domain_default_setup_cleanup_unavailable") from cleanup_error
        raise


@identity_roles._complete_mutation
async def bootstrap_default(domain_id, *, creator_id):
    """Explicit system-admin route only; never called by login or read helpers."""
    async with _mutation() as (lease, ks, catalog):
        domain = await asyncio.to_thread(_exact, ks.domains, domain_id)
        if not _enabled(domain):
            raise HTTPException(403, "domain_disabled")
        if account_spaces.domain_kind(domain) in {"account", "personal"}:
            raise HTTPException(403, "organization_domain_required")
        project = await _bootstrap(domain_id, creator_id, lease, ks, catalog, grant_manager=True)
        await _invalidate(domain_id, {creator_id})
        return {"domain_id": domain_id, "default_project_id": project["id"], "creator_id": creator_id}


@identity_roles._complete_mutation
async def create_domain(*, name, description, enabled, creator_id, mutation=None, metadata=None):
    async with _mutation(snapshot=mutation) as (lease, ks, catalog):
        try:
            _roles(catalog)
            if await asyncio.to_thread(_active_user, ks, creator_id) is None:
                raise HTTPException(403, "domain_creator_disabled")
            name = domain_display.validate_name(name)
            internal_name = domain_display.native_name()
            organizations = await asyncio.to_thread(account_spaces._rows, ks.domains)
            existing = {_field(item, "id") for item in organizations}
            if not await asyncio.to_thread(keystone._is_system_admin, creator_id):
                from app.config import get_settings

                policy = get_settings().auth
                if not policy.organization_creation_enabled:
                    raise HTTPException(403, "organization_creation_disabled")
                count = sum(
                    account_spaces.domain_kind(item) == "organization"
                    and _field(item, "afterglow_created_by") == creator_id
                    for item in organizations
                )
                if count >= policy.max_organizations_per_user:
                    raise HTTPException(403, "organization_creation_limit_reached")
        except HTTPException as exc:
            exc.native_create_dispatched = False
            raise
        # Stage an enabled domain with disabled Default; never retry unknown creates.
        created = await identity_roles._write(
            lease,
            ks.domains.create,
            name=internal_name,
            afterglow_display_name=name,
            description=description,
            enabled=True,
            **(metadata or {}),
            afterglow_domain_kind="organization",
            afterglow_created_by=creator_id,
        )
        domain_id = _field(created, "id")
        if not isinstance(domain_id, str) or not domain_id or domain_id in existing:
            raise _unavailable()
        domain = await asyncio.to_thread(_exact, ks.domains, domain_id)
        if (
            _field(domain, "name") != internal_name
            or domain_display.display_name(domain) != name
            or not _enabled(domain)
            or account_spaces.domain_kind(domain) != "organization"
            or _field(domain, "afterglow_created_by") != creator_id
            or any(_field(domain, key) != value for key, value in (metadata or {}).items())
        ):
            raise _unavailable()
        try:
            project = await _bootstrap(domain_id, creator_id, lease, ks, catalog, grant_manager=True)
        except Exception:
            # A creation response with an exact new ID is owned by this attempt.
            # Known failed domains are disabled before bounded cleanup; unknown
            # nested creations are retained for exact operator disposition.
            try:
                await identity_roles._write(lease, ks.domains.update, domain_id, enabled=False)
                if _enabled(await asyncio.to_thread(_exact, ks.domains, domain_id)):
                    raise _unavailable()
                projects = list(await asyncio.to_thread(ks.projects.list, domain=domain_id))
                groups = list(await asyncio.to_thread(ks.groups.list, domain=domain_id))
                users = list(await asyncio.to_thread(ks.users.list, domain=domain_id))
                if not projects and not groups and not users:
                    await identity_roles._write(lease, ks.domains.delete, domain_id)
                    if domain_id in {_field(d, "id") for d in await asyncio.to_thread(ks.domains.list)}:
                        raise _unavailable()
            except Exception as cleanup_error:
                raise HTTPException(503, "domain_setup_cleanup_unavailable") from cleanup_error
            raise
        if not enabled:
            await identity_roles._write(lease, ks.domains.update, domain_id, enabled=False)
        domain = await asyncio.to_thread(_exact, ks.domains, domain_id)
        if _enabled(domain) is not enabled or domain_display.display_name(domain) != name:
            raise _unavailable()
        await _invalidate(domain_id, {creator_id})
        return {
            "id": domain_id,
            "name": name,
            "description": description,
            "enabled": enabled,
            "kind": "organization",
            "default_project_id": project["id"],
        }


def managers(domain_id, *, ks=None, catalog=None):
    ks = _client(ks)
    catalog = catalog if catalog is not None else _catalog(ks)
    role = _canonical(catalog, "manager")
    project = default_project(domain_id, ks=ks)
    items = []
    if project:
        from app.services.project_service import _assignment_rows, _direct_ids

        direct = _assignment_rows(ks, project["id"])
        for uid in sorted(_manager_users(ks, project, catalog)):
            user = _exact(ks.users, uid)
            items.append(
                {
                    "user_id": uid,
                    "user_name": _field(user, "name", ""),
                    "user_domain_id": _field(user, "domain_id"),
                    "role_id": role["id"],
                    "role_name": "manager",
                    "direct": role["id"] in _direct_ids(direct, uid),
                }
            )
    return {
        "items": items,
        "roles": [{"id": role["id"], "name": "manager", "grantable": True}],
        "default_project_id": project["id"] if project else None,
    }


@identity_roles._complete_mutation
async def change_manager(domain_id, user_id, role_id, *, remove, actor):
    from app.services.project_service import _assignment_rows, _direct_ids

    async with _mutation() as (lease, ks, catalog):
        manager, _ = _roles(catalog)
        if role_id != manager["id"]:
            raise HTTPException(422, "domain_manager_role_invalid")
        project = await asyncio.to_thread(default_project, domain_id, ks=ks)
        if project is None:
            raise HTTPException(409, "domain_default_bootstrap_required")
        if not _enabled(await asyncio.to_thread(_exact, ks.domains, domain_id)):
            raise HTTPException(403, "domain_disabled")
        if await asyncio.to_thread(_active_user, ks, user_id) is None:
            raise HTTPException(403, "domain_user_disabled")
        if not remove:
            await asyncio.to_thread(assert_membership, user_id, domain_id, ks=ks)
        direct = await asyncio.to_thread(_assignment_rows, ks, project["id"])
        exists = role_id in _direct_ids(direct, user_id)
        if remove and not exists:
            raise HTTPException(404, "domain_manager_direct_grant_not_found")
        await identity_roles._session_ready({user_id})
        if remove:
            await asyncio.to_thread(
                assert_managers_remain,
                ks=ks,
                catalog=catalog,
                user_id=user_id,
                project_id=project["id"],
                role_id=role_id,
                remove_assignment=True,
            )
        changed = remove or not exists
        try:
            if changed:
                method = ks.roles.revoke if remove else ks.roles.grant
                await identity_roles._write(lease, method, role_id, user=user_id, project=project["id"])
                checked = await asyncio.to_thread(_assignment_rows, ks, project["id"])
                if (role_id in _direct_ids(checked, user_id)) is remove:
                    raise _unavailable()
            if not remove:
                await _ensure_reader(lease, ks, catalog, project["id"], user_id)
        finally:
            try:
                await _sync(domain_id, lease, ks, catalog)
            finally:
                if changed:
                    await _invalidate(domain_id, {user_id})
