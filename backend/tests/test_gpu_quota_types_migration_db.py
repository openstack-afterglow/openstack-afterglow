"""MariaDB behavior tests for the GPU quota alias normalization migration."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = [pytest.mark.db, pytest.mark.asyncio]

_DB_URL_ENV = "AFTERGLOW_TEST_DATABASE_URL"
_MIGRATION = Path(__file__).parents[1] / "migrations" / "079_normalize_gpu_quota_types.sql"


@pytest.fixture(scope="module")
def db_url() -> str:
    url = os.environ.get(_DB_URL_ENV)
    if not url:
        pytest.skip(f"{_DB_URL_ENV} 미설정 — MariaDB 통합 테스트 건너뜀")
    return url


async def test_gpu_quota_type_normalization_keeps_latest_row_and_timestamps(db_url: str) -> None:
    table = f"gpu_quotas_{uuid.uuid4().hex[:12]}"
    migration_sql = _MIGRATION.read_text(encoding="utf-8").replace("gpu_quotas", table)
    statements = [
        statement.strip()
        for statement in "\n".join(
            line for line in migration_sql.splitlines() if not line.lstrip().startswith("--")
        ).split(";")
        if statement.strip()
    ]
    engine = create_async_engine(db_url, echo=False, pool_pre_ping=True)

    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    f"""CREATE TABLE `{table}` (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        project_id VARCHAR(64) NOT NULL,
                        gpu_type VARCHAR(64) NOT NULL,
                        `limit` INT NOT NULL,
                        created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
                        updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                            ON UPDATE CURRENT_TIMESTAMP(6),
                        UNIQUE KEY uq_{table}_project_gpu_type (project_id, gpu_type)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"""
                )
            )
            await conn.execute(
                text(
                    f"""INSERT INTO `{table}` (project_id, gpu_type, `limit`, created_at, updated_at)
                    VALUES
                        ('p1', 'RTX3090Ti', 1, '2026-09-08 00:00:00.000000', '2026-09-08 00:00:00.000000'),
                        ('__default__', 'GTX_TITAN_X', 2, '2026-08-28 00:00:00.000000', '2026-08-28 00:00:00.000000'),
                        ('__default__', 'GTXTITANX', -1, '2026-09-07 00:00:00.000000', '2026-09-07 00:00:00.000000'),
                        ('__default__', 'GTX1080Ti', -1, '2026-09-07 00:00:00.000000', '2026-09-07 00:00:00.000000')"""
                )
            )
            for _ in range(2):
                for statement in statements:
                    await conn.execute(text(statement))

        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(f"SELECT project_id, gpu_type, `limit`, updated_at FROM `{table}` ORDER BY gpu_type")
                )
            ).all()

        assert [(row.project_id, row.gpu_type, row.limit) for row in rows] == [
            ("__default__", "GTX1080TI", -1),
            ("__default__", "GTXTITANX", -1),
            ("p1", "RTX3090TI", 1),
        ]
        assert [row.updated_at.isoformat(sep=" ") for row in rows] == [
            "2026-09-07 00:00:00",
            "2026-09-07 00:00:00",
            "2026-09-08 00:00:00",
        ]
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(f"DROP TABLE IF EXISTS `{table}`"))
        await engine.dispose()
