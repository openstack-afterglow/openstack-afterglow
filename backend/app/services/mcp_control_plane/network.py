"""Project-owned or explicitly shared Neutron read adapters for consumer MCP."""

from __future__ import annotations

from collections.abc import Mapping
from itertools import chain
from typing import Any

from app.services.mcp_control_plane.sdk import check_mutation_dispatch, run_sdk

_MAX_TEXT = 255


class McpNetworkError(ValueError):
    """Neutron data is unavailable or lacks an allowed visibility proof."""


def _field(resource: Any, name: str) -> Any:
    if isinstance(resource, Mapping):
        return resource.get(name)
    return getattr(resource, name, None)


def _required_text(resource: Any, name: str) -> str:
    value = _field(resource, name)
    if not isinstance(value, str) or not value or len(value) > _MAX_TEXT:
        raise McpNetworkError(f"Neutron network {name} is missing or malformed")
    return value


def _optional_text(resource: Any, name: str) -> str | None:
    value = _field(resource, name)
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > _MAX_TEXT:
        raise McpNetworkError(f"Neutron network {name} is malformed")
    return value


def _is_explicitly_shared(resource: Any) -> bool:
    return bool(_field(resource, "is_shared") or _field(resource, "shared") or _field(resource, "is_router_external"))


def _safe_network(resource: Any, *, project_id: str) -> dict[str, str | bool | None]:
    owner_project_id = _field(resource, "project_id") or _field(resource, "tenant_id")
    is_shared = _is_explicitly_shared(resource)
    if owner_project_id != project_id and not is_shared:
        raise McpNetworkError("Neutron network ownership or shared visibility cannot be proven")
    return {
        "id": _required_text(resource, "id"),
        "name": _optional_text(resource, "name"),
        "status": _optional_text(resource, "status"),
        "is_shared": is_shared,
        "is_external": bool(_field(resource, "is_router_external")),
        "visibility": "owned" if owner_project_id == project_id else "shared",
    }


def _list_networks(conn: Any, *, project_id: str, limit: int) -> list[dict[str, str | bool | None]]:
    # The owner-filtered request is mandatory. Shared/external networks use a
    # separate explicit-visibility branch rather than an unbounded all-project list.
    owned = conn.network.networks(project_id=project_id)
    shared = conn.network.networks(is_shared=True)
    external = conn.network.networks(is_router_external=True)
    seen: set[str] = set()
    safe_networks: list[dict[str, str | bool | None]] = []
    for network in chain(owned, shared, external):
        safe = _safe_network(network, project_id=project_id)
        network_id = str(safe["id"])
        if network_id in seen:
            continue
        seen.add(network_id)
        safe_networks.append(safe)
        if len(safe_networks) == limit:
            break
    return safe_networks


def _get_network(conn: Any, *, project_id: str, network_id: str) -> dict[str, str | bool | None]:
    network = conn.network.get_network(network_id)
    if network is None:
        raise McpNetworkError("Neutron network was not found")
    return _safe_network(network, project_id=project_id)


def _prepare_network_delete(conn: Any, *, project_id: str, network_id: str) -> dict[str, str | bool | None]:
    network = conn.network.get_network(network_id)
    if network is None:
        raise McpNetworkError("Neutron network was not found")
    owner_project_id = _field(network, "project_id") or _field(network, "tenant_id")
    if owner_project_id != project_id:
        raise McpNetworkError("Neutron network ownership cannot be proven for deletion")
    if _is_explicitly_shared(network):
        raise McpNetworkError("Neutron shared or external network cannot be deleted")
    safe_network = _safe_network(network, project_id=project_id)
    if safe_network["status"] not in {"ACTIVE", "DOWN", "ERROR"}:
        raise McpNetworkError("Neutron network is not in a state that permits deletion")
    return {**safe_network, "requested_action": "delete"}


def _delete_network(conn: Any, *, project_id: str, network_id: str) -> dict[str, str | bool | None]:
    safe_network = _prepare_network_delete(conn, project_id=project_id, network_id=network_id)
    check_mutation_dispatch()
    conn.network.delete_network(network_id, ignore_missing=False)
    return safe_network


def _safe_subnet(conn: Any, resource: Any, *, project_id: str) -> dict[str, str | int | None]:
    owner_project_id = _field(resource, "project_id") or _field(resource, "tenant_id")
    if owner_project_id != project_id:
        raise McpNetworkError("Neutron subnet ownership cannot be proven")
    network_id = _required_text(resource, "network_id")
    parent = conn.network.get_network(network_id)
    if parent is None:
        raise McpNetworkError("Neutron subnet parent network was not found")
    _safe_network(parent, project_id=project_id)
    ip_version = _field(resource, "ip_version")
    if ip_version not in (4, 6):
        raise McpNetworkError("Neutron subnet IP version is malformed")
    return {
        "id": _required_text(resource, "id"),
        "name": _optional_text(resource, "name"),
        "network_id": network_id,
        "cidr": _required_text(resource, "cidr"),
        "ip_version": ip_version,
        "gateway_ip": _optional_text(resource, "gateway_ip"),
    }


def _list_subnets(conn: Any, *, project_id: str, limit: int) -> list[dict[str, str | int | None]]:
    subnets = conn.network.subnets(project_id=project_id)
    safe_subnets: list[dict[str, str | int | None]] = []
    for subnet in subnets:
        safe_subnets.append(_safe_subnet(conn, subnet, project_id=project_id))
        if len(safe_subnets) == limit:
            break
    return safe_subnets


def _get_subnet(conn: Any, *, project_id: str, subnet_id: str) -> dict[str, str | int | None]:
    subnet = conn.network.get_subnet(subnet_id)
    if subnet is None:
        raise McpNetworkError("Neutron subnet was not found")
    return _safe_subnet(conn, subnet, project_id=project_id)


def _prepare_subnet_delete(conn: Any, *, project_id: str, subnet_id: str) -> dict[str, str | int | None]:
    subnet = conn.network.get_subnet(subnet_id)
    if subnet is None:
        raise McpNetworkError("Neutron subnet was not found")
    safe_subnet = _safe_subnet(conn, subnet, project_id=project_id)
    parent = conn.network.get_network(str(safe_subnet["network_id"]))
    if parent is None:
        raise McpNetworkError("Neutron subnet parent network was not found")
    owner_project_id = _field(parent, "project_id") or _field(parent, "tenant_id")
    if owner_project_id != project_id or _is_explicitly_shared(parent):
        raise McpNetworkError("Neutron shared or foreign parent network cannot be mutated")
    return {**safe_subnet, "requested_action": "delete"}


def _delete_subnet(conn: Any, *, project_id: str, subnet_id: str) -> dict[str, str | int | None]:
    safe_subnet = _prepare_subnet_delete(conn, project_id=project_id, subnet_id=subnet_id)
    check_mutation_dispatch()
    conn.network.delete_subnet(subnet_id, ignore_missing=False)
    return safe_subnet


async def list_project_networks(conn: Any, *, project_id: str, limit: int) -> list[dict[str, str | bool | None]]:
    """List exact-project and explicitly shared networks with no admin bypass."""
    try:
        return await run_sdk(_list_networks, conn, project_id=project_id, limit=limit)
    except McpNetworkError:
        raise
    except Exception as exc:
        raise McpNetworkError("Neutron network list is unavailable") from exc


async def get_project_network(conn: Any, *, project_id: str, network_id: str) -> dict[str, str | bool | None]:
    """Read one network only after owner or explicit shared-visibility proof."""
    try:
        return await run_sdk(_get_network, conn, project_id=project_id, network_id=network_id)
    except McpNetworkError:
        raise
    except Exception as exc:
        raise McpNetworkError("Neutron network is unavailable") from exc


async def preview_project_network_delete(
    conn: Any, *, project_id: str, network_id: str
) -> dict[str, str | bool | None]:
    """Validate an owned non-shared network deletion against current provider state."""
    try:
        return await run_sdk(_prepare_network_delete, conn, project_id=project_id, network_id=network_id)
    except McpNetworkError:
        raise
    except Exception as exc:
        raise McpNetworkError("Neutron network deletion is unavailable") from exc


async def request_project_network_delete(
    conn: Any, *, project_id: str, network_id: str
) -> dict[str, str | bool | None]:
    """Delete only a current-project non-shared network without force."""
    try:
        return await run_sdk(_delete_network, conn, project_id=project_id, network_id=network_id)
    except McpNetworkError:
        raise
    except Exception as exc:
        raise McpNetworkError("Neutron network deletion is unavailable") from exc


async def list_project_subnets(conn: Any, *, project_id: str, limit: int) -> list[dict[str, str | int | None]]:
    """List subnets only after proving exact ownership and a visible parent network."""
    try:
        return await run_sdk(_list_subnets, conn, project_id=project_id, limit=limit)
    except McpNetworkError:
        raise
    except Exception as exc:
        raise McpNetworkError("Neutron subnet list is unavailable") from exc


async def get_project_subnet(conn: Any, *, project_id: str, subnet_id: str) -> dict[str, str | int | None]:
    """Read one subnet only after proving exact ownership and its visible parent."""
    try:
        return await run_sdk(_get_subnet, conn, project_id=project_id, subnet_id=subnet_id)
    except McpNetworkError:
        raise
    except Exception as exc:
        raise McpNetworkError("Neutron subnet is unavailable") from exc


async def preview_project_subnet_delete(conn: Any, *, project_id: str, subnet_id: str) -> dict[str, str | int | None]:
    """Validate an exact-project subnet deletion against its non-shared parent network."""
    try:
        return await run_sdk(_prepare_subnet_delete, conn, project_id=project_id, subnet_id=subnet_id)
    except McpNetworkError:
        raise
    except Exception as exc:
        raise McpNetworkError("Neutron subnet deletion is unavailable") from exc


async def request_project_subnet_delete(conn: Any, *, project_id: str, subnet_id: str) -> dict[str, str | int | None]:
    """Delete only an exact-project subnet under a non-shared parent network."""
    try:
        return await run_sdk(_delete_subnet, conn, project_id=project_id, subnet_id=subnet_id)
    except McpNetworkError:
        raise
    except Exception as exc:
        raise McpNetworkError("Neutron subnet deletion is unavailable") from exc
