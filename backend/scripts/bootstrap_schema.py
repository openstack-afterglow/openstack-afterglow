"""Canonical bootstrap: missing tables and explicitly pinned SQL106/107/108.

This is not a historical migration runner or a migration-ledger baseline.
MariaDB executes pinned SQL106; MySQL uses its reviewed state-driven equivalent.
DDL commits implicitly; schema-before-writer backup and rollback prerequisites
remain mandatory. SQL107 is diagnostic-only; SQL108 adds usage governance tables.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import re
from contextlib import asynccontextmanager

from sqlalchemy import JSON, MetaData, String, UniqueConstraint, inspect, text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from scripts.baseline_migrations import MIGRATIONS, MigrationLedgerError, load_manifest

_SQL106_ID = "106-mcp-oauth-ongoing"
_SQL106_PATH = "backend/migrations/106_mcp_oauth_ongoing.sql"
_SQL106_SHA256 = "b7ca283cceb76d3ce4c741804e828c0073b6694f5ceb592182041151ca0d6ea6"
_SQL107_ID = "107-experience-events"
_SQL107_PATH = "backend/migrations/107_experience_events.sql"
_SQL107_SHA256 = "1ce65e8130e89107a765dfec5ae3d31d431343f864e93bbf0e2e93b8fdfb8881"
_SQL108_ID = "108-instance-usage-governance"
_SQL108_PATH = "backend/migrations/108_instance_usage_governance.sql"
_SQL108_SHA256 = "fc7f6c0d7e6dcf7162a16af0f7e330eaca24bc60ff2196faf617ecd1b4cfa467"
_USAGE_GOVERNANCE_TABLES = frozenset({"instance_usage_policies", "instance_usage_extension_requests"})
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
_ROLE_CEILING_GUARD = "COALESCE(LOWER(JSON_TYPE(issued_role_ceiling)) = 'object', 0)"
_CHECKS = {
    "chk_mcp_grant_expiry": (
        "expires_at IS NOT NULL OR source = 'personal_token' OR (source = 'oauth' AND oauth_ongoing = 1)"
    ),
    "chk_mcp_grant_ongoing": (
        "oauth_ongoing = 0 OR (source = 'oauth' AND expires_at IS NULL "
        f"AND {_ROLE_CEILING_GUARD})"
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


def load_sql108() -> list[str]:
    """Admit the immutable, additive governance tables only."""
    migration = next((item for item in load_manifest() if item.logical_id == _SQL108_ID), None)
    if migration is None or (migration.relative_path, migration.sha256) != (_SQL108_PATH, _SQL108_SHA256):
        raise MigrationLedgerError("SQL108 immutable manifest identity does not match")
    payload = (MIGRATIONS / "108_instance_usage_governance.sql").read_bytes()
    if hashlib.sha256(payload).hexdigest() != _SQL108_SHA256:
        raise MigrationLedgerError("SQL108 immutable payload checksum does not match")
    sql = "\n".join(line for line in payload.decode("utf-8").splitlines() if not line.lstrip().startswith("--"))
    statements = [statement.strip() for statement in sql.split(";") if statement.strip()]
    names = []
    for statement in statements:
        match = re.match(r"\ACREATE TABLE IF NOT EXISTS ([a-z_]+)\s*\(", statement)
        if match is None:
            raise MigrationLedgerError("SQL108 contains unsupported DDL")
        names.append(match[1])
    if len(names) != len(_USAGE_GOVERNANCE_TABLES) or set(names) != _USAGE_GOVERNANCE_TABLES:
        raise MigrationLedgerError("SQL108 table set does not match")
    return statements


def _check_signature(expression: str) -> tuple:
    """Preserve grouping, accepting only known server spelling differences."""
    # Tokenize SQL, not a lowercased/unescaped string: literal content is part
    # of the guard and must never lose case, whitespace, backticks or escapes.
    lexer = re.compile(
        r"\s+|'(?:''|[^'\\])*'|`[a-z_][a-z_0-9]*`|[a-z_][a-z_0-9]*|[0-9]+|<>|[(),=]",
        re.IGNORECASE,
    )
    tokens = []
    offset = 0
    while offset < len(expression):
        match = lexer.match(expression, offset)
        if match is None:
            raise MigrationLedgerError("unsupported SQL106 check expression")
        token = match[0]
        offset = match.end()
        if not token.isspace():
            tokens.append(token if token.startswith("'") else token.strip("`").lower())
    # MySQL stores character-set introducers on reflected string literals.
    # Strip only those known introducers, never text inside a quoted literal.
    tokens = [
        token
        for index, token in enumerate(tokens)
        if not (
            token in {"_utf8", "_utf8mb3", "_utf8mb4"}
            and index + 1 < len(tokens)
            and tokens[index + 1].startswith("'")
        )
    ]
    aliases = {"true": "1", "false": "0", "lower": "lcase"}
    tokens = [aliases.get(token, token) for token in tokens]

    if not tokens:
        return ("missing",)
    position = 0

    def consume(expected: str | None = None) -> str:
        nonlocal position
        if position >= len(tokens) or (expected is not None and tokens[position] != expected):
            raise MigrationLedgerError("unsupported SQL106 check expression")
        value = tokens[position]
        position += 1
        return value

    def peek() -> str | None:
        return tokens[position] if position < len(tokens) else None

    def expression_signature(minimum: int = 0) -> tuple:
        value = consume()
        if value == "(":
            left = expression_signature()
            consume(")")
        elif value in {"and", "or", "is", "not", "=", "<>", ")", ","}:
            raise MigrationLedgerError("unsupported SQL106 check expression")
        elif peek() == "(":
            consume("(")
            arguments = []
            if peek() != ")":
                while True:
                    arguments.append(expression_signature())
                    if peek() != ",":
                        break
                    consume(",")
            consume(")")
            left = ("call", value, tuple(arguments))
        else:
            left = ("value", value)
        precedence = {"or": 1, "and": 2, "=": 3, "<>": 3, "is": 3}
        while (operator := peek()) in precedence and precedence[operator] >= minimum:
            consume()
            if operator == "is":
                negate = peek() == "not"
                if negate:
                    consume("not")
                consume("null")
                left = ("is_null", left, negate)
                continue
            right = expression_signature(precedence[operator] + 1)
            if operator in {"and", "or"}:
                # Associativity may change in server output, but AND/OR
                # precedence and every function/comparison remain significant.
                lhs = left[1] if left[0] == operator else (left,)
                rhs = right[1] if right[0] == operator else (right,)
                left = (operator, lhs + rhs)
            elif (
                operator == "<>"
                and left == ("value", "0")
                and right == _check_signature(_ROLE_CEILING_GUARD)
            ):
                # MySQL SHOW CREATE prints this boolean guard as 0 <> expr.
                # This exact COALESCE(comparison, 0) can only be 0 or 1,
                # so the coercion is scalar-equivalent even under SQL NULLs.
                # Never remove nonzero tests around arbitrary expressions.
                left = right
            else:
                left = (operator, left, right)
        return left

    result = expression_signature()
    if position != len(tokens):
        raise MigrationLedgerError("unsupported SQL106 check expression")
    return result


def _server_family(version: str) -> str:
    """Keep MariaDB compatibility; admit enforced-CHECK MySQL versions explicitly."""
    if "mariadb" in version.lower():
        return "mariadb"
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:[-+].*)?", version)
    if match is None or tuple(map(int, match.groups())) < (8, 0, 19):
        raise MigrationLedgerError("schema bootstrap requires MariaDB or MySQL 8.0.19+")
    return "mysql"


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
    if conn.dialect.is_mariadb:
        check_sql = (
            "SELECT TABLE_NAME, CONSTRAINT_NAME, CHECK_CLAUSE, 'YES' AS ENFORCED "
            "FROM information_schema.CHECK_CONSTRAINTS "
            "WHERE CONSTRAINT_SCHEMA = DATABASE() AND TABLE_NAME IN (:grants, :tokens)"
        )
    else:
        # MySQL CHECK_CLAUSE contains a SQL-string-escaped representation,
        # not executable expression SQL. Use SQLAlchemy's native SHOW CREATE
        # reflection for expressions rather than globally unescaping literals.
        # Enforcement is independently authoritative in TABLE_CONSTRAINTS.
        check_sql = (
            "SELECT TABLE_NAME, CONSTRAINT_NAME, ENFORCED "
            "FROM information_schema.TABLE_CONSTRAINTS "
            "WHERE CONSTRAINT_SCHEMA = DATABASE() AND CONSTRAINT_TYPE = 'CHECK' "
            "AND TABLE_NAME IN (:grants, :tokens)"
        )
    checks = (await conn.execute(text(check_sql), {"grants": grants, "tokens": tokens})).mappings().all()
    if not conn.dialect.is_mariadb:

        def reflected_checks(sync):
            inspector = inspect(sync)
            return {
                (table, check["name"]): check["sqltext"]
                for table in (grants, tokens)
                if inspector.has_table(table)
                for check in inspector.get_check_constraints(table)
            }

        expressions = await conn.run_sync(reflected_checks)
    else:
        expressions = {(row["TABLE_NAME"], row["CONSTRAINT_NAME"]): row["CHECK_CLAUSE"] for row in checks}
    return (
        {(row["TABLE_NAME"], row["COLUMN_NAME"]): row for row in columns},
        {
            (row["TABLE_NAME"], row["CONSTRAINT_NAME"]): (
                expressions.get((row["TABLE_NAME"], row["CONSTRAINT_NAME"]), "") if row["ENFORCED"] == "YES" else ""
            )
            for row in checks
        },
    )


def _column_errors(
    columns: dict,
    checks: dict,
    grants: str,
    tokens: str,
    *,
    allow_missing: bool,
    mysql: bool = False,
    existing_tables: set[str] | None = None,
) -> list[str]:
    errors = []
    for table, column in ((grants, "expires_at"), (tokens, "expires_at")):
        if existing_tables is not None and table not in existing_tables:
            continue
        saved = columns.get((table, column))
        precisions = range(7) if allow_missing and table == tokens else (6,)
        if saved is None or saved["DATA_TYPE"] != "datetime" or saved["DATETIME_PRECISION"] not in precisions:
            errors.append(f"{table}.{column} has an incompatible DATETIME precision")
        elif (table == grants or not allow_missing) and saved["IS_NULLABLE"] != "YES":
            errors.append(f"{table}.{column} must be nullable")
    if existing_tables is not None and grants not in existing_tables:
        return errors
    ongoing = columns.get((grants, "oauth_ongoing"))
    if ongoing is None:
        if not allow_missing:
            errors.append(f"{grants}.oauth_ongoing is missing")
    elif (
        ongoing["COLUMN_TYPE"].lower() not in ({"tinyint", "tinyint(1)"} if mysql else {"tinyint(1)"})
        or ongoing["IS_NULLABLE"] != "NO"
        or str(ongoing["COLUMN_DEFAULT"]).strip("'").lower() not in {"0", "false"}
    ):
        errors.append(f"{grants}.oauth_ongoing must be BOOLEAN NOT NULL DEFAULT FALSE")
    ceiling = columns.get((grants, "issued_role_ceiling"))
    if ceiling is None:
        if not allow_missing:
            errors.append(f"{grants}.issued_role_ceiling is missing")
    elif (
        ceiling["DATA_TYPE"] != ("json" if mysql else "longtext")
        or ceiling["IS_NULLABLE"] != "YES"
        or str(ceiling["COLUMN_DEFAULT"]).lower() not in {"none", "null"}
        or (
            not mysql
            and _check_signature(checks.get((grants, "issued_role_ceiling"), ""))
            != _check_signature("json_valid(issued_role_ceiling)")
        )
    ):
        errors.append(f"{grants}.issued_role_ceiling must be nullable {'MySQL' if mysql else 'MariaDB'} JSON")
    return errors


def _check_errors(checks: dict, grants: str, tokens: str) -> list[str]:
    return [
        f"{table}.{name} does not match SQL106"
        for name, expression in _CHECKS.items()
        for table in [tokens if name == "chk_mcp_oauth_token_expiry" else grants]
        if _check_signature(checks.get((table, name), "")) != _check_signature(expression)
    ]


async def _require_sql106_engines(
    conn: AsyncConnection, grants: str, tokens: str, *, allow_missing: bool = False
) -> None:
    """MySQL's resumable atomic ALTER guarantee requires InnoDB, never conversion."""
    if conn.dialect.is_mariadb:
        return
    engines = dict(
        (
            await conn.execute(
                text(
                    "SELECT TABLE_NAME, ENGINE FROM information_schema.TABLES "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME IN (:grants, :tokens)"
                ),
                {"grants": grants, "tokens": tokens},
            )
        ).all()
    )
    incompatible = [
        table
        for table in (grants, tokens)
        if (table in engines or not allow_missing) and (engines.get(table) or "").lower() != "innodb"
    ]
    if incompatible:
        raise MigrationLedgerError("SQL106 MySQL tables require InnoDB: " + ", ".join(incompatible))


def _mysql_sql106_statements(columns: dict, checks: dict, grants: str, tokens: str) -> list[str]:
    """Reviewed MySQL equivalent of pinned SQL106, planned from locked native state.

    MySQL has no ADD COLUMN / DROP CHECK IF EXISTS. Each ALTER is atomic, so
    interrupted execution can be resumed by inspection without dropping a valid
    guard or swallowing an unexpected DDL failure.
    """
    statements = []
    for column, definition in (
        ("oauth_ongoing", "BOOLEAN NOT NULL DEFAULT FALSE"),
        ("issued_role_ceiling", "JSON NULL"),
    ):
        if (grants, column) not in columns:
            statements.append(f"ALTER TABLE `{grants}` ADD COLUMN `{column}` {definition}")
    for name, expression in _CHECKS.items():
        table = tokens if name == "chk_mcp_oauth_token_expiry" else grants
        saved = checks.get((table, name))
        clauses = []
        if table == tokens:
            expiry = columns[(tokens, "expires_at")]
            if expiry["DATETIME_PRECISION"] != 6 or expiry["IS_NULLABLE"] != "YES":
                # Alter the check together with its dependent column. MySQL
                # otherwise refuses some type changes under an existing check.
                clauses.append("MODIFY COLUMN expires_at DATETIME(6) NULL")
        if clauses or _check_signature(saved or "") != _check_signature(expression):
            if saved is not None:
                clauses.insert(0, f"DROP CHECK `{name}`")
            clauses.append(f"ADD CONSTRAINT `{name}` CHECK ({expression}) ENFORCED")
        if clauses:
            statements.append(f"ALTER TABLE `{table}` " + ", ".join(clauses))
    return statements


async def ensure_sql106(conn: AsyncConnection, *, grants_table: str = _GRANTS, tokens_table: str = _TOKENS) -> bool:
    """Apply SQL106 if needed; return whether DDL ran, and verify every postcondition.

    Alternate table names allow isolated real-database regression tables without
    touching the canonical application's tables. The CLI never accepts them.
    Caller owns the deployment lock and must have created missing tables first.
    """
    for table in (grants_table, tokens_table):
        if not re.fullmatch(r"[a-z_][a-z_0-9]*", table):
            raise MigrationLedgerError("invalid SQL106 table identifier")
    statements = load_sql106()
    mysql = not conn.dialect.is_mariadb
    await _require_sql106_engines(conn, grants_table, tokens_table)
    if not mysql:
        await conn.execute(text("SET SESSION check_constraint_checks = 1"))
    columns, checks = await _schema_state(conn, grants_table, tokens_table)
    errors = _column_errors(columns, checks, grants_table, tokens_table, allow_missing=True, mysql=mysql)
    if errors:
        raise MigrationLedgerError("SQL106 incompatible prerequisite schema: " + "; ".join(errors))
    if not (
        _column_errors(columns, checks, grants_table, tokens_table, allow_missing=False, mysql=mysql)
        or _check_errors(checks, grants_table, tokens_table)
    ):
        return False
    if mysql:
        statements = _mysql_sql106_statements(columns, checks, grants_table, tokens_table)
    for statement in statements:
        if not mysql:
            statement = statement.replace(_GRANTS, grants_table).replace(_TOKENS, tokens_table)
        await conn.exec_driver_sql(statement)
    columns, checks = await _schema_state(conn, grants_table, tokens_table)
    errors = _column_errors(columns, checks, grants_table, tokens_table, allow_missing=False, mysql=mysql)
    errors += _check_errors(checks, grants_table, tokens_table)
    if errors:
        raise MigrationLedgerError("SQL106 postcondition failed: " + "; ".join(errors))
    return True


@asynccontextmanager
async def schema_lock(conn: AsyncConnection, *, timeout: int = 60):
    """Serialize bootstrap on the configured server, surviving DDL commits."""
    version = (await conn.execute(text("SELECT VERSION()"))).scalar_one()
    _server_family(version)
    database = (await conn.execute(text("SELECT DATABASE()"))).scalar_one()
    if not database:
        raise MigrationLedgerError("schema bootstrap requires a selected database")
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
        instance_usage_governance,
        mcp_authority,
        organization_provisioning,
        project_ownership,
    )

    return Base.metadata


def _verify_sql107(sync, metadata: MetaData, *, tables=_EXPERIENCE_TABLES) -> None:
    """Refuse incompatible existing tables; CREATE IF NOT EXISTS cannot fix them."""
    inspector = inspect(sync)
    database = sync.execute(text("SELECT DATABASE()")).scalar_one()

    def normalized_type(value) -> str:
        compiled = value.compile(dialect=sync.dialect).upper()
        if compiled in {"BOOL", "BOOLEAN", "TINYINT(1)"}:
            return "BOOLEAN"
        return re.sub(r"\b(BIGINT|INT|INTEGER)\([0-9]+\)", r"\1", compiled)

    for name in sorted(tables):
        expected = metadata.tables[name]
        columns = {column["name"]: column for column in inspector.get_columns(name)}
        if set(columns) != set(expected.c.keys()):
            raise MigrationLedgerError(f"SQL107 column set is incompatible: {name}")
        # MariaDB JSON is LONGTEXT plus an inline JSON-validity check; MySQL
        # native JSON enforces validity itself and has no such inline check.
        checks = set()
        if sync.dialect.is_mariadb:
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
        native_text_columns = {}
        if not sync.dialect.is_mariadb:
            native_text_columns = {
                row["COLUMN_NAME"]: row
                for row in sync.execute(
                    text(
                        "SELECT COLUMN_NAME, CHARACTER_SET_NAME, COLLATION_NAME FROM information_schema.COLUMNS "
                        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :name"
                    ),
                    {"name": name},
                ).mappings()
            }
        for column in expected.c:
            actual = columns[column.name]
            if bool(actual["nullable"]) != column.nullable:
                raise MigrationLedgerError(f"SQL107 nullability is incompatible: {name}.{column.name}")
            actual_type = actual["type"]
            expected_type = column.type.dialect_impl(sync.dialect)
            if not sync.dialect.is_mariadb and isinstance(column.type, String):
                saved = native_text_columns[column.name]
                if saved["CHARACTER_SET_NAME"] != "utf8mb4" or saved["COLLATION_NAME"] != (
                    column.type.collation or "utf8mb4_bin"
                ):
                    raise MigrationLedgerError(f"SQL107 column collation is incompatible: {name}.{column.name}")
                # MySQL reflects inherited table collation onto VARCHAR/TEXT
                # types. Compare shape only after validating effective native
                # charset/collation, never by deleting arbitrary SQL suffixes.
                actual_type = actual_type.copy()
                expected_type = expected_type.copy()
                actual_type.charset = expected_type.charset = None
                actual_type.collation = expected_type.collation = None
            native_type = normalized_type(actual_type)
            if isinstance(column.type, JSON):
                valid_json = (
                    native_type == "LONGTEXT" and _check_signature(f"json_valid({column.name})") in checks
                    if sync.dialect.is_mariadb
                    else native_type == "JSON"
                )
                if not valid_json:
                    raise MigrationLedgerError(f"SQL107 JSON guard is incompatible: {name}.{column.name}")
            elif native_type != normalized_type(expected_type):
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
    if "experience_events" in tables:
        identity = next(column for column in inspector.get_columns("experience_events") if column["name"] == "id")
        if identity.get("autoincrement") is not True:
            raise MigrationLedgerError("SQL107 event identity is incompatible")


async def ensure_sql107(conn: AsyncConnection, metadata: MetaData) -> None:
    for statement in load_sql107():
        await conn.exec_driver_sql(statement)
    await conn.run_sync(lambda sync: _verify_sql107(sync, metadata))


async def ensure_sql108(conn: AsyncConnection, metadata: MetaData) -> None:
    for statement in load_sql108():
        await conn.exec_driver_sql(statement)
    await conn.run_sync(lambda sync: _verify_sql107(sync, metadata, tables=_USAGE_GOVERNANCE_TABLES))


async def _preflight_existing(
    conn: AsyncConnection, metadata: MetaData, grants: str, tokens: str, *, canonical: bool
) -> None:
    """Reject inspectable incompatibilities before any implicit-commit DDL.

    Genuinely absent tables/SQL106 additions are allowed. Native DDL may still
    fail on data validation, concurrent external DDL, privileges or IO; this
    preflight is not a transactional migration or a substitute for backups.
    """
    existing = set(await conn.run_sync(lambda sync: inspect(sync).get_table_names()))
    await _require_sql106_engines(conn, grants, tokens, allow_missing=True)
    if existing.intersection({grants, tokens}):
        columns, checks = await _schema_state(conn, grants, tokens)
        errors = _column_errors(
            columns,
            checks,
            grants,
            tokens,
            allow_missing=True,
            mysql=not conn.dialect.is_mariadb,
            existing_tables=existing,
        )
        if errors:
            raise MigrationLedgerError("SQL106 incompatible prerequisite schema: " + "; ".join(errors))
        for (table, name), expression in checks.items():
            if table in {grants, tokens} and name in _CHECKS:
                _check_signature(expression)
    if canonical:
        for tables in (_EXPERIENCE_TABLES, _USAGE_GOVERNANCE_TABLES):
            await conn.run_sync(lambda sync, tables=tables: _verify_sql107(sync, metadata, tables=tables & existing))


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
        load_sql108()
    engine = create_async_engine(database_url, connect_args={"connect_timeout": 10}, hide_parameters=True)
    try:
        async with engine.connect() as conn, schema_lock(conn):
            canonical = metadata is None
            registered = model_metadata() if canonical else metadata
            await _preflight_existing(conn, registered, grants_table, tokens_table, canonical=canonical)
            if not conn.dialect.is_mariadb:
                # Scope this to the owned bootstrap connection: fresh canonical
                # tables (including SQL106 parents) must retain native FKs even
                # when the server's default storage engine is nontransactional.
                await conn.exec_driver_sql("SET SESSION default_storage_engine = 'InnoDB'")
            await conn.run_sync(registered.create_all)
            changed = await ensure_sql106(conn, grants_table=grants_table, tokens_table=tokens_table)
            if canonical:
                await ensure_sql107(conn, registered)
                await ensure_sql108(conn, registered)
            return changed
    finally:
        await engine.dispose()


async def verify_database(database_url: str) -> None:
    """Read-only deployment gate; never substitute for the singleton bootstrap."""
    if not database_url:
        raise MigrationLedgerError("database.url is required for schema verification")
    load_sql106()
    load_sql107()
    load_sql108()
    engine = create_async_engine(database_url, connect_args={"connect_timeout": 10}, hide_parameters=True)
    try:
        async with engine.connect() as conn:
            version = (await conn.execute(text("SELECT VERSION()"))).scalar_one()
            _server_family(version)
            await _require_sql106_engines(conn, _GRANTS, _TOKENS, allow_missing=True)
            metadata = model_metadata()
            tables = set(await conn.run_sync(lambda sync: inspect(sync).get_table_names()))
            missing = set(metadata.tables) - tables
            if missing:
                raise MigrationLedgerError("required application tables are missing")
            columns, checks = await _schema_state(conn, _GRANTS, _TOKENS)
            errors = _column_errors(
                columns, checks, _GRANTS, _TOKENS, allow_missing=False, mysql=not conn.dialect.is_mariadb
            )
            errors += _check_errors(checks, _GRANTS, _TOKENS)
            if errors:
                raise MigrationLedgerError("SQL106 schema verification failed: " + "; ".join(errors))
            await conn.run_sync(lambda sync: _verify_sql107(sync, metadata))
            await conn.run_sync(lambda sync: _verify_sql107(sync, metadata, tables=_USAGE_GOVERNANCE_TABLES))
    finally:
        await engine.dispose()


def main() -> None:
    from app.config import get_settings

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true", help="verify the canonical schema without DDL")
    parser.add_argument("--if-configured", action="store_true", help="skip only when the effective database URL is empty")
    args = parser.parse_args()
    database_url = get_settings().database_url
    if args.if_configured and not database_url:
        print("Database is not configured; schema bootstrap is skipped.")
        return
    operation = verify_database if args.verify_only else bootstrap_database
    asyncio.run(operation(database_url))


if __name__ == "__main__":
    main()
