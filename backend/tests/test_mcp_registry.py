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


def test_consumer_registry_excludes_lumen_service_and_its_api_key_controls():
    for entry in registry_entries():
        assert "lumen" not in entry.name.lower()
        assert entry.service_flag != "service_chat_enabled"


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
