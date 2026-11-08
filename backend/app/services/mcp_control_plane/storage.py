"""Project-owned, redacted Cinder adapters for the consumer MCP registry."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.services.mcp_control_plane.compute import McpComputeError, list_project_server_volume_attachment_ids
from app.services.mcp_control_plane.sdk import check_mutation_dispatch, run_sdk
from app.services.waygate_managed import WaygateManagedResourceError, require_server_not_waygate_managed


class McpStorageError(ValueError):
    """Cinder data is unavailable or does not prove current-project ownership."""


def _field(resource: Any, name: str) -> Any:
    if isinstance(resource, Mapping):
        return resource.get(name)
    return getattr(resource, name, None)


def _required_string(resource: Any, name: str) -> str:
    value = _field(resource, name)
    if not isinstance(value, str) or not value:
        raise McpStorageError(f"Cinder volume {name} is missing")
    return value


def _optional_text(resource: Any, *names: str) -> str | None:
    for name in names:
        value = _field(resource, name)
        if value is None:
            continue
        if isinstance(value, str):
            return value
        if hasattr(value, "isoformat"):
            return value.isoformat()
        raise McpStorageError(f"Cinder volume {name} is malformed")
    return None


def _safe_volume(resource: Any, *, project_id: str) -> dict[str, str | int | None]:
    owner_project_id = _field(resource, "project_id") or _field(resource, "os-vol-tenant-attr:tenant_id")
    if owner_project_id != project_id:
        raise McpStorageError("Cinder volume ownership cannot be proven")
    size_gb = _field(resource, "size")
    if not isinstance(size_gb, int) or isinstance(size_gb, bool) or size_gb < 0:
        raise McpStorageError("Cinder volume size is malformed")
    name = _field(resource, "name")
    if name is not None and not isinstance(name, str):
        raise McpStorageError("Cinder volume name is malformed")
    return {
        "id": _required_string(resource, "id"),
        "name": name,
        "status": _required_string(resource, "status"),
        "size_gb": size_gb,
        "created_at": _optional_text(resource, "created_at", "created"),
    }


def _list_volumes(conn: Any, *, project_id: str, limit: int) -> list[dict[str, str | int | None]]:
    # The credential already scopes Cinder; project_id is an admin-only list
    # filter. Keep the detail response and prove each returned record's owner.
    volumes = conn.block_storage.volumes(details=True)
    safe_volumes: list[dict[str, str | int | None]] = []
    for volume in volumes:
        safe_volumes.append(_safe_volume(volume, project_id=project_id))
        if len(safe_volumes) == limit:
            break
    return safe_volumes


def _get_volume(conn: Any, *, project_id: str, volume_id: str) -> dict[str, str | int | None]:
    volume = conn.block_storage.get_volume(volume_id)
    if volume is None:
        raise McpStorageError("Cinder volume was not found")
    return _safe_volume(volume, project_id=project_id)


def _prepare_volume_create(*, name: str, size_gb: int, availability_zone: str | None) -> dict[str, str | int | None]:
    if not isinstance(name, str) or not name.strip() or len(name) > 255:
        raise McpStorageError("Cinder volume name must contain 1–255 nonblank characters")
    if not isinstance(size_gb, int) or isinstance(size_gb, bool) or not 1 <= size_gb <= 16384:
        raise McpStorageError("Cinder volume size must be an integer from 1 to 16384 GiB")
    if availability_zone is not None and (
        not isinstance(availability_zone, str) or not availability_zone.strip() or len(availability_zone) > 255
    ):
        raise McpStorageError("Cinder volume availability zone must contain 1–255 nonblank characters")
    return {"name": name, "size_gb": size_gb, "availability_zone": availability_zone}


def _create_volume(
    conn: Any, *, project_id: str, name: str, size_gb: int, availability_zone: str | None
) -> dict[str, str | int | None]:
    # Validate again inside the owned SDK worker, not just during the preview.
    preview = _prepare_volume_create(name=name, size_gb=size_gb, availability_zone=availability_zone)
    attributes = {"name": preview["name"], "size": preview["size_gb"]}
    if preview["availability_zone"] is not None:
        attributes["availability_zone"] = preview["availability_zone"]
    check_mutation_dispatch()
    volume = conn.block_storage.create_volume(**attributes)
    volume_id = _required_string(volume, "id")
    if not volume_id.strip():
        raise McpStorageError("Cinder volume id is malformed")
    owners = [_field(volume, "project_id"), _field(volume, "os-vol-tenant-attr:tenant_id")]
    if any(owner is not None and owner != project_id for owner in owners):
        raise McpStorageError("Cinder volume ownership cannot be proven")
    if any(owner is not None for owner in owners):
        safe_volume = _safe_volume(volume, project_id=project_id)
    else:
        # Cinder's create response can omit tenant metadata; never infer it from
        # the credential or clean up a volume after an uncertain output failure.
        volume = conn.block_storage.get_volume(volume_id)
        if volume is None:
            raise McpStorageError("Cinder created volume was not found")
        owners = [_field(volume, "project_id"), _field(volume, "os-vol-tenant-attr:tenant_id")]
        if any(owner is not None and owner != project_id for owner in owners):
            raise McpStorageError("Cinder volume ownership cannot be proven")
        safe_volume = _safe_volume(volume, project_id=project_id)
        if safe_volume["id"] != volume_id:
            raise McpStorageError("Cinder created volume identity cannot be proven")
    return {**safe_volume, "requested_action": "create"}


async def list_project_server_volumes(
    conn: Any, *, project_id: str, server_id: str, limit: int
) -> list[dict[str, str | int | None]]:
    """List attached volumes only after proving both the Nova parent and every Cinder child."""
    try:
        volume_ids = await list_project_server_volume_attachment_ids(
            conn,
            project_id=project_id,
            server_id=server_id,
            limit=limit,
        )
    except McpComputeError as exc:
        raise McpStorageError("Nova server volume attachments are unavailable") from exc
    return [await get_project_volume(conn, project_id=project_id, volume_id=volume_id) for volume_id in volume_ids]


def _prepare_volume_delete(conn: Any, *, project_id: str, volume_id: str) -> dict[str, str | int | None]:
    safe_volume = _get_volume(conn, project_id=project_id, volume_id=volume_id)
    if safe_volume["status"] != "available":
        raise McpStorageError("Cinder volume is not in a state that permits deletion")
    return {**safe_volume, "requested_action": "delete"}


def _delete_volume(conn: Any, *, project_id: str, volume_id: str) -> dict[str, str | int | None]:
    safe_volume = _prepare_volume_delete(conn, project_id=project_id, volume_id=volume_id)
    check_mutation_dispatch()
    conn.block_storage.delete_volume(volume_id, ignore_missing=False, force=False)
    return safe_volume


def _safe_snapshot(conn: Any, resource: Any, *, project_id: str) -> dict[str, str | int | None]:
    owner_project_id = _field(resource, "project_id") or _field(resource, "os-extended-snapshot-attributes:project_id")
    if owner_project_id != project_id:
        raise McpStorageError("Cinder snapshot ownership cannot be proven")
    volume_id = _required_string(resource, "volume_id")
    parent = conn.block_storage.get_volume(volume_id)
    if parent is None:
        raise McpStorageError("Cinder snapshot parent volume was not found")
    _safe_volume(parent, project_id=project_id)
    size_gb = _field(resource, "size")
    if not isinstance(size_gb, int) or isinstance(size_gb, bool) or size_gb < 0:
        raise McpStorageError("Cinder snapshot size is malformed")
    name = _field(resource, "name")
    if name is not None and not isinstance(name, str):
        raise McpStorageError("Cinder snapshot name is malformed")
    return {
        "id": _required_string(resource, "id"),
        "name": name,
        "status": _required_string(resource, "status"),
        "source_volume_id": volume_id,
        "size_gb": size_gb,
        "created_at": _optional_text(resource, "created_at", "created"),
    }


def _list_snapshots(conn: Any, *, project_id: str, limit: int) -> list[dict[str, str | int | None]]:
    snapshots = conn.block_storage.snapshots(details=True)
    safe_snapshots: list[dict[str, str | int | None]] = []
    for snapshot in snapshots:
        safe_snapshots.append(_safe_snapshot(conn, snapshot, project_id=project_id))
        if len(safe_snapshots) == limit:
            break
    return safe_snapshots


def _get_snapshot(conn: Any, *, project_id: str, snapshot_id: str) -> dict[str, str | int | None]:
    snapshot = conn.block_storage.get_snapshot(snapshot_id)
    if snapshot is None:
        raise McpStorageError("Cinder snapshot was not found")
    return _safe_snapshot(conn, snapshot, project_id=project_id)


def _safe_backup(conn: Any, resource: Any, *, project_id: str) -> dict[str, str | int | None]:
    owner_project_id = _field(resource, "project_id") or _field(resource, "os-backup-project-attr:project_id")
    if owner_project_id != project_id:
        raise McpStorageError("Cinder backup ownership cannot be proven")
    volume_id = _required_string(resource, "volume_id")
    parent = conn.block_storage.get_volume(volume_id)
    if parent is None:
        raise McpStorageError("Cinder backup parent volume was not found")
    _safe_volume(parent, project_id=project_id)
    size_gb = _field(resource, "size")
    if not isinstance(size_gb, int) or isinstance(size_gb, bool) or size_gb < 0:
        raise McpStorageError("Cinder backup size is malformed")
    name = _field(resource, "name")
    if name is not None and not isinstance(name, str):
        raise McpStorageError("Cinder backup name is malformed")
    return {
        "id": _required_string(resource, "id"),
        "name": name,
        "status": _required_string(resource, "status"),
        "source_volume_id": volume_id,
        "size_gb": size_gb,
        "created_at": _optional_text(resource, "created_at", "created"),
    }


def _list_backups(conn: Any, *, project_id: str, limit: int) -> list[dict[str, str | int | None]]:
    backups = conn.block_storage.backups(details=True)
    safe_backups: list[dict[str, str | int | None]] = []
    for backup in backups:
        safe_backups.append(_safe_backup(conn, backup, project_id=project_id))
        if len(safe_backups) == limit:
            break
    return safe_backups


def _get_backup(conn: Any, *, project_id: str, backup_id: str) -> dict[str, str | int | None]:
    backup = conn.block_storage.get_backup(backup_id)
    if backup is None:
        raise McpStorageError("Cinder backup was not found")
    return _safe_backup(conn, backup, project_id=project_id)


def _prepare_snapshot_delete(conn: Any, *, project_id: str, snapshot_id: str) -> dict[str, str | int | None]:
    snapshot = _get_snapshot(conn, project_id=project_id, snapshot_id=snapshot_id)
    if snapshot["status"] != "available":
        raise McpStorageError("Cinder snapshot is not in a state that permits deletion")
    return {**snapshot, "requested_action": "delete"}


def _delete_snapshot(conn: Any, *, project_id: str, snapshot_id: str) -> dict[str, str | int | None]:
    snapshot = _prepare_snapshot_delete(conn, project_id=project_id, snapshot_id=snapshot_id)
    check_mutation_dispatch()
    conn.block_storage.delete_snapshot(snapshot_id, ignore_missing=False, force=False)
    return snapshot


def _prepare_backup_delete(conn: Any, *, project_id: str, backup_id: str) -> dict[str, str | int | None]:
    backup = _get_backup(conn, project_id=project_id, backup_id=backup_id)
    if backup["status"] != "available":
        raise McpStorageError("Cinder backup is not in a state that permits deletion")
    return {**backup, "requested_action": "delete"}


def _delete_backup(conn: Any, *, project_id: str, backup_id: str) -> dict[str, str | int | None]:
    backup = _prepare_backup_delete(conn, project_id=project_id, backup_id=backup_id)
    check_mutation_dispatch()
    conn.block_storage.delete_backup(backup_id, ignore_missing=False, force=False)
    return backup


async def list_project_volumes(conn: Any, *, project_id: str, limit: int) -> list[dict[str, str | int | None]]:
    """List volumes only when each provider record proves exact project ownership."""
    try:
        return await run_sdk(_list_volumes, conn, project_id=project_id, limit=limit)
    except McpStorageError:
        raise
    except Exception as exc:
        raise McpStorageError("Cinder volume list is unavailable") from exc


async def get_project_volume(conn: Any, *, project_id: str, volume_id: str) -> dict[str, str | int | None]:
    """Read one volume only after its provider record proves exact project ownership."""
    try:
        return await run_sdk(_get_volume, conn, project_id=project_id, volume_id=volume_id)
    except McpStorageError:
        raise
    except Exception as exc:
        raise McpStorageError("Cinder volume is unavailable") from exc


async def preview_project_volume_create(
    conn: Any,
    *,
    project_id: str,
    name: str,
    size_gb: int,
    availability_zone: str | None = None,
) -> dict[str, str | int | None]:
    """Validate bounded creation inputs without reading or writing cloud resources."""
    try:
        return await run_sdk(_prepare_volume_create, name=name, size_gb=size_gb, availability_zone=availability_zone)
    except McpStorageError:
        raise
    except Exception as exc:
        raise McpStorageError("Cinder volume creation is unavailable") from exc


async def request_project_volume_create(
    conn: Any,
    *,
    project_id: str,
    name: str,
    size_gb: int,
    availability_zone: str | None = None,
) -> dict[str, str | int | None]:
    """Request one creation and return owned metadata, without waiting or rollback."""
    try:
        return await run_sdk(
            _create_volume,
            conn,
            project_id=project_id,
            name=name,
            size_gb=size_gb,
            availability_zone=availability_zone,
        )
    except McpStorageError:
        raise
    except Exception as exc:
        raise McpStorageError("Cinder volume creation is unavailable") from exc


async def preview_project_volume_delete(conn: Any, *, project_id: str, volume_id: str) -> dict[str, str | int | None]:
    """Validate a non-force delete against current exact-project volume state."""
    try:
        return await run_sdk(_prepare_volume_delete, conn, project_id=project_id, volume_id=volume_id)
    except McpStorageError:
        raise
    except Exception as exc:
        raise McpStorageError("Cinder volume deletion is unavailable") from exc


async def request_project_volume_delete(conn: Any, *, project_id: str, volume_id: str) -> dict[str, str | int | None]:
    """Delete only a currently available exact-project volume without force."""
    try:
        return await run_sdk(_delete_volume, conn, project_id=project_id, volume_id=volume_id)
    except McpStorageError:
        raise
    except Exception as exc:
        raise McpStorageError("Cinder volume deletion is unavailable") from exc


async def list_project_snapshots(conn: Any, *, project_id: str, limit: int) -> list[dict[str, str | int | None]]:
    """List snapshots only after proving both snapshot and parent volume ownership."""
    try:
        return await run_sdk(_list_snapshots, conn, project_id=project_id, limit=limit)
    except McpStorageError:
        raise
    except Exception as exc:
        raise McpStorageError("Cinder snapshot list is unavailable") from exc


async def get_project_snapshot(conn: Any, *, project_id: str, snapshot_id: str) -> dict[str, str | int | None]:
    """Read one snapshot only after proving its exact-project parent volume."""
    try:
        return await run_sdk(_get_snapshot, conn, project_id=project_id, snapshot_id=snapshot_id)
    except McpStorageError:
        raise
    except Exception as exc:
        raise McpStorageError("Cinder snapshot is unavailable") from exc


async def preview_project_snapshot_delete(
    conn: Any, *, project_id: str, snapshot_id: str
) -> dict[str, str | int | None]:
    """Validate a non-force delete against current exact-project snapshot and parent volume state."""
    try:
        return await run_sdk(_prepare_snapshot_delete, conn, project_id=project_id, snapshot_id=snapshot_id)
    except McpStorageError:
        raise
    except Exception as exc:
        raise McpStorageError("Cinder snapshot deletion is unavailable") from exc


async def request_project_snapshot_delete(
    conn: Any, *, project_id: str, snapshot_id: str
) -> dict[str, str | int | None]:
    """Delete only an available exact-project snapshot without force."""
    try:
        return await run_sdk(_delete_snapshot, conn, project_id=project_id, snapshot_id=snapshot_id)
    except McpStorageError:
        raise
    except Exception as exc:
        raise McpStorageError("Cinder snapshot deletion is unavailable") from exc


async def list_project_backups(conn: Any, *, project_id: str, limit: int) -> list[dict[str, str | int | None]]:
    """List backups only after proving both backup and parent volume ownership."""
    try:
        return await run_sdk(_list_backups, conn, project_id=project_id, limit=limit)
    except McpStorageError:
        raise
    except Exception as exc:
        raise McpStorageError("Cinder backup list is unavailable") from exc


async def get_project_backup(conn: Any, *, project_id: str, backup_id: str) -> dict[str, str | int | None]:
    """Read one backup only after proving its exact-project parent volume."""
    try:
        return await run_sdk(_get_backup, conn, project_id=project_id, backup_id=backup_id)
    except McpStorageError:
        raise
    except Exception as exc:
        raise McpStorageError("Cinder backup is unavailable") from exc


async def preview_project_backup_delete(conn: Any, *, project_id: str, backup_id: str) -> dict[str, str | int | None]:
    """Validate a non-force delete against current exact-project backup and parent volume state."""
    try:
        return await run_sdk(_prepare_backup_delete, conn, project_id=project_id, backup_id=backup_id)
    except McpStorageError:
        raise
    except Exception as exc:
        raise McpStorageError("Cinder backup deletion is unavailable") from exc


async def request_project_backup_delete(conn: Any, *, project_id: str, backup_id: str) -> dict[str, str | int | None]:
    """Delete only an available exact-project backup without force."""
    try:
        return await run_sdk(_delete_backup, conn, project_id=project_id, backup_id=backup_id)
    except McpStorageError:
        raise
    except Exception as exc:
        raise McpStorageError("Cinder backup deletion is unavailable") from exc


def _management_alias(resource: Any, *names: str, required: bool = True) -> Any:
    values = [_field(resource, name) for name in names if _field(resource, name) is not None]
    if not values:
        if required:
            raise McpStorageError("Provider resource identity or binding is missing")
        return None
    if any(value != values[0] or type(value) is not type(values[0]) for value in values):
        raise McpStorageError("Provider resource aliases contradict each other")
    return values[0]


def _management_resource(conn: Any, *, collection: str, resource_id: str) -> Mapping[str, Any]:
    from urllib.parse import quote

    from app.services.mcp_control_plane.network import McpNetworkError
    from app.services.mcp_control_plane.network_management import _raw_exact_resource

    if not isinstance(resource_id, str) or not resource_id:
        raise McpStorageError("Provider resource identity is missing")
    # SDK GET merges URI ID seeds into response objects. Inspect the original
    # body using the same scoped proxy instead; never infer an omitted ID.
    proxy = conn.compute if collection == "servers" else conn.block_storage
    singular = "server" if collection == "servers" else "volume"
    try:
        return _raw_exact_resource(
            proxy,
            f"/{collection}/{quote(resource_id, safe='')}",
            resource_key=singular,
            resource_id=resource_id,
            microversion="2.3" if collection == "servers" else None,
        )
    except McpNetworkError as exc:
        raise McpStorageError("Exact provider resource identity cannot be proven") from exc


def _management_volume(conn: Any, *, project_id: str, volume_id: str) -> tuple[Any, dict[str, Any]]:
    volume = _management_resource(conn, collection="volumes", resource_id=volume_id)
    owner = _management_alias(volume, "project_id", "tenant_id", "os-vol-tenant-attr:tenant_id")
    if owner != project_id:
        raise McpStorageError("Cinder volume ownership cannot be proven")
    return volume, _safe_volume(volume, project_id=project_id)


def _management_server(conn: Any, *, project_id: str, server_id: str) -> Any:
    from app.services.mcp_control_plane.compute import _safe_server

    server = _management_resource(conn, collection="servers", resource_id=server_id)
    if _management_alias(server, "project_id", "tenant_id") != project_id:
        raise McpStorageError("Nova server ownership cannot be proven")
    try:
        safe = _safe_server(server, project_id=project_id)
    except McpComputeError as exc:
        raise McpStorageError("Nova server ownership cannot be proven") from exc
    if safe["status"] not in {"ACTIVE", "SHUTOFF"}:
        raise McpStorageError("Nova server is not in an eligible state")
    # Volume attachments of a Waygate gateway are Waygate-only (matches the REST surface).
    require_server_not_waygate_managed(server)
    return server


def _management_attachments(volume: Any) -> list[Any]:
    attachments = _field(volume, "attachments")
    if not isinstance(attachments, list) or len(attachments) > 100:
        raise McpStorageError("Cinder volume attachment state is unavailable")
    return attachments


def _management_single_attach(volume: Any) -> None:
    if _management_alias(volume, "is_multiattach", "multiattach") is not False:
        raise McpStorageError("Cinder volume must prove multiattach is disabled")


def _management_volume_attributes(attributes: Mapping[str, Any]) -> dict[str, str]:
    if not isinstance(attributes, Mapping) or not attributes or set(attributes) - {"name", "description"}:
        raise McpStorageError("Cinder volume update attributes are invalid")
    result = {}
    for key, value in attributes.items():
        bound = 255 if key == "name" else 1024
        if not isinstance(value, str) or len(value) > bound or (key == "name" and not value.strip()):
            raise McpStorageError("Cinder volume update text is invalid")
        result[key] = value
    return result


def _prepare_volume_update(
    conn: Any, *, project_id: str, volume_id: str, attributes: Mapping[str, Any]
) -> dict[str, Any]:
    attributes = _management_volume_attributes(attributes)
    _, safe = _management_volume(conn, project_id=project_id, volume_id=volume_id)
    if safe["status"] not in {"available", "in-use"}:
        raise McpStorageError("Cinder volume is not in a state that permits updates")
    return {**safe, "requested_action": "update", "attributes": attributes}


def _update_volume(conn: Any, *, project_id: str, volume_id: str, attributes: Mapping[str, Any]) -> dict[str, Any]:
    preview = _prepare_volume_update(conn, project_id=project_id, volume_id=volume_id, attributes=attributes)
    check_mutation_dispatch()
    conn.block_storage.update_volume(volume_id, **preview["attributes"])
    volume, safe = _management_volume(conn, project_id=project_id, volume_id=volume_id)
    if any(_field(volume, key) != value for key, value in preview["attributes"].items()):
        raise McpStorageError("Cinder updated volume attributes cannot be proven")
    return {**safe, "requested_action": "update"}


def _prepare_volume_extend(conn: Any, *, project_id: str, volume_id: str, size_gb: int) -> dict[str, Any]:
    if not isinstance(size_gb, int) or isinstance(size_gb, bool) or not 1 <= size_gb <= 16384:
        raise McpStorageError("Cinder volume size must be an integer from 1 to 16384 GiB")
    volume, safe = _management_volume(conn, project_id=project_id, volume_id=volume_id)
    if safe["status"] != "available" or _management_attachments(volume):
        raise McpStorageError("Cinder volume extension requires an available unattached volume")
    if size_gb <= safe["size_gb"]:
        raise McpStorageError("Cinder volume extension must increase the current size")
    return {**safe, "requested_action": "extend", "requested_size_gb": size_gb}


def _extend_volume(conn: Any, *, project_id: str, volume_id: str, size_gb: int) -> dict[str, Any]:
    preview = _prepare_volume_extend(conn, project_id=project_id, volume_id=volume_id, size_gb=size_gb)
    check_mutation_dispatch()
    conn.block_storage.extend_volume(volume_id, size=size_gb)
    return preview


def _management_nova_attachments(conn: Any, *, server_id: str) -> list[Any]:
    from urllib.parse import quote

    # SDK VolumeAttachment drops native serverId; URI seeds cannot prove it.
    check_mutation_dispatch()
    response = conn.compute.get(
        f"/servers/{quote(server_id, safe='')}/os-volume_attachments",
        microversion="2.89",
        redirect=False,
        allow_reauth=False,
        raise_exc=False,
        connect_retries=0,
        status_code_retries=0,
    )
    if response.status_code != 200:
        raise McpStorageError("Nova attachment inventory is unavailable")
    body = response.json()
    rows = body.get("volumeAttachments") if isinstance(body, Mapping) else None
    if not isinstance(rows, list) or len(rows) > 100:
        raise McpStorageError("Nova attachment inventory is malformed or exceeds the safe bound")
    attachments = []
    volume_ids = set()
    devices = set()
    for attachment in rows:
        check_mutation_dispatch()
        if not isinstance(attachment, Mapping):
            raise McpStorageError("Nova attachment response is malformed")
        attachment_id = attachment.get("attachment_id")
        if not isinstance(attachment_id, str) or not attachment_id:
            raise McpStorageError("Nova attachment identity is unavailable")
        volume_id = _management_alias(attachment, "volume_id", "volumeId")
        if not isinstance(volume_id, str) or not volume_id or volume_id in volume_ids:
            raise McpStorageError("Nova volume attachment identity is ambiguous")
        parent = _management_alias(attachment, "server_id", "serverId", "server_uuid")
        if parent != server_id:
            raise McpStorageError("Nova volume attachment server contradicts the requested server")
        device = _optional_text(attachment, "device")
        if device:
            if device in devices:
                raise McpStorageError("Nova volume attachment devices are ambiguous")
            devices.add(device)
        volume_ids.add(volume_id)
        attachments.append(attachment)
    return attachments


def _management_cinder_binding(attachment: Any, *, server_id: str, volume_id: str) -> None:
    if _management_alias(attachment, "server_id", "serverId", "server_uuid") != server_id:
        raise McpStorageError("Cinder attachment does not belong to the requested server")
    # Cinder's volume view uses id for the volume, not the attachment record.
    bound_volume = _management_alias(attachment, "id", "volume_id", "volumeId", required=False)
    if bound_volume is not None and bound_volume != volume_id:
        raise McpStorageError("Cinder attachment volume identity contradicts the requested volume")


def _management_attachment_summary(attachment: Any, *, server_id: str, volume_id: str, action: str) -> dict[str, Any]:
    if _management_alias(attachment, "volume_id", "volumeId") != volume_id:
        raise McpStorageError("Nova volume attachment identity cannot be proven")
    legacy_id = _field(attachment, "id")
    if legacy_id is not None and legacy_id != volume_id:
        raise McpStorageError("Nova legacy attachment id contradicts the volume identity")
    parent = _management_alias(attachment, "server_id", "serverId", "server_uuid", required=False)
    if parent is not None and parent != server_id:
        raise McpStorageError("Nova volume attachment server cannot be proven")
    attachment_id = _field(attachment, "attachment_id") or _field(attachment, "id")
    if not isinstance(attachment_id, str) or not attachment_id:
        raise McpStorageError("Nova volume attachment ID is unavailable")
    device = _optional_text(attachment, "device")
    return {
        "server_id": server_id,
        "volume_id": volume_id,
        "attachment_id": attachment_id,
        "device": device,
        "requested_action": action,
    }


def _prepare_server_volume_attach(conn: Any, *, project_id: str, server_id: str, volume_id: str) -> dict[str, Any]:
    server = _management_server(conn, project_id=project_id, server_id=server_id)
    volume, safe = _management_volume(conn, project_id=project_id, volume_id=volume_id)
    _management_single_attach(volume)
    if safe["status"] != "available" or _management_attachments(volume):
        raise McpStorageError("Cinder volume attachment requires an available unattached volume")
    server_zone = _management_alias(server, "availability_zone", "OS-EXT-AZ:availability_zone", required=False)
    volume_zone = _field(volume, "availability_zone")
    for zone in (server_zone, volume_zone):
        if zone is not None and (not isinstance(zone, str) or not zone):
            raise McpStorageError("Provider availability zone is malformed")
    if server_zone is not None and volume_zone is not None and server_zone != volume_zone:
        raise McpStorageError("Nova and Cinder availability zones do not match")
    if any(
        _management_alias(item, "volume_id", "volumeId") == volume_id
        for item in _management_nova_attachments(conn, server_id=server_id)
    ):
        raise McpStorageError("Nova already reports this volume as attached")
    return {
        "server_id": server_id,
        "volume_id": volume_id,
        "attachment_id": None,
        "device": None,
        "requested_action": "attach_volume",
        "server_status": _field(server, "status"),
        "volume_status": safe["status"],
    }


def _attach_server_volume(conn: Any, *, project_id: str, server_id: str, volume_id: str) -> dict[str, Any]:
    _prepare_server_volume_attach(conn, project_id=project_id, server_id=server_id, volume_id=volume_id)
    check_mutation_dispatch()
    created = conn.compute.create_volume_attachment(server_id, volume=volume_id)
    summary = _management_attachment_summary(created, server_id=server_id, volume_id=volume_id, action="attach_volume")
    volume, _ = _management_volume(conn, project_id=project_id, volume_id=volume_id)
    _management_single_attach(volume)
    bindings = _management_attachments(volume)
    if len(bindings) > 1:
        raise McpStorageError("Cinder returned ambiguous volume attachments")
    if bindings:
        _management_cinder_binding(bindings[0], server_id=server_id, volume_id=volume_id)
        cinder_id = _field(bindings[0], "attachment_id")
        nova_id = _field(created, "attachment_id")
        if nova_id is not None and cinder_id is not None and nova_id != cinder_id:
            raise McpStorageError("Nova and Cinder attachment identities contradict each other")
    # A scoped list carries provider volume IDs, unlike create's SDK-seeded
    # volume_id attribute. One read is sufficient; no eventual-consistency loop.
    matches = [
        item
        for item in _management_nova_attachments(conn, server_id=server_id)
        if _management_alias(item, "volume_id", "volumeId") == volume_id
    ]
    if len(matches) != 1:
        raise McpStorageError("Nova accepted attachment cannot be corroborated")
    observed = _management_attachment_summary(
        matches[0], server_id=server_id, volume_id=volume_id, action="attach_volume"
    )
    # POST's legacy id is the volume UUID, not GET's Cinder attachment identity.
    created_id = _field(created, "attachment_id")
    observed_id = _field(matches[0], "attachment_id")
    if bindings:
        cinder_id = _field(bindings[0], "attachment_id")
        if cinder_id is not None and cinder_id != observed_id:
            raise McpStorageError("Nova and Cinder corroborated attachment identities contradict each other")
    if (created_id is not None and observed_id is not None and created_id != observed_id) or (
        summary["device"] is not None and observed["device"] is not None and summary["device"] != observed["device"]
    ):
        raise McpStorageError("Nova attachment responses contradict each other")
    return observed


def _prepare_server_volume_detach(conn: Any, *, project_id: str, server_id: str, volume_id: str) -> dict[str, Any]:
    server = _management_server(conn, project_id=project_id, server_id=server_id)
    volume, safe = _management_volume(conn, project_id=project_id, volume_id=volume_id)
    _management_single_attach(volume)
    bindings = _management_attachments(volume)
    if safe["status"] != "in-use" or len(bindings) != 1:
        raise McpStorageError("Cinder volume must have exactly one in-use attachment")
    binding = bindings[0]
    _management_cinder_binding(binding, server_id=server_id, volume_id=volume_id)
    matches = [
        item
        for item in _management_nova_attachments(conn, server_id=server_id)
        if _management_alias(item, "volume_id", "volumeId") == volume_id
    ]
    if len(matches) != 1:
        raise McpStorageError("Nova volume attachment cannot be corroborated")
    attachment = matches[0]
    summary = _management_attachment_summary(
        attachment, server_id=server_id, volume_id=volume_id, action="detach_volume"
    )
    cinder_id = _field(binding, "attachment_id")
    nova_id = _field(attachment, "attachment_id")
    if nova_id is not None and cinder_id is not None and nova_id != cinder_id:
        raise McpStorageError("Nova and Cinder attachment identities contradict each other")
    device = summary["device"]
    cinder_device = _optional_text(binding, "device")
    if not device or not cinder_device or device != cinder_device:
        raise McpStorageError("Nova and Cinder attachment devices cannot be corroborated")
    root = _management_alias(server, "root_device_name", "OS-EXT-SRV-ATTR:root_device_name", required=False)
    boot_index = _management_alias(attachment, "boot_index", "bootIndex", required=False)
    server_volumes = _management_alias(
        server, "attached_volumes", "os-extended-volumes:volumes_attached", required=False
    )
    if server_volumes is not None:
        if not isinstance(server_volumes, list) or len(server_volumes) > 100:
            raise McpStorageError("Nova server volume inventory is malformed")
        seen = set()
        server_boot_index = None
        for item in server_volumes:
            item_id = _management_alias(item, "id", "volume_id", "volumeId")
            if not isinstance(item_id, str) or not item_id or item_id in seen:
                raise McpStorageError("Nova server volume inventory is ambiguous")
            seen.add(item_id)
            if item_id == volume_id:
                server_boot_index = _management_alias(item, "boot_index", "bootIndex", required=False)
        if volume_id not in seen:
            raise McpStorageError("Nova server volume inventory contradicts its attachment")
        if server_boot_index is not None:
            if boot_index is not None and server_boot_index != boot_index:
                raise McpStorageError("Nova boot index aliases contradict each other")
            boot_index = server_boot_index
    if root is not None and (not isinstance(root, str) or not root):
        raise McpStorageError("Nova root device evidence is malformed")
    if boot_index is not None and (not isinstance(boot_index, int) or isinstance(boot_index, bool) or boot_index < -1):
        raise McpStorageError("Nova boot index evidence is malformed")
    if boot_index == 0 or root == device:
        raise McpStorageError("Detaching a Nova boot/root volume is forbidden")
    if root is None and boot_index is None:
        raise McpStorageError("Nova root volume identity is ambiguous")
    return {**summary, "server_status": _field(server, "status"), "volume_status": safe["status"]}


def _detach_server_volume(conn: Any, *, project_id: str, server_id: str, volume_id: str) -> dict[str, Any]:
    from openstack.compute.v2.server import Server

    preview = _prepare_server_volume_detach(conn, project_id=project_id, server_id=server_id, volume_id=volume_id)
    # The installed proxy takes server first. A typed, already-verified identity
    # avoids its legacy argument-order heuristic performing find_server after
    # the final dispatch fence. This object is URI context, not ownership proof.
    server = Server.existing(id=server_id)
    check_mutation_dispatch()
    conn.compute.delete_volume_attachment(server, volume_id, ignore_missing=False)
    return {key: value for key, value in preview.items() if key not in {"server_status", "volume_status"}}


async def _run_volume_management(operation: Any, conn: Any, **kwargs: Any) -> dict[str, Any]:
    try:
        return await run_sdk(operation, conn, **kwargs)
    except (McpStorageError, WaygateManagedResourceError):
        raise
    except Exception as exc:
        raise McpStorageError("Cinder/Nova volume management is unavailable") from exc


async def preview_project_volume_update(
    conn: Any, *, project_id: str, volume_id: str, attributes: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate a metadata-only update without modifying the volume."""
    return await _run_volume_management(
        _prepare_volume_update, conn, project_id=project_id, volume_id=volume_id, attributes=attributes
    )


async def request_project_volume_update(
    conn: Any, *, project_id: str, volume_id: str, attributes: Mapping[str, Any]
) -> dict[str, Any]:
    """Revalidate, fence and issue one Cinder metadata update."""
    return await _run_volume_management(
        _update_volume, conn, project_id=project_id, volume_id=volume_id, attributes=attributes
    )


async def preview_project_volume_extend(conn: Any, *, project_id: str, volume_id: str, size_gb: int) -> dict[str, Any]:
    """Validate an offline size increase without changing the volume."""
    return await _run_volume_management(
        _prepare_volume_extend, conn, project_id=project_id, volume_id=volume_id, size_gb=size_gb
    )


async def request_project_volume_extend(conn: Any, *, project_id: str, volume_id: str, size_gb: int) -> dict[str, Any]:
    """Request one offline extension; acceptance is not readiness."""
    return await _run_volume_management(
        _extend_volume, conn, project_id=project_id, volume_id=volume_id, size_gb=size_gb
    )


async def preview_project_server_volume_attach(
    conn: Any, *, project_id: str, server_id: str, volume_id: str
) -> dict[str, Any]:
    """Validate exact-owned single-attach data volume admission."""
    return await _run_volume_management(
        _prepare_server_volume_attach, conn, project_id=project_id, server_id=server_id, volume_id=volume_id
    )


async def request_project_server_volume_attach(
    conn: Any, *, project_id: str, server_id: str, volume_id: str
) -> dict[str, Any]:
    """Request and corroborate one Nova attachment without choosing a device."""
    return await _run_volume_management(
        _attach_server_volume, conn, project_id=project_id, server_id=server_id, volume_id=volume_id
    )


async def preview_project_server_volume_detach(
    conn: Any, *, project_id: str, server_id: str, volume_id: str
) -> dict[str, Any]:
    """Corroborate the unique data attachment and prove it is not the root."""
    return await _run_volume_management(
        _prepare_server_volume_detach, conn, project_id=project_id, server_id=server_id, volume_id=volume_id
    )


async def request_project_server_volume_detach(
    conn: Any, *, project_id: str, server_id: str, volume_id: str
) -> dict[str, Any]:
    """Detach exactly one proven data attachment, never delete the volume."""
    return await _run_volume_management(
        _detach_server_volume, conn, project_id=project_id, server_id=server_id, volume_id=volume_id
    )
