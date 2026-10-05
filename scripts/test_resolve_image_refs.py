#!/usr/bin/env python3
"""Offline behavior regressions: python3 scripts/test_resolve_image_refs.py.

Registry responses are fixtures; successful actual registry lookup is a separate
read-only smoke owned by the integrating parent, not evidence supplied by these tests.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


_HELPER = (
    Path(__file__).resolve().parents[1]
    / "deploy/kolla/ansible/roles/afterglow/files/resolve_image_refs.py"
)
_SPEC = importlib.util.spec_from_file_location("resolve_image_refs", _HELPER)
assert _SPEC and _SPEC.loader
_RESOLVER = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_RESOLVER)
_INDEX_DIGEST = "sha256:" + "a1" * 32
_PLATFORM_DIGEST = "sha256:" + "b2" * 32
_SECRET = "registry-password-not-for-logs"


class RegistryFixture:
    """Docker SDK RegistryData shape, with independent index/platform identities."""

    def __init__(self, digest):
        self.attrs = {
            "Descriptor": {
                "digest": digest,
                "mediaType": "application/vnd.oci.image.index.v1+json",
            },
            "Platforms": [{"os": "linux", "architecture": "amd64"}],
            "manifests": [{"digest": _PLATFORM_DIGEST}],
        }

    @property
    def id(self):
        return self.attrs["Descriptor"]["digest"]


class ResolverTests(unittest.TestCase):
    def invoke(self, request, responses=None, initialization_error=None, close_error=None):
        responses = {} if responses is None else responses

        def registry_data(ref, auth_config=None):
            response = responses[ref]
            if isinstance(response, Exception):
                raise response
            if callable(response):
                return response(auth_config)
            return response

        def close():
            if close_error is not None:
                raise close_error

        client = SimpleNamespace(
            images=SimpleNamespace(get_registry_data=registry_data), close=close
        )

        def from_env():
            if initialization_error is not None:
                raise initialization_error
            return client

        stdout, stderr = io.StringIO(), io.StringIO()
        raw = request if isinstance(request, str) else json.dumps(request)
        with (
            patch.dict(sys.modules, {"docker": SimpleNamespace(from_env=from_env)}),
            patch.object(sys, "argv", [str(_HELPER)]),
            patch.object(sys, "stdin", io.StringIO(raw)),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            status = _RESOLVER.main()
        return status, stdout.getvalue(), stderr.getvalue()

    def assert_failure(self, result, diagnostic):
        status, stdout, stderr = result
        self.assertEqual(status, 1)
        self.assertEqual(stdout, "")
        self.assertIn(diagnostic, stderr)
        self.assertNotIn(_SECRET, stderr)
        self.assertNotIn("Traceback", stderr)

    def test_bare_repositories_and_registry_ports_keep_the_index_identity(self):
        status, stdout, stderr = self.invoke(
            {"refs": {
                "hub": "ubuntu",
                "nested": "ghcr.io/team/backend",
                "port": "registry.example:5000/team/backend",
            }},
            {
                "ubuntu": RegistryFixture(_INDEX_DIGEST),
                "ghcr.io/team/backend": RegistryFixture(_INDEX_DIGEST),
                "registry.example:5000/team/backend": RegistryFixture(_INDEX_DIGEST),
            },
        )
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(json.loads(stdout), {
            "hub": f"ubuntu@{_INDEX_DIGEST}",
            "nested": f"ghcr.io/team/backend@{_INDEX_DIGEST}",
            "port": f"registry.example:5000/team/backend@{_INDEX_DIGEST}",
        })

    def test_terminal_alias_is_removed_but_not_repository_or_port(self):
        status, stdout, stderr = self.invoke(
            {"refs": {
                "latest": "registry.example:5000/latest/backend:latest",
                "stable": "registry.example:5000/stable/worker:stable",
            }},
            {
                "registry.example:5000/latest/backend:latest": RegistryFixture(_INDEX_DIGEST),
                "registry.example:5000/stable/worker:stable": RegistryFixture(_PLATFORM_DIGEST),
            },
        )
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(json.loads(stdout), {
            "latest": f"registry.example:5000/latest/backend@{_INDEX_DIGEST}",
            "stable": f"registry.example:5000/stable/worker@{_PLATFORM_DIGEST}",
        })

    def test_explicit_pins_and_source_refs_work_without_docker_installed(self):
        refs = {
            "version": "registry.example:5000/team/backend:v1.2.3",
            "other_tag": "ghcr.io/team/worker:dev",
            "suffix_tag": "ghcr.io/team/worker:v1-latest",
            "digest": f"registry.example:5000/team/backend@{_INDEX_DIGEST}",
            "tag_and_digest": f"ghcr.io/team/backend:latest@{_INDEX_DIGEST}",
            "source": "afterglow-local/backend:123456789abc",
            "source_bare": "afterglow-local/backend",
        }
        result = subprocess.run(
            [sys.executable, "-S", str(_HELPER)],
            input=json.dumps({"refs": refs}), text=True, capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        self.assertEqual(json.loads(result.stdout), refs)

    def test_malformed_digest_rejects_whole_selection(self):
        for digest in (
            None, 42, "sha256:" + "a" * 63, "sha256:" + "a" * 65,
            "sha256:" + "A" * 64, "sha512:" + "a" * 64,
            "sha256:" + "g" * 64, _INDEX_DIGEST + "\n", _SECRET,
        ):
            with self.subTest(digest=digest):
                self.assert_failure(self.invoke(
                    {"refs": {"first": "ubuntu:latest", "second": "alpine:stable"}},
                    {
                        "ubuntu:latest": RegistryFixture(_INDEX_DIGEST),
                        "alpine:stable": RegistryFixture(digest),
                    },
                ), "invalid manifest/index digest for moving image 2")

    def test_registry_failure_never_falls_back_or_emits_partial_refs(self):
        for failed_ref in ("alpine:latest", "alpine:stable", "alpine"):
            with self.subTest(ref=failed_ref):
                self.assert_failure(self.invoke(
                    {"refs": {
                        "pin": "ubuntu:v1.2.3", "first": "ubuntu:latest", "second": failed_ref,
                    }, "auth_config": {
                        "username": "operator", "password": _SECRET,
                        "serveraddress": "https://index.docker.io/v1/",
                    }},
                    {
                        "ubuntu:latest": RegistryFixture(_INDEX_DIGEST),
                        # Alternate aliases exist: falling back would falsely succeed.
                        "alpine:latest": RegistryFixture(_PLATFORM_DIGEST),
                        "alpine:stable": RegistryFixture(_PLATFORM_DIGEST),
                        "alpine": RegistryFixture(_PLATFORM_DIGEST),
                        failed_ref: RuntimeError(f"401 denied; password={_SECRET}"),
                    },
                ), "Registry lookup failed for moving image 2")

    def test_missing_distribution_descriptor_is_an_atomic_failure(self):
        malformed = RegistryFixture(_INDEX_DIGEST)
        malformed.attrs = {}
        self.assert_failure(self.invoke(
            {"refs": {"backend": "ubuntu:latest"}},
            {"ubuntu:latest": malformed},
        ), "Registry lookup failed")

    def test_docker_connection_failure_is_safe_and_has_no_json(self):
        self.assert_failure(self.invoke(
            {"refs": {"backend": "ubuntu:latest"}},
            initialization_error=RuntimeError(f"connect to https://operator:{_SECRET}@docker"),
        ), "Cannot initialize Docker")

    def test_cleanup_failure_does_not_publish_success_json(self):
        self.assert_failure(self.invoke(
            {"refs": {"backend": "ubuntu:latest"}},
            {"ubuntu:latest": RegistryFixture(_INDEX_DIGEST)},
            close_error=RuntimeError(_SECRET),
        ), "Cannot close the Docker connection")

    def test_private_registry_credentials_do_not_break_unrelated_registries(self):
        def private_registry(auth):
            if auth is None or auth.get("username") != "operator" or auth.get("password") != _SECRET:
                raise PermissionError("Private registry login required")
            return RegistryFixture(_INDEX_DIGEST)

        def unrelated_registry(auth):
            if auth is not None:
                raise PermissionError("Credentials from another registry were exposed")
            return RegistryFixture(_PLATFORM_DIGEST)

        status, stdout, stderr = self.invoke(
            {"refs": {
                "private": "registry.example:5000/team/backend:latest",
                "public": "ghcr.io/team/worker:stable",
                "other_port": "registry.example:5001/team/backend:latest",
            }, "auth_config": {
                "username": "operator", "password": _SECRET,
                "serveraddress": "https://registry.example:5000",
            }},
            {
                "registry.example:5000/team/backend:latest": private_registry,
                "ghcr.io/team/worker:stable": unrelated_registry,
                "registry.example:5001/team/backend:latest": unrelated_registry,
            },
        )
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(json.loads(stdout), {
            "private": f"registry.example:5000/team/backend@{_INDEX_DIGEST}",
            "public": f"ghcr.io/team/worker@{_PLATFORM_DIGEST}",
            "other_port": f"registry.example:5001/team/backend@{_PLATFORM_DIGEST}",
        })

    def test_docker_hub_aliases_share_the_configured_login(self):
        def private_hub(auth):
            if auth is None or auth.get("password") != _SECRET:
                raise PermissionError("Private Docker Hub repository login required")
            return RegistryFixture(_INDEX_DIGEST)

        refs = {
            "implicit": "operator/private:latest",
            "docker": "docker.io/operator/private:latest",
            "index": "index.docker.io/operator/private:latest",
            "distribution": "registry-1.docker.io/operator/private:latest",
        }
        for server in ("docker.io", "https://index.docker.io/v1/", "registry-1.docker.io"):
            with self.subTest(server=server):
                status, stdout, stderr = self.invoke(
                    {"refs": refs, "auth_config": {
                        "username": "operator", "password": _SECRET, "serveraddress": server,
                    }},
                    {ref: private_hub for ref in refs.values()},
                )
                self.assertEqual(status, 0)
                self.assertEqual(stderr, "")
                self.assertEqual(json.loads(stdout), {
                    name: f"{ref.removesuffix(':latest')}@{_INDEX_DIGEST}"
                    for name, ref in refs.items()
                })

    def test_invalid_input_never_produces_a_selected_reference_map(self):
        for request in (
            "{", [], {"refs": []}, {"refs": {"backend": None}},
            {"refs": {"backend": ""}}, {"refs": {"backend": " ubuntu:latest"}},
            {"refs": {"backend": "ubuntu\n:latest"}},
            {"refs": {"backend": "ubuntu:latest"}, "auth_config": _SECRET},
            {"refs": {"backend": "ubuntu:latest"}, "password": _SECRET},
            {"refs": {"backend": "ubuntu:latest"}, "auth_config": {
                "username": "operator", "password": _SECRET,
            }},
            {"refs": {"backend": "ubuntu:latest"}, "auth_config": {
                "username": "operator", "password": _SECRET,
                "serveraddress": f"https://operator:{_SECRET}@registry.example",
            }},
        ):
            with self.subTest(request=request):
                self.assert_failure(self.invoke(request), "Image resolution failed:")


if __name__ == "__main__":
    unittest.main()
