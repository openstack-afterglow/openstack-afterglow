"""Project-owned, redacted Trove read adapters for the consumer MCP registry."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.services.mcp_control_plane.sdk import check_mutation_dispatch, run_sdk

_MAX_TEXT = 255


class McpDatabaseError(ValueError):
    """Trove data is unavailable or current-project visibility cannot be proven."""


def _field(resource: Any, name: str) -> Any:
    if isinstance(resource, Mapping):
        return resource.get(name)
    return getattr(resource, name, None)


def _required_text(resource: Any, name: str) -> str:
    value = _field(resource, name)
    if not isinstance(value, str) or not value or len(value) > _MAX_TEXT:
        raise McpDatabaseError(f"Trove instance {name} is missing or malformed")
    return value


def _optional_text(resource: Any, *names: str) -> str | None:
    for name in names:
        value = _field(resource, name)
        if value is None:
            continue
        if isinstance(value, str) and len(value) <= _MAX_TEXT:
            return value
        if hasattr(value, "isoformat"):
            return value.isoformat()
        raise McpDatabaseError(f"Trove instance {name} is malformed")
    return None


def _assert_project_scope(conn: Any, *, project_id: str) -> None:
    if getattr(conn, "_afterglow_project_id", None) != project_id:
        raise McpDatabaseError("Trove connection project scope cannot be proven")


def _safe_instance(resource: Any, *, project_id: str) -> dict[str, str | None]:
    owner_project_id = _field(resource, "tenant_id") or _field(resource, "project_id")
    if owner_project_id is not None and owner_project_id != project_id:
        raise McpDatabaseError("Trove instance owner conflicts with connection scope")
    datastore = _field(resource, "datastore")
    if not isinstance(datastore, Mapping):
        raise McpDatabaseError("Trove instance datastore is malformed")
    return {
        "id": _required_text(resource, "id"),
        "name": _required_text(resource, "name"),
        "status": _required_text(resource, "status"),
        "datastore_type": _required_text(datastore, "type"),
        "datastore_version": _required_text(datastore, "version"),
        "created_at": _optional_text(resource, "created", "created_at"),
    }


def _response_body(response: Any) -> Mapping[str, Any]:
    body = response.json() if hasattr(response, "json") else None
    if not isinstance(body, Mapping):
        raise McpDatabaseError("Trove response is malformed")
    return body


def _list_instances(conn: Any, *, project_id: str, limit: int) -> list[dict[str, str | None]]:
    _assert_project_scope(conn, project_id=project_id)
    body = _response_body(conn.database.get("/instances"))
    instances = body.get("instances")
    if not isinstance(instances, list):
        raise McpDatabaseError("Trove instance list is malformed")
    safe_instances: list[dict[str, str | None]] = []
    for instance in instances:
        if not isinstance(instance, Mapping) or instance.get("deleted"):
            continue
        safe_instances.append(_safe_instance(instance, project_id=project_id))
        if len(safe_instances) == limit:
            break
    return safe_instances


def _get_instance(conn: Any, *, project_id: str, instance_id: str) -> dict[str, str | None]:
    _assert_project_scope(conn, project_id=project_id)
    body = _response_body(conn.database.get(f"/instances/{instance_id}"))
    instance = body.get("instance")
    if not isinstance(instance, Mapping) or instance.get("deleted"):
        raise McpDatabaseError("Trove instance was not found")
    return _safe_instance(instance, project_id=project_id)


def _require_success(response: Any) -> None:
    if hasattr(response, "raise_for_status"):
        response.raise_for_status()
        return
    status_code = getattr(response, "status_code", None)
    if isinstance(status_code, int) and status_code >= 400:
        raise McpDatabaseError("Trove mutation request failed")


def _prepare_instance_restart(conn: Any, *, project_id: str, instance_id: str) -> dict[str, str | None]:
    instance = _get_instance(conn, project_id=project_id, instance_id=instance_id)
    if str(instance["status"]).upper() != "ACTIVE":
        raise McpDatabaseError("Trove instance is not in a state that permits restart")
    return {**instance, "requested_action": "restart"}


def _restart_instance(conn: Any, *, project_id: str, instance_id: str) -> dict[str, str | None]:
    instance = _prepare_instance_restart(conn, project_id=project_id, instance_id=instance_id)
    check_mutation_dispatch()
    response = conn.database.post(f"/instances/{instance_id}/action", json={"restart": {}})
    _require_success(response)
    return instance


def _prepare_instance_delete(conn: Any, *, project_id: str, instance_id: str) -> dict[str, str | None]:
    instance = _get_instance(conn, project_id=project_id, instance_id=instance_id)
    if str(instance["status"]).upper() not in {"ACTIVE", "SHUTDOWN", "ERROR"}:
        raise McpDatabaseError("Trove instance is not in a state that permits deletion")
    return {**instance, "requested_action": "delete"}


def _delete_instance(conn: Any, *, project_id: str, instance_id: str) -> dict[str, str | None]:
    instance = _prepare_instance_delete(conn, project_id=project_id, instance_id=instance_id)
    check_mutation_dispatch()
    response = conn.database.delete(f"/instances/{instance_id}")
    _require_success(response)
    return instance


async def list_project_database_instances(conn: Any, *, project_id: str, limit: int) -> list[dict[str, str | None]]:
    """List current-project Trove records through an independently scoped connection."""
    try:
        return await run_sdk(_list_instances, conn, project_id=project_id, limit=limit)
    except McpDatabaseError:
        raise
    except Exception as exc:
        raise McpDatabaseError("Trove instance list is unavailable") from exc


async def get_project_database_instance(conn: Any, *, project_id: str, instance_id: str) -> dict[str, str | None]:
    """Read one Trove instance through an independently scoped connection."""
    try:
        return await run_sdk(_get_instance, conn, project_id=project_id, instance_id=instance_id)
    except McpDatabaseError:
        raise
    except Exception as exc:
        raise McpDatabaseError("Trove instance is unavailable") from exc


async def preview_project_database_instance_restart(
    conn: Any, *, project_id: str, instance_id: str
) -> dict[str, str | None]:
    """Validate a restart against current exact-project Trove instance state."""
    try:
        return await run_sdk(
            _prepare_instance_restart,
            conn,
            project_id=project_id,
            instance_id=instance_id,
        )
    except McpDatabaseError:
        raise
    except Exception as exc:
        raise McpDatabaseError("Trove instance restart is unavailable") from exc


async def request_project_database_instance_restart(
    conn: Any, *, project_id: str, instance_id: str
) -> dict[str, str | None]:
    """Restart an active exact-project Trove instance after final validation."""
    try:
        return await run_sdk(
            _restart_instance,
            conn,
            project_id=project_id,
            instance_id=instance_id,
        )
    except McpDatabaseError:
        raise
    except Exception as exc:
        raise McpDatabaseError("Trove instance restart is unavailable") from exc


async def preview_project_database_instance_delete(
    conn: Any, *, project_id: str, instance_id: str
) -> dict[str, str | None]:
    """Validate a deletion against current exact-project Trove instance state."""
    try:
        return await run_sdk(
            _prepare_instance_delete,
            conn,
            project_id=project_id,
            instance_id=instance_id,
        )
    except McpDatabaseError:
        raise
    except Exception as exc:
        raise McpDatabaseError("Trove instance deletion is unavailable") from exc


async def request_project_database_instance_delete(
    conn: Any, *, project_id: str, instance_id: str
) -> dict[str, str | None]:
    """Delete an exact-project Trove instance after final validation."""
    try:
        return await run_sdk(
            _delete_instance,
            conn,
            project_id=project_id,
            instance_id=instance_id,
        )
    except McpDatabaseError:
        raise
    except Exception as exc:
        raise McpDatabaseError("Trove instance deletion is unavailable") from exc
