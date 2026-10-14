#!/usr/bin/env python3
"""Opt-in real block-consumer smoke. No SSH, payload transfer, or source publication.

Run with backend's Python environment, AFTERGLOW_TOKEN and OS_CLOUD/OS_* auth.
Default mode observes an existing consume. --exercise explicitly creates one;
--cleanup explicitly requests owner-fenced disposal through the existing API.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from contextlib import closing

import httpx
import openstack


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        required=True,
        help="Trusted Afterglow HTTPS origin, or loopback development URL",
    )
    parser.add_argument(
        "--expected-project",
        required=True,
        help="Exact owner of consumer resources (admin flow uses configured service project)",
    )
    parser.add_argument("--consume-id", type=int)
    parser.add_argument(
        "--exercise",
        action="store_true",
        help="Authorize creation of a new disposable consumer",
    )
    selected = parser.add_mutually_exclusive_group()
    selected.add_argument("--profile")
    selected.add_argument("--import-id", type=int)
    parser.add_argument("--flavor")
    parser.add_argument("--network")
    parser.add_argument("--name")
    parser.add_argument(
        "--ssh-public-key", help="Public key only; never transfers helper code"
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Authorize deletion of this run, including its server/volumes/port, not artifact sources",
    )
    args = parser.parse_args()
    token = os.environ.get("AFTERGLOW_TOKEN")
    if not token:
        parser.error("AFTERGLOW_TOKEN is required; do not put secrets on command line")
    if not args.url.startswith("https://") and not args.url.startswith(
        ("http://127.0.0.1:", "http://localhost:")
    ):
        parser.error("Use HTTPS or an explicitly local development origin")
    if args.exercise:
        if (
            args.consume_id
            or not args.flavor
            or not (args.profile or args.import_id)
            or not args.name
        ):
            parser.error(
                "--exercise requires --flavor, --name and exactly one --profile/--import-id, without --consume-id"
            )
    elif not args.consume_id:
        parser.error("Observation mode requires --consume-id")
    origin = args.url.rstrip("/") + "/api/v1/admin/libraries"
    with (
        closing(openstack.connect()) as conn,
        httpx.Client(
            headers={"Authorization": f"Bearer {token}"}, timeout=1800
        ) as client,
    ):
        conn.authorize()
        if conn.session.get_project_id() != args.expected_project:
            raise RuntimeError(
                "OpenStack observation credentials must be scoped to expected project"
            )
        marker = getattr(conn, "_afterglow_project_id", None)
        if marker is not None and marker != args.expected_project:
            raise RuntimeError(
                "OpenStack observation project marker conflicts with authenticated scope"
            )
        consume_id = args.consume_id
        if args.exercise:
            payload = {
                "transport": "block",
                "flavor_id": args.flavor,
                "server_name": args.name,
                "expected_project_id": args.expected_project,
            }
            for key, val in (
                ("profile_name", args.profile),
                ("import_id", args.import_id),
                ("network_id", args.network),
                ("ssh_public_key", args.ssh_public_key),
            ):
                if val is not None:
                    payload[key] = val
            response = client.post(origin + "/consume", json=payload)
            response.raise_for_status()
            created = response.json()
            consume_id = created["consume_id"]
            print(
                json.dumps(
                    {
                        "created_consume_id": consume_id,
                        "server_id": created["server_id"],
                    }
                ),
                flush=True,
            )
        response = client.get(f"{origin}/consumes/{consume_id}")
        response.raise_for_status()
        consume = response.json()
        if (
            consume.get("transport") != "block"
            or consume.get("project_id") != args.expected_project
        ):
            raise RuntimeError("consume transport/owner mismatch")
        resources = consume.get("resources") or []
        if not consume.get("run_id") or not resources:
            raise RuntimeError("durable run/resource evidence missing")
        observations = []
        for item in resources:
            if item["kind"] not in {"layer", "upper"} or item["state"] == "deleted":
                continue
            if not item.get("id"):
                raise RuntimeError("allocation outcome still unknown")
            volume = conn.block_storage.get_volume(item["id"])
            project = volume.project_id
            metadata = volume.metadata or {}
            if project != args.expected_project or any(
                str(metadata.get(key)) != str(value)
                for key, value in item["metadata"].items()
            ):
                raise RuntimeError("foreign resource/run identity")
            readonly = str(metadata.get("readonly", "")).lower() == "true"
            if item["kind"] == "layer" and not readonly:
                raise RuntimeError("Cinder readonly observation denied/missing")
            if volume.volume_type != item["metadata"].get("afterglow_volume_type_name"):
                raise RuntimeError("Cinder volume type differs from durable snapshot")
            if item["kind"] == "layer":
                length = int(item["metadata"]["afterglow_size_bytes"])
                if (
                    volume.size != (length + (1 << 30) - 1) // (1 << 30)
                    or volume.size > 64
                ):
                    raise RuntimeError(
                        "Cinder layer capacity/size differs from sealed payload"
                    )
            if volume.is_multiattach is not False:
                raise RuntimeError("multiattach source used for consumer")
            attachments = volume.attachments or []
            if consume["status"] == "active" and (
                volume.status != "in-use"
                or len(attachments) != 1
                or attachments[0].get("server_id") != consume["server_id"]
            ):
                raise RuntimeError("consumer attachment not exclusive/ready")
            observations.append(
                {
                    "id": volume.id,
                    "kind": item["kind"],
                    "status": volume.status,
                    "size_gib": volume.size,
                    "volume_type": volume.volume_type,
                    "readonly": readonly,
                    "attachments": attachments,
                    "payload_sha256": item["metadata"].get("afterglow_digest"),
                    "payload_size_bytes": item["metadata"].get("afterglow_size_bytes"),
                }
            )
        if (
            len(observations) + 2 > 24
            or sum(volume["size_gib"] for volume in observations) > 256
        ):
            raise RuntimeError("observed plan exceeds disk/aggregate resource bounds")
        print(
            json.dumps(
                {
                    "consume_id": consume_id,
                    "status": consume["status"],
                    "cleanup_state": consume.get("cleanup_state"),
                    "run_id": consume["run_id"],
                    "volumes": observations,
                },
                indent=2,
            )
        )
        if args.cleanup:
            response = client.delete(f"{origin}/consumes/{consume_id}")
            response.raise_for_status()
            print(
                json.dumps(
                    {
                        "cleanup": response.json() if response.content else "requested",
                        "consume_id": consume_id,
                    }
                )
            )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(
            "Block smoke failed; authentication, scope, resource or API validation did not succeed",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
