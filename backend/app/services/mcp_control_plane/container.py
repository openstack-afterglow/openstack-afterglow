"""Project-owned, redacted Zun read adapters for the consumer MCP registry."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.services.mcp_control_plane.sdk import check_mutation_dispatch, run_sdk

_MAX_TEXT = 255


class McpContainerError(ValueError):
    """Zun data is unavailable or does not prove current-project ownership."""


def _field(resource: Any, name: str) -> Any:
    if isinstance(resource, Mapping):
        return resource.get(name)
    return getattr(resource, name, None)


def _required_text(resource: Any, name: str) -> str:
    value = _field(resource, name)
    if not isinstance(value, str) or not value or len(value) > _MAX_TEXT:
        raise McpContainerError(f"Zun container {name} is missing or malformed")
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
        raise McpContainerError(f"Zun container {name} is malformed")
    return None


def _endpoint(conn: Any) -> str:
    endpoint = conn.session.get_endpoint(service_type="container", interface="public")
    if not isinstance(endpoint, str) or not endpoint.startswith(("https://", "http://")):
        raise McpContainerError("Zun endpoint is unavailable")
    return endpoint.rstrip("/").removesuffix("/v1")


def _response_body(response: Any) -> Mapping[str, Any]:
    body = response.json() if hasattr(response, "json") else None
    if not isinstance(body, Mapping):
        raise McpContainerError("Zun response is malformed")
    return body


def _safe_container(resource: Any, *, project_id: str) -> dict[str, str | None]:
    owner_project_id = _field(resource, "project_id") or _field(resource, "tenant_id")
    if owner_project_id != project_id:
        raise McpContainerError("Zun container ownership cannot be proven")
    return {
        "id": _required_text(resource, "uuid"),
        "name": _required_text(resource, "name"),
        "status": _required_text(resource, "status"),
        "image": _optional_text(resource, "image"),
        "created_at": _optional_text(resource, "created_at", "created"),
    }


def _list_containers(conn: Any, *, project_id: str, limit: int) -> list[dict[str, str | None]]:
    body = _response_body(conn.session.get(f"{_endpoint(conn)}/v1/containers"))
    containers = body.get("containers")
    if not isinstance(containers, list):
        raise McpContainerError("Zun container list is malformed")
    safe_containers: list[dict[str, str | None]] = []
    for container in containers:
        if not isinstance(container, Mapping):
            raise McpContainerError("Zun container record is malformed")
        safe_containers.append(_safe_container(container, project_id=project_id))
        if len(safe_containers) == limit:
            break
    return safe_containers


def _get_container(conn: Any, *, project_id: str, container_id: str) -> dict[str, str | None]:
    body = _response_body(conn.session.get(f"{_endpoint(conn)}/v1/containers/{container_id}"))
    container = body.get("container", body)
    if not isinstance(container, Mapping):
        raise McpContainerError("Zun container was not found")
    return _safe_container(container, project_id=project_id)


_CONTAINER_ACTIONS: dict[str, frozenset[str]] = {
    "start": frozenset({"STOPPED"}),
    "stop": frozenset({"RUNNING"}),
}


def _require_success(response: Any) -> None:
    if hasattr(response, "raise_for_status"):
        response.raise_for_status()
        return
    status_code = getattr(response, "status_code", None)
    if isinstance(status_code, int) and status_code >= 400:
        raise McpContainerError("Zun mutation request failed")


def _prepare_container_action(conn: Any, *, project_id: str, container_id: str, action: str) -> dict[str, str | None]:
    container = _get_container(conn, project_id=project_id, container_id=container_id)
    allowed_statuses = _CONTAINER_ACTIONS.get(action)
    if allowed_statuses is None or str(container["status"]).upper() not in allowed_statuses:
        raise McpContainerError("Zun container is not in a state that permits this action")
    return {**container, "requested_action": action}


def _action_container(conn: Any, *, project_id: str, container_id: str, action: str) -> dict[str, str | None]:
    container = _prepare_container_action(conn, project_id=project_id, container_id=container_id, action=action)
    endpoint = _endpoint(conn)
    check_mutation_dispatch()
    response = conn.session.post(f"{endpoint}/v1/containers/{container_id}/{action}")
    _require_success(response)
    return container


def _prepare_container_delete(conn: Any, *, project_id: str, container_id: str) -> dict[str, str | None]:
    container = _get_container(conn, project_id=project_id, container_id=container_id)
    if str(container["status"]).upper() not in {"STOPPED", "CREATED", "ERROR"}:
        raise McpContainerError("Zun container must be stopped before deletion")
    return {**container, "requested_action": "delete"}


def _delete_container(conn: Any, *, project_id: str, container_id: str) -> dict[str, str | None]:
    container = _prepare_container_delete(conn, project_id=project_id, container_id=container_id)
    endpoint = _endpoint(conn)
    check_mutation_dispatch()
    response = conn.session.delete(f"{endpoint}/v1/containers/{container_id}")
    _require_success(response)
    return container


async def list_project_containers(conn: Any, *, project_id: str, limit: int) -> list[dict[str, str | None]]:
    """List only raw Zun records that independently prove exact project ownership."""
    try:
        return await run_sdk(_list_containers, conn, project_id=project_id, limit=limit)
    except McpContainerError:
        raise
    except Exception as exc:
        raise McpContainerError("Zun container list is unavailable") from exc


async def get_project_container(conn: Any, *, project_id: str, container_id: str) -> dict[str, str | None]:
    """Read one Zun container only after the raw response proves ownership."""
    try:
        return await run_sdk(_get_container, conn, project_id=project_id, container_id=container_id)
    except McpContainerError:
        raise
    except Exception as exc:
        raise McpContainerError("Zun container is unavailable") from exc


async def preview_project_container_action(
    conn: Any, *, project_id: str, container_id: str, action: str
) -> dict[str, str | None]:
    """Validate a bounded container action against current exact-project state."""
    try:
        return await run_sdk(
            _prepare_container_action,
            conn,
            project_id=project_id,
            container_id=container_id,
            action=action,
        )
    except McpContainerError:
        raise
    except Exception as exc:
        raise McpContainerError("Zun container action is unavailable") from exc


async def request_project_container_action(
    conn: Any, *, project_id: str, container_id: str, action: str
) -> dict[str, str | None]:
    """Request a bounded action only after final exact-project ownership/state validation."""
    try:
        return await run_sdk(
            _action_container,
            conn,
            project_id=project_id,
            container_id=container_id,
            action=action,
        )
    except McpContainerError:
        raise
    except Exception as exc:
        raise McpContainerError("Zun container action is unavailable") from exc


async def preview_project_container_delete(conn: Any, *, project_id: str, container_id: str) -> dict[str, str | None]:
    """Validate one stopped exact-project container deletion without dispatching it."""
    try:
        return await run_sdk(
            _prepare_container_delete,
            conn,
            project_id=project_id,
            container_id=container_id,
        )
    except McpContainerError:
        raise
    except Exception as exc:
        raise McpContainerError("Zun container deletion is unavailable") from exc


async def request_project_container_delete(conn: Any, *, project_id: str, container_id: str) -> dict[str, str | None]:
    """Delete only a stopped exact-project container without implicit stop or force."""
    try:
        return await run_sdk(
            _delete_container,
            conn,
            project_id=project_id,
            container_id=container_id,
        )
    except McpContainerError:
        raise
    except Exception as exc:
        raise McpContainerError("Zun container deletion is unavailable") from exc
