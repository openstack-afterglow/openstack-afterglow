"""관리자 쓰기 엔드포인트 403 권한 분리 통합 테스트.

require_admin Depends가 body 파싱/리소스 조회보다 먼저 실행되므로
실제 caller domain ID + 가짜 리소스 ID로 변경 없이 403 검증 가능.
"""

import pytest

# ---------------------------------------------------------------------------
# 관리자 쓰기 엔드포인트 목록 (method, path, body, label)
# ---------------------------------------------------------------------------

ADMIN_WRITE_ENDPOINTS = [
    # ── admin.py ──────────────────────────────────────────────────────────
    ("POST", "/api/v1/admin/file-storage/build", {}, "admin-file-storage-build"),
    ("POST", "/api/v1/admin/ports", {}, "admin-ports-create"),
    ("PATCH", "/api/v1/admin/volumes/fake-volume-id", {}, "admin-volume-patch"),
    ("DELETE", "/api/v1/admin/volumes/fake-volume-id", None, "admin-volume-delete"),
    ("POST", "/api/v1/admin/volumes/fake-volume-id/extend", {}, "admin-volume-extend"),
    ("POST", "/api/v1/admin/volumes/fake-volume-id/reset-status", {}, "admin-volume-reset-status"),
    ("POST", "/api/v1/admin/volumes/fake-volume-id/transfer", {}, "admin-volume-transfer"),
    ("POST", "/api/v1/admin/instances/fake-server-id/live-migrate", {}, "admin-live-migrate"),
    ("POST", "/api/v1/admin/instances/fake-server-id/cold-migrate", {}, "admin-cold-migrate"),
    ("POST", "/api/v1/admin/instances/fake-server-id/confirm-resize", {}, "admin-confirm-resize"),
    ("POST", "/api/v1/admin/networks", {}, "admin-network-create"),
    ("PUT", "/api/v1/admin/networks/fake-net-id", {}, "admin-network-update"),
    ("DELETE", "/api/v1/admin/networks/fake-net-id", None, "admin-network-delete"),
    ("POST", "/api/v1/admin/floating-ips", {}, "admin-fip-create"),
    ("DELETE", "/api/v1/admin/floating-ips/fake-fip-id", None, "admin-fip-delete"),
    ("POST", "/api/v1/admin/routers", {}, "admin-router-create"),
    ("PUT", "/api/v1/admin/routers/fake-router-id", {}, "admin-router-update"),
    ("DELETE", "/api/v1/admin/routers/fake-router-id", None, "admin-router-delete"),
    ("PUT", "/api/v1/admin/ports/fake-port-id", {}, "admin-port-update"),
    ("DELETE", "/api/v1/admin/ports/fake-port-id", None, "admin-port-delete"),
    ("DELETE", "/api/v1/admin/k3s-clusters/fake-cluster-id", None, "admin-k3s-cluster-delete"),
    # ── admin_identity.py ─────────────────────────────────────────────────
    ("POST", "/api/v1/admin/users", {}, "admin-user-create"),
    ("PATCH", "/api/v1/admin/users/fake-user-id", {}, "admin-user-update"),
    ("POST", "/api/v1/admin/projects", {}, "admin-project-create"),
    ("PATCH", "/api/v1/admin/projects/fake-proj-id", {}, "admin-project-update"),
    ("DELETE", "/api/v1/admin/projects/fake-proj-id", None, "admin-project-delete"),
    ("PUT", "/api/v1/admin/quotas/fake-proj-id", {}, "admin-quota-update"),
    ("POST", "/api/v1/admin/groups", {}, "admin-group-create"),
    ("PATCH", "/api/v1/admin/groups/fake-grp-id", {}, "admin-group-update"),
    ("DELETE", "/api/v1/admin/groups/fake-grp-id", None, "admin-group-delete"),
    ("PUT", "/api/v1/admin/groups/fake-grp-id/users/fake-user-id", {}, "admin-group-add-user"),
    ("DELETE", "/api/v1/admin/groups/fake-grp-id/users/fake-user-id", None, "admin-group-remove-user"),
    ("POST", "/api/v1/admin/roles/assign", {}, "admin-role-assign"),
    ("DELETE", "/api/v1/admin/roles/assign", None, "admin-role-unassign"),
    ("POST", "/api/v1/admin/roles/assign-group", {}, "admin-role-assign-group"),
    ("DELETE", "/api/v1/admin/roles/assign-group", None, "admin-role-unassign-group"),
    # ── admin_flavors.py ──────────────────────────────────────────────────
    ("POST", "/api/v1/admin/flavors", {}, "admin-flavor-create"),
    ("DELETE", "/api/v1/admin/flavors/fake-flavor-id", None, "admin-flavor-delete"),
    ("POST", "/api/v1/admin/flavors/fake-flavor-id/extra-specs", {}, "admin-extra-specs-create"),
    ("DELETE", "/api/v1/admin/flavors/fake-flavor-id/extra-specs/fake-key", None, "admin-extra-specs-delete"),
    ("POST", "/api/v1/admin/flavors/fake-flavor-id/access", {}, "admin-flavor-access-add"),
    ("DELETE", "/api/v1/admin/flavors/fake-flavor-id/access/fake-proj", None, "admin-flavor-access-remove"),
    # ── admin_images.py ───────────────────────────────────────────────────
    ("PATCH", "/api/v1/admin/images/fake-img-id", {}, "admin-image-update"),
    ("DELETE", "/api/v1/admin/images/fake-img-id", None, "admin-image-delete"),
    ("POST", "/api/v1/admin/images/fake-img-id/deactivate", {}, "admin-image-deactivate"),
    ("POST", "/api/v1/admin/images/fake-img-id/reactivate", {}, "admin-image-reactivate"),
    # ── admin_notion.py ───────────────────────────────────────────────────
    ("POST", "/api/v1/admin/notion/config", {}, "admin-notion-config-save"),
    ("DELETE", "/api/v1/admin/notion/config", None, "admin-notion-config-delete"),
    ("POST", "/api/v1/admin/notion/test", {}, "admin-notion-test"),
]


@pytest.mark.parametrize(
    "method,path,body,label",
    ADMIN_WRITE_ENDPOINTS,
    ids=[ep[3] for ep in ADMIN_WRITE_ENDPOINTS],
)
@pytest.mark.asyncio(loop_scope="session")
async def test_admin_write_forbidden_for_user(user_client, method, path, body, label, regular_user_domain_id):
    """일반 유저의 관리자 쓰기 요청은 require_admin에서 403으로 즉시 차단된다.

    실제 caller domain ID와 가짜 리소스 ID를 사용하므로 실제 리소스 변경은 발생하지 않는다.
    Depends(require_admin)는 body 파싱보다 먼저 실행되므로 422가 아닌 403이 반환된다.
    """
    scoped = path.startswith(
        (
            "/api/v1/admin/users",
            "/api/v1/admin/projects",
            "/api/v1/admin/groups",
            "/api/v1/admin/quotas",
            "/api/v1/admin/roles/assign",
        )
    )
    creates = method == "POST" and path in {"/api/v1/admin/users", "/api/v1/admin/projects", "/api/v1/admin/groups"}
    payload = {**(body or {}), "domain_id": regular_user_domain_id} if creates else body
    params = {"domain_id": regular_user_domain_id} if scoped and not creates else {}
    resp = await user_client.request(method, path, json=payload, params=params)
    assert resp.status_code == 403, (
        f"{method} {path}: expected 403 (require_admin), got {resp.status_code}: {resp.text[:200]}"
    )
