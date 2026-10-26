"""Managed catalog publication races on the explicitly disposable SQL target.

SQLite tests cover orchestration; this selector checks real FOR UPDATE behavior.
No provider or operational settings are consulted.
"""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.models.db import LayerArtifact, LayerBuild, LayerConsume, LayerProfile
from app.services import palimpsest_catalog as catalog
from app.services.palimpsest_digest import compute_chain_id

pytestmark = [pytest.mark.db, pytest.mark.asyncio]


async def test_publication_withdrawal_wins_before_locked_consume_snapshot():
    url = os.environ.get("AFTERGLOW_TEST_DATABASE_URL")
    if not url:
        pytest.skip("AFTERGLOW_TEST_DATABASE_URL is required for the isolated SQL race")
    engine = create_async_engine(url)
    if engine.dialect.name not in {"mysql", "mariadb"}:
        await engine.dispose()
        pytest.skip("SQLite cannot prove row-lock publication fencing")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    name = "catalog-race-" + uuid4().hex[:16]
    root_id = child_id = profile_id = None
    pending = None
    try:
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda sync: Base.metadata.create_all(
                    sync, tables=[model.__table__ for model in (LayerBuild, LayerArtifact, LayerConsume, LayerProfile)]
                )
            )
        async with factory() as session:
            root_digest = "sha256:" + "a" * 64
            root = LayerArtifact(
                name=name + "-root",
                kind="python",
                share_id="root",
                sqsh_filename="root.sqsh",
                is_published=True,
                is_sealed=True,
                digest_state="ready",
                blob_digest=root_digest,
                chain_id=compute_chain_id(None, root_digest),
                base_image_id="base",
            )
            session.add(root)
            await session.flush()
            root_id = root.id
            child_digest = "sha256:" + "b" * 64
            child = LayerArtifact(
                name=name + "-child",
                kind="pip",
                share_id="child",
                sqsh_filename="child.sqsh",
                is_published=True,
                is_sealed=True,
                digest_state="ready",
                blob_digest=child_digest,
                chain_id=compute_chain_id(root.chain_id, child_digest),
                base_image_id="base",
                parent_id=root_id,
            )
            session.add(child)
            profile = LayerProfile(name=name, layers=[child.name], is_published=True)
            session.add(profile)
            await session.commit()
            child_id, profile_id = child.id, profile.id
        entered = asyncio.Event()

        async def admit():
            async with factory() as session:
                entered.set()
                return await catalog.published_snapshot(session, profile_id, lock=True)

        async with factory() as writer:
            root = await writer.get(LayerArtifact, root_id, with_for_update=True)
            root.is_published = False
            await writer.flush()
            pending = asyncio.create_task(admit())
            await entered.wait()
            await asyncio.sleep(0.1)
            assert not pending.done(), "consume admission must wait on ancestor publication authority"
            await writer.commit()
        with pytest.raises(HTTPException) as withdrawn:
            await asyncio.wait_for(pending, 5)
        assert withdrawn.value.status_code == 409
        async with factory() as session:
            assert (
                await session.execute(select(LayerConsume).where(LayerConsume.profile_name == name))
            ).scalar_one_or_none() is None
    finally:
        if pending is not None and not pending.done():
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
        async with factory() as session:
            if profile_id is not None:
                await session.execute(delete(LayerProfile).where(LayerProfile.id == profile_id))
            if child_id is not None:
                await session.execute(delete(LayerArtifact).where(LayerArtifact.id == child_id))
            if root_id is not None:
                await session.execute(delete(LayerArtifact).where(LayerArtifact.id == root_id))
            await session.commit()
        await engine.dispose()
