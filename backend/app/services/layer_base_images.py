"""Glance base-image validation for squashfs layer workflows."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from openstack.exceptions import NotFoundException

from app.services.layer_ubuntu import normalize_ubuntu_base

IMAGE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_NAME_UBUNTU_RE = re.compile(r"ubuntu[^0-9]*(18\.04|20\.04|22\.04|24\.04)", re.IGNORECASE)
_SUPPORTED_RELEASES = {"18.04", "20.04", "22.04", "24.04"}
FROM_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+\-]{0,127}$")
UBUNTU_TAG_RE = re.compile(r"^ubuntu:(\d{2}\.\d{2})$")
FROM_COMPLETION_LIMIT = 20


def _attr(img: Any, name: str, default: Any = None) -> Any:
    if isinstance(img, dict):
        if name in img:
            return img.get(name)
        props = img.get("properties")
        if isinstance(props, dict):
            return props.get(name, default)
        return default
    if hasattr(img, name):
        return getattr(img, name)
    try:
        return img[name]
    except Exception:
        pass
    props = getattr(img, "properties", None)
    if isinstance(props, dict):
        return props.get(name, default)
    to_dict = getattr(img, "to_dict", None)
    if callable(to_dict):
        data = to_dict()
        if isinstance(data, dict):
            if name in data:
                return data.get(name)
            props = data.get("properties")
            if isinstance(props, dict):
                return props.get(name, default)
    return default


def _string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _release_to_base(value: Any) -> str | None:
    raw = _string(value)
    if not raw:
        return None
    lowered = raw.lower().strip()
    if lowered.startswith("ubuntu-"):
        try:
            return normalize_ubuntu_base(lowered)
        except ValueError:
            return None
    match = re.search(r"(18\.04|20\.04|22\.04|24\.04)", lowered)
    if not match:
        return None
    release = match.group(1)
    if release not in _SUPPORTED_RELEASES:
        return None
    return normalize_ubuntu_base(f"ubuntu-{release}")


def ubuntu_base_from_image(img: Any) -> str | None:
    """Infer supported Ubuntu base from Glance metadata, then safe image name."""
    distro = (_string(_attr(img, "os_distro")) or _string(_attr(img, "distro")) or "").lower()
    if distro == "ubuntu":
        for key in ("os_version", "os_version_id", "release", "ubuntu_base"):
            base = _release_to_base(_attr(img, key))
            if base:
                return base

    name = _string(_attr(img, "name")) or ""
    match = _NAME_UBUNTU_RE.search(name)
    if not match:
        return None
    return normalize_ubuntu_base(f"ubuntu-{match.group(1)}")


def snapshot_from_image(img: Any) -> dict:
    """Return persisted base image fingerprint/display metadata."""
    ubuntu_base = ubuntu_base_from_image(img)
    image_id = _string(_attr(img, "id")) or _string(_attr(img, "image_id"))
    return {
        "base_image_id": image_id,
        "base_image_name": _string(_attr(img, "name")),
        "base_image_checksum": _string(_attr(img, "checksum")),
        "base_image_os_hash_algo": _string(_attr(img, "os_hash_algo")),
        "base_image_os_hash_value": _string(_attr(img, "os_hash_value")),
        "base_image_min_disk": _int(_attr(img, "min_disk")),
        "base_image_visibility": _string(_attr(img, "visibility")),
        "base_image_owner": _string(_attr(img, "owner")),
        "ubuntu_base": ubuntu_base,
        "source_metadata": {"base_image_source": "glance"},
    }


def base_image_item(img: Any) -> dict | None:
    """Project-visible active Ubuntu image in the admin base-image response format."""
    snapshot = snapshot_from_image(img)
    ubuntu_base = snapshot.get("ubuntu_base")
    if not ubuntu_base or not snapshot.get("base_image_id"):
        return None
    status = str(_attr(img, "status", "") or "").lower()
    if status != "active":
        return None
    return {
        "id": snapshot["base_image_id"],
        "name": snapshot.get("base_image_name") or "",
        "status": status,
        "ubuntu_base": ubuntu_base,
        "size": _attr(img, "size", 0) or 0,
        "min_disk": snapshot.get("base_image_min_disk") or 0,
        "min_ram": _attr(img, "min_ram", 0) or 0,
        "disk_format": _attr(img, "disk_format", "") or "",
        "visibility": snapshot.get("base_image_visibility") or "private",
        "owner": snapshot.get("base_image_owner") or "",
        "checksum": snapshot.get("base_image_checksum"),
        "os_hash_algo": snapshot.get("base_image_os_hash_algo"),
        "os_hash_value": snapshot.get("base_image_os_hash_value"),
        "created_at": str(_attr(img, "created_at")) if _attr(img, "created_at", None) else None,
    }


def list_base_images(conn: Any) -> list[dict]:
    items = [item for img in conn.image.images() if (item := base_image_item(img)) is not None]
    return sorted(items, key=lambda item: (item["ubuntu_base"], item["name"], item["id"]))


@dataclass(frozen=True)
class FromResolution:
    ref: str
    kind: str | None
    image: dict | None
    error: str | None
    note: str | None
    completions: list[dict]


def _completions(images: list[dict]) -> list[dict]:
    latest: dict[str, dict] = {}
    for image in images:
        name = image["name"]
        ref = name if FROM_REF_RE.fullmatch(name) else image["id"]
        previous = latest.get(ref)
        if previous is None or (str(image.get("created_at") or ""), image["id"]) > (
            str(previous.get("created_at") or ""),
            previous["id"],
        ):
            latest[ref] = image
    return [
        {
            "ref": ref,
            "id": image["id"],
            "name": image["name"],
            "ubuntu_base": image["ubuntu_base"],
            "created_at": image.get("created_at"),
        }
        for ref, image in sorted(latest.items(), key=lambda pair: (pair[1]["ubuntu_base"], pair[1]["name"]))[
            :FROM_COMPLETION_LIMIT
        ]
    ]


def resolve_from_reference(images: list[dict], ref: str) -> FromResolution:
    """Prefer exact name, then ID, then a unique supported Ubuntu release tag."""
    named = [image for image in images if image["name"] == ref]
    if named:
        selected = max(named, key=lambda image: (str(image.get("created_at") or ""), image["id"]))
        note = (
            f"같은 이름의 이미지 {len(named)}개 중 최신(created_at) 이미지를 선택했습니다" if len(named) > 1 else None
        )
        return FromResolution(ref, "glance_name", selected, None, note, [])
    by_id = next((image for image in images if image["id"] == ref), None)
    if by_id:
        return FromResolution(ref, "glance_id", by_id, None, None, [])
    tag = UBUNTU_TAG_RE.fullmatch(ref)
    if tag:
        release = tag.group(1)
        if release not in _SUPPORTED_RELEASES:
            return FromResolution(
                ref,
                "ubuntu_tag",
                None,
                f"지원하는 Ubuntu 버전은 18.04/20.04/22.04/24.04 입니다 (요청: {release})",
                None,
                [],
            )
        candidates = [image for image in images if image["ubuntu_base"] == f"ubuntu-{release}"]
        if len(candidates) == 1:
            return FromResolution(ref, "ubuntu_tag", candidates[0], None, None, [])
        if candidates:
            return FromResolution(
                ref,
                "ubuntu_tag",
                None,
                f"Ubuntu {release} 이미지가 {len(candidates)}개 있습니다 — FROM에 아래 이미지 이름 또는 UUID를 지정하세요",
                None,
                _completions(candidates),
            )
        return FromResolution(ref, "ubuntu_tag", None, f"Glance에 active Ubuntu {release} 이미지가 없습니다", None, [])
    return FromResolution(
        ref,
        None,
        None,
        f"Glance에서 active Ubuntu 이미지 '{ref}'를 찾을 수 없습니다",
        None,
        _completions([image for image in images if image["name"].lower().startswith(ref.lower())]),
    )


def resolve_glance_base_snapshot(conn: Any, ref: str) -> dict:
    resolution = resolve_from_reference(list_base_images(conn), ref)
    if resolution.image is None:
        choices = ": " + ", ".join(item["ref"] for item in resolution.completions[:5]) if resolution.completions else ""
        raise ValueError(f"{resolution.error}{choices}")
    return resolve_base_image_snapshot(conn, resolution.image["id"])


def validate_base_image_id(base_image_id: str) -> str:
    value = str(base_image_id or "").strip()
    if not IMAGE_ID_RE.match(value):
        raise ValueError("base_image_id 형식이 유효하지 않습니다")
    return value


def resolve_base_image_snapshot(conn: Any, base_image_id: str, expected_ubuntu_base: str | None = None) -> dict:
    """Fetch and validate an active supported Ubuntu Glance image."""
    image_id = validate_base_image_id(base_image_id)
    try:
        img = conn.image.get_image(image_id)
    except NotFoundException as exc:
        raise ValueError("base_image_id에 해당하는 Glance 이미지를 찾을 수 없습니다") from exc
    if img is None:
        raise ValueError("base_image_id에 해당하는 Glance 이미지를 찾을 수 없습니다")
    status = (_string(_attr(img, "status")) or "").lower()
    if status != "active":
        raise ValueError(f"Glance 이미지는 active 상태여야 합니다 (현재: {status or 'unknown'})")
    snapshot = snapshot_from_image(img)
    ubuntu_base = snapshot.get("ubuntu_base")
    if not ubuntu_base:
        raise ValueError("지원하는 Ubuntu 18.04/20.04/22.04/24.04 이미지가 아닙니다")
    if expected_ubuntu_base is not None and normalize_ubuntu_base(expected_ubuntu_base) != ubuntu_base:
        raise ValueError(f"선택한 이미지의 Ubuntu base가 요청과 일치하지 않습니다: {ubuntu_base}")
    snapshot["base_image_id"] = image_id
    return snapshot


def legacy_snapshot_for_ubuntu_base(settings: Any, ubuntu_base: str | None) -> dict:
    """Reject legacy rows until the one-time importer records their exact image."""
    base = normalize_ubuntu_base(ubuntu_base)
    raise RuntimeError(
        f"legacy layer artifact for {base} has no base-image snapshot; "
        "run import_runtime_infrastructure_settings.py --legacy-base-image before consuming it"
    )
