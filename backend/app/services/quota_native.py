"""Native quota transport shared by admin and domain quota orchestration.

``QUOTA_FIELDS`` maps API request keys to provider-native resource names.
``get_section`` and ``update_section`` are synchronous; ``read_project`` is the
independent, cancellation-safe async read boundary. Writes take native names
and only acknowledge transport completion: orchestration owns readback,
operation status, authorization, allocation fencing, and cache invalidation.
"""

import asyncio
import logging
from collections.abc import Iterable

from anyio import CancelScope

from app.config import get_settings
from app.services import manila

_logger = logging.getLogger(__name__)

# Request keys are unique even where two providers use the same quota name.
QUOTA_FIELDS = {
    "compute": {
        key: key
        for key in (
            "instances",
            "cores",
            "ram",
            "key_pairs",
            "server_groups",
            "server_group_members",
            "injected_files",
            "injected_file_content_bytes",
            "injected_file_path_bytes",
            "metadata_items",
        )
    },
    "volume": {key: key for key in ("volumes", "snapshots", "gigabytes")},
    "network": {
        key: key
        for key in ("network", "subnet", "port", "router", "floatingip", "security_group", "security_group_rule")
    },
    "file_storage": {
        "shares": "shares",
        "share_gigabytes": "gigabytes",
        "share_snapshots": "snapshots",
        "share_snapshot_gigabytes": "snapshot_gigabytes",
        "share_networks": "share_networks",
        "share_groups": "share_groups",
        "share_group_snapshots": "share_group_snapshots",
    },
}


class QuotaServiceDisabled(RuntimeError):
    """The requested native quota service is disabled in Afterglow."""


def _quota_entries(raw: object, keys: Iterable[str]) -> dict:
    """Keep only actual usage-bearing entries; never invent a limit or usage."""
    if not isinstance(raw, dict):
        raise ValueError("quota set is malformed")
    entries = {}
    for key in keys:
        item = raw.get(key)
        if item is None:
            continue  # Some deployments do not expose every optional quota.
        if (
            not isinstance(item, dict)
            or not all(type(item.get(field)) is int for field in ("limit", "in_use"))
            or item["limit"] < -1
            or item["in_use"] < 0
        ):
            raise ValueError("quota usage is malformed")
        entry = {"limit": item["limit"], "in_use": item["in_use"]}
        reserved = item.get("reserved")
        if type(reserved) is int and reserved >= 0:
            entry["reserved"] = reserved
        entries[key] = entry
    if not entries:
        raise ValueError("quota set has no usage")
    return entries


def _endpoint(conn, section: str) -> str:
    proxy = {"compute": "compute", "volume": "block_storage", "network": "network"}[section]
    endpoint = getattr(conn, proxy).get_endpoint()
    if not isinstance(endpoint, str) or not endpoint.strip():
        raise RuntimeError("quota service endpoint is unavailable")
    return endpoint.rstrip("/")


def _check_section(section: str) -> None:
    if section not in QUOTA_FIELDS:
        raise ValueError("unknown quota section")
    if section == "file_storage" and not get_settings().service_manila_enabled:
        raise QuotaServiceDisabled("file storage service is disabled")


def get_section(conn, project_id: str, section: str) -> dict:
    """Read native resource entries; unavailable/disabled services always raise.

    Missing resources stay absent, including optional reservation counts.
    Malformed limits/usage fail the section rather than fabricating zero usage.
    """
    _check_section(section)
    if section in ("compute", "volume"):
        url = f"{_endpoint(conn, section)}/os-quota-sets/{project_id}"
        if section == "compute":
            response = conn.session.get(f"{url}/detail")
        else:
            response = conn.session.get(url, params={"usage": "true"})
        response.raise_for_status()
        payload = response.json()
        raw = payload.get("quota_set") if isinstance(payload, dict) else None
    elif section == "network":
        _endpoint(conn, section)  # Do not accept data without a catalog endpoint.
        quota = conn.network.get_quota(project_id, details=True)
        raw = quota.to_dict(original_names=True) if hasattr(quota, "to_dict") else quota
        if isinstance(raw, dict):
            # Neutron calls the measured count 'used' rather than 'in_use'.
            raw = {
                key: {**value, "in_use": value.get("used", value.get("in_use"))} if isinstance(value, dict) else value
                for key, value in raw.items()
            }
    else:
        # get_client performs catalog/override discovery and refuses missing endpoints.
        payload = manila.get_client(conn).get(f"quota-sets/{project_id}/detail")
        raw = payload.get("quota_set") if isinstance(payload, dict) else None
    return _quota_entries(raw, QUOTA_FIELDS[section].values())


def update_section(conn, project_id: str, section: str, values: dict[str, int]) -> None:
    """PUT native resource limits once, propagating transport/status failures.

    ``values`` uses provider names, not the API's disambiguated share names.
    Completion is not verified quota state; the caller must read back even
    after errors because the service may already have committed the mutation.
    """
    _check_section(section)
    if not values or any(
        key not in QUOTA_FIELDS[section].values() or type(value) is not int or value < -1
        for key, value in values.items()
    ):
        raise ValueError("invalid native quota update")
    if section == "file_storage":
        # ManilaClient uses httpx's default non-retrying transport and checks status.
        manila.get_client(conn).put(f"quota-sets/{project_id}", {"quota_set": values})
        return
    endpoint = _endpoint(conn, section)
    path = "quotas" if section == "network" else "os-quota-sets"
    envelope = "quota" if section == "network" else "quota_set"
    # Use the session directly: resource **attrs can silently consume retry
    # kwargs as quota fields instead of forwarding them to the transport.
    response = conn.session.put(
        f"{endpoint}/{path}/{project_id}",
        json={envelope: values},
        connect_retries=0,
        status_code_retries=0,
    )
    response.raise_for_status()


async def read_project(conn, project_id: str) -> dict:
    """Return independent section results, settling workers before cancellation.

    A failed section is null with ``quota_unavailable``; disabled Manila is
    null with ``service_disabled``. Provider exception details never enter the
    DTO. The request-owned connection remains in use until *all* workers end.
    """
    result = {"project_id": project_id, **dict.fromkeys(QUOTA_FIELDS), "availability": {}, "errors": {}}
    calls = asyncio.gather(
        *(asyncio.to_thread(get_section, conn, project_id, section) for section in QUOTA_FIELDS),
        return_exceptions=True,
    )
    try:
        values = await asyncio.shield(calls)
    except asyncio.CancelledError:
        # AnyIO level cancellation and repeated Task.cancel() must not close
        # the connection while any executor thread is still using it.
        with CancelScope(shield=True):
            while not calls.done():
                try:
                    await asyncio.shield(calls)
                except asyncio.CancelledError:
                    continue
            calls.result()
        raise

    for section, value in zip(QUOTA_FIELDS, values, strict=True):
        if isinstance(value, BaseException):
            result["availability"][section] = False
            result["errors"][section] = (
                "service_disabled" if isinstance(value, QuotaServiceDisabled) else "quota_unavailable"
            )
            if not isinstance(value, QuotaServiceDisabled):
                _logger.warning("Native %s quota read failed", section, exc_info=value)
        else:
            result[section] = value
            result["availability"][section] = True
    return result
