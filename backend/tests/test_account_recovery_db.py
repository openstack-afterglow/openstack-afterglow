"""Recovery one-dispatch fences with actual MariaDB transactions and row locks."""

import os
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.account_recovery import AccountRecovery
from tests.test_account_recovery import competing_resets
from tests.test_account_recovery import directory as directory
from tests.test_account_recovery import (
    test_cancelled_request_drains_native_write_and_session_revocation as cancellation_scenario,
)
from tests.test_account_recovery import (
    test_committed_dispatch_fence_survives_final_sql_failure as sql_failure_scenario,
)

pytestmark = [pytest.mark.db, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def recovery_db(directory):
    url = os.environ.get("AFTERGLOW_TEST_DATABASE_URL")
    if not url:
        pytest.skip("AFTERGLOW_TEST_DATABASE_URL is required for recovery row-lock tests")
    engine = create_async_engine(url)
    if engine.dialect.name not in {"mysql", "mariadb"}:
        await engine.dispose()
        pytest.skip("MariaDB is required for recovery FOR UPDATE semantics")
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync: AccountRecovery.__table__.create(sync, checkfirst=True))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    uid = "recovery-" + uuid4().hex
    directory.users["local"].id = uid
    yield factory
    async with factory() as session:
        await session.execute(delete(AccountRecovery).where(AccountRecovery.user_id == uid))
        await session.commit()
    await engine.dispose()


async def test_concurrent_resets_have_one_native_dispatch(directory, recovery_db):
    await competing_resets(directory, recovery_db)


async def test_native_completion_retains_consumed_fence_on_sql_failure(directory, recovery_db, monkeypatch):
    await sql_failure_scenario(directory, recovery_db, monkeypatch)


async def test_cancelled_native_dispatch_finishes_before_lease_release(directory, recovery_db):
    await cancellation_scenario(directory, recovery_db)
