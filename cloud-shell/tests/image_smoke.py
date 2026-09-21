#!/usr/bin/env python3
"""Exercise the built Cloud Shell image through its real setuid PTY bootstrap."""

from __future__ import annotations

import argparse
import base64
import json
import os
import pty
import secrets
import select
import subprocess
import time

READY = b"AFTERGLOW_CLOUD_SHELL_READY_V1\r\n"
OK = b"AFTERGLOW_CLOUD_SHELL_OK_V1\r\n"


def run(*args: str, capture_output: bool = True) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        args,
        check=True,
        capture_output=capture_output,
        timeout=120,
    )


def read_until(fd: int, marker: bytes, *, timeout: float = 20) -> bytes:
    deadline = time.monotonic() + timeout
    output = bytearray()
    while marker not in output and time.monotonic() < deadline:
        readable, _, _ = select.select([fd], [], [], 0.25)
        if not readable:
            continue
        try:
            output.extend(os.read(fd, 65536))
        except OSError:
            break
    if marker not in output:
        raise RuntimeError(f"Cloud Shell image smoke did not observe {marker!r}: {bytes(output)!r}")
    return bytes(output)


def payload(token: str) -> bytes:
    value = {
        "clouds": {
            "afterglow": {
                "auth_type": "v3token",
                "auth": {"auth_url": "https://identity.example.test/v3", "project_id": "project-smoke"},
                "region_name": "RegionOne",
                "interface": "internal",
                "identity_api_version": 3,
            }
        },
        "secure": {"clouds": {"afterglow": {"auth": {"token": token}}}},
    }
    return base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode()) + b"\n"


def bootstrap(container: str, sentinel: str) -> bytes:
    master_fd, slave_fd = pty.openpty()
    process = subprocess.Popen(
        ["docker", "exec", "-it", container, "/usr/local/bin/afterglow-cloud-shell-bootstrap"],
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        close_fds=True,
    )
    os.close(slave_fd)
    token = "smoke-secret-" + secrets.token_hex(16)
    encoded = payload(token)
    try:
        output = bytearray(read_until(master_fd, READY))
        os.write(master_fd, encoded)
        output.extend(read_until(master_fd, OK))
        command = (
            f"printf '%s' '{sentinel}' > /home/cloudshell/persisted-smoke.txt\n"
            "printf 'AFTERGLOW_UID=%s\\n' \"$(id -u)\"\n"
            "openstack --version\n"
            "printf 'AFTERGLOW_SMOKE_DONE\\n'\n"
            "exit\n"
        ).encode()
        os.write(master_fd, command)
        output.extend(read_until(master_fd, b"AFTERGLOW_SMOKE_DONE\r\n"))
        process.wait(timeout=20)
    finally:
        os.close(master_fd)
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
    result = bytes(output)
    if token.encode() in result or encoded.strip() in result:
        raise RuntimeError("Cloud Shell bootstrap echoed credential material")
    if b"AFTERGLOW_UID=1000\r\n" not in result:
        raise RuntimeError(f"Cloud Shell did not drop to UID 1000: {result!r}")
    if b"openstack " not in result:
        raise RuntimeError(f"OpenStack CLI did not execute: {result!r}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", nargs="?", default="afterglow-cloud-shell:test")
    args = parser.parse_args()
    suffix = secrets.token_hex(6)
    first = f"afterglow-cloud-shell-smoke-{suffix}"
    second = f"afterglow-cloud-shell-smoke-restart-{suffix}"
    volume = f"afterglow-cloud-shell-home-{suffix}"
    sentinel = "persistent-" + suffix
    try:
        run("docker", "run", "-d", "--name", first, "--mount", f"source={volume},target=/home/cloudshell", args.image)
        uid = run("docker", "exec", first, "id", "-u").stdout.strip()
        if uid != b"1000":
            raise RuntimeError(f"Cloud Shell container default UID is {uid!r}, expected 1000")
        bootstrap(first, sentinel)
        runtime_fs = run("docker", "exec", first, "stat", "-f", "-c", "%T", "/dev/shm").stdout.strip()
        if runtime_fs != b"tmpfs":
            raise RuntimeError(f"Cloud Shell credential runtime is not tmpfs: {runtime_fs!r}")
        secure_stat = run(
            "docker", "exec", first, "stat", "-c", "%u:%g:%a", "/dev/shm/afterglow/secure.yaml"
        ).stdout.strip()
        if secure_stat != b"1000:1000:600":
            raise RuntimeError(f"Cloud Shell secure config ownership/mode is invalid: {secure_stat!r}")
        run("docker", "exec", first, "test", "!", "-e", "/home/cloudshell/secure.yaml")
        run("docker", "rm", "-f", first)
        run("docker", "run", "-d", "--name", second, "--mount", f"source={volume},target=/home/cloudshell", args.image)
        persisted = run("docker", "exec", second, "cat", "/home/cloudshell/persisted-smoke.txt").stdout.decode()
        if persisted != sentinel:
            raise RuntimeError("Cloud Shell persistent home did not survive container replacement")
        print("Cloud Shell image smoke passed: non-root shell, private bootstrap, CLI, persistent home")
        return 0
    finally:
        subprocess.run(["docker", "rm", "-f", first, second], capture_output=True, check=False, timeout=30)
        subprocess.run(["docker", "volume", "rm", "-f", volume], capture_output=True, check=False, timeout=30)


if __name__ == "__main__":
    raise SystemExit(main())
