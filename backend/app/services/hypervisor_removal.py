"""Read-only, fail-closed evidence for reviewed single-host Nova removal.

These functions never disable/delete services, retry mutations, or clean up
Placement. The route owns approval, physical shutdown attestation and deletion.
Retained history is not proof that a host has never been used. Nova down is not
proof that the physical process has stopped.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from urllib.parse import quote

from app.services import nova_hosts

PLACEMENT_HEADERS = {"OpenStack-API-Version": "placement 1.14"}
MIGRATION_HEADERS = {"OpenStack-API-Version": "compute 2.59"}
UNPAGED_MIGRATION_HEADERS = {"OpenStack-API-Version": "compute 2.58"}


def _check(checks: list, code: str, label: str, state: str, detail: str):
    checks.append({"code": code, "label": label, "state": state, "detail": detail})


def _unknown(checks: list, code: str, label: str):
    # Upstream exceptions/bodies may contain tokens, internal URLs or credentials.
    _check(checks, code, label, "unknown", "Required evidence could not be read or validated.")


def _nova(conn, path: str, params=None, headers=None):
    return nova_hosts._get_json(
        conn,
        conn.compute.get_endpoint(),
        path,
        params=params,
        headers=headers if headers is not None else nova_hosts.NOVA_HOST_HEADERS,
    )


def _placement(conn, path: str, params=None):
    return nova_hosts._get_json(conn, conn.placement.get_endpoint(), path, params=params, headers=PLACEMENT_HEADERS)


def _integer(value, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"Invalid {label}")
    return value


def _date(value, *, required=False):
    if value is None and not required:
        return None
    value = nova_hosts._text(value, "timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    # Nova may emit naive timestamps; they represent UTC, not local time.
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    if parsed > datetime.now(UTC):
        raise ValueError("Timestamp is in the future")
    return value


def _nullable_text(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Invalid metadata string")
    return value


def _hypervisors(conn):
    marker = None
    seen = set()
    for _ in range(nova_hosts.MAX_HOST_PAGES):
        params = {"limit": str(nova_hosts.HOST_SERVER_PAGE_SIZE)}
        if marker is not None:
            params["marker"] = marker
        body = _nova(conn, "/os-hypervisors/detail", params)
        page = nova_hosts._items(body, "hypervisors")
        for node in page:
            node_id = nova_hosts._text(node.get("id"), "compute node ID")
            mapping = nova_hosts._object(node.get("service"), "compute node service")
            nova_hosts._text(mapping.get("id"), "compute node service ID")
            nova_hosts._text(mapping.get("host"), "compute node service host")
            if node_id in seen:
                raise ValueError("Repeated compute node")
            seen.add(node_id)
            yield node
        if not page:
            if body.get("hypervisors_links"):
                raise ValueError("Invalid empty hypervisor page")
            return
        marker = page[-1]["id"]
    raise ValueError("Compute node pagination did not terminate")


def _server(raw: dict, host: str):
    if raw.get("OS-EXT-SRV-ATTR:host") != host:
        raise ValueError("Server host evidence missing or mismatched")
    return {
        "id": nova_hosts._text(raw.get("id"), "server ID"),
        "name": nova_hosts._text(raw.get("name"), "server name"),
        "status": nova_hosts._text(raw.get("status"), "server status"),
        "project_id": nova_hosts._text(raw.get("tenant_id") or raw.get("project_id"), "server project"),
        "created_at": _date(raw.get("created")),
    }


def _migration(raw: dict, host: str, *, with_uuid: bool) -> dict:
    migration_id = raw.get("id")
    if type(migration_id) not in (str, int) or migration_id == "":
        raise ValueError("Missing migration ID")
    item = {"id": str(migration_id), "uuid": nova_hosts._text(raw.get("uuid"), "migration UUID") if with_uuid else ""}
    for field in ("instance_uuid", "status", "migration_type"):
        item[field] = nova_hosts._text(raw.get(field), f"migration {field}")
    # Nova allows an explicit null side (e.g. failed scheduling before a
    # destination exists). A missing key is malformed, not null.
    for field in ("source_compute", "dest_compute"):
        if field not in raw:
            raise ValueError(f"Missing migration {field}")
        value = raw[field]
        if value is not None and (not isinstance(value, str) or not value):
            raise ValueError(f"Invalid migration {field}")
        item[field] = value
    if host not in (item["source_compute"], item["dest_compute"]):
        raise ValueError("Migration host mismatch")
    item["created_at"] = _date(raw.get("created_at"))
    item["updated_at"] = _date(raw.get("updated_at"))
    return item


def _migrations(conn, host: str):
    """Return every API-visible incoming/outgoing migration for the host.

    Nova removes hidden records after applying 2.59 limit/marker pagination,
    so an all-hidden page is empty without links and cannot prove the end. The
    unpaged 2.58 host read is therefore authoritative; the 2.59 UUID scan only
    enriches it and must agree. `hidden` is never sent: Nova strips hidden rows
    from every response and its raw query filter is unsafe.
    """
    body = _nova(conn, "/os-migrations", {"host": host}, UNPAGED_MIGRATION_HEADERS)
    if body.get("migrations_links"):
        raise ValueError("Unexpected unpaged migration continuation")

    # IDs are per-cell autoincrements, so a cross-cell record may share one.
    def key(item):
        return item["id"], item["instance_uuid"], item["created_at"], item["source_compute"], item["dest_compute"]

    records = {}
    for raw in nova_hosts._items(body, "migrations"):
        item = _migration(raw, host, with_uuid=False)
        if key(item) in records:
            raise ValueError("Ambiguous migration identity")
        records[key(item)] = item
    seen = set()
    marker = None
    for _ in range(nova_hosts.MAX_HOST_PAGES):
        params = {"host": host, "limit": str(nova_hosts.HOST_SERVER_PAGE_SIZE)}
        if marker is not None:
            params["marker"] = marker
        body = _nova(conn, "/os-migrations", params, MIGRATION_HEADERS)
        page = nova_hosts._items(body, "migrations")
        for raw in page:
            item = _migration(raw, host, with_uuid=True)
            identity = key(item)
            if item["uuid"] in seen or identity in seen or identity not in records:
                raise ValueError("Migration changed during enumeration")
            seen.update((item["uuid"], identity))
            if records[identity] | {"uuid": item["uuid"]} != item:
                raise ValueError("Migration changed during enumeration")
            records[identity] = item
        if not page:
            break
        marker = page[-1]["uuid"]
    else:
        raise ValueError("Migration pagination did not terminate")
    return sorted(records.values(), key=lambda item: (item["uuid"], item["id"]))


# Nova's own in-progress exclusion (migration_get_in_progress_by_host_and_node).
_TERMINAL_MIGRATION_STATUSES = {"confirmed", "reverted", "error", "failed", "completed", "cancelled", "done"}
_MIGRATION_TYPES = {"migration", "resize", "live-migration", "evacuation"}


def _migration_state(item: dict) -> str:
    if item["migration_type"] not in _MIGRATION_TYPES:
        return "unknown"
    # Every other status, including finished/VERIFY_RESIZE and unrecognised ones, is in progress.
    return "pass" if item["status"].lower() in _TERMINAL_MIGRATION_STATUSES else "blocked"


def _provider(raw: dict) -> dict:
    uuid = nova_hosts._text(raw.get("uuid"), "provider UUID")
    root = nova_hosts._text(raw.get("root_provider_uuid"), "provider root UUID")
    if "parent_provider_uuid" not in raw:
        raise ValueError("Missing provider parent")
    parent = raw["parent_provider_uuid"]
    if parent is not None:
        nova_hosts._text(parent, "provider parent UUID")
    return {
        "uuid": uuid,
        "name": nova_hosts._text(raw.get("name"), "provider name"),
        "parent_provider_uuid": parent,
        "generation": _integer(raw.get("generation"), "provider generation"),
        "root_provider_uuid": root,
    }


def _providers(body: dict) -> list[dict]:
    # Placement 1.14 lists are unpaginated. Never silently truncate an unexpected
    # extension advertising a continuation; it cannot establish safe absence.
    if body.get("resource_providers_links") or body.get("links") or body.get("next") or body.get("next_marker"):
        raise ValueError("Unverified Placement continuation")
    providers = [_provider(raw) for raw in nova_hosts._items(body, "resource_providers")]
    if len({item["uuid"] for item in providers}) != len(providers):
        raise ValueError("Repeated provider UUID")
    return providers


def _inspect_placement(conn, root_id: str):
    root = _provider(_placement(conn, f"/resource_providers/{quote(root_id, safe='')}"))
    if root["uuid"] != root_id or root["parent_provider_uuid"] is not None or root["root_provider_uuid"] != root_id:
        raise ValueError("Invalid compute root provider")
    tree = _providers(_placement(conn, "/resource_providers", {"in_tree": root_id}))
    by_id = {item["uuid"]: item for item in tree}
    if by_id.get(root_id) != root:
        raise ValueError("Missing or changed tree root")
    for provider in tree:
        if provider["root_provider_uuid"] != root_id:
            raise ValueError("Provider outside compute tree")
        cursor, seen = provider, set()
        while cursor["parent_provider_uuid"] is not None:
            if cursor["uuid"] in seen or cursor["parent_provider_uuid"] not in by_id:
                raise ValueError("Invalid provider ancestry")
            seen.add(cursor["uuid"])
            cursor = by_id[cursor["parent_provider_uuid"]]
        if cursor["uuid"] != root_id:
            raise ValueError("Disconnected provider tree")
    result = []
    for provider in sorted(tree, key=lambda item: item["uuid"]):
        body = _placement(conn, f"/resource_providers/{quote(provider['uuid'], safe='')}/allocations")
        allocations = nova_hosts._object(body.get("allocations"), "provider allocations")
        if (
            _integer(body.get("resource_provider_generation"), "allocation provider generation")
            != provider["generation"]
        ):
            raise ValueError("Provider changed during allocation read")
        for consumer, allocation in allocations.items():
            nova_hosts._text(consumer, "allocation consumer")
            resources = nova_hosts._object(nova_hosts._object(allocation, "allocation").get("resources"), "resources")
            if not resources:
                raise ValueError("Empty allocation resources")
            for resource, amount in resources.items():
                nova_hosts._text(resource, "resource class")
                if _integer(amount, "allocation amount") == 0:
                    raise ValueError("Invalid zero allocation")
        result.append(
            {key: value for key, value in provider.items() if key != "root_provider_uuid"}
            | {
                "allocations": allocations,
            }
        )
    return result


def inspect_host(conn, hypervisor_id: str) -> dict:
    """Return the shared UI report; any unknown or blocked check denies removal."""
    report = {
        "hypervisor_id": hypervisor_id,
        "hostname": "",
        "checked_at": datetime.now(UTC).isoformat(),
        "service": dict.fromkeys(
            ("id", "host", "binary", "state", "status", "updated_at", "forced_down", "disabled_reason", "zone")
        ),
        "uptime": {"status": "unavailable", "value": None, "host_time": None},
        "servers": [],
        "history": {
            "deleted_servers": [],
            "migrations": [],
            "note": "Only Nova-retained history is available; Nova never exposes hidden (cross-cell copy) migrations, and empty history does not prove this host was never used.",
        },
        "placement": {"providers": []},
        "checks": [],
        "eligible": False,
    }
    checks = report["checks"]
    try:
        hypervisor = nova_hosts.get_hypervisor(conn, hypervisor_id)
        report["hostname"] = nova_hosts._text(hypervisor.get("hypervisor_hostname"), "hypervisor hostname")
        service = nova_hosts.get_compute_service(conn, hypervisor)
        report["service"].update({key: service.get(key) for key in report["service"]})
        _check(
            checks,
            "identity",
            "Exact Nova host/service mapping",
            "pass",
            "Hypervisor maps to one exact nova-compute service.",
        )
    except Exception:
        _unknown(checks, "identity", "Exact Nova host/service mapping")
        return report

    host = service["host"]
    try:
        nodes = list(_hypervisors(conn))
        matches = [node for node in nodes if node["service"]["id"] == service["id"] or node["service"]["host"] == host]
        safe = (
            len(matches) == 1
            and matches[0]["id"] == hypervisor_id
            and all(matches[0]["service"][field] == service[field] for field in ("id", "host"))
        )
        _check(
            checks,
            "single_compute_node",
            "One compute node per service",
            "pass" if safe else "blocked",
            "Exactly one mapped compute node is required; multi-node services cannot be removed per node.",
        )
    except Exception:
        _unknown(checks, "single_compute_node", "One compute node per service")

    for field, expected in (("status", "disabled"), ("state", "down")):
        values = (service.get(field), hypervisor.get(field))
        state = (
            "unknown"
            if any(value not in ({"enabled", "disabled"} if field == "status" else {"up", "down"}) for value in values)
            else ("pass" if values == (expected, expected) else "blocked")
        )
        _check(
            checks,
            f"service_{field}",
            f"Nova service {field}",
            state,
            f"Both the hypervisor and compute service must report {expected}.",
        )
    try:
        _date(service.get("updated_at"), required=True)
        _check(
            checks, "service_updated_at", "Last service update", "pass", "Nova supplied a valid last service update."
        )
    except Exception:
        _unknown(checks, "service_updated_at", "Last service update")
    forced = service.get("forced_down")
    _check(
        checks,
        "forced_down",
        "Heartbeat is not forcibly overridden",
        "unknown" if type(forced) is not bool else "blocked" if forced else "pass",
        "forced_down must explicitly be false; forced down does not establish heartbeat timeout.",
    )
    try:
        running = _integer(hypervisor.get("running_vms"), "running VM count")
        _check(
            checks,
            "running_vms",
            "Nova reported running instances",
            "blocked" if running else "pass",
            f"Nova reports {running} running instances. CPU and memory overhead need not be zero.",
        )
    except Exception:
        _unknown(checks, "running_vms", "Nova reported running instances")

    try:
        body = _nova(conn, f"/os-hypervisors/{quote(hypervisor_id, safe='')}/uptime")
        uptime = nova_hosts._object(body.get("hypervisor"), "uptime")
        report["uptime"] = {
            "status": "available",
            "value": nova_hosts._text(uptime.get("uptime"), "uptime"),
            "host_time": _nullable_text(uptime.get("host_time")),
        }
    except Exception:
        # Down-host uptime is expected to be unavailable and is not a safety gate.
        pass

    current = {}
    try:
        current = {item["id"]: item for raw in nova_hosts.host_servers(conn, host) if (item := _server(raw, host))}
        report["servers"] = sorted(current.values(), key=lambda item: item["id"])
        _check(
            checks,
            "present_servers",
            "Present instances",
            "blocked" if current else "pass",
            "All-project present instances must be absent, regardless of power state.",
        )
    except Exception:
        _unknown(checks, "present_servers", "Present instances")
    try:
        retained = [_server(raw, host) for raw in nova_hosts.host_servers(conn, host, deleted=True)]
        deleted = []
        for item in retained:
            if item["status"] == "SOFT_DELETED":
                if item["id"] in current and current[item["id"]] != item:
                    raise ValueError("Instance changed during enumeration")
                current[item["id"]] = item
            elif item["status"] == "DELETED":
                if item["id"] in current:
                    raise ValueError("Instance changed during enumeration")
                deleted.append(item)
            else:
                raise ValueError("Unexpected retained instance state")
        report["servers"] = sorted(current.values(), key=lambda item: item["id"])
        report["history"]["deleted_servers"] = sorted(deleted, key=lambda item: item["id"])
        _check(
            checks,
            "retained_servers",
            "Retained deleted and soft-deleted instances",
            "blocked" if any(item["status"] == "SOFT_DELETED" for item in retained) else "pass",
            "Soft-deleted instances remain present; permanently deleted retained instances are historical evidence only.",
        )
    except Exception:
        _unknown(checks, "retained_servers", "Retained deleted and soft-deleted instances")
    try:
        migrations = _migrations(conn, host)
        report["history"]["migrations"] = migrations
        states = {_migration_state(item) for item in migrations}
        state = "blocked" if "blocked" in states else "unknown" if "unknown" in states else "pass"
        _check(
            checks,
            "migrations",
            "Incoming and outgoing retained migrations",
            state,
            "Unfinished migrations, including resize awaiting confirmation, block removal; terminal history is retained for review.",
        )
    except Exception:
        _unknown(checks, "migrations", "Incoming and outgoing retained migrations")
    try:
        providers = _inspect_placement(conn, hypervisor_id)
        report["placement"]["providers"] = providers
        _check(
            checks,
            "placement_allocations",
            "Placement root and child allocations",
            "blocked" if any(item["allocations"] for item in providers) else "pass",
            "Every provider in the compute tree, including GPU children, must have no consumer allocations.",
        )
    except Exception:
        _unknown(checks, "placement_allocations", "Placement root and child allocations")
    report["eligible"] = all(item["state"] == "pass" for item in checks)
    return report


def review_fingerprint(report: dict) -> str:
    """Hash semantic review evidence, independent of list order and uptime samples."""
    metadata = {key: report[key] for key in ("hypervisor_id", "hostname", "service", "eligible")}
    metadata["servers"] = sorted(report["servers"], key=lambda item: item["id"])
    metadata["history"] = {
        "deleted_servers": sorted(report["history"]["deleted_servers"], key=lambda item: item["id"]),
        "migrations": sorted(report["history"]["migrations"], key=lambda item: (item["uuid"], item["id"])),
    }
    metadata["placement"] = {"providers": sorted(report["placement"]["providers"], key=lambda item: item["uuid"])}
    metadata["checks"] = sorted(report["checks"], key=lambda item: item["code"])
    encoded = json.dumps(metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def _is_404(exc: Exception) -> bool:
    # Only an explicit HTTP not-found establishes absence, not arbitrary errors.
    return any(
        type(value) is int and value == 404
        for value in (
            getattr(exc, "status_code", None),
            getattr(exc, "http_status", None),
            getattr(getattr(exc, "response", None), "status_code", None),
        )
    )


def verify_removal(conn, report: dict) -> dict:
    """Observe post-delete residue once, without mutating or retrying anything."""
    checks = []
    service = report["service"]
    service_id, host, hypervisor_id = service.get("id"), service.get("host"), report["hypervisor_id"]
    try:
        nova_hosts._text(service_id, "service ID")
        nova_hosts._text(host, "service host")
        services = nova_hosts._items(_nova(conn, "/os-services", {"host": host, "binary": "nova-compute"}), "services")
        for item in services:
            for key in ("id", "host", "binary"):
                nova_hosts._text(item.get(key), f"service {key}")
        residue = any(
            item["id"] == service_id or (item["host"] == host and item["binary"] == "nova-compute") for item in services
        )
        _check(
            checks,
            "service_absent",
            "Nova service absence",
            "blocked" if residue else "pass",
            "The deleted service and replacement compute services on its host must be absent.",
        )
    except Exception:
        _unknown(checks, "service_absent", "Nova service absence")
    try:
        absent = False
        try:
            nova_hosts.get_hypervisor(conn, hypervisor_id)
        except Exception as exc:
            if not _is_404(exc):
                raise
            absent = True
        nodes = list(_hypervisors(conn))
        residue = any(
            node["id"] == hypervisor_id or node["service"]["id"] == service_id or node["service"]["host"] == host
            for node in nodes
        )
        _check(
            checks,
            "hypervisor_absent",
            "Nova hypervisor absence",
            "pass" if absent and not residue else "blocked",
            "The target hypervisor and all compute nodes mapped to its service/host must be absent.",
        )
    except Exception:
        _unknown(checks, "hypervisor_absent", "Nova hypervisor absence")
    try:
        known = sorted(item["uuid"] for item in report["placement"]["providers"])
        if hypervisor_id not in known:
            raise ValueError("Missing reviewed provider tree")
        # in_tree on an absent root may 404 or be empty; neither proves absence.
        # Each reviewed provider must explicitly be not found. A re-registered
        # root or a surviving child returns 200 and is residue.
        residue = False
        for uuid in known:
            try:
                _placement(conn, f"/resource_providers/{quote(uuid, safe='')}")
                residue = True
            except Exception as exc:
                if not _is_404(exc):
                    raise
        _check(
            checks,
            "placement_absent",
            "Placement tree absence",
            "blocked" if residue else "pass",
            "The root and every reviewed child provider must be absent from Placement.",
        )
    except Exception:
        _unknown(checks, "placement_absent", "Placement tree absence")
    try:
        nova_hosts._text(host, "aggregate host")
        body = _nova(conn, "/os-aggregates")
        if body.get("aggregates_links") or body.get("next_marker"):
            raise ValueError("Unverified aggregate continuation")
        aggregates = nova_hosts._items(body, "aggregates")
        residue = False
        for aggregate in aggregates:
            hosts = aggregate.get("hosts")
            if not isinstance(hosts, list) or any(not isinstance(item, str) or not item for item in hosts):
                raise ValueError("Missing aggregate host membership")
            residue = residue or host in hosts
        _check(
            checks,
            "aggregates_removed",
            "Nova aggregate membership removed",
            "blocked" if residue else "pass",
            "The compute service host must not remain in any Nova aggregate.",
        )
    except Exception:
        _unknown(checks, "aggregates_removed", "Nova aggregate membership removed")
    verified = all(item["state"] == "pass" for item in checks)
    return {
        "status": "removed" if verified else "removal_unverified",
        "verified": verified,
        "hypervisor_id": hypervisor_id,
        "hostname": report["hostname"],
        "service_id": service_id,
        "detail": "Nova registration removal verified."
        if verified
        else "Removal is not verified; review residual or unavailable evidence before taking further action.",
        "checks": checks,
    }
