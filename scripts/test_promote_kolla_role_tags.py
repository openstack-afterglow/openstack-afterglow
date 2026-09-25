#!/usr/bin/env python3
"""Regression tests for immutable Kolla role tag selection."""

from __future__ import annotations
import sys
import importlib.util
import os
import re
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
        repo_root = Path(__file__).resolve().parents[1]
        # Copy actual operator pyproject.toml and uv.lock as realistic starting base
        current_pyproject = (repo_root / "deploy/kolla/operator/pyproject.toml").read_text(encoding="utf-8")
        current_lock = (repo_root / "deploy/kolla/operator/uv.lock").read_text(encoding="utf-8")

        # Override drover source to point to local sibling repo
        repo_url = f"file://{self.sibling_repo.resolve()}"
        v22_sha = self._git("rev-parse", "v0.2.22^{commit}", cwd=self.sibling_repo).strip()
        patched_pyproject = re.sub(
            r'drover = \{[^\}]+\}',
            f'drover = {{ git = "{repo_url}", rev = "{v22_sha}" }}',
            current_pyproject,
        )
        (self.operator_dir / "pyproject.toml").write_text(patched_pyproject, encoding="utf-8")

        # Patch uv.lock drover source to point to local sibling repo with 0.2.22
        patched_lock = re.sub(
            r'(\{\s*name\s*=\s*"drover",\s*git\s*=\s*")[^"]+("\s*\})',
            rf'\g<1>{repo_url}?rev={v22_sha}#{v22_sha}\g<2>',
            current_lock,
        )
        (self.operator_dir / "uv.lock").write_text(patched_lock, encoding="utf-8")

    def test_promote_higher_tag_and_installer_lock_derivation(self) -> None:
        repo_url = f"file://{self.sibling_repo.resolve()}"
        orig_services = dict(_PROMOTER.SERVICES)
        _PROMOTER.SERVICES["drover"] = _PROMOTER.Service("drover", repo_url)
        try:
            changed = _PROMOTER.promote(self.operator_dir, ["drover"])
            self.assertTrue(changed)

            # Verify pyproject.toml has drover tag = "v0.2.23" and no drover rev
            pyproject = (self.operator_dir / "pyproject.toml").read_text(encoding="utf-8")
            self.assertIn(f'drover = {{ git = "{repo_url}", tag = "v0.2.23" }}', pyproject)
            self.assertNotIn(f'drover = {{ git = "{repo_url}", rev =', pyproject)
            # Verify uv.lock entry
            lock_text = (self.operator_dir / "uv.lock").read_text(encoding="utf-8")
            self.assertIn("drover", lock_text)
            self.assertIn("0.2.23", lock_text)
            self.assertIn("?tag=v0.2.23#", lock_text)

            # Verify unconditional verification passes
            _PROMOTER.verify_tag_source(self.operator_dir, "drover", _PROMOTER.SERVICES["drover"])

            # Verify read_locked_version helper extracts the promoted fixture tag version
            read_script = Path(__file__).resolve().parents[1] / "deploy/kolla/read_locked_version.py"
            res = subprocess.run(
                [sys.executable, str(read_script), str(self.operator_dir / "uv.lock"), "drover"],
                capture_output=True,
                text=True,
                check=True,
            )
            expected_version = res.stdout.strip()
            self.assertEqual(expected_version, "0.2.23")
            # 1. Run real install.sh against promoted lock with stale installed metadata -> MUST FAIL!
            stale_res = self._run_install("0.2.22")
            self.assertNotEqual(stale_res.returncode, 0)
            self.assertIn(f"Expected drover=={expected_version} in the active Kolla environment, found '0.2.22'", stale_res.stderr)

            # 2. Run real install.sh against promoted lock with updated metadata -> MUST SUCCEED!
            success_res = self._run_install(expected_version)
            self.assertEqual(success_res.returncode, 0, f"install.sh failed: {success_res.stderr}")
            self.assertIn("Drover role verified at", success_res.stdout)
            self.assertIn(f"(drover=={expected_version})", success_res.stdout)
        finally:
            _PROMOTER.SERVICES.clear()
            _PROMOTER.SERVICES.update(orig_services)

    def _run_install(self, installed_drover_version: str) -> subprocess.CompletedProcess[str]:
        kolla_base = self.base / f"kolla-{installed_drover_version}"
        kolla_base.mkdir(parents=True, exist_ok=True)
        share_dir = kolla_base / "share/kolla-ansible"
        roles_dir = share_dir / "ansible/roles"
        etc_kolla = kolla_base / "etc/kolla"
        plugin_root = etc_kolla / "config/afterglow"
        bin_dir = kolla_base / "bin"
        metadata_dir = kolla_base / "metadata"
        for d in (roles_dir, plugin_root, bin_dir, metadata_dir):
            d.mkdir(parents=True, exist_ok=True)

        root_repo = Path(__file__).resolve().parents[1]
        read_script = root_repo / "deploy/kolla/read_locked_version.py"
        base_lock = root_repo / "deploy/kolla/operator/uv.lock"

        def locked(dist: str) -> str:
            return subprocess.run(
                [sys.executable, str(read_script), str(base_lock), dist],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()

        # Only drover is promoted here; the other roots keep whatever the real
        # operator lock currently requires so the fixture never drifts on release.
        packages = [
            ("drover", installed_drover_version),
            ("lumen", locked("lumen")),
            ("waygate", locked("waygate")),
            ("palimpsest", locked("palimpsest-client")),
        ]
        for role, ver in packages:
            rdir = roles_dir / role
            for sub in ("tasks", "defaults", "templates"):
                (rdir / sub).mkdir(parents=True, exist_ok=True)
            (rdir / "tasks/main.yml").write_text("---\n[]\n", encoding="utf-8")
            (rdir / "tasks/deploy.yml").write_text("---\n[]\n", encoding="utf-8")
            (rdir / "defaults/main.yml").write_text(f"{role}_services: {{}}\n", encoding="utf-8")
            (rdir / f"templates/{role}.conf.j2").write_text("[DEFAULT]\n", encoding="utf-8")

            dist_name = "palimpsest-client" if role == "palimpsest" else role
            dist_info = metadata_dir / f"{dist_name.replace('-', '_')}-{ver}.dist-info"
            dist_info.mkdir(parents=True, exist_ok=True)
            (dist_info / "METADATA").write_text(
                f"Metadata-Version: 2.1\nName: {dist_name}\nVersion: {ver}\n", encoding="utf-8"
            )
        # Find python with PyYAML available (matching kolla-contract.test.js)
        python_bin = subprocess.run(
            ["uv", "run", "--project", str(root_repo / "backend"), "python", "-c", "import sys; print(sys.executable)"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        fake_py = bin_dir / "python"
        fake_py.write_text(
            f'#!/usr/bin/env bash\nexport PYTHONPATH="{metadata_dir.resolve()}:$PYTHONPATH"\nexec "{python_bin}" "$@"\n',
            encoding="utf-8",
        )
        fake_py.chmod(0o755)
        fake_bin = bin_dir / "kolla-ansible"
        fake_bin.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        fake_bin.chmod(0o755)

        (share_dir / "ansible").mkdir(parents=True, exist_ok=True)
        (share_dir / "ansible/site.yml").write_text("---\n- import_playbook: gather-facts.yml\n", encoding="utf-8")
        (etc_kolla / "multinode").write_text("[control]\ncontroller\n", encoding="utf-8")
        (etc_kolla / "globals.yml").write_text("kolla_base: true\n", encoding="utf-8")
        (plugin_root / "globals.yml").write_text("enable_afterglow: true\n", encoding="utf-8")
        (plugin_root / "secrets.yml").write_text("afterglow_secret: test\n", encoding="utf-8")

        root_repo = Path(__file__).resolve().parents[1]
        env = {
            **os.environ,
            "AFTERGLOW_REPO_DIR": str(root_repo),
            "AFTERGLOW_OPERATOR_LOCK": str((self.operator_dir / "uv.lock").resolve()),
            "KOLLA_ANSIBLE_BIN": str(fake_bin),
            "KOLLA_ANSIBLE_DIR": str(share_dir),
            "KOLLA_CONFIG_PATH": str(etc_kolla),
        }
        installer = root_repo / "deploy/kolla/install.sh"
        return subprocess.run(["bash", str(installer)], env=env, capture_output=True, text=True, check=False)

if __name__ == "__main__":
    unittest.main()
