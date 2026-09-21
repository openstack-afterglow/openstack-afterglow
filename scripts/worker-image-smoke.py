#!/usr/bin/env python3
"""Verify the final Notion worker image contains its crypto runtime contract."""

from __future__ import annotations

import argparse
import subprocess

_SMOKE_CODE = r'''
from importlib import metadata
from pathlib import Path
from types import SimpleNamespace

import afterglow_crypto
from app.services import k3s_crypto

key_hex = "a" * 64
settings = SimpleNamespace(
    k3s_kubeconfig_encryption_key=key_hex,
    notion_config_encryption_key=key_hex,
)
k3s_crypto.get_settings = lambda: settings

plaintext = "notion-worker-image-smoke"
ciphertext = k3s_crypto.encrypt_notion_config(plaintext)
assert ciphertext.startswith("v3:")
assert k3s_crypto.decrypt_notion_config(ciphertext) == plaintext

module_path = Path(afterglow_crypto.__file__).resolve()
distribution = metadata.distribution("afterglow-crypto")
assert "/services/afterglow-crypto" not in str(module_path), module_path
print(
    "Notion worker image smoke passed: "
    f"afterglow-crypto={distribution.version} module={module_path}"
)
'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", nargs="?", default="afterglow-worker:test")
    parser.add_argument("--platform", default="linux/amd64")
    args = parser.parse_args()

    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--platform",
            args.platform,
            "--entrypoint",
            "python",
            args.image,
            "-c",
            _SMOKE_CODE,
        ],
        check=True,
        timeout=120,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
