"""One-use SSH proof that a root-overlay consumer finished booting.

Only the public half is placed in cloud-init. The private half exists on the
backend until the health check finishes, then is removed even on failure.
"""

from __future__ import annotations

import hmac
import os
import shlex
import stat
import tempfile

import asyncssh

from app.services import ssh_executor

READY_FILE = "/run/afterglow-layer-ready"


def create_health_key() -> tuple[str, str]:
    key = asyncssh.generate_private_key("ssh-ed25519")
    public_key = key.export_public_key("openssh").decode().strip()
    fd, path = tempfile.mkstemp(prefix="afterglow-layer-health-", suffix=".key")
    try:
        os.fchmod(fd, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(fd, "wb") as private:
            private.write(key.export_private_key("openssh"))
    except Exception:
        os.unlink(path)
        raise
    return path, public_key


async def guest_root_is_ready(host: str, username: str, key_path: str, token: str) -> bool:
    """Guest-produced token is never passed in the SSH command or compared by the guest."""
    try:
        rc, stdout, _ = await ssh_executor.run_command(
            host,
            key_path,
            f"sudo -n cat {READY_FILE} && findmnt -n -o FSTYPE / && systemctl is-active ssh.service",
            username=username,
            connect_timeout=3,
            timeout=10,
        )
    except (OSError, asyncssh.Error, TimeoutError):
        return False
    lines = stdout.splitlines()
    return rc == 0 and len(lines) == 3 and hmac.compare_digest(lines[0], token) and lines[1:] == ["overlay", "active"]


async def remove_health_key(host: str, username: str, key_path: str, public_key: str) -> None:
    """Remove only the one-use authorization; never alter the caller's SSH key."""
    script = (
        "import pathlib,pwd,sys; "
        "p=pathlib.Path(pwd.getpwnam(sys.argv[1]).pw_dir)/'.ssh/authorized_keys'; "
        "lines=p.read_text().splitlines(keepends=True); "
        "p.write_text(''.join(line for line in lines if line.strip()!=sys.argv[2]))"
    )
    command = f"sudo -n python3 -c {shlex.quote(script)} {shlex.quote(username)} {shlex.quote(public_key)}"
    rc, _, stderr = await ssh_executor.run_command(host, key_path, command, username=username, timeout=10)
    if rc != 0:
        raise RuntimeError(f"temporary health SSH authorization cleanup failed: {stderr.strip()[:200]}")
