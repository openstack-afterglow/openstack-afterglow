"""Project-visible Neutron adapters and bounded network mutations for consumer MCP."""

from __future__ import annotations

from collections.abc import Mapping
from itertools import chain
from typing import Any

from app.services.mcp_control_plane.compute import McpComputeError, _safe_server
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


def validate_project_attachment_network(conn: Any, *, project_id: str, network_id: str) -> dict[str, str]:
    """Prove attachment authority; external visibility alone is not permission."""
    network = conn.network.get_network(network_id)
    if network is None:
        raise McpNetworkError("Neutron network was not found")
    if _required_text(network, "id") != network_id:
        raise McpNetworkError("Neutron network identity cannot be proven")
    if _field(network, "status") != "ACTIVE":
        raise McpNetworkError("Neutron network is not active for attachment")
    if _field(network, "is_admin_state_up") is False or _field(network, "admin_state_up") is False:
        raise McpNetworkError("Neutron network is administratively disabled")
    owner_project_id = _field(network, "project_id") or _field(network, "tenant_id")
    is_shared = _field(network, "is_shared") is True or _field(network, "shared") is True
    if not is_shared and any(
        owner is not None and owner != project_id
        for owner in (_field(network, "project_id"), _field(network, "tenant_id"))
    ):
        raise McpNetworkError("Neutron network ownership cannot be proven")
    if owner_project_id != project_id and not is_shared:
        raise McpNetworkError("Neutron network ownership or shared attachment authority cannot be proven")
    return {
        "network_id": network_id,
        "network_status": "ACTIVE",
        "visibility": "owned" if owner_project_id == project_id else "shared",
    }


def _prepare_server_network_attach(conn: Any, *, project_id: str, server_id: str, network_id: str) -> dict[str, str]:
    server = conn.compute.get_server(server_id)
    if server is None:
        raise McpNetworkError("Nova server was not found")
    if any(
        owner is not None and owner != project_id
        for owner in (_field(server, "project_id"), _field(server, "tenant_id"))
    ):
        raise McpNetworkError("Nova server ownership cannot be proven")
    try:
        safe_server = _safe_server(server, project_id=project_id)
    except McpComputeError:
        raise McpNetworkError("Nova server ownership or data cannot be proven") from None
    if safe_server["id"] != server_id:
        raise McpNetworkError("Nova server identity cannot be proven")
    if safe_server["status"] not in {"ACTIVE", "SHUTOFF"}:
        raise McpNetworkError("Nova server is not in a state that permits network attachment")
    network = validate_project_attachment_network(conn, project_id=project_id, network_id=network_id)
    return {"server_id": server_id, "server_status": str(safe_server["status"]), **network}


def _attach_server_network(conn: Any, *, project_id: str, server_id: str, network_id: str) -> dict[str, str | None]:
    _prepare_server_network_attach(conn, project_id=project_id, server_id=server_id, network_id=network_id)
    check_mutation_dispatch()
    interface = conn.compute.create_server_interface(server_id, net_id=network_id)
    interface_network_id = _field(interface, "net_id")
    sdk_network_id = _field(interface, "network_id")
    if (
        (interface_network_id is None and sdk_network_id is None)
        or (interface_network_id is not None and interface_network_id != network_id)
        or (sdk_network_id is not None and sdk_network_id != network_id)
    ):
        raise McpNetworkError("Nova server interface network identity cannot be proven")
    port_id = _required_text(interface, "port_id")
    port = conn.network.get_port(port_id)
    if port is None:
        raise McpNetworkError("Neutron attachment port was not found")
    if _required_text(port, "id") != port_id:
        raise McpNetworkError("Neutron attachment port identity cannot be proven")
    owners = (_field(port, "project_id"), _field(port, "tenant_id"))
    if not any(owner == project_id for owner in owners) or any(
        owner is not None and owner != project_id for owner in owners
    ):
        raise McpNetworkError("Neutron attachment port ownership cannot be proven")
    if _field(port, "network_id") != network_id or _field(port, "device_id") != server_id:
        raise McpNetworkError("Neutron attachment port network or server identity cannot be proven")
    mac_address = _field(port, "mac_address")
    if mac_address is None:
        mac_address = _field(interface, "mac_addr")
    if mac_address is None:
        mac_address = _field(interface, "mac_address")
    if mac_address is not None and (
        not isinstance(mac_address, str) or not mac_address or len(mac_address) > _MAX_TEXT
    ):
        raise McpNetworkError("Neutron attachment port MAC address is malformed")
    return {
        "server_id": server_id,
        "network_id": network_id,
        "port_id": port_id,
        "mac_address": mac_address,
        "requested_action": "attach_network",
    }


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


async def preview_project_server_network_attach(
    conn: Any, *, project_id: str, server_id: str, network_id: str
) -> dict[str, str]:
    """Read current attachment eligibility without creating or reusing a port."""
    try:
        return await run_sdk(
            _prepare_server_network_attach,
            conn,
            project_id=project_id,
            server_id=server_id,
            network_id=network_id,
        )
    except McpNetworkError:
        raise
    except Exception:
        raise McpNetworkError("Nova server network attachment is unavailable") from None


async def request_project_server_network_attach(
    conn: Any, *, project_id: str, server_id: str, network_id: str
) -> dict[str, str | None]:
    """Revalidate, create one interface, and prove its resulting exact-project port."""
    try:
        return await run_sdk(
            _attach_server_network,
            conn,
            project_id=project_id,
            server_id=server_id,
            network_id=network_id,
        )
    except McpNetworkError:
        raise
    except Exception:
        raise McpNetworkError("Nova server network attachment is unavailable") from None
