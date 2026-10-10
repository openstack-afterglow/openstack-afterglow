"""Project-scoped, redacted Barbican secret metadata adapter for consumer MCP."""

from __future__ import annotations

from typing import Any

from app.services import barbican as barbican_service
from app.services.mcp_control_plane.sdk import run_sdk


class McpKeyManagerError(ValueError):
    """Barbican metadata is unavailable or cannot be safely projected."""


def _safe_secret_metadata(secret: dict[str, Any]) -> dict[str, Any]:
    secret_id = secret.get("id")
    if not secret_id:
        raise McpKeyManagerError("Barbican secret metadata is missing an id")

    return {
        "id": str(secret_id),
        "name": str(secret.get("name") or ""),
        "secret_type": str(secret.get("secret_type") or ""),
        "status": str(secret.get("status") or ""),
        "algorithm": str(secret.get("algorithm")) if secret.get("algorithm") else None,
        "bit_length": int(secret["bit_length"]) if secret.get("bit_length") is not None else None,
        "mode": str(secret.get("mode")) if secret.get("mode") else None,
        "created": str(secret.get("created")) if secret.get("created") else None,
        "expires": str(secret.get("expires")) if secret.get("expires") else None,
        "system_managed": bool(secret.get("system_managed", False)),
    }


async def list_project_secret_metadata(conn: Any, *, limit: int) -> list[dict[str, Any]]:
    """Return bounded secret metadata; never fetches or exposes secret payloads."""
    try:
        secrets = await run_sdk(barbican_service.list_secrets, conn, max_items=limit)
        return [_safe_secret_metadata(secret) for secret in secrets]
    except McpKeyManagerError:
        raise
    except Exception as exc:
        raise McpKeyManagerError("Barbican secret metadata is unavailable") from exc
