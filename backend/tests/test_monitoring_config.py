"""Operator config reaches native consumers without publishing observer/analytics secrets."""

import json
import sys
import tomllib
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from fastapi import HTTPException

from app import config as app_config
from app.config import Settings
from app.models.traffic_analytics import TrafficAnalyticsSettings
from app.services.infrastructure_topology import authenticate_observer

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config2helm  # noqa: E402
import generate_k8s  # noqa: E402

OBSERVER_TOKEN = "observer-secret-" + "a" * 32
HMAC_KEY = "visitor-hmac-" + "b" * 32
INGEST_KEY = "writer-secret-" + "c" * 32


def configuration():
    return {
        "app": {"secret_key": "testing-secret-key-" + "d" * 48},
        "monitoring": {
            "infrastructure_topology_enabled": True,
            "infrastructure_topology_observers": [{"host_id": "compute:n1", "token": OBSERVER_TOKEN}],
            "infrastructure_topology_trace_targets": ["1.1.1.1"],
            "infrastructure_topology_peer_targets": [
                {
                    "source_host_id": "compute:n1",
                    "target_host_id": "controller:n2",
                    "address": "10.20.0.12",
                    "port": 9100,
                }
            ],
        },
        "traffic_analytics": {
            "enabled": True,
            "retention_days": 7,
            "hmac_key": HMAC_KEY,
            "frontend_ingest_key": INGEST_KEY,
            "geoip_mmdb": "/etc/afterglow/geoip/country.mmdb",
            "site_country": "KR",
        },
    }


def test_generated_configmap_is_public_but_secret_environment_authenticates_exact_host(monkeypatch):
    cfg = configuration()
    public = yaml.safe_load(generate_k8s.render_configmap(cfg))["data"]
    secrets = yaml.safe_load(generate_k8s.render_secret(cfg))["stringData"]
    public_values = yaml.safe_load(config2helm.render_yaml(config2helm.convert(cfg, include_secrets=False)))
    assert public_values["trafficAnalytics"]["siteCountry"] == "KR"
    for secret in (OBSERVER_TOKEN, HMAC_KEY, INGEST_KEY):
        assert secret not in json.dumps(public)
        assert secret not in config2helm.render_yaml(config2helm.convert(cfg, include_secrets=False))
    parsed = tomllib.loads(public["afterglow.conf"])
    assert parsed["traffic_analytics"]["site_country"] == "KR"
    monkeypatch.setattr(app_config, "load_raw_toml", lambda: parsed)
    seeded = {
        key.upper(): json.dumps(value) if isinstance(value, (dict, list)) else str(value)
        for key, value in app_config._load_toml().items()
    }
    with patch.dict("os.environ", {**seeded, **secrets, "AFTERGLOW_ALLOW_INSECURE": "1"}, clear=True):
        settings = Settings(_env_file=None)
    assert authenticate_observer("compute:n1", "Bearer " + OBSERVER_TOKEN, settings=settings) is settings
    with pytest.raises(HTTPException) as rejected:
        authenticate_observer("controller:n2", "Bearer " + OBSERVER_TOKEN, settings=settings)
    assert rejected.value.status_code in {401, 403}
    assert settings.traffic_analytics.hmac_key.get_secret_value() == HMAC_KEY
    assert settings.traffic_analytics.frontend_ingest_key.get_secret_value() == INGEST_KEY
    assert settings.traffic_analytics.site_country == "KR"
    assert secrets["TRAFFIC_ANALYTICS_INGEST_KEY"] == INGEST_KEY
    peer = settings.monitoring_infrastructure_topology_peer_targets[0]
    assert (peer.source_host_id, peer.target_host_id, peer.address, peer.port) == (
        "compute:n1",
        "controller:n2",
        "10.20.0.12",
        9100,
    )


def test_nested_secret_environment_overrides_protected_toml_without_disabling_collection():
    replacement = "rotated-writer-" + "z" * 32
    with patch.dict(
        "os.environ",
        {
            "TRAFFIC_ANALYTICS": json.dumps(configuration()["traffic_analytics"]),
            "TRAFFIC_ANALYTICS__FRONTEND_INGEST_KEY": replacement,
            "AFTERGLOW_ALLOW_INSECURE": "1",
        },
        clear=True,
    ):
        settings = Settings(_env_file=None)
    assert settings.traffic_analytics.enabled is True
    assert settings.traffic_analytics.retention_days == 7
    assert settings.traffic_analytics.frontend_ingest_key.get_secret_value() == replacement
    assert settings.traffic_analytics.hmac_key.get_secret_value() == HMAC_KEY


def test_helm_list_serialization_preserves_structured_observer_and_probe_authority():
    converted = config2helm.convert(configuration(), include_secrets=True)
    values = yaml.safe_load(config2helm.render_yaml(converted))
    observers = values["secrets"]["infrastructureTopologyObservers"]
    assert values["trafficAnalytics"]["siteCountry"] == "KR"
    peers = values["monitoring"]["infrastructureTopologyPeerTargets"]
    with patch.dict("os.environ", {"AFTERGLOW_ALLOW_INSECURE": "1"}, clear=True):
        settings = Settings(
            _env_file=None,
            monitoring_infrastructure_topology_enabled=True,
            monitoring_infrastructure_topology_observers=observers,
            monitoring_infrastructure_topology_peer_targets=peers,
        )
    assert authenticate_observer("compute:n1", "Bearer " + OBSERVER_TOKEN, settings=settings) is settings
    assert settings.monitoring_infrastructure_topology_peer_targets[0].target_host_id == "controller:n2"


def test_invalid_nested_observer_token_never_appears_in_startup_validation():
    from pydantic import ValidationError

    invalid = "invalid-sensitive-observer-token-with-unsafe-space " + "x" * 32
    with pytest.raises(ValidationError) as failure:
        Settings(
            _env_file=None,
            monitoring_infrastructure_topology_observers=[
                {"host_id": "compute:n1", "token": invalid},
            ],
        )
    assert invalid not in str(failure.value)
    assert "monitoring_infrastructure_topology_observers" in str(failure.value)


@pytest.mark.parametrize("country", ["kr", "Kr", "KOR", "K", "XX", " KR", "KR ", "KR\n", "한국", None, 42])
def test_invalid_traffic_site_country_is_rejected_by_settings(country):
    from pydantic import ValidationError

    with pytest.raises(ValidationError) as failure:
        Settings(_env_file=None, traffic_analytics={"site_country": country})
    assert any(error["loc"] == ("traffic_analytics", "site_country") for error in failure.value.errors())


@pytest.mark.parametrize("country", ["", "KR", "US"])
def test_traffic_site_country_accepts_unconfigured_or_uppercase_country(country):
    assert TrafficAnalyticsSettings(site_country=country).site_country == country


def test_unconfigured_site_country_remains_empty_in_generated_configuration():
    cfg = configuration()
    del cfg["traffic_analytics"]["site_country"]
    public = yaml.safe_load(generate_k8s.render_configmap(cfg))["data"]
    assert tomllib.loads(public["afterglow.conf"])["traffic_analytics"]["site_country"] == ""
    assert TrafficAnalyticsSettings().site_country == ""
