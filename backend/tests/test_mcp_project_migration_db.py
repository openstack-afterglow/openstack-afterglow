"""MariaDB behavior of the additive multi-project authority migration."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import create_async_engine

from app.services.mcp_control_plane.authority import approved_project_metadata

pytestmark = [pytest.mark.db, pytest.mark.asyncio]
_MIGRATION = Path(__file__).parents[1] / "migrations" / "084_mcp_project_delegation.sql"


@pytest.fixture
async def migrated_authority():
    url = os.environ.get("AFTERGLOW_TEST_DATABASE_URL")
    if not url:
        pytest.skip("AFTERGLOW_TEST_DATABASE_URL is required")
    suffix = uuid4().hex[:12]
    grants = f"mcp_grants_{suffix}"
    credentials = f"mcp_credentials_{suffix}"
    sql = _MIGRATION.read_text(encoding="utf-8")
    for old, new in (
        ("mcp_delegated_grants", grants),
        ("mcp_project_credentials", credentials),
        ("chk_mcp_grant_source", f"chk_source_{suffix}"),
        ("chk_mcp_grant_project_scope", f"chk_scope_{suffix}"),
        ("fk_mcp_project_credentials_grant", f"fk_credential_{suffix}"),
    ):
        sql = sql.replace(old, new)
    statements = [
        part.strip()
        for part in "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--")).split(";")
        if part.strip()
    ]
    engine = create_async_engine(url, pool_pre_ping=True)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(f"""CREATE TABLE `{grants}` (
                id CHAR(36) PRIMARY KEY,
                owner_project_id VARCHAR(64) NOT NULL,
                source VARCHAR(20) NOT NULL,
                access_level VARCHAR(10) NOT NULL,
                CONSTRAINT chk_source_{suffix} CHECK (source IN ('personal_token', 'oauth'))
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
            )
            await conn.execute(
                text(f"""INSERT INTO `{grants}` (id, owner_project_id, source, access_level)
                VALUES ('legacy', 'A', 'personal_token', 'manage')""")
            )
            # Reapplying must preserve the legacy row and not broaden its scope.
            for _ in range(2):
                for statement in statements:
                    await conn.execute(text(statement))
        yield engine, grants, credentials
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(f"DROP TABLE IF EXISTS `{credentials}`"))
            await conn.execute(text(f"DROP TABLE IF EXISTS `{grants}`"))
        await engine.dispose()


async def test_additive_migration_preserves_exact_legacy_singleton(migrated_authority):
    engine, grants, _ = migrated_authority
    async with engine.connect() as conn:
        row = (await conn.execute(text(f"SELECT * FROM `{grants}` WHERE id='legacy'"))).mappings().one()
    assert row["project_scope"] == "current"
    assert row["approved_projects"] is None
    saved = approved_project_metadata(SimpleNamespace(**row))
    assert [project["id"] for project in saved] == ["A"]


async def test_internal_source_and_additional_credential_foreign_key(migrated_authority):
    engine, grants, credentials = migrated_authority
    async with engine.begin() as conn:
        await conn.execute(
            text(f"""INSERT INTO `{grants}` (id, owner_project_id, source, access_level)
            VALUES ('internal', 'A', 'lumen', 'read')""")
        )
        await conn.execute(
            text(f"""INSERT INTO `{credentials}`
            (grant_id, project_id, upstream_credential_name) VALUES ('internal', 'B', 'reserved-B')""")
        )
        row = (await conn.execute(text(f"SELECT * FROM `{credentials}`"))).mappings().one()
        assert row["cleanup_pending"] == 1
        assert row["credential_ciphertext"] is None
        with pytest.raises(IntegrityError):
            await conn.execute(
                text(f"""INSERT INTO `{credentials}`
                (grant_id, project_id, upstream_credential_name) VALUES ('missing', 'C', 'orphan-C')""")
            )
        await conn.execute(text(f"DELETE FROM `{grants}` WHERE id='internal'"))
        assert (await conn.execute(text(f"SELECT COUNT(*) FROM `{credentials}`"))).scalar_one() == 0


@pytest.fixture
async def migrated_personal_expiry():
    url = os.environ.get("AFTERGLOW_TEST_DATABASE_URL")
    if not url:
        pytest.skip("AFTERGLOW_TEST_DATABASE_URL is required")
    suffix = uuid4().hex[:12]
    table = f"mcp_expiry_{suffix}"
    sql = (Path(__file__).parents[1] / "migrations" / "085_mcp_personal_token_expiry.sql").read_text(encoding="utf-8")
    sql = sql.replace("mcp_delegated_grants", table).replace("chk_mcp_grant_expiry", f"chk_expiry_{suffix}")
    statements = [
        part.strip()
        for part in "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--")).split(";")
        if part.strip()
    ]
    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    f"CREATE TABLE `{table}` (id CHAR(36) PRIMARY KEY, source VARCHAR(20) NOT NULL, expires_at DATETIME(6) NOT NULL)"
                )
            )
            await conn.execute(
                text(f"INSERT INTO `{table}` VALUES ('legacy', 'personal_token', '2027-01-31 12:34:56.123456')")
            )
            for _ in range(2):
                for statement in statements:
                    await conn.execute(text(statement))
        yield engine, table
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(f"DROP TABLE IF EXISTS `{table}`"))
        await engine.dispose()


@pytest.mark.parametrize("source", ["personal_token", "oauth", "lumen"])
async def test_expiry_migration_preserves_legacy_and_only_allows_unbounded_personal(migrated_personal_expiry, source):
    engine, table = migrated_personal_expiry
    async with engine.begin() as conn:
        legacy = (await conn.execute(text(f"SELECT expires_at FROM `{table}` WHERE id='legacy'"))).scalar_one()
        assert legacy.isoformat() == "2027-01-31T12:34:56.123456"
        insert = text(f"INSERT INTO `{table}` VALUES ('new', :source, NULL)")
        if source == "personal_token":
            await conn.execute(insert, {"source": source})
            assert (await conn.execute(text(f"SELECT expires_at FROM `{table}` WHERE id='new'"))).scalar_one() is None
        else:
            with pytest.raises(OperationalError) as failure:
                await conn.execute(insert, {"source": source})
            assert failure.value.orig.args[0] == 4025  # MariaDB CHECK violation
            assert (await conn.execute(text(f"SELECT COUNT(*) FROM `{table}` WHERE id='new'"))).scalar_one() == 0
