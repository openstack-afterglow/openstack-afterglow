"""Read-only, caller-scoped consumer inventory. Never use administrative lists.

SDK generators paginate natively. REST-only services retain their native list
paths and continuation links; extracted services retain their browser gates.
Only display metadata is projected, never provider payloads or credentials.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
from urllib.parse import parse_qsl, quote, urlsplit

from fastapi import HTTPException, Request

from app.config import get_settings
from app.services import keystone, manila, project_service, service_proxy, swift, zun
from app.services.cache import cached_call, ttl_normal
from app.services.palimpsest_authorization import authorize_current_package_request
from app.services.service_authorization import authorize_service_request
from app.services.service_permissions import require_service_permission

# category: (existing consumer route, optional deployment gate)
CATALOG = {
    "instances": ("/dashboard/compute/instances", None),
    "volumes": ("/dashboard/volumes", None),
    "floating_ips": ("/dashboard/network/floating-ips", None),
    "networks": ("/dashboard/network/networks", None),
    "subnets": ("/dashboard/network/networks", None),
    "routers": ("/dashboard/network/routers", None),
    "security_groups": ("/dashboard/network/security-groups", None),
    "load_balancers": ("/dashboard/network/loadbalancers", None),
    "images": ("/dashboard/compute/images", None),
    "keypairs": ("/dashboard/compute/keypairs", None),
    "database_instances": ("/dashboard/database/instances", "trove"),
    "database_backups": ("/dashboard/database/backups", "trove"),
    "k3s_clusters": ("/dashboard/drover", "k3s"),
    "waygate_gateways": ("/dashboard/network/waygate", "waygate"),
    "containers": ("/dashboard/containers/instances", "zun"),
    "magnum_clusters": ("/dashboard/containers/clusters", "magnum"),
    "shares": ("/dashboard/file-storage", "manila"),
    "share_snapshots": ("/dashboard/file-storage/snapshots", "manila"),
    "share_networks": ("/dashboard/file-storage/networks", "manila"),
    "security_services": ("/dashboard/file-storage/security-services", "manila"),
    "buckets": ("/dashboard/object-storage/buckets", "swift"),
    "volume_snapshots": ("/dashboard/volumes/snapshots", None),
    "volume_backups": ("/dashboard/volumes/backups", None),
    "packages": ("/palimpsest/packages", "palimpsest"),
    "secrets": ("/dashboard/secrets", "barbican"),
}
REMOTE = {"k3s_clusters": ("drover", "/v1/clusters"), "waygate_gateways": ("waygate", "/v1/servers")}
DETAIL = {
    "instances",
    "volumes",
    "networks",
    "routers",
    "load_balancers",
    "database_instances",
    "k3s_clusters",
    "containers",
    "magnum_clusters",
    "shares",
    "buckets",
}


def unavailable(state: str, error: str) -> dict:
    return {"state": state, "count": None, "items": [], "error": error}


def failure(exc: Exception) -> dict:
    status = getattr(exc, "status_code", None) or getattr(exc, "http_status", None)
    response = getattr(exc, "response", None)
    if response is not None:
        status = getattr(response, "status_code", status)
    if isinstance(exc, PermissionError) or status in (401, 403):
        return unavailable("denied", "inventory_denied")
    return unavailable("failed", "inventory_unavailable")


def field(row, *names):
    for name in names:
        value = row.get(name) if isinstance(row, dict) else getattr(row, name, None)
        if value is not None and value != "":
            return value
    return None


def number(value):
    return (
        value
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0
        else None
    )


def scoped_connection(token: str, user_id: str, project_id: str):
    conn = keystone.get_openstack_connection(token, project_id)
    try:
        access = conn.session.auth.get_access(conn.session)
        if access.user_id != user_id or access.project_id != project_id:
            raise PermissionError("Scoped identity mismatch")
        identity_domain_id = getattr(access, "user_domain_id", None)
        domain_id = getattr(access, "project_domain_id", None)
        if (
            not isinstance(identity_domain_id, str)
            or not identity_domain_id
            or not isinstance(domain_id, str)
            or not domain_id
        ):
            raise PermissionError("Scoped domain identity is unavailable")
        from app.services.domain_projects import assert_project_membership
        from app.services.domain_scope import domain_context

        context = domain_context(user_id, domain_id)
        if context["identity_domain_id"] != identity_domain_id:
            raise PermissionError("Scoped identity domain mismatch")
        assert_project_membership(user_id, project_id)
        scoped_token = conn.session.get_token()
        if not isinstance(scoped_token, str) or not scoped_token:
            raise PermissionError("Scoped credential unavailable")
        # REST wrappers must use the issued project credential, not the source
        # token plus a different project header (not equivalent authorization).
        conn._afterglow_token = scoped_token
        conn._afterglow_user_id = user_id
        conn._afterglow_project_id = project_id
        conn._afterglow_domain_id = domain_id
        conn._afterglow_identity_domain_id = identity_domain_id
        return conn, scoped_token
    except Exception:
        conn.close()
        raise


def child_request(request: Request, info: dict) -> Request:
    # Do not forward a browser JWT or the source project's credential/header.
    headers = [
        (key, value)
        for key, value in request.scope.get("headers", [])
        if key.lower() not in {b"authorization", b"x-auth-token", b"x-project-id"}
    ]
    headers.extend([(b"x-auth-token", info["token"].encode()), (b"x-project-id", info["project_id"].encode())])
    scope = {**request.scope, "method": "GET", "headers": headers, "query_string": b"", "state": {}}
    child = Request(scope)
    child.state.token_info = info
    principal = {**info, "is_system_admin": False}
    identity = (info["user_id"], info["project_id"], False)
    child.state.current_service_principal = (identity, principal)
    return child


def _relative_next(href: str, endpoint: str, path: str) -> str:
    if not isinstance(href, str) or not href:
        raise ValueError("Invalid continuation")
    parsed = urlsplit(href)
    base = urlsplit(endpoint)
    if parsed.fragment or parsed.username or parsed.password or (parsed.scheme and not parsed.netloc):
        raise ValueError("Invalid continuation")
    # Continuations may change pagination only, never tenant/admin filters.
    params = parse_qsl(parsed.query, keep_blank_values=True)
    if any(key not in {"marker", "limit", "offset", "page", "sort_key", "sort_dir"} for key, _ in params):
        raise ValueError("Unsafe continuation query")
    if len({key for key, _ in params}) != len(params):
        raise ValueError("Ambiguous continuation query")
    collection = urlsplit(path).path
    absolute_collection = (
        urlsplit(service_proxy.join_version_aware_url(endpoint, collection)).path if endpoint else collection
    )
    if parsed.netloc and (parsed.scheme, parsed.netloc) != (base.scheme, base.netloc):
        raise ValueError("Foreign continuation")
    if parsed.path and parsed.path not in {collection, absolute_collection}:
        raise ValueError("Continuation changed collection")
    return collection + ("?" + parsed.query if parsed.query else "")


def rest_list(get, path: str, key: str, endpoint: str = "") -> list:
    rows, seen = [], set()
    while path:
        if path in seen:
            raise ValueError("Cyclic continuation")
        seen.add(path)
        response = get(path)
        if hasattr(response, "raise_for_status"):
            response.raise_for_status()
            payload = response.json()
        else:
            payload = response
        if not isinstance(payload, dict) or not isinstance(payload.get(key), list):
            raise ValueError("Invalid inventory collection")
        rows.extend(payload[key])
        links = payload.get(key + "_links", payload.get("links", []))
        if not isinstance(links, list):
            raise ValueError("Invalid continuation links")
        next_links = [link.get("href") for link in links if isinstance(link, dict) and link.get("rel") == "next"]
        # Zun's native collection API also emits a top-level next URL.
        native_next = payload.get("next")
        if native_next is not None:
            if not isinstance(native_next, str) or not native_next:
                raise ValueError("Invalid native continuation")
            if not next_links or next_links != [native_next]:
                next_links.append(native_next)
        if len(next_links) > 1:
            raise ValueError("Ambiguous continuation")
        path = _relative_next(next_links[0], endpoint, path) if next_links else ""
    return rows


def native_rows(conn, category: str, project_id: str, user_id: str) -> list:
    """Existing native consumer collection primitives, without lossy wrappers.

    Some UI wrappers swallow errors or remove ownership. Inventory deliberately
    uses the same underlying collection API instead of turning their [] fallback
    into a successful zero or trusting a discarded owner field.
    """
    if category == "instances":
        return list(conn.compute.servers(details=True, user_id=user_id))
    if category == "volumes":
        return list(conn.block_storage.volumes(details=True))
    if category in {"volume_snapshots", "volume_backups"}:
        method = conn.block_storage.snapshots if category == "volume_snapshots" else conn.block_storage.backups
        return list(method(details=True))
    network_methods = {
        "floating_ips": "ips",
        "networks": "networks",
        "subnets": "subnets",
        "routers": "routers",
        "security_groups": "security_groups",
    }
    if category in network_methods:
        return list(getattr(conn.network, network_methods[category])(project_id=project_id))
    if category == "load_balancers":
        return list(conn.load_balancer.load_balancers(project_id=project_id))
    if category == "images":
        return list(conn.image.images(owner=project_id))
    if category == "keypairs":
        return list(conn.compute.keypairs(user_id=user_id))
    if category in {"database_instances", "database_backups"}:
        key = "instances" if category == "database_instances" else "backups"
        endpoint = conn.database.get_endpoint()
        if urlsplit(endpoint).path.rstrip("/").rsplit("/", 1)[-1] != project_id:
            raise PermissionError("Trove endpoint scope mismatch")
        return rest_list(conn.database.get, "/" + key, key, endpoint)
    if category in {"shares", "share_snapshots", "share_networks", "security_services"}:
        client = manila.get_client(conn)
        key, path = {
            "shares": ("shares", "/shares/detail"),
            "share_snapshots": ("snapshots", "/snapshots/detail"),
            "share_networks": ("share_networks", "/share-networks/detail"),
            "security_services": ("security_services", "/security-services/detail"),
        }[category]
        return rest_list(client.get, path, key, client._url("/").rstrip("/"))
    if category == "magnum_clusters":
        return list(conn.container_infrastructure_management.clusters())
    if category == "containers":
        endpoint = zun._get_zun_endpoint(conn)

        def get(path):
            return conn.session.get(service_proxy.join_version_aware_url(endpoint, path))

        return rest_list(get, "/v1/containers", "containers", endpoint)
    if category == "buckets":
        swift._apply_endpoint_override(conn)
        # Swift's account endpoint (AUTH_<project>) is project-bound and does not
        # return an owner on each container. No EC2 credential issuance is needed.
        endpoint = conn.object_store.get_endpoint().rstrip("/")
        if urlsplit(endpoint).path.rsplit("/", 1)[-1] != "AUTH_" + project_id:
            raise PermissionError("Swift account scope mismatch")
        return [
            row
            for row in conn.object_store.containers()
            if not str(field(row, "name") or "").endswith(("_segments", "-quarantine", "-trash"))
        ]
    if category == "secrets":
        return list(conn.key_manager.secrets())
    raise ValueError("Unknown inventory collection")


def project_items(rows: list, category: str, project_id: str, project_name: str, user_id: str) -> list[dict]:
    result, seen = [], set()
    for row in rows:
        if category == "database_instances" and field(row, "deleted"):
            continue
        owner = field(
            row, "project_id", "tenant_id", "os-vol-tenant-attr:tenant_id", "os-extended-snapshot-attributes:project_id"
        )
        if category == "images":
            owner = field(row, "owner", "project_id")
        # These native consumer lists can omit ownership fields. Their checked
        # project token/account is authoritative only when no owner is returned;
        # an explicitly foreign owner is always excluded below.
        scope_only = category in {
            "database_instances",
            "database_backups",
            "secrets",
            "buckets",
            "keypairs",
            "volumes",
            "volume_snapshots",
            "volume_backups",
            "magnum_clusters",
            "security_services",
        }
        if owner is not None and owner != project_id:
            continue
        if owner is None and not scope_only:
            raise ValueError("Provider omitted project ownership")
        owner_scope = "project"
        owner_id = project_id
        creator = field(row, "user_id")
        if category in {"instances", "volumes", "keypairs"}:
            if creator is not None and creator != user_id:
                continue
            if creator is not None or category == "keypairs":
                owner_scope, owner_id = "user", user_id
        ident = (
            field(row, "package_id", "id", "uuid", "name")
            if category == "packages"
            else field(row, "id", "uuid", "name")
        )
        if category == "secrets":
            ident = str(field(row, "secret_ref", "id") or "").rsplit("/", 1)[-1]
        if not isinstance(ident, str) or not ident:
            raise ValueError("Provider omitted resource identity")
        if ident in seen:
            continue
        seen.add(ident)
        href = CATALOG[category][0]
        if category in DETAIL:
            href += "/" + quote(ident, safe="")
        if category == "subnets":
            network_id = field(row, "network_id")
            if not isinstance(network_id, str) or not network_id:
                raise ValueError("Provider omitted owning network")
            href += "/" + quote(network_id, safe="")
        item = {
            "id": ident,
            "name": str(field(row, "name", "floating_ip_address") or ident),
            "status": str(field(row, "status", "provisioning_status", "state") or ""),
            "project_id": project_id,
            "project_name": project_name,
            "owner_scope": owner_scope,
            "owner_id": owner_id,
            "href": href,
        }
        if category == "instances":
            flavor = field(row, "flavor") or {}
            item.update(
                vcpus=number(field(flavor, "vcpus")),
                ram_mb=number(field(flavor, "ram")),
                flavor_name=field(flavor, "original_name", "name") or "",
            )
        if category == "volumes":
            item["size"] = number(field(row, "size"))
        result.append(item)
    return result


async def package_context(request: Request, info: dict) -> dict:
    # Native capability and namespace are current authority, including cache hits.
    from app.api.palimpsest.packages import checked_context

    response = await service_proxy.package_member_request(request, "/v1/projects/current")
    if response.status_code >= 400:
        raise HTTPException(response.status_code, "Package context unavailable")
    context = checked_context(response, info)
    if context["capabilities"]["packages_read"] is not True:
        raise PermissionError("Native package inventory denied")
    return context


async def package_rows(request: Request, info: dict, context: dict) -> list:
    # Metadata only: no package key, registration, download or admin override.
    from app.api.palimpsest.packages import checked_payload

    namespace = context["namespace"]
    if namespace is None:
        # Native explicit absence of a namespace means no packages can exist.
        return []
    rows, seen, cursor = [], set(), None
    while True:
        query = {"limit": "100"}
        if cursor is not None:
            query["cursor"] = cursor
        response = await service_proxy.package_member_request(
            request, f"/v1/projects/{namespace}/packages", query=query
        )
        if response.status_code >= 400:
            raise HTTPException(response.status_code, "Package inventory unavailable")
        payload = checked_payload(response, info, namespace)
        if not isinstance(payload.get("items"), list):
            raise ValueError("Invalid package collection")
        rows.extend(payload["items"])
        cursor = payload.get("next_cursor")
        if cursor is None:
            return rows
        if not isinstance(cursor, str) or not cursor or cursor in seen:
            raise ValueError("Invalid package continuation")
        seen.add(cursor)


def usage(resources: dict) -> dict:
    def total(category, key):
        resource = resources[category]
        if resource["state"] != "ready" or any(
            item["owner_scope"] != "user" or item.get(key) is None for item in resource["items"]
        ):
            return None
        return sum(item[key] for item in resource["items"])

    # Nova infrastructure and logical Trove/Drover/Waygate inventories overlap;
    # only caller-owned Nova and Cinder metadata contribute to these metrics.
    return {
        "vcpus": total("instances", "vcpus"),
        "ram_mb": total("instances", "ram_mb"),
        "storage_gb": total("volumes", "size"),
    }


async def query_project(request: Request, token: str, user_id: str, project: dict, cm) -> dict:
    project_id, project_name = project["id"], project["name"]
    settings = get_settings()
    resources = {}
    for category, (_, gate) in CATALOG.items():
        if gate is not None and not getattr(settings, f"service_{gate}_enabled"):
            resources[category] = unavailable("disabled", "service_disabled")
    conn = None
    try:
        # Always fresh, before cache: current membership/role-ID graph and a real
        # Keystone rescope. Never rely on the caller's verified system-admin bit.
        access = await project_service.get_project_access(project_id, user_id)
        if not access["roles"]:
            raise PermissionError("Current project membership required")
        conn, scoped_token = await asyncio.to_thread(scoped_connection, token, user_id, project_id)
        info = {
            "user_id": user_id,
            "project_id": project_id,
            "connection_project_id": project_id,
            "token": scoped_token,
            "roles": access["roles"],
            "is_system_admin": False,
            "domain_id": conn._afterglow_domain_id,
            "identity_domain_id": conn._afterglow_identity_domain_id,
        }
        child = child_request(request, info)
        fingerprint = hashlib.sha256(
            json.dumps(
                [token, user_id, project_id, project_name, sorted(access["roles"])], separators=(",", ":")
            ).encode()
        ).hexdigest()

        async def category_result(category):
            if category in resources:
                return category, resources[category]
            try:
                cache_fingerprint = fingerprint
                if category in REMOTE:
                    service, path = REMOTE[category]
                    await authorize_service_request(service, child, path)
                elif category == "packages":
                    await authorize_current_package_request(child, "/v1/projects/current", info)
                    require_service_permission(info, "palimpsest-inventory_reader")
                    context = await package_context(child, info)
                    cache_fingerprint = hashlib.sha256(
                        json.dumps([fingerprint, context["namespace"]], separators=(",", ":")).encode()
                    ).hexdigest()

                async def fetch():
                    if category in REMOTE:
                        service, path = REMOTE[category]
                        # Full unpaginated native arrays; no invented cursor API.
                        rows = await service_proxy.get_json(service, child, path)
                        if not isinstance(rows, list):
                            raise ValueError("Invalid native collection")
                    elif category == "packages":
                        rows = await package_rows(child, info, context)
                    else:
                        rows = await asyncio.to_thread(native_rows, conn, category, project_id, user_id)
                    return project_items(rows, category, project_id, project_name, user_id)

                items = await cached_call(
                    f"afterglow:user-inventory:{cache_fingerprint}:{category}",
                    ttl_normal(),
                    fetch,
                    enabled=cm.enabled,
                    refresh=cm.refresh,
                )
                return category, {"state": "ready", "count": len(items), "items": items}
            except Exception as exc:
                return category, failure(exc)

        resources.update(await asyncio.gather(*(category_result(category) for category in CATALOG)))
    except Exception as exc:
        state = failure(exc)
        resources.update({category: dict(state) for category in CATALOG if category not in resources})
    finally:
        if conn is not None:
            await asyncio.to_thread(conn.close)
    return {"project_id": project_id, "project_name": project_name, "resources": resources, "usage": usage(resources)}


def totals(projects: list[dict]) -> dict:
    resources = {}
    settings = get_settings()
    for category in CATALOG:
        values = [project["resources"][category] for project in projects]
        states = {value["state"] for value in values}
        gate = CATALOG[category][1]
        if not values and gate is not None and not getattr(settings, f"service_{gate}_enabled"):
            states = {"disabled"}
        known = sum(value["count"] for value in values if value["state"] == "ready")
        if category == "keypairs":
            # Nova keypairs are user-global. project_id is the token visibility
            # context, not ownership; do not multiply totals by memberships.
            known = len(
                {
                    (item["owner_id"], item["name"])
                    for value in values
                    if value["state"] == "ready"
                    for item in value["items"]
                }
            )
        state = "ready" if not states else next(iter(states)) if len(states) == 1 else "partial"
        resources[category] = {"count": known if state == "ready" else None, "known_count": known, "state": state}
    metrics = {}
    for metric in ("vcpus", "ram_mb", "storage_gb"):
        values = [project["usage"][metric] for project in projects]
        metrics[metric] = None if any(value is None for value in values) else sum(values)
    return {"resources": resources, "usage": metrics}
