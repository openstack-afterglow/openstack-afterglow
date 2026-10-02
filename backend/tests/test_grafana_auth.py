"""Grafana 대시보드 선택 설정의 소비자 계약 테스트."""

import os
from unittest.mock import patch

import pytest

from app.config import get_settings, load_raw_toml


@pytest.fixture
def grafana_config(tmp_path, monkeypatch):
    config_path = tmp_path / "afterglow.conf"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("app.config._config_candidates", lambda: [config_path])
    load_raw_toml.cache_clear()
    get_settings.cache_clear()
    with patch.dict(
        "os.environ",
        {"AFTERGLOW_ENV": "development", "SECRET_KEY": "grafana-config-test-key-0123456789abcdef"},
        clear=True,
    ):
        try:
            yield config_path
        finally:
            load_raw_toml.cache_clear()
            get_settings.cache_clear()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("toml_uid", "env_uid", "expected_uid"),
    [
        (None, None, "afterglow-proxysql"),
        ("operator-proxysql", None, "operator-proxysql"),
        ("operator-proxysql", "environment-proxysql", "environment-proxysql"),
    ],
)
async def test_grafana_dashboard_config_precedence(client, grafana_config, toml_uid, env_uid, expected_uid):
    config = (
        '[monitoring]\ngrafana_base_url = "https://grafana.example.com"\n'
        '[monitoring.dashboards]\nmysqld_uid = "existing-mysql"\n'
    )
    if toml_uid is not None:
        config += f'proxysql_uid = "{toml_uid}"\n'
    grafana_config.write_text(config, encoding="utf-8")
    if env_uid is not None:
        os.environ["GRAFANA_DASHBOARD_PROXYSQL_UID"] = env_uid

    response = await client.get("/api/v1/grafana/dashboards")

    assert response.status_code == 200
    data = response.json()
    assert data["grafana_url"] == "https://grafana.example.com"
    assert data["dashboards"]["proxysql"] == expected_uid
    assert data["dashboards"]["mysqld"] == "existing-mysql"


@pytest.mark.asyncio
async def test_grafana_dashboards_without_url_remains_disabled(client, grafana_config):
    grafana_config.write_text('[monitoring.dashboards]\nproxysql_uid = "operator-proxysql"\n', encoding="utf-8")

    response = await client.get("/api/v1/grafana/dashboards")

    assert response.status_code == 200
    assert response.json()["grafana_url"] == ""
