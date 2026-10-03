"""Verify a stopped Dockerfile builder's output through a disposable read-only VM.

Nova may discard the serial console at SHUTOFF. The guest writes its completion
manifest to its first owned Manila share; a second VM reads that manifest and
hashes *all* sealed blobs before the builder/share lifecycle can advance.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shlex
import textwrap

from app.services import builder_vm, manila, ssh_executor
from app.services.recipe_blocks import _NFS_EXPORT_RE, _SQSH_FILENAME_RE

_logger = logging.getLogger(__name__)

# Sent verbatim to the one-use Ubuntu verifier. No Afterglow installation, backend
# NFS mount privilege, or trust in the serial console is needed on that VM.
_VERIFY_SCRIPT = textwrap.dedent("""\
    import base64
    import hashlib
    import hmac
    import json
    import pathlib
    import subprocess
    import sys
    import tempfile
    import time

    config = json.loads(sys.argv[1])
    mounted = []
    with tempfile.TemporaryDirectory(prefix="afterglow-import-verify-") as workspace:
        try:
            deadline = time.monotonic() + 180
            for index, entry in enumerate(config["outputs"]):
                path = pathlib.Path(workspace) / str(index)
                path.mkdir()
                success = False
                for attempt in range(12):
                    for export in entry["exports"]:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            break
                        try:
                            result = subprocess.run(
                                ["mount", "-t", "nfs4", "-o", "ro,hard", export, str(path)],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                timeout=min(15, remaining),
                            )
                        except (OSError, subprocess.TimeoutExpired):
                            continue
                        if result.returncode == 0:
                            mounted.append(path)
                            success = True
                            break
                    if success or deadline - time.monotonic() <= 0:
                        break
                    if attempt < 11:
                        time.sleep(min(5, max(0, deadline - time.monotonic())))
                if not success:
                    raise RuntimeError("builder output mount unavailable")
            first = mounted[0] / ".afterglow-manifest.json"
            if first.stat().st_size > 1024 * 1024:
                raise ValueError("builder manifest exceeds 1MiB")
            manifest = json.loads(first.read_bytes())
            if not isinstance(manifest, dict) or not hmac.compare_digest(str(manifest.get("token", "")), config["token"]):
                raise ValueError("builder manifest token mismatch")
            reports = manifest.get("reports")
            if not isinstance(reports, list) or [row.get("name") if isinstance(row, dict) else None for row in reports] != [row["name"] for row in config["outputs"]]:
                raise ValueError("builder manifest is incomplete or reordered")
            for index, row in enumerate(reports):
                blob = mounted[index] / "images" / (config["outputs"][index]["name"] + "-latest.sqsh")
                sha256 = hashlib.sha256()
                md5 = hashlib.md5(usedforsecurity=False)
                size = 0
                with blob.open("rb") as source:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        size += len(chunk)
                        sha256.update(chunk)
                        md5.update(chunk)
                if (size <= 0 or type(row.get("size")) is not int or size != row["size"]
                    or not hmac.compare_digest(sha256.hexdigest(), str(row.get("sha256", "")))
                    or not hmac.compare_digest(md5.hexdigest(), str(row.get("md5", "")))):
                    raise ValueError("builder artifact digest or size mismatch")
        finally:
            for path in reversed(mounted):
                subprocess.run(
                    ["umount", str(path)], check=True,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15,
                )
    encoded = base64.b64encode(json.dumps(reports, separators=(",", ":")).encode("utf-8")).decode("ascii")
    print("::AFTERGLOW::MANIFEST::" + config["token"] + "::" + encoded)
""")


async def verify_builder_outputs(
    conn, *, token: str, outputs: list[dict], exports: list[list[str]], share_ids: list[str], snapshot: dict
):
    """Return digest reports only after a token-bound complete manifest and byte checks."""
    if (
        not re.fullmatch(r"[0-9a-f]{32}", token)
        or not outputs
        or len(outputs) != len(exports)
        or len(outputs) != len(share_ids)
    ):
        raise ValueError("invalid builder verification plan")
    entries = []
    for step, alternatives in zip(outputs, exports, strict=True):
        name = step["name"]
        if (
            not _SQSH_FILENAME_RE.fullmatch(f"{name}-latest.sqsh")
            or not isinstance(alternatives, list)
            or not alternatives
            or any(
                not isinstance(export, str) or not _NFS_EXPORT_RE.fullmatch(export) or not export.rpartition(":/")[0]
                for export in alternatives
            )
        ):
            raise ValueError("unsafe builder verification path")
        entries.append({"name": name, "exports": alternatives})
    builder_flavor = snapshot["builder.flavor"]["id"]
    builder_network = snapshot["builder.network"]["id"]
    image_id = snapshot["base_image"]["id"]
    verifier = None
    access_rules: list[tuple[str, str]] = []
    try:
        verifier = await builder_vm.create_ephemeral_vm(
            conn, image_id=image_id, flavor_id=builder_flavor, network_id=builder_network
        )
        for share_id in share_ids:
            existing = await asyncio.to_thread(manila.list_access_rules, conn, share_id)
            existing_ids = {rule.get("id") for rule in existing}
            rule = await asyncio.to_thread(
                manila.ensure_nfs_access_rule,
                conn,
                share_id,
                verifier.internal_ip,
                "ro",
                root_squash=False,
                sec_flavor="sys",
            )
            if rule["access_id"] not in existing_ids:
                access_rules.append((share_id, rule["access_id"]))
        payload = json.dumps({"token": token, "outputs": entries}, separators=(",", ":"))
        command = f"sudo -n python3 -c {shlex.quote(_VERIFY_SCRIPT)} {shlex.quote(payload)}"
        try:
            status, stdout, _stderr = await ssh_executor.run_command(
                verifier.host, verifier.key_path, command, username=verifier.username, timeout=900
            )
        except Exception:
            raise RuntimeError("builder output verification failed (remote execution)") from None
        if status != 0:
            raise RuntimeError(f"builder output verification failed (exit={status})")
        from app.services.dockerfile_import import _parse_dockerfile_manifest

        return _parse_dockerfile_manifest(stdout, token, [step["name"] for step in outputs])
    finally:
        cleanup_error = None
        for share_id, access_id in reversed(access_rules):
            try:
                await asyncio.to_thread(manila.revoke_access_rule, conn, share_id, access_id)
            except Exception as exc:
                _logger.warning("[dockerfile_verify] temporary access cleanup failed")
                cleanup_error = exc
        if verifier is not None:
            await builder_vm.delete_ephemeral_vm(
                conn,
                server_id=verifier.server_id,
                fip_id=verifier.fip_id,
                keypair_name=verifier.keypair_name,
                key_path=verifier.key_path,
            )
        if cleanup_error is not None:
            raise RuntimeError("temporary verifier access could not be revoked") from None
