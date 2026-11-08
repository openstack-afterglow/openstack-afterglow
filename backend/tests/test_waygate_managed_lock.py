"""Waygate gateway VMs and afterglow-waygate-* groups are controllable only through Waygate."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.compute import InstanceInfo
from app.services.waygate_managed import (
    WAYGATE_MANAGED_RESOURCE,
    WaygateManagedResourceError,
    is_waygate_managed_security_group,
    is_waygate_managed_server,
)

PROJECT = "test-project-123"
GATEWAY = {
    "afterglow_managed": "true",
    "waygate_type": "gateway",
    "waygate_server_id": "11111111-1111-4111-8111-111111111111",
    "waygate_create_intent": "22222222-2222-4222-8222-222222222222",
}
BUILDER_ONLY = {"afterglow_managed": "true", "union_type": "ephemeral-builder"}


def _raw(server_id: str, metadata: dict) -> SimpleNamespace:
    return SimpleNamespace(
        id=server_id, name=server_id, project_id=PROJECT, tenant_id=None, status="ACTIVE", metadata=metadata
    )


def _info(server_id: str, metadata: dict) -> InstanceInfo:
    return InstanceInfo(id=server_id, name=server_id, status="ACTIVE", project_id=PROJECT, metadata=metadata)


def _assert_refused(response) -> None:
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == WAYGATE_MANAGED_RESOURCE


@pytest.fixture
def gateway(mock_conn):
    servers = {"gw-1": _raw("gw-1", GATEWAY), "vm-1": _raw("vm-1", {}), "builder-1": _raw("builder-1", BUILDER_ONLY)}
    mock_conn.compute.get_server.side_effect = lambda server_id: servers[server_id]
    with patch(
        "app.api.compute.instances.nova.get_server",
        side_effect=lambda _conn, server_id: _info(server_id, servers[server_id].metadata),
    ):
        yield servers


# ── marker predicates ──


@pytest.mark.parametrize(
    ("metadata", "expected"),
    [
        (GATEWAY, True),
        ({**GATEWAY, "afterglow_managed": "True"}, True),
        ({k: v for k, v in GATEWAY.items() if k != "waygate_create_intent"}, True),
        (BUILDER_ONLY, False),
        ({**GATEWAY, "afterglow_managed": "false"}, False),
        ({**GATEWAY, "waygate_type": "client"}, False),
        ({**GATEWAY, "waygate_server_id": " "}, False),
        ({k: v for k, v in GATEWAY.items() if k != "afterglow_managed"}, False),
        ({}, False),
        (None, False),
    ],
)
def test_gateway_marker_requires_full_waygate_contract(metadata, expected):
    assert is_waygate_managed_server(metadata) is expected


def test_security_group_marker_is_reserved_prefix():
    assert is_waygate_managed_security_group("afterglow-waygate-wireguard")
    assert not is_waygate_managed_security_group("waygate-wireguard")
    assert not is_waygate_managed_security_group(None)


# ── payloads ──


@pytest.mark.asyncio
async def test_instance_list_exposes_waygate_managed_without_marker_parsing(client, mock_conn):
    servers = [_info("gw-1", GATEWAY), _info("builder-1", BUILDER_ONLY), _info("vm-1", {})]
    with (
        patch("app.api.compute.instances.nova.list_servers", return_value=servers),
        patch("app.api.compute.instances.nova.list_flavors", return_value=[]),
        patch("app.api.compute.instances.glance.list_images", return_value=[]),
        patch("app.api.compute.instances.nova.list_volume_attachments", return_value=[]),
        patch("app.api.compute.instances.cached_call", new=lambda _key, _ttl, fn, **_kw: _awaitable(fn())),
    ):
        response = await client.get("/api/v1/instances")
    assert response.status_code == 200
    assert {item["id"]: item["waygate_managed"] for item in response.json()} == {
        "gw-1": True,
        "builder-1": False,
        "vm-1": False,
    }


async def _awaitable(value):
    return value


def test_security_group_dict_exposes_waygate_managed():
    from app.services.neutron import _sg_to_dict

    def group(name):
        return SimpleNamespace(id=name, name=name, description="", security_group_rules=[])

    assert _sg_to_dict(group("afterglow-waygate-wireguard"))["waygate_managed"] is True
    assert _sg_to_dict(group("default"))["waygate_managed"] is False


# ── REST instance routes ──

_NATIVE_MUTATIONS = (
    "app.api.compute.instances.nova.delete_server",
    "app.api.compute.instances.nova.rename_server",
    "app.api.compute.instances.nova.resize_server",
    "app.api.compute.instances.nova.shelve_server",
    "app.api.compute.instances.nova.attach_interface",
    "app.api.compute.instances.nova.detach_interface",
    "app.api.compute.instances.nova.attach_volume",
    "app.api.compute.instances.nova.detach_volume",
    "app.api.compute.instances.nova.update_volume_attachment_delete_flag",
    "app.api.compute.instances.neutron.update_port_security_groups",
    "app.api.compute.instances.neutron.create_floating_ip",
    "app.api.compute.instances.neutron.associate_floating_ip",
    "app.api.compute.instances.neutron.cleanup_instance_fips",
)


@pytest.fixture
def native_mutations():
    mocks = {}
    patches = [patch(target, new=MagicMock(name=target)) for target in _NATIVE_MUTATIONS]
    for target, active in zip(_NATIVE_MUTATIONS, patches, strict=True):
        mocks[target] = active.start()
    try:
        yield mocks
    finally:
        for active in patches:
            active.stop()


def _assert_no_native_mutation(mock_conn, mocks) -> None:
    for target, mock in mocks.items():
        assert mock.call_count == 0, target
    for method in (
        "delete_server",
        "set_server_metadata",
        "delete_server_metadata",
        "create_server_interface",
        "delete_server_interface",
    ):
        assert getattr(mock_conn.compute, method).call_count == 0, method
    for method in ("update_port", "delete_port", "create_ip", "delete_ip", "update_ip"):
        assert getattr(mock_conn.network, method).call_count == 0, method


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("delete", "/api/v1/instances/gw-1", None),
        ("put", "/api/v1/instances/gw-1/name", {"name": "renamed"}),
        ("post", "/api/v1/instances/gw-1/shelve", None),
        ("post", "/api/v1/instances/gw-1/interfaces", {"net_id": "net-1"}),
        ("delete", "/api/v1/instances/gw-1/interfaces/port-1", None),
        ("post", "/api/v1/instances/gw-1/ports/port-1/security-groups", {"security_group_ids": []}),
        ("post", "/api/v1/instances/gw-1/floating-ip", None),
        ("delete", "/api/v1/instances/gw-1/floating-ip", None),
        ("post", "/api/v1/instances/gw-1/volumes", {"volume_id": "vol-1"}),
        ("delete", "/api/v1/instances/gw-1/volumes/boot-vol", None),
        ("patch", "/api/v1/instances/gw-1/volumes/boot-vol", {"delete_on_termination": False}),
        ("post", "/api/v1/instances/gw-1/storage-attachments", {"file_storage_id": "share-1"}),
        ("delete", "/api/v1/instances/gw-1/storage-attachments/share-1", None),
    ],
)
async def test_gateway_instance_mutations_are_refused_before_native_calls(
    client, mock_conn, gateway, native_mutations, method, path, body
):
    with patch("app.services.layer_consume_resources.lookup_for_server", AsyncMock(return_value=[])) as lookup:
        kwargs = {"json": body} if body is not None else {}
        response = await client.request(method.upper(), path, **kwargs)
    _assert_refused(response)
    lookup.assert_not_called()
    _assert_no_native_mutation(mock_conn, native_mutations)


@pytest.mark.asyncio
async def test_gateway_resize_is_refused_before_admission(client, mock_conn, gateway, native_mutations):
    target = AsyncMock(return_value=(_info("gw-1", GATEWAY), [], SimpleNamespace(current=None)))
    with (
        patch("app.api.compute.instances.owned_resize_target", target),
        patch("app.services.flavor_eligibility.require_flavor_eligible", AsyncMock()) as eligible,
    ):
        response = await client.post("/api/v1/instances/gw-1/resize", json={"flavor_id": "f-2"})
    _assert_refused(response)
    eligible.assert_not_called()
    _assert_no_native_mutation(mock_conn, native_mutations)


@pytest.mark.asyncio
async def test_gateway_usage_schedule_edit_refused_but_extension_allowed(client, mock_conn, gateway):
    revision = "0" * 32
    pending = {"status": "pending", "request": {"id": "req-1", "expires_at": "2099-01-01T00:00:00Z"}}
    with (
        patch("app.api.compute.usage_schedules.governance.change_schedule", AsyncMock(return_value=pending)) as change,
        patch("app.api.compute.usage_schedules.usage.require_server_scope"),
    ):
        refused = await client.put(
            "/api/v1/instances/gw-1/usage-schedule",
            json={"expires_at": "2099-01-01T00:00:00Z", "expiry_action": "delete", "revision": revision},
        )
        assert change.call_count == 0
        extended = await client.post(
            "/api/v1/instances/gw-1/usage-schedule/extend",
            json={"expires_at": "2099-01-01T00:00:00Z", "reason": "vpn", "revision": revision},
        )
    _assert_refused(refused)
    assert extended.status_code == 202, extended.text
    assert change.call_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["start", "stop", "reboot"])
async def test_gateway_power_actions_remain_available(client, mock_conn, gateway, action):
    with (
        patch(f"app.api.compute.instances.nova.{action}_server") as native,
        patch("app.api.compute.instances.instance_usage.require_resume_schedule"),
    ):
        response = await client.post(f"/api/v1/instances/gw-1/{action}")
    assert response.status_code == 204, response.text
    native.assert_called_once_with(mock_conn, "gw-1")


@pytest.mark.asyncio
async def test_bulk_delete_reports_gateway_code_and_keeps_other_actions(client, mock_conn, gateway, native_mutations):
    response = await client.post("/api/v1/instances/bulk-action", json={"action": "delete", "instance_ids": ["gw-1"]})
    assert response.status_code == 200
    assert response.json()["results"] == [
        {
            "id": "gw-1",
            "ok": False,
            "error": "This resource is managed by Waygate; change it through Waygate",
            "code": WAYGATE_MANAGED_RESOURCE,
        }
    ]
    _assert_no_native_mutation(mock_conn, native_mutations)
    with patch("app.api.compute.instances.nova.stop_server") as stop:
        stopped = await client.post("/api/v1/instances/bulk-action", json={"action": "stop", "instance_ids": ["gw-1"]})
    assert stopped.json()["results"] == [{"id": "gw-1", "ok": True}]
    stop.assert_called_once_with(mock_conn, "gw-1")


@pytest.mark.asyncio
@pytest.mark.parametrize("instance_id", ["vm-1", "builder-1"])
async def test_non_gateway_instances_are_unaffected(client, mock_conn, gateway, instance_id):
    mock_conn.network.get_port.return_value = SimpleNamespace(
        device_id=instance_id, device_owner="compute:nova", security_group_ids=[]
    )
    with (
        patch("app.api.compute.instances.nova.detach_interface") as detach,
        patch("app.api.compute.instances.nova.shelve_server") as shelve,
        patch("app.api.compute.instances.neutron.update_port_security_groups", return_value={}) as update,
        patch(
            "app.api.compute.instances.nova.rename_server",
            return_value=SimpleNamespace(id=instance_id, project_id=PROJECT, name="renamed"),
        ) as rename,
    ):
        assert (await client.delete(f"/api/v1/instances/{instance_id}/interfaces/port-1")).status_code == 204
        assert (await client.post(f"/api/v1/instances/{instance_id}/shelve")).status_code == 204
        sg = await client.post(
            f"/api/v1/instances/{instance_id}/ports/port-1/security-groups", json={"security_group_ids": ["sg-1"]}
        )
        assert sg.status_code == 200, sg.text
        renamed = await client.put(f"/api/v1/instances/{instance_id}/name", json={"name": "renamed"})
        assert renamed.status_code == 200, renamed.text
    detach.assert_called_once()
    shelve.assert_called_once()
    update.assert_called_once_with(mock_conn, "port-1", ["sg-1"])
    rename.assert_called_once()


@pytest.mark.asyncio
async def test_gateway_port_reached_through_another_instance_path_is_refused(client, mock_conn, gateway):
    mock_conn.network.get_port.return_value = SimpleNamespace(
        device_id="gw-1", device_owner="compute:nova", security_group_ids=["sg-wg"]
    )
    with patch("app.api.compute.instances.neutron.update_port_security_groups") as update:
        response = await client.post(
            "/api/v1/instances/vm-1/ports/port-gw/security-groups", json={"security_group_ids": []}
        )
    _assert_refused(response)
    update.assert_not_called()


@pytest.mark.asyncio
async def test_unbound_waygate_provider_port_cannot_drop_its_group(client, mock_conn, gateway):
    mock_conn.network.get_port.return_value = SimpleNamespace(
        device_id="", device_owner="", security_group_ids=["sg-wg"]
    )
    mock_conn.network.get_security_group.return_value = SimpleNamespace(
        id="sg-wg", name="afterglow-waygate-wireguard", project_id=PROJECT, tenant_id=None
    )
    with patch("app.api.compute.instances.neutron.update_port_security_groups") as update:
        dropped = await client.post(
            "/api/v1/instances/vm-1/ports/port-pending/security-groups", json={"security_group_ids": []}
        )
        kept = await client.post(
            "/api/v1/instances/vm-1/ports/port-pending/security-groups",
            json={"security_group_ids": ["sg-wg", "sg-2"]},
        )
    _assert_refused(dropped)
    assert kept.status_code == 200, kept.text
    update.assert_called_once_with(mock_conn, "port-pending", ["sg-wg", "sg-2"])


@pytest.mark.asyncio
async def test_lock_read_failure_fails_closed(client, mock_conn, gateway):
    mock_conn.compute.get_server.side_effect = RuntimeError("nova unavailable")
    with patch("app.api.compute.instances.nova.detach_interface") as detach:
        response = await client.delete("/api/v1/instances/gw-1/interfaces/port-1")
    assert response.status_code == 503
    detach.assert_not_called()


# ── REST network routes ──


def _waygate_group():
    return SimpleNamespace(id="sg-wg", name="afterglow-waygate-wireguard", project_id=PROJECT, tenant_id=None)


@pytest.mark.asyncio
async def test_waygate_security_group_mutations_are_refused(client, mock_conn):
    mock_conn.network.get_security_group.return_value = _waygate_group()
    mock_conn.network.get_security_group_rule.return_value = SimpleNamespace(
        project_id=PROJECT, tenant_id=None, security_group_id="sg-wg"
    )
    with (
        patch("app.api.network.security_groups.neutron.delete_security_group") as delete_group,
        patch("app.api.network.security_groups.neutron.create_security_group_rule") as create_rule,
        patch("app.api.network.security_groups.neutron.delete_security_group_rule") as delete_rule,
        patch("app.api.network.security_groups.neutron.create_security_group") as create_group,
    ):
        responses = [
            await client.delete("/api/v1/security-groups/sg-wg"),
            await client.post("/api/v1/security-groups/sg-wg/rules", json={"direction": "ingress", "protocol": "tcp"}),
            await client.delete("/api/v1/security-groups/sg-wg/rules/rule-1"),
            await client.post("/api/v1/security-groups", json={"name": "afterglow-waygate-wireguard"}),
        ]
    for response in responses:
        _assert_refused(response)
    for native in (delete_group, create_rule, delete_rule, create_group):
        native.assert_not_called()
    mock_conn.network.get_security_group_rule.assert_not_called()


@pytest.mark.asyncio
async def test_ordinary_security_group_mutations_are_unaffected(client, mock_conn):
    mock_conn.network.get_security_group.return_value = SimpleNamespace(
        id="sg-1", name="web", project_id=PROJECT, tenant_id=None
    )
    with patch("app.api.network.security_groups.neutron.delete_security_group") as delete_group:
        response = await client.delete("/api/v1/security-groups/sg-1")
    assert response.status_code == 204
    delete_group.assert_called_once_with(mock_conn, "sg-1")


@pytest.mark.asyncio
async def test_gateway_floating_ip_cannot_be_moved_or_released(client, mock_conn, gateway):
    mock_conn.network.get_ip.return_value = SimpleNamespace(project_id=PROJECT, tenant_id=None, port_id="port-gw")
    mock_conn.network.get_port.return_value = SimpleNamespace(device_id="gw-1", device_owner="compute:nova")
    with (
        patch("app.api.network.networks.neutron.disassociate_floating_ip") as disassociate,
        patch("app.api.network.networks.neutron.delete_floating_ip") as delete,
        patch("app.api.network.networks.neutron.associate_floating_ip") as associate,
    ):
        responses = [
            await client.post("/api/v1/networks/floating-ips/fip-1/disassociate"),
            await client.delete("/api/v1/networks/floating-ips/fip-1"),
            await client.post("/api/v1/networks/floating-ips/fip-1/associate", json={"instance_id": "vm-1"}),
        ]
        # A free floating IP cannot be associated onto the gateway either.
        mock_conn.network.get_ip.return_value = SimpleNamespace(project_id=PROJECT, tenant_id=None, port_id=None)
        responses.append(
            await client.post("/api/v1/networks/floating-ips/fip-2/associate", json={"instance_id": "gw-1"})
        )
    for response in responses:
        _assert_refused(response)
    for native in (disassociate, delete, associate):
        native.assert_not_called()


@pytest.mark.asyncio
async def test_ordinary_floating_ip_release_is_unaffected(client, mock_conn, gateway):
    mock_conn.network.get_ip.return_value = SimpleNamespace(project_id=PROJECT, tenant_id=None, port_id="port-vm")
    mock_conn.network.get_port.return_value = SimpleNamespace(device_id="vm-1", device_owner="compute:nova")
    with patch("app.api.network.networks.neutron.delete_floating_ip") as delete:
        response = await client.delete("/api/v1/networks/floating-ips/fip-1")
    assert response.status_code == 204
    delete.assert_called_once_with(mock_conn, "fip-1")


# ── MCP control plane ──


def _mcp_conn(metadata: dict):
    calls: list[str] = []
    server = SimpleNamespace(id="server-a", name="gw", status="ACTIVE", project_id="project-a", metadata=metadata)
    compute = SimpleNamespace(
        get_server=lambda _id: server,
        delete_server=lambda *_a, **_k: calls.append("delete"),
        shelve_server=lambda *_a, **_k: calls.append("shelve"),
        stop_server=lambda *_a, **_k: calls.append("stop"),
    )
    return SimpleNamespace(compute=compute), calls


@pytest.mark.asyncio
async def test_mcp_vm_delete_and_shelve_refuse_gateway_with_stable_code():
    from app.services.mcp_control_plane import compute

    conn, calls = _mcp_conn(GATEWAY)
    for operation in (compute.preview_project_server_delete, compute.request_project_server_delete):
        with pytest.raises(WaygateManagedResourceError, match=WAYGATE_MANAGED_RESOURCE):
            await operation(conn, project_id="project-a", server_id="server-a")
    for operation in (compute.preview_project_server_action, compute.request_project_server_action):
        with pytest.raises(WaygateManagedResourceError, match=WAYGATE_MANAGED_RESOURCE):
            await operation(conn, project_id="project-a", server_id="server-a", action="shelve")
    assert calls == []
    await compute.request_project_server_action(conn, project_id="project-a", server_id="server-a", action="stop")
    assert calls == ["stop"]


@pytest.mark.asyncio
async def test_mcp_vm_action_shelve_allowed_for_builder_only_marker():
    from app.services.mcp_control_plane import compute

    conn, calls = _mcp_conn(BUILDER_ONLY)
    await compute.request_project_server_action(conn, project_id="project-a", server_id="server-a", action="shelve")
    assert calls == ["shelve"]


@pytest.mark.asyncio
async def test_mcp_registry_handler_surfaces_code_instead_of_generic_unavailable():
    from app.services.mcp_control_plane import registry

    conn, calls = _mcp_conn(GATEWAY)

    @asynccontextmanager
    async def connection():
        yield conn

    context = SimpleNamespace(project_id="project-a", openstack_connection=connection)
    arguments = registry.VmDeleteArguments.model_validate({"server_id": "11111111-1111-4111-8111-111111111111"})
    conn.compute.get_server = lambda _id: SimpleNamespace(
        id="11111111-1111-4111-8111-111111111111", name="gw", status="ACTIVE", project_id="project-a", metadata=GATEWAY
    )
    for handler in (registry._vm_delete_preview, registry._vm_delete):
        with pytest.raises(WaygateManagedResourceError) as raised:
            await handler(context, arguments)
        assert str(raised.value).startswith(f"{WAYGATE_MANAGED_RESOURCE}: ")
    assert calls == []


@pytest.mark.asyncio
async def test_mcp_interface_and_security_group_tools_refuse_gateway():
    from app.services.mcp_control_plane import instance_management as management
    from tests.test_mcp_instance_management import PORT, PROJECT, SERVER, Cloud

    cloud = Cloud(bound=True)
    cloud.server["metadata"] = dict(GATEWAY)
    target = {"project_id": PROJECT, "server_id": SERVER, "port_id": PORT}
    operations = [
        (management.preview_project_server_interface_detach, target),
        (management.request_project_server_interface_detach, target),
        (management.preview_project_server_interface_attach, target),
        (management.request_project_server_interface_attach, target),
        (management.preview_project_server_security_groups_set, {**target, "security_group_ids": []}),
        (management.request_project_server_security_groups_set, {**target, "security_group_ids": []}),
    ]
    for operation, kwargs in operations:
        with pytest.raises(WaygateManagedResourceError):
            await operation(cloud.conn, **kwargs)
    assert cloud.writes == []


@pytest.mark.asyncio
async def test_mcp_port_update_and_delete_refuse_waygate_ports():
    from app.services.mcp_control_plane import network_management as management
    from tests.test_mcp_network_management import GROUP, PORT, PROJECT, Neutron

    # Unbound provider port still carrying the Waygate group (gateway pending or replaced).
    neutron = Neutron()
    neutron.records["security-groups"][GROUP]["name"] = "afterglow-waygate-wireguard"
    conn = SimpleNamespace(network=neutron)
    for operation, kwargs in (
        (management.preview_project_port_update, {"attributes": {"name": "x"}}),
        (management.request_project_port_update, {"attributes": {"name": "x"}}),
        (management.preview_project_port_delete, {}),
        (management.request_project_port_delete, {}),
    ):
        with pytest.raises(WaygateManagedResourceError):
            await operation(conn, project_id=PROJECT, port_id=PORT, **kwargs)
    assert neutron.writes == []

    # Bound to a gateway VM: the stable code replaces the generic bound-port refusal.
    neutron = Neutron()
    neutron.records["ports"][PORT].update(device_id="gw-vm", device_owner="compute:nova", status="ACTIVE")
    conn = SimpleNamespace(
        network=neutron,
        compute=SimpleNamespace(get_server=lambda _id: SimpleNamespace(id="gw-vm", metadata=dict(GATEWAY))),
    )
    with pytest.raises(WaygateManagedResourceError):
        await management.request_project_port_delete(conn, project_id=PROJECT, port_id=PORT)
    assert neutron.writes == []
