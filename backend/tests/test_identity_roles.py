"""HTTP role lifecycle/security regressions with a stateful Keystone boundary.

The provider fixture models the installed SDK/native wire API, not service-function
forwarding. Session tests use the real session store against isolated fake Redis.
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

from app.api.deps import get_os_conn, get_token_info
from app.api.identity.admin_identity import router
from app.services import identity_roles, keystone, session_store


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

    def role_assignments(self, role_id, effective=False):
        if self.assignments_error:
            raise RuntimeError("assignment metadata unavailable")
        result = []
        for assignment in self.assignments:
            if assignment["role"]["id"] != role_id:
                continue
            if effective and "group" in assignment:
                for uid in self.groups[assignment["group"]["id"]]:
                    result.append({"role": assignment["role"], "user": {"id": uid}, "scope": assignment["scope"]})
            else:
                result.append(assignment)
        return iter(result)

    def group_users(self, gid):
        return iter(SimpleNamespace(id=uid) for uid in self.groups[gid])


@pytest.fixture
async def role_env(monkeypatch):
    provider = IdentityProvider()
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

    async def get_redis():
        return redis

    async def record(**kwargs):
        events.append(kwargs)

    async def invalidate(key):
        cleared.append(key)

    events, cleared, revoked = [], [], []
    monkeypatch.setattr(session_store, "_get_redis", get_redis)
    # Actual session deletion still runs; token revocation is an external boundary.
    monkeypatch.setattr(keystone, "revoke_token", revoked.append)
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
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield SimpleNamespace(
            provider=provider, redis=redis, client=client, auth=state, events=events, cleared=cleared, revoked=revoked
        )
    await redis.close()


async def session(uid):
    await session_store.store_session("session-" + uid, "token-" + uid, "project", uid, int(time.time()) + 3600)


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
    assert not role_env.events


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
    assert (await client.post("/api/v1/admin/roles", json={"name": "custom"})).status_code == 409
    created = await client.post("/api/v1/admin/roles", json={"name": "New Role", "description": "Details"})
    assert created.status_code == 201
    rid = created.json()["id"]
    assert created.json()["implied_role_ids"] == []
    assert (await client.patch(f"/api/v1/admin/roles/{rid}", json={"name": "Renamed"})).json()["name"] == "Renamed"
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
        {"afterglow:admin:roles", "afterglow:admin:identity:summary", identity_roles.VISIBILITY_KEY},
    )
    created = await client.post("/api/v1/admin/roles", json={"name": "Audited"})
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
        {
            "role": {"id": "other"},
            "group": {"id": "g"},
            "scope": {"domain": {"id": "d"}, "OS-INHERIT:inherited_to": "projects"},
        },
    ]


@pytest.mark.asyncio
async def test_edge_removal_revokes_real_sessions_for_group_inherited_and_ancestor_holders(role_env):
    p, client = role_env.provider, role_env.client
    _holder_fixture(p)
    p.edges.add(("custom", "reader"))
    for uid in ("direct", "group-user", "unaffected"):
        await session(uid)
    response = await client.delete("/api/v1/admin/roles/custom/implies/reader")
    assert response.status_code == 200
    assert await session_store.get_session("session-direct") is None
    assert await session_store.get_session("session-group-user") is None
    assert await session_store.get_session("session-unaffected") is not None
    assert set(role_env.revoked) == {"token-direct", "token-group-user"}


@pytest.mark.asyncio
async def test_adding_lower_edge_keeps_holder_sessions(role_env):
    p, client = role_env.provider, role_env.client
    _holder_fixture(p)
    p.assignments_error = True  # Adding a lower edge needs no recipient lookup.
    await session("direct")
    assert (await client.put("/api/v1/admin/roles/custom/implies/reader")).status_code == 200
    assert await session_store.get_session("session-direct") is not None
    assert not role_env.revoked


@pytest.mark.asyncio
async def test_rename_revokes_holders_and_unknown_recipients_block_removal(role_env):
    p, client = role_env.provider, role_env.client
    p.assignments = [{"role": {"id": "custom"}, "user": {"id": "holder"}, "scope": {"project": {"id": "p"}}}]
    await session("holder")
    assert (await client.patch("/api/v1/admin/roles/custom", json={"name": "Renamed"})).status_code == 200
    assert await session_store.get_session("session-holder") is None
    p.edges.add(("custom", "reader"))
    p.assignments_error = True
    assert (await client.delete("/api/v1/admin/roles/custom/implies/reader")).status_code == 503
    assert ("custom", "reader") in p.edges
    assert (await client.patch("/api/v1/admin/roles/custom", json={"name": "Again"})).status_code == 503
    assert p.rows["custom"]["name"] == "Renamed"
    p.edges.clear()
    assert (await client.delete("/api/v1/admin/roles/custom")).status_code == 503
    assert "custom" in p.rows


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

    async def failed_revoke(uid):
        raise RuntimeError("session deletion failed after preflight")

    monkeypatch.setattr(session_store, "revoke_user_sessions", failed_revoke)
    response = await role_env.client.delete("/api/v1/admin/roles/custom/implies/reader")
    assert response.status_code == 503
    assert "applied" in response.json()["detail"]
    assert ("custom", "reader") not in p.edges
    assert not role_env.events


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
        body = {"name": "New"} if method == "POST" else {"description": "x"} if method == "PATCH" else None
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
    from app.main import app

    p = IdentityProvider()
    _trusted(monkeypatch, p)
    _memory_cache(monkeypatch, {})
    assert await identity_roles.visible_role_names(["custom"], False) == ["custom"]  # warm old graph
    # Created and assigned through the CLI: safe external role, then an external alias.
    p.rows["cli-role"] = {"id": "cli-role", "name": "cli-role", "description": "", "domain_id": None}
    p.rows["cli-alias"] = {"id": "cli-alias", "name": "cli-alias", "description": "", "domain_id": None}
    p.edges.add(("cli-alias", "admin"))
    token = {
        "user_id": "u",
        "username": "u",
        "project_id": "p",
        "project_name": "P",
        "roles": ["member", "cli-role", "cli-alias", "never-listed"],
        "is_system_admin": False,
        "auth_method": "password",
    }
    app.dependency_overrides[get_token_info] = lambda: token
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/auth/me")
    finally:
        app.dependency_overrides.pop(get_token_info, None)
    assert response.status_code == 200
    assert response.json()["roles"] == ["member", "cli-role"]


@pytest.mark.asyncio
async def test_cancelled_edge_removal_finishes_required_session_invalidation(role_env, monkeypatch):
    provider = role_env.provider
    _holder_fixture(provider)
    provider.edges.add(("custom", "reader"))
    await session("direct")
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
    request = asyncio.create_task(role_env.client.delete("/api/v1/admin/roles/custom/implies/reader"))
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

    assert ("custom", "reader") not in provider.edges
    assert await session_store.get_session("session-direct") is None
    assert "token-direct" in role_env.revoked
    assert identity_roles.VISIBILITY_KEY in role_env.cleared
