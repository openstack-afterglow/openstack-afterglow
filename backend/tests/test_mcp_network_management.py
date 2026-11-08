from __future__ import annotations

import asyncio
import copy
import threading
from types import SimpleNamespace

import pytest
from openstack.network.v2.port import Port

from app.services.mcp_control_plane import network_management as management
from app.services.mcp_control_plane import sdk
from app.services.mcp_control_plane.network import McpNetworkError

PROJECT = "10000000-0000-0000-0000-000000000001"
FOREIGN = "10000000-0000-0000-0000-000000000002"
NETWORK = "20000000-0000-0000-0000-000000000001"
SUBNET = "30000000-0000-0000-0000-000000000001"
PORT = "40000000-0000-0000-0000-000000000001"
GROUP = "50000000-0000-0000-0000-000000000001"
OTHER = "60000000-0000-0000-0000-000000000001"


class Neutron:
    def __init__(self):
        self.records = {
            "networks": {
                NETWORK: {
                    "id": NETWORK,
                    "project_id": PROJECT,
                    "name": "tenant",
                    "status": "ACTIVE",
                    "shared": False,
                    "router:external": False,
                    "admin_state_up": True,
                    "revision_number": 7,
                },
            },
            "subnets": {
                SUBNET: {
                    "id": SUBNET,
                    "project_id": PROJECT,
                    "name": "v4",
                    "network_id": NETWORK,
                    "cidr": "192.0.2.0/24",
                    "ip_version": 4,
                    "gateway_ip": "192.0.2.1",
                    "enable_dhcp": True,
                    "dns_nameservers": ["192.0.2.53"],
                    "revision_number": 9,
                },
            },
            "ports": {
                PORT: {
                    "id": PORT,
                    "project_id": PROJECT,
                    "name": "free",
                    "description": "ordinary",
                    "network_id": NETWORK,
                    "status": "DOWN",
                    "admin_state_up": True,
                    "mac_address": "fa:16:3e:00:00:01",
                    "device_id": "",
                    "device_owner": "",
                    "fixed_ips": [{"subnet_id": SUBNET, "ip_address": "192.0.2.20"}],
                    "security_groups": [GROUP],
                    "binding:host_id": "",
                    "binding:vif_type": "unbound",
                    "binding:profile": {},
                    "binding:vif_details": {},
                    "revision_number": 11,
                },
            },
            "security-groups": {GROUP: {"id": GROUP, "project_id": PROJECT, "name": "default"}},
        }
        self.reads = []
        self.writes = []
        self.list_queries = []
        self.extension = {"alias": "revision-if-match"}
        self.before_write = None
        self.after_write = None

    def get(self, path, **kwargs):
        self.reads.append((path, kwargs))
        collection, resource_id = path.strip("/").split("/")
        singular = {"networks": "network", "subnets": "subnet", "ports": "port", "security-groups": "security_group"}[
            collection
        ]
        resource = self.records[collection].get(resource_id)
        return SimpleNamespace(
            status_code=200 if resource is not None else 404, json=lambda: {singular: copy.deepcopy(resource)}
        )

    def find_extension(self, alias, *, ignore_missing):
        assert alias == "revision-if-match" and ignore_missing is True
        return self.extension

    def ports(self, **query):
        self.list_queries.append(query)
        return iter(copy.deepcopy(list(self.records["ports"].values())))

    @staticmethod
    def _json(attrs):
        aliases = {
            "is_shared": "shared",
            "is_router_external": "router:external",
            "is_admin_state_up": "admin_state_up",
            "is_dhcp_enabled": "enable_dhcp",
            "security_group_ids": "security_groups",
        }
        return {aliases.get(key, key): copy.deepcopy(value) for key, value in attrs.items()}

    def _create(self, collection, resource_id, attrs):
        self.writes.append(("create", collection, attrs))
        record = self.records[collection][resource_id]
        record.update(self._json(attrs))
        if self.after_write:
            self.after_write(record)
        return copy.deepcopy(record)

    def _update(self, collection, resource_id, revision, attrs):
        record = self.records[collection][resource_id]
        if self.before_write:
            self.before_write(record)
        if record["revision_number"] != revision:
            raise RuntimeError("provider HTTP 412: revision changed")
        self.writes.append(("update", collection, resource_id, revision, attrs))
        record.update(self._json(attrs))
        record["revision_number"] += 1
        if self.after_write:
            self.after_write(record)
        return copy.deepcopy(record)

    def create_network(self, **attrs):
        return self._create("networks", NETWORK, attrs)

    def update_network(self, resource_id, *, if_revision, **attrs):
        return self._update("networks", resource_id, if_revision, attrs)

    def create_subnet(self, **attrs):
        return self._create("subnets", SUBNET, attrs)

    def update_subnet(self, resource_id, *, if_revision, **attrs):
        return self._update("subnets", resource_id, if_revision, attrs)

    def create_port(self, **attrs):
        return self._create("ports", PORT, attrs)

    def update_port(self, resource_id, *, if_revision, **attrs):
        return self._update("ports", resource_id, if_revision, attrs)

    def delete_port(self, resource_id, *, if_revision, ignore_missing):
        assert ignore_missing is False
        record = self.records["ports"][resource_id]
        if self.before_write:
            self.before_write(record)
        if record["revision_number"] != if_revision:
            raise RuntimeError("provider HTTP 412: revision changed")
        self.writes.append(("delete", "ports", resource_id, if_revision))
        del self.records["ports"][resource_id]


@pytest.fixture
def conn():
    # The real consumer connection always carries the project's domain (VPN reserved ranges).
    return SimpleNamespace(network=Neutron(), _afterglow_domain_id="domain-a")


@pytest.mark.asyncio
async def test_owned_network_create_and_update_use_fixed_tenant_and_conditional_native_write(conn):
    attrs = {"name": "new tenant", "description": "safe", "admin_state_up": False}
    preview = await management.preview_project_network_create(conn, project_id=PROJECT, attributes=attrs)
    assert preview["attributes"] == attrs
    assert conn.network.writes == []
    created = await management.request_project_network_create(conn, project_id=PROJECT, attributes=attrs)
    assert created["id"] == NETWORK and created["requested_action"] == "create"
    assert conn.network.writes[0] == (
        "create",
        "networks",
        {
            "project_id": PROJECT,
            "is_shared": False,
            "is_router_external": False,
            "name": "new tenant",
            "description": "safe",
            "is_admin_state_up": False,
        },
    )
    await management.preview_project_network_update(
        conn, project_id=PROJECT, network_id=NETWORK, attributes={"name": "renamed"}
    )
    updated = await management.request_project_network_update(
        conn, project_id=PROJECT, network_id=NETWORK, attributes={"name": "renamed"}
    )
    assert updated["name"] == "renamed"
    assert conn.network.writes[-1] == ("update", "networks", NETWORK, 7, {"name": "renamed"})
    for _, options in conn.network.reads:
        assert options == {
            "redirect": False,
            "allow_reauth": False,
            "raise_exc": False,
            "connect_retries": 0,
            "status_code_retries": 0,
        }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"project_id": FOREIGN},
        {"tenant_id": FOREIGN},
        {"shared": True},
        {"router:external": True},
        {"status": "BUILD"},
        {"status": None},
        {"id": OTHER},
        {"shared": None},
        {"revision_number": True},
    ],
)
async def test_network_update_rejects_unsafe_owner_visibility_state_identity_or_revision(conn, changes):
    conn.network.records["networks"][NETWORK].update(changes)
    with pytest.raises(McpNetworkError):
        await management.request_project_network_update(
            conn, project_id=PROJECT, network_id=NETWORK, attributes={"name": "changed"}
        )
    assert conn.network.writes == []


@pytest.mark.asyncio
@pytest.mark.parametrize("extension", [None, {"alias": "standard-attr-revisions"}, {}])
async def test_mutations_require_advertised_revision_if_match_not_just_revision_number(conn, extension):
    conn.network.extension = extension
    with pytest.raises(McpNetworkError, match="precondition"):
        await management.request_project_port_delete(conn, project_id=PROJECT, port_id=PORT)
    assert conn.network.writes == []


@pytest.mark.asyncio
async def test_subnet_create_derives_ip_version_and_preserves_explicit_no_gateway(conn):
    attrs = {
        "network_id": NETWORK,
        "name": "new subnet",
        "cidr": "192.0.2.0/24",
        "gateway_ip": None,
        "enable_dhcp": False,
        "dns_nameservers": [],
    }
    preview = await management.preview_project_subnet_create(conn, project_id=PROJECT, attributes=attrs)
    assert preview["attributes"]["gateway_ip"] is None and conn.network.writes == []
    result = await management.request_project_subnet_create(conn, project_id=PROJECT, attributes=attrs)
    assert result["ip_version"] == 4 and result["gateway_ip"] is None
    payload = conn.network.writes[-1][-1]
    assert payload["ip_version"] == 4 and payload["project_id"] == PROJECT
    assert payload["is_dhcp_enabled"] is False and payload["dns_nameservers"] == []
    assert payload["gateway_ip"] is None


@pytest.mark.asyncio
async def test_subnet_update_omission_preserves_gateway_but_null_removes_it(conn):
    preview = await management.preview_project_subnet_update(
        conn, project_id=PROJECT, subnet_id=SUBNET, attributes={"name": "renamed"}
    )
    assert "gateway_ip" not in preview["attributes"]
    result = await management.request_project_subnet_update(
        conn, project_id=PROJECT, subnet_id=SUBNET, attributes={"name": "renamed"}
    )
    assert result["gateway_ip"] == "192.0.2.1"
    result = await management.request_project_subnet_update(
        conn, project_id=PROJECT, subnet_id=SUBNET, attributes={"gateway_ip": None}
    )
    assert result["gateway_ip"] is None
    assert conn.network.writes[-1] == ("update", "subnets", SUBNET, 10, {"gateway_ip": None})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "patch",
    [
        {"cidr": "192.0.2.5/24"},
        {"cidr": "192.0.2.0/24", "gateway_ip": "198.51.100.1"},
        {"gateway_ip": "2001:db8::1"},
        {"dns_nameservers": ["2001:db8::53"]},
        {"dns_nameservers": ["invalid"]},
        {"enable_dhcp": 1},
        {"gateway_ip": "bad"},
        {"project_id": FOREIGN},
    ],
)
async def test_subnet_create_denies_invalid_network_addresses_and_internal_attribute_bypass(conn, patch):
    attrs = {"network_id": NETWORK, "name": "new", "cidr": "192.0.2.0/24", **patch}
    with pytest.raises(McpNetworkError):
        await management.request_project_subnet_create(conn, project_id=PROJECT, attributes=attrs)
    assert conn.network.writes == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "patch", [{"cidr": "198.51.100.0/24"}, {"network_id": OTHER}, {"description": None}, {}, {"enable_dhcp": None}]
)
async def test_subnet_update_denies_parent_cidr_and_null_or_empty_patch(conn, patch):
    with pytest.raises(McpNetworkError):
        await management.request_project_subnet_update(conn, project_id=PROJECT, subnet_id=SUBNET, attributes=patch)
    assert conn.network.writes == []


@pytest.mark.asyncio
async def test_port_owned_create_update_list_get_delete_are_redacted_and_conditional(conn):
    attrs = {
        "network_id": NETWORK,
        "name": "created",
        "fixed_ips": [{"subnet_id": SUBNET, "ip_address": "192.0.2.20"}],
        "security_group_ids": [GROUP],
    }
    preview = await management.preview_project_port_create(conn, project_id=PROJECT, attributes=attrs)
    assert preview["attributes"] == attrs and conn.network.writes == []
    created = await management.request_project_port_create(conn, project_id=PROJECT, attributes=attrs)
    assert created["requested_action"] == "create" and created["security_group_ids"] == [GROUP]
    assert not any("binding" in key or key == "project_id" for key in created)
    await management.preview_project_port_update(
        conn, project_id=PROJECT, port_id=PORT, attributes={"security_group_ids": [], "fixed_ips": []}
    )
    updated = await management.request_project_port_update(
        conn, project_id=PROJECT, port_id=PORT, attributes={"security_group_ids": [], "fixed_ips": []}
    )
    assert updated["security_group_ids"] == [] and updated["fixed_ips"] == []
    assert conn.network.writes[-1] == ("update", "ports", PORT, 11, {"security_group_ids": [], "fixed_ips": []})
    listed = await management.list_project_ports(conn, project_id=PROJECT, limit=1, network_id=NETWORK)
    fetched = await management.get_project_port(conn, project_id=PROJECT, port_id=PORT)
    assert listed == [fetched]
    await management.preview_project_port_delete(conn, project_id=PROJECT, port_id=PORT)
    deleted = await management.request_project_port_delete(conn, project_id=PROJECT, port_id=PORT)
    assert deleted["requested_action"] == "delete"
    assert conn.network.writes[-1] == ("delete", "ports", PORT, 12)


@pytest.mark.asyncio
async def test_shared_network_allows_legitimate_provider_owned_subnet_but_not_foreign_subnet(conn):
    parent = conn.network.records["networks"][NETWORK]
    parent.update(project_id=FOREIGN, shared=True)
    conn.network.records["subnets"][SUBNET]["project_id"] = FOREIGN
    result = await management.preview_project_port_create(
        conn, project_id=PROJECT, attributes={"network_id": NETWORK, "fixed_ips": [{"subnet_id": SUBNET}]}
    )
    assert result["network_id"] == NETWORK
    conn.network.records["subnets"][SUBNET]["project_id"] = OTHER
    with pytest.raises(McpNetworkError, match="ownership"):
        await management.request_project_port_create(
            conn, project_id=PROJECT, attributes={"network_id": NETWORK, "fixed_ips": [{"subnet_id": SUBNET}]}
        )
    assert conn.network.writes == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"project_id": FOREIGN, "shared": False},
        {"project_id": FOREIGN, "shared": False, "router:external": True},
        {"status": "DOWN"},
        {"admin_state_up": False},
        {"admin_state_up": None},
    ],
)
async def test_port_create_requires_attachment_authority_not_external_visibility(conn, changes):
    conn.network.records["networks"][NETWORK].update(changes)
    with pytest.raises(McpNetworkError):
        await management.request_project_port_create(conn, project_id=PROJECT, attributes={"network_id": NETWORK})
    assert conn.network.writes == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"device_id": OTHER, "device_owner": "compute:nova"},
        {"device_owner": "network:dhcp"},
        {"device_owner": "network:router_interface"},
        {"device_id": None},
        {"device_owner": None},
        {"binding:host_id": "compute-1"},
        {"binding:vif_type": "ovs"},
        {"binding:vif_type": "binding_failed"},
        {"binding:profile": {"pci_slot": "00:01"}},
        {"binding:vif_details": {"port_filter": True}},
        {"trunk_details": {"trunk_id": OTHER}},
        {"status": "BUILD"},
        {"project_id": FOREIGN},
        {"tenant_id": FOREIGN},
    ],
)
@pytest.mark.parametrize("action", ["update", "delete"])
async def test_port_mutations_reject_bound_infrastructure_foreign_and_unknown_ports(conn, changes, action):
    conn.network.records["ports"][PORT].update(changes)
    kwargs = {"attributes": {"name": "updated"}} if action == "update" else {}
    with pytest.raises(McpNetworkError):
        await getattr(management, f"request_project_port_{action}")(conn, project_id=PROJECT, port_id=PORT, **kwargs)
    assert conn.network.writes == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "attrs",
    [
        {"fixed_ips": [{"subnet_id": SUBNET, "ip_address": "198.51.100.20"}]},
        {"fixed_ips": [{"subnet_id": SUBNET, "ip_address": "2001:db8::20"}]},
        {"fixed_ips": [{"subnet_id": SUBNET, "ip_address": None}]},
        {"fixed_ips": [{"subnet_id": SUBNET, "device_id": OTHER}]},
        {"security_group_ids": [GROUP, GROUP]},
        {"security_group_ids": None},
        {"fixed_ips": None},
        {"admin_state_up": 1},
        {"device_id": OTHER},
        {"binding:host_id": "compute-1"},
        {"mac_address": "fa:16:3e:00:00:02"},
        {"port_security_enabled": False},
        {"name": None},
        {},
    ],
)
async def test_port_update_independently_rejects_unsupported_and_invalid_attributes(conn, attrs):
    with pytest.raises(McpNetworkError):
        await management.request_project_port_update(conn, project_id=PROJECT, port_id=PORT, attributes=attrs)
    assert conn.network.writes == []


@pytest.mark.asyncio
async def test_port_create_denies_foreign_group_and_mismatched_fixed_subnet(conn):
    conn.network.records["security-groups"][GROUP]["project_id"] = FOREIGN
    with pytest.raises(McpNetworkError, match="ownership"):
        await management.request_project_port_create(
            conn, project_id=PROJECT, attributes={"network_id": NETWORK, "security_group_ids": [GROUP]}
        )
    conn.network.records["subnets"][SUBNET]["network_id"] = OTHER
    with pytest.raises(McpNetworkError):
        await management.request_project_port_create(
            conn, project_id=PROJECT, attributes={"network_id": NETWORK, "fixed_ips": [{"subnet_id": SUBNET}]}
        )
    assert conn.network.writes == []


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["network", "subnet", "port"])
async def test_request_revalidates_owner_after_readonly_preview(conn, kind):
    resource_id = {"network": NETWORK, "subnet": SUBNET, "port": PORT}[kind]
    kwargs = {f"{kind}_id": resource_id, "attributes": {"name": "new"}}
    await getattr(management, f"preview_project_{kind}_update")(conn, project_id=PROJECT, **kwargs)
    conn.network.records[f"{kind}s"][resource_id]["project_id"] = FOREIGN
    with pytest.raises(McpNetworkError):
        await getattr(management, f"request_project_{kind}_update")(conn, project_id=PROJECT, **kwargs)
    assert conn.network.writes == []


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["update", "delete"])
async def test_port_revision_change_between_read_and_dispatch_denies_without_retry(conn, action):
    def bind_port(record):
        record.update(device_id=OTHER, device_owner="compute:nova", revision_number=record["revision_number"] + 1)

    conn.network.before_write = bind_port
    kwargs = {"attributes": {"name": "updated"}} if action == "update" else {}
    with pytest.raises(McpNetworkError, match="unavailable"):
        await getattr(management, f"request_project_port_{action}")(conn, project_id=PROJECT, port_id=PORT, **kwargs)
    assert conn.network.writes == []


@pytest.mark.asyncio
async def test_post_write_wrong_owner_raises_uncertainty_without_rollback_or_retry(conn):
    conn.network.after_write = lambda record: record.update(project_id=FOREIGN)
    with pytest.raises(McpNetworkError, match="ownership"):
        await management.request_project_network_create(conn, project_id=PROJECT, attributes={"name": "created"})
    assert len(conn.network.writes) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["id", "project_id"])
async def test_original_provider_json_missing_identity_is_not_repaired_by_sdk_seed(conn, missing):
    del conn.network.records["ports"][PORT][missing]
    with pytest.raises(McpNetworkError):
        await management.get_project_port(conn, project_id=PROJECT, port_id=PORT)


@pytest.mark.asyncio
async def test_sdk_descriptor_default_does_not_prove_port_admin_state(conn):
    raw = copy.deepcopy(conn.network.records["ports"][PORT])
    del raw["admin_state_up"]
    resource = Port(**raw)
    conn.network.ports = lambda **kwargs: iter([resource])
    with pytest.raises(McpNetworkError, match="administrative"):
        await management.list_project_ports(conn, project_id=PROJECT, limit=1)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_patch",
    [
        {"project_id": FOREIGN},
        {"is_shared": True},
        {"router:external": True},
        {"admin_state_up": None},
        {"name": None},
        {"description": "x" * 1025},
        {},
    ],
)
async def test_network_create_validates_internal_callers_not_only_registry(conn, bad_patch):
    attrs = {"name": "new", **bad_patch} if bad_patch else {}
    with pytest.raises(McpNetworkError):
        await management.request_project_network_create(conn, project_id=PROJECT, attributes=attrs)
    assert conn.network.writes == []


@pytest.mark.asyncio
async def test_cancellation_during_ownership_reads_drains_worker_and_fences_native_write(conn):
    entered = threading.Event()
    release = threading.Event()
    settled = threading.Event()
    original = conn.network.get

    def blocking_get(path, **kwargs):
        if path == f"/ports/{PORT}":
            entered.set()
            release.wait(5)
            settled.set()
        return original(path, **kwargs)

    conn.network.get = blocking_get
    task = asyncio.create_task(management.request_project_port_delete(conn, project_id=PROJECT, port_id=PORT))
    try:
        assert await asyncio.to_thread(entered.wait, 5)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert settled.is_set() and conn.network.writes == []


@pytest.mark.asyncio
async def test_expired_dispatch_deadline_never_writes(conn):
    with sdk.sdk_deadline(-1):
        with pytest.raises(McpNetworkError):
            await management.request_project_network_create(conn, project_id=PROJECT, attributes={"name": "new"})
    assert conn.network.writes == []


@pytest.mark.asyncio
async def test_ipv6_subnet_and_fixed_ip_validation_accepts_matching_family(conn):
    subnet = conn.network.records["subnets"][SUBNET]
    subnet.update(cidr="2001:db8::/64", ip_version=6, gateway_ip="2001:db8::1")
    preview = await management.preview_project_subnet_create(
        conn,
        project_id=PROJECT,
        attributes={
            "network_id": NETWORK,
            "name": "ipv6",
            "cidr": "2001:db8::/64",
            "dns_nameservers": ["2001:db8::53"],
        },
    )
    assert preview["cidr"] == "2001:db8::/64"
    port = await management.preview_project_port_create(
        conn,
        project_id=PROJECT,
        attributes={"network_id": NETWORK, "fixed_ips": [{"subnet_id": SUBNET, "ip_address": "2001:db8::20"}]},
    )
    assert port["attributes"]["fixed_ips"][0]["ip_address"] == "2001:db8::20"
    assert conn.network.writes == []


@pytest.mark.asyncio
@pytest.mark.parametrize("address", ["192.0.2.0", "192.0.2.255"])
async def test_port_create_rejects_ipv4_network_and_broadcast_addresses(conn, address):
    with pytest.raises(McpNetworkError, match="usable"):
        await management.request_project_port_create(
            conn,
            project_id=PROJECT,
            attributes={"network_id": NETWORK, "fixed_ips": [{"subnet_id": SUBNET, "ip_address": address}]},
        )
    assert conn.network.writes == []


@pytest.mark.asyncio
async def test_subnet_update_rejects_parent_becoming_shared_after_preview(conn):
    await management.preview_project_subnet_update(
        conn, project_id=PROJECT, subnet_id=SUBNET, attributes={"name": "renamed"}
    )
    conn.network.records["networks"][NETWORK]["shared"] = True
    with pytest.raises(McpNetworkError, match="shared"):
        await management.request_project_subnet_update(
            conn, project_id=PROJECT, subnet_id=SUBNET, attributes={"name": "renamed"}
        )
    assert conn.network.writes == []


@pytest.mark.asyncio
async def test_port_delete_revalidates_binding_after_preview(conn):
    await management.preview_project_port_delete(conn, project_id=PROJECT, port_id=PORT)
    conn.network.records["ports"][PORT].update(device_id=OTHER, device_owner="compute:nova")
    with pytest.raises(McpNetworkError, match="bound"):
        await management.request_project_port_delete(conn, project_id=PROJECT, port_id=PORT)
    assert conn.network.writes == []


@pytest.mark.asyncio
async def test_port_metadata_update_can_be_used_on_safe_administratively_down_parent(conn):
    conn.network.records["networks"][NETWORK].update(status="DOWN", admin_state_up=False)
    result = await management.request_project_port_update(
        conn, project_id=PROJECT, port_id=PORT, attributes={"name": "renamed"}
    )
    assert result["name"] == "renamed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "attributes",
    [
        {"fixed_ips": [{"subnet_id": SUBNET}] * 33},
        {"security_group_ids": [GROUP] * 33},
    ],
)
async def test_port_reference_lists_are_bounded_before_any_write(conn, attributes):
    with pytest.raises(McpNetworkError):
        await management.request_project_port_create(
            conn, project_id=PROJECT, attributes={"network_id": NETWORK, **attributes}
        )
    assert conn.network.writes == []


@pytest.mark.asyncio
async def test_port_get_rejects_missing_raw_owner_or_mismatched_provider_aliases(conn):
    record = conn.network.records["ports"][PORT]
    record["tenant_id"] = FOREIGN
    with pytest.raises(McpNetworkError, match="contradict"):
        await management.get_project_port(conn, project_id=PROJECT, port_id=PORT)
    del record["tenant_id"]
    del record["project_id"]
    with pytest.raises(McpNetworkError, match="ownership"):
        await management.get_project_port(conn, project_id=PROJECT, port_id=PORT)


@pytest.mark.asyncio
async def test_binding_vnic_type_json_alias_is_not_ignored(conn):
    conn.network.records["ports"][PORT]["binding:vnic_type"] = "direct"
    with pytest.raises(McpNetworkError, match="nonordinary"):
        await management.request_project_port_delete(conn, project_id=PROJECT, port_id=PORT)
    assert conn.network.writes == []


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["gateway_ip", "dns_nameservers", "fixed_ips"])
async def test_scoped_ipv6_addresses_are_denied_before_native_write(conn, field):
    conn.network.records["subnets"][SUBNET].update(
        cidr="2001:db8::/64",
        ip_version=6,
        gateway_ip="2001:db8::1",
    )
    scoped = "2001:db8::20%eth0"
    with pytest.raises(McpNetworkError, match="malformed"):
        if field == "fixed_ips":
            await management.request_project_port_create(
                conn,
                project_id=PROJECT,
                attributes={"network_id": NETWORK, "fixed_ips": [{"subnet_id": SUBNET, "ip_address": scoped}]},
            )
        else:
            value = [scoped] if field == "dns_nameservers" else scoped
            await management.request_project_subnet_update(
                conn,
                project_id=PROJECT,
                subnet_id=SUBNET,
                attributes={field: value},
            )
    assert conn.network.writes == []


@pytest.mark.asyncio
async def test_cancelled_port_traversal_stops_after_inflight_parent_read(conn):
    entered, finish = threading.Event(), threading.Event()
    original = conn.network.get
    paths = []

    def blocked(path, **kwargs):
        paths.append(path)
        if path == f"/networks/{NETWORK}":
            entered.set()
            assert finish.wait(2)
        return original(path, **kwargs)

    conn.network.get = blocked
    task = asyncio.create_task(management.list_project_ports(conn, project_id=PROJECT, limit=1))
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        task.cancel()
        await asyncio.sleep(0)  # deliver cancellation before releasing the in-flight read
    finally:
        finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert paths == [f"/networks/{NETWORK}"]
