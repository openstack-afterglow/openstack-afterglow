"""Fresh, fail-closed OpenStack inventory used only to guard project deletion.

No quota usage, cached UI lists, service passwords, or resource cleanup belongs
here. Exhaust each provider iterator: a later-page failure invalidates the whole
kind rather than turning a partial result into an empty-project assertion.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, urlparse

from app.services import zun
from app.services.service_proxy import join_version_aware_url

_PAGE_SIZE = 200
_SAMPLE_LIMIT = 5
_OWNER_KEYS = ("project_id", "tenant_id")


class _UnverifiedInventory(Exception):
    def __init__(self, reason: str):
        self.reason = reason


def _value(resource: Any, key: str) -> Any:
    if isinstance(resource, dict):
        return resource.get(key)
    return getattr(resource, key, None)


def _identity(resource: Any) -> str:
    for key in ("id", "uuid", "secret_ref", "container_ref", "order_ref", "name"):
        value = _value(resource, key)
        if isinstance(value, str) and value:
            # Barbican identifiers can be references; never expose endpoint URLs.
            return value.rsplit("/", 1)[-1] if "://" in value else value
    raise _UnverifiedInventory("resource_ownership_unverified")


def _owner(resource: Any, keys: tuple[str, ...], scoped_project: str | None) -> str:
    owners = set()
    for key in keys:
        value = _value(resource, key)
        if value is None or value == "":
            continue
        if not isinstance(value, str):
            raise _UnverifiedInventory("resource_ownership_unverified")
        owners.add(value)
    if len(owners) > 1 or (not owners and scoped_project is None):
        raise _UnverifiedInventory("resource_ownership_unverified")
    return next(iter(owners)) if owners else scoped_project


def _entry(kind: str, service: str, status: str, reason: str | None = None) -> dict:
    return {
        "kind": kind,
        "service": service,
        "status": status,
        "count": 0 if status == "ok" else None,
        "samples": [],
        "reason": reason,
    }


def _collect(
    kind: str,
    service: str,
    project_id: str,
    read: Callable[[], Iterable],
    *,
    owners: tuple[str, ...] = _OWNER_KEYS,
    scoped_project: str | None = None,
) -> dict:
    result = _entry(kind, service, "ok")
    seen = set()
    default_group_seen = False
    try:
        for resource in read():
            identifier = _identity(resource)
            if identifier in seen:
                raise _UnverifiedInventory("resource_check_failed")
            seen.add(identifier)
            if _owner(resource, owners, scoped_project) != project_id:
                continue
            # The public API identifies the automatic group by name, not the
            # database is_default bit. Multiple owned groups named default are
            # ambiguous and must not all disappear from this inventory.
            if kind == "security_groups" and _value(resource, "name") == "default":
                if default_group_seen:
                    raise _UnverifiedInventory("resource_ownership_unverified")
                default_group_seen = True
                continue
            result["count"] += 1
            if len(result["samples"]) < _SAMPLE_LIMIT:
                sample = {"id": identifier[:200]}
                for key in ("name", "status"):
                    value = _value(resource, key)
                    if isinstance(value, str) and value:
                        sample[key] = value[:200]
                result["samples"].append(sample)
    except _UnverifiedInventory as exc:
        return _entry(kind, service, "unavailable", exc.reason)
    except Exception:
        # Exception messages can contain tokens, URLs, or provider payloads.
        return _entry(kind, service, "unavailable", "resource_check_failed")
    return result


def _catalog_types(conn: Any) -> set[str]:
    catalog = conn.session.auth.get_access(conn.session).service_catalog.catalog
    if not isinstance(catalog, list):
        raise _UnverifiedInventory("service_catalog_unavailable")
    services = set()
    for item in catalog:
        if not isinstance(item, dict) or not isinstance(item.get("type"), str) or not item["type"]:
            raise _UnverifiedInventory("service_catalog_unavailable")
        # A present service without usable endpoints is not an absent service.
        if not isinstance(item.get("endpoints"), list):
            raise _UnverifiedInventory("service_catalog_unavailable")
        services.add(item["type"])
    return services


def _require_project_scope(conn: Any, project_id: str, proxy: Any, *, account: bool = False) -> str:
    # Use the token's actual SDK scope, not merely Afterglow's request attribute.
    if conn.current_project_id != project_id:
        raise _UnverifiedInventory("project_scope_unverified")
    if account:
        endpoint = proxy.get_endpoint()
        expected = f"AUTH_{project_id}"
        if not isinstance(endpoint, str) or urlparse(endpoint).path.rstrip("/").rsplit("/", 1)[-1] != expected:
            raise _UnverifiedInventory("project_scope_unverified")
    return project_id


def _raw_pages(
    proxy: Any,
    path: str,
    key: str,
    *,
    params: dict | None = None,
    offset: bool = False,
    microversion: str | None = None,
) -> Iterable[dict]:
    """Read native paginated APIs not faithfully represented by SDK mappings.

    Nova server groups and Barbican/Manila use offset pagination. In particular,
    SDK ServerGroup does not map offset, and ShareSnapshot does not map the
    all_tenants filter. Do not pass those through SDK client-side filtering.
    Keep requests on the original proxy/path; only adopt pagination tokens from
    next links, never send authentication to a provider-supplied next URL.
    """
    query = dict(params or {})
    query["limit"] = _PAGE_SIZE
    if offset:
        query["offset"] = 0
    while True:
        kwargs = {"params": query.copy()}
        if microversion:
            kwargs["microversion"] = microversion
        response = proxy.get(path, **kwargs)
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict) or not isinstance(body.get(key), list):
            raise _UnverifiedInventory("resource_check_failed")
        rows = body[key]
        if not rows:
            return
        for row in rows:
            if not isinstance(row, dict):
                raise _UnverifiedInventory("resource_check_failed")
            yield row
        pagination = "offset" if offset else "marker"
        token = None
        links = body.get(f"{key}_links", body.get("links", []))
        next_link = body.get("next")
        if isinstance(links, list):
            for link in links:
                if isinstance(link, dict) and link.get("rel") == "next":
                    next_link = link.get("href")
        if next_link:
            if not isinstance(next_link, str):
                raise _UnverifiedInventory("resource_check_failed")
            values = parse_qs(urlparse(next_link).query).get(pagination)
            if not values or len(values) != 1:
                raise _UnverifiedInventory("resource_check_failed")
            token = values[0]
        if token is None:
            token = query["offset"] + len(rows) if offset else _identity(rows[-1])
        if str(query.get(pagination, "")) == str(token):
            raise _UnverifiedInventory("resource_check_failed")
        if offset:
            token = int(token)
        query[pagination] = token


def _native_admin(conn: Any) -> bool:
    # Afterglow's system-admin flag comes from a Keystone assignment, while the
    # providers authorize this project-scoped token. Without a native admin
    # context, Cinder/Neutron/Glance/Heat can shrink cross-project lists to the
    # caller's view and still return HTTP 200, which must never prove emptiness.
    try:
        access = conn.session.auth.get_access(conn.session)
        roles = access.role_names
        return (
            isinstance(roles, list)
            and "admin" in {role.lower() for role in roles if isinstance(role, str)}
            and access.is_admin_project is True
        )
    except Exception:
        return False


def inspect_project_resources(conn: Any, project_id: str) -> dict:
    """Collect complete owned-resource counts, isolating every kind's failure."""
    resources = []
    authorized = _native_admin(conn)

    def add(kind: str, service: str, read: Callable, **kwargs: Any) -> None:
        if authorized:
            resources.append(_collect(kind, service, project_id, read, **kwargs))
        else:
            resources.append(_entry(kind, service, "unavailable", "admin_authority_unverified"))

    add("instances", "compute", lambda: conn.compute.servers(details=True, all_projects=True, limit=_PAGE_SIZE))
    add(
        "server_groups",
        "compute",
        lambda: _raw_pages(
            conn.compute,
            "/os-server-groups",
            "server_groups",
            params={"all_projects": True},
            offset=True,
            microversion="2.13",
        ),
    )
    for kind, method, alias in (
        ("volumes", "volumes", "os-vol-tenant-attr:tenant_id"),
        ("volume_snapshots", "snapshots", "os-extended-snapshot-attributes:project_id"),
        ("volume_backups", "backups", "os-backup-project-attr:project_id"),
    ):
        add(
            kind,
            "volume",
            lambda method=method: getattr(conn.block_storage, method)(
                details=True,
                all_projects=True,
                limit=_PAGE_SIZE,
            ),
            owners=(*_OWNER_KEYS, alias),
        )
    for kind, method in (
        ("networks", "networks"),
        ("subnets", "subnets"),
        ("routers", "routers"),
        ("ports", "ports"),
        ("floating_ips", "ips"),
        ("security_groups", "security_groups"),
    ):
        add(
            kind,
            "network",
            lambda method=method: getattr(conn.network, method)(project_id=project_id, limit=_PAGE_SIZE),
        )

    def images() -> Iterable:
        # Glance's default list excludes hidden/community images and restricts
        # shared membership. Both hidden partitions must be fully inspected.
        for hidden in (False, True):
            yield from conn.image.images(
                owner=project_id,
                visibility="all",
                member_status="all",
                is_hidden=hidden,
                limit=_PAGE_SIZE,
            )

    add("images", "image", images, owners=("owner", "owner_id"))

    try:
        catalog = _catalog_types(conn)
    except Exception:
        catalog = None

    def optional(kind: str, service: str, aliases: tuple[str, ...], read: Callable, **kwargs: Any) -> None:
        if not authorized:
            resources.append(_entry(kind, service, "unavailable", "admin_authority_unverified"))
        elif catalog is None:
            resources.append(_entry(kind, service, "unavailable", "service_catalog_unavailable"))
        elif not catalog.intersection(aliases):
            resources.append(_entry(kind, service, "skipped", "service_not_present"))
        else:
            add(kind, service, read, **kwargs)

    def scoped_raw(
        proxy_name: str,
        path: str,
        key: str,
        *,
        offset: bool = False,
        params: dict | None = None,
    ) -> Iterable:
        proxy = getattr(conn, proxy_name)
        _require_project_scope(conn, project_id, proxy)
        return _raw_pages(proxy, path, key, offset=offset, params=params)

    optional(
        "load_balancers",
        "load_balancer",
        ("load-balancer",),
        lambda: conn.load_balancer.load_balancers(project_id=project_id, limit=_PAGE_SIZE),
    )
    for kind, path, key in (
        ("shares", "/shares/detail", "shares"),
        ("share_snapshots", "/snapshots/detail", "snapshots"),
        ("share_networks", "/share-networks/detail", "share_networks"),
        ("security_services", "/security-services/detail", "security_services"),
    ):
        optional(
            kind,
            "share",
            ("sharev2", "share"),
            lambda path=path, key=key: _raw_pages(
                conn.shared_file_system,
                path,
                key,
                params={"all_tenants": True},
                offset=True,
            ),
        )

    def object_containers() -> Iterable:
        _require_project_scope(conn, project_id, conn.object_store, account=True)
        # Include hidden segment/quarantine/trash containers: they are real allocations.
        return conn.object_store.containers(limit=_PAGE_SIZE)

    optional("object_containers", "object_store", ("object-store",), object_containers, scoped_project=project_id)
    for kind, key in (("secrets", "secrets"), ("secret_containers", "containers"), ("secret_orders", "orders")):
        optional(
            kind,
            "key_manager",
            ("key-manager",),
            lambda key=key: scoped_raw(
                "key_manager",
                f"/{key}",
                key,
                offset=True,
            ),
            scoped_project=project_id,
        )
    optional(
        "database_instances",
        "database",
        ("database",),
        lambda: (
            row
            for row in _raw_pages(conn.database, "/mgmt/instances", "instances")
            if row.get("deleted") not in (True, 1, "1")
        ),
    )
    optional(
        "database_backups",
        "database",
        ("database",),
        lambda: _raw_pages(
            conn.database,
            "/backups",
            "backups",
            params={"all_projects": True, "project_id": project_id},
        ),
    )
    # Trove lists every configuration to admins, but its list view does not
    # expose owners. Such rows remain unverified, even for a target token.
    optional(
        "database_configurations",
        "database",
        ("database",),
        lambda: _raw_pages(conn.database, "/configurations", "configurations"),
    )
    optional(
        "containers",
        "container",
        ("container",),
        lambda: _raw_pages(
            conn.session,
            join_version_aware_url(zun._get_zun_endpoint(conn), "/v1/containers"),
            "containers",
            params={"all_projects": True},
        ),
    )
    # Magnum admin lists span every project. The compact cluster list omits
    # project_id; detail preserves it.
    optional(
        "clusters",
        "container_infra",
        ("container-infra",),
        lambda: _raw_pages(conn.container_infrastructure_management, "/clusters/detail", "clusters"),
    )
    optional(
        "cluster_templates",
        "container_infra",
        ("container-infra",),
        lambda: _raw_pages(conn.container_infrastructure_management, "/clustertemplates", "clustertemplates"),
    )
    # Heat's global_tenant listing is deny_everybody by default. Its ordinary
    # index spans tenants for an admin context and then exposes `project`.
    optional(
        "stacks",
        "orchestration",
        ("orchestration",),
        lambda: _raw_pages(
            conn.orchestration,
            "/stacks",
            "stacks",
            params={"tenant": project_id, "show_nested": True, "show_hidden": True},
        ),
        owners=(*_OWNER_KEYS, "project"),
    )
    return {
        "project_id": project_id,
        "checked_at": datetime.now(UTC).isoformat(),
        "can_delete": all(
            item["status"] == "skipped" or (item["status"] == "ok" and item["count"] == 0) for item in resources
        ),
        "resources": resources,
    }
