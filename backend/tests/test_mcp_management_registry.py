"""Behavioral coverage for management handlers, approval plans and authority boundaries."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import replace
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.api import mcp_lumen
from app.services.mcp_control_plane import ledger, registry, transport
from app.services.mcp_control_plane.authentication import McpPrincipal

NETWORK_ID = "11111111-1111-4111-8111-111111111111"
SUBNET_ID = "22222222-2222-4222-8222-222222222222"
PORT_ID = "33333333-3333-4333-8333-333333333333"
SERVER_ID = "44444444-4444-4444-8444-444444444444"
GROUP_ID = "55555555-5555-4555-8555-555555555555"
VOLUME_ID = "66666666-6666-4666-8666-666666666666"
ATTACHMENT_ID = "77777777-7777-4777-8777-777777777777"
NETWORK = {
    "id": NETWORK_ID,
    "name": "tenant-net",
    "status": "ACTIVE",
    "is_shared": False,
    "is_external": False,
    "visibility": "owned",
}
SUBNET = {
    "id": SUBNET_ID,
    "name": "tenant-subnet",
    "network_id": NETWORK_ID,
    "cidr": "192.0.2.0/24",
    "ip_version": 4,
    "gateway_ip": "192.0.2.1",
}
PORT = {
    "id": PORT_ID,
    "name": "tenant-port",
    "description": "",
    "network_id": NETWORK_ID,
    "status": "DOWN",
    "admin_state_up": True,
    "mac_address": "fa:16:3e:00:00:01",
    "device_id": "",
    "device_owner": "",
    "fixed_ips": [{"subnet_id": SUBNET_ID, "ip_address": "192.0.2.20"}],
    "security_group_ids": [GROUP_ID],
}
GROUP = {"id": GROUP_ID, "name": "web", "description": "tenant web group"}
INTERFACE = {
    "server_id": SERVER_ID,
    "network_id": NETWORK_ID,
    "port_id": PORT_ID,
    "mac_address": PORT["mac_address"],
}
VOLUME = {
    "id": VOLUME_ID,
    "name": "data",
    "status": "available",
    "size_gb": 10,
    "created_at": None,
}
ATTACHMENT = {
    "server_id": SERVER_ID,
    "volume_id": VOLUME_ID,
    "attachment_id": ATTACHMENT_ID,
    "device": "/dev/sdb",
}

# Each case asserts the real public handler forwards the selected target and exact
# typed inputs to its one frozen adapter, then validates the adapter's final output.
MUTATIONS = [
    (
        "afterglow_network_create",
        "project_network_create",
        {"name": "tenant-net", "admin_state_up": False},
        {"attributes": {"name": "tenant-net", "admin_state_up": False}},
        {**NETWORK, "requested_action": "create"},
    ),
    (
        "afterglow_network_update",
        "project_network_update",
        {"network_id": NETWORK_ID, "description": "", "admin_state_up": False},
        {"network_id": NETWORK_ID, "attributes": {"description": "", "admin_state_up": False}},
        {**NETWORK, "requested_action": "update"},
    ),
    (
        "afterglow_subnet_create",
        "project_subnet_create",
        {"network_id": NETWORK_ID, "name": "tenant-subnet", "cidr": "192.0.2.0/24", "gateway_ip": None},
        {"attributes": {"network_id": NETWORK_ID, "name": "tenant-subnet", "cidr": "192.0.2.0/24", "gateway_ip": None}},
        {**SUBNET, "requested_action": "create"},
    ),
    (
        "afterglow_subnet_update",
        "project_subnet_update",
        {"subnet_id": SUBNET_ID, "gateway_ip": None, "dns_nameservers": []},
        {"subnet_id": SUBNET_ID, "attributes": {"gateway_ip": None, "dns_nameservers": []}},
        {**SUBNET, "requested_action": "update"},
    ),
    (
        "afterglow_port_create",
        "project_port_create",
        {"network_id": NETWORK_ID, "fixed_ips": [{"subnet_id": SUBNET_ID}], "security_group_ids": [GROUP_ID]},
        {
            "attributes": {
                "network_id": NETWORK_ID,
                "fixed_ips": [{"subnet_id": SUBNET_ID}],
                "security_group_ids": [GROUP_ID],
            }
        },
        {**PORT, "requested_action": "create"},
    ),
    (
        "afterglow_port_update",
        "project_port_update",
        {"port_id": PORT_ID, "fixed_ips": [], "security_group_ids": []},
        {"port_id": PORT_ID, "attributes": {"fixed_ips": [], "security_group_ids": []}},
        {**PORT, "requested_action": "update"},
    ),
    (
        "afterglow_port_delete",
        "project_port_delete",
        {"port_id": PORT_ID},
        {"port_id": PORT_ID},
        {**PORT, "requested_action": "delete"},
    ),
    (
        "afterglow_vm_interface_attach",
        "project_server_interface_attach",
        {"server_id": SERVER_ID, "port_id": PORT_ID},
        {"server_id": SERVER_ID, "port_id": PORT_ID},
        {**INTERFACE, "requested_action": "attach_interface"},
    ),
    (
        "afterglow_vm_interface_detach",
        "project_server_interface_detach",
        {"server_id": SERVER_ID, "port_id": PORT_ID},
        {"server_id": SERVER_ID, "port_id": PORT_ID},
        {**INTERFACE, "requested_action": "detach_interface"},
    ),
    (
        "afterglow_vm_security_groups_set",
        "project_server_security_groups_set",
        {"server_id": SERVER_ID, "port_id": PORT_ID, "security_group_ids": [GROUP_ID]},
        {"server_id": SERVER_ID, "port_id": PORT_ID, "security_group_ids": [GROUP_ID]},
        {
            "server_id": SERVER_ID,
            "port_id": PORT_ID,
            "security_group_ids": [GROUP_ID],
            "requested_action": "set_security_groups",
        },
    ),
    (
        "afterglow_volume_update",
        "project_volume_update",
        {"volume_id": VOLUME_ID, "description": ""},
        {"volume_id": VOLUME_ID, "attributes": {"description": ""}},
        {**VOLUME, "requested_action": "update"},
    ),
    (
        "afterglow_volume_extend",
        "project_volume_extend",
        {"volume_id": VOLUME_ID, "size_gb": 20},
        {"volume_id": VOLUME_ID, "size_gb": 20},
        {**VOLUME, "requested_action": "extend", "requested_size_gb": 20},
    ),
    (
        "afterglow_vm_volume_attach",
        "project_server_volume_attach",
        {"server_id": SERVER_ID, "volume_id": VOLUME_ID},
        {"server_id": SERVER_ID, "volume_id": VOLUME_ID},
        {**ATTACHMENT, "requested_action": "attach_volume"},
    ),
    (
        "afterglow_vm_volume_detach",
        "project_server_volume_detach",
        {"server_id": SERVER_ID, "volume_id": VOLUME_ID},
        {"server_id": SERVER_ID, "volume_id": VOLUME_ID},
        {**ATTACHMENT, "requested_action": "detach_volume"},
    ),
]
READS = [
    (
        "afterglow_port_list",
        "list_project_ports",
        {"limit": 7, "network_id": NETWORK_ID},
        {"limit": 7, "network_id": NETWORK_ID},
        [PORT],
        {"ports": [PORT]},
    ),
    ("afterglow_port_get", "get_project_port", {"port_id": PORT_ID}, {"port_id": PORT_ID}, PORT, PORT),
    (
        "afterglow_security_group_list",
        "list_project_security_groups",
        {"limit": 7},
        {"limit": 7},
        [GROUP],
        {"security_groups": [GROUP]},
    ),
    (
        "afterglow_security_group_get",
        "get_project_security_group",
        {"security_group_id": GROUP_ID},
        {"security_group_id": GROUP_ID},
        GROUP,
        GROUP,
    ),
]


@pytest.fixture
def management_runtime(monkeypatch):
    principal = McpPrincipal(
        grant_id="grant-a",
        user_id="user-a",
        project_id="project-a",
        credential_epoch=1,
        scopes=frozenset({"mcp:read", "mcp:write"}),
        source="personal_token",
    )
    state = SimpleNamespace(principal=principal, connection=object(), resolutions=[], connections=[])

    async def resolve(current, project_id=None, *, write=False):
        target = project_id or current.project_id
        state.resolutions.append((target, write))
        if target not in {"project-a", "project-b", "reader-project"} or (write and target == "reader-project"):
            raise ValueError("MCP target is unavailable")
        return replace(current, project_id=target, owner_project_id=current.anchor_project_id)

    @asynccontextmanager
    async def connection(context):
        state.connections.append(context.project_id)
        yield state.connection

    monkeypatch.setattr(registry, "resolve_principal_target", resolve)
    monkeypatch.setattr(registry.ConsumerCloudContext, "openstack_connection", connection)
    return state


@pytest.mark.asyncio
@pytest.mark.parametrize("name,adapter,raw,expected,result", MUTATIONS, ids=[case[0] for case in MUTATIONS])
async def test_management_mutations_preview_reads_then_dispatches_exact_desired_plan(
    monkeypatch,
    management_runtime,
    name,
    adapter,
    raw,
    expected,
    result,
):
    state = management_runtime
    calls = []

    async def preview(conn, **kwargs):
        assert conn is state.connection
        calls.append(("preview", kwargs))
        return {**result, "server_status": "ACTIVE", "volume_status": "available", "network_id": NETWORK_ID}

    async def request(conn, **kwargs):
        assert conn is state.connection
        calls.append(("request", kwargs))
        return result

    monkeypatch.setattr(registry, f"preview_{adapter}", preview)
    monkeypatch.setattr(registry, f"request_{adapter}", request)
    entry = registry.entry_by_name(name)
    parsed = registry.parse_entry_arguments(entry, {**raw, "project_id": "project-b"})
    # This is also the approval-confirmation serialization used by Lumen.
    confirmed = registry.parse_entry_arguments(entry, parsed.model_dump(mode="json"))
    context = registry.ConsumerCloudContext(principal=state.principal)
    plan = await registry.build_mutation_preview(context, entry=entry, arguments=confirmed)
    assert calls == [("preview", {"project_id": "project-b", **expected})]
    assert plan.intended_transition == result["requested_action"]
    assert plan.destructive == entry.destructive
    assert plan.estimated_effect
    output = await registry.dispatch(context, entry=entry, arguments=confirmed)
    assert registry.output_payload(entry, output) == result
    assert calls == [
        ("preview", {"project_id": "project-b", **expected}),
        ("request", {"project_id": "project-b", **expected}),
    ]
    assert state.connections == ["project-b", "project-b"]
    assert all(write for _, write in state.resolutions)


@pytest.mark.asyncio
@pytest.mark.parametrize("name,adapter,raw,expected,result,payload", READS, ids=[case[0] for case in READS])
async def test_management_reads_use_resolved_target_and_bounded_adapter_inputs(
    monkeypatch,
    management_runtime,
    name,
    adapter,
    raw,
    expected,
    result,
    payload,
):
    calls = []

    async def read(conn, **kwargs):
        assert conn is management_runtime.connection
        calls.append(kwargs)
        return result

    monkeypatch.setattr(registry, adapter, read)
    entry = registry.entry_by_name(name)
    parsed = registry.parse_entry_arguments(entry, {**raw, "project_id": "project-b"})
    output = await registry.dispatch(
        registry.ConsumerCloudContext(principal=management_runtime.principal),
        entry=entry,
        arguments=parsed,
    )
    assert registry.output_payload(entry, output) == payload
    assert calls == [{"project_id": "project-b", **expected}]
    assert management_runtime.resolutions == [("project-b", False)]


@pytest.mark.asyncio
@pytest.mark.parametrize("name,adapter,raw,expected,result", MUTATIONS, ids=[case[0] for case in MUTATIONS])
async def test_reader_cannot_direct_call_or_preview_management_mutations(
    management_runtime,
    name,
    adapter,
    raw,
    expected,
    result,
):
    reader = replace(management_runtime.principal, scopes=frozenset({"mcp:read"}))
    context = registry.ConsumerCloudContext(principal=reader)
    entry = registry.entry_by_name(name)
    parsed = registry.parse_entry_arguments(entry, raw)
    with pytest.raises(ValueError, match="MCP tool is unavailable"):
        await registry.dispatch(context, entry=entry, arguments=parsed)
    with pytest.raises(ValueError, match="MCP tool is unavailable"):
        await registry.build_mutation_preview(context, entry=entry, arguments=parsed)
    assert not management_runtime.resolutions
    assert not management_runtime.connections
    assert entry not in registry.enabled_entries(reader)


@pytest.mark.asyncio
async def test_management_target_write_denial_happens_before_connection_or_native_adapter(management_runtime):
    entry = registry.entry_by_name("afterglow_port_update")
    parsed = registry.parse_entry_arguments(
        entry,
        {"project_id": "reader-project", "port_id": PORT_ID, "description": "metadata"},
    )
    context = registry.ConsumerCloudContext(principal=management_runtime.principal)
    with pytest.raises(ValueError, match="target is unavailable"):
        await registry.dispatch(context, entry=entry, arguments=parsed)
    with pytest.raises(ValueError, match="target is unavailable"):
        await registry.build_mutation_preview(context, entry=entry, arguments=parsed)
    assert not management_runtime.connections


@pytest.mark.asyncio
@pytest.mark.parametrize("explicit", [{"gateway_ip": None}, {"gateway_ip": "192.0.2.2"}, {"enable_dhcp": False}])
async def test_omission_and_explicit_gateway_changes_bind_different_approval_and_ledger_hashes(
    monkeypatch,
    management_runtime,
    explicit,
):
    async def preview(conn, **kwargs):
        # Deliberately unchanged current summary: desired changes must still be bound.
        return {**SUBNET, "requested_action": "update"}

    monkeypatch.setattr(registry, "preview_project_subnet_update", preview)
    entry = registry.entry_by_name("afterglow_subnet_update")
    base = {"project_id": "project-b", "subnet_id": SUBNET_ID, "name": "renamed"}
    omitted = registry.parse_entry_arguments(entry, base)
    changed = registry.parse_entry_arguments(entry, {**base, **explicit})
    omitted_dump = omitted.model_dump(mode="json")
    changed_dump = changed.model_dump(mode="json")
    assert omitted_dump == base
    assert changed_dump == {**base, **explicit}
    assert ledger.canonical_arguments_hash(omitted_dump) != ledger.canonical_arguments_hash(changed_dump)
    reparsed = registry.parse_entry_arguments(entry, omitted_dump)
    assert reparsed.model_dump(mode="json") == omitted_dump
    assert "gateway_ip" not in reparsed.model_fields_set
    context = registry.ConsumerCloudContext(principal=management_runtime.principal)
    first = await registry.build_mutation_preview(context, entry=entry, arguments=omitted)
    repeated = await registry.build_mutation_preview(context, entry=entry, arguments=reparsed)
    second = await registry.build_mutation_preview(context, entry=entry, arguments=changed)
    assert first.fingerprint == repeated.fingerprint
    assert first.fingerprint != second.fingerprint
    assert first.estimated_effect != second.estimated_effect


@pytest.mark.asyncio
async def test_fingerprint_binds_target_project_even_when_provider_summaries_match(monkeypatch, management_runtime):
    async def preview(conn, **kwargs):
        return {**NETWORK, "requested_action": "update"}

    monkeypatch.setattr(registry, "preview_project_network_update", preview)
    entry = registry.entry_by_name("afterglow_network_update")
    context = registry.ConsumerCloudContext(principal=management_runtime.principal)
    plans = []
    for target in ("project-a", "project-b"):
        plans.append(
            await registry.build_mutation_preview(
                context,
                entry=entry,
                arguments=registry.parse_entry_arguments(
                    entry, {"project_id": target, "network_id": NETWORK_ID, "name": "same"}
                ),
            )
        )
    assert plans[0].fingerprint != plans[1].fingerprint


@pytest.mark.asyncio
async def test_empty_group_replacement_is_explicit_destructive_and_not_an_omitted_default(
    monkeypatch, management_runtime
):
    calls = []

    async def preview(conn, **kwargs):
        calls.append(kwargs)
        return {
            "server_id": SERVER_ID,
            "port_id": PORT_ID,
            "network_id": NETWORK_ID,
            "server_status": "ACTIVE",
            "current_security_group_ids": [GROUP_ID],
            "security_group_ids": kwargs["security_group_ids"],
            "requested_action": "set_security_groups",
        }

    monkeypatch.setattr(registry, "preview_project_server_security_groups_set", preview)
    entry = registry.entry_by_name("afterglow_vm_security_groups_set")
    raw = {"server_id": SERVER_ID, "port_id": PORT_ID, "security_group_ids": []}
    parsed = registry.parse_entry_arguments(entry, raw)
    confirmed = registry.parse_entry_arguments(entry, parsed.model_dump(mode="json"))
    plan = await registry.build_mutation_preview(
        registry.ConsumerCloudContext(principal=management_runtime.principal),
        entry=entry,
        arguments=confirmed,
    )
    assert calls[0]["security_group_ids"] == []
    assert plan.destructive and "[] removes every group" in plan.estimated_effect
    assert f"nova-server:{SERVER_ID}" in plan.dependent_resources
    with pytest.raises(ValidationError):
        registry.parse_entry_arguments(entry, {"server_id": SERVER_ID, "port_id": PORT_ID})


@pytest.mark.asyncio
async def test_transport_and_lumen_keep_omission_distinct_in_actual_claim_normalization(
    monkeypatch, management_runtime
):
    claims = []

    async def claim(principal, **kwargs):
        claims.append(kwargs["arguments"])
        # A replay stops before execution; this test exercises each real caller's
        # parser/binder/serializer before its durable claim, not a copied recipe.
        return SimpleNamespace(state="replay", result={})

    monkeypatch.setattr(transport, "claim_mutation", claim)
    monkeypatch.setattr(ledger, "claim_mutation", claim)
    entry = registry.entry_by_name("afterglow_subnet_create")
    base = {"network_id": NETWORK_ID, "name": "tenant-subnet", "cidr": "192.0.2.0/24"}
    token = transport._current_principal.set(management_runtime.principal)
    try:
        for extra in ({}, {"gateway_ip": None}):
            raw = {**base, **extra}
            await transport._call_tool(entry.name, {**raw, "idempotency_key": "management-normalization"})
            body = mcp_lumen._ExecuteRequest(
                snapshot={},
                name=entry.name,
                arguments=raw,
                idempotency_key="management-normalization",
            )
            await mcp_lumen._execute_tool(management_runtime.principal, entry=entry, body=body)
    finally:
        transport._current_principal.reset(token)
    assert claims[0] == claims[1] == {"project_id": "project-a", **base}
    assert claims[2] == claims[3] == {"project_id": "project-a", **base, "gateway_ip": None}
    assert ledger.canonical_arguments_hash(claims[0]) != ledger.canonical_arguments_hash(claims[2])
    for normalized in claims:
        confirmed = registry.parse_entry_arguments(entry, normalized)
        assert confirmed.model_dump(mode="json") == normalized
        assert "enable_dhcp" not in normalized and "dns_nameservers" not in normalized


@pytest.mark.parametrize(
    "name,raw",
    [
        ("afterglow_network_update", {"network_id": NETWORK_ID}),
        ("afterglow_subnet_update", {"subnet_id": SUBNET_ID}),
        ("afterglow_port_update", {"port_id": PORT_ID}),
        ("afterglow_volume_update", {"volume_id": VOLUME_ID}),
        ("afterglow_network_create", {"name": "net", "admin_state_up": "false"}),
        ("afterglow_network_create", {"name": "net", "description": None}),
        (
            "afterglow_subnet_create",
            {"network_id": NETWORK_ID, "name": "subnet", "cidr": "192.0.2.0/24", "enable_dhcp": 0},
        ),
        (
            "afterglow_port_create",
            {"network_id": NETWORK_ID, "fixed_ips": [{"subnet_id": SUBNET_ID, "ip_address": None}]},
        ),
        ("afterglow_port_create", {"network_id": NETWORK_ID, "security_group_ids": [GROUP_ID, GROUP_ID]}),
        ("afterglow_port_create", {"network_id": NETWORK_ID, "security_group_ids": None}),
        ("afterglow_port_update", {"port_id": PORT_ID, "device_id": SERVER_ID}),
        (
            "afterglow_vm_security_groups_set",
            {"server_id": SERVER_ID, "port_id": PORT_ID, "security_group_ids": [GROUP_ID, GROUP_ID]},
        ),
        (
            "afterglow_vm_security_groups_set",
            {"server_id": SERVER_ID, "port_id": PORT_ID, "security_group_ids": (GROUP_ID,)},
        ),
        ("afterglow_volume_extend", {"volume_id": VOLUME_ID, "size_gb": True}),
        ("afterglow_volume_extend", {"volume_id": VOLUME_ID, "size_gb": "20"}),
        ("afterglow_port_list", {"limit": 101}),
        ("afterglow_security_group_list", {"limit": True}),
    ],
)
def test_management_rejects_ambiguous_or_widened_inputs_before_native_calls(name, raw):
    with pytest.raises(ValidationError):
        registry.parse_entry_arguments(registry.entry_by_name(name), raw)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name,adapter,raw,error",
    [
        ("afterglow_port_delete", "project_port_delete", {"port_id": PORT_ID}, registry.McpNetworkError),
        (
            "afterglow_vm_security_groups_set",
            "project_server_security_groups_set",
            {"server_id": SERVER_ID, "port_id": PORT_ID, "security_group_ids": []},
            registry.McpNetworkError,
        ),
        (
            "afterglow_volume_extend",
            "project_volume_extend",
            {"volume_id": VOLUME_ID, "size_gb": 20},
            registry.McpStorageError,
        ),
    ],
)
async def test_adapter_owner_state_or_revision_refusal_is_safe_and_never_runs_request_after_preview(
    monkeypatch,
    management_runtime,
    name,
    adapter,
    raw,
    error,
):
    calls = []

    async def preview(conn, **kwargs):
        calls.append("preview")
        raise error("provider-token-secret; revision-if-match unavailable")

    async def request(conn, **kwargs):
        calls.append("request")
        raise error("provider-token-secret; post-write outcome unknown")

    monkeypatch.setattr(registry, f"preview_{adapter}", preview)
    monkeypatch.setattr(registry, f"request_{adapter}", request)
    entry = registry.entry_by_name(name)
    parsed = registry.parse_entry_arguments(entry, raw)
    context = registry.ConsumerCloudContext(principal=management_runtime.principal)
    with pytest.raises(ValueError) as preview_error:
        await registry.build_mutation_preview(context, entry=entry, arguments=parsed)
    assert "provider-token-secret" not in str(preview_error.value)
    assert calls == ["preview"]
    with pytest.raises(ValueError) as request_error:
        await registry.dispatch(context, entry=entry, arguments=parsed)
    assert "provider-token-secret" not in str(request_error.value)
    assert calls == ["preview", "request"]


@pytest.mark.asyncio
async def test_port_output_validation_redacts_public_error_and_actual_read_ledger_text(monkeypatch, management_runtime):
    recorded = []

    async def get_port(conn, **kwargs):
        return {**PORT, "binding_profile": {"native-secret": "must-not-escape"}}

    async def record(principal, **kwargs):
        recorded.append(kwargs)

    monkeypatch.setattr(registry, "get_project_port", get_port)
    monkeypatch.setattr(transport, "record_read_invocation", record)
    token = transport._current_principal.set(management_runtime.principal)
    try:
        with pytest.raises(ValueError) as public_error:
            await transport._call_tool("afterglow_port_get", {"port_id": PORT_ID})
    finally:
        transport._current_principal.reset(token)
    assert str(public_error.value) == "MCP management response is unavailable"
    assert len(recorded) == 1 and recorded[0]["status"] == "failed"
    assert recorded[0]["error"] == str(public_error.value)
    for forbidden in ("native-secret", "must-not-escape", "binding_profile"):
        assert forbidden not in str(public_error.value)
        assert forbidden not in str(recorded)


@pytest.mark.asyncio
async def test_management_output_does_not_coerce_provider_size_strings(monkeypatch, management_runtime):
    async def extend(conn, **kwargs):
        return {**VOLUME, "size_gb": "10", "requested_action": "extend", "requested_size_gb": 20}

    monkeypatch.setattr(registry, "request_project_volume_extend", extend)
    entry = registry.entry_by_name("afterglow_volume_extend")
    with pytest.raises(ValueError, match="^MCP management response is unavailable$"):
        await registry.dispatch(
            registry.ConsumerCloudContext(principal=management_runtime.principal),
            entry=entry,
            arguments=registry.parse_entry_arguments(entry, {"volume_id": VOLUME_ID, "size_gb": 20}),
        )
