"""Ongoing OAuth is additive: legacy rows stay finite and nullable access is forbidden."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import JSON, Boolean, CheckConstraint, Column, MetaData, String, Table, text
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from app.models.mcp_authority import McpDelegatedGrant, McpOAuthToken
from scripts.baseline_migrations import MigrationLedgerError
from scripts.bootstrap_schema import _check_signature, bootstrap_database, load_sql106, schema_lock


def test_sqlite_ongoing_model_constraints_require_explicit_oauth_ceiling_and_finite_access():
    with sqlite3.connect(":memory:") as db:
        grant_checks = [
            str(check.sqltext)
            for check in McpDelegatedGrant.__table__.constraints
            if isinstance(check, CheckConstraint) and check.name in {"chk_mcp_grant_expiry", "chk_mcp_grant_ongoing"}
        ]
        db.execute(
            "CREATE TABLE grants (source TEXT, expires_at TEXT, oauth_ongoing INTEGER NOT NULL DEFAULT 0, "
            "issued_role_ceiling TEXT, " + ", ".join(f"CHECK ({value})" for value in grant_checks) + ")"
        )
        db.execute("INSERT INTO grants VALUES ('oauth', '2026-12-01', 0, NULL)")
        db.execute("INSERT INTO grants VALUES ('personal_token', NULL, 0, NULL)")
        ceiling = json.dumps({"project": [{"id": "reader-id", "name": "reader"}]})
        db.execute("INSERT INTO grants VALUES ('oauth', NULL, 1, ?)", (ceiling,))
        for source, expiry, ongoing, saved in [
            ("oauth", None, 0, None),
            ("oauth", None, 1, None),
            ("oauth", None, 1, "null"),
            ("oauth", None, 1, "[]"),
            ("lumen", None, 1, ceiling),
            ("personal_token", None, 1, ceiling),
            ("oauth", "2026-12-01", 1, ceiling),
        ]:
            with pytest.raises(sqlite3.IntegrityError):
                db.execute("INSERT INTO grants VALUES (?, ?, ?, ?)", (source, expiry, ongoing, saved))
        token_check = next(
            str(check.sqltext)
            for check in McpOAuthToken.__table__.constraints
            if isinstance(check, CheckConstraint) and check.name == "chk_mcp_oauth_token_expiry"
        )
        db.execute(f"CREATE TABLE tokens (token_type TEXT, expires_at TEXT, CHECK ({token_check}))")
        db.execute("INSERT INTO tokens VALUES ('refresh', NULL)")
        db.execute("INSERT INTO tokens VALUES ('access', '2026-12-01')")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO tokens VALUES ('access', NULL)")


@pytest.mark.db
@pytest.mark.asyncio
@pytest.mark.parametrize("applied_prefix", range(9))
async def test_raw_mariadb_ongoing_upgrade_preserves_legacy_deadlines_and_replays_safely(applied_prefix):
    url = os.environ.get("AFTERGLOW_TEST_DATABASE_URL")
    if not url:
        pytest.skip("AFTERGLOW_TEST_DATABASE_URL is required")
    suffix = uuid4().hex[:12]
    grants, tokens = f"mcp_ongoing_grants_{suffix}", f"mcp_ongoing_tokens_{suffix}"
    statements = [
        statement.replace("mcp_delegated_grants", grants).replace("mcp_oauth_tokens", tokens)
        for statement in load_sql106()
    ]
    engine = create_async_engine(url)
    deadline = datetime(2026, 12, 1, 12, 34, 56, 123456)
    token_deadline = deadline.replace(microsecond=0)
    ceiling = json.dumps({"project": [{"id": "reader-id", "name": "reader"}]})
    try:
        async with engine.connect() as conn:
            await conn.execute(
                text(
                    f"CREATE TABLE `{grants}` (id VARCHAR(64) PRIMARY KEY, "
                    "source VARCHAR(20) NOT NULL, expires_at DATETIME(6) NULL, "
                    "CONSTRAINT chk_mcp_grant_expiry "
                    "CHECK (expires_at IS NOT NULL OR source = 'personal_token'))"
                )
            )
            await conn.execute(
                text(
                    f"CREATE TABLE `{tokens}` (id VARCHAR(64) PRIMARY KEY, "
                    "token_type VARCHAR(10) NOT NULL, expires_at DATETIME NOT NULL)"
                )
            )
            for source in ("oauth", "lumen", "personal_token"):
                await conn.execute(
                    text(f"INSERT INTO `{grants}` (id, source, expires_at) VALUES (:id, :id, :expiry)"),
                    {"id": source, "expiry": deadline},
                )
            await conn.execute(
                text(f"INSERT INTO `{tokens}` VALUES ('old-refresh', 'refresh', :expiry)"), {"expiry": token_deadline}
            )
            # Resume every possible implicit-commit boundary of the real DDL.
            for statement in statements[:applied_prefix]:
                await conn.exec_driver_sql(statement)
            await conn.commit()
            assert await bootstrap_database(url, metadata=MetaData(), grants_table=grants, tokens_table=tokens) is (
                applied_prefix < 8
            )
            assert await bootstrap_database(url, metadata=MetaData(), grants_table=grants, tokens_table=tokens) is False
            precision = (
                await conn.execute(
                    text(
                        "SELECT DATETIME_PRECISION FROM information_schema.COLUMNS "
                        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table AND COLUMN_NAME = 'expires_at'"
                    ),
                    {"table": tokens},
                )
            ).scalar_one()
            assert precision == 6
            rows = (
                await conn.execute(
                    text(
                        f"SELECT source, expires_at, oauth_ongoing, issued_role_ceiling FROM `{grants}` ORDER BY source"
                    )
                )
            ).all()
            assert rows == [(source, deadline, 0, None) for source in ("lumen", "oauth", "personal_token")]
            await conn.execute(
                text(
                    f"INSERT INTO `{grants}` (id, source, expires_at, oauth_ongoing, issued_role_ceiling) "
                    "VALUES ('ongoing', 'oauth', NULL, TRUE, :ceiling)"
                ),
                {"ceiling": ceiling},
            )
            for source, ongoing, saved in [
                ("oauth", 0, None),
                ("oauth", 1, None),
                ("oauth", 1, "null"),
                ("oauth", 1, "[]"),
                ("lumen", 1, ceiling),
                ("personal_token", 1, ceiling),
            ]:
                with pytest.raises(DBAPIError) as rejected:
                    await conn.execute(
                        text(
                            f"INSERT INTO `{grants}` (id, source, expires_at, oauth_ongoing, issued_role_ceiling) "
                            "VALUES (:id, :source, NULL, :ongoing, :ceiling)"
                        ),
                        {"id": str(uuid4()), "source": source, "ongoing": ongoing, "ceiling": saved},
                    )
                assert rejected.value.orig.args[0] == 4025
            await conn.execute(text(f"INSERT INTO `{tokens}` VALUES ('ongoing-refresh', 'refresh', NULL)"))
            with pytest.raises(DBAPIError) as rejected:
                await conn.execute(text(f"INSERT INTO `{tokens}` VALUES ('bad-access', 'access', NULL)"))
            assert rejected.value.orig.args[0] == 4025
            assert (
                await conn.execute(text(f"SELECT expires_at FROM `{tokens}` WHERE id = 'old-refresh'"))
            ).scalar_one() == token_deadline
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(f"DROP TABLE IF EXISTS `{tokens}`"))
            await conn.execute(text(f"DROP TABLE IF EXISTS `{grants}`"))
        await engine.dispose()


def test_sql106_check_comparison_preserves_boolean_grouping():
    expected = (
        "oauth_ongoing = FALSE OR (source = 'oauth' AND expires_at IS NULL "
        "AND COALESCE(LOWER(JSON_TYPE(issued_role_ceiling)) = 'object', 0))"
    )
    mariadb = (
        "`oauth_ongoing` = 0 or `source` = 'oauth' and `expires_at` is null "
        "and coalesce(lcase(json_type(`issued_role_ceiling`)) = 'object',0)"
    )
    assert _check_signature(expected) == _check_signature(mariadb)
    assert _check_signature("a = 1 OR (b = 1 AND c = 1)") != _check_signature("(a = 1 OR b = 1) AND c = 1")


@pytest.mark.db
@pytest.mark.asyncio
async def test_sql106_fresh_orm_tables_skip_all_alter_statements():
    url = os.environ.get("AFTERGLOW_TEST_DATABASE_URL")
    if not url:
        pytest.skip("AFTERGLOW_TEST_DATABASE_URL is required")
    suffix = uuid4().hex[:12]
    grants, tokens = f"mcp_fresh_grants_{suffix}", f"mcp_fresh_tokens_{suffix}"
    metadata = MetaData()
    Table(
        grants,
        metadata,
        Column("source", String(20), nullable=False),
        Column("expires_at", DATETIME(fsp=6)),
        Column("oauth_ongoing", Boolean, nullable=False, server_default="0"),
        Column("issued_role_ceiling", JSON),
        *[
            CheckConstraint(str(check.sqltext), name=check.name)
            for check in McpDelegatedGrant.__table__.constraints
            if isinstance(check, CheckConstraint) and check.name in {"chk_mcp_grant_expiry", "chk_mcp_grant_ongoing"}
        ],
    )
    Table(
        tokens,
        metadata,
        Column("token_type", String(10), nullable=False),
        Column("expires_at", DATETIME(fsp=6)),
        *[
            CheckConstraint(str(check.sqltext), name=check.name)
            for check in McpOAuthToken.__table__.constraints
            if isinstance(check, CheckConstraint) and check.name == "chk_mcp_oauth_token_expiry"
        ],
    )
    engine = create_async_engine(url)
    try:
        assert await bootstrap_database(url, metadata=metadata, grants_table=grants, tokens_table=tokens) is False
        async with engine.connect() as conn:
            before = [(await conn.exec_driver_sql(f"SHOW CREATE TABLE `{table}`")).one() for table in (grants, tokens)]
        assert await bootstrap_database(url, metadata=metadata, grants_table=grants, tokens_table=tokens) is False
        async with engine.connect() as conn:
            after = [(await conn.exec_driver_sql(f"SHOW CREATE TABLE `{table}`")).one() for table in (grants, tokens)]
            assert after == before
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(metadata.drop_all)
        await engine.dispose()


@pytest.mark.db
@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["incompatible_column", "invalid_legacy_row", "table_creation"])
async def test_sql106_bootstrap_propagates_schema_and_ddl_failure_without_changing_finite_rows(failure):
    url = os.environ.get("AFTERGLOW_TEST_DATABASE_URL")
    if not url:
        pytest.skip("AFTERGLOW_TEST_DATABASE_URL is required")
    suffix = uuid4().hex[:12]
    grants, tokens = f"mcp_bad_grants_{suffix}", f"mcp_bad_tokens_{suffix}"
    engine = create_async_engine(url)
    deadline = datetime(2026, 12, 1, 12, 34, 56, 123456)
    try:
        async with engine.begin() as conn:
            extra = ", oauth_ongoing VARCHAR(8) NOT NULL DEFAULT '0'" if failure == "incompatible_column" else ""
            await conn.exec_driver_sql(
                f"CREATE TABLE `{grants}` (id VARCHAR(64) PRIMARY KEY, "
                f"source VARCHAR(20) NOT NULL, expires_at DATETIME(6) NULL{extra})"
            )
            await conn.exec_driver_sql(
                f"CREATE TABLE `{tokens}` (id VARCHAR(64) PRIMARY KEY, "
                "token_type VARCHAR(10) NOT NULL, expires_at DATETIME(6) NOT NULL)"
            )
            await conn.execute(
                text(f"INSERT INTO `{grants}` (id, source, expires_at) VALUES ('finite', 'oauth', :expiry)"),
                {"expiry": deadline},
            )
            await conn.execute(
                text(f"INSERT INTO `{tokens}` VALUES ('finite-refresh', 'refresh', :expiry)"),
                {"expiry": deadline},
            )
            if failure == "invalid_legacy_row":
                await conn.exec_driver_sql(
                    f"INSERT INTO `{grants}` (id, source, expires_at) VALUES ('invalid', 'oauth', NULL)"
                )
            # DDL commits are not rollbackable: the runner must surface the error,
            # not invent a successful migration receipt or extend existing rows.
            await conn.commit()
        metadata = MetaData()
        invalid_table = f"mcp_bad_create_{suffix}"
        if failure == "table_creation":
            Table(
                invalid_table,
                metadata,
                Column("id", String(64)),
                CheckConstraint("missing_column = 0", name="invalid_bootstrap_column"),
            )
        if failure == "incompatible_column":
            with pytest.raises(MigrationLedgerError, match="incompatible prerequisite schema"):
                await bootstrap_database(url, metadata=metadata, grants_table=grants, tokens_table=tokens)
        else:
            with pytest.raises(DBAPIError) as rejected:
                await bootstrap_database(url, metadata=metadata, grants_table=grants, tokens_table=tokens)
            assert rejected.value.orig.args[0] == (1054 if failure == "table_creation" else 4025)
        async with engine.connect() as conn:
            assert (
                await conn.execute(text(f"SELECT expires_at FROM `{grants}` WHERE id = 'finite'"))
            ).scalar_one() == deadline
            assert (
                await conn.execute(text(f"SELECT expires_at FROM `{tokens}` WHERE id = 'finite-refresh'"))
            ).scalar_one() == deadline
            nullable = (
                await conn.execute(
                    text(
                        "SELECT IS_NULLABLE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() "
                        "AND TABLE_NAME = :table AND COLUMN_NAME = 'expires_at'"
                    ),
                    {"table": tokens},
                )
            ).scalar_one()
            assert nullable == "NO"
    finally:
        async with engine.begin() as conn:
            await conn.exec_driver_sql(f"DROP TABLE IF EXISTS `{tokens}`")
            await conn.exec_driver_sql(f"DROP TABLE IF EXISTS `mcp_bad_create_{suffix}`")
            await conn.exec_driver_sql(f"DROP TABLE IF EXISTS `{grants}`")
        await engine.dispose()


@pytest.mark.db
@pytest.mark.asyncio
async def test_schema_bootstrap_lock_refuses_concurrent_owner_and_releases_after_failure():
    url = os.environ.get("AFTERGLOW_TEST_DATABASE_URL")
    if not url:
        pytest.skip("AFTERGLOW_TEST_DATABASE_URL is required")
    engine = create_async_engine(url)
    try:
        async with engine.connect() as first, engine.connect() as second:
            with pytest.raises(RuntimeError, match="bootstrap failure"):
                async with schema_lock(first):
                    with pytest.raises(MigrationLedgerError, match="lock was not acquired"):
                        async with schema_lock(second, timeout=0):
                            pytest.fail("a second bootstrap acquired the same database lock")
                    raise RuntimeError("bootstrap failure")
            async with schema_lock(second, timeout=0):
                assert (await second.exec_driver_sql("SELECT 1")).scalar_one() == 1
    finally:
        await engine.dispose()
