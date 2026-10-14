"""Verify Dockerfile output bytes through one durable, read-only utility VM.

The stopped builder's console is not proof. The verifier hashes every output
and reports its token-bound manifest while ACTIVE, so a handoff can observe the
same VM without SSH key material or an additional CREATE.
"""

from __future__ import annotations

import asyncio
import base64
import json
import re
import shlex
import textwrap

from app.services import build_work, manila, neutron, nova
from app.services.recipe_blocks import _NFS_EXPORT_RE, _SQSH_FILENAME_RE

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


async def _cleanup_verifier(conn, state):
    try:
        for rule in state["rules"]:
            if not rule.get("revoked"):
                await build_work.run_sync(manila.revoke_access_rule, conn, rule["share_id"], rule["access_id"])
                rule["revoked"] = True
                await build_work.journal_update(verifier=state)
        if state.get("server_id") and not state.get("deleted"):
            await build_work.run_sync(conn.compute.delete_server, state["server_id"], ignore_missing=True)
            state["deleted"] = True
            await build_work.journal_update(verifier=state)
        if state.get("port_id") and not state.get("port_deleted"):
            await build_work.run_sync(neutron.delete_port, conn, state["port_id"])
            state["port_deleted"] = True
            await build_work.journal_update(verifier=state)
    except build_work.DispatcherUnavailable:
        raise
    except Exception as exc:
        raise build_work.SubmissionUnknown("verifier cleanup awaits handoff") from exc


async def verify_builder_outputs(
    conn, *, token: str, outputs: list[dict], exports: list[list[str]], share_ids: list[str], snapshot: dict
):
    """Return only complete byte-verified reports; preserve resources on handoff."""
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
    await build_work.checkpoint()
    from app.services.dockerfile_import import (
        _accepted_id,
        _discover_import_resource,
        _import_rule,
        _parse_dockerfile_manifest,
    )
    from app.services.palimpsest_digest import DigestReport

    import_id = int(build_work.current_binding().member.split(":", 1)[1])
    state = (await build_work.journal_get()).get("verifier", {})
    config = {"token": token, "outputs": entries, "share_ids": share_ids, "snapshot": snapshot}
    if state and state.get("config") != config:
        raise ValueError("verifier context changed after admission")
    if not state:
        state = {"config": config, "rules": []}
        await build_work.journal_update(verifier=state)
    if state.get("failure"):
        await _cleanup_verifier(conn, state)
        raise RuntimeError("builder output verification failed (remote execution)")
    if not state.get("reports"):
        name = f"afterglow-import-verify-{token}"
        port_id = await _accepted_id(
            "verifier-port",
            state.get("port_id"),
            observe=lambda: _discover_import_resource(
                conn,
                "port",
                name,
                snapshot["openstack.service_project"]["id"],
                token,
                import_id,
                snapshot["builder.network"]["id"],
            ),
        )
        if port_id:
            port = await build_work.run_sync(conn.network.get_port, port_id)
        else:
            port = await build_work.submit(
                "verifier-port",
                conn.network.create_port,
                name=name,
                network_id=snapshot["builder.network"]["id"],
                description=f"afterglow-import:{import_id}:{token}",
            )
            port_id = port.id
        if port is None or not port.fixed_ips:
            raise RuntimeError("builder output verifier port is unavailable")
        fixed_ip = port.fixed_ips[0]["ip_address"]
        state["port_id"], state["fixed_ip"] = port_id, fixed_ip
        await build_work.journal_update(verifier=state)
        # A replacement can arrive long after the guest mount deadline. All
        # grants must therefore exist before the one-shot guest can ever boot.
        for index, share_id in enumerate(share_ids):
            if index < len(state["rules"]):
                continue
            access_id = await _import_rule(conn, f"verifier-ro:{index}", share_id, fixed_ip, "ro")
            state["rules"].append({"share_id": share_id, "access_id": access_id})
            await build_work.journal_update(verifier=state)
        server_id = await _accepted_id(
            "verifier-server",
            state.get("server_id"),
            observe=lambda: _discover_import_resource(
                conn, "server", name, snapshot["openstack.service_project"]["id"], token, import_id
            ),
        )
        if not server_id:
            payload = json.dumps({"token": token, "outputs": entries}, separators=(",", ":"))
            # No SSH/one-controller local key state. The VM stays ACTIVE after
            # the read-only check, retaining its serial receipt until cleanup.
            command = f"python3 -c {shlex.quote(_VERIFY_SCRIPT)} {shlex.quote(payload)}"
            user_data = (
                "#!/bin/bash\nset -euo pipefail\nexec > /dev/console 2>&1\n"
                f"trap 'echo ::AFTERGLOW::VERIFY_FAILURE::{token}' ERR\n"
                "apt-get update -qq\napt-get install -y --no-install-recommends nfs-common\n" + command + "\n"
            )
            state["user_data"] = user_data
            await build_work.journal_update(verifier=state)
            server = await build_work.submit(
                "verifier-server",
                conn.compute.create_server,
                name=name,
                image_id=snapshot["base_image"]["id"],
                flavor_id=snapshot["builder.flavor"]["id"],
                networks=[{"port": port_id}],
                user_data=base64.b64encode(user_data.encode()).decode(),
                metadata={
                    "union_type": "dockerfile-output-verifier",
                    "afterglow_managed": "true",
                    "import_id": str(import_id),
                    "build_token": token,
                },
            )
            server_id = server.id
        state["server_id"] = server_id
        await build_work.journal_update(verifier=state)
        for _ in range(60):
            server = await build_work.run_sync(conn.compute.get_server, server_id)
            if server is None or server.status == "ERROR":
                raise RuntimeError("builder output verifier is unavailable")
            if server.status == "ACTIVE":
                break
            await asyncio.sleep(10)
        else:
            raise TimeoutError("builder output verifier did not become active")
        for _ in range(90):
            console = await build_work.run_sync(nova.get_console_output, conn, server_id, None)
            if f"::AFTERGLOW::VERIFY_FAILURE::{token}" in console:
                state["failure"] = True
                await build_work.journal_update(verifier=state)
                await _cleanup_verifier(conn, state)
                raise RuntimeError("builder output verification failed (remote execution)")
            if f"::AFTERGLOW::MANIFEST::{token}::" in console:
                reports = _parse_dockerfile_manifest(console, token, [step["name"] for step in outputs])
                state["reports"] = {
                    name: {
                        "layer_name": report.layer_name,
                        "blob_digest": report.blob_digest,
                        "blob_md5": report.blob_md5,
                        "size_bytes": report.size_bytes,
                    }
                    for name, report in reports.items()
                }
                await build_work.journal_update(verifier=state)
                break
            await asyncio.sleep(10)
        else:
            raise TimeoutError("builder output verifier did not report a complete manifest")
    # Cleanup can be resumed from the receipt. Never run mutations in finally:
    # cancellation or lease loss preserves this VM and access for the next owner.
    await _cleanup_verifier(conn, state)
    return {name: DigestReport(**report) for name, report in state["reports"].items()}
