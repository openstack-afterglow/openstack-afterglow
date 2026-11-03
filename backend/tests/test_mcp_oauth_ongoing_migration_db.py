"""Ongoing OAuth is additive: legacy rows stay finite and nullable access is forbidden."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import CheckConstraint, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from app.models.mcp_authority import McpDelegatedGrant, McpOAuthToken

_ROOT = Path(__file__).parents[2]


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
async def test_raw_mariadb_ongoing_upgrade_preserves_legacy_deadlines_and_replays_safely():
    url = os.environ.get("AFTERGLOW_TEST_DATABASE_URL")
    if not url:
        pytest.skip("AFTERGLOW_TEST_DATABASE_URL is required")
    suffix = uuid4().hex[:12]
    grants, tokens = f"mcp_ongoing_grants_{suffix}", f"mcp_ongoing_tokens_{suffix}"
    sql = (_ROOT / "backend/migrations/106_mcp_oauth_ongoing.sql").read_text(encoding="utf-8")
    sql = sql.replace("mcp_delegated_grants", grants).replace("mcp_oauth_tokens", tokens)
    statements = [
        part.strip()
        for part in "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--")).split(";")
        if part.strip()
    ]
    engine = create_async_engine(url)
    deadline = datetime(2026, 12, 1, 12, 34, 56, 123456)
    ceiling = json.dumps({"project": [{"id": "reader-id", "name": "reader"}]})
    try:
        async with engine.begin() as conn:
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
                    "token_type VARCHAR(10) NOT NULL, expires_at DATETIME(6) NOT NULL)"
                )
            )
            for source in ("oauth", "lumen", "personal_token"):
                await conn.execute(
                    text(f"INSERT INTO `{grants}` (id, source, expires_at) VALUES (:id, :id, :expiry)"),
                    {"id": source, "expiry": deadline},
                )
            await conn.execute(
                text(f"INSERT INTO `{tokens}` VALUES ('old-refresh', 'refresh', :expiry)"), {"expiry": deadline}
            )
            for _ in range(2):
                for statement in statements:
                    await conn.execute(text(statement))
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
            ).scalar_one() == deadline
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(f"DROP TABLE IF EXISTS `{tokens}`"))
            await conn.execute(text(f"DROP TABLE IF EXISTS `{grants}`"))
        await engine.dispose()
