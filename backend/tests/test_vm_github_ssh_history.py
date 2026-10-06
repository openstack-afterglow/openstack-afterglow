from __future__ import annotations

import base64
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.compute.instances import _verify_github_ssh
from app.api.union import layer_public
from app.models.compute import CreateInstanceRequest
from app.services import github_ssh, nova
from tests.conftest import make_mock_conn
from tests.test_common_libraries_squashfs import _artifact, _FakeScalarResult, _FakeSession

_BASE_PAYLOAD = {
    "name": "github-vm",
    "image_id": "img-1",
    "flavor_id": "flavor-1",
    "network_id": "net-1",
    "github_username": "octocat",
}


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/api/v1/instances", "/api/v1/instances/async"])
async def test_user_create_rejects_unverified_github_before_openstack_mutation(client, path):
    error = github_ssh.GitHubSshInvalid("GitHub 계정에 공개 SSH 키가 없습니다.")
    with (
        patch("app.services.github_ssh.verify_and_record", AsyncMock(side_effect=error)) as verify,
        patch("app.api.compute.instances.cinder.create_volume_from_image") as create_volume,
        patch("app.api.compute.instances.nova.create_server") as create_server,
    ):
        response = await client.post(path, json=_BASE_PAYLOAD)

    assert response.status_code == 422
    assert response.json() == {"detail": "GitHub 계정에 공개 SSH 키가 없습니다."}
    verify.assert_awaited_once_with(user_id="test-user-123", username="octocat")
    create_volume.assert_not_called()
    create_server.assert_not_called()


@pytest.mark.asyncio
async def test_admin_create_rejects_unverified_github_before_target_connection(admin_client):
    error = github_ssh.GitHubSshUnavailable("GitHub 공개키 조회를 사용할 수 없습니다.")
    payload = {**_BASE_PAYLOAD, "project_id": "target-project-abc"}
    with (
        patch("app.services.github_ssh.verify_and_record", AsyncMock(side_effect=error)),
        patch("app.api.identity.admin_instances._make_admin_conn") as make_admin_conn,
        patch("app.api.identity.admin_instances.nova.create_server") as create_server,
    ):
        response = await admin_client.post("/api/v1/admin/instances/async", json=payload)

    assert response.status_code == 503
    make_admin_conn.assert_not_called()
    create_server.assert_not_called()


@pytest.mark.asyncio
async def test_public_squashfs_consume_rejects_unverified_github_before_database_or_openstack(monkeypatch):
    error = github_ssh.GitHubSshInvalid("GitHub 계정에 공개 SSH 키가 없습니다.")
    factory = MagicMock()
    monkeypatch.setattr(layer_public, "get_session_factory", lambda: factory)
    verify = AsyncMock(side_effect=error)
    monkeypatch.setattr(github_ssh, "verify_and_record", verify)
    run_consume = AsyncMock()
    monkeypatch.setattr("app.services.layer_build.run_layer_consume", run_consume)

    with pytest.raises(HTTPException) as exc:
        await layer_public.consume_public_squashfs(
            layer_public.PublicLayerConsumeRequest(
                artifact_ids=[1],
                server_name="github-vm",
                flavor_id="flavor-1",
                github_username="octocat",
            ),
            conn=MagicMock(_afterglow_project_id="project-a", _afterglow_authenticated_project_id="project-a"),
            token_info={"project_id": "project-a", "user_id": "user-a"},
        )

    assert exc.value.status_code == 422
    verify.assert_awaited_once_with(user_id="user-a", username="octocat")
    factory.assert_not_called()
    run_consume.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_preflight_replaces_input_with_canonical_github_login():
    req = CreateInstanceRequest(**_BASE_PAYLOAD)
    profile = {
        "id": 583231,
        "login": "OctoCat",
        "name": None,
        "public_email": None,
        "html_url": "https://github.com/OctoCat",
        "has_public_keys": True,
        "verified_at": "2026-09-20T00:00:00+00:00",
    }
    with patch("app.services.github_ssh.verify_and_record", AsyncMock(return_value=profile)) as verify:
        updated = await _verify_github_ssh(req, token_info={"user_id": "user-a", "project_id": "project-a"})

    assert updated.github_username == "OctoCat"
    assert req.github_username == "octocat"
    verify.assert_awaited_once_with(user_id="user-a", username="octocat")


def _persist_sdk_servers(conn):
    """Fake only SDK persistence; Nova creation and all projections stay real."""
    servers = {}

    def create_server(**body):
        server = SimpleNamespace(
            id="server-1",
            name=body["name"],
            status="ACTIVE",
            addresses={},
            metadata=dict(body.get("metadata", {})),
            image={"id": body["image_id"]} if body.get("image_id") else {},
            flavor={"id": body.get("flavor_id", body.get("flavorRef"))},
            created_at="2026-01-01T00:00:00Z",
            key_name=body.get("key_name"),
            user_id="test-user-123",
            project_id=conn._afterglow_project_id,
            compute_host=None,
        )
        servers[server.id] = server
        return server

    conn.compute.create_server.side_effect = create_server
    conn.compute.wait_for_server.side_effect = lambda server, **_kwargs: server
    conn.compute.get_server.side_effect = servers.__getitem__
    conn.compute.servers.side_effect = lambda **_kwargs: list(servers.values())
    conn.compute.volume_attachments.return_value = []
    conn.session.get.return_value.json.return_value = {
        "quota_set": {key: {"limit": -1, "in_use": 0} for key in ("instances", "cores", "ram")}
    }
    return servers


@pytest.fixture
def creation_boundary(monkeypatch, mock_conn, available_flavor_capacity):
    """Reuse creation resource boundaries without mocking metadata or Nova."""
    from app.api.compute import instances
    from app.api.identity import admin_instances
    from app.services import instance_orchestration, vm_cloud_init_library

    servers = _persist_sdk_servers(mock_conn)
    mock_conn._afterglow_authenticated_project_id = mock_conn._afterglow_project_id
    verify = AsyncMock(return_value={"login": "OctoCat"})
    monkeypatch.setattr(github_ssh, "verify_and_record", verify)
    monkeypatch.setattr(instance_orchestration, "resolve_availability_zones", AsyncMock(return_value=("", "")))
    monkeypatch.setattr(instance_orchestration, "compute_effective_security_groups", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        nova,
        "list_flavors",
        lambda _conn: [SimpleNamespace(id="flavor-1", name="small", is_gpu=False, extra_specs={}, vcpus=2, ram=2048)],
    )
    monkeypatch.setattr(
        instances.cinder,
        "create_volume_from_image",
        lambda *_args, **_kwargs: SimpleNamespace(id="boot-vol"),
    )
    monkeypatch.setattr(instances.cinder, "rename_volume", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(instances.neutron, "list_networks", lambda *_args: [])
    monkeypatch.setattr(instances.glance, "list_images", lambda _conn: [])
    monkeypatch.setattr(vm_cloud_init_library, "record_history", AsyncMock())
    for api in (instances, admin_instances):
        monkeypatch.setattr(api, "rec", AsyncMock())
    monkeypatch.setattr(instances, "invalidate", AsyncMock())
    monkeypatch.setattr(instances.cache_invalidation, "invalidate_mutation_count", AsyncMock())
    return SimpleNamespace(servers=servers, verify=verify)


def _completed_instance_id(response):
    assert response.status_code == 200, response.text
    assert "text/event-stream" in response.headers["content-type"]
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    assert not [event for event in events if event["step"] == "failed"], events
    completed = [event for event in events if event["step"] == "completed"]
    assert len(completed) == 1, events
    assert completed[0]["progress"] == 100
    return completed[0]["instance_id"]


def _assert_ssh_projection(info, *, github_login, key_name, metadata):
    assert info["ssh_access_mode"] == ("github" if github_login else None)
    assert info["github_login"] == github_login
    assert info["key_name"] == key_name
    assert info["metadata"] == metadata


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/api/v1/instances", "/api/v1/instances/async"])
@pytest.mark.parametrize("github_login,key_name", [("OctoCat", None), (None, "existing-keypair")])
async def test_user_creation_persists_ssh_source_in_real_nova_response(
    client, mock_conn, creation_boundary, path, github_login, key_name
):
    payload = {
        **_BASE_PAYLOAD,
        "github_username": "octocat" if github_login else None,
        "key_name": key_name,
        "scheduling": "ha",
    }
    response = await client.post(path, json=payload)
    if path.endswith("/async"):
        server_id = _completed_instance_id(response)
    else:
        assert response.status_code == 201, response.text
        server_id = response.json()["id"]

    metadata = {"scheduling": "ha", "HA_Enabled": "True"}
    if github_login:
        metadata.update({"afterglow_ssh_access_mode": "github", "afterglow_github_login": "OctoCat"})
        creation_boundary.verify.assert_awaited_once_with(user_id="test-user-123", username="octocat")
    else:
        creation_boundary.verify.assert_not_awaited()
    assert creation_boundary.servers[server_id].metadata == metadata
    assert mock_conn.compute.create_server.call_args.kwargs.get("key_name") == key_name
    mock_conn.compute.wait_for_server.assert_called_once_with(
        creation_boundary.servers[server_id], status="ACTIVE", wait=600
    )
    if not path.endswith("/async"):
        _assert_ssh_projection(response.json(), github_login=github_login, key_name=key_name, metadata=metadata)
        assert response.json()["scheduling"] == "ha"
    detail = await client.get(f"/api/v1/instances/{server_id}")
    assert detail.status_code == 200, detail.text
    _assert_ssh_projection(detail.json(), github_login=github_login, key_name=key_name, metadata=metadata)
    listing = await client.get("/api/v1/instances")
    assert listing.status_code == 200, listing.text
    assert [info["id"] for info in listing.json()] == [server_id]
    _assert_ssh_projection(listing.json()[0], github_login=github_login, key_name=key_name, metadata=metadata)


@pytest.mark.asyncio
@pytest.mark.parametrize("github_login,key_name", [("OctoCat", None), (None, "existing-keypair")])
async def test_admin_creation_persists_ssh_source_in_target_project(
    admin_client, monkeypatch, creation_boundary, github_login, key_name
):
    from app.api.deps import get_os_conn
    from app.api.identity import admin_instances
    from app.main import app

    target_conn = make_mock_conn("target-project-abc")
    servers = _persist_sdk_servers(target_conn)
    get_connection = MagicMock(return_value=target_conn)
    monkeypatch.setattr(admin_instances.keystone, "get_admin_connection_for_project", get_connection)
    response = await admin_client.post(
        "/api/v1/admin/instances/async",
        json={
            **_BASE_PAYLOAD,
            "project_id": "target-project-abc",
            "github_username": "octocat" if github_login else None,
            "key_name": key_name,
            "scheduling": "ha",
        },
    )
    server_id = _completed_instance_id(response)
    get_connection.assert_called_once_with("target-project-abc")
    metadata = {"scheduling": "ha", "HA_Enabled": "True"}
    if github_login:
        metadata.update({"afterglow_ssh_access_mode": "github", "afterglow_github_login": "OctoCat"})
        creation_boundary.verify.assert_awaited_once_with(user_id="test-user-123", username="octocat")
    else:
        creation_boundary.verify.assert_not_awaited()
    assert servers[server_id].metadata == metadata
    assert target_conn.compute.create_server.call_args.kwargs.get("key_name") == key_name
    target_conn.compute.wait_for_server.assert_called_once_with(servers[server_id], status="ACTIVE", wait=600)

    async def target_project_connection():
        yield target_conn

    monkeypatch.setitem(app.dependency_overrides, get_os_conn, target_project_connection)
    detail = await admin_client.get(f"/api/v1/instances/{server_id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["project_id"] == "target-project-abc"
    assert detail.json()["scheduling"] == "ha"
    _assert_ssh_projection(detail.json(), github_login=github_login, key_name=key_name, metadata=metadata)
    listing = await admin_client.get("/api/v1/instances")
    assert listing.status_code == 200, listing.text
    assert [info["id"] for info in listing.json()] == [server_id]
    _assert_ssh_projection(listing.json()[0], github_login=github_login, key_name=key_name, metadata=metadata)


@pytest.mark.asyncio
@pytest.mark.parametrize("github_login,key_name", [("OctoCat", None), (None, "existing-keypair")])
async def test_public_squashfs_creation_persists_ssh_source_with_real_consume_and_nova(
    client, mock_conn, monkeypatch, creation_boundary, github_login, key_name
):
    from app.services import layer_build

    artifact = _artifact(id=1, name="root")
    added = []
    results = [_FakeScalarResult(rows=[artifact]), _FakeScalarResult(rows=[artifact])]
    monkeypatch.setattr(layer_public, "get_session_factory", lambda: lambda: _FakeSession(results, added))
    share_conn = MagicMock()
    monkeypatch.setattr(layer_public, "get_service_project_connection", AsyncMock(return_value=share_conn))
    monkeypatch.setattr(
        layer_build,
        "resolve_layer_consume_resource_snapshot",
        AsyncMock(
            return_value={
                "network": {"id": "net-1", "name": "network"},
                "flavor": {"id": "flavor-1", "name": "small"},
                "openstack.service_project": {"id": "service", "name": "service"},
            }
        ),
    )
    mock_conn.image.get_image.return_value = SimpleNamespace(
        id="img-24",
        name="ubuntu-24.04",
        status="active",
        checksum="sum",
        os_hash_algo="sha512",
        os_hash_value="hash",
    )
    public_key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITest existing-keypair"
    mock_conn.compute.get_keypair.return_value = SimpleNamespace(public_key=public_key)
    update = AsyncMock()
    monkeypatch.setattr(layer_build, "_update_consume_db", update)
    monkeypatch.setattr(layer_build.neutron, "create_port", lambda *_args: {"id": "port-1", "fixed_ip": "10.0.0.5"})
    monkeypatch.setattr(layer_build.manila, "list_access_rules", lambda *_args: [])
    monkeypatch.setattr(layer_build.manila, "ensure_nfs_access_rule", lambda *_args, **_kwargs: {"access_id": "rule-1"})
    monkeypatch.setattr(layer_build.manila, "get_export_locations", lambda *_args: ["10.0.0.1:/share"])
    monkeypatch.setattr(layer_build, "_wait_for_consume_health", AsyncMock(return_value=True))
    monkeypatch.setattr(layer_public, "invalidate", AsyncMock())

    response = await client.post(
        "/api/v1/libraries/squashfs/consume",
        json={
            "artifact_ids": [1],
            "server_name": "github-vm",
            "flavor_id": "flavor-1",
            "network_id": "net-1",
            "github_username": "octocat" if github_login else None,
            "key_name": key_name,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"consume_id": 41, "server_id": "server-1", "status": "active", "ready": True}
    assert len(added) == 1
    assert added[0].project_id == "test-project-123"
    assert added[0].artifact_ids == [1]
    metadata = {
        "union_type": "layer-consumer",
        "layer_profile": added[0].profile_name,
        "ubuntu_base": "ubuntu-24.04",
        "base_image_id": "img-24",
        "afterglow_managed": "true",
    }
    if github_login:
        metadata.update({"afterglow_ssh_access_mode": "github", "afterglow_github_login": "OctoCat"})
        creation_boundary.verify.assert_awaited_once_with(user_id="test-user-123", username="octocat")
        mock_conn.compute.get_keypair.assert_not_called()
    else:
        creation_boundary.verify.assert_not_awaited()
        mock_conn.compute.get_keypair.assert_called_once_with("existing-keypair")
    assert creation_boundary.servers["server-1"].metadata == metadata
    update.assert_any_await(41, server_id="server-1")
    update.assert_any_await(41, status="active", completed=True)
    sdk_body = mock_conn.compute.create_server.call_args.kwargs
    assert "key_name" not in sdk_body  # Squashfs keypairs still become guest authorized keys.
    rendered = base64.b64decode(sdk_body["user_data"]).decode()
    assert ("gh:OctoCat" if github_login else public_key) in rendered
    detail = await client.get("/api/v1/instances/server-1")
    assert detail.status_code == 200, detail.text
    _assert_ssh_projection(detail.json(), github_login=github_login, key_name=None, metadata=metadata)
    listing = await client.get("/api/v1/instances")
    assert listing.status_code == 200, listing.text
    assert [info["id"] for info in listing.json()] == ["server-1"]
    _assert_ssh_projection(listing.json()[0], github_login=github_login, key_name=None, metadata=metadata)
