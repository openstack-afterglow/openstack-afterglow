from __future__ import annotations

import base64
import hashlib
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

# The shipped helper deliberately uses Linux/GNU initramfs utilities.
pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux guest helper with GNU coreutils")

CHILD = "01234567-89ab-cdef-0123-456789abcdef"
PARENT = "abcdef01-2345-6789-abcd-ef0123456789"
UPPER = "11111111-2222-3333-4444-555555555555"

FIXTURE_FUNCTIONS = r"""
layer_block_inventory() { cat "$INVENTORY"; }
blockdev() {
    case "$1" in
        --getro) printf '%s\n' "${KERNEL_RO:-1}" ;;
        --getsize64) stat -c%s "$2" ;;
        *) return 1 ;;
    esac
}
"""


def _digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _files(config: str) -> dict[str, str]:
    return {
        entry["path"]: base64.b64decode(entry["content"]).decode() for entry in yaml.safe_load(config)["write_files"]
    }


def _config(root_mode: bool = False) -> str:
    from app.services.layer_build import render_layer_consume_user_data

    return render_layer_consume_user_data(
        "blocks",
        [("", "child.sqsh"), ("", "parent.sqsh")],
        block_layers=[
            {"volume_id": CHILD, "digest": _digest(b"child"), "size_bytes": 5},
            {"volume_id": PARENT.replace("-", "").upper(), "digest": _digest(b"parent"), "size_bytes": 6},
        ],
        root_mode=root_mode,
        root_upper_volume_id=UPPER if root_mode else None,
    )


def _fixture(tmp_path: Path, inventory: str, volumes: list[str] | None = None) -> dict[str, str]:
    helper = tmp_path / "helper.sh"
    helper.write_text(_files(_config())["/usr/local/bin/layer-block-device.sh"])
    supplied = tmp_path / "volumes.conf"
    supplied.write_text("\n".join(volumes or [CHILD, PARENT, UPPER]) + "\n")
    disks = tmp_path / "inventory"
    disks.write_text(inventory)
    return {
        **os.environ,
        "HELPER": str(helper),
        "VOLUMES": str(supplied),
        "INVENTORY": str(disks),
    }


def _run(env: dict[str, str], command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", '. "$HELPER"\n' + FIXTURE_FUNCTIONS + command],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )


@pytest.mark.parametrize(
    "serial", [CHILD, CHILD.upper(), CHILD.replace("-", ""), CHILD[:20], CHILD.replace("-", "")[:20]]
)
def test_guest_resolves_only_supported_cinder_serials(tmp_path, serial):
    env = _fixture(tmp_path, f"/dev/vdz|disk|virtio_blk|{serial}|1|1073741824\n")
    result = _run(env, f'layer_block_resolve {CHILD.replace("-", "")} "$VOLUMES"')
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "/dev/vdz"


@pytest.mark.parametrize("serial", [CHILD[:19], CHILD[:21], CHILD.replace("-", "")[:17], "junk", CHILD + "tail"])
def test_guest_never_accepts_arbitrary_serial_prefixes(tmp_path, serial):
    env = _fixture(tmp_path, f"/dev/vdb|disk|virtio_blk|{serial}|1|4096\n")
    result = _run(env, f'layer_block_resolve {CHILD} "$VOLUMES"')
    assert result.returncode != 0
    assert "missing or ambiguous" in result.stderr


@pytest.mark.parametrize("compact", [False, True])
def test_truncated_serial_collision_with_any_supplied_volume_is_fatal(tmp_path, compact):
    # Treat the colliding ID as the writable upper, not just another layer.
    collision = "01234567-89ab-cdef-0123-000000000000"
    serial = CHILD.replace("-", "")[:20] if compact else CHILD[:20]
    env = _fixture(tmp_path, f"/dev/vdb|disk|virtio_blk|{serial}|1|4096\n", [CHILD, PARENT, collision])
    result = _run(env, f'layer_block_resolve {CHILD} "$VOLUMES"')
    assert result.returncode != 0
    assert "ambiguous Cinder serial among supplied volumes" in result.stderr


def test_full_serials_distinguish_volumes_with_shared_truncated_prefix(tmp_path):
    collision = "01234567-89ab-cdef-0123-000000000000"
    env = _fixture(
        tmp_path,
        f"/dev/vdz|disk|virtio_blk|{CHILD}|1|4096\n/dev/vdb|disk|virtio_blk|{collision}|0|4096\n",
        [CHILD, collision],
    )
    result = _run(env, f'layer_block_resolve {CHILD} "$VOLUMES"')
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "/dev/vdz"


@pytest.mark.parametrize(
    ("kind", "driver", "ro", "error"),
    [
        ("part", "virtio_blk", "1", "unexpected layer disk type"),
        ("disk", "sd", "1", "unexpected layer disk type"),
        ("loop", "loop", "1", "unexpected layer disk type"),
        ("disk", "virtio_blk", "0", "not kernel readonly"),
    ],
)
def test_guest_rejects_wrong_disk_type_driver_or_kernel_ro(tmp_path, kind, driver, ro, error):
    env = _fixture(tmp_path, f"/dev/vdb|{kind}|{driver}|{CHILD}|{ro}|4096\n")
    result = _run(env, f'layer_block_resolve {CHILD} "$VOLUMES"')
    assert result.returncode != 0
    assert error in result.stderr


def test_guest_rejects_two_devices_with_same_serial(tmp_path):
    env = _fixture(
        tmp_path,
        f"/dev/vdb|disk|virtio_blk|{CHILD}|1|4096\n/dev/vdc|disk|virtio_blk|{CHILD}|1|4096\n",
    )
    result = _run(env, f'layer_block_resolve {CHILD} "$VOLUMES"')
    assert result.returncode != 0
    assert "ambiguous Cinder layer device" in result.stderr


@pytest.mark.parametrize("padding", [b"\0" * 8192, b"untrusted GiB padding" * 400])
def test_guest_hashes_exact_payload_without_copying_padding(tmp_path, padding):
    payload = b"hsqs sealed squashfs bytes\0" * 117
    source = tmp_path / "payload"
    source.write_bytes(payload + padding)
    env = _fixture(tmp_path, "")
    env["PAYLOAD"] = str(source)
    result = _run(env, f'layer_block_verify "$PAYLOAD" {_digest(payload)} {len(payload)}')
    assert result.returncode == 0, result.stderr
    assert source.read_bytes() == payload + padding
    assert {path.name for path in tmp_path.iterdir()} == {"payload", "helper.sh", "volumes.conf", "inventory"}


@pytest.mark.parametrize(
    ("data", "size", "ro", "digest", "error"),
    [
        (b"tampered", 8, "1", _digest(b"original"), "digest mismatch"),
        (b"tiny", 5, "1", _digest(b"tiny"), "insufficient layer device size"),
        (b"sealed", 6, "0", _digest(b"sealed"), "not kernel readonly"),
        (b"sealedpadding", 7, "1", _digest(b"sealed"), "digest mismatch"),
    ],
)
def test_guest_verification_fails_closed(tmp_path, data, size, ro, digest, error):
    source = tmp_path / "payload"
    source.write_bytes(data)
    env = _fixture(tmp_path, "")
    env.update(PAYLOAD=str(source), KERNEL_RO=ro)
    result = _run(env, f'layer_block_verify "$PAYLOAD" {digest} {size}')
    assert result.returncode != 0
    assert error in result.stderr


def test_guest_hash_read_failure_propagates_through_pipefail(tmp_path):
    env = _fixture(tmp_path, "")
    # A readable geometry response is not proof that the payload read succeeds.
    result = _run(
        env,
        f"""blockdev() {{ [ "$1" = --getro ] && echo 1 || echo 4096; }}
layer_block_verify /missing-layer-device {_digest(b"")} 32""",
    )
    assert result.returncode != 0


@pytest.mark.parametrize(
    "changes",
    [
        {"block_layers": []},
        {"mounts": [("10.0.0.1:/share", "child.sqsh")]},
        {"root_export_candidates": [["10.0.0.1:/share"]]},
        {"digests": ["sha256:" + "0" * 64]},
        {"block_layers": [{"volume_id": CHILD[:20], "digest": _digest(b"child"), "size_bytes": 5}]},
        {"block_layers": [{"volume_id": CHILD, "digest": "md5:abcd", "size_bytes": 5}]},
        {"block_layers": [{"volume_id": CHILD, "digest": _digest(b"child"), "size_bytes": True}]},
        {"block_layers": [{"volume_id": CHILD, "digest": _digest(b"child"), "size_bytes": 0}]},
        {"block_layers": [{"volume_id": CHILD, "digest": _digest(b"child"), "size_bytes": 2**63}]},
        {"root_mode": True, "root_upper_volume_id": CHILD},
    ],
)
def test_renderer_rejects_invalid_block_contract(changes):
    from app.services.layer_build import render_layer_consume_user_data

    args = {
        "mounts": [("", "child.sqsh")],
        "block_layers": [{"volume_id": CHILD, "digest": _digest(b"child"), "size_bytes": 5}],
        **changes,
    }
    with pytest.raises(ValueError):
        render_layer_consume_user_data("blocks", **args)


def _guest_payload_fixture(tmp_path: Path) -> tuple[dict[str, str], Path, Path]:
    child = tmp_path / "child-device"
    parent = tmp_path / "parent-device"
    child.write_bytes(b"child" + b"\0" * 4096)
    parent.write_bytes(b"parent" + b"padding" * 4096)
    env = _fixture(
        tmp_path,
        # Parent intentionally precedes child in the guest inventory.
        f"{parent}|disk|virtio_blk|{PARENT}|1|65536\n{child}|disk|virtio_blk|{CHILD[:20]}|1|65536\n",
    )
    wrapper = tmp_path / "resolve-and-verify.sh"
    wrapper.write_text(
        '#!/bin/bash\n. "$HELPER"\n'
        + FIXTURE_FUNCTIONS
        + 'device="$(layer_block_resolve "$1" "$4")" || exit 1\n'
        + 'layer_block_verify "$device" "$2" "$3" || exit 1\n'
        + 'printf "%s\\n" "$device"\n'
    )
    wrapper.chmod(0o755)
    env.update(WRAPPER=str(wrapper), MOUNT_LOG=str(tmp_path / "mounts.log"))
    return env, child, parent


@pytest.mark.parametrize("same_filename", [False, True])
def test_usr_activation_executes_block_helper_and_keeps_child_first_overlay(tmp_path, same_filename):
    files = _files(_config())
    if same_filename:
        files["/etc/afterglow/layers/blocks.conf"] = files["/etc/afterglow/layers/blocks.conf"].replace(
            "parent.sqsh", "child.sqsh"
        )
    env, child, parent = _guest_payload_fixture(tmp_path)
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    for name in ("blocks.conf", "block-volumes.conf"):
        (profiles / name).write_text(files[f"/etc/afterglow/layers/{name}"])
    sqsh = tmp_path / "sqsh"
    for name in (CHILD, PARENT):
        (sqsh / name / "usr").mkdir(parents=True)
    script = (
        files["/usr/local/bin/layer-activate.sh"]
        .replace('LOG="/var/log/layer-activate.log"', f"LOG={shlex.quote(str(tmp_path / 'activate.log'))}")
        .replace("/usr/local/bin/layer-block-device.sh", env["WRAPPER"])
    )
    # Isolate hook discovery from the host's /usr; mount is a syscall fixture.
    script = script.replace('hook_dir="/usr/lib/afterglow/layer-hooks.d"', f'hook_dir="{tmp_path}/no-hooks"')
    env.update(
        OVERLAY_TARGET="/usr",
        LOCAL_PROFILE_DIR=str(profiles),
        SQSH_BASE=str(sqsh),
        CACHE_DIR=str(tmp_path / "cache"),
        LOCAL_UPPER=str(tmp_path / "upper"),
        LOCAL_WORK=str(tmp_path / "work"),
        BASE_USR_LOWER=str(tmp_path / "base-usr"),
    )
    harness = 'mountpoint() { return 1; }\nmount() { printf "%s\\n" "$*" >> "$MOUNT_LOG"; }\n'
    result = subprocess.run(
        ["bash", "-c", harness + script, "layer-activate.sh", "blocks"],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, (tmp_path / "activate.log").read_text()
    calls = Path(env["MOUNT_LOG"]).read_text().splitlines()
    assert calls[:2] == [
        f"-t squashfs {child} {sqsh}/{CHILD} -o ro",
        f"-t squashfs {parent} {sqsh}/{PARENT} -o ro",
    ]
    assert f"lowerdir={sqsh}/{CHILD}/usr:{sqsh}/{PARENT}/usr:{tmp_path}/base-usr," in calls[-1]
    assert not list((tmp_path / "cache").iterdir())


@pytest.mark.parametrize("failure", ["hash", "readonly", "size", "ambiguous"])
def test_root_boot_reresolves_devices_and_verifies_each_boot_without_cached_blobs(tmp_path, failure):
    files = _files(_config(True))
    env, child, parent = _guest_payload_fixture(tmp_path)
    root = tmp_path / "boot-root"
    config_dir = root / "etc/afterglow/layers"
    config_dir.mkdir(parents=True)
    (config_dir / "root.conf").write_text(files["/etc/afterglow/layers/blocks.conf"])
    (config_dir / "block-volumes.conf").write_text(files["/etc/afterglow/layers/block-volumes.conf"])
    state = tmp_path / "state"
    layers = tmp_path / "sqsh"
    # Execute the real hook from the lower-mount phase onward. The existing
    # dedicated ext4 upper UUID mount is outside this transport regression.
    hook = files["/etc/initramfs-tools/scripts/local-bottom/afterglow-root"].split("lower=\n", 1)[1]
    hook = "lower=\n" + hook.replace("/usr/local/bin/layer-block-device.sh", env["WRAPPER"])
    prelude = (
        f'rootmnt="{root}"; conf="{config_dir}/root.conf"; state="{state}"; '
        f'layers="{layers}"; base="{tmp_path}/base"\n'
        'mount() { printf "%s\\n" "$*" >> "$MOUNT_LOG"; }\nset -eu\n'
    )

    def boot():
        return subprocess.run(["sh", "-c", prelude + hook], env=env, capture_output=True, text=True, timeout=10)

    first = boot()
    assert first.returncode == 0, first.stderr
    calls = Path(env["MOUNT_LOG"]).read_text().splitlines()
    assert calls[:2] == [f"-t squashfs -o ro {child} {layers}/0", f"-t squashfs -o ro {parent} {layers}/1"]
    assert f"lowerdir={layers}/0:{layers}/1,upperdir={state}/upper,workdir={state}/work" in calls[4]
    assert calls[-1] == f"--bind {tmp_path}/base/var/lib/cloud {root}/var/lib/cloud"
    assert not (state / "blobs").exists()

    # Device names and enumeration order change on reboot, but serial identity
    # and child-first manifest order remain authoritative.
    moved = tmp_path / "new-child-device"
    child.rename(moved)
    Path(env["INVENTORY"]).write_text(
        f"{moved}|disk|virtio_blk|{CHILD.replace('-', '')}|1|65536\n{parent}|disk|virtio_blk|{PARENT[:20]}|1|65536\n"
    )
    Path(env["MOUNT_LOG"]).write_text("")
    second = boot()
    assert second.returncode == 0, second.stderr
    assert Path(env["MOUNT_LOG"]).read_text().splitlines()[0] == f"-t squashfs -o ro {moved} {layers}/0"

    if failure == "hash":
        moved.write_bytes(b"wrong" + b"\0" * 4096)
        error = "digest mismatch"
    elif failure == "readonly":
        # Inventory still advertises RO; the fresh kernel ioctl must agree.
        env["KERNEL_RO"] = "0"
        error = "not kernel readonly"
    elif failure == "size":
        moved.write_bytes(b"tiny")
        error = "insufficient layer device size"
    else:
        with Path(env["INVENTORY"]).open("a") as handle:
            handle.write(f"{moved}|disk|virtio_blk|{CHILD}|1|65536\n")
        error = "ambiguous Cinder layer device"
    Path(env["MOUNT_LOG"]).write_text("")
    corrupt = boot()
    assert corrupt.returncode != 0
    assert error in corrupt.stderr
    assert Path(env["MOUNT_LOG"]).read_text() == ""


def test_renderer_rejects_duplicate_volume_ids_after_normalization():
    from app.services.layer_build import render_layer_consume_user_data

    with pytest.raises(ValueError, match="distinct volumes"):
        render_layer_consume_user_data(
            "blocks",
            [("", "child.sqsh"), ("", "parent.sqsh")],
            block_layers=[
                {"volume_id": CHILD, "digest": _digest(b"child"), "size_bytes": 5},
                {"volume_id": CHILD.replace("-", "").upper(), "digest": _digest(b"parent"), "size_bytes": 6},
            ],
        )


UPPER_FS = "99999999-aaaa-bbbb-cccc-dddddddddddd"
UPPER_FUNCTIONS = r"""
layer_block_inventory() { cat "$INVENTORY"; }
findmnt() { printf '%s\n' /dev/vda1; }
lsblk() {
    case "$*" in
        *'-o PATH'*) printf '%s\n' "${BOOT_ANCESTORS:-/dev/vda1
/dev/vda}" ;;
        *'-o TYPE'*) printf '%s\n' "${DISK_TYPES:-disk}" ;;
        *) return 1 ;;
    esac
}
blockdev() {
    case "$1" in
        --getro) printf '%s\n' "${KERNEL_RO:-0}" ;;
        --getsize64) stat -c%s "$2" ;;
        *) return 1 ;;
    esac
}
layer_upper_filesystems() {
    local path uuid
    while IFS= read -r path; do
        uuid="$(blkid -p -s UUID -o value "$path")" || return 1
        printf '%s|%s\n' "$path" "$uuid"
    done < "$FILESYSTEMS"
}
"""


def _upper_fixture(tmp_path: Path, *, block: bool = True) -> tuple[dict[str, str], Path]:
    from app.services.layer_build import render_layer_consume_user_data

    files = _files(
        _config(True)
        if block
        else render_layer_consume_user_data(
            "nfsroot",
            [("10.0.0.1:/child", "child.sqsh"), ("10.0.0.1:/parent", "parent.sqsh")],
            root_mode=True,
            root_upper_volume_id=UPPER,
            digests=[_digest(b"child"), _digest(b"parent")],
        )
    )
    helper = tmp_path / "helper.sh"
    helper.write_text(files["/usr/local/bin/layer-block-device.sh"])
    upper_helper = tmp_path / "upper-helper.sh"
    upper_helper.write_text(
        files["/usr/local/bin/layer-upper-device.sh"].replace("/usr/local/bin/layer-block-device.sh", str(helper))
    )
    volumes = tmp_path / "volumes.conf"
    volumes.write_text(files["/etc/afterglow/layers/root-volumes.conf"])
    manifest = tmp_path / "root.conf"
    manifest.write_text(files[f"/etc/afterglow/layers/{'blocks' if block else 'nfsroot'}.conf"])
    upper = tmp_path / "upper-device"
    upper.write_bytes(b"\0" * 65536)
    inventory = tmp_path / "inventory"
    inventory.write_text(f"{upper}|disk|virtio_blk|{UPPER}|0|65536\n")
    filesystems = tmp_path / "filesystems"
    filesystems.write_text(str(upper) + "\n")
    return {
        **os.environ,
        "HELPER": str(helper),
        "UPPER_HELPER": str(upper_helper),
        "VOLUMES": str(volumes),
        "MANIFEST": str(manifest),
        "INVENTORY": str(inventory),
        "FILESYSTEMS": str(filesystems),
        "UPPER_DEVICE": str(upper),
        "KERNEL_RO": "0",
    }, upper


def _run_upper(env: dict[str, str], command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", '. "$UPPER_HELPER"\n' + UPPER_FUNCTIONS + command],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )


@pytest.mark.parametrize("block", [False, True])
@pytest.mark.parametrize(
    "serial", [UPPER, UPPER.upper(), UPPER.replace("-", ""), UPPER[:20], UPPER.replace("-", "")[:20]]
)
def test_upper_uses_strict_serial_identity_with_writable_policy(tmp_path, block, serial):
    env, upper = _upper_fixture(tmp_path, block=block)
    Path(env["INVENTORY"]).write_text(f"{upper}|disk|virtio_blk|{serial}|0|65536\n")
    result = _run_upper(env, f'layer_upper_resolve {UPPER} "$VOLUMES" "$MANIFEST" /')
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(upper)


@pytest.mark.parametrize("serial", [UPPER[:19], UPPER[:21], UPPER.replace("-", "")[:17], UPPER + "x", PARENT, "junk"])
def test_upper_rejects_wrong_and_arbitrarily_truncated_serials(tmp_path, serial):
    env, upper = _upper_fixture(tmp_path)
    Path(env["INVENTORY"]).write_text(f"{upper}|disk|virtio_blk|{serial}|0|65536\n")
    result = _run_upper(env, f'layer_upper_resolve {UPPER} "$VOLUMES" "$MANIFEST" /')
    assert result.returncode != 0


@pytest.mark.parametrize("compact", [False, True])
@pytest.mark.parametrize("role", ["layer", "boot", "other"])
def test_upper_serial_collision_with_every_supplied_role_is_fatal(tmp_path, compact, role):
    env, upper = _upper_fixture(tmp_path)
    collision = "11111111-2222-3333-4444-000000000000"
    serial = UPPER.replace("-", "")[:20] if compact else UPPER[:20]
    with Path(env["VOLUMES"]).open("a") as handle:
        handle.write(collision + "\n")
    if role == "layer":
        with Path(env["MANIFEST"]).open("a") as handle:
            handle.write(f"|extra.sqsh|{_digest(b'extra')}|{collision}|5\n")
    Path(env["INVENTORY"]).write_text(f"{upper}|disk|virtio_blk|{serial}|0|65536\n")
    result = _run_upper(env, f'layer_upper_resolve {UPPER} "$VOLUMES" "$MANIFEST" /')
    assert result.returncode != 0
    assert "ambiguous Cinder serial" in result.stderr


@pytest.mark.parametrize("failure", ["boot", "layer", "readonly", "ioctl-readonly", "partition", "driver", "duplicate"])
def test_upper_rejects_boot_layer_and_conflicting_device_policies(tmp_path, failure):
    env, upper = _upper_fixture(tmp_path)
    record = f"{upper}|disk|virtio_blk|{UPPER}|0|65536\n"
    if failure == "boot":
        env["BOOT_ANCESTORS"] = f"/dev/vda1\n{upper}"
    elif failure == "layer":
        with Path(env["MANIFEST"]).open("a") as handle:
            handle.write(f"|upper.sqsh|{_digest(b'upper')}|{UPPER}|5\n")
    elif failure == "readonly":
        record = record.replace("|0|", "|1|")
    elif failure == "ioctl-readonly":
        env["KERNEL_RO"] = "1"
    elif failure == "partition":
        record = record.replace("|disk|", "|part|")
    elif failure == "driver":
        record = record.replace("|virtio_blk|", "|sd|")
    else:
        record += f"/dev/vdz|disk|virtio_blk|{UPPER}|0|65536\n"
    Path(env["INVENTORY"]).write_text(record)
    result = _run_upper(env, f'layer_upper_resolve {UPPER} "$VOLUMES" "$MANIFEST" /')
    assert result.returncode != 0
    assert result.stdout == ""


@pytest.mark.parametrize("contents", ["zero", "raw-tail", "ext4", "signature", "partition", "probe-error"])
def test_first_boot_proves_entire_upper_empty_before_formatting(tmp_path, contents):
    env, upper = _upper_fixture(tmp_path)
    prelude = ""
    if contents == "raw-tail":
        with upper.open("r+b") as handle:
            handle.seek(-1, os.SEEK_END)
            handle.write(b"x")
    elif contents == "ext4":
        _make_ext4(upper)
    elif contents == "signature":
        prelude = "blkid() { return 0; }\n"
    elif contents == "partition":
        env["DISK_TYPES"] = "disk\npart"
    elif contents == "probe-error":
        prelude = "blkid() { return 4; }\n"
    result = _run_upper(env, prelude + 'layer_upper_empty "$UPPER_DEVICE" || exit 1\nprintf "format-allowed\\n"')
    if contents == "zero":
        assert result.returncode == 0, result.stderr
        assert result.stdout == "format-allowed\n"
    else:
        assert result.returncode != 0
        assert result.stdout == ""


def _make_ext4(device: Path, uuid: str = UPPER_FS) -> None:
    import shutil

    executable = shutil.which("mkfs.ext4")
    if not executable:
        pytest.skip("ext4 guest fixture requires mkfs.ext4")
    with device.open("wb") as handle:
        handle.truncate(8 * 1024 * 1024)
    subprocess.run([executable, "-q", "-F", "-U", uuid, str(device)], check=True, capture_output=True, timeout=10)


@pytest.mark.parametrize("failure", ["wrong-fs", "duplicate-fs", "wrong-cinder", "lookalike", "readonly", "non-ext4"])
def test_reboot_requires_both_cinder_identity_and_unique_exact_ext4_uuid(tmp_path, failure):
    env, upper = _upper_fixture(tmp_path)
    _make_ext4(upper)
    command = f'device="$(layer_upper_resolve {UPPER} "$VOLUMES" "$MANIFEST" /boot-root)" || exit 1\nlayer_upper_verify "$device" {UPPER_FS}'
    first = _run_upper(env, command)
    assert first.returncode == 0, first.stderr
    if failure == "wrong-fs":
        _make_ext4(upper, CHILD)
    elif failure == "duplicate-fs":
        duplicate = tmp_path / "unidentified-partition"
        _make_ext4(duplicate)
        # No serial in the device inventory: UUID ambiguity still must fail.
        with Path(env["FILESYSTEMS"]).open("a") as handle:
            handle.write(str(duplicate) + "\n")
    elif failure in {"wrong-cinder", "lookalike"}:
        serial = PARENT if failure == "wrong-cinder" else UPPER.replace("-", "")[:17]
        Path(env["INVENTORY"]).write_text(f"{upper}|disk|virtio_blk|{serial}|0|65536\n")
    elif failure == "readonly":
        env["KERNEL_RO"] = "1"
    else:
        command = 'blkid() { [ "$3" = TYPE ] && echo xfs || echo ' + UPPER_FS + "; }\n" + command
    reboot = _run_upper(env, command)
    assert reboot.returncode != 0


@pytest.mark.parametrize("block", [False, True])
@pytest.mark.parametrize("failure", ["wrong-cinder", "wrong-fs", "duplicate-fs", "lookalike"])
def test_complete_root_hook_checks_upper_before_writable_mount_and_preserves_state(tmp_path, block, failure):
    env, upper = _upper_fixture(tmp_path, block=block)
    _make_ext4(upper)
    from app.services.layer_build import _ROOT_INITRAMFS_HOOK

    root = tmp_path / "bootstrap"
    config_dir = root / "etc/afterglow/layers"
    config_dir.mkdir(parents=True)
    (config_dir / "root.conf").write_text(Path(env["MANIFEST"]).read_text())
    (config_dir / "root-volumes.conf").write_text(Path(env["VOLUMES"]).read_text())
    if block:
        (config_dir / "block-volumes.conf").write_text(Path(env["VOLUMES"]).read_text())
    (config_dir / "root-upper-volume-id").write_text(UPPER + "\n")
    (config_dir / "root-upper-uuid").write_text(UPPER_FS + "\n")
    state = tmp_path / "state"
    (state / "upper").mkdir(parents=True)
    (state / "work").mkdir()
    persisted = state / "upper/persistent-data"
    persisted.write_text("survives reboot")
    if not block:
        (state / "blobs").mkdir()
        (state / "blobs/0.sqsh").write_bytes(b"child")
        (state / "blobs/1.sqsh").write_bytes(b"parent")
    wrapper = tmp_path / "upper-verify.sh"
    wrapper.write_text(
        '#!/bin/bash\n. "$UPPER_HELPER"\n'
        + UPPER_FUNCTIONS
        + 'device="$(layer_upper_resolve "$2" "$3" "$4" "$5")" || exit 1\n'
        + 'layer_upper_verify "$device" "$6" || exit 1\nprintf "%s\\n" "$device"\n'
    )
    wrapper.chmod(0o755)
    layer_wrapper = tmp_path / "layer-verify.sh"
    layer_wrapper.write_text(
        '#!/bin/bash\n. "$HELPER"\n'
        + FIXTURE_FUNCTIONS
        + 'KERNEL_RO=1\ndevice="$(layer_block_resolve "$1" "$4")" || exit 1\n'
        + 'layer_block_verify "$device" "$2" "$3" || exit 1\nprintf "%s\\n" "$device"\n'
    )
    layer_wrapper.chmod(0o755)
    layer_records = ""
    if block:
        for volume, payload in ((CHILD, b"child"), (PARENT, b"parent")):
            layer = tmp_path / volume
            layer.write_bytes(payload + b"\0" * 4096)
            layer_records += f"{layer}|disk|virtio_blk|{volume}|1|65536\n"
        with Path(env["INVENTORY"]).open("a") as handle:
            handle.write(layer_records)
    hook = (
        _ROOT_INITRAMFS_HOOK.replace("/run/afterglow/base-root", str(tmp_path / "base"))
        .replace("/run/afterglow/sqsh", str(tmp_path / "sqsh"))
        .replace("/run/afterglow/state", str(state))
        .replace("/usr/local/bin/layer-upper-device.sh", str(wrapper))
        .replace("/usr/local/bin/layer-block-device.sh", str(layer_wrapper))
    )
    log = tmp_path / "mounts.log"
    env.update(rootmnt=str(root), MOUNT_LOG=str(log))
    harness = 'mount() { printf "%s\\n" "$*" >> "$MOUNT_LOG"; }\n'

    def boot():
        log.write_text("")
        return subprocess.run(["sh", "-c", harness + hook], env=env, capture_output=True, text=True, timeout=10)

    first = boot()
    assert first.returncode == 0, first.stderr
    assert log.read_text().splitlines()[0] == f"-t ext4 -o rw {upper} {state}"
    renamed = tmp_path / "upper-after-reboot"
    upper.rename(renamed)
    Path(env["INVENTORY"]).write_text(f"{renamed}|disk|virtio_blk|{UPPER[:20]}|0|8388608\n" + layer_records)
    Path(env["FILESYSTEMS"]).write_text(str(renamed) + "\n")
    second = boot()
    assert second.returncode == 0, second.stderr
    assert log.read_text().splitlines()[0] == f"-t ext4 -o rw {renamed} {state}"
    assert persisted.read_text() == "survives reboot"
    if failure == "wrong-cinder":
        (config_dir / "root-upper-volume-id").write_text(PARENT + "\n")
    elif failure == "wrong-fs":
        (config_dir / "root-upper-uuid").write_text(CHILD + "\n")
    elif failure == "duplicate-fs":
        duplicate = tmp_path / "unidentified-device"
        _make_ext4(duplicate)
        with Path(env["FILESYSTEMS"]).open("a") as handle:
            handle.write(str(duplicate) + "\n")
    else:
        Path(env["INVENTORY"]).write_text(
            f"{renamed}|disk|virtio_blk|{UPPER.replace('-', '')[:17]}|0|8388608\n" + layer_records
        )
    rejected = boot()
    assert rejected.returncode != 0
    assert log.read_text() == ""
    assert persisted.read_text() == "survives reboot"
