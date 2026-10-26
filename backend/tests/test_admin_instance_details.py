"""Explicit admin transport and native parent/child fences for shared VM details."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from openstack.block_storage.v3.volume import Volume
from openstack.compute.v2.server import Server
from openstack.network.v2.floating_ip import FloatingIP
from openstack.network.v2.network import Network
from openstack.network.v2.port import Port
from openstack.network.v2.security_group import SecurityGroup

from app.api.deps import get_os_conn
from app.api.identity import admin_instances
from app.main import app
from app.services import nova


@pytest.fixture
def native_detail(mock_conn, monkeypatch):
    server = Server(
        id="vm",
        name="foreign VM",
        status="SHUTOFF",
        project_id="foreign-project",
        user_id="creator",
        image={"id": "private-image"},
        flavor={"id": "flavor"},
        addresses={},
        metadata={},
    )
    port = Port(
        id="port",
        project_id="foreign-project",
        device_id="vm",
        network_id="network",
        fixed_ips=[{"subnet_id": "subnet", "ip_address": "10.0.0.4"}],
        security_group_ids=["group"],
        status="ACTIVE",
        mac_address="fa:16:3e:00:00:01",
    )
    volume = Volume(
        id="volume",
        project_id="foreign-project",
        name="disk",
        status="in-use",
        size=10,
        volume_type="rbd",
        attachments=[{"server_id": "vm", "volume_id": "volume"}],
    )
    attachment = {
        "id": "attachment",
        "server_id": "vm",
        "volume_id": "volume",
        "device": "/dev/vda",
        "delete_on_termination": False,
    }
    group = SecurityGroup(
        id="group", project_id="foreign-project", name="default", description="", security_group_rules=[]
    )
    network = Network(
        id="network",
        project_id="foreign-project",
        name="private",
        status="ACTIVE",
        subnet_ids=["subnet"],
        is_shared=False,
        is_router_external=False,
    )
    fip = FloatingIP(
        id="floating",
        project_id="foreign-project",
        port_id="port",
        floating_network_id="external",
        floating_ip_address="192.0.2.3",
        fixed_ip_address="10.0.0.4",
        status="ACTIVE",
    )
    mock_conn._afterglow_project_id = "caller-personal"
    mock_conn._afterglow_authenticated_project_id = "fixed-admin-executor"
    mock_conn.compute.get_server.return_value = server
    mock_conn.network.ports.return_value = [port]
    mock_conn.network.update_port.return_value = port
    mock_conn.network.security_groups.return_value = [group]
    mock_conn.network.get_security_group.return_value = group
    mock_conn.network.networks.return_value = [network]
    mock_conn.network.get_network.return_value = network
    mock_conn.network.ips.return_value = [fip]
    mock_conn.network.get_ip.return_value = fip
    mock_conn.block_storage.get_volume.return_value = volume
    mock_conn.block_storage.volumes.return_value = []
    mock_conn.identity.get_user.return_value = SimpleNamespace(
        id="creator", name="Creator", email="creator@example.test"
    )
    monkeypatch.setattr(nova, "list_volume_attachments", lambda conn, instance_id: [attachment])
    monkeypatch.setattr(nova, "list_flavors", lambda conn: [])
    monkeypatch.setattr(nova, "get_server_image_meta", lambda conn, instance_id: {"os_type": "windows"})
    monkeypatch.setattr("app.services.glance.list_images", lambda conn: [])
    return SimpleNamespace(
        server=server, port=port, volume=volume, attachment=attachment, group=group, network=network, fip=fip
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "suffix",
    [
        "",
        "/interfaces",
        "/volumes",
        "/available-volumes",
        "/security-groups",
        "/floating-ips",
        "/networks",
        "/owner",
        "/console",
        "/log",
        "/resize-flavors",
        "/admin-password/precheck",
        "/storage-attachments",
        "/file-storage",
        "/metrics-batch?metrics=cpu",
        "/metrics-summary",
        "/volumes/volume",
    ],
)
async def test_admin_instance_reads_deny_ordinary_members(client, suffix):
    response = await client.get(f"/api/v1/admin/instances/vm{suffix}")
    assert response.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "suffix",
    [
        "",
        "/interfaces",
        "/volumes",
        "/available-volumes",
        "/security-groups",
        "/floating-ips",
        "/networks",
        "/owner",
        "/volumes/volume",
    ],
)
async def test_foreign_project_detail_uses_fixed_executor(admin_client, mock_conn, native_detail, suffix):
    response = await admin_client.get(f"/api/v1/admin/instances/vm{suffix}", headers={"X-Project-ID": "forged-project"})
    assert response.status_code == 200, response.text
    mock_conn.compute.get_server.assert_called_with("vm")
    assert mock_conn._afterglow_project_id == "caller-personal"
    assert mock_conn._afterglow_authenticated_project_id == "fixed-admin-executor"
    if suffix == "":
        assert response.json()["project_id"] == "foreign-project"
        assert response.json()["os_type"] == "windows"
    if suffix == "/interfaces":
        mock_conn.network.ports.assert_called_with(device_id="vm", project_id="foreign-project")
    if suffix == "/security-groups":
        mock_conn.network.security_groups.assert_called_with(project_id="foreign-project")
    if suffix == "/owner":
        assert response.json()["name"] == "Creator"


@pytest.mark.asyncio
@pytest.mark.parametrize("owner", [None, ""])
async def test_missing_server_owner_fails_closed_before_child_reads(admin_client, mock_conn, native_detail, owner):
    native_detail.server.project_id = owner
    response = await admin_client.get("/api/v1/admin/instances/vm/interfaces")
    assert response.status_code == 409
    mock_conn.network.ports.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value", [("project_id", "other-project"), ("project_id", None), ("device_id", "other-vm")]
)
async def test_instance_port_owner_and_parent_mismatch_rejected(admin_client, native_detail, field, value):
    setattr(native_detail.port, field, value)
    response = await admin_client.get("/api/v1/admin/instances/vm/interfaces")
    assert response.status_code == 409
    assert "mac_address" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["owner", "nova-parent", "cinder-parent"])
async def test_volume_parent_fences_reject_before_return_or_mutation(admin_client, mock_conn, native_detail, change):
    if change == "owner":
        native_detail.volume.project_id = "other-project"
    elif change == "nova-parent":
        native_detail.attachment["server_id"] = "other-vm"
    else:
        native_detail.volume.attachments = [{"server_id": "other-vm"}]
    response = await admin_client.get("/api/v1/admin/instances/vm/volumes")
    assert response.status_code == 409
    response = await admin_client.post("/api/v1/admin/instances/vm/volumes/volume/extend", json={"new_size": 20})
    assert response.status_code == 409
    mock_conn.block_storage.extend_volume.assert_not_called()


@pytest.mark.asyncio
async def test_foreign_group_on_owned_port_is_not_disclosed(admin_client, native_detail):
    native_detail.group.project_id = "other-project"
    response = await admin_client.get("/api/v1/admin/instances/vm/security-groups")
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_unrelated_floating_ip_rejected(admin_client, native_detail, mock_conn):
    native_detail.fip.port_id = "unrelated-port"
    response = await admin_client.get("/api/v1/admin/instances/vm/floating-ips")
    assert response.status_code == 409
    response = await admin_client.delete("/api/v1/admin/instances/vm/floating-ips/floating")
    assert response.status_code == 409
    mock_conn.network.delete_ip.assert_not_called()


@pytest.mark.asyncio
async def test_console_and_log_use_fixed_executor_after_server_fence(
    admin_client, mock_conn, native_detail, monkeypatch
):
    console = MagicMock(return_value="https://console.example.test/token")
    log = MagicMock(return_value="serial output")
    monkeypatch.setattr(nova, "get_console_url", console)
    monkeypatch.setattr(nova, "get_console_output", log)
    assert (await admin_client.get("/api/v1/admin/instances/vm/console")).json() == {"url": console.return_value}
    assert (await admin_client.get("/api/v1/admin/instances/vm/log?length=200")).json() == {"output": "serial output"}
    console.assert_called_once_with(mock_conn, "vm")
    log.assert_called_once_with(mock_conn, "vm", 200)
    native_detail.server.project_id = None
    assert (await admin_client.get("/api/v1/admin/instances/vm/console")).status_code == 409
    assert console.call_count == 1


@pytest.mark.asyncio
async def test_foreign_instance_action_and_attached_child_mutations(
    admin_client, mock_conn, native_detail, monkeypatch
):
    invalidate = AsyncMock()
    monkeypatch.setattr(admin_instances, "invalidate", invalidate)
    response = await admin_client.post("/api/v1/admin/instances/vm/start")
    assert response.status_code == 204
    mock_conn.compute.start_server.assert_called_once_with("vm")
    assert any("foreign-project" in call.args[0] for call in invalidate.call_args_list)
    response = await admin_client.post(
        "/api/v1/admin/instances/vm/ports/port/security-groups", json={"security_group_ids": ["group"]}
    )
    assert response.status_code == 200
    mock_conn.network.update_port.assert_called_once_with("port", security_groups=["group"])
    native_detail.port.device_id = "other-vm"
    response = await admin_client.delete("/api/v1/admin/instances/vm/interfaces/port")
    assert response.status_code == 409
    mock_conn.compute.delete_server_interface.assert_not_called()


@pytest.mark.asyncio
async def test_metrics_never_forward_executor_to_native_telemetry(admin_client, mock_conn, native_detail, monkeypatch):
    from app.api.compute import instance_metrics

    caller = SimpleNamespace(_afterglow_authenticated_project_id="caller-personal")

    async def caller_transport():
        yield caller

    app.dependency_overrides[get_os_conn] = caller_transport
    native = AsyncMock(return_value={"cpu": {"status": "forbidden"}})
    monkeypatch.setattr(instance_metrics, "_native_instance_series", native)
    monkeypatch.setattr(
        instance_metrics, "_metric_series", AsyncMock(return_value={"series": [], "status": "not_collected"})
    )
    response = await admin_client.get("/api/v1/admin/instances/vm/metrics-batch?metrics=cpu")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert native.call_args.args[0] is caller
    assert native.call_args.args[0] is not mock_conn
    assert native.call_args.args[1].project_id == "foreign-project"


@pytest.mark.asyncio
async def test_storage_reference_cannot_select_foreign_share(admin_client, native_detail, monkeypatch):
    share = SimpleNamespace(id="share", project_id="unrelated", share_network_id=None)
    monkeypatch.setattr(admin_instances.manila, "get_file_storage", lambda conn, share_id: share)
    create = MagicMock()
    monkeypatch.setattr(admin_instances.manila, "create_access_rule", create)
    response = await admin_client.post(
        "/api/v1/admin/instances/vm/storage-attachments", json={"file_storage_id": "share", "read_only": True}
    )
    assert response.status_code == 409
    create.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,suffix,body",
    [
        ("post", "/start", {}),
        ("post", "/stop", {}),
        ("post", "/reboot", {}),
        ("post", "/shelve", {}),
        ("post", "/unshelve", {}),
        ("delete", "", None),
        ("post", "/volumes", {"volume_id": "volume"}),
        ("delete", "/volumes/volume", None),
        ("patch", "/volumes/volume", {"delete_on_termination": True}),
        ("post", "/interfaces", {"net_id": "network"}),
        ("delete", "/interfaces/port", None),
        ("post", "/ports/port/security-groups", {"security_group_ids": []}),
        ("post", "/floating-ip?port_id=port", {}),
        ("delete", "/floating-ips/floating", None),
        ("post", "/admin-password", {"new_password": "Valid-password123!"}),
        ("post", "/volumes/volume/extend", {"new_size": 20}),
        ("post", "/storage-attachments", {"file_storage_id": "share", "read_only": True}),
        ("post", "/storage-attachments/share/connection-info", {}),
        ("delete", "/storage-attachments/share", None),
    ],
)
async def test_admin_instance_writes_deny_member_before_provider(client, mock_conn, method, suffix, body):
    response = await client.request(
        method.upper(), f"/api/v1/admin/instances/vm{suffix}", **({"json": body} if body is not None else {})
    )
    assert response.status_code == 403
    mock_conn.compute.get_server.assert_not_called()


@pytest.mark.asyncio
async def test_parent_bound_extension_reuses_native_power_and_owner_safety(admin_client, mock_conn, native_detail):
    native_detail.server.power_state = 4
    native_detail.server.task_state = None
    native_detail.server.attached_volumes = [{"id": "volume"}]
    response = await admin_client.post("/api/v1/admin/instances/vm/volumes/volume/extend", json={"new_size": 20})
    assert response.status_code == 200, response.text
    mock_conn.block_storage.extend_volume.assert_called_once_with("volume", 20)
    assert response.json()["size"] == 10  # Native reread, not invented requested capacity.
    assert mock_conn._afterglow_project_id == "caller-personal"
    assert mock_conn._afterglow_authenticated_project_id == "fixed-admin-executor"


@pytest.mark.asyncio
async def test_parent_bound_extension_blocks_running_attached_server(admin_client, mock_conn, native_detail):
    native_detail.server.status = "ACTIVE"
    native_detail.server.power_state = 1
    native_detail.server.task_state = None
    native_detail.server.attached_volumes = [{"id": "volume"}]
    response = await admin_client.post("/api/v1/admin/instances/vm/volumes/volume/extend", json={"new_size": 20})
    assert response.status_code == 409
    mock_conn.block_storage.extend_volume.assert_not_called()


@pytest.mark.asyncio
async def test_block_cleanup_is_rejected_before_any_native_mutation(
    admin_client, mock_conn, native_detail, monkeypatch
):
    cleanup = AsyncMock()
    monkeypatch.setattr("app.services.layer_consume_resources.lookup_for_server", AsyncMock(return_value=[7]))
    monkeypatch.setattr("app.api.compute.instances._bulk_delete_one", cleanup)
    response = await admin_client.delete("/api/v1/admin/instances/vm")
    assert response.status_code == 409
    cleanup.assert_not_awaited()
    mock_conn.compute.delete_server.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["volume", "network", "group", "password-boot-volume"])
async def test_admin_writes_reject_foreign_children_before_send(admin_client, mock_conn, native_detail, kind):
    if kind == "volume":
        native_detail.volume.project_id = "unrelated"
        response = await admin_client.post("/api/v1/admin/instances/vm/volumes", json={"volume_id": "volume"})
        mock_conn.compute.create_volume_attachment.assert_not_called()
    elif kind == "network":
        native_detail.network.project_id = "unrelated"
        response = await admin_client.post("/api/v1/admin/instances/vm/interfaces", json={"net_id": "network"})
        mock_conn.compute.create_server_interface.assert_not_called()
    elif kind == "group":
        native_detail.group.project_id = "unrelated"
        response = await admin_client.post(
            "/api/v1/admin/instances/vm/ports/port/security-groups", json={"security_group_ids": ["group"]}
        )
        mock_conn.network.update_port.assert_not_called()
    else:
        native_detail.volume.project_id = "unrelated"
        response = await admin_client.post(
            "/api/v1/admin/instances/vm/admin-password", json={"new_password": "Valid-password123!"}
        )
        mock_conn.compute.change_server_password.assert_not_called()
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_server_identifier_mismatch_is_not_accepted(admin_client, mock_conn, native_detail):
    native_detail.server.id = "other-vm"
    response = await admin_client.get("/api/v1/admin/instances/vm/interfaces")
    assert response.status_code == 409
    mock_conn.network.ports.assert_not_called()


@pytest.mark.asyncio
async def test_summary_keeps_native_telemetry_on_caller_connection(admin_client, mock_conn, native_detail, monkeypatch):
    from app.api.compute import instance_metrics

    caller = SimpleNamespace(_afterglow_authenticated_project_id="caller-personal")

    async def caller_transport():
        yield caller

    app.dependency_overrides[get_os_conn] = caller_transport
    native = AsyncMock(return_value={})
    monkeypatch.setattr(instance_metrics, "_native_instance_series", native)
    monkeypatch.setattr(
        instance_metrics,
        "_metric_stats",
        AsyncMock(
            return_value={
                "status": "forbidden",
                "native_status": "forbidden",
                "avg": None,
                "min": None,
                "max": None,
            }
        ),
    )
    response = await admin_client.get("/api/v1/admin/instances/vm/metrics-summary")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert native.call_args.args[0] is caller
    assert native.call_args.args[0] is not mock_conn


@pytest.mark.asyncio
async def test_storage_network_owner_is_checked_from_native_response(admin_client, native_detail, monkeypatch):
    share = SimpleNamespace(id="share", project_id="foreign-project", share_network_id="share-network")
    monkeypatch.setattr(admin_instances.manila, "get_file_storage", lambda conn, share_id: share)
    client = SimpleNamespace(get=lambda path: {"share_network": {"id": "share-network", "project_id": "unrelated"}})
    monkeypatch.setattr(admin_instances.manila, "get_client", lambda conn: client)
    create = MagicMock()
    monkeypatch.setattr(admin_instances.manila, "create_access_rule", create)
    response = await admin_client.post(
        "/api/v1/admin/instances/vm/storage-attachments", json={"file_storage_id": "share", "read_only": True}
    )
    assert response.status_code == 409
    create.assert_not_called()


@pytest.mark.asyncio
async def test_admin_metric_validation_error_is_not_cacheable(admin_client):
    response = await admin_client.get("/api/v1/admin/instances/vm/metrics-batch?metrics=unknown")
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
async def test_admin_health_static_route_is_not_shadowed(admin_client, mock_conn, monkeypatch):
    from app.api.identity import admin_dashboard

    collect = AsyncMock(return_value={"health_route": True})
    monkeypatch.setattr(admin_dashboard, "cached_call", collect)
    response = await admin_client.get("/api/v1/admin/instances/health")
    assert response.status_code == 200
    assert response.json() == {"health_route": True}
    collect.assert_awaited_once()
    mock_conn.compute.get_server.assert_not_called()


@pytest.mark.asyncio
async def test_admin_mutations_audit_success_and_failure_without_secret_bodies(
    admin_client, mock_conn, native_detail, monkeypatch
):
    record = AsyncMock()
    monkeypatch.setattr(admin_instances, "rec", record)
    assert (await admin_client.post("/api/v1/admin/instances/vm/start")).status_code == 204
    assert record.call_args.kwargs["status"] == "success"
    assert record.call_args.kwargs["resource_id"] == "vm"
    assert record.call_args.kwargs["extra"] == {"target_project_id": "foreign-project"}
    native_detail.volume.project_id = "unrelated"
    response = await admin_client.post("/api/v1/admin/instances/vm/volumes", json={"volume_id": "volume"})
    assert response.status_code == 409
    assert record.call_args.kwargs["status"] == "failed"
    assert record.call_args.kwargs["extra"] == {"target_project_id": "foreign-project"}
    assert "body" not in record.call_args.kwargs


@pytest.mark.asyncio
async def test_admin_storage_grant_and_connection_info_never_disclose_ceph_key(
    admin_client, mock_conn, native_detail, monkeypatch
):
    from app.api.compute import instances

    instance_id = "20000000-0000-4000-8000-000000000001"
    native_detail.server.id = instance_id
    share = SimpleNamespace(
        id="share",
        project_id="foreign-project",
        share_network_id=None,
        name="private-data",
        status="available",
        share_proto="CEPHFS",
        export_locations=["192.0.2.1:/data"],
    )
    rules = []

    def create_rule(conn, share_id, access_to, level, **kwargs):
        rule = {
            "id": "native-access-rule",
            "access_type": "cephx",
            "access_to": access_to,
            "access_level": level,
            "state": "active",
            "access_key": "provider-private-ceph-key",
            "metadata": kwargs["metadata"],
        }
        rules.append(rule)
        return rule

    monkeypatch.setattr(instances.manila, "get_file_storage", lambda *args, **kwargs: share)
    monkeypatch.setattr(instances.manila, "list_access_rules", lambda *args, **kwargs: list(rules))
    monkeypatch.setattr(instances.manila, "create_access_rule", create_rule)
    mock_conn.compute.set_server_metadata.side_effect = lambda sid, **metadata: native_detail.server.metadata.update(
        metadata
    )
    monkeypatch.setattr(admin_instances, "rec", AsyncMock())
    url = f"/api/v1/admin/instances/{instance_id}/storage-attachments"
    granted = await admin_client.post(url, json={"file_storage_id": "share", "read_only": True})
    assert granted.status_code == 200, granted.text
    inspected = await admin_client.post(f"{url}/share/connection-info", json={})
    assert inspected.status_code == 200, inspected.text
    for response in (granted, inspected):
        assert response.headers["Cache-Control"] == "no-store"
        assert response.json()["access_id"] == "native-access-rule"
        assert response.json()["exports"] == ["192.0.2.1:/data"]
        assert "secret" not in response.json() and "access_key" not in response.json()
        assert "provider-private-ceph-key" not in response.text
    assert rules[0]["access_key"] == "provider-private-ceph-key"
    assert native_detail.server.metadata
    assert mock_conn._afterglow_authenticated_project_id == "fixed-admin-executor"
