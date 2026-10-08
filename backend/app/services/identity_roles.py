"""Keystone role lifecycle and real graph; presets are explicitly applied only.

A -> B grants B to holders of A. Management always uses the caller's connection;
only public presentation uses cached service-admin metadata. Afterglow serializes
its own role writes per Keystone endpoint so privilege checks cannot race; this is
not an atomic multi-request transaction and cannot fence writes made outside Afterglow.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import secrets
from collections.abc import Mapping
from contextlib import asynccontextmanager, suppress
from functools import wraps
from urllib.parse import quote

from anyio import CancelScope
from fastapi import HTTPException
from redis.exceptions import WatchError

from app.services import activity, keystone, session_store
from app.services.cache import cached_call, invalidate, ttl_slow
from app.services.service_permissions import ROLE_IMPLICATIONS, ROLE_PRESETS, normalize_role_name

_logger = logging.getLogger(__name__)
_GRAPH_LOCK_TTL_SECONDS = 60

CORE_NAMES = frozenset({"admin", "manager", "member", "reader"})
SYSTEM_NAMES = frozenset({"admin", "manager"})
VISIBILITY_KEY = "afterglow:identity:role-visibility"


def _field(value, key, default=None):
    return value.get(key, default) if isinstance(value, Mapping) else getattr(value, key, default)


def _unavailable(detail="Role security metadata is unavailable"):
    return HTTPException(status_code=503, detail=detail)


def _provider_error(exc):
    if isinstance(exc, HTTPException):
        return exc
    status = getattr(exc, "http_status", None) or getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    if status in (403, 404, 409):
        return HTTPException(status_code=status, detail="Keystone role operation rejected")
    if status == 400:
        return HTTPException(status_code=422, detail="Keystone rejected role request")
    return _unavailable("Keystone role operation is unavailable")


def _catalog(roles, inferences):
    rows = {}
    for role in roles:
        rid, name = _field(role, "id"), _field(role, "name")
        domain = _field(role, "domain_id")
        description = _field(role, "description") or ""
        if (
            not isinstance(rid, str)
            or not rid
            or rid in rows
            or not isinstance(name, str)
            or not name.strip()
            or (domain is not None and not isinstance(domain, str))
            or not isinstance(description, str)
        ):
            raise _unavailable()
        rows[rid] = {
            "id": rid,
            "name": name,
            "description": description,
            "domain_id": domain,
            "protected": name.casefold() in CORE_NAMES or name == "project_owner",
            "implied_role_ids": set(),
            "parent_role_ids": set(),
        }
    if not isinstance(inferences, list):
        raise _unavailable()
    for inference in inferences:
        prior = _field(_field(inference, "prior_role"), "id")
        children = _field(inference, "implies")
        if prior not in rows or not isinstance(children, list):
            raise _unavailable()
        for child in children:
            implied = _field(child, "id")
            if implied not in rows:
                raise _unavailable()
            rows[prior]["implied_role_ids"].add(implied)
            rows[implied]["parent_role_ids"].add(prior)
    for rid, row in rows.items():
        descendants = set()
        pending = list(row["implied_role_ids"])
        while pending:
            child = pending.pop()
            if child in descendants:
                continue
            descendants.add(child)
            pending.extend(rows[child]["implied_role_ids"])
        if rid in descendants:
            raise _unavailable("Keystone role implication graph contains a cycle")
        row["inherited_role_ids"] = sorted(descendants - {rid})
        row["system_only"] = any(rows[item]["name"].casefold() in SYSTEM_NAMES for item in descendants | {rid})
        row["implied_role_ids"] = sorted(row["implied_role_ids"])
        row["parent_role_ids"] = sorted(row["parent_role_ids"])
    return list(rows.values())


def load_catalog(conn) -> list[dict]:
    """Load SDK roles and Keystone's grouped /role_inferences response, uncached."""
    try:
        roles = list(conn.identity.roles())
        response = conn.identity.get("/role_inferences")
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or "role_inferences" not in payload:
            raise _unavailable()
        return _catalog(roles, payload["role_inferences"])
    except Exception as exc:
        error = _provider_error(exc)
        # A missing inference API is unavailable security metadata, not an empty graph.
        if error.status_code == 404:
            error = _unavailable("Keystone role graph is unavailable")
        raise error from exc


def _trusted_catalog():
    try:
        ks = keystone._get_admin_ks_client()
        return _catalog(list(ks.roles.list()), list(ks.inference_rules.list_inference_roles()))
    except Exception as exc:
        error = _provider_error(exc)
        if error.status_code == 404:
            error = _unavailable()
        raise error from exc


async def visible_role_names(names: list[str], is_system_admin: bool) -> list[str]:
    """Presentation only: never use this projection for authorization.

    Login and /me must not fail because presentation metadata is stale or down:
    noncore names that cannot be classified are hidden, never shown or raised.
    """
    if is_system_admin:
        return names
    core = [name for name in names if name.casefold() in CORE_NAMES - SYSTEM_NAMES]
    custom = [name for name in names if name.casefold() not in CORE_NAMES]
    if not custom:
        return core
    visible = set()
    for refresh in (False, True):
        try:
            by_name = _classify(await cached_call(VISIBILITY_KEY, ttl_slow(), _trusted_catalog, refresh=refresh))
        except ValueError:
            if not refresh:
                continue  # Replace a malformed cached snapshot once.
            _logger.warning("Role visibility metadata malformed; hiding custom role names")
            break
        except Exception:
            # Provider outage: do not retry per login; hide unclassifiable custom names.
            _logger.warning("Role visibility metadata unavailable; hiding custom role names", exc_info=True)
            break
        visible = {name for name in custom if by_name.get(name.casefold()) is False}
        # A role created/assigned outside Afterglow may be newer than the cached graph.
        if all(name.casefold() in by_name for name in custom):
            break
    return [name for name in names if name in core or name in visible]


def _classify(catalog) -> dict[str, bool]:
    if not isinstance(catalog, list) or any(
        not isinstance(row, dict)
        or not isinstance(row.get("name"), str)
        or not isinstance(row.get("system_only"), bool)
        for row in catalog
    ):
        raise ValueError("cached role visibility metadata is malformed")
    # Duplicate names across domains are conservative: any privileged match hides it.
    by_name = {}
    for row in catalog:
        key = row["name"].casefold()
        by_name[key] = by_name.get(key, False) or row["system_only"]
    return by_name


def _role(catalog, role_id):
    for row in catalog:
        if row["id"] == role_id:
            return row
    raise HTTPException(status_code=404, detail="Role not found")


def _ancestors(catalog, role_id):
    return {row["id"] for row in catalog if row["id"] == role_id or role_id in row["inherited_role_ids"]}


def _validate_edge(catalog, prior_id, implied_id):
    prior, implied = _role(catalog, prior_id), _role(catalog, implied_id)
    if prior_id == implied_id or prior_id in implied["inherited_role_ids"]:
        raise HTTPException(status_code=409, detail="Role implication would create a cycle")
    if implied_id in prior["implied_role_ids"]:
        raise HTTPException(status_code=409, detail="Role implication already exists")
    if implied["domain_id"] is not None and prior["domain_id"] != implied["domain_id"]:
        raise HTTPException(status_code=409, detail="Unsupported cross-domain implication")
    target_names = {_role(catalog, rid)["name"].casefold() for rid in [implied_id, *implied["inherited_role_ids"]]}
    for rid in _ancestors(catalog, prior_id):
        name = _role(catalog, rid)["name"].casefold()
        forbidden = (
            set()
            if name == "admin"
            else {"admin"}
            if name == "manager"
            else {"admin", "manager", "member"}
            if name == "reader"
            else SYSTEM_NAMES
        )
        if target_names & forbidden:
            raise HTTPException(status_code=409, detail="Role implication would elevate privilege")
    managed = {row["name"] for row in ROLE_PRESETS}
    if any(_role(catalog, rid)["name"] in managed for rid in _ancestors(catalog, prior_id)):
        candidate = [
            {**row, "implied_role_ids": sorted(set(row["implied_role_ids"]) | {implied_id})}
            if row["id"] == prior_id
            else row
            for row in catalog
        ]
        _validate_preset_catalog(candidate)


def _holders(conn, catalog, role_id):
    """Resolve effective and raw holders before mutation, including group/inherit grants.

    Raw grants cover inherited domain/project assignments without child projects yet;
    effective grants include Keystone-expanded groups and inherited recipients.
    """
    users = set()
    try:
        for rid in _ancestors(catalog, role_id):
            for effective in (False, True):
                query = {"role_id": rid, "effective": True} if effective else {"role_id": rid}
                # Keystone treats the effective flag by presence; omit it for raw grants.
                for assignment in conn.identity.role_assignments(**query):
                    assigned_role = _field(_field(assignment, "role"), "id")
                    if assigned_role != rid:
                        raise _unavailable()
                    user_id = _field(_field(assignment, "user"), "id")
                    group_id = _field(_field(assignment, "group"), "id")
                    if isinstance(user_id, str) and user_id:
                        users.add(user_id)
                    elif isinstance(group_id, str) and group_id:
                        for user in conn.identity.group_users(group_id):
                            uid = _field(user, "id")
                            if not isinstance(uid, str) or not uid:
                                raise _unavailable()
                            users.add(uid)
                    else:
                        raise _unavailable()
        return users
    except Exception as exc:
        raise _provider_error(exc) from exc


def _validate_name(catalog, name, domain, exclude=None):
    if name.casefold() in CORE_NAMES:
        raise HTTPException(status_code=409, detail="Reserved core role name")
    if any(
        row["id"] != exclude and row["domain_id"] == domain and row["name"].casefold() == name.casefold()
        for row in catalog
    ):
        raise HTTPException(status_code=409, detail="Role name already exists")


def _canonical_name(name):
    try:
        return normalize_role_name(name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _descendant_ids(catalog, role_id):
    by_id = {row["id"]: row for row in catalog}
    result, visiting = set(), set()

    def visit(rid):
        if rid not in by_id:
            raise _unavailable("Keystone role graph references an unknown role")
        if rid in visiting:
            raise _unavailable("Keystone role graph contains a cycle")
        if rid in result:
            return
        visiting.add(rid)
        for child in by_id[rid]["implied_role_ids"]:
            visit(child)
        visiting.remove(rid)
        result.add(rid)

    visit(role_id)
    return result - {role_id}


def _preset_names_below(name):
    edges = {}
    for prior, implied in ROLE_IMPLICATIONS:
        edges.setdefault(prior, set()).add(implied)
    # Do not seed a native edge; account for an already implied reader in bounds.
    edges.setdefault("member", set()).add("reader")
    result, pending = set(), list(edges.get(name, ()))
    while pending:
        child = pending.pop()
        if child not in result:
            result.add(child)
            pending.extend(edges.get(child, ()))
    return result


def _validate_preset_catalog(catalog):
    """Known identities have bounded descendants; unknown extra grants fail closed."""
    bindings, by_id = {}, {row["id"]: row for row in catalog}
    for definition in ROLE_PRESETS:
        name = definition["name"]
        matches = [row for row in catalog if row["domain_id"] is None and row["name"].casefold() == name]
        if not matches:
            continue
        if len(matches) != 1 or matches[0]["domain_id"] is not None or matches[0]["name"] != name:
            raise HTTPException(status_code=409, detail=f"Role identity is ambiguous or noncanonical: {name}")
        row = matches[0]
        allowed = _preset_names_below(name)
        for rid in _descendant_ids(catalog, row["id"]):
            child = by_id[rid]
            if child["domain_id"] is not None or child["name"] not in allowed:
                raise HTTPException(
                    status_code=409, detail=f"Unsafe role implication requires review: {name} -> {child['name']}"
                )
        if row["system_only"]:
            raise HTTPException(status_code=409, detail=f"Role reaches OpenStack administrator authority: {name}")
        bindings[name] = row
    return bindings


async def _to_completion(awaitable):
    """Do not report or unlock while a cancelled request's provider work still runs."""
    task = asyncio.ensure_future(awaitable)
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        with CancelScope(shield=True):
            while not task.done():
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    continue
                except Exception:
                    break
            with suppress(Exception):
                task.result()
        raise


def _complete_mutation(fn):
    """Keep provider write, cache clearing and revocation in one shielded lifecycle."""

    @wraps(fn)
    async def complete(*args, **kwargs):
        return await _to_completion(fn(*args, **kwargs))

    return complete


class _GraphLease:
    def __init__(self, redis, key, owner):
        self.redis, self.key, self.owner, self.lost = redis, key, owner, False

    async def _if_owned(self, operation) -> bool:
        """Owner compare-and-operate with WATCH, matching the Redis lease ownership pattern."""
        async with self.redis.pipeline() as pipe:
            try:
                await pipe.watch(self.key)
                value = await pipe.get(self.key)
                if isinstance(value, bytes):
                    value = value.decode()
                if not isinstance(value, str) or not hmac.compare_digest(value, self.owner):
                    await pipe.unwatch()
                    return False
                pipe.multi()
                operation(pipe)
                await pipe.execute()
                return True
            except WatchError:
                return False

    async def assert_owned(self) -> None:
        try:
            owned = await self.redis.get(self.key)
        except Exception:
            self.lost = True
            raise _unavailable("Role graph lock cannot be verified") from None
        if isinstance(owned, bytes):
            owned = owned.decode()
        if self.lost or not isinstance(owned, str) or not hmac.compare_digest(owned, self.owner):
            raise HTTPException(status_code=409, detail="Role graph lock expired; reload and retry")

    async def renew(self) -> None:
        while True:
            await asyncio.sleep(_GRAPH_LOCK_TTL_SECONDS / 3)
            try:
                if not await self._if_owned(lambda pipe: pipe.expire(self.key, _GRAPH_LOCK_TTL_SECONDS)):
                    self.lost = True
                    return
            except Exception:
                self.lost = True
                return


@asynccontextmanager
async def _graph_lock(conn):
    owner = secrets.token_hex(24)
    try:
        endpoint = await asyncio.to_thread(conn.endpoint_for, "identity")
        if not isinstance(endpoint, str) or not endpoint:
            raise ValueError("identity endpoint is unavailable")
        key = "afterglow:identity-role-graph:" + hashlib.sha256(endpoint.rstrip("/").encode()).hexdigest()
        redis = await session_store._get_redis()
        acquired = await redis.set(key, owner, nx=True, ex=_GRAPH_LOCK_TTL_SECONDS)
    except Exception:
        raise _unavailable("Role graph lock is unavailable") from None
    if not acquired:
        raise HTTPException(status_code=409, detail="Another role change is in progress")
    lease = _GraphLease(redis, key, owner)
    renewal = asyncio.create_task(lease.renew())
    try:
        yield lease
    finally:
        with CancelScope(shield=True):
            renewal.cancel()
            with suppress(asyncio.CancelledError):
                await renewal
            try:
                await lease._if_owned(lambda pipe: pipe.delete(key))
            except Exception:
                _logger.warning("Role graph lock release failed; it expires automatically")


async def _write(lease, fn, *args, **kwargs):
    await lease.assert_owned()
    try:
        return await _to_completion(asyncio.to_thread(fn, *args, **kwargs))
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        raise _provider_error(exc) from exc


async def _finish(token_info, action, role_id, users=(), extra=None, *, status="success"):
    # invalidate() fences in-flight local snapshots as well as stored cache entries.
    for key in ("afterglow:admin:roles", "afterglow:admin:identity:summary", VISIBILITY_KEY):
        await invalidate(key)
    try:
        for uid in sorted(users):
            await session_store.revoke_user_sessions(uid)
    except Exception as exc:
        raise _unavailable("Role change applied, but required session invalidation failed") from exc
    await activity.record(
        project_id=token_info.get("project_id", ""),
        user_id=token_info["user_id"],
        username=token_info.get("username", ""),
        resource_type="role",
        action=action,
        status=status,
        resource_id=role_id,
        extra=extra or {},
    )


async def _applied(conn, catalog, role_id, users, token_info, action, extra=None):
    """Post-write work is uncancellable; holders are re-read to close the snapshot gap."""

    async def complete():
        recipients = set(users or ())
        if users is not None and role_id is not None:
            try:
                recipients |= await asyncio.to_thread(_holders, conn, catalog, role_id)
            except HTTPException as exc:
                await _finish(token_info, action, role_id, recipients, extra)
                raise _unavailable("Role change applied, but session recipients could not be rechecked") from exc
        await _finish(token_info, action, role_id, recipients, extra)

    await _to_completion(complete())


async def _session_ready(users):
    if users:
        try:
            redis = await session_store._get_redis()
            await redis.ping()
        except Exception as exc:
            raise _unavailable("Required session invalidation store is unavailable") from exc


def _created_id(role):
    rid = _field(role, "id")
    if not isinstance(rid, str) or not rid:
        raise _unavailable("Keystone returned an invalid created role")
    return rid


@_complete_mutation
async def create_role(conn, token_info, attrs):
    attrs = {**attrs, "name": _canonical_name(attrs["name"])}
    async with _graph_lock(conn) as lease:
        catalog = await asyncio.to_thread(load_catalog, conn)
        _validate_name(catalog, attrs["name"], attrs.get("domain_id"))
        rid = _created_id(await _write(lease, conn.identity.create_role, **attrs))
        await _applied(conn, catalog, rid, None, token_info, "role_create")
    return _role(await asyncio.to_thread(load_catalog, conn), rid)


@_complete_mutation
async def update_role(conn, token_info, role_id, attrs):
    async with _graph_lock(conn) as lease:
        catalog = await asyncio.to_thread(load_catalog, conn)
        row = _role(catalog, role_id)
        renamed = "name" in attrs and attrs["name"] != row["name"]
        if renamed:
            if row["protected"]:
                raise HTTPException(status_code=409, detail="Core roles cannot be renamed")
            attrs = {**attrs, "name": _canonical_name(attrs["name"])}
            _validate_name(catalog, attrs["name"], row["domain_id"], exclude=role_id)
        # Token role names change for every holder of this role or an ancestor alias.
        users = await asyncio.to_thread(_holders, conn, catalog, role_id) if renamed else None
        await _session_ready(users)
        await _write(lease, conn.identity.update_role, role_id, **attrs)
        await _applied(conn, catalog, role_id, users, token_info, "role_update")
    return _role(await asyncio.to_thread(load_catalog, conn), role_id)


@_complete_mutation
async def delete_role(conn, token_info, role_id):
    async with _graph_lock(conn) as lease:
        catalog = await asyncio.to_thread(load_catalog, conn)
        row = _role(catalog, role_id)
        if row["protected"] or row["implied_role_ids"] or row["parent_role_ids"]:
            raise HTTPException(status_code=409, detail="Protected or connected roles cannot be deleted")
        try:
            # Raw grants include group/system/domain and inherited assignments; effective
            # alone can miss inherited grants which currently expand to no projects.
            assignments = await asyncio.to_thread(lambda: list(conn.identity.role_assignments(role_id=role_id)))
        except Exception as exc:
            raise _provider_error(exc) from exc
        if assignments:
            raise HTTPException(status_code=409, detail="Assigned roles cannot be deleted")
        await _write(lease, conn.identity.delete_role, role_id, ignore_missing=False)
        await _applied(conn, catalog, role_id, None, token_info, "role_delete")
    return {"status": "deleted"}


def _native_edge(conn, method, path):
    response = getattr(conn.identity, method)(path)
    response.raise_for_status()


@_complete_mutation
async def change_edge(conn, token_info, prior_id, implied_id, *, remove=False):
    async with _graph_lock(conn) as lease:
        catalog = await asyncio.to_thread(load_catalog, conn)
        prior = _role(catalog, prior_id)
        child = _role(catalog, implied_id)
        if any(_role(catalog, rid)["name"] == "project_owner" for rid in {implied_id, *child["inherited_role_ids"]}):
            raise HTTPException(status_code=409, detail="Use the project ownership workflow to change owner grants")
        if remove:
            if implied_id not in prior["implied_role_ids"]:
                raise HTTPException(status_code=404, detail="Role implication not found")
        else:
            _validate_edge(catalog, prior_id, implied_id)
            # Adding a lower edge grants only extra permissions: existing sessions retain no
            # removed privilege, so do not log out every holder. Removal must revoke.
        users = None
        if remove:
            # Snapshot before the write. The edge does not change prior's ancestors, so
            # the same catalog is re-used after the write to include concurrent grants.
            users = await asyncio.to_thread(_holders, conn, catalog, prior_id)
            await _session_ready(users)
        path = f"/roles/{quote(prior_id, safe='')}/implies/{quote(implied_id, safe='')}"
        await _write(lease, _native_edge, conn, "delete" if remove else "put", path)
        await _applied(
            conn,
            catalog,
            prior_id,
            users,
            token_info,
            "role_implication_delete" if remove else "role_implication_create",
            {"implied_role_id": implied_id},
        )
    return {"status": "deleted" if remove else "created"}


@_complete_mutation
async def apply_role_presets(conn, token_info):
    """Idempotent additive application; no role/assignment is replaced or deleted."""
    created_roles, created_edges = [], []
    attempted = False
    async with _graph_lock(conn) as lease:
        catalog = await asyncio.to_thread(load_catalog, conn)
        bindings = _validate_preset_catalog(catalog)
        for name in ("member", "reader"):
            matches = [row for row in catalog if row["domain_id"] is None and row["name"].casefold() == name]
            if len(matches) != 1 or matches[0]["domain_id"] is not None or matches[0]["name"] != name:
                raise HTTPException(status_code=409, detail=f"Existing global native role is required: {name}")
            bindings[name] = matches[0]
        try:
            for definition in ROLE_PRESETS:
                name = definition["name"]
                if name not in bindings:
                    attempted = True
                    role = await _write(
                        lease, conn.identity.create_role, name=name, description=definition["description"]
                    )
                    rid = _created_id(role)
                    created_roles.append(name)
                    catalog = await asyncio.to_thread(load_catalog, conn)
                    bindings.update(_validate_preset_catalog(catalog))
                    if bindings.get(name, {}).get("id") != rid:
                        raise _unavailable("Created role identity could not be verified")
            for prior_name, implied_name in ROLE_IMPLICATIONS:
                catalog = await asyncio.to_thread(load_catalog, conn)
                bindings.update(_validate_preset_catalog(catalog))
                prior, child = bindings[prior_name], bindings[implied_name]
                if child["id"] in _role(catalog, prior["id"])["implied_role_ids"]:
                    continue
                _validate_edge(catalog, prior["id"], child["id"])
                path = f"/roles/{quote(prior['id'], safe='')}/implies/{quote(child['id'], safe='')}"
                attempted = True
                await _write(lease, _native_edge, conn, "put", path)
                created_edges.append({"prior": prior_name, "implied": implied_name})
            fresh = await asyncio.to_thread(load_catalog, conn)
            _validate_preset_catalog(fresh)
        except HTTPException as exc:
            if attempted:
                await _finish(
                    token_info,
                    "role_presets_partial",
                    None,
                    extra={"created_roles": created_roles, "created_implications": created_edges},
                    status="failed",
                )
                raise HTTPException(
                    status_code=exc.status_code,
                    detail={
                        "message": "Preset application may be partial; retry preserves existing roles",
                        "created_roles": created_roles,
                        "created_implications": created_edges,
                        "cause": exc.detail,
                    },
                ) from exc
            raise
        await _finish(
            token_info,
            "role_presets_apply",
            None,
            extra={"created_roles": created_roles, "created_implications": created_edges},
        )
    return {"created_roles": created_roles, "created_implications": created_edges, "roles": fresh}


def _owner_bearing_role(catalog, role_id):
    by_id = {row["id"]: row for row in catalog}
    _role(catalog, role_id)
    return any(
        by_id[rid]["name"].casefold() == "project_owner" for rid in {role_id, *_descendant_ids(catalog, role_id)}
    )


async def _assignment_invalidation(token_info, action, role_id, users, project_id, *, succeeded):
    from app.services.cache import keys

    try:
        for user_id in users:
            await invalidate(keys.user_key(user_id, "projects"))
    finally:
        await _finish(
            token_info,
            action,
            role_id,
            users,
            {"target_project_id": project_id},
            status="success" if succeeded else "failed",
        )


@_complete_mutation
async def change_project_assignment(
    conn, token_info, project_id, role_id, *, user_id=None, group_id=None, remove=False
):
    """Generic system-admin assignment cannot circumvent scoped owner protection."""
    async with _graph_lock(conn) as lease:
        catalog = await asyncio.to_thread(load_catalog, conn)
        if _owner_bearing_role(catalog, role_id):
            raise HTTPException(status_code=409, detail="Use the project ownership workflow for owner-bearing roles")
        if (user_id is None) == (group_id is None):
            raise HTTPException(status_code=422, detail="Supply exactly one assignment principal")
        if group_id is not None:
            members = await asyncio.to_thread(lambda: list(conn.identity.group_users(group_id)))
            users = {_field(member, "id") for member in members}
            if any(not isinstance(uid, str) or not uid for uid in users):
                raise _unavailable("Group assignment recipients are unavailable")
            method = (
                conn.identity.unassign_project_role_from_group if remove else conn.identity.assign_project_role_to_group
            )
            args = (project_id, group_id, role_id)
        else:
            users = {user_id}
            method = (
                conn.identity.unassign_project_role_from_user if remove else conn.identity.assign_project_role_to_user
            )
            args = (project_id, user_id, role_id)
        await _session_ready(users)
        succeeded = False
        try:
            await _write(lease, method, *args)
            succeeded = True
        finally:
            # An uncertain provider response can still have committed the change.
            await _assignment_invalidation(
                token_info, "role_revoke" if remove else "role_assign", role_id, users, project_id, succeeded=succeeded
            )
    return {"status": "revoked" if remove else "assigned"}


@_complete_mutation
async def change_group_membership(conn, token_info, group_id, *, user_id=None, remove=False, delete=False):
    """Owner-bearing group grants remain read-only in generic group management.

    There is no target-project ownership transition on a global group endpoint.
    Reject rather than silently remove the last owner of any inherited project.
    """
    async with _graph_lock(conn) as lease:
        catalog = await asyncio.to_thread(load_catalog, conn)
        assignments = await asyncio.to_thread(lambda: list(conn.identity.role_assignments(group_id=group_id)))
        for assignment in assignments:
            if _field(_field(assignment, "group", {}), "id") != group_id:
                raise _unavailable("Group assignment scope is unavailable")
            role_id = _field(_field(assignment, "role", {}), "id")
            if _owner_bearing_role(catalog, role_id):
                raise HTTPException(
                    status_code=409,
                    detail="Owner-bearing group grants require an explicit project ownership transition",
                )
        if delete:
            members = await asyncio.to_thread(lambda: list(conn.identity.group_users(group_id)))
            users = {_field(member, "id") for member in members}
            if any(not isinstance(uid, str) or not uid for uid in users):
                raise _unavailable("Group mutation recipients are unavailable")
            method, args, kwargs = conn.identity.delete_group, (group_id,), {"ignore_missing": False}
        else:
            users = {user_id}
            method = conn.identity.remove_user_from_group if remove else conn.identity.add_user_to_group
            args, kwargs = (user_id, group_id), {}
        await _session_ready(users)
        succeeded = False
        try:
            await _write(lease, method, *args, **kwargs)
            succeeded = True
        finally:
            await _assignment_invalidation(
                token_info,
                "group_delete" if delete else "group_member_remove" if remove else "group_member_add",
                None,
                users,
                None,
                succeeded=succeeded,
            )
