from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.services.mcp_control_plane import instance_management as management
from app.services.mcp_control_plane.network import McpNetworkError

PROJECT = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
FOREIGN = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
SERVER = "11111111-1111-4111-8111-111111111111"
PORT = "22222222-2222-4222-8222-222222222222"
NETWORK = "33333333-3333-4333-8333-333333333333"
GROUP = "44444444-4444-4444-8444-444444444444"
OTHER_GROUP = "55555555-5555-4555-8555-555555555555"
TARGET = {"project_id": PROJECT, "server_id": SERVER, "port_id": PORT}


class Cloud:
    """Stateful provider boundary; writes and post-write uncertainty are observable."""

    def __init__(self, *, bound=False):
        self.calls = []
        self.server = {"id": SERVER, "project_id": PROJECT, "name": "vm", "status": "ACTIVE"}
        self.port = {
            "id": PORT,
            "project_id": PROJECT,
            "network_id": NETWORK,
            "status": "ACTIVE" if bound else "DOWN",
            "device_id": SERVER if bound else "",
            "device_owner": "compute:nova" if bound else "",
            "mac_address": "fa:16:3e:11:22:33",
            "binding_host_id": "host-secret" if bound else "",
            "binding_vif_type": "ovs" if bound else "unbound",
            "security_group_ids": [OTHER_GROUP],
            "is_port_security_enabled": True,
            "revision_number": 7,
            "binding_profile": {},
            "binding_vif_details": {},
        }
        self.network = {"id": NETWORK, "project_id": PROJECT, "status": "ACTIVE", "is_shared": False}
        self.group = {
            "id": GROUP,
            "project_id": PROJECT,
            "name": "web",
            "description": "http",
            "security_group_rules": [{"secret": "never exposed"}],
            "tags": ["secret"],
        }
        self.interface = {"port_id": PORT, "net_id": NETWORK, "mac_addr": "fa:16:3e:11:22:33"}
        self.interfaces = [self.interface] if bound else []
        self.extension = {"alias": "revision-if-match"}
        self.attach_response = None
        self.after_write = None
        self.write_error = None
        self.conn = SimpleNamespace(
            compute=SimpleNamespace(
                get=self.get,
                server_interfaces=self.server_interfaces,
                create_server_interface=self.attach,
                delete_server_interface=self.detach,
            ),
            network=SimpleNamespace(
                get=self.get,
                security_groups=self.security_groups,
                update_port=self.update_port,
                find_extension=self.find_extension,
            ),
        )

    def get(self, path, **options):
        assert options == {
            "redirect": False,
            "allow_reauth": False,
            "raise_exc": False,
            "connect_retries": 0,
            "status_code_retries": 0,
        }
        collection, resource_id = path.strip("/").split("/")
        key, getter = {
            "servers": ("server", self.get_server),
            "ports": ("port", self.get_port),
            "networks": ("network", self.get_network),
            "security-groups": ("security_group", self.get_security_group),
        }[collection]
        body = {key: getter(resource_id)}
        return SimpleNamespace(status_code=200, json=lambda: body)

    def get_server(self, server_id):
        self.calls.append(("server", server_id))
        return deepcopy(self.server)

    def get_port(self, port_id):
        self.calls.append(("port", port_id))
        return deepcopy(self.port)

    def get_network(self, network_id):
        self.calls.append(("network", network_id))
        return deepcopy(self.network)

    def get_security_group(self, security_group_id):
        self.calls.append(("group", security_group_id))
        return deepcopy(self.group)

    def security_groups(self, **query):
        self.calls.append(("groups", query))
        yield deepcopy(self.group)
        raise AssertionError("bounded security-group query read beyond requested limit")

    def server_interfaces(self, server_id):
        self.calls.append(("interfaces", server_id))
        return deepcopy(self.interfaces)

    def find_extension(self, alias, *, ignore_missing):
        self.calls.append(("extension", alias, ignore_missing))
        return deepcopy(self.extension)

    def _after_write(self):
        if self.write_error:
            raise self.write_error
        if self.after_write:
            self.after_write(self)

    def attach(self, server_id, **attrs):
        self.calls.append(("attach", server_id, attrs))
        self.port.update(device_id=SERVER, device_owner="compute:nova", status="ACTIVE", binding_vif_type="ovs")
        self.interfaces = [self.interface]
        self._after_write()
        return deepcopy(self.interface if self.attach_response is None else self.attach_response)

    def detach(self, port_id, server_id, *, ignore_missing):
        self.calls.append(("detach", port_id, server_id, ignore_missing))
        self.interfaces = []
        self._after_write()

    def update_port(self, port_id, *, if_revision, **attrs):
        self.calls.append(("update", port_id, if_revision, attrs))
        if if_revision != self.port["revision_number"]:
            raise RuntimeError("provider revision conflict")
        self.port.update(deepcopy(attrs))
        self.port["revision_number"] += 1
        self._after_write()
        return deepcopy(self.port)

    @property
    def writes(self):
        return [call for call in self.calls if call[0] in {"attach", "detach", "update"}]


@pytest.mark.asyncio
async def test_security_group_reads_are_owned_bounded_and_redacted():
    cloud = Cloud()
    listed = await management.list_project_security_groups(cloud.conn, project_id=PROJECT, limit=1)
    fetched = await management.get_project_security_group(cloud.conn, project_id=PROJECT, security_group_id=GROUP)
    assert listed == [fetched] == [{"id": GROUP, "name": "web", "description": "http"}]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"project_id": FOREIGN},
        {"project_id": None},
        {"tenant_id": FOREIGN},
        {"id": OTHER_GROUP},
    ],
)
async def test_security_group_get_rejects_unproven_identity_or_owner(changes):
    cloud = Cloud()
    cloud.group.update(changes)
    with pytest.raises(McpNetworkError):
        await management.get_project_security_group(cloud.conn, project_id=PROJECT, security_group_id=GROUP)
    assert not cloud.writes


@pytest.mark.asyncio
async def test_security_group_list_rejects_foreign_provider_record_despite_filter():
    cloud = Cloud()
    cloud.group["tenant_id"] = FOREIGN
    with pytest.raises(McpNetworkError, match="ownership"):
        await management.list_project_security_groups(cloud.conn, project_id=PROJECT, limit=1)


@pytest.mark.asyncio
async def test_existing_port_attach_preview_is_readonly_and_request_proves_final_binding():
    cloud = Cloud()
    preview = await management.preview_project_server_interface_attach(cloud.conn, **TARGET)
    assert preview["server_status"] == "ACTIVE"
    assert not cloud.writes
    result = await management.request_project_server_interface_attach(cloud.conn, **TARGET)
    assert cloud.writes == [("attach", SERVER, {"port_id": PORT})]
    assert result == {
        "server_id": SERVER,
        "network_id": NETWORK,
        "port_id": PORT,
        "mac_address": "fa:16:3e:11:22:33",
        "requested_action": "attach_interface",
    }
    assert "host-secret" not in str(result)
    assert cloud.calls.count(("server", SERVER)) == 2
    assert cloud.calls[-1] == ("port", PORT)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["BUILD", "ERROR", "REBUILD", "PAUSED", "DELETED", None])
@pytest.mark.parametrize(
    "operation",
    [
        management.request_project_server_interface_attach,
        management.request_project_server_interface_detach,
        management.request_project_server_security_groups_set,
    ],
)
async def test_interface_mutations_refuse_transitional_or_unknown_servers(status, operation):
    cloud = Cloud(bound=operation is not management.request_project_server_interface_attach)
    cloud.server["status"] = status
    kwargs = {**TARGET}
    if operation is management.request_project_server_security_groups_set:
        kwargs["security_group_ids"] = [GROUP]
    with pytest.raises(McpNetworkError):
        await operation(cloud.conn, **kwargs)
    assert not cloud.writes


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "target,changes",
    [
        ("server", {"project_id": FOREIGN}),
        ("server", {"tenant_id": FOREIGN}),
        ("server", {"id": PORT}),
        ("server", {"task_state": "spawning"}),
        ("port", {"project_id": FOREIGN}),
        ("port", {"tenant_id": FOREIGN}),
        ("port", {"id": SERVER}),
        ("port", {"status": "BUILD"}),
        ("port", {"device_id": SERVER}),
        ("port", {"device_owner": "network:dhcp"}),
        ("port", {"binding_host_id": "host"}),
        ("port", {"binding:host_id": "host"}),
        ("port", {"binding_vif_type": "ovs"}),
        ("port", {"binding_vif_type": "binding_failed"}),
        ("port", {"binding_profile": {"pci_slot": "secret"}}),
        ("port", {"binding_vif_details": {"port_filter": True}}),
        ("port", {"binding_vnic_type": "direct"}),
        ("port", {"binding:vnic_type": "macvtap"}),
        ("port", {"binding_vnic_type": "normal", "binding:vnic_type": "direct"}),
        ("port", {"trunk_details": {"trunk_id": "secret"}}),
        ("network", {"project_id": FOREIGN}),
        ("network", {"project_id": FOREIGN, "is_router_external": True}),
        ("network", {"tenant_id": FOREIGN, "is_shared": True}),
        ("network", {"status": "DOWN"}),
        ("network", {"admin_state_up": False}),
        ("network", {"id": PORT}),
    ],
)
async def test_attach_rejects_foreign_bound_infrastructure_and_unusable_networks(target, changes):
    cloud = Cloud()
    getattr(cloud, target).update(changes)
    with pytest.raises(McpNetworkError):
        await management.request_project_server_interface_attach(cloud.conn, **TARGET)
    assert not cloud.writes


@pytest.mark.asyncio
async def test_attach_accepts_explicit_shared_network_and_shutoff_owned_server():
    cloud = Cloud()
    cloud.server["status"] = "SHUTOFF"
    cloud.network.update(project_id=FOREIGN, tenant_id=FOREIGN, is_shared=True)
    await management.request_project_server_interface_attach(cloud.conn, **TARGET)
    assert len(cloud.writes) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        {},
        {"port_id": OTHER_GROUP, "net_id": NETWORK},
        {"port_id": PORT, "net_id": OTHER_GROUP},
        {"port_id": PORT, "net_id": NETWORK, "network_id": OTHER_GROUP},
        {"port_id": PORT, "net_id": NETWORK, "server_id": PORT},
    ],
)
async def test_attach_ambiguous_provider_result_is_uncertain_without_rollback_or_replay(response):
    cloud = Cloud()
    cloud.attach_response = response
    with pytest.raises(McpNetworkError):
        await management.request_project_server_interface_attach(cloud.conn, **TARGET)
    assert cloud.writes == [("attach", SERVER, {"port_id": PORT})]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"device_id": PORT},
        {"device_owner": "network:router_interface"},
        {"project_id": FOREIGN},
        {"network_id": GROUP},
        {"binding_vif_type": "binding_failed"},
    ],
)
async def test_attach_requires_final_owned_neutron_compute_binding(changes):
    cloud = Cloud()
    cloud.after_write = lambda state: state.port.update(changes)
    with pytest.raises(McpNetworkError):
        await management.request_project_server_interface_attach(cloud.conn, **TARGET)
    assert len(cloud.writes) == 1


@pytest.mark.asyncio
async def test_request_revalidates_preview_instead_of_reusing_stale_binding():
    cloud = Cloud()
    await management.preview_project_server_interface_attach(cloud.conn, **TARGET)
    cloud.port.update(device_owner="network:dhcp", device_id="dhcp-agent")
    with pytest.raises(McpNetworkError):
        await management.request_project_server_interface_attach(cloud.conn, **TARGET)
    assert not cloud.writes


@pytest.mark.asyncio
async def test_detach_corroborates_nova_interface_and_uses_correct_native_argument_order_only():
    cloud = Cloud(bound=True)
    preview = await management.preview_project_server_interface_detach(cloud.conn, **TARGET)
    assert not cloud.writes
    assert preview["server_status"] == "ACTIVE"
    result = await management.request_project_server_interface_detach(cloud.conn, **TARGET)
    assert cloud.writes == [("detach", PORT, SERVER, False)]
    assert result == {
        "server_id": SERVER,
        "network_id": NETWORK,
        "port_id": PORT,
        "mac_address": "fa:16:3e:11:22:33",
        "requested_action": "detach_interface",
    }
    assert not hasattr(cloud.conn.network, "delete_port")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"device_id": GROUP},
        {"device_owner": "network:dhcp"},
        {"device_owner": "network:router_interface"},
        {"device_owner": "compute:"},
        {"device_owner": None},
        {"project_id": FOREIGN},
        {"binding_vif_type": "unbound"},
    ],
)
async def test_detach_rejects_foreign_and_noncompute_binding(changes):
    cloud = Cloud(bound=True)
    cloud.port.update(changes)
    with pytest.raises(McpNetworkError):
        await management.request_project_server_interface_detach(cloud.conn, **TARGET)
    assert not cloud.writes


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "interfaces",
    [
        [],
        [{"port_id": PORT}],
        [{"port_id": PORT, "net_id": GROUP}],
        [{"port_id": GROUP, "net_id": NETWORK}],
        [{"port_id": PORT, "net_id": NETWORK}, {"port_id": PORT, "net_id": NETWORK}],
    ],
)
async def test_detach_requires_exact_unambiguous_nova_interface(interfaces):
    cloud = Cloud(bound=True)
    cloud.interfaces = interfaces
    with pytest.raises(McpNetworkError):
        await management.request_project_server_interface_detach(cloud.conn, **TARGET)
    assert not cloud.writes


@pytest.mark.asyncio
@pytest.mark.parametrize("desired", [[GROUP], []])
async def test_group_replacement_is_exact_revision_cas_preserving_security_and_empty_semantics(desired):
    cloud = Cloud(bound=True)
    preview = await management.preview_project_server_security_groups_set(
        cloud.conn, **TARGET, security_group_ids=desired
    )
    assert not cloud.writes
    assert preview["current_security_group_ids"] == [OTHER_GROUP]
    assert preview["security_group_ids"] == desired
    result = await management.request_project_server_security_groups_set(
        cloud.conn, **TARGET, security_group_ids=desired
    )
    assert cloud.writes == [("update", PORT, 7, {"security_group_ids": desired})]
    assert result == {
        "server_id": SERVER,
        "port_id": PORT,
        "security_group_ids": desired,
        "requested_action": "set_security_groups",
    }
    assert cloud.port["is_port_security_enabled"] is True
    assert ("extension", "revision-if-match", True) in cloud.calls
    assert ("group", GROUP) in cloud.calls if desired else not any(call[0] == "group" for call in cloud.calls)


@pytest.mark.asyncio
@pytest.mark.parametrize("groups", [[GROUP, GROUP], ["not-uuid"], [GROUP] * 33, None, "", [None], [1]])
async def test_group_replacement_rejects_invalid_internal_inputs_before_native_write(groups):
    cloud = Cloud(bound=True)
    with pytest.raises(McpNetworkError):
        await management.request_project_server_security_groups_set(cloud.conn, **TARGET, security_group_ids=groups)
    assert not cloud.writes


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"project_id": FOREIGN},
        {"tenant_id": FOREIGN},
        {"id": OTHER_GROUP},
    ],
)
async def test_group_replacement_requires_exact_owned_referenced_groups(changes):
    cloud = Cloud(bound=True)
    cloud.group.update(changes)
    with pytest.raises(McpNetworkError):
        await management.request_project_server_security_groups_set(cloud.conn, **TARGET, security_group_ids=[GROUP])
    assert not cloud.writes


@pytest.mark.asyncio
@pytest.mark.parametrize("revision", [None, True, "7", 7.0, -1])
async def test_group_replacement_requires_actual_integer_revision(revision):
    cloud = Cloud(bound=True)
    cloud.port["revision_number"] = revision
    with pytest.raises(McpNetworkError, match="revision"):
        await management.request_project_server_security_groups_set(cloud.conn, **TARGET, security_group_ids=[])
    assert not cloud.writes


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["server", "port", "network", "group"])
async def test_original_provider_json_requires_id_not_sdk_request_seed(target):
    cloud = Cloud(bound=target == "group")
    getattr(cloud, target).pop("id")
    with pytest.raises(McpNetworkError, match="missing|identity"):
        if target == "group":
            await management.request_project_server_security_groups_set(
                cloud.conn, **TARGET, security_group_ids=[GROUP]
            )
        else:
            await management.request_project_server_interface_attach(cloud.conn, **TARGET)
    assert not cloud.writes


@pytest.mark.asyncio
@pytest.mark.parametrize("extension", [None, {}, {"alias": "standard-attr-revisions"}])
async def test_group_replacement_refuses_missing_revision_if_match_extension(extension):
    cloud = Cloud(bound=True)
    cloud.extension = extension
    with pytest.raises(McpNetworkError, match="revision-if-match"):
        await management.preview_project_server_security_groups_set(cloud.conn, **TARGET, security_group_ids=[])
    with pytest.raises(McpNetworkError, match="revision-if-match"):
        await management.request_project_server_security_groups_set(cloud.conn, **TARGET, security_group_ids=[])
    assert not cloud.writes


@pytest.mark.asyncio
async def test_group_revision_conflict_is_never_replayed():
    cloud = Cloud(bound=True)
    original = cloud.get_security_group

    def concurrent_group_read(group_id):
        cloud.port["revision_number"] += 1
        return original(group_id)

    cloud.get_security_group = concurrent_group_read
    with pytest.raises(McpNetworkError):
        await management.request_project_server_security_groups_set(cloud.conn, **TARGET, security_group_ids=[GROUP])
    assert cloud.writes == [("update", PORT, 7, {"security_group_ids": [GROUP]})]
    assert cloud.port["security_group_ids"] == [OTHER_GROUP]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"security_group_ids": [OTHER_GROUP]},
        {"is_port_security_enabled": False},
        {"device_id": PORT},
        {"tenant_id": FOREIGN},
        {"network_id": GROUP},
    ],
)
async def test_group_postwrite_ownership_binding_exact_groups_and_security_are_required(changes):
    cloud = Cloud(bound=True)
    cloud.after_write = lambda state: state.port.update(changes)
    with pytest.raises(McpNetworkError):
        await management.request_project_server_security_groups_set(cloud.conn, **TARGET, security_group_ids=[GROUP])
    assert len(cloud.writes) == 1


@pytest.mark.asyncio
async def test_missing_provider_port_security_setting_does_not_use_sdk_default_false():
    cloud = Cloud(bound=True)
    cloud.port.pop("is_port_security_enabled")
    with pytest.raises(McpNetworkError, match="Port security"):
        await management.request_project_server_security_groups_set(cloud.conn, **TARGET, security_group_ids=[])
    assert not cloud.writes


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operation",
    [
        management.request_project_server_interface_attach,
        management.request_project_server_interface_detach,
        management.request_project_server_security_groups_set,
    ],
)
async def test_final_dispatch_fence_runs_after_reads_immediately_before_native_write(monkeypatch, operation):
    cloud = Cloud(bound=operation is not management.request_project_server_interface_attach)
    kwargs = {**TARGET}
    if operation is management.request_project_server_security_groups_set:
        kwargs["security_group_ids"] = [GROUP]

    def expired():
        assert cloud.calls
        assert not cloud.writes
        raise ValueError("expired")

    monkeypatch.setattr(management, "check_mutation_dispatch", expired)
    with pytest.raises(McpNetworkError):
        await operation(cloud.conn, **kwargs)
    assert not cloud.writes


@pytest.mark.asyncio
async def test_provider_write_failure_is_generic_redacted_and_never_replayed():
    cloud = Cloud()
    cloud.write_error = RuntimeError("token-and-host-secret")
    with pytest.raises(McpNetworkError) as error:
        await management.request_project_server_interface_attach(cloud.conn, **TARGET)
    assert "token-and-host-secret" not in str(error.value)
    assert cloud.writes == [("attach", SERVER, {"port_id": PORT})]


@pytest.mark.asyncio
async def test_attach_requires_unseeded_postwrite_nova_interface_even_with_valid_sdk_response():
    cloud = Cloud()
    cloud.after_write = lambda state: setattr(state, "interfaces", [])
    with pytest.raises(McpNetworkError, match="interface"):
        await management.request_project_server_interface_attach(cloud.conn, **TARGET)
    assert cloud.writes == [("attach", SERVER, {"port_id": PORT})]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"device_id": None},
        {"device_owner": None},
        {"binding:profile": {"pci_slot": "secret"}},
    ],
)
async def test_attach_requires_positive_unbound_device_proof(changes):
    cloud = Cloud()
    cloud.port.update(changes)
    with pytest.raises(McpNetworkError):
        await management.request_project_server_interface_attach(cloud.conn, **TARGET)
    assert not cloud.writes


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"is_shared": True, "shared": False},
        {"is_shared": "true"},
        {"is_admin_state_up": True, "admin_state_up": False},
        {"admin_state_up": "true"},
    ],
)
async def test_attach_rejects_malformed_or_contradictory_network_flags(changes):
    cloud = Cloud()
    cloud.network.update(changes)
    with pytest.raises(McpNetworkError):
        await management.request_project_server_interface_attach(cloud.conn, **TARGET)
    assert not cloud.writes


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"project_id": FOREIGN},
        {"device_id": PORT},
        {"device_owner": "network:router_interface"},
        {"security_group_ids": None},
        {"security_group_ids": [GROUP], "security_groups": []},
        {"is_port_security_enabled": True, "port_security_enabled": False},
        {"is_port_security_enabled": "true"},
    ],
)
async def test_group_set_requires_owned_compute_binding_and_unambiguous_current_state(changes):
    cloud = Cloud(bound=True)
    cloud.port.update(changes)
    with pytest.raises(McpNetworkError):
        await management.request_project_server_security_groups_set(cloud.conn, **TARGET, security_group_ids=[GROUP])
    assert not cloud.writes


@pytest.mark.asyncio
async def test_group_set_never_enables_port_security_while_removing_existing_groups():
    cloud = Cloud(bound=True)
    cloud.port["is_port_security_enabled"] = False
    result = await management.request_project_server_security_groups_set(cloud.conn, **TARGET, security_group_ids=[])
    assert result["security_group_ids"] == []
    assert cloud.port["is_port_security_enabled"] is False
    assert cloud.writes == [("update", PORT, 7, {"security_group_ids": []})]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [302, 401, 404, 500, "200", True])
async def test_raw_provider_fetch_requires_exact_success_without_redirect_or_reauth(status):
    cloud = Cloud()
    cloud.conn.compute.get = lambda *args, **kwargs: SimpleNamespace(
        status_code=status, json=lambda: {"server": cloud.server}
    )
    with pytest.raises(McpNetworkError):
        await management.request_project_server_interface_attach(cloud.conn, **TARGET)
    assert not cloud.writes


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [None, [], {}, {"server": None}, {"server": []}])
async def test_raw_provider_fetch_rejects_malformed_original_envelope(body):
    cloud = Cloud()
    cloud.conn.compute.get = lambda *args, **kwargs: SimpleNamespace(status_code=200, json=lambda: body)
    with pytest.raises(McpNetworkError):
        await management.request_project_server_interface_attach(cloud.conn, **TARGET)
    assert not cloud.writes
