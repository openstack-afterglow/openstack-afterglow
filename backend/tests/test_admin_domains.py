"""Domain inventory, manager bootstrap and whole-domain monitoring boundaries.

Keystone/Nova/Cinder are isolated SDK-shaped fixtures; authorization dependencies,
domain/ownership filters and native error mapping are the real route code.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI, HTTPException

from app.api.deps import get_admin_os_conn, get_os_conn, get_token_info, require_admin
from app.api.identity import domains as domains_api
from app.services import (
    activity,
    domain_iam,
    domain_monitoring,
    domain_projects,
    identity_roles,
    login_monitoring,
    session_store,
    traffic_analytics,
)
from tests.admin_gate import synthetic_verified_admin
from tests.ownership_journal import ownership_journal as ownership_journal
from tests.test_domain_projects import domain_native as domain_native


class NativeError(Exception):
    def __init__(self, status):
        super().__init__("native-secret-detail")
        self.status_code = status


def domain(id, name=None, enabled=True):
    return SimpleNamespace(id=id, name=name or id, is_enabled=enabled, description="")


def member(id, domain_id):
    return SimpleNamespace(id=id, name=id, domain_id=domain_id, is_enabled=True)


@pytest.fixture
def native():
    conn = MagicMock()
    domains = {"tenant-a": domain("tenant-a", "Tenant A"), "tenant-b": domain("tenant-b")}
    conn.identity.get_domain.side_effect = lambda domain_id: domains.get(domain_id)
    conn.identity.domains.side_effect = lambda: iter(domains.values())
    # Providers can ignore a filter; route code must still prove domain_id.
    conn.identity.users.side_effect = lambda **_: iter([member("u-a", "tenant-a"), member("u-b", "tenant-b")])
    conn.identity.projects.side_effect = lambda **_: iter([member("p-a", "tenant-a"), member("p-b", "tenant-b")])
    users = {"u-a": member("u-a", "tenant-a"), "u-b": member("u-b", "tenant-b")}
    conn.identity.get_user.side_effect = lambda user_id: users.get(user_id)
    return conn


@pytest.fixture
def app(native, monkeypatch, domain_native, ownership_journal):
    info = {"user_id": "operator", "username": "operator", "project_id": "admin", "is_system_admin": True}
    application = FastAPI()
    application.include_router(domains_api.router, prefix="/api/v1/admin")
    application.dependency_overrides[get_os_conn] = lambda: native
    application.dependency_overrides[get_admin_os_conn] = lambda: native
    application.dependency_overrides[get_token_info] = lambda: info
    application.dependency_overrides[require_admin] = synthetic_verified_admin
    audits, revoked = [], []

    async def record(**kwargs):
        audits.append(kwargs)

    async def revoke(user_id, **_):
        revoked.append(user_id)
        return 1

    monkeypatch.setattr(activity, "record", record)
    monkeypatch.setattr(session_store, "revoke_user_sessions", revoke)
    application.state.audits, application.state.revoked, application.state.info = audits, revoked, info
    return application


def client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_every_domain_route_requires_verified_system_admin(app, native):
    app.state.info["is_system_admin"] = False
    async with client(app) as http:
        for method, path in [
            ("GET", "/api/v1/admin/domains"),
            ("POST", "/api/v1/admin/domains"),
            ("PATCH", "/api/v1/admin/domains/tenant-a"),
            ("GET", "/api/v1/admin/domains/tenant-a/monitoring"),
            ("GET", "/api/v1/admin/domains/tenant-a/members"),
            ("GET", "/api/v1/admin/domains/tenant-a/managers"),
            ("POST", "/api/v1/admin/domains/tenant-a/managers"),
            ("DELETE", "/api/v1/admin/domains/tenant-a/managers?user_id=u-a&role_id=r"),
            ("POST", "/api/v1/admin/domains/tenant-a/default"),
        ]:
            response = await http.request(method, path, json={"name": "x", "user_id": "u", "role_id": "r"})
            assert response.status_code == 403, path
    native.identity.create_domain.assert_not_called()
    native.identity.assign_domain_role_to_user.assert_not_called()


@pytest.mark.asyncio
async def test_membership_directory_tracks_joined_home_identity_without_credentials(app, domain_native):
    from tests.test_domain_projects import grant

    domain_native.user_rows["second"].email = "joined@example.test"
    domain_native.user_rows["second"].password = "not-public"
    joined = grant("project_reader", user="second", project="work-a")
    domain_native.raw.append(joined)
    async with client(app) as http:
        response = await http.get("/api/v1/admin/domains/tenant-a/members")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store, private"
        assert response.json()["domain_id"] == "tenant-a"
        users = {row["id"]: row for row in response.json()["items"]}
        assert set(users) == {"creator", "ordinary", "second"}
        assert users["second"]["domain_id"] == "home"
        assert set(users["second"]) == {"id", "name", "email", "enabled", "domain_id"}
        assert "not-public" not in response.text
        domain_native.raw.remove(joined)
        refreshed = await http.get("/api/v1/admin/domains/tenant-a/members")
        assert "second" not in {row["id"] for row in refreshed.json()["items"]}


@pytest.fixture
def candidate_directory(domain_native):
    from tests.test_domain_projects import grant

    home_id = "adfe08c4-f0ba-4735-a31b-14a2c48921a1"
    joined_id = "6a1c1b95-c3cf-41dc-8e6a-e1e67cacfd54"
    for uid, home in ((home_id, "tenant-a"), (joined_id, "home")):
        domain_native.user_rows[uid] = SimpleNamespace(
            id=uid, name="pieroot", email=f"{home}@example.test", enabled=True, domain_id=home
        )
    domain_native.raw.extend(
        [
            grant("project_reader", user=joined_id, project="work-a"),
            grant("reader", user="deleted-user", project="default-a"),
        ]
    )
    get_user = domain_native.users.get

    def exact_user(uid):
        if uid not in domain_native.user_rows:
            raise NativeError(404)
        return get_user(uid)

    domain_native.users.get = exact_user
    return SimpleNamespace(native=domain_native, home_id=home_id, joined_id=joined_id)


@pytest.mark.asyncio
async def test_candidate_directory_omits_confirmed_absent_user_not_valid_same_name_identities(app, candidate_directory):
    directory = candidate_directory
    async with client(app) as http:
        response = await http.get("/api/v1/admin/domains/tenant-a/members")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, private"
    users = {item["id"]: item for item in response.json()["items"]}
    assert set(users) == {"creator", "ordinary", directory.home_id, directory.joined_id}
    for uid, home in ((directory.home_id, "tenant-a"), (directory.joined_id, "home")):
        assert users[uid] == {
            "id": uid,
            "name": "pieroot",
            "email": f"{home}@example.test",
            "enabled": True,
            "domain_id": home,
        }
    assert not any(call[0] == "users.list" and call[2] is None for call in directory.native.read_calls)
    assert not directory.native.calls


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "status"),
    [
        ("user_denied", 403),
        ("user_unavailable", 503),
        ("home_absent", 404),
        ("user_mismatch", 503),
        ("home_unknown", 503),
        ("graph_malformed", 503),
        ("graph_absent", 404),
    ],
)
async def test_candidate_directory_preserves_provider_and_native_graph_failures(
    app, candidate_directory, failure, status
):
    from tests.test_domain_projects import grant

    directory = candidate_directory.native
    joined_id = candidate_directory.joined_id
    get_user = directory.users.get
    get_domain = directory.domains.get

    if failure in {"user_denied", "user_unavailable"}:

        def unavailable_user(uid):
            if uid == joined_id:
                raise NativeError(403 if failure == "user_denied" else 503)
            return get_user(uid)

        directory.users.get = unavailable_user
    elif failure == "home_absent":

        def absent_home(did):
            if did == "home":
                raise NativeError(404)
            return get_domain(did)

        directory.domains.get = absent_home
    elif failure == "user_mismatch":
        directory.users.get = lambda uid: get_user("ordinary" if uid == joined_id else uid)
    elif failure == "home_unknown":
        directory.user_rows[joined_id].domain_id = None
    elif failure == "graph_malformed":
        directory.raw.append(grant("unknown-role", user="deleted-user", project="default-a"))
    else:

        def absent_graph(**kwargs):
            raise NativeError(404)

        directory.role_assignments.list = absent_graph
    async with client(app) as http:
        response = await http.get("/api/v1/admin/domains/tenant-a/members")
    assert response.status_code == status
    assert "items" not in response.json()
    assert "native-secret-detail" not in response.text
    assert not directory.calls


@pytest.mark.asyncio
async def test_candidate_directory_omits_deleted_home_list_result_only_after_exact_404(app, domain_native):
    get_user = domain_native.users.get

    def deleted_after_list(uid):
        if uid == "ordinary":
            raise NativeError(404)
        return get_user(uid)

    domain_native.users.get = deleted_after_list
    async with client(app) as http:
        response = await http.get("/api/v1/admin/domains/tenant-a/members")
    assert response.status_code == 200
    assert {item["id"] for item in response.json()["items"]} == {"creator"}


@pytest.mark.asyncio
@pytest.mark.parametrize("disabled", ["home_user", "joined_user", "joined_home_domain"])
async def test_candidate_directory_missing_user_tolerance_does_not_include_disabled_identities(
    app, candidate_directory, disabled
):
    directory = candidate_directory
    expected = {"creator", "ordinary", directory.home_id, directory.joined_id}
    if disabled == "home_user":
        directory.native.user_rows[directory.home_id].enabled = False
        expected.remove(directory.home_id)
    elif disabled == "joined_user":
        directory.native.user_rows[directory.joined_id].enabled = False
        expected.remove(directory.joined_id)
    else:
        directory.native.domain_rows["home"].enabled = False
        expected.difference_update({"creator", directory.joined_id})
    async with client(app) as http:
        response = await http.get("/api/v1/admin/domains/tenant-a/members")
    assert response.status_code == 200
    assert {item["id"] for item in response.json()["items"]} == expected


@pytest.mark.asyncio
async def test_candidate_directory_tolerance_never_grants_missing_identity_authority(candidate_directory):
    from tests.test_domain_projects import grant

    directory = candidate_directory.native
    for read in (
        domain_iam.directory_users("tenant-a", ks=directory),
        domain_iam.assert_joined_user("tenant-a", "deleted-user", ks=directory),
    ):
        with pytest.raises(HTTPException) as missing:
            await read
        assert missing.value.status_code == 404
    directory.group_rows["team"] = SimpleNamespace(id="team", name="team", domain_id="tenant-a", description="")
    writes = []
    conn = SimpleNamespace(identity=SimpleNamespace(add_user_to_group=lambda *args: writes.append(args)))
    with pytest.raises(HTTPException) as missing:
        await identity_roles.change_group_membership(
            conn, {"user_id": "operator", "domain_id": "tenant-a"}, "team", user_id="deleted-user"
        )
    assert missing.value.status_code == 404
    directory.raw.append(grant("manager", user="deleted-user", project="default-a"))
    with pytest.raises(HTTPException) as unknown_manager:
        domain_projects.has_manager("creator", "tenant-a", ks=directory)
    assert unknown_manager.value.status_code == 404
    assert not writes and not directory.calls


@pytest.mark.asyncio
async def test_domain_create_update_and_native_conflict(app, native, domain_native):
    async with client(app) as http:
        created = await http.post("/api/v1/admin/domains", json={"name": " Lab ", "enabled": False})
        updated = await http.patch("/api/v1/admin/domains/tenant-a", json={"enabled": True})
        empty = await http.patch("/api/v1/admin/domains/tenant-a", json={})
        missing = await http.patch("/api/v1/admin/domains/absent", json={"name": "x"})
        domain_native.domains.create = lambda **_: (_ for _ in ()).throw(NativeError(409))
        conflict = await http.post("/api/v1/admin/domains", json={"name": "Lab"})
    assert created.status_code == 201
    assert created.json() == {
        "id": "created-domain",
        "name": "Lab",
        "kind": "organization",
        "enabled": False,
        "description": "",
        "default_project_id": "created-default",
    }
    assert domain_projects.default_project("created-domain")["id"] == "created-default"
    assert updated.json()["enabled"] is True
    assert domain_native.domain_rows["tenant-a"].enabled is True
    assert empty.status_code == 422
    assert missing.status_code == 404
    assert conflict.status_code == 409 and "native-secret-detail" not in conflict.text
    assert [audit["action"] for audit in app.state.audits] == ["domain.create", "domain.update"]
    assert all(audit["project_id"] == "" and audit["extra"]["domain_id"] for audit in app.state.audits)


@pytest.mark.asyncio
async def test_manager_list_resolves_effective_Default_authority_including_external_accounts(app, domain_native):
    from tests.test_domain_projects import grant, row

    domain_native.group_rows["external"] = row(id="external", name="Team", domain_id="home", description="")
    domain_native.members["external"] = {"second"}
    domain_native.raw.append(grant("alias", group="external", project="default-a"))
    domain_native.raw.append(grant("admin", user="ordinary", domain="tenant-a"))
    async with client(app) as http:
        response = await http.get("/api/v1/admin/domains/tenant-a/managers")
    assert response.status_code == 200
    data = response.json()
    assert data["default_project_id"] == "default-a"
    assert data["roles"] == [{"id": "manager", "name": "manager", "grantable": True}]
    assert [(i["user_id"], i["user_domain_id"], i["direct"]) for i in data["items"]] == [
        ("creator", "home", True),
        ("second", "home", False),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["admin", "reader", "alias", "missing"])
async def test_manager_route_grants_only_canonical_manager(app, native, domain_native, role):
    from tests.test_domain_projects import grant

    domain_native.raw.append(grant("project_reader", user="other", project="default-a"))
    async with client(app) as http:
        response = await http.post(
            "/api/v1/admin/domains/tenant-a/managers", json={"user_id": "other", "role_id": role}
        )
    assert response.status_code == 422
    assert domain_native.calls == []
    native.identity.assign_domain_role_to_user.assert_not_called()


@pytest.mark.asyncio
async def test_manager_grant_and_revoke_use_Default_project_and_protect_last_manager(app, native, domain_native):
    from tests.test_domain_projects import grant

    domain_native.raw.append(grant("project_reader", user="other", project="default-a"))
    async with client(app) as http:
        last = await http.delete(
            "/api/v1/admin/domains/tenant-a/managers", params={"user_id": "creator", "role_id": "manager"}
        )
        granted = await http.post(
            "/api/v1/admin/domains/tenant-a/managers", json={"user_id": "other", "role_id": "manager"}
        )
        revoked = await http.delete(
            "/api/v1/admin/domains/tenant-a/managers", params={"user_id": "creator", "role_id": "manager"}
        )
        absent = await http.delete(
            "/api/v1/admin/domains/tenant-a/managers", params={"user_id": "creator", "role_id": "manager"}
        )
    assert last.status_code == 409
    assert granted.status_code == 201 and revoked.status_code == 204 and absent.status_code == 404
    assert ("grant", "manager", "other", None, "default-a", None, False) in domain_native.calls
    assert ("revoke", "manager", "creator", "default-a") in domain_native.calls
    assert domain_native.members["projection-tenant-a"] == {"other"}
    native.identity.assign_domain_role_to_user.assert_not_called()
    native.identity.unassign_domain_role_from_user.assert_not_called()
    assert [audit["action"] for audit in app.state.audits] == ["domain.manager.grant", "domain.manager.revoke"]


@pytest.mark.asyncio
async def test_manager_grant_cannot_admit_an_outsider(app, native, domain_native):
    async with client(app) as http:
        response = await http.post(
            "/api/v1/admin/domains/tenant-a/managers", json={"user_id": "other", "role_id": "manager"}
        )
    assert response.status_code == 403
    assert response.json()["detail"] == "domain_membership_denied"
    assert domain_native.calls == []
    assert not domain_projects.has_manager("other", "tenant-a")
    assert domain_native.user_rows["other"].domain_id == "tenant-b"
    native.identity.assign_domain_role_to_user.assert_not_called()


@pytest.mark.asyncio
async def test_existing_domain_Default_requires_explicit_system_admin_bootstrap(app, domain_native):
    del domain_native.project_rows["default-b"]
    async with client(app) as http:
        before = await http.get("/api/v1/admin/domains/tenant-b/managers")
        refusal = await http.post(
            "/api/v1/admin/domains/tenant-b/managers", json={"user_id": "other", "role_id": "manager"}
        )
        bootstrap = await http.post("/api/v1/admin/domains/tenant-b/default", json={"creator_id": "creator"})
    assert before.json()["default_project_id"] is None and before.json()["items"] == []
    assert refusal.status_code == 409
    assert bootstrap.status_code == 201 and bootstrap.json()["creator_id"] == "creator"
    assert domain_projects.has_manager("creator", "tenant-b")
    assert not domain_projects.has_manager("other", "tenant-b")
    assert [audit["action"] for audit in app.state.audits] == ["domain.default.bootstrap"]


@pytest.mark.asyncio
async def test_ambiguous_canonical_manager_role_fails_closed(app, native, domain_native):
    from tests.test_domain_projects import row

    domain_native.role_rows.append(row(id="manager-2", name="Manager", domain_id=None))
    async with client(app) as http:
        response = await http.post(
            "/api/v1/admin/domains/tenant-a/managers", json={"user_id": "ordinary", "role_id": "manager"}
        )
    assert response.status_code == 503
    assert domain_native.calls == []
    native.identity.assign_domain_role_to_user.assert_not_called()


@pytest.fixture
def monitoring(native, monkeypatch):
    settings = SimpleNamespace(
        **{f"service_{gate}_enabled": False for _, gate in domain_monitoring.user_inventory.CATALOG.values() if gate}
    )
    monkeypatch.setattr(domain_monitoring, "get_settings", lambda: settings)
    monkeypatch.setattr(
        domain_monitoring.domain_iam, "directory_users", AsyncMock(return_value=[member("u-a", "tenant-a")])
    )
    native.compute.servers.return_value = [
        SimpleNamespace(id="s-a", project_id="p-a", flavor={"vcpus": 2, "ram": 1024}),
        SimpleNamespace(id="s-b", project_id="p-b", flavor={"vcpus": 64, "ram": 999999}),
    ]
    native.block_storage.volumes.return_value = [
        SimpleNamespace(id="v-a", project_id="p-a", size=10),
        SimpleNamespace(id="v-b", project_id="p-b", size=500),
    ]
    native.block_storage.snapshots.return_value = []
    # A pre-3.18 backup listing without owners cannot be attributed.
    native.block_storage.backups.return_value = [SimpleNamespace(id="b-x", project_id=None)]
    for method in ("ips", "networks", "subnets", "routers", "security_groups"):
        getattr(native.network, method).return_value = []
    native.load_balancer.load_balancers.return_value = []
    native.image.images.return_value = [
        SimpleNamespace(id="i-a", owner="p-a"),
        SimpleNamespace(id="i-b", owner="p-b"),
        SimpleNamespace(id="i-unowned", owner=None),
    ]
    native.compute.get_quota_set.side_effect = lambda project_id: SimpleNamespace(instances=10, cores=-1, ram=2048)
    native.block_storage.get_quota_set.side_effect = NativeError(403)
    observed = {}

    async def requests(domain_id, window):
        observed["requests"] = (domain_id, window)
        return {"state": "partial", "window": window, "total": 3, "errors": 1, "services": [], "timeline": []}

    async def observation(domain_id, user_ids, project_ids, window):
        observed["observation"] = (domain_id, user_ids, project_ids, window)
        unknown = {"state": "partial"}
        return {
            "logins": {**unknown, "successes": None},
            "activity": {**unknown, "events": None},
            "sessions": {**unknown, "valid_count": None, "online_count": None},
            "notes": ["sessions_are_not_online_presence"],
        }

    monkeypatch.setattr(traffic_analytics, "domain_snapshot", requests)
    monkeypatch.setattr(login_monitoring, "domain_observation", observation)
    return observed


def metric(payload, name):
    return next(row for row in payload["resources"] if row["metric"] == name)


@pytest.mark.asyncio
async def test_monitoring_counts_only_authoritative_domain_projects_and_reports_gaps(app, native, monitoring):
    async with client(app) as http:
        response = await http.get("/api/v1/admin/domains/tenant-a/monitoring?window=7d")
    assert response.status_code == 200
    data = response.json()
    assert data["domain"] == {"id": "tenant-a", "name": "Tenant A", "enabled": True}
    assert data["directory"] == {"users": 1, "projects": 1}
    assert monitoring["observation"] == ("tenant-a", {"u-a"}, {"p-a"}, "7d")
    assert monitoring["requests"] == ("tenant-a", "7d")
    assert metric(data, "instances") == {**metric(data, "instances"), "value": 1, "status": "ready", "kind": "count"}
    assert metric(data, "vcpus")["value"] == 2 and metric(data, "vcpus")["kind"] == "utilization"
    assert metric(data, "ram_mb")["value"] == 1024
    assert metric(data, "volume_gb")["value"] == 10
    # One ownerless image elsewhere makes the domain count a visible lower bound.
    assert metric(data, "images") == {
        **metric(data, "images"),
        "value": 1,
        "status": "partial",
        "error": "owner_unavailable",
    }
    native.image.images.assert_called_once_with(visibility="all")
    assert metric(data, "networks") == {**metric(data, "networks"), "value": 0, "status": "ready"}
    # Missing ownership, unsupported APIs and disabled services are never zero.
    assert metric(data, "volume_backups")["value"] is None
    assert metric(data, "volume_backups")["error"] == "owner_unavailable"
    assert metric(data, "keypairs")["error"] == "domain_aggregate_unsupported"
    assert metric(data, "containers")["status"] == "disabled"
    assert metric(data, "quota_instances") == {**metric(data, "quota_instances"), "value": 10, "kind": "allocation"}
    assert metric(data, "quota_cores")["status"] == "unlimited" and metric(data, "quota_cores")["value"] is None
    assert metric(data, "quota_gigabytes")["status"] == "denied" and metric(data, "quota_gigabytes")["value"] is None
    assert data["sessions"]["online_count"] is None
    assert data["coverage"]["partial"] is True and data["coverage"]["window"] == "7d"
    assert "native-secret-detail" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("status,expected", [(403, 403), (404, 404), (500, 503)])
async def test_monitoring_directory_failure_is_not_an_empty_domain(app, native, monitoring, status, expected):
    native.identity.users.side_effect = NativeError(status)
    async with client(app) as http:
        response = await http.get("/api/v1/admin/domains/tenant-a/monitoring")
    assert response.status_code == expected
    assert "requests" not in monitoring and "native-secret-detail" not in response.text


@pytest.mark.asyncio
async def test_monitoring_unknown_domain_and_window(app, native, monitoring):
    async with client(app) as http:
        missing = await http.get("/api/v1/admin/domains/absent/monitoring")
        window = await http.get("/api/v1/admin/domains/tenant-a/monitoring?window=1y")
    assert missing.status_code == 404
    assert window.status_code == 422


@pytest.mark.parametrize(
    "template,service",
    [
        ("/api/v1/file-storage/{share_id}", "manila"),
        ("/api/v1/database-instances", "trove"),
        ("/api/v1/secret-containers/{id}", "barbican"),
        ("/api/v1/secret-orders", "barbican"),
        ("/api/v1/volumes/backups/{backup_id}", "cinder"),
        ("/api/v1/k3s/clusters/{id}", "drover"),
        ("/api/v1/chat/{path:path}", "lumen"),
        ("/api/v1/admin/projects/{project_id}", "afterglow"),
        ("/api/v1/admin/palimpsest/builds", "afterglow"),
        (None, "afterglow"),
    ],
)
def test_request_service_labels_follow_mounted_prefixes(template, service):
    assert traffic_analytics.domain_service(template) == service


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "admins,status",
    [({"u-a": "tenant-a"}, 422), ({"u-a": "tenant-a", "root": "tenant-b"}, 200), (None, 503)],
)
async def test_disabling_domain_of_last_system_admins_is_refused(
    app, native, monkeypatch, admins, status, domain_native
):
    import fakeredis.aioredis

    from app.services import keystone

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

    async def get_redis():
        return redis

    monkeypatch.setattr(session_store, "_get_redis", get_redis)
    native.endpoint_for.return_value = "https://keystone.invalid/v3"
    monkeypatch.setattr(keystone, "_resolve_admin_role_id", lambda: "admin")

    if admins is not None:
        for uid, did in admins.items():
            domain_native.user_rows[uid] = SimpleNamespace(id=uid, enabled=True, domain_id=did)
            domain_native.raw.append(
                SimpleNamespace(user={"id": uid}, role={"id": "admin"}, scope={"system": {"all": True}})
            )

    def ks():
        if admins is None:
            raise RuntimeError("keystone unavailable")
        return domain_native

    monkeypatch.setattr(keystone, "_get_admin_ks_client", ks)
    # This test isolates the system-admin guard; manager simulations have their
    # own native-state tests above and in test_domain_projects.
    monkeypatch.setattr(domain_projects, "assert_managers_remain", lambda **_: set())
    async with client(app) as http:
        response = await http.patch("/api/v1/admin/domains/tenant-a", json={"enabled": False})
    assert response.status_code == status
    assert domain_native.domain_rows["tenant-a"].enabled is (status != 200)
    await redis.close()
