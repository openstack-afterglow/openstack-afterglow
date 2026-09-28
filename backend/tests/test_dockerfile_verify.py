"""A stopped Nova builder is trusted only after a complete token-bound blob readback."""

import hashlib
import json
import shutil
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import dockerfile_guest, dockerfile_verify
from app.services.dockerfile_import import DockerfileImportError, _parse_dockerfile_manifest, _read_dockerfile_reports

_TOKEN = "a" * 32
_NAMES = ["root-proof", "proof-01-run"]


def _digest(blob):
    return {
        "sha256": hashlib.sha256(blob).hexdigest(),
        "md5": hashlib.md5(blob, usedforsecurity=False).hexdigest(),
        "size": len(blob),
    }


def test_guest_persists_complete_manifest_before_console_output(tmp_path, monkeypatch):
    monkeypatch.setattr(dockerfile_guest, "OUTPUTS", tmp_path / "out")
    monkeypatch.setattr(dockerfile_guest, "STATE", tmp_path / "state")
    monkeypatch.setenv("AFTERGLOW_BUILD_TOKEN", _TOKEN)
    original_read = dockerfile_guest.Path.read_text

    def config_file(path, *args, **kwargs):
        if str(path).endswith("dockerfile-plan.json"):
            return "[]"
        if str(path).endswith("dockerfile-config.json"):
            return json.dumps({"ancestors": [], "root_name": "root-proof", "base_volume_id": "a" * 32, "context": None})
        return original_read(path, *args, **kwargs)

    def make_root(name, index, volume_id):
        share = dockerfile_guest.OUTPUTS / "0"
        (share / "images").mkdir(parents=True)
        blob = share / "images" / f"{name}-latest.sqsh"
        blob.write_bytes(b"real sealed squashfs")
        dockerfile_guest.report_digest(name, blob)
        return "/sealed/root"

    monkeypatch.setattr(dockerfile_guest.Path, "read_text", config_file)
    monkeypatch.setattr(dockerfile_guest, "snapshot_root", make_root)
    monkeypatch.setattr(dockerfile_guest, "REPORTS", [])
    releases = []

    def release(*args):
        assert args[0] == "umount"
        assert (dockerfile_guest.OUTPUTS / "0" / ".afterglow-manifest.json").exists()
        releases.append(args[1])

    with (
        patch("builtins.open", side_effect=OSError("no serial console")),
        patch.object(dockerfile_guest, "call", side_effect=release),
        patch.object(dockerfile_guest, "detach_image_loops"),
    ):
        dockerfile_guest.run()
    assert releases == ["/sealed/root", str(dockerfile_guest.OUTPUTS / "0")]
    saved = json.loads((dockerfile_guest.OUTPUTS / "0" / ".afterglow-manifest.json").read_text())
    assert saved == {"token": _TOKEN, "reports": [{"name": "root-proof", **_digest(b"real sealed squashfs")}]}


@pytest.mark.parametrize(
    "corruption", ["wrong-token", "missing-report", "modified-blob", "missing-blob", "missing-manifest"]
)
def test_remote_verifier_rejects_incomplete_or_tampered_artifacts(tmp_path, monkeypatch, capsys, corruption):
    shares = [tmp_path / f"share-{index}" for index in range(2)]
    reports = []
    for share, name in zip(shares, _NAMES, strict=True):
        images = share / "images"
        images.mkdir(parents=True)
        blob = (name + "-content").encode()
        (images / f"{name}-latest.sqsh").write_bytes(blob)
        reports.append({"name": name, **_digest(blob)})
    if corruption != "missing-manifest":
        (shares[0] / ".afterglow-manifest.json").write_text(
            json.dumps(
                {
                    "token": "b" * 32 if corruption == "wrong-token" else _TOKEN,
                    "reports": reports[:-1] if corruption == "missing-report" else reports,
                }
            )
        )
    if corruption == "modified-blob":
        (shares[1] / "images" / f"{_NAMES[1]}-latest.sqsh").write_bytes(b"tampered")
    if corruption == "missing-blob":
        (shares[1] / "images" / f"{_NAMES[1]}-latest.sqsh").unlink()
    config = {
        "token": _TOKEN,
        "outputs": [{"name": name, "exports": [str(share)]} for name, share in zip(_NAMES, shares)],
    }
    mounted = []

    def mount(args, **kwargs):
        if args[0] == "mount":
            assert not kwargs.get("check", False)
            assert args[4] == "ro,hard"
            assert kwargs["stdout"] == kwargs["stderr"] == subprocess.DEVNULL
            assert 0 < kwargs["timeout"] <= 15
            shutil.copytree(args[5], args[6], dirs_exist_ok=True)
            mounted.append(args[6])
        elif args[0] == "umount":
            mounted.remove(args[1])
        else:
            raise AssertionError(f"unexpected verifier command: {args[0]}")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(subprocess, "run", mount)
    monkeypatch.setattr(sys, "argv", ["python3", json.dumps(config)])
    with pytest.raises((ValueError, FileNotFoundError)):
        exec(compile(dockerfile_verify._VERIFY_SCRIPT, "<guest verifier>", "exec"), {"__name__": "__main__"})
    assert capsys.readouterr().out == ""
    assert not mounted


def test_remote_verifier_accepts_complete_bytes(tmp_path, monkeypatch, capsys):
    blob = b"actually sealed squashfs"
    share = tmp_path / "share"
    (share / "images").mkdir(parents=True)
    (share / "images" / "root-proof-latest.sqsh").write_bytes(blob)
    (share / ".afterglow-manifest.json").write_text(
        json.dumps({"token": _TOKEN, "reports": [{"name": "root-proof", **_digest(blob)}]})
    )

    def mount(args, **kwargs):
        if args[0] == "mount":
            assert args[4] == "ro,hard"
            shutil.copytree(args[5], args[6], dirs_exist_ok=True)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(subprocess, "run", mount)
    monkeypatch.setattr(
        sys,
        "argv",
        ["python3", json.dumps({"token": _TOKEN, "outputs": [{"name": "root-proof", "exports": [str(share)]}]})],
    )
    exec(compile(dockerfile_verify._VERIFY_SCRIPT, "<guest verifier>", "exec"), {"__name__": "__main__"})
    report = _parse_dockerfile_manifest(capsys.readouterr().out, _TOKEN, ["root-proof"])
    assert report["root-proof"].blob_digest == "sha256:" + hashlib.sha256(blob).hexdigest()


def test_remote_verifier_retries_access_rule_propagation(tmp_path, monkeypatch, capsys):
    blob = b"verified after Manila access propagation"
    share = tmp_path / "share"
    (share / "images").mkdir(parents=True)
    (share / "images" / "root-proof-latest.sqsh").write_bytes(blob)
    (share / ".afterglow-manifest.json").write_text(
        json.dumps({"token": _TOKEN, "reports": [{"name": "root-proof", **_digest(blob)}]})
    )
    attempts = []

    def mount(args, **kwargs):
        if args[0] == "mount":
            attempts.append(args)
            if len(attempts) == 1:
                return SimpleNamespace(returncode=32)
            shutil.copytree(args[5], args[6], dirs_exist_ok=True)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(subprocess, "run", mount)
    monkeypatch.setattr("time.sleep", lambda _: None)
    monkeypatch.setattr(
        sys,
        "argv",
        ["python3", json.dumps({"token": _TOKEN, "outputs": [{"name": "root-proof", "exports": [str(share)]}]})],
    )
    exec(compile(dockerfile_verify._VERIFY_SCRIPT, "<guest verifier>", "exec"), {"__name__": "__main__"})
    assert len(attempts) == 2
    assert _parse_dockerfile_manifest(capsys.readouterr().out, _TOKEN, ["root-proof"])["root-proof"].size_bytes == len(
        blob
    )


def test_remote_verifier_uses_second_export_when_first_unavailable(tmp_path, monkeypatch, capsys):
    blob = b"verified using the alternate NFS endpoint"
    share = tmp_path / "share"
    (share / "images").mkdir(parents=True)
    (share / "images" / "root-proof-latest.sqsh").write_bytes(blob)
    (share / ".afterglow-manifest.json").write_text(
        json.dumps({"token": _TOKEN, "reports": [{"name": "root-proof", **_digest(blob)}]})
    )
    attempts = []

    def mount(args, **kwargs):
        if args[0] == "mount":
            attempts.append(args[5])
            assert args[4] == "ro,hard"
            assert kwargs["stdout"] == kwargs["stderr"] == subprocess.DEVNULL
            assert 0 < kwargs["timeout"] <= 15
            if args[5] == "unavailable:/out":
                return SimpleNamespace(returncode=32)
            shutil.copytree(share, args[6], dirs_exist_ok=True)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(subprocess, "run", mount)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "python3",
            json.dumps(
                {
                    "token": _TOKEN,
                    "outputs": [{"name": "root-proof", "exports": ["unavailable:/out", "available:/out"]}],
                }
            ),
        ],
    )
    exec(compile(dockerfile_verify._VERIFY_SCRIPT, "<guest verifier>", "exec"), {"__name__": "__main__"})
    assert attempts == ["unavailable:/out", "available:/out"]
    report = _parse_dockerfile_manifest(capsys.readouterr().out, _TOKEN, ["root-proof"])
    assert report["root-proof"].blob_digest == "sha256:" + hashlib.sha256(blob).hexdigest()


def test_remote_verifier_fails_after_bounded_rounds_when_every_export_is_unavailable(monkeypatch, capsys):
    attempts = []
    delays = []

    def unavailable(args, **kwargs):
        assert args[0] == "mount"
        attempts.append(args[5])
        assert kwargs["stdout"] == kwargs["stderr"] == subprocess.DEVNULL
        assert 0 < kwargs["timeout"] <= 15
        return SimpleNamespace(returncode=32)

    monkeypatch.setattr(subprocess, "run", unavailable)
    monkeypatch.setattr("time.sleep", delays.append)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "python3",
            json.dumps(
                {
                    "token": _TOKEN,
                    "outputs": [{"name": "root-proof", "exports": ["first:/out", "second:/out"]}],
                }
            ),
        ],
    )
    with pytest.raises(RuntimeError, match="builder output mount unavailable"):
        exec(compile(dockerfile_verify._VERIFY_SCRIPT, "<guest verifier>", "exec"), {"__name__": "__main__"})
    assert attempts == ["first:/out", "second:/out"] * 12
    assert len(delays) == 11
    assert capsys.readouterr().out == ""


def test_remote_verifier_retries_an_alternate_after_mount_timeout(tmp_path, monkeypatch, capsys):
    blob = b"sealed"
    share = tmp_path / "share"
    (share / "images").mkdir(parents=True)
    (share / "images" / "root-proof-latest.sqsh").write_bytes(blob)
    (share / ".afterglow-manifest.json").write_text(
        json.dumps({"token": _TOKEN, "reports": [{"name": "root-proof", **_digest(blob)}]})
    )
    attempts = []

    def mount(args, **kwargs):
        if args[0] == "mount":
            attempts.append(args[5])
            if args[5] == "timed-out:/out":
                raise subprocess.TimeoutExpired(args, kwargs["timeout"])
            shutil.copytree(share, args[6], dirs_exist_ok=True)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(subprocess, "run", mount)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "python3",
            json.dumps(
                {
                    "token": _TOKEN,
                    "outputs": [{"name": "root-proof", "exports": ["timed-out:/out", "available:/out"]}],
                }
            ),
        ],
    )
    exec(compile(dockerfile_verify._VERIFY_SCRIPT, "<guest verifier>", "exec"), {"__name__": "__main__"})
    assert attempts == ["timed-out:/out", "available:/out"]
    assert _parse_dockerfile_manifest(capsys.readouterr().out, _TOKEN, ["root-proof"])["root-proof"].size_bytes == len(
        blob
    )


@pytest.mark.asyncio
async def test_console_404_uses_verified_shares_but_error_builder_never_seals():
    outputs = [{"name": "root-proof"}]
    conn = SimpleNamespace(
        compute=SimpleNamespace(get_server=MagicMock(return_value=SimpleNamespace(status="SHUTOFF")))
    )
    verified = {"root-proof": object()}
    with (
        patch("app.services.dockerfile_import.nova.get_console_output", side_effect=RuntimeError("no console")),
        patch(
            "app.services.dockerfile_verify.verify_builder_outputs", new_callable=AsyncMock, return_value=verified
        ) as fallback,
    ):
        result = await _read_dockerfile_reports(
            conn, "server", _TOKEN, outputs, [["host:/out"]], ["share"], {}, False, False
        )
        assert result is verified
        conn.compute.get_server.return_value.status = "ERROR"
        with pytest.raises(DockerfileImportError):
            await _read_dockerfile_reports(
                conn, "server", _TOKEN, outputs, [["host:/out"]], ["share"], {}, False, False
            )
        fallback.assert_awaited_once()


@pytest.mark.asyncio
async def test_console_manifest_cannot_bypass_byte_verifier_when_share_manifest_is_missing():
    import base64

    outputs = [{"name": "root-proof"}]
    encoded = base64.b64encode(json.dumps([{"name": "root-proof", **_digest(b"console-only")}]).encode()).decode()
    console = f"::AFTERGLOW::SUCCESS::{_TOKEN}\n::AFTERGLOW::MANIFEST::{_TOKEN}::{encoded}\n"
    conn = SimpleNamespace(
        compute=SimpleNamespace(get_server=MagicMock(return_value=SimpleNamespace(status="SHUTOFF")))
    )
    with (
        patch("app.services.dockerfile_import.nova.get_console_output", return_value=console),
        patch(
            "app.services.dockerfile_verify.verify_builder_outputs",
            new_callable=AsyncMock,
            side_effect=FileNotFoundError("missing share manifest"),
        ) as verifier,
    ):
        with pytest.raises(FileNotFoundError, match="missing share manifest"):
            await _read_dockerfile_reports(conn, "server", _TOKEN, outputs, [["host:/out"]], ["share"], {}, True, False)
    verifier.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exports",
    [
        [],
        ["host:/out"],
        [[]],
        [["host:/out", "bad:/path\nsecret"]],
        [["host:/out", "hostonly"]],
        [["host:/out", 42]],
    ],
)
async def test_verifier_rejects_every_malformed_export_before_vm_or_access(exports):
    snapshot = {"builder.flavor": {"id": "flavor"}, "builder.network": {"id": "network"}, "base_image": {"id": "image"}}
    with (
        patch.object(dockerfile_verify.builder_vm, "create_ephemeral_vm", new_callable=AsyncMock) as create_vm,
        patch.object(dockerfile_verify.manila, "ensure_nfs_access_rule") as grant_access,
    ):
        with pytest.raises(ValueError):
            await dockerfile_verify.verify_builder_outputs(
                object(),
                token=_TOKEN,
                outputs=[{"name": "root-proof"}],
                exports=exports,
                share_ids=["share"],
                snapshot=snapshot,
            )
    create_vm.assert_not_awaited()
    grant_access.assert_not_called()


@pytest.mark.asyncio
async def test_verifier_releases_only_its_new_access_and_disposable_vm_on_failure():
    vm = SimpleNamespace(
        host="172.30.0.2",
        internal_ip="172.30.0.2",
        username="ubuntu",
        key_path="/tmp/key",
        server_id="utility",
        fip_id=None,
        keypair_name="once",
    )
    snapshot = {"builder.flavor": {"id": "flavor"}, "builder.network": {"id": "network"}, "base_image": {"id": "image"}}
    with (
        patch.object(dockerfile_verify.builder_vm, "create_ephemeral_vm", new_callable=AsyncMock, return_value=vm),
        patch.object(dockerfile_verify.builder_vm, "delete_ephemeral_vm", new_callable=AsyncMock) as delete_vm,
        patch.object(dockerfile_verify.manila, "list_access_rules", return_value=[]) as list_rules,
        patch.object(dockerfile_verify.manila, "ensure_nfs_access_rule", return_value={"access_id": "new"}),
        patch.object(dockerfile_verify.manila, "revoke_access_rule") as revoke,
        patch.object(
            dockerfile_verify.ssh_executor,
            "run_command",
            new_callable=AsyncMock,
            return_value=(1, "", "mount 172.30.0.1:/out failed; secret=password123"),
        ),
    ):
        with pytest.raises(RuntimeError, match="verification failed") as failure:
            await dockerfile_verify.verify_builder_outputs(
                object(),
                token=_TOKEN,
                outputs=[{"name": "root-proof"}],
                exports=[["172.30.0.1:/out"]],
                share_ids=["share"],
                snapshot=snapshot,
            )
    assert "172.30.0.1" not in str(failure.value)
    assert "password123" not in str(failure.value)
    assert list_rules.call_count >= 1
    revoke.assert_called_once()
    delete_vm.assert_awaited_once()


@pytest.mark.asyncio
async def test_verifier_does_not_seal_if_temporary_access_revocation_fails():
    import base64

    vm = SimpleNamespace(
        host="172.30.0.2",
        internal_ip="172.30.0.2",
        username="ubuntu",
        key_path="/tmp/key",
        server_id="utility",
        fip_id=None,
        keypair_name="once",
    )
    snapshot = {"builder.flavor": {"id": "flavor"}, "builder.network": {"id": "network"}, "base_image": {"id": "image"}}
    encoded = base64.b64encode(json.dumps([{"name": "root-proof", **_digest(b"sealed")}]).encode()).decode()
    manifest = f"::AFTERGLOW::MANIFEST::{_TOKEN}::{encoded}\n"
    with (
        patch.object(dockerfile_verify.builder_vm, "create_ephemeral_vm", new_callable=AsyncMock, return_value=vm),
        patch.object(dockerfile_verify.builder_vm, "delete_ephemeral_vm", new_callable=AsyncMock) as delete_vm,
        patch.object(dockerfile_verify.manila, "list_access_rules", return_value=[]),
        patch.object(dockerfile_verify.manila, "ensure_nfs_access_rule", return_value={"access_id": "new"}),
        patch.object(dockerfile_verify.manila, "revoke_access_rule", side_effect=RuntimeError("Manila unavailable")),
        patch.object(
            dockerfile_verify.ssh_executor, "run_command", new_callable=AsyncMock, return_value=(0, manifest, "")
        ),
    ):
        with pytest.raises(RuntimeError, match="temporary verifier access could not be revoked"):
            await dockerfile_verify.verify_builder_outputs(
                object(),
                token=_TOKEN,
                outputs=[{"name": "root-proof"}],
                exports=[["172.30.0.1:/out"]],
                share_ids=["share"],
                snapshot=snapshot,
            )
    delete_vm.assert_awaited_once()
