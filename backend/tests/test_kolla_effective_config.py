"""Behavioral boundaries for native Kolla TOML plus operator overrides."""

import importlib.util
import json
import re
import stat
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

_KOLLA = Path(__file__).resolve().parents[2] / "deploy/kolla"
_ROLE = _KOLLA / "ansible/roles/afterglow"
_FILES = _ROLE / "files"
_HELPER_PATH = _FILES / "render_effective_config.py"
_INGRESS_GENERATOR = _KOLLA / "operator/afterglow_kolla_operator/generate_ingress_secret.py"
_INGRESS_VAR = "lumen_afterglow_ingress_secret"
_INGRESS_TOML = "lumen_ingress_secret"


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


def _render_backend_template(**overrides: object) -> str:
    from jinja2 import Environment, StrictUndefined, meta

    environment = Environment(undefined=StrictUndefined)
    environment.filters.update(bool=bool, to_json=json.dumps)
    template = environment.parse((_ROLE / "templates/afterglow.conf.j2").read_text(encoding="utf-8"))
    context = dict.fromkeys(meta.find_undeclared_variables(template) - {_INGRESS_VAR}, "")
    for key in (
        "backend_port",
        "frontend_port",
        "cloud_shell_home_size_gib",
        "cloud_shell_cpu",
        "cloud_shell_memory_mib",
        "cloud_shell_idle_timeout_seconds",
        "cloud_shell_max_session_seconds",
        "cloud_shell_ticket_ttl_seconds",
        "cloud_shell_reconcile_interval_seconds",
    ):
        context["afterglow_" + key] = 1
    context["afterglow_rbd_volume_pools"] = {}
    return environment.from_string(template).render(context | overrides)


@pytest.mark.parametrize("operator_enabled", [None, False, True])
def test_instance_usage_scheduler_native_default_and_sparse_operator_override(effective_config, operator_enabled):
    native = _render_backend_template()
    assert tomllib.loads(native)["instance_usage"]["scheduler_enabled"] is False
    operator = '[app]\nsite_name = "Preserved operator"\n'
    if operator_enabled is not None:
        operator += f"[instance_usage]\nscheduler_enabled = {str(operator_enabled).lower()}\n"
    effective = tomllib.loads(effective_config.render_toml(effective_config.merge_config(native, operator)))
    assert effective["instance_usage"]["scheduler_enabled"] is bool(operator_enabled)
    assert effective["app"]["site_name"] == "Preserved operator"


@pytest.mark.parametrize(
    ("variables", "expected"),
    [
        ({}, ""),
        ({_INGRESS_VAR: None}, ""),
        ({_INGRESS_VAR: ""}, ""),
        ({_INGRESS_VAR: "🙂" * 8}, "🙂" * 8),
    ],
    ids=["absent", "null", "disabled", "exact-32-utf8-bytes"],
)
def test_kolla_ingress_secret_stays_in_private_config(effective_config, variables, expected):
    native = _render_backend_template(**variables)
    merged = effective_config.merge_config(native, "[services]\nchat = true\n")
    private = tomllib.loads(effective_config.render_toml(merged))
    assert private["services"][_INGRESS_TOML] == expected
    public = subprocess.run(
        [sys.executable, str(_FILES / "render_frontend_config.py"), "--project-json"],
        input=json.dumps({"config": merged}), capture_output=True, text=True, check=True,
    )
    projected = json.loads(public.stdout)
    assert _INGRESS_TOML not in projected["config"]["services"]
    assert _INGRESS_TOML not in projected["toml"]
    assert not expected or expected not in projected["toml"]
    assert projected["config"]["services"]["chat"] is True


@pytest.mark.parametrize(
    ("secret", "override"),
    [("é" * 15 + "x", ""), (32, ""), ("configured" * 4, '[services]\nlumen_ingress_secret = ""\n')],
    ids=["short-utf8", "not-a-string", "conflicting-operator-override"],
)
def test_kolla_ingress_secret_failures_disclose_no_config(secret, override):
    result = subprocess.run(
        [sys.executable, str(_HELPER_PATH)],
        input=json.dumps({"base": _render_backend_template(**{_INGRESS_VAR: secret}), "operator": override}),
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == "Cannot render effective Afterglow configuration; check protected inputs\n"


@pytest.mark.parametrize("source", ["sample", "null-with-comment", "missing", "explicit-empty", "existing"])
def test_kolla_ingress_generator_preserves_existing_bytes(tmp_path, source):
    path = tmp_path / "secrets.yml"
    null_line = ""
    if source == "sample":
        original = (_KOLLA / "passwords.afterglow.additions.yml").read_text(encoding="utf-8")
        assert f"\n{_INGRESS_VAR}:\n" in original
        null_line = f"{_INGRESS_VAR}:"
    else:
        original = (
            "# Keep this operator warning.\r\n"
            "unrelated: 'keep this quoting'\r\n"
            "afterglow_secret_key: !vault |\r\n"
            "  opaque vault ciphertext"
        )
        if source == "missing":
            # A final comment without a newline does not affect the preceding vault scalar.
            original += "\r\n# end of operator values"
        elif source == "null-with-comment":
            null_line = f"{_INGRESS_VAR}:  null # Keep this inline comment."
            original += f"\r\n{null_line}\r\n"
        elif source == "explicit-empty":
            original += f'\r\n{_INGRESS_VAR}: ""\r\n'
        elif source == "existing":
            original += f'\r\n{_INGRESS_VAR}: "{"é" * 16}"\r\n'
    path.write_bytes(original.encode("utf-8"))
    path.chmod(0o400 if source == "missing" else 0o600)
    original_stat = path.stat()
    command = [sys.executable, str(_INGRESS_GENERATOR), str(path)]
    result = subprocess.run(command, capture_output=True, check=False)
    configured = source in {"explicit-empty", "existing"}
    assert result.returncode == int(configured)
    assert result.stdout == b""
    assert result.stderr == (
        f"{_INGRESS_VAR} is already set; no changes were made\n".encode() if configured else b""
    )
    updated_stat = path.stat()
    assert stat.S_IMODE(updated_stat.st_mode) == stat.S_IMODE(original_stat.st_mode)
    assert (updated_stat.st_uid, updated_stat.st_gid) == (original_stat.st_uid, original_stat.st_gid)
    updated = path.read_bytes().decode("utf-8")
    if source in {"sample", "null-with-comment", "missing"}:
        match = re.search(rf'(?m)^{_INGRESS_VAR}: +("[a-f0-9]{{64}}")', updated)
        assert match is not None
        secret = match[1]
        if source == "missing":
            assert updated == original + f"\r\n{_INGRESS_VAR}: {secret}\r\n"
        elif source == "sample":
            assert updated == original.replace(null_line + "\n", null_line + f" {secret}\n")
        else:
            assert updated == original.replace(null_line, null_line.replace("null", secret))
    else:
        assert updated == original
    repeated = subprocess.run(command, capture_output=True, check=False)
    assert repeated.returncode == 1
    assert repeated.stdout == b""
    assert repeated.stderr == f"{_INGRESS_VAR} is already set; no changes were made\n".encode()
    assert path.read_bytes().decode("utf-8") == updated
    assert list(tmp_path.iterdir()) == [path]


def test_kolla_ingress_generator_does_not_race_to_replace_published_key(tmp_path):
    path = tmp_path / "secrets.yml"
    original = b"# Protected input\nother: !vault |\n  opaque\n"
    path.write_bytes(original)
    path.chmod(0o600)
    command = [sys.executable, str(_INGRESS_GENERATOR), str(path)]

    with (
        subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as first,
        subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as second,
    ):
        first_stdout, _ = first.communicate(timeout=10)
        second_stdout, _ = second.communicate(timeout=10)
    assert [first_stdout, second_stdout] == [b"", b""]
    assert sorted([first.returncode, second.returncode]) == [0, 1]
    updated = path.read_bytes()
    assert updated.startswith(original)
    assert re.fullmatch(rb'lumen_afterglow_ingress_secret: "[a-f0-9]{64}"\n', updated[len(original):])


@pytest.mark.parametrize(
    "failure",
    ["unsafe-mode", "symlink", "invalid-yaml", "short-key", "duplicate", "document-end", "clip-scalar", "flow-null"],
)
def test_kolla_ingress_generator_rejects_unsafe_input_without_disclosing_values(tmp_path, failure):
    path = tmp_path / "secrets.yml"
    original = 'afterglow_secret_key: "unrelated private material"\n'
    if failure == "invalid-yaml":
        original += f"{_INGRESS_VAR}: [SECRET WITHOUT CLOSING BRACKET"
    elif failure == "short-key":
        original += f'{_INGRESS_VAR}: "{"é" * 15}"\n'
    elif failure == "duplicate":
        original += f'{_INGRESS_VAR}:\n{_INGRESS_VAR}: ""\n'
    elif failure == "document-end":
        original += "...\n"
    elif failure == "clip-scalar":
        original += "vault_value: |\n  content without a final newline"
    elif failure == "flow-null":
        original = f'{{afterglow_secret_key: "unrelated private material", {_INGRESS_VAR}: null}}\n'
    path.write_bytes(original.encode("utf-8"))
    path.chmod(0o640 if failure == "unsafe-mode" else 0o600)
    input_path = path
    if failure == "symlink":
        input_path = tmp_path / "linked-secrets.yml"
        input_path.symlink_to(path)
    result = subprocess.run(
        [sys.executable, str(_INGRESS_GENERATOR), str(input_path)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 1
    assert result.stdout == ""
    assert "unrelated private material" not in result.stderr
    assert "SECRET WITHOUT CLOSING BRACKET" not in result.stderr
    assert "é" not in result.stderr
    assert path.read_text(encoding="utf-8") == original
    assert set(tmp_path.iterdir()) == {path, input_path}
