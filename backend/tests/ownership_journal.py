"""Real disposable SQL journal boundary for synthetic Keystone role tests."""

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.models.project_ownership import ProjectOwnershipTransfer
from app.services import project_ownership_journal


@pytest_asyncio.fixture
async def ownership_journal(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync: Base.metadata.create_all(sync, tables=[ProjectOwnershipTransfer.__table__]))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(project_ownership_journal, "get_session_factory", lambda: factory)
    try:
        yield factory
    finally:
        await engine.dispose()
