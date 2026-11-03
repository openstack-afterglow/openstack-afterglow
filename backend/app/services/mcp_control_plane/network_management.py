"""Bounded tenant Neutron management with provider proofs and revision fences."""

from __future__ import annotations

from collections.abc import Mapping
from ipaddress import ip_address, ip_network
from itertools import islice
from typing import Any
from urllib.parse import quote
from uuid import UUID

from openstack.resource import Body, Resource

from app.services.mcp_control_plane.network import McpNetworkError
from app.services.mcp_control_plane.sdk import check_mutation_dispatch, run_sdk

_MAX_FIXED_IPS = 32
_MAX_GROUPS = 32


def _field(resource: Any, name: str) -> Any:
    # Descriptors coerce values and supply defaults: neither is provider proof.
    if isinstance(resource, Resource):
        descriptor = getattr(type(resource), name, None)
        if isinstance(descriptor, Body):
            return resource._body.attributes.get(descriptor.name)
        return None
    if isinstance(resource, Mapping):
        return resource.get(name)
    return getattr(resource, name, None)


def _alias(resource: Any, *names: str) -> Any:
    values = [_field(resource, name) for name in names if _field(resource, name) is not None]
    if values and any(value != values[0] or type(value) is not type(values[0]) for value in values):
        raise McpNetworkError("Neutron response aliases contradict one another")
    return values[0] if values else None


def _text(value: Any, label: str, *, maximum: int = 255, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or len(value) > maximum or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise McpNetworkError(f"Neutron {label} is malformed")
    return value


def _id(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise McpNetworkError(f"Neutron {label} identity is malformed")
    try:
        UUID(value)
    except ValueError:
        raise McpNetworkError(f"Neutron {label} identity is malformed") from None
    return value


def _owner(resource: Any) -> str:
    value = _alias(resource, "project_id", "tenant_id")
    if not isinstance(value, str) or not value:
        raise McpNetworkError("Neutron ownership cannot be proven")
    return value


def _owned(resource: Any, project_id: str) -> None:
    if _owner(resource) != project_id:
        raise McpNetworkError("Neutron ownership cannot be proven")


def _identity(resource: Any, resource_id: str) -> None:
    if resource is None or _field(resource, "id") != resource_id:
        raise McpNetworkError("Neutron resource identity cannot be proven")


def _flag(resource: Any, *names: str) -> bool:
    value = _alias(resource, *names)
    if type(value) is not bool:
        raise McpNetworkError("Neutron network visibility cannot be proven")
    return value


def _raw_exact_resource(
    proxy: Any, path: str, *, resource_key: str, resource_id: str, microversion: str | None = None
) -> Mapping[str, Any]:
    """Read original native JSON, stopping new I/O once its owned call expires."""
    options = dict(redirect=False, allow_reauth=False, raise_exc=False, connect_retries=0, status_code_retries=0)
    if microversion is not None:
        options["microversion"] = microversion
    check_mutation_dispatch()
    response = proxy.get(path, **options)
    if type(response.status_code) is not int or response.status_code != 200:
        raise McpNetworkError("Native exact resource is unavailable")
    body = response.json()
    resource = body.get(resource_key) if isinstance(body, Mapping) else None
    if not isinstance(resource, Mapping):
        raise McpNetworkError("Native exact resource response is malformed")
    _identity(resource, resource_id)
    return resource


def _raw_resource(conn: Any, collection: str, resource_id: str) -> Mapping[str, Any]:
    """Read Neutron JSON without SDK fields merged with request ID/owner seeds."""
    singular = {"networks": "network", "subnets": "subnet", "ports": "port", "security-groups": "security_group"}
    if collection not in singular:
        raise McpNetworkError("Neutron resource collection is unsupported")
    _id(resource_id, singular[collection])
    return _raw_exact_resource(
        conn.network,
        f"/{collection}/{quote(resource_id, safe='')}",
        resource_key=singular[collection],
        resource_id=resource_id,
    )


def _network(
    conn: Any, project_id: str, network_id: str, *, ordinary: bool = False, attachment: bool = False
) -> tuple[Any, dict[str, Any]]:
    _id(network_id, "network")
    network = _raw_resource(conn, "networks", network_id)
    _identity(network, network_id)
    owner = _owner(network)
    shared = _flag(network, "is_shared", "shared")
    external = _flag(network, "is_router_external", "router:external", "is_external")
    if owner != project_id and not shared:
        raise McpNetworkError("Neutron network ownership or shared authority cannot be proven")
    if ordinary and (owner != project_id or shared or external):
        raise McpNetworkError("Neutron shared, external or foreign network cannot be mutated")
    status = _field(network, "status")
    if status not in {"ACTIVE", "DOWN", "ERROR"}:
        raise McpNetworkError("Neutron network state cannot be proven")
    if attachment and (status != "ACTIVE" or _alias(network, "is_admin_state_up", "admin_state_up") is not True):
        raise McpNetworkError("Neutron network is not active for attachment")
    return network, {
        "id": network_id,
        "name": _text(_field(network, "name"), "name", nullable=True),
        "status": status,
        "is_shared": shared,
        "is_external": external,
        "visibility": "owned" if owner == project_id else "shared",
    }


def _revision(conn: Any, resource: Any) -> int:
    revision = _field(resource, "revision_number")
    if type(revision) is not int or revision < 0:
        raise McpNetworkError("Neutron revision precondition cannot be proven")
    extension = conn.network.find_extension("revision-if-match", ignore_missing=True)
    if extension is None or _field(extension, "alias") != "revision-if-match":
        raise McpNetworkError("Neutron revision precondition is unsupported")
    return revision


def _attributes(attributes: Any, allowed: set[str], *, required: set[str] | None = None) -> dict[str, Any]:
    if (
        not isinstance(attributes, Mapping)
        or not attributes
        or set(attributes) - allowed
        or (required or set()) - set(attributes)
    ):
        raise McpNetworkError("Neutron mutation attributes are missing or unsupported")
    result = dict(attributes)
    for key in ("name", "description"):
        if key in result:
            result[key] = _text(result[key], key, maximum=1024 if key == "description" else 255)
    for key in ("admin_state_up", "enable_dhcp"):
        if key in result and type(result[key]) is not bool:
            raise McpNetworkError(f"Neutron {key} must be a boolean")
    return result


def _sdk_attributes(attributes: dict[str, Any]) -> dict[str, Any]:
    # SDK Body names differ from the JSON/registry names; explicit null survives.
    aliases = {"admin_state_up": "is_admin_state_up", "enable_dhcp": "is_dhcp_enabled"}
    return {aliases.get(key, key): value for key, value in attributes.items()}


def _cidr(value: Any) -> Any:
    if not isinstance(value, str):
        raise McpNetworkError("Neutron subnet CIDR is malformed")
    try:
        network = ip_network(value, strict=True)
    except ValueError:
        raise McpNetworkError("Neutron subnet CIDR is malformed") from None
    if str(network) != value:
        raise McpNetworkError("Neutron subnet CIDR must be canonical")
    return network


def _address(value: Any, network: Any, *, inside: bool) -> str:
    if not isinstance(value, str) or "%" in value:
        raise McpNetworkError("Neutron IP address is malformed")
    try:
        address = ip_address(value)
    except ValueError:
        raise McpNetworkError("Neutron IP address is malformed") from None
    if address.version != network.version or (inside and address not in network):
        raise McpNetworkError("Neutron IP address family or subnet does not match")
    if (
        inside
        and network.version == 4
        and network.prefixlen < 31
        and address in (network.network_address, network.broadcast_address)
    ):
        raise McpNetworkError("Neutron IP address is not a usable subnet host")
    return str(address)


def _subnet_addresses(attributes: dict[str, Any], network: Any) -> None:
    if "gateway_ip" in attributes and attributes["gateway_ip"] is not None:
        attributes["gateway_ip"] = _address(attributes["gateway_ip"], network, inside=True)
    if "dns_nameservers" in attributes:
        servers = attributes["dns_nameservers"]
        if not isinstance(servers, list) or len(servers) > 16:
            raise McpNetworkError("Neutron DNS nameservers are malformed")
        attributes["dns_nameservers"] = [_address(value, network, inside=False) for value in servers]


def _subnet(
    conn: Any, project_id: str, subnet_id: str, *, parent: dict[str, Any] | None = None
) -> tuple[Any, dict[str, Any]]:
    _id(subnet_id, "subnet")
    subnet = _raw_resource(conn, "subnets", subnet_id)
    _identity(subnet, subnet_id)
    network_id = _id(_field(subnet, "network_id"), "network")
    if parent is None:
        _, parent = _network(conn, project_id, network_id, ordinary=True)
        _owned(subnet, project_id)
    elif network_id != parent["id"] or (
        _owner(subnet) != project_id and not (parent["is_shared"] and _owner(subnet) == parent["owner_id"])
    ):
        raise McpNetworkError("Neutron fixed subnet ownership or parent does not match")
    network = _cidr(_field(subnet, "cidr"))
    version = _field(subnet, "ip_version")
    if type(version) is not int or version != network.version:
        raise McpNetworkError("Neutron subnet IP version does not match CIDR")
    gateway = _field(subnet, "gateway_ip")
    if gateway is not None:
        gateway = _address(gateway, network, inside=True)
    return subnet, {
        "id": subnet_id,
        "name": _text(_field(subnet, "name"), "name", nullable=True),
        "network_id": network_id,
        "cidr": str(network),
        "ip_version": version,
        "gateway_ip": gateway,
    }


def _groups(conn: Any, project_id: str, values: Any) -> list[str]:
    if not isinstance(values, list) or len(values) > _MAX_GROUPS:
        raise McpNetworkError("Neutron security group IDs are malformed")
    result: list[str] = []
    for value in values:
        group_id = _id(value, "security group")
        if group_id in result:
            raise McpNetworkError("Neutron security group IDs must be unique")
        group = _raw_resource(conn, "security-groups", group_id)
        _identity(group, group_id)
        _owned(group, project_id)
        result.append(group_id)
    return result


def _fixed_ips(
    conn: Any, project_id: str, parent: dict[str, Any], values: Any, *, output: bool = False
) -> list[dict[str, str]]:
    if not isinstance(values, list) or len(values) > _MAX_FIXED_IPS:
        raise McpNetworkError("Neutron fixed IP list is malformed")
    result: list[dict[str, str]] = []
    for value in values:
        if not isinstance(value, Mapping) or set(value) - {"subnet_id", "ip_address"} or "subnet_id" not in value:
            raise McpNetworkError("Neutron fixed IP attributes are malformed")
        subnet_id = _id(value["subnet_id"], "subnet")
        _, subnet = _subnet(conn, project_id, subnet_id, parent=parent)
        safe = {"subnet_id": subnet_id}
        if "ip_address" in value:
            safe["ip_address"] = _address(value["ip_address"], _cidr(subnet["cidr"]), inside=True)
        elif output:
            raise McpNetworkError("Neutron fixed IP address is missing")
        if safe in result:
            raise McpNetworkError("Neutron fixed IP list contains duplicates")
        result.append(safe)
    return result


def _port_parent(conn: Any, project_id: str, network_id: str, *, attachment: bool = False) -> dict[str, Any]:
    resource, safe = _network(conn, project_id, network_id, attachment=attachment)
    return {**safe, "owner_id": _owner(resource)}


def _safe_port(conn: Any, project_id: str, port: Any, *, port_id: str | None = None) -> dict[str, Any]:
    resource_id = _id(_field(port, "id"), "port")
    if port_id is not None:
        _identity(port, port_id)
    _owned(port, project_id)
    network_id = _id(_field(port, "network_id"), "network")
    parent = _port_parent(conn, project_id, network_id)
    state = _field(port, "status")
    if state not in {"ACTIVE", "DOWN", "BUILD", "ERROR"}:
        raise McpNetworkError("Neutron port state cannot be proven")
    admin = _alias(port, "is_admin_state_up", "admin_state_up")
    if type(admin) is not bool:
        raise McpNetworkError("Neutron port administrative state cannot be proven")
    return {
        "id": resource_id,
        "name": _text(_field(port, "name"), "name", nullable=True),
        "description": _text(_field(port, "description"), "description", maximum=1024, nullable=True),
        "network_id": network_id,
        "status": state,
        "admin_state_up": admin,
        "mac_address": _text(_field(port, "mac_address"), "MAC address", nullable=True),
        "device_id": _text(_field(port, "device_id"), "device ID", nullable=True),
        "device_owner": _text(_field(port, "device_owner"), "device owner", nullable=True),
        "fixed_ips": _fixed_ips(conn, project_id, parent, _field(port, "fixed_ips"), output=True),
        "security_group_ids": _groups(conn, project_id, _alias(port, "security_group_ids", "security_groups")),
    }


def _unbound(port: Any) -> None:
    # Missing device fields are not evidence of an empty binding.
    if _field(port, "device_id") != "" or _field(port, "device_owner") != "":
        raise McpNetworkError("Neutron bound or infrastructure port cannot be mutated")
    if _field(port, "status") not in {"DOWN", "ACTIVE"}:
        raise McpNetworkError("Neutron port is not in a mutable state")
    for names in (("binding_host_id", "binding:host_id"), ("binding_vif_type", "binding:vif_type")):
        value = _alias(port, *names)
        allowed = (None, "", "unbound") if "vif" in names[0] else (None, "")
        if value not in allowed:
            raise McpNetworkError("Neutron port binding evidence prevents mutation")
    for names in (
        ("binding_profile", "binding:profile"),
        ("binding_vif_details", "binding:vif_details"),
        ("trunk_details",),
    ):
        if _alias(port, *names) not in (None, {}):
            raise McpNetworkError("Neutron port binding or trunk evidence prevents mutation")
    if _alias(port, "binding_vnic_type", "binding:vnic_type") not in (None, "", "normal"):
        raise McpNetworkError("Neutron nonordinary port cannot be mutated")


def _prepare_network(
    conn: Any, project_id: str, attributes: Any, *, network_id: str | None = None
) -> tuple[dict[str, Any], dict[str, Any], int | None]:
    attrs = _attributes(
        attributes, {"name", "description", "admin_state_up"}, required={"name"} if network_id is None else None
    )
    if network_id is None:
        if not attrs["name"].strip():
            raise McpNetworkError("Neutron network name is missing")
        return attrs, {"name": attrs["name"], "attributes": attrs, "requested_action": "create"}, None
    resource, safe = _network(conn, project_id, network_id, ordinary=True)
    revision = _revision(conn, resource)
    return attrs, {**safe, "attributes": attrs, "requested_action": "update"}, revision


def _create_network(conn: Any, *, project_id: str, attributes: Any, preview: bool) -> dict[str, Any]:
    attrs, safe, _ = _prepare_network(conn, project_id, attributes)
    if preview:
        return safe
    check_mutation_dispatch()
    resource = conn.network.create_network(
        project_id=project_id, is_shared=False, is_router_external=False, **_sdk_attributes(attrs)
    )
    resource_id = _id(_field(resource, "id"), "network")
    _, result = _network(conn, project_id, resource_id, ordinary=True)
    return {**result, "requested_action": "create"}


def _update_network(conn: Any, *, project_id: str, network_id: str, attributes: Any, preview: bool) -> dict[str, Any]:
    attrs, safe, revision = _prepare_network(conn, project_id, attributes, network_id=network_id)
    if preview:
        return safe
    check_mutation_dispatch()
    resource = conn.network.update_network(network_id, if_revision=revision, **_sdk_attributes(attrs))
    _identity(resource, network_id)
    _, result = _network(conn, project_id, network_id, ordinary=True)
    return {**result, "requested_action": "update"}


def _prepare_subnet(
    conn: Any, project_id: str, attributes: Any, *, subnet_id: str | None = None
) -> tuple[dict[str, Any], dict[str, Any], int | None]:
    if subnet_id is None:
        attrs = _attributes(
            attributes,
            {"network_id", "name", "cidr", "gateway_ip", "enable_dhcp", "dns_nameservers"},
            required={"network_id", "name", "cidr"},
        )
        _, parent = _network(conn, project_id, attrs["network_id"], ordinary=True)
        if not attrs["name"].strip():
            raise McpNetworkError("Neutron subnet name is missing")
        network = _cidr(attrs["cidr"])
        _subnet_addresses(attrs, network)
        return (
            attrs,
            {
                "network_id": parent["id"],
                "name": attrs["name"],
                "cidr": attrs["cidr"],
                "attributes": attrs,
                "requested_action": "create",
            },
            None,
        )
    attrs = _attributes(attributes, {"name", "description", "gateway_ip", "enable_dhcp", "dns_nameservers"})
    resource, safe = _subnet(conn, project_id, subnet_id)
    _subnet_addresses(attrs, _cidr(safe["cidr"]))
    revision = _revision(conn, resource)
    return attrs, {**safe, "attributes": attrs, "requested_action": "update"}, revision


def _create_subnet(conn: Any, *, project_id: str, attributes: Any, preview: bool) -> dict[str, Any]:
    attrs, safe, _ = _prepare_subnet(conn, project_id, attributes)
    if preview:
        return safe
    ip_version = _cidr(attrs["cidr"]).version
    check_mutation_dispatch()
    resource = conn.network.create_subnet(project_id=project_id, ip_version=ip_version, **_sdk_attributes(attrs))
    resource_id = _id(_field(resource, "id"), "subnet")
    _, result = _subnet(conn, project_id, resource_id)
    if result["network_id"] != attrs["network_id"] or result["cidr"] != attrs["cidr"]:
        raise McpNetworkError("Neutron created subnet identity or CIDR cannot be proven")
    return {**result, "requested_action": "create"}


def _update_subnet(conn: Any, *, project_id: str, subnet_id: str, attributes: Any, preview: bool) -> dict[str, Any]:
    attrs, safe, revision = _prepare_subnet(conn, project_id, attributes, subnet_id=subnet_id)
    if preview:
        return safe
    check_mutation_dispatch()
    resource = conn.network.update_subnet(subnet_id, if_revision=revision, **_sdk_attributes(attrs))
    _identity(resource, subnet_id)
    _, result = _subnet(conn, project_id, subnet_id)
    if result["network_id"] != safe["network_id"] or result["cidr"] != safe["cidr"]:
        raise McpNetworkError("Neutron updated subnet parent or CIDR changed")
    return {**result, "requested_action": "update"}


def _prepare_port(
    conn: Any, project_id: str, attributes: Any = None, *, port_id: str | None = None, delete: bool = False
) -> tuple[dict[str, Any], dict[str, Any], int | None]:
    allowed = {"name", "description", "admin_state_up", "fixed_ips", "security_group_ids"}
    if port_id is None:
        attrs = _attributes(attributes, allowed | {"network_id"}, required={"network_id"})
        parent = _port_parent(conn, project_id, attrs["network_id"], attachment=True)
        safe = {"network_id": parent["id"], "requested_action": "create"}
        revision = None
    else:
        _id(port_id, "port")
        resource = _raw_resource(conn, "ports", port_id)
        _identity(resource, port_id)
        _unbound(resource)
        safe = _safe_port(conn, project_id, resource, port_id=port_id)
        revision = _revision(conn, resource)
        if delete:
            return {}, {**safe, "requested_action": "delete"}, revision
        attrs = _attributes(attributes, allowed)
        parent = _port_parent(conn, project_id, safe["network_id"])
        safe["requested_action"] = "update"
    if "fixed_ips" in attrs:
        attrs["fixed_ips"] = _fixed_ips(conn, project_id, parent, attrs["fixed_ips"])
    if "security_group_ids" in attrs:
        attrs["security_group_ids"] = _groups(conn, project_id, attrs["security_group_ids"])
    return attrs, {**safe, "attributes": attrs}, revision


def _create_port(conn: Any, *, project_id: str, attributes: Any, preview: bool) -> dict[str, Any]:
    attrs, safe, _ = _prepare_port(conn, project_id, attributes)
    if preview:
        return safe
    check_mutation_dispatch()
    resource = conn.network.create_port(project_id=project_id, **_sdk_attributes(attrs))
    resource_id = _id(_field(resource, "id"), "port")
    result = _get_port(conn, project_id=project_id, port_id=resource_id)
    if result["network_id"] != attrs["network_id"]:
        raise McpNetworkError("Neutron created port parent cannot be proven")
    return {**result, "requested_action": "create"}


def _update_port(conn: Any, *, project_id: str, port_id: str, attributes: Any, preview: bool) -> dict[str, Any]:
    attrs, safe, revision = _prepare_port(conn, project_id, attributes, port_id=port_id)
    if preview:
        return safe
    check_mutation_dispatch()
    resource = conn.network.update_port(port_id, if_revision=revision, **_sdk_attributes(attrs))
    _identity(resource, port_id)
    result = _get_port(conn, project_id=project_id, port_id=port_id)
    if result["network_id"] != safe["network_id"]:
        raise McpNetworkError("Neutron updated port parent changed")
    return {**result, "requested_action": "update"}


def _delete_port(conn: Any, *, project_id: str, port_id: str, preview: bool) -> dict[str, Any]:
    _, safe, revision = _prepare_port(conn, project_id, port_id=port_id, delete=True)
    if not preview:
        check_mutation_dispatch()
        conn.network.delete_port(port_id, ignore_missing=False, if_revision=revision)
    return safe


def _get_port(conn: Any, *, project_id: str, port_id: str) -> dict[str, Any]:
    _id(port_id, "port")
    resource = _raw_resource(conn, "ports", port_id)
    _identity(resource, port_id)
    return _safe_port(conn, project_id, resource, port_id=port_id)


def _list_ports(conn: Any, *, project_id: str, limit: int, network_id: str | None) -> list[dict[str, Any]]:
    if type(limit) is not int or not 1 <= limit <= 100:
        raise McpNetworkError("Neutron port list limit is malformed")
    query: dict[str, Any] = {"project_id": project_id, "limit": limit}
    if network_id is not None:
        _port_parent(conn, project_id, network_id)
        query["network_id"] = network_id
    result = []
    check_mutation_dispatch()
    for resource in islice(conn.network.ports(**query), limit):
        check_mutation_dispatch()
        safe = _safe_port(conn, project_id, resource)
        if network_id is not None and safe["network_id"] != network_id:
            raise McpNetworkError("Neutron port network filter was not honored")
        result.append(safe)
    return result


async def _run(function: Any, conn: Any, **kwargs: Any) -> Any:
    try:
        return await run_sdk(function, conn, **kwargs)
    except McpNetworkError:
        raise
    except Exception as exc:
        raise McpNetworkError("Neutron management operation is unavailable") from exc


async def preview_project_network_create(conn: Any, *, project_id: str, attributes: dict[str, Any]) -> dict[str, Any]:
    return await _run(_create_network, conn, project_id=project_id, attributes=attributes, preview=True)


async def request_project_network_create(conn: Any, *, project_id: str, attributes: dict[str, Any]) -> dict[str, Any]:
    return await _run(_create_network, conn, project_id=project_id, attributes=attributes, preview=False)


async def preview_project_network_update(
    conn: Any, *, project_id: str, network_id: str, attributes: dict[str, Any]
) -> dict[str, Any]:
    return await _run(
        _update_network, conn, project_id=project_id, network_id=network_id, attributes=attributes, preview=True
    )


async def request_project_network_update(
    conn: Any, *, project_id: str, network_id: str, attributes: dict[str, Any]
) -> dict[str, Any]:
    return await _run(
        _update_network, conn, project_id=project_id, network_id=network_id, attributes=attributes, preview=False
    )


async def preview_project_subnet_create(conn: Any, *, project_id: str, attributes: dict[str, Any]) -> dict[str, Any]:
    return await _run(_create_subnet, conn, project_id=project_id, attributes=attributes, preview=True)


async def request_project_subnet_create(conn: Any, *, project_id: str, attributes: dict[str, Any]) -> dict[str, Any]:
    return await _run(_create_subnet, conn, project_id=project_id, attributes=attributes, preview=False)


async def preview_project_subnet_update(
    conn: Any, *, project_id: str, subnet_id: str, attributes: dict[str, Any]
) -> dict[str, Any]:
    return await _run(
        _update_subnet, conn, project_id=project_id, subnet_id=subnet_id, attributes=attributes, preview=True
    )


async def request_project_subnet_update(
    conn: Any, *, project_id: str, subnet_id: str, attributes: dict[str, Any]
) -> dict[str, Any]:
    return await _run(
        _update_subnet, conn, project_id=project_id, subnet_id=subnet_id, attributes=attributes, preview=False
    )


async def list_project_ports(
    conn: Any, *, project_id: str, limit: int, network_id: str | None = None
) -> list[dict[str, Any]]:
    return await _run(_list_ports, conn, project_id=project_id, limit=limit, network_id=network_id)


async def get_project_port(conn: Any, *, project_id: str, port_id: str) -> dict[str, Any]:
    return await _run(_get_port, conn, project_id=project_id, port_id=port_id)


async def preview_project_port_create(conn: Any, *, project_id: str, attributes: dict[str, Any]) -> dict[str, Any]:
    return await _run(_create_port, conn, project_id=project_id, attributes=attributes, preview=True)


async def request_project_port_create(conn: Any, *, project_id: str, attributes: dict[str, Any]) -> dict[str, Any]:
    return await _run(_create_port, conn, project_id=project_id, attributes=attributes, preview=False)


async def preview_project_port_update(
    conn: Any, *, project_id: str, port_id: str, attributes: dict[str, Any]
) -> dict[str, Any]:
    return await _run(_update_port, conn, project_id=project_id, port_id=port_id, attributes=attributes, preview=True)


async def request_project_port_update(
    conn: Any, *, project_id: str, port_id: str, attributes: dict[str, Any]
) -> dict[str, Any]:
    return await _run(_update_port, conn, project_id=project_id, port_id=port_id, attributes=attributes, preview=False)


async def preview_project_port_delete(conn: Any, *, project_id: str, port_id: str) -> dict[str, Any]:
    return await _run(_delete_port, conn, project_id=project_id, port_id=port_id, preview=True)


async def request_project_port_delete(conn: Any, *, project_id: str, port_id: str) -> dict[str, Any]:
    return await _run(_delete_port, conn, project_id=project_id, port_id=port_id, preview=False)
