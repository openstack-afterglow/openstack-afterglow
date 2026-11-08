"""Owned interface and security-group management through caller-scoped SDKs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import quote
from uuid import UUID

from app.services.mcp_control_plane.compute import McpComputeError, _safe_server
from app.services.mcp_control_plane.network import McpNetworkError, _field, _required_text
from app.services.mcp_control_plane.sdk import check_mutation_dispatch, run_sdk
from app.services.waygate_managed import WaygateManagedResourceError, require_server_not_waygate_managed


def _owner(resource: Any, *, project_id: str) -> None:
    owners = (_field(resource, "project_id"), _field(resource, "tenant_id"))
    if not any(owner == project_id for owner in owners) or any(
        owner is not None and owner != project_id for owner in owners
    ):
        raise McpNetworkError("Resource ownership cannot be proven")


def _identity(resource: Any, resource_id: str) -> None:
    if resource is None or _required_text(resource, "id") != resource_id:
        raise McpNetworkError("Resource identity cannot be proven")


def _raw_resource(conn: Any, collection: str, resource_id: str) -> Mapping[str, Any]:
    from app.services.mcp_control_plane.network_management import _raw_exact_resource

    singular = {"ports": "port", "networks": "network", "security-groups": "security_group", "servers": "server"}
    try:
        UUID(resource_id)
    except (ValueError, TypeError, AttributeError):
        raise McpNetworkError("Resource ID is malformed") from None
    proxy = conn.compute if collection == "servers" else conn.network
    return _raw_exact_resource(
        proxy,
        f"/{collection}/{quote(resource_id, safe='')}",
        resource_key=singular[collection],
        resource_id=resource_id,
    )


def _optional_text(resource: Any, name: str, *, maximum: int = 255) -> str | None:
    value = _field(resource, name)
    if value is not None and (not isinstance(value, str) or len(value) > maximum):
        raise McpNetworkError("Resource text is malformed")
    return value


def _security_group(resource: Any, *, project_id: str) -> dict[str, Any]:
    _owner(resource, project_id=project_id)
    return {
        "id": _required_text(resource, "id"),
        "name": _optional_text(resource, "name"),
        "description": _optional_text(resource, "description", maximum=1024),
    }


def _get_security_group(conn: Any, *, project_id: str, security_group_id: str) -> dict[str, Any]:
    resource = _raw_resource(conn, "security-groups", security_group_id)
    _identity(resource, security_group_id)
    return _security_group(resource, project_id=project_id)


def _list_security_groups(conn: Any, *, project_id: str, limit: int) -> list[dict[str, Any]]:
    if type(limit) is not int or not 1 <= limit <= 100:
        raise McpNetworkError("Security-group list limit is invalid")
    result = []
    check_mutation_dispatch()
    for resource in conn.network.security_groups(project_id=project_id, limit=limit):
        check_mutation_dispatch()
        result.append(_security_group(resource, project_id=project_id))
        if len(result) == limit:
            break
    return result


def _server(conn: Any, *, project_id: str, server_id: str) -> str:
    resource = _raw_resource(conn, "servers", server_id)
    _identity(resource, server_id)
    _owner(resource, project_id=project_id)
    try:
        safe = _safe_server(resource, project_id=project_id)
    except McpComputeError:
        raise McpNetworkError("Nova server data cannot be proven") from None
    # Interfaces and port security groups of a Waygate gateway are Waygate-only.
    require_server_not_waygate_managed(resource)
    if safe["status"] not in {"ACTIVE", "SHUTOFF"}:
        raise McpNetworkError("Nova server state does not permit interface management")
    # A stable status alone does not prove that a concurrent Nova task is absent.
    for name in ("task_state", "OS-EXT-STS:task_state"):
        if _field(resource, name) not in (None, ""):
            raise McpNetworkError("Nova server has an active transition")
    return str(safe["status"])


def _port(conn: Any, *, project_id: str, port_id: str) -> Any:
    resource = _raw_resource(conn, "ports", port_id)
    _identity(resource, port_id)
    _owner(resource, project_id=project_id)
    _required_text(resource, "network_id")
    if _field(resource, "status") not in {"ACTIVE", "DOWN"}:
        raise McpNetworkError("Neutron port state does not permit interface management")
    if _field(resource, "trunk_details") not in (None, {}):
        raise McpNetworkError("Neutron trunk infrastructure ports cannot be managed")
    return resource


def _boolean_alias(resource: Any, *names: str) -> bool | None:
    present = [_field(resource, name) for name in names if _field(resource, name) is not None]
    if any(type(value) is not bool or value != present[0] for value in present):
        raise McpNetworkError("Neutron boolean aliases are malformed or contradictory")
    return present[0] if present else None


def _attachment_network(conn: Any, *, project_id: str, network_id: str) -> None:
    resource = _raw_resource(conn, "networks", network_id)
    _identity(resource, network_id)
    owners = [_field(resource, name) for name in ("project_id", "tenant_id")]
    present = [owner for owner in owners if owner is not None]
    if not present or any(not isinstance(owner, str) or not owner for owner in present):
        raise McpNetworkError("Neutron network ownership cannot be proven")
    if len(set(present)) != 1:
        raise McpNetworkError("Neutron network ownership aliases contradict")
    shared = _boolean_alias(resource, "is_shared", "shared") is True
    if present[0] != project_id and not shared:
        raise McpNetworkError("Neutron network attachment authority cannot be proven")
    if _field(resource, "status") != "ACTIVE":
        raise McpNetworkError("Neutron network is not active for attachment")
    if _boolean_alias(resource, "is_admin_state_up", "admin_state_up") is False:
        raise McpNetworkError("Neutron network is administratively disabled")


def _unbound(port: Any) -> None:
    if _field(port, "device_id") != "" or _field(port, "device_owner") != "":
        raise McpNetworkError("Neutron port unbound device identity cannot be proven")
    for name in (
        "binding_host_id",
        "binding:host_id",
        "binding_profile",
        "binding:profile",
        "binding_vif_details",
        "binding:vif_details",
    ):
        if _field(port, name) not in (None, "", {}):
            raise McpNetworkError("Neutron port has binding infrastructure evidence")
    for name in ("binding_vif_type", "binding:vif_type"):
        if _field(port, name) not in (None, "", "unbound"):
            raise McpNetworkError("Neutron port has a bound or failed VIF")
    types = [_field(port, name) for name in ("binding_vnic_type", "binding:vnic_type")]
    present = [value for value in types if value is not None]
    if any(value != "normal" for value in present):
        raise McpNetworkError("Neutron nonordinary VNIC ports cannot be attached")
    if _field(port, "status") != "DOWN":
        raise McpNetworkError("Unbound Neutron port must be down")


def _bound(port: Any, *, server_id: str) -> None:
    owner = _field(port, "device_owner")
    if _field(port, "device_id") != server_id or not isinstance(owner, str) or not owner.startswith("compute:"):
        raise McpNetworkError("Neutron compute binding to this server cannot be proven")
    if owner == "compute:":
        raise McpNetworkError("Neutron compute device owner is malformed")
    for name in ("binding_vif_type", "binding:vif_type"):
        if _field(port, name) in ("unbound", "binding_failed"):
            raise McpNetworkError("Neutron compute binding is unsettled")


def _interface_identity(interface: Any, *, server_id: str, port_id: str, network_id: str) -> None:
    if _field(interface, "port_id") != port_id:
        raise McpNetworkError("Nova interface port identity cannot be proven")
    networks = [_field(interface, name) for name in ("net_id", "network_id")]
    if not any(value == network_id for value in networks) or any(
        value is not None and value != network_id for value in networks
    ):
        raise McpNetworkError("Nova interface network identity cannot be proven")
    if _field(interface, "server_id") not in (None, server_id):
        raise McpNetworkError("Nova interface server identity contradicts")


def _actual_interface(conn: Any, *, server_id: str, port_id: str, network_id: str) -> Any:
    # Listing avoids get_server_interface seeding the requested port_id into an
    # SDK resource when the provider omits that identity from its response.
    found = None
    for index, interface in enumerate(conn.compute.server_interfaces(server_id)):
        if index >= 1000:
            raise McpNetworkError("Nova interface inventory exceeds the bounded proof limit")
        if _field(interface, "port_id") == port_id:
            if found is not None:
                raise McpNetworkError("Nova interface identity is ambiguous")
            _interface_identity(interface, server_id=server_id, port_id=port_id, network_id=network_id)
            found = interface
    if found is None:
        raise McpNetworkError("Nova exact server interface was not found")
    return found


def _summary(port: Any, *, server_id: str, port_id: str, action: str) -> dict[str, Any]:
    return {
        "server_id": server_id,
        "network_id": _required_text(port, "network_id"),
        "port_id": port_id,
        "mac_address": _optional_text(port, "mac_address"),
        "requested_action": action,
    }


def _prepare_interface(conn: Any, *, project_id: str, server_id: str, port_id: str, attach: bool) -> dict[str, Any]:
    status = _server(conn, project_id=project_id, server_id=server_id)
    port = _port(conn, project_id=project_id, port_id=port_id)
    network_id = _required_text(port, "network_id")
    if attach:
        _unbound(port)
        _attachment_network(conn, project_id=project_id, network_id=network_id)
    else:
        _bound(port, server_id=server_id)
        _actual_interface(conn, server_id=server_id, port_id=port_id, network_id=network_id)
    action = "attach_interface" if attach else "detach_interface"
    return {**_summary(port, server_id=server_id, port_id=port_id, action=action), "server_status": status}


def _request_interface(conn: Any, *, project_id: str, server_id: str, port_id: str, attach: bool) -> dict[str, Any]:
    prepared = _prepare_interface(conn, project_id=project_id, server_id=server_id, port_id=port_id, attach=attach)
    network_id = prepared["network_id"]
    if attach:
        check_mutation_dispatch()
        interface = conn.compute.create_server_interface(server_id, port_id=port_id)
        _interface_identity(interface, server_id=server_id, port_id=port_id, network_id=network_id)
        _actual_interface(conn, server_id=server_id, port_id=port_id, network_id=network_id)
        port = _port(conn, project_id=project_id, port_id=port_id)
        _bound(port, server_id=server_id)
        if _field(port, "network_id") != network_id:
            raise McpNetworkError("Attached Neutron port network identity changed")
        return _summary(port, server_id=server_id, port_id=port_id, action="attach_interface")
    check_mutation_dispatch()
    conn.compute.delete_server_interface(port_id, server_id, ignore_missing=False)
    # Nova owns whether an auto-created port is removed. Never delete it here.
    return {key: value for key, value in prepared.items() if key != "server_status"}


def _group_ids(value: Any) -> list[str]:
    if not isinstance(value, list) or len(value) > 32:
        raise McpNetworkError("Security-group IDs must be a bounded list")
    result = []
    for item in value:
        if not isinstance(item, str):
            raise McpNetworkError("Security-group ID is malformed")
        try:
            normalized = str(UUID(item))
        except ValueError:
            raise McpNetworkError("Security-group ID is malformed") from None
        if normalized != item or item in result:
            raise McpNetworkError("Security-group IDs must be unique canonical UUIDs")
        result.append(item)
    return result


def _current_groups(port: Any) -> list[str]:
    values = [_field(port, name) for name in ("security_group_ids", "security_groups")]
    present = [value for value in values if value is not None]
    if not present:
        raise McpNetworkError("Current port security groups cannot be proven")
    groups = _group_ids(present[0])
    if any(set(_group_ids(value)) != set(groups) for value in present[1:]):
        raise McpNetworkError("Current port security-group aliases contradict")
    return groups


def _port_security(port: Any) -> bool:
    values = [_field(port, name) for name in ("is_port_security_enabled", "port_security_enabled")]
    present = [value for value in values if value is not None]
    if not present or any(type(value) is not bool or value != present[0] for value in present):
        raise McpNetworkError("Port security setting cannot be proven")
    return present[0]


def _prepare_groups(
    conn: Any, *, project_id: str, server_id: str, port_id: str, security_group_ids: list[str]
) -> tuple[dict[str, Any], int, bool]:
    desired = _group_ids(security_group_ids)
    status = _server(conn, project_id=project_id, server_id=server_id)
    port = _port(conn, project_id=project_id, port_id=port_id)
    _bound(port, server_id=server_id)
    network_id = _required_text(port, "network_id")
    _actual_interface(conn, server_id=server_id, port_id=port_id, network_id=network_id)
    current = _current_groups(port)
    enabled = _port_security(port)
    if desired and not enabled:
        raise McpNetworkError("Security groups cannot be assigned to a port with security disabled")
    revision = _field(port, "revision_number")
    if type(revision) is not int or revision < 0:
        raise McpNetworkError("Neutron port revision CAS cannot be proven")
    extension = conn.network.find_extension("revision-if-match", ignore_missing=True)
    if extension is None or _field(extension, "alias") != "revision-if-match":
        raise McpNetworkError("Neutron revision-if-match support cannot be proven")
    for group_id in desired:
        _get_security_group(conn, project_id=project_id, security_group_id=group_id)
    return (
        {
            "server_id": server_id,
            "port_id": port_id,
            "network_id": network_id,
            "server_status": status,
            "security_group_ids": desired,
            "current_security_group_ids": current,
            "requested_action": "set_security_groups",
        },
        revision,
        enabled,
    )


def _preview_groups(conn: Any, **kwargs: Any) -> dict[str, Any]:
    prepared, _, _ = _prepare_groups(conn, **kwargs)
    return prepared


def _request_groups(
    conn: Any, *, project_id: str, server_id: str, port_id: str, security_group_ids: list[str]
) -> dict[str, Any]:
    prepared, revision, enabled = _prepare_groups(
        conn, project_id=project_id, server_id=server_id, port_id=port_id, security_group_ids=security_group_ids
    )
    check_mutation_dispatch()
    conn.network.update_port(port_id, if_revision=revision, security_group_ids=prepared["security_group_ids"])
    port = _port(conn, project_id=project_id, port_id=port_id)
    _bound(port, server_id=server_id)
    if _field(port, "network_id") != prepared["network_id"]:
        raise McpNetworkError("Updated port network identity changed")
    if set(_current_groups(port)) != set(prepared["security_group_ids"]) or _port_security(port) != enabled:
        raise McpNetworkError("Updated port groups or preserved port security cannot be proven")
    return {key: prepared[key] for key in ("server_id", "port_id", "security_group_ids", "requested_action")}


async def _invoke(function: Any, conn: Any, **kwargs: Any) -> Any:
    try:
        return await run_sdk(function, conn, **kwargs)
    except (McpNetworkError, WaygateManagedResourceError):
        raise
    except Exception as exc:
        raise McpNetworkError("Instance network management is unavailable") from exc


async def list_project_security_groups(conn: Any, *, project_id: str, limit: int) -> list[dict[str, Any]]:
    return await _invoke(_list_security_groups, conn, project_id=project_id, limit=limit)


async def get_project_security_group(conn: Any, *, project_id: str, security_group_id: str) -> dict[str, Any]:
    return await _invoke(_get_security_group, conn, project_id=project_id, security_group_id=security_group_id)


async def preview_project_server_interface_attach(
    conn: Any, *, project_id: str, server_id: str, port_id: str
) -> dict[str, Any]:
    return await _invoke(
        _prepare_interface, conn, project_id=project_id, server_id=server_id, port_id=port_id, attach=True
    )


async def request_project_server_interface_attach(
    conn: Any, *, project_id: str, server_id: str, port_id: str
) -> dict[str, Any]:
    return await _invoke(
        _request_interface, conn, project_id=project_id, server_id=server_id, port_id=port_id, attach=True
    )


async def preview_project_server_interface_detach(
    conn: Any, *, project_id: str, server_id: str, port_id: str
) -> dict[str, Any]:
    return await _invoke(
        _prepare_interface, conn, project_id=project_id, server_id=server_id, port_id=port_id, attach=False
    )


async def request_project_server_interface_detach(
    conn: Any, *, project_id: str, server_id: str, port_id: str
) -> dict[str, Any]:
    return await _invoke(
        _request_interface, conn, project_id=project_id, server_id=server_id, port_id=port_id, attach=False
    )


async def preview_project_server_security_groups_set(
    conn: Any, *, project_id: str, server_id: str, port_id: str, security_group_ids: list[str]
) -> dict[str, Any]:
    return await _invoke(
        _preview_groups,
        conn,
        project_id=project_id,
        server_id=server_id,
        port_id=port_id,
        security_group_ids=security_group_ids,
    )


async def request_project_server_security_groups_set(
    conn: Any, *, project_id: str, server_id: str, port_id: str, security_group_ids: list[str]
) -> dict[str, Any]:
    return await _invoke(
        _request_groups,
        conn,
        project_id=project_id,
        server_id=server_id,
        port_id=port_id,
        security_group_ids=security_group_ids,
    )
