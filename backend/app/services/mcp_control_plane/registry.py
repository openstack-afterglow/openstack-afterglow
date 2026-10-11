"""Canonical, closed consumer-MCP tool registry shared by MCP and Lumen.

Entries are intentionally explicit.  No HTTP route or provider method is reflected
into this registry, so privileged or secret-bearing surfaces cannot appear by
accident.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from hashlib import sha256
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import get_settings
from app.database import get_session_factory
from app.services.mcp_control_plane.authentication import McpPrincipal, lock_principal_grant, resolve_principal_target
from app.services.mcp_control_plane.authority import approved_project_metadata
from app.services.mcp_control_plane.compute import (
    McpComputeError,
    get_project_server,
    list_project_server_interfaces,
    list_project_servers,
    preview_project_server_action,
    preview_project_server_create,
    preview_project_server_delete,
    project_server_overview,
    request_project_server_action,
    request_project_server_create,
    request_project_server_delete,
)
from app.services.mcp_control_plane.connection import McpConsumerConnectionError
from app.services.mcp_control_plane.container import (
    McpContainerError,
    get_project_container,
    list_project_containers,
    preview_project_container_action,
    preview_project_container_delete,
    request_project_container_action,
    request_project_container_delete,
)
from app.services.mcp_control_plane.dashboard import McpDashboardError, project_quotas
from app.services.mcp_control_plane.database import (
    McpDatabaseError,
    get_project_database_instance,
    list_project_database_instances,
    preview_project_database_instance_delete,
    preview_project_database_instance_restart,
    request_project_database_instance_delete,
    request_project_database_instance_restart,
)
from app.services.mcp_control_plane.file_storage import (
    McpFileStorageError,
    get_project_share_quota,
)
from app.services.mcp_control_plane.k3s import (
    McpK3sError,
    get_project_k3s_cluster,
    list_project_k3s_clusters,
)
from app.services.mcp_control_plane.key_manager import (
    McpKeyManagerError,
    list_project_secret_metadata,
)
from app.services.mcp_control_plane.network import (
    McpNetworkError,
    get_project_network,
    get_project_subnet,
    list_project_networks,
    list_project_subnets,
    preview_project_network_delete,
    preview_project_server_network_attach,
    preview_project_subnet_delete,
    request_project_network_delete,
    request_project_server_network_attach,
    request_project_subnet_delete,
)
from app.services.mcp_control_plane.object_storage import (
    McpObjectStorageError,
    get_project_swift_account,
)
from app.services.mcp_control_plane.operations import McpOperationError, get_operation
from app.services.mcp_control_plane.sdk import sdk_deadline
from app.services.mcp_control_plane.storage import (
    McpStorageError,
    get_project_backup,
    get_project_snapshot,
    get_project_volume,
    list_project_backups,
    list_project_server_volumes,
    list_project_snapshots,
    list_project_volumes,
    preview_project_backup_delete,
    preview_project_snapshot_delete,
    preview_project_volume_create,
    preview_project_volume_delete,
    request_project_backup_delete,
    request_project_snapshot_delete,
    request_project_volume_create,
    request_project_volume_delete,
)
from app.services.mcp_control_plane.waygate import (
    McpWaygateError,
    get_project_waygate_server,
    list_project_waygate_servers,
)

REGISTRY_VERSION = "2026-10-11.2"


class McpDomainArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    project_id: str | None = Field(default=None, min_length=1, max_length=64)


class McpDomainOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class McpMutationPreview(BaseModel):
    """Human-reviewable, non-secret mutation plan bound to final revalidation."""

    model_config = ConfigDict(extra="forbid")

    resource_identity: str
    current_state: str | None
    intended_transition: str
    dependent_resources: list[str]
    destructive: bool
    estimated_effect: str | None
    fingerprint: str


@dataclass(frozen=True)
class ConsumerCloudContext:
    principal: McpPrincipal

    @property
    def user_id(self) -> str:
        return self.principal.user_id

    @property
    def project_id(self) -> str:
        return self.principal.project_id

    @asynccontextmanager
    async def openstack_connection(self) -> AsyncIterator[object]:
        """Grant-scoped connection; the registry never exposes a credential string."""
        from app.services.mcp_control_plane.connection import consumer_connection

        async with consumer_connection(self.principal) as conn:
            yield conn


@dataclass(frozen=True)
class RegistryEntry:
    name: str
    description: str
    arguments: type[McpDomainArguments]

    output: type[McpDomainOutput]
    minimum_scope: Literal["mcp:read", "mcp:write"]
    effect: Literal["read", "external_mutation"]
    service_flag: str | None
    timeout_seconds: int
    result_max_bytes: int
    handler: Callable[[ConsumerCloudContext, McpDomainArguments], Awaitable[McpDomainOutput]]
    preview_builder: Callable[[ConsumerCloudContext, McpDomainArguments], Awaitable[McpMutationPreview]] | None = None
    destructive: bool = False

    def __post_init__(self) -> None:
        if self.effect == "external_mutation" and self.preview_builder is None:
            raise ValueError("External MCP mutations require a preview builder")
        if self.effect == "read" and self.preview_builder is not None:
            raise ValueError("Read-only MCP tools cannot define a mutation preview")
        if self.effect == "read" and self.destructive:
            raise ValueError("Read-only MCP tools cannot be destructive")

    def mcp_input_schema(self) -> dict[str, Any]:
        """External MCP mutations add the envelope key without widening the domain model."""
        schema = self.input_schema()
        if self.effect != "external_mutation":
            return schema
        properties = dict(schema.get("properties", {}))
        properties["idempotency_key"] = {
            "type": "string",
            "description": "Opaque client-generated replay key (8-128 ASCII characters).",
            "minLength": 8,
            "maxLength": 128,
            "pattern": "^[A-Za-z0-9._:-]{8,128}$",
        }
        schema["properties"] = properties
        schema["required"] = [*schema.get("required", []), "idempotency_key"]
        return schema

    def enabled(self) -> bool:
        return self.service_flag is None or bool(getattr(get_settings(), self.service_flag, False))

    def allowed_for(self, principal: McpPrincipal) -> bool:
        return self.enabled() and self.minimum_scope in principal.scopes

    def input_schema(self) -> dict[str, Any]:
        return self.arguments.model_json_schema()

    def output_schema(self) -> dict[str, Any]:
        return self.output.model_json_schema()


class CapabilitiesGetArguments(McpDomainArguments):
    pass


class CapabilitiesGetOutput(McpDomainOutput):
    registry_version: str
    enabled_domains: list[str]


class ProjectsListArguments(McpDomainArguments):
    pass


class AllowedProjectOutput(McpDomainOutput):
    id: str
    name: str


class ProjectsListOutput(McpDomainOutput):
    projects: list[AllowedProjectOutput]


async def _projects_list(context: ConsumerCloudContext, _: ProjectsListArguments) -> ProjectsListOutput:
    factory = get_session_factory()
    if factory is None:
        raise ValueError("MCP authority storage is unavailable")
    async with factory() as session, session.begin():
        grant = await lock_principal_grant(session, context.principal)
        return ProjectsListOutput(projects=approved_project_metadata(grant))


_TOOL_DOMAIN_PREFIXES: tuple[tuple[str, str], ...] = (
    ("afterglow_vm_", "compute"),
    ("afterglow_volume_", "storage"),
    ("afterglow_network_", "network"),
    ("afterglow_subnet_", "network"),
    ("afterglow_database_", "database"),
    ("afterglow_container_", "containers"),
    ("afterglow_file_storage_", "file_storage"),
    ("afterglow_k3s_", "k3s"),
    ("afterglow_object_storage_", "object_storage"),
    ("afterglow_key_manager_", "key_manager"),
    ("afterglow_waygate_", "waygate"),
)

_INVENTORY_DOMAIN_PREFIXES: tuple[tuple[str, str], ...] = (
    *_TOOL_DOMAIN_PREFIXES,
    ("afterglow_capabilities_", "platform"),
    ("afterglow_projects_", "platform"),
    ("afterglow_cloud_", "platform"),
    ("afterglow_quota_", "platform"),
    ("afterglow_operation_", "operations"),
)
_INVENTORY_SERVICE_FLAGS = {
    "compute": None,
    "storage": None,
    "network": None,
    "database": "service_trove_enabled",
    "containers": "service_zun_enabled",
    "platform": None,
    "operations": None,
    "file_storage": "service_manila_enabled",
    "k3s": "service_k3s_enabled",
    "object_storage": "service_swift_enabled",
    "key_manager": "service_barbican_enabled",
    "waygate": "service_waygate_enabled",
}


def validate_registry_inventory(entries: tuple[RegistryEntry, ...]) -> None:
    """Fail closed when a cloud tool lacks an explicit safe-domain classification."""

    names: set[str] = set()
    domains: set[str] = set()
    for entry in entries:
        if entry.name in names:
            raise ValueError(f"MCP registry inventory contains duplicate tool {entry.name!r}")
        names.add(entry.name)
        domain = next((domain for prefix, domain in _INVENTORY_DOMAIN_PREFIXES if entry.name.startswith(prefix)), None)
        if domain is None:
            raise ValueError(f"MCP registry inventory leaves tool {entry.name!r} unclassified")
        if entry.service_flag != _INVENTORY_SERVICE_FLAGS[domain]:
            raise ValueError(f"MCP registry inventory assigns tool {entry.name!r} to an invalid service gate")
        domains.add(domain)

    missing_domains = sorted(set(_INVENTORY_SERVICE_FLAGS) - domains)
    if missing_domains:
        raise ValueError(f"MCP registry inventory has no registered tool for domains: {', '.join(missing_domains)}")


def _registered_enabled_domains() -> list[str]:
    return sorted(
        {
            domain
            for entry in _ENTRIES
            if entry.enabled()
            for prefix, domain in _TOOL_DOMAIN_PREFIXES
            if entry.name.startswith(prefix)
        }
    )


async def _capabilities_get(_: ConsumerCloudContext, __: CapabilitiesGetArguments) -> CapabilitiesGetOutput:
    return CapabilitiesGetOutput(
        registry_version=REGISTRY_VERSION,
        enabled_domains=_registered_enabled_domains(),
    )


class QuotaGetArguments(McpDomainArguments):
    pass


class QuotaValueOutput(McpDomainOutput):
    limit: int | float
    in_use: int | float


class ComputeQuotaOutput(McpDomainOutput):
    instances: QuotaValueOutput
    cores: QuotaValueOutput
    ram: QuotaValueOutput


class StorageQuotaOutput(McpDomainOutput):
    volumes: QuotaValueOutput
    gigabytes: QuotaValueOutput


class NetworkQuotaOutput(McpDomainOutput):
    floatingip: QuotaValueOutput


class FileStorageQuotaOutput(McpDomainOutput):
    shares: QuotaValueOutput
    gigabytes: QuotaValueOutput


class QuotaGetOutput(McpDomainOutput):
    compute: ComputeQuotaOutput
    storage: StorageQuotaOutput
    network: NetworkQuotaOutput
    file_storage: FileStorageQuotaOutput | None


async def _quota_get(context: ConsumerCloudContext, _: QuotaGetArguments) -> QuotaGetOutput:
    try:
        async with context.openstack_connection() as conn:
            result = await project_quotas(
                conn,
                project_id=context.project_id,
                manila_enabled=get_settings().service_manila_enabled,
            )
    except (McpDashboardError, McpConsumerConnectionError) as exc:
        raise ValueError("MCP quota data is unavailable") from exc
    return QuotaGetOutput.model_validate(result)


class CloudOverviewGetArguments(McpDomainArguments):
    pass


class CloudOverviewOutput(McpDomainOutput):
    total_instances: int
    active_instances: int
    shutoff_instances: int
    error_instances: int


async def _cloud_overview_get(context: ConsumerCloudContext, _: CloudOverviewGetArguments) -> CloudOverviewOutput:
    try:
        async with context.openstack_connection() as conn:
            overview = await project_server_overview(conn, project_id=context.project_id)
    except (McpComputeError, McpConsumerConnectionError) as exc:
        raise ValueError("MCP cloud overview is unavailable") from exc
    return CloudOverviewOutput(
        total_instances=overview["total"],
        active_instances=overview["active"],
        shutoff_instances=overview["shutoff"],
        error_instances=overview["error"],
    )


class VmListArguments(McpDomainArguments):
    limit: int = Field(default=50, ge=1, le=100)


class VmSummaryOutput(McpDomainOutput):
    id: str
    name: str
    status: str
    created_at: str | None
    updated_at: str | None


class VmCreateArguments(McpDomainArguments):
    name: str = Field(min_length=1, max_length=63, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,62}$")
    image_id: UUID = Field(strict=False, description="Active owned, public, community or accepted shared Glance image.")
    flavor_id: str = Field(min_length=1, max_length=255, pattern=r"^[A-Za-z0-9._-]+$")
    network_id: UUID = Field(strict=False, description="Active project-owned or explicitly shared Neutron network.")
    boot_volume_size_gb: int = Field(
        default=50, ge=1, le=16384, description="Root volume GiB; must satisfy image min_disk."
    )
    delete_boot_volume_on_termination: bool = False
    key_name: str | None = Field(default=None, min_length=1, max_length=255)
    availability_zone: str | None = Field(default=None, min_length=1, max_length=255, pattern=r"^[^:]+$")

    @field_validator("key_name", "availability_zone")
    @classmethod
    def reject_blank_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Creation selections must not be blank")
        return value


class VmCreateOutput(VmSummaryOutput):
    requested_action: Literal["create"]


async def _vm_create_preview(context: ConsumerCloudContext, arguments: VmCreateArguments) -> McpMutationPreview:
    try:
        async with context.openstack_connection() as conn:
            plan = await preview_project_server_create(
                conn,
                project_id=context.project_id,
                user_id=context.user_id,
                **arguments.model_dump(exclude={"project_id", "image_id", "network_id"}),
                image_id=str(arguments.image_id),
                network_id=str(arguments.network_id),
            )
    except (McpComputeError, McpConsumerConnectionError) as exc:
        raise ValueError("MCP VM creation is unavailable") from exc
    fingerprint = sha256(
        json.dumps({"project_id": context.project_id, **plan}, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return McpMutationPreview(
        resource_identity=f"nova-server:new:{context.project_id}:{plan['name']}",
        current_state=None,
        intended_transition="create",
        dependent_resources=[
            f"glance-image:{plan['image_id']}",
            f"nova-flavor:{plan['flavor_id']}",
            f"neutron-network:{plan['network_id']}",
        ],
        destructive=False,
        estimated_effect=f"create one VM with a {plan['boot_volume_size_gb']} GiB boot volume",
        fingerprint=fingerprint,
    )


async def _vm_create(context: ConsumerCloudContext, arguments: VmCreateArguments) -> VmCreateOutput:
    try:
        async with context.openstack_connection() as conn:
            server = await request_project_server_create(
                conn,
                project_id=context.project_id,
                user_id=context.user_id,
                **arguments.model_dump(exclude={"project_id", "image_id", "network_id"}),
                image_id=str(arguments.image_id),
                network_id=str(arguments.network_id),
            )
    except (McpComputeError, McpConsumerConnectionError) as exc:
        raise ValueError("MCP VM creation is unavailable") from exc
    return VmCreateOutput.model_validate(server)


class VmNetworkAttachArguments(McpDomainArguments):
    server_id: UUID = Field(strict=False)
    network_id: UUID = Field(strict=False)


class VmNetworkAttachOutput(McpDomainOutput):
    server_id: str
    network_id: str
    port_id: str
    mac_address: str | None
    requested_action: Literal["attach_network"]


async def _vm_network_attach_preview(
    context: ConsumerCloudContext, arguments: VmNetworkAttachArguments
) -> McpMutationPreview:
    try:
        async with context.openstack_connection() as conn:
            plan = await preview_project_server_network_attach(
                conn,
                project_id=context.project_id,
                server_id=str(arguments.server_id),
                network_id=str(arguments.network_id),
            )
    except (McpNetworkError, McpConsumerConnectionError) as exc:
        raise ValueError("MCP VM network attachment is unavailable") from exc
    fingerprint = sha256(
        json.dumps({"project_id": context.project_id, **plan}, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return McpMutationPreview(
        resource_identity=f"nova-server:{plan['server_id']}",
        current_state=plan["server_status"],
        intended_transition="attach_network",
        dependent_resources=[f"neutron-network:{plan['network_id']}"],
        destructive=False,
        estimated_effect="create one project-owned network interface",
        fingerprint=fingerprint,
    )


async def _vm_network_attach(
    context: ConsumerCloudContext, arguments: VmNetworkAttachArguments
) -> VmNetworkAttachOutput:
    try:
        async with context.openstack_connection() as conn:
            interface = await request_project_server_network_attach(
                conn,
                project_id=context.project_id,
                server_id=str(arguments.server_id),
                network_id=str(arguments.network_id),
            )
    except (McpNetworkError, McpConsumerConnectionError) as exc:
        raise ValueError("MCP VM network attachment is unavailable") from exc
    return VmNetworkAttachOutput.model_validate(interface)


class VmListOutput(McpDomainOutput):
    servers: list[VmSummaryOutput]


async def _vm_list(context: ConsumerCloudContext, arguments: VmListArguments) -> VmListOutput:
    try:
        async with context.openstack_connection() as conn:
            servers = await list_project_servers(conn, project_id=context.project_id, limit=arguments.limit)
    except (McpComputeError, McpConsumerConnectionError) as exc:
        raise ValueError("MCP VM data is unavailable") from exc
    return VmListOutput.model_validate({"servers": servers})


class VmGetArguments(McpDomainArguments):
    server_id: UUID = Field(strict=False)


async def _vm_get(context: ConsumerCloudContext, arguments: VmGetArguments) -> VmSummaryOutput:
    try:
        async with context.openstack_connection() as conn:
            server = await get_project_server(conn, project_id=context.project_id, server_id=str(arguments.server_id))
    except (McpComputeError, McpConsumerConnectionError) as exc:
        raise ValueError("MCP VM data is unavailable") from exc
    return VmSummaryOutput.model_validate(server)


class VmInterfacesListArguments(McpDomainArguments):
    server_id: UUID = Field(strict=False)
    limit: int = Field(default=50, ge=1, le=100)


class VmInterfaceOutput(McpDomainOutput):
    port_id: str
    mac_address: str | None


class VmInterfacesListOutput(McpDomainOutput):
    interfaces: list[VmInterfaceOutput]


async def _vm_interfaces_list(
    context: ConsumerCloudContext, arguments: VmInterfacesListArguments
) -> VmInterfacesListOutput:
    try:
        async with context.openstack_connection() as conn:
            interfaces = await list_project_server_interfaces(
                conn,
                project_id=context.project_id,
                server_id=str(arguments.server_id),
                limit=arguments.limit,
            )
    except (McpComputeError, McpConsumerConnectionError) as exc:
        raise ValueError("MCP VM interface data is unavailable") from exc
    return VmInterfacesListOutput.model_validate({"interfaces": interfaces})


class VmActionArguments(McpDomainArguments):
    server_id: UUID = Field(strict=False)
    action: Literal["start", "stop", "reboot", "shelve", "unshelve"]


class VmActionOutput(VmSummaryOutput):
    requested_action: Literal["start", "stop", "reboot", "shelve", "unshelve"]


async def _vm_action_preview(context: ConsumerCloudContext, arguments: VmActionArguments) -> McpMutationPreview:
    try:
        async with context.openstack_connection() as conn:
            server = await preview_project_server_action(
                conn,
                project_id=context.project_id,
                server_id=str(arguments.server_id),
                action=arguments.action,
            )
    except (McpComputeError, McpConsumerConnectionError) as exc:
        raise ValueError("MCP VM action is unavailable") from exc
    fingerprint_payload = {
        "server_id": server["id"],
        "status": server["status"],
        "action": arguments.action,
    }
    fingerprint = sha256(
        json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return McpMutationPreview(
        resource_identity=f"nova-server:{server['id']}",
        current_state=server["status"],
        intended_transition=arguments.action,
        dependent_resources=[],
        destructive=True,
        estimated_effect="asynchronous Nova lifecycle transition",
        fingerprint=fingerprint,
    )


async def _vm_action(context: ConsumerCloudContext, arguments: VmActionArguments) -> VmActionOutput:
    try:
        async with context.openstack_connection() as conn:
            server = await request_project_server_action(
                conn,
                project_id=context.project_id,
                server_id=str(arguments.server_id),
                action=arguments.action,
            )
    except (McpComputeError, McpConsumerConnectionError) as exc:
        raise ValueError("MCP VM action is unavailable") from exc
    return VmActionOutput.model_validate(server)


class VmDeleteArguments(McpDomainArguments):
    server_id: UUID = Field(strict=False)


class VmDeleteOutput(VmSummaryOutput):
    requested_action: Literal["delete"]


async def _vm_delete_preview(context: ConsumerCloudContext, arguments: VmDeleteArguments) -> McpMutationPreview:
    try:
        async with context.openstack_connection() as conn:
            server = await preview_project_server_delete(
                conn,
                project_id=context.project_id,
                server_id=str(arguments.server_id),
            )
    except (McpComputeError, McpConsumerConnectionError) as exc:
        raise ValueError("MCP VM deletion is unavailable") from exc
    fingerprint = sha256(
        json.dumps(
            {"server_id": server["id"], "status": server["status"], "action": "delete"},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return McpMutationPreview(
        resource_identity=f"nova-server:{server['id']}",
        current_state=server["status"],
        intended_transition="delete",
        dependent_resources=[],
        destructive=True,
        estimated_effect="delete Nova server",
        fingerprint=fingerprint,
    )


async def _vm_delete(context: ConsumerCloudContext, arguments: VmDeleteArguments) -> VmDeleteOutput:
    try:
        async with context.openstack_connection() as conn:
            server = await request_project_server_delete(
                conn,
                project_id=context.project_id,
                server_id=str(arguments.server_id),
            )
    except (McpComputeError, McpConsumerConnectionError) as exc:
        raise ValueError("MCP VM deletion is unavailable") from exc
    return VmDeleteOutput.model_validate(server)


class VolumeListArguments(McpDomainArguments):
    limit: int = Field(default=50, ge=1, le=100)


class VolumeGetArguments(McpDomainArguments):
    volume_id: UUID = Field(strict=False)


class VmVolumesListArguments(McpDomainArguments):
    server_id: UUID = Field(strict=False)
    limit: int = Field(default=50, ge=1, le=100)


class VolumeSummaryOutput(McpDomainOutput):
    id: str
    name: str | None
    status: str
    size_gb: int
    created_at: str | None


class VolumeCreateArguments(McpDomainArguments):
    name: str = Field(min_length=1, max_length=255)
    size_gb: int = Field(ge=1, le=16384)
    availability_zone: str | None = Field(default=None, min_length=1, max_length=255)

    @field_validator("name", "availability_zone")
    @classmethod
    def reject_blank_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Creation selections must not be blank")
        return value


class VolumeCreateOutput(VolumeSummaryOutput):
    requested_action: Literal["create"]


async def _volume_create_preview(context: ConsumerCloudContext, arguments: VolumeCreateArguments) -> McpMutationPreview:
    try:
        async with context.openstack_connection() as conn:
            plan = await preview_project_volume_create(
                conn,
                project_id=context.project_id,
                name=arguments.name,
                size_gb=arguments.size_gb,
                availability_zone=arguments.availability_zone,
            )
    except (McpStorageError, McpConsumerConnectionError) as exc:
        raise ValueError("MCP volume creation is unavailable") from exc
    fingerprint = sha256(
        json.dumps({"project_id": context.project_id, **plan}, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return McpMutationPreview(
        resource_identity=f"cinder-volume:new:{context.project_id}:{plan['name']}",
        current_state=None,
        intended_transition="create",
        dependent_resources=[],
        destructive=False,
        estimated_effect=f"create one {plan['size_gb']} GiB empty volume",
        fingerprint=fingerprint,
    )


async def _volume_create(context: ConsumerCloudContext, arguments: VolumeCreateArguments) -> VolumeCreateOutput:
    try:
        async with context.openstack_connection() as conn:
            volume = await request_project_volume_create(
                conn,
                project_id=context.project_id,
                name=arguments.name,
                size_gb=arguments.size_gb,
                availability_zone=arguments.availability_zone,
            )
    except (McpStorageError, McpConsumerConnectionError) as exc:
        raise ValueError("MCP volume creation is unavailable") from exc
    return VolumeCreateOutput.model_validate(volume)


class VolumeListOutput(McpDomainOutput):
    volumes: list[VolumeSummaryOutput]


async def _volume_list(context: ConsumerCloudContext, arguments: VolumeListArguments) -> VolumeListOutput:
    try:
        async with context.openstack_connection() as conn:
            volumes = await list_project_volumes(conn, project_id=context.project_id, limit=arguments.limit)
    except (McpConsumerConnectionError, McpStorageError) as exc:
        raise ValueError("MCP volume data is unavailable") from exc
    return VolumeListOutput.model_validate({"volumes": volumes})


async def _volume_get(context: ConsumerCloudContext, arguments: VolumeGetArguments) -> VolumeSummaryOutput:
    try:
        async with context.openstack_connection() as conn:
            volume = await get_project_volume(conn, project_id=context.project_id, volume_id=str(arguments.volume_id))
    except (McpConsumerConnectionError, McpStorageError) as exc:
        raise ValueError("MCP volume data is unavailable") from exc
    return VolumeSummaryOutput.model_validate(volume)


class VmVolumesListOutput(McpDomainOutput):
    volumes: list[VolumeSummaryOutput]


async def _vm_volumes_list(context: ConsumerCloudContext, arguments: VmVolumesListArguments) -> VmVolumesListOutput:
    try:
        async with context.openstack_connection() as conn:
            volumes = await list_project_server_volumes(
                conn,
                project_id=context.project_id,
                server_id=str(arguments.server_id),
                limit=arguments.limit,
            )
    except (McpConsumerConnectionError, McpStorageError) as exc:
        raise ValueError("MCP VM volume data is unavailable") from exc
    return VmVolumesListOutput.model_validate({"volumes": volumes})


class VolumeDeleteArguments(McpDomainArguments):
    volume_id: UUID = Field(strict=False)


class VolumeDeleteOutput(VolumeSummaryOutput):
    requested_action: Literal["delete"]


async def _volume_delete_preview(context: ConsumerCloudContext, arguments: VolumeDeleteArguments) -> McpMutationPreview:
    try:
        async with context.openstack_connection() as conn:
            volume = await preview_project_volume_delete(
                conn,
                project_id=context.project_id,
                volume_id=str(arguments.volume_id),
            )
    except (McpConsumerConnectionError, McpStorageError) as exc:
        raise ValueError("MCP volume deletion is unavailable") from exc
    fingerprint = sha256(
        json.dumps(
            {"volume_id": volume["id"], "status": volume["status"], "action": "delete"},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return McpMutationPreview(
        resource_identity=f"cinder-volume:{volume['id']}",
        current_state=str(volume["status"]),
        intended_transition="delete",
        dependent_resources=[],
        destructive=True,
        estimated_effect=f"delete {volume['size_gb']} GiB volume",
        fingerprint=fingerprint,
    )


async def _volume_delete(context: ConsumerCloudContext, arguments: VolumeDeleteArguments) -> VolumeDeleteOutput:
    try:
        async with context.openstack_connection() as conn:
            volume = await request_project_volume_delete(
                conn,
                project_id=context.project_id,
                volume_id=str(arguments.volume_id),
            )
    except (McpConsumerConnectionError, McpStorageError) as exc:
        raise ValueError("MCP volume deletion is unavailable") from exc
    return VolumeDeleteOutput.model_validate(volume)


class SnapshotListArguments(McpDomainArguments):
    limit: int = Field(default=50, ge=1, le=100)


class SnapshotGetArguments(McpDomainArguments):
    snapshot_id: UUID = Field(strict=False)


class SnapshotSummaryOutput(McpDomainOutput):
    id: str
    name: str | None
    status: str
    source_volume_id: str
    size_gb: int
    created_at: str | None


class SnapshotListOutput(McpDomainOutput):
    snapshots: list[SnapshotSummaryOutput]


async def _snapshot_list(context: ConsumerCloudContext, arguments: SnapshotListArguments) -> SnapshotListOutput:
    try:
        async with context.openstack_connection() as conn:
            snapshots = await list_project_snapshots(conn, project_id=context.project_id, limit=arguments.limit)
    except (McpConsumerConnectionError, McpStorageError) as exc:
        raise ValueError("MCP volume snapshot data is unavailable") from exc
    return SnapshotListOutput.model_validate({"snapshots": snapshots})


async def _snapshot_get(context: ConsumerCloudContext, arguments: SnapshotGetArguments) -> SnapshotSummaryOutput:
    try:
        async with context.openstack_connection() as conn:
            snapshot = await get_project_snapshot(
                conn, project_id=context.project_id, snapshot_id=str(arguments.snapshot_id)
            )
    except (McpConsumerConnectionError, McpStorageError) as exc:
        raise ValueError("MCP volume snapshot is unavailable") from exc
    return SnapshotSummaryOutput.model_validate(snapshot)


class SnapshotDeleteArguments(McpDomainArguments):
    snapshot_id: UUID = Field(strict=False)


class SnapshotDeleteOutput(SnapshotSummaryOutput):
    requested_action: Literal["delete"]


async def _snapshot_delete_preview(
    context: ConsumerCloudContext, arguments: SnapshotDeleteArguments
) -> McpMutationPreview:
    try:
        async with context.openstack_connection() as conn:
            snapshot = await preview_project_snapshot_delete(
                conn,
                project_id=context.project_id,
                snapshot_id=str(arguments.snapshot_id),
            )
    except (McpConsumerConnectionError, McpStorageError) as exc:
        raise ValueError("MCP volume snapshot deletion is unavailable") from exc
    fingerprint = sha256(
        json.dumps(
            {"snapshot_id": snapshot["id"], "status": snapshot["status"], "action": "delete"},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return McpMutationPreview(
        resource_identity=f"cinder-snapshot:{snapshot['id']}",
        current_state=str(snapshot["status"]),
        intended_transition="delete",
        dependent_resources=[f"cinder-volume:{snapshot['source_volume_id']}"],
        destructive=True,
        estimated_effect=f"delete {snapshot['size_gb']} GiB volume snapshot",
        fingerprint=fingerprint,
    )


async def _snapshot_delete(context: ConsumerCloudContext, arguments: SnapshotDeleteArguments) -> SnapshotDeleteOutput:
    try:
        async with context.openstack_connection() as conn:
            snapshot = await request_project_snapshot_delete(
                conn,
                project_id=context.project_id,
                snapshot_id=str(arguments.snapshot_id),
            )
    except (McpConsumerConnectionError, McpStorageError) as exc:
        raise ValueError("MCP volume snapshot deletion is unavailable") from exc
    return SnapshotDeleteOutput.model_validate(snapshot)


class BackupListArguments(McpDomainArguments):
    limit: int = Field(default=50, ge=1, le=100)


class BackupGetArguments(McpDomainArguments):
    backup_id: UUID = Field(strict=False)


class BackupSummaryOutput(McpDomainOutput):
    id: str
    name: str | None
    status: str
    source_volume_id: str
    size_gb: int
    created_at: str | None


class BackupListOutput(McpDomainOutput):
    backups: list[BackupSummaryOutput]


async def _backup_list(context: ConsumerCloudContext, arguments: BackupListArguments) -> BackupListOutput:
    try:
        async with context.openstack_connection() as conn:
            backups = await list_project_backups(conn, project_id=context.project_id, limit=arguments.limit)
    except (McpConsumerConnectionError, McpStorageError) as exc:
        raise ValueError("MCP volume backup data is unavailable") from exc
    return BackupListOutput.model_validate({"backups": backups})


async def _backup_get(context: ConsumerCloudContext, arguments: BackupGetArguments) -> BackupSummaryOutput:
    try:
        async with context.openstack_connection() as conn:
            backup = await get_project_backup(conn, project_id=context.project_id, backup_id=str(arguments.backup_id))
    except (McpConsumerConnectionError, McpStorageError) as exc:
        raise ValueError("MCP volume backup is unavailable") from exc
    return BackupSummaryOutput.model_validate(backup)


class BackupDeleteArguments(McpDomainArguments):
    backup_id: UUID = Field(strict=False)


class BackupDeleteOutput(BackupSummaryOutput):
    requested_action: Literal["delete"]


async def _backup_delete_preview(context: ConsumerCloudContext, arguments: BackupDeleteArguments) -> McpMutationPreview:
    try:
        async with context.openstack_connection() as conn:
            backup = await preview_project_backup_delete(
                conn,
                project_id=context.project_id,
                backup_id=str(arguments.backup_id),
            )
    except (McpConsumerConnectionError, McpStorageError) as exc:
        raise ValueError("MCP volume backup deletion is unavailable") from exc
    fingerprint = sha256(
        json.dumps(
            {"backup_id": backup["id"], "status": backup["status"], "action": "delete"},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return McpMutationPreview(
        resource_identity=f"cinder-backup:{backup['id']}",
        current_state=str(backup["status"]),
        intended_transition="delete",
        dependent_resources=[f"cinder-volume:{backup['source_volume_id']}"],
        destructive=True,
        estimated_effect=f"delete {backup['size_gb']} GiB volume backup",
        fingerprint=fingerprint,
    )


async def _backup_delete(context: ConsumerCloudContext, arguments: BackupDeleteArguments) -> BackupDeleteOutput:
    try:
        async with context.openstack_connection() as conn:
            backup = await request_project_backup_delete(
                conn,
                project_id=context.project_id,
                backup_id=str(arguments.backup_id),
            )
    except (McpConsumerConnectionError, McpStorageError) as exc:
        raise ValueError("MCP volume backup deletion is unavailable") from exc
    return BackupDeleteOutput.model_validate(backup)


class DatabaseInstanceListArguments(McpDomainArguments):
    limit: int = Field(default=50, ge=1, le=100)


class DatabaseInstanceGetArguments(McpDomainArguments):
    instance_id: UUID = Field(strict=False)


class DatabaseInstanceSummaryOutput(McpDomainOutput):
    id: str
    name: str
    status: str
    datastore_type: str
    datastore_version: str
    created_at: str | None


class DatabaseInstanceListOutput(McpDomainOutput):
    instances: list[DatabaseInstanceSummaryOutput]


async def _database_instance_list(
    context: ConsumerCloudContext, arguments: DatabaseInstanceListArguments
) -> DatabaseInstanceListOutput:
    try:
        async with context.openstack_connection() as conn:
            instances = await list_project_database_instances(
                conn,
                project_id=context.project_id,
                limit=arguments.limit,
            )
    except (McpConsumerConnectionError, McpDatabaseError) as exc:
        raise ValueError("MCP database instance data is unavailable") from exc
    return DatabaseInstanceListOutput.model_validate({"instances": instances})


async def _database_instance_get(
    context: ConsumerCloudContext, arguments: DatabaseInstanceGetArguments
) -> DatabaseInstanceSummaryOutput:
    try:
        async with context.openstack_connection() as conn:
            instance = await get_project_database_instance(
                conn,
                project_id=context.project_id,
                instance_id=str(arguments.instance_id),
            )
    except (McpConsumerConnectionError, McpDatabaseError) as exc:
        raise ValueError("MCP database instance is unavailable") from exc
    return DatabaseInstanceSummaryOutput.model_validate(instance)


class DatabaseInstanceRestartArguments(McpDomainArguments):
    instance_id: UUID = Field(strict=False)


class DatabaseInstanceRestartOutput(DatabaseInstanceSummaryOutput):
    requested_action: Literal["restart"]


async def _database_instance_restart_preview(
    context: ConsumerCloudContext, arguments: DatabaseInstanceRestartArguments
) -> McpMutationPreview:
    try:
        async with context.openstack_connection() as conn:
            instance = await preview_project_database_instance_restart(
                conn,
                project_id=context.project_id,
                instance_id=str(arguments.instance_id),
            )
    except (McpConsumerConnectionError, McpDatabaseError) as exc:
        raise ValueError("MCP database instance restart is unavailable") from exc
    fingerprint = sha256(
        json.dumps(
            {"instance_id": instance["id"], "status": instance["status"], "action": "restart"},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return McpMutationPreview(
        resource_identity=f"trove-instance:{instance['id']}",
        current_state=instance["status"],
        intended_transition="restart",
        dependent_resources=[],
        destructive=True,
        estimated_effect="asynchronous Trove instance restart",
        fingerprint=fingerprint,
    )


async def _database_instance_restart(
    context: ConsumerCloudContext, arguments: DatabaseInstanceRestartArguments
) -> DatabaseInstanceRestartOutput:
    try:
        async with context.openstack_connection() as conn:
            instance = await request_project_database_instance_restart(
                conn,
                project_id=context.project_id,
                instance_id=str(arguments.instance_id),
            )
    except (McpConsumerConnectionError, McpDatabaseError) as exc:
        raise ValueError("MCP database instance restart is unavailable") from exc
    return DatabaseInstanceRestartOutput.model_validate(instance)


class DatabaseInstanceDeleteArguments(McpDomainArguments):
    instance_id: UUID = Field(strict=False)


class DatabaseInstanceDeleteOutput(DatabaseInstanceSummaryOutput):
    requested_action: Literal["delete"]


async def _database_instance_delete_preview(
    context: ConsumerCloudContext, arguments: DatabaseInstanceDeleteArguments
) -> McpMutationPreview:
    try:
        async with context.openstack_connection() as conn:
            instance = await preview_project_database_instance_delete(
                conn,
                project_id=context.project_id,
                instance_id=str(arguments.instance_id),
            )
    except (McpConsumerConnectionError, McpDatabaseError) as exc:
        raise ValueError("MCP database instance deletion is unavailable") from exc
    fingerprint = sha256(
        json.dumps(
            {"instance_id": instance["id"], "status": instance["status"], "action": "delete"},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return McpMutationPreview(
        resource_identity=f"trove-instance:{instance['id']}",
        current_state=instance["status"],
        intended_transition="delete",
        dependent_resources=[],
        destructive=True,
        estimated_effect="delete Trove instance",
        fingerprint=fingerprint,
    )


async def _database_instance_delete(
    context: ConsumerCloudContext, arguments: DatabaseInstanceDeleteArguments
) -> DatabaseInstanceDeleteOutput:
    try:
        async with context.openstack_connection() as conn:
            instance = await request_project_database_instance_delete(
                conn,
                project_id=context.project_id,
                instance_id=str(arguments.instance_id),
            )
    except (McpConsumerConnectionError, McpDatabaseError) as exc:
        raise ValueError("MCP database instance deletion is unavailable") from exc
    return DatabaseInstanceDeleteOutput.model_validate(instance)


class ContainerListArguments(McpDomainArguments):
    limit: int = Field(default=50, ge=1, le=100)


class ContainerGetArguments(McpDomainArguments):
    container_id: UUID = Field(strict=False)


class ContainerSummaryOutput(McpDomainOutput):
    id: str
    name: str
    status: str
    image: str | None
    created_at: str | None


class ContainerListOutput(McpDomainOutput):
    containers: list[ContainerSummaryOutput]


async def _container_list(context: ConsumerCloudContext, arguments: ContainerListArguments) -> ContainerListOutput:
    try:
        async with context.openstack_connection() as conn:
            containers = await list_project_containers(conn, project_id=context.project_id, limit=arguments.limit)
    except (McpConsumerConnectionError, McpContainerError) as exc:
        raise ValueError("MCP container data is unavailable") from exc
    return ContainerListOutput.model_validate({"containers": containers})


async def _container_get(context: ConsumerCloudContext, arguments: ContainerGetArguments) -> ContainerSummaryOutput:
    try:
        async with context.openstack_connection() as conn:
            container = await get_project_container(
                conn,
                project_id=context.project_id,
                container_id=str(arguments.container_id),
            )
    except (McpConsumerConnectionError, McpContainerError) as exc:
        raise ValueError("MCP container is unavailable") from exc
    return ContainerSummaryOutput.model_validate(container)


class ContainerActionArguments(McpDomainArguments):
    container_id: UUID = Field(strict=False)
    action: Literal["start", "stop"]


class ContainerActionOutput(ContainerSummaryOutput):
    requested_action: Literal["start", "stop"]


async def _container_action_preview(
    context: ConsumerCloudContext, arguments: ContainerActionArguments
) -> McpMutationPreview:
    try:
        async with context.openstack_connection() as conn:
            container = await preview_project_container_action(
                conn,
                project_id=context.project_id,
                container_id=str(arguments.container_id),
                action=arguments.action,
            )
    except (McpConsumerConnectionError, McpContainerError) as exc:
        raise ValueError("MCP container action is unavailable") from exc
    fingerprint = sha256(
        json.dumps(
            {"container_id": container["id"], "status": container["status"], "action": arguments.action},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return McpMutationPreview(
        resource_identity=f"zun-container:{container['id']}",
        current_state=container["status"],
        intended_transition=arguments.action,
        dependent_resources=[],
        destructive=True,
        estimated_effect="asynchronous Zun lifecycle transition",
        fingerprint=fingerprint,
    )


async def _container_action(
    context: ConsumerCloudContext, arguments: ContainerActionArguments
) -> ContainerActionOutput:
    try:
        async with context.openstack_connection() as conn:
            container = await request_project_container_action(
                conn,
                project_id=context.project_id,
                container_id=str(arguments.container_id),
                action=arguments.action,
            )
    except (McpConsumerConnectionError, McpContainerError) as exc:
        raise ValueError("MCP container action is unavailable") from exc
    return ContainerActionOutput.model_validate(container)


class ContainerDeleteArguments(McpDomainArguments):
    container_id: UUID = Field(strict=False)


class ContainerDeleteOutput(ContainerSummaryOutput):
    requested_action: Literal["delete"]


async def _container_delete_preview(
    context: ConsumerCloudContext, arguments: ContainerDeleteArguments
) -> McpMutationPreview:
    try:
        async with context.openstack_connection() as conn:
            container = await preview_project_container_delete(
                conn,
                project_id=context.project_id,
                container_id=str(arguments.container_id),
            )
    except (McpConsumerConnectionError, McpContainerError) as exc:
        raise ValueError("MCP container deletion is unavailable") from exc
    fingerprint = sha256(
        json.dumps(
            {"container_id": container["id"], "status": container["status"], "action": "delete"},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return McpMutationPreview(
        resource_identity=f"zun-container:{container['id']}",
        current_state=container["status"],
        intended_transition="delete",
        dependent_resources=[],
        destructive=True,
        estimated_effect="delete stopped Zun container",
        fingerprint=fingerprint,
    )


async def _container_delete(
    context: ConsumerCloudContext, arguments: ContainerDeleteArguments
) -> ContainerDeleteOutput:
    try:
        async with context.openstack_connection() as conn:
            container = await request_project_container_delete(
                conn,
                project_id=context.project_id,
                container_id=str(arguments.container_id),
            )
    except (McpConsumerConnectionError, McpContainerError) as exc:
        raise ValueError("MCP container deletion is unavailable") from exc
    return ContainerDeleteOutput.model_validate(container)


class NetworkListArguments(McpDomainArguments):
    limit: int = Field(default=50, ge=1, le=100)


class NetworkGetArguments(McpDomainArguments):
    network_id: UUID = Field(strict=False)


class NetworkSummaryOutput(McpDomainOutput):
    id: str
    name: str | None
    status: str | None
    is_shared: bool
    is_external: bool
    visibility: Literal["owned", "shared"]


class NetworkListOutput(McpDomainOutput):
    networks: list[NetworkSummaryOutput]


async def _network_list(context: ConsumerCloudContext, arguments: NetworkListArguments) -> NetworkListOutput:
    try:
        async with context.openstack_connection() as conn:
            networks = await list_project_networks(conn, project_id=context.project_id, limit=arguments.limit)
    except (McpConsumerConnectionError, McpNetworkError) as exc:
        raise ValueError("MCP network data is unavailable") from exc
    return NetworkListOutput.model_validate({"networks": networks})


async def _network_get(context: ConsumerCloudContext, arguments: NetworkGetArguments) -> NetworkSummaryOutput:
    try:
        async with context.openstack_connection() as conn:
            network = await get_project_network(
                conn, project_id=context.project_id, network_id=str(arguments.network_id)
            )
    except (McpConsumerConnectionError, McpNetworkError) as exc:
        raise ValueError("MCP network data is unavailable") from exc
    return NetworkSummaryOutput.model_validate(network)


class NetworkDeleteArguments(McpDomainArguments):
    network_id: UUID = Field(strict=False)


class NetworkDeleteOutput(NetworkSummaryOutput):
    requested_action: Literal["delete"]


async def _network_delete_preview(
    context: ConsumerCloudContext, arguments: NetworkDeleteArguments
) -> McpMutationPreview:
    try:
        async with context.openstack_connection() as conn:
            network = await preview_project_network_delete(
                conn,
                project_id=context.project_id,
                network_id=str(arguments.network_id),
            )
    except (McpConsumerConnectionError, McpNetworkError) as exc:
        raise ValueError("MCP network deletion is unavailable") from exc
    fingerprint = sha256(
        json.dumps(
            {"network_id": network["id"], "status": network["status"], "action": "delete"},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return McpMutationPreview(
        resource_identity=f"neutron-network:{network['id']}",
        current_state=network["status"],
        intended_transition="delete",
        dependent_resources=[],
        destructive=True,
        estimated_effect="delete network if it has no attached resources",
        fingerprint=fingerprint,
    )


async def _network_delete(context: ConsumerCloudContext, arguments: NetworkDeleteArguments) -> NetworkDeleteOutput:
    try:
        async with context.openstack_connection() as conn:
            network = await request_project_network_delete(
                conn,
                project_id=context.project_id,
                network_id=str(arguments.network_id),
            )
    except (McpConsumerConnectionError, McpNetworkError) as exc:
        raise ValueError("MCP network deletion is unavailable") from exc
    return NetworkDeleteOutput.model_validate(network)


class SubnetListArguments(McpDomainArguments):
    limit: int = Field(default=50, ge=1, le=100)


class SubnetGetArguments(McpDomainArguments):
    subnet_id: UUID = Field(strict=False)


class SubnetSummaryOutput(McpDomainOutput):
    id: str
    name: str | None
    network_id: str
    cidr: str
    ip_version: Literal[4, 6]
    gateway_ip: str | None


class SubnetListOutput(McpDomainOutput):
    subnets: list[SubnetSummaryOutput]


async def _subnet_list(context: ConsumerCloudContext, arguments: SubnetListArguments) -> SubnetListOutput:
    try:
        async with context.openstack_connection() as conn:
            subnets = await list_project_subnets(conn, project_id=context.project_id, limit=arguments.limit)
    except (McpConsumerConnectionError, McpNetworkError) as exc:
        raise ValueError("MCP subnet data is unavailable") from exc
    return SubnetListOutput.model_validate({"subnets": subnets})


async def _subnet_get(context: ConsumerCloudContext, arguments: SubnetGetArguments) -> SubnetSummaryOutput:
    try:
        async with context.openstack_connection() as conn:
            subnet = await get_project_subnet(conn, project_id=context.project_id, subnet_id=str(arguments.subnet_id))
    except (McpConsumerConnectionError, McpNetworkError) as exc:
        raise ValueError("MCP subnet is unavailable") from exc
    return SubnetSummaryOutput.model_validate(subnet)


class SubnetDeleteArguments(McpDomainArguments):
    subnet_id: UUID = Field(strict=False)


class SubnetDeleteOutput(SubnetSummaryOutput):
    requested_action: Literal["delete"]


async def _subnet_delete_preview(context: ConsumerCloudContext, arguments: SubnetDeleteArguments) -> McpMutationPreview:
    try:
        async with context.openstack_connection() as conn:
            subnet = await preview_project_subnet_delete(
                conn,
                project_id=context.project_id,
                subnet_id=str(arguments.subnet_id),
            )
    except (McpConsumerConnectionError, McpNetworkError) as exc:
        raise ValueError("MCP subnet deletion is unavailable") from exc
    fingerprint = sha256(
        json.dumps(
            {"subnet_id": subnet["id"], "network_id": subnet["network_id"], "action": "delete"},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return McpMutationPreview(
        resource_identity=f"neutron-subnet:{subnet['id']}",
        current_state=None,
        intended_transition="delete",
        dependent_resources=[f"neutron-network:{subnet['network_id']}"],
        destructive=True,
        estimated_effect=f"delete {subnet['cidr']} subnet",
        fingerprint=fingerprint,
    )


async def _subnet_delete(context: ConsumerCloudContext, arguments: SubnetDeleteArguments) -> SubnetDeleteOutput:
    try:
        async with context.openstack_connection() as conn:
            subnet = await request_project_subnet_delete(
                conn,
                project_id=context.project_id,
                subnet_id=str(arguments.subnet_id),
            )
    except (McpConsumerConnectionError, McpNetworkError) as exc:
        raise ValueError("MCP subnet deletion is unavailable") from exc
    return SubnetDeleteOutput.model_validate(subnet)


class OperationGetArguments(McpDomainArguments):
    invocation_id: UUID = Field(strict=False)


class OperationGetOutput(McpDomainOutput):
    invocation_id: str
    status: Literal["claimed", "dispatch_authorized", "succeeded", "failed", "unknown"]
    tool_name: str
    created_at: str
    resource_ref: str | None
    operation_ref: str | None


async def _operation_get(context: ConsumerCloudContext, arguments: OperationGetArguments) -> OperationGetOutput:
    try:
        operation = await get_operation(context.principal, invocation_id=str(arguments.invocation_id))
    except McpOperationError as exc:
        raise ValueError(str(exc)) from exc
    return OperationGetOutput(
        invocation_id=operation.invocation_id,
        status=operation.status,
        tool_name=operation.tool_name,
        created_at=operation.created_at.isoformat(),
        resource_ref=operation.resource_ref,
        operation_ref=operation.operation_ref,
    )


class FileStorageQuotaGetArguments(McpDomainArguments):
    pass


class FileStorageQuotaGetOutput(McpDomainOutput):
    shares: QuotaValueOutput
    gigabytes: QuotaValueOutput


async def _file_storage_quota_get(
    context: ConsumerCloudContext, _: FileStorageQuotaGetArguments
) -> FileStorageQuotaGetOutput:
    try:
        async with context.openstack_connection() as conn:
            quota = await get_project_share_quota(conn)
    except (McpFileStorageError, McpConsumerConnectionError) as exc:
        raise ValueError("MCP file storage quota data is unavailable") from exc
    return FileStorageQuotaGetOutput.model_validate(quota)


class K3sClusterListArguments(McpDomainArguments):
    limit: int = Field(default=50, ge=1, le=100)


class K3sClusterGetArguments(McpDomainArguments):
    cluster_id: UUID = Field(strict=False)


class K3sClusterSummaryOutput(McpDomainOutput):
    id: str
    name: str
    status: str
    agent_count: int
    k3s_version: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    master_count: int = 1
    stampede_enabled: bool = False
    occm_enabled: bool = False


class K3sClusterListOutput(McpDomainOutput):
    clusters: list[K3sClusterSummaryOutput]


async def _k3s_cluster_list(context: ConsumerCloudContext, arguments: K3sClusterListArguments) -> K3sClusterListOutput:
    try:
        async with context.openstack_connection() as conn:
            clusters = await list_project_k3s_clusters(
                conn,
                project_id=context.project_id,
                limit=arguments.limit,
            )
    except (McpK3sError, McpConsumerConnectionError) as exc:
        raise ValueError("MCP K3s cluster data is unavailable") from exc
    return K3sClusterListOutput.model_validate({"clusters": clusters})


async def _k3s_cluster_get(context: ConsumerCloudContext, arguments: K3sClusterGetArguments) -> K3sClusterSummaryOutput:
    try:
        async with context.openstack_connection() as conn:
            cluster = await get_project_k3s_cluster(
                conn,
                project_id=context.project_id,
                cluster_id=str(arguments.cluster_id),
            )
    except (McpK3sError, McpConsumerConnectionError) as exc:
        raise ValueError("MCP K3s cluster data is unavailable") from exc
    return K3sClusterSummaryOutput.model_validate(cluster)


class ObjectStorageAccountGetArguments(McpDomainArguments):
    pass


class ObjectStorageAccountSummaryOutput(McpDomainOutput):
    container_count: int
    object_count: int
    bytes_used: int


async def _object_storage_account_get(
    context: ConsumerCloudContext, _: ObjectStorageAccountGetArguments
) -> ObjectStorageAccountSummaryOutput:
    try:
        async with context.openstack_connection() as conn:
            account = await get_project_swift_account(conn)
    except (McpObjectStorageError, McpConsumerConnectionError) as exc:
        raise ValueError("MCP object storage account data is unavailable") from exc
    return ObjectStorageAccountSummaryOutput.model_validate(account)


class KeyManagerSecretListArguments(McpDomainArguments):
    limit: int = Field(default=50, ge=1, le=100)


class KeyManagerSecretMetadataOutput(McpDomainOutput):
    id: str
    name: str
    secret_type: str
    status: str
    algorithm: str | None = None
    bit_length: int | None = None
    mode: str | None = None
    created: str | None = None
    expires: str | None = None
    system_managed: bool


class KeyManagerSecretListOutput(McpDomainOutput):
    secrets: list[KeyManagerSecretMetadataOutput]


async def _key_manager_secret_list(
    context: ConsumerCloudContext, arguments: KeyManagerSecretListArguments
) -> KeyManagerSecretListOutput:
    try:
        async with context.openstack_connection() as conn:
            secrets = await list_project_secret_metadata(conn, limit=arguments.limit)
    except (McpKeyManagerError, McpConsumerConnectionError) as exc:
        raise ValueError("MCP key manager metadata is unavailable") from exc
    return KeyManagerSecretListOutput.model_validate({"secrets": secrets})


class WaygateServerListArguments(McpDomainArguments):
    limit: int = Field(default=50, ge=1, le=100)


class WaygateServerGetArguments(McpDomainArguments):
    server_id: UUID = Field(strict=False)


class WaygateServerSummaryOutput(McpDomainOutput):
    id: str
    name: str
    status: str
    created_at: str | None = None
    updated_at: str | None = None


class WaygateServerListOutput(McpDomainOutput):
    servers: list[WaygateServerSummaryOutput]


async def _waygate_server_list(
    context: ConsumerCloudContext, arguments: WaygateServerListArguments
) -> WaygateServerListOutput:
    try:
        async with context.openstack_connection() as conn:
            servers = await list_project_waygate_servers(
                conn,
                context.project_id,
                limit=arguments.limit,
            )
    except (McpWaygateError, McpConsumerConnectionError) as exc:
        raise ValueError("MCP Waygate server data is unavailable") from exc
    return WaygateServerListOutput.model_validate({"servers": servers})


async def _waygate_server_get(
    context: ConsumerCloudContext, arguments: WaygateServerGetArguments
) -> WaygateServerSummaryOutput:
    try:
        async with context.openstack_connection() as conn:
            server = await get_project_waygate_server(
                conn,
                context.project_id,
                str(arguments.server_id),
            )
    except (McpWaygateError, McpConsumerConnectionError) as exc:
        raise ValueError("MCP Waygate server data is unavailable") from exc
    return WaygateServerSummaryOutput.model_validate(server)


_ENTRIES: tuple[RegistryEntry, ...] = (
    RegistryEntry(
        name="afterglow_projects_list",
        description="List the authenticated grant's saved allowed projects (id and name only).",
        arguments=ProjectsListArguments,
        output=ProjectsListOutput,
        minimum_scope="mcp:read",
        effect="read",
        service_flag=None,
        timeout_seconds=10,
        result_max_bytes=64 * 1024,
        handler=_projects_list,
    ),
    RegistryEntry(
        name="afterglow_capabilities_get",
        description="Return the enabled safe consumer-cloud domains and registry version.",
        arguments=CapabilitiesGetArguments,
        output=CapabilitiesGetOutput,
        minimum_scope="mcp:read",
        effect="read",
        service_flag=None,
        timeout_seconds=10,
        result_max_bytes=16 * 1024,
        handler=_capabilities_get,
    ),
    RegistryEntry(
        name="afterglow_cloud_overview_get",
        description="Return fixed current-project Nova instance counts without instance details.",
        arguments=CloudOverviewGetArguments,
        output=CloudOverviewOutput,
        minimum_scope="mcp:read",
        effect="read",
        service_flag=None,
        timeout_seconds=15,
        result_max_bytes=16 * 1024,
        handler=_cloud_overview_get,
    ),
    RegistryEntry(
        name="afterglow_quota_get",
        description="Return fixed current-project compute, storage, network, and enabled file-storage quotas.",
        arguments=QuotaGetArguments,
        output=QuotaGetOutput,
        minimum_scope="mcp:read",
        effect="read",
        service_flag=None,
        timeout_seconds=15,
        result_max_bytes=16 * 1024,
        handler=_quota_get,
    ),
    RegistryEntry(
        name="afterglow_vm_create",
        description="Request creation of one VM with an image-backed boot volume in the selected project; acceptance is not guest readiness.",
        arguments=VmCreateArguments,
        output=VmCreateOutput,
        minimum_scope="mcp:write",
        effect="external_mutation",
        service_flag=None,
        timeout_seconds=30,
        result_max_bytes=16 * 1024,
        handler=_vm_create,
        preview_builder=_vm_create_preview,
    ),
    RegistryEntry(
        name="afterglow_vm_network_attach",
        description="Attach one owned or explicitly shared network to an owned ACTIVE or SHUTOFF VM using a new project-owned port.",
        arguments=VmNetworkAttachArguments,
        output=VmNetworkAttachOutput,
        minimum_scope="mcp:write",
        effect="external_mutation",
        service_flag=None,
        timeout_seconds=30,
        result_max_bytes=16 * 1024,
        handler=_vm_network_attach,
        preview_builder=_vm_network_attach_preview,
    ),
    RegistryEntry(
        name="afterglow_vm_list",
        description="List bounded safe metadata for Nova servers owned by the current project.",
        arguments=VmListArguments,
        output=VmListOutput,
        minimum_scope="mcp:read",
        effect="read",
        service_flag=None,
        timeout_seconds=15,
        result_max_bytes=128 * 1024,
        handler=_vm_list,
    ),
    RegistryEntry(
        name="afterglow_vm_get",
        description="Return safe metadata for one Nova server owned by the current project.",
        arguments=VmGetArguments,
        output=VmSummaryOutput,
        minimum_scope="mcp:read",
        effect="read",
        service_flag=None,
        timeout_seconds=15,
        result_max_bytes=16 * 1024,
        handler=_vm_get,
    ),
    RegistryEntry(
        name="afterglow_vm_interfaces_list",
        description="List bounded safe interfaces only after proving the server and every attached port are owned.",
        arguments=VmInterfacesListArguments,
        output=VmInterfacesListOutput,
        minimum_scope="mcp:read",
        effect="read",
        service_flag=None,
        timeout_seconds=15,
        result_max_bytes=128 * 1024,
        handler=_vm_interfaces_list,
    ),
    RegistryEntry(
        name="afterglow_vm_volumes_list",
        description="List bounded safe attached volumes only after proving the server and every Cinder child are owned.",
        arguments=VmVolumesListArguments,
        output=VmVolumesListOutput,
        minimum_scope="mcp:read",
        effect="read",
        service_flag=None,
        timeout_seconds=15,
        result_max_bytes=128 * 1024,
        handler=_vm_volumes_list,
    ),
    RegistryEntry(
        name="afterglow_vm_action",
        description="Request one bounded lifecycle action for a current-project Nova server.",
        arguments=VmActionArguments,
        output=VmActionOutput,
        minimum_scope="mcp:write",
        effect="external_mutation",
        destructive=True,
        service_flag=None,
        timeout_seconds=30,
        result_max_bytes=64 * 1024,
        handler=_vm_action,
        preview_builder=_vm_action_preview,
    ),
    RegistryEntry(
        name="afterglow_vm_delete",
        description="Delete one current-project Nova server without force or missing-resource suppression.",
        arguments=VmDeleteArguments,
        output=VmDeleteOutput,
        minimum_scope="mcp:write",
        effect="external_mutation",
        destructive=True,
        service_flag=None,
        timeout_seconds=30,
        result_max_bytes=64 * 1024,
        handler=_vm_delete,
        preview_builder=_vm_delete_preview,
    ),
    RegistryEntry(
        name="afterglow_volume_create",
        description="Request creation of one empty 1–16384 GiB Cinder volume in the selected project without waiting or retrying.",
        arguments=VolumeCreateArguments,
        output=VolumeCreateOutput,
        minimum_scope="mcp:write",
        effect="external_mutation",
        service_flag=None,
        timeout_seconds=30,
        result_max_bytes=16 * 1024,
        handler=_volume_create,
        preview_builder=_volume_create_preview,
    ),
    RegistryEntry(
        name="afterglow_volume_list",
        description="List bounded safe metadata for Cinder volumes owned by the current project.",
        arguments=VolumeListArguments,
        output=VolumeListOutput,
        minimum_scope="mcp:read",
        effect="read",
        service_flag=None,
        timeout_seconds=15,
        result_max_bytes=128 * 1024,
        handler=_volume_list,
    ),
    RegistryEntry(
        name="afterglow_volume_get",
        description="Return safe metadata for one Cinder volume owned by the current project.",
        arguments=VolumeGetArguments,
        output=VolumeSummaryOutput,
        minimum_scope="mcp:read",
        effect="read",
        service_flag=None,
        timeout_seconds=15,
        result_max_bytes=16 * 1024,
        handler=_volume_get,
    ),
    RegistryEntry(
        name="afterglow_volume_delete",
        description="Delete one currently available Cinder volume owned by the current project without force.",
        arguments=VolumeDeleteArguments,
        output=VolumeDeleteOutput,
        minimum_scope="mcp:write",
        effect="external_mutation",
        destructive=True,
        service_flag=None,
        timeout_seconds=30,
        result_max_bytes=64 * 1024,
        handler=_volume_delete,
        preview_builder=_volume_delete_preview,
    ),
    RegistryEntry(
        name="afterglow_volume_snapshot_list",
        description="List bounded safe metadata for Cinder snapshots owned by the current project.",
        arguments=SnapshotListArguments,
        output=SnapshotListOutput,
        minimum_scope="mcp:read",
        effect="read",
        service_flag=None,
        timeout_seconds=15,
        result_max_bytes=128 * 1024,
        handler=_snapshot_list,
    ),
    RegistryEntry(
        name="afterglow_volume_snapshot_get",
        description="Return safe metadata for one Cinder snapshot owned by the current project.",
        arguments=SnapshotGetArguments,
        output=SnapshotSummaryOutput,
        minimum_scope="mcp:read",
        effect="read",
        service_flag=None,
        timeout_seconds=15,
        result_max_bytes=16 * 1024,
        handler=_snapshot_get,
    ),
    RegistryEntry(
        name="afterglow_volume_snapshot_delete",
        description="Delete one available Cinder snapshot only after proving its owner and parent volume.",
        arguments=SnapshotDeleteArguments,
        output=SnapshotDeleteOutput,
        minimum_scope="mcp:write",
        effect="external_mutation",
        destructive=True,
        service_flag=None,
        timeout_seconds=30,
        result_max_bytes=64 * 1024,
        handler=_snapshot_delete,
        preview_builder=_snapshot_delete_preview,
    ),
    RegistryEntry(
        name="afterglow_volume_backup_list",
        description="List bounded safe metadata for Cinder backups owned by the current project.",
        arguments=BackupListArguments,
        output=BackupListOutput,
        minimum_scope="mcp:read",
        effect="read",
        service_flag=None,
        timeout_seconds=15,
        result_max_bytes=128 * 1024,
        handler=_backup_list,
    ),
    RegistryEntry(
        name="afterglow_volume_backup_get",
        description="Return safe metadata for one Cinder backup owned by the current project.",
        arguments=BackupGetArguments,
        output=BackupSummaryOutput,
        minimum_scope="mcp:read",
        effect="read",
        service_flag=None,
        timeout_seconds=15,
        result_max_bytes=16 * 1024,
        handler=_backup_get,
    ),
    RegistryEntry(
        name="afterglow_volume_backup_delete",
        description="Delete one available Cinder backup only after proving its owner and parent volume.",
        arguments=BackupDeleteArguments,
        output=BackupDeleteOutput,
        minimum_scope="mcp:write",
        effect="external_mutation",
        destructive=True,
        service_flag=None,
        timeout_seconds=30,
        result_max_bytes=64 * 1024,
        handler=_backup_delete,
        preview_builder=_backup_delete_preview,
    ),
    RegistryEntry(
        name="afterglow_database_instance_list",
        description="List bounded safe metadata for Trove instances owned by the current project.",
        arguments=DatabaseInstanceListArguments,
        output=DatabaseInstanceListOutput,
        minimum_scope="mcp:read",
        effect="read",
        service_flag="service_trove_enabled",
        timeout_seconds=15,
        result_max_bytes=128 * 1024,
        handler=_database_instance_list,
    ),
    RegistryEntry(
        name="afterglow_database_instance_get",
        description="Return safe metadata for one Trove instance owned by the current project.",
        arguments=DatabaseInstanceGetArguments,
        output=DatabaseInstanceSummaryOutput,
        minimum_scope="mcp:read",
        effect="read",
        service_flag="service_trove_enabled",
        timeout_seconds=15,
        result_max_bytes=16 * 1024,
        handler=_database_instance_get,
    ),
    RegistryEntry(
        name="afterglow_database_instance_restart",
        description="Restart one active current-project Trove instance.",
        arguments=DatabaseInstanceRestartArguments,
        output=DatabaseInstanceRestartOutput,
        minimum_scope="mcp:write",
        effect="external_mutation",
        destructive=True,
        service_flag="service_trove_enabled",
        timeout_seconds=30,
        result_max_bytes=64 * 1024,
        handler=_database_instance_restart,
        preview_builder=_database_instance_restart_preview,
    ),
    RegistryEntry(
        name="afterglow_database_instance_delete",
        description="Delete one current-project Trove instance after final state validation.",
        arguments=DatabaseInstanceDeleteArguments,
        output=DatabaseInstanceDeleteOutput,
        minimum_scope="mcp:write",
        effect="external_mutation",
        destructive=True,
        service_flag="service_trove_enabled",
        timeout_seconds=30,
        result_max_bytes=64 * 1024,
        handler=_database_instance_delete,
        preview_builder=_database_instance_delete_preview,
    ),
    RegistryEntry(
        name="afterglow_container_list",
        description="List bounded safe metadata for Zun containers owned by the current project.",
        arguments=ContainerListArguments,
        output=ContainerListOutput,
        minimum_scope="mcp:read",
        effect="read",
        service_flag="service_zun_enabled",
        timeout_seconds=15,
        result_max_bytes=128 * 1024,
        handler=_container_list,
    ),
    RegistryEntry(
        name="afterglow_container_get",
        description="Return safe metadata for one Zun container owned by the current project.",
        arguments=ContainerGetArguments,
        output=ContainerSummaryOutput,
        minimum_scope="mcp:read",
        effect="read",
        service_flag="service_zun_enabled",
        timeout_seconds=15,
        result_max_bytes=16 * 1024,
        handler=_container_get,
    ),
    RegistryEntry(
        name="afterglow_container_action",
        description="Request one bounded start or stop action for a current-project Zun container.",
        arguments=ContainerActionArguments,
        output=ContainerActionOutput,
        minimum_scope="mcp:write",
        effect="external_mutation",
        destructive=True,
        service_flag="service_zun_enabled",
        timeout_seconds=30,
        result_max_bytes=64 * 1024,
        handler=_container_action,
        preview_builder=_container_action_preview,
    ),
    RegistryEntry(
        name="afterglow_container_delete",
        description="Delete one stopped current-project Zun container without force or implicit stop.",
        arguments=ContainerDeleteArguments,
        output=ContainerDeleteOutput,
        minimum_scope="mcp:write",
        effect="external_mutation",
        destructive=True,
        service_flag="service_zun_enabled",
        timeout_seconds=30,
        result_max_bytes=64 * 1024,
        handler=_container_delete,
        preview_builder=_container_delete_preview,
    ),
    RegistryEntry(
        name="afterglow_network_list",
        description="List bounded current-project and explicitly shared Neutron network metadata.",
        arguments=NetworkListArguments,
        output=NetworkListOutput,
        minimum_scope="mcp:read",
        effect="read",
        service_flag=None,
        timeout_seconds=15,
        result_max_bytes=128 * 1024,
        handler=_network_list,
    ),
    RegistryEntry(
        name="afterglow_network_get",
        description="Return safe metadata for one current-project or explicitly shared Neutron network.",
        arguments=NetworkGetArguments,
        output=NetworkSummaryOutput,
        minimum_scope="mcp:read",
        effect="read",
        service_flag=None,
        timeout_seconds=15,
        result_max_bytes=16 * 1024,
        handler=_network_get,
    ),
    RegistryEntry(
        name="afterglow_network_delete",
        description="Delete one owned Neutron network without force or shared-network access.",
        arguments=NetworkDeleteArguments,
        output=NetworkDeleteOutput,
        minimum_scope="mcp:write",
        effect="external_mutation",
        destructive=True,
        service_flag=None,
        timeout_seconds=30,
        result_max_bytes=64 * 1024,
        handler=_network_delete,
        preview_builder=_network_delete_preview,
    ),
    RegistryEntry(
        name="afterglow_subnet_list",
        description="List bounded safe metadata for subnets owned by the current project.",
        arguments=SubnetListArguments,
        output=SubnetListOutput,
        minimum_scope="mcp:read",
        effect="read",
        service_flag=None,
        timeout_seconds=15,
        result_max_bytes=128 * 1024,
        handler=_subnet_list,
    ),
    RegistryEntry(
        name="afterglow_subnet_get",
        description="Return safe metadata for one subnet owned by the current project.",
        arguments=SubnetGetArguments,
        output=SubnetSummaryOutput,
        minimum_scope="mcp:read",
        effect="read",
        service_flag=None,
        timeout_seconds=15,
        result_max_bytes=16 * 1024,
        handler=_subnet_get,
    ),
    RegistryEntry(
        name="afterglow_subnet_delete",
        description="Delete one exact-project subnet only under an owned non-shared parent network.",
        arguments=SubnetDeleteArguments,
        output=SubnetDeleteOutput,
        minimum_scope="mcp:write",
        effect="external_mutation",
        destructive=True,
        service_flag=None,
        timeout_seconds=30,
        result_max_bytes=64 * 1024,
        handler=_subnet_delete,
        preview_builder=_subnet_delete_preview,
    ),
    RegistryEntry(
        name="afterglow_operation_get",
        description="Return bounded status metadata for one invocation created by this MCP grant.",
        arguments=OperationGetArguments,
        output=OperationGetOutput,
        minimum_scope="mcp:read",
        effect="read",
        service_flag=None,
        timeout_seconds=10,
        result_max_bytes=16 * 1024,
        handler=_operation_get,
    ),
    RegistryEntry(
        name="afterglow_file_storage_quota_get",
        description="Return Manila file storage quota limits and usage for the current project.",
        arguments=FileStorageQuotaGetArguments,
        output=FileStorageQuotaGetOutput,
        minimum_scope="mcp:read",
        effect="read",
        service_flag="service_manila_enabled",
        timeout_seconds=10,
        result_max_bytes=16 * 1024,
        handler=_file_storage_quota_get,
    ),
    RegistryEntry(
        name="afterglow_k3s_cluster_list",
        description="List bounded non-sensitive metadata for K3s clusters owned by the current project.",
        arguments=K3sClusterListArguments,
        output=K3sClusterListOutput,
        minimum_scope="mcp:read",
        effect="read",
        service_flag="service_k3s_enabled",
        timeout_seconds=10,
        result_max_bytes=64 * 1024,
        handler=_k3s_cluster_list,
    ),
    RegistryEntry(
        name="afterglow_k3s_cluster_get",
        description="Return bounded non-sensitive metadata for one K3s cluster owned by the current project.",
        arguments=K3sClusterGetArguments,
        output=K3sClusterSummaryOutput,
        minimum_scope="mcp:read",
        effect="read",
        service_flag="service_k3s_enabled",
        timeout_seconds=10,
        result_max_bytes=16 * 1024,
        handler=_k3s_cluster_get,
    ),
    RegistryEntry(
        name="afterglow_object_storage_account_get",
        description="Return project-scoped Swift object storage account aggregate metrics.",
        arguments=ObjectStorageAccountGetArguments,
        output=ObjectStorageAccountSummaryOutput,
        minimum_scope="mcp:read",
        effect="read",
        service_flag="service_swift_enabled",
        timeout_seconds=10,
        result_max_bytes=16 * 1024,
        handler=_object_storage_account_get,
    ),
    RegistryEntry(
        name="afterglow_key_manager_secret_list",
        description="List bounded non-sensitive Barbican secret metadata for the current project.",
        arguments=KeyManagerSecretListArguments,
        output=KeyManagerSecretListOutput,
        minimum_scope="mcp:read",
        effect="read",
        service_flag="service_barbican_enabled",
        timeout_seconds=10,
        result_max_bytes=64 * 1024,
        handler=_key_manager_secret_list,
    ),
    RegistryEntry(
        name="afterglow_waygate_server_list",
        description="List bounded non-sensitive Waygate servers owned by the current project.",
        arguments=WaygateServerListArguments,
        output=WaygateServerListOutput,
        minimum_scope="mcp:read",
        effect="read",
        service_flag="service_waygate_enabled",
        timeout_seconds=10,
        result_max_bytes=64 * 1024,
        handler=_waygate_server_list,
    ),
    RegistryEntry(
        name="afterglow_waygate_server_get",
        description="Return bounded non-sensitive metadata for one current-project Waygate server.",
        arguments=WaygateServerGetArguments,
        output=WaygateServerSummaryOutput,
        minimum_scope="mcp:read",
        effect="read",
        service_flag="service_waygate_enabled",
        timeout_seconds=10,
        result_max_bytes=16 * 1024,
        handler=_waygate_server_get,
    ),
)


def registry_entries() -> tuple[RegistryEntry, ...]:
    validate_registry_inventory(_ENTRIES)
    return _ENTRIES


def enabled_entries(principal: McpPrincipal) -> tuple[RegistryEntry, ...]:
    validate_registry_inventory(_ENTRIES)
    return tuple(entry for entry in _ENTRIES if entry.allowed_for(principal))


def entry_by_name(name: str) -> RegistryEntry | None:
    return next((entry for entry in _ENTRIES if entry.name == name), None)


def output_payload(entry: RegistryEntry, result: McpDomainOutput) -> dict[str, Any]:
    """Serialize only a closed output schema and enforce the entry-specific byte ceiling."""
    payload = result.model_dump(mode="json")
    encoded = json.dumps(payload, allow_nan=False, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
    if len(encoded) > entry.result_max_bytes:
        raise ValueError("MCP tool result exceeds its safe output limit")
    return payload


def parse_entry_arguments(entry: RegistryEntry, arguments: object) -> McpDomainArguments:
    if not entry.enabled():
        raise ValueError("MCP tool is unavailable")
    return entry.arguments.model_validate(arguments)


async def bind_entry_target(
    principal: McpPrincipal, *, entry: RegistryEntry, arguments: McpDomainArguments
) -> tuple[McpPrincipal, McpDomainArguments]:
    if not entry.allowed_for(principal):
        raise ValueError("MCP tool is unavailable")
    resolved = await resolve_principal_target(
        principal, arguments.project_id, write=entry.effect == "external_mutation"
    )
    return resolved, arguments.model_copy(update={"project_id": resolved.project_id})


async def dispatch(
    context: ConsumerCloudContext, *, entry: RegistryEntry, arguments: McpDomainArguments
) -> McpDomainOutput:
    if not entry.allowed_for(context.principal):
        raise ValueError("MCP tool is unavailable")
    principal, arguments = await bind_entry_target(context.principal, entry=entry, arguments=arguments)
    context = replace(context, principal=principal)
    try:
        with sdk_deadline(entry.timeout_seconds):
            async with asyncio.timeout(entry.timeout_seconds):
                result = await entry.handler(context, arguments)
    except TimeoutError as exc:
        raise ValueError("MCP tool timed out") from exc
    return entry.output.model_validate(result)


async def build_mutation_preview(
    context: ConsumerCloudContext, *, entry: RegistryEntry, arguments: McpDomainArguments
) -> McpMutationPreview:
    """Build a non-secret preview; handlers must independently revalidate before dispatch."""
    if entry.effect != "external_mutation" or entry.preview_builder is None:
        raise ValueError("MCP tool is not a mutation")
    if not entry.allowed_for(context.principal):
        raise ValueError("MCP tool is unavailable")
    principal, arguments = await bind_entry_target(context.principal, entry=entry, arguments=arguments)
    context = replace(context, principal=principal)
    try:
        with sdk_deadline(entry.timeout_seconds):
            async with asyncio.timeout(entry.timeout_seconds):
                preview = await entry.preview_builder(context, arguments)
    except TimeoutError as exc:
        raise ValueError("MCP mutation preview timed out") from exc
    return McpMutationPreview.model_validate(preview)


def enabled_service_fingerprint() -> str:
    settings = get_settings()
    payload = {
        "registry_version": REGISTRY_VERSION,
        "entries": [
            {"name": entry.name, "enabled": entry.enabled(), "scope": entry.minimum_scope, "effect": entry.effect}
            for entry in _ENTRIES
        ],
        "services": {
            key: getattr(settings, key)
            for key in (
                "service_trove_enabled",
                "service_zun_enabled",
                "service_manila_enabled",
                "service_k3s_enabled",
                "service_swift_enabled",
                "service_barbican_enabled",
                "service_waygate_enabled",
            )
        },
    }
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
