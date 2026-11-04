"""SQL-backed approval lifecycle with real schedule validation and native writes.

Native provider transport/authority is isolated; these are not production or
cross-process deployment qualification.
"""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.instance_usage_governance import InstanceUsageExtensionRequest as Extension
from app.models.instance_usage_governance import InstanceUsagePolicy as Policy
from app.services import instance_usage as usage
from app.services import instance_usage_governance as governance
from tests import test_instance_usage_routes as usage_fixtures
from tests.test_instance_usage_routes import INSTANCE, PROJECT

DOMAIN = "default"
BASE = "/api/v1/instances"

governance_store = usage_fixtures.governance_store
usage_cloud = usage_fixtures.usage_cloud


def access(*, manager=False, review=False, write=True):
    return {"manager": manager, "review": manager or review, "write": write, "read": True}


async def manual(factory):
    async with factory() as session:
        row = Policy(
            cloud_id="c" * 64,
            domain_id=DOMAIN,
            review_required=True,
            revision="a" * 32,
            updated_by="manager",
            updated_at=datetime.now(UTC),
        )
        session.add(row)
        await session.commit()


def extension(native):
    schedule = usage.parse_schedule(native)
    return {
        "revision": schedule.revision,
        "expires_at": (datetime.fromisoformat(schedule.expires_at) + timedelta(days=7)).isoformat(),
        "reason": "Long-running evaluation",
    }


async def pending(client, native):
    response = await client.post(f"{BASE}/{INSTANCE}/usage-schedule/extend", json=extension(native))
    assert response.status_code == 202, response.text
    return response.json()["request"]


async def review(client, row, decision="approve"):
    return await client.post(
        f"{BASE}/usage-extension-requests/{row['id']}/review", json={"decision": decision, "revision": row["revision"]}
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["member_put", "member_extend", "admin_put", "admin_extend"])
async def test_every_schedule_route_holds_native_expiry_pending(
    client,
    admin_client,
    mock_conn,
    usage_cloud,
    governance_store,
    route,
):
    await manual(governance_store)
    before = deepcopy(usage_cloud.metadata)
    prefix = "/api/v1/admin/instances" if route.startswith("admin") else BASE
    api = admin_client if route.startswith("admin") else client
    suffix = "/extend" if route.endswith("extend") else ""
    response = await (api.post if suffix else api.put)(
        f"{prefix}/{INSTANCE}/usage-schedule{suffix}",
        json=extension(usage_cloud),
    )
    assert response.status_code == 202, response.text
    data = response.json()
    assert data["status"] == data["request"]["status"] == "pending"
    assert data["schedule"]["revision"] == before["afterglow_usage_revision"]
    assert data["schedule"]["expires_at"] == usage.parse_schedule(usage_cloud).expires_at
    assert usage_cloud.metadata == before
    mock_conn.compute.set_server_metadata.assert_not_called()
    async with governance_store() as session:
        assert (await session.execute(select(Extension))).scalar_one().status == "pending"


@pytest.mark.asyncio
async def test_pending_refuses_bundled_destructive_action(client, mock_conn, usage_cloud, governance_store):
    await manual(governance_store)
    response = await client.put(
        f"{BASE}/{INSTANCE}/usage-schedule",
        json={
            **extension(usage_cloud),
            "expiry_action": "delete",
            "delete_volumes": True,
        },
    )
    assert response.status_code == 422
    mock_conn.compute.set_server_metadata.assert_not_called()


@pytest.mark.asyncio
async def test_shortening_remains_direct_under_manual_policy(client, usage_cloud, governance_store):
    await manual(governance_store)
    schedule = usage.parse_schedule(usage_cloud)
    expires = datetime.fromisoformat(schedule.expires_at) - timedelta(days=1)
    response = await client.put(
        f"{BASE}/{INSTANCE}/usage-schedule",
        json={
            "revision": schedule.revision,
            "expires_at": expires.isoformat(),
        },
    )
    assert response.status_code == 200, response.text
    assert datetime.fromisoformat(response.json()["expires_at"]) == expires
    async with governance_store() as session:
        assert not (await session.execute(select(Extension))).scalars().all()


@pytest.mark.asyncio
async def test_automatic_default_is_sql_checked_and_journaled(client, usage_cloud, governance_store):
    response = await client.post(f"{BASE}/{INSTANCE}/usage-schedule/extend", json=extension(usage_cloud))
    assert response.status_code == 200, response.text
    async with governance_store() as session:
        row = (await session.execute(select(Extension))).scalar_one()
        assert row.status == "approved"
        assert row.policy_revision == governance.DEFAULT_REVISION
        assert row.applied_schedule == response.json()


@pytest.mark.asyncio
async def test_policy_requires_live_exact_domain_manager_and_revision(
    client,
    usage_cloud,
    governance_store,
    monkeypatch,
):
    initial = await client.get(f"{BASE}/usage-extension-policy")
    assert initial.status_code == 200
    assert initial.json() == {
        "domain_id": DOMAIN,
        "review_required": False,
        "revision": governance.DEFAULT_REVISION,
        "can_manage": False,
    }
    body = {"revision": initial.json()["revision"], "review_required": True}
    assert (await client.put(f"{BASE}/usage-extension-policy", json=body)).status_code == 403
    monkeypatch.setattr(governance, "live_access", AsyncMock(return_value=access(manager=True)))
    changed = await client.put(f"{BASE}/usage-extension-policy", json=body)
    assert changed.status_code == 200
    assert changed.json()["review_required"] is True
    assert changed.json()["revision"] != body["revision"]
    assert (await client.put(f"{BASE}/usage-extension-policy", json=body)).status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize("reviewer", ["manager", "project_admin"])
async def test_scoped_reviewer_applies_once_with_native_readback(
    client,
    mock_conn,
    usage_cloud,
    governance_store,
    monkeypatch,
    reviewer,
):
    await manual(governance_store)
    row = await pending(client, usage_cloud)
    monkeypatch.setattr(
        governance,
        "live_access",
        AsyncMock(
            return_value=access(
                manager=reviewer == "manager",
                review=True,
            )
        ),
    )
    response = await review(client, row)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "approved"
    assert response.json()["can_review"] is False
    assert usage.parse_schedule(usage_cloud).expires_at == row["expires_at"]
    assert mock_conn.compute.set_server_metadata.call_count == 1
    assert (await review(client, row)).status_code == 409
    assert mock_conn.compute.set_server_metadata.call_count == 1


@pytest.mark.asyncio
async def test_live_revocation_and_cached_admin_never_authorize_review(
    client,
    admin_client,
    mock_conn,
    usage_cloud,
    governance_store,
):
    await manual(governance_store)
    row = await pending(client, usage_cloud)
    assert (await review(client, row)).status_code == 403
    assert (await review(admin_client, row)).status_code == 403
    mock_conn.compute.set_server_metadata.assert_not_called()


@pytest.mark.asyncio
async def test_rejection_and_duplicate_requests_do_not_change_native_schedule(
    client,
    mock_conn,
    usage_cloud,
    governance_store,
    monkeypatch,
):
    await manual(governance_store)
    row = await pending(client, usage_cloud)
    assert (
        await client.post(f"{BASE}/{INSTANCE}/usage-schedule/extend", json=extension(usage_cloud))
    ).status_code == 409
    before = deepcopy(usage_cloud.metadata)
    monkeypatch.setattr(governance, "live_access", AsyncMock(return_value=access(review=True)))
    response = await review(client, row, "reject")
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert usage_cloud.metadata == before
    mock_conn.compute.set_server_metadata.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["policy", "schedule", "lifecycle", "requester"])
async def test_stale_or_revoked_request_cannot_be_approved(
    client,
    mock_conn,
    usage_cloud,
    governance_store,
    monkeypatch,
    change,
):
    await manual(governance_store)
    row = await pending(client, usage_cloud)
    if change == "policy":
        async with governance_store() as session:
            policy = await session.get(Policy, ("c" * 64, DOMAIN))
            policy.revision = "b" * 32
            await session.commit()
    elif change == "schedule":
        usage_cloud.metadata["afterglow_usage_revision"] = "b" * 32
    elif change == "lifecycle":
        usage_cloud.metadata["afterglow_usage_state"] = "shelve_requested"
    calls = 0

    async def authority(*args):
        nonlocal calls
        calls += 1
        return access(review=True, write=not (change == "requester" and calls > 1))

    monkeypatch.setattr(governance, "live_access", authority)
    response = await review(client, row)
    assert response.status_code == (403 if change == "requester" else 409), response.text
    mock_conn.compute.set_server_metadata.assert_not_called()


@pytest.mark.asyncio
async def test_ambiguous_native_write_is_durable_and_not_retried(
    client,
    mock_conn,
    usage_cloud,
    governance_store,
    monkeypatch,
):
    await manual(governance_store)
    row = await pending(client, usage_cloud)
    monkeypatch.setattr(governance, "live_access", AsyncMock(return_value=access(review=True)))
    mock_conn.compute.set_server_metadata.side_effect = TimeoutError("response lost")
    response = await review(client, row)
    assert response.status_code == 502, response.text
    async with governance_store() as session:
        saved = await session.get(Extension, row["id"])
        assert saved.status == "uncertain"
        assert saved.revision != row["revision"]
        retry = {**row, "revision": saved.revision}
    assert (await review(client, retry)).status_code == 409
    assert (
        await client.post(f"{BASE}/{INSTANCE}/usage-schedule/extend", json=extension(usage_cloud))
    ).status_code == 409
    assert mock_conn.compute.set_server_metadata.call_count == 1


@pytest.mark.asyncio
async def test_automatic_uncertain_write_is_also_nonreplayable(
    client,
    mock_conn,
    usage_cloud,
    governance_store,
):
    mock_conn.compute.set_server_metadata.side_effect = TimeoutError("response lost")
    payload = extension(usage_cloud)
    assert (await client.post(f"{BASE}/{INSTANCE}/usage-schedule/extend", json=payload)).status_code == 502
    async with governance_store() as session:
        assert (await session.execute(select(Extension))).scalar_one().status == "uncertain"
    assert (await client.post(f"{BASE}/{INSTANCE}/usage-schedule/extend", json=payload)).status_code == 409
    assert mock_conn.compute.set_server_metadata.call_count == 1


@pytest.mark.asyncio
async def test_member_queue_visible_but_domain_queue_requires_manager(
    client,
    usage_cloud,
    governance_store,
    monkeypatch,
):
    await manual(governance_store)
    row = await pending(client, usage_cloud)
    listed = await client.get(f"{BASE}/usage-extension-requests")
    assert listed.status_code == 200
    assert listed.json()["items"][0]["id"] == row["id"]
    assert listed.json()["items"][0]["can_review"] is False
    assert (await client.get(f"{BASE}/usage-extension-requests", params={"domain_id": DOMAIN})).status_code == 403
    monkeypatch.setattr(governance, "live_access", AsyncMock(return_value=access(manager=True)))
    domain = await client.get(f"{BASE}/usage-extension-requests", params={"domain_id": DOMAIN})
    assert domain.status_code == 200
    assert domain.json()["items"][0]["can_review"] is True


@pytest.mark.asyncio
async def test_database_unavailable_fails_before_native_dispatch(
    client,
    mock_conn,
    usage_cloud,
    monkeypatch,
):
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def missing():
        raise HTTPException(503, "schema unavailable")
        yield

    monkeypatch.setattr(governance, "session_scope", missing)
    response = await client.post(f"{BASE}/{INSTANCE}/usage-schedule/extend", json=extension(usage_cloud))
    assert response.status_code == 503
    mock_conn.compute.set_server_metadata.assert_not_called()


def test_sql108_is_pinned_and_only_adds_governance_tables():
    from scripts.bootstrap_schema import load_sql108, model_metadata

    statements = load_sql108()
    assert len(statements) == 2
    assert all(statement.startswith("CREATE TABLE IF NOT EXISTS instance_usage_") for statement in statements)
    metadata = model_metadata()
    assert "instance_usage_policies" in metadata.tables
    assert "instance_usage_extension_requests" in metadata.tables


@pytest.mark.asyncio
async def test_domain_only_manager_can_read_policy_queue_and_review_without_project(
    client,
    mock_conn,
    usage_cloud,
    governance_store,
    monkeypatch,
):
    from app.api.deps import get_token_info
    from app.main import app
    from tests.conftest import make_token_info

    await manual(governance_store)
    row = await pending(client, usage_cloud)
    mock_conn._afterglow_project_id = ""
    app.dependency_overrides[get_token_info] = lambda: make_token_info(project_id="")
    monkeypatch.setattr(governance, "live_access", AsyncMock(return_value=access(manager=True)))
    # Projectless reads never silently substitute the fixed executor's project.
    assert (await client.get(f"{BASE}/usage-extension-policy")).status_code == 403
    policy = await client.get(f"{BASE}/usage-extension-policy", params={"domain_id": DOMAIN})
    assert policy.status_code == 200
    assert policy.json()["can_manage"] is True
    queue = await client.get(f"{BASE}/usage-extension-requests", params={"domain_id": DOMAIN})
    assert queue.status_code == 200
    assert queue.json()["items"][0]["can_review"] is True
    response = await review(client, row, "reject")
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    monkeypatch.setattr(governance, "live_access", AsyncMock(return_value=access()))
    assert (await client.get(f"{BASE}/usage-extension-policy", params={"domain_id": DOMAIN})).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,expected",
    [
        ("admin", True),
        ("project_owner", True),
        ("project_admin", True),
        ("manager", False),
        ("member", False),
        ("reader", False),
    ],
)
async def test_live_native_review_role_is_exact_project_bound(monkeypatch, role, expected):
    # Exercise the actual authority composer, not the HTTP fixture's substitute.
    async def provider(fn, *args, **kwargs):
        if fn is governance.keystone.get_identity_user:
            assert args == ("human",)
            return {"id": "human", "domain_id": "identity-home"}
        if fn is governance.domain_scope.resolve_domain:
            assert args == (DOMAIN,)
            return {"id": DOMAIN}
        if fn is governance.domain_projects.has_manager:
            assert args == ("human", DOMAIN)
            return False
        if fn is governance.domain_projects.assert_project_membership:
            assert args == ("human", PROJECT)
            return None
        raise AssertionError(fn)

    monkeypatch.setattr(governance.project_service, "_provider_call", provider)
    monkeypatch.setattr(governance, "project_domain", AsyncMock(return_value=DOMAIN))
    roles = AsyncMock(return_value=[{"id": "native-role", "name": role}])
    monkeypatch.setattr(governance.project_service, "get_project_delegation_roles", roles)
    result = await governance.live_access("human", DOMAIN, PROJECT)
    assert result["review"] is expected
    roles.assert_awaited_once_with(PROJECT, "human")


@pytest.mark.asyncio
async def test_live_native_authority_refuses_moved_project_and_provider_failure(monkeypatch):
    async def provider(fn, *args, **kwargs):
        if fn is governance.keystone.get_identity_user:
            return {"id": "human"}
        if fn is governance.domain_scope.resolve_domain:
            return {"id": DOMAIN}
        if fn is governance.domain_projects.has_manager:
            return True
        raise AssertionError(fn)

    monkeypatch.setattr(governance.project_service, "_provider_call", provider)
    monkeypatch.setattr(governance, "project_domain", AsyncMock(return_value="foreign-domain"))
    with pytest.raises(HTTPException) as moved:
        await governance.live_access("human", DOMAIN, PROJECT)
    assert moved.value.status_code == 403
    monkeypatch.setattr(
        governance.project_service, "_provider_call", AsyncMock(side_effect=HTTPException(503, "native down"))
    )
    with pytest.raises(HTTPException) as unavailable:
        await governance.live_access("human", DOMAIN, PROJECT)
    assert unavailable.value.status_code == 503


@pytest.mark.asyncio
async def test_cancelled_native_attempt_leaves_nonreplayable_applying_intent(
    client,
    usage_cloud,
    governance_store,
    monkeypatch,
):
    import asyncio

    from app.models.instance_usage_governance import UsageExtensionReview

    await manual(governance_store)
    row = await pending(client, usage_cloud)
    monkeypatch.setattr(governance, "live_access", AsyncMock(return_value=access(review=True)))
    monkeypatch.setattr(usage, "_update_locked", AsyncMock(side_effect=asyncio.CancelledError()))
    with pytest.raises(asyncio.CancelledError):
        await governance.review_request(
            # Connection is used only for exact-cloud binding, isolated by fixture.
            None,
            {"user_id": "test-user-123", "domain_id": DOMAIN},
            row["id"],
            UsageExtensionReview(decision="approve", revision=row["revision"]),
        )
    async with governance_store() as session:
        saved = await session.get(Extension, row["id"])
        assert saved.status == "applying"
        assert saved.applied_schedule is None


def test_sql108_refuses_manifest_drift(monkeypatch):
    from types import SimpleNamespace

    from scripts import bootstrap_schema
    from scripts.baseline_migrations import MigrationLedgerError

    monkeypatch.setattr(
        bootstrap_schema,
        "load_manifest",
        lambda: [
            SimpleNamespace(
                logical_id="108-instance-usage-governance",
                relative_path="backend/migrations/108_instance_usage_governance.sql",
                sha256="bad",
            ),
        ],
    )
    with pytest.raises(MigrationLedgerError, match="SQL108 immutable manifest identity"):
        bootstrap_schema.load_sql108()


@pytest.mark.asyncio
@pytest.mark.parametrize("reviewed", [False, True])
async def test_graph_loss_during_final_native_read_prevents_metadata_dispatch(
    client,
    mock_conn,
    usage_cloud,
    governance_store,
    monkeypatch,
    reviewed,
):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    row = None
    if reviewed:
        await manual(governance_store)
        row = await pending(client, usage_cloud)
        monkeypatch.setattr(governance, "live_access", AsyncMock(return_value=access(review=True)))

    ownership = {"lost": False, "reads": 0}
    original_get = mock_conn.compute.get_server

    def losing_get(instance_id):
        ownership["reads"] += 1
        # Service fresh read, _update_locked fresh read, then the metadata
        # writer's final pre-POST read. Ownership is valid at outer assertions.
        if ownership["reads"] == 3:
            ownership["lost"] = True
        return original_get(instance_id)

    async def assert_owned():
        if ownership["lost"]:
            raise HTTPException(409, "Native graph ownership was lost")

    @asynccontextmanager
    async def graph():
        yield SimpleNamespace(assert_owned=assert_owned)

    monkeypatch.setattr(governance, "governance_lock", graph)
    mock_conn.compute.get_server = losing_get
    before = deepcopy(usage_cloud.metadata)
    response = (
        await review(client, row)
        if reviewed
        else await client.post(f"{BASE}/{INSTANCE}/usage-schedule/extend", json=extension(usage_cloud))
    )
    assert response.status_code in {409, 502}
    assert ownership["reads"] == 3
    assert ownership["lost"] is True
    assert usage_cloud.metadata == before
    mock_conn.compute.set_server_metadata.assert_not_called()
    async with governance_store() as session:
        intent = (await session.execute(select(Extension))).scalar_one()
        assert intent.status == "uncertain"


@pytest.mark.asyncio
async def test_working_domain_fences_policy_queue_and_review_even_for_multidomain_manager(
    client,
    usage_cloud,
    governance_store,
    monkeypatch,
):
    from app.api.deps import get_token_info
    from app.main import app
    from tests.conftest import make_token_info

    await manual(governance_store)
    row = await pending(client, usage_cloud)
    authority = AsyncMock(return_value=access(manager=True))
    monkeypatch.setattr(governance, "live_access", authority)
    # Native membership in both domains is not an authenticated domain switch.
    app.dependency_overrides[get_token_info] = lambda: make_token_info(domain_id="other-working-domain")
    for path in ("usage-extension-policy", "usage-extension-requests"):
        response = await client.get(f"{BASE}/{path}", params={"domain_id": DOMAIN})
        assert response.status_code == 403
    response = await client.put(
        f"{BASE}/usage-extension-policy",
        params={"domain_id": DOMAIN},
        json={"review_required": False, "revision": "a" * 32},
    )
    assert response.status_code == 403
    assert (await client.get(f"{BASE}/usage-extension-policy", params={"project_id": PROJECT})).status_code == 403
    assert (await review(client, row)).status_code == 403
    authority.assert_not_awaited()
    async with governance_store() as session:
        assert (await session.get(Extension, row["id"])).status == "pending"
        assert (await session.get(Policy, ("c" * 64, DOMAIN))).review_required is True


@pytest.mark.asyncio
async def test_queue_paginates_past_500_and_prioritizes_pending(
    client,
    usage_cloud,
    governance_store,
):
    stamp = datetime.now(UTC)
    async with governance_store() as session:
        for index in range(507):
            session.add(
                Extension(
                    id=f"{index:032x}",
                    cloud_id="c" * 64,
                    domain_id=DOMAIN,
                    project_id=PROJECT,
                    instance_id=INSTANCE,
                    instance_name="queue fixture",
                    requested_by="human",
                    requested_at=stamp + timedelta(seconds=index),
                    expires_at=stamp + timedelta(days=7),
                    reason="evaluation",
                    schedule_revision="a" * 32,
                    policy_revision="b" * 32,
                    revision="c" * 32,
                    status="pending" if index < 2 else "approved",
                )
            )
        await session.commit()
    cursor = None
    observed = []
    for _ in range(6):
        params = {"limit": 100}
        if cursor is not None:
            params["cursor"] = cursor
        response = await client.get(f"{BASE}/usage-extension-requests", params=params)
        assert response.status_code == 200, response.text
        payload = response.json()
        observed.extend(payload["items"])
        cursor = payload["next_cursor"]
        if cursor is None:
            break
    assert cursor is None
    assert len(observed) == len({row["id"] for row in observed}) == 507
    assert [row["status"] for row in observed[:2]] == ["pending", "pending"]
    assert all(row["status"] == "approved" for row in observed[2:])


@pytest.mark.asyncio
async def test_queue_cursor_retains_original_rank_if_anchor_is_reviewed(
    client,
    usage_cloud,
    governance_store,
):
    stamp = datetime.now(UTC)
    async with governance_store() as session:
        for index in range(2):
            session.add(
                Extension(
                    id=f"{index:032x}",
                    cloud_id="c" * 64,
                    domain_id=DOMAIN,
                    project_id=PROJECT,
                    instance_id=INSTANCE,
                    instance_name="queue fixture",
                    requested_by="human",
                    requested_at=stamp + timedelta(seconds=index),
                    expires_at=stamp + timedelta(days=7),
                    reason="evaluation",
                    schedule_revision="a" * 32,
                    policy_revision="b" * 32,
                    revision="c" * 32,
                    status="pending",
                )
            )
        await session.commit()
    first = (await client.get(f"{BASE}/usage-extension-requests", params={"limit": 1})).json()
    async with governance_store() as session:
        anchor = await session.get(Extension, first["items"][0]["id"])
        anchor.status = "rejected"
        await session.commit()
    second = await client.get(
        f"{BASE}/usage-extension-requests",
        params={"limit": 1, "cursor": first["next_cursor"]},
    )
    assert second.status_code == 200
    assert second.json()["items"][0]["id"] == f"{0:032x}"
    assert second.json()["items"][0]["status"] == "pending"


@pytest.mark.asyncio
@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"cursor": "not-a-cursor"}, {"cursor": "e30"}])
async def test_queue_rejects_invalid_bounds_and_cursor(client, usage_cloud, params):
    assert (await client.get(f"{BASE}/usage-extension-requests", params=params)).status_code == 422


@pytest.mark.asyncio
async def test_lost_graph_delayed_policy_write_cannot_overwrite_newer_manual_policy(
    mock_conn,
    governance_store,
    monkeypatch,
):
    import asyncio
    from contextlib import asynccontextmanager, suppress
    from types import SimpleNamespace

    from app.models.instance_usage_governance import UsagePolicyUpdate

    await manual(governance_store)
    entered = asyncio.Event()
    resume = asyncio.Event()
    ownership = {"lost": False}

    async def assert_owned():
        if ownership["lost"]:
            raise HTTPException(409, "Graph owner expired")

    @asynccontextmanager
    async def graph():
        yield SimpleNamespace(assert_owned=assert_owned)

    @asynccontextmanager
    async def delayed_sessions():
        async with governance_store() as session:
            execute = session.execute

            async def delayed_execute(statement, *args, **kwargs):
                if getattr(statement, "is_update", False) and statement.table.name == Policy.__tablename__:
                    # Simulate a database statement delayed after Redis proof,
                    # while another owner commits a newer review-required policy.
                    entered.set()
                    await resume.wait()
                return await execute(statement, *args, **kwargs)

            session.execute = delayed_execute
            yield session

    monkeypatch.setattr(governance, "governance_lock", graph)
    monkeypatch.setattr(governance, "session_scope", delayed_sessions)
    monkeypatch.setattr(governance, "live_access", AsyncMock(return_value=access(manager=True)))
    pending_write = asyncio.create_task(
        governance.set_policy(
            mock_conn,
            {"user_id": "manager", "domain_id": DOMAIN},
            UsagePolicyUpdate(review_required=False, revision="a" * 32),
            domain_id=DOMAIN,
        )
    )
    try:
        async with asyncio.timeout(3):
            await entered.wait()
        ownership["lost"] = True
        async with governance_store() as session:
            latest = await session.get(Policy, ("c" * 64, DOMAIN))
            latest.review_required = True
            latest.revision = "e" * 32
            await session.commit()
        resume.set()
        with pytest.raises(HTTPException) as stale:
            await pending_write
        assert stale.value.status_code == 409
        async with governance_store() as session:
            latest = await session.get(Policy, ("c" * 64, DOMAIN))
            assert latest.review_required is True
            assert latest.revision == "e" * 32
    finally:
        resume.set()
        if not pending_write.done():
            pending_write.cancel()
            with suppress(asyncio.CancelledError):
                await pending_write


@pytest.mark.asyncio
async def test_racing_default_policy_insert_cannot_replace_newer_manual_policy(
    mock_conn,
    governance_store,
    monkeypatch,
):
    from contextlib import asynccontextmanager

    from app.models.instance_usage_governance import UsagePolicyUpdate

    @asynccontextmanager
    async def delayed_sessions():
        async with governance_store() as session:
            commit = session.commit

            async def delayed_commit():
                # The old writer has read an absent row and passed its lease
                # check. Another owner inserts before this writer's flush.
                async with governance_store() as newer:
                    newer.add(
                        Policy(
                            cloud_id="c" * 64,
                            domain_id=DOMAIN,
                            review_required=True,
                            revision="e" * 32,
                            updated_by="new-manager",
                            updated_at=datetime.now(UTC),
                        )
                    )
                    await newer.commit()
                await commit()

            session.commit = delayed_commit
            yield session

    monkeypatch.setattr(governance, "session_scope", delayed_sessions)
    monkeypatch.setattr(governance, "live_access", AsyncMock(return_value=access(manager=True)))
    with pytest.raises(HTTPException) as stale:
        await governance.set_policy(
            mock_conn,
            {"user_id": "manager", "domain_id": DOMAIN},
            UsagePolicyUpdate(review_required=False, revision=governance.DEFAULT_REVISION),
            domain_id=DOMAIN,
        )
    assert stale.value.status_code == 409
    async with governance_store() as session:
        latest = await session.get(Policy, ("c" * 64, DOMAIN))
        assert latest.review_required is True
        assert latest.revision == "e" * 32


@pytest.mark.asyncio
@pytest.mark.parametrize("new_status", ["applying", "uncertain", "approved"])
async def test_delayed_rejection_cannot_overwrite_newer_native_intent(
    client, usage_cloud, governance_store, monkeypatch, new_status
):
    from contextlib import asynccontextmanager

    await manual(governance_store)
    row = await pending(client, usage_cloud)
    monkeypatch.setattr(governance, "live_access", AsyncMock(return_value=access(review=True)))

    @asynccontextmanager
    async def delayed_sessions():
        async with governance_store() as session:
            commit = session.commit

            async def delayed_commit():
                # A different owner advances the request after the old owner's
                # lease check, but before the old rejection flushes.
                async with governance_store() as newer:
                    current = await newer.get(Extension, row["id"])
                    current.status = new_status
                    current.revision = "e" * 32
                    await newer.commit()
                await commit()

            session.commit = delayed_commit
            yield session

    monkeypatch.setattr(governance, "session_scope", delayed_sessions)
    response = await review(client, row, "reject")
    assert response.status_code == 409
    async with governance_store() as session:
        current = await session.get(Extension, row["id"])
        assert current.status == new_status
        assert current.revision == "e" * 32
