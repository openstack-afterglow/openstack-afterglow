"""Project-scoped, redacted dashboard adapters for consumer MCP tools."""

from __future__ import annotations

import math
from typing import Any

from app.services import cinder, nova
from app.services import manila as manila_service
from app.services import neutron as neutron_service
from app.services.mcp_control_plane.sdk import gather_sdk, run_sdk


class McpDashboardError(RuntimeError):
    """Dashboard data is incomplete or cannot be safely projected."""


def _quota_entry(raw: object, key: str, *, usage_keys: tuple[str, ...] = ("in_use",)) -> dict[str, float | int]:
    if not isinstance(raw, dict) or not isinstance(raw.get(key), dict):
        raise McpDashboardError(f"MCP quota data is missing {key}")
    entry = raw[key]
    usage_key = next((candidate for candidate in usage_keys if candidate in entry), None)
    if usage_key is None:
        raise McpDashboardError(f"MCP quota data is missing usage for {key}")
    limit, in_use = entry.get("limit"), entry.get(usage_key)
    if (
        not isinstance(limit, (int, float))
        or isinstance(limit, bool)
        or not isinstance(in_use, (int, float))
        or isinstance(in_use, bool)
        or not math.isfinite(float(limit))
        or not math.isfinite(float(in_use))
        or limit < -1
        or in_use < 0
    ):
        raise McpDashboardError(f"MCP quota data is invalid for {key}")
    return {"limit": limit, "in_use": in_use}


async def project_quotas(conn: Any, *, project_id: str, manila_enabled: bool) -> dict[str, object]:
    """Return only fixed dashboard quota fields from an exact project connection."""
    calls: dict[str, object] = {
        "compute": run_sdk(nova.get_project_quota, conn, project_id, strict=True),
        "storage": run_sdk(cinder.get_volume_quota, conn, project_id, strict=True),
        "network": run_sdk(neutron_service.get_network_quota, conn, project_id, strict=True),
    }
    if manila_enabled:
        calls["file_storage"] = run_sdk(manila_service.get_file_storage_quota, conn, strict=True)
    results = await gather_sdk(*calls.values())
    settled = dict(zip(calls, results, strict=True))
    if any(isinstance(value, BaseException) for value in settled.values()):
        raise McpDashboardError("MCP quota source is unavailable")
    return {
        "compute": {
            "instances": _quota_entry(settled["compute"], "instances"),
            "cores": _quota_entry(settled["compute"], "cores"),
            "ram": _quota_entry(settled["compute"], "ram"),
        },
        "storage": {
            "volumes": _quota_entry(settled["storage"], "volumes"),
            "gigabytes": _quota_entry(settled["storage"], "gigabytes"),
        },
        "network": {"floatingip": _quota_entry(settled["network"], "floatingip", usage_keys=("used", "in_use"))},
        "file_storage": (
            {
                "shares": _quota_entry(settled["file_storage"], "shares"),
                "gigabytes": _quota_entry(settled["file_storage"], "gigabytes"),
            }
            if manila_enabled
            else None
        ),
    }
