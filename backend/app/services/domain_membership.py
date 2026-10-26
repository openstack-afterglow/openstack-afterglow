"""Organization eviction without deleting identity, resources or foreign grants."""

import asyncio
from urllib.parse import quote

from fastapi import HTTPException

from app.services import domain_iam, domain_projects, identity_roles, keystone, project_ownership_journal
from app.services.project_service import _provider_call

_field = identity_roles._field


def _complete_rows(manager, path, key, **query):
    transport = getattr(manager, "client", None)
    if transport is not None and callable(getattr(transport, "get", None)):
        _, body = transport.get(path)
        if not isinstance(body, dict) or not isinstance(body.get(key), list):
            raise domain_projects._unavailable()
        links = body.get("links")
        if not isinstance(links, dict) or links.get("next") or body.get("truncated") or body.get("limited"):
            raise HTTPException(503, "domain_eviction_inventory_incomplete")
        return body[key]
    rows = manager.list(**query)
    links = getattr(rows, "links", {})
    if (
        getattr(rows, "truncated", False)
        or getattr(rows, "limited", False)
        or getattr(rows, "next", None)
        or isinstance(links, dict)
        and links.get("next")
    ):
        raise HTTPException(503, "domain_eviction_inventory_incomplete")
    return list(rows)


def _plan(ks, catalog, domain_id, user_id):
    """Validate every source before writing: group removal must be domain-local."""
    user = domain_projects._exact(ks.users, user_id)
    if _field(user, "domain_id") == domain_id:
        raise HTTPException(409, "domain_eviction_identity_home")
    raw_rows = _complete_rows(
        ks.role_assignments, f"/role_assignments?user.id={quote(user_id, safe='')}", "role_assignments", user=user_id
    )
    raw = [domain_projects._assignment(row, catalog) for row in raw_rows]
    if any(row["user_id"] != user_id for row in raw):
        raise domain_projects._unavailable()
    groups = _complete_rows(ks.groups, f"/users/{quote(user_id, safe='')}/groups", "groups", user=user_id)
    # Native project LIST may silently truncate. Resolve exact source projects,
    # including disabled ones, instead of selecting revokes from a partial list.
    reads = {}
    project_ids = set()
    group_ids = set()
    for group in groups:
        gid = _field(group, "id")
        if not isinstance(gid, str) or not gid:
            raise domain_projects._unavailable()
        group_ids.add(gid)
    for gid in sorted(group_ids):
        grants = [
            domain_projects._assignment(row, catalog)
            for row in _complete_rows(
                ks.role_assignments, f"/role_assignments?group.id={quote(gid, safe='')}", "role_assignments", group=gid
            )
        ]
        if any(row["group_id"] != gid for row in grants):
            raise domain_projects._unavailable()
        raw.extend(grants)
    for pid in {row["scope_id"] for row in raw if row["kind"] == "project"}:
        project = domain_projects._exact(ks.projects, pid, reads=reads)
        if _field(project, "domain_id") == domain_id:
            project_ids.add(pid)
    relevant = [
        row
        for row in raw
        if (
            row["kind"] == "domain"
            and row["scope_id"] == domain_id
            or row["kind"] == "project"
            and row["scope_id"] in project_ids
        )
        and (row["user_id"] == user_id or row["group_id"] in group_ids)
    ]
    if not relevant:
        raise HTTPException(409, "domain_eviction_not_joined")
    # Ownership/manager authority must be explicitly transferred first; removing
    # even one owner-bearing source through this bulk workflow is not a transfer.
    by_id = {row["id"]: row for row in catalog}
    for row in relevant:
        ids = {row["role_id"], *identity_roles._descendant_ids(catalog, row["role_id"])}
        if any(by_id[rid]["name"] in {"project_owner", "manager", "admin", "service"} for rid in ids):
            raise HTTPException(409, "domain_eviction_privileged_source")
    removing_groups = {row["group_id"] for row in relevant if row["group_id"]}
    for gid in removing_groups:
        group = domain_projects._exact(ks.groups, gid)
        if _field(group, "domain_id") != domain_id or domain_projects._is_projection_group(group):
            raise HTTPException(409, "domain_eviction_shared_group")
        for row in raw:
            if row["group_id"] != gid:
                continue
            if not (
                row["kind"] == "domain"
                and row["scope_id"] == domain_id
                or row["kind"] == "project"
                and row["scope_id"] in project_ids
            ):
                raise HTTPException(409, "domain_eviction_shared_group")
    direct = [row for row in relevant if row["user_id"] == user_id]
    # An inherited project source could authorize a child outside this domain;
    # prove the native project subtree before revoking the shared source.
    for row in relevant:
        if row["kind"] == "project" and row["inherited"]:
            parent = domain_projects._exact(ks.projects, row["scope_id"])
            descendants = ks.projects.get(_field(parent, "id"), subtree_as_ids=True)
            subtree = _field(descendants, "subtree")
            if not hasattr(descendants, "subtree") and not (isinstance(descendants, dict) and "subtree" in descendants):
                raise domain_projects._unavailable()
            if subtree is not None and not isinstance(subtree, dict):
                raise domain_projects._unavailable()
            pending = [subtree] if subtree is not None else []
            while pending:
                for pid, children in pending.pop().items():
                    project = domain_projects._exact(ks.projects, pid, reads=reads)
                    if _field(project, "domain_id") != domain_id or (
                        children is not None and not isinstance(children, dict)
                    ):
                        raise HTTPException(409, "domain_eviction_shared_source")
                    if children is not None:
                        pending.append(children)
    return direct, sorted(removing_groups)


@identity_roles._complete_mutation
async def remove_user(user_id, token_info):
    ctx = await domain_iam.context(token_info)
    domain_id = ctx["domain_id"]
    if user_id == token_info["user_id"]:
        raise HTTPException(403, "domain_eviction_self")
    conn = await _provider_call(keystone.get_admin_project_connection)
    try:
        async with identity_roles._graph_lock(conn) as lease:
            await domain_iam.context(token_info)
            ks = await _provider_call(keystone._get_admin_ks_client)
            catalog = await _provider_call(identity_roles.load_catalog, conn)
            user = await _provider_call(domain_projects._exact, ks.users, user_id)
            if await domain_iam.protected_user(user, domain_id, credentials=False, system_services=True):
                raise HTTPException(403, "domain_eviction_protected")
            await project_ownership_journal.assert_user_resolved(user_id)
            direct, groups = await _provider_call(_plan, ks, catalog, domain_id, user_id)
            await identity_roles._session_ready({user_id})
            attempted = False
            succeeded = False
            try:
                for row in direct:
                    kwargs = {"user": user_id, row["kind"]: row["scope_id"]}
                    if row["inherited"]:
                        kwargs["os_inherit_extension_inherited"] = True
                    attempted = True
                    await identity_roles._write(lease, ks.roles.revoke, row["role_id"], **kwargs)
                for gid in groups:
                    attempted = True
                    await identity_roles._write(lease, ks.users.remove_from_group, user_id, gid)
                # Never announce eviction while any native domain source remains.
                try:
                    await _provider_call(_plan, ks, catalog, domain_id, user_id)
                except HTTPException as exc:
                    if exc.status_code != 409 or exc.detail != "domain_eviction_not_joined":
                        raise
                else:
                    raise HTTPException(503, "domain_eviction_uncertain")
                succeeded = True
            except Exception as exc:
                if attempted:
                    raise HTTPException(503, "domain_eviction_uncertain") from exc
                raise
            finally:
                if attempted:
                    await domain_projects._invalidate(domain_id, {user_id})
                    await identity_roles._applied(
                        None,
                        catalog,
                        None,
                        {user_id},
                        token_info,
                        "domain_member_remove",
                        {"domain_id": domain_id, "user_id": user_id},
                        status="success" if succeeded else "failed",
                    )
            return {"status": "removed", "domain_id": domain_id, "user_id": user_id}
    finally:
        await asyncio.to_thread(conn.close)
