"""Shared initialization, override, private file and namespace contracts."""

import os
import stat
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from generation_config import load_config, prepare_config, write_files  # noqa: E402


def test_missing_config_uses_canonical_example_and_never_rotates(tmp_path):
    path = tmp_path / "afterglow.conf"
    cfg = load_config(path)
    assert path.is_file()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    initial = path.read_bytes()
    example = tomllib.loads((ROOT / "afterglow.conf.example").read_text())
    assert cfg["cloud_shell"] == example["cloud_shell"]
    assert len(cfg["app"]["secret_key"]) >= 32
    cfg["app"]["secret_key"] = example["app"]["secret_key"]
    assert cfg == example
    assert load_config(path)["app"]["secret_key"] != "change-me-in-production"
    assert path.read_bytes() == initial
    assert prepare_config(path).encode() == initial


@pytest.mark.parametrize("name", ["afterglow.conf", "operator.toml"])
def test_empty_and_public_frontend_overrides_are_not_backend_inputs(tmp_path, name):
    path = tmp_path / name
    path.write_text('[DEFAULT]\ndebug=false\n[app]\nsite_name="operator"\n')
    path.with_name(f"{path.stem}.a{path.suffix}").write_text("[DEFAULT]\ndebug=true\n")
    path.with_name(f"{path.stem}.empty{path.suffix}").write_text("")
    (tmp_path / "afterglow.frontend.conf").write_text('[app]\nsite_name="wrong"\n')
    (tmp_path / "config.gpu.toml").write_text("[gpu]\navailable_visible=false\n")
    cfg = load_config(path)
    assert cfg["app"]["site_name"] == "operator"
    assert cfg["DEFAULT"]["debug"] is True
    assert cfg["gpu"]["available_visible"] is False


@pytest.mark.parametrize("namespace", ["afterglow", "afterglow-dev"])
def test_k8s_direct_cli_initializes_in_caller_directory_without_operator_domain(tmp_path, namespace):
    result = subprocess.run(
        [sys.executable, str(ROOT / "generate_k8s.py"), "--namespace", namespace],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        timeout=45,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "afterglow.conf").is_file()
    output = tmp_path / "deploy/k8s"
    cm = yaml.safe_load((output / "configmap.yaml").read_text())
    assert cm["metadata"]["namespace"] == namespace
    assert "dmslab" not in cm["data"]["APP_ORIGIN"]
    assert "dmslab" not in cm["data"]["PUBLIC_API_BASE"]
    assert "dmslab" not in cm["data"]["afterglow.conf"]
    assert (output / "base/backend/deployment.yaml").is_file()
    assert (output / "kustomization.yaml").is_file()
    assert not (output / "base/worker/deployment.yaml").exists()


def test_k8s_dry_run_never_initializes_or_previews_secrets(tmp_path):
    result = subprocess.run(
        [sys.executable, str(ROOT / "generate_k8s.py"), "--dry-run"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        timeout=45,
    )
    assert result.returncode == 0, result.stderr
    assert "kind: ConfigMap" in result.stdout
    assert "kind: Secret" not in result.stdout
    assert "change-me-in-production" not in result.stdout
    assert not (tmp_path / "afterglow.conf").exists()
    assert not (tmp_path / "deploy").exists()


def test_private_writer_rejects_symlink_or_alias_without_touching_inputs(tmp_path):
    source = tmp_path / "private"
    source.write_text("protected")
    link = tmp_path / "output"
    link.symlink_to(source)
    with pytest.raises(ValueError):
        write_files({link: "replacement"})
    assert source.read_text() == "protected"
    with pytest.raises(ValueError):
        write_files({source: "one", tmp_path / "folder" / ".." / "private": "two"})
    assert source.read_text() == "protected"


def test_writer_restricts_modes_despite_permissive_umask(tmp_path):
    path = tmp_path / "private"
    path.write_text("old")
    path.chmod(0o644)
    previous = os.umask(0)
    try:
        write_files({path: "new"}, {path})
    finally:
        os.umask(previous)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.with_name("private.bak").stat().st_mode) == 0o600
