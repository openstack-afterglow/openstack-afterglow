"""Read-only configured Nova aliases and Placement-visible PCI observations.

Configuration is an effective-file snapshot, not running-process attestation.
Placement cannot prove physical completeness or GPU/audio same-card affinity.
"""

from __future__ import annotations

import json
import os
import re
import stat
import time
from datetime import datetime
from pathlib import Path

from app.models.flavor_automation import ALIAS_PATTERN
from app.services import flavor_automation_policy, gpu_inventory
from app.services.work_dispatcher import run_sync

ALIAS_SNAPSHOT_PATH = Path("/app/nova-pci-aliases/aliases.json")
_MAX_BYTES = 4_194_304
_MAX_CONTROLLERS = 128
_MAX_ALIASES = 4096
_MAX_PROVIDERS = 4096
_DEADLINE_SECONDS = 30.0
_CATALOG_UNAVAILABLE = object()
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_HEX = re.compile(r"^[0-9A-Fa-f]{4}$")
_RC = re.compile(r"^CUSTOM_PCI_([0-9A-F]{4})_([0-9A-F]{4})$")
_RESOURCE = re.compile(r"^[A-Z][A-Z0-9_]{0,254}$")
_BDF = re.compile(r"^(.+)_([0-9a-fA-F]{4}:[0-9a-fA-F]{2}:[01][0-9a-fA-F]\.[0-7])$")
_ALIAS_FIELDS = frozenset({"name", "vendor_id", "product_id", "resource_class", "device_type", "traits", "numa_policy"})


def _text(value, maximum=255):
    return isinstance(value, str) and 0 < len(value) <= maximum and value.isprintable()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _timestamp(value):
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 64:
        raise ValueError("invalid observation timestamp")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("unscoped observation timestamp")
    return parsed


def _kind(vendor, product, name="", device_map=None):
    if device_map is _CATALOG_UNAVAILABLE:
        return "unknown", None
    mapping = gpu_inventory.PCI_DEVICE_MAP if device_map is None else device_map
    info = mapping.get(vendor, {}).get(product)
    named_audio = "audio" in name.casefold()
    if info is not None:
        audio = info.get("is_audio")
        if audio is True:
            return "audio", info.get("name") if _text(info.get("name")) else None
        if audio is False and not named_audio:
            return "gpu", info.get("name") if _text(info.get("name")) else None
        return "unknown", None
    return ("audio" if named_audio else "unknown"), None


def _alias(raw, device_map=None):
    if not isinstance(raw, dict) or not _text(raw.get("name")):
        raise ValueError("invalid alias name")
    invalid = bool(raw.keys() - _ALIAS_FIELDS)
    for field in ("device_type", "numa_policy"):
        if raw.get(field) is not None and not _text(raw[field]):
            invalid = True
    traits = raw.get("traits")
    if traits is not None and not isinstance(traits, str) and traits != []:
        invalid = True
    if isinstance(traits, str) and (len(traits) > 4096 or not traits.isprintable() and traits != ""):
        invalid = True
    ids = []
    for field in ("vendor_id", "product_id"):
        value = raw.get(field)
        if value is not None and (not isinstance(value, str) or not _HEX.fullmatch(value)):
            invalid = True
            value = None
        ids.append(value.upper() if value is not None else None)
    vendor, product = ids
    default = f"CUSTOM_PCI_{vendor}_{product}" if vendor and product else None
    resource = raw.get("resource_class")
    if resource is None:
        resource = default
    elif not _text(resource):
        resource, invalid = None, True
    kind, device_name = _kind(vendor, product, raw["name"], device_map)
    supported = (
        not invalid
        and ALIAS_PATTERN.fullmatch(raw["name"]) is not None
        and default is not None
        and resource == default
        and raw.get("device_type") in (None, "type-PCI", "type-PF")
        and raw.get("traits") in (None, [], "")
        and raw.get("numa_policy") is None
    )
    row = {
        "name": raw["name"],
        "vendor_id": vendor,
        "product_id": product,
        "resource_class": resource,
        "kind": kind,
        "device_name": device_name,
        "selectable": bool(supported),
        "mapped_groups": [],
    }
    # Preserve alternative definitions, including constraints not rendered by this API.
    definition = {key: raw.get(key) for key in sorted(_ALIAS_FIELDS)}
    definition.update(vendor_id=vendor, product_id=product, resource_class=resource)
    signature = json.dumps(definition, sort_keys=True)
    return row, signature, invalid


def _read_aliases(device_map=None):
    source = {
        "state": "unavailable",
        "source": "nova_api_config",
        "observed_at": None,
        "message": "Nova PCI alias snapshot is unavailable.",
    }
    try:
        descriptor = os.open(ALIAS_SNAPSHOT_PATH, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        with os.fdopen(descriptor, "rb") as snapshot:
            if not stat.S_ISREG(os.fstat(snapshot.fileno()).st_mode):
                return source, []
            content = snapshot.read(_MAX_BYTES + 1)
        if len(content) > _MAX_BYTES:
            return source, []
        body = json.loads(content, object_pairs_hook=_unique_object)
        if (
            not isinstance(body, dict)
            or type(body.get("schema_version")) is not int
            or body["schema_version"] != 1
            or body.get("source") != "nova_api_config"
            or not isinstance(body.get("controllers"), list)
            or not 1 <= len(body["controllers"]) <= _MAX_CONTROLLERS
        ):
            return source, []
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError):
        return source, []

    rows, definitions, controllers, observed, hosts = {}, {}, [], [], set()
    partial, ready = False, 0
    alias_count = 0
    for controller in body["controllers"]:
        if not isinstance(controller, dict) or not _text(controller.get("host")):
            partial = True
            continue
        if controller["host"] in hosts:
            partial = True
        hosts.add(controller["host"])
        aliases = controller.get("aliases")
        try:
            timestamp = _timestamp(controller.get("observed_at"))
        except (TypeError, ValueError):
            timestamp, partial = None, True
        if controller.get("state") != "ready" or not isinstance(aliases, list):
            partial = True
            continue
        if alias_count + len(aliases) > _MAX_ALIASES:
            partial = True
            continue
        alias_count += len(aliases)
        ready += 1
        if timestamp is not None:
            observed.append(timestamp)
        signatures = []
        for raw in aliases:
            try:
                row, signature, invalid = _alias(raw, device_map)
            except (TypeError, ValueError, RecursionError):
                partial = True
                continue
            partial |= invalid
            rows.setdefault(signature, row)
            signatures.append(signature)
            definitions.setdefault(row["name"], set()).add(signature)
        controllers.append(sorted(signatures))
    if controllers and any(value != controllers[0] for value in controllers[1:]):
        partial = True
    if any(len(values) != 1 for values in definitions.values()):
        partial = True
    source["state"] = "partial" if partial and ready else "ready" if ready else "unavailable"
    source["observed_at"] = min(observed).isoformat() if observed else None
    source["message"] = (
        "Nova controller PCI aliases are incomplete, inconsistent or malformed."
        if source["state"] == "partial"
        else None
        if source["state"] == "ready"
        else source["message"]
    )
    for row in rows.values():
        conflict = len(definitions[row["name"]]) != 1
        if conflict:
            row["kind"], row["device_name"] = "unknown", None
        row["selectable"] &= source["state"] == "ready" and not conflict
    return source, sorted(rows.values(), key=lambda row: (row["name"], row["vendor_id"] or "", row["product_id"] or ""))


def _get(conn, endpoint, path, deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ValueError("observation deadline")
    response = conn.session.get(
        endpoint + path,
        headers={
            "OpenStack-API-Version": "placement 1.36",
            "Accept": "application/json",
            "Accept-Encoding": "identity",
        },
        timeout=min(5.0, remaining),
        connect_retries=0,
        status_code_retries=0,
        allow_reauth=False,
        redirect=False,
        raise_exc=False,
        stream=True,
        log=False,
    )
    try:
        if type(response.status_code) is not int or response.status_code != 200:
            raise ValueError("Placement read failed")
        # Avoid decoder/framing reads that can buffer a continuously dripping
        # body indefinitely before yielding an application-visible chunk.
        if response.headers.get("Content-Encoding", "identity").lower() not in ("", "identity"):
            raise ValueError("unsupported encoded Placement response")
        if response.headers.get("Transfer-Encoding"):
            raise ValueError("unsupported framed Placement response")
        length = response.headers.get("Content-Length")
        if length is not None and (not length.isdecimal() or int(length) > _MAX_BYTES):
            raise ValueError("Placement response exceeds observation limit")
        content = bytearray()
        for chunk in response.iter_content(chunk_size=1):
            if time.monotonic() >= deadline:
                raise ValueError("observation deadline")
            if not isinstance(chunk, bytes) or len(content) + len(chunk) > _MAX_BYTES:
                raise ValueError("Placement response exceeds observation limit")
            content.extend(chunk)
        if time.monotonic() >= deadline:
            raise ValueError("observation deadline")
        if length is not None and len(content) != int(length):
            raise ValueError("incomplete Placement response")
        body = json.loads(content, object_pairs_hook=_unique_object)
        if not isinstance(body, dict):
            raise ValueError("malformed Placement response")
        return body
    finally:
        response.close()


def _root(provider, providers):
    seen = set()
    current = provider
    root = provider["root_provider_uuid"]
    while current["parent_provider_uuid"] is not None:
        if current["uuid"] in seen or current["root_provider_uuid"] != root:
            raise ValueError("invalid provider tree")
        seen.add(current["uuid"])
        current = providers[current["parent_provider_uuid"]]
    if current["uuid"] != root or current["root_provider_uuid"] != root:
        raise ValueError("invalid provider root")
    return current


def _amount(value):
    return type(value) is int and 0 <= value <= 2**63 - 1


def _inventory(conn, device_map=None):
    result = {"state": "unavailable", "devices": [], "errors": []}
    errors = set()
    deadline = time.monotonic() + _DEADLINE_SECONDS
    try:
        endpoint = conn.placement.get_endpoint()
        if not isinstance(endpoint, str) or not endpoint:
            raise ValueError("missing endpoint")
        endpoint = endpoint.rstrip("/")
        body = _get(conn, endpoint, "/resource_providers", deadline)
        raw_providers = body.get("resource_providers")
        if not isinstance(raw_providers, list):
            raise ValueError("missing providers")
    except Exception:
        result["errors"] = ["Placement provider directory is unavailable."]
        return result
    if body.get("resource_providers_links"):
        errors.add("Placement provider directory is incomplete.")
    if len(raw_providers) > _MAX_PROVIDERS:
        errors.add("Placement provider directory exceeds the observation limit.")
    providers, duplicates = {}, set()
    for row in raw_providers[:_MAX_PROVIDERS]:
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("uuid"), str)
            or not _ID.fullmatch(row["uuid"])
            or not _text(row.get("name"))
            or not isinstance(row.get("root_provider_uuid"), str)
            or not _ID.fullmatch(row["root_provider_uuid"])
            or "parent_provider_uuid" not in row
            or not (
                row["parent_provider_uuid"] is None
                or isinstance(row["parent_provider_uuid"], str)
                and _ID.fullmatch(row["parent_provider_uuid"])
            )
        ):
            errors.add("Placement contains malformed provider identities.")
            continue
        if row["uuid"] in providers:
            duplicates.add(row["uuid"])
            errors.add("Placement contains duplicate provider identities.")
        providers[row["uuid"]] = row
    for identity in duplicates:
        providers.pop(identity, None)
    successful = 0
    for provider in providers.values():
        if time.monotonic() >= deadline:
            errors.add("Placement PCI observation deadline was reached.")
            break
        try:
            root = _root(provider, providers)
        except (KeyError, ValueError):
            errors.add("Placement contains incomplete or inconsistent provider trees.")
            continue
        path = f"/resource_providers/{provider['uuid']}"
        try:
            inventories = _get(conn, endpoint, path + "/inventories", deadline).get("inventories")
            if not isinstance(inventories, dict):
                raise ValueError("invalid inventories")
        except Exception:
            errors.add("Placement provider inventories are unavailable or malformed.")
            continue
        successful += 1
        # Nova PCI providers use a host_BDF name even when the operator assigns
        # a non-default resource class. The address remains a name-derived hint.
        address = _BDF.fullmatch(provider["name"])
        bdf_provider = bool(address and address[1] == root["name"])
        pci = {
            rc: value
            for rc, value in inventories.items()
            if isinstance(rc, str) and (rc.startswith("CUSTOM_PCI_") or bdf_provider)
        }
        if not pci:
            continue
        try:
            usages = _get(conn, endpoint, path + "/usages", deadline).get("usages")
            if not isinstance(usages, dict):
                raise ValueError("invalid usages")
        except Exception:
            usages = {}
            errors.add("Placement PCI usages are unavailable or malformed; usage is unknown.")
        for resource, inventory in pci.items():
            if (
                not _RESOURCE.fullmatch(resource)
                or not isinstance(inventory, dict)
                or not _amount(inventory.get("total"))
                or not _amount(inventory.get("reserved"))
                or inventory["reserved"] > inventory["total"]
            ):
                errors.add("Placement contains malformed PCI inventory quantities or resource classes.")
                continue
            used = usages.get(resource)
            if not _amount(used):
                used = None
                errors.add("Placement PCI usages are unavailable or malformed; usage is unknown.")
            match = _RC.fullmatch(resource)
            vendor, product = match.groups() if match else (None, None)
            kind, _ = _kind(vendor, product, device_map=device_map)
            result["devices"].append(
                {
                    "host": root["name"],
                    "provider_uuid": provider["uuid"],
                    "provider_name": provider["name"],
                    "pci_address": address[2].lower() if address and address[1] == root["name"] else None,
                    "resource_class": resource,
                    "vendor_id": vendor,
                    "product_id": product,
                    "kind": kind,
                    "total": inventory["total"],
                    "reserved": inventory["reserved"],
                    "used": used,
                    "mapped_groups": [],
                }
            )
    result["errors"] = sorted(errors)
    result["state"] = (
        "partial" if errors and (successful or result["devices"]) else "unavailable" if errors else "ready"
    )
    result["devices"].sort(key=lambda row: (row["host"], row["provider_name"], row["resource_class"]))
    return result


async def discover(conn):
    """Read fresh observations and saved mappings without native or policy writes."""
    from app.database import is_db_available, is_db_configured
    from app.services import gpu_catalog

    policy = await flavor_automation_policy.load_policy()
    if is_db_configured():
        try:
            entries = await gpu_catalog.list_db_devices() if is_db_available() else None
            device_map = (
                await run_sync(gpu_inventory._device_map_with_db_overlay, entries)
                if entries is not None
                else _CATALOG_UNAVAILABLE
            )
        except Exception:
            # A stale local overlay is not authority after another replica edits
            # the catalog. Unknown roles require explicit administrator review.
            device_map = _CATALOG_UNAVAILABLE
    else:
        device_map = await run_sync(gpu_inventory._load_device_map)
    source, aliases = await run_sync(_read_aliases, device_map)
    inventory = await run_sync(_inventory, conn, device_map)
    for row in aliases:
        row["mapped_groups"] = sorted(
            {
                profile["name"]
                for profile in policy["gpu_profiles"]
                if profile["alias_resource_classes"].get(row["name"]) == row["resource_class"]
                and row["resource_class"] is not None
            }
        )
    for row in inventory["devices"]:
        row["mapped_groups"] = sorted(
            {
                profile["name"]
                for profile in policy["gpu_profiles"]
                if row["resource_class"] in profile["resource_requirements"]
            }
        )
    return {"alias_source": source, "aliases": aliases, "inventory": inventory}
