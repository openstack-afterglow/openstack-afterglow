from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.mcp_control_plane import sdk
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


@pytest.mark.asyncio
async def test_network_list_uses_separate_owned_and_shared_visibility_queries():
    calls: list[dict[str, object]] = []

    class Network:
        def networks(self, **kwargs):
            calls.append(kwargs)
            if "project_id" in kwargs:
                return [
                    SimpleNamespace(
                        id="network-a",
                        name="private-a",
                        status="ACTIVE",
                        project_id="project-a",
                        is_shared=False,
                        is_router_external=False,
                        provider_physical_network="private",
                    )
                ]
            return [
                SimpleNamespace(
                    id="network-public",
                    name="public",
                    status="ACTIVE",
                    project_id="provider-project",
                    is_shared=True,
                    is_router_external=True,
                    provider_segmentation_id="secret",
                )
            ]

    result = await list_project_networks(SimpleNamespace(network=Network()), project_id="project-a", limit=50)

    assert calls == [{"project_id": "project-a"}, {"is_shared": True}, {"is_router_external": True}]
    assert result == [
        {
            "id": "network-a",
            "name": "private-a",
            "status": "ACTIVE",
            "is_shared": False,
            "is_external": False,
            "visibility": "owned",
        },
        {
            "id": "network-public",
            "name": "public",
            "status": "ACTIVE",
            "is_shared": True,
            "is_external": True,
            "visibility": "shared",
        },
    ]


@pytest.mark.asyncio
async def test_network_get_rejects_foreign_private_networks():
    class Network:
        def get_network(self, _network_id):
            return SimpleNamespace(
                id="network-b", name="foreign", status="ACTIVE", project_id="project-b", is_shared=False
            )

    with pytest.raises(McpNetworkError, match="ownership"):
        await get_project_network(SimpleNamespace(network=Network()), project_id="project-a", network_id="network-b")


@pytest.mark.asyncio
async def test_subnet_list_uses_project_filter_and_proves_visible_parent():
    calls: list[tuple[str, object]] = []

    class Network:
        def subnets(self, **kwargs):
            calls.append(("subnets", kwargs))
            return [
                SimpleNamespace(
                    id="subnet-a",
                    name="private-subnet",
                    network_id="network-a",
                    cidr="10.0.0.0/24",
                    ip_version=4,
                    gateway_ip="10.0.0.1",
                    project_id="project-a",
                    allocation_pools=[{"start": "10.0.0.10", "end": "10.0.0.200"}],
                )
            ]

        def get_network(self, network_id):
            calls.append(("get_network", network_id))
            return SimpleNamespace(
                id=network_id,
                name="private-a",
                status="ACTIVE",
                project_id="project-a",
                is_shared=False,
                is_router_external=False,
            )

    result = await list_project_subnets(SimpleNamespace(network=Network()), project_id="project-a", limit=50)

    assert calls == [
        ("subnets", {"project_id": "project-a"}),
        ("get_network", "network-a"),
    ]
    assert result == [
        {
            "id": "subnet-a",
            "name": "private-subnet",
            "network_id": "network-a",
            "cidr": "10.0.0.0/24",
            "ip_version": 4,
            "gateway_ip": "10.0.0.1",
        }
    ]


@pytest.mark.asyncio
async def test_subnet_get_rejects_foreign_parent_network():
    class Network:
        def get_subnet(self, _subnet_id):
            return SimpleNamespace(
                id="subnet-a",
                name="private-subnet",
                network_id="network-a",
                cidr="10.0.0.0/24",
                ip_version=4,
                gateway_ip="10.0.0.1",
                project_id="project-a",
            )

        def get_network(self, network_id):
            return SimpleNamespace(
                id=network_id,
                name="private-b",
                status="ACTIVE",
                project_id="project-b",
                is_shared=False,
                is_router_external=False,
            )

    with pytest.raises(McpNetworkError, match="ownership"):
        await get_project_subnet(SimpleNamespace(network=Network()), project_id="project-a", subnet_id="subnet-a")


@pytest.mark.asyncio
async def test_network_delete_revalidates_owned_network_without_force():
    calls: list[tuple[str, object]] = []

    class Network:
        def get_network(self, network_id):
            calls.append(("get_network", network_id))
            return SimpleNamespace(
                id=network_id,
                name="private-a",
                status="ACTIVE",
                project_id="project-a",
                is_shared=False,
                is_router_external=False,
            )

        def delete_network(self, network_id, **kwargs):
            calls.append(("delete_network", (network_id, kwargs)))

    conn = SimpleNamespace(network=Network())
    preview = await preview_project_network_delete(conn, project_id="project-a", network_id="network-a")
    result = await request_project_network_delete(conn, project_id="project-a", network_id="network-a")

    assert preview["requested_action"] == "delete"
    assert result["requested_action"] == "delete"
    assert calls == [
        ("get_network", "network-a"),
        ("get_network", "network-a"),
        ("delete_network", ("network-a", {"ignore_missing": False})),
    ]


@pytest.mark.asyncio
async def test_network_delete_rejects_shared_or_foreign_targets_before_provider_call():
    calls: list[str] = []

    class Network:
        def get_network(self, network_id):
            return SimpleNamespace(
                id=network_id,
                name="public",
                status="ACTIVE",
                project_id="project-a",
                is_shared=True,
                is_router_external=True,
            )

        def delete_network(self, network_id, **_kwargs):
            calls.append(network_id)

    with pytest.raises(McpNetworkError, match="shared"):
        await request_project_network_delete(
            SimpleNamespace(network=Network()),
            project_id="project-a",
            network_id="network-public",
        )

    assert calls == []


@pytest.mark.asyncio
async def test_subnet_delete_revalidates_owned_non_shared_parent_without_force():
    calls: list[tuple[str, object]] = []

    class Network:
        def get_subnet(self, subnet_id):
            calls.append(("get_subnet", subnet_id))
            return SimpleNamespace(
                id=subnet_id,
                name="private-subnet",
                network_id="network-a",
                cidr="10.0.0.0/24",
                ip_version=4,
                gateway_ip="10.0.0.1",
                project_id="project-a",
            )

        def get_network(self, network_id):
            calls.append(("get_network", network_id))
            return SimpleNamespace(
                id=network_id,
                name="private-a",
                status="ACTIVE",
                project_id="project-a",
                is_shared=False,
                is_router_external=False,
            )

        def delete_subnet(self, subnet_id, **kwargs):
            calls.append(("delete_subnet", (subnet_id, kwargs)))

    conn = SimpleNamespace(network=Network())
    preview = await preview_project_subnet_delete(conn, project_id="project-a", subnet_id="subnet-a")
    result = await request_project_subnet_delete(conn, project_id="project-a", subnet_id="subnet-a")

    assert preview["requested_action"] == "delete"
    assert result["requested_action"] == "delete"
    assert calls == [
        ("get_subnet", "subnet-a"),
        ("get_network", "network-a"),
        ("get_network", "network-a"),
        ("get_subnet", "subnet-a"),
        ("get_network", "network-a"),
        ("get_network", "network-a"),
        ("delete_subnet", ("subnet-a", {"ignore_missing": False})),
    ]


@pytest.mark.asyncio
async def test_subnet_delete_rejects_shared_parent_before_provider_call():
    calls: list[str] = []

    class Network:
        def get_subnet(self, subnet_id):
            return SimpleNamespace(
                id=subnet_id,
                name="shared-subnet",
                network_id="network-shared",
                cidr="10.0.0.0/24",
                ip_version=4,
                gateway_ip="10.0.0.1",
                project_id="project-a",
            )

        def get_network(self, network_id):
            return SimpleNamespace(
                id=network_id,
                name="shared",
                status="ACTIVE",
                project_id="project-a",
                is_shared=True,
                is_router_external=False,
            )

        def delete_subnet(self, subnet_id, **_kwargs):
            calls.append(subnet_id)

    with pytest.raises(McpNetworkError, match="shared"):
        await request_project_subnet_delete(
            SimpleNamespace(network=Network()),
            project_id="project-a",
            subnet_id="subnet-a",
        )

    assert calls == []


_ATTACH_ARGUMENTS = {"project_id": "project-a", "server_id": "server-a", "network_id": "network-a"}


class _AttachmentProvider:
    """Isolated Nova/Neutron boundary with separately mutable resource proofs."""

    def __init__(self):
        self.server = {"id": "server-a", "name": "instance", "status": "ACTIVE", "project_id": "project-a"}
        self.network = {
            "id": "network-a",
            "status": "ACTIVE",
            "project_id": "project-a",
            "is_shared": False,
            "is_admin_state_up": True,
        }
        self.interface = {"net_id": "network-a", "port_id": "port-new", "mac_addr": "fa:16:3e:00:00:01"}
        self.port = {
            "id": "port-new",
            "project_id": "project-a",
            "network_id": "network-a",
            "device_id": "server-a",
            "fixed_ips": [{"ip_address": "10.0.0.10"}],
            "binding_host_id": "private-host",
        }
        self.reads = []
        self.writes = []
        self.after_network_read = None
        self.fail_at = None
        self.conn = SimpleNamespace(
            compute=SimpleNamespace(
                get_server=self.get_server,
                create_server_interface=self.create_server_interface,
                delete_server_interface=self.cleanup,
                delete_server=self.cleanup,
            ),
            network=SimpleNamespace(
                get_network=self.get_network,
                get_port=self.get_port,
                delete_port=self.cleanup,
                delete_network=self.cleanup,
            ),
        )

    def _fail_if_requested(self, operation):
        if self.fail_at == operation:
            raise RuntimeError("provider-secret: token=private-token password=private-password")

    def get_server(self, server_id):
        self.reads.append(("server", server_id))
        self._fail_if_requested("server")
        return dict(self.server) if self.server is not None else None

    def get_network(self, network_id):
        self.reads.append(("network", network_id))
        self._fail_if_requested("network")
        if self.after_network_read is not None:
            self.after_network_read()
        return dict(self.network) if self.network is not None else None

    def create_server_interface(self, server_id, **kwargs):
        self.writes.append(("attach", server_id, kwargs))
        self._fail_if_requested("attach")
        return dict(self.interface) if self.interface is not None else None

    def get_port(self, port_id):
        self.reads.append(("port", port_id))
        self._fail_if_requested("port")
        return dict(self.port) if self.port is not None else None

    def cleanup(self, *args, **kwargs):
        self.writes.append(("cleanup", args, kwargs))


@pytest.fixture
def attachment_provider():
    return _AttachmentProvider()


@pytest.mark.asyncio
@pytest.mark.parametrize("server_status", ["ACTIVE", "SHUTOFF"])
@pytest.mark.parametrize("visibility", ["owned", "shared", "shared_alias"])
async def test_network_attach_preview_is_read_only_and_request_creates_only_a_new_interface(
    attachment_provider, server_status, visibility
):
    provider = attachment_provider
    provider.server["status"] = server_status
    if visibility != "owned":
        provider.network["project_id"] = "provider-project"
        provider.network["is_shared" if visibility == "shared" else "shared"] = True

    preview = await preview_project_server_network_attach(provider.conn, **_ATTACH_ARGUMENTS)

    assert preview == {
        "server_id": "server-a",
        "server_status": server_status,
        "network_id": "network-a",
        "network_status": "ACTIVE",
        "visibility": "owned" if visibility == "owned" else "shared",
    }
    assert provider.writes == []
    assert provider.reads == [("server", "server-a"), ("network", "network-a")]

    result = await request_project_server_network_attach(provider.conn, **_ATTACH_ARGUMENTS)

    assert result == {
        "server_id": "server-a",
        "network_id": "network-a",
        "port_id": "port-new",
        "mac_address": "fa:16:3e:00:00:01",
        "requested_action": "attach_network",
    }
    assert provider.writes == [("attach", "server-a", {"net_id": "network-a"})]
    assert provider.reads == [
        ("server", "server-a"),
        ("network", "network-a"),
        ("server", "server-a"),
        ("network", "network-a"),
        ("port", "port-new"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("owner", [None, "project-b"])
async def test_network_attach_rejects_missing_or_foreign_server_owner_without_writes(attachment_provider, owner):
    provider = attachment_provider
    provider.server["project_id"] = owner

    for operation in (preview_project_server_network_attach, request_project_server_network_attach):
        with pytest.raises(McpNetworkError, match="ownership"):
            await operation(provider.conn, **_ATTACH_ARGUMENTS)

    assert provider.writes == []
    assert provider.reads == [("server", "server-a"), ("server", "server-a")]


@pytest.mark.asyncio
@pytest.mark.parametrize("server_change", [{"status": "BUILD"}, {"status": "ERROR"}, {"id": "server-b"}])
async def test_network_attach_rejects_server_state_or_identity_before_network_reads(attachment_provider, server_change):
    provider = attachment_provider
    provider.server.update(server_change)

    for operation in (preview_project_server_network_attach, request_project_server_network_attach):
        with pytest.raises(McpNetworkError):
            await operation(provider.conn, **_ATTACH_ARGUMENTS)

    assert provider.writes == []
    assert provider.reads == [("server", "server-a"), ("server", "server-a")]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "network_change",
    [
        {"project_id": "project-b", "is_router_external": True},
        {"project_id": "project-b", "is_shared": "true"},
        {"project_id": "project-b", "shared": "true"},
        {"project_id": "project-b", "is_shared": 1},
        {"project_id": "project-b", "shared": 1},
        {"project_id": None},
        {"id": "network-b"},
        {"id": None},
        {"status": "DOWN"},
        {"status": None},
        {"is_admin_state_up": False},
        {"admin_state_up": False},
    ],
)
async def test_network_attach_requires_exact_active_owned_or_literal_shared_network(
    attachment_provider, network_change
):
    provider = attachment_provider
    provider.network.update(network_change)

    for operation in (preview_project_server_network_attach, request_project_server_network_attach):
        with pytest.raises(McpNetworkError):
            await operation(provider.conn, **_ATTACH_ARGUMENTS)

    assert provider.writes == []
    assert all(kind != "port" for kind, _resource_id in provider.reads)


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_resource", ["server", "network"])
async def test_network_attach_missing_precheck_resource_never_dispatches(attachment_provider, missing_resource):
    provider = attachment_provider
    setattr(provider, missing_resource, None)

    for operation in (preview_project_server_network_attach, request_project_server_network_attach):
        with pytest.raises(McpNetworkError, match="not found"):
            await operation(provider.conn, **_ATTACH_ARGUMENTS)

    assert provider.writes == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("resource", "change"),
    [
        ("server", {"project_id": "project-b"}),
        ("server", {"project_id": None}),
        ("server", {"status": "BUILD"}),
        ("network", {"project_id": "project-b"}),
        ("network", {"status": "DOWN"}),
        ("network", {"is_admin_state_up": False}),
    ],
)
async def test_network_attach_revalidates_state_and_owner_after_preview(attachment_provider, resource, change):
    provider = attachment_provider
    await preview_project_server_network_attach(provider.conn, **_ATTACH_ARGUMENTS)
    getattr(provider, resource).update(change)

    with pytest.raises(McpNetworkError):
        await request_project_server_network_attach(provider.conn, **_ATTACH_ARGUMENTS)

    assert provider.writes == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "interface",
    [
        None,
        {},
        {"net_id": "network-b", "port_id": "port-new"},
        {"net_id": "network-a", "network_id": "network-b", "port_id": "port-new"},
        {"net_id": "network-a"},
        {"net_id": "network-a", "port_id": ""},
        {"net_id": "network-a", "port_id": 123},
    ],
)
async def test_network_attach_rejects_unproven_interface_without_cleanup(attachment_provider, interface):
    provider = attachment_provider
    provider.interface = interface

    with pytest.raises(McpNetworkError):
        await request_project_server_network_attach(provider.conn, **_ATTACH_ARGUMENTS)

    assert provider.writes == [("attach", "server-a", {"net_id": "network-a"})]
    assert all(kind != "port" for kind, _resource_id in provider.reads)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "port_change",
    [
        {"project_id": "project-b"},
        {"project_id": None},
        {"tenant_id": "project-b"},
        {"network_id": "network-b"},
        {"network_id": None},
        {"device_id": "server-b"},
        {"device_id": None},
        {"id": "port-other"},
        {"id": None},
    ],
)
async def test_network_attach_requires_exact_owned_result_port_without_cleanup(attachment_provider, port_change):
    provider = attachment_provider
    provider.port.update(port_change)

    with pytest.raises(McpNetworkError):
        await request_project_server_network_attach(provider.conn, **_ATTACH_ARGUMENTS)

    assert provider.writes == [("attach", "server-a", {"net_id": "network-a"})]
    assert provider.reads[-1] == ("port", "port-new")


@pytest.mark.asyncio
async def test_network_attach_missing_result_port_does_not_retry_or_cleanup(attachment_provider):
    provider = attachment_provider
    provider.port = None

    with pytest.raises(McpNetworkError, match="port was not found"):
        await request_project_server_network_attach(provider.conn, **_ATTACH_ARGUMENTS)

    assert provider.writes == [("attach", "server-a", {"net_id": "network-a"})]
    assert provider.reads[-1] == ("port", "port-new")


@pytest.mark.asyncio
@pytest.mark.parametrize("mac_address", [None, "fa:16:3e:00:00:02"])
async def test_network_attach_accepts_sdk_network_alias_and_optional_mac(attachment_provider, mac_address):
    provider = attachment_provider
    provider.interface = {"network_id": "network-a", "port_id": "port-new"}
    provider.port["mac_address"] = mac_address

    result = await request_project_server_network_attach(provider.conn, **_ATTACH_ARGUMENTS)

    assert result["mac_address"] == mac_address
    assert provider.writes == [("attach", "server-a", {"net_id": "network-a"})]


@pytest.mark.asyncio
@pytest.mark.parametrize("mac_address", ["", 123, "x" * 256])
async def test_network_attach_rejects_malformed_mac_without_cleanup(attachment_provider, mac_address):
    provider = attachment_provider
    provider.port["mac_address"] = mac_address

    with pytest.raises(McpNetworkError, match="MAC address is malformed"):
        await request_project_server_network_attach(provider.conn, **_ATTACH_ARGUMENTS)

    assert provider.writes == [("attach", "server-a", {"net_id": "network-a"})]


@pytest.mark.asyncio
async def test_network_attach_deadline_expiring_during_final_reads_fences_dispatch(attachment_provider):
    provider = attachment_provider

    def expire_call():
        sdk._current_call.get().deadline = 0

    provider.after_network_read = expire_call
    with sdk.sdk_deadline(60), pytest.raises(McpNetworkError, match="attachment is unavailable"):
        await request_project_server_network_attach(provider.conn, **_ATTACH_ARGUMENTS)

    assert provider.reads == [("server", "server-a"), ("network", "network-a")]
    assert provider.writes == []


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_at", ["server", "network", "attach", "port"])
async def test_network_attach_redacts_provider_secrets_and_never_retries_or_cleans_up(attachment_provider, fail_at):
    provider = attachment_provider
    provider.fail_at = fail_at

    with pytest.raises(McpNetworkError) as caught:
        await request_project_server_network_attach(provider.conn, **_ATTACH_ARGUMENTS)

    assert str(caught.value) == "Nova server network attachment is unavailable"
    assert caught.value.__suppress_context__
    assert provider.writes == (
        [] if fail_at in {"server", "network"} else [("attach", "server-a", {"net_id": "network-a"})]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_at", ["server", "network"])
async def test_network_attach_preview_redacts_provider_secrets_without_writes(attachment_provider, fail_at):
    provider = attachment_provider
    provider.fail_at = fail_at

    with pytest.raises(McpNetworkError) as caught:
        await preview_project_server_network_attach(provider.conn, **_ATTACH_ARGUMENTS)

    assert str(caught.value) == "Nova server network attachment is unavailable"
    assert caught.value.__suppress_context__
    assert provider.writes == []
