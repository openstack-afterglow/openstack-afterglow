"""대시보드, 메트릭, 라이브러리, 사이트 설정, 유저 대시보드 통합 테스트."""

import pytest

# ─────────────────────────────────────────────────────────────────
# 대시보드
# ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_dashboard_summary(client):
    resp = await client.get("/api/v1/dashboard/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert "instances" in data
    assert "gpu_used" in data


@pytest.mark.asyncio(loop_scope="session")
async def test_dashboard_config(client):
    resp = await client.get("/api/v1/dashboard/config")
    assert resp.status_code == 200
    data = resp.json()
    assert "refresh_interval_ms" in data


@pytest.mark.asyncio(loop_scope="session")
async def test_dashboard_quotas(client):
    resp = await client.get("/api/v1/dashboard/quotas")
    assert resp.status_code == 200
    data = resp.json()
    assert "compute" in data
    assert "storage" in data
    assert "network" in data


@pytest.mark.asyncio(loop_scope="session")
async def test_dashboard_usage(client):
    resp = await client.get("/api/v1/dashboard/usage")
    assert resp.status_code == 200
    data = resp.json()
    assert "start" in data
    assert "end" in data


# ─────────────────────────────────────────────────────────────────
# 사이트 설정 (인증 불필요)
# ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_site_config(anon_client):
    resp = await anon_client.get("/api/v1/site-config")
    assert resp.status_code == 200
    data = resp.json()
    assert "site_name" in data
    assert "services" in data


# ─────────────────────────────────────────────────────────────────
# 헬스체크 (인증 불필요)
# ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_health(anon_client):
    resp = await anon_client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio(loop_scope="session")
async def test_list_libraries(client):
    resp = await client.get("/api/v1/libraries")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert "id" in data[0]
    assert "name" in data[0]


# ─────────────────────────────────────────────────────────────────
# 유저 대시보드
# ─────────────────────────────────────────────────────────────────


def _assert_user_inventory(data):
    categories = {
        "instances",
        "volumes",
        "floating_ips",
        "networks",
        "subnets",
        "routers",
        "security_groups",
        "load_balancers",
        "images",
        "keypairs",
        "database_instances",
        "database_backups",
        "k3s_clusters",
        "waygate_gateways",
        "containers",
        "magnum_clusters",
        "shares",
        "share_snapshots",
        "share_networks",
        "security_services",
        "buckets",
        "volume_snapshots",
        "volume_backups",
        "packages",
        "secrets",
    }
    assert set(data) == {"user_id", "current_project_id", "projects", "totals"}
    assert isinstance(data["user_id"], str) and data["user_id"]
    assert set(data["totals"]) == {"resources", "usage"}
    assert set(data["totals"]["resources"]) == categories
    for project in data["projects"]:
        assert set(project) == {"project_id", "project_name", "resources", "usage"}
        assert set(project["resources"]) == categories
        assert set(project["usage"]) == {"vcpus", "ram_mb", "storage_gb"}
        for value in project["resources"].values():
            assert value["state"] in {"ready", "disabled", "denied", "failed"}
            if value["state"] == "ready":
                assert value["count"] == len(value["items"])
            else:
                assert value["count"] is None and value["items"] == []
            for item in value["items"]:
                assert {
                    "id",
                    "name",
                    "status",
                    "project_id",
                    "project_name",
                    "owner_scope",
                    "owner_id",
                    "href",
                } <= item.keys()
                assert item["project_id"] == project["project_id"]
                assert item["owner_scope"] in {"user", "project"}
                assert item["owner_id"] == (data["user_id"] if item["owner_scope"] == "user" else project["project_id"])
                assert not {"payload", "password", "private_key", "secret", "token"}.intersection(item)
    for value in data["totals"]["resources"].values():
        assert set(value) == {"state", "count", "known_count"}
        assert value["state"] in {"ready", "disabled", "denied", "failed", "partial"}
        assert isinstance(value["known_count"], int) and value["known_count"] >= 0
        assert (value["count"] is not None) == (value["state"] == "ready")
    assert set(data["totals"]["usage"]) == {"vcpus", "ram_mb", "storage_gb"}


@pytest.mark.asyncio(loop_scope="session")
async def test_user_dashboard_summary(client):
    resp = await client.get("/api/v1/user-dashboard/summary")
    assert resp.status_code == 200
    data = resp.json()
    _assert_user_inventory(data)


# ─────────────────────────────────────────────────────────────────
# 프로필
# ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_get_profile(client):
    resp = await client.get("/api/v1/profile")
    assert resp.status_code == 200
    data = resp.json()
    assert "user_id" in data or "id" in data


# ─────────────────────────────────────────────────────────────────
# PR4: 일반 유저도 대시보드/프로필 조회 가능 확인
# ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_dashboard_summary_as_user(user_client):
    resp = await user_client.get("/api/v1/dashboard/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert "instances" in data


@pytest.mark.asyncio(loop_scope="session")
async def test_dashboard_quotas_as_user(user_client):
    resp = await user_client.get("/api/v1/dashboard/quotas")
    assert resp.status_code == 200
    data = resp.json()
    assert "compute" in data


@pytest.mark.asyncio(loop_scope="session")
async def test_user_dashboard_summary_as_user(user_client):
    resp = await user_client.get("/api/v1/user-dashboard/summary")
    assert resp.status_code == 200
    _assert_user_inventory(resp.json())


@pytest.mark.asyncio(loop_scope="session")
async def test_get_profile_as_user(user_client):
    resp = await user_client.get("/api/v1/profile")
    assert resp.status_code == 200
    data = resp.json()
    assert "user_id" in data or "id" in data


@pytest.mark.asyncio(loop_scope="session")
async def test_dashboard_config_public(anon_client):
    """dashboard/config는 인증 없이도 접근 가능해야 한다."""
    resp = await anon_client.get("/api/v1/dashboard/config")
    assert resp.status_code == 200
    assert "refresh_interval_ms" in resp.json()
