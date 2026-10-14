"""Global discovered-resource policy registry and OpenStack validation.

Policies persist stable resource IDs (or canonical availability-zone names where
OpenStack exposes no ID). Display names are snapshots only. Every write and
provisioning resolution validates the saved value in the operation's actual
OpenStack scope; no policy falls back to deployment configuration.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from openstack.exceptions import ResourceNotFound

from app.services import glance, manila, neutron, nova


@dataclass(frozen=True)
class PolicySpec:
    key: str
    resource_kind: str
    title: str
    group: str
    help_text: str
    execution_scope: str = "tenant"  # admin | tenant | service
    dependency: str | None = None
    required_when: str | None = None
    external_only: bool = False
    shared_only: bool = False


_POLICY_SPECS = (
    PolicySpec(
        "openstack.service_project",
        "project",
        "Service project",
        "OpenStack",
        "Project used for Builder and service-owned Manila resources.",
        execution_scope="admin",
    ),
    PolicySpec(
        "nova.default_network",
        "network",
        "Default tenant network",
        "Nova / Cinder",
        "Shared fallback network used only when project auto-networking is disabled.",
        shared_only=True,
    ),
    PolicySpec(
        "nova.default_external_network",
        "network",
        "Default external network",
        "Nova / Cinder",
        "External network required when project default networking is enabled.",
        external_only=True,
        required_when="default_network_enabled",
    ),
    PolicySpec(
        "nova.default_compute_availability_zone",
        "compute_availability_zone",
        "Default compute availability zone",
        "Nova / Cinder",
        "Nova scheduling zone when a request does not provide one.",
        execution_scope="admin",
    ),
    PolicySpec(
        "cinder.default_volume_availability_zone",
        "volume_availability_zone",
        "Default volume availability zone",
        "Nova / Cinder",
        "Cinder placement zone when a request does not provide one.",
        execution_scope="admin",
    ),
    PolicySpec(
        "manila.share_network",
        "share_network",
        "Service share network",
        "Manila",
        "Share network used only by Builder and service-owned NFS/DHSS shares.",
        execution_scope="service",
        dependency="openstack.service_project",
    ),
    PolicySpec(
        "manila.cephfs_share_type",
        "share_type",
        "Public CephFS share type",
        "Manila",
        "Public share type available in service and tenant projects for CephFS.",
        execution_scope="tenant",
    ),
    PolicySpec(
        "manila.nfs_share_type",
        "share_type",
        "Public NFS share type",
        "Manila",
        "Public share type available in service and tenant projects for NFS.",
        execution_scope="tenant",
    ),
    PolicySpec(
        "builder.flavor",
        "flavor",
        "Builder flavor",
        "Builder",
        "Default Builder flavor; individual jobs may override it.",
        execution_scope="service",
        dependency="openstack.service_project",
    ),
    PolicySpec(
        "builder.network",
        "network",
        "Builder network",
        "Builder",
        "Default Builder network; individual jobs may override it.",
        execution_scope="service",
        dependency="openstack.service_project",
    ),
    PolicySpec(
        "builder.floating_network",
        "network",
        "Builder floating network",
        "Builder",
        "Optional external network for Builder utility VMs.",
        execution_scope="service",
        dependency="openstack.service_project",
        external_only=True,
    ),
)
POLICY_SPECS = {spec.key: spec for spec in _POLICY_SPECS}


class ResourcePolicyValidationError(ValueError):
    """Selected resource cannot satisfy its declared global policy."""


def get_spec(key: str) -> PolicySpec:
    try:
        return POLICY_SPECS[key]
    except KeyError as exc:
        raise ResourcePolicyValidationError("unknown resource policy") from exc


def list_specs() -> list[PolicySpec]:
    return list(_POLICY_SPECS)


def _option(resource_id: object, name: object, **extra: Any) -> dict[str, Any]:
    return {"id": str(resource_id), "name": str(name or resource_id), **extra}


def _is_tenant_network(network: object) -> bool:
    return bool(getattr(network, "is_shared", False) or getattr(network, "is_router_external", False))


def _zone_option(zone: object) -> dict[str, Any] | None:
    if isinstance(zone, dict):
        name = zone.get("name") or zone.get("zoneName")
        state = zone.get("state") or zone.get("zoneState") or {}
    else:
        name = getattr(zone, "name", None) or getattr(zone, "zoneName", None)
        state = getattr(zone, "state", {}) or getattr(zone, "zoneState", {}) or {}
    if not name or str(name).lower() == "internal":
        return None
    available = state.get("available", True) if isinstance(state, dict) else True
    if not available:
        return None
    return _option(name, name)


def _share_type_options(conn: object, spec: PolicySpec) -> list[dict[str, Any]]:
    protocol = "CEPHFS" if spec.key == "manila.cephfs_share_type" else "NFS"
    options: list[dict[str, Any]] = []
    for share_type in manila.list_share_types(conn):
        if not bool(share_type.get("is_public", share_type.get("is_default", True))):
            continue
        if protocol not in {item.upper() for item in share_type.get("supported_protocols", [])}:
            continue
        resource_id = share_type.get("id") or share_type.get("name")
        if resource_id:
            options.append(_option(resource_id, share_type.get("name"), protocol=protocol))
    return options


def _discover_sync(conn, spec: PolicySpec) -> list[dict[str, Any]]:
    if spec.resource_kind == "project":
        return [
            _option(project.id, project.name, domain_id=getattr(project, "domain_id", None))
            for project in conn.identity.projects()
        ]
    if spec.resource_kind == "image":
        images = glance.list_images(conn)
        if spec.execution_scope == "tenant":
            images = [image for image in images if image.visibility in {"public", "community"}]
        return [_option(image.id, image.name, status=image.status) for image in images]
    if spec.resource_kind == "flavor":
        flavors = nova.list_flavors(conn)
        if spec.execution_scope == "tenant":
            flavors = [flavor for flavor in flavors if flavor.is_public]
        return [_option(flavor.id, flavor.name, vcpus=flavor.vcpus, ram=flavor.ram) for flavor in flavors]
    if spec.resource_kind == "network":
        options = [
            _option(
                network.id,
                network.name,
                is_external=bool(network.is_external),
                is_shared=bool(getattr(network, "is_shared", False)),
            )
            for network in neutron.list_networks(conn)
            if spec.execution_scope != "tenant" or _is_tenant_network(network)
        ]
        return [
            option
            for option in options
            if (not spec.external_only or option["is_external"]) and (not spec.shared_only or option["is_shared"])
        ]
    if spec.resource_kind == "subnet":
        options = []
        for subnet in conn.network.subnets():
            parent = conn.network.get_network(subnet.network_id)
            if parent is None or (spec.execution_scope == "tenant" and not _is_tenant_network(parent)):
                continue
            options.append(_option(subnet.id, subnet.name, network_id=subnet.network_id, cidr=subnet.cidr))
        return options
    if spec.resource_kind == "share_network":
        return [
            _option(item.get("id"), item.get("name")) for item in manila.list_share_networks(conn) if item.get("id")
        ]
    if spec.resource_kind == "share_type":
        return _share_type_options(conn, spec)
    if spec.resource_kind == "compute_availability_zone":
        return [option for zone in conn.compute.availability_zones() if (option := _zone_option(zone)) is not None]
    if spec.resource_kind == "volume_availability_zone":
        zones = getattr(conn.block_storage, "availability_zones", lambda: [])()
        return [option for zone in zones if (option := _zone_option(zone)) is not None]
    raise AssertionError(f"unsupported resource kind: {spec.resource_kind}")


async def discovery_connection(admin_conn, spec: PolicySpec):
    """Use the same OpenStack scope as the eventual provisioning operation."""
    if spec.execution_scope == "service":
        from app.services.resource_policy_store import get_service_project_connection

        return await get_service_project_connection()
    return admin_conn


async def discover_options(conn, key: str) -> list[dict[str, Any]]:
    spec = get_spec(key)
    execution_conn = await discovery_connection(conn, spec)
    owns_connection = execution_conn is not conn
    try:
        return await asyncio.to_thread(_discover_sync, execution_conn, spec)
    finally:
        if owns_connection:
            with suppress(Exception):
                await asyncio.to_thread(execution_conn.close)


def _validate_catalog_value(conn: object, spec: PolicySpec, resource_id: str) -> dict[str, Any]:
    for option in _discover_sync(conn, spec):
        if option["id"] == resource_id:
            return option
    raise ResourcePolicyValidationError("selected resource is unavailable or violates policy constraints")


def _validate_existing_sync(conn, spec: PolicySpec, resource_id: str) -> dict[str, Any]:
    """Validate one persisted value without re-enumerating resources where possible."""
    if spec.resource_kind == "project":
        project = conn.identity.get_project(resource_id)
        if project is None:
            raise ResourcePolicyValidationError("selected project is unavailable")
        return _option(project.id, project.name, domain_id=getattr(project, "domain_id", None))
    if spec.resource_kind == "image":
        image = conn.image.get_image(resource_id)
        if image is None or (
            spec.execution_scope == "tenant" and getattr(image, "visibility", None) not in {"public", "community"}
        ):
            raise ResourcePolicyValidationError("selected image is unavailable in the execution scope")
        return _option(image.id, image.name, status=getattr(image, "status", None))
    if spec.resource_kind == "flavor":
        flavor = conn.compute.get_flavor(resource_id)
        if flavor is None or (spec.execution_scope == "tenant" and not bool(getattr(flavor, "is_public", False))):
            raise ResourcePolicyValidationError("selected flavor is unavailable in the execution scope")
        return _option(flavor.id, flavor.name)
    if spec.resource_kind == "network":
        try:
            network = conn.network.get_network(resource_id)
        except ResourceNotFound as exc:
            raise ResourcePolicyValidationError("selected network is unavailable in the execution scope") from exc
        if (
            network is None
            or (spec.execution_scope == "tenant" and not _is_tenant_network(network))
            or (spec.external_only and not bool(getattr(network, "is_router_external", False)))
            or (spec.shared_only and not bool(getattr(network, "is_shared", False)))
        ):
            raise ResourcePolicyValidationError("selected network is unavailable in the execution scope")
        return _option(network.id, network.name)
    if spec.resource_kind == "subnet":
        subnet = conn.network.get_subnet(resource_id)
        parent = conn.network.get_network(subnet.network_id) if subnet is not None else None
        if subnet is None or parent is None or (spec.execution_scope == "tenant" and not _is_tenant_network(parent)):
            raise ResourcePolicyValidationError("selected subnet is unavailable in the execution scope")
        return _option(subnet.id, subnet.name)
    if spec.resource_kind == "share_network":
        share_network = manila.get_share_network(conn, resource_id)
        if not share_network or not share_network.get("id"):
            raise ResourcePolicyValidationError("selected share network is unavailable in the execution scope")
        return _option(share_network["id"], share_network.get("name"))
    if spec.resource_kind in {"share_type", "compute_availability_zone", "volume_availability_zone"}:
        return _validate_catalog_value(conn, spec, resource_id)
    raise AssertionError(f"unsupported resource kind: {spec.resource_kind}")


async def validate_existing_selection(conn, key: str, resource_id: str) -> dict[str, Any]:
    return await asyncio.to_thread(_validate_existing_sync, conn, get_spec(key), resource_id)


async def validate_selection(conn, key: str, resource_id: str | None) -> dict[str, Any] | None:
    if resource_id is None or not resource_id.strip():
        return None
    return await validate_existing_selection(conn, key, resource_id.strip())


async def validate_legacy_selection(
    conn, key: str, value: str, *, allow_exact_name: bool = False
) -> dict[str, Any] | None:
    """Resolve importer-only legacy selectors to a stable policy ID.

    Deployment configuration historically stored names for a small set of
    selectors. Runtime writes remain ID-only; this compatibility path accepts
    a name only when exactly one discovered resource has that name.
    """
    if value is None or not value.strip():
        return None
    normalized = value.strip()
    spec = get_spec(key)
    try:
        return await asyncio.to_thread(_validate_existing_sync, conn, spec, normalized)
    except (ResourcePolicyValidationError, ResourceNotFound):
        if not allow_exact_name:
            raise

    matches = await asyncio.to_thread(
        lambda: [option for option in _discover_sync(conn, spec) if option["name"] == normalized]
    )
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ResourcePolicyValidationError("legacy selector name is ambiguous")
    raise ResourcePolicyValidationError("selected resource is unavailable or violates policy constraints")


def dependencies_for(key: str) -> Iterable[str]:
    dependency = get_spec(key).dependency
    return (dependency,) if dependency else ()
