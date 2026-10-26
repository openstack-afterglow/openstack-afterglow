"""Explicit group admission through the real HTTP router, graph lease and native guards.

Only Keystone/token I/O and the isolated Redis transport are synthetic. Membership,
source-home proof, current system authority, audit and invalidation run production code.
"""

from copy import deepcopy
from types import SimpleNamespace

import fakeredis.aioredis
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_admin_os_conn, get_token_info
from app.api.identity.admin_identity import router
from app.services import cache, domain_projects, identity_roles, keystone, session_store
from app.services.cache.redis_backend import RedisBackend
from tests.test_identity_roles import IdentityProvider


class NativeError(Exception):
    def __init__(self, status):
        self.status_code = status
        super().__init__("private-native-detail")


class GroupDirectory(IdentityProvider):
    def __init__(self):
        super().__init__()
        self.domains = {
            did: SimpleNamespace(id=did, name=name, enabled=True)
            for did, name in (("organization", "Organization"), ("accounts", "Accounts"), ("other-home", "Other"))
        }
        self.users = {
            uid: SimpleNamespace(id=uid, name="same-name", email=email, enabled=True, domain_id=home)
            for uid, home, email in (
                ("operator", "organization", "operator@example.test"),
                ("account-uuid-full", "accounts", "account@example.test"),
                ("other-uuid-full", "other-home", "other@example.test"),
            )
        }
        self.projects = {
            "work": SimpleNamespace(id="work", name="Work", domain_id="organization", enabled=True),
            "foreign": SimpleNamespace(id="foreign", name="Foreign", domain_id="other-home", enabled=True),
        }
        self.groups = {"team": set()}
        self.group = SimpleNamespace(id="team", name="Team", description="", domain_id="organization")
        self.assignments = [{"user": {"id": "operator"}, "role": {"id": "admin"}, "scope": {"system": {"all": True}}}]
        self.writes = []
        self.reads = []
        self.failures = {}
        self.list_extra = []

    def exact(self, kind, object_id, rows):
        self.reads.append((kind, object_id))
        failure = self.failures.get((kind, object_id))
        if failure:
            raise NativeError(failure)
        if object_id not in rows:
            raise NativeError(404)
        return rows[object_id]

    def get_domain(self, did):
        return self.exact("domain", did, self.domains)

    def get_user(self, uid):
        return self.exact("user", uid, self.users)

    def get_group(self, gid):
        return self.exact("group", gid, {"team": self.group})

    def get_project(self, pid):
        return self.exact("project", pid, self.projects)

    def list_users(self, *, domain=None, group=None):
        self.reads.append(("users", domain, group))
        if self.failures.get(("users", domain)):
            yield self.users["account-uuid-full"]
            raise NativeError(self.failures[("users", domain)])
        if group is not None:
            yield from (self.users[uid] for uid in self.groups[group])
        else:
            yield from (user for user in self.users.values() if user.domain_id == domain)
            yield from self.list_extra

    def list_groups(self, *, user=None, domain=None):
        return [self.group] if (user in self.groups["team"] if user else domain == self.group.domain_id) else []

    def role_assignments(self, *args, **query):
        rows = list(super().role_assignments(*args, **query))
        if query.get("effective"):
            rows = [row for row in rows if "system" not in row["scope"]]
        if "system" in query:
            rows = [row for row in rows if row["scope"] == {"system": {"all": True}}]
        return iter(rows)

    def add_user_to_group(self, uid, gid):
        self.writes.append(("add", uid, gid))
        self.groups[gid].add(uid)

    def grant(self, *, project=None, domain=None, role="reader", inherited=False):
        scope = {"project" if project else "domain": {"id": project or domain}}
        if inherited:
            scope["OS-INHERIT:inherited_to"] = "projects"
        self.assignments.append({"group": {"id": "team"}, "role": {"id": role}, "scope": scope})


@pytest.fixture
async def group_home(monkeypatch):
    directory = GroupDirectory()
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    native = SimpleNamespace(
        users=SimpleNamespace(get=directory.get_user, list=directory.list_users),
        domains=SimpleNamespace(get=directory.get_domain, list=lambda: list(directory.domains.values())),
        groups=SimpleNamespace(get=directory.get_group, list=directory.list_groups),
        projects=SimpleNamespace(
            get=directory.get_project,
            list=lambda **query: [p for p in directory.projects.values() if p.domain_id == query.get("domain")],
        ),
        roles=SimpleNamespace(list=directory.roles),
        inference_rules=SimpleNamespace(
            list_inference_roles=lambda: directory.get("/role_inferences").json()["role_inferences"]
        ),
        role_assignments=SimpleNamespace(list=directory.native_assignments),
    )
    monkeypatch.setattr(keystone, "_get_admin_ks_client", lambda: native)
    monkeypatch.setattr(cache, "_backend", RedisBackend(client=redis))

    async def get_redis():
        return redis

    events = []

    async def record(**kwargs):
        events.append(kwargs)

    monkeypatch.setattr(session_store, "_get_redis", get_redis)
    monkeypatch.setattr(identity_roles.activity, "record", record)
    actor = {
        "user_id": "operator",
        "username": "operator",
        "domain_id": "organization",
        "identity_domain_id": "organization",
        "project_id": "",
        "connection_project_id": "",
        "token": "native-token",
        "roles": ["member"],
        "is_system_admin": True,
    }

    def validate_token(token, **kwargs):
        return {
            "user_id": "operator",
            "domain_id": "organization",
            "identity_domain_id": "organization",
            "project_id": "",
            "roles": ["member"],
        }

    monkeypatch.setattr(keystone, "validate_token", validate_token)
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/admin")
    conn = SimpleNamespace(identity=directory, endpoint_for=lambda service: "https://keystone.invalid/v3")
    app.dependency_overrides[get_admin_os_conn] = lambda: conn
    app.dependency_overrides[get_token_info] = lambda: actor
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield SimpleNamespace(
            directory=directory,
            native=native,
            redis=redis,
            client=client,
            actor=actor,
            events=events,
            conn=conn,
        )
    await redis.close()


CANDIDATES = "/api/v1/admin/groups/team/candidates"
ADD = "/api/v1/admin/groups/team/users/account-uuid-full"
EXPLICIT = {"domain_id": "organization", "user_domain_id": "accounts"}


@pytest.mark.asyncio
async def test_group_candidates_select_exact_accounts_home_with_same_named_other_home(group_home):
    env = group_home
    env.directory.grant(project="work")
    env.directory.groups["team"].add("other-uuid-full")
    response = await env.client.get(CANDIDATES, params=EXPLICIT)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, private"
    assert response.json() == {
        **EXPLICIT,
        "items": [
            {
                "id": "account-uuid-full",
                "name": "same-name",
                "email": "account@example.test",
                "enabled": True,
                "domain_id": "accounts",
            }
        ],
    }
    other = await env.client.get(CANDIDATES, params={**EXPLICIT, "user_domain_id": "other-home"})
    assert other.status_code == 200
    assert other.json()["items"][0]["id"] == "other-uuid-full"
    assert not env.directory.writes


@pytest.mark.asyncio
async def test_accounts_directory_does_not_reread_each_candidate(group_home):
    env = group_home
    expected = {"account-uuid-full"}
    for number in range(500):
        uid = f"account-{number:04}"
        expected.add(uid)
        env.directory.users[uid] = SimpleNamespace(
            id=uid, name=f"Account {number}", email=f"account-{number}@example.test", enabled=True, domain_id="accounts"
        )
    response = await env.client.get(CANDIDATES, params=EXPLICIT)
    assert response.status_code == 200
    assert [row["id"] for row in response.json()["items"]] == sorted(expected)
    candidate_reads = [row for row in env.directory.reads if row[0] == "user" and row[1] in expected]
    assert candidate_reads == []
    assert not env.directory.writes


@pytest.mark.asyncio
@pytest.mark.parametrize("grant", ["none", "project", "inherited-domain"])
async def test_explicit_unjoined_account_admission_preserves_default_denial_and_grants(group_home, grant):
    env = group_home
    if grant == "project":
        env.directory.grant(project="work")
    elif grant == "inherited-domain":
        env.directory.grant(domain="organization", inherited=True)
    original = deepcopy(env.directory.assignments)
    default = await env.client.put(ADD, params={"domain_id": "organization"})
    assert default.status_code == 403
    assert not env.directory.writes
    await env.redis.set("afterglow:session:test-validation", "old")
    explicit = await env.client.put(ADD, params=EXPLICIT)
    assert explicit.status_code == 204
    assert env.directory.writes == [("add", "account-uuid-full", "team")]
    assert env.directory.groups["team"] == {"account-uuid-full"}
    assert env.directory.assignments == original
    assert await env.redis.get("afterglow:session:test-validation") is None
    assert env.events[-1]["action"] == "group_member_add"
    assert env.actor["domain_id"] == "organization"
    if grant != "none":
        domain_projects.assert_membership("account-uuid-full", "organization", ks=env.native)


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", ["project", "domain", "inherited-domain"])
async def test_explicit_group_admission_never_waives_foreign_grant_membership(group_home, scope):
    env = group_home
    if scope == "project":
        env.directory.grant(project="foreign")
    else:
        env.directory.grant(domain="other-home", inherited=scope == "inherited-domain")
    response = await env.client.put(ADD, params=EXPLICIT)
    assert response.status_code == 403
    assert not env.directory.writes
    assert not env.events


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["GET", "PUT"])
@pytest.mark.parametrize(
    "failure,status",
    [
        ("wrong-source", 403),
        ("disabled-source", 403),
        ("disabled-target", 403),
        ("deleted-source", 404),
        ("source-denied", 403),
        ("source-failed", 503),
        ("source-id", 503),
        ("group-domain", 403),
    ],
)
async def test_explicit_group_home_failures_never_read_inventory_or_write(group_home, method, failure, status):
    env = group_home
    params = dict(EXPLICIT)
    if failure == "wrong-source":
        params["user_domain_id"] = "other-home"
        if method == "GET":
            env.directory.list_extra = [env.directory.users["account-uuid-full"]]
            status = 503
    elif failure == "disabled-source":
        env.directory.domains["accounts"].enabled = False
    elif failure == "disabled-target":
        env.directory.domains["organization"].enabled = False
    elif failure == "deleted-source":
        del env.directory.domains["accounts"]
    elif failure == "source-denied":
        env.directory.failures[("domain", "accounts")] = 403
    elif failure == "source-failed":
        env.directory.failures[("domain", "accounts")] = 503
    elif failure == "source-id":
        env.directory.domains["accounts"].id = "substitute"
    else:
        env.directory.group.domain_id = "other-home"
    response = await env.client.request(method, CANDIDATES if method == "GET" else ADD, params=params)
    assert response.status_code == status
    assert "private-native-detail" not in response.text
    assert not env.directory.writes
    assert not env.events


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure,status",
    [
        ("deleted", 404),
        ("disabled", 403),
        ("denied", 403),
        ("failed", 503),
        ("id", 503),
        ("home", 403),
        ("enabled-metadata", 503),
    ],
)
async def test_explicit_admission_rechecks_exact_active_user_before_write(group_home, failure, status):
    env = group_home
    listed = await env.client.get(CANDIDATES, params=EXPLICIT)
    assert listed.status_code == 200
    assert listed.json()["items"][0]["id"] == "account-uuid-full"
    user = env.directory.users["account-uuid-full"]
    if failure == "deleted":
        del env.directory.users[user.id]
    elif failure == "disabled":
        user.enabled = False
    elif failure in {"denied", "failed"}:
        env.directory.failures[("user", user.id)] = status
    elif failure == "id":
        user.id = "substitute"
    elif failure == "home":
        user.domain_id = "other-home"
    else:
        del user.enabled
    response = await env.client.put(ADD, params=EXPLICIT)
    assert response.status_code == status
    assert not env.directory.writes


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure,status",
    [
        ("duplicate", 503),
        ("email", 503),
        ("id", 503),
        ("home", 503),
        ("name", 503),
        ("enabled", 503),
        ("enabled-string", 503),
        ("enabled-int", 503),
        ("list-denied", 403),
        ("list-failed", 503),
    ],
)
async def test_candidates_never_return_partial_or_malformed_success(group_home, failure, status):
    env = group_home
    user = env.directory.users["account-uuid-full"]
    if failure in {"list-denied", "list-failed"}:
        env.directory.failures[("users", "accounts")] = status
    elif failure == "id":
        user.id = None
    elif failure == "duplicate":
        env.directory.list_extra = [deepcopy(user)]
    elif failure == "home":
        env.directory.list_extra = [env.directory.users["other-uuid-full"]]
    elif failure == "name":
        user.name = {"malformed": True}
    elif failure == "email":
        user.email = {"malformed": True}
    elif failure == "enabled-string":
        user.enabled = "true"
    elif failure == "enabled-int":
        user.enabled = 1
    else:
        del user.enabled
    response = await env.client.get(CANDIDATES, params=EXPLICIT)
    assert response.status_code == status
    assert "items" not in response.json()
    assert not env.directory.writes


@pytest.mark.asyncio
async def test_candidates_omit_disabled_but_stale_list_row_does_not_authorize_admission(group_home):
    env = group_home
    stale = SimpleNamespace(
        id="deleted", name="Deleted", email="deleted@example.test", domain_id="accounts", enabled=True
    )
    env.native.users.list = lambda **_: [stale, env.directory.users["account-uuid-full"]]
    env.directory.users["account-uuid-full"].enabled = False
    response = await env.client.get(CANDIDATES, params=EXPLICIT)
    assert response.status_code == 200
    assert [row["id"] for row in response.json()["items"]] == ["deleted"]
    assert ("user", "deleted") not in env.directory.reads
    rejected = await env.client.put("/api/v1/admin/groups/team/users/deleted", params=EXPLICIT)
    assert rejected.status_code == 404
    assert not env.directory.writes


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["GET", "PUT"])
@pytest.mark.parametrize("authority", ["member", "manager", "stale-admin"])
async def test_group_home_requires_live_system_admin_not_manager_or_cached_claim(group_home, method, authority):
    env = group_home
    env.directory.assignments = []
    env.actor["roles"] = ["manager"] if authority == "manager" else ["member"]
    env.actor["is_system_admin"] = authority == "stale-admin"
    response = await env.client.request(method, CANDIDATES if method == "GET" else ADD, params=EXPLICIT)
    assert response.status_code == 403
    assert not any(read[0] == "users" for read in env.directory.reads)
    assert not env.directory.writes


@pytest.mark.asyncio
async def test_explicit_admission_reproves_authority_after_acquiring_lease(group_home, monkeypatch):
    from contextlib import asynccontextmanager

    env = group_home
    original = identity_roles._graph_lock

    @asynccontextmanager
    async def revoke_at_lease(conn):
        async with original(conn) as lease:
            env.directory.assignments = []
            yield lease

    monkeypatch.setattr(identity_roles, "_graph_lock", revoke_at_lease)
    response = await env.client.put(ADD, params=EXPLICIT)
    assert response.status_code == 403
    assert env.actor["_live_system_admin"] is True  # Earlier proof is not sufficient.
    assert not env.directory.writes


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "guard,status",
    [("owner", 409), ("projection", 403), ("redis", 503), ("lease", 503), ("disabled-project", 403)],
)
async def test_explicit_admission_preserves_mutation_safeguards(group_home, monkeypatch, guard, status):
    env = group_home
    if guard == "owner":
        env.directory.rows["project_owner"] = {"id": "project_owner", "name": "project_owner", "domain_id": None}
        env.directory.grant(project="work", role="project_owner")
    elif guard == "projection":
        env.directory.group.name = "afterglow-default-managers-organization"
    elif guard == "redis":

        async def unavailable():
            raise RuntimeError("unavailable")

        monkeypatch.setattr(session_store, "_get_redis", unavailable)
    elif guard == "lease":

        async def lost(self):
            raise identity_roles._unavailable("Lease lost")

        monkeypatch.setattr(identity_roles._GraphLease, "assert_owned", lost)
    else:
        env.directory.grant(project="work")
        env.directory.projects["work"].enabled = False
    response = await env.client.put(ADD, params=EXPLICIT)
    assert response.status_code == status
    assert not env.directory.writes


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["GET", "PUT"])
async def test_explicit_group_home_requires_both_exact_domain_parameters(group_home, method):
    path = CANDIDATES if method == "GET" else ADD
    response = await group_home.client.request(method, path, params={"user_domain_id": "accounts"})
    assert response.status_code == 422
    assert not group_home.directory.writes


@pytest.mark.asyncio
@pytest.mark.parametrize("change,status", [("group-owner", 403), ("source-disabled", 403), ("user-deleted", 404)])
async def test_explicit_admission_rechecks_native_selection_after_lease(group_home, monkeypatch, change, status):
    from contextlib import asynccontextmanager

    env = group_home
    original = identity_roles._graph_lock

    @asynccontextmanager
    async def change_at_lease(conn):
        async with original(conn) as lease:
            if change == "group-owner":
                env.directory.group.domain_id = "other-home"
            elif change == "source-disabled":
                env.directory.domains["accounts"].enabled = False
            else:
                del env.directory.users["account-uuid-full"]
            yield lease

    monkeypatch.setattr(identity_roles, "_graph_lock", change_at_lease)
    response = await env.client.put(ADD, params=EXPLICIT)
    assert response.status_code == status
    assert not env.directory.writes
    assert not env.events
