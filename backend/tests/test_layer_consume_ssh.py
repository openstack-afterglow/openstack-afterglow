"""Root consumer readiness must not depend on Nova's optional serial console."""

import base64
import os
import shlex
import stat
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import yaml

from app.services import layer_consume_ssh
from app.services.layer_build import _wait_for_consume_health, render_layer_consume_user_data

_TOKEN = "e" * 32
_VOLUME = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


def test_root_cloud_init_has_usable_temporary_key_and_post_reboot_ready_marker(tmp_path):
    path, public_key = layer_consume_ssh.create_health_key()
    try:
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
        config = yaml.safe_load(
            render_layer_consume_user_data(
                "proof",
                [("10.0.0.1:/root", "root-latest.sqsh")],
                ssh_public_key="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITest termius by jung:admin #note",
                ssh_username="ubuntu",
                root_mode=True,
                root_upper_volume_id=_VOLUME,
                digests=["sha256:" + "a" * 64],
                health_token=_TOKEN,
                health_ssh_public_key=public_key,
            )
        )
        keys = config["users"][1]["ssh_authorized_keys"]
        assert public_key in keys and len(keys) == 2
        scripts = {
            item["path"]: base64.b64decode(item["content"])
            for item in config["write_files"]
            if item.get("encoding") == "b64"
        }
        health = scripts["/etc/afterglow/layer-health.sh"]
        auto = scripts["/usr/local/bin/layer-activate-auto.sh"]
        for script in (health, auto):
            subprocess.run(["bash", "-n"], input=script, check=True)
        assert f"echo '{_TOKEN}' > {layer_consume_ssh.READY_FILE}".encode() in health
        assert b"findmnt -n -o FSTYPE /" in health
        assert b"/dev/console; } 2>/dev/null || :" in health
    finally:
        os.unlink(path)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reply,expected",
    [
        ((0, f"{_TOKEN}\noverlay\nactive\n", ""), True),
        ((0, "other\noverlay\nactive\n", ""), False),
        ((0, f"{_TOKEN}\next4\nactive\n", ""), False),
        ((0, f"{_TOKEN}\noverlay\ninactive\n", ""), False),
        ((1, f"{_TOKEN}\noverlay\nactive\n", ""), False),
    ],
)
async def test_ssh_health_requires_guest_generated_token_and_actual_overlay(reply, expected):
    with patch.object(layer_consume_ssh.ssh_executor, "run_command", new_callable=AsyncMock, return_value=reply) as run:
        assert await layer_consume_ssh.guest_root_is_ready("10.0.0.5", "ubuntu", "/tmp/proof", _TOKEN) is expected
    assert _TOKEN not in run.await_args.args[2]


@pytest.mark.asyncio
async def test_consumer_poll_accepts_verified_ssh_without_console_but_rejects_nova_error():
    conn = SimpleNamespace(compute=SimpleNamespace(get_server=lambda _id: SimpleNamespace(status="ACTIVE")))
    with (
        patch("app.services.layer_build.nova.get_console_output", side_effect=RuntimeError("console 404")),
        patch.object(
            layer_consume_ssh, "guest_root_is_ready", new_callable=AsyncMock, side_effect=[False, True]
        ) as probe,
        patch("app.services.layer_build.asyncio.sleep", new_callable=AsyncMock),
    ):
        assert (
            await _wait_for_consume_health(conn, "server", _TOKEN, ssh_host="10.0.0.5", ssh_key_path="/tmp/proof")
            is True
        )
        assert probe.await_count == 2
        conn.compute.get_server = lambda _id: SimpleNamespace(status="ERROR")
        with pytest.raises(RuntimeError, match="entered ERROR"):
            await _wait_for_consume_health(conn, "server", _TOKEN, ssh_host="10.0.0.5", ssh_key_path="/tmp/proof")


@pytest.mark.asyncio
async def test_one_use_key_removal_preserves_users_authorized_key(tmp_path):
    import pwd

    ssh = tmp_path / ".ssh"
    ssh.mkdir()
    user_key = "ssh-ed25519 AAAA-user proof-user"
    health_key = "ssh-ed25519 AAAA-health"
    authorized = ssh / "authorized_keys"
    authorized.write_text(user_key + "\n" + health_key + "\n")
    actual_pwd = pwd.getpwnam

    def fake_pwd(user):
        assert user == "ubuntu"
        return SimpleNamespace(pw_dir=str(tmp_path))

    def run_script(_host, _key_path, command, **_kwargs):
        args = shlex.split(command)
        assert args[:3] == ["sudo", "-n", "python3"]
        old_argv = sys.argv
        try:
            sys.argv = ["python3", *args[5:]]
            exec(args[4], {"__name__": "__main__"})
        finally:
            sys.argv = old_argv
        return (0, "", "")

    with (
        patch.object(pwd, "getpwnam", side_effect=fake_pwd),
        patch.object(layer_consume_ssh.ssh_executor, "run_command", new_callable=AsyncMock, side_effect=run_script),
    ):
        await layer_consume_ssh.remove_health_key("10.0.0.5", "ubuntu", "/tmp/key", health_key)
    assert authorized.read_text() == user_key + "\n"
    assert pwd.getpwnam is actual_pwd
