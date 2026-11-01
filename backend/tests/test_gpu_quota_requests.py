"""Durable manager requests and manual admin decisions never write cloud policy."""

import asyncio
import copy
import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api import deps
from app.api.identity.gpu_quota_requests import router
from app.models.compute_pools import MAX_AMOUNT
from app.models.gpu_quota_requests import GpuQuotaRequest
from app.services import compute_pools, domain_iam, flavor_automation_policy, identity_roles
from app.services import gpu_quota_requests as queue
from tests.test_compute_pools import AUDIO, GPU, NativeProvider

LIVE_SESSION = queue._live_session
SESSION_SIGNATURE = queue._session_signature

MANAGER = {
    "user_id": "manager",
    "domain_id": "org",
    "identity_domain_id": "accounts",
    "project_id": "p1",
    "connection_project_id": "p1",
    "token": "private-native-token",
    "refresh_jti": "private-session-jti",
    "is_domain_manager": True,
    "is_system_admin": False,
}
ADMIN = {**MANAGER, "user_id": "reviewer", "is_system_admin": True}
PUBLIC_FIELDS = {
    "id",
    "domain_id",
    "project_id",
    "requester_id",
    "gpu_profile_name",
    "resource_class",
    "additional",
    "baseline_limit",
    "target_limit",
    "pool_revision",
    "reason",
    "status",
    "created_at",
    "reviewer_id",
    "reviewed_at",
    "note",
}


@pytest_asyncio.fixture
async def store(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(GpuQuotaRequest.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(queue, "get_session_factory", lambda: factory)
    monkeypatch.setattr(queue, "is_db_available", lambda: True)
    yield factory
    await engine.dispose()


@pytest.fixture
def native(monkeypatch):
    provider = NativeProvider()
    provider.capabilities["gpu_profiles"][0].update(
        enabled=True,
        extra_specs={"pci_passthrough:alias": "GA106:1,GA106-audio:1"},
        alias_resource_classes={"GA106": GPU, "GA106-audio": AUDIO},
    )
    provider.session_available = True
    provider.session_signature = "session-generation-1"
    provider.manager_allowed = True
    provider.admin_allowed = True
    provider.lock_owned = True
    provider.on_authorize = None
    provider.authorizations = 0
    provider.fresh_sessions = 0
    lock = asyncio.Lock()

    async def capabilities():
        return copy.deepcopy(provider.capabilities)

    @asynccontextmanager
    async def operator():
        yield provider.conn

    @asynccontextmanager
    async def graph(_conn):
        async with lock:

            class Lease:
                async def assert_owned(self):
                    if not provider.lock_owned:
                        raise HTTPException(409, "graph_lock_lost")

            yield Lease()

    async def manager_context(info):
        provider.authorizations += 1
        if provider.on_authorize:
            provider.on_authorize(provider.authorizations)
        if not provider.manager_allowed or not info.get("is_domain_manager"):
            raise HTTPException(403, "manager_revoked")
        return {"domain_id": info["domain_id"], "is_domain_manager": True}

    async def admin_context(info):
        provider.authorizations += 1
        if provider.on_authorize:
            provider.on_authorize(provider.authorizations)
        if not provider.admin_allowed or not info.get("is_system_admin"):
            raise HTTPException(403, "admin_revoked")
        return info

    async def live_session(info):
        provider.fresh_sessions += 1
        if not provider.session_available:
            raise HTTPException(401, "session_revoked")
        return provider.session_signature

    monkeypatch.setattr(compute_pools, "_operator", operator)
    monkeypatch.setattr(identity_roles, "_graph_lock", graph)
    monkeypatch.setattr(flavor_automation_policy, "capabilities", capabilities)
    monkeypatch.setattr(domain_iam, "context", manager_context)
    monkeypatch.setattr(deps, "require_admin", admin_context)
    monkeypatch.setattr(queue, "_live_session", live_session)
    monkeypatch.setattr(queue, "_session_signature", live_session)
    return provider


@pytest_asyncio.fixture
async def client(store, native):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    async def actor():
        return copy.deepcopy(MANAGER)

    async def admin():
        return copy.deepcopy(ADMIN)

    app.dependency_overrides[deps.require_domain_manager] = actor
    # Router imported this function before the fixture monkeypatched the module.
    from app.api.identity import gpu_quota_requests as endpoints

    app.dependency_overrides[endpoints.require_admin] = admin
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
        yield http


async def submit(client, **updates):
    return await client.post(
        "/api/v1/iam/gpu-quota-requests",
        json={
            "project_id": "p1",
            "resource_class": GPU,
            "additional": 2,
            "reason": "Training capacity",
            **updates,
        },
    )


async def decide(client, request_id, status="fulfilled", **updates):
    return await client.post(
        f"/api/v1/admin/gpu-quota-requests/{request_id}/resolve",
        json={
            "status": status,
            "note": "Reviewed manual quota adjustment",
            **updates,
        },
    )


async def persisted(store, request_id):
    async with store() as session:
        return await session.get(GpuQuotaRequest, request_id)


def assert_no_native_writes(native, original):
    assert native.domain == original
    assert all(method == "GET" for method, _, _ in native.calls)


@pytest.mark.asyncio
@pytest.mark.parametrize("cap,baseline,target", [(None, 4, 6), (0, 0, 2), (2, 2, 4)])
async def test_create_records_inherited_and_explicit_absolute_target(client, native, store, cap, baseline, target):
    if cap is not None:
        native.domain[compute_pools.POLICY_KEY]["project_limits"] = {"p1": {GPU: cap}}
    original = copy.deepcopy(native.domain)
    response = await submit(client)
    assert response.status_code == 201, response.text
    dto = response.json()
    assert set(dto) == PUBLIC_FIELDS
    assert dto["domain_id"] == "org" and dto["project_id"] == "p1" and dto["requester_id"] == "manager"
    assert dto["baseline_limit"] == baseline and dto["target_limit"] == target and dto["additional"] == 2
    assert dto["gpu_profile_name"] == "3060lhr" and dto["resource_class"] == GPU and dto["pool_revision"] == 0
    assert dto["status"] == "pending" and dto["reviewed_at"] is None and dto["reviewer_id"] is None
    assert datetime.fromisoformat(dto["created_at"]).utcoffset() == timedelta(0)
    assert (await persisted(store, dto["id"])).target_limit == target
    assert "token" not in response.text and "fingerprint" not in response.text
    assert response.headers["cache-control"] == "no-store, private"
    assert_no_native_writes(native, original)


@pytest.mark.asyncio
async def test_missing_domain_gpu_limit_is_verified_zero_not_unavailable(client, native):
    native.domain[compute_pools.POLICY_KEY]["limits"].pop(GPU)
    response = await submit(client)
    assert response.status_code == 201
    assert response.json()["baseline_limit"] == 0 and response.json()["target_limit"] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [-1, MAX_AMOUNT, MAX_AMOUNT - 1])
async def test_unlimited_and_target_overflow_are_not_increasable(client, native, limit):
    native.domain[compute_pools.POLICY_KEY]["limits"][GPU] = limit
    assert (await submit(client)).status_code == 409
    assert (await client.get("/api/v1/iam/gpu-quota-requests")).json()["items"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "updates",
    [
        {"additional": 0},
        {"additional": -1},
        {"additional": True},
        {"additional": "2"},
        {"additional": 2.0},
        {"additional": MAX_AMOUNT + 1},
        {"project_id": "../p1"},
        {"project_id": 1},
        {"project_id": "p" * 65},
        {"resource_class": "3060 LHR"},
        {"resource_class": "CPU"},
        {"reason": None},
        {"reason": "x" * 2001},
        {"domain_id": "other"},
        {"requester_id": "other"},
        {"target_limit": 99},
    ],
)
async def test_create_strict_bounded_body(client, updates):
    response = await submit(client, **updates)
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid IAM request"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change,expected",
    [
        ("cross_domain", 403),
        ("disabled_project", 409),
        ("missing_project", 409),
        ("disabled_domain", 503),
        ("disabled_profile", 409),
        ("companion", 409),
        ("unready", 503),
        ("partial_directory", 503),
        ("unknown_usage", 503),
        ("underflow", 503),
    ],
)
async def test_unavailable_and_unapproved_targets_never_become_zero(client, native, change, expected):
    updates = {}
    if change == "cross_domain":
        native.projects[0]["domain_id"] = "other"
    elif change == "disabled_project":
        native.projects[0]["enabled"] = False
    elif change == "missing_project":
        updates["project_id"] = "missing"
    elif change == "disabled_domain":
        native.domain["enabled"] = False
    elif change == "disabled_profile":
        native.capabilities["gpu_profiles"][0]["enabled"] = False
    elif change == "companion":
        updates["resource_class"] = AUDIO
    elif change == "unready":
        native.capabilities["policy_ready"] = False
    elif change == "partial_directory":
        native.list_flags["truncated"] = True
    elif change == "unknown_usage":
        native.usages["p1"]["CUSTOM_UNKNOWN"] = 1
    elif change == "underflow":
        native.domain[compute_pools.POLICY_KEY]["limits"][GPU] = -2
    original = copy.deepcopy(native.domain)
    response = await submit(client, **updates)
    assert response.status_code == expected, response.text
    assert_no_native_writes(native, original)


@pytest.mark.asyncio
@pytest.mark.parametrize("state,baseline", [("paused", 4), ("unmanaged", 0)])
async def test_inactive_pool_accepts_request_but_requires_activation_to_fulfill(client, native, state, baseline):
    if state == "paused":
        native.domain[compute_pools.POLICY_KEY]["enabled"] = False
    else:
        native.domain.pop(compute_pools.POLICY_KEY)
    original = copy.deepcopy(native.domain)
    created = await submit(client)
    assert created.status_code == 201, created.text
    assert created.json()["baseline_limit"] == baseline
    assert created.json()["target_limit"] == baseline + 2
    assert (await decide(client, created.json()["id"])).status_code == 409
    assert_no_native_writes(native, original)


@pytest.mark.asyncio
async def test_manager_authority_revocation_and_current_domain_are_rechecked(client, native, store, monkeypatch):
    native.on_authorize = lambda count: setattr(native, "manager_allowed", False) if count == 2 else None
    response = await submit(client)
    assert response.status_code == 403
    async with store() as session:
        assert (await session.execute(select(GpuQuotaRequest))).scalars().all() == []
    native.manager_allowed = True
    native.on_authorize = None

    async def wrong_context(info):
        return {"domain_id": "other", "is_domain_manager": True}

    monkeypatch.setattr(domain_iam, "context", wrong_context)
    assert (await submit(client)).status_code == 403
    assert (await client.get("/api/v1/iam/gpu-quota-requests")).status_code == 403


@pytest.mark.asyncio
async def test_changed_session_and_lost_lease_cannot_persist(client, native):
    native.on_authorize = lambda count: setattr(native, "session_signature", "new-generation")
    assert (await submit(client)).status_code == 401
    native.on_authorize = None
    native.lock_owned = False
    assert (await submit(client)).status_code == 409
    native.lock_owned = True
    native.session_available = False
    assert (await submit(client)).status_code == 401


@pytest.mark.asyncio
async def test_pool_revision_drift_before_persist_is_conflict(client, native):
    def drift(count):
        if count == 2:
            native.domain[compute_pools.POLICY_KEY]["revision"] += 1

    native.on_authorize = drift
    assert (await submit(client)).status_code == 409


@pytest.mark.asyncio
async def test_manual_quota_adjustment_then_fulfill_only_records_decision(client, native, store):
    created = (await submit(client)).json()
    original = copy.deepcopy(native.domain)
    assert (await decide(client, created["id"])).status_code == 409
    assert (await persisted(store, created["id"])).status == "pending"
    assert_no_native_writes(native, original)
    # The administrator's separate existing control already changed native metadata.
    native.domain[compute_pools.POLICY_KEY]["limits"][GPU] = 6
    native.domain[compute_pools.POLICY_KEY]["revision"] = 1
    adjusted = copy.deepcopy(native.domain)
    response = await decide(client, created["id"])
    assert response.status_code == 200, response.text
    dto = response.json()
    assert dto["status"] == "fulfilled" and dto["reviewer_id"] == "reviewer"
    assert dto["target_limit"] == 6 and dto["pool_revision"] == 0
    assert datetime.fromisoformat(dto["reviewed_at"]).utcoffset() == timedelta(0)
    assert (await persisted(store, created["id"])).status == "fulfilled"
    assert_no_native_writes(native, adjusted)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "domain_limit,cap,expected", [(6, 5, 409), (5, 6, 503), (-1, 6, 200), (6, -1, 503), (-1, -1, 200)]
)
async def test_fulfill_requires_both_domain_and_effective_project_target(client, native, domain_limit, cap, expected):
    created = (await submit(client)).json()
    policy = native.domain[compute_pools.POLICY_KEY]
    policy["limits"][GPU] = domain_limit
    policy["project_limits"] = {"p1": {GPU: cap}}
    policy["revision"] += 1
    # Invalid project caps above a finite domain ceiling are unavailable evidence,
    # not grounds for approval (the explicit row remains pending).
    response = await decide(client, created["id"])
    assert response.status_code == expected, response.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change", ["domain", "disabled", "profile_name", "profile_contract", "profile_disabled", "pool_paused"]
)
async def test_target_identity_and_approved_profile_cannot_drift(client, native, store, change):
    created = (await submit(client)).json()
    native.domain[compute_pools.POLICY_KEY]["limits"][GPU] = 10
    if change == "domain":
        native.projects[0]["domain_id"] = "other"
    elif change == "disabled":
        native.projects[0]["enabled"] = False
    elif change == "profile_name":
        native.capabilities["gpu_profiles"][0]["name"] = "replacement"
    elif change == "profile_contract":
        native.capabilities["gpu_profiles"][0]["extra_specs"]["hw:cpu_policy"] = "dedicated"
    elif change == "profile_disabled":
        native.capabilities["gpu_profiles"][0]["enabled"] = False
    elif change == "pool_paused":
        native.domain[compute_pools.POLICY_KEY]["enabled"] = False
    assert (await decide(client, created["id"])).status_code == 409
    assert (await persisted(store, created["id"])).status == "pending"


@pytest.mark.asyncio
async def test_reject_does_not_read_or_require_current_pool(client, native, monkeypatch):
    created = (await submit(client)).json()
    original = copy.deepcopy(native.domain)

    async def unavailable():
        raise HTTPException(503, "policy_unavailable")

    monkeypatch.setattr(flavor_automation_policy, "capabilities", unavailable)
    response = await decide(client, created["id"], "rejected")
    assert response.status_code == 200 and response.json()["status"] == "rejected"
    replay = await decide(client, created["id"], "rejected", note="cannot overwrite winner")
    assert replay.json() == response.json()
    assert (await decide(client, created["id"], "fulfilled")).status_code == 409
    assert_no_native_writes(native, original)


@pytest.mark.asyncio
async def test_competing_decisions_never_overwrite_winner(client, native):
    created = (await submit(client)).json()
    native.domain[compute_pools.POLICY_KEY]["limits"][GPU] = 6
    responses = await asyncio.gather(
        decide(client, created["id"], "fulfilled"), decide(client, created["id"], "rejected")
    )
    assert sorted(response.status_code for response in responses) == [200, 409]
    winner = next(response.json() for response in responses if response.status_code == 200)
    replay = await decide(client, created["id"], winner["status"], note="replay does not replace audit note")
    assert replay.status_code == 200 and replay.json() == winner


@pytest.mark.asyncio
async def test_admin_authority_revocation_prevents_list_and_decision(client, native):
    created = (await submit(client)).json()
    native.admin_allowed = False
    assert (await client.get("/api/v1/admin/gpu-quota-requests")).status_code == 403
    assert (await decide(client, created["id"], "rejected")).status_code == 403


@pytest.mark.asyncio
async def test_history_scopes_to_current_domain_and_survives_pool_unavailability(client, native, store, monkeypatch):
    created = (await submit(client)).json()
    async with store() as session:
        source = await session.get(GpuQuotaRequest, created["id"])
        foreign = {column.name: getattr(source, column.name) for column in GpuQuotaRequest.__table__.columns}
        foreign.update(id=uuid4().hex, domain_id="other", project_id="elsewhere")
        session.add(GpuQuotaRequest(**foreign))
        await session.commit()

    async def unavailable():
        raise HTTPException(503, "policy_unavailable")

    monkeypatch.setattr(flavor_automation_policy, "capabilities", unavailable)
    manager = await client.get("/api/v1/iam/gpu-quota-requests?status=all")
    assert manager.status_code == 200 and [row["id"] for row in manager.json()["items"]] == [created["id"]]
    admin = await client.get("/api/v1/admin/gpu-quota-requests?status=all")
    assert admin.status_code == 200 and len(admin.json()["items"]) == 2
    foreign_id = next(row["id"] for row in admin.json()["items"] if row["domain_id"] == "other")
    assert (await client.get(f"/api/v1/iam/gpu-quota-requests?cursor={foreign_id}")).status_code == 400


@pytest.mark.asyncio
async def test_cursor_page_is_bounded_and_total_ordered(client, store):
    created = (await submit(client)).json()
    async with store() as session:
        source = await session.get(GpuQuotaRequest, created["id"])
        values = {column.name: getattr(source, column.name) for column in GpuQuotaRequest.__table__.columns}
        for index in range(55):
            session.add(
                GpuQuotaRequest(**{**values, "id": f"{index:032x}", "created_at": datetime(2020, 1, 1, tzinfo=UTC)})
            )
        await session.commit()
    first = (await client.get("/api/v1/iam/gpu-quota-requests?status=all")).json()
    assert len(first["items"]) == 50 and first["next_cursor"] == first["items"][-1]["id"]
    second = (await client.get(f"/api/v1/iam/gpu-quota-requests?status=all&cursor={first['next_cursor']}")).json()
    assert len(second["items"]) == 6 and second["next_cursor"] is None
    assert not {row["id"] for row in first["items"]} & {row["id"] for row in second["items"]}
    assert (await client.get("/api/v1/iam/gpu-quota-requests?cursor=bad")).status_code == 422
    assert (await client.get("/api/v1/iam/gpu-quota-requests?status=unknown")).status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["unconfigured", "breaker", "missing_schema", "query_error"])
async def test_database_unavailable_is_never_empty_or_success(client, native, monkeypatch, failure):
    if failure == "unconfigured":
        monkeypatch.setattr(queue, "get_session_factory", lambda: None)
    elif failure == "breaker":
        monkeypatch.setattr(queue, "is_db_available", lambda: False)
    elif failure == "missing_schema":
        factory = queue.get_session_factory()
        async with factory() as session:
            await session.execute(text("DROP TABLE gpu_quota_requests"))
            await session.commit()
    else:

        class BrokenSession:
            async def __aenter__(self):
                raise RuntimeError("private-db-credential")

            async def __aexit__(self, *_):
                return None

        monkeypatch.setattr(queue, "get_session_factory", lambda: BrokenSession)
    for response in (
        await submit(client),
        await client.get("/api/v1/iam/gpu-quota-requests"),
        await client.get("/api/v1/admin/gpu-quota-requests"),
        await decide(client, "0" * 32, "rejected"),
    ):
        assert response.status_code == 503
        assert "private-db-credential" not in response.text


@pytest.mark.asyncio
async def test_stalled_profile_policy_read_is_bounded_and_releases_graph_lock(client, native, monkeypatch):
    async def stalled_policy():
        await asyncio.Event().wait()

    original = flavor_automation_policy.capabilities
    monkeypatch.setattr(queue, "_STORAGE_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(flavor_automation_policy, "capabilities", stalled_policy)
    response = await submit(client)
    assert response.status_code == 503
    assert response.json()["detail"] == "gpu_quota_request_policy_unavailable"
    monkeypatch.setattr(flavor_automation_policy, "capabilities", original)
    assert (await submit(client)).status_code == 201


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["create", "list", "resolve"])
@pytest.mark.parametrize(
    "change", ["renew", "scope", "provider", "deleted", "blacklisted", "empty_proof", "blank_proof"]
)
async def test_session_token_renewal_and_scope_change_during_queue_io(
    client, store, native, monkeypatch, _fake_redis_global, stage, change
):
    """Native-proof refresh is not a logout; real session/scope loss stays fenced."""
    info = copy.deepcopy(MANAGER)
    key = f"afterglow:refresh:{info['refresh_jti']}"
    session = {
        "user_id": info["user_id"],
        "domain_id": info["domain_id"],
        "identity_domain_id": info["identity_domain_id"],
        "project_id": info["project_id"],
        "family_id": "test-family",
        "scope_revision": 0,
        "keystone_token": "old-native-proof",
    }
    await _fake_redis_global.set(key, json.dumps(session), ex=60)
    native_user = [info["user_id"]]

    def validate(_token, *, project_id, operation):
        return {"user_id": native_user[0], "identity_domain_id": "accounts", "project_id": project_id}

    monkeypatch.setattr(queue, "_session_signature", SESSION_SIGNATURE)
    monkeypatch.setattr(queue, "_live_session", LIVE_SESSION)
    monkeypatch.setattr(queue.keystone, "validate_token", validate)
    created = (await submit(client)).json() if stage != "create" else None
    if stage == "resolve":
        session["user_id"] = native_user[0] = ADMIN["user_id"]
        await _fake_redis_global.set(key, json.dumps(session), ex=60)

    changed = False

    async def change_session():
        nonlocal changed
        if changed:
            return
        changed = True
        if change == "renew":
            assert await queue.session_store.update_session_token(
                info["refresh_jti"], "renewed-native-proof", expected_token="old-native-proof"
            )
        elif change == "deleted":
            await _fake_redis_global.delete(key)
        else:
            current = json.loads(await _fake_redis_global.get(key))
            if change == "scope":
                current["scope_revision"] = 1
            elif change == "provider":
                current["provider_revision"] = 1
            elif change == "blacklisted":
                current["blacklisted"] = True
            else:
                current["keystone_token"] = "   " if change == "blank_proof" else ""
            await _fake_redis_global.set(key, json.dumps(current), ex=60)

    class ChangingSession(AsyncSession):
        async def flush(self, *args, **kwargs):
            result = await super().flush(*args, **kwargs)
            if stage == "create":
                await change_session()
            return result

        async def execute(self, statement, *args, **kwargs):
            result = await super().execute(statement, *args, **kwargs)
            if (stage == "resolve" and getattr(statement, "is_update", False)) or (
                stage == "list" and getattr(statement, "is_select", False)
            ):
                await change_session()
            return result

    factory = async_sessionmaker(store.kw["bind"], class_=ChangingSession, expire_on_commit=False)
    monkeypatch.setattr(queue, "get_session_factory", lambda: factory)
    if stage == "create":
        response = await submit(client)
    elif stage == "list":
        response = await client.get("/api/v1/iam/gpu-quota-requests")
    else:
        response = await decide(client, created["id"], "rejected")
    assert changed
    expected_status = (201 if stage == "create" else 200) if change == "renew" else 401
    assert response.status_code == expected_status, response.text
    async with store() as db:
        rows = (await db.execute(select(GpuQuotaRequest))).scalars().all()
    if stage == "create":
        assert len(rows) == (1 if change == "renew" else 0)
    elif stage == "resolve":
        assert len(rows) == 1 and rows[0].status == ("rejected" if change == "renew" else "pending")
    assert all(method == "GET" for method, _, _ in native.calls)


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["create", "resolve"])
async def test_session_revoked_during_sql_write_cannot_commit(client, store, native, monkeypatch, stage):
    created = (await submit(client)).json() if stage == "resolve" else None
    entered, release = asyncio.Event(), asyncio.Event()

    class PausedWriteSession(AsyncSession):
        async def flush(self, *args, **kwargs):
            result = await super().flush(*args, **kwargs)
            if stage == "create":
                entered.set()
                await release.wait()
            return result

        async def execute(self, statement, *args, **kwargs):
            result = await super().execute(statement, *args, **kwargs)
            if stage == "resolve" and getattr(statement, "is_update", False):
                entered.set()
                await release.wait()
            return result

    paused = async_sessionmaker(store.kw["bind"], class_=PausedWriteSession, expire_on_commit=False)
    monkeypatch.setattr(queue, "get_session_factory", lambda: paused)
    task = asyncio.create_task(decide(client, created["id"], "rejected") if created else submit(client))
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        native.session_available = False
    finally:
        release.set()
    assert (await task).status_code == 401
    async with store() as session:
        rows = (await session.execute(select(GpuQuotaRequest))).scalars().all()
    if created:
        assert len(rows) == 1 and rows[0].status == "pending"
    else:
        assert rows == []


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["list", "create_flush", "create_commit", "resolve_update"])
async def test_stalled_queue_storage_fails_without_mutating_native_policy(client, store, native, monkeypatch, stage):
    created = (await submit(client)).json() if stage == "resolve_update" else None
    original = copy.deepcopy(native.domain)
    stalled = asyncio.Event()

    class StalledSession(AsyncSession):
        async def execute(self, statement, *args, **kwargs):
            if stage == "list" or (stage == "resolve_update" and getattr(statement, "is_update", False)):
                stalled.set()
                await asyncio.Event().wait()
            return await super().execute(statement, *args, **kwargs)

        async def flush(self, *args, **kwargs):
            if stage == "create_flush":
                stalled.set()
                await asyncio.Event().wait()
            return await super().flush(*args, **kwargs)

        async def commit(self):
            if stage == "create_commit":
                stalled.set()
                await asyncio.Event().wait()
            return await super().commit()

    monkeypatch.setattr(queue, "_STORAGE_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(
        queue,
        "get_session_factory",
        lambda: async_sessionmaker(store.kw["bind"], class_=StalledSession, expire_on_commit=False),
    )
    if stage == "list":
        response = await client.get("/api/v1/iam/gpu-quota-requests")
    elif stage == "resolve_update":
        response = await decide(client, created["id"], "rejected")
    else:
        response = await submit(client)
    assert stalled.is_set() and response.status_code == 503
    assert response.json()["detail"] == "gpu_quota_request_storage_unavailable"
    assert_no_native_writes(native, original)
    if created:
        assert (await persisted(store, created["id"])).status == "pending"


@pytest.mark.asyncio
@pytest.mark.parametrize("revoked,expected", [("role", 403), ("session", 401)])
async def test_idempotent_review_does_not_return_after_admin_revocation(client, native, store, revoked, expected):
    created = (await submit(client)).json()
    assert (await decide(client, created["id"], "rejected", note="original")).status_code == 200
    native.authorizations = 0

    def revoke(count):
        if revoked == "role" and count == 2:
            native.admin_allowed = False
        if revoked == "session" and count == 1:
            native.session_available = False

    native.on_authorize = revoke
    response = await decide(client, created["id"], "rejected", note="replacement")
    assert response.status_code == expected
    row = await persisted(store, created["id"])
    assert row.status == "rejected" and row.note == "original"


@pytest.mark.asyncio
async def test_missing_request_and_invalid_decision_body(client):
    assert (await decide(client, "0" * 32, "rejected")).status_code == 404
    for updates in (
        {"status": "pending"},
        {"status": "approved"},
        {"note": None},
        {"note": "x" * 2001},
        {"target_limit": 10},
    ):
        assert (await decide(client, "0" * 32, **updates)).status_code == 422
    assert (await decide(client, "../wrong", "rejected")).status_code in {404, 422}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure,expected",
    [
        ("none", 200),
        ("missing", 401),
        ("blacklisted", 401),
        ("domain", 401),
        ("subject", 403),
        ("identity", 403),
        ("project", 403),
        ("native_error", 503),
        ("session_error", 503),
    ],
)
async def test_live_session_fences_exact_jti_and_native_identity(monkeypatch, failure, expected):
    info = copy.deepcopy(MANAGER)
    session = {
        "user_id": info["user_id"],
        "domain_id": info["domain_id"],
        "identity_domain_id": info["identity_domain_id"],
        "project_id": "p1",
        "family_id": "family",
        "keystone_token": "private-root-proof",
    }
    native = {"user_id": "manager", "identity_domain_id": "accounts", "project_id": "p1"}
    if failure == "blacklisted":
        session["blacklisted"] = True
    elif failure == "domain":
        session["domain_id"] = "other"
    elif failure in {"subject", "identity", "project"}:
        native[{"subject": "user_id", "identity": "identity_domain_id", "project": "project_id"}[failure]] = "other"

    async def get_session(jti):
        assert jti == "private-session-jti"
        if failure == "session_error":
            raise RuntimeError("private-redis-secret")
        return None if failure == "missing" else session

    def validate(token, *, project_id, operation):
        assert token == "private-native-token" and project_id == "p1"
        if failure == "native_error":
            raise RuntimeError("private-native-secret")
        return native

    monkeypatch.setattr(queue.session_store, "get_session", get_session)
    monkeypatch.setattr(queue.keystone, "validate_token", validate)
    if expected == 200:
        assert await LIVE_SESSION(info) is not None
    else:
        with pytest.raises(HTTPException) as error:
            await LIVE_SESSION(info)
        assert error.value.status_code == expected
        assert "private-" not in str(error.value.detail)


@pytest.mark.asyncio
async def test_readback_transport_timeout_keeps_request_pending(client, native, store, monkeypatch):
    created = (await submit(client)).json()
    original = copy.deepcopy(native.domain)

    def unavailable(*_args, **_kwargs):
        raise compute_pools.ComputePoolUnavailable("private-provider-timeout")

    monkeypatch.setattr(compute_pools._Native, "exact", unavailable)
    response = await decide(client, created["id"])
    assert response.status_code == 503 and "private-provider" not in response.text
    assert (await persisted(store, created["id"])).status == "pending"
    assert_no_native_writes(native, original)


@pytest.mark.asyncio
async def test_final_authority_recheck_prevents_review_after_revocation(client, native, store):
    created = (await submit(client)).json()
    native.domain[compute_pools.POLICY_KEY]["limits"][GPU] = 6
    native.authorizations = 0

    def revoke(count):
        if count == 3:
            native.admin_allowed = False

    native.on_authorize = revoke
    assert (await decide(client, created["id"])).status_code == 403
    assert (await persisted(store, created["id"])).status == "pending"


@pytest.mark.asyncio
@pytest.mark.parametrize("winner,expected", [("rejected", 200), ("fulfilled", 409)])
async def test_conditional_update_preserves_competing_sql_winner(client, store, native, monkeypatch, winner, expected):
    created = (await submit(client)).json()

    class RacingSession(AsyncSession):
        async def execute(self, statement, *args, **kwargs):
            if getattr(statement, "is_update", False):
                # Another committed decision won after the initial pending read.
                await super().execute(
                    update(GpuQuotaRequest)
                    .where(
                        GpuQuotaRequest.id == created["id"],
                    )
                    .values(
                        status=winner, reviewer_id="other-reviewer", note="winner-note", reviewed_at=datetime.now(UTC)
                    )
                )
                await self.commit()
            return await super().execute(statement, *args, **kwargs)

    racing = async_sessionmaker(store.kw["bind"], class_=RacingSession, expire_on_commit=False)
    monkeypatch.setattr(queue, "get_session_factory", lambda: racing)
    original = copy.deepcopy(native.domain)
    response = await decide(client, created["id"], "rejected")
    assert response.status_code == expected, response.text
    row = await persisted(store, created["id"])
    assert row.status == winner and row.reviewer_id == "other-reviewer" and row.note == "winner-note"
    assert_no_native_writes(native, original)


@pytest.mark.asyncio
async def test_cancelled_request_drains_sql_commit_before_unlocking(client, store, native, monkeypatch):
    entered, release = asyncio.Event(), asyncio.Event()

    class PausedSession(AsyncSession):
        async def commit(self):
            entered.set()
            await release.wait()
            await super().commit()

    paused = async_sessionmaker(store.kw["bind"], class_=PausedSession, expire_on_commit=False)
    monkeypatch.setattr(queue, "get_session_factory", lambda: paused)
    from app.models.gpu_quota_requests import CreateGpuQuotaRequest

    task = asyncio.create_task(
        queue.create(
            copy.deepcopy(MANAGER),
            CreateGpuQuotaRequest(
                project_id="p1",
                resource_class=GPU,
                additional=1,
            ),
        )
    )
    await asyncio.wait_for(entered.wait(), timeout=2)
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    async with store() as session:
        rows = (await session.execute(select(GpuQuotaRequest))).scalars().all()
        assert len(rows) == 1 and rows[0].status == "pending"


@pytest.mark.asyncio
async def test_lost_lease_during_insert_flush_rolls_back_request(client, store, native, monkeypatch):
    entered, release = asyncio.Event(), asyncio.Event()

    class PausedFlushSession(AsyncSession):
        async def flush(self, *args, **kwargs):
            await super().flush(*args, **kwargs)
            entered.set()
            await release.wait()

    paused = async_sessionmaker(store.kw["bind"], class_=PausedFlushSession, expire_on_commit=False)
    monkeypatch.setattr(queue, "get_session_factory", lambda: paused)
    task = asyncio.create_task(submit(client))
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        native.lock_owned = False
    finally:
        release.set()
    response = await task
    assert response.status_code == 409, response.text
    async with store() as session:
        assert (await session.execute(select(GpuQuotaRequest))).scalars().all() == []


@pytest.mark.asyncio
async def test_lost_lease_during_decision_update_rolls_back_decision(client, store, native, monkeypatch):
    created = (await submit(client)).json()
    entered, release = asyncio.Event(), asyncio.Event()

    class PausedUpdateSession(AsyncSession):
        async def execute(self, statement, *args, **kwargs):
            result = await super().execute(statement, *args, **kwargs)
            if getattr(statement, "is_update", False):
                entered.set()
                await release.wait()
            return result

    paused = async_sessionmaker(store.kw["bind"], class_=PausedUpdateSession, expire_on_commit=False)
    monkeypatch.setattr(queue, "get_session_factory", lambda: paused)
    task = asyncio.create_task(decide(client, created["id"], "rejected"))
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        native.lock_owned = False
    finally:
        release.set()
    response = await task
    assert response.status_code == 409, response.text
    row = await persisted(store, created["id"])
    assert row.status == "pending" and row.reviewer_id is None and row.reviewed_at is None and row.note == ""
