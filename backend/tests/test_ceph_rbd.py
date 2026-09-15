from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.services import ceph_rbd

VOLUME_ID = "676cc4e2-0000-0000-0000-000000000000"
IMAGE_NAME = f"volume-{VOLUME_ID}"
IMAGE_ID = "aa11bb22cc33"


def _proc(returncode: int = 0, stdout: str | bytes = "", stderr: str | bytes = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr=stderr)


def _client(runner) -> ceph_rbd.RbdClient:
    return ceph_rbd.RbdClient(
        conf_path="/etc/ceph/ceph.conf",
        keyring_path="/etc/ceph/ceph.client.afterglow.keyring",
        client_name="client.afterglow",
        timeout_seconds=7,
        runner=runner,
    )


def test_client_uses_argv_only_and_shared_credentials() -> None:
    calls: list[tuple[list[str], int]] = []

    def runner(argv: list[str], timeout: int) -> subprocess.CompletedProcess:
        calls.append((argv, timeout))
        return _proc(stdout="cluster-fsid\n")

    assert _client(runner).cluster_fsid() == ("present", "cluster-fsid")
    assert calls == [
        (
            [
                "ceph",
                "--conf",
                "/etc/ceph/ceph.conf",
                "--keyring",
                "/etc/ceph/ceph.client.afterglow.keyring",
                "--name",
                "client.afterglow",
                "fsid",
            ],
            7,
        )
    ]
    assert isinstance(calls[0][0], list)


def test_check_classifies_only_exact_enoent_as_absent() -> None:
    responses = iter(
        [
            _proc(2, stderr="error opening object: (2) No such file or directory"),
            _proc(2, stderr="permission denied"),
            _proc(13, stderr="(2) No such file or directory"),
        ]
    )
    client = _client(lambda _argv, _timeout: next(responses))

    assert client.stat_object("volumes", "rbd_header.aa11bb")[0] == "absent"
    assert client.stat_object("volumes", "rbd_header.aa11bb")[0] == "unknown"
    assert client.stat_object("volumes", "rbd_header.aa11bb")[0] == "unknown"


def test_directory_lookup_parses_little_endian_length_prefixed_id(tmp_path: Path) -> None:
    def runner(argv: list[str], _timeout: int) -> subprocess.CompletedProcess:
        Path(argv[-1]).write_bytes(ceph_rbd.RbdClient.name_mapping_payload(IMAGE_ID))
        return _proc()

    assert _client(runner).directory_lookup("volumes", IMAGE_NAME) == ("present", IMAGE_ID)


def test_image_info_parses_geometry_and_parent() -> None:
    payload = {
        "id": IMAGE_ID,
        "size": 32 * 1024**3,
        "order": 22,
        "parent": {"pool": "images", "image": "base-image", "snapshot": "snap"},
    }
    client = _client(lambda _argv, _timeout: _proc(stdout=json.dumps(payload)))

    state, info = client.image_info_by_id("volumes", IMAGE_ID)

    assert state == "present"
    assert info == ceph_rbd.RbdImageInfo(
        id=IMAGE_ID,
        size=32 * 1024**3,
        order=22,
        parent_pool="images",
        parent_image="base-image",
        parent_snapshot="snap",
    )


def test_sampled_data_objects_is_bounded_and_propagates_unknown() -> None:
    client = _client(lambda _argv, _timeout: _proc())
    stat = MagicMock(return_value=("absent", None))
    stat.side_effect = [("unknown", "timeout"), *[("absent", None)] * 31]
    client.stat_object = stat

    state, detail = client.sampled_data_objects("volumes", IMAGE_ID, 10 * 1024**3, 22)

    assert state == "unknown"
    assert detail == "sampled=32/2560"
    assert stat.call_count == 32


def test_restore_name_mapping_requires_exact_safe_preconditions_and_verifies() -> None:
    calls: list[list[str]] = []

    def runner(argv: list[str], _timeout: int) -> subprocess.CompletedProcess:
        calls.append(argv)
        if "put" in argv:
            assert Path(argv[-1]).read_bytes() == ceph_rbd.RbdClient.name_mapping_payload(IMAGE_ID)
        return _proc()

    client = _client(runner)
    client.stat_object = MagicMock(return_value=("absent", None))
    client.directory_lookup = MagicMock(return_value=("present", IMAGE_ID))
    client.image_info_by_id = MagicMock(return_value=("present", ceph_rbd.RbdImageInfo(id=IMAGE_ID, size=1, order=22)))
    client.watchers = MagicMock(return_value=("absent", "watchers=0"))
    client.image_info_by_name = MagicMock(
        return_value=("present", ceph_rbd.RbdImageInfo(id=IMAGE_ID, size=1, order=22))
    )

    client.restore_name_mapping("volumes", IMAGE_NAME, IMAGE_ID)

    assert any(argv[-2:] == ["create", f"rbd_id.{IMAGE_NAME}"] for argv in calls)
    assert any("put" in argv and f"rbd_id.{IMAGE_NAME}" in argv for argv in calls)


def test_restore_name_mapping_fails_closed_when_watchers_exist() -> None:
    runner = MagicMock(return_value=_proc())
    client = _client(runner)
    client.stat_object = MagicMock(return_value=("absent", None))
    client.directory_lookup = MagicMock(return_value=("present", IMAGE_ID))
    client.image_info_by_id = MagicMock(return_value=("present", ceph_rbd.RbdImageInfo(id=IMAGE_ID, size=1, order=22)))
    client.watchers = MagicMock(return_value=("present", "watchers=1"))

    with pytest.raises(ceph_rbd.RbdCommandError, match="watchers_precondition_failed"):
        client.restore_name_mapping("volumes", IMAGE_NAME, IMAGE_ID)

    runner.assert_not_called()


def test_cleanup_stale_mapping_removes_only_exact_payload_after_all_absence_checks() -> None:
    runner = MagicMock(return_value=_proc())
    client = _client(runner)
    client.read_name_mapping = MagicMock(return_value=("present", ceph_rbd.RbdClient.name_mapping_payload(IMAGE_ID)))
    client.stat_object = MagicMock(return_value=("absent", None))
    client.object_map_present = MagicMock(return_value=("absent", None))
    client.directory_lookup = MagicMock(return_value=("absent", None))
    client.directory_lookup_by_id = MagicMock(return_value=("absent", None))
    client.trash_contains = MagicMock(return_value=("absent", None))

    client.cleanup_stale_name_mapping("volumes", IMAGE_NAME, IMAGE_ID)

    rm_argv = runner.call_args.args[0]
    assert rm_argv[-4:] == ["-p", "volumes", "rm", f"rbd_id.{IMAGE_NAME}"]


def test_cleanup_stale_mapping_never_removes_on_unknown_or_payload_mismatch() -> None:
    runner = MagicMock(return_value=_proc())
    client = _client(runner)
    client.read_name_mapping = MagicMock(return_value=("present", b"wrong"))

    with pytest.raises(ceph_rbd.RbdCommandError, match="mapping_payload"):
        client.cleanup_stale_name_mapping("volumes", IMAGE_NAME, IMAGE_ID)

    assert not any("rm" in call.args[0] for call in runner.call_args_list if call.args)


def test_invalid_identifiers_never_reach_runner() -> None:
    runner = MagicMock(return_value=_proc())
    client = _client(runner)

    with pytest.raises(ValueError, match="invalid_volume_id"):
        ceph_rbd.volume_image_name("x; rados rm")
    with pytest.raises(ValueError, match="invalid_pool"):
        client.stat_object("volumes;rm", "rbd_header.aa11bb")

    runner.assert_not_called()
