"""GitHub SSH verification history — MariaDB persistence integration tests.

Run with AFTERGLOW_TEST_DATABASE_URL=mysql+aiomysql://... pytest -m db.
"""

from __future__ import annotations

import asyncio
import os

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import create_async_engine

import app.models.db  # noqa: F401 — registers ORM models with Base metadata
from app import database as db_mod
from app.models.db import VmGithubSshUser
from app.services import github_ssh

pytestmark = [pytest.mark.db, pytest.mark.asyncio]

_DB_URL_ENV = "AFTERGLOW_TEST_DATABASE_URL"


@pytest.fixture(scope="module")
def db_url():
    url = os.environ.get(_DB_URL_ENV)
    if not url:
        pytest.skip(f"{_DB_URL_ENV} 미설정 — MariaDB 통합 테스트 건너뜀")
    return url


@pytest.fixture(scope="module")
def db_tables(db_url):
    from app.database import Base

    async def setup():
        engine = create_async_engine(db_url, echo=False, pool_pre_ping=True)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    async def teardown():
        engine = create_async_engine(db_url, echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()

    asyncio.run(setup())
    yield
    asyncio.run(teardown())


@pytest_asyncio.fixture
async def live_db(db_tables, db_url):
    db_mod.init_db(db_url)
    yield
    factory = db_mod.get_session_factory()
    async with factory() as session:
        await session.execute(text("DELETE FROM vm_github_ssh_users"))
        await session.commit()
    await db_mod.close_db()


def _profile(github_id: int, login: str) -> dict[str, object]:
    return {"id": github_id, "login": login}


async def test_history_upserts_by_user_and_github_identity(live_db):
    first_verified = await github_ssh._upsert_history(user_id="user-a", profile=_profile(1, "octocat"))
    second_verified = await github_ssh._upsert_history(user_id="user-a", profile=_profile(1, "OctoCat"))
    await github_ssh._upsert_history(user_id="user-b", profile=_profile(1, "octocat"))

    assert second_verified >= first_verified
    assert await github_ssh.list_history(user_id="user-a") == [
        {"id": 1, "login": "OctoCat", "verified_at": second_verified}
    ]
    assert (await github_ssh.list_history(user_id="user-b"))[0]["login"] == "octocat"

    factory = db_mod.get_session_factory()
    async with factory() as session:
        count = await session.scalar(select(func.count()).select_from(VmGithubSshUser))
    assert count == 2


async def test_history_retains_latest_twenty_per_user(live_db):
    for index in range(21):
        await github_ssh._upsert_history(user_id="user-a", profile=_profile(index + 1, f"user-{index + 1}"))

    history = await github_ssh.list_history(user_id="user-a")

    assert len(history) == 20
    assert {entry["id"] for entry in history} == set(range(2, 22))
