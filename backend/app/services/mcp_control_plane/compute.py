"""Project-owned, redacted Nova adapters for the consumer MCP registry."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

from app.models.compute import FlavorInfo
from app.services import flavor_eligibility
from app.services.instance_names import ensure_unique_instance_name, normalize_requested_instance_name
from app.services.mcp_control_plane.sdk import _drain, check_mutation_dispatch, run_sdk


class McpComputeError(ValueError):
    """Nova data is unavailable or does not prove current-project ownership."""


def _field(resource: Any, name: str) -> Any:
    if isinstance(resource, Mapping):
        return resource.get(name)
    return getattr(resource, name, None)


def _required_string(resource: Any, name: str) -> str:
    value = _field(resource, name)
    if not isinstance(value, str) or not value:
        raise McpComputeError(f"Nova server {name} is missing")
    return value


def _optional_timestamp(resource: Any, *names: str) -> str | None:
    for name in names:
        value = _field(resource, name)
        if value is None:
            continue
        if isinstance(value, str):
            return value
        if hasattr(value, "isoformat"):
            return value.isoformat()
        raise McpComputeError(f"Nova server {name} is malformed")
    return None


def _safe_server(resource: Any, *, project_id: str) -> dict[str, str | None]:
    owner_project_id = _field(resource, "project_id") or _field(resource, "tenant_id")
    if owner_project_id != project_id:
        raise McpComputeError("Nova server ownership cannot be proven")
    return {
        "id": _required_string(resource, "id"),
        "name": _required_string(resource, "name"),
        "status": _required_string(resource, "status"),
        "created_at": _optional_timestamp(resource, "created_at", "created"),
        "updated_at": _optional_timestamp(resource, "updated_at", "updated"),
    }


def _list_servers(conn: Any, *, project_id: str, limit: int) -> list[dict[str, str | None]]:
    servers = conn.compute.servers(details=True, project_id=project_id)
    safe_servers: list[dict[str, str | None]] = []
    for server in servers:
        safe_servers.append(_safe_server(server, project_id=project_id))
        if len(safe_servers) == limit:
            break
    return safe_servers


def _server_overview(conn: Any, *, project_id: str) -> dict[str, int]:
    counts = {"total": 0, "active": 0, "shutoff": 0, "error": 0}
    for server in conn.compute.servers(details=True, project_id=project_id):
        safe_server = _safe_server(server, project_id=project_id)
        counts["total"] += 1
        if safe_server["status"] == "ACTIVE":
            counts["active"] += 1
        elif safe_server["status"] == "SHUTOFF":
            counts["shutoff"] += 1
        elif safe_server["status"] == "ERROR":
            counts["error"] += 1
    return counts


def _get_server(conn: Any, *, project_id: str, server_id: str) -> dict[str, str | None]:
    server = conn.compute.get_server(server_id)
    if server is None:
        raise McpComputeError("Nova server was not found")
    return _safe_server(server, project_id=project_id)


_SERVER_ACTIONS: dict[str, tuple[frozenset[str], str, dict[str, Any]]] = {
    "start": (frozenset({"SHUTOFF"}), "start_server", {}),
    "stop": (frozenset({"ACTIVE"}), "stop_server", {}),
    "reboot": (frozenset({"ACTIVE"}), "reboot_server", {"reboot_type": "SOFT"}),
    "shelve": (frozenset({"ACTIVE"}), "shelve_server", {}),
    "unshelve": (frozenset({"SHELVED", "SHELVED_OFFLOADED"}), "unshelve_server", {}),
}


def _prepare_server_action(conn: Any, *, project_id: str, server_id: str, action: str) -> dict[str, str | None]:
    server = conn.compute.get_server(server_id)
    if server is None:
        raise McpComputeError("Nova server was not found")
    safe_server = _safe_server(server, project_id=project_id)
    action_spec = _SERVER_ACTIONS.get(action)
    if action_spec is None:
        raise McpComputeError("Nova server action is invalid")
    allowed_statuses, _, _ = action_spec
    if safe_server["status"] not in allowed_statuses:
        raise McpComputeError("Nova server is not in a state that permits this action")
    return {**safe_server, "requested_action": action}


def _action_server(conn: Any, *, project_id: str, server_id: str, action: str) -> dict[str, str | None]:
    safe_server = _prepare_server_action(conn, project_id=project_id, server_id=server_id, action=action)
    _, method_name, arguments = _SERVER_ACTIONS[action]
    action_method = getattr(conn.compute, method_name, None)
    if not callable(action_method):
        raise McpComputeError("Nova server action is unavailable")
    check_mutation_dispatch()
    action_method(server_id, **arguments)
    return safe_server


def _checked_server_delete(server: Any, *, project_id: str) -> dict[str, str | None]:
    if server is None:
        raise McpComputeError("Nova server was not found")
    safe_server = _safe_server(server, project_id=project_id)
    if safe_server["status"] == "DELETED":
        raise McpComputeError("Nova server is already deleted")
    return {**safe_server, "requested_action": "delete"}


def _prepare_server_delete(conn: Any, *, project_id: str, server_id: str) -> dict[str, str | None]:
    return _checked_server_delete(conn.compute.get_server(server_id), project_id=project_id)


def _delete_server(conn: Any, server: Any, *, project_id: str, server_id: str) -> dict[str, str | None]:
    safe_server = _checked_server_delete(server, project_id=project_id)
    check_mutation_dispatch()
    conn.compute.delete_server(server_id, ignore_missing=False, force=False)
    return safe_server


def _safe_server_interface(conn: Any, resource: Any, *, project_id: str) -> dict[str, str | None]:
    port_id = _required_string(resource, "port_id")
    port = conn.network.get_port(port_id)
    if port is None:
        raise McpComputeError("Neutron port was not found")
    owner_project_id = _field(port, "project_id") or _field(port, "tenant_id")
    if owner_project_id != project_id:
        raise McpComputeError("Neutron port ownership cannot be proven")
    mac_address = _field(resource, "mac_addr")
    if mac_address is not None and (not isinstance(mac_address, str) or not mac_address or len(mac_address) > 255):
        raise McpComputeError("Nova server interface MAC address is malformed")
    return {"port_id": port_id, "mac_address": mac_address}


def _list_server_interfaces(conn: Any, *, project_id: str, server_id: str, limit: int) -> list[dict[str, str | None]]:
    server = conn.compute.get_server(server_id)
    if server is None:
        raise McpComputeError("Nova server was not found")
    _safe_server(server, project_id=project_id)
    interfaces = conn.compute.server_interfaces(server_id)
    safe_interfaces: list[dict[str, str | None]] = []
    for interface in interfaces:
        safe_interfaces.append(_safe_server_interface(conn, interface, project_id=project_id))
        if len(safe_interfaces) == limit:
            break
    return safe_interfaces


def _list_server_volume_attachment_ids(conn: Any, *, project_id: str, server_id: str, limit: int) -> list[str]:
    server = conn.compute.get_server(server_id)
    if server is None:
        raise McpComputeError("Nova server was not found")
    _safe_server(server, project_id=project_id)
    volume_ids: list[str] = []
    for attachment in conn.compute.volume_attachments(server_id):
        volume_id = _required_string(attachment, "volume_id")
        if volume_id not in volume_ids:
            volume_ids.append(volume_id)
        if len(volume_ids) == limit:
            break
    return volume_ids


async def list_project_servers(conn: Any, *, project_id: str, limit: int) -> list[dict[str, str | None]]:
    """List only servers whose provider response independently proves ownership."""
    try:
        return await run_sdk(_list_servers, conn, project_id=project_id, limit=limit)
    except McpComputeError:
        raise
    except Exception as exc:
        raise McpComputeError("Nova server list is unavailable") from exc


async def list_project_server_interfaces(
    conn: Any, *, project_id: str, server_id: str, limit: int
) -> list[dict[str, str | None]]:
    """List interfaces only when both the server and each attached port are project owned."""
    try:
        return await run_sdk(
            _list_server_interfaces,
            conn,
            project_id=project_id,
            server_id=server_id,
            limit=limit,
        )
    except McpComputeError:
        raise
    except Exception as exc:
        raise McpComputeError("Nova server interfaces are unavailable") from exc


async def list_project_server_volume_attachment_ids(
    conn: Any, *, project_id: str, server_id: str, limit: int
) -> list[str]:
    """List attached volume IDs only after proving the parent server is project owned."""
    try:
        return await run_sdk(
            _list_server_volume_attachment_ids,
            conn,
            project_id=project_id,
            server_id=server_id,
            limit=limit,
        )
    except McpComputeError:
        raise
    except Exception as exc:
        raise McpComputeError("Nova server volume attachments are unavailable") from exc


async def get_project_server(conn: Any, *, project_id: str, server_id: str) -> dict[str, str | None]:
    """Read one Nova server only after its provider record proves exact ownership."""
    try:
        return await run_sdk(_get_server, conn, project_id=project_id, server_id=server_id)
    except McpComputeError:
        raise
    except Exception as exc:
        raise McpComputeError("Nova server is unavailable") from exc


async def project_server_overview(conn: Any, *, project_id: str) -> dict[str, int]:
    """Return fixed exact-project instance counts without server details."""
    try:
        return await run_sdk(_server_overview, conn, project_id=project_id)
    except McpComputeError:
        raise
    except Exception as exc:
        raise McpComputeError("Nova server overview is unavailable") from exc


async def preview_project_server_action(
    conn: Any, *, project_id: str, server_id: str, action: str
) -> dict[str, str | None]:
    """Validate a bounded action against current exact-project server state."""
    try:
        return await run_sdk(
            _prepare_server_action,
            conn,
            project_id=project_id,
            server_id=server_id,
            action=action,
        )
    except McpComputeError:
        raise
    except Exception as exc:
        raise McpComputeError("Nova server action is unavailable") from exc


async def request_project_server_action(
    conn: Any, *, project_id: str, server_id: str, action: str
) -> dict[str, str | None]:
    """Request a bounded action only after final exact-project ownership/state validation."""
    try:
        return await run_sdk(_action_server, conn, project_id=project_id, server_id=server_id, action=action)
    except McpComputeError:
        raise
    except Exception as exc:
        raise McpComputeError("Nova server action is unavailable") from exc


async def preview_project_server_delete(conn: Any, *, project_id: str, server_id: str) -> dict[str, str | None]:
    """Validate one exact-project server deletion without dispatching it."""
    try:
        return await run_sdk(_prepare_server_delete, conn, project_id=project_id, server_id=server_id)
    except McpComputeError:
        raise
    except Exception as exc:
        raise McpComputeError("Nova server deletion is unavailable") from exc


async def request_project_server_delete(conn: Any, *, project_id: str, server_id: str) -> dict[str, str | None]:
    """Delete one exact-project Nova server without force or missing-resource suppression."""
    try:
        server = await run_sdk(conn.compute.get_server, server_id)
        safe_server = _checked_server_delete(server, project_id=project_id)
        from app.services.palimpsest_catalog_cleanup import McpCleanupAuthority, cleanup_consume, lookup_catalog_consume

        authority = McpCleanupAuthority(conn, getattr(conn, "_afterglow_user_id", ""), project_id)
        consume_id = await lookup_catalog_consume(server_id, server, authority)
        if consume_id is not None:
            await cleanup_consume(conn, consume_id, authority)
            return safe_server
        return await run_sdk(_delete_server, conn, server, project_id=project_id, server_id=server_id)
    except McpComputeError:
        raise
    except Exception as exc:
        from fastapi import HTTPException

        if isinstance(exc, HTTPException):
            raise McpComputeError(str(exc.detail)) from exc
        raise McpComputeError("Nova server deletion is unavailable") from exc


def _create_text(value: Any, *, name: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise McpComputeError(f"Nova create {name} is missing or malformed")
    return value


def _create_zone(value: Any) -> str | None:
    if value is None:
        return None
    zone = _create_text(value, name="availability zone", maximum=255)
    if ":" in zone:
        raise McpComputeError("Nova create cannot select a host or node")
    return zone


def _prepare_server_create(
    conn: Any,
    *,
    project_id: str,
    user_id: str,
    name: str,
    image_id: str,
    flavor_id: str,
    network_id: str,
    boot_volume_size_gb: int,
    delete_boot_volume_on_termination: bool,
    key_name: str | None,
    availability_zone: str | None,
) -> tuple[dict[str, Any], FlavorInfo]:
    from app.services.mcp_control_plane.network import validate_project_attachment_network

    _create_text(name, name="name", maximum=63)
    if normalize_requested_instance_name(name) != name:
        raise McpComputeError("Nova create name must use the normalized instance name")
    if type(boot_volume_size_gb) is not int or not 1 <= boot_volume_size_gb <= 16384:
        raise McpComputeError("Nova boot volume size must be 1–16384 GiB")
    if type(delete_boot_volume_on_termination) is not bool:
        raise McpComputeError("Nova boot volume lifetime is malformed")
    availability_zone = _create_zone(availability_zone)
    for identifier, label in ((image_id, "image ID"), (flavor_id, "flavor ID"), (network_id, "network ID")):
        _create_text(identifier, name=label, maximum=255)

    image = conn.image.get_image(image_id)
    if image is None or _field(image, "id") != image_id or _field(image, "status") != "active":
        raise McpComputeError("Glance boot image is unavailable")
    if _field(image, "owner") != project_id and _field(image, "visibility") not in {"public", "community"}:
        if _field(image, "visibility") != "shared":
            raise McpComputeError("Glance boot image visibility cannot be proven")
        member = conn.image.get_member(project_id, image_id)
        if member is None or _field(member, "member_id") != project_id or _field(member, "status") != "accepted":
            raise McpComputeError("Glance boot image membership cannot be proven")

    native_flavor = conn.compute.get_flavor(flavor_id, get_extra_specs=True)
    if native_flavor is None or _field(native_flavor, "id") != flavor_id:
        raise McpComputeError("Nova create flavor is unavailable")
    specs = _field(native_flavor, "extra_specs")
    if not isinstance(specs, Mapping):
        raise McpComputeError("Nova flavor requirements cannot be proven")
    flavor = FlavorInfo(
        id=flavor_id,
        name=_create_text(_field(native_flavor, "name"), name="flavor name", maximum=255),
        vcpus=_field(native_flavor, "vcpus"),
        ram=_field(native_flavor, "ram"),
        disk=_field(native_flavor, "disk"),
        extra_specs=dict(specs),
    )
    for field_name in ("vcpus", "ram", "disk"):
        value = _field(native_flavor, field_name)
        if type(value) is not int or value < (0 if field_name == "disk" else 1):
            raise McpComputeError("Nova flavor capacity is malformed")
    for field_name, available in (("min_disk", boot_volume_size_gb), ("min_ram", flavor.ram)):
        required = _field(image, field_name)
        if type(required) is not int or required < 0 or required > available:
            raise McpComputeError("Glance boot image requirements are not satisfied")

    network = validate_project_attachment_network(conn, project_id=project_id, network_id=network_id)
    if key_name is not None:
        _create_text(key_name, name="keypair name", maximum=255)
        # SDK get_keypair(user_id=...) seeds the resource body, not a query;
        # omitted provider ownership must not inherit a caller-supplied proof.
        keypair = conn.compute.get_keypair(key_name)
        if keypair is None or _field(keypair, "name") != key_name or _field(keypair, "user_id") != user_id:
            raise McpComputeError("Nova keypair ownership cannot be proven")
    ensure_unique_instance_name(conn, name)
    return {
        "name": name,
        "image_id": image_id,
        "flavor_id": flavor_id,
        "network_id": network_id,
        "boot_volume_size_gb": boot_volume_size_gb,
        "delete_boot_volume_on_termination": delete_boot_volume_on_termination,
        "key_name": key_name,
        "availability_zone": availability_zone,
        "network_visibility": network["visibility"],
    }, flavor


async def _owned_policy_result(task: asyncio.Task[Any]) -> Any:
    """Policy helpers use threads too; retain the connection until they settle."""
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await _drain(task)
        raise


async def _server_create_zone(conn: Any, requested_zone: str | None) -> str:
    if requested_zone is not None:
        return _create_zone(requested_zone)
    from app.services.resource_policy_store import resolve_policies

    policies = await _owned_policy_result(
        asyncio.create_task(resolve_policies(conn=conn, keys=("nova.default_compute_availability_zone",)))
    )
    zone = _create_zone(policies["nova.default_compute_availability_zone"])
    if zone is None:
        raise McpComputeError("Nova default availability zone is unavailable")
    return zone


async def preview_project_server_create(
    conn: Any,
    *,
    project_id: str,
    user_id: str,
    name: str,
    image_id: str,
    flavor_id: str,
    network_id: str,
    boot_volume_size_gb: int,
    delete_boot_volume_on_termination: bool = False,
    key_name: str | None = None,
    availability_zone: str | None = None,
) -> dict[str, Any]:
    """Read native dependencies and existing quota/capacity policy without reservations."""
    try:
        zone = await _server_create_zone(conn, availability_zone)
        plan, flavor = await run_sdk(
            _prepare_server_create,
            conn,
            project_id=project_id,
            user_id=user_id,
            name=name,
            image_id=image_id,
            flavor_id=flavor_id,
            network_id=network_id,
            boot_volume_size_gb=boot_volume_size_gb,
            key_name=key_name,
            availability_zone=zone,
            delete_boot_volume_on_termination=delete_boot_volume_on_termination,
        )
        await _owned_policy_result(
            asyncio.create_task(
                flavor_eligibility.require_flavor_eligible(
                    conn,
                    project_id,
                    flavor,
                    check_capacity=True,
                    availability_zone=zone,
                )
            )
        )
        return plan
    except McpComputeError:
        raise
    except Exception as exc:
        raise McpComputeError("Nova server creation preview is unavailable") from exc


def _create_server(conn: Any, *, project_id: str, expected_flavor: FlavorInfo, **arguments: Any) -> dict[str, Any]:
    plan, flavor = _prepare_server_create(conn, project_id=project_id, **arguments)
    if flavor != expected_flavor:
        raise McpComputeError("Nova flavor changed after creation admission")
    body = {
        "name": plan["name"],
        "flavor_id": plan["flavor_id"],
        "networks": [{"uuid": plan["network_id"]}],
        "availability_zone": plan["availability_zone"],
        "block_device_mapping": [
            {
                "uuid": plan["image_id"],
                "source_type": "image",
                "destination_type": "volume",
                "boot_index": 0,
                "volume_size": plan["boot_volume_size_gb"],
                "delete_on_termination": plan["delete_boot_volume_on_termination"],
            }
        ],
    }
    if plan["key_name"] is not None:
        body["key_name"] = plan["key_name"]
    check_mutation_dispatch()
    created = conn.compute.create_server(**body)
    server_id = _required_string(created, "id")
    for owner_field in ("project_id", "tenant_id"):
        owner = _field(created, owner_field)
        if owner is not None and owner != project_id:
            raise McpComputeError("Nova created server ownership cannot be proven")
    # Nova's normal create reply contains only ID/links/adminPass, never infer an owner.
    server = conn.compute.get_server(server_id)
    if server is None:
        raise McpComputeError("Nova created server was not found")
    for owner_field in ("project_id", "tenant_id"):
        owner = _field(server, owner_field)
        if owner is not None and owner != project_id:
            raise McpComputeError("Nova created server ownership cannot be proven")
    safe_server = _safe_server(server, project_id=project_id)
    if safe_server["id"] != server_id:
        raise McpComputeError("Nova created server identity cannot be proven")
    return {**safe_server, "requested_action": "create"}


async def request_project_server_create(
    conn: Any,
    *,
    project_id: str,
    user_id: str,
    name: str,
    image_id: str,
    flavor_id: str,
    network_id: str,
    boot_volume_size_gb: int,
    delete_boot_volume_on_termination: bool = False,
    key_name: str | None = None,
    availability_zone: str | None = None,
) -> dict[str, Any]:
    """Admit one VM and send one asynchronous Nova image-to-volume boot request."""
    admission_task = None
    try:
        zone = await _server_create_zone(conn, availability_zone)
        arguments = dict(
            user_id=user_id,
            name=name,
            image_id=image_id,
            flavor_id=flavor_id,
            network_id=network_id,
            boot_volume_size_gb=boot_volume_size_gb,
            key_name=key_name,
            availability_zone=zone,
        )
        arguments["delete_boot_volume_on_termination"] = delete_boot_volume_on_termination
        _, flavor = await run_sdk(_prepare_server_create, conn, project_id=project_id, **arguments)
        admission_task = asyncio.create_task(
            flavor_eligibility.admit_flavor(
                conn,
                project_id,
                flavor,
                availability_zone=zone,
            )
        )
        await _owned_policy_result(admission_task)
        return await run_sdk(_create_server, conn, project_id=project_id, expected_flavor=flavor, **arguments)
    except McpComputeError:
        raise
    except Exception as exc:
        raise McpComputeError("Nova server creation is unavailable") from exc
    finally:
        if (
            admission_task is not None
            and admission_task.done()
            and not admission_task.cancelled()
            and admission_task.exception() is None
        ):
            try:
                await _owned_policy_result(
                    asyncio.create_task(flavor_eligibility.release_admission(admission_task.result()))
                )
            except Exception as exc:
                raise McpComputeError("Nova creation admission cleanup is unavailable") from exc
