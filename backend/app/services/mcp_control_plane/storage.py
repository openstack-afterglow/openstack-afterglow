"""Project-owned, redacted Cinder read adapters for the consumer MCP registry."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.services.mcp_control_plane.compute import McpComputeError, list_project_server_volume_attachment_ids
from app.services.mcp_control_plane.sdk import check_mutation_dispatch, run_sdk


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
    volumes = conn.block_storage.volumes(details=True, project_id=project_id)
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
    snapshots = conn.block_storage.snapshots(details=True, project_id=project_id)
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
    backups = conn.block_storage.backups(details=True, project_id=project_id)
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
