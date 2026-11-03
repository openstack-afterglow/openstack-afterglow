from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest
from openstack.compute.v2.server import Server
from openstack.compute.v2.volume_attachment import VolumeAttachment

from app.services.mcp_control_plane import storage

PROJECT = "project-a"
SERVER = "server-a"
VOLUME = "volume-a"


@pytest.fixture
def cloud(monkeypatch):
    state = SimpleNamespace(
        server={
            "id": SERVER,
            "project_id": PROJECT,
            "status": "ACTIVE",
            "name": "vm",
            "availability_zone": "nova",
            "root_device_name": "/dev/sda",
        },
        volume={
            "id": VOLUME,
            "project_id": PROJECT,
            "name": "data",
            "description": "",
            "status": "available",
            "size": 10,
            "attachments": [],
            "is_multiattach": False,
            "availability_zone": "nova",
            "metadata": {"secret": "never-return"},
        },
        nova=[],
        events=[],
        writes=[],
        fail_after_write=False,
    )

    def get_server(server_id):
        assert server_id == SERVER
        state.events.append("server-read")
        return deepcopy(state.server)

    def get_volume(volume_id):
        assert volume_id == VOLUME
        state.events.append("volume-read")
        return deepcopy(state.volume)

    def raw_get(path, **kwargs):
        if path == f"/servers/{SERVER}":
            body = {"server": get_server(SERVER)}
        elif path == f"/volumes/{VOLUME}":
            body = {"volume": get_volume(VOLUME)}
        elif path == f"/servers/{SERVER}/os-volume_attachments":
            state.events.append("attachments-read")
            body = {"volumeAttachments": deepcopy(state.nova)}
        else:
            raise AssertionError(f"Unexpected native read: {path}")
        return SimpleNamespace(status_code=200, json=lambda: body)

    def record(kind, *args, **kwargs):
        assert state.events[-1] == "fence"
        state.events.append(kind)
        state.writes.append((kind, args, kwargs))
        if state.fail_after_write:
            raise RuntimeError("uncertain native write")

    def update(volume_id, **attributes):
        record("update", volume_id, **attributes)
        state.volume.update(attributes)
        return {"id": volume_id, "metadata": {"secret": "never-return"}}

    def extend(volume_id, *, size):
        record("extend", volume_id, size=size)

    def attach(server_id, **attributes):
        record("attach", server_id, **attributes)
        item = {
            "id": VOLUME,
            "volume_id": VOLUME,
            "server_id": SERVER,
            "attachment_id": "attachment-a",
            "device": "/dev/vda",
        }
        state.nova = [item]
        state.volume["status"] = "in-use"
        state.volume["attachments"] = [
            {
                "id": VOLUME,
                "attachment_id": "attachment-a",
                "server_id": SERVER,
                "volume_id": VOLUME,
                "device": "/dev/vda",
            }
        ]
        return deepcopy(item)

    def detach(server, volume_id, *, ignore_missing):
        assert isinstance(server, Server)
        assert server.id == SERVER and volume_id == VOLUME and ignore_missing is False
        record("detach", server.id, volume_id, ignore_missing=ignore_missing)

    state.conn = SimpleNamespace(
        compute=SimpleNamespace(
            get=raw_get,
            get_server=get_server,
            create_volume_attachment=attach,
            delete_volume_attachment=detach,
        ),
        block_storage=SimpleNamespace(get=raw_get, get_volume=get_volume, update_volume=update, extend_volume=extend),
    )
    monkeypatch.setattr(storage, "check_mutation_dispatch", lambda: state.events.append("fence"))
    return state


def attached(cloud, *, device="/dev/vda"):
    cloud.volume["status"] = "in-use"
    cloud.volume["attachments"] = [
        {
            "id": VOLUME,
            "attachment_id": "attachment-a",
            "server_id": SERVER,
            "volume_id": VOLUME,
            "device": device,
        }
    ]
    cloud.nova = [
        {
            "id": VOLUME,
            "volume_id": VOLUME,
            "server_id": SERVER,
            "attachment_id": "attachment-a",
            "device": device,
        }
    ]


@pytest.mark.asyncio
async def test_metadata_preview_readonly_and_request_redacts_provider_output(cloud):
    kwargs = dict(project_id=PROJECT, volume_id=VOLUME, attributes={"name": "renamed", "description": ""})
    preview = await storage.preview_project_volume_update(cloud.conn, **kwargs)
    assert preview["attributes"] == kwargs["attributes"]
    assert not cloud.writes and "fence" not in cloud.events
    result = await storage.request_project_volume_update(cloud.conn, **kwargs)
    assert result["name"] == "renamed" and result["requested_action"] == "update"
    assert set(result) == {"id", "name", "status", "size_gb", "created_at", "requested_action"}
    assert cloud.writes == [("update", (VOLUME,), {"name": "renamed", "description": ""})]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "attributes",
    [
        {},
        {"size": 30},
        {"name": None},
        {"description": None},
        {"name": " "},
        {"name": "x" * 256},
        {"description": "x" * 1025},
    ],
)
async def test_metadata_internal_callers_cannot_bypass_attribute_contract(cloud, attributes):
    with pytest.raises(storage.McpStorageError):
        await storage.request_project_volume_update(
            cloud.conn, project_id=PROJECT, volume_id=VOLUME, attributes=attributes
        )
    assert not cloud.writes


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["available", "in-use"])
async def test_metadata_updates_allow_only_stable_volume_states(cloud, status):
    cloud.volume["status"] = status
    result = await storage.request_project_volume_update(
        cloud.conn, project_id=PROJECT, volume_id=VOLUME, attributes={"description": "new"}
    )
    assert result["status"] == status


@pytest.mark.asyncio
async def test_metadata_request_revalidates_after_preview(cloud):
    kwargs = dict(project_id=PROJECT, volume_id=VOLUME, attributes={"name": "new"})
    await storage.preview_project_volume_update(cloud.conn, **kwargs)
    cloud.volume["status"] = "deleting"
    with pytest.raises(storage.McpStorageError):
        await storage.request_project_volume_update(cloud.conn, **kwargs)
    assert not cloud.writes


@pytest.mark.asyncio
async def test_offline_extend_is_one_native_action_without_polling(cloud):
    kwargs = dict(project_id=PROJECT, volume_id=VOLUME, size_gb=20)
    preview = await storage.preview_project_volume_extend(cloud.conn, **kwargs)
    assert preview["requested_size_gb"] == 20 and not cloud.writes
    cloud.events.clear()
    result = await storage.request_project_volume_extend(cloud.conn, **kwargs)
    assert result["size_gb"] == 10 and result["requested_size_gb"] == 20
    assert cloud.events == ["volume-read", "fence", "extend"]
    assert cloud.writes == [("extend", (VOLUME,), {"size": 20})]


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [True, 0, 10, 9, 16385, "20", 20.5])
async def test_extend_refuses_invalid_or_nonincreasing_size(cloud, size):
    with pytest.raises(storage.McpStorageError):
        await storage.request_project_volume_extend(cloud.conn, project_id=PROJECT, volume_id=VOLUME, size_gb=size)
    assert not cloud.writes


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        {"status": "in-use"},
        {"status": "extending"},
        {"attachments": None},
        {"attachments": [{"server_id": SERVER}]},
        {"id": "another-volume"},
        {"project_id": "foreign"},
        {"tenant_id": "foreign"},
        {"os-vol-tenant-attr:tenant_id": "foreign"},
    ],
)
async def test_extend_refuses_unowned_ambiguous_or_attached_volume(cloud, change):
    cloud.volume.update(change)
    with pytest.raises(storage.McpStorageError):
        await storage.request_project_volume_extend(cloud.conn, project_id=PROJECT, volume_id=VOLUME, size_gb=20)
    assert not cloud.writes


@pytest.mark.asyncio
async def test_attach_preview_and_request_do_not_choose_guest_device(cloud):
    kwargs = dict(project_id=PROJECT, server_id=SERVER, volume_id=VOLUME)
    preview = await storage.preview_project_server_volume_attach(cloud.conn, **kwargs)
    assert preview["attachment_id"] is None and preview["server_status"] == "ACTIVE"
    assert not cloud.writes
    result = await storage.request_project_server_volume_attach(cloud.conn, **kwargs)
    assert result == {
        "server_id": SERVER,
        "volume_id": VOLUME,
        "attachment_id": "attachment-a",
        "device": "/dev/vda",
        "requested_action": "attach_volume",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "target,change",
    [
        ("server", {"project_id": "foreign"}),
        ("server", {"tenant_id": "foreign"}),
        ("server", {"id": "other"}),
        ("server", {"status": "BUILD"}),
        ("server", {"availability_zone": "other-zone"}),
        ("volume", {"is_multiattach": True}),
        ("volume", {"is_multiattach": None}),
        ("volume", {"multiattach": True}),
        ("volume", {"status": "in-use"}),
        ("volume", {"attachments": [{"server_id": SERVER}]}),
        ("volume", {"project_id": "foreign"}),
        ("volume", {"id": "other"}),
    ],
)
async def test_attach_refuses_foreign_ineligible_and_contradictory_state(cloud, target, change):
    getattr(cloud, target).update(change)
    with pytest.raises(storage.McpStorageError):
        await storage.request_project_server_volume_attach(
            cloud.conn, project_id=PROJECT, server_id=SERVER, volume_id=VOLUME
        )
    assert not cloud.writes


@pytest.mark.asyncio
async def test_attach_postwrite_owner_uncertainty_is_not_replayed_or_rolled_back(cloud):
    original = cloud.conn.compute.create_volume_attachment

    def uncertain(*args, **kwargs):
        response = original(*args, **kwargs)
        cloud.volume["project_id"] = "foreign"
        return response

    cloud.conn.compute.create_volume_attachment = uncertain
    with pytest.raises(storage.McpStorageError):
        await storage.request_project_server_volume_attach(
            cloud.conn, project_id=PROJECT, server_id=SERVER, volume_id=VOLUME
        )
    assert [item[0] for item in cloud.writes] == ["attach"]


@pytest.mark.asyncio
async def test_attach_refuses_sdk_seeded_identity_without_native_list_corroboration(cloud):
    def seed_only(server_id, **kwargs):
        assert server_id == SERVER
        cloud.writes.append(("attach", (server_id,), kwargs))
        return VolumeAttachment.existing(server_id=SERVER, volume_id=VOLUME, id=VOLUME)

    cloud.conn.compute.create_volume_attachment = seed_only
    with pytest.raises(storage.McpStorageError, match="corroborated"):
        await storage.request_project_server_volume_attach(
            cloud.conn, project_id=PROJECT, server_id=SERVER, volume_id=VOLUME
        )
    assert len(cloud.writes) == 1


@pytest.mark.asyncio
async def test_windows_scsi_root_does_not_block_actual_vda_data_disk_detach(cloud):
    attached(cloud, device="/dev/vda")
    cloud.volume["is_bootable"] = True  # Image-derived data disks need not be the actual boot disk.
    cloud.server["attached_volumes"] = [{"id": "root-volume"}, {"id": VOLUME}]
    preview = await storage.preview_project_server_volume_detach(
        cloud.conn, project_id=PROJECT, server_id=SERVER, volume_id=VOLUME
    )
    assert preview["device"] == "/dev/vda" and not cloud.writes
    cloud.events.clear()
    result = await storage.request_project_server_volume_detach(
        cloud.conn, project_id=PROJECT, server_id=SERVER, volume_id=VOLUME
    )
    assert result["requested_action"] == "detach_volume"
    assert "server_status" not in result and "volume_status" not in result
    assert cloud.events[-2:] == ["fence", "detach"]
    assert cloud.writes == [("detach", (SERVER, VOLUME), {"ignore_missing": False})]


@pytest.mark.asyncio
@pytest.mark.parametrize("root", ["/dev/sda", "/dev/vda", "/dev/xvda"])
async def test_actual_root_is_never_detachable_regardless_of_linux_device_convention(cloud, root):
    attached(cloud, device=root)
    cloud.server["root_device_name"] = root
    with pytest.raises(storage.McpStorageError, match="boot/root"):
        await storage.request_project_server_volume_detach(
            cloud.conn, project_id=PROJECT, server_id=SERVER, volume_id=VOLUME
        )
    assert not cloud.writes


@pytest.mark.asyncio
async def test_missing_root_identity_refuses_even_vdb_named_disk(cloud):
    attached(cloud, device="/dev/vdb")
    cloud.server.pop("root_device_name")
    with pytest.raises(storage.McpStorageError, match="ambiguous"):
        await storage.request_project_server_volume_detach(
            cloud.conn, project_id=PROJECT, server_id=SERVER, volume_id=VOLUME
        )
    assert not cloud.writes


@pytest.mark.asyncio
@pytest.mark.parametrize("boot_index,allowed", [(0, False), (1, True), (-1, True), (True, False), ("1", False)])
async def test_explicit_boot_index_can_prove_data_disk_when_root_device_is_hidden(cloud, boot_index, allowed):
    attached(cloud)
    cloud.server.pop("root_device_name")
    cloud.server["attached_volumes"] = [{"id": VOLUME, "boot_index": boot_index}]
    if allowed:
        await storage.request_project_server_volume_detach(
            cloud.conn, project_id=PROJECT, server_id=SERVER, volume_id=VOLUME
        )
        assert len(cloud.writes) == 1
    else:
        with pytest.raises(storage.McpStorageError):
            await storage.request_project_server_volume_detach(
                cloud.conn, project_id=PROJECT, server_id=SERVER, volume_id=VOLUME
            )
        assert not cloud.writes


@pytest.mark.asyncio
async def test_server_boot_index_blocks_detach_even_when_root_name_looks_like_another_disk(cloud):
    attached(cloud)
    cloud.server["attached_volumes"] = [{"id": VOLUME, "boot_index": 0}]
    with pytest.raises(storage.McpStorageError, match="boot/root"):
        await storage.request_project_server_volume_detach(
            cloud.conn, project_id=PROJECT, server_id=SERVER, volume_id=VOLUME
        )
    assert not cloud.writes


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        "foreign-server",
        "foreign-volume",
        "multiattach",
        "multiple-bindings",
        "missing-binding",
        "missing-nova",
        "different-device",
        "different-id",
        "volume-alias",
        "server-alias",
        "root-alias",
        "duplicate-device",
        "server-inventory",
        "transitional",
    ],
)
async def test_detach_requires_unique_consistent_native_binding(cloud, case):
    attached(cloud)
    if case == "foreign-server":
        cloud.volume["attachments"][0]["server_id"] = "foreign"
    elif case == "foreign-volume":
        cloud.volume["project_id"] = "foreign"
    elif case == "multiattach":
        cloud.volume["is_multiattach"] = True
    elif case == "multiple-bindings":
        cloud.volume["attachments"].append(deepcopy(cloud.volume["attachments"][0]))
    elif case == "missing-binding":
        cloud.volume["attachments"] = []
    elif case == "missing-nova":
        cloud.nova = []
    elif case == "different-device":
        cloud.volume["attachments"][0]["device"] = "/dev/vdb"
    elif case == "different-id":
        cloud.nova[0]["attachment_id"] = "other"
    elif case == "volume-alias":
        cloud.nova[0]["volumeId"] = "other"
    elif case == "server-alias":
        cloud.nova[0]["server_uuid"] = "other"
    elif case == "root-alias":
        cloud.server["OS-EXT-SRV-ATTR:root_device_name"] = "/dev/vda"
    elif case == "duplicate-device":
        cloud.nova.append({"id": "other", "volume_id": "other", "device": "/dev/vda"})
    elif case == "server-inventory":
        cloud.server["attached_volumes"] = [{"id": "other"}]
    elif case == "transitional":
        cloud.volume["status"] = "detaching"
    with pytest.raises(storage.McpStorageError):
        await storage.request_project_server_volume_detach(
            cloud.conn, project_id=PROJECT, server_id=SERVER, volume_id=VOLUME
        )
    assert not cloud.writes


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["update", "extend", "attach", "detach"])
async def test_final_fence_prevents_every_native_volume_mutation(cloud, monkeypatch, action):
    def denied():
        raise RuntimeError("expired admission fence")

    monkeypatch.setattr(storage, "check_mutation_dispatch", denied)
    if action == "detach":
        attached(cloud)
    operation, kwargs = {
        "update": (storage.request_project_volume_update, {"attributes": {"name": "new"}}),
        "extend": (storage.request_project_volume_extend, {"size_gb": 20}),
        "attach": (storage.request_project_server_volume_attach, {"server_id": SERVER}),
        "detach": (storage.request_project_server_volume_detach, {"server_id": SERVER}),
    }[action]
    with pytest.raises(storage.McpStorageError):
        await operation(cloud.conn, project_id=PROJECT, volume_id=VOLUME, **kwargs)
    assert not cloud.writes


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["update", "extend", "attach", "detach"])
async def test_uncertain_native_write_never_retries(cloud, action):
    if action == "detach":
        attached(cloud)
    cloud.fail_after_write = True
    operation, kwargs = {
        "update": (storage.request_project_volume_update, {"attributes": {"name": "new"}}),
        "extend": (storage.request_project_volume_extend, {"size_gb": 20}),
        "attach": (storage.request_project_server_volume_attach, {"server_id": SERVER}),
        "detach": (storage.request_project_server_volume_detach, {"server_id": SERVER}),
    }[action]
    with pytest.raises(storage.McpStorageError):
        await operation(cloud.conn, project_id=PROJECT, volume_id=VOLUME, **kwargs)
    assert len(cloud.writes) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("resource", ["server", "volume"])
async def test_native_response_must_supply_identity_not_just_request_seed(cloud, resource):
    getattr(cloud, resource).pop("id")
    with pytest.raises(storage.McpStorageError):
        await storage.request_project_server_volume_attach(
            cloud.conn, project_id=PROJECT, server_id=SERVER, volume_id=VOLUME
        )
    assert not cloud.writes


@pytest.mark.asyncio
async def test_detach_rejects_cinder_volume_id_alias_contradiction(cloud):
    attached(cloud)
    cloud.volume["attachments"][0]["id"] = "another-volume"
    with pytest.raises(storage.McpStorageError, match="aliases contradict"):
        await storage.request_project_server_volume_detach(
            cloud.conn, project_id=PROJECT, server_id=SERVER, volume_id=VOLUME
        )
    assert not cloud.writes
