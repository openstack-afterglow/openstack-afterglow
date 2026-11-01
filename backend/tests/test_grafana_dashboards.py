"""GET /api/v1/grafana/dashboards 접근 계약과 Grafana 패널 테스트."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.config import Settings

DASHBOARD_DIR = Path(__file__).parents[2] / "monitoring" / "grafana" / "provisioning" / "dashboards"


@pytest.mark.asyncio
async def test_get_dashboards_denies_authenticated_member(non_admin_client):
    """A project member cannot discover an unscoped infrastructure origin/catalog."""
    fake_settings = Settings(_env_file=None, grafana_base_url="https://grafana.example.com", secret_key="a" * 64)

    with patch("app.api.common.grafana_auth.get_settings", return_value=fake_settings):
        resp = await non_admin_client.get("/api/v1/grafana/dashboards")

    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "system_admin_required"
    assert "grafana_url" not in resp.json()


@pytest.mark.asyncio
async def test_get_dashboards_retains_verified_administrator_catalog(admin_client):
    fake_settings = Settings(_env_file=None, grafana_base_url="https://grafana.example.com", secret_key="a" * 64)
    with patch("app.api.common.grafana_auth.get_settings", return_value=fake_settings):
        response = await admin_client.get("/api/v1/grafana/dashboards")
    assert response.status_code == 200
    assert response.json()["grafana_url"] == "https://grafana.example.com"
    assert response.json()["dashboards"]["node"] == "afterglow-node"
    assert response.json()["dashboards"]["instance-cpu"] == fake_settings.grafana_dashboard_instance_cpu_uid


@pytest.mark.asyncio
async def test_grafana_catalog_rechecks_native_admin_grant(admin_client):
    """A remembered admin flag cannot bypass the existing fresh native guard."""
    from app.api.deps import require_admin
    from app.main import app

    app.dependency_overrides.pop(require_admin)
    with (
        patch("app.services.domain_scope.domain_context", return_value={}),
        patch("app.services.domain_scope.assert_token_context"),
        patch("app.services.keystone.validate_token", return_value={"roles": ["member"]}),
        patch("app.services.keystone._is_system_admin", return_value=False) as live_grant,
    ):
        response = await admin_client.get("/api/v1/grafana/dashboards")
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "system_admin_required"
    live_grant.assert_called_once()


def test_ceph_dashboard_pool_storage_panel():
    """ceph.json 풀별 저장 용량 패널(id=13)이 올바른 format/transformation을 사용한다."""
    ceph_json = DASHBOARD_DIR / "ceph.json"
    dashboard = json.loads(ceph_json.read_text())

    panel = next(p for p in dashboard["panels"] if p.get("id") == 13)
    target = panel["targets"][0]

    assert target.get("format") == "table", "instant table 쿼리에 format: table 필요"
    assert target.get("instant") is True
    assert "ceph_pool_stored" in target["expr"]
    assert "ceph_pool_metadata" in target["expr"]

    transform_ids = [t["id"] for t in panel.get("transformations", [])]
    assert "reduce" not in transform_ids, "reduce transformation은 table format에서 컬럼명 불일치를 유발함"
    assert "organize" in transform_ids

    organize = next(t for t in panel["transformations"] if t["id"] == "organize")
    rename = organize["options"]["renameByName"]
    assert rename.get("name") == "Pool 이름"
    assert rename.get("Value") == "저장 용량"


def _flatten_panels(dashboard: dict) -> list:
    """row 내부 panels 배열까지 포함해 모든 패널을 평탄화."""
    result = []
    for p in dashboard.get("panels", []):
        if p.get("type") == "row":
            result.extend(p.get("panels", []))
        else:
            result.append(p)
    return result


def test_openstack_dashboard_service_status_panels():
    """openstack.json에 서비스 up/down stat 7개 + 에이전트 활성 비율 stat 3개가 존재한다."""
    dashboard = json.loads((DASHBOARD_DIR / "openstack.json").read_text())
    panels = _flatten_panels(dashboard)

    up_exprs = [
        p["targets"][0]["expr"]
        for p in panels
        if p.get("type") == "stat" and p.get("targets") and "_up" in p["targets"][0].get("expr", "")
    ]
    for svc in ["nova", "neutron", "cinder", "glance", "identity", "placement", "loadbalancer"]:
        assert any(f"openstack_{svc}_up" in e for e in up_exprs), f"{svc}_up 패널 없음"

    ratio_exprs = [p["targets"][0]["expr"] for p in panels if p.get("type") == "stat" and p.get("targets")]
    for svc in ["nova", "neutron", "cinder"]:
        assert any(f"sum(openstack_{svc}_agent_state)" in e and "count(" in e for e in ratio_exprs), (
            f"{svc} 에이전트 활성 비율 패널 없음"
        )
