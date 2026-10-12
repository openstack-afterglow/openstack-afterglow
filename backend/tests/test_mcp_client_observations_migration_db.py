"""Additive observation JSON upgrades preserve legacy unknown and stored evidence."""

from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

_ROOT = Path(__file__).parents[2]
_MIGRATION_PATH = "backend/migrations/087_mcp_client_observations.sql"


@pytest.mark.db
@pytest.mark.asyncio
async def test_observation_upgrade_is_nullable_persistent_and_idempotent():
    url = os.environ.get("AFTERGLOW_TEST_DATABASE_URL")
    if not url:
        pytest.skip("AFTERGLOW_TEST_DATABASE_URL is required")
    table = f"mcp_observations_{uuid4().hex[:12]}"
    sql = (_ROOT / _MIGRATION_PATH).read_text(encoding="utf-8").replace("mcp_delegated_grants", table)
    statements = [
        part.strip()
        for part in "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--")).split(";")
        if part.strip()
    ]
    engine = create_async_engine(url)
    evidence = [
        {
            "client_name": "Codex",
            "client_version": "1.2",
            "product": "Codex",
            "kind": "agent",
            "identity_source": "client_info",
            "browser": None,
            "os": None,
            "first_seen_at": "2026-10-12T00:00:00+00:00",
            "last_seen_at": "2026-10-12T00:01:00+00:00",
        }
    ]
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(f"CREATE TABLE `{table}` (id VARCHAR(64) PRIMARY KEY, status VARCHAR(10) NOT NULL)")
            )
            await conn.execute(text(f"INSERT INTO `{table}` VALUES ('legacy', 'active')"))
            for _ in range(2):
                for statement in statements:
                    await conn.execute(text(statement))
            legacy = (
                await conn.execute(text(f"SELECT client_observations FROM `{table}` WHERE id='legacy'"))
            ).scalar_one()
            assert legacy is None
            nullable = (
                await conn.execute(
                    text(
                        "SELECT IS_NULLABLE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() "
                        "AND TABLE_NAME = :table AND COLUMN_NAME = 'client_observations'"
                    ),
                    {"table": table},
                )
            ).scalar_one()
            assert nullable == "YES"
            await conn.execute(
                text(
                    f"INSERT INTO `{table}` (id, status, client_observations) VALUES ('observed', 'active', :evidence)"
                ),
                {"evidence": json.dumps(evidence)},
            )
        # New transaction/connection observes durable evidence, not an ORM-only cache.
        async with engine.begin() as conn:
            for statement in statements:
                await conn.execute(text(statement))
            rows = dict((await conn.execute(text(f"SELECT id, client_observations FROM `{table}`"))).all())
            assert rows["legacy"] is None
            assert json.loads(rows["observed"]) == evidence
            await conn.execute(text(f"INSERT INTO `{table}` (id, status) VALUES ('omitted', 'active')"))
            assert (
                await conn.execute(text(f"SELECT client_observations FROM `{table}` WHERE id='omitted'"))
            ).scalar_one() is None
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(f"DROP TABLE IF EXISTS `{table}`"))
        await engine.dispose()
