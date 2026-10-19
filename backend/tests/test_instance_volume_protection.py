"""Instance HTTP orchestration uses real durable protection policies before success."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.compute import instances
from app.api.identity import admin_instances
from app.models.compute import InstanceInfo
from app.services import auto_backup, auto_snapshot, flavor_eligibility, volume_protection
from tests.conftest import make_mock_conn

PROJECT = "test-project-123"
TARGET = "target-protection-project"
VOLUME = "generated-boot-volume"
BASE = {"name": "protected-vm", "image_id": "image-1", "flavor_id": "flavor-1", "network_id": "network-1"}
ROUTES = ["/api/v1/instances", "/api/v1/instances/async", "/api/v1/admin/instances/async"]


def events(response):
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


@pytest.fixture
async def protection_cloud(monkeypatch, mock_conn):
    from app.services.cache import _get_redis

    target = make_mock_conn(TARGET)
    for conn in (mock_conn, target):
        conn.compute.servers.return_value = []
        conn.compute.get_server.return_value = SimpleNamespace(fault=None)
        conn.image.get_image.return_value = SimpleNamespace(properties={"os_type": "linux"})
        conn.block_storage.get_volume.return_value = SimpleNamespace(
            id=VOLUME, project_id=conn._afterglow_project_id, status="in-use", bootable=True
        )
    monkeypatch.setattr(admin_instances, "_make_admin_conn", lambda *_args: target)
    monkeypatch.setattr(instances.nova, "list_flavors", lambda _conn: [SimpleNamespace(id="flavor-1")])
    monkeypatch.setattr(instances.instance_orch, "resolve_availability_zones", AsyncMock(return_value=("nova", "nova")))
    monkeypatch.setattr(instances.instance_orch, "compute_effective_security_groups", AsyncMock(return_value=[]))
    monkeypatch.setattr(flavor_eligibility, "admit_flavor", AsyncMock(return_value=SimpleNamespace(gpu_requested=0)))
    release = AsyncMock()
    monkeypatch.setattr(flavor_eligibility, "release_admission", release)
    create_volume = MagicMock(return_value=SimpleNamespace(id=VOLUME))
    monkeypatch.setattr(instances.cinder, "create_volume_from_image", create_volume)
    monkeypatch.setattr(instances.cinder, "rename_volume", MagicMock())
    server = InstanceInfo(id="server-1", name="protected-vm", status="ACTIVE")
    create_server = MagicMock(return_value=server)
    monkeypatch.setattr(instances.nova, "create_server", create_server)
    monkeypatch.setattr(instances.neutron, "list_networks", lambda _conn: [])
    monkeypatch.setattr(instances.vm_cloud_init_library, "record_history", AsyncMock())
    monkeypatch.setattr(instances, "rec", AsyncMock())
    monkeypatch.setattr(admin_instances, "rec", AsyncMock())
    monkeypatch.setattr(instances, "invalidate", AsyncMock())
    monkeypatch.setattr(instances.cache_invalidation, "invalidate_mutation_count", AsyncMock())
    rollback = AsyncMock()
    monkeypatch.setattr(instances.instance_orch, "rollback_instance", rollback)
    # Exercise Lua against the suite's isolated Redis backend, not mocked registration.
    monkeypatch.setattr(auto_backup, "_get_redis", _get_redis)
    if hasattr(auto_snapshot, "_get_redis"):
        monkeypatch.setattr(auto_snapshot, "_get_redis", _get_redis)
    return SimpleNamespace(
        target=target, create_volume=create_volume, create_server=create_server, rollback=rollback, release=release
    )


def payload(route, **fields):
    body = {**BASE, **fields}
    if "/admin/" in route:
        body["project_id"] = TARGET
    return body


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize(
    "flags", [{"auto_snapshot": True}, {"auto_backup": True}, {"auto_snapshot": True, "auto_backup": True}]
)
async def test_protection_consent_rejected_before_cloud(admin_client, protection_cloud, route, flags):
    response = await admin_client.post(route, json=payload(route, **flags))
    assert response.status_code == 422
    protection_cloud.create_volume.assert_not_called()
    protection_cloud.create_server.assert_not_called()
    protection_cloud.release.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("flag", ["auto_snapshot", "auto_backup"])
async def test_reused_boot_volume_protection_flags_rejected(admin_client, protection_cloud, route, flag):
    body = payload(route, boot_volume_id="existing-boot", volume_protection_force=True, **{flag: True})
    body.pop("image_id")
    response = await admin_client.post(route, json=body)
    assert response.status_code == 422
    protection_cloud.create_volume.assert_not_called()
    protection_cloud.create_server.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("snapshot,backup", [(False, False), (True, False), (False, True), (True, True)])
async def test_generated_boot_policies_are_independent_and_durable_before_success(
    admin_client, protection_cloud, route, snapshot, backup
):
    response = await admin_client.post(
        route,
        json=payload(
            route, auto_snapshot=snapshot, auto_backup=backup, volume_protection_force=bool(snapshot or backup)
        ),
    )
    assert response.status_code == (200 if route.endswith("/async") else 201)
    if route.endswith("/async"):
        assert events(response)[-1]["step"] == "completed"
    pid = TARGET if "/admin/" in route else PROJECT
    for selected, get_config in (
        (snapshot, auto_snapshot.get_auto_snapshot_config),
        (backup, auto_backup.get_auto_backup_config),
    ):
        config = await get_config(pid, VOLUME)
        if not selected:
            assert config is None
            continue
        assert config["project_id"] == pid
        assert config["volume_id"] == VOLUME
        assert config["enabled"] is True
        assert config["force"] is True
        assert (config["max_daily"], config["max_weekly"], config["max_monthly"]) == (2, 2, 1)
        assert config["schedule_time"] == "03:00"
        assert config["timezone"] == "UTC"
        assert config["next_run_at"] is not None
    protection_cloud.release.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ROUTES)
async def test_lost_registration_ack_compensates_only_request_policies(
    admin_client, protection_cloud, monkeypatch, route
):
    actual = volume_protection.register_volume_protection

    async def applied_then_lost_ack(*args, **kwargs):
        await actual(*args, **kwargs)
        raise ConnectionError("registration acknowledgement lost")

    monkeypatch.setattr(instances, "register_volume_protection", applied_then_lost_ack)
    monkeypatch.setattr(admin_instances, "register_volume_protection", applied_then_lost_ack)
    response = await admin_client.post(
        route, json=payload(route, auto_snapshot=True, auto_backup=True, volume_protection_force=True)
    )
    if not route.endswith("/async"):
        assert response.status_code == 500
    else:
        assert response.status_code == 200
        assert events(response)[-1]["step"] == "failed"
        assert all(event["step"] != "completed" for event in events(response))
    pid = TARGET if "/admin/" in route else PROJECT
    assert await auto_backup.get_auto_backup_config(pid, VOLUME) is None
    assert await auto_snapshot.get_auto_snapshot_config(pid, VOLUME) is None
    assert protection_cloud.rollback.await_args.args[2] == VOLUME
    protection_cloud.release.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ROUTES)
async def test_registration_conflict_preserves_existing_policy(admin_client, protection_cloud, route):
    pid = TARGET if "/admin/" in route else PROJECT
    original = await auto_backup.enable_auto_backup(pid, VOLUME, max_daily=7)
    response = await admin_client.post(
        route, json=payload(route, auto_snapshot=True, auto_backup=True, volume_protection_force=True)
    )
    if route.endswith("/async"):
        assert events(response)[-1]["step"] == "failed"
    else:
        assert response.status_code != 201
    assert await auto_backup.get_auto_backup_config(pid, VOLUME) == original
    assert await auto_snapshot.get_auto_snapshot_config(pid, VOLUME) is None
    protection_cloud.rollback.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("route", [route for route in ROUTES if route.endswith("/async")])
async def test_registration_failure_rolls_back_new_attachment_volumes_not_reused_ones(
    admin_client, protection_cloud, monkeypatch, route
):
    monkeypatch.setattr(instances.cinder, "create_empty_volume", lambda *_args: SimpleNamespace(id="new-data"))
    fail = AsyncMock(side_effect=RuntimeError("policy storage unavailable"))
    monkeypatch.setattr(instances, "register_volume_protection", fail)
    monkeypatch.setattr(admin_instances, "register_volume_protection", fail)
    response = await admin_client.post(
        route,
        json=payload(
            route,
            auto_snapshot=True,
            volume_protection_force=True,
            additional_volume_ids=["existing-data"],
            new_volumes=[{"name": "data", "size_gb": 10}],
        ),
    )
    assert events(response)[-1]["step"] == "failed"
    assert protection_cloud.rollback.await_args.kwargs["additional_volume_ids"] == ["new-data"]


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ROUTES)
async def test_bookkeeping_failure_never_emits_completed_or_leaves_policies(
    admin_client, protection_cloud, monkeypatch, route
):
    activity = AsyncMock(side_effect=RuntimeError("audit unavailable"))

    # Fail only the success recorder; preserve the existing failure event path.
    async def record(*args, **kwargs):
        if kwargs["status"] == "success":
            await activity(*args, **kwargs)

    monkeypatch.setattr(instances, "rec", record)
    monkeypatch.setattr(admin_instances, "rec", record)
    response = await admin_client.post(
        route, json=payload(route, auto_snapshot=True, auto_backup=True, volume_protection_force=True)
    )
    if not route.endswith("/async"):
        assert response.status_code == 500
    else:
        assert events(response)[-1]["step"] == "failed"
        assert all(event["step"] != "completed" for event in events(response))
    pid = TARGET if "/admin/" in route else PROJECT
    assert await auto_backup.get_auto_backup_config(pid, VOLUME) is None
    assert await auto_snapshot.get_auto_snapshot_config(pid, VOLUME) is None
    protection_cloud.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_native_rollback_deletes_only_tracked_new_attachment_volumes(monkeypatch, mock_conn):
    from app.services import cinder, instance_orchestration, keystone, nova

    deleted = []
    monkeypatch.setattr(nova, "delete_server", lambda _conn, _id: None)
    monkeypatch.setattr(cinder, "delete_volume", lambda _conn, volume_id: deleted.append(volume_id))
    monkeypatch.setattr(keystone, "get_service_project_connection", lambda: mock_conn)
    await instance_orchestration.rollback_instance(
        mock_conn, "new-server", None, None, [], [], additional_volume_ids=["new-data"]
    )
    assert deleted == ["new-data"]


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ROUTES)
async def test_unselected_options_preserve_reused_boot_policies(admin_client, protection_cloud, monkeypatch, route):
    from app.models.storage import VolumeInfo

    pid = TARGET if "/admin/" in route else PROJECT
    backup = await auto_backup.enable_auto_backup(pid, VOLUME, max_daily=7)
    snapshot = await auto_snapshot.enable_auto_snapshot(pid, VOLUME, max_daily=9)
    monkeypatch.setattr(
        instances.cinder,
        "get_volume",
        lambda *_args: VolumeInfo(
            id=VOLUME, name="existing", status="available", size=64, bootable=True, attachments=[]
        ),
    )
    register = AsyncMock()
    monkeypatch.setattr(instances, "register_volume_protection", register)
    monkeypatch.setattr(admin_instances, "register_volume_protection", register)
    body = payload(route, boot_volume_id=VOLUME)
    body.pop("image_id")
    response = await admin_client.post(route, json=body)
    assert response.status_code == (200 if route.endswith("/async") else 201)
    if route.endswith("/async"):
        assert events(response)[-1]["step"] == "completed"
    register.assert_not_awaited()
    protection_cloud.create_volume.assert_not_called()
    assert await auto_backup.get_auto_backup_config(pid, VOLUME) == backup
    assert await auto_snapshot.get_auto_snapshot_config(pid, VOLUME) == snapshot


@pytest.mark.asyncio
@pytest.mark.parametrize("edited_kind", ["backup", "snapshot"])
async def test_explicit_edit_relinquishes_registration_ownership(protection_cloud, edited_kind):
    token = "registration-before-explicit-edit"
    await volume_protection.register_volume_protection(
        protection_cloud.target,
        TARGET,
        VOLUME,
        auto_backup=True,
        auto_snapshot=True,
        registration_id=token,
    )
    enable = auto_backup.enable_auto_backup if edited_kind == "backup" else auto_snapshot.enable_auto_snapshot
    get_config = (
        auto_backup.get_auto_backup_config if edited_kind == "backup" else auto_snapshot.get_auto_snapshot_config
    )
    peer_get = auto_snapshot.get_auto_snapshot_config if edited_kind == "backup" else auto_backup.get_auto_backup_config
    edited = await enable(TARGET, VOLUME, max_daily=11, force=True)
    assert "registration_id" not in edited
    await volume_protection.rollback_volume_protection(TARGET, VOLUME, token)
    assert await get_config(TARGET, VOLUME) == edited
    assert await peer_get(TARGET, VOLUME) is None
