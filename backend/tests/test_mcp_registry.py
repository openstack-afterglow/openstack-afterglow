from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.services.mcp_control_plane.authentication import McpPrincipal
from app.services.mcp_control_plane.ledger import McpInvocationError, canonical_arguments_hash, validate_idempotency_key
from app.services.mcp_control_plane.registry import (
    ConsumerCloudContext,
    McpDomainArguments,
    McpDomainOutput,
    McpMutationPreview,
    RegistryEntry,
    build_mutation_preview,
    dispatch,
    enabled_entries,
    entry_by_name,
    output_payload,
    parse_entry_arguments,
    registry_entries,
    validate_registry_inventory,
)


def _vm_create_arguments():
    return {
        "name": "scheduled-vm",
        "image_id": "33333333-3333-4333-8333-333333333333",
        "flavor_id": "large",
        "network_id": "22222222-2222-4222-8222-222222222222",
        "availability_zone": "nova",
    }


@pytest.mark.parametrize("schedule", [{}, {"expires_at": None}])
def test_vm_create_schedule_requires_explicit_expiry_without_approval_protocol_changes(schedule):
    entry = entry_by_name("afterglow_vm_create")
    with pytest.raises(ValueError, match="usage_schedule.expires_at is required"):
        parse_entry_arguments(entry, {**_vm_create_arguments(), "usage_schedule": schedule})


@pytest.mark.asyncio
async def test_vm_create_schedule_approval_fingerprint_covers_expiry_reason_and_all_deletion_consent(monkeypatch):
    from app.services.mcp_control_plane import registry

    @asynccontextmanager
    async def connection(_context):
        yield object()

    async def preview_create(_conn, **arguments):
        return {key: value for key, value in arguments.items() if key not in {"user_id", "project_id"}}

    monkeypatch.setattr(ConsumerCloudContext, "openstack_connection", connection)
    monkeypatch.setattr(registry, "preview_project_server_create", preview_create)
    entry = entry_by_name("afterglow_vm_create")
    principal = McpPrincipal(
        grant_id="grant-a",
        user_id="user-a",
        project_id="project-a",
        credential_epoch=1,
        scopes=frozenset({"mcp:read", "mcp:write"}),
        source="personal_token",
    )
    context = ConsumerCloudContext(principal=principal)
    expiry = datetime.now(UTC).replace(microsecond=0) + timedelta(days=7)
    schedule = {"expires_at": expiry.isoformat(), "reason": "study"}
    raw = {**_vm_create_arguments(), "usage_schedule": schedule}
    parsed = parse_entry_arguments(entry, raw)
    first = await build_mutation_preview(context, entry=entry, arguments=parsed)
    confirmed = parse_entry_arguments(entry, parsed.model_dump(mode="json"))
    second = await build_mutation_preview(context, entry=entry, arguments=confirmed)
    assert first == second
    assert confirmed.usage_schedule.expires_at == expiry
    assert "shelve and offload" in first.estimated_effect and "retain attached volumes" in first.estimated_effect
    assert parsed.model_dump(mode="json")["usage_schedule"]["expires_at"] in first.estimated_effect
    assert "study" in first.estimated_effect
    assert not first.destructive
    fingerprints = {first.fingerprint}
    variants = [
        {"usage_schedule": {**schedule, "expires_at": (expiry + timedelta(days=1)).isoformat()}},
        {"usage_schedule": {**schedule, "reason": "another study"}},
        {"usage_schedule": {**schedule, "expiry_action": "delete"}},
        {"usage_schedule": {**schedule, "expiry_action": "delete", "delete_volumes": True}},
        {"delete_boot_volume_on_termination": True},
    ]
    for change in variants:
        preview = await build_mutation_preview(
            context, entry=entry, arguments=parse_entry_arguments(entry, {**raw, **change})
        )
        assert preview.fingerprint not in fingerprints
        fingerprints.add(preview.fingerprint)
        if change.get("usage_schedule", {}).get("expiry_action") == "delete":
            assert preview.destructive and "stop then delete the VM" in preview.estimated_effect
            if change["usage_schedule"].get("delete_volumes"):
                assert "delete all attached volumes" in preview.estimated_effect
            else:
                assert "retain attached volumes" in preview.estimated_effect


@pytest.mark.asyncio
async def test_vm_create_dispatch_forwards_public_serialized_schedule_unchanged(monkeypatch):
    from app.services.mcp_control_plane import registry

    @asynccontextmanager
    async def connection(_context):
        yield object()

    received = []

    async def create(_conn, **arguments):
        received.append(arguments)
        return {
            "id": "server-new",
            "name": arguments["name"],
            "status": "BUILD",
            "created_at": None,
            "updated_at": None,
            "requested_action": "create",
        }

    monkeypatch.setattr(ConsumerCloudContext, "openstack_connection", connection)
    monkeypatch.setattr(registry, "request_project_server_create", create)
    entry = entry_by_name("afterglow_vm_create")
    parsed = parse_entry_arguments(
        entry,
        {
            **_vm_create_arguments(),
            "usage_schedule": {
                "expires_at": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
                "expiry_action": "delete",
                "delete_volumes": True,
                "reason": "study",
            },
        },
    )
    principal = McpPrincipal(
        grant_id="grant-a",
        user_id="user-a",
        project_id="project-a",
        credential_epoch=1,
        scopes=frozenset({"mcp:read", "mcp:write"}),
        source="personal_token",
    )
    await dispatch(ConsumerCloudContext(principal=principal), entry=entry, arguments=parsed)
    assert len(received) == 1
    assert received[0]["usage_schedule"] == parsed.model_dump(mode="json")["usage_schedule"]
    assert isinstance(received[0]["usage_schedule"], dict)


@pytest.fixture(autouse=True)
def isolated_authority(monkeypatch):
    """Isolate storage in registry units; runtime scope is tested behaviorally."""

    async def resolve(principal, project_id=None, *, write=False):
        return replace(
            principal, project_id=project_id or principal.project_id, owner_project_id=principal.anchor_project_id
        )

    monkeypatch.setattr("app.services.mcp_control_plane.registry.resolve_principal_target", resolve)


class _MutationArguments(McpDomainArguments):
    resource_id: str


class _MutationOutput(McpDomainOutput):
    status: str


async def _mutation_handler(_: ConsumerCloudContext, __: _MutationArguments) -> _MutationOutput:
    return _MutationOutput(status="accepted")


async def _mutation_preview(_: ConsumerCloudContext, arguments: _MutationArguments) -> McpMutationPreview:
    return McpMutationPreview(
        resource_identity=arguments.resource_id,
        current_state="ACTIVE",
        intended_transition="stop",
        dependent_resources=[],
        destructive=False,
        estimated_effect=None,
        fingerprint="test-fingerprint",
    )


def _mutation_entry() -> RegistryEntry:
    return RegistryEntry(
        name="afterglow_test_mutation",
        description="test-only closed mutation entry",
        arguments=_MutationArguments,
        output=_MutationOutput,
        minimum_scope="mcp:write",
        effect="external_mutation",
        service_flag=None,
        timeout_seconds=10,
        result_max_bytes=64 * 1024,
        handler=_mutation_handler,
        preview_builder=_mutation_preview,
    )


def test_registry_inventory_is_complete_and_fail_closed():
    entries = registry_entries()
    database_entry = entry_by_name("afterglow_database_instance_list")

    assert database_entry is not None
    assert "afterglow_subnet_list" in {entry.name for entry in entries}
    with pytest.raises(ValueError, match="unclassified"):
        validate_registry_inventory((_mutation_entry(),))
    with pytest.raises(ValueError, match="invalid service gate"):
        validate_registry_inventory((replace(database_entry, service_flag=None),))
    with pytest.raises(ValueError, match="duplicate tool"):
        validate_registry_inventory((database_entry, database_entry))
    without_operations = tuple(entry for entry in entries if entry.name != "afterglow_operation_get")
    with pytest.raises(ValueError, match="no registered tool for domains: operations"):
        validate_registry_inventory(without_operations)


def test_registry_exposes_only_explicit_safe_entries(monkeypatch):
    settings = SimpleNamespace(
        service_trove_enabled=False,
        service_zun_enabled=False,
        service_manila_enabled=False,
        service_k3s_enabled=False,
        service_swift_enabled=False,
        service_barbican_enabled=False,
        service_waygate_enabled=False,
    )
    monkeypatch.setattr("app.services.mcp_control_plane.registry.get_settings", lambda: settings)
    principal = McpPrincipal(
        grant_id="grant-a",
        user_id="user-a",
        project_id="project-a",
        credential_epoch=1,
        scopes=frozenset({"mcp:read"}),
        source="personal_token",
    )

    entries = enabled_entries(principal)

    assert [entry.name for entry in entries] == [
        "afterglow_projects_list",
        "afterglow_capabilities_get",
        "afterglow_cloud_overview_get",
        "afterglow_quota_get",
        "afterglow_vm_list",
        "afterglow_vm_get",
        "afterglow_vm_interfaces_list",
        "afterglow_vm_volumes_list",
        "afterglow_volume_list",
        "afterglow_volume_get",
        "afterglow_volume_snapshot_list",
        "afterglow_volume_snapshot_get",
        "afterglow_volume_backup_list",
        "afterglow_volume_backup_get",
        "afterglow_network_list",
        "afterglow_network_get",
        "afterglow_subnet_list",
        "afterglow_subnet_get",
        "afterglow_operation_get",
    ]
    cloud_overview = entry_by_name("afterglow_cloud_overview_get")
    assert cloud_overview is not None
    assert set(cloud_overview.input_schema()["properties"]) == {"project_id"}
    assert set(cloud_overview.output_schema()["properties"]) == {
        "total_instances",
        "active_instances",
        "shutoff_instances",
        "error_instances",
    }
    vm_list = entry_by_name("afterglow_vm_list")
    assert vm_list is not None
    assert set(vm_list.input_schema()["properties"]) == ({"project_id"} | {"limit"})
    assert set(vm_list.output_schema()["$defs"]["VmSummaryOutput"]["properties"]) == {
        "id",
        "name",
        "status",
        "created_at",
        "updated_at",
    }
    vm_get = entry_by_name("afterglow_vm_get")
    assert vm_get is not None
    assert set(vm_get.input_schema()["properties"]) == ({"project_id"} | {"server_id"})
    assert set(vm_get.output_schema()["properties"]) == {
        "id",
        "name",
        "status",
        "created_at",
        "updated_at",
    }
    vm_interfaces_list = entry_by_name("afterglow_vm_interfaces_list")
    assert vm_interfaces_list is not None
    assert set(vm_interfaces_list.input_schema()["properties"]) == ({"project_id"} | {"server_id", "limit"})
    assert set(vm_interfaces_list.output_schema()["$defs"]["VmInterfaceOutput"]["properties"]) == {
        "port_id",
        "mac_address",
    }
    vm_volumes_list = entry_by_name("afterglow_vm_volumes_list")
    assert vm_volumes_list is not None
    assert set(vm_volumes_list.input_schema()["properties"]) == ({"project_id"} | {"server_id", "limit"})
    assert set(vm_volumes_list.output_schema()["$defs"]["VolumeSummaryOutput"]["properties"]) == {
        "id",
        "name",
        "status",
        "size_gb",
        "created_at",
    }
    volume_list = entry_by_name("afterglow_volume_list")
    assert volume_list is not None
    assert set(volume_list.input_schema()["properties"]) == ({"project_id"} | {"limit"})
    assert set(volume_list.output_schema()["$defs"]["VolumeSummaryOutput"]["properties"]) == {
        "id",
        "name",
        "status",
        "size_gb",
        "created_at",
    }
    volume_get = entry_by_name("afterglow_volume_get")
    assert volume_get is not None
    assert set(volume_get.input_schema()["properties"]) == ({"project_id"} | {"volume_id"})
    assert set(volume_get.output_schema()["properties"]) == {
        "id",
        "name",
        "status",
        "size_gb",
        "created_at",
    }
    snapshot_list = entry_by_name("afterglow_volume_snapshot_list")
    assert snapshot_list is not None
    assert set(snapshot_list.input_schema()["properties"]) == ({"project_id"} | {"limit"})
    assert set(snapshot_list.output_schema()["$defs"]["SnapshotSummaryOutput"]["properties"]) == {
        "id",
        "name",
        "status",
        "source_volume_id",
        "size_gb",
        "created_at",
    }
    snapshot_get = entry_by_name("afterglow_volume_snapshot_get")
    assert snapshot_get is not None
    assert set(snapshot_get.input_schema()["properties"]) == ({"project_id"} | {"snapshot_id"})
    assert set(snapshot_get.output_schema()["properties"]) == {
        "id",
        "name",
        "status",
        "source_volume_id",
        "size_gb",
        "created_at",
    }
    backup_list = entry_by_name("afterglow_volume_backup_list")
    assert backup_list is not None
    assert set(backup_list.input_schema()["properties"]) == ({"project_id"} | {"limit"})
    assert set(backup_list.output_schema()["$defs"]["BackupSummaryOutput"]["properties"]) == {
        "id",
        "name",
        "status",
        "source_volume_id",
        "size_gb",
        "created_at",
    }
    backup_get = entry_by_name("afterglow_volume_backup_get")
    assert backup_get is not None
    assert set(backup_get.input_schema()["properties"]) == ({"project_id"} | {"backup_id"})
    assert set(backup_get.output_schema()["properties"]) == {
        "id",
        "name",
        "status",
        "source_volume_id",
        "size_gb",
        "created_at",
    }
    network_list = entry_by_name("afterglow_network_list")
    assert network_list is not None
    assert set(network_list.input_schema()["properties"]) == ({"project_id"} | {"limit"})
    assert set(network_list.output_schema()["$defs"]["NetworkSummaryOutput"]["properties"]) == {
        "id",
        "name",
        "status",
        "is_shared",
        "is_external",
        "visibility",
    }
    network_get = entry_by_name("afterglow_network_get")
    assert network_get is not None
    assert set(network_get.input_schema()["properties"]) == ({"project_id"} | {"network_id"})
    assert set(network_get.output_schema()["properties"]) == {
        "id",
        "name",
        "status",
        "is_shared",
        "is_external",
        "visibility",
    }
    subnet_list = entry_by_name("afterglow_subnet_list")
    assert subnet_list is not None
    assert set(subnet_list.input_schema()["properties"]) == ({"project_id"} | {"limit"})
    assert set(subnet_list.output_schema()["$defs"]["SubnetSummaryOutput"]["properties"]) == {
        "id",
        "name",
        "network_id",
        "cidr",
        "ip_version",
        "gateway_ip",
    }
    subnet_get = entry_by_name("afterglow_subnet_get")
    assert subnet_get is not None
    assert set(subnet_get.input_schema()["properties"]) == ({"project_id"} | {"subnet_id"})
    assert set(subnet_get.output_schema()["properties"]) == {
        "id",
        "name",
        "network_id",
        "cidr",
        "ip_version",
        "gateway_ip",
    }
    assert entry_by_name("afterglow_vm_console_get") is None
    vm_action = entry_by_name("afterglow_vm_action")
    assert vm_action is not None
    assert vm_action.minimum_scope == "mcp:write"
    assert vm_action.effect == "external_mutation"
    assert set(vm_action.input_schema()["properties"]) == ({"project_id"} | {"server_id", "action"})
    assert set(vm_action.mcp_input_schema()["properties"]) == (
        {"project_id"} | {"server_id", "action", "idempotency_key"}
    )
    assert set(vm_action.output_schema()["properties"]) == {
        "id",
        "name",
        "status",
        "created_at",
        "updated_at",
        "requested_action",
    }
    vm_delete = entry_by_name("afterglow_vm_delete")
    assert vm_delete is not None
    assert vm_delete.minimum_scope == "mcp:write"
    assert vm_delete.effect == "external_mutation"
    assert set(vm_delete.input_schema()["properties"]) == ({"project_id"} | {"server_id"})
    assert set(vm_delete.mcp_input_schema()["properties"]) == ({"project_id"} | {"server_id", "idempotency_key"})
    assert set(vm_delete.output_schema()["properties"]) == {
        "id",
        "name",
        "status",
        "created_at",
        "updated_at",
        "requested_action",
    }
    volume_delete = entry_by_name("afterglow_volume_delete")
    assert volume_delete is not None
    assert volume_delete.minimum_scope == "mcp:write"
    assert volume_delete.effect == "external_mutation"
    assert set(volume_delete.input_schema()["properties"]) == ({"project_id"} | {"volume_id"})
    assert set(volume_delete.mcp_input_schema()["properties"]) == ({"project_id"} | {"volume_id", "idempotency_key"})
    assert set(volume_delete.output_schema()["properties"]) == {
        "id",
        "name",
        "status",
        "size_gb",
        "created_at",
        "requested_action",
    }
    for name, argument_name, expected_fields in (
        (
            "afterglow_volume_snapshot_delete",
            "snapshot_id",
            {
                "id",
                "name",
                "status",
                "source_volume_id",
                "size_gb",
                "created_at",
                "requested_action",
            },
        ),
        (
            "afterglow_volume_backup_delete",
            "backup_id",
            {
                "id",
                "name",
                "status",
                "source_volume_id",
                "size_gb",
                "created_at",
                "requested_action",
            },
        ),
    ):
        entry = entry_by_name(name)
        assert entry is not None
        assert entry.minimum_scope == "mcp:write"
        assert entry.effect == "external_mutation"
        assert set(entry.input_schema()["properties"]) == ({"project_id"} | {argument_name})
        assert set(entry.mcp_input_schema()["properties"]) == ({"project_id"} | {argument_name, "idempotency_key"})
        assert set(entry.output_schema()["properties"]) == expected_fields
    network_delete = entry_by_name("afterglow_network_delete")
    assert network_delete is not None
    assert network_delete.minimum_scope == "mcp:write"
    assert network_delete.effect == "external_mutation"
    assert set(network_delete.input_schema()["properties"]) == ({"project_id"} | {"network_id"})
    assert set(network_delete.mcp_input_schema()["properties"]) == ({"project_id"} | {"network_id", "idempotency_key"})
    assert set(network_delete.output_schema()["properties"]) == {
        "id",
        "name",
        "status",
        "is_shared",
        "is_external",
        "visibility",
        "requested_action",
    }
    subnet_delete = entry_by_name("afterglow_subnet_delete")
    assert subnet_delete is not None
    assert subnet_delete.minimum_scope == "mcp:write"
    assert subnet_delete.effect == "external_mutation"
    assert set(subnet_delete.input_schema()["properties"]) == ({"project_id"} | {"subnet_id"})
    assert set(subnet_delete.mcp_input_schema()["properties"]) == ({"project_id"} | {"subnet_id", "idempotency_key"})
    assert set(subnet_delete.output_schema()["properties"]) == {
        "id",
        "name",
        "network_id",
        "cidr",
        "ip_version",
        "gateway_ip",
        "requested_action",
    }
    database_list = entry_by_name("afterglow_database_instance_list")
    assert database_list is not None
    assert database_list.service_flag == "service_trove_enabled"
    assert set(database_list.input_schema()["properties"]) == ({"project_id"} | {"limit"})
    assert set(database_list.output_schema()["$defs"]["DatabaseInstanceSummaryOutput"]["properties"]) == {
        "id",
        "name",
        "status",
        "datastore_type",
        "datastore_version",
        "created_at",
    }
    database_get = entry_by_name("afterglow_database_instance_get")
    assert database_get is not None
    assert database_get.service_flag == "service_trove_enabled"
    assert set(database_get.input_schema()["properties"]) == ({"project_id"} | {"instance_id"})
    assert set(database_get.output_schema()["properties"]) == {
        "id",
        "name",
        "status",
        "datastore_type",
        "datastore_version",
        "created_at",
    }
    for name in ("afterglow_database_instance_restart", "afterglow_database_instance_delete"):
        entry = entry_by_name(name)
        assert entry is not None
        assert entry.service_flag == "service_trove_enabled"
        assert entry.minimum_scope == "mcp:write"
        assert entry.effect == "external_mutation"
        assert set(entry.input_schema()["properties"]) == ({"project_id"} | {"instance_id"})
        assert set(entry.mcp_input_schema()["properties"]) == ({"project_id"} | {"instance_id", "idempotency_key"})
    container_list = entry_by_name("afterglow_container_list")
    assert container_list is not None
    assert container_list.service_flag == "service_zun_enabled"
    assert set(container_list.input_schema()["properties"]) == ({"project_id"} | {"limit"})
    assert set(container_list.output_schema()["$defs"]["ContainerSummaryOutput"]["properties"]) == {
        "id",
        "name",
        "status",
        "image",
        "created_at",
    }
    container_get = entry_by_name("afterglow_container_get")
    assert container_get is not None
    assert container_get.service_flag == "service_zun_enabled"
    assert set(container_get.input_schema()["properties"]) == ({"project_id"} | {"container_id"})
    assert set(container_get.output_schema()["properties"]) == {
        "id",
        "name",
        "status",
        "image",
        "created_at",
    }
    for name, expected_properties in (
        ("afterglow_container_action", {"container_id", "action"}),
        ("afterglow_container_delete", {"container_id"}),
    ):
        entry = entry_by_name(name)
        assert entry is not None
        assert entry.service_flag == "service_zun_enabled"
        assert entry.minimum_scope == "mcp:write"
        assert entry.effect == "external_mutation"
        assert set(entry.input_schema()["properties"]) == ({"project_id"} | expected_properties)
        assert set(entry.mcp_input_schema()["properties"]) == (
            {"project_id"} | {*expected_properties, "idempotency_key"}
        )


@pytest.mark.asyncio
async def test_capabilities_reports_only_domains_with_registered_enabled_tools(monkeypatch):
    monkeypatch.setattr(
        "app.services.mcp_control_plane.registry.get_settings",
        lambda: SimpleNamespace(service_trove_enabled=True, service_zun_enabled=True),
    )
    principal = McpPrincipal(
        grant_id="grant-a",
        user_id="user-a",
        project_id="project-a",
        credential_epoch=1,
        scopes=frozenset({"mcp:read"}),
        source="personal_token",
    )
    entry = entry_by_name("afterglow_capabilities_get")
    assert entry is not None

    result = await entry.handler(ConsumerCloudContext(principal=principal), entry.arguments())

    assert result.enabled_domains == ["compute", "containers", "database", "network", "storage"]


def test_external_mutation_schema_requires_envelope_key_without_widening_domain_schema():
    entry = _mutation_entry()

    schema = entry.mcp_input_schema()

    assert schema["required"] == ["resource_id", "idempotency_key"]
    assert "idempotency_key" in schema["properties"]
    assert parse_entry_arguments(entry, {"resource_id": "vm-a"}).resource_id == "vm-a"
    with pytest.raises(Exception):
        parse_entry_arguments(entry, {"resource_id": "vm-a", "idempotency_key": "call-0001"})


def test_registry_accepts_json_uuid_strings_without_widening_other_arguments():
    entry = entry_by_name("afterglow_vm_get")
    assert entry is not None

    parsed = parse_entry_arguments(entry, {"server_id": "12345678-1234-1234-1234-123456789abc"})

    assert str(parsed.server_id) == "12345678-1234-1234-1234-123456789abc"


@pytest.mark.asyncio
async def test_external_mutation_preview_is_required_and_closed_to_registered_arguments():
    with pytest.raises(ValueError, match="preview"):
        replace(_mutation_entry(), preview_builder=None)
    principal = McpPrincipal(
        grant_id="grant-a",
        user_id="user-a",
        project_id="project-a",
        credential_epoch=1,
        scopes=frozenset({"mcp:read", "mcp:write"}),
        source="personal_token",
    )

    preview = await build_mutation_preview(
        ConsumerCloudContext(principal=principal),
        entry=_mutation_entry(),
        arguments=_MutationArguments(resource_id="vm-a"),
    )

    assert preview.model_dump() == {
        "resource_identity": "vm-a",
        "current_state": "ACTIVE",
        "intended_transition": "stop",
        "dependent_resources": [],
        "destructive": False,
        "estimated_effect": None,
        "fingerprint": "test-fingerprint",
    }


def test_idempotency_key_and_argument_hash_are_strict_and_canonical():
    assert validate_idempotency_key("call-0001") == "call-0001"
    assert canonical_arguments_hash({"label": "caf\u00e9"}) == canonical_arguments_hash({"label": "cafe\u0301"})
    with pytest.raises(McpInvocationError, match="idempotency"):
        validate_idempotency_key("short")
    with pytest.raises(McpInvocationError, match="idempotency"):
        validate_idempotency_key("call key with spaces")
    with pytest.raises(McpInvocationError, match="canonically"):
        canonical_arguments_hash({"not_a_number": float("nan")})


def test_registry_rejects_output_exceeding_entry_safe_limit():
    entry = _mutation_entry()

    with pytest.raises(ValueError, match="safe output limit"):
        output_payload(entry, _MutationOutput(status="x" * (64 * 1024)))


@pytest.mark.asyncio
async def test_registry_enforces_timeouts_for_handlers_and_mutation_previews():
    principal = McpPrincipal(
        grant_id="grant-a",
        user_id="user-a",
        project_id="project-a",
        credential_epoch=1,
        scopes=frozenset({"mcp:read", "mcp:write"}),
        source="personal_token",
    )
    context = ConsumerCloudContext(principal=principal)

    async def stalled_handler(_: ConsumerCloudContext, __: _MutationArguments) -> _MutationOutput:
        await asyncio.sleep(1)
        return _MutationOutput(status="accepted")

    async def stalled_preview(_: ConsumerCloudContext, __: _MutationArguments) -> McpMutationPreview:
        await asyncio.sleep(1)
        return await _mutation_preview(_, __)

    arguments = _MutationArguments(resource_id="vm-a")
    stalled_handler_entry = replace(_mutation_entry(), handler=stalled_handler, timeout_seconds=0.001)
    with pytest.raises(ValueError, match="timed out"):
        await dispatch(context, entry=stalled_handler_entry, arguments=arguments)

    stalled_preview_entry = replace(_mutation_entry(), preview_builder=stalled_preview, timeout_seconds=0.001)
    with pytest.raises(ValueError, match="preview timed out"):
        await build_mutation_preview(context, entry=stalled_preview_entry, arguments=arguments)
