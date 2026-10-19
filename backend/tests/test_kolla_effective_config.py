"""Behavioral boundaries for native Kolla TOML plus operator overrides."""

import importlib.util
import json
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

_FILES = Path(__file__).resolve().parents[2] / "deploy/kolla/ansible/roles/afterglow/files"
_HELPER_PATH = _FILES / "render_effective_config.py"


@pytest.fixture
def effective_config(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.syspath_prepend(str(_FILES))
    spec = importlib.util.spec_from_file_location("kolla_effective_config_renderer", _HELPER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_operator_values_win_without_discarding_native_siblings(effective_config) -> None:
    native = (
        '[app]\nsite_name = "Native Cloud"\nbackend_port = 8020\n'
        '[openstack]\nauth_url = "https://keystone.native.test/v3"\nregion_name = "NativeRegion"\n'
        '[services]\nchat = false\npalimpsest_internal_url = "https://native-hub.test"\n'
        '[custom.nested]\nretained = "native"\nreplaced = "native"\n'
    )
    operator = (
        '[app]\nsite_name = "Operator Cloud"\n'
        '[openstack]\nauth_url = "https://keystone.operator.test/v3"\n'
        '[services]\nchat = true\npalimpsest_internal_url = "https://operator-hub.test"\n'
        '[custom.nested]\nreplaced = "operator"\nadded = 7\n'
    )

    merged = effective_config.merge_config(native, operator)

    assert merged == {
        "app": {"site_name": "Operator Cloud", "backend_port": 8020},
        "openstack": {"auth_url": "https://keystone.operator.test/v3", "region_name": "NativeRegion"},
        "services": {"chat": True, "palimpsest_internal_url": "https://operator-hub.test"},
        "custom": {"nested": {"retained": "native", "replaced": "operator", "added": 7}},
    }
    assert effective_config.merge_config(native, operator) == merged


def test_removing_override_restores_current_native_value(effective_config) -> None:
    native = '[app]\nsite_name = "Native Cloud"\n[services]\nchat = true\n'
    operator = '[app]\nsite_name = "Operator Cloud"\n[services]\nchat = false\n'
    assert effective_config.merge_config(native, operator) == {
        "app": {"site_name": "Operator Cloud"},
        "services": {"chat": False},
    }

    regenerated = '[app]\nsite_name = "Regenerated Cloud"\n[services]\nchat = true\n'
    assert effective_config.merge_config(regenerated, "# All overrides removed.\n") == {
        "app": {"site_name": "Regenerated Cloud"},
        "services": {"chat": True},
    }
    assert effective_config.merge_config(regenerated, '[app]\nsite_name = "Operator Cloud"\n') == {
        "app": {"site_name": "Operator Cloud"},
        "services": {"chat": True},
    }


@pytest.mark.parametrize(
    ("native_value", "operator_value", "expected"),
    [
        ("true", "false", False),
        ("42", "0", 0),
        ('"native"', '""', ""),
        ('["native", "retained"]', "[]", []),
        ('["native", "retained"]', '["operator"]', ["operator"]),
        ('{ retained = "native" }', '["replacement"]', ["replacement"]),
        ('["native"]', '{ replacement = "operator" }', {"replacement": "operator"}),
    ],
)
def test_override_replaces_values_without_truthiness_or_list_append(
    effective_config, native_value: str, operator_value: str, expected
) -> None:
    native = f'[custom]\nvalue = {native_value}\nuntouched = "native"\n'
    operator = f"[custom]\nvalue = {operator_value}\n"

    merged = effective_config.merge_config(native, operator)

    assert merged == {"custom": {"value": expected, "untouched": "native"}}
    assert type(merged["custom"]["value"]) is type(expected)


@pytest.mark.parametrize("key_layer", ["native", "operator", "both"])
def test_legacy_builder_key_is_removed_but_other_private_settings_survive(effective_config, key_layer: str) -> None:
    native = '[builder]\nssh_user = "builder"\n[app]\nsecret_key = "backend-secret"\n'
    operator = '[builder]\nimage = "operator-image"\n[database]\nurl = "mysql://backend-only"\n'
    key = '\n[builder]\nssh_private_key = """legacy\nprivate-key\n"""\n'
    if key_layer in ("native", "both"):
        native = native.replace("[builder]\n", key.lstrip(), 1)
    if key_layer in ("operator", "both"):
        operator = operator.replace("[builder]\n", key.lstrip(), 1)

    assert effective_config.merge_config(native, operator) == {
        "builder": {"ssh_user": "builder", "image": "operator-image"},
        "app": {"secret_key": "backend-secret"},
        "database": {"url": "mysql://backend-only"},
    }


@pytest.mark.parametrize("private_key", ['"legacy-key"', "'''legacy\nkey'''", '"""legacy\nkey"""'])
def test_legacy_key_sanitization_preserves_other_operator_data_and_sources(
    effective_config, tmp_path: Path, private_key: str
) -> None:
    source = tmp_path / "operator.conf"
    original = (
        '# Operator comments remain untouched.\n[builder]\nssh_user = "builder"\n'
        f'"ssh_private_key" = {private_key}\n'
        '[custom]\nssh_private_key = "unrelated-value"\nvalues = [0, 1]\nempty = ""\n'
    )
    source.write_text(original, encoding="utf-8")
    original_stat = source.stat()

    merged = effective_config.load_merged([source])

    assert merged == {
        "builder": {"ssh_user": "builder"},
        "custom": {"ssh_private_key": "unrelated-value", "values": [0, 1], "empty": ""},
    }
    rendered = effective_config.render_toml(merged)
    assert tomllib.loads(rendered) == merged
    assert effective_config.render_toml(effective_config.load_merged([source])) == rendered
    assert source.read_text(encoding="utf-8") == original
    assert source.stat().st_ino == original_stat.st_ino
    assert source.stat().st_mtime_ns == original_stat.st_mtime_ns


@pytest.mark.parametrize("invalid_layer", ["base", "operator"])
def test_invalid_toml_is_rejected_by_merge_and_cli(effective_config, invalid_layer: str, tmp_path: Path) -> None:
    payload = {"base": '[app]\nsite_name = "Native Cloud"\n', "operator": ""}
    payload[invalid_layer] = "[DEFAULT]\ndebug = True\n"
    with pytest.raises(tomllib.TOMLDecodeError):
        effective_config.merge_config(payload["base"], payload["operator"])

    result = subprocess.run(
        [sys.executable, str(_HELPER_PATH)],
        input=json.dumps(payload),
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert result.stdout == ""
    assert list(tmp_path.iterdir()) == []


def test_cli_emits_merged_json_without_creating_files(tmp_path: Path) -> None:
    payload = {
        "base": '[app]\nsite_name = "Native Cloud"\nsecret_key = "backend-secret"\n[services]\nchat = true\n',
        "operator": '[app]\nsite_name = "Operator Cloud"\n[services]\nchat = false\n',
    }
    result = subprocess.run(
        [sys.executable, str(_HELPER_PATH)],
        input=json.dumps(payload),
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "app": {"site_name": "Operator Cloud", "secret_key": "backend-secret"},
        "services": {"chat": False},
    }
    assert list(tmp_path.iterdir()) == []


def test_effective_toml_rendering_is_stable_and_round_trips_private_values(effective_config) -> None:
    config = {
        "DEFAULT": {"debug": False},
        "app": {"site_name": 'Cloud "Operator"\n새로운', "backend_port": 0, "secret_key": "private\\key"},
        "custom.section": {"key.with.dots": "", "items": [], "ratio": 0.25, "ports": [0, 8020]},
        "custom": {"nested": {"enabled": True, "names": ["first", "second"]}},
    }

    rendered = effective_config.render_toml(config)

    assert effective_config.render_toml(config) == rendered
    assert tomllib.loads(rendered) == config
    assert effective_config.render_toml(tomllib.loads(rendered)) == rendered


def test_effective_file_loading_sanitizes_without_touching_sources(effective_config, tmp_path: Path) -> None:
    native = tmp_path / "native.conf"
    operator = tmp_path / "operator.conf"
    native.write_text(
        '[builder]\nssh_private_key = "native-legacy-key"\nssh_user = "builder"\n'
        '[custom]\nitems = ["native", "retained"]\n',
        encoding="utf-8",
    )
    operator.write_text(
        '# Operator-owned input\n[builder]\nssh_private_key = "operator-legacy-key"\n[custom]\nitems = []\n',
        encoding="utf-8",
    )
    sources = {source: source.read_bytes() for source in (native, operator)}
    original_entries = set(tmp_path.iterdir())

    assert effective_config.load_merged([native, operator]) == {
        "builder": {"ssh_user": "builder"},
        "custom": {"items": []},
    }
    assert {source: source.read_bytes() for source in sources} == sources
    assert set(tmp_path.iterdir()) == original_entries


def test_render_cli_emits_toml_without_creating_files(tmp_path: Path) -> None:
    config = {
        "app": {"site_name": "Operator Cloud", "secret_key": "backend-only"},
        "custom": {"empty": "", "disabled": False, "zero": 0, "items": []},
    }
    result = subprocess.run(
        [sys.executable, str(_HELPER_PATH), "--render"],
        input=json.dumps(config),
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert tomllib.loads(result.stdout) == config
    assert list(tmp_path.iterdir()) == []
