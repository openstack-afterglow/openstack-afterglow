"""Sealed layer sources and exclusive caller-owned readonly Cinder copies.

No service/admin connection is acquired here. Allocation is deliberately split
from preparation: persist the returned id before any provider wait or action.
"""

from __future__ import annotations

import hashlib
import re

from app.services import cinder, glance

GIB = 1024**3
MAX_DISKS = 24
MAX_LAYER_GB = 64
MAX_TOTAL_GB = 256


def project_id(conn, *, expected: str | None = None) -> str:
    value = conn.session.get_project_id()
    if not isinstance(value, str) or not value:
        raise ValueError("project-scoped connection required")
    marker = getattr(conn, "_afterglow_project_id", None)
    if marker is not None and marker != value:
        raise ValueError("connection project marker conflicts with authenticated scope")
    if expected is not None and value != expected:
        raise ValueError("connection project differs from trusted resource owner")
    return value


def artifact_identity(entry) -> dict:
    if entry.get("is_sealed") is not True or entry.get("digest_state") != "ready":
        raise ValueError("sealed artifact with ready digest required")
    if not isinstance(entry.get("id"), int) or isinstance(entry["id"], bool) or entry["id"] <= 0:
        raise ValueError("artifact id required")
    for key in ("blob_digest", "chain_id"):
        if not isinstance(entry.get(key), str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", entry[key]):
            raise ValueError(f"invalid {key}")
    length = entry.get("size_bytes")
    if not isinstance(length, int) or isinstance(length, bool) or not 0 < length <= MAX_LAYER_GB * GIB:
        raise ValueError("layer length must be positive and at most 64 GiB")
    parent = entry.get("parent_id")
    if parent is not None and (not isinstance(parent, int) or isinstance(parent, bool) or parent <= 0):
        raise ValueError("invalid parent id")
    return {
        "artifact_id": entry["id"],
        **{key: entry.get(key) for key in ("parent_id", "chain_id", "blob_digest", "size_bytes")},
    }


def source_properties(entry, source) -> dict:
    identity = artifact_identity(entry)
    return {
        "afterglow_layer_artifact_id": str(identity["artifact_id"]),
        "afterglow_layer_parent_id": str(identity["parent_id"] or ""),
        "afterglow_layer_chain_id": identity["chain_id"],
        "afterglow_layer_digest": identity["blob_digest"],
        "afterglow_layer_length": str(identity["size_bytes"]),
        "afterglow_layer_upload_id": source["upload_id"],
        "afterglow_layer_store_id": source["store_id"],
    }


def validate_source_image(entry, source, image, *, active=True) -> None:
    identity = artifact_identity(entry)
    if not isinstance(source, dict) or any(source.get(key) != value for key, value in identity.items()):
        raise ValueError("source artifact identity differs")
    if not source.get("owner_project_id") or not source.get("upload_id"):
        raise ValueError("source owner/upload identity missing")
    if not isinstance(source.get("store_id"), str) or not source["store_id"]:
        raise ValueError("explicit source store missing")
    if not isinstance(image, dict) or image.get("id") != source.get("image_id"):
        raise ValueError("source image identity differs")
    if image.get("owner") != source["owner_project_id"]:
        raise ValueError("foreign source owner")
    if image.get("disk_format") != "raw" or image.get("container_format") != "bare":
        raise ValueError("source must be raw/bare")
    if image.get("protected") is not True or image.get("visibility") != "shared":
        raise ValueError("source must be protected and explicitly shared")
    if any(image.get(key) != value for key, value in source_properties(entry, source).items()):
        raise ValueError("source lineage/digest metadata differs")
    if active and (image.get("status") != "active" or image.get("size") != identity["size_bytes"]):
        raise ValueError("source not active or exact length differs")
    if active:
        stores = image.get("stores")
        if not isinstance(stores, str) or source["store_id"] not in stores.split(","):
            raise ValueError("source not present in selected Glance store")


def _validate_source(conn, entry) -> dict:
    caller = project_id(conn)
    source = entry.get("block_source")
    if not isinstance(source, dict) or source.get("state") != "ready":
        raise ValueError("layer has no published block source")
    if caller != source.get("owner_project_id") and caller not in source.get("member_project_ids", []):
        raise ValueError("source is not shared with caller project")
    image = glance.get_source_image(conn, source["image_id"])
    validate_source_image(entry, source, image)
    # Metadata alone is not integrity proof; Glance commonly uses SHA512.
    glance.verify_source_bytes(conn, source["image_id"], entry["blob_digest"], entry["size_bytes"])
    return image


def validate_sources(conn, entries) -> list[dict]:
    if not entries:
        raise ValueError("at least one source required")
    chains = {}
    for entry in entries:
        identity = artifact_identity(entry)
        artifact_id = identity["artifact_id"]
        if artifact_id in chains:
            raise ValueError("duplicate artifact or cyclic lineage")
        parent_id = identity["parent_id"]
        if parent_id is None:
            expected = identity["blob_digest"]
        else:
            if parent_id not in chains:
                raise ValueError("complete parent-first lineage required")
            expected = (
                "sha256:" + hashlib.sha256((chains[parent_id] + " " + identity["blob_digest"]).encode()).hexdigest()
            )
        if identity["chain_id"] != expected:
            raise ValueError("artifact chain digest differs from actual parent lineage")
        chains[artifact_id] = expected
    return [_validate_source(conn, entry) for entry in entries]


def plan_volumes(conn, entries, root_mode, upper_gb) -> dict:
    if not entries:
        raise ValueError("at least one layer required")
    sizes = [(artifact_identity(entry)["size_bytes"] + GIB - 1) // GIB for entry in entries]
    if not isinstance(root_mode, bool):
        raise ValueError("root_mode must be boolean")
    if not isinstance(upper_gb, int) or isinstance(upper_gb, bool) or upper_gb < 0 or (root_mode and upper_gb == 0):
        raise ValueError("positive root upper size required")
    upper = upper_gb if root_mode else 0
    count = len(sizes) + int(root_mode)
    total = sum(sizes) + upper
    if count + 2 > MAX_DISKS or total > MAX_TOTAL_GB:
        raise ValueError("block plan exceeds 24 total disks or 256 GiB aggregate")
    # Unlike overview quota helpers, preserve reservations and fail closed.
    caller = project_id(conn)
    response = conn.block_storage.get(f"/os-quota-sets/{caller}", params={"usage": "true"})
    response.raise_for_status()
    quotas = response.json()["quota_set"]
    response = conn.block_storage.get("/types/default")
    response.raise_for_status()
    volume_type = response.json()["volume_type"]
    if not isinstance(volume_type.get("id"), str) or not volume_type["id"] or not volume_type.get("name"):
        raise ValueError("default volume type identity unavailable")
    if volume_type.get("extra_specs", {}).get("multiattach", "<is> False") not in ("<is> False", "False", "false"):
        raise ValueError("exclusive default volume type required")
    requirements = [("volumes", count), ("gigabytes", total)]
    for key, needed in tuple(requirements):
        typed_key = f"{key}_{volume_type['name']}"
        if typed_key in quotas:
            requirements.append((typed_key, needed))
    for key, needed in requirements:
        quota = quotas.get(key)
        if not isinstance(quota, dict):
            raise ValueError("quota usage unavailable")
        values = [quota.get(field) for field in ("limit", "in_use", "reserved")]
        if any(not isinstance(value, int) or isinstance(value, bool) for value in values):
            raise ValueError("quota usage malformed")
        limit, used, reserved = values
        if limit < -1 or used < 0 or reserved < 0:
            raise ValueError("quota usage malformed")
        if limit != -1 and used + reserved + needed > limit:
            raise ValueError(f"insufficient {key} quota")
    return {
        "layer_sizes_gb": sizes,
        "upper_gb": upper,
        "volume_count": count,
        "total_gb": total,
        "disk_count": count + 2,
        "volume_type_id": volume_type["id"],
        "volume_type_name": volume_type["name"],
    }


def _metadata(conn, metadata) -> dict:
    if (
        not isinstance(metadata, dict)
        or not metadata
        or any(not isinstance(key, str) or not isinstance(value, str) for key, value in metadata.items())
    ):
        raise ValueError("run-owner metadata required")
    if metadata.get("afterglow_project_id") != project_id(conn):
        raise ValueError("run-owner project differs from caller")
    if not re.fullmatch(r"[0-9a-f]{32}", metadata.get("afterglow_run_id", "")):
        raise ValueError("run-owner identity required")
    if not metadata.get("afterglow_consume_id", "").isdigit() or "readonly" in metadata:
        raise ValueError("consume identity required; readonly is provider-controlled")
    return dict(metadata)


def validate_owned_volume(conn, volume, metadata) -> None:
    expected = _metadata(conn, metadata)
    if not isinstance(volume, dict):
        volume = volume.to_dict(original_names=True, computed=False)
    owners = [volume.get(key) for key in ("project_id", "os-vol-tenant-attr:tenant_id") if volume.get(key)]
    if not owners or any(owner != project_id(conn) for owner in owners):
        raise ValueError("foreign volume owner")
    actual = volume.get("metadata")
    if not isinstance(actual, dict) or any(actual.get(key) != value for key, value in expected.items()):
        raise ValueError("volume run-owner metadata differs")
    if volume.get("multiattach") is not False or volume.get("attachments") != []:
        raise ValueError("volume is not exclusive and detached")


def _volume_metadata(conn, entry, metadata) -> dict:
    expected = _metadata(conn, metadata)
    lineage = {
        "afterglow_artifact_id": str(entry["id"]),
        "afterglow_digest": entry["blob_digest"],
        "afterglow_size_bytes": str(entry["size_bytes"]),
        "afterglow_source_image_id": entry["block_source"]["image_id"],
    }
    if any(key in expected and expected[key] != value for key, value in lineage.items()):
        raise ValueError("run metadata differs from artifact/source identity")
    return {**expected, **lineage, **source_properties(entry, entry["block_source"])}


def layer_volume_create_options(conn, entry, name, metadata) -> dict:
    """Validate before recording CREATE intent; the caller sends only this request."""
    _validate_source(conn, entry)
    expected = _volume_metadata(conn, entry, metadata)
    if not expected.get("afterglow_volume_type_id") or not expected.get("afterglow_volume_type_name"):
        raise ValueError("pinned volume type identity required")
    return {
        "name": name,
        "size": (entry["size_bytes"] + GIB - 1) // GIB,
        "image_id": entry["block_source"]["image_id"],
        "metadata": expected,
        "volume_type": expected["afterglow_volume_type_id"],
    }


def _validate_ready(conn, volume, entry, metadata):
    validate_owned_volume(conn, volume, _volume_metadata(conn, entry, metadata))
    if volume.get("status") != "available":
        raise ValueError("layer volume not ready")
    if volume.get("size") != (entry["size_bytes"] + GIB - 1) // GIB:
        raise ValueError("layer volume size differs")
    if volume.get("snapshot_id") or volume.get("source_volid"):
        raise ValueError("layer volume has foreign lineage")
    if volume.get("volume_type") != metadata.get("afterglow_volume_type_name"):
        raise ValueError("volume type differs from pinned plan")
    if volume.get("volume_type_id") and volume["volume_type_id"] != metadata.get("afterglow_volume_type_id"):
        raise ValueError("volume type id differs from pinned plan")
    image_metadata = volume.get("volume_image_metadata")
    if not isinstance(image_metadata, dict) or image_metadata.get("image_id") != entry["block_source"]["image_id"]:
        raise ValueError("volume source image differs")
    if image_metadata.get("disk_format") != "raw" or image_metadata.get("container_format") != "bare":
        raise ValueError("volume source format differs")
    if any(image_metadata.get(key) != value for key, value in source_properties(entry, entry["block_source"]).items()):
        raise ValueError("volume source digest/lineage differs")


def prepare_layer_volume(conn, volume_id, entry, metadata) -> dict:
    volume = cinder.get_volume_details(conn, volume_id)
    if volume.get("id") != volume_id:
        raise ValueError("provider volume id differs")
    validate_owned_volume(conn, volume, _volume_metadata(conn, entry, metadata))
    resource = conn.block_storage.get_volume(volume_id)
    conn.block_storage.wait_for_status(resource, status="available", failures=["error", "error_restoring"], wait=300)
    volume = cinder.get_volume_details(conn, volume_id)
    if volume.get("id") != volume_id:
        raise ValueError("provider volume id differs")
    _validate_ready(conn, volume, entry, metadata)
    volume = cinder.set_volume_readonly(conn, volume_id)
    if volume.get("id") != volume_id:
        raise ValueError("provider volume id differs")
    _validate_ready(conn, volume, entry, metadata)
    if volume.get("metadata", {}).get("readonly") not in (True, "True", "true"):
        raise ValueError("Cinder did not verify readonly")
    return volume
