#!/usr/bin/env python3
"""Contract tests for scripts/export_native_cloud.py.

Covers argument parsing, host fail-closed checks, rootfs tar validation and
extraction, rootfs contract inspection, boot additions and disk metadata.
No root, loop device, mount or GRUB installation is used.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import stat
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_SCRIPT = Path(__file__).with_name("export_native_cloud.py")
_SPEC = importlib.util.spec_from_file_location("export_native_cloud", _SCRIPT)
assert _SPEC and _SPEC.loader
_EXPORT = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _EXPORT
_SPEC.loader.exec_module(_EXPORT)

SOURCE = "ab" * 32
UID = os.getuid()
GID = os.getgid()


def _entry(name, kind="file", data=b"", mode=None, uid=UID, gid=GID, link=""):
    info = tarfile.TarInfo(name)
    info.uid, info.gid = uid, gid
    info.mtime = 1_700_000_000
    if kind == "dir":
        info.type, info.mode = tarfile.DIRTYPE, 0o755 if mode is None else mode
    elif kind == "file":
        info.type, info.mode, info.size = tarfile.REGTYPE, 0o644 if mode is None else mode, len(data)
    elif kind == "symlink":
        info.type, info.mode, info.linkname = tarfile.SYMTYPE, 0o777, link
    elif kind == "hardlink":
        info.type, info.mode, info.linkname = tarfile.LNKTYPE, 0o644 if mode is None else mode, link
    elif kind == "fifo":
        info.type, info.mode = tarfile.FIFOTYPE, 0o600 if mode is None else mode
    elif kind == "chr":
        info.type, info.mode, info.devmajor, info.devminor = tarfile.CHRTYPE, 0o666, 1, 3
    return info, data


def _tar(entries) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for info, data in entries:
            archive.addfile(info, io.BytesIO(data) if info.isreg() else None)
    return buffer.getvalue()


def _valid_entries(uid=UID):
    return [
        _entry("./", "dir"),
        _entry("./etc/", "dir"),
        _entry("./etc/passwd", data=b"root:x:0:0::/root:/bin/sh\n", uid=uid),
        _entry("./usr/", "dir"),
        _entry("./usr/bin/", "dir"),
        _entry("./usr/bin/tool", data=b"#!/bin/sh\n", mode=0o4755, uid=uid),
        _entry("./usr/bin/alias", "hardlink", link="./usr/bin/tool", mode=0o4755, uid=uid),
        _entry("./bin", "symlink", link="usr/bin"),
        _entry("./run/", "dir"),
        _entry("./run/pipe", "fifo"),
        _entry("./app/", "dir"),
        _entry("./app/afterglow.conf", "symlink", link="/var/lib/afterglow/afterglow.conf"),
    ]


def _scan(entries):
    archive = tarfile.open(fileobj=io.BytesIO(_tar(entries)), mode="r:")
    return archive, _EXPORT.scan_rootfs(archive)


class ArgumentTests(unittest.TestCase):
    def parse(self, *extra):
        return _EXPORT.parse_args(["--rootfs", "r.tar", "--output", "d.raw", *extra])

    def test_exact_contract_cli(self):
        args = self.parse("--size-gib", "8", "--source-sha256", SOURCE.upper())
        self.assertEqual(args.rootfs, Path("r.tar"))
        self.assertEqual(args.output, Path("d.raw"))
        self.assertEqual(args.size_gib, 8)
        self.assertEqual(args.source_sha256, SOURCE)
        self.assertEqual(self.parse("--source-sha256", SOURCE).size_gib, 8)

    def test_rejects_invalid_values(self):
        for extra in (
            ("--source-sha256", "ab" * 31),
            ("--source-sha256", "zz" * 32),
            ("--source-sha256", SOURCE, "--size-gib", "3"),
            ("--source-sha256", SOURCE, "--size-gib", "65"),
            ("--source-sha256", SOURCE, "--size-gib", "8.5"),
            (),
        ):
            with self.subTest(extra=extra), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    self.parse(*extra)


class HostTests(unittest.TestCase):
    def test_fails_closed_off_linux_amd64_root(self):
        with mock.patch.object(_EXPORT.sys, "platform", "darwin"):
            with self.assertRaisesRegex(_EXPORT.ExportError, "Linux"):
                _EXPORT.require_host()
        with mock.patch.object(_EXPORT.sys, "platform", "linux"), mock.patch.object(
            _EXPORT.platform, "machine", return_value="aarch64"
        ):
            with self.assertRaisesRegex(_EXPORT.ExportError, "amd64"):
                _EXPORT.require_host()
        with mock.patch.object(_EXPORT.sys, "platform", "linux"), mock.patch.object(
            _EXPORT.platform, "machine", return_value="x86_64"
        ), mock.patch.object(_EXPORT.os, "geteuid", return_value=1000):
            with self.assertRaisesRegex(_EXPORT.ExportError, "root"):
                _EXPORT.require_host()

    def test_missing_tool_fails_closed(self):
        with mock.patch.object(_EXPORT.sys, "platform", "linux"), mock.patch.object(
            _EXPORT.platform, "machine", return_value="x86_64"
        ), mock.patch.object(_EXPORT.os, "geteuid", return_value=0):
            which = lambda name, path=None: None if name == "grub-install" else f"/usr/sbin/{name}"  # noqa: E731
            with self.assertRaisesRegex(_EXPORT.ExportError, "grub-install"):
                _EXPORT.require_host(which=which)
            tools = _EXPORT.require_host(which=lambda name, path=None: f"/usr/sbin/{name}")
            self.assertEqual(set(_EXPORT.REQUIRED_TOOLS) | {"udevadm"}, set(tools))

    def test_main_creates_nothing_when_host_is_unsupported(self):
        with tempfile.TemporaryDirectory() as directory:
            rootfs = Path(directory) / "rootfs.tar"
            rootfs.write_bytes(_tar(_valid_entries()))
            output = Path(directory) / "disk.raw"
            with mock.patch.object(_EXPORT.sys, "platform", "darwin"), contextlib.redirect_stderr(io.StringIO()):
                status = _EXPORT.main(
                    ["--rootfs", str(rootfs), "--output", str(output), "--size-gib", "8", "--source-sha256", SOURCE]
                )
            self.assertEqual(status, 1)
            self.assertEqual(sorted(p.name for p in Path(directory).iterdir()), ["rootfs.tar"])

    def test_prepare_paths_refuses_existing_outputs_and_device_trees(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            rootfs = base / "rootfs.tar"
            rootfs.write_bytes(b"")
            paths = _EXPORT.prepare_paths(rootfs, base / "disk.raw")
            self.assertEqual(paths.checksum.name, "disk.raw.sha256")
            self.assertEqual(paths.metadata.name, "disk.raw.metadata.json")
            self.assertEqual(paths.partial.name, "disk.raw.partial")
            for name in ("disk.raw", "disk.raw.sha256", "disk.raw.metadata.json", "disk.raw.partial"):
                (base / name).write_bytes(b"")
                with self.subTest(name=name), self.assertRaisesRegex(_EXPORT.ExportError, "existing"):
                    _EXPORT.prepare_paths(rootfs, base / "disk.raw")
                (base / name).unlink()
            with self.assertRaisesRegex(_EXPORT.ExportError, "does not exist"):
                _EXPORT.prepare_paths(base / "missing.tar", base / "disk.raw")
            if Path("/dev").is_dir():
                with self.assertRaisesRegex(_EXPORT.ExportError, "/dev"):
                    _EXPORT.prepare_paths(rootfs, Path("/dev/afterglow-test.raw"))


class ScanTests(unittest.TestCase):
    def test_accepts_contained_tree_and_normalizes_names(self):
        archive, plan = _scan(_valid_entries())
        with archive:
            names = [info.name for info in plan.members]
            self.assertNotIn("", names)
            self.assertEqual(names[:2], [".", "etc"])
            self.assertEqual(plan.kinds["bin"], "symlink")
            self.assertEqual(plan.kinds["usr/bin/alias"], "hardlink")
            self.assertEqual(plan.members[names.index("usr/bin/alias")].linkname, "usr/bin/tool")
            self.assertEqual(plan.kinds["run/pipe"], "fifo")
            self.assertEqual(plan.regular_bytes, len(b"root:x:0:0::/root:/bin/sh\n") + len(b"#!/bin/sh\n"))

    def test_rejects_unsafe_members(self):
        base = [_entry("etc/", "dir"), _entry("bin", "symlink", link="usr/bin"), _entry("etc/f", data=b"x")]
        cases = {
            "absolute": [_entry("/etc/", "dir")],
            "absolute root": [_entry("/", "dir")],
            "hard link owner mismatch": base + [_entry("etc/h", "hardlink", link="etc/f", uid=UID + 1)],
            "hard link mode mismatch": base + [_entry("etc/h", "hardlink", link="etc/f", mode=0o600)],
            "parent traversal": [_entry("etc/", "dir"), _entry("etc/../x", data=b"")],
            "duplicate": [_entry("etc/", "dir"), _entry("etc/", "dir")],
            "undeclared parent": [_entry("missing/x", data=b"")],
            "through symlink": base + [_entry("bin/x", data=b"")],
            "hard link to symlink": base + [_entry("etc/h", "hardlink", link="bin")],
            "hard link to later file": [_entry("etc/", "dir"), _entry("etc/h", "hardlink", link="etc/later")],
            "hard link escape": base + [_entry("etc/h", "hardlink", link="../etc/f")],
            "symlink escape": base + [_entry("etc/l", "symlink", link="../../outside")],
            "empty symlink": base + [_entry("etc/l", "symlink", link="")],
            "device": base + [_entry("etc/null", "chr")],
            "whiteout": base + [_entry("etc/.wh.f", data=b"")],
            "replace symlink with file": base + [_entry("bin", data=b"")],
        }
        for label, entries in cases.items():
            with self.subTest(label=label), self.assertRaises(_EXPORT.ExportError):
                archive, _ = _scan(entries)
                archive.close()

    def test_rejects_empty_archive(self):
        with self.assertRaisesRegex(_EXPORT.ExportError, "empty"):
            _scan([_entry("./", "dir")])


class ExtractionTests(unittest.TestCase):
    def test_extracts_and_verifies_types_modes_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive, plan = _scan(_valid_entries())
            with archive:
                result = _EXPORT.extract_rootfs(archive, plan, root)
            self.assertEqual(result, {"xattrs_applied": 0, "xattrs_skipped": 0})
            # Unprivileged extraction cannot chown and BSD hosts inherit the
            # directory group, so numeric ownership is asserted only as root.
            owner_checked = os.geteuid() == 0
            self.assertEqual(_EXPORT.verify_extraction(plan, root, check_owner=owner_checked), len(plan.members))
            tool = root / "usr/bin/tool"
            self.assertEqual(stat.S_IMODE(os.lstat(tool).st_mode), 0o4755)
            self.assertEqual(os.lstat(tool).st_ino, os.lstat(root / "usr/bin/alias").st_ino)
            self.assertEqual(os.readlink(root / "app/afterglow.conf"), "/var/lib/afterglow/afterglow.conf")
            self.assertTrue(stat.S_ISFIFO(os.lstat(root / "run/pipe").st_mode))
            os.chmod(tool, 0o755)
            with self.assertRaisesRegex(_EXPORT.ExportError, "mode not preserved"):
                _EXPORT.verify_extraction(plan, root, check_owner=False)

    def test_numeric_owner_mismatch_is_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive, plan = _scan(_valid_entries(uid=UID + 1))
            with archive:
                _EXPORT.extract_rootfs(archive, plan, root)
            if os.geteuid() == 0:
                self.assertEqual(os.lstat(root / "usr/bin/tool").st_uid, UID + 1)
                _EXPORT.verify_extraction(plan, root, check_owner=True)
            else:
                with self.assertRaisesRegex(_EXPORT.ExportError, "numeric owner"):
                    _EXPORT.verify_extraction(plan, root, check_owner=True)


def _make_rootfs(root: Path, kernel="6.12.48+deb13-amd64"):
    def write(relative, text="", mode=0o644):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        os.chmod(path, mode)
        return path

    def link(relative, target):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(target, path)

    for name in ("bin", "sbin", "lib"):
        link(name, f"usr/{name}")
    write("usr/lib/systemd/systemd", mode=0o755)
    link("usr/sbin/init", "../lib/systemd/systemd")
    write("usr/lib/systemd/systemd-resolved", mode=0o755)
    write(f"boot/vmlinuz-{kernel}", "kernel")
    write(f"boot/initrd.img-{kernel}", "initrd")
    (root / f"usr/lib/modules/{kernel}/kernel/fs/ceph").mkdir(parents=True)
    write("usr/lib/grub/i386-pc/boot.img", "boot")
    write("usr/lib/grub/i386-pc/kernel.img", "kernel")
    write(
        "usr/lib/grub/i386-pc/modinfo.sh",
        'grub_modinfo_target_cpu=i386\ngrub_modinfo_platform=pc\ngrub_version="2.12"\n'
        'grub_package_version="2.12-9"\n',
    )
    write("etc/machine-id")
    write("etc/ssh/sshd_config", "PasswordAuthentication no\n")
    write("usr/sbin/sshd", mode=0o755)
    write("usr/bin/cloud-init", mode=0o755)
    (root / "var/lib/afterglow").mkdir(parents=True)
    os.chmod(root / "var/lib/afterglow", 0o700)
    state = os.lstat(root / "var/lib/afterglow")
    write("etc/passwd", f"root:x:0:0::/root:/bin/sh\nappuser:x:{state.st_uid}:{state.st_gid}::/home/appuser:/bin/sh\n")
    link("app/afterglow.conf", "/var/lib/afterglow/afterglow.conf")
    write("app/scripts/native_vm.py", mode=0o755)
    write("usr/local/bin/python3.12", mode=0o755)
    link("app/.venv/bin/python", "/usr/local/bin/python3.12")
    write("etc/systemd/system/afterglow-native.service", "[Unit]\n")
    link("etc/systemd/system/multi-user.target.wants/afterglow-native.service", "/etc/systemd/system/afterglow-native.service")
    write("usr/lib/os-release", 'ID=debian\nVERSION_ID="13"\nVERSION_CODENAME=trixie\nPRETTY_NAME="Debian GNU/Linux 13 (trixie)"\n')
    link("etc/os-release", "../usr/lib/os-release")
    write(
        "var/lib/dpkg/status",
        "Package: systemd\nStatus: install ok installed\nVersion: 257.8-1\n\n"
        "Package: cloud-init\nStatus: deinstall ok config-files\nVersion: 25.1-1\n\n"
        "Package: linux-image-amd64\nStatus: install ok installed\nVersion: 6.12.48-1\n",
    )
    write("etc/resolv.conf")


class InspectionTests(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.root = Path(self._directory.name)
        _make_rootfs(self.root)

    def tearDown(self):
        self._directory.cleanup()

    def test_resolve_in_root_never_leaves_root(self):
        init = _EXPORT.resolve_in_root(self.root, "/sbin/init")
        self.assertEqual(init, self.root / "usr/lib/systemd/systemd")
        os.symlink("/../../../usr/lib/systemd", self.root / "escape")
        self.assertEqual(_EXPORT.resolve_in_root(self.root, "/escape/systemd"), init)
        self.assertIsNone(_EXPORT.resolve_in_root(self.root, "/missing/file"))
        os.symlink("loop", self.root / "loop")
        with self.assertRaisesRegex(_EXPORT.ExportError, "loop"):
            _EXPORT.resolve_in_root(self.root, "/loop")

    def test_valid_rootfs_identity(self):
        identity = _EXPORT.inspect_rootfs(self.root)
        self.assertEqual(identity["kernel_release"], "6.12.48+deb13-amd64")
        self.assertEqual(identity["os_release"]["VERSION_CODENAME"], "trixie")
        self.assertEqual(identity["grub_modules_version"], "2.12-9")
        state = os.lstat(self.root / "var/lib/afterglow")
        self.assertEqual(identity["app_user"], {"name": "appuser", "uid": state.st_uid, "gid": state.st_gid})
        self.assertEqual(identity["dpkg"], {"linux-image-amd64": "6.12.48-1", "systemd": "257.8-1"})
        self.assertEqual(len(identity["kernel_sha256"]), 64)

    def test_contract_violations_fail_closed(self):
        violations = {
            "baked host key": lambda r: (r / "etc/ssh/ssh_host_ed25519_key").write_text("k"),
            "machine identity": lambda r: (r / "etc/machine-id").write_text("0123456789abcdef\n"),
            "second kernel": lambda r: (r / "boot/vmlinuz-6.1.0-1-amd64").write_text("k"),
            "baked state": lambda r: (r / "var/lib/afterglow/credentials.json").write_text("{}"),
            "config not a link": lambda r: ((r / "app/afterglow.conf").unlink(), (r / "app/afterglow.conf").write_text("")),
            "container engine": lambda r: (r / "usr/bin/dockerd").write_text(""),
            "service disabled": lambda r: (r / "etc/systemd/system/multi-user.target.wants/afterglow-native.service").unlink(),
            "preexisting grub": lambda r: ((r / "boot/grub").mkdir(), (r / "boot/grub/grub.cfg").write_text("")),
            "foreign grub": lambda r: (r / "usr/lib/grub/i386-pc/modinfo.sh").write_text(
                "grub_modinfo_target_cpu=x86_64\ngrub_modinfo_platform=efi\n"
            ),
            "cloud-init state": lambda r: (r / "var/lib/cloud/instance").mkdir(parents=True),
            "not debian": lambda r: (r / "usr/lib/os-release").write_text("ID=ubuntu\n"),
            "state mode": lambda r: os.chmod(r / "var/lib/afterglow", 0o755),
            "init": lambda r: (r / "usr/sbin/init").unlink(),
        }
        for label, mutate in violations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                _make_rootfs(root)
                mutate(root)
                with self.assertRaises(_EXPORT.ExportError):
                    _EXPORT.inspect_rootfs(root)


class BootAdditionTests(unittest.TestCase):
    def test_boot_files_mountpoints_and_resolver_link(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _make_rootfs(root)
            record = _EXPORT.write_boot_file(root, "etc/fstab", _EXPORT.fstab_text("1234"))
            self.assertEqual(record["path"], "etc/fstab")
            self.assertIn("UUID=1234 / ext4", (root / "etc/fstab").read_text())
            os.symlink("/etc/shadow", root / "etc/hostile")
            with self.assertRaisesRegex(_EXPORT.ExportError, "non-regular"):
                _EXPORT.write_boot_file(root, "etc/hostile", "x")
            resolv = _EXPORT.link_resolv_conf(root)
            self.assertEqual(resolv, {"path": "etc/resolv.conf", "kind": "symlink", "target": _EXPORT.RESOLV_STUB, "changed": True})
            self.assertEqual(os.readlink(root / "etc/resolv.conf"), _EXPORT.RESOLV_STUB)
            self.assertFalse(_EXPORT.link_resolv_conf(root)["changed"])
            created = _EXPORT.ensure_mountpoints(root)
            self.assertEqual([r["path"] for r in created], ["dev", "proc", "sys", "run", "tmp"])
            self.assertEqual(stat.S_IMODE(os.lstat(root / "tmp").st_mode), 0o1777)
            self.assertEqual(_EXPORT.ensure_mountpoints(root), [])
            (root / "boot/grub/i386-pc").mkdir(parents=True)
            (root / "boot/grub/i386-pc/core.img").write_bytes(b"core")
            _EXPORT.write_boot_file(root, "boot/grub/grub.cfg", _EXPORT.grub_cfg_text("1234", "6.12"))
            self.assertEqual(
                [r["path"] for r in _EXPORT.tree_records(root, "boot/grub")],
                ["boot/grub/grub.cfg", "boot/grub/i386-pc/core.img"],
            )

    def test_boot_file_replacement_does_not_modify_other_archive_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "etc").mkdir()
            original = root / "etc/original"
            original.write_text("retain this inode")
            os.link(original, root / "etc/fstab")
            _EXPORT.write_boot_file(root, "etc/fstab", "new fstab")
            self.assertEqual(original.read_text(), "retain this inode")
            self.assertEqual((root / "etc/fstab").read_text(), "new fstab")
            self.assertNotEqual(os.stat(original).st_ino, os.stat(root / "etc/fstab").st_ino)

    def test_grub_cfg_boots_root_uuid_on_serial(self):
        text = _EXPORT.grub_cfg_text("0f0e-uuid", "6.12.48+deb13-amd64")
        self.assertIn("search --no-floppy --fs-uuid --set=root 0f0e-uuid", text)
        self.assertIn("linux /boot/vmlinuz-6.12.48+deb13-amd64 root=UUID=0f0e-uuid ro console=tty0 console=ttyS0,115200n8", text)
        self.assertIn("initrd /boot/initrd.img-6.12.48+deb13-amd64", text)

    def test_builder_grub_metadata_uses_only_builder_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            modules = Path(directory)
            # This is treated as bytes, never as a script by the metadata reader.
            for name in ("boot.img", "kernel.img", "modinfo.sh"):
                (modules / name).write_text("not executable rootfs instructions")
            with mock.patch.object(_EXPORT, "BUILDER_GRUB_MODULES", modules), mock.patch.object(
                _EXPORT, "run", return_value="grub-install (GRUB) 2.12-1ubuntu7.3"
            ) as run:
                record = _EXPORT.builder_grub_identity({"grub-install": "/usr/sbin/grub-install"})
            run.assert_called_once_with(["/usr/sbin/grub-install", "--version"])
            self.assertEqual(record["upstream_version"], "2.12")
            self.assertEqual(record["source_directory"], str(modules))
            self.assertEqual(set(record["source_sha256"]), {"boot.img", "kernel.img", "modinfo.sh"})
            self.assertTrue(all(len(value) == 64 for value in record["source_sha256"].values()))


class DiskCleanupTests(unittest.TestCase):
    def test_unmount_oserror_preserves_loop_and_backing_image(self):
        resources = _EXPORT.Resources(
            tools={"umount": "/usr/bin/umount", "losetup": "/usr/sbin/losetup"},
            image=Path("owned.raw.partial"), loop="/dev/loop42",
            mountpoint=Path("/private/mount"), mounted=True,
        )
        with mock.patch.object(_EXPORT, "run", side_effect=OSError("failed unmount")) as run:
            errors = resources.release()
        self.assertTrue(errors)
        self.assertTrue(resources.mounted)
        self.assertEqual(resources.loop, "/dev/loop42")
        self.assertEqual(run.call_count, 1)

    def test_cleanup_verifies_loop_identity_before_detaching(self):
        resources = _EXPORT.Resources(
            tools={"losetup": "/usr/sbin/losetup"},
            image=Path("owned.raw.partial"), loop="/dev/loop42",
        )
        with mock.patch.object(_EXPORT, "verify_loop", side_effect=_EXPORT.ExportError("not ours")), mock.patch.object(
            _EXPORT, "run"
        ) as run:
            self.assertTrue(resources.release())
            run.assert_not_called()
        self.assertEqual(resources.loop, "/dev/loop42")

    def test_partial_sidecar_is_removed_on_write_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "disk.metadata.json"
            real_fdopen = os.fdopen

            @contextlib.contextmanager
            def failed_writer(descriptor, *args, **kwargs):
                with real_fdopen(descriptor, *args, **kwargs) as handle:
                    handle.write("partial")
                    yield mock.Mock(write=mock.Mock(side_effect=OSError("write failed")))

            with mock.patch.object(_EXPORT.os, "fdopen", failed_writer):
                with self.assertRaises(OSError):
                    _EXPORT._create_exclusive(path, "metadata")
            self.assertFalse(path.exists())


class DiskMetadataTests(unittest.TestCase):
    def test_layout_and_partition_script(self):
        layout = _EXPORT.partition_layout(8)
        self.assertEqual(layout["size_bytes"], 8 * 1024**3)
        self.assertEqual(layout["start_sector"], 2048)
        self.assertEqual(layout["sectors"], 8 * 1024**3 // 512 - 2048)
        script = _EXPORT.sfdisk_script(0x1234ABCD, layout)
        self.assertIn("label: dos\n", script)
        self.assertIn("label-id: 0x1234abcd\n", script)
        self.assertIn(f"start=2048, size={layout['sectors']}, type=83, bootable\n", script)

    def test_dumpe2fs_parsing(self):
        parsed = _EXPORT.parse_dumpe2fs(
            "Filesystem volume name:   afterglow-root\n"
            "Filesystem UUID:          5c1b0c4e-0000-4000-8000-000000000000\n"
            "Filesystem features:      has_journal ext_attr resize_inode dir_index filetype extent 64bit\n"
            "Block count:              2096896\n"
            "Block size:               4096\n"
        )
        self.assertEqual(parsed["uuid"], "5c1b0c4e-0000-4000-8000-000000000000")
        self.assertEqual(parsed["label"], "afterglow-root")
        self.assertIn("64bit", parsed["features"])
        self.assertEqual((parsed["block_count"], parsed["block_size"]), (2096896, 4096))
        with self.assertRaises(_EXPORT.ExportError):
            _EXPORT.parse_dumpe2fs("Filesystem UUID: x\n")

    def test_metadata_records_source_rootfs_boot_and_disk_identity(self):
        metadata = _EXPORT.build_metadata(
            source_sha256=SOURCE,
            rootfs={"sha256": "cd" * 32, "bytes": 10, "members": 3, "regular_bytes": 4},
            identity={"kernel_release": "6.12", "os_release": {"ID": "debian"}},
            additions=[{"path": "etc/fstab", "kind": "file", "sha256": "ef" * 32}],
            disk={"format": "raw", "sha256": "12" * 32, "size_bytes": 8 * 1024**3},
            filesystem={"type": "ext4", "uuid": "5c1b"},
            ownership={"verified_members": 3, "numeric_owner": True},
            exporter={"path": "scripts/export_native_cloud.py"},
        )
        self.assertEqual(metadata["schema"], 1)
        self.assertEqual(metadata["source"]["bundle_sha256"], SOURCE)
        self.assertEqual(metadata["source"]["rootfs_tar_sha256"], "cd" * 32)
        self.assertEqual(metadata["source"]["dockerfile_target"], "native-cloud-vm")
        self.assertEqual(metadata["source"]["derived_from_target"], "native-vm")
        self.assertEqual(metadata["base_identity"]["kernel_release"], "6.12")
        self.assertEqual(metadata["boot_additions"][0]["path"], "etc/fstab")
        self.assertEqual((metadata["disk"]["format"], metadata["disk"]["size_bytes"]), ("raw", 8 * 1024**3))
        self.assertEqual(metadata["root_filesystem"]["uuid"], "5c1b")
        self.assertIsNone(metadata["guest"]["container_engine"])
        self.assertFalse(metadata["claims"]["untouched_oci_root"])
        self.assertFalse(metadata["claims"]["protected_oci_root_stage1"])
        self.assertFalse(metadata["claims"]["security_parity"])


if __name__ == "__main__":
    unittest.main()
