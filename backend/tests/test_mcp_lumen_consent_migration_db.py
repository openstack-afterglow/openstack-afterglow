"""Additive consent upgrade keeps legacy authority unapproved until explicit consent."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

_ROOT = Path(__file__).parents[2]
_MIGRATION_PATH = "backend/migrations/086_mcp_lumen_explicit_consent.sql"


@pytest.mark.db
@pytest.mark.asyncio
async def test_lumen_consent_upgrade_is_nullable_without_legacy_backfill():
    url = os.environ.get("AFTERGLOW_TEST_DATABASE_URL")
    if not url:
        pytest.skip("AFTERGLOW_TEST_DATABASE_URL is required")
    table = f"mcp_consent_{uuid4().hex[:12]}"
    sql = (_ROOT / _MIGRATION_PATH).read_text(encoding="utf-8").replace("mcp_delegated_grants", table)
    statements = [
        part.strip()
        for part in "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--")).split(";")
        if part.strip()
    ]
    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(f"CREATE TABLE `{table}` (id VARCHAR(64) PRIMARY KEY, source VARCHAR(20) NOT NULL)")
            )
            for source in ("lumen", "personal_token", "oauth"):
                await conn.execute(
                    text(f"INSERT INTO `{table}` (id, source) VALUES (:source, :source)"), {"source": source}
                )
            for _ in range(2):
                for statement in statements:
                    await conn.execute(text(statement))
            columns = (
                (
                    await conn.execute(
                        text(
                            "SELECT IS_NULLABLE, DATA_TYPE, DATETIME_PRECISION, COLUMN_DEFAULT "
                            "FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() "
                            "AND TABLE_NAME = :table AND COLUMN_NAME = 'consented_at'"
                        ),
                        {"table": table},
                    )
                )
                .mappings()
                .one()
            )
            assert columns["IS_NULLABLE"] == "YES"
            assert columns["DATA_TYPE"] == "datetime"
            assert columns["DATETIME_PRECISION"] == 6
            assert columns["COLUMN_DEFAULT"] in (None, "NULL")
            rows = (await conn.execute(text(f"SELECT id, consented_at FROM `{table}` ORDER BY id"))).all()
            assert rows == [("lumen", None), ("oauth", None), ("personal_token", None)]
            await conn.execute(text(f"INSERT INTO `{table}` (id, source) VALUES ('omitted', 'lumen')"))
            await conn.execute(text(f"INSERT INTO `{table}` VALUES ('explicit-null', 'lumen', NULL)"))
            consented_at = datetime(2026, 10, 11, 12, 34, 56, 123456)
            await conn.execute(
                text(f"UPDATE `{table}` SET consented_at = :consent WHERE id = 'lumen'"),
                {"consent": consented_at},
            )
            for statement in statements:
                await conn.execute(text(statement))
            rows = dict((await conn.execute(text(f"SELECT id, consented_at FROM `{table}`"))).all())
            assert rows.pop("lumen") == consented_at
            assert rows == {"oauth": None, "personal_token": None, "omitted": None, "explicit-null": None}
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(f"DROP TABLE IF EXISTS `{table}`"))
        await engine.dispose()
