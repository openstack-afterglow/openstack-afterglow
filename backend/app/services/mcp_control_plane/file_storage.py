"""Project-owned, redacted Manila file storage quota read adapter for consumer MCP."""

from __future__ import annotations

from typing import Any

from app.services import manila as manila_service
from app.services.mcp_control_plane.sdk import run_sdk


class McpFileStorageError(ValueError):
    """Manila quota data is unavailable or cannot be safely projected."""


async def get_project_share_quota(conn: Any) -> dict[str, Any]:
    """Return project Manila quota limits and usage projected into numeric limits/in_use."""
    try:
        quota = await run_sdk(manila_service.get_file_storage_quota, conn, strict=True)
        return {
            "shares": {
                "limit": quota["shares"]["limit"],
                "in_use": quota["shares"]["in_use"],
            },
            "gigabytes": {
                "limit": quota["gigabytes"]["limit"],
                "in_use": quota["gigabytes"]["in_use"],
            },
        }
    except Exception as exc:
        raise McpFileStorageError("Manila quota source is unavailable") from exc
