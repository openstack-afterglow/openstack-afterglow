"""Full-root guest disk discovery against Nova's truncated virtio serial and duplicate image UUIDs."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services import dockerfile_guest

VOLUME_ID = "3b77947b-4126-48b0-9bb6-f51ebc8cdb19"


def test_mount_ancestors_verifies_local_copy_and_releases_nfs_before_loop_mount(tmp_path):
    inputs = tmp_path / "inputs"
    state = tmp_path / "state"
    image = inputs / "0" / "images" / "root.sqsh"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"verified root bytes")
    digest = hashlib.sha256(image.read_bytes()).hexdigest()
    staged = state / "ancestor-0.sqsh"
    mounted_nfs = False
    attempts = []

    def nfs_mount(argv, *, stdout, stderr, timeout):
        nonlocal mounted_nfs
        assert argv[:5] == ["mount", "-t", "nfs4", "-o", "ro,hard"]
        assert stdout == stderr == dockerfile_guest.subprocess.DEVNULL
        assert 0 < timeout <= 15
        attempts.append(argv)
        mounted_nfs = True
        return SimpleNamespace(returncode=0)

    def mounts(*args):
        nonlocal mounted_nfs
        if args[0] == "umount":
            assert args[1] == str(inputs / "0") and mounted_nfs
            assert staged.read_bytes() == image.read_bytes()
            mounted_nfs = False
        elif args[:3] == ("mount", "-t", "squashfs"):
            assert args[3:5] == ("-o", "ro")
            assert args[-2] == str(staged) and not mounted_nfs
        else:
            raise AssertionError(f"unexpected command: {args}")

    with (
        patch.object(dockerfile_guest, "STATE", state),
        patch.object(dockerfile_guest, "INPUTS", inputs),
        patch.object(dockerfile_guest.subprocess, "run", side_effect=nfs_mount),
        patch.object(dockerfile_guest, "call", side_effect=mounts),
    ):
        lowers = dockerfile_guest.mount_ancestors(
            [
                {
                    "exports": ["127.0.0.1:/example"],
                    "filename": "root.sqsh",
                    "blob_digest": "sha256:" + digest,
                }
            ]
        )

    assert lowers == [str(state / "cached-0")]
    assert len(attempts) == 1
    assert not mounted_nfs


def test_mount_ancestors_digest_mismatch_releases_share_without_mounting_blob(tmp_path):
    inputs = tmp_path / "inputs"
    state = tmp_path / "state"
    image = inputs / "0" / "images" / "root.sqsh"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"wrong contents")
    calls = []

    def nfs_mount(argv, *, stdout, stderr, timeout):
        assert argv[4] == "ro,hard" and stdout == stderr == dockerfile_guest.subprocess.DEVNULL
        return SimpleNamespace(returncode=0)

    with (
        patch.object(dockerfile_guest, "STATE", state),
        patch.object(dockerfile_guest, "INPUTS", inputs),
        patch.object(dockerfile_guest.subprocess, "run", side_effect=nfs_mount),
        patch.object(dockerfile_guest, "call", side_effect=lambda *args: calls.append(args)),
    ):
        with pytest.raises(RuntimeError, match="cached ancestor digest mismatch"):
            dockerfile_guest.mount_ancestors(
                [
                    {
                        "exports": ["127.0.0.1:/example"],
                        "filename": "root.sqsh",
                        "blob_digest": "sha256:" + "0" * 64,
                    }
                ]
            )

    assert [args[0] for args in calls] == ["umount"]
    assert not (state / "ancestor-0.sqsh").exists()


def test_mount_ancestors_uses_second_export_when_first_is_unavailable(tmp_path):
    inputs = tmp_path / "inputs"
    state = tmp_path / "state"
    image = inputs / "0" / "images" / "root.sqsh"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"sealed ancestor")
    attempts = []
    commands = []
    exports = ["192.0.2.1:/unavailable", "192.0.2.2:/available"]

    def nfs_mount(argv, *, stdout, stderr, timeout):
        assert argv[3:5] == ["-o", "ro,hard"]
        assert stdout == stderr == dockerfile_guest.subprocess.DEVNULL
        attempts.append(argv[5])
        if argv[5] == exports[0]:
            raise dockerfile_guest.subprocess.TimeoutExpired(argv, timeout, stderr=b"192.0.2.1: unavailable")
        return SimpleNamespace(returncode=0)

    def mounts(*args):
        commands.append(args)
        if args[0] == "umount":
            assert (state / "ancestor-0.sqsh").read_bytes() == image.read_bytes()

    with (
        patch.object(dockerfile_guest, "STATE", state),
        patch.object(dockerfile_guest, "INPUTS", inputs),
        patch.object(dockerfile_guest.subprocess, "run", side_effect=nfs_mount),
        patch.object(dockerfile_guest, "call", side_effect=mounts),
        patch.object(dockerfile_guest.time, "sleep") as sleep,
    ):
        lowers = dockerfile_guest.mount_ancestors(
            [
                {
                    "exports": exports,
                    "filename": "root.sqsh",
                    "blob_digest": "sha256:" + hashlib.sha256(image.read_bytes()).hexdigest(),
                }
            ]
        )

    assert lowers == [str(state / "cached-0")]
    assert attempts == exports
    assert commands == [
        ("umount", str(inputs / "0")),
        ("mount", "-t", "squashfs", "-o", "ro", str(state / "ancestor-0.sqsh"), str(state / "cached-0")),
    ]
    sleep.assert_not_called()


def test_mount_ancestors_all_exports_unavailable_exhausts_rounds_without_leaking(tmp_path, capsys):
    inputs = tmp_path / "inputs"
    state = tmp_path / "state"
    exports = ["192.0.2.1:/private", "192.0.2.2:/private"]
    now = 0.0
    attempts = []
    sleeps = []

    def sleep(seconds):
        nonlocal now
        sleeps.append(seconds)
        now += seconds

    def nfs_mount(argv, *, stdout, stderr, timeout):
        assert stdout == stderr == dockerfile_guest.subprocess.DEVNULL
        assert 0 < timeout <= 15
        attempts.append(argv[5])
        return SimpleNamespace(returncode=32)

    with (
        patch.object(dockerfile_guest, "STATE", state),
        patch.object(dockerfile_guest, "INPUTS", inputs),
        patch.object(dockerfile_guest.subprocess, "run", side_effect=nfs_mount),
        patch.object(dockerfile_guest, "call") as other_mounts,
        patch.object(dockerfile_guest.time, "monotonic", side_effect=lambda: now),
        patch.object(dockerfile_guest.time, "sleep", side_effect=sleep),
    ):
        with pytest.raises(RuntimeError) as failure:
            dockerfile_guest.mount_ancestors(
                [{"exports": exports, "filename": "root.sqsh", "blob_digest": "sha256:" + "0" * 64}]
            )

    assert attempts == exports * 12
    assert sleeps == [5] * 11 and now == 55
    assert str(failure.value) == "cached ancestor NFS mount failed"
    assert capsys.readouterr() == ("", "")
    other_mounts.assert_not_called()
    assert not (state / "ancestor-0.sqsh").exists()


def test_mount_ancestors_timeout_caps_total_time_even_with_many_exports(tmp_path):
    now = 0.0
    attempts = []
    exports = [f"192.0.2.{index}:/private" for index in range(1, 5)]

    def nfs_mount(argv, *, stdout, stderr, timeout):
        nonlocal now
        assert stdout == stderr == dockerfile_guest.subprocess.DEVNULL
        assert 0 < timeout <= 15
        attempts.append(argv[5])
        now += timeout
        raise dockerfile_guest.subprocess.TimeoutExpired(argv, timeout, stderr=b"private export")

    def advance(seconds):
        nonlocal now
        now += seconds

    with (
        patch.object(dockerfile_guest, "STATE", tmp_path / "state"),
        patch.object(dockerfile_guest, "INPUTS", tmp_path / "inputs"),
        patch.object(dockerfile_guest.subprocess, "run", side_effect=nfs_mount),
        patch.object(dockerfile_guest, "call") as other_mounts,
        patch.object(dockerfile_guest.time, "monotonic", side_effect=lambda: now),
        patch.object(dockerfile_guest.time, "sleep", side_effect=advance) as sleep,
    ):
        with pytest.raises(RuntimeError, match="^cached ancestor NFS mount failed$"):
            dockerfile_guest.mount_ancestors(
                [{"exports": exports, "filename": "root.sqsh", "blob_digest": "sha256:" + "0" * 64}]
            )

    assert attempts == exports * 3
    assert now == 180
    assert sleep.call_count == 2
    other_mounts.assert_not_called()


@pytest.mark.parametrize("serial", [VOLUME_ID[:20], VOLUME_ID.replace("-", "")[:20]])
def test_image_root_finds_attached_clone_by_truncated_virtio_serial(tmp_path, serial):
    disk = {
        "name": "vdb",
        "type": "disk",
        "path": "/dev/vdb",
        "serial": serial,
        "children": [
            {"name": "vdb1", "fstype": "ext4", "path": "/dev/vdb1", "maj:min": "252:17"},
            {"name": "vdb15", "fstype": "vfat", "path": "/dev/vdb15", "maj:min": "252:31"},
        ],
    }

    def output(argv, *, text):
        if argv[0] == "findmnt":
            # SOURCE /dev/vdb1 is misleading: the cloned image duplicates the boot
            # filesystem UUID. The mounted root is actually major:minor 252:1.
            return "252:1\n" if "MAJ:MIN" in argv else "/dev/vdb1\n"
        if argv[1] == "-n":
            return "vdb\n"
        return json.dumps(
            {
                "blockdevices": [
                    {
                        "name": "vda",
                        "type": "disk",
                        "path": "/dev/vda",
                        "serial": None,
                        "children": [{"name": "vda1", "fstype": "ext4", "path": "/dev/vda1", "maj:min": "252:1"}],
                    },
                    disk,
                ]
            }
        )

    def mounted(*argv):
        if argv[0] == "mount":
            target = Path(argv[-1])
            (target / "etc").mkdir(parents=True)
            (target / "etc/os-release").write_text("ID=ubuntu\n")
            (target / "usr").mkdir()

    with (
        patch.object(dockerfile_guest, "STATE", tmp_path),
        patch.object(dockerfile_guest.subprocess, "check_output", side_effect=output),
        patch.object(dockerfile_guest, "call", side_effect=mounted) as mount,
        patch.object(dockerfile_guest.time, "monotonic", side_effect=[0, 1, 181]),
    ):
        assert dockerfile_guest.image_root(VOLUME_ID) == tmp_path / "image-root-0"
    mount.assert_called_once_with("mount", "-t", "ext4", "-o", "ro,noload", "/dev/vdb1", str(tmp_path / "image-root-0"))


def test_image_root_rejects_short_ambiguous_serial_before_mount(tmp_path):
    with (
        patch.object(dockerfile_guest, "STATE", tmp_path),
        patch.object(
            dockerfile_guest.subprocess,
            "check_output",
            side_effect=[
                "252:1\n",
                json.dumps(
                    {
                        "blockdevices": [
                            {
                                "name": "vda",
                                "type": "disk",
                                "path": "/dev/vda",
                                "serial": None,
                                "children": [{"name": "vda1", "path": "/dev/vda1", "maj:min": "252:1"}],
                            },
                            {"name": "vdb", "type": "disk", "path": "/dev/vdb", "serial": VOLUME_ID[:14]},
                        ]
                    }
                ),
            ],
        ),
        patch.object(dockerfile_guest, "call") as mount,
        patch.object(dockerfile_guest.time, "monotonic", side_effect=[0, 1, 181]),
    ):
        with pytest.raises(TimeoutError, match="did not attach by serial"):
            dockerfile_guest.image_root(VOLUME_ID)
    mount.assert_not_called()


def test_image_root_refuses_clone_when_actual_boot_device_is_unknown(tmp_path):
    with (
        patch.object(dockerfile_guest, "STATE", tmp_path),
        patch.object(
            dockerfile_guest.subprocess,
            "check_output",
            side_effect=[
                "252:99\n",
                json.dumps(
                    {
                        "blockdevices": [
                            {
                                "name": "vda",
                                "type": "disk",
                                "serial": VOLUME_ID[:20],
                                "children": [{"name": "vda1", "path": "/dev/vda1", "maj:min": "252:1"}],
                            }
                        ]
                    }
                ),
            ],
        ),
        patch.object(dockerfile_guest, "call") as mount,
        patch.object(dockerfile_guest.time, "monotonic", side_effect=[0, 1]),
    ):
        with pytest.raises(RuntimeError, match="cannot identify builder root disk"):
            dockerfile_guest.image_root(VOLUME_ID)
    mount.assert_not_called()


def test_run_releases_backing_shares_after_sealing_manifest(tmp_path):
    state = tmp_path / "state"
    inputs = tmp_path / "inputs"
    outputs = tmp_path / "outputs"
    (outputs / "0").mkdir(parents=True)
    cached = state / "cached-0"
    built = state / "new-0"
    active = {str(cached), str(built), str(outputs / "0")}
    loops = {
        "/dev/loop0": str(state / "ancestor-0.sqsh"),
        "/dev/loop1": str(state / "step-0.sqsh"),
    }
    unrelated = str(tmp_path / "unrelated.sqsh")
    loops["/dev/loop2"] = unrelated
    original_read_text = Path.read_text

    def read_plan(path, *args, **kwargs):
        if str(path) == "/etc/afterglow/dockerfile-plan.json":
            return json.dumps([{"name": "delta", "instruction": "RUN"}])
        if str(path) == "/etc/afterglow/dockerfile-config.json":
            return json.dumps({"ancestors": [{"filename": "root.sqsh"}], "root_name": None, "context": None})
        return original_read_text(path, *args, **kwargs)

    def loop_lookup(argv, *, text):
        # Only exact backing-path matches may be detached; unrelated loops remain.
        assert argv == ["losetup", "-a"]
        return "".join(f"{device}: [0049]:1 ({backing})\n" for device, backing in loops.items())

    def release(*argv):
        if argv[0] == "losetup":
            assert argv[1] == "-d" and argv[2] in loops
            loops.pop(argv[2])
            return
        command, path = argv
        assert command == "umount" and path in active
        assert path != str(inputs / "0")
        if path == str(outputs / "0"):
            assert str(built) not in active
            assert "/dev/loop1" not in loops
        active.remove(path)

    with (
        patch.object(dockerfile_guest, "STATE", state),
        patch.object(dockerfile_guest, "INPUTS", inputs),
        patch.object(dockerfile_guest, "OUTPUTS", outputs),
        patch.object(dockerfile_guest, "REPORTS", [{"name": "delta", "sha256": "digest", "size": 1}]),
        patch.object(Path, "read_text", read_plan),
        patch.object(dockerfile_guest, "mount_ancestors", return_value=[str(cached)]),
        patch.object(dockerfile_guest, "run_step", return_value=str(built)),
        patch.object(dockerfile_guest, "call", side_effect=release),
        patch.object(dockerfile_guest.subprocess, "check_output", side_effect=loop_lookup),
        patch.dict("os.environ", {"AFTERGLOW_BUILD_TOKEN": "sealed-token"}),
    ):
        dockerfile_guest.run()

    assert not active and loops == {"/dev/loop2": unrelated}
    manifest = json.loads((outputs / "0" / ".afterglow-manifest.json").read_text())
    assert manifest["token"] == "sealed-token"
    assert manifest["reports"] == [{"name": "delta", "sha256": "digest", "size": 1}]
