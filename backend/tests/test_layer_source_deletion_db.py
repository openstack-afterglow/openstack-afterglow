"""Source/DELETE races through HTTP and real MariaDB row locks.

Run in the disposable functional database with ``pytest -m db`` and
AFTERGLOW_TEST_DATABASE_URL. SQLite cannot represent SELECT FOR UPDATE.
Provider evidence is synthetic loopback OpenStack, never live cloud allocation.
"""

from __future__ import annotations

import asyncio
import os
import threading
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import deps
from app.api.union import layer_block_sources, layer_ops
from app.database import Base
from app.models.db import LayerArtifact, LayerBuild, LayerConsume, LayerProfile
from app.services import glance, keystone, layer_block, manila
from tests.test_layer_block import DATA, METADATA
from tests.test_layer_block import block_provider as block_provider

pytestmark = [pytest.mark.db, pytest.mark.asyncio]
_TABLES = [model.__table__ for model in (LayerArtifact, LayerBuild, LayerConsume, LayerProfile)]


@pytest_asyncio.fixture
async def source_race(block_provider, monkeypatch):
    url = os.environ.get("AFTERGLOW_TEST_DATABASE_URL")
    if not url:
        pytest.skip("AFTERGLOW_TEST_DATABASE_URL is required for MariaDB row-lock behavior")
    engine = create_async_engine(url)
    if engine.dialect.name not in {"mysql", "mariadb"}:
        await engine.dispose()
        pytest.skip("SQLite cannot represent the artifact FOR UPDATE transaction")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    conn, provider, entry = block_provider
    conn._afterglow_project_id = "service"
    monkeypatch.setattr(conn.session, "get_project_id", lambda: "service")
    # The fixture owns this loopback connection until consumer verification ends.
    monkeypatch.setattr(conn, "close", lambda: None)
    provider.image = None
    entry = dict(entry)
    name = "race-" + uuid4().hex[:20]
    build_id = consume_id = artifact_id = None
    tasks = []
    gates = []
    try:
        async with engine.begin() as connection:
            await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=_TABLES))
        async with factory() as session:
            old = datetime.now(UTC) - timedelta(days=2)
            # Both helpers have real changes to commit. Neither may drop the
            # deletion lock; they must finish before that transaction begins.
            build = LayerBuild(
                layer_name=name,
                kind="pip",
                share_id="",
                status="building",
                started_at=old,
                created_at=old,
                updated_at=old,
            )
            consume = LayerConsume(
                profile_name=name,
                share_id="",
                status="creating",
                created_at=old,
                updated_at=old,
            )
            session.add_all([build, consume])
            await session.flush()
            build_id, consume_id = build.id, consume.id
            artifact = LayerArtifact(
                name=name,
                kind="pip",
                sqsh_filename=name + ".sqsh",
                share_id="share-" + name,
                chain_id=entry["chain_id"],
                blob_digest=entry["blob_digest"],
                size_bytes=len(DATA),
                is_sealed=True,
                digest_state="ready",
            )
            session.add(artifact)
            await session.commit()
            artifact_id = artifact.id
            entry["id"] = artifact_id
            entry["block_source"] = None
        monkeypatch.setattr(layer_ops, "get_session_factory", lambda: factory)
        monkeypatch.setattr(layer_block_sources, "get_session_factory", lambda: factory)
        monkeypatch.setattr(layer_block_sources, "get_service_project_connection", lambda: conn)
        monkeypatch.setattr(keystone, "get_service_project_connection", lambda: conn)
        destructive = []
        monkeypatch.setattr(manila, "list_access_rules", lambda *_args: [])
        monkeypatch.setattr(manila, "revoke_access_rule", lambda *args: destructive.append(("revoke", args)))
        monkeypatch.setattr(manila, "delete_file_storage", lambda *args: destructive.append(("delete", args)))
        app = FastAPI()
        app.include_router(layer_ops.router)
        app.dependency_overrides[deps.require_admin] = lambda: {"is_system_admin": True}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            base = f"/artifacts/{artifact_id}"
            race = SimpleNamespace(
                factory=factory,
                conn=conn,
                provider=provider,
                entry=entry,
                client=client,
                base=base,
                publication=base + "/block-source?store_id=rbd&member_project_id=caller",
                destructive=destructive,
                tasks=tasks,
                gates=gates,
            )
            yield race
    finally:
        # Release provider threads and async barriers even if an assertion fails.
        for gate in gates:
            gate.set()
        if tasks:
            await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=15)
        async with factory() as session:
            if artifact_id is not None:
                await session.execute(delete(LayerArtifact).where(LayerArtifact.id == artifact_id))
            if consume_id is not None:
                await session.execute(delete(LayerConsume).where(LayerConsume.id == consume_id))
            if build_id is not None:
                await session.execute(delete(LayerBuild).where(LayerBuild.id == build_id))
            await session.commit()
        await engine.dispose()


def start(race, awaitable):
    task = asyncio.create_task(awaitable)
    race.tasks.append(task)
    return task


async def wait_for(event):
    await asyncio.wait_for(event.wait(), timeout=10)


async def assert_artifact_locked(race):
    """NOWAIT proves the lock while a provider is paused, without sleep/racy timing.

    This executes a competing transaction, not a SQL-generation assertion. MariaDB
    returns ER_LOCK_WAIT_TIMEOUT for NOWAIT; MySQL uses ER_LOCK_NOWAIT.
    """
    async with race.factory() as session:
        with pytest.raises(OperationalError) as caught:
            await session.execute(
                select(LayerArtifact).where(LayerArtifact.id == race.entry["id"]).with_for_update(nowait=True)
            )
        assert caught.value.orig.args[0] in {1205, 3572}
        await session.rollback()


async def prove_consumer(race, source, monkeypatch):
    """The retained publication still materializes the sealed bytes for a consumer."""
    fetched = await race.client.get(race.base + "/block-source")
    assert fetched.status_code == 200
    assert fetched.json()["block_source"] == source
    race.entry["block_source"] = source
    race.conn._afterglow_project_id = "caller"
    monkeypatch.setattr(race.conn.session, "get_project_id", lambda: "caller")
    await asyncio.to_thread(layer_block.validate_sources, race.conn, [race.entry])
    volume = await asyncio.to_thread(
        race.conn.block_storage.create_volume,
        **layer_block.layer_volume_create_options(race.conn, race.entry, "retained-source-consumer", METADATA),
    )
    prepared = await asyncio.to_thread(layer_block.prepare_layer_volume, race.conn, volume.id, race.entry, METADATA)
    assert prepared["metadata"]["readonly"] == "True"
    assert prepared["volume_image_metadata"]["image_id"] == source["image_id"]
    assert race.provider.data == DATA
    assert race.provider.image["protected"] is True


async def test_reservation_wins_stale_delete_and_preserves_pending_recovery(source_race, monkeypatch):
    race = source_race
    reconciling = asyncio.Event()
    reconcile_release = asyncio.Event()
    reserved = asyncio.Event()
    publish_release = asyncio.Event()
    race.gates.extend([reconcile_release, publish_release])
    sync = layer_ops._sync_consume_rows_with_nova
    reserve = layer_block_sources._reserve

    async def pause_reconciliation(session, rows):
        # DELETE already has its old target in this real session's identity map.
        reconciling.set()
        await reconcile_release.wait()
        await sync(session, rows)

    async def pause_after_reservation(*args):
        source = await reserve(*args)
        reserved.set()
        await publish_release.wait()
        return source

    monkeypatch.setattr(layer_ops, "_sync_consume_rows_with_nova", pause_reconciliation)
    monkeypatch.setattr(layer_block_sources, "_reserve", pause_after_reservation)
    deleting = start(race, race.client.delete(race.base))
    await wait_for(reconciling)
    publishing = start(race, race.client.put(race.publication, content=DATA))
    await wait_for(reserved)
    pending = (await race.client.get(race.base + "/block-source")).json()["block_source"]
    assert pending["state"] == "pending"
    assert race.provider.image is None
    reconcile_release.set()
    rejected = await asyncio.wait_for(deleting, timeout=10)
    assert rejected.status_code == 409
    assert "retained_block_source" in {b["type"] for b in rejected.json()["detail"]["delete_blockers"]}
    assert race.destructive == []
    async with race.factory() as session:
        row = await session.get(LayerArtifact, race.entry["id"])
        assert row.block_source == pending
    publish_release.set()
    published = await asyncio.wait_for(publishing, timeout=10)
    assert published.status_code == 200
    assert published.json()["image_id"] == pending["image_id"]
    assert published.json()["upload_id"] == pending["upload_id"]
    await prove_consumer(race, published.json(), monkeypatch)


async def test_delete_wins_manila_wait_and_publication_gets_404_without_image_creation(source_race, monkeypatch):
    race = source_race
    ready_to_reserve = asyncio.Event()
    reserve_release = asyncio.Event()
    reserve_attempt = asyncio.Event()
    manila_started = asyncio.Event()
    manila_release = threading.Event()
    race.gates.extend([reserve_release, manila_release])
    reserve = layer_block_sources._reserve
    loop = asyncio.get_running_loop()

    async def pause_before_reservation(*args):
        # Publication has read and verified the artifact but has not reserved it.
        ready_to_reserve.set()
        await reserve_release.wait()
        reserve_attempt.set()
        return await reserve(*args)

    def pause_manila(*args):
        loop.call_soon_threadsafe(manila_started.set)
        if not manila_release.wait(timeout=15):
            raise TimeoutError("test did not release Manila deletion")
        race.destructive.append(("delete", args))

    monkeypatch.setattr(layer_block_sources, "_reserve", pause_before_reservation)
    monkeypatch.setattr(manila, "delete_file_storage", pause_manila)
    publishing = start(race, race.client.put(race.publication, content=DATA))
    await wait_for(ready_to_reserve)
    deleting = start(race, race.client.delete(race.base))
    await wait_for(manila_started)
    await assert_artifact_locked(race)
    reserve_release.set()
    await wait_for(reserve_attempt)
    assert race.provider.image is None
    assert not any(call[0] == "POST" for call in race.provider.calls)
    manila_release.set()
    deleted, rejected = await asyncio.wait_for(asyncio.gather(deleting, publishing), timeout=10)
    assert deleted.status_code == 200
    assert rejected.status_code == 404
    assert len(race.destructive) == 1
    assert race.provider.image is None
    assert not any(call[0] == "POST" for call in race.provider.calls)
    assert (await race.client.get(race.base + "/block-source")).status_code == 404
    async with race.factory() as session:
        assert await session.get(LayerArtifact, race.entry["id"]) is None


async def test_protected_glance_creation_fences_delete_without_provider_db_deadlock(source_race, monkeypatch):
    race = source_race
    creating = asyncio.Event()
    reconciled = asyncio.Event()
    create_release = threading.Event()
    race.gates.append(create_release)
    allocate = glance.allocate_source_image
    sync = layer_ops._sync_build_rows_timeouts
    loop = asyncio.get_running_loop()

    def pause_creation(*args):
        loop.call_soon_threadsafe(creating.set)
        if not create_release.wait(timeout=15):
            raise TimeoutError("test did not release Glance creation")
        return allocate(*args)

    async def report_reconciled(session, rows):
        await sync(session, rows)
        reconciled.set()

    monkeypatch.setattr(glance, "allocate_source_image", pause_creation)
    monkeypatch.setattr(layer_ops, "_sync_build_rows_timeouts", report_reconciled)
    publishing = start(race, race.client.put(race.publication, content=DATA))
    await wait_for(creating)
    await assert_artifact_locked(race)
    deleting = start(race, race.client.delete(race.base))
    # The reconciliation commits complete without waiting for the publisher's
    # provider. DELETE only then queues for the same artifact lock.
    await wait_for(reconciled)
    assert race.destructive == []
    create_release.set()
    published, rejected = await asyncio.wait_for(asyncio.gather(publishing, deleting), timeout=10)
    assert published.status_code == 200
    assert rejected.status_code == 409
    assert race.destructive == []
    await prove_consumer(race, published.json(), monkeypatch)


async def test_cancelled_delete_keeps_artifact_locked_until_provider_and_sql_complete(source_race, monkeypatch):
    race = source_race
    manila_started = asyncio.Event()
    manila_release = threading.Event()
    publication_attempted = asyncio.Event()
    race.gates.append(manila_release)
    loop = asyncio.get_running_loop()
    locked = layer_block_sources._locked

    def pause_delete(*args):
        loop.call_soon_threadsafe(manila_started.set)
        if not manila_release.wait(timeout=15):
            raise TimeoutError("deletion not released")
        race.destructive.append(("delete", args))

    async def observe_lock(*args):
        publication_attempted.set()
        return await locked(*args)

    monkeypatch.setattr(manila, "delete_file_storage", pause_delete)
    monkeypatch.setattr(layer_block_sources, "_locked", observe_lock)
    deleting = start(race, race.client.delete(race.base))
    await wait_for(manila_started)
    deleting.cancel()
    await assert_artifact_locked(race)
    publishing = start(race, race.client.put(race.publication, content=DATA))
    await wait_for(publication_attempted)
    deleting.cancel()
    await assert_artifact_locked(race)
    assert race.provider.image is None
    manila_release.set()
    deleted, published = await asyncio.wait_for(
        asyncio.gather(deleting, publishing, return_exceptions=True), timeout=10
    )
    assert isinstance(deleted, asyncio.CancelledError)
    assert published.status_code == 404
    assert len(race.destructive) == 1
    assert race.provider.image is None
    async with race.factory() as session:
        assert await session.get(LayerArtifact, race.entry["id"]) is None
