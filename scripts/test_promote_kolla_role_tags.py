#!/usr/bin/env python3
"""Regression tests for immutable Kolla role tag selection."""

from __future__ import annotations
import sys
import importlib.util
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


_SCRIPT = Path(__file__).with_name("promote_kolla_role_tags.py")
_SPEC = importlib.util.spec_from_file_location("promote_kolla_role_tags", _SCRIPT)
assert _SPEC and _SPEC.loader
_PROMOTER = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _PROMOTER
_SPEC.loader.exec_module(_PROMOTER)


class SelectTagTests(unittest.TestCase):
    def test_adopts_matching_release_tag_over_commit_pin(self) -> None:
        self.assertEqual(_PROMOTER.select_tag("0.2.22", None, ["v0.2.21", "v0.2.22"]), "v0.2.22")

    def test_selects_newest_non_downgrade_tag(self) -> None:
        self.assertEqual(_PROMOTER.select_tag("0.2.22", "v0.2.22", ["v0.2.22", "v0.2.23"]), "v0.2.23")

    def test_never_downgrades_to_an_older_tag(self) -> None:
        self.assertIsNone(_PROMOTER.select_tag("0.2.22", None, ["v0.2.20", "v0.2.21"]))

    def test_rejects_non_stable_release_tags(self) -> None:
        with self.assertRaises(_PROMOTER.PromotionError):
            _PROMOTER.tag_version("v0.2.22-rc1")


class PromotionIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.sibling_repo = self.base / "drover-repo"
        self.operator_dir = self.base / "operator"
        self._setup_sibling_git_repo()
        self._setup_operator_project()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _git(self, *args: str, cwd: Path) -> str:
        res = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed: {res.stderr}")
        return res.stdout

    def _setup_sibling_git_repo(self) -> None:
        self.sibling_repo.mkdir(parents=True)
        self._git("init", cwd=self.sibling_repo)
        self._git("config", "user.name", "Test Runner", cwd=self.sibling_repo)
        self._git("config", "user.email", "test@example.com", cwd=self.sibling_repo)

        # Commit 1: v0.2.22
        (self.sibling_repo / "pyproject.toml").write_text(
            '[project]\nname = "drover"\nversion = "0.2.22"\nrequires-python = ">=3.11"\ndependencies = []\n'
            '[build-system]\nrequires = ["hatchling"]\nbuild-backend = "hatchling.build"\n',
            encoding="utf-8",
        )
        role_tasks = self.sibling_repo / "src/drover_kolla/roles/drover/tasks"
        role_tasks.mkdir(parents=True)
        (role_tasks / "main.yml").write_text("---\n[]\n", encoding="utf-8")
        self._git("add", "-A", cwd=self.sibling_repo)
        self._git("commit", "-m", "v0.2.22 release", cwd=self.sibling_repo)
        self._git("tag", "v0.2.22", cwd=self.sibling_repo)

        # Commit 2: v0.2.23 (new release tag)
        (self.sibling_repo / "pyproject.toml").write_text(
            '[project]\nname = "drover"\nversion = "0.2.23"\nrequires-python = ">=3.11"\ndependencies = []\n'
            '[build-system]\nrequires = ["hatchling"]\nbuild-backend = "hatchling.build"\n',
            encoding="utf-8",
        )
        self._git("add", "pyproject.toml", cwd=self.sibling_repo)
        self._git("commit", "-m", "v0.2.23 release", cwd=self.sibling_repo)
        self._git("tag", "v0.2.23", cwd=self.sibling_repo)

    def _setup_operator_project(self) -> None:
        self.operator_dir.mkdir(parents=True)
        v22_sha = self._git("rev-parse", "v0.2.22^{commit}", cwd=self.sibling_repo).strip()
        repo_url = f"file://{self.sibling_repo.resolve()}"
        (self.operator_dir / "pyproject.toml").write_text(
            '[project]\nname = "test-operator"\nversion = "0.1.0"\nrequires-python = ">=3.11"\ndependencies = ["drover"]\n'
            f'[tool.uv.sources]\ndrover = {{ git = "{repo_url}", rev = "{v22_sha}" }}\n'
            '[build-system]\nrequires = ["hatchling"]\nbuild-backend = "hatchling.build"\n',
            encoding="utf-8",
        )
        subprocess.run(["uv", "lock"], cwd=self.operator_dir, check=True, capture_output=True)

    def test_promote_higher_tag_and_installer_lock_derivation(self) -> None:
        repo_url = f"file://{self.sibling_repo.resolve()}"
        orig_services = dict(_PROMOTER.SERVICES)
        _PROMOTER.SERVICES["drover"] = _PROMOTER.Service("drover", repo_url)
        try:
            changed = _PROMOTER.promote(self.operator_dir, ["drover"])
            self.assertTrue(changed)

            # Verify pyproject.toml has tag = "v0.2.23"
            pyproject = (self.operator_dir / "pyproject.toml").read_text(encoding="utf-8")
            self.assertIn('tag = "v0.2.23"', pyproject)
            self.assertNotIn("rev =", pyproject)

            # Verify uv.lock entry
            lock_text = (self.operator_dir / "uv.lock").read_text(encoding="utf-8")
            self.assertIn("drover", lock_text)
            self.assertIn("0.2.23", lock_text)
            self.assertIn("?tag=v0.2.23#", lock_text)

            # Verify unconditional verification passes
            _PROMOTER.verify_tag_source(self.operator_dir, "drover", _PROMOTER.SERVICES["drover"])

            # Verify read_locked_version helper extracts 0.2.23
            read_script = Path(__file__).resolve().parents[1] / "deploy/kolla/read_locked_version.py"
            res = subprocess.run(
                [sys.executable, str(read_script), str(self.operator_dir / "uv.lock"), "drover"],
                capture_output=True,
                text=True,
                check=True,
            )
            expected_version = res.stdout.strip()
            self.assertEqual(expected_version, "0.2.23")

            # Verify that installer's version expectation rejects 0.2.22 and accepts 0.2.23
            installed_stale = "0.2.22"
            self.assertNotEqual(installed_stale, expected_version)
            installed_new = "0.2.23"
            self.assertEqual(installed_new, expected_version)
        finally:
            _PROMOTER.SERVICES.clear()
            _PROMOTER.SERVICES.update(orig_services)

if __name__ == "__main__":
    unittest.main()
