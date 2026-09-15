from __future__ import annotations

import json
import math
import os
import re
import struct
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

CheckState = Literal["present", "absent", "unknown"]
CheckResult = tuple[CheckState, str | None]
Runner = Callable[[list[str], int], subprocess.CompletedProcess]

_VOLUME_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_IMAGE_ID_RE = re.compile(r"^[0-9a-f]{6,32}$")
_POOL_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_CLIENT_RE = re.compile(r"^client\.[A-Za-z0-9._-]{1,64}$")
_OBJECT_RE = re.compile(r"^[A-Za-z0-9._-]{1,255}$")
_PARENT_COMPONENT_RE = re.compile(r"^[A-Za-z0-9._-]{1,255}$")
_ENOENT = "(2) No such file or directory"


class RbdCommandError(RuntimeError):
    def __init__(self, message: str, *, returncode: int | None = None, stderr: str = "") -> None:
        self.returncode = returncode
        self.stderr = stderr[:400]
        suffix = f":{self.stderr}" if self.stderr else ""
        super().__init__(f"{message}{suffix}")


@dataclass(frozen=True)
class RbdImageInfo:
    id: str
    size: int
    order: int
    parent_pool: str | None = None
    parent_image: str | None = None
    parent_snapshot: str | None = None

    @property
    def parent_spec(self) -> str | None:
        if self.parent_pool and self.parent_image and self.parent_snapshot:
            return f"{self.parent_pool}/{self.parent_image}@{self.parent_snapshot}"
        return None


def _detail(value: object, limit: int = 200) -> str:
    return str(value).replace("\x00", "")[:limit]


def _validate(value: str, pattern: re.Pattern[str], label: str) -> str:
    if pattern.fullmatch(value) is None:
        raise ValueError(f"invalid_{label}")
    return value


def volume_image_name(volume_id: str) -> str:
    return f"volume-{_validate(volume_id, _VOLUME_ID_RE, 'volume_id')}"


class RbdClient:
    def __init__(
        self,
        *,
        conf_path: str,
        keyring_path: str,
        client_name: str,
        timeout_seconds: int,
        runner: Runner | None = None,
    ) -> None:
        if not conf_path or "\x00" in conf_path:
            raise ValueError("invalid_conf_path")
        if not keyring_path or "\x00" in keyring_path:
            raise ValueError("invalid_keyring_path")
        self.conf_path = conf_path
        self.keyring_path = keyring_path
        self.client_name = _validate(client_name, _CLIENT_RE, "client_name")
        if timeout_seconds <= 0:
            raise ValueError("invalid_timeout_seconds")
        self.timeout_seconds = timeout_seconds
        self._runner = runner or self._default_runner

    @staticmethod
    def _default_runner(argv: list[str], timeout: int) -> subprocess.CompletedProcess:
        return subprocess.run(argv, capture_output=True, timeout=timeout, check=False)

    def _base(self, tool: str) -> list[str]:
        if tool not in {"ceph", "rbd", "rados"}:
            raise ValueError("invalid_ceph_tool")
        return [
            tool,
            "--conf",
            self.conf_path,
            "--keyring",
            self.keyring_path,
            "--name",
            self.client_name,
        ]

    def _invoke(self, argv: list[str]) -> tuple[subprocess.CompletedProcess | None, str | None]:
        try:
            return self._runner(argv, self.timeout_seconds), None
        except subprocess.TimeoutExpired:
            return None, "timeout"
        except FileNotFoundError:
            return None, "command_not_found"
        except OSError as exc:
            return None, _detail(exc)

    def _check(self, argv: list[str]) -> tuple[CheckState, str, str | None]:
        proc, invoke_error = self._invoke(argv)
        if proc is None:
            return "unknown", "", invoke_error
        stdout = proc.stdout.decode(errors="replace") if isinstance(proc.stdout, bytes) else str(proc.stdout or "")
        stderr = proc.stderr.decode(errors="replace") if isinstance(proc.stderr, bytes) else str(proc.stderr or "")
        if proc.returncode == 0:
            return "present", stdout, None
        if proc.returncode == 2 and _ENOENT in stderr:
            return "absent", stdout, _detail(stderr)
        return "unknown", stdout, _detail(stderr or f"returncode={proc.returncode}")

    def _required(self, argv: list[str], error_code: str) -> subprocess.CompletedProcess:
        proc, invoke_error = self._invoke(argv)
        if proc is None:
            raise RbdCommandError(error_code, stderr=invoke_error or "unknown")
        if proc.returncode != 0:
            stderr = proc.stderr.decode(errors="replace") if isinstance(proc.stderr, bytes) else str(proc.stderr or "")
            raise RbdCommandError(error_code, returncode=proc.returncode, stderr=stderr)
        return proc

    def cluster_fsid(self) -> CheckResult:
        state, stdout, detail = self._check([*self._base("ceph"), "fsid"])
        if state != "present":
            return state, detail
        fsid = stdout.strip()
        return ("present", fsid) if fsid else ("unknown", "empty_fsid")

    def stat_object(self, pool: str, oid: str) -> CheckResult:
        pool = _validate(pool, _POOL_RE, "pool")
        oid = _validate(oid, _OBJECT_RE, "object")
        state, _, detail = self._check([*self._base("rados"), "-p", pool, "stat", oid])
        return state, detail

    def _omap_lookup(self, pool: str, key: str) -> tuple[CheckState, bytes | None, str | None]:
        pool = _validate(pool, _POOL_RE, "pool")
        if _OBJECT_RE.fullmatch(key) is None:
            raise ValueError("invalid_omap_key")
        fd, path = tempfile.mkstemp(prefix="afterglow-rbd-omap-")
        os.close(fd)
        try:
            state, _, detail = self._check([*self._base("rados"), "-p", pool, "getomapval", "rbd_directory", key, path])
            if state != "present":
                return state, None, detail
            try:
                return "present", Path(path).read_bytes(), None
            except OSError as exc:
                return "unknown", None, _detail(exc)
        finally:
            Path(path).unlink(missing_ok=True)

    @staticmethod
    def _parse_directory_value(raw: bytes) -> tuple[CheckState, str | None]:
        if len(raw) < 4:
            return "unknown", "directory_value_too_short"
        size = struct.unpack("<I", raw[:4])[0]
        payload = raw[4:]
        if size != len(payload):
            return "unknown", "directory_value_length_mismatch"
        try:
            image_id = payload.decode("ascii")
        except UnicodeDecodeError:
            return "unknown", "directory_value_non_ascii"
        if _IMAGE_ID_RE.fullmatch(image_id) is None:
            return "unknown", "directory_value_invalid_id"
        return "present", image_id

    def directory_lookup(self, pool: str, name: str) -> CheckResult:
        if not name.startswith("volume-") or _VOLUME_ID_RE.fullmatch(name[7:]) is None:
            raise ValueError("invalid_image_name")
        state, raw, detail = self._omap_lookup(pool, f"name_{name}")
        if state != "present" or raw is None:
            return state, detail
        return self._parse_directory_value(raw)

    def directory_lookup_by_id(self, pool: str, image_id: str) -> CheckResult:
        image_id = _validate(image_id, _IMAGE_ID_RE, "image_id")
        state, raw, detail = self._omap_lookup(pool, f"id_{image_id}")
        if state != "present" or raw is None:
            return state, detail
        try:
            name = raw.decode("utf-8")
        except UnicodeDecodeError:
            return "unknown", "directory_name_non_utf8"
        if not name.startswith("volume-") or _VOLUME_ID_RE.fullmatch(name[7:]) is None:
            return "unknown", "directory_name_invalid"
        return "present", name

    @staticmethod
    def _parse_parent(parent: Any) -> tuple[str | None, str | None, str | None]:
        if not parent:
            return None, None, None
        if isinstance(parent, dict):
            pool = str(parent.get("pool") or "")
            image = str(parent.get("image") or "")
            snap = str(parent.get("snapshot") or parent.get("snap") or "")
        elif isinstance(parent, str) and "/" in parent and "@" in parent:
            pool, remainder = parent.split("/", 1)
            image, snap = remainder.rsplit("@", 1)
        else:
            raise ValueError("invalid_parent")
        for value, label in ((pool, "parent_pool"), (image, "parent_image"), (snap, "parent_snapshot")):
            _validate(value, _PARENT_COMPONENT_RE, label)
        return pool, image, snap

    @classmethod
    def _parse_image_info(cls, stdout: str) -> RbdImageInfo:
        payload = json.loads(stdout)
        if not isinstance(payload, dict):
            raise ValueError("image_info_not_object")
        image_id = _validate(str(payload.get("id") or ""), _IMAGE_ID_RE, "image_id")
        size = int(payload["size"])
        order = int(payload["order"])
        if size < 0 or order < 0 or order > 63:
            raise ValueError("invalid_image_geometry")
        parent_pool, parent_image, parent_snapshot = cls._parse_parent(payload.get("parent"))
        return RbdImageInfo(
            id=image_id,
            size=size,
            order=order,
            parent_pool=parent_pool,
            parent_image=parent_image,
            parent_snapshot=parent_snapshot,
        )

    def _image_info(self, argv: list[str]) -> tuple[CheckState, RbdImageInfo | None]:
        state, stdout, detail = self._check(argv)
        if state != "present":
            return state, None
        try:
            return "present", self._parse_image_info(stdout)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return "unknown", None

    def image_info_by_id(self, pool: str, image_id: str) -> tuple[CheckState, RbdImageInfo | None]:
        pool = _validate(pool, _POOL_RE, "pool")
        image_id = _validate(image_id, _IMAGE_ID_RE, "image_id")
        return self._image_info([*self._base("rbd"), "-p", pool, "info", "--image-id", image_id, "--format", "json"])

    def image_info_by_name(self, pool: str, name: str) -> tuple[CheckState, RbdImageInfo | None]:
        pool = _validate(pool, _POOL_RE, "pool")
        if not name.startswith("volume-") or _VOLUME_ID_RE.fullmatch(name[7:]) is None:
            raise ValueError("invalid_image_name")
        return self._image_info([*self._base("rbd"), "info", f"{pool}/{name}", "--format", "json"])

    def watchers(self, pool: str, image_id: str) -> CheckResult:
        pool = _validate(pool, _POOL_RE, "pool")
        image_id = _validate(image_id, _IMAGE_ID_RE, "image_id")
        state, stdout, detail = self._check(
            [*self._base("rados"), "-p", pool, "listwatchers", f"rbd_header.{image_id}", "--format", "json"]
        )
        if state != "present":
            return state, detail
        try:
            watchers = json.loads(stdout)
            if not isinstance(watchers, list):
                raise ValueError
            return ("present", f"watchers={len(watchers)}") if watchers else ("absent", "watchers=0")
        except (ValueError, json.JSONDecodeError):
            lines = [line for line in stdout.splitlines() if line.strip()]
            return ("present", f"watchers={len(lines)}") if lines else ("absent", "watchers=0")

    def snapshots_by_id(self, pool: str, image_id: str) -> CheckResult:
        pool = _validate(pool, _POOL_RE, "pool")
        image_id = _validate(image_id, _IMAGE_ID_RE, "image_id")
        state, stdout, detail = self._check(
            [*self._base("rbd"), "-p", pool, "snap", "ls", "--image-id", image_id, "--format", "json"]
        )
        if state != "present":
            return state, detail
        try:
            snapshots = json.loads(stdout)
            if not isinstance(snapshots, list):
                raise ValueError
            return ("present", f"snapshots={len(snapshots)}") if snapshots else ("absent", "snapshots=0")
        except (ValueError, json.JSONDecodeError):
            return "unknown", "snapshots_json_invalid"

    def children_of(
        self,
        parent_pool: str,
        parent_image: str,
        snap: str,
        *,
        image_name: str | None = None,
        image_id: str | None = None,
    ) -> CheckResult:
        parent_pool = _validate(parent_pool, _POOL_RE, "parent_pool")
        parent_image = _validate(parent_image, _PARENT_COMPONENT_RE, "parent_image")
        snap = _validate(snap, _PARENT_COMPONENT_RE, "parent_snapshot")
        if image_name is not None and (
            not image_name.startswith("volume-") or _VOLUME_ID_RE.fullmatch(image_name[7:]) is None
        ):
            raise ValueError("invalid_image_name")
        if image_id is not None:
            _validate(image_id, _IMAGE_ID_RE, "image_id")
        state, stdout, detail = self._check(
            [*self._base("rbd"), "children", f"{parent_pool}/{parent_image}@{snap}", "--all", "--format", "json"]
        )
        if state != "present":
            return state, detail
        try:
            children = json.loads(stdout)
            if not isinstance(children, list):
                raise ValueError
        except (ValueError, json.JSONDecodeError):
            return "unknown", "children_json_invalid"
        matched = False
        for child in children:
            if isinstance(child, dict):
                matched = matched or (image_name is not None and child.get("image") == image_name)
                matched = matched or (image_id is not None and child.get("id") == image_id)
            elif isinstance(child, str):
                matched = matched or (image_name is not None and child.endswith(f"/{image_name}"))
        siblings = len(children) - (1 if matched else 0)
        return ("present", f"siblings={max(siblings, 0)}") if matched else ("absent", f"siblings={len(children)}")

    def trash_contains(self, pool: str, name: str, image_id: str | None = None) -> CheckResult:
        pool = _validate(pool, _POOL_RE, "pool")
        if not name.startswith("volume-") or _VOLUME_ID_RE.fullmatch(name[7:]) is None:
            raise ValueError("invalid_image_name")
        if image_id is not None:
            _validate(image_id, _IMAGE_ID_RE, "image_id")
        state, stdout, detail = self._check([*self._base("rbd"), "trash", "ls", pool, "--format", "json"])
        if state != "present":
            return state, detail
        try:
            items = json.loads(stdout)
            if not isinstance(items, list):
                raise ValueError
        except (ValueError, json.JSONDecodeError):
            return "unknown", "trash_json_invalid"
        match = next(
            (
                item
                for item in items
                if isinstance(item, dict)
                and (item.get("name") == name or (image_id is not None and item.get("id") == image_id))
            ),
            None,
        )
        return ("present", "trash_match") if match is not None else ("absent", "trash_clear")

    def sampled_data_objects(self, pool: str, image_id: str, size_bytes: int, order: int) -> CheckResult:
        pool = _validate(pool, _POOL_RE, "pool")
        image_id = _validate(image_id, _IMAGE_ID_RE, "image_id")
        if size_bytes < 0 or order < 0 or order > 63:
            raise ValueError("invalid_image_geometry")
        object_count = math.ceil(size_bytes / (1 << order)) if size_bytes else 0
        if object_count == 0:
            return "absent", "sampled=0/0"
        indices = {0, object_count - 1}
        indices.update((step * (object_count - 1)) // 31 for step in range(1, 31))
        unknown = False
        for index in sorted(indices):
            state, _ = self.stat_object(pool, f"rbd_data.{image_id}.{index:016x}")
            if state == "present":
                return "present", f"sampled={len(indices)}/{object_count}"
            unknown = unknown or state == "unknown"
        return ("unknown" if unknown else "absent"), f"sampled={len(indices)}/{object_count}"

    def object_map_present(self, pool: str, image_id: str) -> CheckResult:
        image_id = _validate(image_id, _IMAGE_ID_RE, "image_id")
        return self.stat_object(pool, f"rbd_object_map.{image_id}")

    @staticmethod
    def name_mapping_payload(image_id: str) -> bytes:
        image_id = _validate(image_id, _IMAGE_ID_RE, "image_id")
        return struct.pack("<I", len(image_id)) + image_id.encode("ascii")

    def read_name_mapping(self, pool: str, name: str) -> tuple[CheckState, bytes | None]:
        pool = _validate(pool, _POOL_RE, "pool")
        if not name.startswith("volume-") or _VOLUME_ID_RE.fullmatch(name[7:]) is None:
            raise ValueError("invalid_image_name")
        oid = f"rbd_id.{name}"
        fd, path = tempfile.mkstemp(prefix="afterglow-rbd-id-")
        os.close(fd)
        try:
            state, _, _ = self._check([*self._base("rados"), "-p", pool, "get", oid, path])
            if state != "present":
                return state, None
            try:
                return "present", Path(path).read_bytes()
            except OSError:
                return "unknown", None
        finally:
            Path(path).unlink(missing_ok=True)

    def restore_name_mapping(self, pool: str, name: str, image_id: str) -> None:
        pool = _validate(pool, _POOL_RE, "pool")
        image_id = _validate(image_id, _IMAGE_ID_RE, "image_id")
        mapping_state, _ = self.stat_object(pool, f"rbd_id.{name}")
        if mapping_state == "present":
            raise RbdCommandError("mapping_exists")
        if mapping_state != "absent":
            raise RbdCommandError("mapping_state_unknown")
        directory_state, directory_id = self.directory_lookup(pool, name)
        if directory_state != "present" or directory_id != image_id:
            raise RbdCommandError("directory_precondition_failed")
        info_state, info = self.image_info_by_id(pool, image_id)
        if info_state != "present" or info is None or info.id != image_id:
            raise RbdCommandError("image_id_precondition_failed")
        watcher_state, _ = self.watchers(pool, image_id)
        if watcher_state != "absent":
            raise RbdCommandError("watchers_precondition_failed")
        create_argv = [*self._base("rados"), "-p", pool, "create", f"rbd_id.{name}"]
        try:
            self._required(create_argv, "mapping_create_failed")
        except RbdCommandError as exc:
            if "File exists" in exc.stderr or "EEXIST" in exc.stderr:
                raise RbdCommandError("mapping_conflict", returncode=exc.returncode, stderr=exc.stderr) from exc
            raise
        fd, path = tempfile.mkstemp(prefix="afterglow-rbd-id-put-")
        try:
            os.chmod(path, 0o600)
            os.write(fd, self.name_mapping_payload(image_id))
            os.close(fd)
            fd = -1
            self._required(
                [*self._base("rados"), "-p", pool, "put", f"rbd_id.{name}", path],
                "mapping_put_failed",
            )
        finally:
            if fd >= 0:
                os.close(fd)
            Path(path).unlink(missing_ok=True)
        verify_state, verify_info = self.image_info_by_name(pool, name)
        seen = verify_info.id if verify_info is not None else verify_state
        if verify_state != "present" or verify_info is None or verify_info.id != image_id:
            raise RbdCommandError(f"mapping_verify_failed:{seen}")

    def cleanup_stale_name_mapping(self, pool: str, name: str, image_id: str) -> None:
        expected = self.name_mapping_payload(image_id)
        mapping_state, payload = self.read_name_mapping(pool, name)
        checks: list[tuple[str, bool]] = [("mapping_payload", mapping_state == "present" and payload == expected)]
        header_state, _ = self.stat_object(pool, f"rbd_header.{image_id}")
        checks.append(("header", header_state == "absent"))
        object_map_state, _ = self.object_map_present(pool, image_id)
        checks.append(("object_map", object_map_state == "absent"))
        directory_name_state, _ = self.directory_lookup(pool, name)
        checks.append(("directory_name", directory_name_state == "absent"))
        directory_id_state, _ = self.directory_lookup_by_id(pool, image_id)
        checks.append(("directory_id", directory_id_state == "absent"))
        trash_state, _ = self.trash_contains(pool, name, image_id)
        checks.append(("trash", trash_state == "absent"))
        failed = next((label for label, ok in checks if not ok), None)
        if failed is not None:
            raise RbdCommandError(f"stale_mapping_preconditions_failed:{failed}")
        self._required([*self._base("rados"), "-p", pool, "rm", f"rbd_id.{name}"], "stale_mapping_remove_failed")


def from_settings(settings: Any) -> RbdClient | None:
    if not settings.ceph_rbd_enabled:
        return None
    return RbdClient(
        conf_path=settings.ceph_rbd_conf_path,
        keyring_path=settings.ceph_rbd_keyring_path,
        client_name=settings.ceph_rbd_client_name,
        timeout_seconds=settings.ceph_rbd_command_timeout_seconds,
    )


def pool_for_volume(settings: Any, host: str | None) -> str | None:
    if not host or "@" not in host:
        return None
    backend = host.split("@", 1)[1].split("#", 1)[0]
    if _POOL_RE.fullmatch(backend) is None and re.fullmatch(r"[A-Za-z0-9._@-]{1,64}", backend) is None:
        return None
    pool = settings.ceph_rbd_volume_pools.get(backend)
    return _validate(pool, _POOL_RE, "pool") if pool else None
