from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

_UPPER_ID = "11111111-2222-3333-4444-555555555555"


def _decode_write_file(user_data: str, path: str) -> str:
    doc = yaml.safe_load(user_data)
    item = next(entry for entry in doc["write_files"] if entry["path"] == path)
    return base64.b64decode(item["content"]).decode()


def _snapshot() -> dict:
    return {
        "network": {"id": "snapshot-network", "name": "network"},
        "flavor": {"id": "snapshot-flavor", "name": "flavor"},
        "openstack.service_project": {"id": "service-project", "name": "service"},
    }


@pytest.mark.asyncio
async def test_run_layer_consume_requires_complete_snapshot_before_side_effects():
    from app.services.layer_build import run_layer_consume

    with (
        patch("app.services.layer_build._update_consume_db", new_callable=AsyncMock) as update,
        patch("app.services.layer_build.neutron.create_port") as create_port,
    ):
        with pytest.raises(RuntimeError, match="resource snapshot is incomplete"):
            await run_layer_consume(1, "profile", "consumer", "ignored", resource_snapshot={})

    update.assert_not_awaited()
    create_port.assert_not_called()


@pytest.mark.asyncio
async def test_run_layer_consume_uses_artifact_and_resource_snapshots():
    from app.services.layer_build import run_layer_consume

    connection = MagicMock()
    connection.compute.create_server.return_value = MagicMock(id="server-1")
    connection.image.get_image.return_value = SimpleNamespace(
        id="artifact-image", name="ubuntu-20.04", status="active", checksum="checksum-a"
    )
    artifact = {
        "id": 1,
        "name": "python311",
        "share_id": "artifact-share",
        "sqsh_filename": "python311-latest.sqsh",
        "ubuntu_base": "ubuntu-20.04",
        "base_image_id": "artifact-image",
        "base_image_checksum": "checksum-a",
    }
    with (
        patch("app.services.layer_build._update_consume_db", new_callable=AsyncMock),
        patch("app.services.layer_build.neutron.create_port", return_value={"id": "port-1", "fixed_ip": "10.0.0.5"}),
        patch("app.services.layer_build.manila.ensure_nfs_access_rule", return_value={"access_id": "rule-1"}),
        patch("app.services.layer_build.manila.get_export_locations", return_value=["10.0.0.1:/share"]),
        patch("app.services.layer_build.manila.list_access_rules", return_value=[]),
        patch("app.services.layer_build._wait_for_consume_health", new_callable=AsyncMock) as health,
    ):
        server_id = await run_layer_consume(
            consume_db_id=1,
            profile_name="profile",
            server_name="consumer",
            flavor_id="ignored",
            resource_snapshot=_snapshot(),
            compute_conn=connection,
            share_conn=connection,
            resolved_artifacts=[artifact],
        )

    assert server_id == "server-1"
    kwargs = connection.compute.create_server.call_args.kwargs
    assert kwargs["image_id"] == "artifact-image"
    assert kwargs["flavor_id"] == "snapshot-flavor"
    assert kwargs["metadata"]["base_image_id"] == "artifact-image"
    assert "block_device_mapping_v2" not in kwargs
    health.assert_awaited_once()


@pytest.mark.asyncio
async def test_root_consume_mounts_child_before_ancestor_and_waits_for_health():
    from app.services.layer_build import run_layer_consume

    conn = MagicMock()
    conn.image.get_image.return_value = SimpleNamespace(id="image-a", name="ubuntu-24.04", status="active")
    conn.compute.create_server.return_value = SimpleNamespace(id="server-1")
    ancestors = [
        {
            "id": 1,
            "parent_id": None,
            "name": "root",
            "kind": "dockerfile-root",
            "share_id": "share-1",
            "sqsh_filename": "root.sqsh",
            "ubuntu_base": "ubuntu-24.04",
            "base_image_id": "image-a",
            "blob_digest": "sha256:" + "c" * 64,
        },
        {
            "id": 2,
            "parent_id": 1,
            "name": "step",
            "kind": "dockerfile",
            "share_id": "share-2",
            "sqsh_filename": "step.sqsh",
            "ubuntu_base": "ubuntu-24.04",
            "base_image_id": "image-a",
            "blob_digest": "sha256:" + "d" * 64,
        },
    ]
    updates: list[dict] = []

    async def record(_id, **kwargs):
        updates.append(kwargs)

    with (
        patch("app.services.layer_build._update_consume_db", side_effect=record),
        patch("app.services.layer_build.neutron.create_port", return_value={"id": "port-1", "fixed_ip": "10.0.0.5"}),
        patch("app.services.layer_build.manila.list_access_rules", return_value=[]),
        patch("app.services.layer_build.manila.ensure_nfs_access_rule", return_value={"access_id": "rule-1"}),
        patch(
            "app.services.layer_build.manila.get_export_locations",
            side_effect=[
                ["10.0.0.1:/root", "10.0.0.3:/root"],
                ["10.0.0.2:/step", "10.0.0.4:/step"],
            ],
        ),
        patch(
            "app.services.layer_build.cinder.create_empty_volume", return_value=SimpleNamespace(id=_UPPER_ID)
        ) as create_upper,
        patch("app.services.layer_build._wait_for_consume_health", new_callable=AsyncMock) as health,
        patch("app.services.layer_build.layer_consume_ssh.remove_health_key", new_callable=AsyncMock),
    ):
        await run_layer_consume(
            1,
            "root",
            "vm",
            "flavor",
            resource_snapshot=_snapshot(),
            compute_conn=conn,
            share_conn=conn,
            resolved_artifacts=ancestors,
        )

    user_data = yaml.safe_load(base64.b64decode(conn.compute.create_server.call_args.kwargs["user_data"]))
    manifest = _decode_write_file(yaml.safe_dump(user_data), "/etc/afterglow/layers/root.conf")
    assert manifest == (
        "/mnt/nfs-layers/0|step.sqsh|sha256:" + "d" * 64 + "\n/mnt/nfs-layers/1|root.sqsh|sha256:" + "c" * 64 + "\n"
    )
    assert _decode_write_file(yaml.safe_dump(user_data), "/etc/afterglow/layers/root-exports.conf") == (
        "0|10.0.0.2:/step\n0|10.0.0.4:/step\n1|10.0.0.1:/root\n1|10.0.0.3:/root\n"
    )
    assert not any(item["path"] == "/etc/fstab" for item in user_data["write_files"])
    assert any(
        item["path"] == "/etc/initramfs-tools/scripts/local-bottom/afterglow-root" for item in user_data["write_files"]
    )
    assert updates[-2]["server_id"] == "server-1" and "status" not in updates[-2]
    assert updates[-1]["status"] == "active" and updates[-1]["completed"]
    create_upper.assert_called_once()
    server_kwargs = conn.compute.create_server.call_args.kwargs
    assert server_kwargs["image_id"] == "image-a"
    assert server_kwargs["block_device_mapping_v2"] == [
        {"boot_index": 0, "uuid": "image-a", "source_type": "image", "destination_type": "local"},
        {
            "boot_index": -1,
            "uuid": _UPPER_ID,
            "source_type": "volume",
            "destination_type": "volume",
            "delete_on_termination": True,
        },
    ]
    assert server_kwargs["metadata"]["union_upper_volume_id"] == _UPPER_ID
    auto = _decode_write_file(yaml.safe_dump(user_data), "/usr/local/bin/layer-activate-auto.sh")
    assert f"ROOT_UPPER_VOLUME_ID={_UPPER_ID}" in auto
    activate = _decode_write_file(yaml.safe_dump(user_data), "/usr/local/bin/layer-activate.sh")
    assert "CACHE_DIR=/run/afterglow/state/blobs" in activate
    assert "root-state.img" not in activate
    initrd = _decode_write_file(yaml.safe_dump(user_data), "/etc/initramfs-tools/scripts/local-bottom/afterglow-root")
    assert "root-upper-uuid" in initrd and "$state/blobs/${index}.sqsh" in initrd
    health.assert_awaited_once()
    assert ' "${CONSUMER_SSH_USER:-ubuntu}" /\n' in activate
    assert "etc/systemd/system/multi-user.target.wants/layer-health.service" in activate
    prereq_run = subprocess.run(
        ["sh", "-c", initrd, "afterglow-root", "prereqs"], env={}, capture_output=True, text=True
    )
    assert prereq_run.returncode == 0


@pytest.mark.asyncio
async def test_root_only_consume_prepares_boot_without_usr_overlay():
    from app.services.layer_build import run_layer_consume

    conn = MagicMock()
    conn.image.get_image.return_value = SimpleNamespace(id="image-a", name="ubuntu-24.04", status="active")
    conn.compute.create_server.return_value = SimpleNamespace(id="server-root")
    root = {
        "id": 1,
        "parent_id": None,
        "kind": "dockerfile-root",
        "name": "root",
        "share_id": "share-root",
        "sqsh_filename": "root.sqsh",
        "blob_digest": "sha256:" + "a" * 64,
        "base_image_id": "image-a",
        "ubuntu_base": "ubuntu-24.04",
    }
    with (
        patch("app.services.layer_build._update_consume_db", new_callable=AsyncMock),
        patch("app.services.layer_build.neutron.create_port", return_value={"id": "port-1", "fixed_ip": "10.0.0.5"}),
        patch("app.services.layer_build.manila.list_access_rules", return_value=[]),
        patch("app.services.layer_build.manila.ensure_nfs_access_rule", return_value={"access_id": "rule-1"}),
        patch("app.services.layer_build.manila.get_export_locations", return_value=["10.0.0.1:/root"]),
        patch("app.services.layer_build.cinder.create_empty_volume", return_value=SimpleNamespace(id=_UPPER_ID)),
        patch("app.services.layer_build._wait_for_consume_health", new_callable=AsyncMock),
        patch("app.services.layer_build.layer_consume_ssh.remove_health_key", new_callable=AsyncMock),
    ):
        await run_layer_consume(
            1,
            "root",
            "vm",
            "flavor",
            resource_snapshot=_snapshot(),
            compute_conn=conn,
            share_conn=conn,
            resolved_artifacts=[root],
        )
    config = yaml.safe_load(base64.b64decode(conn.compute.create_server.call_args.kwargs["user_data"]))
    assert config["power_state"]["mode"] == "reboot"
    assert _decode_write_file(yaml.safe_dump(config), "/etc/afterglow/layers/root.conf") == (
        "/mnt/nfs-layers/0|root.sqsh|sha256:" + "a" * 64 + "\n"
    )
    auto = _decode_write_file(yaml.safe_dump(config), "/usr/local/bin/layer-activate-auto.sh")
    assert "OVERLAY_TARGET=/ " in auto
    assert conn.compute.create_server.call_args.kwargs["block_device_mapping_v2"] == [
        {"boot_index": 0, "uuid": "image-a", "source_type": "image", "destination_type": "local"},
        {
            "boot_index": -1,
            "uuid": _UPPER_ID,
            "source_type": "volume",
            "destination_type": "volume",
            "delete_on_termination": True,
        },
    ]


@pytest.mark.asyncio
async def test_root_consume_nova_rejection_deletes_unclaimed_upper_volume():
    from app.services.layer_build import run_layer_consume

    conn = MagicMock()
    conn.image.get_image.return_value = SimpleNamespace(id="image-a", name="ubuntu-24.04", status="active")
    conn.compute.create_server.side_effect = RuntimeError("Nova rejected server")
    root = {
        "id": 1,
        "parent_id": None,
        "kind": "dockerfile-root",
        "name": "root",
        "share_id": "share-root",
        "sqsh_filename": "root.sqsh",
        "blob_digest": "sha256:" + "a" * 64,
        "base_image_id": "image-a",
        "ubuntu_base": "ubuntu-24.04",
    }
    with (
        patch("app.services.layer_build._update_consume_db", new_callable=AsyncMock),
        patch("app.services.layer_build.neutron.create_port", return_value={"id": "port-1", "fixed_ip": "10.0.0.5"}),
        patch("app.services.layer_build.neutron.delete_port") as delete_port,
        patch("app.services.layer_build.manila.list_access_rules", return_value=[]),
        patch("app.services.layer_build.manila.ensure_nfs_access_rule", return_value={"access_id": "rule-1"}),
        patch("app.services.layer_build.manila.get_export_locations", return_value=["10.0.0.1:/root"]),
        patch("app.services.layer_build.manila.revoke_access_rule") as revoke_rule,
        patch("app.services.layer_build.cinder.create_empty_volume", return_value=SimpleNamespace(id=_UPPER_ID)),
        patch("app.services.layer_build.cinder.delete_volume") as delete_upper,
    ):
        with pytest.raises(RuntimeError, match="Nova rejected"):
            await run_layer_consume(
                1,
                "root",
                "vm",
                "flavor",
                resource_snapshot=_snapshot(),
                compute_conn=conn,
                share_conn=conn,
                resolved_artifacts=[root],
            )
    delete_upper.assert_called_once_with(conn, _UPPER_ID)
    delete_port.assert_called_once_with(conn, "port-1")
    revoke_rule.assert_called_once_with(conn, "share-root", "rule-1")


def test_unavailable_cinder_upper_is_deleted_before_server_creation():
    from app.services.cinder import create_empty_volume

    conn = MagicMock()
    conn.block_storage.create_volume.return_value = SimpleNamespace(id=_UPPER_ID)
    conn.block_storage.wait_for_status.side_effect = TimeoutError("Cinder unavailable")
    with pytest.raises(TimeoutError, match="Cinder unavailable"):
        create_empty_volume(conn, "root-upper", 50)
    conn.block_storage.delete_volume.assert_called_once_with(_UPPER_ID, ignore_missing=True)


@pytest.mark.parametrize(
    "children,fstype,ambiguous",
    [
        (None, None, False),
        (None, "ext4", False),
        ([{"name": "vdc1"}], None, False),
        (None, None, True),
    ],
)
def test_guest_upper_device_requires_unique_empty_non_boot_disk(children, fstype, ambiguous, capsys):
    from app.services.layer_build import _ROOT_UPPER_DEVICE_PY

    serial = _UPPER_ID[:20]
    disks = [
        {"name": "vda", "type": "disk", "path": "/dev/vda", "serial": "boot"},
        {"name": "vdb", "type": "disk", "path": "/dev/vdb", "serial": serial, "children": children, "fstype": fstype},
    ]
    if ambiguous:
        disks.append({"name": "vdc", "type": "disk", "path": "/dev/vdc", "serial": serial})

    def fake_check_output(argv, *, text):
        if argv[0] == "findmnt":
            return "/dev/vda1\n"
        if argv[1] == "-n":
            return "vda\n"
        return json.dumps({"blockdevices": disks})

    with (
        patch.object(sys, "argv", ["layer-upper-device.py", _UPPER_ID]),
        patch("subprocess.check_output", side_effect=fake_check_output),
    ):
        if fstype or children or ambiguous:
            with pytest.raises(RuntimeError, match="not an empty|ambiguous"):
                exec(_ROOT_UPPER_DEVICE_PY, {"__name__": "__main__"})
        else:
            exec(_ROOT_UPPER_DEVICE_PY, {"__name__": "__main__"})
            assert capsys.readouterr().out.strip() == "/dev/vdb"


def test_root_identity_merge_keeps_dockerfile_users_and_adds_consumer_ssh(tmp_path):
    from app.services.layer_build import _ROOT_IDENTITY_MERGE_PY

    root = tmp_path / "root"
    upper = tmp_path / "upper"
    consumer = tmp_path / "consumer"
    for directory in (root / "etc", consumer / "etc", upper / "etc"):
        directory.mkdir(parents=True)
    files = {
        "passwd": (
            "root:x:0:0:root:/root:/bin/bash\napp:x:1001:1001:app:/srv/app:/bin/sh\n",
            "root:x:0:0:root:/root:/bin/bash\nworker:x:1002:1002:worker:/home/worker:/bin/bash\n",
        ),
        "shadow": ("root:!:1:0:99999:7:::\napp:!:1:0:99999:7:::\n", "root:!:1:0:99999:7:::\nworker:!:1:0:99999:7:::\n"),
        "group": ("root:x:0:\napp:x:1001:\nsudo:x:27:app\n", "root:x:0:\nworker:x:1002:\nsudo:x:27:worker\n"),
        "gshadow": ("root:!::\napp:!::\nsudo:!::app\n", "root:!::\nworker:!::\nsudo:!::worker\n"),
    }
    for name, (layer_data, consumer_data) in files.items():
        (root / "etc" / name).write_text(layer_data)
        (consumer / "etc" / name).write_text(consumer_data)
    subprocess.run(
        [sys.executable, "-c", _ROOT_IDENTITY_MERGE_PY, str(root), str(upper), "worker", str(consumer)], check=True
    )
    assert "app:x:1001:1001" in (upper / "etc/passwd").read_text()
    assert "worker:x:1002:1002" in (upper / "etc/passwd").read_text()
    assert "sudo:x:27:app,worker" in (upper / "etc/group").read_text()


@pytest.mark.asyncio
async def test_root_rejects_incomplete_ancestor_before_allocating_port():
    from app.services.layer_build import run_layer_consume

    root = {
        "id": 1,
        "parent_id": None,
        "name": "root",
        "kind": "dockerfile-root",
        "share_id": "share-1",
        "sqsh_filename": "root.sqsh",
        "blob_digest": "sha256:" + "a" * 64,
        "ubuntu_base": "ubuntu-24.04",
        "base_image_id": "image-a",
    }
    child = {
        "id": 3,
        "parent_id": 2,
        "name": "step",
        "kind": "dockerfile",
        "share_id": "share-3",
        "sqsh_filename": "step.sqsh",
        "ubuntu_base": "ubuntu-24.04",
        "base_image_id": "image-a",
    }
    with (
        patch("app.services.layer_build._update_consume_db", new_callable=AsyncMock),
        patch("app.services.layer_build.neutron.create_port") as port,
    ):
        with pytest.raises(RuntimeError, match="lineage is incomplete"):
            await run_layer_consume(
                1,
                "root",
                "vm",
                "flavor",
                resource_snapshot=_snapshot(),
                compute_conn=MagicMock(),
                resolved_artifacts=[root, child],
            )
    port.assert_not_called()


@pytest.mark.asyncio
async def test_consumer_waits_across_nova_active_and_reboot_until_guest_mount_signal():
    from app.services.layer_build import _wait_for_consume_health

    conn = MagicMock()
    conn.compute.get_server.side_effect = [SimpleNamespace(status=s) for s in ["ACTIVE", "SHUTOFF", "ACTIVE"]]
    with (
        patch(
            "app.services.layer_build.nova.get_console_output",
            side_effect=["", "", "::AFTERGLOW::SUCCESS::" + "a" * 32],
        ) as console,
        patch("app.services.layer_build.asyncio.sleep", new_callable=AsyncMock) as sleep,
    ):
        assert await _wait_for_consume_health(conn, "server-1", "a" * 32) is False
    assert console.call_count == 3
    assert sleep.await_count == 2


@pytest.mark.asyncio
async def test_consumer_guest_failure_cannot_become_ready():
    from app.services.layer_build import _wait_for_consume_health

    conn = MagicMock()
    conn.compute.get_server.return_value = SimpleNamespace(status="ACTIVE")
    with patch("app.services.layer_build.nova.get_console_output", return_value="::AFTERGLOW::FAILURE::" + "b" * 32):
        with pytest.raises(RuntimeError, match="activation failed"):
            await _wait_for_consume_health(conn, "server-1", "b" * 32)


def test_legacy_usr_consume_does_not_install_root_boot_hook():
    from app.services.layer_build import render_layer_consume_user_data

    config = yaml.safe_load(render_layer_consume_user_data("legacy", [("10.0.0.1:/share", "usr.sqsh")]))
    assert not any(item["path"].startswith("/etc/initramfs-tools/") for item in config["write_files"])
    auto = base64.b64decode(
        next(
            item["content"] for item in config["write_files"] if item["path"] == "/usr/local/bin/layer-activate-auto.sh"
        )
    ).decode()
    assert "/etc/fstab" in [item["path"] for item in config["write_files"]]
    assert not any(item["path"].endswith("root-exports.conf") for item in config["write_files"])
    assert "OVERLAY_TARGET=/usr" in auto


@pytest.mark.asyncio
async def test_admin_root_profile_resolves_sealed_ancestors_by_id():
    from app.services.layer_build import resolve_admin_consume_artifacts

    delta = SimpleNamespace(
        id=2,
        name="step",
        kind="dockerfile",
        parent_id=1,
        is_sealed=True,
        blob_digest="sha256:" + "b" * 64,
        share_id="share-2",
        sqsh_filename="step.sqsh",
        base_image_id="image-a",
        ubuntu_base="ubuntu-24.04",
    )
    root = SimpleNamespace(
        id=1,
        name="root",
        kind="dockerfile-root",
        parent_id=None,
        is_sealed=True,
        blob_digest="sha256:" + "a" * 64,
        share_id="share-1",
        sqsh_filename="root.sqsh",
        base_image_id="image-a",
        ubuntu_base="ubuntu-24.04",
    )
    session = AsyncMock()
    session.__aenter__.return_value = session
    session.execute.side_effect = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=SimpleNamespace(layers=["step"]))),
        MagicMock(scalar_one_or_none=MagicMock(return_value=delta)),
    ]
    session.get.return_value = root
    with patch("app.database.get_session_factory", return_value=lambda: session):
        lineage = await resolve_admin_consume_artifacts("root-profile")
    assert [art["id"] for art in lineage] == [1, 2]
    assert [art["share_id"] for art in lineage] == ["share-1", "share-2"]


@pytest.mark.asyncio
async def test_import_consume_resolves_exact_sealed_job_lineage_even_if_profile_changes():
    from app.services.layer_build import resolve_import_consume_artifacts

    rows = {
        1: SimpleNamespace(
            id=1,
            name="root",
            kind="dockerfile-root",
            parent_id=None,
            is_sealed=True,
            blob_digest="sha256:" + "a" * 64,
            share_id="share-1",
            sqsh_filename="root.sqsh",
            base_image_id="image-a",
            ubuntu_base="ubuntu-24.04",
        ),
        3: SimpleNamespace(
            id=3,
            name="old-step",
            kind="dockerfile",
            parent_id=1,
            is_sealed=True,
            blob_digest="sha256:" + "b" * 64,
            share_id="share-3",
            sqsh_filename="step.sqsh",
            base_image_id="image-a",
            ubuntu_base="ubuntu-24.04",
        ),
    }
    job = SimpleNamespace(status="complete", profile_name="moved-profile", artifact_ids=[1, 3])
    session = AsyncMock()
    session.__aenter__.return_value = session
    session.get.side_effect = lambda model, key: job if model.__name__ == "LayerImportJob" else rows.get(key)
    with patch("app.database.get_session_factory", return_value=lambda: session):
        profile_name, artifacts = await resolve_import_consume_artifacts(7)
    assert profile_name == "moved-profile"
    assert [item["id"] for item in artifacts] == [1, 3]

    rows[3].parent_id = 2
    with patch("app.database.get_session_factory", return_value=lambda: session):
        with pytest.raises(RuntimeError, match="lineage"):
            await resolve_import_consume_artifacts(7)
    rows[3].parent_id = 1
    rows[3].is_sealed = False
    with patch("app.database.get_session_factory", return_value=lambda: session):
        with pytest.raises(RuntimeError, match="봉인"):
            await resolve_import_consume_artifacts(7)


@pytest.mark.asyncio
async def test_image_fingerprint_mismatch_rejects_before_port_creation():
    from app.services.layer_build import run_layer_consume

    conn = MagicMock()
    conn.image.get_image.return_value = SimpleNamespace(
        id="image-a", name="ubuntu-24.04", status="active", checksum="changed"
    )
    artifact = {
        "id": 1,
        "name": "legacy",
        "kind": "uv",
        "share_id": "share-1",
        "sqsh_filename": "legacy.sqsh",
        "ubuntu_base": "ubuntu-24.04",
        "base_image_id": "image-a",
        "base_image_checksum": "original",
    }
    with (
        patch("app.services.layer_build._update_consume_db", new_callable=AsyncMock),
        patch("app.services.layer_build.neutron.create_port") as port,
    ):
        with pytest.raises(RuntimeError, match="base image identity mismatch"):
            await run_layer_consume(
                1,
                "legacy",
                "vm",
                "flavor",
                resource_snapshot=_snapshot(),
                compute_conn=conn,
                resolved_artifacts=[artifact],
            )
    port.assert_not_called()


@pytest.mark.asyncio
async def test_run_layer_consume_rejects_mixed_artifact_base_images_before_port_creation():
    from app.services.layer_build import run_layer_consume

    connection = MagicMock()
    artifacts = [
        {
            "id": 1,
            "name": "one",
            "share_id": "share-1",
            "sqsh_filename": "one.sqsh",
            "ubuntu_base": "ubuntu-22.04",
            "base_image_id": "image-a",
        },
        {
            "id": 2,
            "name": "two",
            "share_id": "share-2",
            "sqsh_filename": "two.sqsh",
            "ubuntu_base": "ubuntu-22.04",
            "base_image_id": "image-b",
        },
    ]
    with (
        patch("app.services.layer_build._update_consume_db", new_callable=AsyncMock),
        patch("app.services.layer_build.neutron.create_port") as create_port,
    ):
        with pytest.raises(RuntimeError, match="base image가 일치하지 않습니다"):
            await run_layer_consume(
                1,
                "profile",
                "consumer",
                "ignored",
                resource_snapshot=_snapshot(),
                compute_conn=connection,
                share_conn=connection,
                resolved_artifacts=artifacts,
            )

    create_port.assert_not_called()


def test_render_layer_consume_user_data_includes_default_and_custom_ssh_user():
    from app.services.layer_build import render_layer_consume_user_data

    user_data = render_layer_consume_user_data(
        "test-python-layer",
        [("10.0.0.10:/share", "test-python-layer-latest.sqsh")],
        ssh_public_key="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITest termius by jung:admin #note",
        ssh_username="ubuntu",
    )
    assert "users:" in user_data
    assert "  - default" in user_data
    assert "  - name: ubuntu" in user_data
    assert '      - "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITest termius by jung:admin #note"' in user_data


def test_render_layer_consume_user_data_imports_github_key_for_default_user():
    from app.services.layer_build import render_layer_consume_user_data

    user_data = render_layer_consume_user_data(
        "test-python-layer", [("10.0.0.10:/share", "test-python-layer-latest.sqsh")], github_username="octocat"
    )
    assert 'ssh_import_id:\n  - "gh:octocat"' in user_data


def test_render_layer_consume_user_data_starts_activation_on_first_boot():
    from app.services.layer_build import render_layer_consume_user_data

    user_data = render_layer_consume_user_data(
        "test-python-layer", [("10.0.0.10:/share-a", "uv-latest.sqsh"), ("10.0.0.11:/share-b", "python-latest.sqsh")]
    )
    assert "systemctl enable layer-activate.service" in user_data
    assert "systemctl start layer-activate.service" in user_data


@pytest.mark.parametrize("mode", ["success", "missing", "corrupt"])
def test_root_staging_tries_next_export_then_fails_closed(tmp_path, mode):
    from app.services.layer_build import render_layer_consume_user_data

    blob = b"sealed root contents"
    delta = b"sealed delta contents"
    digest = "sha256:" + hashlib.sha256(blob).hexdigest()
    delta_digest = "sha256:" + hashlib.sha256(delta).hexdigest()
    config = render_layer_consume_user_data(
        "root",
        [("10.0.0.1:/root", "root.sqsh"), ("10.0.0.1:/delta", "delta.sqsh")],
        root_mode=True,
        digests=[digest, delta_digest],
        root_upper_volume_id=_UPPER_ID,
        root_export_candidates=[
            ["10.0.0.1:/root", "10.0.0.2:/root"],
            ["10.0.0.1:/delta", "10.0.0.2:/delta"],
        ],
    )
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()
    (profile_dir / "root-exports.conf").write_text(
        _decode_write_file(config, "/etc/afterglow/layers/root-exports.conf")
    )
    mntpt = tmp_path / "nfs"
    mntpt.mkdir()
    cache = tmp_path / "0.sqsh"
    delta_cache = tmp_path / "1.sqsh"
    script = _decode_write_file(config, "/usr/local/bin/layer-activate.sh")
    staging = "_stage_root_layer() {" + script.split("_stage_root_layer() {", 1)[1].split("\n_layer_lowerdir() {", 1)[0]
    guest = (
        "set -euo pipefail\n"
        + staging
        + """
mountpoint() { [ -e "$2/.mounted" ]; }
timeout() { shift; "$@"; }
mount() {
    local target="${@: -1}" export="${@: -2:1}"
    touch "$target/.mounted"
    if [ "$export" = '10.0.0.1:/root' ] && [ "$MODE" = corrupt ]; then
        mkdir -p "$target/images"
        printf 'tampered' > "$target/images/root.sqsh"
    elif [ "${export%%:*}" = '10.0.0.2' ] && [ "$MODE" != missing ]; then
        mkdir -p "$target/images"
        if [ "$export" = '10.0.0.2:/root' ]; then
            printf '%s' "$BLOB" > "$target/images/root.sqsh"
        else
            printf '%s' "$DELTA" > "$target/images/delta.sqsh"
        fi
    fi
}
umount() { rm -f "$1/.mounted" "$1/images/root.sqsh" "$1/images/delta.sqsh"; }
sleep() { :; }
_stage_root_layer 0 "$MNTPT" root.sqsh "$DIGEST" "$CACHE"
_stage_root_layer 1 "$MNTPT" delta.sqsh "$DELTA_DIGEST" "$DELTA_CACHE"
"""
    )
    result = subprocess.run(
        ["bash", "-c", guest],
        env={
            "PATH": os.environ["PATH"],
            "LOCAL_PROFILE_DIR": str(profile_dir),
            "MNTPT": str(mntpt),
            "CACHE": str(cache),
            "DELTA_CACHE": str(delta_cache),
            "DELTA": delta.decode(),
            "DELTA_DIGEST": delta_digest,
            "BLOB": blob.decode(),
            "DIGEST": digest,
            "MODE": mode,
        },
        capture_output=True,
        text=True,
    )
    if mode == "success":
        assert result.returncode == 0, result.stderr
        assert cache.read_bytes() == blob
        assert delta_cache.read_bytes() == delta
    else:
        assert result.returncode != 0
        assert ("no usable root export" if mode == "missing" else "FAILED") in result.stderr + result.stdout
        assert not cache.exists() and not delta_cache.exists()
    assert not (mntpt / ".mounted").exists()


def test_render_layer_consume_user_data_mounts_fstab_paths_before_sqsh_lookup():
    from app.services.layer_build import render_layer_consume_user_data

    script = _decode_write_file(
        render_layer_consume_user_data("test-python-layer", [("10.0.0.10:/share-a", "uv-latest.sqsh")]),
        "/usr/local/bin/layer-activate.sh",
    )
    assert "_ensure_nfs_mount()" in script
    assert '_ensure_nfs_mount "$MNTPT"' in script
    assert script.index('_ensure_nfs_mount "$MNTPT"') < script.index('SQSH_NFS="${MNTPT}/images/${SQSH_FILE}"')


def test_scaffold_layer_activate_uses_usr_lowerdirs_for_usr_overlay():
    script = (Path(__file__).resolve().parents[2] / "layers/vm/layer-activate.sh").read_text()
    assert "_layer_lowerdir()" in script
    assert 'local lower="${mount_point}/usr"' in script
    assert "BASE_USR_LOWER:-/run/afterglow/base-usr" in script
    assert 'mount --bind /usr "$BASE_LOWER"' in script
    assert "lowerdir=${LOWER_DIRS}:${BASE_LOWER}" in script
