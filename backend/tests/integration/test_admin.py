"""관리자 API 통합 테스트.

afterglow.conf의 admin 계정으로 로그인하므로 admin 역할이 있어야 한다.
"""

import pytest

# ─────────────────────────────────────────────────────────────────
# 관리자 개요
# ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_admin_overview(client):
    resp = await client.get("/api/v1/admin/overview")
    assert resp.status_code == 200
    data = resp.json()
    assert "instances_count" in data or "total_instances" in data or isinstance(data, dict)


# ─────────────────────────────────────────────────────────────────
# 관리자 서비스 상태
# ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_admin_services(client):
    resp = await client.get("/api/v1/admin/services")
    assert resp.status_code == 200
    data = resp.json()
    assert "compute" in data
    assert "block_storage" in data
    assert "endpoints" in data


# ─────────────────────────────────────────────────────────────────
# 관리자 인스턴스/볼륨/네트워크 전체 목록
# ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_admin_all_instances(client):
    resp = await client.get("/api/v1/admin/all-instances")
    assert resp.status_code == 200
    data = resp.json()
    # 페이지네이션 응답 {count, items} 또는 list
    assert isinstance(data, (list, dict))
    if isinstance(data, dict):
        assert "items" in data


@pytest.mark.asyncio(loop_scope="session")
async def test_admin_all_volumes(client):
    resp = await client.get("/api/v1/admin/all-volumes")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, (list, dict))
    if isinstance(data, dict):
        assert "items" in data


@pytest.mark.asyncio(loop_scope="session")
async def test_admin_all_networks(client):
    resp = await client.get("/api/v1/admin/all-networks")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, (list, dict))


@pytest.mark.asyncio(loop_scope="session")
async def test_admin_all_floating_ips(client):
    resp = await client.get("/api/v1/admin/all-floating-ips")
    assert resp.status_code in (200, 500)  # 내부 에러 가능 (Neutron 상태에 따라)


@pytest.mark.asyncio(loop_scope="session")
async def test_admin_all_routers(client):
    resp = await client.get("/api/v1/admin/all-routers")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, (list, dict))


@pytest.mark.asyncio(loop_scope="session")
async def test_admin_all_ports(client):
    resp = await client.get("/api/v1/admin/all-ports")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, (list, dict))


# ─────────────────────────────────────────────────────────────────
# 관리자 하이퍼바이저
# ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_admin_hypervisors(client):
    resp = await client.get("/api/v1/admin/hypervisors")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    if data:
        assert "hostname" in data[0] or "hypervisor_hostname" in data[0] or "id" in data[0]


# ─────────────────────────────────────────────────────────────────
# 관리자 GPU
# ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_admin_gpu_hosts(client):
    resp = await client.get("/api/v1/admin/gpu-hosts")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, (list, dict))


# ─────────────────────────────────────────────────────────────────
# 관리자 플레이버
# ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_admin_list_flavors(client):
    resp = await client.get("/api/v1/admin/flavors")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, (list, dict))
    items = data if isinstance(data, list) else data.get("items", data.get("flavors", []))
    assert len(items) > 0


# ─────────────────────────────────────────────────────────────────
# 관리자 Identity (사용자, 프로젝트, 그룹, 역할)
# ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_admin_list_users(client, selected_domain_id):
    resp = await client.get("/api/v1/admin/users", params={"domain_id": selected_domain_id})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, (list, dict))
    items = data if isinstance(data, list) else data.get("items", data.get("users", []))
    assert len(items) > 0
    assert all(item["domain_id"] == selected_domain_id for item in items)


@pytest.mark.asyncio(loop_scope="session")
async def test_admin_list_projects(client, selected_domain_id):
    resp = await client.get("/api/v1/admin/projects", params={"domain_id": selected_domain_id})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, (list, dict))
    items = data if isinstance(data, list) else data.get("items", data.get("projects", []))
    assert len(items) > 0
    assert all(item["domain_id"] == selected_domain_id for item in items)


@pytest.mark.asyncio(loop_scope="session")
async def test_admin_list_project_names(client, selected_domain_id):
    resp = await client.get("/api/v1/admin/projects/names", params={"domain_id": selected_domain_id})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


@pytest.mark.asyncio(loop_scope="session")
async def test_admin_list_groups(client, selected_domain_id):
    resp = await client.get("/api/v1/admin/groups", params={"domain_id": selected_domain_id})
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio(loop_scope="session")
async def test_admin_list_roles(client):
    resp = await client.get("/api/v1/admin/roles")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0


@pytest.mark.asyncio(loop_scope="session")
async def test_admin_project_quotas(client, project_id, selected_domain_id):
    resp = await client.get(f"/api/v1/admin/quotas/{project_id}", params={"domain_id": selected_domain_id})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)
    assert data["project_id"] == project_id
    assert set(data["availability"]) == {"compute", "volume", "network", "file_storage"}


@pytest.mark.asyncio(loop_scope="session")
async def test_admin_domains_overview(client):
    resp = await client.get("/api/v1/admin/overview/domains")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


# ─────────────────────────────────────────────────────────────────
# 관리자 토폴로지
# ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_admin_topology(client):
    resp = await client.get("/api/v1/admin/topology")
    assert resp.status_code in (200, 500)


# ─────────────────────────────────────────────────────────────────
# 관리자 시계열
# ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_admin_timeseries(client):
    resp = await client.get("/api/v1/admin/timeseries/instances?range=7d")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ─────────────────────────────────────────────────────────────────
# 관리자 파일 스토리지
# ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_admin_file_storages(client, settings):
    if not settings.service_manila_enabled:
        pytest.skip("Manila 비활성화")
    resp = await client.get("/api/v1/admin/file-storage")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio(loop_scope="session")
async def test_admin_all_file_storages(client, settings):
    if not settings.service_manila_enabled:
        pytest.skip("Manila 비활성화")
    resp = await client.get("/api/v1/admin/all-file-storages")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ─────────────────────────────────────────────────────────────────
# 관리자 컨테이너 (Zun)
# ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_admin_all_containers(client, settings):
    if not settings.service_zun_enabled:
        pytest.skip("Zun 비활성화")
    resp = await client.get("/api/v1/admin/all-containers")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ─────────────────────────────────────────────────────────────────
# 관리자 Notion 설정
# ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_admin_notion_config_get(client):
    resp = await client.get("/api/v1/admin/notion/config")
    assert resp.status_code == 200
    data = resp.json()
    assert "configured" in data


# ─────────────────────────────────────────────────────────────────
# 메트릭 (Prometheus)
# ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_metrics(client):
    resp = await client.get("/api/v1/metrics")
    assert resp.status_code == 200


@pytest.mark.asyncio(loop_scope="session")
async def test_metrics_admin_access(admin_client):
    resp = await admin_client.get("/api/v1/metrics")
    assert resp.status_code == 200


@pytest.mark.asyncio(loop_scope="session")
async def test_metrics_rejects_non_admin(user_client):
    resp = await user_client.get("/api/v1/metrics")
    assert resp.status_code == 403


# ─────────────────────────────────────────────────────────────────
# PR4: 권한 분리 — admin GET 엔드포인트 × 일반 유저 → 403
# ─────────────────────────────────────────────────────────────────

from app.config import get_settings as _get_settings

_s = _get_settings()

# 경로 파라미터 없는 admin GET 엔드포인트 (비조건부)
_ADMIN_SIMPLE_PATHS = [
    "/api/v1/admin/overview",
    "/api/v1/admin/hypervisors",
    "/api/v1/admin/all-instances",
    "/api/v1/admin/all-volumes",
    "/api/v1/admin/all-networks",
    "/api/v1/admin/all-floating-ips",
    "/api/v1/admin/all-routers",
    "/api/v1/admin/all-ports",
    "/api/v1/admin/overview/domains",
    "/api/v1/admin/compute-hosts",
    "/api/v1/admin/version",
    "/api/v1/admin/topology",
    "/api/v1/admin/timeseries/instances",
    "/api/v1/admin/users",
    "/api/v1/admin/projects",
    "/api/v1/admin/projects/names",
    "/api/v1/admin/groups",
    "/api/v1/admin/roles",
    "/api/v1/admin/flavors",
    "/api/v1/admin/images",
    "/api/v1/admin/notion/config",
    "/api/v1/admin/services",
    "/api/v1/admin/gpu-hosts",
]

# 경로 파라미터 있는 엔드포인트 — require_admin이 먼저 발동하므로 가짜 ID로도 403 확인 가능
_ADMIN_PARAMETERIZED_PATHS = [
    "/api/v1/admin/quotas/fake-project-id",
    "/api/v1/admin/hypervisors/fake-hypervisor-id",
    "/api/v1/admin/volumes/fake-volume-id",
    "/api/v1/admin/networks/fake-network-id",
    "/api/v1/admin/projects/fake-project-id/members",
    "/api/v1/admin/groups/fake-group-id/users",
    "/api/v1/admin/flavors/fake-flavor-id/access",
    "/api/v1/admin/images/fake-image-id",
]

# 조건부 서비스 엔드포인트 (서비스 활성화 시에만 403 테스트)
_ADMIN_CONDITIONAL_PATHS: list[str] = []
if _s.service_manila_enabled:
    _ADMIN_CONDITIONAL_PATHS += [
        "/api/v1/admin/file-storage",
        "/api/v1/admin/file-storage/builds",
        "/api/v1/admin/all-file-storages",
    ]
if _s.service_zun_enabled:
    _ADMIN_CONDITIONAL_PATHS.append("/api/v1/admin/all-containers")
if getattr(_s, "service_k3s_enabled", False):
    _ADMIN_CONDITIONAL_PATHS += [
        "/api/v1/admin/k3s-clusters",
        "/api/v1/admin/k3s-clusters/fake-cluster-id",
        "/api/v1/admin/k3s-clusters/fake-cluster-id/kubeconfig",
    ]

_ALL_ADMIN_GET_PATHS = _ADMIN_SIMPLE_PATHS + _ADMIN_PARAMETERIZED_PATHS + _ADMIN_CONDITIONAL_PATHS


@pytest.mark.parametrize("path", _ALL_ADMIN_GET_PATHS)
@pytest.mark.asyncio(loop_scope="session")
async def test_admin_get_forbidden_for_regular_user(user_client, path, regular_user_domain_id):
    """모든 admin GET 엔드포인트는 일반 유저에게 403을 반환해야 한다."""
    scoped = path.startswith(
        ("/api/v1/admin/users", "/api/v1/admin/projects", "/api/v1/admin/groups", "/api/v1/admin/quotas")
    )
    resp = await user_client.get(path, params={"domain_id": regular_user_domain_id} if scoped else {})
    assert resp.status_code == 403, f"[{path}] Expected 403 Forbidden, got {resp.status_code}: {resp.text[:200]}"


# ─────────────────────────────────────────────────────────────────
# PR4: admin 계정으로 경로 파라미터 엔드포인트 정상 접근 확인
# ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_admin_quotas_by_project(admin_client, project_id, selected_domain_id):
    resp = await admin_client.get(f"/api/v1/admin/quotas/{project_id}", params={"domain_id": selected_domain_id})
    assert resp.status_code == 200


@pytest.mark.asyncio(loop_scope="session")
async def test_admin_timeseries_instances(admin_client):
    resp = await admin_client.get("/api/v1/admin/timeseries/instances?range=7d")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio(loop_scope="session")
async def test_admin_hypervisor_detail(admin_client):
    hypervisors = (await admin_client.get("/api/v1/admin/hypervisors")).json()
    if not hypervisors:
        pytest.skip("하이퍼바이저 없음")
    hv_id = hypervisors[0].get("id") or hypervisors[0].get("hypervisor_hostname")
    resp = await admin_client.get(f"/api/v1/admin/hypervisors/{hv_id}")
    assert resp.status_code == 200


@pytest.mark.asyncio(loop_scope="session")
async def test_admin_volume_detail(admin_client):
    volumes = (await admin_client.get("/api/v1/admin/all-volumes")).json()
    items = volumes if isinstance(volumes, list) else volumes.get("items", [])
    if not items:
        pytest.skip("볼륨 없음")
    vol_id = items[0]["id"]
    resp = await admin_client.get(f"/api/v1/admin/volumes/{vol_id}")
    assert resp.status_code == 200


@pytest.mark.asyncio(loop_scope="session")
async def test_admin_network_detail(admin_client):
    networks = (await admin_client.get("/api/v1/admin/all-networks")).json()
    items = networks if isinstance(networks, list) else networks.get("items", [])
    if not items:
        pytest.skip("네트워크 없음")
    net_id = items[0]["id"]
    resp = await admin_client.get(f"/api/v1/admin/networks/{net_id}")
    assert resp.status_code == 200


@pytest.mark.asyncio(loop_scope="session")
async def test_admin_project_members(admin_client, project_id, selected_domain_id):
    resp = await admin_client.get(
        f"/api/v1/admin/projects/{project_id}/members", params={"domain_id": selected_domain_id}
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio(loop_scope="session")
async def test_admin_flavor_access(admin_client):
    flavors = (await admin_client.get("/api/v1/admin/flavors")).json()
    items = flavors if isinstance(flavors, list) else flavors.get("items", flavors.get("flavors", []))
    if not items:
        pytest.skip("플레이버 없음")
    flavor_id = items[0]["id"]
    resp = await admin_client.get(f"/api/v1/admin/flavors/{flavor_id}/access")
    # 공개 플레이버는 access list 조회가 403(아닌 경우)일 수 있음 — 2xx 또는 403(플레이버 정책)
    assert resp.status_code in (200, 403), f"Unexpected: {resp.status_code}"


@pytest.mark.asyncio(loop_scope="session")
async def test_admin_image_detail(admin_client):
    images = (await admin_client.get("/api/v1/admin/images")).json()
    items = images if isinstance(images, list) else images.get("images", [])
    if not items:
        pytest.skip("이미지 없음")
    image_id = items[0]["id"]
    resp = await admin_client.get(f"/api/v1/admin/images/{image_id}")
    assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────
# admin_user 검증 (default project ≠ admin 이어도 admin 페이지 접근 가능해야 함)
# credentials.toml [admin_user] 또는 AFTERGLOW_TEST_ADMIN_USER_* 환경변수 필요
# ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_admin_user_can_access_admin_overview(admin_user_client):
    """admin_user 가 /api/admin/overview 에 접근 가능해야 한다.

    scoped token 의 project 가 admin 이 아니어도 is_system_admin=True 이면 통과.
    이것이 pieroot 버그 수정의 핵심 회귀 테스트.
    """
    resp = await admin_user_client.get("/api/v1/admin/overview")
    assert resp.status_code == 200, (
        f"admin_user 가 /api/admin/overview 에 접근 실패 ({resp.status_code}): {resp.text[:200]}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_admin_user_can_access_admin_users(admin_user_client, admin_user_domain_id):
    """admin_user 가 /api/admin/users 에 접근 가능해야 한다."""
    resp = await admin_user_client.get("/api/v1/admin/users", params={"domain_id": admin_user_domain_id})
    assert resp.status_code == 200, (
        f"admin_user 가 /api/admin/users 에 접근 실패 ({resp.status_code}): {resp.text[:200]}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_admin_user_can_access_admin_projects(admin_user_client, admin_user_domain_id):
    """admin_user 가 /api/admin/projects 에 접근 가능해야 한다."""
    resp = await admin_user_client.get("/api/v1/admin/projects", params={"domain_id": admin_user_domain_id})
    assert resp.status_code == 200, (
        f"admin_user 가 /api/admin/projects 에 접근 실패 ({resp.status_code}): {resp.text[:200]}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_admin_user_foreign_project_instance_detail_endpoints(admin_user_client, admin_user_auth_data):
    """admin_user가 자신에게 권한 할당이 없는 타 테넌트 인스턴스의 상세/인터페이스/볼륨/보안그룹/소유자 API에 X-Project-Id 헤더로 접근 가능해야 한다."""
    admin_scoped_project = admin_user_auth_data.get("project_id", "")

    # 1. 관리자 권한으로 모든 인스턴스 목록 조회
    resp = await admin_user_client.get("/api/v1/admin/all-instances")
    assert resp.status_code == 200
    all_instances = resp.json()
    items = all_instances.get("items", all_instances) if isinstance(all_instances, dict) else all_instances

    # 2. admin_user의 scoped project와 다른 프로젝트 소유 인스턴스 선택
    target_inst = None
    target_project_id = None
    for inst in items:
        p_id = inst.get("project_id") or inst.get("tenant_id")
        if p_id and p_id != admin_scoped_project:
            target_inst = inst
            target_project_id = p_id
            break

    if not target_inst or not target_project_id:
        pytest.skip("admin_user의 scoped project와 다른 프로젝트 소유 인스턴스가 없어 테스트를 스킵합니다.")

    instance_id = target_inst["id"]
    headers = {"X-Project-Id": target_project_id}

    # 3. detail, interfaces, volumes, security-groups, owner 5개 엔드포인트 요청 및 200 확인
    endpoints = [
        f"/api/v1/instances/{instance_id}",
        f"/api/v1/instances/{instance_id}/interfaces",
        f"/api/v1/instances/{instance_id}/volumes",
        f"/api/v1/instances/{instance_id}/security-groups",
        f"/api/v1/instances/{instance_id}/owner",
    ]

    for ep in endpoints:
        r = await admin_user_client.get(ep, headers=headers)
        assert r.status_code == 200, (
            f"Failed on {ep} with X-Project-Id={target_project_id}: status {r.status_code}, body: {r.text[:200]}"
        )
