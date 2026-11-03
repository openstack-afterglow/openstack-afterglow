"""Bounded, provider-proven provisioning discovery for consumer MCP tools."""

from __future__ import annotations

from collections.abc import Mapping
from itertools import islice
from typing import Any
from urllib.parse import quote

from openstack.resource import Body, Resource

from app.services.gpu_inventory import is_gpu_flavor
from app.services.instance_usage import requires_schedule
from app.services.mcp_control_plane.sdk import run_sdk
from app.services.nova import _requires_flavor_access_check, flavor_extra_specs


class McpCatalogError(ValueError):
    """Catalog data is unavailable, malformed, or does not prove visibility."""


_MAX_INTEGER = 2**63 - 1
_MEMBERSHIP_LIMIT = 100


def _field(resource: Any, name: str) -> Any:
    # SDK descriptors supply defaults and coercions, neither of which proves
    # a field was actually present and well-formed in the provider response.
    if isinstance(resource, Resource):
        descriptor = getattr(type(resource), name, None)
        if isinstance(descriptor, Body):
            return resource._body.attributes.get(descriptor.name)
        return None
    if isinstance(resource, Mapping):
        return resource.get(name)
    return getattr(resource, name, None)


def _text(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > 255
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise McpCatalogError(f"Catalog {label} is malformed")
    return value


def _key_name(value: Any) -> str:
    name = _text(value, "key_name")
    if any(char in name for char in "/\\?#%"):
        raise McpCatalogError("Catalog key_name contains reserved path characters")
    return name


def _string(resource: Any, name: str) -> str:
    return _text(_field(resource, name), name)


def _optional_string(resource: Any, name: str) -> str | None:
    value = _field(resource, name)
    return None if value is None else _text(value, name)


def _integer(value: Any, label: str, *, minimum: int = 0, maximum: int | None = _MAX_INTEGER) -> int:
    if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
        raise McpCatalogError(f"Catalog {label} is malformed")
    return value


def _page_args(limit: int, marker: str | None) -> dict[str, Any]:
    query: dict[str, Any] = {
        "paginated": False,
        "limit": _integer(limit, "limit", minimum=1, maximum=100),
    }
    if marker is not None:
        query["marker"] = _text(marker, "marker")
    return query


def _page(resources: Any, *, limit: int, marker: str | None, identity: str):
    seen: set[str] = set()
    for resource in islice(resources, limit):
        resource_id = _string(resource, identity)
        if resource_id == marker or resource_id in seen:
            raise McpCatalogError("Catalog page identity is malformed")
        seen.add(resource_id)
        yield resource_id, resource


def _flavor_visible(conn: Any, flavor: Any, *, project_id: str, flavor_id: str) -> bool:
    public = _field(flavor, "is_public")
    if type(public) is not bool:
        raise McpCatalogError("Catalog flavor visibility is missing")
    if public:
        return True
    if not _requires_flavor_access_check(conn):
        # Nova applies private ACLs to the validated project-scoped nonadmin
        # token. Its admin-only access endpoint is not available to readers.
        return True
    # Nova's successful admin-scoped GET/list does not establish project access.
    access = conn.compute.get_flavor_access(flavor_id)
    if not isinstance(access, list):
        raise McpCatalogError("Catalog flavor access is malformed")
    return any(
        _field(entry, "flavor_id") == flavor_id and _field(entry, "tenant_id") == project_id
        for entry in islice(access, _MEMBERSHIP_LIMIT)
    )


def _safe_flavor(conn: Any, flavor: Any, *, flavor_id: str) -> dict[str, Any]:
    specs = flavor_extra_specs(conn.compute, flavor)
    if (
        not isinstance(specs, Mapping)
        or len(specs) > 256
        or any(
            not isinstance(key, str) or not key or len(key) > 255 or not isinstance(value, str) or len(value) > 4096
            for key, value in specs.items()
        )
    ):
        raise McpCatalogError("Catalog flavor extra specs are malformed")
    vcpus = _integer(_field(flavor, "vcpus"), "vcpus", minimum=1)
    ram = _integer(_field(flavor, "ram"), "ram", minimum=1)
    # Do not pass provider names or an untrusted is_gpu flag to classifiers.
    checked = {"vcpus": vcpus, "ram": ram, "extra_specs": dict(specs)}
    return {
        "id": flavor_id,
        "name": _string(flavor, "name"),
        "vcpus": vcpus,
        "ram_mb": ram,
        "disk_gb": _integer(_field(flavor, "disk"), "disk"),
        "is_public": _field(flavor, "is_public"),
        "is_gpu": is_gpu_flavor(checked),
        "requires_usage_schedule": requires_schedule(checked),
    }


def _list_flavors(conn: Any, *, project_id: str, limit: int, marker: str | None, vcpus: int | None, ram_mb: int | None):
    query = _page_args(limit, marker)
    # SDK3.3 injects is_public=None when omitted; Nova's True filter includes
    # public plus this token project's private ACLs without global enumeration.
    resources = conn.compute.flavors(details=True, get_extra_specs=False, is_public=True, **query)
    result = []
    last = None
    count = 0
    for flavor_id, flavor in _page(resources, limit=limit, marker=marker, identity="id"):
        last, count = flavor_id, count + 1
        if vcpus is not None and _integer(_field(flavor, "vcpus"), "vcpus", minimum=1) != vcpus:
            continue
        if ram_mb is not None and _integer(_field(flavor, "ram"), "ram", minimum=1) != ram_mb:
            continue
        if not _flavor_visible(conn, flavor, project_id=project_id, flavor_id=flavor_id):
            continue
        result.append(_safe_flavor(conn, flavor, flavor_id=flavor_id))
    return {"flavors": result, "next_marker": last if count == limit else None}


def _get_flavor(conn: Any, *, project_id: str, flavor_id: str):
    flavor = conn.compute.get_flavor(flavor_id)
    if _string(flavor, "id") != flavor_id:
        raise McpCatalogError("Catalog flavor identity does not match")
    if not _flavor_visible(conn, flavor, project_id=project_id, flavor_id=flavor_id):
        raise McpCatalogError("Catalog flavor access cannot be proven")
    return _safe_flavor(conn, flavor, flavor_id=flavor_id)


def _image_visible(conn: Any, image: Any, *, project_id: str, image_id: str) -> bool:
    if _field(image, "status") != "active":
        return False
    owner = _string(image, "owner")
    visibility = _field(image, "visibility")
    if visibility not in {"public", "community", "private", "shared"}:
        raise McpCatalogError("Catalog image visibility is malformed")
    if owner == project_id or visibility in {"public", "community"}:
        return True
    if visibility != "shared":
        return False
    # SDK 3.3 get_member seeds the caller's member Body; members() drops all
    # pagination kwargs. Read one exact native JSON record with neither flaw.
    response = conn.image.get(
        f"/images/{quote(image_id, safe='')}/members/{quote(project_id, safe='')}",
        redirect=False,
        allow_reauth=False,
        raise_exc=False,
        connect_retries=0,
        status_code_retries=0,
    )
    if type(response.status_code) is int and response.status_code in {403, 404}:
        return False
    if type(response.status_code) is not int or not 200 <= response.status_code < 300:
        raise McpCatalogError("Glance image membership is unavailable")
    member = response.json()
    return (
        isinstance(member, dict)
        and member.get("member_id") == project_id
        and member.get("image_id") == image_id
        and member.get("status") == "accepted"
    )


def _safe_image(image: Any, *, image_id: str) -> dict[str, Any]:
    size = _field(image, "size")
    return {
        "id": image_id,
        "name": _string(image, "name"),
        "status": _string(image, "status"),
        "visibility": _string(image, "visibility"),
        "min_disk_gb": _integer(_field(image, "min_disk"), "min_disk"),
        "min_ram_mb": _integer(_field(image, "min_ram"), "min_ram"),
        "size_bytes": None if size is None else _integer(size, "size"),
        "disk_format": _optional_string(image, "disk_format"),
        "os_distro": _optional_string(image, "os_distro"),
        "os_version": _optional_string(image, "os_version"),
        "os_admin_user": _optional_string(image, "os_admin_user"),
    }


def _list_images(
    conn: Any,
    *,
    project_id: str,
    limit: int,
    marker: str | None,
    name: str | None,
    visibility: str | None,
):
    query = _page_args(limit, marker)
    if visibility is not None:
        query["visibility"] = visibility
    resources = conn.image.images(**query)
    result = []
    last = None
    count = 0
    for image_id, image in _page(resources, limit=limit, marker=marker, identity="id"):
        last, count = image_id, count + 1
        if not _image_visible(conn, image, project_id=project_id, image_id=image_id):
            continue
        safe = _safe_image(image, image_id=image_id)
        if (name is None or safe["name"] == name) and (visibility is None or safe["visibility"] == visibility):
            result.append(safe)
    return {"images": result, "next_marker": last if count == limit else None}


def _get_image(conn: Any, *, project_id: str, image_id: str):
    image = conn.image.get_image(image_id)
    if _string(image, "id") != image_id:
        raise McpCatalogError("Catalog image identity does not match")
    if not _image_visible(conn, image, project_id=project_id, image_id=image_id):
        raise McpCatalogError("Catalog image visibility cannot be proven")
    return _safe_image(image, image_id=image_id)


def _key_owned(key: Any, user_id: str) -> bool:
    return _string(key, "user_id") == user_id


def _safe_key(key: Any, *, name: str) -> dict[str, Any]:
    return {"name": name, "type": _optional_string(key, "type"), "fingerprint": _optional_string(key, "fingerprint")}


def _list_keys(conn: Any, *, user_id: str, limit: int, marker: str | None):
    if getattr(conn, "_afterglow_user_id", None) != user_id:
        raise McpCatalogError("Catalog keypair caller identity cannot be proven")
    # SDK 3.3.0 caps Keypair at 2.10, but native limit/marker need 2.35.
    # Use the same authenticated proxy with an explicit native microversion,
    # never an unbounded client-side scan of the legacy full-list response.
    query = _page_args(limit, marker)
    del query["paginated"]
    response = conn.compute.get(
        "/os-keypairs",
        microversion="2.35",
        params=query,
        redirect=False,
        allow_reauth=False,
        connect_retries=0,
        status_code_retries=0,
    )
    if type(response.status_code) is not int or not 200 <= response.status_code < 300:
        raise McpCatalogError("Nova keypair list is unavailable")
    payload = response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("keypairs"), list):
        raise McpCatalogError("Catalog keypair page is malformed")
    rows = payload["keypairs"]
    if len(rows) > limit or any(not isinstance(row, dict) or not isinstance(row.get("keypair"), dict) for row in rows):
        raise McpCatalogError("Catalog keypair page is malformed")
    resources = (row["keypair"] for row in rows)
    result = []
    last = None
    count = 0
    for name, _ in _page(resources, limit=limit, marker=marker, identity="name"):
        last, count = name, count + 1
        _key_name(name)
        # Native list views omit user_id. Show independently proves it, without
        # the SDK's historical caller-owner seeding bug.
        key = conn.compute.get_keypair(name)
        if _string(key, "name") != name:
            raise McpCatalogError("Catalog keypair identity does not match")
        if _key_owned(key, user_id):
            result.append(_safe_key(key, name=name))
    return {"keypairs": result, "next_marker": last if count == limit else None}


def _get_key(conn: Any, *, user_id: str, key_name: str):
    if getattr(conn, "_afterglow_user_id", None) != user_id:
        raise McpCatalogError("Catalog keypair caller identity cannot be proven")
    # Passing user_id seeds the returned Resource in installed SDK 3.3.0 even
    # when Nova omits it; never turn the caller's input into ownership proof.
    key = conn.compute.get_keypair(key_name)
    if _string(key, "name") != key_name:
        raise McpCatalogError("Catalog keypair identity does not match")
    if not _key_owned(key, user_id):
        raise McpCatalogError("Catalog keypair ownership cannot be proven")
    return _safe_key(key, name=key_name)


async def _read(function, conn: Any, *, unavailable: str, **kwargs):
    try:
        return await run_sdk(function, conn, **kwargs)
    except McpCatalogError:
        raise
    except Exception as exc:
        raise McpCatalogError(unavailable) from exc


async def list_project_flavors(
    conn: Any,
    *,
    project_id: str,
    limit: int = 50,
    marker: str | None = None,
    vcpus: int | None = None,
    ram_mb: int | None = None,
) -> dict[str, Any]:
    """Scan one bounded raw Nova page; filters never trigger refill requests."""
    _text(project_id, "project_id")
    _page_args(limit, marker)
    for label, value in (("vcpus", vcpus), ("ram_mb", ram_mb)):
        if value is not None:
            _integer(value, label, minimum=1, maximum=None)
    return await _read(
        _list_flavors,
        conn,
        unavailable="Nova flavor list is unavailable",
        project_id=project_id,
        limit=limit,
        marker=marker,
        vcpus=vcpus,
        ram_mb=ram_mb,
    )


async def get_project_flavor(conn: Any, *, project_id: str, flavor_id: str) -> dict[str, Any]:
    """Read only an exact public or explicitly project-authorized flavor."""
    _text(project_id, "project_id")
    _text(flavor_id, "flavor_id")
    return await _read(
        _get_flavor, conn, unavailable="Nova flavor is unavailable", project_id=project_id, flavor_id=flavor_id
    )


async def list_project_images(
    conn: Any,
    *,
    project_id: str,
    limit: int = 50,
    marker: str | None = None,
    name: str | None = None,
    visibility: str | None = None,
) -> dict[str, Any]:
    """Scan active visible images with an optional exact local name match."""
    _text(project_id, "project_id")
    _page_args(limit, marker)
    if name is not None:
        _text(name, "name")
    if visibility is not None and visibility not in ("public", "private", "shared", "community"):
        raise McpCatalogError("Catalog image visibility filter is malformed")
    return await _read(
        _list_images,
        conn,
        unavailable="Glance image list is unavailable",
        project_id=project_id,
        limit=limit,
        marker=marker,
        name=name,
        visibility=visibility,
    )


async def get_project_image(conn: Any, *, project_id: str, image_id: str) -> dict[str, Any]:
    """Read only an exact active owned, public, community, or accepted image."""
    _text(project_id, "project_id")
    _text(image_id, "image_id")
    return await _read(
        _get_image, conn, unavailable="Glance image is unavailable", project_id=project_id, image_id=image_id
    )


async def list_user_keypairs(
    conn: Any,
    *,
    user_id: str,
    limit: int = 50,
    marker: str | None = None,
) -> dict[str, Any]:
    """List caller-owned names and fingerprints without any key material."""
    _text(user_id, "user_id")
    _page_args(limit, marker)
    return await _read(
        _list_keys, conn, unavailable="Nova keypair list is unavailable", user_id=user_id, limit=limit, marker=marker
    )


async def get_user_keypair(conn: Any, *, user_id: str, key_name: str) -> dict[str, Any]:
    """Require Nova's returned owner without seeding an SDK owner attribute."""
    _text(user_id, "user_id")
    _key_name(key_name)
    return await _read(_get_key, conn, unavailable="Nova keypair is unavailable", user_id=user_id, key_name=key_name)
