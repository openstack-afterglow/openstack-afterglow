"""Isolated SQL regressions; native SDK and dispatcher boundaries are synthetic.

SQLite verifies snapshot/CAS behavior, not production MariaDB row-lock semantics.
"""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import ResourcePolicy
from app.services import resource_policies
from app.services import resource_policy_reconciliation as service
from app.services import resource_policy_store as store

COMPUTE = "nova.default_compute_availability_zone"
VOLUME = "cinder.default_volume_availability_zone"
PROJECT = "openstack.service_project"
NETWORK = "nova.default_network"
BUILDER = "builder.network"


@pytest_asyncio.fixture
async def policy_db(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'policies.sqlite'}")
    async with engine.begin() as conn:
        await conn.run_sync(ResourcePolicy.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(store, "is_db_available", lambda: True)
    monkeypatch.setattr(store, "get_session_factory", lambda: factory)
    yield factory, engine
    await engine.dispose()


async def _seed(factory, selections):
    async with factory() as session, session.begin():
        for key, resource_id in selections.items():
            session.add(
                ResourcePolicy(
                    policy_key=key,
                    resource_kind=resource_policies.get_spec(key).resource_kind,
                    resource_id=resource_id,
                    resource_name="old" if resource_id is not None else None,
                    constraints={"administrator": "preserve"},
                    updated_by_user_id="admin",
                )
            )


async def _rows(factory):
    async with factory() as session:
        return {
            row.policy_key: store._row_snapshot(row)
            for row in (await session.execute(select(ResourcePolicy))).scalars()
        }


def _conn(compute=(), volume=()):
    return SimpleNamespace(
        compute=SimpleNamespace(availability_zones=lambda: iter(compute)),
        block_storage=SimpleNamespace(availability_zones=lambda: iter(volume)),
        close=lambda: None,
    )


def _zone(name, available=True):
    return {"zoneName": name, "zoneState": {"available": available}}


@pytest.mark.asyncio
async def test_empty_database_initializes_only_unique_available_az_defaults(policy_db, monkeypatch):
    factory, engine = policy_db
    conn = _conn([_zone("internal"), _zone("disabled", False), _zone("nova")], [_zone("storage")])
    original = service._available_zones

    def discover(native_conn, spec):
        assert engine.sync_engine.pool.checkedout() == 0, "SQL session held across native discovery"
        return original(native_conn, spec)

    monkeypatch.setattr(service, "_available_zones", discover)
    assert await service.reconcile_once(conn) == 2
    rows = await _rows(factory)
    assert {key: row.resource_id for key, row in rows.items()} == {COMPUTE: "nova", VOLUME: "storage"}
    assert rows[COMPUTE].updated_by_user_id is None
    before = rows
    assert await service.reconcile_once(conn) == 0
    assert await _rows(factory) == before


@pytest.mark.asyncio
async def test_all_eleven_valid_ids_refresh_names_in_execution_scope(policy_db, monkeypatch):
    factory, engine = policy_db
    selections = {spec.key: f"id-{spec.key}" for spec in resource_policies.list_specs()}
    selections.update({COMPUTE: "nova", VOLUME: "storage"})
    await _seed(factory, selections)
    conn = _conn([_zone("nova"), _zone("second")], [_zone("storage")])
    closed = []
    service_conn = SimpleNamespace(close=lambda: closed.append(True))
    connection = AsyncMock(return_value=service_conn)
    monkeypatch.setattr(store, "get_service_project_connection", connection)
    observed = []

    def validate(native_conn, spec, resource_id):
        assert engine.sync_engine.pool.checkedout() == 0
        assert native_conn is (service_conn if spec.execution_scope == "service" else conn)
        observed.append(spec.key)
        return {"id": resource_id, "name": f"fresh-{resource_id}"}

    monkeypatch.setattr(resource_policies, "_validate_existing_sync", validate)
    assert await service.reconcile_once(conn) == 11
    rows = await _rows(factory)
    assert len(observed) == 9
    assert len(rows) == len(resource_policies.list_specs()) == 11
    assert {key: row.resource_id for key, row in rows.items()} == selections
    assert all(
        row.updated_by_user_id == "admin" and row.constraints == {"administrator": "preserve"} for row in rows.values()
    )
    assert rows[COMPUTE].resource_name == "nova"
    assert rows[BUILDER].resource_name == f"fresh-{selections[BUILDER]}"
    connection.assert_awaited_once_with(selections[PROJECT])
    assert closed == [True]
    assert await service.reconcile_once(conn) == 0
    assert await _rows(factory) == rows


@pytest.mark.parametrize("existing", [None, "deleted-zone"])
@pytest.mark.parametrize("catalog", [[], [_zone("one"), _zone("two")], [_zone("offline", False)]])
@pytest.mark.asyncio
async def test_missing_or_invalid_az_with_no_unique_candidate_is_unchanged(policy_db, existing, catalog):
    factory, _ = policy_db
    if existing is not None:
        await _seed(factory, {COMPUTE: existing})
    before = await _rows(factory)
    assert await service.reconcile_once(_conn(catalog)) == 0
    assert await _rows(factory) == before


@pytest.mark.parametrize(
    "catalog",
    [
        [{"zoneName": "one"}],
        [_zone("one"), {"zoneName": "incomplete", "zoneState": {}}],
        [{"zoneName": "one", "zoneState": {"available": "true"}}],
        [_zone("one"), _zone("one")],
        [_zone("one"), {"zoneState": {"available": True}}],
    ],
)
@pytest.mark.asyncio
async def test_incomplete_native_catalog_cannot_repair_an_az(policy_db, catalog):
    factory, _ = policy_db
    await _seed(factory, {COMPUTE: "deleted-zone"})
    before = await _rows(factory)
    assert await service.reconcile_once(_conn(catalog)) == 0
    assert await _rows(factory) == before


@pytest.mark.asyncio
async def test_partial_catalog_failure_preserves_saved_and_absent_defaults(policy_db):
    factory, _ = policy_db
    await _seed(factory, {COMPUTE: "deleted-zone"})
    before = await _rows(factory)

    def partial():
        yield _zone("only-observed")
        raise RuntimeError("native page unavailable")

    conn = _conn()
    conn.compute.availability_zones = partial
    conn.block_storage.availability_zones = partial
    assert await service.reconcile_once(conn) == 0
    assert await _rows(factory) == before


@pytest.mark.parametrize("key", [COMPUTE, VOLUME])
@pytest.mark.asyncio
async def test_present_unavailable_saved_az_preserved_despite_unique_available_alternative(policy_db, key):
    factory, _ = policy_db
    await _seed(factory, {key: "offline"})
    before = await _rows(factory)
    catalog = [_zone("offline", False), _zone("replacement")]
    conn = _conn(compute=catalog if key == COMPUTE else (), volume=catalog if key == VOLUME else ())
    assert await service.reconcile_once(conn) == 0
    assert await _rows(factory) == before


@pytest.mark.parametrize("key", [COMPUTE, VOLUME])
@pytest.mark.asyncio
async def test_saved_internal_zone_repairs_to_unique_valid_candidate(policy_db, key):
    factory, _ = policy_db
    await _seed(factory, {key: "internal"})
    catalog = [_zone("internal"), _zone("valid-zone")]
    conn = _conn(compute=catalog if key == COMPUTE else (), volume=catalog if key == VOLUME else ())
    assert await service.reconcile_once(conn) == 1
    row = (await _rows(factory))[key]
    assert row.resource_id == row.resource_name == "valid-zone"
    assert row.updated_by_user_id == "admin"


@pytest.mark.asyncio
async def test_invalid_az_repaired_but_explicit_administrator_clear_preserved(policy_db):
    factory, _ = policy_db
    await _seed(factory, {COMPUTE: "removed", VOLUME: None})
    before = await _rows(factory)
    assert await service.reconcile_once(_conn([_zone("new")], [_zone("storage")])) == 1
    rows = await _rows(factory)
    assert rows[COMPUTE].resource_id == "new"
    assert rows[COMPUTE].updated_by_user_id == "admin"
    assert rows[VOLUME] == before[VOLUME]


@pytest.mark.asyncio
async def test_stale_non_az_and_native_outage_do_not_change_any_id(policy_db, monkeypatch):
    factory, _ = policy_db
    await _seed(factory, {NETWORK: "deleted-network", PROJECT: "service-project", BUILDER: "builder-network"})
    before = await _rows(factory)

    def validate(_conn, spec, _resource_id):
        if spec.key == NETWORK:
            raise resource_policies.ResourcePolicyValidationError("invalid")
        raise RuntimeError("identity unavailable")

    monkeypatch.setattr(resource_policies, "_validate_existing_sync", validate)
    monkeypatch.setattr(
        store, "get_service_project_connection", AsyncMock(side_effect=RuntimeError("scope unavailable"))
    )
    assert await service.reconcile_once(_conn()) == 0
    assert await _rows(factory) == before


@pytest.mark.asyncio
async def test_discovery_cannot_replace_a_non_az_id_even_if_native_returns_another(policy_db, monkeypatch):
    factory, _ = policy_db
    await _seed(factory, {NETWORK: "exact-id"})
    before = await _rows(factory)
    monkeypatch.setattr(resource_policies, "_validate_existing_sync", lambda *_: {"id": "other", "name": "Other"})
    assert await service.reconcile_once(_conn()) == 0
    assert await _rows(factory) == before
    assert not await store.apply_reconciled_policy(
        key=NETWORK, expected=before[NETWORK], resource_id="other", resource_name="Other"
    )


@pytest.mark.parametrize(
    "mutation", ["resource_id", "resource_name", "constraints", "updated_by_user_id", "updated_at", "created_at"]
)
@pytest.mark.asyncio
async def test_full_row_identity_and_aba_timestamp_fence_stale_refresh(policy_db, mutation):
    factory, _ = policy_db
    await _seed(factory, {NETWORK: "network"})
    snapshot = await store.reconciliation_snapshot()
    async with factory() as session, session.begin():
        row = await session.get(ResourcePolicy, NETWORK)
        if mutation.endswith("_at"):
            setattr(row, mutation, getattr(row, mutation) + timedelta(seconds=1))
        elif mutation == "constraints":
            row.constraints = {"new-administrator-decision": True}
        else:
            setattr(row, mutation, "new-administrator-decision")
    before = await _rows(factory)
    assert not await store.apply_reconciled_policy(
        key=NETWORK, expected=snapshot[NETWORK], resource_id="network", resource_name="native-new-name"
    )
    assert await _rows(factory) == before


@pytest.mark.asyncio
async def test_concurrent_administrator_update_wins_after_native_discovery(policy_db, monkeypatch):
    factory, _ = policy_db
    await _seed(factory, {COMPUTE: "removed"})
    original = store.apply_reconciled_policy

    async def concurrent(**kwargs):
        async with factory() as session, session.begin():
            row = await session.get(ResourcePolicy, COMPUTE)
            row.resource_id = "administrator-zone"
            row.resource_name = "Administrator choice"
        return await original(**kwargs)

    monkeypatch.setattr(store, "apply_reconciled_policy", concurrent)
    assert await service.reconcile_once(_conn([_zone("unique")])) == 0
    assert (await _rows(factory))[COMPUTE].resource_id == "administrator-zone"


@pytest.mark.asyncio
async def test_concurrent_absent_row_insert_is_conflict_safe(policy_db, monkeypatch):
    factory, _ = policy_db
    original = store.apply_reconciled_policy

    async def concurrent(**kwargs):
        await _seed(factory, {COMPUTE: None})
        return await original(**kwargs)

    monkeypatch.setattr(store, "apply_reconciled_policy", concurrent)
    assert await service.reconcile_once(_conn([_zone("unique")])) == 0
    row = (await _rows(factory))[COMPUTE]
    assert row.resource_id is None
    assert row.updated_by_user_id == "admin"


@pytest.mark.parametrize("new_id", ["different-service", "service-project"])
@pytest.mark.asyncio
async def test_service_scope_change_or_aba_blocks_child_refresh(policy_db, new_id):
    factory, _ = policy_db
    await _seed(factory, {PROJECT: "service-project", BUILDER: "network"})
    snapshot = await store.reconciliation_snapshot()
    async with factory() as session, session.begin():
        scope = await session.get(ResourcePolicy, PROJECT)
        scope.resource_id = new_id
        scope.updated_at += timedelta(seconds=1)
    before = await _rows(factory)
    assert not await store.apply_reconciled_policy(
        key=BUILDER,
        expected=snapshot[BUILDER],
        resource_id="network",
        resource_name="new-native-name",
        service_project=snapshot[PROJECT],
    )
    assert await _rows(factory) == before


@pytest.mark.asyncio
async def test_service_setter_uses_exact_scope_and_rejects_changed_parent(policy_db, monkeypatch):
    factory, _ = policy_db
    await _seed(factory, {PROJECT: "service-project"})
    conn = _conn()
    connection = AsyncMock(return_value=conn)
    monkeypatch.setattr(store, "get_service_project_connection", connection)

    async def validate(native_conn, key, resource_id):
        assert native_conn is conn
        assert key == BUILDER
        async with factory() as session, session.begin():
            scope = await session.get(ResourcePolicy, PROJECT)
            scope.updated_at += timedelta(seconds=1)
        return {"id": resource_id, "name": "network"}

    monkeypatch.setattr(store, "validate_selection", validate)
    with pytest.raises(resource_policies.ResourcePolicyValidationError, match="service project changed"):
        await store.set_policy(conn=object(), key=BUILDER, resource_id="network", updated_by_user_id="admin")
    connection.assert_awaited_once_with("service-project")
    assert BUILDER not in await _rows(factory)


@pytest.mark.asyncio
async def test_repeated_administrator_write_advances_aba_timestamp(policy_db, monkeypatch):
    factory, _ = policy_db
    monkeypatch.setattr(store, "validate_selection", AsyncMock(return_value={"id": "network", "name": "network"}))
    await store.set_policy(conn=object(), key=NETWORK, resource_id="network", updated_by_user_id="admin")
    before = (await _rows(factory))[NETWORK]
    await store.set_policy(conn=object(), key=NETWORK, resource_id="network", updated_by_user_id="admin")
    after = (await _rows(factory))[NETWORK]
    assert after.updated_at > before.updated_at
    assert not await store.apply_reconciled_policy(
        key=NETWORK, expected=before, resource_id="network", resource_name="new-native-name"
    )


@pytest.mark.parametrize("writer", ["administrator", "reconciliation"])
@pytest.mark.asyncio
async def test_zero_fractional_storage_fences_same_second_aba_for_every_writer(policy_db, monkeypatch, writer):
    factory, engine = policy_db
    # Model the generic auto-created MySQL DATETIME column, not DATETIME(6).
    # Both INSERT and UPDATE lose every fractional digit in actual SQL storage.
    async with engine.begin() as connection:
        for operation in ("INSERT", "UPDATE"):
            await connection.exec_driver_sql(
                f"""CREATE TRIGGER coarse_policy_{operation.lower()}
                AFTER {operation} ON resource_policies
                WHEN instr(NEW.updated_at, '.') > 0
                BEGIN
                    UPDATE resource_policies
                    SET updated_at = strftime('%Y-%m-%d %H:%M:%S', NEW.updated_at)
                    WHERE policy_key = NEW.policy_key;
                END"""
            )

    class FixedClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2030, 1, 1, 12, 0, 0, 123456, tzinfo=UTC)

    monkeypatch.setattr(store, "datetime", FixedClock)

    async def validate(_conn, _key, resource_id):
        return {"id": resource_id, "name": resource_id}

    monkeypatch.setattr(store, "validate_selection", validate)
    await store.set_policy(conn=object(), key=NETWORK, resource_id="A", updated_by_user_id="admin")
    before = (await _rows(factory))[NETWORK]
    assert before.updated_at.microsecond == 0
    if writer == "administrator":
        for resource_id in ("B", "A"):
            await store.set_policy(conn=object(), key=NETWORK, resource_id=resource_id, updated_by_user_id="admin")
    else:
        for name in ("B", "A"):
            current = (await _rows(factory))[NETWORK]
            assert await store.apply_reconciled_policy(
                key=NETWORK, expected=current, resource_id="A", resource_name=name
            )
    after = (await _rows(factory))[NETWORK]
    assert replace(after, updated_at=before.updated_at) == before
    assert after.updated_at.microsecond == 0
    assert after.updated_at >= before.updated_at + timedelta(seconds=2)
    assert not await store.apply_reconciled_policy(
        key=NETWORK, expected=before, resource_id="A", resource_name="stale-observation"
    )


@pytest.mark.asyncio
async def test_loop_runs_immediately_then_every_sixty_seconds_and_closes(policy_db, monkeypatch):
    conn = object()
    calls = []
    monkeypatch.setattr(service, "open_connection", AsyncMock(return_value=conn))
    monkeypatch.setattr(
        service, "close_connection", AsyncMock(side_effect=lambda value: calls.append(("close", value)))
    )
    monkeypatch.setattr(
        service, "reconcile_once", AsyncMock(side_effect=lambda value: calls.append(("reconcile", value)))
    )

    async def sleep(seconds):
        calls.append(("sleep", seconds))
        raise asyncio.CancelledError

    monkeypatch.setattr(service.asyncio, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        await service.reconciliation_loop()
    assert calls == [("reconcile", conn), ("close", conn), ("sleep", 60)]


@pytest.mark.asyncio
async def test_loop_cancellation_drains_native_observation_and_closes_connection(policy_db, monkeypatch):
    import threading

    entered = threading.Event()
    release = threading.Event()
    closed = []
    conn = _conn()
    conn.close = lambda: closed.append("close")

    def zones():
        entered.set()
        release.wait(5)
        closed.append("drained")
        return [_zone("nova")]

    conn.compute.availability_zones = zones
    monkeypatch.setattr(service, "open_connection", AsyncMock(return_value=conn))
    operation = asyncio.create_task(service.reconciliation_loop())
    assert await asyncio.to_thread(entered.wait, 5)
    operation.cancel()
    await asyncio.sleep(0)
    assert closed == []
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await operation
    assert closed == ["drained", "close"]
    factory, _ = policy_db
    assert await _rows(factory) == {}
