"""Selected-domain administrator identity boundaries through the real admin router.

Keystone is an SDK-shaped fixture that deliberately ignores domain filters so
the route's own exact domain proof is exercised before pagination or mutation.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import event

from app.api.deps import get_os_conn, get_token_info, require_admin
from app.api.identity import admin_identity
from app.database import get_session
from app.services import activity, identity_roles, session_store
from tests.admin_gate import synthetic_verified_admin
from tests.test_domain_iam import directory as directory
from tests.test_domain_iam import enrollments as enrollments

DOMAIN = {"domain_id": "tenant-a"}


class NativeError(Exception):
    def __init__(self, status):
        super().__init__("native-secret-detail")
        self.status_code = status


def obj(id, domain_id="tenant-a", **extra):
    return SimpleNamespace(id=id, name=id, domain_id=domain_id, is_enabled=True, description="", email="", **extra)


@pytest.fixture
def native():
    conn = MagicMock()
    domains = {
        "tenant-a": SimpleNamespace(id="tenant-a", name="A"),
        "tenant-b": SimpleNamespace(id="tenant-b", name="B"),
    }
    users = {u.id: u for u in [obj("u1"), obj("u2"), obj("u3"), obj("x1", "tenant-b")]}
    projects = {p.id: p for p in [obj("p1"), obj("px", "tenant-b")]}
    groups = {g.id: g for g in [obj("g1"), obj("gx", "tenant-b")]}
    roles = {
        "global": SimpleNamespace(id="global", domain_id=None),
        "foreign-role": SimpleNamespace(id="foreign-role", domain_id="tenant-b"),
    }
    conn.identity.get_domain.side_effect = lambda i: domains.get(i)
    conn.identity.get_user.side_effect = lambda i: users.get(i)
    conn.identity.get_project.side_effect = lambda i: projects.get(i)
    conn.identity.get_group.side_effect = lambda i: groups.get(i)
    conn.identity.get_role.side_effect = lambda i: roles.get(i)
    conn.identity.users.side_effect = lambda **_: iter(users.values())
    conn.identity.projects.side_effect = lambda **_: iter(projects.values())
    conn.identity.groups.side_effect = lambda **_: iter(groups.values())
    return conn


@pytest.fixture
def app(native, monkeypatch):
    info = {"user_id": "operator", "username": "operator", "project_id": "admin", "is_system_admin": True}
    application = FastAPI()
    application.include_router(admin_identity.router, prefix="/api/v1/admin")
    application.dependency_overrides[get_os_conn] = lambda: native
    application.dependency_overrides[get_token_info] = lambda: info
    application.dependency_overrides[require_admin] = synthetic_verified_admin
    monkeypatch.setattr(activity, "get_user_activity_bounds", AsyncMock(return_value={}))
    monkeypatch.setattr(activity, "get_resource_creation_times", AsyncMock(return_value={}))
    monkeypatch.setattr(activity, "record", AsyncMock())
    return application


def client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_lists_exclude_foreign_objects_before_pagination(app):
    async with client(app) as http:
        first = await http.get("/api/v1/admin/users", params={**DOMAIN, "limit": 2})
        second = await http.get(
            "/api/v1/admin/users", params={**DOMAIN, "limit": 2, "marker": first.json()["next_marker"]}
        )
        stats = await http.get("/api/v1/admin/users/stats", params=DOMAIN)
        projects = await http.get("/api/v1/admin/projects", params=DOMAIN)
        names = await http.get("/api/v1/admin/projects/names", params=DOMAIN)
        groups = await http.get("/api/v1/admin/groups", params=DOMAIN)
    assert [u["id"] for u in first.json()["items"]] == ["u1", "u2"]
    assert [u["id"] for u in second.json()["items"]] == ["u3"] and second.json()["next_marker"] is None
    assert stats.json() == {"total": 3, "enabled": 3, "disabled": 0}
    assert [p["id"] for p in projects.json()["items"]] == ["p1"] and projects.json()["total"] == 1
    assert [p["id"] for p in names.json()] == ["p1"]
    assert [g["id"] for g in groups.json()] == ["g1"]


@pytest.mark.asyncio
@pytest.mark.parametrize("email", ["foreign@test.invalid", "FOREIGN@TEST.INVALID"])
async def test_admin_email_update_cannot_claim_existing_foreign_home_address(app, native, directory, email):
    async with client(app) as http:
        response = await http.patch("/api/v1/admin/users/u1", params=DOMAIN, json={"email": email})
    assert response.status_code == 409
    assert response.json()["detail"] == "Email belongs to another account"
    assert directory.users["foreign"].email == "foreign@test.invalid"
    native.identity.update_user.assert_not_called()


@pytest.mark.asyncio
async def test_user_activity_is_limited_to_domain_subjects(app, monkeypatch):
    events = AsyncMock(return_value=[])
    monkeypatch.setattr(activity, "list_user_management_events", events)
    async with client(app) as http:
        response = await http.get("/api/v1/admin/users/activity", params={**DOMAIN, "limit": 5})
    assert response.status_code == 200
    assert sorted(events.call_args.kwargs["user_ids"]) == ["u1", "u2", "u3"]


@pytest.mark.asyncio
async def test_domain_selection_and_explicit_creation_domain_are_required(app, native, enrollments):
    # FastAPI resolves the session dependency before validating the request body.
    # Supply the real isolated store, but require validation to touch no SQL.
    async def session_dep():
        async with enrollments() as session:
            yield session

    statements = []

    def record_sql(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    app.dependency_overrides[get_session] = session_dep
    engine = enrollments.kw["bind"]
    event.listen(engine.sync_engine, "before_cursor_execute", record_sql)
    user = {
        "name": "n",
        "email": "new@test.invalid",
        "password": "Strong-password-123!",
    }
    try:
        async with client(app) as http:
            assert (await http.get("/api/v1/admin/users")).status_code == 422
            missing_domain = await http.post("/api/v1/admin/users", json=user)
            assert missing_domain.status_code == 422
            assert [error["loc"] for error in missing_domain.json()["detail"]] == [["body", "domain_id"]]
            removed_personal = await http.post(
                "/api/v1/admin/users",
                json={**user, **DOMAIN, "personal_domain_name": "Not accepted"},
            )
            assert removed_personal.status_code == 422
            assert [error["loc"] for error in removed_personal.json()["detail"]] == [["body", "personal_domain_name"]]
            assert (await http.post("/api/v1/admin/projects", json={"name": "n"})).status_code == 422
            assert (await http.post("/api/v1/admin/groups", json={"name": "n"})).status_code == 422
            unknown = await http.post("/api/v1/admin/projects", json={"name": "n", "domain_id": "absent"})
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", record_sql)
        app.dependency_overrides.pop(get_session)
    assert unknown.status_code == 404
    assert statements == []
    native.identity.get_domain.assert_called_once_with("absent")
    native.identity.create_user.assert_not_called()
    native.identity.create_project.assert_not_called()
    native.identity.create_group.assert_not_called()


@pytest.mark.asyncio
async def test_creation_sends_selected_domain(app, native):
    native.identity.create_group.side_effect = lambda **kw: obj("new", kw["domain_id"])
    async with client(app) as http:
        response = await http.post("/api/v1/admin/groups", json={"name": "team", "domain_id": "tenant-a"})
    assert response.status_code == 201
    native.identity.create_group.assert_called_once_with(name="team", domain_id="tenant-a")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,path,body",
    [
        ("PATCH", "/api/v1/admin/users/x1", {"name": "n"}),
        ("GET", "/api/v1/admin/users/x1/sessions", None),
        ("POST", "/api/v1/admin/users/x1/revoke-sessions", None),
        ("PATCH", "/api/v1/admin/projects/px", {"name": "n"}),
        ("DELETE", "/api/v1/admin/projects/px", None),
        ("GET", "/api/v1/admin/quotas/px", None),
        ("DELETE", "/api/v1/admin/groups/gx/users/u1", None),
        ("POST", "/api/v1/admin/roles/assign", {"user_id": "u1", "project_id": "px", "role_id": "global"}),
        ("POST", "/api/v1/admin/roles/assign", {"user_id": "u1", "project_id": "p1", "role_id": "foreign-role"}),
    ],
)
async def test_foreign_objects_are_rejected_before_native_mutation(app, native, monkeypatch, method, path, body):
    membership = AsyncMock()
    assignment = AsyncMock()
    revoke = AsyncMock(return_value=0)
    monkeypatch.setattr(identity_roles, "change_group_membership", membership)
    monkeypatch.setattr(identity_roles, "change_project_assignment", assignment)
    monkeypatch.setattr(session_store, "revoke_user_sessions", revoke)
    async with client(app) as http:
        response = await http.request(method, path, params=DOMAIN, json=body)
    assert response.status_code == 403
    assert response.json()["detail"] == "identity_domain_mismatch"
    native.identity.update_user.assert_not_called()
    native.identity.update_project.assert_not_called()
    native.identity.delete_project.assert_not_called()
    membership.assert_not_called()
    assignment.assert_not_called()
    revoke.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,expected", [(403, "identity_native_denied"), (404, "identity_not_found"), (500, "identity_unavailable")]
)
async def test_native_directory_errors_are_preserved_not_empty(app, native, status, expected):
    native.identity.users.side_effect = NativeError(status)
    async with client(app) as http:
        response = await http.get("/api/v1/admin/users", params=DOMAIN)
    assert response.json()["detail"] == expected
    assert response.status_code == {403: 403, 404: 404, 500: 503}[status]
    assert "native-secret-detail" not in response.text


@pytest.mark.asyncio
async def test_permissions_are_projected_to_selected_domain_and_sessions_stay_revocable(app, monkeypatch):
    # The user is proven in tenant-a; legacy rows without stored domain remain visible.
    sessions = [{"jti_hash": "a", "domain_id": "tenant-a"}, {"jti_hash": "c"}]
    monkeypatch.setattr(session_store, "list_user_sessions", AsyncMock(return_value=sessions))
    monkeypatch.setattr(
        identity_roles,
        "user_permissions",
        lambda conn, user_id: {
            "items": [
                {"scope_type": "system", "scope_id": "all", "roles": []},
                {"scope_type": "domain", "scope_id": "tenant-a", "roles": []},
                {"scope_type": "domain", "scope_id": "tenant-b", "roles": []},
                {"scope_type": "project", "scope_id": "p1", "roles": []},
                {"scope_type": "project", "scope_id": "px", "roles": []},
            ],
            "count": 5,
        },
    )
    async with client(app) as http:
        listed = await http.get("/api/v1/admin/users/u1/sessions", params=DOMAIN)
        permissions = await http.get("/api/v1/admin/users/u1/permissions", params=DOMAIN)
    assert listed.json() == {"sessions": sessions, "count": 2}
    assert [(i["scope_type"], i["scope_id"]) for i in permissions.json()["items"]] == [
        ("system", "all"),
        ("domain", "tenant-a"),
        ("project", "p1"),
    ]


@pytest.mark.asyncio
async def test_project_members_include_exact_project_cross_identity_principals(app, native):
    native.identity.role_assignments.return_value = [
        SimpleNamespace(
            user={"id": "u1"}, group=None, role={"id": "r", "name": "member"}, scope={"project": {"id": "p1"}}
        ),
        SimpleNamespace(
            user={"id": "x1"}, group=None, role={"id": "r", "name": "member"}, scope={"project": {"id": "p1"}}
        ),
        SimpleNamespace(
            user=None, group={"id": "gx"}, role={"id": "r", "name": "member"}, scope={"project": {"id": "p1"}}
        ),
        SimpleNamespace(
            user=None, group={"id": "g1"}, role={"id": "r", "name": "member"}, scope={"project": {"id": "p1"}}
        ),
    ]
    async with client(app) as http:
        response = await http.get("/api/v1/admin/projects/p1/members", params=DOMAIN)
    assert [(row["type"], row["user_id"]) for row in response.json()] == [
        ("user", "u1"),
        ("user", "x1"),
        ("group", "group:gx"),
        ("group", "group:g1"),
    ]
    assert next(row for row in response.json() if row["user_id"] == "x1")["identity_read_only"]
    native.identity.users.assert_not_called()
    native.identity.groups.assert_not_called()
    native.identity.role_assignments.assert_called_once_with(scope_project_id="p1", include_names=True)


@pytest.mark.asyncio
async def test_security_policy_reports_only_actual_system_grants(app, monkeypatch):
    monkeypatch.setattr(
        admin_identity, "list_system_roles", AsyncMock(return_value=[{"user_id": "a"}, {"user_id": "b"}])
    )
    async with client(app) as http:
        response = await http.get("/api/v1/admin/identity/security-policy")
    assert response.json() == {"system_admin_count": 2}


@pytest.mark.asyncio
async def test_object_routes_without_selection_keep_system_scope_and_lists_require_one(app, native):
    native.identity.role_assignments.return_value = [
        SimpleNamespace(
            user={"id": "x1", "name": "x1"},
            group=None,
            role={"id": "r", "name": "member"},
            scope={"project": {"id": "px"}},
        ),
    ]
    async with client(app) as http:
        members = await http.get("/api/v1/admin/projects/px/members")
        names = await http.get("/api/v1/admin/projects/names")
        users = await http.get("/api/v1/admin/users")
    assert [row["user_id"] for row in members.json()] == ["x1"]
    assert sorted(p["id"] for p in names.json()) == ["p1", "px"]
    assert users.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,path,body",
    [
        ("POST", "/api/v1/admin/roles/assign", {"user_id": "x1", "project_id": "px", "role_id": "foreign-role"}),
    ],
)
async def test_unselected_cross_domain_grants_are_anchored_to_target(app, native, monkeypatch, method, path, body):
    membership, assignment = AsyncMock(), AsyncMock()
    monkeypatch.setattr(identity_roles, "change_group_membership", membership)
    monkeypatch.setattr(identity_roles, "change_project_assignment", assignment)
    native.identity.get_role.side_effect = lambda i: {
        "global": SimpleNamespace(id="global", domain_id=None),
        "foreign-role": SimpleNamespace(id="foreign-role", domain_id="tenant-a"),
    }.get(i)
    async with client(app) as http:
        response = await http.request(method, path, json=body)
    assert response.status_code == 403
    assert response.json()["detail"] == "identity_domain_mismatch"
    membership.assert_not_called()
    assignment.assert_not_called()


@pytest.mark.asyncio
async def test_user_management_events_filter_by_subject_not_actor(monkeypatch):
    from sqlalchemy import Integer, MetaData
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.activity import ActivityLog

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    table = ActivityLog.__table__.to_metadata(MetaData())
    table.c.id.type = Integer()
    async with engine.begin() as connection:
        await connection.run_sync(table.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(activity, "is_db_available", lambda: True)
    monkeypatch.setattr(activity, "get_session_factory", lambda: factory)
    try:
        async with factory() as session:
            for actor, subject in [("foreign-admin", "u1"), ("u1", "x1")]:
                session.add(
                    ActivityLog(
                        project_id="admin",
                        user_id=actor,
                        username=actor,
                        resource_type="user",
                        resource_id=subject,
                        action="user.update",
                        status="success",
                    )
                )
            await session.commit()
        events = await activity.list_user_management_events(limit=10, user_ids=["u1", "u2"])
        assert [(e["user_id"], e["resource_id"]) for e in events] == [("foreign-admin", "u1")]
        assert await activity.list_user_management_events(limit=10, user_ids=[]) == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_group_member_listing_preserves_external_identity_read_only_boundary(app, native):
    native.identity.group_users.return_value = [obj("u1"), obj("x1", "tenant-b")]
    async with client(app) as http:
        response = await http.get("/api/v1/admin/groups/g1/users", params=DOMAIN)
    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == ["u1", "x1"]
    external = response.json()[1]
    assert external["domain_id"] == "tenant-b" and external["identity_read_only"]
    native.identity.group_users.assert_called_once_with("g1")
    native.identity.users.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["account", "personal"])
async def test_generic_admin_project_creation_rejects_reserved_native_kind(app, native, monkeypatch, kind):
    from app.services import keystone

    # SDK names need not retain metadata: inspect the exact extensible native row.
    domain = SimpleNamespace(id="tenant-a", name="opaque", enabled=True, afterglow_domain_kind=kind)
    monkeypatch.setattr(
        keystone, "_get_admin_ks_client", lambda: SimpleNamespace(domains=SimpleNamespace(get=lambda did: domain))
    )
    async with client(app) as http:
        response = await http.post("/api/v1/admin/projects", json={"name": "n", "domain_id": "tenant-a"})
    assert response.status_code == 403
    native.identity.create_project.assert_not_called()
