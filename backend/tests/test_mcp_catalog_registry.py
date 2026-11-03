"""Exercise catalog discovery through the real registry and shared MCP transport."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.models.mcp_authority import McpDelegatedGrant, McpPersonalToken
from app.services.mcp_control_plane import authentication, registry, transport
from app.services.mcp_control_plane.authority import McpAuthorityError

IMAGE_ID = "33333333-3333-4333-8333-333333333333"
NETWORK_ID = "22222222-2222-4222-8222-222222222222"
SERVER_ID = "11111111-1111-4111-8111-111111111111"
CATALOG_ARGUMENTS = {
    "afterglow_flavor_list": {},
    "afterglow_flavor_get": {"flavor_id": "standard.small"},
    "afterglow_image_list": {},
    "afterglow_image_get": {"image_id": IMAGE_ID},
    "afterglow_keypair_list": {},
    "afterglow_keypair_get": {"key_name": "research-key"},
}
FLAVOR_FIELDS = {"id", "name", "vcpus", "ram_mb", "disk_gb", "is_public", "is_gpu", "requires_usage_schedule"}
IMAGE_FIELDS = {
    "id",
    "name",
    "status",
    "visibility",
    "min_disk_gb",
    "min_ram_mb",
    "size_bytes",
    "disk_format",
    "os_distro",
    "os_version",
    "os_admin_user",
}
KEYPAIR_FIELDS = {"name", "type", "fingerprint"}


class CatalogSession:
    """Substitute storage only; saved-project and scope validation stay production code."""

    def __init__(self, grant):
        self.grant = grant

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def begin(self):
        return self

    async def scalar(self, statement):
        entity = statement.column_descriptions[0]["entity"]
        if entity is McpDelegatedGrant:
            assert statement.compile().params["owner_project_id_1"] == "project-a"
            return self.grant
        if entity is McpPersonalToken:
            return SimpleNamespace(revoked_at=None)
        raise AssertionError(entity)


@pytest.fixture
def catalog_runtime(monkeypatch):
    grant = SimpleNamespace(
        id="grant-a",
        owner_user_id="user-a",
        owner_project_id="project-a",
        source="personal_token",
        status="active",
        access_level="read",
        credential_epoch=1,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        approved_projects=[
            {"id": "project-a", "name": "Alpha", "roles": ["reader"], "can_write": False},
            {"id": "project-b", "name": "Beta", "roles": ["reader"], "can_write": False},
        ],
    )
    monkeypatch.setattr(authentication, "get_session_factory", lambda: lambda: CatalogSession(grant))

    async def lock_owner(*args, **kwargs):
        return SimpleNamespace()

    monkeypatch.setattr(authentication, "lock_owner", lock_owner)
    state = SimpleNamespace(
        grant=grant,
        calls=[],
        connections=[],
        audits=[],
        flavor={
            "id": "standard.small",
            "name": "Not a GPU despite its name",
            "vcpus": 2,
            "ram": 4096,
            "disk": 20,
            "is_public": True,
            "extra_specs": {},
            "description": "native-secret",
        },
        image={
            "id": IMAGE_ID,
            "name": "Ubuntu",
            "status": "active",
            "visibility": "public",
            "owner": "provider-project",
            "owner_id": "provider-project",
            "min_disk": 10,
            "min_ram": 1024,
            "size": 2048,
            "disk_format": "qcow2",
            "os_distro": "ubuntu",
            "os_version": "24.04",
            "os_admin_user": "ubuntu",
            "locations": ["https://native-secret.invalid/image"],
            "properties": {"private_property": "native-secret"},
        },
        keypair={
            "name": "research-key",
            "user_id": "user-a",
            "type": "ssh",
            "fingerprint": "aa:bb",
            "private_key": "native-secret-private-key",
            "public_key": "native-secret-public-key",
        },
        network={
            "id": NETWORK_ID,
            "name": "Research",
            "status": "ACTIVE",
            "project_id": "project-b",
            "is_shared": False,
            "is_router_external": False,
            "provider:physical_network": "native-secret",
        },
    )

    class Compute:
        def flavors(self, **kwargs):
            state.calls.append(("flavors", kwargs))
            return iter([state.flavor])

        def get_flavor(self, flavor_id, **kwargs):
            state.calls.append(("get_flavor", flavor_id, kwargs))
            return state.flavor

        def fetch_flavor_extra_specs(self, flavor):
            state.calls.append(("fetch_flavor_extra_specs",))
            return state.flavor

        def get_flavor_access(self, flavor_id):
            state.calls.append(("get_flavor_access", flavor_id))
            return []

        def get(self, path, **kwargs):
            assert path == "/os-keypairs"
            assert kwargs["microversion"] == "2.35"
            assert kwargs["redirect"] is False and kwargs["allow_reauth"] is False
            assert kwargs["connect_retries"] == 0 and kwargs["status_code_retries"] == 0
            assert "user_id" not in kwargs["params"]
            state.calls.append(("keypairs", kwargs))
            listed = {name: value for name, value in state.keypair.items() if name != "user_id"}
            return SimpleNamespace(
                status_code=200,
                json=lambda: {"keypairs": [{"keypair": listed}]},
            )

        def get_keypair(self, name, **kwargs):
            assert not kwargs, "Do not seed the provider owner via SDK get_keypair(user_id=...)"
            state.calls.append(("get_keypair", name))
            return state.keypair

    class Images:
        def images(self, **kwargs):
            state.calls.append(("images", kwargs))
            return iter([state.image])

        def get_image(self, image_id):
            state.calls.append(("get_image", image_id))
            return state.image

        def members(self, image_id, **kwargs):
            state.calls.append(("members", image_id, kwargs))
            return iter([])

    class Networks:
        def networks(self, **kwargs):
            state.calls.append(("networks", kwargs))
            return iter([state.network] if kwargs.get("project_id") == "project-b" else [])

        def get_network(self, network_id):
            state.calls.append(("get_network", network_id))
            return state.network

    state.conn = SimpleNamespace(compute=Compute(), image=Images(), network=Networks(), _afterglow_user_id="user-a")
    state.principal = authentication.McpPrincipal(
        grant_id="grant-a",
        user_id="user-a",
        project_id="project-a",
        credential_epoch=1,
        scopes=frozenset({"mcp:read"}),
        source="personal_token",
    )

    @asynccontextmanager
    async def connection(context):
        state.connections.append((context.project_id, context.user_id, context.principal.anchor_project_id))
        yield state.conn

    async def record(principal, **kwargs):
        state.audits.append((principal.project_id, kwargs))

    monkeypatch.setattr(registry.ConsumerCloudContext, "openstack_connection", connection)
    monkeypatch.setattr(transport, "record_read_invocation", record)
    return state


async def invoke(runtime, surface, name, arguments):
    if surface == "registry":
        entry = registry.entry_by_name(name)
        result = await registry.dispatch(
            registry.ConsumerCloudContext(principal=runtime.principal),
            entry=entry,
            arguments=registry.parse_entry_arguments(entry, arguments),
        )
        return registry.output_payload(entry, result)
    token = transport._current_principal.set(runtime.principal)
    try:
        return await transport._call_tool(name, arguments)
    finally:
        transport._current_principal.reset(token)


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["registry", "mcp"])
@pytest.mark.parametrize("name,arguments", CATALOG_ARGUMENTS.items())
async def test_reader_catalog_discovery_uses_resolved_project_and_redacts_native_data(
    catalog_runtime, surface, name, arguments
):
    result = await invoke(catalog_runtime, surface, name, {**arguments, "project_id": "project-b"})
    family = name.split("_")[1]
    collection = {"flavor": "flavors", "image": "images", "keypair": "keypairs"}[family]
    item = result[collection][0] if name.endswith("_list") else result
    assert set(item) == {"flavor": FLAVOR_FIELDS, "image": IMAGE_FIELDS, "keypair": KEYPAIR_FIELDS}[family]
    assert "native-secret" not in json.dumps(result)
    assert catalog_runtime.connections == [("project-b", "user-a", "project-a")]
    if family == "flavor":
        assert item["is_gpu"] is False
        assert item["requires_usage_schedule"] is False
    if surface == "mcp":
        assert catalog_runtime.audits[-1][0] == "project-b"
        assert catalog_runtime.audits[-1][1]["status"] == "succeeded"


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["registry", "mcp"])
@pytest.mark.parametrize("name,arguments", CATALOG_ARGUMENTS.items())
async def test_catalog_foreign_project_rejected_before_connection_or_native_read(
    catalog_runtime, surface, name, arguments
):
    with pytest.raises(McpAuthorityError, match="outside the MCP approved scope"):
        await invoke(catalog_runtime, surface, name, {**arguments, "project_id": "foreign-project"})
    assert catalog_runtime.connections == []
    assert catalog_runtime.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["registry", "mcp"])
@pytest.mark.parametrize("family", ["flavor", "image", "keypair"])
async def test_catalog_get_fails_closed_on_foreign_or_unproven_provider_visibility(catalog_runtime, surface, family):
    if family == "flavor":
        catalog_runtime.flavor["is_public"] = False
        catalog_runtime.conn._afterglow_compute_admin = True
    elif family == "image":
        catalog_runtime.image["visibility"] = "private"
    else:
        catalog_runtime.keypair["user_id"] = "foreign-user"
    name = f"afterglow_{family}_get"
    with pytest.raises(ValueError, match=f"^MCP {family} data is unavailable$"):
        await invoke(catalog_runtime, surface, name, CATALOG_ARGUMENTS[name])


@pytest.mark.asyncio
async def test_shared_transport_lists_catalog_as_readonly_compute_without_network_aliases(catalog_runtime):
    token = transport._current_principal.set(catalog_runtime.principal)
    try:
        result = await transport._list_tools(None)
    finally:
        transport._current_principal.reset(token)
    tools = {tool.name: tool for tool in result.tools}
    assert set(CATALOG_ARGUMENTS) <= tools.keys()
    assert {"afterglow_network_list", "afterglow_network_get"} <= tools.keys()
    assert "afterglow_vm_network_attach" not in tools
    for name in CATALOG_ARGUMENTS:
        assert tools[name].annotations.readOnlyHint is True
        assert tools[name].inputSchema["additionalProperties"] is False
        assert "idempotency_key" not in tools[name].inputSchema["properties"]
        entry = registry.entry_by_name(name)
        assert entry.service_flag is None and entry.minimum_scope == "mcp:read"
        assert entry.effect == "read" and entry.preview_builder is None
    registry.validate_registry_inventory(registry.registry_entries())
    capabilities = await invoke(catalog_runtime, "registry", "afterglow_capabilities_get", {})
    assert "compute" in capabilities["enabled_domains"]


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["registry", "mcp"])
async def test_reader_can_discover_network_but_cannot_attach_and_writer_retains_envelope(catalog_runtime, surface):
    listed = await invoke(catalog_runtime, surface, "afterglow_network_list", {"project_id": "project-b"})
    got = await invoke(
        catalog_runtime, surface, "afterglow_network_get", {"project_id": "project-b", "network_id": NETWORK_ID}
    )
    assert listed["networks"] == [got]
    assert got["visibility"] == "owned" and "native-secret" not in json.dumps(got)
    reads = list(catalog_runtime.calls)
    with pytest.raises(ValueError, match="MCP tool is unavailable"):
        await invoke(
            catalog_runtime,
            surface,
            "afterglow_vm_network_attach",
            {
                "project_id": "project-b",
                "server_id": SERVER_ID,
                "network_id": NETWORK_ID,
            },
        )
    assert catalog_runtime.calls == reads
    writer = replace(catalog_runtime.principal, scopes=frozenset({"mcp:read", "mcp:write"}))
    attach = registry.entry_by_name("afterglow_vm_network_attach")
    assert attach.allowed_for(writer)
    assert attach.effect == "external_mutation" and attach.minimum_scope == "mcp:write"
    assert attach.preview_builder is not None
    assert "idempotency_key" in attach.mcp_input_schema()["required"]


@pytest.mark.parametrize(
    "name,invalid",
    [
        ("afterglow_flavor_list", {"limit": 0}),
        ("afterglow_flavor_list", {"limit": 101}),
        ("afterglow_flavor_list", {"limit": True}),
        ("afterglow_flavor_list", {"vcpus": 0}),
        ("afterglow_flavor_list", {"vcpus": "2"}),
        ("afterglow_flavor_list", {"ram_mb": 0}),
        ("afterglow_flavor_list", {"ram_mb": True}),
        ("afterglow_flavor_get", {"flavor_id": "forbidden/id"}),
        ("afterglow_flavor_get", {"flavor_id": " "}),
        ("afterglow_flavor_get", {"flavor_id": "a" * 256}),
        ("afterglow_image_get", {"image_id": "not-a-uuid"}),
        ("afterglow_image_list", {"name": ""}),
        ("afterglow_image_list", {"name": " "}),
        ("afterglow_image_list", {"name": "a" * 256}),
        ("afterglow_keypair_get", {"key_name": ""}),
        ("afterglow_keypair_get", {"key_name": " \t"}),
        ("afterglow_keypair_get", {"key_name": "a" * 256}),
        ("afterglow_keypair_get", {"key_name": "a?user_id=foreign"}),
        ("afterglow_keypair_get", {"key_name": "a/b"}),
        ("afterglow_image_list", {"visibility": "all"}),
    ],
)
def test_catalog_arguments_are_strict(name, invalid):
    entry = registry.entry_by_name(name)
    with pytest.raises(ValidationError):
        registry.parse_entry_arguments(entry, {**CATALOG_ARGUMENTS[name], **invalid})


@pytest.mark.parametrize("name", CATALOG_ARGUMENTS)
@pytest.mark.parametrize("extra", [{"all_projects": True}, {"user_id": "foreign"}, {"admin": True}])
def test_catalog_arguments_reject_authority_expansion(name, extra):
    with pytest.raises(ValidationError):
        registry.parse_entry_arguments(registry.entry_by_name(name), {**CATALOG_ARGUMENTS[name], **extra})


@pytest.mark.parametrize("family", ["flavor", "image", "keypair"])
@pytest.mark.parametrize("invalid", ["", " ", "a" * 256])
def test_catalog_list_markers_are_bounded_and_nonblank(family, invalid):
    entry = registry.entry_by_name(f"afterglow_{family}_list")
    with pytest.raises(ValidationError):
        registry.parse_entry_arguments(entry, {"marker": invalid})


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["registry", "mcp"])
@pytest.mark.parametrize("family", ["flavor", "image"])
async def test_filtered_catalog_page_keeps_raw_scan_marker_without_refilling(catalog_runtime, surface, family):
    filters = {"vcpus": 3} if family == "flavor" else {"name": "Not Ubuntu"}
    result = await invoke(catalog_runtime, surface, f"afterglow_{family}_list", {"limit": 1, **filters})
    collection = "flavors" if family == "flavor" else "images"
    expected_marker = catalog_runtime.flavor["id"] if family == "flavor" else IMAGE_ID
    assert result == {collection: [], "next_marker": expected_marker}
    assert sum(call[0] == collection for call in catalog_runtime.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["registry", "mcp"])
async def test_catalog_checked_usage_schedule_designation_is_projected_without_raw_specs(catalog_runtime, surface):
    catalog_runtime.flavor["extra_specs"] = {
        "afterglow:usage_schedule_required": "true",
        "private:native_token": "native-secret",
    }
    result = await invoke(catalog_runtime, surface, "afterglow_flavor_get", {"flavor_id": "standard.small"})
    assert result["requires_usage_schedule"] is True and result["is_gpu"] is False
    assert set(result) == FLAVOR_FIELDS and "native-secret" not in json.dumps(result)


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["registry", "mcp"])
async def test_network_attach_still_intersects_writer_scope_with_saved_project_management(catalog_runtime, surface):
    catalog_runtime.principal = replace(catalog_runtime.principal, scopes=frozenset({"mcp:read", "mcp:write"}))
    with pytest.raises(McpAuthorityError, match="does not allow management"):
        await invoke(
            catalog_runtime,
            surface,
            "afterglow_vm_network_attach",
            {
                "project_id": "project-b",
                "server_id": SERVER_ID,
                "network_id": NETWORK_ID,
            },
        )
    assert catalog_runtime.connections == [] and catalog_runtime.calls == []
