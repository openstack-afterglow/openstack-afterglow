"""Exercise native password delivery and privacy through admin HTTP/SSE."""

from __future__ import annotations

import base64
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from openstack.block_storage.v3.volume import Volume
from openstack.compute.v2.server import Server

from app.api.identity import admin_instances
from app.models.compute import FlavorInfo
from app.services import (
    cinder,
    flavor_eligibility,
    github_ssh,
    instance_orchestration,
    keystone,
    nova,
    vm_cloud_init_library,
)
from tests.conftest import make_mock_conn

PATH = "/api/v1/admin/instances/async"
PROJECT = "target-password-project"
IMAGE = "target-image"
VOLUME = "target-volume"
SERVER = "11111111-2222-3333-4444-555555555555"
PASSWORD = "  P'ass$word`42‘’𐐀  "
ENCODED_PASSWORD = base64.b64encode(PASSWORD.encode("utf-8")).decode("ascii")
ACCOUNT = "Ops’'; Write-Output 'unsafe'; #𐐀"
WINDOWS = {
    "os_type": " Windows ",
    "windows_initial_password_method": "nova-adminpass-configdrive",
    "os_admin_user": ACCOUNT,
}


def payload(source="image", **extra):
    return {
        "name": "admin-password-vm",
        "project_id": PROJECT,
        "flavor_id": "small",
        "network_id": "target-network",
        ("image_id" if source == "image" else "boot_volume_id"): IMAGE if source == "image" else VOLUME,
        "admin_pass": PASSWORD,
        **extra,
    }


def events(response):
    assert response.status_code == 200, response.text
    assert "text/event-stream" in response.headers["content-type"]
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


@pytest.fixture
def boundary(monkeypatch, mock_conn):
    """Fake cloud I/O, but retain metadata preflight, native planning and Nova."""
    target = make_mock_conn(PROJECT)
    image = SimpleNamespace(id=IMAGE, name="Not inferred from this name", properties=dict(WINDOWS))
    volume = Volume.new(
        id=VOLUME,
        name="Linux misleading volume name",
        status="available",
        size=80,
        project_id=PROJECT,
        is_bootable=True,
        volume_image_metadata=dict(WINDOWS),
        attachments=[],
        volume_type="fast",
    )
    target.image.get_image.return_value = image
    target.block_storage.get_volume.return_value = volume
    server = Server.new(
        id=SERVER,
        name="admin-password-vm",
        status="ACTIVE",
        addresses={},
        metadata={},
        flavor={"id": "small"},
        image={},
        project_id=PROJECT,
    )
    target.compute.create_server.return_value = server
    target.compute.wait_for_server.return_value = server
    target.compute.get_server.return_value = server
    connection = MagicMock(return_value=target)
    monkeypatch.setattr(keystone, "get_admin_connection_for_project", connection)
    flavor = FlavorInfo(id="small", name="small", vcpus=2, ram=2048, disk=0, extra_specs={})
    monkeypatch.setattr(nova, "list_flavors", lambda conn: [flavor])
    admission = AsyncMock(return_value=SimpleNamespace(gpu_requested={}))
    release = AsyncMock()
    monkeypatch.setattr(flavor_eligibility, "admit_flavor", admission)
    monkeypatch.setattr(flavor_eligibility, "release_admission", release)
    name = MagicMock(side_effect=lambda conn, requested: requested)
    monkeypatch.setattr(admin_instances, "ensure_unique_instance_name", name)
    zones = AsyncMock(return_value=("nova", "nova"))
    network = AsyncMock(return_value="target-network")
    monkeypatch.setattr(instance_orchestration, "resolve_availability_zones", zones)
    monkeypatch.setattr(instance_orchestration, "resolve_default_network", network)
    create_volume = MagicMock(return_value=SimpleNamespace(id="created-boot"))
    rename = MagicMock()
    monkeypatch.setattr(cinder, "create_volume_from_image", create_volume)
    monkeypatch.setattr(cinder, "rename_volume", rename)
    monkeypatch.setattr(admin_instances.neutron, "list_networks", lambda conn: [])
    verify = AsyncMock(return_value={"login": "OctoCat"})
    monkeypatch.setattr(github_ssh, "verify_and_record", verify)
    generate_userdata = MagicMock(wraps=admin_instances.cloudinit.generate_userdata)
    compose_userdata = MagicMock(wraps=admin_instances.cloudinit.compose_userdata)
    monkeypatch.setattr(admin_instances.cloudinit, "generate_userdata", generate_userdata)
    monkeypatch.setattr(admin_instances.cloudinit, "compose_userdata", compose_userdata)
    history = AsyncMock()
    activity = AsyncMock()
    monkeypatch.setattr(vm_cloud_init_library, "record_history", history)
    monkeypatch.setattr(admin_instances, "rec", activity)
    native_delete_server = nova.delete_server
    delete_server = MagicMock()
    delete_volume = MagicMock()
    monkeypatch.setattr(nova, "delete_server", delete_server)
    monkeypatch.setattr(cinder, "delete_volume", delete_volume)
    monkeypatch.setattr(keystone, "get_service_project_connection", MagicMock(side_effect=RuntimeError("unavailable")))
    # A caller-project image would wrongly select Linux. Only target scope is valid.
    mock_conn.image.get_image.return_value = SimpleNamespace(properties={"os_type": "linux"})
    mock_conn.block_storage.get_volume.return_value = Volume.new(
        id=VOLUME,
        project_id="test-project-123",
        volume_image_metadata={"os_type": "linux"},
    )
    return SimpleNamespace(
        target=target,
        caller=mock_conn,
        image=image,
        volume=volume,
        server=server,
        connection=connection,
        flavor=flavor,
        admission=admission,
        release=release,
        name=name,
        zones=zones,
        network=network,
        create_volume=create_volume,
        rename=rename,
        verify=verify,
        generate_userdata=generate_userdata,
        compose_userdata=compose_userdata,
        history=history,
        activity=activity,
        delete_server=delete_server,
        delete_volume=delete_volume,
        native_delete_server=native_delete_server,
    )


def no_mutation(b):
    b.admission.assert_not_awaited()
    b.name.assert_not_called()
    b.zones.assert_not_awaited()
    b.network.assert_not_awaited()
    b.verify.assert_not_awaited()
    b.generate_userdata.assert_not_called()
    b.compose_userdata.assert_not_called()
    b.create_volume.assert_not_called()
    b.rename.assert_not_called()
    b.target.compute.create_server.assert_not_called()
    b.target.compute.create_volume_attachment.assert_not_called()
    b.history.assert_not_awaited()
    b.activity.assert_not_awaited()
    b.release.assert_not_awaited()
    b.target.close.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["image", "volume"])
async def test_admin_windows_password_uses_scoped_metadata_and_native_nova(admin_client, boundary, source, caplog):
    response = await admin_client.post(PATH, json=payload(source))
    stream = events(response)
    completed = [event for event in stream if event["step"] == "completed"]
    assert len(completed) == 1
    assert completed[0]["instance_id"] == SERVER
    assert not any(event["step"] == "failed" for event in stream)
    body = boundary.target.compute.create_server.call_args.kwargs
    assert body["config_drive"] is True
    assert body["adminPass"] == PASSWORD
    assert "user_data" not in body
    assert "metadata" not in body
    assert "key_name" not in body
    boundary.generate_userdata.assert_not_called()
    boundary.compose_userdata.assert_not_called()
    assert body["block_device_mapping_v2"][0]["uuid"] == ("created-boot" if source == "image" else VOLUME)
    assert body["block_device_mapping_v2"][0]["delete_on_termination"] is False
    boundary.connection.assert_called_once_with(PROJECT)
    boundary.caller.image.get_image.assert_not_called()
    boundary.caller.block_storage.get_volume.assert_not_called()
    if source == "image":
        boundary.target.image.get_image.assert_called_once_with(IMAGE)
        boundary.target.block_storage.get_volume.assert_not_called()
    else:
        assert all(call.args == (VOLUME,) for call in boundary.target.block_storage.get_volume.call_args_list)
        boundary.target.block_storage.get_volume.assert_called()
        boundary.target.image.get_image.assert_not_called()
        boundary.create_volume.assert_not_called()
    boundary.admission.assert_awaited_once()
    boundary.delete_server.assert_not_called()
    boundary.delete_volume.assert_not_called()
    boundary.activity.assert_awaited_once()
    assert boundary.activity.await_args.kwargs["status"] == "success"
    assert boundary.activity.await_args.kwargs["resource_id"] == SERVER
    boundary.history.assert_not_awaited()
    boundary.verify.assert_not_awaited()
    boundary.release.assert_awaited_once()
    boundary.target.close.assert_called_once()
    visible = response.text + caplog.text + repr(boundary.activity.await_args_list)
    for secret in (
        PASSWORD,
        ENCODED_PASSWORD,
        repr(PASSWORD),
        json.dumps(PASSWORD),
        json.dumps(PASSWORD, ensure_ascii=False),
    ):
        assert secret not in visible


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["image", "volume"])
@pytest.mark.parametrize("conflict", ["userdata", "github", "data_mounts"])
async def test_admin_windows_password_conflicts_reject_before_side_effects(admin_client, boundary, source, conflict):
    extras = {
        "userdata": {"userdata": "#cloud-config\npackages: [curl]"},
        "github": {"github_username": "octocat"},
        "data_mounts": {"data_mounts": [{"file_storage_id": "share-1", "mount_point": "/data/share"}]},
    }[conflict]
    boundary.flavor.extra_specs = {"pci_passthrough:alias": "nvidia_gpu:1"}
    response = await admin_client.post(PATH, json=payload(source, **extras))
    assert response.status_code == 400, response.text
    no_mutation(boundary)


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["image", "volume"])
@pytest.mark.parametrize(
    "metadata",
    [
        {},
        {"os_type": "windows"},
        {**WINDOWS, "windows_initial_password_method": "native-nova"},
        {**WINDOWS, "windows_initial_password_method": "cloudbase-user-data"},
        {**WINDOWS, "windows_initial_password_method": "nova-adminpass-configdrive "},
        {**WINDOWS, "windows_initial_password_method": " nova-adminpass-configdrive"},
        {**WINDOWS, "windows_initial_password_method": "NOVA-ADMINPASS-CONFIGDRIVE"},
        {**WINDOWS, "windows_initial_password_method": None},
        {**WINDOWS, "os_admin_user": None},
        {**WINDOWS, "os_admin_user": 123},
        {**WINDOWS, "os_admin_user": ""},
        {**WINDOWS, "os_admin_user": "  "},
        {**WINDOWS, "os_admin_user": "Bad\nAccount"},
        {**WINDOWS, "os_admin_user": "Bad\x7fAccount"},
        {**WINDOWS, "os_admin_user": "Bad\x85Account"},
        "not-a-metadata-map",
    ],
)
async def test_admin_password_metadata_rejection_closes_target_without_mutation(
    admin_client, boundary, source, metadata
):
    if source == "image":
        boundary.image.properties = metadata
    else:
        boundary.volume.volume_image_metadata = metadata
    response = await admin_client.post(PATH, json=payload(source))
    assert response.status_code == 400, response.text
    assert PASSWORD not in response.text
    no_mutation(boundary)


@pytest.mark.asyncio
async def test_admin_password_rejects_foreign_volume_metadata(admin_client, boundary):
    boundary.volume.project_id = "other-project"
    response = await admin_client.post(PATH, json=payload("volume"))
    assert response.status_code == 400
    no_mutation(boundary)


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["image", "volume"])
async def test_admin_password_provider_metadata_error_is_private_and_closes(admin_client, boundary, source, caplog):
    reader = boundary.target.image.get_image if source == "image" else boundary.target.block_storage.get_volume
    reader.side_effect = RuntimeError(f"provider credential {PASSWORD}")
    response = await admin_client.post(PATH, json=payload(source))
    assert response.status_code == 400
    assert PASSWORD not in response.text + caplog.text
    no_mutation(boundary)


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["image", "volume"])
@pytest.mark.parametrize("http_error", [False, True])
async def test_admin_password_unexpected_metadata_error_closes_without_disclosure(
    admin_client,
    boundary,
    caplog,
    source,
    http_error,
):
    def metadata_error():
        if http_error:
            raise HTTPException(status_code=500, detail=f"unexpected metadata failure {PASSWORD}")
        raise RuntimeError(f"unexpected metadata failure {PASSWORD}")

    class BrokenImage:
        @property
        def properties(self):
            metadata_error()

    class BrokenVolume:
        project_id = PROJECT

        def to_dict(self, **kwargs):
            metadata_error()

    if source == "image":
        boundary.target.image.get_image.return_value = BrokenImage()
    else:
        boundary.target.block_storage.get_volume.return_value = BrokenVolume()
    response = await admin_client.post(PATH, json=payload(source))
    assert response.status_code == 400
    assert PASSWORD not in response.text + caplog.text
    no_mutation(boundary)


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["image", "volume"])
@pytest.mark.parametrize("error_source", ["exception", "fault"])
@pytest.mark.parametrize("encoding", ["clear", "encoded"])
@pytest.mark.parametrize("operating_system", ["windows", "linux"])
async def test_admin_password_upstream_error_and_fault_rollback_are_private(
    admin_client,
    boundary,
    source,
    error_source,
    encoding,
    operating_system,
    caplog,
):
    leaked = []
    if operating_system == "linux":
        boundary.image.properties = {"os_type": "linux"}
        boundary.volume.volume_image_metadata = {"os_type": "linux"}

    def failed_wait(server, **kwargs):
        body = boundary.target.compute.create_server.call_args.kwargs
        assert body["adminPass"] == PASSWORD
        if operating_system == "windows":
            assert body["config_drive"] is True
            assert "user_data" not in body
            secret = body["adminPass"] if encoding == "clear" else ENCODED_PASSWORD
        else:
            secret = body["adminPass"] if encoding == "clear" else body["user_data"]
        leaked.append(secret)
        if error_source == "fault":
            server.fault = {"message": f"provider fault echoed {secret}"}
            raise RuntimeError(f"Server:{SERVER} entered ERROR")
        raise RuntimeError(f"Server:{SERVER} provider echoed {secret}")

    boundary.target.compute.wait_for_server.side_effect = failed_wait
    response = await admin_client.post(
        PATH,
        json=payload(source, userdata="#cloud-config\npackages: [curl]" if operating_system == "linux" else None),
    )
    failed = [event for event in events(response) if event["step"] == "failed"]
    assert len(failed) == 1
    assert not any(event["step"] == "completed" for event in events(response))
    boundary.target.compute.get_server.assert_called_once_with(SERVER)
    boundary.delete_server.assert_called_once()
    if source == "image":
        boundary.delete_volume.assert_called_once_with(boundary.target, "created-boot")
    else:
        boundary.delete_volume.assert_not_called()
    boundary.history.assert_not_awaited()
    boundary.release.assert_awaited_once()
    boundary.target.close.assert_called_once()
    assert boundary.activity.await_args.kwargs["status"] == "failed"
    visible = response.text + caplog.text + repr(boundary.activity.await_args_list)
    assert PASSWORD not in visible
    assert all(secret not in visible for secret in leaked)
    assert len(leaked) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["image", "volume"])
async def test_admin_linux_password_preserves_native_nova_and_custom_history(admin_client, boundary, source):
    boundary.image.properties = {"os_type": "linux"}
    boundary.volume.volume_image_metadata = {"os_type": "linux"}
    custom = "#cloud-config\npackages: [curl]\n"
    response = await admin_client.post(PATH, json=payload(source, userdata=custom))
    assert any(event["step"] == "completed" for event in events(response))
    body = boundary.target.compute.create_server.call_args.kwargs
    assert body["adminPass"] == PASSWORD
    assert base64.b64decode(body["user_data"], validate=True).decode("utf-8") == custom
    assert "config_drive" not in body
    boundary.generate_userdata.assert_not_called()
    boundary.compose_userdata.assert_called_once_with(None, custom, None)
    boundary.history.assert_awaited_once_with(user_id="test-user-123", content=custom)
    boundary.target.close.assert_called_once()
    assert PASSWORD not in response.text + repr(boundary.activity.await_args_list)


@pytest.mark.asyncio
async def test_admin_absent_password_keeps_github_preflight_before_connection(admin_client, boundary):
    from app.services.github_ssh import GitHubSshUnavailable

    boundary.verify.side_effect = GitHubSshUnavailable("GitHub public keys unavailable")
    response = await admin_client.post(PATH, json=payload(admin_pass=None, github_username="octocat"))
    assert response.status_code == 503
    boundary.connection.assert_not_called()
    boundary.target.image.get_image.assert_not_called()
    boundary.target.block_storage.get_volume.assert_not_called()
    boundary.target.compute.create_server.assert_not_called()


@pytest.mark.asyncio
async def test_admin_absent_password_does_not_require_windows_metadata(admin_client, boundary):
    boundary.image.properties = {}
    response = await admin_client.post(PATH, json=payload(admin_pass=None))
    assert any(event["step"] == "completed" for event in events(response))
    body = boundary.target.compute.create_server.call_args.kwargs
    assert "adminPass" not in body
    assert "user_data" not in body
    assert "config_drive" not in body
    boundary.target.image.get_image.assert_not_called()
    boundary.target.block_storage.get_volume.assert_not_called()
    boundary.target.close.assert_called_once()


@pytest.mark.asyncio
async def test_admin_password_connection_creation_error_is_private(admin_client, boundary, caplog):
    boundary.connection.side_effect = RuntimeError(f"connection credentials {PASSWORD}")
    response = await admin_client.post(PATH, json=payload())
    assert response.status_code == 500
    assert response.json() == {"detail": "내부 서버 오류"}
    assert PASSWORD not in response.text + caplog.text
    boundary.target.image.get_image.assert_not_called()
    boundary.admission.assert_not_awaited()
    boundary.target.compute.create_server.assert_not_called()


@pytest.mark.asyncio
async def test_admin_password_readonly_flavor_error_closes_without_disclosure(
    admin_client, boundary, monkeypatch, caplog
):
    monkeypatch.setattr(nova, "list_flavors", MagicMock(side_effect=RuntimeError(f"flavor failure {PASSWORD}")))
    response = await admin_client.post(PATH, json=payload())
    assert response.status_code == 400
    assert PASSWORD not in response.text + caplog.text
    no_mutation(boundary)


@pytest.mark.asyncio
async def test_admin_password_preflight_close_error_does_not_replace_safe_rejection(admin_client, boundary, caplog):
    boundary.image.properties = {"os_type": "windows"}
    boundary.target.close.side_effect = RuntimeError(f"close failure {PASSWORD}")
    response = await admin_client.post(PATH, json=payload())
    assert response.status_code == 400
    assert PASSWORD not in response.text + caplog.text
    no_mutation(boundary)


@pytest.mark.asyncio
@pytest.mark.parametrize("encoding", ["clear", "encoded"])
async def test_admin_password_rollback_cleanup_errors_stay_private(admin_client, boundary, encoding, caplog):
    leaked = []

    def failed_wait(server, **kwargs):
        body = boundary.target.compute.create_server.call_args.kwargs
        assert body["adminPass"] == PASSWORD
        assert body["config_drive"] is True
        assert "user_data" not in body
        secret = body["adminPass"] if encoding == "clear" else ENCODED_PASSWORD
        leaked.append(secret)
        boundary.delete_server.side_effect = RuntimeError(f"delete server echoed {secret}")
        boundary.delete_volume.side_effect = RuntimeError(f"delete volume echoed {secret}")
        raise RuntimeError(f"Server:{SERVER} entered ERROR")

    boundary.target.compute.wait_for_server.side_effect = failed_wait
    response = await admin_client.post(PATH, json=payload())
    assert any(event["step"] == "failed" for event in events(response))
    boundary.delete_server.assert_called_once()
    boundary.delete_volume.assert_called_once_with(boundary.target, "created-boot")
    boundary.release.assert_awaited_once()
    boundary.target.close.assert_called_once()
    visible = response.text + caplog.text + repr(boundary.activity.await_args_list)
    assert PASSWORD not in visible
    assert all(secret not in visible for secret in leaked)
    assert len(leaked) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("encoding", ["clear", "encoded"])
async def test_admin_password_ignored_provider_delete_error_is_private_at_debug(
    admin_client,
    boundary,
    monkeypatch,
    encoding,
    caplog,
):
    caplog.set_level("DEBUG", logger="app.services.nova")
    monkeypatch.setattr(nova, "delete_server", boundary.native_delete_server)
    leaked = []

    def failed_wait(server, **kwargs):
        body = boundary.target.compute.create_server.call_args.kwargs
        assert body["adminPass"] == PASSWORD
        assert body["config_drive"] is True
        assert "user_data" not in body
        secret = body["adminPass"] if encoding == "clear" else ENCODED_PASSWORD
        leaked.append(secret)
        boundary.target.compute.delete_server.side_effect = RuntimeError(f"404 provider echoed {secret}")
        raise RuntimeError(f"Server:{SERVER} entered ERROR")

    boundary.target.compute.wait_for_server.side_effect = failed_wait
    response = await admin_client.post(PATH, json=payload())
    assert any(event["step"] == "failed" for event in events(response))
    boundary.target.compute.delete_server.assert_called_once_with(SERVER, force=True)
    boundary.delete_volume.assert_called_once_with(boundary.target, "created-boot")
    boundary.target.close.assert_called_once()
    visible = response.text + caplog.text + repr(boundary.activity.await_args_list)
    assert PASSWORD not in visible
    assert all(secret not in visible for secret in leaked)
    assert len(leaked) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["image", "volume"])
@pytest.mark.parametrize(
    "extra_specs",
    [
        {"pci_passthrough:alias": "nvidia_gpu:1"},
        {":category": "gpu"},
    ],
)
async def test_admin_windows_gpu_password_skips_linux_bootstrap(
    admin_client,
    boundary,
    source,
    extra_specs,
):
    boundary.flavor.extra_specs = extra_specs
    boundary.admission.return_value = SimpleNamespace(gpu_requested={"nvidia_gpu": 1})
    response = await admin_client.post(PATH, json=payload(source))
    stream = events(response)
    assert stream[-1]["step"] == "completed"
    assert stream[-1]["instance_id"] == SERVER
    body = boundary.target.compute.create_server.call_args.kwargs
    assert "user_data" not in body
    boundary.generate_userdata.assert_not_called()
    boundary.compose_userdata.assert_not_called()
    assert not any(event["step"] == "userdata_generating" for event in stream)
    assert body["config_drive"] is True
    assert body["adminPass"] == PASSWORD
    assert "metadata" not in body
    boundary.admission.assert_awaited_once()
    boundary.release.assert_awaited_once()
    boundary.history.assert_not_awaited()
    boundary.verify.assert_not_awaited()
    boundary.delete_server.assert_not_called()
    boundary.delete_volume.assert_not_called()
    boundary.target.close.assert_called_once()


@pytest.mark.asyncio
async def test_admin_linux_password_github_rate_limit_preserves_retry_contract(admin_client, boundary):
    boundary.image.properties = {"os_type": "linux"}
    boundary.verify.side_effect = github_ssh.GitHubSshRateLimited(retry_after=17)
    response = await admin_client.post(PATH, json=payload(github_username="octocat"))
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "17"
    assert PASSWORD not in response.text
    boundary.target.close.assert_called_once()
    boundary.target.compute.create_server.assert_not_called()
