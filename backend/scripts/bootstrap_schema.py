"""Canonical Kolla bootstrap: missing tables and explicitly pinned SQL106/107.

This is not a historical migration runner or a migration-ledger baseline.
DDL commits implicitly; schema-before-writer backup and rollback prerequisites
remain mandatory. SQL107 adds diagnostics only, never business-table columns.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from contextlib import asynccontextmanager

from sqlalchemy import JSON, MetaData, UniqueConstraint, inspect, text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from scripts.baseline_migrations import MIGRATIONS, MigrationLedgerError, load_manifest

_SQL106_ID = "106-mcp-oauth-ongoing"
_SQL106_PATH = "backend/migrations/106_mcp_oauth_ongoing.sql"
_SQL106_SHA256 = "b7ca283cceb76d3ce4c741804e828c0073b6694f5ceb592182041151ca0d6ea6"
_SQL107_ID = "107-experience-events"
_SQL107_PATH = "backend/migrations/107_experience_events.sql"
_SQL107_SHA256 = "1ce65e8130e89107a765dfec5ae3d31d431343f864e93bbf0e2e93b8fdfb8881"
_EXPERIENCE_TABLES = frozenset(
    {
        "experience_events",
        "experience_catalogs",
        "experience_operation_links",
        "experience_holds",
        "experience_aggregates",
        "experience_maintenance",
    }
)
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


def load_sql107() -> list[str]:
    """Admit only the reviewed additive diagnostic tables, never arbitrary DDL."""
    migration = next((item for item in load_manifest() if item.logical_id == _SQL107_ID), None)
    if migration is None or (migration.relative_path, migration.sha256) != (_SQL107_PATH, _SQL107_SHA256):
        raise MigrationLedgerError("SQL107 immutable manifest identity does not match")
    payload = (MIGRATIONS / "107_experience_events.sql").read_bytes()
    if hashlib.sha256(payload).hexdigest() != _SQL107_SHA256:
        raise MigrationLedgerError("SQL107 immutable payload checksum does not match")
    sql = "\n".join(line for line in payload.decode("utf-8").splitlines() if not line.lstrip().startswith("--"))
    statements = [statement.strip() for statement in sql.split(";") if statement.strip()]
    names = []
    for statement in statements:
        match = re.match(r"\ACREATE TABLE IF NOT EXISTS ([a-z_]+)\s*\(", statement)
        if match is None:
            raise MigrationLedgerError("SQL107 contains unsupported DDL")
        names.append(match[1])
    if len(names) != len(_EXPERIENCE_TABLES) or set(names) != _EXPERIENCE_TABLES:
        raise MigrationLedgerError("SQL107 table set does not match")
    return statements


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
        experience,
        gpu_quota_requests,
        mcp_authority,
        organization_provisioning,
        project_ownership,
    )

    return Base.metadata


def _verify_sql107(sync, metadata: MetaData) -> None:
    """Refuse incompatible existing tables; CREATE IF NOT EXISTS cannot fix them."""
    inspector = inspect(sync)
    database = sync.execute(text("SELECT DATABASE()")).scalar_one()

    def normalized_type(value) -> str:
        compiled = value.compile(dialect=sync.dialect).upper()
        return re.sub(r"\b(BIGINT|INT|INTEGER)\([0-9]+\)", r"\1", compiled)

    for name in sorted(_EXPERIENCE_TABLES):
        expected = metadata.tables[name]
        columns = {column["name"]: column for column in inspector.get_columns(name)}
        if set(columns) != set(expected.c.keys()):
            raise MigrationLedgerError(f"SQL107 column set is incompatible: {name}")
        # SQLAlchemy's MariaDB inspector omits inline JSON CHECK constraints.
        checks = set()
        clauses = sync.execute(
            text(
                "SELECT CHECK_CLAUSE FROM information_schema.CHECK_CONSTRAINTS "
                "WHERE CONSTRAINT_SCHEMA = DATABASE() AND TABLE_NAME = :name"
            ),
            {"name": name},
        ).scalars()
        for clause in clauses:
            try:
                checks.add(_check_signature(clause))
            except MigrationLedgerError:
                continue
        for column in expected.c:
            actual = columns[column.name]
            if bool(actual["nullable"]) != column.nullable:
                raise MigrationLedgerError(f"SQL107 nullability is incompatible: {name}.{column.name}")
            native_type = normalized_type(actual["type"])
            if isinstance(column.type, JSON):
                if native_type != "LONGTEXT" or _check_signature(f"json_valid({column.name})") not in checks:
                    raise MigrationLedgerError(f"SQL107 JSON guard is incompatible: {name}.{column.name}")
            elif native_type != normalized_type(column.type.dialect_impl(sync.dialect)):
                raise MigrationLedgerError(f"SQL107 type is incompatible: {name}.{column.name}")
        if inspector.get_pk_constraint(name)["constrained_columns"] != [column.name for column in expected.primary_key]:
            raise MigrationLedgerError(f"SQL107 primary key is incompatible: {name}")
        expected_indexes = {
            index.name: (tuple(column.name for column in index.columns), bool(index.unique))
            for index in expected.indexes
        }
        expected_indexes.update(
            {
                constraint.name: (tuple(column.name for column in constraint.columns), True)
                for constraint in expected.constraints
                if isinstance(constraint, UniqueConstraint)
            }
        )
        actual_indexes = {
            index["name"]: (tuple(index["column_names"]), bool(index["unique"]))
            for index in inspector.get_indexes(name)
        }
        if any(actual_indexes.get(key) != value for key, value in expected_indexes.items()):
            raise MigrationLedgerError(f"SQL107 indexes are incompatible: {name}")
        expected_foreign_keys = {
            constraint.name: (
                tuple(column.name for column in constraint.columns),
                constraint.referred_table.name,
                tuple(element.column.name for element in constraint.elements),
            )
            for constraint in expected.foreign_key_constraints
        }
        actual_foreign_keys = {key["name"]: key for key in inspector.get_foreign_keys(name)}
        for key, (columns, parent, parent_columns) in expected_foreign_keys.items():
            saved = actual_foreign_keys.get(key)
            if (
                saved is None
                or tuple(saved["constrained_columns"]) != columns
                or saved["referred_table"] != parent
                or saved.get("referred_schema") not in {None, database}
                or tuple(saved["referred_columns"]) != parent_columns
                or (saved.get("options", {}).get("ondelete") or "RESTRICT").upper() not in {"RESTRICT", "NO ACTION"}
            ):
                raise MigrationLedgerError(f"SQL107 catalog referential guard is incompatible: {name}")
        options = inspector.get_table_options(name)
        if options.get("mysql_collate") != "utf8mb4_bin" or options.get("mysql_engine", "").lower() != "innodb":
            raise MigrationLedgerError(f"SQL107 engine or exact-identity collation is incompatible: {name}")
    identity = next(column for column in inspector.get_columns("experience_events") if column["name"] == "id")
    if identity.get("autoincrement") is not True:
        raise MigrationLedgerError("SQL107 event identity is incompatible")


async def ensure_sql107(conn: AsyncConnection, metadata: MetaData) -> None:
    for statement in load_sql107():
        await conn.exec_driver_sql(statement)
    await conn.run_sync(lambda sync: _verify_sql107(sync, metadata))


async def bootstrap_database(
    database_url: str,
    *,
    metadata: MetaData | None = None,
    grants_table: str = _GRANTS,
    tokens_table: str = _TOKENS,
) -> bool:
    """Strict missing-table initialization followed by pinned schemas under one lock.

    Optional metadata/table names isolate real bootstrap regression schemas;
    the CLI always uses the registered canonical application models.
    """

    if not database_url:
        raise MigrationLedgerError("database.url is required for schema bootstrap")
    # Validate image contents before opening or changing the database.
    load_sql106()
    if metadata is None:
        load_sql107()
    engine = create_async_engine(database_url, connect_args={"connect_timeout": 10}, hide_parameters=True)
    try:
        async with engine.connect() as conn, schema_lock(conn):
            canonical = metadata is None
            registered = model_metadata() if canonical else metadata
            await conn.run_sync(registered.create_all)
            changed = await ensure_sql106(conn, grants_table=grants_table, tokens_table=tokens_table)
            if canonical:
                await ensure_sql107(conn, registered)
            return changed
    finally:
        await engine.dispose()


def main() -> None:
    from app.config import get_settings

    asyncio.run(bootstrap_database(get_settings().database_url))


if __name__ == "__main__":
    main()
