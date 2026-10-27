"""Complete optional-provider inventories and one normal, owner-proven deletion.

Only catalog endpoints are destinations. Pagination consumes tokens, never URLs;
all transports disable redirects, reauthentication and native request replay.
"""

from __future__ import annotations

from copy import copy
from functools import partial
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

from fastapi import HTTPException
from openstack.proxy import Proxy

from app.services import barbican, zun
from app.services import project_deletion as inventory
from app.services.service_proxy import join_version_aware_url

# proxy, collection path/key, detail envelope, catalog aliases, offset pagination
_SPECS = {
    "load_balancers": (
        "load_balancer",
        "/lbaas/loadbalancers",
        "loadbalancers",
        "loadbalancer",
        ("load-balancer",),
        False,
    ),
    "shares": ("shared_file_system", "/shares/detail", "shares", "share", ("sharev2", "share"), True),
    "share_snapshots": ("shared_file_system", "/snapshots/detail", "snapshots", "snapshot", ("sharev2", "share"), True),
    "share_networks": (
        "shared_file_system",
        "/share-networks/detail",
        "share_networks",
        "share_network",
        ("sharev2", "share"),
        True,
    ),
    "security_services": (
        "shared_file_system",
        "/security-services/detail",
        "security_services",
        "security_service",
        ("sharev2", "share"),
        True,
    ),
    "object_containers": ("object_store", "/", "containers", None, ("object-store",), False),
    "secrets": ("key_manager", "/secrets", "secrets", None, ("key-manager",), True),
    "secret_containers": ("key_manager", "/containers", "containers", None, ("key-manager",), True),
    "secret_orders": ("key_manager", "/orders", "orders", None, ("key-manager",), True),
    "database_instances": ("database", "/mgmt/instances", "instances", "instance", ("database",), False),
    "database_backups": ("database", "/backups", "backups", "backup", ("database",), False),
    "database_configurations": ("database", "/configurations", "configurations", "configuration", ("database",), False),
    "containers": ("session", "/v1/containers", "containers", None, ("container",), False),
    "clusters": (
        "container_infrastructure_management",
        "/clusters/detail",
        "clusters",
        None,
        ("container-infra",),
        False,
    ),
    "cluster_templates": (
        "container_infrastructure_management",
        "/clustertemplates",
        "clustertemplates",
        None,
        ("container-infra",),
        False,
    ),
    "stacks": ("orchestration", "/stacks", "stacks", "stack", ("orchestration",), False),
}
OPTIONAL_KINDS = frozenset(_SPECS)
_PRIVATE = frozenset(("secrets", "secret_containers", "secret_orders"))
REQUIRED_PROJECT_SCOPE_KINDS = _PRIVATE | {"object_containers"}
_OWNERS = ("project_id", "tenant_id", "project")


def _safe_proxy(proxy: Any) -> Any:
    transport = copy(proxy)
    kwargs = {"skip_cache": True} if isinstance(proxy, Proxy) else {}
    transport.request = partial(
        transport.request,
        allow_reauth=False,
        connect_retries=0,
        status_code_retries=0,
        redirect=False,
        headers={"Accept": "application/json"},
        **kwargs,
    )
    return transport


def _segment(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value in (".", "..")
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
        or any(char in value for char in "/\\?#%")
    ):
        raise inventory._UnverifiedInventory("resource_identity_unverified")
    return quote(value, safe="")


def _swift_segment(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value in (".", "..")
        or "/" in value
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise inventory._UnverifiedInventory("resource_identity_unverified")
    return quote(value, safe="")


def _id(row: dict, kind: str | None = None) -> str:
    reference = {"secrets": "secret_ref", "secret_containers": "container_ref", "secret_orders": "order_ref"}.get(kind)
    # Completed orders reference the newly generated secret/container as well
    # as themselves. Those output references are not aliases of the order ID.
    keys = ("id", "uuid", reference) if reference else ("id", "uuid")
    present = [row[key] for key in keys if row.get(key) not in (None, "")]
    if not present or not isinstance(present[0], str):
        raise inventory._UnverifiedInventory("resource_identity_unverified")
    identifier = present[0].rsplit("/", 1)[-1] if "://" in present[0] else present[0]
    _segment(identifier)
    # Conflicting identifiers must not select a different object for deletion.
    for key in keys:
        value = row.get(key)
        if (
            value is not None
            and value != ""
            and (not isinstance(value, str) or value.rstrip("/").rsplit("/", 1)[-1] != identifier)
        ):
            raise inventory._UnverifiedInventory("resource_identity_unverified")
    return identifier


def _scope(conn: Any, project_id: str, proxy: Any, *, account: bool = False) -> str:
    inventory._require_project_scope(conn, project_id, proxy, account=account)
    access = conn.session.auth.get_access(conn.session)
    if access.project_id != project_id:
        raise inventory._UnverifiedInventory("project_scope_unverified")
    return project_id


def _checked(response: Any) -> Any:
    response.raise_for_status()
    if not 200 <= response.status_code < 300:
        # requests.raise_for_status does not reject redirects.
        raise inventory._UnverifiedInventory("resource_check_failed")
    return response


def _detail(
    proxy: Any,
    path: str,
    envelope: str | None,
    expected: str,
    *,
    params: dict | None = None,
    kind: str | None = None,
) -> dict:
    body = _checked(proxy.get(path, params=params)).json()
    row = body.get(envelope) if isinstance(body, dict) and envelope else body
    if not isinstance(row, dict) or _id(row, kind) != expected:
        raise inventory._UnverifiedInventory("resource_identity_unverified")
    return row


def _pages(proxy: Any, path: str, key: str, *, params: dict | None = None, offset: bool = False):
    # The existing collector reads tokens from next links without following them.
    # Reject 3xx as well as failures even when a provider returns a JSON body.
    transport = copy(proxy)
    original_get = proxy.get

    def get(*args, **kwargs):
        return _checked(original_get(*args, **kwargs))

    transport.get = get
    yield from inventory._raw_pages(transport, path, key, params=params, offset=offset)


def _swift_rows(proxy: Any):
    marker = None
    seen = set()
    while True:
        params = {"format": "json", "limit": 200}
        if marker is not None:
            params["marker"] = marker
        rows = _checked(proxy.get("/", params=params)).json()
        if not isinstance(rows, list):
            raise inventory._UnverifiedInventory("resource_check_failed")
        if not rows:
            return
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("name"), str):
                raise inventory._UnverifiedInventory("resource_identity_unverified")
            identifier = row["name"]
            _swift_segment(identifier)
            if identifier in seen:
                raise inventory._UnverifiedInventory("resource_check_failed")
            seen.add(identifier)
            yield {"id": identifier, "name": identifier}
        marker = rows[-1]["name"]


def _heat_proxy(conn: Any, project_id: str) -> Any:
    proxy = _safe_proxy(conn.orchestration)
    endpoint = proxy.get_endpoint()
    parsed = urlsplit(endpoint)
    actual = conn.current_project_id
    # Heat's identity paths contain a tenant. Replace only the verified catalog
    # tenant segment, never resolve an arbitrary provider self/next URL.
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or not isinstance(actual, str)
        or parsed.path.rstrip("/").rsplit("/", 1)[-1] != actual
    ):
        raise inventory._UnverifiedInventory("project_scope_unverified")
    base = parsed.path.rstrip("/").rsplit("/", 1)[0]
    proxy.endpoint_override = urlunsplit((parsed.scheme, parsed.netloc, f"{base}/{_segment(project_id)}", "", ""))
    return proxy


def _provider(conn: Any, project_id: str, kind: str):
    if kind not in _SPECS:
        raise HTTPException(422, "unknown_resource_kind")
    proxy_name, path, key, envelope, aliases, offset = _SPECS[kind]
    if not inventory._catalog_types(conn).intersection(aliases):
        return None
    proxy = _heat_proxy(conn, project_id) if kind == "stacks" else _safe_proxy(getattr(conn, proxy_name))
    if proxy_name == "shared_file_system":
        # Snapshot ownership is exposed at 2.17; snapshot management metadata
        # at 2.73. Never silently drop either guard on an older provider.
        proxy.request = partial(proxy.request, microversion="2.73")
    if kind == "containers":
        path = join_version_aware_url(zun._get_zun_endpoint(conn), path)
    if kind == "object_containers" or kind in _PRIVATE:
        _scope(conn, project_id, proxy, account=kind == "object_containers")
    elif not inventory._native_admin(conn):
        if kind != "database_configurations":
            raise inventory._UnverifiedInventory("admin_authority_unverified")
        # The only tenant-only alternative is Trove's documented non-admin
        # configuration index/detail. Its admin context is explicitly global.
        _configuration_owner(conn, project_id, proxy, {})
    return proxy, path, key, envelope, offset


def _configuration_owner(conn: Any, project_id: str, proxy: Any, row: dict) -> str:
    if any(row.get(key) not in (None, "") for key in _OWNERS):
        return inventory._owner(row, _OWNERS, None)
    # Trove's standard admin index AND detail omit tenant_id. A project in the
    # URL cannot prove ownership for an admin: Configurations.load is global.
    # Non-admin Configuration.load is tenant-constrained, so an exact native
    # GET with a verified target token and endpoint is authoritative.
    access = conn.session.auth.get_access(conn.session)
    roles = access.role_names
    if not isinstance(roles, list) or any(not isinstance(role, str) for role in roles):
        raise inventory._UnverifiedInventory("resource_ownership_unverified")
    if any(role.lower() == "admin" for role in roles):
        raise inventory._UnverifiedInventory("resource_ownership_unverified")
    _scope(conn, project_id, proxy)
    endpoint = urlsplit(proxy.get_endpoint())
    if endpoint.path.rstrip("/").rsplit("/", 1)[-1] != project_id:
        raise inventory._UnverifiedInventory("project_scope_unverified")
    return project_id


def _rows(conn: Any, project_id: str, kind: str, provider):
    proxy, path, key, envelope, offset = provider
    if kind == "object_containers":
        yield from _swift_rows(proxy)
        return
    params = {}
    if kind == "load_balancers":
        params["project_id"] = project_id
    elif kind in ("shares", "share_snapshots", "share_networks", "security_services"):
        params["all_tenants"] = True
    elif kind == "database_backups":
        params.update(all_projects=True, project_id=project_id)
    elif kind == "containers":
        params["all_projects"] = True
    elif kind == "stacks":
        params.update(tenant=project_id, show_nested=True, show_hidden=True)
    seen = set()
    for row in _pages(proxy, path, key, params=params, offset=offset):
        identifier = _id(row, kind)
        if identifier in seen:
            raise inventory._UnverifiedInventory("resource_check_failed")
        seen.add(identifier)
        if kind == "database_instances" and row.get("deleted") in (True, 1, "1"):
            continue
        if kind == "database_configurations":
            row = _detail(proxy, f"/configurations/{_segment(identifier)}", envelope, identifier)
            owner = _configuration_owner(conn, project_id, proxy, row)
        else:
            owner = inventory._owner(row, _OWNERS, project_id if kind in _PRIVATE else None)
        if owner == project_id:
            yield row


def _result(status: str, reason: str | None = None, resources: list | None = None) -> dict:
    return {
        "status": status,
        "reason": reason,
        "resources": resources or [],
        "count": len(resources or []) if status == "ok" else None,
    }


def list_resources(conn: Any, project_id: str, kind: str) -> dict:
    """Return only complete safe metadata; an unavailable provider is not empty."""
    try:
        provider = _provider(conn, project_id, kind)
        if provider is None:
            return _result("skipped", "service_not_present")
        resources = []
        for row in _rows(conn, project_id, kind, provider):
            item = {"id": row["id"] if kind == "object_containers" else _id(row, kind)}
            if kind not in _PRIVATE:
                name = row.get("stack_name") if kind == "stacks" else row.get("name")
                if isinstance(name, str):
                    item["name"] = name
            status = row.get("stack_status") if kind == "stacks" else row.get("status")
            if isinstance(status, str):
                item["status"] = status
            resources.append(item)
        return _result("ok", resources=resources)
    except HTTPException:
        raise
    except inventory._UnverifiedInventory as exc:
        return _result("unavailable", exc.reason)
    except Exception:
        return _result("unavailable", "resource_check_failed")


def _assert_unmanaged(kind: str, row: dict) -> None:
    from app.services.project_cleanup import _assert_native_unmanaged

    _assert_native_unmanaged(row)
    if kind in _PRIVATE and barbican._is_system_managed(row.get("name")):
        raise HTTPException(409, "resource_is_system_managed")
    for field in ("metadata", "labels"):
        values = row.get(field)
        if values is not None and not isinstance(values, dict):
            raise inventory._UnverifiedInventory("resource_management_unverified")
        for key in values or {}:
            if isinstance(key, str) and key.startswith(
                ("palimpsest", "drover", "union_", "afterglow.", "afterglow_", "layer_transport")
            ):
                raise HTTPException(409, "resource_is_system_managed")
    tags = row.get("tags")
    if tags is not None and not isinstance(tags, list):
        raise inventory._UnverifiedInventory("resource_management_unverified")
    if any(
        isinstance(tag, str) and tag.startswith(("drover", "palimpsest", "afterglow-managed")) for tag in tags or []
    ):
        raise HTTPException(409, "resource_is_system_managed")
    if kind == "stacks" and row.get("parent"):
        raise HTTPException(409, "resource_is_system_managed")
    if kind == "containers" and row.get("status") not in ("Stopped", "STOPPED", "Created", "CREATED", "Error", "ERROR"):
        raise HTTPException(409, "container_must_be_stopped")


def _assert_stack_not_cluster_managed(conn: Any, project_id: str, stack_id: str) -> None:
    provider = _provider(conn, project_id, "clusters")
    if provider is None:
        return
    # Magnum owns teardown for its top-level Heat stacks. Complete the native
    # project inventory first; a failed page cannot authorize direct deletion.
    clusters = list(_rows(conn, project_id, "clusters", provider))
    for cluster in clusters:
        if "stack_id" not in cluster or (cluster["stack_id"] is not None and not isinstance(cluster["stack_id"], str)):
            raise inventory._UnverifiedInventory("resource_management_unverified")
        if cluster["stack_id"] == stack_id:
            raise HTTPException(409, "resource_is_system_managed")


def _error(exc: Exception) -> HTTPException:
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None) if response is not None else None
    status = status or getattr(exc, "status_code", None) or getattr(exc, "http_status", None)
    if status in (401, 403):
        return HTTPException(403, "resource_operation_denied")
    if status == 404:
        return HTTPException(404, "resource_not_found")
    if status in (400, 409, 412):
        return HTTPException(409, "resource_delete_conflict")
    return HTTPException(502, "resource_provider_failed")


def delete_resource(conn: Any, project_id: str, kind: str, resource_id: str) -> None:
    """Prove fresh ownership, then submit exactly one ordinary native DELETE."""
    try:
        identifier = _swift_segment(resource_id) if kind == "object_containers" else _segment(resource_id)
        provider = _provider(conn, project_id, kind)
        if provider is None:
            raise HTTPException(503, "service_not_present")
        proxy, collection, _, envelope, _ = provider
        if kind == "object_containers":
            # Swift HEAD is exact within the verified AUTH account. Never empty
            # the container or invoke the existing cascading container helper.
            path = f"/{identifier}"
            _checked(proxy.head(path))
            _checked(proxy.delete(path))
            return
        membership = None
        if kind in _PRIVATE or kind == "stacks":
            # Barbican detail may be ACL-shared. Only fresh project index
            # membership is ownership proof. Heat's detail omits project too.
            rows = list(_rows(conn, project_id, kind, provider))
            membership = next((row for row in rows if _id(row, kind) == resource_id), None)
            if membership is None:
                raise HTTPException(404, "resource_not_found")
        if kind == "stacks":
            name = membership.get("stack_name")
            path = f"/stacks/{_segment(name)}/{identifier}"
        elif kind == "containers":
            path = f"{collection}/{identifier}"
        else:
            base = collection.removesuffix("/detail")
            path = f"{base}/{identifier}"
        params = {"all_projects": True} if kind == "containers" else None
        row = _detail(proxy, path, envelope, resource_id, params=params, kind=kind)
        if kind == "database_configurations":
            owner = _configuration_owner(conn, project_id, proxy, row)
        else:
            owner = inventory._owner(row, _OWNERS, project_id if membership is not None else None)
        if owner != project_id:
            raise HTTPException(403, "resource_project_mismatch")
        if kind == "stacks" and row.get("stack_name") != membership.get("stack_name"):
            raise inventory._UnverifiedInventory("resource_identity_unverified")
        _assert_unmanaged(kind, row)
        if kind == "stacks":
            _assert_stack_not_cluster_managed(conn, project_id, resource_id)
        if kind == "share_snapshots":
            share_id = row.get("share_id")
            parent = _detail(proxy, f"/shares/{_segment(share_id)}", "share", share_id)
            if inventory._owner(parent, _OWNERS, None) != project_id:
                raise HTTPException(403, "resource_project_mismatch")
            _assert_unmanaged("shares", parent)
        if kind == "database_instances":
            path = f"/instances/{identifier}"
        _checked(proxy.delete(path, params=params))
    except HTTPException:
        raise
    except inventory._UnverifiedInventory as exc:
        raise HTTPException(503, exc.reason) from None
    except Exception as exc:
        raise _error(exc) from None
