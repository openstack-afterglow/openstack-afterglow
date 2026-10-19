"""Read-only whole-domain monitoring for verified system administrators.

The native Keystone directory is the only source of domain membership: users and
projects are listed by exact domain and re-checked by returned ``domain_id``.
Resources are attributed only by an explicit native owner in that project set.
Rows without an owner, unsupported cross-project service APIs, denials and
outages are reported as unavailable or partial, never as zero. Allocation (quota
limits) and utilization (resources actually provisioned) are separate kinds.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from fastapi import HTTPException

from app.api.common.errors import public_service_error
from app.config import get_settings
from app.services import (
    domain_display,
    domain_iam,
    identity_roles,
    login_monitoring,
    manila,
    quota_native,
    service_proxy,
    traffic_analytics,
    user_inventory,
    zun,
)

QUOTA_PROJECT_LIMIT = 100
QUOTA_CONCURRENCY = 8

SERVICE = {
    "instances": "nova",
    "keypairs": "nova",
    "volumes": "cinder",
    "volume_snapshots": "cinder",
    "volume_backups": "cinder",
    "floating_ips": "neutron",
    "networks": "neutron",
    "subnets": "neutron",
    "routers": "neutron",
    "security_groups": "neutron",
    "load_balancers": "octavia",
    "images": "glance",
    "database_instances": "trove",
    "database_backups": "trove",
    "k3s_clusters": "drover",
    "waygate_gateways": "waygate",
    "containers": "zun",
    "magnum_clusters": "magnum",
    "shares": "manila",
    "share_snapshots": "manila",
    "share_networks": "manila",
    "security_services": "manila",
    "buckets": "swift",
    "packages": "palimpsest",
    "secrets": "barbican",
}
# These services have no native cross-project listing usable from this boundary
# (user-global keypairs, per-account Swift, per-project Barbican/Trove, and the
# independently authorized Drover/Waygate/Palimpsest/Magnum APIs).
UNSUPPORTED = {
    "keypairs",
    "database_instances",
    "database_backups",
    "k3s_clusters",
    "waygate_gateways",
    "magnum_clusters",
    "buckets",
    "packages",
    "secrets",
}


def _native_error(exc: Exception) -> HTTPException:
    if isinstance(exc, HTTPException):
        return exc
    status = getattr(exc, "status_code", None) or getattr(exc, "http_status", None)
    if status in (401, 403):
        return HTTPException(403, "domain_monitoring_native_denied")
    if status == 404:
        return HTTPException(404, "domain_not_found")
    return public_service_error(503, "domain_monitoring_directory_unavailable")


def directory(conn, domain_id: str) -> dict:
    """Exact native domain, users and projects; any failure aborts the snapshot."""
    try:
        domain = conn.identity.get_domain(domain_id)
        if domain is None:
            raise HTTPException(404, "domain_not_found")
        if getattr(domain, "id", None) != domain_id:
            raise public_service_error(503, "domain_monitoring_directory_unavailable")
        users = {
            u.id: u for u in conn.identity.users(domain_id=domain_id) if getattr(u, "domain_id", None) == domain_id
        }
        projects = {
            p.id: p for p in conn.identity.projects(domain_id=domain_id) if getattr(p, "domain_id", None) == domain_id
        }
    except Exception as exc:
        raise _native_error(exc) from exc
    return {
        "domain": {
            "id": domain.id,
            "name": domain_display.display_name(domain),
            "enabled": bool(getattr(domain, "is_enabled", False)),
        },
        "user_ids": set(users),
        "project_ids": set(projects),
        "users": users,
        "projects": projects,
    }


def _admin_rows(conn, category: str) -> list:
    """Native administrator collections across projects; ownership is filtered later."""
    if category == "instances":
        return list(conn.compute.servers(details=True, all_projects=True))
    if category == "volumes":
        return list(conn.block_storage.volumes(details=True, all_projects=True))
    if category == "volume_snapshots":
        return list(conn.block_storage.snapshots(details=True, all_projects=True))
    if category == "volume_backups":
        return list(conn.block_storage.backups(details=True, all_projects=True))
    network = {
        "floating_ips": "ips",
        "networks": "networks",
        "subnets": "subnets",
        "routers": "routers",
        "security_groups": "security_groups",
    }
    if category in network:
        return list(getattr(conn.network, network[category])())
    if category == "load_balancers":
        return list(conn.load_balancer.load_balancers())
    if category == "images":
        # Default listings omit community images owned by other projects.
        return list(conn.image.images(visibility="all"))
    if category in {"shares", "share_snapshots", "share_networks", "security_services"}:
        client = manila.get_client(conn)
        key, path = {
            "shares": ("shares", "/shares/detail?all_tenants=1"),
            "share_snapshots": ("snapshots", "/snapshots/detail?all_tenants=1"),
            "share_networks": ("share_networks", "/share-networks/detail?all_tenants=1"),
            "security_services": ("security_services", "/security-services/detail?all_tenants=1"),
        }[category]
        return user_inventory.rest_list(client.get, path, key, client._url("/").rstrip("/"))
    if category == "containers":
        endpoint = zun._get_zun_endpoint(conn)

        def get(path):
            return conn.session.get(service_proxy.join_version_aware_url(endpoint, path))

        return user_inventory.rest_list(get, "/v1/containers?all_projects=True", "containers", endpoint)
    raise ValueError("Unsupported domain aggregate")


def _owner(row, category: str):
    if category == "images":
        return user_inventory.field(row, "owner", "owner_id", "project_id")
    return user_inventory.field(
        row, "project_id", "tenant_id", "os-vol-tenant-attr:tenant_id", "os-extended-snapshot-attributes:project_id"
    )


def _metric(service, metric, kind, unit, value=None, status="unavailable", error=None) -> dict:
    row = {"service": service, "metric": metric, "kind": kind, "value": value, "unit": unit, "status": status}
    if error:
        row["error"] = error
    return row


def _failure(exc: Exception) -> tuple[str, str]:
    state = user_inventory.failure(exc)
    return ("denied", "native_denied") if state["state"] == "denied" else ("unavailable", "native_unavailable")


def _attributed_rows(conn, category: str, project_ids: set[str]):
    """Single ownership boundary for admin aggregates and manager details."""
    gate = user_inventory.CATALOG[category][1]
    if gate is not None and not getattr(get_settings(), f"service_{gate}_enabled"):
        return [], "disabled", "service_disabled"
    if category in UNSUPPORTED:
        return [], "unavailable", "domain_aggregate_unsupported"
    try:
        rows = _admin_rows(conn, category)
    except Exception as exc:
        status, error = _failure(exc)
        return [], status, error
    owned, seen, missing = [], set(), 0
    for row in rows:
        owner = _owner(row, category)
        ident = user_inventory.field(row, "id", "uuid")
        if not isinstance(owner, str) or not owner or not isinstance(ident, str) or not ident:
            missing += 1
            continue
        key = (owner, ident)
        if owner in project_ids and key not in seen:
            seen.add(key)
            owned.append(row)
    if rows and missing == len(rows):
        return [], "unavailable", "owner_unavailable"
    return owned, "partial" if missing else "ready", "owner_unavailable" if missing else None


def _resource_metrics(category, owned, status, error):
    service = SERVICE[category]
    extra = {"instances": [("vcpus", "vcpu"), ("ram_mb", "MiB")], "volumes": [("volume_gb", "GiB")]}.get(category, [])
    names = [(category, "count", "count"), *((name, "utilization", unit) for name, unit in extra)]
    if status not in {"ready", "partial"}:
        return [_metric(service, name, kind, unit, status=status, error=error) for name, kind, unit in names]
    result = [_metric(service, category, "count", "count", len(owned), status, error)]
    for name, unit in extra:
        key = "vcpus" if name == "vcpus" else "ram"
        values = [
            user_inventory.number(
                user_inventory.field(row, "size")
                if name == "volume_gb"
                else user_inventory.field(user_inventory.field(row, "flavor") or {}, key)
            )
            for row in owned
        ]
        if any(value is None for value in values):
            result.append(_metric(service, name, "utilization", unit, status="partial", error="value_unavailable"))
        else:
            result.append(_metric(service, name, "utilization", unit, sum(values), status, error))
    return result


def collect_category(conn, category: str, project_ids: set[str]) -> list[dict]:
    return _resource_metrics(category, *_attributed_rows(conn, category, project_ids))


QUOTAS = {
    "nova": (("instances", "count"), ("cores", "vcpu"), ("ram", "MiB")),
    "cinder": (("volumes", "count"), ("gigabytes", "GiB")),
}


def _quota_set(conn, service: str, project_id: str):
    proxy = conn.compute if service == "nova" else conn.block_storage
    return proxy.get_quota_set(project_id)


async def allocation(conn, project_ids: set[str]) -> list[dict]:
    """Summed per-project quota limits; unlimited (-1) is not a finite total."""
    projects = sorted(project_ids)
    metrics = []
    for service, keys in QUOTAS.items():
        names = [(f"quota_{key}", unit) for key, unit in keys]
        if len(projects) > QUOTA_PROJECT_LIMIT:
            metrics.extend(
                _metric(service, name, "allocation", unit, status="partial", error="project_limit_exceeded")
                for name, unit in names
            )
            continue
        gate = asyncio.Semaphore(QUOTA_CONCURRENCY)

        async def fetch(project_id, service=service, gate=gate):
            async with gate:
                return await _native_call(_quota_set, conn, service, project_id)

        results = await asyncio.gather(*(fetch(pid) for pid in projects), return_exceptions=True)
        failed = next((r for r in results if isinstance(r, Exception)), None)
        if failed is not None:
            status, error = _failure(failed)
            metrics.extend(
                _metric(service, name, "allocation", unit, status=status, error=error) for name, unit in names
            )
            continue
        for key, unit in keys:
            values = [getattr(r, key, None) for r in results]
            if any(isinstance(v, int) and not isinstance(v, bool) and v < 0 for v in values):
                metrics.append(_metric(service, f"quota_{key}", "allocation", unit, status="unlimited"))
            elif any(user_inventory.number(v) is None for v in values):
                metrics.append(_metric(service, f"quota_{key}", "allocation", unit, error="value_unavailable"))
            else:
                metrics.append(_metric(service, f"quota_{key}", "allocation", unit, sum(values), "ready"))
    return metrics


async def snapshot(conn, domain_id: str, window: login_monitoring.Window) -> dict:
    scope = await _workspace_directory(conn, domain_id)
    project_ids, user_ids = scope["project_ids"], scope["user_ids"]
    categories = list(user_inventory.CATALOG)
    resource_groups, allocations, requests, observation = await asyncio.gather(
        asyncio.gather(*(_native_call(collect_category, conn, c, project_ids) for c in categories)),
        allocation(conn, project_ids),
        traffic_analytics.domain_snapshot(domain_id, window),
        login_monitoring.domain_observation(domain_id, user_ids, project_ids, window),
    )
    resources = [metric for group in resource_groups for metric in group] + allocations
    notes = list(observation["notes"])
    if any(metric["status"] != "ready" for metric in resources):
        notes.append("resources_incomplete")
    if requests["state"] != "ready":
        notes.append("requests_token_attributed_partial")
    partial = (
        any(metric["status"] not in {"ready", "disabled", "unlimited"} for metric in resources)
        or requests["state"] != "ready"
        or any(observation[key]["state"] != "ready" for key in ("logins", "activity", "sessions"))
    )
    return {
        "domain": scope["domain"],
        "directory": {"users": len(user_ids), "projects": len(project_ids)},
        "resources": resources,
        "requests": requests,
        "logins": observation["logins"],
        "sessions": observation["sessions"],
        "activity": observation["activity"],
        "coverage": {
            "window": window,
            "observed_at": datetime.now(UTC).isoformat(),
            "partial": partial,
            "notes": notes,
        },
    }


async def _native_call(fn, *args, **kwargs):
    return await identity_roles._to_completion(asyncio.to_thread(fn, *args, **kwargs))


async def _workspace_directory(conn, domain_id):
    scope = await _native_call(directory, conn, domain_id)
    # Reuse IAM's native explicit-source/effective-membership boundary. Home
    # domain users alone omit identities that joined through Default reader.
    joined = await domain_iam.directory_users(domain_id)
    for user in joined:
        uid = identity_roles._field(user, "id")
        home = identity_roles._field(user, "domain_id")
        if not isinstance(uid, str) or not uid or not isinstance(home, str) or not home:
            raise public_service_error(503, "domain_monitoring_directory_unavailable")
        scope["users"][uid] = user
    scope["user_ids"] = set(scope["users"])
    return scope


def _memberships(conn, project_ids, user_ids):
    result = {uid: [] for uid in user_ids}
    try:
        for pid in sorted(project_ids):
            for row in conn.identity.role_assignments(scope_project_id=pid, effective=True):
                scope = identity_roles._field(row, "scope", {})
                project = identity_roles._field(scope, "project", {})
                uid = identity_roles._field(identity_roles._field(row, "user", {}), "id")
                if identity_roles._field(project, "id") != pid or not isinstance(uid, str) or not uid:
                    raise ValueError("Effective membership is not attributable")
                if uid in result and pid not in result[uid]:
                    result[uid].append(pid)
        return result, "ready"
    except Exception:
        # The array is only a known inventory; this state distinguishes failed
        # membership observation from an authoritative no-project membership.
        return result, "unavailable"


def _native_user(row):
    value = user_inventory.field(row, "user_id", "os-extended-snapshot-attributes:user_id")
    return value if isinstance(value, str) and value else None


def _quota_allocation_metrics(quotas):
    result = []
    for section, fields in quota_native.QUOTA_FIELDS.items():
        service = {"compute": "nova", "volume": "cinder", "network": "neutron", "file_storage": "manila"}[section]
        for key, native in fields.items():
            values, errors = [], []
            for quota in quotas:
                entries = quota.get(section)
                entry = entries.get(native) if isinstance(entries, dict) else None
                value = entry.get("limit") if isinstance(entry, dict) else None
                values.append(value if type(value) is int and value >= -1 else None)
                errors.append(quota.get("errors", {}).get(section))
            unit = (
                "MiB"
                if key == "ram"
                else "vcpu"
                if key == "cores"
                else "GiB"
                if "gigabytes" in key
                else "bytes"
                if "bytes" in key
                else "count"
            )
            if any(value is None for value in values):
                disabled = bool(errors) and all(error == "service_disabled" for error in errors)
                result.append(
                    _metric(
                        service,
                        f"quota_{key}",
                        "allocation",
                        unit,
                        status="disabled" if disabled else "unavailable",
                        error="service_disabled" if disabled else "quota_unavailable",
                    )
                )
            elif -1 in values:
                result.append(_metric(service, f"quota_{key}", "allocation", unit, status="unlimited"))
            else:
                result.append(_metric(service, f"quota_{key}", "allocation", unit, sum(values), "ready"))
    return result


async def manager_workspace(conn, domain_id: str) -> dict:
    """Exact-domain inventory, joined identities and attributable actual use.

    No traffic/session/credential detail is borrowed from system-admin views.
    Native project quota limits are not represented as per-user quotas.
    """
    scope = await _workspace_directory(conn, domain_id)
    projects = [
        {
            "id": pid,
            "name": identity_roles._field(row, "name") or "",
            "enabled": bool(identity_roles._field(row, "is_enabled", identity_roles._field(row, "enabled", False))),
            "resources": [],
        }
        for pid, row in sorted(scope["projects"].items())
    ]
    users = [
        {
            "id": uid,
            "name": identity_roles._field(row, "name") or "",
            "domain_id": identity_roles._field(row, "domain_id"),
            "enabled": bool(identity_roles._field(row, "enabled", identity_roles._field(row, "is_enabled", False))),
            "project_ids": [],
            "membership_state": "unavailable",
            "resources": [],
        }
        for uid, row in sorted(scope["users"].items())
    ]
    gate = asyncio.Semaphore(QUOTA_CONCURRENCY)

    async def category_read(category):
        async with gate:
            return category, await _native_call(_attributed_rows, conn, category, scope["project_ids"])

    async def quota_read(project):
        async with gate:
            return project["id"], await quota_native.read_project(conn, project["id"])

    categories, quotas, memberships = await asyncio.gather(
        asyncio.gather(*(category_read(category) for category in user_inventory.CATALOG)),
        asyncio.gather(*(quota_read(project) for project in projects)),
        _native_call(_memberships, conn, scope["project_ids"], scope["user_ids"]),
    )
    quota_by_project = dict(quotas)
    membership_map, membership_state = memberships
    for project in projects:
        project["quotas"] = quota_by_project[project["id"]]
        project["resources"].extend(_quota_allocation_metrics([project["quotas"]]))
    for user in users:
        user["project_ids"] = membership_map[user["id"]]
        user["membership_state"] = membership_state
    resources, inventory, notes = [], [], []
    for category, (rows, status, error) in categories:
        resources.extend(_resource_metrics(category, rows, status, error))
        for project in projects:
            owned = [row for row in rows if _owner(row, category) == project["id"]]
            project["resources"].extend(_resource_metrics(category, owned, status, error))
        unattributable = any(_native_user(row) not in scope["user_ids"] for row in rows)
        for user in users:
            attributed = [row for row in rows if _native_user(row) == user["id"]]
            user_status, user_error = status, error
            if unattributable and status in {"ready", "partial"}:
                user_status, user_error = "partial", "user_attribution_unavailable"
            user["resources"].extend(_resource_metrics(category, attributed, user_status, user_error))
        if unattributable:
            notes.append(f"{category}:user_attribution_unavailable")
        for row in rows:
            uid = _native_user(row)
            native_status = user_inventory.field(row, "status", "state")
            inventory.append(
                {
                    "category": category,
                    "id": user_inventory.field(row, "id", "uuid"),
                    "name": user_inventory.field(row, "name", "display_name") or "",
                    "project_id": _owner(row, category),
                    "user_id": uid if uid in scope["user_ids"] else None,
                    "status": native_status if isinstance(native_status, str) else None,
                }
            )
    resources.extend(_quota_allocation_metrics(list(quota_by_project.values())))
    if membership_state != "ready":
        notes.append("project_memberships_unavailable")
    partial = (
        membership_state != "ready"
        or bool(notes)
        or any(metric["status"] not in {"ready", "disabled", "unlimited"} for metric in resources)
    )
    if partial:
        notes.append("resources_incomplete")
    return {
        "domain": scope["domain"],
        "projects": projects,
        "users": users,
        "resources": resources,
        "inventory": inventory,
        "coverage": {"observed_at": datetime.now(UTC).isoformat(), "partial": partial, "notes": notes},
    }
