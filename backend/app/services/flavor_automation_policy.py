"""Revision-fenced administrator approval and last-supported host registry.

Native liveness is observation, never retirement authority. This policy does not
claim native global quota enforcement or approve discovered PCI devices.
"""

from __future__ import annotations

import copy
import json
import re
from datetime import datetime
from urllib.parse import quote

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.database import get_session_factory, is_db_available
from app.models.compute_pools import MAX_AMOUNT
from app.models.db import RuntimeSetting
from app.models.flavor_automation import RC_PATTERN, validate_profiles
from app.services import identity_roles
from app.services.work_dispatcher import run_sync

KEY = "compute.flavor_automation_policy"
_MAX_HOSTS = 4096


def _default():
    return {"revision": 0, "hosts": [], "gpu_profiles": []}


def _validated(value):
    if value is None:
        return _default()
    try:
        if (
            not isinstance(value, dict)
            or set(value) != {"revision", "hosts", "gpu_profiles"}
            or type(value["revision"]) is not int
            or not 0 <= value["revision"] <= MAX_AMOUNT
            or not isinstance(value["hosts"], list)
            or len(value["hosts"]) > _MAX_HOSTS
            or not isinstance(value["gpu_profiles"], list)
            or len(value["gpu_profiles"]) > 128
        ):
            raise ValueError("malformed policy")
        result = copy.deepcopy(value)
        result["gpu_profiles"] = validate_profiles(value["gpu_profiles"])
        ids, names = set(), set()
        for host in result["hosts"]:
            if (
                not isinstance(host, dict)
                or not isinstance(host.get("id"), str)
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", host["id"])
                or not isinstance(host.get("name"), str)
                or not 1 <= len(host["name"]) <= 255
                or host["id"] in ids
                or host["name"] in names
                or type(host.get("removed")) is not bool
                or not isinstance(host.get("observed_at"), str)
                or datetime.fromisoformat(host["observed_at"]).tzinfo is None
                or not isinstance(host.get("gpu"), dict)
            ):
                raise ValueError("malformed retained host")
            ids.add(host["id"])
            names.add(host["name"])
            for resource in ("cpu", "ram", *(("pcpu",) if "pcpu" in host else ())):
                inventory = host.get(resource)
                if (
                    not isinstance(inventory, dict)
                    or set(inventory) != {"capacity", "min", "step"}
                    or any(
                        type(amount) is not int or amount < (0 if key == "capacity" else 1)
                        for key, amount in inventory.items()
                    )
                ):
                    raise ValueError("malformed retained inventory")
            if any(
                not RC_PATTERN.fullmatch(rc) or type(amount) is not int or amount < 0
                for rc, amount in host["gpu"].items()
            ):
                raise ValueError("malformed retained PCI inventory")
        if len(json.dumps(result)) > 4_194_304:
            raise ValueError("policy exceeds bound")
        return result
    except (KeyError, TypeError, ValueError, ValidationError):
        raise HTTPException(503, "flavor_automation_policy_unavailable") from None


def _factory():
    factory = get_session_factory()
    if not is_db_available() or factory is None:
        raise HTTPException(503, "flavor_automation_storage_unavailable")
    return factory


async def load_policy():
    """Validate stored approval without native calls, discovery or writes."""
    try:
        async with _factory()() as session:
            row = await session.get(RuntimeSetting, KEY)
            return _validated(row.value_json if row else None)
    except SQLAlchemyError:
        raise HTTPException(503, "flavor_automation_storage_unavailable") from None


async def _save(policy, *, expected_revision, user_id=None):
    policy = _validated(policy)
    try:
        async with _factory()() as session, session.begin():
            row = await session.get(RuntimeSetting, KEY, with_for_update=True)
            if _validated(row.value_json if row else None)["revision"] != expected_revision:
                raise HTTPException(409, "flavor_automation_revision_conflict")
            if row is None:
                row = RuntimeSetting(setting_key=KEY)
                session.add(row)
            row.value_json = copy.deepcopy(policy)
            if user_id is not None:
                row.updated_by_user_id = user_id
        if await load_policy() != policy:
            raise HTTPException(503, "flavor_automation_policy_readback_mismatch")
    except SQLAlchemyError:
        raise HTTPException(503, "flavor_automation_storage_unavailable") from None


def _revision(policy, expected):
    if policy["revision"] != expected:
        raise HTTPException(409, "flavor_automation_revision_conflict")
    if expected >= MAX_AMOUNT:
        raise HTTPException(409, "flavor_automation_revision_exhausted")


def _audio_companion(name, resource):
    """A companion is not automatically an audio function."""
    if "audio" in name.lower():
        return True
    from app.services.gpu_inventory import PCI_DEVICE_MAP

    parts = resource.split("_")
    device = PCI_DEVICE_MAP.get(parts[2], {}).get(parts[3])
    return isinstance(device, dict) and device.get("is_audio") is True


async def capabilities():
    policy = await load_policy()
    profiles = [profile for profile in policy["gpu_profiles"] if profile["enabled"]]
    primary, pci, kinds = [], [], {}
    for profile in profiles:
        mapping = profile["alias_resource_classes"]
        companions = [name for name, rc in mapping.items() if rc != profile["resource_class"]]
        for resource in profile["resource_requirements"]:
            kinds[resource] = "gpu" if resource == profile["resource_class"] else "companion"
        for name, resource in mapping.items():
            gpu = resource == profile["resource_class"]
            row = {
                "name": name,
                "resource_class": resource,
                "is_gpu": gpu,
                "is_companion": not gpu,
                "is_audio": not gpu and _audio_companion(name, resource),
                "classification_verified": True,
                "companions_verified": True,
                "companion_aliases": companions if gpu else [],
                "resource_requirements": dict(profile["resource_requirements"]),
                "profile_name": profile["name"],
            }
            pci.append(row)
            if gpu:
                primary.append(dict(row))
        for resource in profile["resource_requirements"]:
            if resource in mapping.values():
                continue
            gpu = resource == profile["resource_class"]
            row = {
                "name": profile["name"] if gpu else resource,
                "resource_class": resource,
                "is_gpu": gpu,
                "is_companion": not gpu,
                "is_audio": not gpu and _audio_companion("", resource),
                "classification_verified": True,
                "companions_verified": True,
                "companion_aliases": [],
                "resource_requirements": dict(profile["resource_requirements"]),
                "profile_name": profile["name"],
                "display_only": True,
            }
            pci.append(row)
            if gpu:
                primary.append(dict(row))
    pci = list({(row["name"], row["resource_class"], row.get("display_only", False)): row for row in pci}.values())
    return {
        "schema": 1,
        "revision": policy["revision"],
        "policy_ready": True,
        "control_scope": "afterglow",
        "aliases": primary,
        "pci_aliases": pci,
        "unsupported_aliases": [],
        "gpu_profiles": profiles,
        "resource_kinds": kinds,
    }


async def _authorize(token_info):
    from app.api.deps import require_admin

    return await require_admin(token_info)


@identity_roles._complete_mutation
async def update_profiles(conn, *, revision, gpu_profiles, token_info):
    try:
        profiles = validate_profiles(gpu_profiles)
    except (ValueError, ValidationError):
        raise HTTPException(422, "flavor_automation_profiles_invalid") from None
    async with identity_roles._graph_lock(conn) as lease:
        await _authorize(token_info)
        policy = await load_policy()
        _revision(policy, revision)
        policy.update(gpu_profiles=profiles, revision=revision + 1)
        await lease.assert_owned()
        await _authorize(token_info)
        await _save(policy, expected_revision=revision, user_id=token_info["user_id"])
        return policy


def _supports_previous(observed, previous):
    for resource in ("cpu", "ram", *(("pcpu",) if "pcpu" in previous else ())):
        new = observed.get(resource, {"capacity": 0, "min": 1, "step": 1})
        old = previous[resource]
        if new["capacity"] < old["capacity"] or new["min"] > old["min"] or old["step"] % new["step"]:
            return False
    return all(observed["gpu"].get(resource, 0) >= amount for resource, amount in previous["gpu"].items())


def merge_hosts(policy, observed, *, complete):
    """Never shrink supported hardware or erase a tombstone from observation."""
    merged = copy.deepcopy(policy)
    hosts = {host["id"]: host for host in merged["hosts"]}
    seen = set()
    for observation in observed:
        hid = observation["id"]
        if hid in seen:
            raise ValueError("duplicate observed host")
        seen.add(hid)
        previous = hosts.get(hid)
        if previous is not None:
            if previous["name"] != observation["name"]:
                raise ValueError("retained compute host identity changed")
            replacement = {**observation, "removed": previous["removed"]}
            if (
                observation.get("state") != "up"
                or observation.get("status") != "enabled"
                or not _supports_previous(observation, previous)
            ):
                for key in ("cpu", "ram", "gpu", *(("pcpu",) if "pcpu" in previous else ())):
                    replacement[key] = previous[key]
                replacement["inventory_retained"] = True
            hosts[hid] = replacement
        else:
            hosts[hid] = {**observation, "removed": False}
    for hid, host in hosts.items():
        if hid not in seen:
            host["state"] = "missing" if complete else "unknown"
            host["status"] = "observation_unavailable"
    merged["hosts"] = sorted(hosts.values(), key=lambda host: host["id"])
    return _validated(merged)


async def discover_locked(conn, lease, *, token_info=None, staged_facts=None):
    """Merge observations into current policy under the caller's graph lease.

    Staged facts are read-only evidence, not policy authority. A None observation
    records failed discovery and retains the same latest-policy fallback.
    """
    from app.services.managed_flavors import supported_hosts

    policy = await load_policy()
    try:
        observations, complete = staged_facts if staged_facts is not None else await run_sync(supported_hosts, conn)
        if observations is None:
            raise ValueError("staged inventory unavailable")
    except Exception:
        if not policy["hosts"]:
            raise HTTPException(503, "flavor_automation_inventory_unavailable") from None
        observations, complete = [], False
    merged = merge_hosts(policy, observations, complete=complete)

    def material(value):
        return {
            **value,
            "hosts": [{key: item for key, item in host.items() if key != "observed_at"} for host in value["hosts"]],
        }

    if material(merged) == material(policy):
        return policy
    _revision(policy, policy["revision"])
    merged["revision"] += 1
    await lease.assert_owned()
    if token_info is not None:
        await _authorize(token_info)
    await _save(merged, expected_revision=policy["revision"], user_id=token_info["user_id"] if token_info else None)
    return merged


@identity_roles._complete_mutation
async def discover(conn, *, token_info):
    async with identity_roles._graph_lock(conn) as lease:
        await _authorize(token_info)
        return await discover_locked(conn, lease, token_info=token_info)


def _services(conn):
    # 2.69 exposes unavailable-cell services as partial UNKNOWN rows rather than
    # silently omitting them. Reject those rows before claiming directory absence.
    endpoint = conn.compute.get_endpoint().rstrip("/")
    response = conn.session.request(
        endpoint + "/os-services",
        "GET",
        params={"binary": "nova-compute"},
        headers={"OpenStack-API-Version": "compute 2.69"},
        timeout=5,
        connect_retries=0,
        status_code_retries=0,
        allow_reauth=False,
        redirect=False,
        raise_exc=False,
    )
    if type(response.status_code) is not int or not 200 <= response.status_code < 300:
        raise ValueError("compute service directory unavailable")
    body = response.json()
    if not isinstance(body, dict):
        raise ValueError("malformed compute service directory")
    if (
        not isinstance(body.get("services"), list)
        or len(body["services"]) > _MAX_HOSTS
        or body.get("services_links")
        or body.get("links", {}).get("next")
        or body.get("truncated")
        or body.get("limited")
    ):
        raise ValueError("incomplete compute service directory")
    services, ids = [], set()
    for service in body["services"]:
        if (
            not isinstance(service, dict)
            or service.get("binary") != "nova-compute"
            or not isinstance(service.get("id"), str)
            or not service["id"]
            or service["id"] in ids
            or not isinstance(service.get("host"), str)
            or not service["host"]
            or service.get("status") not in ("enabled", "disabled")
        ):
            raise ValueError("malformed compute service directory")
        ids.add(service["id"])
        services.append(service)
    return services


def _disable(conn, service_id):
    endpoint = conn.compute.get_endpoint().rstrip("/")
    response = conn.session.request(
        endpoint + "/os-services/" + quote(service_id, safe=""),
        "PUT",
        json={"status": "disabled"},
        headers={"OpenStack-API-Version": "compute 2.53"},
        timeout=5,
        connect_retries=0,
        status_code_retries=0,
        allow_reauth=False,
        redirect=False,
        raise_exc=False,
    )
    if type(response.status_code) is not int or not 200 <= response.status_code < 300:
        raise ValueError("compute service disable outcome unknown")


@identity_roles._complete_mutation
async def update_host(conn, host_id, *, revision, removed, token_info):
    async with identity_roles._graph_lock(conn) as lease:
        await _authorize(token_info)
        policy = await load_policy()
        _revision(policy, revision)
        host = next((row for row in policy["hosts"] if row["id"] == host_id), None)
        if host is None:
            raise HTTPException(404, "flavor_automation_host_not_found")
        if removed:
            try:
                services = await run_sync(_services, conn)
                matching = [row for row in services if row["host"] == host["name"]]
                if len(matching) > 1:
                    raise ValueError("ambiguous compute service")
                if matching:
                    service = matching[0]
                    await lease.assert_owned()
                    await _authorize(token_info)
                    if service["status"] != "disabled":
                        await run_sync(_disable, conn, service["id"])
                    after = await run_sync(_services, conn)
                    readback = [row for row in after if row["host"] == host["name"]]
                    if len(readback) != 1 or readback[0]["id"] != service["id"] or readback[0]["status"] != "disabled":
                        raise ValueError("compute disable readback mismatch")
                    host["status"] = "disabled"
            except HTTPException:
                raise
            except Exception:
                raise HTTPException(503, "flavor_automation_host_retirement_unknown") from None
        # Re-inclusion changes catalog policy only: NEVER enable native maintenance.
        host["removed"] = removed
        policy["revision"] += 1
        await lease.assert_owned()
        await _authorize(token_info)
        await _save(policy, expected_revision=revision, user_id=token_info["user_id"])
        return policy
