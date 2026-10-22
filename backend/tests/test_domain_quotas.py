"""Allocation budgets and durable native boundaries.

SQLite exercises persistence with synthetic native/lease boundaries, not
production FOR UPDATE or Redis behavior.
"""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import get_admin_os_conn, get_os_conn, require_admin, require_domain_manager
from app.api.identity import domain_quotas as api
from app.models.domain_quotas import DomainQuotaOperation, DomainQuotaPolicy, ProjectQuotaUpdate
from app.services import domain_quotas as service

DOMAIN = "domain-a"


@pytest_asyncio.fixture
async def budget(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'quota.sqlite'}")
    async with engine.begin() as connection:
        await connection.run_sync(DomainQuotaPolicy.__table__.create)
        await connection.run_sync(DomainQuotaOperation.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(service, "get_session_factory", lambda: factory)
    projects = {
        pid: SimpleNamespace(id=pid, name=pid, domain_id=DOMAIN, is_enabled=enabled)
        for pid, enabled in (("a", True), ("b", False))
    }
    conn = SimpleNamespace(
        identity=SimpleNamespace(
            get_domain=lambda did: SimpleNamespace(id=did),
            projects=lambda **_: iter(projects.values()),
            get_project=lambda pid: projects.get(pid),
        )
    )
    limits = {"a": {"instances": 4, "volumes": 1}, "b": {"instances": 2, "volumes": 1}}
    writes, commits = [], []
    lease = SimpleNamespace(assert_owned=AsyncMock())
    busy = False

    @asynccontextmanager
    async def lock(_):
        nonlocal busy
        if busy:
            raise HTTPException(409, "busy")
        busy = True
        try:
            yield lease
        finally:
            busy = False

    def read(_, pid, section):
        if section not in {"compute", "volume"}:
            raise RuntimeError("service unavailable")
        return {key: {"limit": value, "in_use": 0, "reserved": 0} for key, value in limits[pid].items()}

    def write(_, pid, section, kwargs):
        assert commits and commits[-1]["sections"][section]["status"] == "writing"
        writes.append((pid, section, dict(kwargs)))
        limits[pid].update(kwargs)

    original_commit = service._commit

    async def commit(session, lease):
        await original_commit(session, lease)
        operations = list((await session.execute(select(DomainQuotaOperation))).scalars())
        if operations:
            commits.append({"status": operations[-1].status, "sections": dict(operations[-1].sections)})

    monkeypatch.setattr(service.identity_roles, "_graph_lock", lock)
    monkeypatch.setattr(service.quota_native, "get_section", read)
    monkeypatch.setattr(service.quota_native, "update_section", write)
    monkeypatch.setattr(service, "_commit", commit)
    monkeypatch.setattr(service, "invalidate", AsyncMock())
    monkeypatch.setattr(
        service.domain_iam, "context", AsyncMock(return_value={"domain_id": DOMAIN, "is_domain_manager": True})
    )
    state = SimpleNamespace(
        factory=factory, conn=conn, projects=projects, limits=limits, writes=writes, lease=lease, commits=commits
    )
    yield state
    await engine.dispose()


async def policy(budget, *, ceiling=10, defaults=None):
    async with budget.factory() as session:
        session.add(
            DomainQuotaPolicy(domain_id=DOMAIN, revision=1, ceilings={"instances": ceiling}, defaults=defaults or {})
        )
        await session.commit()


@pytest.mark.asyncio
async def test_budget_counts_disabled_projects_not_actual_usage(budget):
    await policy(budget, ceiling=6)
    with pytest.raises(HTTPException) as error:
        await service.update_project(budget.conn, "a", {"instances": 5})
    assert error.value.status_code == 409
    assert budget.writes == []
    assert budget.limits["b"]["instances"] == 2  # disabled is still allocation


@pytest.mark.asyncio
async def test_exact_budget_zero_and_unlimited_are_distinct(budget):
    await policy(budget, ceiling=6)
    success = await service.update_project(budget.conn, "a", {"instances": 4})
    assert success["status"] == "updated"
    with pytest.raises(HTTPException):
        await service.update_project(budget.conn, "a", {"instances": -1})
    await service.update_project(budget.conn, "a", {"instances": 0})
    snapshot = await service.snapshot(budget.conn, DOMAIN)
    assert snapshot["allocations"]["instances"] == {"limit": 2, "status": "ready", "within_budget": True}
    assert budget.limits["a"]["instances"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("other", [-1, None])
async def test_unknown_or_unlimited_peer_allocation_fails_closed(budget, other):
    await policy(budget)
    budget.limits["b"]["instances"] = other
    with pytest.raises(HTTPException) as error:
        await service.update_project(budget.conn, "a", {"instances": 1})
    assert error.value.status_code == 409
    assert not budget.writes


@pytest.mark.asyncio
async def test_explicit_unlimited_policy_preserves_native_unlimited(budget):
    await policy(budget, ceiling=-1)
    result = await service.update_project(budget.conn, "a", {"instances": -1})
    assert result["status"] == "updated"
    snapshot = await service.snapshot(budget.conn, DOMAIN)
    assert snapshot["allocations"]["instances"] == {"limit": -1, "status": "unlimited", "within_budget": True}


@pytest.mark.asyncio
async def test_concurrent_first_party_allocations_cannot_both_consume_budget(budget, monkeypatch):
    await policy(budget, ceiling=8)
    entered, release = asyncio.Event(), asyncio.Event()
    original = service._proposal

    async def gated(*args, **kwargs):
        entered.set()
        await release.wait()
        return await original(*args, **kwargs)

    monkeypatch.setattr(service, "_proposal", gated)
    first = asyncio.create_task(service.update_project(budget.conn, "a", {"instances": 6}))
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        second = asyncio.create_task(service.update_project(budget.conn, "b", {"instances": 4}))
        await asyncio.sleep(0)
    finally:
        release.set()
    results = await asyncio.gather(first, second, return_exceptions=True)
    assert sum(isinstance(result, dict) for result in results) == 1
    assert sum(budget.limits[pid]["instances"] for pid in budget.limits) == 8
    with pytest.raises(HTTPException):
        await service.update_project(budget.conn, "b", {"instances": 4})


@pytest.mark.asyncio
async def test_native_timeout_matching_readback_still_requires_explicit_settlement(budget, monkeypatch):
    await policy(budget)

    def timeout(_, pid, section, kwargs):
        budget.limits[pid].update(kwargs)
        raise TimeoutError("secret internal endpoint")

    monkeypatch.setattr(service.quota_native, "update_section", timeout)
    result = await service.update_project(budget.conn, "a", {"instances": 5})
    assert result["status"] == "unknown" and result["updated"] == []
    assert result["errors"] == {"compute": "native_outcome_unknown"}
    async with budget.factory() as session:
        operation = (await session.execute(select(DomainQuotaOperation))).scalar_one()
        assert operation.status == "unknown"
        assert operation.sections["compute"]["observed"] == {"instances": 5}


@pytest.mark.asyncio
async def test_readback_unknown_is_durable_blocks_writers_and_never_replays(budget, monkeypatch):
    await policy(budget)
    original_read = service.quota_native.get_section
    written = False

    def write(*_):
        nonlocal written
        written = True
        raise TimeoutError("provider credential")

    def read(*args):
        if written:
            raise RuntimeError("unavailable credential")
        return original_read(*args)

    monkeypatch.setattr(service.quota_native, "update_section", write)
    monkeypatch.setattr(service.quota_native, "get_section", read)
    result = await service.update_project(budget.conn, "a", {"instances": 5, "volumes": 3})
    assert result["status"] == "unknown"
    assert result["errors"]["volume"] == "not_attempted"
    assert "credential" not in str(result)
    with pytest.raises(HTTPException) as blocked:
        await service.update_project(budget.conn, "a", {"instances": 1})
    assert blocked.value.detail == "quota_native_operation_unresolved"
    async with budget.factory() as session:
        operation = (await session.execute(select(DomainQuotaOperation))).scalar_one()
        assert operation.status == "unknown"
        assert operation.sections["volume"]["status"] == "pending"


@pytest.mark.asyncio
async def test_partial_mismatch_does_not_claim_all_service_transaction(budget, monkeypatch):
    await policy(budget)
    monkeypatch.setattr(service.quota_native, "update_section", lambda *_: None)
    result = await service.update_project(budget.conn, "a", {"instances": 5})
    assert result["status"] == "partial"
    assert result["updated"] == []
    assert result["errors"] == {"compute": "native_readback_mismatch"}
    assert budget.limits["a"]["instances"] == 4


@pytest.mark.asyncio
async def test_defaults_are_future_only_revision_fenced_and_before_enable(budget):
    await policy(budget)
    await service.update_policy(budget.conn, DOMAIN, 1, {"instances": 3}, defaults=True)
    assert budget.limits["a"]["instances"] == 4
    assert budget.writes == []
    with pytest.raises(HTTPException) as conflict:
        await service.update_policy(budget.conn, DOMAIN, 1, {}, defaults=True)
    assert conflict.value.status_code == 409
    with pytest.raises(HTTPException):
        await service.apply_project_defaults(budget.conn, DOMAIN, "a", lease=budget.lease)
    result = await service.apply_project_defaults(budget.conn, DOMAIN, "b", lease=budget.lease)
    assert result["status"] == "updated"
    assert budget.limits["b"]["instances"] == 3
    assert budget.projects["b"].is_enabled is False


@pytest.mark.asyncio
async def test_creation_without_policy_preserves_native_defaults(budget):
    result = await service.apply_project_defaults(budget.conn, DOMAIN, "b", lease=budget.lease)
    assert result["updated"] == []
    assert not budget.writes


@pytest.mark.asyncio
async def test_no_storage_cannot_assume_no_budget(budget, monkeypatch):
    monkeypatch.setattr(service, "get_session_factory", lambda: None)
    with pytest.raises(HTTPException) as unavailable:
        await service.apply_project_defaults(budget.conn, DOMAIN, "b", lease=budget.lease)
    assert unavailable.value.status_code == 503
    assert not budget.writes


@pytest.mark.asyncio
async def test_lost_caller_lease_fails_before_native_defaults(budget):
    await policy(budget, defaults={"instances": 3})
    budget.lease.assert_owned.side_effect = HTTPException(409, "expired")
    with pytest.raises(HTTPException):
        await service.apply_project_defaults(budget.conn, DOMAIN, "b", lease=budget.lease)
    assert not budget.writes


@pytest.mark.parametrize(
    "payload", [{"instances": True}, {"instances": "4"}, {"instances": None}, {"instances": -2}, {"instances": 1.5}]
)
def test_model_rejects_coercion_and_invalid_limits(payload):
    with pytest.raises(ValidationError):
        ProjectQuotaUpdate.model_validate(payload)


@pytest.mark.parametrize("payload", [{}, {"admin": 5}])
def test_model_rejects_empty_or_unknown_keys(payload):
    with pytest.raises(ValidationError):
        ProjectQuotaUpdate.model_validate(payload)


@pytest.mark.asyncio
async def test_routes_exact_domain_manager_boundary_and_no_store(budget, monkeypatch):
    app = FastAPI()
    app.include_router(api.router, prefix="/api/v1")
    token = {"user_id": "manager", "domain_id": DOMAIN}
    app.dependency_overrides[require_domain_manager] = lambda: token
    app.dependency_overrides[get_os_conn] = lambda: budget.conn
    monkeypatch.setattr(service.keystone, "get_admin_project_connection", lambda: budget.conn)
    budget.conn.close = MagicMock()
    budget.projects["foreign"] = SimpleNamespace(id="foreign", domain_id="domain-b", is_enabled=True)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.put("/api/v1/iam/projects/foreign/quotas", json={"instances": 0})
        bad = await client.put("/api/v1/iam/projects/a/quotas", json={"instances": True})
    assert denied.status_code == 403
    assert bad.status_code == 422
    assert denied.headers["cache-control"] == "no-store, private"
    assert not budget.writes


@pytest.mark.asyncio
async def test_recovery_requires_explicit_admin_confirmation_and_readback(budget, monkeypatch):
    await policy(budget)
    async with budget.factory() as session:
        session.add(
            DomainQuotaOperation(
                id="interrupted",
                domain_id=DOMAIN,
                project_id="a",
                status="applying",
                requested={"instances": 5},
                sections={"compute": {"status": "writing"}},
            )
        )
        await session.commit()
    app = FastAPI()
    app.include_router(api.router, prefix="/api/v1")
    app.dependency_overrides[get_os_conn] = lambda: budget.conn
    app.dependency_overrides[get_admin_os_conn] = lambda: budget.conn

    async def verified_admin():
        return {"user_id": "system-admin"}

    app.dependency_overrides[require_admin] = verified_admin
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        path = f"/api/v1/admin/domains/{DOMAIN}/quotas/operations/interrupted/reconcile"
        refused = await client.post(path, json={"native_calls_settled": False})
        accepted = await client.post(path, json={"native_calls_settled": True})
    assert refused.status_code == 422
    assert accepted.status_code == 200
    assert not budget.writes
    async with budget.factory() as session:
        operation = await session.get(DomainQuotaOperation, "interrupted")
        assert operation.status == "reconciled"
        assert operation.sections["compute"]["observed"] == {"instances": 4}


@pytest.mark.asyncio
async def test_missing_requested_service_fails_before_any_native_write(budget):
    await policy(budget)
    with pytest.raises(HTTPException) as unavailable:
        await service.update_project(budget.conn, "a", {"instances": 5, "shares": 3})
    assert unavailable.value.status_code == 503
    assert unavailable.value.detail == "quota_native_preflight_unavailable"
    assert not budget.writes
    async with budget.factory() as session:
        assert not list((await session.execute(select(DomainQuotaOperation))).scalars())


@pytest.mark.asyncio
async def test_creation_defaults_over_budget_fail_while_project_stays_disabled(budget):
    await policy(budget, ceiling=6, defaults={"instances": 3})
    with pytest.raises(HTTPException) as conflict:
        await service.apply_project_defaults(budget.conn, DOMAIN, "b", lease=budget.lease)
    assert conflict.value.status_code == 409
    assert budget.projects["b"].is_enabled is False
    assert not budget.writes


@pytest.mark.asyncio
async def test_creation_cannot_use_decreasing_drift_repair_to_exceed_domain_budget(budget):
    budget.limits["a"]["instances"] = 90
    budget.limits["b"]["instances"] = 20
    await policy(budget, ceiling=100, defaults={"instances": 15})
    with pytest.raises(HTTPException) as conflict:
        await service.apply_project_defaults(budget.conn, DOMAIN, "b", lease=budget.lease)
    assert conflict.value.status_code == 409
    assert budget.projects["b"].is_enabled is False
    assert budget.limits["b"]["instances"] == 20
    assert not budget.writes


@pytest.mark.asyncio
async def test_external_native_drift_is_visible_and_only_decreasing_repair_allowed(budget):
    await policy(budget, ceiling=5)
    snapshot = await service.snapshot(budget.conn, DOMAIN)
    assert snapshot["drift"] is True
    with pytest.raises(HTTPException):
        await service.update_project(budget.conn, "a", {"instances": 5})
    result = await service.update_project(budget.conn, "a", {"instances": 3})
    assert result["status"] == "updated"
    assert (await service.snapshot(budget.conn, DOMAIN))["drift"] is False


@pytest.mark.parametrize(
    "values", [{"unknown": 4}, {"instances": True}, {"instances": "5"}, {"instances": None}, {"instances": -2}]
)
def test_ceiling_and_defaults_models_reject_invalid_map_entries(values):
    from app.models.domain_quotas import DefaultsUpdate, PolicyUpdate

    with pytest.raises(ValidationError):
        PolicyUpdate.model_validate({"revision": 0, "ceilings": values})
    with pytest.raises(ValidationError):
        DefaultsUpdate.model_validate({"revision": 0, "defaults": values})


@pytest.mark.asyncio
async def test_system_admin_guard_covers_explicit_domain_policy_and_recovery(budget):
    app = FastAPI()
    app.include_router(api.router, prefix="/api/v1")

    async def forbidden():
        raise HTTPException(403, "verified_system_admin_required")

    app.dependency_overrides[require_admin] = forbidden
    app.dependency_overrides[get_os_conn] = lambda: budget.conn
    app.dependency_overrides[get_admin_os_conn] = lambda: budget.conn
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        for method, path, body in [
            ("GET", f"/api/v1/admin/domains/{DOMAIN}/quotas", None),
            ("PUT", f"/api/v1/admin/domains/{DOMAIN}/quotas", {"revision": 0, "ceilings": {}}),
            ("POST", f"/api/v1/admin/domains/{DOMAIN}/quotas/operations/op/reconcile", {"native_calls_settled": True}),
        ]:
            response = await client.request(method, path, json=body)
            assert response.status_code == 403
    assert not budget.writes


@pytest.mark.asyncio
async def test_old_unresolved_operation_is_never_hidden_by_history_limit(budget):
    from datetime import datetime

    await policy(budget)
    async with budget.factory() as session:
        session.add(
            DomainQuotaOperation(
                id="old-blocker",
                domain_id=DOMAIN,
                project_id="a",
                status="unknown",
                requested={"instances": 5},
                sections={"compute": {"status": "unknown"}},
                created_at=datetime(2000, 1, 1),
            )
        )
        for index in range(60):
            session.add(
                DomainQuotaOperation(
                    id=f"finished-{index}",
                    domain_id=DOMAIN,
                    project_id="a",
                    status="updated",
                    requested={"instances": 4},
                    sections={"compute": {"status": "verified"}},
                )
            )
        await session.commit()
    snapshot = await service.snapshot(budget.conn, DOMAIN)
    assert len(snapshot["operations"]) == 50
    assert snapshot["operations"][0]["id"] == "old-blocker"
    assert snapshot["allocation_blocked"] is True
    assert snapshot["blocking_operation_id"] == "old-blocker"
    with pytest.raises(HTTPException) as blocked:
        await service.update_project(budget.conn, "a", {"instances": 1})
    assert blocked.value.detail == "quota_native_operation_unresolved"
    assert not budget.writes


@pytest.mark.asyncio
async def test_recovery_of_compensated_deleted_project_never_replays_quota(budget):
    await policy(budget)
    async with budget.factory() as session:
        session.add(
            DomainQuotaOperation(
                id="compensated",
                domain_id=DOMAIN,
                project_id="b",
                status="unknown",
                requested={"instances": 3},
                sections={"compute": {"status": "unknown"}},
            )
        )
        await session.commit()
    del budget.projects["b"]
    snapshot = await service.reconcile_operation(budget.conn, DOMAIN, "compensated")
    assert snapshot["allocation_blocked"] is False
    assert not budget.writes
    async with budget.factory() as session:
        operation = await session.get(DomainQuotaOperation, "compensated")
        assert operation.status == "reconciled"
        assert operation.sections == {"compute": {"status": "project_deleted"}}


@pytest.mark.asyncio
async def test_recovery_never_accepts_foreign_operation_scope(budget):
    async with budget.factory() as session:
        session.add(
            DomainQuotaOperation(
                id="foreign-op",
                domain_id="foreign",
                project_id="a",
                status="unknown",
                requested={"instances": 3},
                sections={"compute": {"status": "unknown"}},
            )
        )
        await session.commit()
    with pytest.raises(HTTPException) as denied:
        await service.reconcile_operation(budget.conn, DOMAIN, "foreign-op")
    assert denied.value.status_code == 404
    assert not budget.writes


@pytest.mark.asyncio
async def test_enable_assertion_checks_current_allocation_without_future_defaults(budget):
    await policy(budget, defaults={"instances": 3})
    result = await service.assert_project_allocation(budget.conn, DOMAIN, "b", lease=budget.lease)
    assert result == {"domain_id": DOMAIN, "project_id": "b", "status": "verified"}
    assert budget.limits["b"]["instances"] == 2
    assert not budget.writes
    assert budget.projects["b"].is_enabled is False
    async with budget.factory() as session:
        assert not list((await session.execute(select(DomainQuotaOperation))).scalars())


@pytest.mark.asyncio
async def test_enable_assertion_refuses_overbudget_unknown_and_unresolved_state(budget):
    await policy(budget, ceiling=5)
    with pytest.raises(HTTPException) as over:
        await service.assert_project_allocation(budget.conn, DOMAIN, "b", lease=budget.lease)
    assert over.value.status_code == 409
    budget.limits["a"]["instances"] = None
    with pytest.raises(HTTPException) as unknown:
        await service.assert_project_allocation(budget.conn, DOMAIN, "b", lease=budget.lease)
    assert unknown.value.status_code == 409
    budget.limits["a"]["instances"] = 0
    async with budget.factory() as session:
        session.add(
            DomainQuotaOperation(
                id="enable-blocker",
                domain_id=DOMAIN,
                project_id="b",
                status="unknown",
                requested={"instances": 3},
                sections={"compute": {"status": "unknown"}},
            )
        )
        await session.commit()
    with pytest.raises(HTTPException) as unresolved:
        await service.assert_project_allocation(budget.conn, DOMAIN, "b", lease=budget.lease)
    assert unresolved.value.detail == "quota_native_operation_unresolved"
    assert not budget.writes


@pytest.mark.asyncio
async def test_personal_quota_update_never_consumes_another_users_budget(budget, monkeypatch):
    for project in budget.projects.values():
        project.domain_id = "personal"
    monkeypatch.setattr(
        budget.conn.identity,
        "get_domain",
        lambda did: SimpleNamespace(id=did, name="personal", afterglow_domain_kind="personal"),
    )
    # A historical shared-domain policy must not cap or mutate personal peers.
    async with budget.factory() as session:
        session.add(
            DomainQuotaPolicy(domain_id="personal", revision=1, ceilings={"instances": 0}, defaults={"instances": 0})
        )
        await session.commit()
    budget.limits["b"]["instances"] = -1
    result = await service.update_project(budget.conn, "a", {"instances": 5})
    assert result["status"] == "updated"
    assert budget.limits["a"]["instances"] == 5
    assert budget.limits["b"]["instances"] == -1
    assert budget.writes == [("a", "compute", {"instances": 5})]
    with pytest.raises(HTTPException) as denied:
        await service.snapshot(budget.conn, "personal")
    assert denied.value.detail == "organization_domain_required"


@pytest.mark.asyncio
async def test_personal_quota_uncertainty_fences_only_the_affected_project(budget, monkeypatch):
    for project in budget.projects.values():
        project.domain_id = "personal"
    monkeypatch.setattr(
        budget.conn.identity,
        "get_domain",
        lambda did: SimpleNamespace(id=did, name="personal", afterglow_domain_kind="personal"),
    )
    async with budget.factory() as session:
        session.add(
            DomainQuotaOperation(
                id="a-uncertain",
                domain_id="personal",
                project_id="a",
                status="unknown",
                requested={"instances": 7},
                sections={"compute": {"status": "unknown"}},
            )
        )
        await session.commit()
    result = await service.update_project(budget.conn, "b", {"instances": 3})
    assert result["status"] == "updated"
    with pytest.raises(HTTPException) as denied:
        await service.update_project(budget.conn, "a", {"instances": 7})
    assert denied.value.detail == "quota_native_operation_unresolved"
    assert budget.writes == [("b", "compute", {"instances": 3})]
