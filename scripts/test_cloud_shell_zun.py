#!/usr/bin/env python3
"""Offline boundary regressions for the native Cloud Shell deployment probe."""
import contextlib
import importlib.util
import io
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch


PATH = Path(__file__).resolve().parents[1] / "deploy/kolla/ansible/roles/afterglow/files/check_cloud_shell_zun.py"
spec = importlib.util.spec_from_file_location("cloud_shell_zun_check", PATH)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
PROJECT = "c99f06f9719747c68eead4bf7578fac1"


class NativePrecheckTests(unittest.TestCase):
    def setup_native(self, authenticated_project=PROJECT, status=200, body=None):
        cloud = SimpleNamespace(
            config={"auth": {"auth_url": "https://identity.example/v3", "username": "operator", "password": "private-test-password", "project_name": "admin", "system_scope": "all"}},
            verify=True, cert=None, get_interface=lambda: "internal", get_region_name=lambda: "region",
        )
        calls = []
        closed = []
        class Session:
            def __init__(self, **kwargs):
                self.session = SimpleNamespace(close=lambda: closed.append(True))
            def get_endpoint(self, **kwargs):
                return "https://zun.example/v1/"
            def get(self, *args, **kwargs):
                calls.append(args)
                return SimpleNamespace(status_code=status, json=lambda: {"containers": []} if body is None else body)
        class Password:
            def __init__(self, **kwargs):
                pass
            def get_access(self, session):
                return SimpleNamespace(project_id=authenticated_project)
        config = SimpleNamespace(OpenStackConfig=lambda: SimpleNamespace(get_one_cloud=lambda **kwargs: cloud))
        modules = {
            "openstack": SimpleNamespace(config=config), "openstack.config": config,
            "keystoneauth1": SimpleNamespace(), "keystoneauth1.identity": SimpleNamespace(v3=SimpleNamespace(Password=Password)),
            "keystoneauth1.session": SimpleNamespace(Session=Session),
        }
        return modules, calls, closed

    def test_substituted_project_is_rejected_before_any_zun_request(self):
        modules, calls, closed = self.setup_native(authenticated_project="another-project")
        with patch.dict("sys.modules", modules), self.assertRaises(RuntimeError):
            probe.check(PROJECT)
        self.assertEqual(calls, [])
        self.assertEqual(closed, [True])

    def test_native_denial_or_invalid_list_never_becomes_readiness(self):
        for status, body in [(403, None), (503, None), (200, {"containers": {}}), (200, [])]:
            with self.subTest(status=status, body=body):
                modules, _, closed = self.setup_native(status=status, body=body)
                with patch.dict("sys.modules", modules), self.assertRaises(RuntimeError):
                    probe.check(PROJECT)
                self.assertEqual(closed, [True])

    def test_cli_does_not_publish_credential_bearing_errors(self):
        out, err = io.StringIO(), io.StringIO()
        with patch.object(probe.sys, "argv", ["probe", PROJECT]), patch.object(probe, "check", side_effect=RuntimeError("private-test-password")), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(probe.main(), 1)
        self.assertEqual(out.getvalue(), "")
        self.assertNotIn("private-test-password", err.getvalue())
        self.assertEqual(err.getvalue(), "Dedicated Cloud Shell Zun authentication/list precheck failed\n")


if __name__ == "__main__":
    unittest.main()
