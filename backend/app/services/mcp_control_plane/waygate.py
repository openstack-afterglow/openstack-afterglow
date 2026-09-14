"""Project-owned, redacted Waygate server adapter for consumer MCP."""

from __future__ import annotations

import asyncio
from typing import Any

from app.services.keystone import get_waygate_proxy


class McpWaygateError(ValueError):
    """Waygate metadata is unavailable or current-project scope cannot be proven."""


def _safe_server(server: dict[str, Any], *, project_id: str) -> dict[str, str | None]:
    if server.get("project_id") != project_id:
        raise McpWaygateError("Waygate server ownership cannot be proven")

    server_id = server.get("id")
    if not server_id:
        raise McpWaygateError("Waygate server id is missing")

    return {
        "id": str(server_id),
        "name": str(server.get("name") or ""),
        "status": str(server.get("status") or ""),
        "created_at": str(server.get("created_at")) if server.get("created_at") else None,
        "updated_at": str(server.get("updated_at")) if server.get("updated_at") else None,
    }


def _list_servers(conn: object) -> object:
    return get_waygate_proxy(conn).servers()


def _get_server(conn: object, server_id: str) -> object:
    return get_waygate_proxy(conn).get_server(server_id)


async def list_project_waygate_servers(
    conn: object,
    project_id: str,
    *,
    limit: int,
) -> list[dict[str, str | None]]:
    """Return bounded, exact-project Waygate metadata through its catalog service."""
    try:
        servers = await asyncio.to_thread(_list_servers, conn)
        if not isinstance(servers, list):
            raise McpWaygateError("Waygate server list response is invalid")
        return [_safe_server(server, project_id=project_id) for server in servers[:limit]]
    except McpWaygateError:
        raise
    except Exception as exc:
        raise McpWaygateError("Waygate server list query failed") from exc


async def get_project_waygate_server(
    conn: object,
    project_id: str,
    server_id: str,
) -> dict[str, str | None]:
    """Return one exact-project Waygate server through its catalog service."""
    try:
        server = await asyncio.to_thread(_get_server, conn, server_id)
        if not isinstance(server, dict):
            raise McpWaygateError("Waygate server response is invalid")
        return _safe_server(server, project_id=project_id)
    except McpWaygateError:
        raise
    except Exception as exc:
        raise McpWaygateError("Waygate server query failed") from exc
