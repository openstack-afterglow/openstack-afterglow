#!/usr/bin/env python3
"""Publish only the reviewed native image; no registry credentials in release assets."""

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def main():
    manifest = json.loads(
        Path("services/keystone-first-password/release-image.json").read_text()
    )
    owner = os.environ["NATIVE_IMAGE_OWNER"].lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", owner):
        raise SystemExit("Invalid registry owner")
    image_id = manifest["image_id"]
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise SystemExit("Invalid expected image identity")
    with tempfile.TemporaryDirectory(prefix="native-keystone-publish-") as directory:
        target = Path(directory)
        run(
            "gh",
            "release",
            "download",
            manifest["release"],
            "--repo",
            os.environ["GITHUB_REPOSITORY"],
            "--pattern",
            manifest["asset"],
            "--dir",
            directory,
        )
        artifact = target / manifest["asset"]
        with artifact.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != manifest["sha256"]:
            raise SystemExit("Native image artifact checksum mismatch")
        run("docker", "load", "--input", str(artifact))
        inspected = run(
            "docker", "image", "inspect", image_id, capture_output=True, text=True
        )
        image = json.loads(inspected.stdout)[0]
        if (
            image["Id"] != image_id
            or image["Architecture"] != "amd64"
            or image["Os"] != "linux"
        ):
            raise SystemExit("Native image identity/platform mismatch")
        # The checksum-pinned export retains both exact images even if the old upstream
        # registry manifest has been garbage-collected. Never substitute the moving tag.
        baseline = run(
            "docker",
            "image",
            "inspect",
            manifest["base_image_id"],
            capture_output=True,
            text=True,
        )
        base_image = json.loads(baseline.stdout)[0]
        if base_image["Id"] != manifest["base_image_id"]:
            raise SystemExit("Retained native base identity mismatch")
        base_layers = base_image["RootFS"]["Layers"]
        if image["RootFS"]["Layers"][: len(base_layers)] != base_layers:
            raise SystemExit("Native image no longer derives from retained base layers")
        base_config = base_image["Config"]
        for field in (
            "User",
            "Entrypoint",
            "Cmd",
            "Env",
            "Labels",
            "WorkingDir",
            "ExposedPorts",
            "Volumes",
            "StopSignal",
            "Healthcheck",
            "Shell",
            "ArgsEscaped",
        ):
            if image["Config"].get(field) != base_config.get(field):
                raise SystemExit(f"Native Kolla runtime configuration changed: {field}")
        run(
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--entrypoint",
            "/var/lib/kolla/venv/bin/python",
            image_id,
            "-c",
            "import importlib.metadata as m; from afterglow_keystone_first_password import verify_build; "
            "m.version('keystone') == '28.1.0' or exit('Keystone version mismatch'); "
            "verify_build(); print('native build verified')",
        )
        ref = f"ghcr.io/{owner}/keystone-first-password:{manifest['tag']}"
        run(
            "docker",
            "login",
            "ghcr.io",
            "--username",
            os.environ["GITHUB_ACTOR"],
            "--password-stdin",
            input=os.environ["GH_TOKEN"],
            text=True,
            stdout=subprocess.DEVNULL,
        )
        run("docker", "tag", image_id, ref)
        run("docker", "push", ref)
        print(f"Published {ref} from verified {image_id}")


if __name__ == "__main__":
    main()
