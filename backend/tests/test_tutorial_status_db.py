"""tutorial_status 서비스 — MariaDB 실 SQL 통합 테스트.

upsert(신규 insert / 기존 update), 사용자 격리, 화이트리스트 검증을 실 DB 로 확인한다
(tests/test_announcements_db.py 패턴 준용).

실행: AFTERGLOW_TEST_DATABASE_URL=mysql+aiomysql://afterglow:dev@127.0.0.1:3306/afterglow_pytest \
     pytest tests/test_tutorial_status_db.py -v -m db
"""

from __future__ import annotations

import asyncio
import os

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

import app.models.db  # noqa: F401 — side-effect: Base에 ORM 모델 등록
from app import database as db_mod
from app.services import tutorial_status as svc

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

    async def _setup():
        engine = create_async_engine(db_url, echo=False, pool_pre_ping=True)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    async def _teardown():
        engine = create_async_engine(db_url, echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()

    asyncio.run(_setup())
    yield
    asyncio.run(_teardown())


@pytest_asyncio.fixture
async def live_db(db_tables, db_url):
    db_mod.init_db(db_url)
    yield
    factory = db_mod.get_session_factory()
    async with factory() as session:
        await session.execute(text("DELETE FROM user_tutorial_statuses"))
        await session.commit()
    await db_mod.close_db()


async def test_set_and_get_status(live_db):
    await svc.set_status(user_id="user-a", tour_id="vm-create", status="completed")
    statuses = await svc.get_user_statuses("user-a")
    assert statuses == {"vm-create": "completed"}


async def test_upsert_overwrites_existing_status(live_db):
    await svc.set_status(user_id="user-a", tour_id="volume", status="dismissed")
    await svc.set_status(user_id="user-a", tour_id="volume", status="completed")
    statuses = await svc.get_user_statuses("user-a")
    assert statuses["volume"] == "completed"
    # upsert 이므로 중복 행이 생기지 않는다 — 맵에 volume 키는 하나뿐.
    assert list(statuses).count("volume") == 1


async def test_status_is_isolated_per_user(live_db):
    await svc.set_status(user_id="user-a", tour_id="drover", status="completed")
    assert await svc.get_user_statuses("user-b") == {}


@pytest.mark.parametrize("tour_id", ["images", "admin-images"])
async def test_image_tour_status_survives_update_without_cross_user_visibility(live_db, tour_id):
    await svc.set_status(user_id="image-user", tour_id=tour_id, status="dismissed")
    assert await svc.get_user_statuses("image-user") == {tour_id: "dismissed"}
    assert await svc.get_user_statuses("other-user") == {}
    await svc.set_status(user_id="image-user", tour_id=tour_id, status="completed")
    assert await svc.get_user_statuses("image-user") == {tour_id: "completed"}


async def test_unknown_user_returns_empty(live_db):
    assert await svc.get_user_statuses("") == {}


async def test_validation_rejects_bad_tour_and_status(live_db):
    with pytest.raises(svc.TutorialValidationError):
        await svc.set_status(user_id="user-a", tour_id="nope", status="completed")
    with pytest.raises(svc.TutorialValidationError):
        await svc.set_status(user_id="user-a", tour_id="vm-create", status="nope")
