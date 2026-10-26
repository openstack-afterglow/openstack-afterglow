"""Explicit administrator reads using the fixed native admin-project executor.

The workspace project is never an authentication scope. Native parent metadata
and parent-bound child URLs, not browser project parameters, establish ownership.
"""

from __future__ import annotations

import asyncio
from itertools import islice
from typing import Annotated, Any
from urllib.parse import parse_qs, quote, urlsplit

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from openstack.resource import Resource

from app.api.common.admin_resource_scope import resolve_scope
from app.api.deps import get_admin_os_conn
from app.services import manila, octavia, trove

router = APIRouter()
NativeId = Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]+$", max_length=128)]


def _field(resource: Any, key: str) -> Any:
    # SDK Resources subclass dict, but its JSON snapshot can lag native attributes.
    if isinstance(resource, Resource):
        return getattr(resource, key, None)
    return resource.get(key) if isinstance(resource, dict) else getattr(resource, key, None)


def _not_found() -> None:
    raise HTTPException(404, "관리자 상세 자원의 소유권 또는 연결 정보를 확인할 수 없습니다")


def _identity(resource: Any, resource_id: str | None = None, owner: str | None = None) -> str:
    actual_id = _field(resource, "id")
    project_id = _field(resource, "project_id") or _field(resource, "tenant_id")
    if (
        not isinstance(actual_id, str)
        or not actual_id
        or (resource_id is not None and actual_id != resource_id)
        or not isinstance(project_id, str)
        or not project_id.strip()
        or (_field(resource, "tenant_id") not in (None, project_id))
        or (owner is not None and project_id != owner)
    ):
        _not_found()
    return project_id


def _lb_child(resource: Any, lb_id: str, owner: str, *, pool: bool = False) -> None:
    _identity(resource, owner=owner)
    parents = _field(resource, "loadbalancers" if pool else "load_balancers")
    direct = _field(resource, "loadbalancer_id" if pool else "load_balancer_id")
    parent_ids = {item.get("id") for item in parents or [] if isinstance(item, dict)}
    if direct:
        parent_ids.add(direct)
    if parent_ids != {lb_id}:
        _not_found()


async def _read(fn, *args, **kwargs):
    try:
        return await asyncio.to_thread(fn, *args, **kwargs)
    except HTTPException:
        raise
    except Exception as exc:
        status = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
        raise HTTPException(404 if status == 404 else 502, "관리자 자원 조회 실패") from exc


def _share(conn, share_id: str):
    # Check canonical native owner before export locations or access secrets.
    raw = manila.get_client(conn).get(f"shares/{share_id}").get("share")
    owner = _identity(raw, share_id)
    metadata_owner = (raw.get("metadata") or {}).get("union_project_id")
    if metadata_owner and metadata_owner != owner:
        _not_found()
    return raw


@router.get("/file-storage/{file_storage_id}")
async def get_admin_file_storage(file_storage_id: NativeId, conn=Depends(get_admin_os_conn)):
    raw = await _read(_share, conn, file_storage_id)
    detail = await _read(manila.get_file_storage, conn, file_storage_id, resolve_user=True)
    _identity(detail, file_storage_id, raw["project_id"])
    return detail


@router.get("/file-storage/{file_storage_id}/access-rules")
async def get_admin_file_storage_access_rules(file_storage_id: NativeId, conn=Depends(get_admin_os_conn)):
    raw = await _read(_share, conn, file_storage_id)
    rules = await _read(manila.list_access_rules, conn, file_storage_id, strict=True)
    result = []
    for listed in rules:
        rule = await _read(manila.get_access_rule, conn, file_storage_id, listed["id"])
        if (
            not isinstance(rule, dict)
            or rule.get("id") != listed["id"]
            or rule.get("share_id") != file_storage_id
            or (rule.get("project_id") and rule["project_id"] != raw["project_id"])
        ):
            _not_found()
        result.append({key: value for key, value in rule.items() if key not in {"secret", "access_key"}})
    return result


async def _load_balancer(conn, lb_id: str):
    lb = await _read(conn.load_balancer.get_load_balancer, lb_id)
    _identity(lb, lb_id)
    return lb


@router.get("/loadbalancers/{lb_id}")
async def get_admin_load_balancer(lb_id: NativeId, conn=Depends(get_admin_os_conn)):
    return octavia._lb_to_dict(await _load_balancer(conn, lb_id))


async def _lb_children(conn, lb_id: str, kind: str):
    lb = await _load_balancer(conn, lb_id)
    query = {"loadbalancer_id" if kind == "pools" else "load_balancer_id": lb_id}
    rows = await _read(lambda: list(islice(getattr(conn.load_balancer, kind)(**query), 10001)))
    if len(rows) > 10000:
        raise HTTPException(502, "관리자 하위 자원 조회 한도를 초과했습니다")
    for row in rows:
        _lb_child(row, lb_id, _identity(lb, lb_id), pool=kind == "pools")
    return rows


@router.get("/loadbalancers/{lb_id}/listeners")
async def get_admin_lb_listeners(lb_id: NativeId, conn=Depends(get_admin_os_conn)):
    return [
        {**octavia._listener_to_dict(row), "load_balancer_id": lb_id}
        for row in await _lb_children(conn, lb_id, "listeners")
    ]


@router.get("/loadbalancers/{lb_id}/pools")
async def get_admin_lb_pools(lb_id: NativeId, conn=Depends(get_admin_os_conn)):
    return [
        {**octavia._pool_to_dict(row), "load_balancer_id": lb_id} for row in await _lb_children(conn, lb_id, "pools")
    ]


async def _pool(conn, lb_id: str, pool_id: str, owner: str):
    pool = await _read(conn.load_balancer.get_pool, pool_id)
    _identity(pool, pool_id, owner)
    _lb_child(pool, lb_id, owner, pool=True)
    return pool


@router.get("/loadbalancers/{lb_id}/pools/{pool_id}/members")
async def get_admin_lb_members(lb_id: NativeId, pool_id: NativeId, conn=Depends(get_admin_os_conn)):
    lb = await _load_balancer(conn, lb_id)
    owner = _identity(lb, lb_id)
    await _pool(conn, lb_id, pool_id, owner)
    # Octavia's member collection URI binds pool_id; project_id is native body metadata.
    members = await _read(lambda: list(islice(conn.load_balancer.members(pool_id), 10001)))
    if len(members) > 10000:
        raise HTTPException(502, "관리자 하위 자원 조회 한도를 초과했습니다")
    for member in members:
        _identity(member, owner=owner)
        if _field(member, "pool_id") not in (None, pool_id):
            _not_found()
    return [octavia._member_to_dict(member) for member in members]


@router.get("/loadbalancers/{lb_id}/status")
async def get_admin_lb_status(lb_id: NativeId, conn=Depends(get_admin_os_conn)):
    lb = await _load_balancer(conn, lb_id)
    owner = _identity(lb, lb_id)

    def status():
        response = conn.load_balancer.get(f"/lbaas/loadbalancers/{lb_id}/status")
        response.raise_for_status()
        return response.json().get("statuses", {}).get("loadbalancer")

    tree = await _read(status)
    if not isinstance(tree, dict) or tree.get("id") != lb_id:
        _not_found()
    # A status tree has no owner fields: prove each nested native resource.
    for listener in tree.get("listeners", []):
        if not isinstance(listener, dict) or not listener.get("id"):
            _not_found()
        native = await _read(conn.load_balancer.get_listener, listener.get("id"))
        _identity(native, listener.get("id"), owner)
        _lb_child(native, lb_id, owner)
    pools = list(tree.get("pools", []))
    for listener in tree.get("listeners", []):
        pools.extend(listener.get("pools", []))
    for pool in pools:
        pool_id = pool.get("id")
        if not pool_id:
            _not_found()
        await _pool(conn, lb_id, pool_id, owner)
        for member in pool.get("members", []):
            if not isinstance(member, dict) or not member.get("id"):
                _not_found()
            native = await _read(conn.load_balancer.get_member, member.get("id"), pool_id)
            _identity(native, member.get("id"), owner)
            if _field(native, "pool_id") not in (None, pool_id):
                _not_found()
        monitor = pool.get("healthmonitor")
        if monitor:
            if not isinstance(monitor, dict) or not monitor.get("id"):
                _not_found()
            native = await _read(conn.load_balancer.get_health_monitor, monitor.get("id"))
            _identity(native, monitor.get("id"), owner)
            if {item.get("id") for item in _field(native, "pools") or []} != {pool_id}:
                _not_found()
    return tree


def _trove_body(conn, path: str) -> dict:
    # Relative requests retain the authenticated catalog project's URL and token.
    # Trove's native admin context can load foreign instances by ID; changing the
    # URL project or authenticating as the target tenant is neither needed nor safe.
    response = conn.database.get(path)
    response.raise_for_status()
    body = response.json()
    if not isinstance(body, dict):
        raise ValueError("Invalid Trove response")
    return body


async def _database_instance(conn, instance_id: str):
    body = await _read(_trove_body, conn, f"/mgmt/instances/{instance_id}")
    raw = body.get("instance")
    _identity(raw, instance_id)
    if raw.get("deleted"):
        _not_found()
    return raw


@router.get("/database-instances")
async def list_admin_database_instances(
    conn=Depends(get_admin_os_conn),
    domain_id: str | None = Query(None, min_length=1),
    project_id: str | None = Query(None, min_length=1),
):
    scope = await _read(resolve_scope, conn, domain_id, project_id)
    rows = await _read(trove.list_instances_admin_all_projects, conn)
    for row in rows:
        _identity(row)
    return scope.filter(rows)


@router.get("/database-instances/{instance_id}")
async def get_admin_database_instance(instance_id: NativeId, conn=Depends(get_admin_os_conn)):
    raw = await _database_instance(conn, instance_id)
    return {**trove._dict_from_raw(raw), "project_id": _identity(raw, instance_id)}


async def _database_children(conn, instance_id: str, kind: str):
    parent = await _database_instance(conn, instance_id)
    owner = _identity(parent, instance_id)
    rows = []
    marker = None
    seen = set()
    for _ in range(100):
        path = f"/instances/{instance_id}/{kind}"
        if marker:
            path += f"?marker={quote(marker, safe='')}"
        body = await _read(_trove_body, conn, path)
        batch = body.get(kind)
        if not isinstance(batch, list) or any(not isinstance(row, dict) for row in batch):
            _not_found()
        for row in batch:
            # Databases/users expose only names and are bound by their native
            # parent URI. Backups additionally identify the actual instance.
            if kind != "backups" and (not isinstance(row.get("name"), str) or not row["name"]):
                _not_found()
            if kind == "backups" and (not row.get("id") or row.get("instance_id") != instance_id):
                _not_found()
            if row.get("project_id") not in (None, owner) or row.get("tenant_id") not in (None, owner):
                _not_found()
            if row.get("instance_id") not in (None, instance_id):
                _not_found()
        rows.extend(batch)
        if len(rows) > 10000:
            raise HTTPException(502, "관리자 하위 자원 조회 한도를 초과했습니다")
        links = body.get(f"{kind}_links", body.get("links", []))
        if not isinstance(links, list) or any(not isinstance(link, dict) for link in links):
            _not_found()
        next_links = [link for link in links if link.get("rel") == "next"]
        if not next_links:
            return rows
        if len(next_links) != 1 or not isinstance(next_links[0].get("href"), str):
            _not_found()
        # Trove user markers include name@host (not merely name). Carry only the
        # native marker; never follow the supplied origin, path or other params.
        markers = parse_qs(urlsplit(next_links[0]["href"]).query, keep_blank_values=True).get("marker", [])
        if len(markers) != 1 or not markers[0] or len(markers[0]) > 1024:
            _not_found()
        marker = markers[0]
        if not marker or marker in seen:
            _not_found()
        seen.add(marker)
    raise HTTPException(502, "관리자 하위 자원 조회 한도를 초과했습니다")


@router.get("/database-instances/{instance_id}/databases")
async def get_admin_databases(instance_id: NativeId, conn=Depends(get_admin_os_conn)):
    return await _database_children(conn, instance_id, "databases")


@router.get("/database-instances/{instance_id}/users")
async def get_admin_database_users(instance_id: NativeId, conn=Depends(get_admin_os_conn)):
    rows = await _database_children(conn, instance_id, "users")
    return [
        {"name": row.get("name", ""), "host": row.get("host") or "%", "databases": row.get("databases") or []}
        for row in rows
    ]


@router.get("/database-instances/{instance_id}/backups")
async def get_admin_database_backups(instance_id: NativeId, conn=Depends(get_admin_os_conn)):
    return [trove._backup_to_dict(row) for row in await _database_children(conn, instance_id, "backups")]
