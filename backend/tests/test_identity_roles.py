"""HTTP role lifecycle/security regressions with a stateful Keystone boundary.

The provider fixture models the installed SDK/native wire API, not service-function
forwarding. Session tests use the real session store against isolated fake Redis.
Role/permission reductions must preserve the stored login family and proof; only
explicit session revocation removes them. Cache tests exercise old-entry eviction,
not distributed authorization freshness. Native token liveness/revocation is a
synthetic provider boundary, not evidence about real Keystone group-member deletion.
"""

import asyncio
import hashlib
import json
import threading
import time
from types import SimpleNamespace

import fakeredis.aioredis
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from requests import Response

from app.api.deps import get_os_conn, get_token_info, require_admin
from app.api.identity.admin_identity import router
from app.services import cache, identity_roles, keystone, project_service, session_store
from app.services.cache.redis_backend import RedisBackend
from tests.admin_gate import synthetic_verified_admin


class IdentityProvider:
    def __init__(self):
        self.rows = {
            name: {"id": name, "name": name, "description": "", "domain_id": None}
            for name in ("admin", "manager", "member", "reader", "custom", "other", "alias")
        }
        self.edges = {("admin", "manager"), ("manager", "member"), ("member", "reader")}
        self.assignments = []
        self.groups = {}
        self.graph_status = 200
        self.graph_payload = None
        self.write_status = None
        self.assignments_error = False
        self.native_tokens = set()
        self.projects = {
            pid: SimpleNamespace(id=pid, name=pid, domain_id="default", enabled=True)
            for pid in ("project", "p", "tenant", "isolated")
        }

    @staticmethod
    def response(status, payload=None):
        response = Response()
        response.status_code = status
        response.url = "https://keystone.invalid/v3/roles"
        response._content = json.dumps(payload or {}).encode()
        return response

    def roles(self):
        return iter(SimpleNamespace(**row) for row in self.rows.values())

    def get(self, path):
        assert path == "/role_inferences"
        grouped = []
        for prior in sorted({a for a, _ in self.edges}):
            grouped.append(
                {"prior_role": {"id": prior}, "implies": [{"id": b} for a, b in sorted(self.edges) if a == prior]}
            )
        payload = self.graph_payload if self.graph_payload is not None else {"role_inferences": grouped}
        return self.response(self.graph_status, payload)

    def put(self, path):
        if self.write_status:
            return self.response(self.write_status)
        _, kind, prior, implies, child = path.split("/")
        assert (kind, implies) == ("roles", "implies")
        if prior not in self.rows or child not in self.rows:
            return self.response(404)
        if (prior, child) in self.edges:
            return self.response(409)
        self.edges.add((prior, child))
        return self.response(201, {"role_inference": {"prior_role": {"id": prior}, "implies": [{"id": child}]}})

    def delete(self, path):
        if self.write_status:
            return self.response(self.write_status)
        _, _, prior, _, child = path.split("/")
        if (prior, child) not in self.edges:
            return self.response(404)
        self.edges.remove((prior, child))
        return self.response(204)

    def create_role(self, **attrs):
        rid = "new-" + attrs["name"]
        self.rows[rid] = {"id": rid, "domain_id": None, "description": "", **attrs}
        return SimpleNamespace(**self.rows[rid])

    def update_role(self, rid, **attrs):
        self.rows[rid].update(attrs)
        return SimpleNamespace(**self.rows[rid])

    def delete_role(self, rid, ignore_missing=True):
        del self.rows[rid]

    def role_assignments(self, role_id=None, effective=False, **query):
        if self.assignments_error:
            raise RuntimeError("assignment metadata unavailable")
        result = []
        for assignment in self.assignments:
            if role_id is not None and assignment["role"]["id"] != role_id:
                continue
            rows = [assignment]
            if effective and "group" in assignment:
                rows = [
                    {"role": assignment["role"], "user": {"id": uid}, "scope": assignment["scope"]}
                    for uid in self.groups[assignment["group"]["id"]]
                ]
            for row in rows:
                scope = row["scope"]
                if effective and "domain" in scope and scope.get("OS-INHERIT:inherited_to") == "projects":
                    scopes = [
                        {"project": {"id": project.id}, "OS-INHERIT:inherited_to": "projects"}
                        for project in self.projects.values()
                        if project.domain_id == scope["domain"]["id"]
                    ]
                else:
                    scopes = [scope]
                for resolved_scope in scopes:
                    resolved = {**row, "scope": resolved_scope}
                    if any(
                        resolved.get(kind, {}).get("id") != query.get(kind, query.get(kind + "_id"))
                        for kind in ("user", "group", "role")
                        if kind in query or kind + "_id" in query
                    ):
                        continue
                    if any(
                        resolved_scope.get(kind, {}).get("id") != query[kind]
                        for kind in ("project", "domain")
                        if kind in query
                    ):
                        continue
                    result.append(resolved)
        return iter(result)

    def get_domain(self, did):
        return SimpleNamespace(id=did, name=did, enabled=True)

    def get_user(self, uid):
        return SimpleNamespace(id=uid, name=uid, domain_id="default", enabled=True)

    def get_project(self, pid):
        return self.projects[pid]

    def get_group(self, gid):
        assert gid in self.groups
        return SimpleNamespace(id=gid, name=gid, description="", domain_id="default")

    def get_role(self, rid):
        return SimpleNamespace(**self.rows[rid])

    def _project_assignment(self, pid, principal, subject, rid, *, remove=False):
        row = {"role": {"id": rid}, principal: {"id": subject}, "scope": {"project": {"id": pid}}}
        if remove:
            self.assignments.remove(row)
        elif row not in self.assignments:
            self.assignments.append(row)

    def assign_project_role_to_user(self, pid, uid, rid):
        self._project_assignment(pid, "user", uid, rid)

    def unassign_project_role_from_user(self, pid, uid, rid):
        self._project_assignment(pid, "user", uid, rid, remove=True)

    def assign_project_role_to_group(self, pid, gid, rid):
        self._project_assignment(pid, "group", gid, rid)

    def unassign_project_role_from_group(self, pid, gid, rid):
        self._project_assignment(pid, "group", gid, rid, remove=True)

    def native_assignments(self, **query):
        return list(self.role_assignments(**query))

    def group_users(self, gid):
        return iter(SimpleNamespace(id=uid) for uid in self.groups[gid])


@pytest.fixture
async def role_env(monkeypatch):
    provider = IdentityProvider()
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    # The graph lifecycle suite represents legacy native domains without
    # Default projects. Default-manager source simulations live in its own suite.
    native = SimpleNamespace(
        domains=SimpleNamespace(
            get=provider.get_domain,
            list=lambda: [provider.get_domain("default")],
        ),
        projects=SimpleNamespace(
            get=provider.get_project,
            list=lambda **query: [
                project
                for project in provider.projects.values()
                if all(
                    getattr(project, "domain_id" if key == "domain" else key) == value for key, value in query.items()
                )
            ],
        ),
        users=SimpleNamespace(get=provider.get_user, list=lambda group=None: list(provider.group_users(group))),
        groups=SimpleNamespace(get=provider.get_group),
        roles=SimpleNamespace(list=provider.roles),
        inference_rules=SimpleNamespace(
            list_inference_roles=lambda: provider.get("/role_inferences").json()["role_inferences"]
        ),
        role_assignments=SimpleNamespace(list=provider.native_assignments),
    )
    monkeypatch.setattr(keystone, "_get_admin_ks_client", lambda: native)
    monkeypatch.setattr(cache, "_backend", RedisBackend(client=redis))

    async def get_redis():
        return redis

    async def record(**kwargs):
        events.append(kwargs)

    async def invalidate(key):
        cleared.append(key)
        await cache.invalidate(key)

    def revoke_native(token):
        revoked.append(token)
        provider.native_tokens.remove(token)

    events, cleared, revoked = [], [], []
    monkeypatch.setattr(session_store, "_get_redis", get_redis)
    # Real family deletion runs; only the external native revocation is synthetic.
    monkeypatch.setattr(keystone, "revoke_token", revoke_native)
    monkeypatch.setattr(identity_roles.activity, "record", record)
    monkeypatch.setattr(identity_roles, "invalidate", invalidate)
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/admin")
    state = {
        "user_id": "operator",
        "username": "operator",
        "project_id": "admin-project",
        "roles": ["admin", "manager"],
        "is_system_admin": True,
    }
    app.dependency_overrides[get_os_conn] = lambda: SimpleNamespace(
        identity=provider, endpoint_for=lambda service: "https://keystone.invalid/v3"
    )
    app.dependency_overrides[get_token_info] = lambda: state
    app.dependency_overrides[require_admin] = synthetic_verified_admin
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield SimpleNamespace(
            provider=provider, redis=redis, client=client, auth=state, events=events, cleared=cleared, revoked=revoked
        )
    await redis.close()


async def session(env, uid, project_id="project"):
    """Create and rotate a real login family, retaining its native login proof."""
    token, initial, current = "token-" + uid, "login-" + uid, "session-" + uid
    env.provider.native_tokens.add(token)
    exp = int(time.time()) + 3600
    assert await session_store.store_session(
        initial,
        token,
        project_id,
        uid,
        exp,
        domain_id="default",
        identity_domain_id="home",
        started_at=time.time() - 30,
        origin_ip="192.0.2.10",
        origin_fp="browser",
    )
    assert await session_store.store_session(
        current,
        token,
        project_id,
        uid,
        exp,
        domain_id="default",
        identity_domain_id="home",
        previous_jti=initial,
        timeout_seconds=7200,
    )
    stored = await session_store.get_session(current)
    assert stored["family_id"] == initial
    return stored


async def assert_login_survives(env, uid, stored):
    current, initial = "session-" + uid, "login-" + uid
    assert await session_store.get_session(current) == stored
    assert await env.redis.get("afterglow:session-family:" + initial) == current
    assert await env.redis.get("afterglow:refresh-family:" + initial) == initial
    assert await env.redis.smembers("afterglow:user-sessions:" + uid) == {current}
    assert stored["keystone_token"] in env.provider.native_tokens
    assert stored["keystone_token"] not in env.revoked


async def cached_access(uid, project_id="project"):
    """Cache real current-project permissions in the native-validation namespace.

    No auth resolver is replaced: this isolates cache eviction from refresh-family
    storage while using the production current role-ID/DAG permission resolver.
    """
    token_hash = hashlib.sha256(("token-" + uid).encode()).hexdigest()

    async def load():
        return await project_service.get_project_access(project_id, uid)

    key = f"afterglow:session:{token_hash}:{project_id}"
    access = await cache.cached_call(key, 60, load)
    # A swallowed cache-write failure must not turn this into an uncached test.
    assert json.loads(await cache.get_backend().get(key)) == access
    return access


def add_chat_permission(provider):
    provider.rows["lumen-chat_user"] = {
        "id": "lumen-chat_user",
        "name": "lumen-chat_user",
        "description": "",
        "domain_id": None,
    }


def has_chat_role(access):
    return "lumen-chat_user" in access["roles"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,path,body",
    [
        ("GET", "/roles", None),
        ("POST", "/roles", {"name": "new"}),
        ("PATCH", "/roles/custom", {"description": "changed"}),
        ("DELETE", "/roles/custom", None),
        ("PUT", "/roles/custom/implies/reader", None),
        ("DELETE", "/roles/admin/implies/manager", None),
    ],
)
async def test_management_requires_verified_system_admin_not_role_names(role_env, method, path, body):
    role_env.auth["is_system_admin"] = False  # Even admin/manager role names do not suffice.
    before = set(role_env.provider.edges)
    response = await role_env.client.request(method, "/api/v1/admin" + path, json=body)
    assert response.status_code == 403
    assert role_env.provider.edges == before
    assert role_env.provider.rows["custom"]["description"] == ""
    assert "new-new" not in role_env.provider.rows


@pytest.mark.asyncio
async def test_catalog_reports_real_direct_transitive_and_alias_graph_fresh(role_env):
    p, client = role_env.provider, role_env.client
    p.edges.add(("alias", "manager"))
    rows = {row["id"]: row for row in (await client.get("/api/v1/admin/roles")).json()}
    assert rows["alias"]["system_only"] is True
    assert rows["alias"]["protected"] is False
    assert rows["alias"]["implied_role_ids"] == ["manager"]
    assert rows["alias"]["inherited_role_ids"] == ["manager", "member", "reader"]
    assert rows["manager"]["parent_role_ids"] == ["admin", "alias"]
    p.edges.remove(("alias", "manager"))
    fresh = {row["id"]: row for row in (await client.get("/api/v1/admin/roles")).json()}
    assert fresh["alias"]["system_only"] is False
    assert fresh["alias"]["inherited_role_ids"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,payload,expected",
    [
        (500, None, 503),
        (404, None, 503),
        (403, None, 403),
        (200, {"unrelated": []}, 503),
        (200, {"role_inferences": [{"prior_role": {"id": "missing"}, "implies": []}]}, 503),
    ],
)
async def test_graph_failures_are_consumer_visible_not_successful_empty_catalog(role_env, status, payload, expected):
    role_env.provider.graph_status = status
    role_env.provider.graph_payload = payload
    response = await role_env.client.get("/api/v1/admin/roles")
    assert response.status_code == expected
    assert "detail" in response.json()
    blocked = await role_env.client.put("/api/v1/admin/roles/custom/implies/reader")
    assert blocked.status_code == expected
    assert ("custom", "reader") not in role_env.provider.edges


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "prior,child",
    [
        ("custom", "custom"),
        ("reader", "member"),
        ("manager", "admin"),
        ("custom", "manager"),
        ("custom", "alias"),
        ("reader", "other"),
    ],
)
async def test_cycles_and_upward_edges_including_aliases_and_ancestors(role_env, prior, child):
    role_env.provider.edges.update({("alias", "admin"), ("other", "member")})
    response = await role_env.client.put(f"/api/v1/admin/roles/{prior}/implies/{child}")
    assert response.status_code == 409
    assert (prior, child) not in role_env.provider.edges


@pytest.mark.asyncio
async def test_member_and_reader_ancestors_cannot_be_elevated_later(role_env):
    client = role_env.client
    assert (await client.put("/api/v1/admin/roles/member/implies/custom")).status_code == 200
    assert (await client.put("/api/v1/admin/roles/custom/implies/admin")).status_code == 409
    assert (await client.put("/api/v1/admin/roles/reader/implies/other")).status_code == 200
    assert (await client.put("/api/v1/admin/roles/other/implies/member")).status_code == 409


@pytest.mark.asyncio
async def test_actual_repeated_edge_and_removal_do_not_fake_success(role_env):
    client = role_env.client
    path = "/api/v1/admin/roles/custom/implies/reader"
    assert (await client.put(path)).json() == {"status": "created"}
    assert ("custom", "reader") in role_env.provider.edges
    assert (await client.put(path)).status_code == 409
    assert (await client.delete(path)).json() == {"status": "deleted"}
    assert ("custom", "reader") not in role_env.provider.edges
    assert (await client.delete(path)).status_code == 404
    assert [e["action"] for e in role_env.events] == ["role_implication_create", "role_implication_delete"]
    assert set(role_env.cleared) == {
        "afterglow:admin:roles",
        "afterglow:admin:identity:summary",
        identity_roles.VISIBILITY_KEY,
        "afterglow:session:*",
    }


@pytest.mark.asyncio
async def test_unknown_and_cross_domain_edges_are_rejected(role_env):
    p, client = role_env.provider, role_env.client
    assert (await client.put("/api/v1/admin/roles/missing/implies/reader")).status_code == 404
    p.rows["custom"]["domain_id"] = "a"
    p.rows["other"]["domain_id"] = "b"
    assert (await client.put("/api/v1/admin/roles/custom/implies/other")).status_code == 409
    assert (await client.put("/api/v1/admin/roles/member/implies/custom")).status_code == 409
    assert (await client.put("/api/v1/admin/roles/custom/implies/reader")).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("status,expected", [(400, 422), (403, 403), (404, 404), (409, 409), (500, 503)])
async def test_actual_provider_write_errors_are_not_success_or_empty(role_env, status, expected):
    role_env.provider.write_status = status
    response = await role_env.client.put("/api/v1/admin/roles/custom/implies/reader")
    assert response.status_code == expected
    assert ("custom", "reader") not in role_env.provider.edges
    assert len(role_env.events) == 1 and role_env.events[0]["status"] == "failed"


@pytest.mark.asyncio
@pytest.mark.parametrize("core", ["admin", "manager", "member", "reader"])
async def test_core_role_identity_is_immutable_but_description_editable(role_env, core):
    p, client = role_env.provider, role_env.client
    p.rows[core]["name"] = core.upper()  # Protection is case-insensitive.
    assert (await client.patch(f"/api/v1/admin/roles/{core}", json={"name": "renamed"})).status_code == 409
    assert (await client.delete(f"/api/v1/admin/roles/{core}")).status_code == 409
    response = await client.patch(f"/api/v1/admin/roles/{core}", json={"description": "Updated"})
    assert response.status_code == 200
    assert response.json()["description"] == "Updated"
    assert response.json()["protected"] is True


@pytest.mark.asyncio
async def test_metadata_lifecycle_validation_and_safe_delete(role_env):
    p, client = role_env.provider, role_env.client
    for attrs in ({"name": " "}, {"name": "name", "unknown": True}):
        assert (await client.post("/api/v1/admin/roles", json=attrs)).status_code == 422
    assert (await client.post("/api/v1/admin/roles", json={"name": "ADMIN"})).status_code == 409
    assert (await client.post("/api/v1/admin/roles", json={"name": "custom"})).status_code == 422
    created = await client.post("/api/v1/admin/roles", json={"name": "New Role_user", "description": "Details"})
    assert created.status_code == 201
    rid = created.json()["id"]
    assert created.json()["implied_role_ids"] == []
    assert (await client.patch(f"/api/v1/admin/roles/{rid}", json={"name": "Renamed_user"})).json()[
        "name"
    ] == "renamed_user"
    assert (await client.patch(f"/api/v1/admin/roles/{rid}", json={})).status_code == 422
    assert (await client.patch(f"/api/v1/admin/roles/{rid}", json={"name": None})).status_code == 422
    assert (await client.patch(f"/api/v1/admin/roles/{rid}", json={"name": "manager"})).status_code == 409
    assert (await client.delete(f"/api/v1/admin/roles/{rid}")).json() == {"status": "deleted"}
    assert rid not in p.rows
    assert (await client.delete(f"/api/v1/admin/roles/{rid}")).status_code == 404
    p.edges.add(("custom", "other"))
    assert (await client.delete("/api/v1/admin/roles/custom")).status_code == 409
    assert (await client.delete("/api/v1/admin/roles/other")).status_code == 409
    p.edges.clear()
    p.assignments.append(
        {
            "role": {"id": "custom"},
            "group": {"id": "g"},
            "scope": {"domain": {"id": "d"}, "OS-INHERIT:inherited_to": "projects"},
        }
    )
    p.groups["g"] = []  # Even a currently empty inherited group grant blocks deletion.
    assert (await client.delete("/api/v1/admin/roles/custom")).status_code == 409
    assert "custom" in p.rows


@pytest.mark.asyncio
async def test_create_description_and_delete_success_clear_caches_and_audit(role_env):
    client, keys = (
        role_env.client,
        {
            "afterglow:admin:roles",
            "afterglow:admin:identity:summary",
            identity_roles.VISIBILITY_KEY,
            "afterglow:session:*",
        },
    )
    created = await client.post("/api/v1/admin/roles", json={"name": "Audited_user"})
    assert created.status_code == 201
    assert set(role_env.cleared) == keys
    role_env.cleared.clear()
    updated = await client.patch("/api/v1/admin/roles/custom", json={"description": "only text"})
    assert updated.status_code == 200
    assert updated.json()["description"] == "only text"
    assert set(role_env.cleared) == keys
    role_env.cleared.clear()
    assert (await client.delete(f"/api/v1/admin/roles/{created.json()['id']}")).status_code == 200
    assert set(role_env.cleared) == keys
    assert [e["action"] for e in role_env.events] == ["role_create", "role_update", "role_delete"]
    assert not role_env.revoked


def _holder_fixture(p):
    p.edges.add(("other", "custom"))
    p.groups["g"] = ["group-user"]
    p.assignments = [
        {"role": {"id": "custom"}, "user": {"id": "direct"}, "scope": {"system": {"all": True}}},
        {"role": {"id": "custom"}, "user": {"id": "direct"}, "scope": {"project": {"id": "project"}}},
        *[
            {"role": {"id": "member"}, "user": {"id": uid}, "scope": {"project": {"id": "project"}}}
            for uid in ("direct", "group-user")
        ],
        {
            "role": {"id": "other"},
            "group": {"id": "g"},
            "scope": {"domain": {"id": "default"}, "OS-INHERIT:inherited_to": "projects"},
        },
    ]


@pytest.mark.asyncio
async def test_edge_removal_drops_current_permissions_but_preserves_holder_logins(role_env):
    p, client = role_env.provider, role_env.client
    _holder_fixture(p)
    add_chat_permission(p)
    p.edges.add(("custom", "lumen-chat_user"))
    stored = {uid: await session(role_env, uid) for uid in ("direct", "group-user", "unaffected")}
    before = {uid: await cached_access(uid) for uid in stored}
    for uid in ("direct", "group-user"):
        assert "lumen-chat_user" in before[uid]["roles"]
        assert has_chat_role(before[uid])
    assert not has_chat_role(before["unaffected"])

    response = await client.delete("/api/v1/admin/roles/custom/implies/lumen-chat_user")
    assert response.status_code == 200
    for uid in ("direct", "group-user"):
        current = await cached_access(uid)
        assert "lumen-chat_user" not in current["roles"]
        assert "custom" in current["roles"]
        assert not has_chat_role(current)
    assert await cached_access("unaffected") == before["unaffected"]
    for uid, snapshot in stored.items():
        await assert_login_survives(role_env, uid, snapshot)
    assert not role_env.revoked


@pytest.mark.asyncio
async def test_adding_lower_edge_refreshes_cached_permissions_without_holder_lookup(role_env):
    p, client = role_env.provider, role_env.client
    _holder_fixture(p)
    add_chat_permission(p)
    stored = {uid: await session(role_env, uid) for uid in ("direct", "group-user", "unaffected")}
    before = {uid: await cached_access(uid) for uid in stored}
    assert all(not has_chat_role(access) for access in before.values())
    p.assignments_error = True  # A write with any holder lookup would fail.
    assert (await client.put("/api/v1/admin/roles/custom/implies/lumen-chat_user")).status_code == 200
    p.assignments_error = False
    for uid in ("direct", "group-user"):
        current = await cached_access(uid)
        assert "lumen-chat_user" in current["roles"]
        assert has_chat_role(current)
    assert await cached_access("unaffected") == before["unaffected"]
    for uid, snapshot in stored.items():
        await assert_login_survives(role_env, uid, snapshot)
    assert not role_env.revoked


@pytest.mark.asyncio
async def test_rename_refreshes_permissions_preserves_login_and_unknown_recipients_block_removal(role_env):
    p, client = role_env.provider, role_env.client
    p.rows["custom"]["name"] = "lumen-chat_user"
    p.assignments = [
        {"role": {"id": rid}, "user": {"id": "holder"}, "scope": {"project": {"id": "p"}}}
        for rid in ("custom", "member")
    ]
    stored = await session(role_env, "holder", "p")
    before = await cached_access("holder", "p")
    assert "lumen-chat_user" in before["roles"] and has_chat_role(before)
    assert (await client.patch("/api/v1/admin/roles/custom", json={"name": "Renamed_user"})).status_code == 200
    current = await cached_access("holder", "p")
    assert "lumen-chat_user" not in current["roles"]
    assert "renamed_user" in current["roles"]
    assert not has_chat_role(current)
    await assert_login_survives(role_env, "holder", stored)
    p.edges.add(("custom", "reader"))
    p.assignments_error = True
    assert (await client.delete("/api/v1/admin/roles/custom/implies/reader")).status_code == 503
    assert ("custom", "reader") in p.edges
    assert (await client.patch("/api/v1/admin/roles/custom", json={"name": "Again_user"})).status_code == 503
    assert p.rows["custom"]["name"] == "renamed_user"
    p.edges.clear()
    assert (await client.delete("/api/v1/admin/roles/custom")).status_code == 503
    assert "custom" in p.rows
    await assert_login_survives(role_env, "holder", stored)
    assert not role_env.revoked


@pytest.mark.asyncio
async def test_malformed_recipient_and_session_store_failure_block_removal(role_env, monkeypatch):
    p, client = role_env.provider, role_env.client
    p.edges.add(("custom", "reader"))
    p.assignments = [{"role": {"id": "custom"}, "scope": {"project": {"id": "p"}}}]
    assert (await client.delete("/api/v1/admin/roles/custom/implies/reader")).status_code == 503
    p.assignments[0]["user"] = {"id": "holder"}

    async def unavailable():
        raise RuntimeError("Redis unavailable")

    monkeypatch.setattr(session_store, "_get_redis", unavailable)
    assert (await client.delete("/api/v1/admin/roles/custom/implies/reader")).status_code == 503
    assert ("custom", "reader") in p.edges


@pytest.mark.asyncio
async def test_post_write_invalidation_failure_reports_applied_change(role_env, monkeypatch):
    p = role_env.provider
    p.edges.add(("custom", "reader"))
    p.assignments = [{"role": {"id": "custom"}, "user": {"id": "holder"}, "scope": {"project": {"id": "p"}}}]
    stored = await session(role_env, "holder", "p")
    before = await cached_access("holder", "p")
    original_invalidate = identity_roles.invalidate

    async def failed_invalidate(key):
        if key == "afterglow:session:*":
            raise RuntimeError("validation cache deletion failed after preflight")
        await original_invalidate(key)

    monkeypatch.setattr(identity_roles, "invalidate", failed_invalidate)
    response = await role_env.client.delete("/api/v1/admin/roles/custom/implies/reader")
    assert response.status_code == 503
    assert "applied" in response.json()["detail"]
    assert ("custom", "reader") not in p.edges
    assert not role_env.events
    assert await cached_access("holder", "p") == before
    assert "reader" not in (await project_service.get_project_access("p", "holder"))["roles"]
    await assert_login_survives(role_env, "holder", stored)


@pytest.mark.asyncio
async def test_graph_lease_serializes_writes_and_is_released(role_env):
    p, client, redis = role_env.provider, role_env.client, role_env.redis
    key = "afterglow:identity-role-graph:" + hashlib.sha256(b"https://keystone.invalid/v3").hexdigest()
    await redis.set(key, "another-request", ex=60)
    for method, path in (
        ("PUT", "/roles/custom/implies/reader"),
        ("DELETE", "/roles/other"),
        ("POST", "/roles"),
        ("PATCH", "/roles/custom"),
    ):
        body = {"name": "New_user"} if method == "POST" else {"description": "x"} if method == "PATCH" else None
        assert (await client.request(method, "/api/v1/admin" + path, json=body)).status_code == 409
    assert ("custom", "reader") not in p.edges and "other" in p.rows
    await redis.delete(key)
    assert (await client.put("/api/v1/admin/roles/custom/implies/reader")).status_code == 200
    assert await redis.get(key) is None


@pytest.mark.asyncio
async def test_graph_lease_unavailable_blocks_writes(role_env, monkeypatch):
    async def unavailable():
        raise RuntimeError("Redis unavailable")

    monkeypatch.setattr(session_store, "_get_redis", unavailable)
    assert (await role_env.client.put("/api/v1/admin/roles/custom/implies/reader")).status_code == 503
    assert ("custom", "reader") not in role_env.provider.edges


def _trusted(monkeypatch, p):
    class Inferences:
        def list_inference_roles(self):
            return p.get("/role_inferences").json()["role_inferences"]

    ks = SimpleNamespace(roles=SimpleNamespace(list=p.roles), inference_rules=Inferences())
    monkeypatch.setattr(keystone, "_get_admin_ks_client", lambda: ks)


def _memory_cache(monkeypatch, store):
    async def cached(key, ttl, fn, refresh=False):
        if refresh or key not in store:
            store[key] = fn()
        return store[key]

    monkeypatch.setattr(identity_roles, "cached_call", cached)


@pytest.mark.asyncio
async def test_public_projection_uses_real_alias_graph_and_hides_unclassifiable(monkeypatch):
    p = IdentityProvider()
    p.edges.add(("alias", "manager"))
    _trusted(monkeypatch, p)
    _memory_cache(monkeypatch, {})
    names = ["Admin", "manager", "member", "reader", "alias", "custom"]
    assert await identity_roles.visible_role_names(names, True) == names
    assert await identity_roles.visible_role_names(names, False) == ["member", "reader", "custom"]
    assert await identity_roles.visible_role_names(["reader", "unknown"], False) == ["reader"]

    def unavailable():
        raise RuntimeError("Keystone unavailable")

    monkeypatch.setattr(keystone, "_get_admin_ks_client", unavailable)
    _memory_cache(monkeypatch, {})
    assert await identity_roles.visible_role_names(["admin", "manager", "member", "reader"], False) == [
        "member",
        "reader",
    ]
    assert await identity_roles.visible_role_names(["member", "custom"], False) == ["member"]


@pytest.mark.asyncio
async def test_corrupt_visibility_metadata_is_refreshed_once_then_hidden(monkeypatch):
    p = IdentityProvider()
    _trusted(monkeypatch, p)
    store = {identity_roles.VISIBILITY_KEY: [{"name": "custom", "system_only": "false"}]}
    _memory_cache(monkeypatch, store)
    assert await identity_roles.visible_role_names(["custom"], False) == ["custom"]

    async def always_corrupt(key, ttl, fn, refresh=False):
        return [{"name": "custom", "system_only": "false"}]

    monkeypatch.setattr(identity_roles, "cached_call", always_corrupt)
    assert await identity_roles.visible_role_names(["reader", "custom"], False) == ["reader"]


@pytest.mark.asyncio
async def test_auth_me_succeeds_after_external_custom_role_outdates_cached_catalog(monkeypatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.main import app
    from app.models.domain_auth import DomainLoginPolicy
    from app.services import domain_auth

    p = IdentityProvider()
    _trusted(monkeypatch, p)
    ks = keystone._get_admin_ks_client()
    # Exact enabled native resources and current grants back the real domain
    # visibility/system-authority checks; token role names are not authority.
    users = {"u": SimpleNamespace(id="u", name="u", domain_id="default", enabled=True)}
    domains = {"default": SimpleNamespace(id="default", name="Default", enabled=True)}
    projects = {"p": SimpleNamespace(id="p", name="P", domain_id="default", enabled=True)}
    ks.users = SimpleNamespace(get=users.__getitem__)
    ks.domains = SimpleNamespace(get=domains.__getitem__, list=lambda: list(domains.values()))
    ks.projects = SimpleNamespace(get=projects.__getitem__)

    def groups(*, user):
        return [SimpleNamespace(id=gid) for gid, members in p.groups.items() if user in members]

    def assignments(**query):
        # All grants here are direct user grants, so raw and effective rows
        # coincide. An unfiltered read must still return the complete source.
        rows = list(p.assignments)
        for principal in ("user", "group", "role"):
            if principal in query:
                rows = [row for row in rows if row.get(principal, {}).get("id") == query[principal]]
        for scope in ("project", "domain"):
            if scope in query:
                rows = [row for row in rows if row["scope"].get(scope, {}).get("id") == query[scope]]
        if "system" in query:
            rows = [row for row in rows if row["scope"].get("system") == {"all": True}]
        return rows

    ks.groups = SimpleNamespace(list=groups)
    ks.role_assignments = SimpleNamespace(list=assignments)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(DomainLoginPolicy.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(domain_auth.database, "is_db_available", lambda: True)
    monkeypatch.setattr(domain_auth.database, "get_session_factory", lambda: factory)
    _memory_cache(monkeypatch, {})
    assert await identity_roles.visible_role_names(["custom"], False) == ["custom"]  # warm old graph
    # Created and assigned through the CLI: safe external role, then an external alias.
    p.rows["cli-role"] = {"id": "cli-role", "name": "cli-role", "description": "", "domain_id": None}
    p.rows["cli-alias"] = {"id": "cli-alias", "name": "cli-alias", "description": "", "domain_id": None}
    p.edges.add(("cli-alias", "admin"))
    p.assignments = [
        {"user": {"id": "u"}, "role": {"id": rid}, "scope": {"project": {"id": "p"}}}
        for rid in ("member", "cli-role", "cli-alias")
    ]
    token = {
        "user_id": "u",
        "username": "u",
        "project_id": "p",
        "project_name": "P",
        "roles": ["member", "cli-role", "cli-alias", "never-listed"],
        "is_system_admin": False,
        "auth_method": "password",
        "domain_id": "default",
        "domain_name": "Default",
        "identity_domain_id": "default",
        "identity_domain_name": "Default",
    }
    app.dependency_overrides[get_token_info] = lambda: token
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/auth/me")
    finally:
        app.dependency_overrides.pop(get_token_info, None)
        await engine.dispose()
    assert response.status_code == 200
    assert response.json()["roles"] == ["member", "cli-role"]
    assert response.json()["is_system_admin"] is False


@pytest.mark.asyncio
async def test_cancelled_edge_removal_finishes_validation_eviction_and_preserves_login(role_env, monkeypatch):
    provider = role_env.provider
    _holder_fixture(provider)
    add_chat_permission(provider)
    provider.edges.add(("custom", "lumen-chat_user"))
    stored = await session(role_env, "direct")
    assert has_chat_role(await cached_access("direct"))
    entered = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    original_delete = provider.delete

    def blocking_delete(path):
        response = original_delete(path)
        loop.call_soon_threadsafe(entered.set)
        assert release.wait(5), "provider write was not released"
        return response

    monkeypatch.setattr(provider, "delete", blocking_delete)
    request = asyncio.create_task(role_env.client.delete("/api/v1/admin/roles/custom/implies/lumen-chat_user"))
    try:
        await asyncio.wait_for(entered.wait(), 5)
        request.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await request
    finally:
        release.set()
        if not request.done():
            await request

    assert ("custom", "lumen-chat_user") not in provider.edges
    current = await cached_access("direct")
    assert "lumen-chat_user" not in current["roles"]
    assert not has_chat_role(current)
    await assert_login_survives(role_env, "direct", stored)
    assert not role_env.revoked
    assert identity_roles.VISIBILITY_KEY in role_env.cleared


@pytest.mark.asyncio
async def test_post_write_holder_recheck_failure_still_evicts_validation_without_revoking_login(role_env, monkeypatch):
    p = role_env.provider
    _holder_fixture(p)
    add_chat_permission(p)
    p.edges.add(("custom", "lumen-chat_user"))
    stored = await session(role_env, "direct")
    assert has_chat_role(await cached_access("direct"))
    original_delete = p.delete

    def delete_then_lose_metadata(path):
        response = original_delete(path)
        p.assignments_error = True
        return response

    monkeypatch.setattr(p, "delete", delete_then_lose_metadata)
    response = await role_env.client.delete("/api/v1/admin/roles/custom/implies/lumen-chat_user")
    assert response.status_code == 503
    assert "applied" in response.json()["detail"]
    p.assignments_error = False
    current = await cached_access("direct")
    assert "lumen-chat_user" not in current["roles"]
    assert not has_chat_role(current)
    await assert_login_survives(role_env, "direct", stored)
    assert not role_env.revoked


@pytest.mark.asyncio
@pytest.mark.parametrize("principal", ["user", "group"])
@pytest.mark.parametrize("self_change", [False, True], ids=["other-user", "self"])
@pytest.mark.parametrize("role_id", ["project_admin", "lumen-chat_user"])
async def test_generic_project_assignment_updates_current_authority_without_cross_project_logout(
    role_env, principal, self_change, role_id
):
    p, client = role_env.provider, role_env.client
    existing_project_hierarchy(p)
    add_chat_permission(p)
    target = "operator" if self_change else "target"
    if self_change:
        role_env.auth["project_id"] = "tenant"
    affected = [target, "group-peer"] if principal == "group" else [target]
    p.groups["editors"] = affected
    for uid in [*affected, "outsider"]:
        for pid in ("tenant", "isolated"):
            p.assign_project_role_to_user(pid, uid, "member")
    for uid in affected:
        p.assign_project_role_to_user("isolated", uid, role_id)
    stored = {uid: await session(role_env, uid, "tenant") for uid in [*affected, "outsider"]}
    isolated = {uid: await cached_access(uid, "isolated") for uid in stored}
    for uid in affected:
        before = await cached_access(uid, "tenant")
        assert role_id not in before["roles"]
        assert not before["is_manager"] and not has_chat_role(before)
        assert role_id in isolated[uid]["roles"]
    outsider = await cached_access("outsider", "tenant")
    subject = {"user_id": target} if principal == "user" else {"group_id": "editors"}
    path = "/api/v1/admin/roles/assign" + ("-group" if principal == "group" else "")
    payload = {**subject, "project_id": "tenant", "role_id": role_id}
    granted = await client.post(path, params={"domain_id": "default"}, json=payload)
    assert granted.status_code == 200, granted.text
    assert granted.json() == {"status": "assigned"}
    for uid in affected:
        current = await cached_access(uid, "tenant")
        assert role_id in current["roles"]
        assert current["is_manager"] is (role_id == "project_admin")
        assert has_chat_role(current) is (role_id == "lumen-chat_user")
        await assert_login_survives(role_env, uid, stored[uid])
    assert await cached_access("outsider", "tenant") == outsider
    for uid in stored:
        assert await cached_access(uid, "isolated") == isolated[uid]

    revoked = await client.delete(path, params={"domain_id": "default", **payload})
    assert revoked.status_code == 200, revoked.text
    assert revoked.json() == {"status": "revoked"}
    for uid in affected:
        current = await cached_access(uid, "tenant")
        assert role_id not in current["roles"]
        assert "member" in current["roles"]
        assert not current["is_manager"] and not has_chat_role(current)
        assert role_id in (await cached_access(uid, "isolated"))["roles"]
    assert await cached_access("outsider", "tenant") == outsider
    for uid, snapshot in stored.items():
        assert await cached_access(uid, "isolated") == isolated[uid]
        await assert_login_survives(role_env, uid, snapshot)
    assert [event["action"] for event in role_env.events] == ["role_assign", "role_revoke"]
    for uid in affected:
        assert f"afterglow:user:{uid}:domain:*:projects" in role_env.cleared
    assert not role_env.revoked


@pytest.mark.asyncio
@pytest.mark.parametrize("revoke_all", [False, True], ids=["owned-rotated-family", "all-user-families"])
async def test_explicit_revocation_still_removes_family_and_native_proof_after_role_change(role_env, revoke_all):
    p = role_env.provider
    _holder_fixture(p)
    add_chat_permission(p)
    p.edges.add(("custom", "lumen-chat_user"))
    stored = await session(role_env, "direct")
    unrelated = await session(role_env, "unaffected")
    assert has_chat_role(await cached_access("direct"))
    response = await role_env.client.delete("/api/v1/admin/roles/custom/implies/lumen-chat_user")
    assert response.status_code == 200
    assert not has_chat_role(await cached_access("direct"))
    await assert_login_survives(role_env, "direct", stored)

    if revoke_all:
        assert await session_store.revoke_user_sessions("direct") == 1
    else:
        # The session-list JTI may have rotated: its retained alias must still
        # remove the current family, not merely the already consumed record.
        assert await session_store.delete_session_owned("direct", "login-direct")
    assert await session_store.get_session("session-direct") is None
    assert await role_env.redis.get("afterglow:session-family:login-direct") is None
    assert await session_store.list_user_sessions("direct") == []
    assert "token-direct" not in p.native_tokens
    assert role_env.revoked == ["token-direct"]
    assert not await session_store.store_session(
        "after-revoke",
        "token-direct",
        "project",
        "direct",
        int(time.time()) + 3600,
        previous_jti="session-direct",
        timeout_seconds=7200,
        domain_id="default",
        identity_domain_id="home",
    )
    assert await session_store.get_session("after-revoke") is None
    await assert_login_survives(role_env, "unaffected", unrelated)


def existing_project_hierarchy(provider):
    for name in ("project_owner", "project_admin", "project_member", "project_reader"):
        provider.rows[name] = {"id": name, "name": name, "description": "existing " + name, "domain_id": None}
    provider.edges.update(
        {
            ("project_owner", "project_admin"),
            ("project_admin", "project_member"),
            ("project_member", "project_reader"),
            ("project_member", "member"),
            ("project_reader", "reader"),
        }
    )


@pytest.mark.asyncio
async def test_project_reader_custom_implication_survives_preset_application(role_env):
    p, client = role_env.provider, role_env.client
    existing_project_hierarchy(p)
    p.rows["audit-id"] = {"id": "audit-id", "name": "audit", "domain_id": None, "description": ""}
    linked = await client.put("/api/v1/admin/roles/project_reader/implies/audit-id")
    assert linked.status_code == 200, linked.text
    assert linked.json() == {"status": "created"}
    applied = await client.post("/api/v1/admin/roles/presets/apply")
    assert applied.status_code == 200, applied.text
    rows = {row["id"]: row for row in (await client.get("/api/v1/admin/roles")).json()}
    for parent in ("project_owner", "project_admin", "project_member", "project_reader"):
        assert "audit-id" in rows[parent]["inherited_role_ids"]
    assert rows["audit-id"]["parent_role_ids"] == ["project_reader"]
    assert "member" not in rows["project_reader"]["inherited_role_ids"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "target_name,target_domain",
    [
        ("admin", None),
        ("manager", None),
        ("member", None),
        ("MEMBER", None),
        ("project_admin", None),
        ("lumen-resources_admin", None),
        ("external_audit", "other-domain"),
    ],
)
async def test_custom_descendants_cannot_bypass_preset_authority_bounds(role_env, target_name, target_domain):
    p, client = role_env.provider, role_env.client
    existing_project_hierarchy(p)
    p.rows["audit-id"] = {"id": "audit-id", "name": "audit", "domain_id": None, "description": ""}
    p.rows["alias-id"] = {"id": "alias-id", "name": "external_alias", "domain_id": None, "description": ""}
    target = next((row["id"] for row in p.rows.values() if row["name"] == target_name), "target-id")
    if target == "target-id":
        p.rows[target] = {"id": target, "name": target_name, "domain_id": target_domain, "description": ""}
    p.edges.update({("audit-id", "alias-id"), ("alias-id", target)})
    response = await client.put("/api/v1/admin/roles/project_reader/implies/audit-id")
    assert response.status_code == 409
    assert ("project_reader", "audit-id") not in p.edges


@pytest.mark.asyncio
async def test_project_reader_principal_cannot_edit_global_role_implications(role_env):
    p = role_env.provider
    existing_project_hierarchy(p)
    p.rows["audit-id"] = {"id": "audit-id", "name": "audit", "domain_id": None, "description": ""}
    role_env.auth.update(is_system_admin=False, roles=["project_reader", "reader"])
    denied = await role_env.client.put("/api/v1/admin/roles/project_reader/implies/audit-id")
    assert denied.status_code == 403
    assert ("project_reader", "audit-id") not in p.edges


@pytest.mark.asyncio
async def test_role_area_grade_normalization_collision_and_legacy_metadata(role_env):
    p, client = role_env.provider, role_env.client
    response = await client.post("/api/v1/admin/roles", json={"name": " Way Gate _ Client Admin "})
    assert response.status_code == 201
    assert response.json()["name"] == "-way-gate-_-client-admin-"
    assert p.rows[response.json()["id"]]["name"] == "-way-gate-_-client-admin-"
    assert (await client.post("/api/v1/admin/roles", json={"name": "-WAY-GATE-_-CLIENT-ADMIN-"})).status_code == 409
    for name in ("area grade", "_reader", "area_", "area_user_extra", "영역_reader", "area/path_reader"):
        assert (await client.post("/api/v1/admin/roles", json={"name": name})).status_code == 422
    p.rows["custom"]["name"] = "Mixed Case Legacy"
    updated = await client.patch("/api/v1/admin/roles/custom", json={"description": "Metadata only"})
    assert updated.status_code == 200
    assert updated.json()["name"] == "Mixed Case Legacy"


@pytest.mark.asyncio
async def test_preset_preview_is_read_only_and_apply_reuses_ids_assignments_and_actual_dag(role_env):
    from copy import deepcopy

    from app.services.service_permissions import ROLE_IMPLICATIONS, SERVICE_ROLE_GRADES

    p, client = role_env.provider, role_env.client
    existing_project_hierarchy(p)
    p.assignments.append(
        {"user": {"id": "owner"}, "role": {"id": "project_owner"}, "scope": {"project": {"id": "tenant"}}}
    )
    existing_rows, existing_edges, assignments = deepcopy(p.rows), set(p.edges), deepcopy(p.assignments)
    preview = await client.get("/api/v1/admin/roles/presets")
    assert preview.status_code == 200
    assert {"prior": "waygate_admin", "implied": "waygate_editor"} not in preview.json()["implications"]
    assert p.rows == existing_rows and p.edges == existing_edges and p.assignments == assignments
    applied = await client.post("/api/v1/admin/roles/presets/apply")
    assert applied.status_code == 200, applied.text
    for rid, row in existing_rows.items():
        assert p.rows[rid] == row
    assert p.assignments == assignments
    rows = {row["name"]: row for row in applied.json()["roles"] if row["domain_id"] is None}
    assert {(rows[prior]["id"], rows[child]["id"]) for prior, child in ROLE_IMPLICATIONS} <= p.edges
    for service in SERVICE_ROLE_GRADES:
        assert rows[service + "_admin"]["inherited_role_ids"] == []
    repeated = await client.post("/api/v1/admin/roles/presets/apply")
    assert repeated.status_code == 200
    assert repeated.json()["created_roles"] == [] and repeated.json()["created_implications"] == []
    assert p.assignments == assignments


@pytest.mark.asyncio
async def test_service_preset_cutover_preserves_ids_grants_custom_edges_and_login(role_env):
    from copy import deepcopy

    p, client = role_env.provider, role_env.client
    existing_project_hierarchy(p)
    assert (await client.post("/api/v1/admin/roles/presets/apply")).status_code == 200
    by_name = {row["name"]: row["id"] for row in p.rows.values()}
    retired = {
        (by_name["waygate_admin"], by_name["waygate_editor"]),
        (by_name["waygate_editor"], by_name["waygate-clients_editor"]),
        (by_name["waygate-clients_editor"], by_name["waygate_reader"]),
        (by_name["waygate_reader"], by_name["waygate-inventory_reader"]),
    }
    custom = (by_name["waygate_admin"], "other")
    p.edges.update(retired | {custom})
    p.assignments.append(
        {"user": {"id": "operator"}, "role": {"id": by_name["waygate_admin"]}, "scope": {"project": {"id": "tenant"}}}
    )
    roles, grants = deepcopy(p.rows), deepcopy(p.assignments)
    login = await session(role_env, "operator")

    response = await client.post("/api/v1/admin/roles/presets/apply")
    assert response.status_code == 200, response.text
    assert not p.edges.intersection(retired)
    assert custom in p.edges
    assert ("project_owner", "project_admin") in p.edges
    assert p.rows == roles and p.assignments == grants
    assert {tuple(item.values()) for item in response.json()["removed_implications"]} == {
        ("waygate_admin", "waygate_editor"),
        ("waygate_editor", "waygate-clients_editor"),
        ("waygate-clients_editor", "waygate_reader"),
        ("waygate_reader", "waygate-inventory_reader"),
    }
    await assert_login_survives(role_env, "operator", login)
    again = await client.post("/api/v1/admin/roles/presets/apply")
    assert again.status_code == 200 and again.json()["removed_implications"] == []


@pytest.mark.asyncio
async def test_preset_rejects_unsafe_existing_service_role_before_any_creation(role_env):
    p, client = role_env.provider, role_env.client
    p.rows["unsafe-reader"] = {"id": "unsafe-reader", "name": "lumen_reader", "domain_id": None, "description": ""}
    p.edges.update({("unsafe-reader", "alias"), ("alias", "admin")})
    before = dict(p.rows)
    response = await client.post("/api/v1/admin/roles/presets/apply")
    assert response.status_code == 409
    assert p.rows == before


@pytest.mark.asyncio
async def test_preset_partial_provider_failure_reports_retained_roles_and_retry_is_additive(role_env):
    p, client = role_env.provider, role_env.client
    existing_project_hierarchy(p)
    p.edges.discard(("project_owner", "project_admin"))
    p.write_status = 500
    failed = await client.post("/api/v1/admin/roles/presets/apply")
    assert failed.status_code == 503
    detail = failed.json()["detail"]
    retained = {row["name"]: row["id"] for row in p.rows.values()}
    assert "waygate_admin" in detail["created_roles"]
    assert retained["project_owner"] == "project_owner"
    p.write_status = None
    retried = await client.post("/api/v1/admin/roles/presets/apply")
    assert retried.status_code == 200
    assert retried.json()["created_roles"] == []
    assert {row["name"]: row["id"] for row in p.rows.values()} == retained


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path", [("GET", "/roles/presets"), ("POST", "/roles/presets/apply")])
async def test_presets_require_verified_system_admin(role_env, method, path):
    role_env.auth["is_system_admin"] = False
    response = await role_env.client.request(method, "/api/v1/admin" + path)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_generic_identity_assignment_and_edge_api_cannot_bypass_owner_workflow(role_env):
    p, client = role_env.provider, role_env.client
    existing_project_hierarchy(p)
    p.rows["owner-alias"] = {"id": "owner-alias", "name": "owner-alias_admin", "domain_id": None, "description": ""}
    p.edges.add(("owner-alias", "project_owner"))
    p.get_domain = lambda did: SimpleNamespace(id=did, name="Default")
    p.get_user = lambda uid: SimpleNamespace(id=uid, domain_id="default")
    p.get_project = lambda pid: SimpleNamespace(id=pid, domain_id="default")
    p.get_role = lambda rid: SimpleNamespace(**p.rows[rid])
    for role_id in ("project_owner", "owner-alias"):
        response = await client.post(
            "/api/v1/admin/roles/assign?domain_id=default",
            json={"user_id": "member", "project_id": "tenant", "role_id": role_id},
        )
        assert response.status_code == 409
        response = await client.delete(
            "/api/v1/admin/roles/assign",
            params={"domain_id": "default", "user_id": "member", "project_id": "tenant", "role_id": role_id},
        )
        assert response.status_code == 409
    assert (await client.delete("/api/v1/admin/roles/owner-alias/implies/project_owner")).status_code == 409
    assert ("owner-alias", "project_owner") in p.edges


@pytest.mark.asyncio
async def test_rename_cannot_create_owner_authority_from_existing_assigned_role(role_env):
    p, client = role_env.provider, role_env.client
    p.assignments = [{"role": {"id": "custom"}, "user": {"id": "member"}, "scope": {"project": {"id": "tenant"}}}]
    response = await client.patch("/api/v1/admin/roles/custom", json={"name": "project_owner"})
    assert response.status_code == 409
    assert p.rows["custom"]["name"] == "custom"


@pytest.mark.asyncio
async def test_manager_owner_implication_and_owner_alias_rename_are_explicitly_blocked(role_env):
    p, client = role_env.provider, role_env.client
    existing_project_hierarchy(p)
    response = await client.put("/api/v1/admin/roles/manager/implies/project_owner")
    assert response.status_code == 409
    assert ("manager", "project_owner") not in p.edges
    p.edges.add(("alias", "project_owner"))
    response = await client.patch("/api/v1/admin/roles/alias", json={"name": "renamed"})
    assert response.status_code == 409
    assert p.rows["alias"]["name"] == "alias"
    p.rows["project_owner"]["name"] = "PROJECT_OWNER"
    response = await client.delete("/api/v1/admin/roles/alias/implies/project_owner")
    assert response.status_code == 409
    assert ("alias", "project_owner") in p.edges
