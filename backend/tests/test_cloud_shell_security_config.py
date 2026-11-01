"""Run configuration loaders and actual renderers across the deny-policy cutover."""

import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml
from jinja2 import Environment, StrictUndefined, meta
from pydantic import ValidationError

from app import config as app_config
from app.services.cloud_shell_security import MANDATORY_BLOCKED_CIDRS

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config2helm  # noqa: E402
import generate_k8s  # noqa: E402


@pytest.fixture
def isolated_settings(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AFTERGLOW_ENV", "development")
    for field in app_config.Settings.model_fields:
        monkeypatch.delenv(field.upper(), raising=False)
    monkeypatch.setenv("SECRET_KEY", "synthetic-shell-security-config-" + "a" * 32)
    monkeypatch.setattr(app_config, "load_raw_toml", lambda: {})
    app_config.get_settings.cache_clear()
    yield monkeypatch
    app_config.get_settings.cache_clear()


def _load(parsed, monkeypatch):
    monkeypatch.setattr(app_config, "load_raw_toml", lambda: parsed)
    return app_config.Settings(_env_file=None, **app_config._load_toml())


@pytest.mark.parametrize("blocked", [None, sorted([*MANDATORY_BLOCKED_CIDRS, "10.42.0.0/16"])])
def test_toml_kubernetes_and_helm_conversion_preserve_exact_deny_policy(isolated_settings, blocked):
    cloud_shell = {} if blocked is None else {"blocked_cidrs": blocked, "cpu": 0.25, "memory_mib": 512}
    config = {"cloud_shell": cloud_shell}
    expected = blocked if blocked is not None else list(MANDATORY_BLOCKED_CIDRS)
    native = _load(config, isolated_settings)
    assert native.cloud_shell_blocked_cidrs == expected
    generated = tomllib.loads(generate_k8s._render_toml_for_k8s(config))
    assert generated["cloud_shell"]["blocked_cidrs"] == expected
    assert _load(generated, isolated_settings).cloud_shell_blocked_cidrs == expected
    converted = config2helm.convert(config, False)
    if blocked is not None:
        assert converted["cloudShell"]["blockedCidrs"] == expected
        assert converted["cloudShell"]["cpu"] == 0.25
        assert converted["cloudShell"]["memoryMib"] == 512
    else:
        defaults = yaml.safe_load((ROOT / "helm/afterglow/values.yaml").read_text())
        assert defaults["cloudShell"]["blockedCidrs"] == expected


def test_environment_deny_policy_overrides_toml_without_losing_mandatory_blocks(isolated_settings):
    blocked = sorted([*MANDATORY_BLOCKED_CIDRS, "10.42.0.0/16"])
    isolated_settings.setenv("CLOUD_SHELL_BLOCKED_CIDRS", json.dumps(blocked))
    assert app_config.get_settings().cloud_shell_blocked_cidrs == blocked


@pytest.mark.parametrize(
    "invalid",
    [
        [],
        ["169.254.169.254/32"],
        list(MANDATORY_BLOCKED_CIDRS[:2]),
        [*MANDATORY_BLOCKED_CIDRS, "10.0.0.1/24"],
        [*MANDATORY_BLOCKED_CIDRS, "FD00:EC2::254/128"],
        [*MANDATORY_BLOCKED_CIDRS, "169.254.169.254/32"],
        [*MANDATORY_BLOCKED_CIDRS, 123],
    ],
)
def test_config_refuses_metadata_route_omission_and_noncanonical_cidrs(isolated_settings, invalid):
    with pytest.raises(ValidationError):
        _load({"cloud_shell": {"blocked_cidrs": invalid}}, isolated_settings)
    isolated_settings.setenv("CLOUD_SHELL_BLOCKED_CIDRS", json.dumps(invalid))
    with pytest.raises(ValidationError):
        app_config.get_settings()


@pytest.mark.parametrize(
    "field,value", [("cpu", 1.01), ("cpu", 0), ("cpu", float("nan")), ("memory_mib", 1025), ("memory_mib", 255)]
)
def test_config_does_not_allow_runtime_profile_resource_override(isolated_settings, field, value):
    with pytest.raises(ValidationError):
        _load({"cloud_shell": {field: value}}, isolated_settings)


@pytest.mark.parametrize("custom", [False, True])
def test_actual_helm_configmap_preserves_native_policy(isolated_settings, tmp_path, custom):
    helm = shutil.which("helm")
    if helm is None:
        pytest.skip("Helm is required for the actual chart rendering contract")
    blocked = sorted([*MANDATORY_BLOCKED_CIDRS, "10.42.0.0/16"]) if custom else list(MANDATORY_BLOCKED_CIDRS)
    config = {"cloud_shell": {"blocked_cidrs": blocked}} if custom else {}
    values = tmp_path / "values.yaml"
    values.write_text(config2helm.render_values(config, False))
    rendered = subprocess.run(
        [helm, "template", "afterglow", str(ROOT / "helm/afterglow"), "-f", str(values)],
        capture_output=True,
        text=True,
        check=True,
    )
    configmap = next(
        item
        for item in yaml.safe_load_all(rendered.stdout)
        if item.get("kind") == "ConfigMap" and "afterglow.conf" in item.get("data", {})
    )
    parsed = tomllib.loads(configmap["data"]["afterglow.conf"])
    assert parsed["cloud_shell"]["blocked_cidrs"] == blocked
    assert _load(parsed, isolated_settings).cloud_shell_blocked_cidrs == blocked


def test_actual_kolla_template_defaults_and_override_preserve_policy(isolated_settings):
    role = ROOT / "deploy/kolla/ansible/roles/afterglow"
    defaults = yaml.safe_load((role / "defaults/main.yml").read_text())
    environment = Environment(undefined=StrictUndefined)
    environment.filters.update(bool=bool, to_json=json.dumps)
    source = (role / "templates/afterglow.conf.j2").read_text()
    context = dict.fromkeys(meta.find_undeclared_variables(environment.parse(source)), "")
    context.update({key: value for key, value in defaults.items() if key in context})
    context.update(
        afterglow_backend_port=8000,
        afterglow_frontend_port=3080,
        afterglow_cloud_shell_auth_url="",
        afterglow_rbd_volume_pools={},
    )
    template = environment.from_string(source)
    for blocked in (list(MANDATORY_BLOCKED_CIDRS), sorted([*MANDATORY_BLOCKED_CIDRS, "10.42.0.0/16"])):
        context["afterglow_cloud_shell_blocked_cidrs"] = blocked
        parsed = tomllib.loads(template.render(context))
        assert parsed["cloud_shell"]["blocked_cidrs"] == blocked
        # Validate only this section: other native defaults contain operator Jinja
        # expressions which the full Ansible context, not this fixture, resolves.
        assert _load({"cloud_shell": parsed["cloud_shell"]}, isolated_settings).cloud_shell_blocked_cidrs == blocked


@pytest.mark.parametrize(
    "override,accepted",
    [
        ({}, True),
        ({"cpu": 0.25, "memory_mib": 256}, True),
        ({"cpu": 1.01}, False),
        ({"memory_mib": 1025}, False),
        ({"blocked_cidrs": []}, False),
        ({"blocked_cidrs": list(MANDATORY_BLOCKED_CIDRS[:2])}, False),
        ({"blocked_cidrs": "169.254.169.254/32"}, False),
        ({"cpu": 0.01}, True),
        ({"cpu": 0.009999}, False),
        ({"blocked_cidrs": [*MANDATORY_BLOCKED_CIDRS, *[f"10.0.0.{n}/32" for n in range(61)]]}, True),
        ({"blocked_cidrs": [*MANDATORY_BLOCKED_CIDRS, *[f"10.0.0.{n}/32" for n in range(62)]]}, False),
    ],
)
def test_actual_kolla_static_assertions_enforce_profile_bounds_and_metadata_blocks(tmp_path, override, accepted):
    local_ansible = ROOT / "deploy/kolla/operator/.venv/bin/ansible-playbook"
    ansible = str(local_ansible) if local_ansible.is_file() else shutil.which("ansible-playbook")
    if ansible is None:
        pytest.skip("Kolla Ansible is required to exercise actual native prechecks")
    role = ROOT / "deploy/kolla/ansible/roles/afterglow"
    tasks = yaml.safe_load((role / "tasks/precheck_cloud_shell.yml").read_text())
    static = next(task for task in tasks if task["name"].endswith("Validate static configuration"))
    shell = {
        "service_project_id": "11111111-1111-4111-8111-111111111111",
        "network_id": "",
        "image": "registry.invalid/shell@sha256:" + "a" * 64,
        "image_pull_policy": "",
        "registry_id": "",
        "auth_url": "https://keystone.invalid/v3",
        "zun_websocket_origin": "wss://zun.invalid",
        "interface": "public",
        "home_size_gib": 5,
        "cpu": 1.0,
        "memory_mib": 1024,
        "blocked_cidrs": list(MANDATORY_BLOCKED_CIDRS),
        "idle_timeout_seconds": 1200,
        "max_session_seconds": 3600,
        "ticket_ttl_seconds": 60,
        "reconcile_interval_seconds": 60,
        **override,
    }
    play = tmp_path / "assert.yml"
    play.write_text(
        yaml.safe_dump(
            [
                {
                    "hosts": "localhost",
                    "gather_facts": False,
                    "vars": {
                        "afterglow_effective_config": {
                            "cloud_shell": shell,
                            "openstack": {
                                "service_project_id": "22222222-2222-4222-8222-222222222222",
                            },
                        },
                        "afterglow_cloud_shell_precheck_security_group": "shell-egress-only",
                    },
                    "tasks": [static],
                }
            ]
        )
    )
    environment = {key: value for key, value in os.environ.items() if not key.startswith(("ANSIBLE_", "KOLLA_"))}
    environment.update(
        ANSIBLE_LOCAL_TEMP=str(tmp_path / "ansible-local"),
        ANSIBLE_REMOTE_TEMP=str(tmp_path / "ansible-remote"),
        OBJC_DISABLE_INITIALIZE_FORK_SAFETY="YES",
    )
    result = subprocess.run(
        [ansible, "-i", "localhost,", "-c", "local", str(play)],
        env=environment,
        cwd=tmp_path,
        text=True,
        capture_output=True,
    )
    assert (result.returncode == 0) is accepted, result.stdout + result.stderr


@pytest.mark.parametrize("cpu,accepted", [(0.01, True), (0.009999, False)])
def test_settings_match_native_cpu_quota_minimum(isolated_settings, cpu, accepted):
    if accepted:
        assert _load({"cloud_shell": {"cpu": cpu}}, isolated_settings).cloud_shell_cpu == cpu
    else:
        with pytest.raises(ValidationError):
            _load({"cloud_shell": {"cpu": cpu}}, isolated_settings)


@pytest.mark.parametrize("count,accepted", [(64, True), (65, False)])
def test_rendered_settings_match_native_deny_route_ceiling(isolated_settings, count, accepted):
    blocked = sorted([*MANDATORY_BLOCKED_CIDRS, *[f"10.0.0.{n}/32" for n in range(count - 3)]])
    generated = tomllib.loads(generate_k8s._render_toml_for_k8s({"cloud_shell": {"blocked_cidrs": blocked}}))
    if accepted:
        assert _load(generated, isolated_settings).cloud_shell_blocked_cidrs == blocked
    else:
        with pytest.raises(ValidationError):
            _load(generated, isolated_settings)
