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

    def test_selects_mixed_numeric_and_historical_tags_by_version(self) -> None:
        self.assertEqual(_PROMOTER.select_tag("0.2.22", "v0.2.22", ["0.2.23", "v0.2.24"]), "v0.2.24")
        self.assertEqual(_PROMOTER.select_tag("0.2.22", None, ["v0.2.22", "0.2.23"]), "0.2.23")

    def test_equal_version_aliases_prefer_plain_tag_in_either_order(self) -> None:
        for tags in (["v0.2.23", "0.2.23"], ["0.2.23", "v0.2.23"]):
            self.assertEqual(_PROMOTER.select_tag("0.2.22", None, tags), "0.2.23")
            self.assertIsNone(_PROMOTER.select_tag("0.2.23", "0.2.23", tags))
            self.assertIsNone(_PROMOTER.select_tag("0.2.23", "v0.2.23", tags))

    def test_plain_tags_do_not_downgrade_and_matching_pins_stay_unchanged(self) -> None:
        self.assertIsNone(_PROMOTER.select_tag("0.2.23", None, ["0.2.22", "v0.2.21"]))
        self.assertIsNone(_PROMOTER.select_tag("0.2.23", "0.2.23", ["0.2.23"]))

    def test_rejects_malformed_plain_and_historical_tags(self) -> None:
        for tag in ("0.2", "0.2.23junk", "v0.2.23/extra", "00.2.23", "0.2.23-rc1", "0.2.23+build"):
            with self.subTest(tag=tag), self.assertRaises(_PROMOTER.PromotionError):
                _PROMOTER.tag_version(tag)


class VerifyTagSourceTests(unittest.TestCase):
    def test_verifies_exact_tag_identity_and_package_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            operator = Path(directory)
            for tag in ("1.32.1", "v1.32.1"):
                (operator / "pyproject.toml").write_text(
                    f'[tool.uv.sources]\ndrover = {{ git = "https://example.invalid/drover.git", tag = "{tag}" }}\n',
                    encoding="utf-8",
                )
                for resolved_tag, version, error in (
                    (tag, "1.32.1", None),
                    ("v1.32.1" if tag == "1.32.1" else "1.32.1", "1.32.1", "not resolved from tag"),
                    (tag, "1.32.0", "resolves to package version"),
                ):
                    with self.subTest(tag=tag, resolved_tag=resolved_tag, version=version):
                        (operator / "uv.lock").write_text(
                            f'[[package]]\nname = "drover"\nversion = "{version}"\n'
                            f'source = {{ git = "https://example.invalid/drover.git?tag={resolved_tag}#{"a" * 40}" }}\n',
                            encoding="utf-8",
                        )
                        if error is None:
                            _PROMOTER.verify_tag_source(operator, "drover", _PROMOTER.SERVICES["drover"])
                        else:
                            with self.assertRaisesRegex(_PROMOTER.PromotionError, error):
                                _PROMOTER.verify_tag_source(operator, "drover", _PROMOTER.SERVICES["drover"])


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

        # Commit 2: plain SemVer release tag
        (self.sibling_repo / "pyproject.toml").write_text(
            '[project]\nname = "drover"\nversion = "0.2.23"\nrequires-python = ">=3.11"\ndependencies = []\n'
            '[build-system]\nrequires = ["hatchling"]\nbuild-backend = "hatchling.build"\n',
            encoding="utf-8",
        )
        self._git("add", "pyproject.toml", cwd=self.sibling_repo)
        self._git("commit", "-m", "0.2.23 release", cwd=self.sibling_repo)
        self._git("tag", "0.2.23", cwd=self.sibling_repo)

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

        # Patch uv.lock drover source and resolved package to the local sibling repo at 0.2.22. The package
        # entry must be rewritten too; otherwise the fixture inherits the real lock's promoted version.
        patched_lock = re.sub(
            r'(\{\s*name\s*=\s*"drover",\s*git\s*=\s*")[^"]+("\s*\})',
            rf'\g<1>{repo_url}?rev={v22_sha}#{v22_sha}\g<2>',
            current_lock,
        )
        patched_lock, package_count = re.subn(
            r'(\[\[package\]\]\nname = "drover"\nversion = ")[^"]+("\nsource = \{ git = ")[^"]+(" \})',
            rf'\g<1>0.2.22\g<2>{repo_url}?rev={v22_sha}#{v22_sha}\g<3>',
            patched_lock,
        )
        assert package_count == 1, "operator lock must contain exactly one drover package entry"
        (self.operator_dir / "uv.lock").write_text(patched_lock, encoding="utf-8")

    def test_remote_tags_discover_both_styles_and_ignore_prereleases(self) -> None:
        self._git("tag", "0.2.24-rc1", cwd=self.sibling_repo)
        service = _PROMOTER.Service("drover", self.sibling_repo.as_uri())
        self.assertEqual(sorted(_PROMOTER.remote_tags(service, self.base)), ["0.2.23", "v0.2.22"])

    def test_same_commit_annotated_aliases_prefer_plain_tag(self) -> None:
        self._git("tag", "-a", "v0.2.23", "-m", "Historical alias", "0.2.23", cwd=self.sibling_repo)
        service = _PROMOTER.Service("drover", self.sibling_repo.as_uri())
        tags = _PROMOTER.remote_tags(service, self.base)
        self.assertEqual(sorted(tags), ["0.2.23", "v0.2.22", "v0.2.23"])
        self.assertEqual(_PROMOTER.select_tag("0.2.22", None, tags), "0.2.23")

    def test_conflicting_plain_and_historical_aliases_fail_closed(self) -> None:
        self._git("tag", "v0.2.23", "v0.2.22", cwd=self.sibling_repo)
        service = _PROMOTER.Service("drover", self.sibling_repo.as_uri())
        with self.assertRaisesRegex(_PROMOTER.PromotionError, "conflicting release tags"):
            _PROMOTER.remote_tags(service, self.base)

    def test_promote_higher_plain_tag_and_installer_lock_derivation(self) -> None:
        self._assert_promotion("0.2.23")

    def test_promote_higher_historical_tag_and_installer_lock_derivation(self) -> None:
        self._git("tag", "v0.2.23", "0.2.23", cwd=self.sibling_repo)
        self._git("tag", "-d", "0.2.23", cwd=self.sibling_repo)
        self._assert_promotion("v0.2.23")

    def _assert_promotion(self, release_tag: str) -> None:
        repo_url = f"file://{self.sibling_repo.resolve()}"
        orig_services = dict(_PROMOTER.SERVICES)
        _PROMOTER.SERVICES["drover"] = _PROMOTER.Service("drover", repo_url)
        try:
            changed = _PROMOTER.promote(self.operator_dir, ["drover"])
            self.assertTrue(changed)

            # The operator and lock must retain the exact advertised tag identity.
            pyproject = (self.operator_dir / "pyproject.toml").read_text(encoding="utf-8")
            self.assertIn(f'drover = {{ git = "{repo_url}", tag = "{release_tag}" }}', pyproject)
            self.assertNotIn(f'drover = {{ git = "{repo_url}", rev =', pyproject)
            # Verify uv.lock entry
            lock_text = (self.operator_dir / "uv.lock").read_text(encoding="utf-8")
            self.assertIn("drover", lock_text)
            self.assertIn("0.2.23", lock_text)
            self.assertIn(f"?tag={release_tag}#", lock_text)

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
