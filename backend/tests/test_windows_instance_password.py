"""Password admission and delivery through the public synchronous/SSE APIs."""

import base64
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from openstack.block_storage.v3.volume import Volume
from openstack.compute.v2.server import Server

from app.models.compute import CreateInstanceRequest, FlavorInfo
from app.services.instance_password import preflight_password

PASSWORD = "  quote'\"$(`exec`)\\secret safe’ ; $script:Injected=$true; #9!😀  "
ACCOUNT = "Operator' ‘smart’ $(`literal`) 😀"
SERVER_ID = "12345678-1234-1234-1234-123456789abc"
WINDOWS = {
    "os_type": " Windows ",
    "windows_initial_password_method": "nova-adminpass-configdrive",
    "os_admin_user": ACCOUNT,
}
BASE = {"name": "password-vm", "image_id": "image-1", "flavor_id": "flavor-1", "network_id": "network-1"}
ROUTES = ["/api/v1/instances", "/api/v1/instances/async"]


@pytest.fixture
def password_cloud(monkeypatch, mock_conn):
    """Keep the real admission, Linux bootstrap and Nova request conversion."""
    from app.api.compute import instances
    from app.services import flavor_eligibility

    state = SimpleNamespace(bodies=[], metadata=dict(WINDOWS))
    state.generate_userdata = MagicMock(wraps=instances.cloudinit.generate_userdata)
    monkeypatch.setattr(instances.cloudinit, "generate_userdata", state.generate_userdata)
    state.compose_userdata = MagicMock(wraps=instances.cloudinit.compose_userdata)
    monkeypatch.setattr(instances.cloudinit, "compose_userdata", state.compose_userdata)
    mock_conn.image.get_image.side_effect = lambda _id: SimpleNamespace(properties=state.metadata)
    mock_conn.compute.servers.return_value = []
    mock_conn.block_storage.get_volume.return_value = Volume(
        id="boot-existing",
        name="Existing",
        status="available",
        size=64,
        **{
            "bootable": "true",
            "volume_image_metadata": dict(WINDOWS),
            "os-vol-tenant-attr:tenant_id": "test-project-123",
        },
    )

    def create(**body):
        state.bodies.append(body)
        return Server(
            id=SERVER_ID,
            name=body["name"],
            status="ACTIVE",
            addresses={},
            metadata=body.get("metadata", {}),
            image={},
            flavor={"id": body["flavorRef"]},
            project_id="test-project-123",
        )

    mock_conn.compute.create_server.side_effect = create
    mock_conn.compute.wait_for_server.side_effect = lambda server, **_kw: server
    mock_conn.compute.get_server.return_value = Server(id=SERVER_ID, status="ERROR", fault={})
    monkeypatch.setattr(
        instances.nova,
        "list_flavors",
        lambda _conn: [FlavorInfo(id="flavor-1", name="m1.small", vcpus=2, ram=4096, disk=0)],
    )
    monkeypatch.setattr(instances.instance_orch, "resolve_availability_zones", AsyncMock(return_value=("nova", "nova")))
    monkeypatch.setattr(instances.instance_orch, "compute_effective_security_groups", AsyncMock(return_value=[]))
    state.admit = AsyncMock(return_value=SimpleNamespace(gpu_requested=0))
    monkeypatch.setattr(flavor_eligibility, "admit_flavor", state.admit)
    monkeypatch.setattr(flavor_eligibility, "release_admission", AsyncMock())
    state.create_volume = MagicMock(return_value=SimpleNamespace(id="boot-new"))
    monkeypatch.setattr(instances.cinder, "create_volume_from_image", state.create_volume)
    monkeypatch.setattr(instances.cinder, "rename_volume", MagicMock())
    monkeypatch.setattr(instances.neutron, "list_networks", lambda _conn: [])
    state.history = AsyncMock()
    monkeypatch.setattr(instances.vm_cloud_init_library, "record_history", state.history)
    state.activity = AsyncMock()
    monkeypatch.setattr(instances, "rec", state.activity)
    monkeypatch.setattr(instances, "invalidate", AsyncMock())
    monkeypatch.setattr(instances.cache_invalidation, "invalidate_mutation_count", AsyncMock())
    state.mounts = AsyncMock()
    monkeypatch.setattr(instances, "_prepare_data_mounts", state.mounts)
    state.github = AsyncMock(return_value={"login": "octocat"})
    monkeypatch.setattr(instances.github_ssh, "verify_and_record", state.github)
    state.rollback = AsyncMock()
    monkeypatch.setattr(instances.instance_orch, "rollback_instance", state.rollback)
    return state


def events(response):
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


def assert_password_not_exposed(response, password_cloud, caplog):
    external = (
        response.text
        + caplog.text
        + repr(password_cloud.activity.await_args_list)
        + json.dumps([body.get("metadata", {}) for body in password_cloud.bodies], ensure_ascii=False)
    )
    # JSON and repr escape quotes, backslashes and sometimes Unicode differently.
    secrets = {
        PASSWORD,
        repr(PASSWORD)[1:-1],
        ascii(PASSWORD)[1:-1],
        json.dumps(PASSWORD, ensure_ascii=False)[1:-1],
        json.dumps(PASSWORD, ensure_ascii=True)[1:-1],
        base64.b64encode(PASSWORD.encode("utf-8")).decode("ascii"),
    }
    for secret in secrets:
        assert secret not in external


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("source", ["image", "volume"])
async def test_windows_password_delivers_native_password_without_userdata_or_history(
    client, password_cloud, route, source, caplog
):
    payload = {**BASE, "admin_pass": PASSWORD}
    if source == "volume":
        payload.pop("image_id")
        payload["boot_volume_id"] = "boot-existing"
    response = await client.post(route, json=payload)
    assert response.status_code == (201 if route == ROUTES[0] else 200)
    (body,) = password_cloud.bodies
    assert body["config_drive"] is True
    assert body["adminPass"] == PASSWORD
    assert "user_data" not in body
    password_cloud.generate_userdata.assert_not_called()
    password_cloud.compose_userdata.assert_not_called()
    assert_password_not_exposed(response, password_cloud, caplog)
    password_cloud.history.assert_not_awaited()
    if route == ROUTES[1]:
        assert events(response)[-1]["instance_id"] == SERVER_ID
    if source == "volume":
        password_cloud.create_volume.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("property_keys", [[], ["windows_initial_password_method"]])
async def test_windows_password_accepts_native_metadata_from_fallback_image_fields(
    client, mock_conn, password_cloud, route, property_keys, caplog
):
    mock_conn.image.get_image.side_effect = None
    mock_conn.image.get_image.return_value = SimpleNamespace(
        properties={key: WINDOWS[key] for key in property_keys}, **WINDOWS
    )
    response = await client.post(route, json={**BASE, "admin_pass": PASSWORD})
    assert response.status_code == (201 if route == ROUTES[0] else 200)
    (body,) = password_cloud.bodies
    assert body["adminPass"] == PASSWORD
    assert body["config_drive"] is True
    assert "user_data" not in body
    password_cloud.generate_userdata.assert_not_called()
    password_cloud.compose_userdata.assert_not_called()
    password_cloud.history.assert_not_awaited()
    assert_password_not_exposed(response, password_cloud, caplog)


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize(
    "properties",
    [
        {"os_type": ""},
        {"os_admin_user": ""},
        {"windows_initial_password_method": "cloudbase-user-data"},
    ],
)
async def test_windows_password_rejects_explicit_invalid_properties_over_valid_fallback_image_fields(
    client, mock_conn, password_cloud, route, properties, caplog
):
    mock_conn.image.get_image.side_effect = None
    mock_conn.image.get_image.return_value = SimpleNamespace(properties=properties, **WINDOWS)
    response = await client.post(route, json={**BASE, "admin_pass": PASSWORD})
    assert response.status_code == 400
    password_cloud.admit.assert_not_awaited()
    password_cloud.create_volume.assert_not_called()
    password_cloud.mounts.assert_not_awaited()
    assert password_cloud.bodies == []
    assert_password_not_exposed(response, password_cloud, caplog)


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("source", ["image", "volume"])
@pytest.mark.parametrize(
    "os_type, custom",
    [("windows", None), ("linux", None), ("linux", "#cloud-config\npackages: [curl]\n")],
)
async def test_gpu_password_uses_native_windows_delivery_or_linux_bootstrap(
    client, mock_conn, password_cloud, monkeypatch, route, source, os_type, custom, caplog
):
    metadata = dict(WINDOWS) if os_type == "windows" else {"os_type": "linux"}
    password_cloud.metadata = metadata
    mock_conn.block_storage.get_volume.return_value.volume_image_metadata = metadata
    monkeypatch.setattr(
        "app.api.compute.instances.nova.list_flavors",
        lambda _conn: [
            FlavorInfo(
                id="flavor-1",
                name="gpu.a100x1_small",
                vcpus=4,
                ram=8192,
                disk=0,
                extra_specs={"pci_passthrough:alias": "a100:1"},
            )
        ],
    )
    password_cloud.admit.return_value = SimpleNamespace(gpu_requested={"a100": 1})
    payload = {**BASE, "admin_pass": PASSWORD}
    if custom:
        payload["userdata"] = custom
    if source == "volume":
        payload.pop("image_id")
        payload["boot_volume_id"] = "boot-existing"
    response = await client.post(route, json=payload)
    assert response.status_code == (201 if route == ROUTES[0] else 200), response.text
    (body,) = password_cloud.bodies
    assert body["flavorRef"] == "flavor-1"
    if os_type == "windows":
        assert "user_data" not in body
        assert body["config_drive"] is True
        assert body["adminPass"] == PASSWORD
        password_cloud.history.assert_not_awaited()
    else:
        from email import policy
        from email.parser import BytesParser

        userdata = base64.b64decode(body["user_data"], validate=True)
        message = BytesParser(policy=policy.default).parsebytes(userdata)
        parts = [part.get_content() for part in message.iter_parts()] if message.is_multipart() else [userdata.decode()]
        if custom:
            assert custom in parts
            password_cloud.history.assert_awaited_once_with(user_id="test-user-123", content=custom)
        assert any("install_gpu_monitoring.sh" in part for part in parts)
        assert body["adminPass"] == PASSWORD
        assert "config_drive" not in body
    assert_password_not_exposed(response, password_cloud, caplog)
    password_cloud.admit.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("source", ["image", "volume"])
@pytest.mark.parametrize(
    "metadata",
    [
        {"os_type": "windows", "os_admin_user": "Operator"},
        {**WINDOWS, "windows_initial_password_method": "cloudbase-user-data"},
        {**WINDOWS, "windows_initial_password_method": "nova"},
        {**WINDOWS, "windows_initial_password_method": "future-method"},
        {**WINDOWS, "windows_initial_password_method": None},
        {**WINDOWS, "windows_initial_password_method": "nova-adminpass-configdrive "},
        {**WINDOWS, "windows_initial_password_method": " nova-adminpass-configdrive"},
        {**WINDOWS, "windows_initial_password_method": "NOVA-ADMINPASS-CONFIGDRIVE"},
        {**WINDOWS, "os_admin_user": None},
        {**WINDOWS, "os_admin_user": "  "},
        {**WINDOWS, "os_admin_user": "Operator\nInjected"},
        {**WINDOWS, "os_admin_user": "Operator\x7f"},
        {**WINDOWS, "os_admin_user": "Operator\x85"},
    ],
)
async def test_windows_password_rejects_legacy_unknown_or_inexact_methods_and_invalid_accounts_before_mutation(
    client, mock_conn, password_cloud, route, source, metadata, caplog
):
    password_cloud.metadata = metadata
    mock_conn.block_storage.get_volume.return_value.volume_image_metadata = metadata
    payload = {**BASE, "admin_pass": PASSWORD}
    if source == "volume":
        payload.pop("image_id")
        payload["boot_volume_id"] = "boot-existing"
    response = await client.post(route, json=payload)
    assert response.status_code == 400
    password_cloud.admit.assert_not_awaited()
    password_cloud.create_volume.assert_not_called()
    password_cloud.mounts.assert_not_awaited()
    assert password_cloud.bodies == []
    assert_password_not_exposed(response, password_cloud, caplog)


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize(
    "extra",
    [
        {"userdata": "#cloud-config\npackages: [curl]"},
        {"github_username": "octocat"},
        {"data_mounts": [{"file_storage_id": "share-1", "mount_point": "/mnt/data"}]},
    ],
)
async def test_windows_password_rejects_linux_bootstrap_conflicts_before_effects(
    client, password_cloud, monkeypatch, route, extra
):
    monkeypatch.setattr(
        "app.api.compute.instances.nova.list_flavors",
        lambda _conn: [FlavorInfo(id="flavor-1", name="gpu.a100x1_small", vcpus=4, ram=8192, disk=0)],
    )
    payload = {**BASE, "admin_pass": PASSWORD, **extra}
    response = await client.post(route, json=payload)
    assert response.status_code == 400
    password_cloud.admit.assert_not_awaited()
    password_cloud.github.assert_not_awaited()
    password_cloud.create_volume.assert_not_called()
    password_cloud.mounts.assert_not_awaited()
    assert password_cloud.bodies == []


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("os_type", ["windows", "linux"])
@pytest.mark.parametrize(
    "failure",
    ["create-plaintext", "create-encoded", "wait-plaintext", "wait-encoded", "fault-plaintext", "fault-encoded"],
)
async def test_password_provider_failures_never_escape(
    admin_client, mock_conn, password_cloud, route, os_type, failure, caplog
):
    password_cloud.metadata = dict(WINDOWS) if os_type == "windows" else {"os_type": "linux"}
    leak = base64.b64encode(PASSWORD.encode("utf-8")).decode("ascii")
    error_text = PASSWORD if failure.endswith("plaintext") else leak
    if failure.startswith("create"):

        def create(**body):
            password_cloud.bodies.append(body)
            raise RuntimeError(f"Server:{SERVER_ID} {error_text}")

        mock_conn.compute.create_server.side_effect = create
    else:
        wait_text = "provider failed" if failure.startswith("fault") else error_text
        mock_conn.compute.wait_for_server.side_effect = RuntimeError(f"Server:{SERVER_ID} {wait_text}")
    fault = {"message": error_text} if failure.startswith("fault") else {}
    mock_conn.compute.get_server.return_value = Server(id=SERVER_ID, status="ERROR", fault=fault)
    response = await admin_client.post(route, json={**BASE, "admin_pass": PASSWORD})
    assert response.status_code == (500 if route == ROUTES[0] else 200)
    (body,) = password_cloud.bodies
    assert body["adminPass"] == PASSWORD
    if os_type == "windows":
        assert body["config_drive"] is True
        assert "user_data" not in body
    assert_password_not_exposed(response, password_cloud, caplog)
    if route == ROUTES[1]:
        assert events(response)[-1]["step"] == "failed"
    if failure.startswith("fault"):
        mock_conn.compute.get_server.assert_called_once_with(SERVER_ID)
    failed = [call.kwargs for call in password_cloud.activity.await_args_list if call.kwargs.get("status") == "failed"]
    assert len(failed) == 1
    assert PASSWORD not in failed[0]["error_message"]
    assert leak not in failed[0]["error_message"]


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ROUTES)
async def test_explicit_linux_native_password_preserves_custom_userdata_and_history(
    client, password_cloud, route, caplog
):
    password_cloud.metadata = {"os_type": "linux"}
    custom = "#cloud-config\npackages: [curl]\n"
    response = await client.post(
        route, json={**BASE, "admin_pass": PASSWORD, "userdata": custom, "key_name": "ssh-key"}
    )
    assert response.status_code in (200, 201)
    (body,) = password_cloud.bodies
    assert body["adminPass"] == PASSWORD
    assert "config_drive" not in body
    assert body["key_name"] == "ssh-key"
    assert_password_not_exposed(response, password_cloud, caplog)
    assert custom in base64.b64decode(body["user_data"]).decode()
    password_cloud.history.assert_awaited_once_with(user_id="test-user-123", content=custom)


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ROUTES)
async def test_absent_password_does_not_require_boot_metadata(client, mock_conn, password_cloud, route):
    mock_conn.image.get_image.side_effect = AssertionError("No password must not perform metadata lookup")
    response = await client.post(route, json=BASE)
    assert response.status_code in (200, 201)
    (body,) = password_cloud.bodies
    assert "adminPass" not in body
    assert "user_data" not in body
    assert "config_drive" not in body


@pytest.mark.parametrize("owner", [None, "other-project"])
def test_password_volume_metadata_cannot_cross_target_project(mock_conn, owner):
    from fastapi import HTTPException

    mock_conn.block_storage.get_volume.return_value = Volume(
        id="foreign-boot",
        **{"os-vol-tenant-attr:tenant_id": owner, "volume_image_metadata": WINDOWS},
    )
    req = CreateInstanceRequest(flavor_id="flavor-1", boot_volume_id="foreign-boot", admin_pass=PASSWORD)
    with pytest.raises(HTTPException) as error:
        preflight_password(mock_conn, req)
    assert error.value.status_code == 400
    assert PASSWORD not in str(error.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ROUTES)
async def test_absent_password_github_failure_precedes_cloud_lookups(client, mock_conn, password_cloud, route):
    from app.services.github_ssh import GitHubSshUnavailable

    password_cloud.github.side_effect = GitHubSshUnavailable("GitHub unavailable")
    response = await client.post(route, json={**BASE, "github_username": "octocat"})
    assert response.status_code == 503
    mock_conn.compute.servers.assert_not_called()
    mock_conn.image.get_image.assert_not_called()
    password_cloud.admit.assert_not_awaited()
    password_cloud.create_volume.assert_not_called()
    assert password_cloud.bodies == []


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ROUTES)
async def test_password_rejection_does_not_allocate_automatic_network(client, password_cloud, monkeypatch, route):
    allocated = []

    async def automatic_network(_conn, _settings):
        allocated.append("new-network")
        return allocated[-1]

    monkeypatch.setattr("app.services.instance_orchestration.resolve_default_network", automatic_network)
    password_cloud.metadata = {"os_type": "windows"}
    response = await client.post(route, json={**BASE, "network_id": None, "admin_pass": PASSWORD})
    assert response.status_code == 400
    assert allocated == []
    assert password_cloud.bodies == []


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ROUTES)
async def test_linux_password_github_rate_limit_preserves_retry_contract(client, password_cloud, route):
    from app.services.github_ssh import GitHubSshRateLimited

    password_cloud.metadata = {"os_type": "linux"}
    password_cloud.github.side_effect = GitHubSshRateLimited(retry_after=17)
    response = await client.post(route, json={**BASE, "admin_pass": PASSWORD, "github_username": "octocat"})
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "17"
    assert PASSWORD not in response.text
    assert password_cloud.bodies == []


@pytest.mark.asyncio
@pytest.mark.parametrize("status, bootable", [("in-use", True), ("available", False)])
async def test_password_volume_admission_failure_remains_bad_request(
    client, mock_conn, password_cloud, status, bootable
):
    mock_conn.block_storage.get_volume.return_value = Volume(
        id="boot-existing",
        name="Existing",
        status=status,
        size=64,
        **{
            "bootable": "true" if bootable else "false",
            "volume_image_metadata": WINDOWS,
            "os-vol-tenant-attr:tenant_id": "test-project-123",
        },
    )
    response = await client.post(
        ROUTES[0],
        json={
            "flavor_id": "flavor-1",
            "boot_volume_id": "boot-existing",
            "network_id": "network-1",
            "admin_pass": PASSWORD,
        },
    )
    assert response.status_code == 400
    assert PASSWORD not in response.text
    assert password_cloud.bodies == []
