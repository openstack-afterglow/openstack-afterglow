"""Project-owned, redacted Swift object storage account read adapter for consumer MCP."""

from __future__ import annotations

from typing import Any

from app.services import swift as swift_service
from app.services.mcp_control_plane.sdk import run_sdk


class McpObjectStorageError(ValueError):
    """Swift account data is unavailable or cannot be safely projected."""


async def get_project_swift_account(conn: Any) -> dict[str, int]:
    """Return strictly project-scoped Swift account aggregate metrics."""
    try:
        data = await run_sdk(swift_service.get_account_metadata, conn, strict=True)
        return {
            "container_count": int(data.get("container_count", 0) or 0),
            "object_count": int(data.get("object_count", 0) or 0),
            "bytes_used": int(data.get("bytes_used", 0) or 0),
        }
    except Exception as exc:
        raise McpObjectStorageError("Swift account metadata source is unavailable") from exc
