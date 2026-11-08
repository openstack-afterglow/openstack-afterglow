"""Waygate-managed resource markers and the single lock refusal used by Afterglow surfaces.

Waygate creates VPN gateway VMs in the requester's project and controls them with its own
trust token. Afterglow must not delete, reconfigure, or detach them (or their
``afterglow-waygate-*`` security groups); doing so silently breaks the VPN. Only the
project surfaces (REST and MCP) are locked: the system-admin surface stays available for
production repair, and native OpenStack API access outside Afterglow is not covered.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import HTTPException

MARKER_MANAGED = "afterglow_managed"
MARKER_TYPE = "waygate_type"
MARKER_SERVER_ID = "waygate_server_id"
MARKER_CREATE_INTENT = "waygate_create_intent"
GATEWAY_TYPE = "gateway"
SECURITY_GROUP_PREFIX = "afterglow-waygate-"

WAYGATE_MANAGED_RESOURCE = "waygate_managed_resource"
WAYGATE_MANAGED_DETAIL = "This resource is managed by Waygate; change it through Waygate"

_TRUE_VALUES = frozenset({"true", "1", "yes"})


class WaygateManagedResourceError(ValueError):
    """Raised by non-HTTP surfaces (MCP); the message carries the stable code."""

    code = WAYGATE_MANAGED_RESOURCE

    def __init__(self) -> None:
        super().__init__(f"{WAYGATE_MANAGED_RESOURCE}: {WAYGATE_MANAGED_DETAIL}")


def _truthy(value: Any) -> bool:
    if value is True:
        return True
    return isinstance(value, str) and value.strip().lower() in _TRUE_VALUES


def is_waygate_managed_server(metadata: Mapping[str, Any] | None) -> bool:
    """True only for the full gateway marker; ``afterglow_managed`` alone is used by other builders."""
    if not isinstance(metadata, Mapping):
        return False
    server_id = metadata.get(MARKER_SERVER_ID)
    return (
        metadata.get(MARKER_TYPE) == GATEWAY_TYPE
        and isinstance(server_id, str)
        and bool(server_id.strip())
        and _truthy(metadata.get(MARKER_MANAGED))
    )


def is_waygate_managed_security_group(name: Any) -> bool:
    return isinstance(name, str) and name.startswith(SECURITY_GROUP_PREFIX)


def _field(resource: Any, name: str) -> Any:
    return resource.get(name) if isinstance(resource, Mapping) else getattr(resource, name, None)


def server_is_waygate_managed(server: Any) -> bool:
    metadata = _field(server, "metadata")
    return is_waygate_managed_server(metadata if isinstance(metadata, Mapping) else None)


def waygate_managed_http_error() -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={"code": WAYGATE_MANAGED_RESOURCE, "message": WAYGATE_MANAGED_DETAIL},
    )


def ensure_server_not_waygate_managed(server: Any) -> None:
    """Refuse an Afterglow REST mutation of a Waygate gateway VM (HTTP 409)."""
    if server_is_waygate_managed(server):
        raise waygate_managed_http_error()


def ensure_security_group_not_waygate_managed(security_group: Any) -> None:
    if is_waygate_managed_security_group(_field(security_group, "name")):
        raise waygate_managed_http_error()


def port_device_is_waygate_managed(conn: Any, port: Any) -> bool:
    """Synchronous SDK check: is this Neutron port bound to a Waygate gateway VM?

    Provider read failures propagate so callers fail closed.
    """
    device_id = _field(port, "device_id")
    device_owner = _field(port, "device_owner")
    if not device_id or not isinstance(device_owner, str) or not device_owner.startswith("compute:"):
        return False
    return server_is_waygate_managed(conn.compute.get_server(device_id))


def require_server_not_waygate_managed(server: Any) -> None:
    """MCP/service variant: raise the stable non-HTTP refusal."""
    if server_is_waygate_managed(server):
        raise WaygateManagedResourceError()
