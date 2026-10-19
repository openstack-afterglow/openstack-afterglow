"""Generation-only setup integration, preservation and real-terminal contracts."""

import importlib.util
import os
import pty
import select
import signal
import stat
import subprocess
import sys
import time
import tomllib
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import generate_k8s  # noqa: E402
import generation_config  # noqa: E402

_spec = importlib.util.spec_from_file_location("afterglow_setup_workflow", ROOT / "setup.py")
setup = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(setup)


def invoke(directory, *args, input=None):
    return subprocess.run(
        [sys.executable, str(ROOT / "setup.py"), *args],
        cwd=directory,
        input=input,
        text=True,
        capture_output=True,
        timeout=45,
    )


def test_first_run_and_rerun_share_canonical_config_without_secret_rotation(tmp_path):
    directory = tmp_path / "directory with spaces"
    directory.mkdir()
    password = directory / "password"
    password.write_text("synthetic-private-password", encoding="utf-8")
    result = invoke(
        directory,
        "--non-interactive",
        "--target",
        "both",
        "--set",
        'app.site_name="Chosen cloud"',
        "--set-file",
        f"openstack.password={password}",
    )
    assert result.returncode == 0, result.stderr
    config = directory / "afterglow.conf"
    original = config.read_text()
    cfg = tomllib.loads(original)
    assert cfg["app"]["site_name"] == "Chosen cloud"
    assert len(cfg["app"]["secret_key"]) >= 32
    assert cfg["cloud_shell"]["image"] == "ghcr.io/openstack-afterglow/openstack-client:slim"
    assert cfg["cloud_shell"]["image_pull_policy"] == ""
    assert cfg["cloud_shell"]["registry_id"] == ""
    assert cfg["openstack"]["password"] == "synthetic-private-password"
    artifacts = directory / "generated"
    cm = yaml.safe_load((artifacts / "k8s/configmap.yaml").read_text())
    values = yaml.safe_load((artifacts / "helm/afterglow/values-local.yaml").read_text())
    secret = yaml.safe_load((artifacts / "k8s/secret.yaml").read_text())
    assert cm["data"]["afterglow.conf"]
    assert values["app"]["siteName"] == "Chosen cloud"
    assert secret["stringData"]["SECRET_KEY"] == cfg["app"]["secret_key"]
    assert values["secrets"]["secretKey"] == cfg["app"]["secret_key"]
    assert cfg["app"]["secret_key"] not in cm["data"]["afterglow.conf"]
    assert "synthetic-private-password" not in str(cm)
    assert "synthetic-private-password" not in result.stdout + result.stderr
    assert (artifacts / "k8s/base/backend/deployment.yaml").is_file()
    assert (artifacts / "k8s/kustomization.yaml").is_file()
    assert (artifacts / "helm/afterglow/Chart.yaml").is_file()
    assert (artifacts / "helm/afterglow/templates/backend/deployment.yaml").is_file()
    # Keep unknown tables/comments and all unselected manual values on rerun.
    manual = original + '\n# Keep this operator extension\n[operator_extension]\nunknown = "retained"\n'
    config.write_text(manual)
    result = invoke(directory, "--non-interactive", "--target", "both")
    assert result.returncode == 0, result.stderr
    assert config.read_text() == manual
    assert config.with_name("afterglow.conf.bak").read_text() == manual
    assert tomllib.loads(config.read_text())["app"]["secret_key"] == cfg["app"]["secret_key"]
    for path in [
        config,
        config.with_name("afterglow.conf.bak"),
        artifacts / "k8s/secret.yaml",
        artifacts / "helm/afterglow/values-local.yaml",
    ]:
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_custom_paths_and_override_order_are_identical_for_both_generators(tmp_path):
    config = tmp_path / "private" / "custom.toml"
    config.parent.mkdir()
    config.write_text('[app]\nsecret_key = "' + "x" * 64 + '"\nsite_name = "base"\n')
    (config.parent / "custom.a.toml").write_text('[app]\nsite_name = "auto-a"\n')
    final = config.parent / "custom.z.toml"
    final.write_text('[app]\nsite_name = "explicit"\n')
    (config.parent / "afterglow.frontend.conf").write_text('[app]\nsite_name = "frontend-only"\n')
    gpu = config.parent / "config.gpu.toml"
    gpu.write_text('[[gpu.devices]]\nvendor_id="1234"\ndevice_id="5678"\nname="GPU"\nprivate_token="must-not-copy"\n')
    output = tmp_path / "elsewhere"
    result = invoke(
        tmp_path, "--non-interactive", "--config", str(config), "--output-dir", str(output), "--override", str(final)
    )
    assert result.returncode == 0, result.stderr
    cm = yaml.safe_load((output / "k8s/configmap.yaml").read_text())
    helm = yaml.safe_load((output / "helm/afterglow/values-local.yaml").read_text())
    assert tomllib.loads(cm["data"]["afterglow.conf"])["app"]["site_name"] == "explicit"
    assert helm["app"]["siteName"] == "explicit"
    assert "must-not-copy" not in str(cm)
    assert "must-not-copy" not in str(helm)
    assert config.read_text().endswith('site_name = "base"\n')
    assert not (tmp_path / "afterglow.conf").exists()


def test_explicit_auto_discovered_overrides_are_reapplied_in_argv_order(tmp_path):
    config = tmp_path / "afterglow.conf"
    config.write_text('[app]\nsite_name="base"\n')
    first = tmp_path / "afterglow.a.conf"
    last = tmp_path / "afterglow.z.conf"
    first.write_text('[app]\nsite_name="a"\n')
    last.write_text('[app]\nsite_name="z"\n')
    (tmp_path / "afterglow.frontend.conf").write_text('[app]\nsite_name="frontend"\n')
    assert generation_config.load_config(config, [last, first])["app"]["site_name"] == "a"
    assert config.read_text() == '[app]\nsite_name="base"\n'


def test_selected_edits_preserve_multiline_unknown_values_and_unselected_placeholders():
    text = '# operator comment\n[app]\nsecret_key="unchanged"\nsite_name="old" # note\n\n[unknown]\nmultiline="""\n[app]\nsite_name = fake\n"""\narr=[\n  "a",\n  "b",\n]\n'
    changed = setup.edit_config(text, "app.site_name", '"new"')
    assert changed == text.replace('site_name="old" # note', 'site_name = "new"')
    assert tomllib.loads(changed)["unknown"] == tomllib.loads(text)["unknown"]
    assert setup.edit_config(text, "app.frontend_base_url", '""').count("frontend_base_url") == 1


def test_cancel_and_invalid_input_do_not_initialize_or_overwrite(tmp_path):
    result = invoke(tmp_path, input="q\n")
    assert result.returncode == 0
    assert not (tmp_path / "afterglow.conf").exists()
    assert not (tmp_path / "generated").exists()
    config = tmp_path / "afterglow.conf"
    config.write_text('[app]\nsecret_key="invalid-existing-do-not-rotate"\n')
    original = config.read_bytes()
    result = invoke(tmp_path, "--non-interactive", "--target", "k8s")
    assert result.returncode != 0
    assert config.read_bytes() == original
    assert not config.with_name("afterglow.conf.bak").exists()
    assert not (tmp_path / "generated").exists()
    result = invoke(tmp_path, "--non-interactive", "--set", 'openstack.password="argv-secret"')
    assert result.returncode != 0
    assert "argv-secret" not in result.stdout + result.stderr
    assert config.read_bytes() == original


def test_private_file_is_exact_string_and_never_previewed(tmp_path):
    password = tmp_path / "credential"
    password.write_bytes(b"multiline-private\r\nsecond-line\n")
    result = invoke(tmp_path, "--non-interactive", "--target", "k8s", "--set-file", f"openstack.password={password}")
    assert result.returncode == 0, result.stderr
    cfg = tomllib.loads((tmp_path / "afterglow.conf").read_text())
    assert cfg["openstack"]["password"] == password.read_bytes().decode()
    secret = yaml.safe_load((tmp_path / "generated/k8s/secret.yaml").read_text())
    assert secret["stringData"]["OS_PASSWORD"] == password.read_bytes().decode()
    assert "multiline-private" not in result.stdout + result.stderr


def test_transaction_restores_existing_files_after_mid_commit_failure(tmp_path, monkeypatch):
    first, second = tmp_path / "config", tmp_path / "values"
    first.write_text("original-config")
    second.write_text("original-values")
    replace = os.replace
    calls = 0

    def fail_second(source, destination):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("synthetic write failure")
        return replace(source, destination)

    monkeypatch.setattr(generation_config.os, "replace", fail_second)
    with pytest.raises(OSError):
        generation_config.write_files({first: "new-config", second: "new-values"}, {first})
    assert first.read_text() == "original-config"
    assert second.read_text() == "original-values"
    assert not list(tmp_path.glob(".afterglow-*"))
    assert not (tmp_path / "config.bak").exists()


def test_k8s_sources_exclude_unreferenced_private_files(tmp_path):
    template = tmp_path / "template"
    for folder in ("base", "monitoring"):
        (template / folder).mkdir(parents=True)
        (template / folder / "kustomization.yaml").write_text("resources:\n  - public.yaml\n")
        (template / folder / "public.yaml").write_text("public")
        (template / folder / "private.yaml").write_text("never-copy-this")
        (template / folder / "public.yaml.bak").write_text("never-copy-backup")
    sources = generate_k8s._application_sources(template)
    assert len(sources) == 4
    assert all("never-copy" not in text for text in sources.values())


@pytest.mark.skipif(os.name != "posix", reason="Requires a controlling PTY")
@pytest.mark.parametrize("finish", ["generate", "cancel", "interrupt"])
def test_real_pty_edit_hidden_secret_and_generate_or_cancel(tmp_path, finish):
    pid, terminal = pty.fork()
    if pid == 0:
        os.chdir(tmp_path)
        os.execv(sys.executable, [sys.executable, str(ROOT / "setup.py")])
    transcript = bytearray()
    pending = bytearray()

    def expect(marker):
        deadline = time.monotonic() + 30
        while marker not in pending:
            if time.monotonic() > deadline:
                raise AssertionError(f"PTY did not reach {marker!r}")
            ready, _, _ = select.select([terminal], [], [], 1)
            if ready:
                chunk = os.read(terminal, 65536)
                if not chunk:
                    raise AssertionError("PTY ended before prompt")
                transcript.extend(chunk)
                pending.extend(chunk)
        end = pending.index(marker) + len(marker)
        del pending[:end]

    try:
        expect(b"Choice:")
        os.write(terminal, b"1\n")
        expect(b"Setting (section.key; blank cancels edit):")
        os.write(terminal, b"app.site_name\n")
        expect(b"New TOML value")
        os.write(terminal, b'"Terminal cloud"\n')
        expect(b"Choice:")
        os.write(terminal, b"1\n")
        expect(b"Setting (section.key; blank cancels edit):")
        os.write(terminal, b"openstack.password\n")
        expect(b"New private value (hidden; blank keeps current):")
        os.write(terminal, b"pty-hidden-secret-sentinel\n")
        expect(b"Choice:")
        if finish == "generate":
            os.write(terminal, b"4\n")
            expect(b"Save configuration and generate both artifacts? [y/N]:")
            assert not (tmp_path / "afterglow.conf").exists()
            os.write(terminal, b"y\n")
            expect(b"No deployment performed.")
            config = tomllib.loads((tmp_path / "afterglow.conf").read_text())
            assert config["app"]["site_name"] == "Terminal cloud"
            assert config["openstack"]["password"] == "pty-hidden-secret-sentinel"
            assert (tmp_path / "generated/k8s/secret.yaml").is_file()
            assert (tmp_path / "generated/helm/afterglow/values-local.yaml").is_file()
        else:
            os.write(terminal, b"q\n" if finish == "cancel" else b"\x03")
            expect(b"Cancelled. No files written.")
            assert not (tmp_path / "afterglow.conf").exists()
            assert not (tmp_path / "generated").exists()
        assert b"pty-hidden-secret-sentinel" not in transcript
    finally:
        os.close(terminal)
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        os.waitpid(pid, 0)
