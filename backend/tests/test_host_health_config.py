"""Host health target configuration: validation, flat TOML, generator and example parity."""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

import pytest
from pydantic import ValidationError

from app import config as app_config
from app.config import Settings

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import generate_k8s  # noqa: E402

TARGETS = [
    {"name": "ctl-1", "address": "ctl-1.mgmt.example", "role": "controller", "port": 9101},
    {"name": "ceph-1", "address": "10.20.0.31", "role": "storage", "port": 9100},
]


@pytest.mark.parametrize(
    "address",
    [
        "http://10.0.0.1",
        "10.0.0.1:9100",
        "user@host.example",
        "host.example/metrics",
        "host.example?x=1",
        "localhost",
        "metadata.google.internal",
        "127.0.0.1",
        "169.254.169.254",
        "fd00:ec2::254",
        "0.0.0.0",
        "224.0.0.1",
        "::ffff:127.0.0.1",
        "fe80::1%eth0",
        "1234",
        " host.example",
    ],
)
def test_unsafe_or_url_shaped_target_addresses_are_rejected(address):
    with pytest.raises(ValidationError):
        Settings(monitoring_host_healthcheck_targets=[{"name": "n1", "address": address, "role": "controller"}])


def test_targets_require_known_roles_unique_identities_and_integer_ports():
    for target in (
        {"name": "n1", "address": "10.0.0.1", "role": "network"},
        {"name": "n1", "address": "10.0.0.1", "role": "compute", "port": "9100"},
        {"name": "n1", "address": "10.0.0.1", "role": "compute", "port": 0},
        {"name": "n1", "address": "10.0.0.1", "role": "compute", "path": "/metrics"},
    ):
        with pytest.raises(ValidationError):
            Settings(monitoring_host_healthcheck_targets=[target])
    with pytest.raises(ValidationError):
        Settings(
            monitoring_host_healthcheck_targets=[
                {"name": "CTL-1", "address": "10.0.0.1", "role": "controller"},
                {"name": "ctl-1", "address": "10.0.0.2", "role": "controller"},
            ]
        )
    # The same host name may be an independent row for another role.
    Settings(
        monitoring_host_healthcheck_targets=[
            {"name": "node-1", "address": "10.0.0.1", "role": "controller"},
            {"name": "node-1", "address": "10.0.0.1", "role": "storage"},
        ]
    )


def test_flat_toml_targets_survive_the_environment_seeding_path(monkeypatch):
    monkeypatch.setattr(
        app_config,
        "load_raw_toml",
        lambda: {"monitoring": {"host_healthcheck_enabled": False, "host_healthcheck_targets": TARGETS}},
    )
    flat = app_config._load_toml()
    assert flat["monitoring_host_healthcheck_enabled"] is False
    assert flat["monitoring_host_healthcheck_targets"] == TARGETS

    # get_settings() seeds missing environment keys with JSON for structured values.
    monkeypatch.setenv("MONITORING_HOST_HEALTHCHECK_TARGETS", json.dumps(flat["monitoring_host_healthcheck_targets"]))
    monkeypatch.setenv("MONITORING_HOST_HEALTHCHECK_ENABLED", str(flat["monitoring_host_healthcheck_enabled"]))
    settings = Settings()
    assert settings.monitoring_host_healthcheck_enabled is False
    assert [target.model_dump() for target in settings.monitoring_host_healthcheck_targets] == TARGETS


def test_generated_kubernetes_config_preserves_targets_inside_monitoring():
    rendered = tomllib.loads(
        generate_k8s._render_toml_for_k8s(
            {"monitoring": {"host_healthcheck_enabled": False, "host_healthcheck_targets": TARGETS}}
        )
    )
    monitoring = rendered["monitoring"]
    assert monitoring["host_healthcheck_enabled"] is False
    assert monitoring["host_healthcheck_targets"] == TARGETS
    assert "node_uid" in monitoring["dashboards"]

    defaults = tomllib.loads(generate_k8s._render_toml_for_k8s({}))["monitoring"]
    assert defaults["host_healthcheck_enabled"] is True
    assert defaults["host_healthcheck_targets"] == []
