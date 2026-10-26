"""Selected-domain administrator identity boundaries through the real admin router.

Keystone is an SDK-shaped fixture that deliberately ignores domain filters so
the route's own exact domain proof is exercised before pagination or mutation.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import Depends, FastAPI
from sqlalchemy import event

from app.api.deps import get_admin_os_conn, get_os_conn, get_token_info, require_admin
from app.api.identity import admin_identity
from app.database import get_session
from app.services import activity, domain_scope, identity_roles, keystone, session_store
from app.services.native_operation import NativeOperation
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
    info = {
        "token": "personal-member-token",
        "user_id": "operator",
        "username": "operator",
        "project_id": "personal-project",
        "connection_project_id": "personal-project",
        "domain_id": "personal",
        "domain_name": "Personal",
        "identity_domain_id": "accounts",
        "roles": ["member"],
        "is_system_admin": True,
    }
    native.session.auth.get_access.return_value = SimpleNamespace(
        project_id="configured-executor-project",
        auth_token="executor-admin-token",
        project_scoped=True,
        system_scoped=False,
        is_admin_project=True,
        role_names=["admin"],
        _data={"token": {}},
    )
    monkeypatch.setattr(keystone, "get_admin_project_connection", MagicMock(return_value=native))

    def personal_member_transport():
        raise AssertionError("Administrator directory must not resolve the caller's member transport")

    async def executor(_admin=Depends(require_admin)):
        yield native

    application = FastAPI()
    application.include_router(admin_identity.router, prefix="/api/v1/admin")
    application.dependency_overrides[get_os_conn] = personal_member_transport
    application.dependency_overrides[get_admin_os_conn] = executor
    application.dependency_overrides[get_token_info] = lambda: info
    application.dependency_overrides[require_admin] = synthetic_verified_admin
    application.state.actor = info
    monkeypatch.setattr(activity, "get_user_activity_bounds", AsyncMock(return_value={}))
    monkeypatch.setattr(activity, "get_resource_creation_times", AsyncMock(return_value={}))
    monkeypatch.setattr(activity, "record", AsyncMock())
    return application


@pytest.fixture
def executor_boundary(app, native, monkeypatch):
    """Exercise real authorization and executor dependencies, stubbing native I/O only."""
    app.dependency_overrides.pop(require_admin)
    app.dependency_overrides.pop(get_admin_os_conn)
    actor = app.state.actor
    monkeypatch.setattr(
        domain_scope,
        "domain_context",
        MagicMock(
            return_value={
                "domain_id": "personal",
                "domain_name": "Personal",
                "identity_domain_id": "accounts",
                "identity_domain_name": "Accounts",
                "is_domain_manager": False,
            }
        ),
    )
    monkeypatch.setattr(domain_scope, "assert_project_domain", MagicMock())
    monkeypatch.setattr(
        keystone,
        "validate_token",
        MagicMock(
            return_value={
                "user_id": "operator",
                "project_id": "personal-project",
                "domain_id": "personal",
                "identity_domain_id": "accounts",
                "roles": ["member"],
            }
        ),
    )
    monkeypatch.setattr(keystone, "_is_system_admin", MagicMock(return_value=True))
    monkeypatch.setattr(activity, "list_user_management_events", AsyncMock(return_value=[]))
    monkeypatch.setattr(session_store, "list_user_sessions", AsyncMock(return_value=[]))
    native.identity.roles.side_effect = lambda: iter(
        [{"id": "global", "name": "member", "domain_id": None, "description": ""}]
    )
    native.identity.get.return_value.json.return_value = {"role_inferences": []}
    native.identity.role_assignments.side_effect = lambda **kwargs: iter(())
    native.identity.group_users.side_effect = lambda group_id: iter(())
    return app, actor


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
@pytest.mark.parametrize("status", [403, 404, 503])
@pytest.mark.parametrize("partial", [False, True])
async def test_group_member_listing_provider_failure_never_returns_empty_or_partial_success(
    app, native, status, partial
):
    def members(group_id):
        if partial:
            yield obj("u1")
        raise NativeError(status)

    native.identity.group_users.side_effect = members
    async with client(app) as http:
        response = await http.get("/api/v1/admin/groups/g1/users", params=DOMAIN)
    assert response.status_code == status
    assert "detail" in response.json()
    assert "native-secret-detail" not in response.text
    native.identity.users.assert_not_called()


@pytest.mark.asyncio
async def test_group_member_listing_preserves_same_name_uuid_email_and_home_domain(app, native):
    home_id = "adfe08c4-f0ba-4735-a31b-14a2c48921a1"
    external_id = "6a1c1b95-c3cf-41dc-8e6a-e1e67cacfd54"
    members = [obj(home_id), obj(external_id, "tenant-b")]
    for user in members:
        user.name = "pieroot"
        user.email = f"{user.domain_id}@example.test"
    native.identity.group_users.return_value = members
    async with client(app) as http:
        response = await http.get("/api/v1/admin/groups/g1/users", params=DOMAIN)
    assert response.status_code == 200
    assert response.json() == [
        {
            "id": uid,
            "name": "pieroot",
            "email": f"{home}@example.test",
            "domain_id": home,
            "identity_read_only": read_only,
            "enabled": True,
        }
        for uid, home, read_only in ((home_id, "tenant-a", False), (external_id, "tenant-b", True))
    ]


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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/users",
        "/users/stats",
        "/users/activity",
        "/users/u1/sessions",
        "/users/u1/permissions",
        "/projects",
        "/projects/names",
        "/projects/p1",
        "/projects/p1/members",
        "/groups",
        "/groups/g1/users",
        "/roles",
    ],
)
async def test_personal_member_admin_reads_use_independent_verified_executor(executor_boundary, native, path):
    app, actor = executor_boundary
    async with client(app) as http:
        response = await http.get("/api/v1/admin" + path, params=DOMAIN)
    assert response.status_code == 200, response.text
    operation = keystone.validate_token.call_args.kwargs["operation"]
    assert isinstance(operation, NativeOperation)
    keystone.validate_token.assert_called_once_with(
        "personal-member-token", project_id="personal-project", operation=operation
    )
    keystone._is_system_admin.assert_called_once_with("operator", operation=operation)
    assert domain_scope.domain_context.call_args.kwargs["operation"] is operation
    assert operation.reads == {} and operation.subjects == {}
    keystone.get_admin_project_connection.assert_called_once_with()
    native.close.assert_called_once_with()
    assert actor["roles"] == ["member"]
    assert actor["connection_project_id"] == "personal-project"
    assert native._afterglow_token == "executor-admin-token"
    assert native._afterglow_authenticated_project_id == "configured-executor-project"
    assert native._afterglow_project_id == "personal-project"
    assert native._afterglow_user_id == "operator"


@pytest.mark.asyncio
@pytest.mark.parametrize("claimed_admin,fresh_admin", [(False, True), (True, False)])
@pytest.mark.parametrize("path", ["/users", "/projects/p1", "/groups/g1/users", "/roles"])
async def test_unverified_admin_never_acquires_executor(executor_boundary, native, path, claimed_admin, fresh_admin):
    app, actor = executor_boundary
    actor["is_system_admin"] = claimed_admin
    keystone._is_system_admin.return_value = fresh_admin
    async with client(app) as http:
        response = await http.get("/api/v1/admin" + path, params=DOMAIN)
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "system_admin_required"
    keystone.get_admin_project_connection.assert_not_called()
    native.identity.get_domain.assert_not_called()
    native.identity.users.assert_not_called()
    native.identity.get_project.assert_not_called()
    native.identity.group_users.assert_not_called()
    native.identity.roles.assert_not_called()
    native.close.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path,domain,status,detail",
    [
        ("/users", "absent", 404, "identity_domain_not_found"),
        ("/users/x1/sessions", "tenant-a", 403, "identity_domain_mismatch"),
        ("/users/absent/sessions", "tenant-a", 404, "identity_not_found"),
        ("/projects/px", "tenant-a", 403, "identity_domain_mismatch"),
        ("/projects/absent", "tenant-a", 404, "identity_not_found"),
        ("/groups/gx/users", "tenant-a", 403, "identity_domain_mismatch"),
        ("/groups/absent/users", "tenant-a", 404, "identity_not_found"),
    ],
)
async def test_verified_executor_preserves_selected_domain_and_object_rejections(
    executor_boundary, native, path, domain, status, detail
):
    app, _ = executor_boundary
    async with client(app) as http:
        response = await http.get("/api/v1/admin" + path, params={"domain_id": domain})
    assert response.status_code == status
    assert response.json()["detail"] == detail
    keystone.get_admin_project_connection.assert_called_once_with()
    native.close.assert_called_once_with()
    native.identity.users.assert_not_called()
    native.identity.group_users.assert_not_called()
    session_store.list_user_sessions.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind,path",
    [("user", "/users/u1/sessions"), ("project", "/projects/p1"), ("group", "/groups/g1/users")],
)
async def test_executor_rejects_native_object_id_substitution(executor_boundary, native, kind, path):
    app, _ = executor_boundary
    getattr(native.identity, f"get_{kind}").side_effect = lambda _: obj("different-native-id")
    async with client(app) as http:
        response = await http.get("/api/v1/admin" + path, params=DOMAIN)
    assert response.status_code == 503
    assert response.json()["detail"] == "identity_object_unverified"
    native.close.assert_called_once_with()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value", [("project_scoped", False), ("role_names", ["member"]), ("is_admin_project", False)]
)
async def test_invalid_executor_native_scope_prevents_directory_access(executor_boundary, native, field, value):
    app, _ = executor_boundary
    setattr(native.session.auth.get_access.return_value, field, value)
    async with client(app) as http:
        response = await http.get("/api/v1/admin/users", params=DOMAIN)
    assert response.status_code == 503
    assert response.json()["detail"] == "Native administrator project scope is invalid"
    native.identity.get_domain.assert_not_called()
    native.identity.users.assert_not_called()
    native.close.assert_called_once_with()


@pytest.mark.asyncio
async def test_admin_creation_and_profile_update_use_executor_without_elevating_caller(executor_boundary, native):
    app, actor = executor_boundary
    native.identity.create_group.side_effect = lambda **kwargs: obj("created-group", kwargs["domain_id"])
    native.identity.update_user.side_effect = lambda user_id, **kwargs: obj(user_id)
    async with client(app) as http:
        created = await http.post("/api/v1/admin/groups", json={"name": "team", "domain_id": "tenant-a"})
        updated = await http.patch("/api/v1/admin/users/u1", params=DOMAIN, json={"name": "renamed"})
    assert created.status_code == 201
    assert updated.status_code == 200
    native.identity.create_group.assert_called_once_with(name="team", domain_id="tenant-a")
    native.identity.update_user.assert_called_once_with("u1", name="renamed")
    assert keystone.get_admin_project_connection.call_count == 2
    assert native.close.call_count == 2
    assert actor["roles"] == ["member"]
    assert actor["project_id"] == "personal-project"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,path,body,service,args,kwargs",
    [
        ("PUT", "/groups/g1/users/x1", None, "change_group_membership", ("g1",), {"user_id": "x1"}),
        (
            "DELETE",
            "/groups/g1/users/x1",
            None,
            "change_group_membership",
            ("g1",),
            {"user_id": "x1", "remove": True},
        ),
        (
            "POST",
            "/roles/assign",
            {"project_id": "p1", "user_id": "x1", "role_id": "global"},
            "change_project_assignment",
            ("p1", "global"),
            {"user_id": "x1"},
        ),
        (
            "POST",
            "/roles/assign-group",
            {"project_id": "p1", "group_id": "gx", "role_id": "global"},
            "change_project_assignment",
            ("p1", "global"),
            {"group_id": "gx"},
        ),
    ],
)
async def test_cross_identity_membership_writes_use_executor_and_target_domain_anchor(
    executor_boundary, native, monkeypatch, method, path, body, service, args, kwargs
):
    app, actor = executor_boundary
    change = AsyncMock(return_value={"status": "assigned"})
    monkeypatch.setattr(identity_roles, service, change)
    async with client(app) as http:
        response = await http.request(method, "/api/v1/admin" + path, params=DOMAIN, json=body)
    assert response.status_code == (204 if path.startswith("/groups/") else 200), response.text
    change.assert_awaited_once_with(native, actor, *args, **kwargs)
    keystone.get_admin_project_connection.assert_called_once_with()
    native.close.assert_called_once_with()
    assert native._afterglow_authenticated_project_id == "configured-executor-project"
    assert actor["roles"] == ["member"]


@pytest.mark.asyncio
async def test_selected_project_quota_uses_same_verified_executor_for_boundary_and_read(
    executor_boundary, native, monkeypatch
):
    app, _ = executor_boundary
    read = AsyncMock(return_value={"project_id": "p1"})
    monkeypatch.setattr(admin_identity.quota_native, "read_project", read)
    async with client(app) as http:
        response = await http.get("/api/v1/admin/quotas/p1", params=DOMAIN)
    assert response.status_code == 200
    read.assert_awaited_once_with(native, "p1")
    native.identity.get_project.assert_called_once_with("p1")
    keystone.get_admin_project_connection.assert_called_once_with()
    native.close.assert_called_once_with()


@pytest.mark.asyncio
async def test_executor_rejects_unowned_selected_project_before_quota_read(executor_boundary, native, monkeypatch):
    app, _ = executor_boundary
    native.identity.get_project.side_effect = lambda project_id: obj(project_id, domain_id=None)
    read = AsyncMock()
    monkeypatch.setattr(admin_identity.quota_native, "read_project", read)
    async with client(app) as http:
        response = await http.get("/api/v1/admin/quotas/p1", params=DOMAIN)
    assert response.status_code == 403
    assert response.json()["detail"] == "identity_domain_mismatch"
    read.assert_not_called()
    native.close.assert_called_once_with()
