"""Domain-manager group CRUD and membership inside the session's organization domain.

The domain always comes from the authenticated session. The managed manager
projection group is invisible and immutable, and a group whose grants reach
beyond project roles a domain manager could assign in this domain is read-only.
Operator SSO mappings resolve groups in this domain by exact name, so a mapped
group can never be renamed or deleted here and its name cannot be reassigned.
Membership and deletion reuse the generic native path (graph lease, last-manager
and owner-bearing protection, post-write invalidation) through its scoped
``authorize`` hook, so this module only adds the domain boundary.
"""

from __future__ import annotations

import asyncio

from fastapi import HTTPException

from app.services import activity, domain_iam, domain_projects, domain_scope, identity_roles, keystone, project_service
from app.services.cache import invalidate
from app.services.project_service import _provider_call

_field = identity_roles._field
_ADMIN_GROUPS_CACHE = "afterglow:admin:groups:*"


def _group(ks, group_id, domain_id, *, reads=None):
    try:
        group = domain_projects._exact(ks.groups, group_id, reads=reads)
    except HTTPException as exc:
        if exc.status_code == 404:
            raise HTTPException(404, "domain_group_not_found") from exc
        raise
    if domain_projects._is_projection_group(group):
        raise HTTPException(403, "domain_manager_projection_is_private")
    domain_scope.assert_domain_resource(domain_id, _field(group, "domain_id"))
    return group


def _member_ids(ks, group_id):
    ids = [_field(user, "id") for user in ks.users.list(group=group_id)]
    if any(not isinstance(uid, str) or not uid for uid in ids):
        raise identity_roles._unavailable("Group members are unavailable")
    return ids


def _manageable(ks, catalog, group_id, domain_id, *, reads):
    """Only project roles a domain manager may assign, on this domain's projects."""
    managed = project_service._managed_roles(catalog)
    rows = [
        *ks.role_assignments.list(group=group_id),
        *ks.role_assignments.list(group=group_id, system="all"),
    ]
    for row in rows:
        meta = domain_projects._assignment(row, catalog)
        if meta["group_id"] != group_id:
            raise identity_roles._unavailable("Group assignment scope is unavailable")
        if meta["role_id"] not in managed:
            return False
        if meta["kind"] == "project":
            project = domain_projects._exact(ks.projects, meta["scope_id"], reads=reads)
            if _field(project, "domain_id") != domain_id:
                return False
        elif meta["kind"] != "domain" or meta["scope_id"] != domain_id:
            return False
    return True


def _editable(ks, catalog, group_id, domain_id):
    reads = {}
    group = _group(ks, group_id, domain_id, reads=reads)
    if not _manageable(ks, catalog, group_id, domain_id, reads=reads):
        raise HTTPException(403, "domain_group_read_only")
    return group


def _mapped_names(ks, domain_id):
    """Casefolded group names this domain's configured SSO mappings resolve by name.

    Mirrors the group clauses domain_auth._require_accounts_email_mapping accepts;
    renaming or deleting such a group would make every SSO login fail closed.
    """
    from app.services import domain_auth

    names = set()
    try:
        for provider in domain_auth._selected_config_providers(domain_id).values():
            protocol = ks.federation.protocols.get(provider.keystone_idp_id, provider.keystone_protocol_id)
            mapping_id = _field(protocol, "mapping_id")
            rules = _field(ks.federation.mappings.get(mapping_id), "rules", []) if mapping_id else []
            if not isinstance(rules, list):
                raise ValueError("mapping rules are malformed")
            for rule in rules:
                local = rule.get("local") if isinstance(rule, dict) else None
                for value in local if isinstance(local, list) else ():
                    group = value.get("group") if isinstance(value, dict) else None
                    if isinstance(group, dict) and group.get("domain") == {"id": domain_id}:
                        if not isinstance(group.get("name"), str):
                            raise ValueError("mapped group name is malformed")
                        names.add(group["name"].casefold())
    except Exception as exc:
        # Login-critical metadata: never treat an unreadable mapping as unmapped.
        raise identity_roles._unavailable("SSO group mappings are unavailable") from exc
    return names


def _assert_unmapped(mapped, group, *, new_name=None):
    if group is not None and (_field(group, "name", "") or "").casefold() in mapped:
        raise HTTPException(403, "domain_group_read_only")
    if new_name is not None and new_name.casefold() in mapped:
        raise HTTPException(403, "domain_group_name_reserved")


def _assert_unique_name(ks, domain_id, name, group_id=None):
    for row in ks.groups.list(domain=domain_id):
        domain_scope.assert_domain_resource(domain_id, _field(row, "domain_id"))
        other = _field(row, "name")
        if not isinstance(other, str):
            raise identity_roles._unavailable("Group directory is unavailable")
        if other.casefold() == name.casefold() and _field(row, "id") != group_id:
            raise HTTPException(409, "domain_group_name_exists")


def _dto(group, domain_id, *, member_count, protected, sso_mapped):
    return {
        "id": _field(group, "id"),
        "name": _field(group, "name", "") or "",
        "description": _field(group, "description", "") or "",
        "domain_id": domain_id,
        "member_count": member_count,
        "protected": protected,
        "sso_mapped": sso_mapped,
    }


async def _assert_unprotected(user, domain_id, token_info):
    # Mirrors domain project membership: another privileged account is read-only.
    if _field(user, "id") != token_info["user_id"] and await domain_iam.protected_user(
        user, domain_id, credentials=False
    ):
        raise HTTPException(403, "Privileged accounts are read-only in domain IAM")


async def list_groups(token_info):
    ctx = await domain_iam.context(token_info)
    did = ctx["domain_id"]
    ks = await _provider_call(keystone._get_admin_ks_client)
    catalog = await _provider_call(identity_roles._trusted_catalog)
    groups = []
    for row in await _provider_call(lambda: list(ks.groups.list(domain=did))):
        domain_scope.assert_domain_resource(did, _field(row, "domain_id"))
        gid = _field(row, "id")
        if not isinstance(gid, str) or not gid:
            raise identity_roles._unavailable("Group directory is unavailable")
        if not domain_projects._is_projection_group(row):
            groups.append(row)

    mapped = await _provider_call(_mapped_names, ks, did)

    async def view(group):
        gid = _field(group, "id")
        members = await _provider_call(_member_ids, ks, gid)
        manageable = await _provider_call(_manageable, ks, catalog, gid, did, reads={})
        sso_mapped = (_field(group, "name", "") or "").casefold() in mapped
        return _dto(group, did, member_count=len(members), protected=not manageable, sso_mapped=sso_mapped)

    items = await asyncio.gather(*(view(group) for group in groups))
    return {"items": sorted(items, key=lambda item: (item["name"].casefold(), item["id"]))}


async def list_members(group_id, token_info):
    ctx = await domain_iam.context(token_info)
    did = ctx["domain_id"]
    ks = await _provider_call(keystone._get_admin_ks_client)
    await _provider_call(_group, ks, group_id, did)
    users = await _provider_call(lambda: list(ks.users.list(group=group_id)))
    items = []
    for user in users:
        if not isinstance(_field(user, "id"), str) or not _field(user, "id"):
            raise identity_roles._unavailable("Group members are unavailable")
        protected = _field(user, "id") != token_info["user_id"] and await domain_iam.protected_user(
            user, did, credentials=False
        )
        items.append({**domain_iam.user_dto(user, protected), "identity_read_only": _field(user, "domain_id") != did})
    return {"items": sorted(items, key=lambda item: (item["name"].casefold(), item["id"]))}


async def _record(token_info, action, group, status="success"):
    await activity.record(
        project_id=token_info.get("project_id", ""),
        user_id=token_info["user_id"],
        username=token_info.get("username", ""),
        resource_type="group",
        action=action,
        status=status,
        resource_id=_field(group, "id"),
        resource_name=_field(group, "name"),
        service="keystone",
    )


@identity_roles._complete_mutation
async def create_group(attrs, token_info):
    domain_projects.assert_projection_attributes(attrs)
    await domain_iam.context(token_info)
    async with domain_iam._iam_write() as (lease, ks, _catalog):
        ctx = await domain_iam.context(token_info)
        did = ctx["domain_id"]
        await _provider_call(_assert_unique_name, ks, did, attrs["name"])
        _assert_unmapped(await _provider_call(_mapped_names, ks, did), None, new_name=attrs["name"])
        group = await identity_roles._write(
            lease, ks.groups.create, name=attrs["name"], domain=did, description=attrs.get("description") or ""
        )
        if not isinstance(_field(group, "id"), str) or not _field(group, "id"):
            raise identity_roles._unavailable("Keystone returned an invalid created group")
        try:
            await _record(token_info, "group.create", group)
        finally:
            await invalidate(_ADMIN_GROUPS_CACHE)
        return _dto(group, did, member_count=0, protected=False, sso_mapped=False)


@identity_roles._complete_mutation
async def update_group(group_id, attrs, token_info):
    domain_projects.assert_projection_attributes(attrs)
    await domain_iam.context(token_info)
    async with domain_iam._iam_write() as (lease, ks, catalog):
        ctx = await domain_iam.context(token_info)
        did = ctx["domain_id"]
        group = await _provider_call(_editable, ks, catalog, group_id, did)
        mapped = await _provider_call(_mapped_names, ks, did)
        if "name" in attrs and attrs["name"] != _field(group, "name"):
            await _provider_call(_assert_unique_name, ks, did, attrs["name"], group_id)
            # Description-only edits never change what a name-based SSO mapping resolves.
            _assert_unmapped(mapped, group, new_name=attrs["name"])
        updated = await identity_roles._write(lease, ks.groups.update, group_id, **attrs)
        if _field(updated, "id") != group_id:
            raise identity_roles._unavailable("Keystone returned an invalid updated group")
        try:
            await _record(token_info, "group.update", updated)
        finally:
            await invalidate(_ADMIN_GROUPS_CACHE)
        members = await _provider_call(_member_ids, ks, group_id)
        sso_mapped = (_field(updated, "name", "") or "").casefold() in mapped
        return _dto(updated, did, member_count=len(members), protected=False, sso_mapped=sso_mapped)


def _authorize(token_info, group_id, *, user_id=None, add=False, delete=False):
    async def authorize(ks, catalog):
        # Re-prove live manager authority and every boundary under the shared lease.
        ctx = await domain_iam.context(token_info)
        did = ctx["domain_id"]
        group = await _provider_call(_editable, ks, catalog, group_id, did)
        members = await _provider_call(_member_ids, ks, group_id)
        if delete:
            _assert_unmapped(await _provider_call(_mapped_names, ks, did), group)
            for uid in members:
                await _assert_unprotected(await _provider_call(domain_projects._exact, ks.users, uid), did, token_info)
            return
        if add:
            if user_id in members:
                raise HTTPException(409, "domain_group_member_exists")
            user = await domain_iam.assert_joined_user(did, user_id, ks=ks)
        else:
            if user_id not in members:
                raise HTTPException(404, "domain_group_member_not_found")
            user = await _provider_call(domain_projects._exact, ks.users, user_id)
        await _assert_unprotected(user, did, token_info)

    return authorize


async def _change(token_info, group_id, *, user_id=None, remove=False, delete=False):
    await domain_iam.context(token_info)
    authorize = _authorize(token_info, group_id, user_id=user_id, add=not remove and not delete, delete=delete)
    conn = await _provider_call(keystone.get_admin_project_connection)
    try:
        await identity_roles.change_group_membership(
            conn, token_info, group_id, user_id=user_id, remove=remove, delete=delete, authorize=authorize
        )
    finally:
        await asyncio.to_thread(conn.close)


async def add_member(group_id, user_id, token_info):
    await _change(token_info, group_id, user_id=user_id)


async def remove_member(group_id, user_id, token_info):
    await _change(token_info, group_id, user_id=user_id, remove=True)


async def delete_group(group_id, token_info):
    await _change(token_info, group_id, delete=True)
    await invalidate(_ADMIN_GROUPS_CACHE)
