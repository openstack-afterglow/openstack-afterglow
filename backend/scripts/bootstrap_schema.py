"""Canonical Kolla bootstrap: create missing tables and apply only verified SQL106.

This is not a historical migration runner or a migration-ledger baseline. SQL106
DDL commits implicitly; operators must retain the schema-before-writer backup and
rollback prerequisites documented in the immutable migration.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from contextlib import asynccontextmanager

from sqlalchemy import MetaData, text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from scripts.baseline_migrations import MIGRATIONS, MigrationLedgerError, load_manifest

_SQL106_ID = "106-mcp-oauth-ongoing"
_SQL106_PATH = "backend/migrations/106_mcp_oauth_ongoing.sql"
_SQL106_SHA256 = "b7ca283cceb76d3ce4c741804e828c0073b6694f5ceb592182041151ca0d6ea6"
_GRANTS = "mcp_delegated_grants"
_TOKENS = "mcp_oauth_tokens"
_CHECKS = {
    "chk_mcp_grant_expiry": (
        "expires_at IS NOT NULL OR source = 'personal_token' OR (source = 'oauth' AND oauth_ongoing = 1)"
    ),
    "chk_mcp_grant_ongoing": (
        "oauth_ongoing = 0 OR (source = 'oauth' AND expires_at IS NULL "
        "AND COALESCE(LOWER(JSON_TYPE(issued_role_ceiling)) = 'object', 0))"
    ),
    "chk_mcp_oauth_token_expiry": "expires_at IS NOT NULL OR token_type = 'refresh'",
}


def load_sql106() -> list[str]:
    """Validate the complete packaged manifest, then pin the one allowed DDL file."""
    migration = next((item for item in load_manifest() if item.logical_id == _SQL106_ID), None)
    if migration is None or (migration.relative_path, migration.sha256) != (_SQL106_PATH, _SQL106_SHA256):
        raise MigrationLedgerError("SQL106 immutable manifest identity does not match")
    payload = (MIGRATIONS / "106_mcp_oauth_ongoing.sql").read_bytes()
    if hashlib.sha256(payload).hexdigest() != _SQL106_SHA256:
        raise MigrationLedgerError("SQL106 immutable payload checksum does not match")
    # This pinned file contains only simple ALTER statements, no SQL procedures
    # or semicolons inside literals. Do not generalize this to arbitrary files.
    sql = "\n".join(line for line in payload.decode("utf-8").splitlines() if not line.lstrip().startswith("--"))
    return [statement.strip() for statement in sql.split(";") if statement.strip()]


def _check_signature(expression: str) -> tuple:
    """Preserve AND/OR grouping while accepting MariaDB's redundant parentheses."""
    tokens = re.findall(r"'[^']*'|[a-z_][a-z_0-9]*|[0-9]+|[(),=]", expression.lower().replace("`", ""))
    compact = re.sub(r"\s+", "", expression.lower().replace("`", ""))
    if "".join(tokens) != compact:
        raise MigrationLedgerError("unsupported SQL106 check expression")
    aliases = {"true": "1", "false": "0", "lower": "lcase"}
    tokens = [aliases.get(token, token) for token in tokens]

    def signature(parts: list[str]) -> tuple:
        while parts and parts[0] == "(" and parts[-1] == ")":
            depth, end = 0, 0
            for token in parts:
                end += 1
                depth += (token == "(") - (token == ")")
                if depth == 0:
                    break
            if end != len(parts):
                break
            parts = parts[1:-1]
        for operator in ("or", "and"):
            depth, start = 0, 0
            groups = []
            for index, token in enumerate(parts):
                depth += (token == "(") - (token == ")")
                if depth == 0 and token == operator:
                    groups.append(signature(parts[start:index]))
                    start = index + 1
            if groups:
                groups.append(signature(parts[start:]))
                return operator, tuple(groups)
        return "atom", tuple(parts)

    return signature(tokens)


async def _schema_state(conn: AsyncConnection, grants: str, tokens: str) -> tuple[dict, dict]:
    columns = (
        await conn.execute(
            text(
                "SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, COLUMN_TYPE, IS_NULLABLE, "
                "COLUMN_DEFAULT, DATETIME_PRECISION FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME IN (:grants, :tokens)"
            ),
            {"grants": grants, "tokens": tokens},
        )
    ).mappings()
    checks = (
        await conn.execute(
            text(
                "SELECT TABLE_NAME, CONSTRAINT_NAME, CHECK_CLAUSE FROM information_schema.CHECK_CONSTRAINTS "
                "WHERE CONSTRAINT_SCHEMA = DATABASE() AND TABLE_NAME IN (:grants, :tokens)"
            ),
            {"grants": grants, "tokens": tokens},
        )
    ).mappings()
    return (
        {(row["TABLE_NAME"], row["COLUMN_NAME"]): row for row in columns},
        {(row["TABLE_NAME"], row["CONSTRAINT_NAME"]): row["CHECK_CLAUSE"] for row in checks},
    )


def _column_errors(columns: dict, checks: dict, grants: str, tokens: str, *, allow_missing: bool) -> list[str]:
    errors = []
    for table, column in ((grants, "expires_at"), (tokens, "expires_at")):
        saved = columns.get((table, column))
        precisions = range(7) if allow_missing and table == tokens else (6,)
        if saved is None or saved["DATA_TYPE"] != "datetime" or saved["DATETIME_PRECISION"] not in precisions:
            errors.append(f"{table}.{column} has an incompatible DATETIME precision")
        elif (table == grants or not allow_missing) and saved["IS_NULLABLE"] != "YES":
            errors.append(f"{table}.{column} must be nullable")
    ongoing = columns.get((grants, "oauth_ongoing"))
    if ongoing is None:
        if not allow_missing:
            errors.append(f"{grants}.oauth_ongoing is missing")
    elif (
        ongoing["COLUMN_TYPE"].lower() != "tinyint(1)"
        or ongoing["IS_NULLABLE"] != "NO"
        or str(ongoing["COLUMN_DEFAULT"]).strip("'").lower() not in {"0", "false"}
    ):
        errors.append(f"{grants}.oauth_ongoing must be BOOLEAN NOT NULL DEFAULT FALSE")
    ceiling = columns.get((grants, "issued_role_ceiling"))
    if ceiling is None:
        if not allow_missing:
            errors.append(f"{grants}.issued_role_ceiling is missing")
    elif (
        ceiling["DATA_TYPE"] != "longtext"
        or ceiling["IS_NULLABLE"] != "YES"
        or str(ceiling["COLUMN_DEFAULT"]).lower() not in {"none", "null"}
        or _check_signature(checks.get((grants, "issued_role_ceiling"), ""))
        != _check_signature("json_valid(issued_role_ceiling)")
    ):
        errors.append(f"{grants}.issued_role_ceiling must be nullable MariaDB JSON")
    return errors


def _check_errors(checks: dict, grants: str, tokens: str) -> list[str]:
    return [
        f"{table}.{name} does not match SQL106"
        for name, expression in _CHECKS.items()
        for table in [tokens if name == "chk_mcp_oauth_token_expiry" else grants]
        if _check_signature(checks.get((table, name), "")) != _check_signature(expression)
    ]


async def ensure_sql106(conn: AsyncConnection, *, grants_table: str = _GRANTS, tokens_table: str = _TOKENS) -> bool:
    """Apply SQL106 if needed; return whether DDL ran, and verify every postcondition.

    Alternate table names allow isolated real-MariaDB regression tables without
    touching the canonical application's tables. The CLI never accepts them.
    Caller owns the deployment lock and must have created missing tables first.
    """
    for table in (grants_table, tokens_table):
        if not re.fullmatch(r"[a-z_][a-z_0-9]*", table):
            raise MigrationLedgerError("invalid SQL106 table identifier")
    statements = load_sql106()
    await conn.execute(text("SET SESSION check_constraint_checks = 1"))
    columns, checks = await _schema_state(conn, grants_table, tokens_table)
    errors = _column_errors(columns, checks, grants_table, tokens_table, allow_missing=True)
    if errors:
        raise MigrationLedgerError("SQL106 incompatible prerequisite schema: " + "; ".join(errors))
    if not (
        _column_errors(columns, checks, grants_table, tokens_table, allow_missing=False)
        or _check_errors(checks, grants_table, tokens_table)
    ):
        return False
    for statement in statements:
        statement = statement.replace(_GRANTS, grants_table).replace(_TOKENS, tokens_table)
        await conn.exec_driver_sql(statement)
    columns, checks = await _schema_state(conn, grants_table, tokens_table)
    errors = _column_errors(columns, checks, grants_table, tokens_table, allow_missing=False)
    errors += _check_errors(checks, grants_table, tokens_table)
    if errors:
        raise MigrationLedgerError("SQL106 postcondition failed: " + "; ".join(errors))
    return True


@asynccontextmanager
async def schema_lock(conn: AsyncConnection, *, timeout: int = 60):
    """Serialize bootstrap on the configured MariaDB server, surviving DDL commits."""
    version = (await conn.execute(text("SELECT VERSION()"))).scalar_one()
    if "mariadb" not in version.lower():
        raise MigrationLedgerError("SQL106 bootstrap requires MariaDB")
    database = (await conn.execute(text("SELECT DATABASE()"))).scalar_one()
    if not database:
        raise MigrationLedgerError("SQL106 bootstrap requires a selected database")
    name = "afterglow:bootstrap:" + hashlib.sha256(database.encode()).hexdigest()[:40]
    acquired = (
        await conn.execute(text("SELECT GET_LOCK(:name, :timeout)"), {"name": name, "timeout": timeout})
    ).scalar_one()
    if acquired != 1:
        raise MigrationLedgerError("database bootstrap lock was not acquired")
    try:
        yield
    finally:
        released = (await conn.execute(text("SELECT RELEASE_LOCK(:name)"), {"name": name})).scalar_one()
        if released != 1:
            raise MigrationLedgerError("database bootstrap lock was not released")


def model_metadata() -> MetaData:
    """Register persistence models explicitly, without importing the API runtime."""
    from app.database import Base
    from app.models import (  # noqa: F401 — registration only
        account_recovery,
        account_spaces,
        activity,
        announcement,
        db,
        domain_auth,
        domain_iam,
        domain_quotas,
        email_delivery,
        enrollment_policy,
        gpu_quota_requests,
        mcp_authority,
        organization_provisioning,
        project_ownership,
    )

    return Base.metadata


async def bootstrap_database(
    database_url: str,
    *,
    metadata: MetaData | None = None,
    grants_table: str = _GRANTS,
    tokens_table: str = _TOKENS,
) -> bool:
    """Strict missing-table initialization followed by SQL106 under one lock.

    Optional metadata/table names isolate real bootstrap regression schemas;
    the CLI always uses the registered canonical application models.
    """

    if not database_url:
        raise MigrationLedgerError("database.url is required for schema bootstrap")
    # Validate image contents before opening or changing the database.
    load_sql106()
    engine = create_async_engine(database_url, connect_args={"connect_timeout": 10}, hide_parameters=True)
    try:
        async with engine.connect() as conn, schema_lock(conn):
            await conn.run_sync((metadata if metadata is not None else model_metadata()).create_all)
            return await ensure_sql106(conn, grants_table=grants_table, tokens_table=tokens_table)
    finally:
        await engine.dispose()


def main() -> None:
    from app.config import get_settings

    asyncio.run(bootstrap_database(get_settings().database_url))


if __name__ == "__main__":
    main()
