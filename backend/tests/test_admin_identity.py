"""admin_identity.py 엔드포인트 단위 테스트.

사용자/프로젝트/그룹/역할/할당량 관리 API (22개 엔드포인트).
각 엔드포인트에 대해:
  - non_admin_client → 403
  - admin_client      → 명시적인 성공 응답 및 provider 부작용 검증
"""

import asyncio
import json
import threading
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis.aioredis
import pytest
from requests import Response

from app.services import identity_roles, keystone, session_store
from tests.ownership_journal import ownership_journal as ownership_journal
from tests.test_domain_projects import domain_native as domain_native


@pytest.fixture(autouse=True)
def selected_domain_directory(mock_conn, ownership_journal):
    """Native directory authority for these explicitly default-domain requests."""
    mock_conn.identity.get_domain.return_value = SimpleNamespace(id="default", name="Default")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 사용자 관리 (3개)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.mark.asyncio
async def test_list_users_requires_admin(non_admin_client):
    resp = await non_admin_client.get("/api/v1/admin/users?domain_id=default")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_users_allowed(admin_client, mock_conn):
    mock_conn.identity.users.return_value = iter([])
    resp = await admin_client.get("/api/v1/admin/users?domain_id=default")
    assert resp.status_code == 200
    assert resp.json() == {"items": [], "next_marker": None, "count": 0}


@pytest.mark.asyncio
async def test_create_user_requires_admin(non_admin_client):
    resp = await non_admin_client.post(
        "/api/v1/admin/users", json={"name": "u", "password": "pw", "domain_id": "default"}
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_update_user_requires_admin(non_admin_client):
    resp = await non_admin_client.patch("/api/v1/admin/users/user-1?domain_id=default", json={"name": "u"})
    assert resp.status_code == 403


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 프로젝트 관리 (6개)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.mark.asyncio
async def test_list_project_names_requires_admin(non_admin_client):
    resp = await non_admin_client.get("/api/v1/admin/projects/names?domain_id=default")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_projects_requires_admin(non_admin_client):
    resp = await non_admin_client.get("/api/v1/admin/projects?domain_id=default")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_projects_allowed(admin_client, mock_conn):
    mock_conn.identity.projects.return_value = iter([])
    resp = await admin_client.get("/api/v1/admin/projects?domain_id=default")
    assert resp.status_code == 200
    assert resp.json()["items"] == []
    assert resp.json()["count"] == 0
    assert resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_create_project_requires_admin(non_admin_client):
    resp = await non_admin_client.post("/api/v1/admin/projects", json={"name": "p", "domain_id": "default"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_update_project_requires_admin(non_admin_client):
    resp = await non_admin_client.patch("/api/v1/admin/projects/proj-1?domain_id=default", json={"name": "p"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_delete_project_requires_admin(non_admin_client):
    resp = await non_admin_client.delete("/api/v1/admin/projects/proj-1?domain_id=default")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_project_members_requires_admin(non_admin_client):
    resp = await non_admin_client.get("/api/v1/admin/projects/proj-1/members?domain_id=default")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_project_requires_admin(non_admin_client):
    resp = await non_admin_client.get("/api/v1/admin/projects/proj-1?domain_id=default")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_project_returns_shape(admin_client, mock_conn):
    """GET /api/admin/projects/{id} 가 Project shape 를 반환한다."""
    fake_proj = MagicMock()
    fake_proj.id = "proj-abc"
    fake_proj.name = "테스트 프로젝트"
    fake_proj.is_enabled = True
    fake_proj.domain_id = "default"
    fake_proj.created_at = "2024-01-01T00:00:00Z"
    type(fake_proj).__getattr__ = lambda self, k: None  # getattr fallback
    mock_conn.identity.get_project.return_value = fake_proj

    resp = await admin_client.get("/api/v1/admin/projects/proj-abc?domain_id=default")

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "proj-abc"
    assert data["name"] == "테스트 프로젝트"
    assert data["enabled"] is True
    assert data["domain_id"] == "default"
    assert "created_at" in data


@pytest.mark.asyncio
async def test_get_project_not_found(admin_client, mock_conn):
    """존재하지 않는 project_id → 404."""
    mock_conn.identity.get_project.return_value = None

    resp = await admin_client.get("/api/v1/admin/projects/nonexistent?domain_id=default")

    assert resp.status_code == 404
    assert resp.json() == {"detail": "identity_not_found"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 할당량 (2개)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.mark.asyncio
async def test_get_quota_requires_admin(non_admin_client):
    resp = await non_admin_client.get("/api/v1/admin/quotas/proj-1?domain_id=default")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_update_quota_requires_admin(non_admin_client):
    resp = await non_admin_client.put("/api/v1/admin/quotas/proj-1?domain_id=default", json={"cores": 20})
    assert resp.status_code == 403


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 그룹 관리 (6개)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.mark.asyncio
async def test_list_groups_requires_admin(non_admin_client):
    resp = await non_admin_client.get("/api/v1/admin/groups?domain_id=default")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_groups_allowed(admin_client, mock_conn):
    mock_conn.identity.groups.return_value = iter([])
    resp = await admin_client.get("/api/v1/admin/groups?domain_id=default")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_group_requires_admin(non_admin_client):
    resp = await non_admin_client.post("/api/v1/admin/groups", json={"name": "g", "domain_id": "default"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_update_group_requires_admin(non_admin_client):
    resp = await non_admin_client.patch("/api/v1/admin/groups/grp-1?domain_id=default", json={"name": "g"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_delete_group_requires_admin(non_admin_client):
    resp = await non_admin_client.delete("/api/v1/admin/groups/grp-1?domain_id=default")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_group_users_requires_admin(non_admin_client):
    resp = await non_admin_client.get("/api/v1/admin/groups/grp-1/users?domain_id=default")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_add_user_to_group_requires_admin(non_admin_client):
    resp = await non_admin_client.put("/api/v1/admin/groups/grp-1/users/user-1?domain_id=default")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_remove_user_from_group_requires_admin(non_admin_client):
    resp = await non_admin_client.delete("/api/v1/admin/groups/grp-1/users/user-1?domain_id=default")
    assert resp.status_code == 403


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 역할 관리 (5개)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.mark.asyncio
async def test_list_roles_requires_admin(non_admin_client):
    resp = await non_admin_client.get("/api/v1/admin/roles")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_roles_allowed(admin_client, mock_conn):
    mock_conn.identity.roles.return_value = iter([])
    mock_conn.identity.get.return_value.json.return_value = {"role_inferences": []}
    resp = await admin_client.get("/api/v1/admin/roles")
    assert resp.status_code == 200
    assert resp.json() == []
    mock_conn.identity.get.assert_called_once_with("/role_inferences")


@pytest.mark.asyncio
async def test_assign_role_requires_admin(non_admin_client):
    resp = await non_admin_client.post(
        "/api/v1/admin/roles/assign?domain_id=default", json={"user_id": "u", "project_id": "p", "role_id": "r"}
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_revoke_role_requires_admin(non_admin_client):
    resp = await non_admin_client.delete(
        "/api/v1/admin/roles/assign?domain_id=default",
        params={"domain_id": "default", "user_id": "u", "project_id": "p", "role_id": "r"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_assign_group_role_requires_admin(non_admin_client):
    resp = await non_admin_client.post(
        "/api/v1/admin/roles/assign-group?domain_id=default", json={"group_id": "g", "project_id": "p", "role_id": "r"}
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_revoke_group_role_requires_admin(non_admin_client):
    resp = await non_admin_client.delete(
        "/api/v1/admin/roles/assign-group?domain_id=default",
        params={"domain_id": "default", "group_id": "g", "project_id": "p", "role_id": "r"},
    )
    assert resp.status_code == 403


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 역할 할당/회수 audit + 즉시 세션 무효화
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_ADMIN_ROLE_ID = "admin-role-id-xyz"
_MEMBER_ROLE_ID = "member-role-id-abc"
_OWNER_ROLE_ID = "owner-role-id"
_OWNER_ALIAS_ID = "owner-alias-id"


@pytest.fixture
async def assignment_authority(mock_conn, monkeypatch):
    """Model Keystone's catalog/writes; run the real graph lock and session store."""
    roles = [
        {"id": rid, "name": name, "domain_id": None, "description": ""}
        for rid, name in (
            (_ADMIN_ROLE_ID, "admin"),
            (_MEMBER_ROLE_ID, "member"),
            ("manager-role-id", "manager"),
            ("reader-role-id", "reader"),
            (_OWNER_ROLE_ID, "project_owner"),
            (_OWNER_ALIAS_ID, "owner_alias"),
        )
    ]
    inferences = [
        {"prior_role": {"id": _ADMIN_ROLE_ID}, "implies": [{"id": _MEMBER_ROLE_ID}]},
        {"prior_role": {"id": _OWNER_ALIAS_ID}, "implies": [{"id": _OWNER_ROLE_ID}]},
    ]

    def graph(path):
        assert path == "/role_inferences"
        response = Response()
        response.status_code = 200
        response._content = json.dumps({"role_inferences": inferences}).encode()
        return response

    assignments = set()

    def assign(project_id, user_id, role_id):
        assignments.add((project_id, user_id, role_id))

    def revoke(project_id, user_id, role_id):
        assignments.remove((project_id, user_id, role_id))

    mock_conn.endpoint_for.return_value = "https://keystone.invalid/v3"
    mock_conn.identity.roles.side_effect = lambda: iter(roles)
    mock_conn.identity.get.side_effect = graph
    mock_conn.identity.get_user.side_effect = lambda uid: SimpleNamespace(
        id=uid, name=uid, domain_id="default", enabled=True
    )
    mock_conn.identity.get_project.side_effect = lambda pid: SimpleNamespace(
        id=pid, name=pid, domain_id="default", enabled=True
    )
    mock_conn.identity.get_group.side_effect = lambda gid: SimpleNamespace(
        id=gid, name=gid, domain_id="default", enabled=True
    )
    mock_conn.identity.get_role.side_effect = lambda rid: SimpleNamespace(
        **next(role for role in roles if role["id"] == rid)
    )
    mock_conn.identity.assign_project_role_to_user.side_effect = assign
    mock_conn.identity.unassign_project_role_from_user.side_effect = revoke

    def native_assignments(user=None, project=None, role=None, group=None, domain=None, system=None, **kwargs):
        if group is not None or domain is not None or system is not None:
            return []
        return [
            {"user": {"id": uid}, "role": {"id": rid}, "scope": {"project": {"id": pid}}}
            for pid, uid, rid in assignments
            if (user is None or uid == user) and (project is None or pid == project) and (role is None or rid == role)
        ]

    native = SimpleNamespace(
        users=SimpleNamespace(get=mock_conn.identity.get_user),
        projects=SimpleNamespace(get=mock_conn.identity.get_project),
        domains=SimpleNamespace(get=lambda did: SimpleNamespace(id=did, name="Default", enabled=True)),
        groups=SimpleNamespace(list=lambda **kwargs: []),
        roles=SimpleNamespace(list=lambda: list(roles)),
        inference_rules=SimpleNamespace(list_inference_roles=lambda: list(inferences)),
        role_assignments=SimpleNamespace(list=native_assignments),
    )
    monkeypatch.setattr(keystone, "_get_admin_ks_client", lambda: native)
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

    async def get_redis():
        return redis

    record = AsyncMock()
    revoke_token = MagicMock()
    monkeypatch.setattr(session_store, "_get_redis", get_redis)
    monkeypatch.setattr(keystone, "revoke_token", revoke_token)
    monkeypatch.setattr(identity_roles.activity, "record", record)
    try:
        yield SimpleNamespace(assignments=assignments, record=record, revoke_token=revoke_token, redis=redis)
    finally:
        await redis.close()


async def _assignment_sessions(user_id):
    for uid in (user_id, "unaffected-user"):
        await session_store.store_session("session-" + uid, "token-" + uid, "some-proj", uid, int(time.time()) + 3600)
    return {uid: await session_store.get_session("session-" + uid) for uid in (user_id, "unaffected-user")}


async def _assert_assignment_sessions(sessions):
    for uid, original in sessions.items():
        assert await session_store.get_session("session-" + uid) == original


@pytest.mark.asyncio
async def test_assign_admin_role_is_denied_without_native_writes_or_logout(
    admin_client, mock_conn, assignment_authority
):
    """A denied native admin project grant must not mutate IAM or login families."""
    sessions = await _assignment_sessions("target-user-1")
    resp = await admin_client.post(
        "/api/v1/admin/roles/assign?domain_id=default",
        json={"user_id": "target-user-1", "project_id": "admin-proj", "role_id": _ADMIN_ROLE_ID},
    )

    assert resp.status_code == 422
    assert "removal-only" in resp.json()["detail"]
    assert assignment_authority.assignments == set()
    mock_conn.identity.assign_project_role_to_user.assert_not_called()
    mock_conn.identity.unassign_project_role_from_user.assert_not_called()
    assignment_authority.revoke_token.assert_not_called()
    assignment_authority.record.assert_not_awaited()
    await _assert_assignment_sessions(sessions)


@pytest.mark.asyncio
async def test_assign_non_admin_role_preserves_login(admin_client, mock_conn, assignment_authority):
    """A member grant changes native authority without deleting login families."""
    sessions = await _assignment_sessions("target-user-2")
    resp = await admin_client.post(
        "/api/v1/admin/roles/assign?domain_id=default",
        json={"user_id": "target-user-2", "project_id": "some-proj", "role_id": _MEMBER_ROLE_ID},
    )

    assert resp.status_code == 200
    assert resp.json() == {"status": "assigned"}
    assert assignment_authority.assignments == {("some-proj", "target-user-2", _MEMBER_ROLE_ID)}
    await _assert_assignment_sessions(sessions)


@pytest.mark.asyncio
async def test_revoke_admin_role_preserves_login(admin_client, mock_conn, assignment_authority):
    """A project admin revoke removes the grant without deleting login families."""
    assignment_authority.assignments.add(("admin-proj", "target-user-3", _ADMIN_ROLE_ID))
    sessions = await _assignment_sessions("target-user-3")
    resp = await admin_client.delete(
        "/api/v1/admin/roles/assign?domain_id=default",
        params={
            "domain_id": "default",
            "user_id": "target-user-3",
            "project_id": "admin-proj",
            "role_id": _ADMIN_ROLE_ID,
        },
    )

    assert resp.status_code == 200
    assert resp.json() == {"status": "revoked"}
    assert assignment_authority.assignments == set()
    await _assert_assignment_sessions(sessions)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Security Policy
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.mark.asyncio
async def test_security_policy_requires_admin(non_admin_client):
    resp = await non_admin_client.get("/api/v1/admin/identity/security-policy")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_security_policy_returns_only_native_system_admin_count(admin_client):
    """Project grants and compatibility settings never affect the strict policy shape."""
    mock_ks = MagicMock()
    mock_ks.role_assignments.list.return_value = [
        SimpleNamespace(user={"id": "sys-1"}),
        SimpleNamespace(user={"id": "sys-2"}),
    ]
    mock_ks.users.get.return_value = SimpleNamespace(name="Admin", email="", enabled=True)
    with (
        patch("app.api.identity.admin_identity.keystone._resolve_admin_role_id", return_value=_ADMIN_ROLE_ID),
        patch("app.api.identity.admin_identity.keystone._get_admin_ks_client", return_value=mock_ks),
    ):
        resp = await admin_client.get("/api/v1/admin/identity/security-policy")

    assert resp.status_code == 200
    assert resp.json() == {"system_admin_count": 2}
    mock_ks.role_assignments.list.assert_called_once_with(role=_ADMIN_ROLE_ID, system="all")


@pytest.mark.asyncio
async def test_security_policy_native_list_failure_is_not_zero(admin_client):
    mock_ks = MagicMock()
    mock_ks.role_assignments.list.side_effect = RuntimeError("native assignment list unavailable")
    with (
        patch("app.api.identity.admin_identity.keystone._resolve_admin_role_id", return_value=_ADMIN_ROLE_ID),
        patch("app.api.identity.admin_identity.keystone._get_admin_ks_client", return_value=mock_ks),
    ):
        resp = await admin_client.get("/api/v1/admin/identity/security-policy")

    assert resp.status_code == 500
    assert "system_admin_count" not in resp.json()
    mock_ks.role_assignments.list.assert_called_once_with(role=_ADMIN_ROLE_ID, system="all")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# System Roles (system:all scope)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.mark.asyncio
async def test_list_system_roles_requires_admin(non_admin_client):
    resp = await non_admin_client.get("/api/v1/admin/identity/system-roles")
    assert resp.status_code == 403


class _SystemKeystone:
    """Native raw system grants and group members; effective omits system grants."""

    def __init__(self, direct, *, via_group=(), disabled=()):
        self.direct, self.via_group, self.disabled = set(direct), set(via_group), set(disabled)
        self.calls = []
        self.role_assignments = SimpleNamespace(list=self._list)
        self.roles = SimpleNamespace(grant=self._grant, revoke=self._revoke)
        native_roles = [
            {"id": role_id, "name": name, "domain_id": None}
            for role_id, name in (
                (_ADMIN_ROLE_ID, "admin"),
                ("native-manager", "manager"),
                (_MEMBER_ROLE_ID, "member"),
                ("native-reader", "reader"),
            )
        ]
        self.roles.list = lambda: list(native_roles)
        self.inference_rules = SimpleNamespace(list_inference_roles=lambda: [])
        self.domains = SimpleNamespace(
            get=lambda did: SimpleNamespace(id=did, name=did, enabled=True),
            list=lambda: [SimpleNamespace(id="default", name="Default", enabled=True)],
        )
        # System-authority tests represent a legacy identity domain with no
        # canonical Default project; policy reads must not bootstrap one.
        self.projects = SimpleNamespace(list=lambda **kwargs: [])
        self.groups = SimpleNamespace(
            get=lambda gid: SimpleNamespace(id=gid, name=gid, description="", domain_id="default"),
            list=lambda user=None, **kwargs: [SimpleNamespace(id="operators")] if user in self.via_group else [],
        )
        self.users = SimpleNamespace(
            get=lambda uid: SimpleNamespace(id=uid, domain_id="default", enabled=uid not in self.disabled),
            list=lambda group: (
                [SimpleNamespace(id=uid) for uid in sorted(self.via_group)] if group == "operators" else []
            ),
        )

    def _list(self, role=None, system=None, user=None, effective=False, group=None, project=None, domain=None):
        assert system in {None, "all"}
        if project is not None or domain is not None:
            return []
        if effective:
            return []
        rows = [
            SimpleNamespace(user={"id": uid}, role={"id": _ADMIN_ROLE_ID}, scope={"system": {"all": True}})
            for uid in sorted(self.direct)
            if group is None and (user is None or uid == user)
        ]
        if self.via_group and user is None and group in {None, "operators"}:
            rows.append(
                SimpleNamespace(group={"id": "operators"}, role={"id": _ADMIN_ROLE_ID}, scope={"system": {"all": True}})
            )
        return rows

    def _grant(self, *, role, user, system):
        self.calls.append(("grant", user))
        self.direct.add(user)

    def _revoke(self, *, role, user, system):
        self.calls.append(("revoke", user))
        self.direct.discard(user)


@pytest.fixture
def system_keystone(assignment_authority, monkeypatch, mock_conn):
    state = {}
    original_roles = mock_conn.identity.roles.side_effect

    def native_catalog():
        rows = list(original_roles())
        if not any(identity_roles._field(row, "name") == "manager" for row in rows):
            rows.append({"id": "native-manager", "name": "manager", "domain_id": None, "description": ""})
        return iter(rows)

    mock_conn.identity.roles.side_effect = native_catalog

    def install(ks):
        state["ks"] = ks
        monkeypatch.setattr(keystone, "_resolve_admin_role_id", lambda: _ADMIN_ROLE_ID)
        monkeypatch.setattr(keystone, "_get_admin_ks_client", lambda: ks)
        return ks

    return install


@pytest.mark.asyncio
async def test_grant_system_role_revokes_sessions(admin_client, system_keystone):
    """system role grant 시 대상 세션 즉시 무효화 + audit 기록."""
    ks = system_keystone(_SystemKeystone({"admin-1"}))
    with (
        patch(
            "app.api.identity.admin_identity.session_store.revoke_user_sessions", new=AsyncMock(return_value=1)
        ) as mock_revoke,
        patch("app.api.identity.admin_identity.activity.record", new=AsyncMock()) as mock_record,
    ):
        resp = await admin_client.post("/api/v1/admin/identity/system-roles/grant", json={"user_id": "target-user-sys"})
    assert resp.status_code == 200
    assert ks.calls == [("grant", "target-user-sys")]
    mock_revoke.assert_awaited_once_with("target-user-sys")
    assert mock_record.call_args.kwargs["action"] == "admin_system_role_grant"
    assert mock_record.call_args.kwargs["resource_id"] == "target-user-sys"


@pytest.mark.asyncio
async def test_revoke_system_role_revokes_sessions(admin_client, system_keystone):
    """system role revoke 시 대상 세션 즉시 무효화 + audit 기록."""
    ks = system_keystone(_SystemKeystone({"target-user-sys", "admin-2"}))
    with (
        patch(
            "app.api.identity.admin_identity.session_store.revoke_user_sessions", new=AsyncMock(return_value=1)
        ) as mock_revoke,
        patch("app.api.identity.admin_identity.activity.record", new=AsyncMock()) as mock_record,
    ):
        resp = await admin_client.post(
            "/api/v1/admin/identity/system-roles/revoke", json={"user_id": "target-user-sys"}
        )
    assert resp.status_code == 200 and resp.json()["status"] == "revoked"
    assert ks.calls == [("revoke", "target-user-sys")]
    mock_revoke.assert_awaited_once_with("target-user-sys")
    assert mock_record.call_args.kwargs["action"] == "admin_system_role_revoke"


@pytest.mark.asyncio
async def test_native_admin_project_restriction_does_not_block_dedicated_system_admin_lifecycle(
    admin_client, system_keystone, monkeypatch
):
    ks = system_keystone(_SystemKeystone({"admin-1"}))
    project_assignment = AsyncMock(side_effect=AssertionError("System scope must not use project assignment"))
    monkeypatch.setattr(identity_roles, "change_project_assignment", project_assignment)
    with (
        patch("app.api.identity.admin_identity.session_store.revoke_user_sessions", new=AsyncMock(return_value=1)),
        patch("app.api.identity.admin_identity.activity.record", new=AsyncMock()),
    ):
        granted = await admin_client.post(
            "/api/v1/admin/identity/system-roles/grant", json={"user_id": "target-user-sys"}
        )
        assert granted.status_code == 200
        assert ks.direct == {"admin-1", "target-user-sys"}
        revoked = await admin_client.post("/api/v1/admin/identity/system-roles/revoke", json={"user_id": "admin-1"})
        assert revoked.status_code == 200
        assert ks.direct == {"target-user-sys"}
        protected = await admin_client.post(
            "/api/v1/admin/identity/system-roles/revoke", json={"user_id": "target-user-sys"}
        )
    assert protected.status_code == 422
    assert "마지막" in protected.json()["detail"]
    assert ks.direct == {"target-user-sys"}
    assert ks.calls == [("grant", "target-user-sys"), ("revoke", "admin-1")]
    project_assignment.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["cancel", "lost_reply"])
async def test_committed_system_revoke_invalidates_sessions_after_interrupted_reply(
    admin_client, system_keystone, monkeypatch, failure
):
    from app.api.identity import admin_identity

    ks = system_keystone(_SystemKeystone({"target-user-sys", "admin-2"}))
    entered, release = threading.Event(), threading.Event()
    original = ks.roles.revoke
    sessions = {"target-user-sys", "admin-2"}
    cleared_authority = []

    def revoke(**attrs):
        entered.set()
        assert release.wait(5)
        original(**attrs)
        if failure == "lost_reply":
            raise ConnectionError("Synthetic committed revocation reply lost")

    async def invalidate():
        cleared_authority.append(True)

    async def revoke_sessions(uid):
        sessions.discard(uid)

    ks.roles.revoke = revoke
    monkeypatch.setattr(admin_identity, "invalidate_authority", invalidate)
    monkeypatch.setattr(session_store, "revoke_user_sessions", revoke_sessions)
    monkeypatch.setattr(admin_identity.activity, "record", AsyncMock())
    request = asyncio.create_task(
        admin_client.post("/api/v1/admin/identity/system-roles/revoke", json={"user_id": "target-user-sys"})
    )
    try:
        assert await asyncio.to_thread(entered.wait, 5)
        if failure == "cancel":
            request.cancel()
        release.set()
        if failure == "cancel":
            with pytest.raises(asyncio.CancelledError):
                await request
        else:
            assert (await request).status_code >= 500
    finally:
        release.set()
    assert ks.direct == {"admin-2"}
    assert sessions == {"admin-2"}
    assert cleared_authority


@pytest.mark.asyncio
async def test_list_system_roles_returns_enriched_fields(admin_client):
    """list_system_roles 응답에 name/email/enabled 필드가 포함된다."""
    mock_assignment = MagicMock()
    mock_assignment.user = {"id": "sys-user-1"}

    mock_user = MagicMock()
    mock_user.name = "Alice"
    mock_user.email = "alice@example.com"
    mock_user.enabled = True

    mock_ks = MagicMock()
    mock_ks.role_assignments.list.return_value = [mock_assignment]
    mock_ks.users.get.return_value = mock_user

    with (
        patch(
            "app.api.identity.admin_identity.keystone._resolve_admin_role_id",
            return_value=_ADMIN_ROLE_ID,
        ),
        patch(
            "app.api.identity.admin_identity.keystone._get_admin_ks_client",
            return_value=mock_ks,
        ),
    ):
        resp = await admin_client.get("/api/v1/admin/identity/system-roles")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["user_id"] == "sys-user-1"
    assert data[0]["name"] == "Alice"
    assert data[0]["email"] == "alice@example.com"
    assert data[0]["enabled"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "direct,disabled",
    [({"last-admin"}, set()), ({"last-admin", "disabled-admin"}, {"disabled-admin"})],
)
async def test_revoke_last_enabled_effective_system_admin_blocked(admin_client, system_keystone, direct, disabled):
    """A disabled account never counts as the remaining administrator."""
    ks = system_keystone(_SystemKeystone(direct, disabled=disabled))
    with patch("app.api.identity.admin_identity.activity.record", new=AsyncMock()):
        resp = await admin_client.post("/api/v1/admin/identity/system-roles/revoke", json={"user_id": "last-admin"})
    assert resp.status_code == 422
    assert "마지막" in resp.json()["detail"]
    assert ks.calls == []


@pytest.mark.asyncio
async def test_revoke_allowed_when_group_derived_admin_remains(admin_client, system_keystone):
    ks = system_keystone(_SystemKeystone({"admin-1"}, via_group={"group-admin"}))
    with patch("app.api.identity.admin_identity.activity.record", new=AsyncMock()):
        resp = await admin_client.post("/api/v1/admin/identity/system-roles/revoke", json={"user_id": "admin-1"})
    assert resp.status_code == 200
    assert ks.calls == [("revoke", "admin-1")]


@pytest.mark.asyncio
async def test_revoke_without_direct_grant_is_not_found(admin_client, system_keystone):
    ks = system_keystone(_SystemKeystone({"admin-1", "admin-2"}, via_group={"group-only"}))
    with patch("app.api.identity.admin_identity.activity.record", new=AsyncMock()):
        resp = await admin_client.post("/api/v1/admin/identity/system-roles/revoke", json={"user_id": "group-only"})
    assert resp.status_code == 404
    assert ks.calls == []


@pytest.mark.asyncio
async def test_concurrent_revokes_never_remove_every_system_admin(admin_client, system_keystone):
    ks = system_keystone(_SystemKeystone({"admin-1", "admin-2"}))
    with patch("app.api.identity.admin_identity.activity.record", new=AsyncMock()):
        responses = await asyncio.gather(
            admin_client.post("/api/v1/admin/identity/system-roles/revoke", json={"user_id": "admin-1"}),
            admin_client.post("/api/v1/admin/identity/system-roles/revoke", json={"user_id": "admin-2"}),
        )
    assert all(r.status_code in (200, 409, 422) for r in responses)
    assert len([r for r in responses if r.status_code == 200]) == 1
    assert len(ks.direct) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("others,status", [(set(), 422), ({"admin-2"}, 200)])
async def test_disabling_last_enabled_system_admin_is_refused(admin_client, mock_conn, system_keystone, others, status):
    system_keystone(_SystemKeystone({"admin-1", *others}))
    mock_conn.identity.update_user.return_value = SimpleNamespace(id="admin-1", name="a", email="", is_enabled=False)
    resp = await admin_client.patch("/api/v1/admin/users/admin-1", json={"enabled": False})
    assert resp.status_code == status
    assert mock_conn.identity.update_user.called is (status == 200)


def _system_group(mock_conn, group_id, members):
    mock_conn.identity.role_assignments.side_effect = lambda **_: [
        SimpleNamespace(group={"id": group_id}, role={"id": _ADMIN_ROLE_ID}, scope={"system": {"all": True}})
    ]
    mock_conn.identity.group_users.side_effect = lambda gid: iter(SimpleNamespace(id=uid) for uid in members)


@pytest.mark.asyncio
@pytest.mark.parametrize("group_admins,status", [({"admin-1"}, 422), ({"admin-1", "admin-2"}, 204)])
async def test_group_member_removal_keeps_a_system_admin(
    admin_client, mock_conn, system_keystone, group_admins, status
):
    system_keystone(_SystemKeystone(set(), via_group=group_admins))
    _system_group(mock_conn, "sys-group", group_admins)
    resp = await admin_client.delete("/api/v1/admin/groups/sys-group/users/admin-1")
    assert resp.status_code == status
    assert mock_conn.identity.remove_user_from_group.called is (status == 204)


@pytest.mark.asyncio
async def test_group_delete_cannot_remove_every_system_admin(admin_client, mock_conn, system_keystone):
    system_keystone(_SystemKeystone(set(), via_group={"admin-1", "admin-2"}))
    _system_group(mock_conn, "sys-group", {"admin-1", "admin-2", "member"})
    resp = await admin_client.delete("/api/v1/admin/groups/sys-group")
    assert resp.status_code == 422
    mock_conn.identity.delete_group.assert_not_called()


@pytest.mark.asyncio
async def test_unreadable_system_authority_fails_closed(admin_client, mock_conn, system_keystone, monkeypatch):
    system_keystone(_SystemKeystone({"admin-1", "admin-2"}))

    def unavailable():
        raise RuntimeError("keystone down")

    monkeypatch.setattr(keystone, "_get_admin_ks_client", unavailable)
    resp = await admin_client.patch("/api/v1/admin/users/admin-1", json={"enabled": False})
    assert resp.status_code == 503
    mock_conn.identity.update_user.assert_not_called()


@pytest.mark.asyncio
async def test_revoke_non_admin_role_preserves_login(admin_client, mock_conn, assignment_authority):
    """Member revocation removes native authority without deleting login families."""
    assignment_authority.assignments.add(("some-proj", "target-user-4", _MEMBER_ROLE_ID))
    sessions = await _assignment_sessions("target-user-4")
    resp = await admin_client.delete(
        "/api/v1/admin/roles/assign?domain_id=default",
        params={
            "domain_id": "default",
            "user_id": "target-user-4",
            "project_id": "some-proj",
            "role_id": _MEMBER_ROLE_ID,
        },
    )

    assert resp.status_code == 200
    assert resp.json() == {"status": "revoked"}
    assert assignment_authority.assignments == set()
    await _assert_assignment_sessions(sessions)


@pytest.mark.asyncio
async def test_sync_monitoring_sg_returns_both_sg_names(admin_client, mock_conn):
    """sync-monitoring-sg 엔드포인트가 두 SG 이름을 반환한다."""
    mock_conn.identity.get_project.return_value = SimpleNamespace(id="proj-abc", domain_id="default")
    fake_settings = MagicMock()
    fake_settings.monitoring_scrape_cidr = "10.0.0.0/8"
    fake_settings.node_exporter_sg_name = "node_exporter"
    fake_settings.dcgm_exporter_sg_name = "dcgm_exporter"

    with (
        patch("app.config.get_settings", return_value=fake_settings),
        patch("app.services.neutron.ensure_node_exporter_sg", return_value="node_exporter"),
        patch("app.services.neutron.ensure_dcgm_exporter_sg", return_value="dcgm_exporter"),
    ):
        resp = await admin_client.post("/api/v1/admin/projects/proj-abc/sync-monitoring-sg?domain_id=default")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["project_id"] == "proj-abc"
    assert data["sg_names"]["node_exporter"] == "node_exporter"
    assert data["sg_names"]["dcgm_exporter"] == "dcgm_exporter"


@pytest.mark.asyncio
async def test_admin_version_returns_current_runtime_shape(admin_client):
    """GET /api/v1/admin/version 엔드포인트가 현재 런타임 구조를 반환한다."""
    resp = await admin_client.get("/api/v1/admin/version")
    assert resp.status_code == 200
    data = resp.json()

    assert "platform" in data
    assert isinstance(data["platform"].get("backend_version"), str)

    assert "runtime" in data
    assert isinstance(data["runtime"].get("python_version"), str)
    assert isinstance(data["runtime"].get("uptime_seconds"), int)

    assert "dependencies" in data
    assert isinstance(data["dependencies"], dict)
    for pkg in ("fastapi", "openstacksdk", "python-keystoneclient", "pydantic", "uvicorn"):
        assert pkg in data["dependencies"]
        assert data["dependencies"][pkg] is None or isinstance(data["dependencies"][pkg], str)

    assert "git" in data
    assert isinstance(data["git"], dict)
    assert "commit" in data["git"]
    assert "tag" in data["git"]
    assert "branch" in data["git"]
    assert data["git"]["commit"] is None or isinstance(data["git"]["commit"], str)
    assert data["git"]["tag"] is None or isinstance(data["git"]["tag"], str)
    assert data["git"]["branch"] is None or isinstance(data["git"]["branch"], str)

    assert "config" not in data


@pytest.mark.asyncio
@pytest.mark.parametrize("role_id", [_OWNER_ROLE_ID, _OWNER_ALIAS_ID])
@pytest.mark.parametrize("remove", [False, True])
@pytest.mark.parametrize("principal", ["user", "group"])
async def test_generic_assignment_rejects_owner_bearing_roles_without_side_effects(
    admin_client, mock_conn, assignment_authority, role_id, remove, principal
):
    await _assignment_sessions("target-user")
    assignment = ("some-proj", "target-user", role_id)
    assignment_authority.assignments.add(assignment)
    payload = {
        f"{principal}_id": "target-user" if principal == "user" else "target-group",
        "project_id": "some-proj",
        "role_id": role_id,
    }
    path = "/api/v1/admin/roles/assign" + ("-group" if principal == "group" else "") + "?domain_id=default"
    if remove:
        response = await admin_client.delete(path, params={"domain_id": "default", **payload})
    else:
        response = await admin_client.post(path, json=payload)

    assert response.status_code == 409
    assert "ownership workflow" in response.json()["detail"]
    assert assignment_authority.assignments == {assignment}
    for method in (
        "assign_project_role_to_user",
        "unassign_project_role_from_user",
        "assign_project_role_to_group",
        "unassign_project_role_from_group",
    ):
        getattr(mock_conn.identity, method).assert_not_called()
    assignment_authority.record.assert_not_awaited()
    assignment_authority.revoke_token.assert_not_called()
    assert await session_store.get_session("session-target-user") is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("remove", [False, True])
async def test_project_assignment_fails_closed_without_graph_metadata(
    admin_client, mock_conn, assignment_authority, remove
):
    await _assignment_sessions("target-user")
    mock_conn.identity.get.side_effect = RuntimeError("provider graph unavailable")
    payload = {"user_id": "target-user", "project_id": "some-proj", "role_id": _MEMBER_ROLE_ID}
    if remove:
        response = await admin_client.delete(
            "/api/v1/admin/roles/assign?domain_id=default", params={"domain_id": "default", **payload}
        )
    else:
        response = await admin_client.post("/api/v1/admin/roles/assign?domain_id=default", json=payload)

    assert response.status_code == 503
    mock_conn.identity.assign_project_role_to_user.assert_not_called()
    mock_conn.identity.unassign_project_role_from_user.assert_not_called()
    assignment_authority.record.assert_not_awaited()
    assignment_authority.revoke_token.assert_not_called()
    assert await session_store.get_session("session-target-user") is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("remove", [False, True])
async def test_project_assignment_rejects_concurrent_graph_mutation(
    admin_client, mock_conn, assignment_authority, remove
):
    await _assignment_sessions("target-user")
    payload = {"user_id": "target-user", "project_id": "some-proj", "role_id": _MEMBER_ROLE_ID}
    async with identity_roles._graph_lock(mock_conn):
        if remove:
            response = await admin_client.delete(
                "/api/v1/admin/roles/assign?domain_id=default", params={"domain_id": "default", **payload}
            )
        else:
            response = await admin_client.post("/api/v1/admin/roles/assign?domain_id=default", json=payload)

    assert response.status_code == 409
    assert "in progress" in response.json()["detail"]
    mock_conn.identity.roles.assert_not_called()
    mock_conn.identity.assign_project_role_to_user.assert_not_called()
    mock_conn.identity.unassign_project_role_from_user.assert_not_called()
    assignment_authority.record.assert_not_awaited()
    assignment_authority.revoke_token.assert_not_called()
    assert await session_store.get_session("session-target-user") is not None


@pytest.mark.asyncio
async def test_revoke_counts_native_role_inference_admin(admin_client, system_keystone, monkeypatch):
    ks = system_keystone(_SystemKeystone({"admin-1"}))
    direct_list = ks.role_assignments.list

    def assignments(**query):
        rows = direct_list(**query)
        if query.get("user") is None:
            rows.append(
                SimpleNamespace(
                    user={"id": "alias-admin"}, role={"id": "system-admin-alias"}, scope={"system": {"all": True}}
                )
            )
        return rows

    ks.role_assignments.list = assignments
    monkeypatch.setattr(
        identity_roles,
        "_trusted_catalog",
        lambda: [
            {"id": _ADMIN_ROLE_ID, "inherited_role_ids": []},
            {"id": "system-admin-alias", "inherited_role_ids": [_ADMIN_ROLE_ID]},
        ],
    )
    response = await admin_client.post("/api/v1/admin/identity/system-roles/revoke", json={"user_id": "admin-1"})
    assert response.status_code == 200
    assert ks.calls == [("revoke", "admin-1")]


@pytest.mark.asyncio
async def test_revoke_rejects_foreign_scope_in_system_directory(admin_client, system_keystone):
    ks = system_keystone(_SystemKeystone({"admin-1", "admin-2"}))
    direct_list = ks.role_assignments.list

    def assignments(**query):
        rows = direct_list(**query)
        if query.get("user") is None:
            rows[-1].scope = {"project": {"id": "foreign-project"}}
        return rows

    ks.role_assignments.list = assignments
    response = await admin_client.post("/api/v1/admin/identity/system-roles/revoke", json={"user_id": "admin-1"})
    assert response.status_code == 503
    assert ks.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("attrs", [{"name": "Renamed"}, {"enabled": False}])
async def test_default_project_mutation_rejected_before_provider_write(admin_client, mock_conn, domain_native, attrs):
    mock_conn.identity.get_project.return_value = SimpleNamespace(
        id="domain-default", name="Default", domain_id="default", is_enabled=True
    )
    response = await admin_client.patch("/api/v1/admin/projects/domain-default?domain_id=default", json=attrs)
    assert response.status_code == 422
    mock_conn.identity.update_project.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path", [("DELETE", ""), ("GET", "/deletion-check")])
async def test_default_project_delete_rejected_before_resource_inspection(
    admin_client, mock_conn, domain_native, method, path
):
    mock_conn.identity.get_project.return_value = SimpleNamespace(
        id="domain-default", name="Default", domain_id="default", is_enabled=True
    )
    with patch("app.api.identity.admin_identity.inspect_project_resources") as inspect:
        response = await admin_client.request(method, f"/api/v1/admin/projects/domain-default{path}?domain_id=default")
    assert response.status_code == 422
    inspect.assert_not_called()
    mock_conn.identity.delete_project.assert_not_called()


@pytest.mark.asyncio
async def test_ordinary_project_cannot_be_renamed_to_default(admin_client, mock_conn, domain_native):
    mock_conn.identity.get_project.return_value = SimpleNamespace(
        id="tenant", name="Tenant", domain_id="default", is_enabled=True
    )
    response = await admin_client.patch("/api/v1/admin/projects/tenant?domain_id=default", json={"name": "Default"})
    assert response.status_code == 422
    mock_conn.identity.update_project.assert_not_called()
