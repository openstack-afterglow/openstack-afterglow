"""Canonical bootstrap on an explicitly disposable, empty real MySQL 8.0.19+ schema.

Set AFTERGLOW_TEST_MYSQL_DATABASE_URL to a dedicated test schema, never the
application database. Only registered tables created by these tests are removed.
No server/database is provisioned or dropped by this module.
"""

from __future__ import annotations

import json
import os
from datetime import datetime

import pytest
from sqlalchemy import event, inspect, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from scripts import bootstrap_schema
from scripts.baseline_migrations import MigrationLedgerError
from scripts.bootstrap_schema import (
    _CHECKS,
    _check_signature,
    _server_family,
    bootstrap_database,
    model_metadata,
    verify_database,
)
from tests.db_target_safety import assert_isolated_test_database

_MCP_TABLES = ("mcp_delegated_grants", "mcp_oauth_token_families", "mcp_oauth_tokens")
_SNAPSHOT_TABLES = (
    *_MCP_TABLES,
    "experience_catalogs",
    "experience_events",
    "experience_operation_links",
    "experience_holds",
    "experience_aggregates",
    "experience_maintenance",
    "instance_usage_policies",
    "instance_usage_extension_requests",
)


@pytest.mark.parametrize("version", ["5.7.44", "8.0.15", "8.0.18", "8.0", "not-mysql", "8.0.19garbage"])
def test_bootstrap_refuses_unsupported_mysql_versions(version):
    with pytest.raises(MigrationLedgerError, match=r"MySQL 8\.0\.19\+"):
        _server_family(version)


@pytest.mark.parametrize("version", ["8.0.19", "8.0.40-commercial", "8.4.3", "9.1.0"])
def test_bootstrap_admits_supported_mysql_versions(version):
    assert _server_family(version) == "mysql"


def test_bootstrap_preserves_mariadb_version_admission_and_mysql_check_grouping():
    assert _server_family("5.5.5-10.11.19-MariaDB") == "mariadb"
    mysql = (
        "((`oauth_ongoing` = false) or ((`source` = _utf8mb4'oauth') and (`expires_at` is null) "
        "and coalesce((lower(json_type(`issued_role_ceiling`)) = _utf8mb4'object'),0)))"
    )
    assert _check_signature(mysql) == _check_signature(_CHECKS["chk_mcp_grant_ongoing"])
    assert _check_signature("a = 1 OR (b = 1 AND c = 1)") != _check_signature("(a = 1 OR b = 1) AND c = 1")


@pytest.mark.parametrize("literal", ["'OAuth'", "'o`auth'", "'o auth'", "'_utf8mb4oauth'", "'o''auth'"])
def test_sql106_signature_never_normalizes_literal_content(literal):
    assert _check_signature(f"source = {literal}") != _check_signature("source = 'oauth'")


def test_sql106_signature_refuses_escaped_information_schema_text_as_expression_sql():
    # Actual MySQL CHECK_CLAUSE transport text from the native regression:
    # stripping these backslashes globally would also alter genuine literals.
    escaped = r"((`expires_at` is not null) or (`source` = _utf8mb4\'personal_token\'))"
    with pytest.raises(MigrationLedgerError, match="unsupported SQL106 check expression"):
        _check_signature(escaped)


def test_sql106_signature_recognizes_exact_mysql_boolean_ceiling_coercion():
    # Exact SHOW CREATE expression observed in the real MySQL regression.
    mysql = (
        "((`oauth_ongoing` = 0) or ((`source` = _utf8mb4'oauth') and (`expires_at` is null) "
        "and (0 <> coalesce((lower(json_type(`issued_role_ceiling`)) = _utf8mb4'object'),0))))"
    )
    assert _check_signature(mysql) == _check_signature(_CHECKS["chk_mcp_grant_ongoing"])


@pytest.mark.parametrize(
    "guard",
    [
        "1 <> coalesce(lower(json_type(issued_role_ceiling)) = 'object', 0)",
        "0 <> coalesce(lower(json_type(issued_role_ceiling)) = 'object', 1)",
        "0 <> coalesce(lower(json_type(other_column)) = 'object', 0)",
        "0 <> coalesce(json_type(issued_role_ceiling) = 'object', 0)",
        "0 <> coalesce(lower(json_type(issued_role_ceiling)) = 'OBJECT', 0)",
        "0 <> coalesce(lower(json_type(issued_role_ceiling)) = 'object', '0')",
        "0 <> issued_role_ceiling",
    ],
)
def test_sql106_signature_does_not_generalize_mysql_boolean_coercion(guard):
    expression = f"oauth_ongoing = 0 OR (source = 'oauth' AND expires_at IS NULL AND {guard})"
    assert _check_signature(expression) != _check_signature(_CHECKS["chk_mcp_grant_ongoing"])
    assert _check_signature("0 <> other_expression") != _check_signature("other_expression")


@pytest.mark.parametrize("operator", ["!=", ">", ">=", "<", "<=", "<=>", "||", "&&"])
def test_sql106_signature_refuses_unknown_operators(operator):
    with pytest.raises(MigrationLedgerError, match="unsupported SQL106 check expression"):
        _check_signature(f"source {operator} 'oauth'")


@pytest.fixture
async def mysql_schema():
    url = os.environ.get("AFTERGLOW_TEST_MYSQL_DATABASE_URL")
    if not url:
        pytest.skip("AFTERGLOW_TEST_MYSQL_DATABASE_URL is required for real MySQL qualification")
    from app.config import get_settings

    assert_isolated_test_database(
        test_database_url=url,
        application_database_url=get_settings().database_url,
        allow_shared=False,
    )
    metadata = model_metadata()
    engine = create_async_engine(url, hide_parameters=True)
    owns_tables = False
    try:
        async with engine.connect() as conn:
            version = (await conn.exec_driver_sql("SELECT VERSION()")).scalar_one()
            assert "mariadb" not in version.lower(), "This regression must exercise real MySQL, not MariaDB"
            assert _server_family(version) == "mysql"
            existing = await conn.run_sync(
                lambda sync: inspect(sync).get_table_names() + inspect(sync).get_view_names()
            )
            assert not existing, "MySQL bootstrap tests require an empty dedicated test schema"
        owns_tables = True
        yield url, engine, metadata
    finally:
        try:
            if owns_tables:
                async with engine.begin() as conn:
                    await conn.run_sync(lambda sync: metadata.drop_all(sync, tables=list(metadata.sorted_tables)))
        finally:
            await engine.dispose()


async def _seed_mcp(engine, metadata):
    async with engine.begin() as conn:
        for source in ("oauth", "lumen", "personal_token"):
            await conn.execute(
                metadata.tables["mcp_delegated_grants"].insert(),
                {
                    "id": source,
                    "owner_user_id": "owner-before-bootstrap",
                    "owner_project_id": "project-before-bootstrap",
                    "upstream_credential_name": source,
                    "display_name": "Preserve the original consent",
                    "source": source,
                    "access_level": "read",
                    "status": "active",
                    "approved_projects": [{"id": "project-before-bootstrap", "name": "Original"}],
                    "credential_ciphertext": "opaque-existing-ciphertext",
                    "expires_at": datetime(2026, 12, 1, 12, 34, 56, 123456),
                },
            )
        await conn.execute(metadata.tables["mcp_oauth_token_families"].insert(), {"id": "family", "grant_id": "oauth"})
        for token_type in ("access", "refresh"):
            await conn.execute(
                metadata.tables["mcp_oauth_tokens"].insert(),
                {
                    "id": token_type,
                    "family_id": "family",
                    "token_hash": token_type,
                    "token_type": token_type,
                    "resource": "https://example.invalid/mcp",
                    "scopes": ["read"],
                    "generation": 1,
                    "expires_at": datetime(2026, 12, 1, 12, 34, 56),
                },
            )


async def _snapshot(engine, tables=_SNAPSHOT_TABLES, *, legacy_columns=False):
    async with engine.connect() as conn:
        snapshot = {}
        for name in tables:
            rows = [dict(row) for row in (await conn.exec_driver_sql(f"SELECT * FROM `{name}`")).mappings()]
            if legacy_columns and name == "mcp_delegated_grants":
                for row in rows:
                    row.pop("oauth_ongoing", None)
                    row.pop("issued_role_ceiling", None)
            snapshot[name] = sorted(rows, key=lambda row: str(sorted(row.items())))
        return snapshot


async def _ddl(engine, tables=_SNAPSHOT_TABLES):
    async with engine.connect() as conn:
        return {name: (await conn.exec_driver_sql(f"SHOW CREATE TABLE `{name}`")).one()[1] for name in tables}


@pytest.mark.db
@pytest.mark.asyncio
async def test_mysql_canonical_fresh_verify_and_repeat_preserve_native_json_rows(mysql_schema):
    url, engine, metadata = mysql_schema
    with pytest.raises(MigrationLedgerError, match="required application tables are missing"):
        await verify_database(url)
    async with engine.connect() as conn:
        assert await conn.run_sync(lambda sync: inspect(sync).get_table_names()) == []
    assert await bootstrap_database(url) is False
    await _seed_mcp(engine, metadata)
    async with engine.begin() as conn:
        assert set(await conn.run_sync(lambda sync: inspect(sync).get_table_names())) == set(metadata.tables)
        await conn.execute(
            metadata.tables["experience_catalogs"].insert(),
            {"id": "catalog", "revision": "1", "key": "mysql.bootstrap", "locale": "en", "template": "Preserve"},
        )
        await conn.execute(
            metadata.tables["experience_events"].insert(),
            {
                "received_at": datetime(2026, 11, 4),
                "owner_key": "owner",
                "user_id": "user",
                "project_id": "project",
                "segment_id": "segment",
                "event_id": "event",
                "source": "ui",
                "fingerprint": "fingerprint",
                "catalog_id": "catalog",
                "data": {"preserve": ["native-json", 1]},
            },
        )
        await conn.execute(
            metadata.tables["instance_usage_policies"].insert(),
            {
                "cloud_id": "cloud",
                "domain_id": "domain",
                "review_required": True,
                "revision": "a" * 32,
                "updated_by": "owner",
                "updated_at": datetime(2026, 11, 4),
            },
        )
    before, ddl = await _snapshot(engine), await _ddl(engine)
    await verify_database(url)
    assert await bootstrap_database(url) is False
    await verify_database(url)
    assert await _snapshot(engine) == before
    assert await _ddl(engine) == ddl


@pytest.mark.db
@pytest.mark.asyncio
@pytest.mark.parametrize("applied_prefix", range(6))
async def test_mysql_legacy_partial_bootstrap_resumes_and_preserves_all_original_rows(mysql_schema, applied_prefix):
    url, engine, metadata = mysql_schema
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync: metadata.create_all(sync, tables=[metadata.tables[name] for name in _MCP_TABLES])
        )
    await _seed_mcp(engine, metadata)
    async with engine.begin() as conn:
        await conn.exec_driver_sql(
            "ALTER TABLE mcp_delegated_grants DROP CHECK chk_mcp_grant_expiry, DROP CHECK chk_mcp_grant_ongoing, "
            "DROP COLUMN oauth_ongoing, DROP COLUMN issued_role_ceiling, "
            "ADD CONSTRAINT chk_mcp_grant_expiry CHECK (expires_at IS NOT NULL OR source = 'personal_token') ENFORCED"
        )
        await conn.exec_driver_sql(
            "ALTER TABLE mcp_oauth_tokens DROP CHECK chk_mcp_oauth_token_expiry, "
            "MODIFY COLUMN expires_at DATETIME NOT NULL"
        )
        # Cover each implicit-commit boundary independently of the production
        # planner: MySQL cannot replay MariaDB's ADD/DROP IF EXISTS syntax.
        partial = [
            "ALTER TABLE mcp_delegated_grants ADD COLUMN oauth_ongoing BOOLEAN NOT NULL DEFAULT FALSE",
            "ALTER TABLE mcp_delegated_grants ADD COLUMN issued_role_ceiling JSON NULL",
            "ALTER TABLE mcp_delegated_grants DROP CHECK chk_mcp_grant_expiry, "
            f"ADD CONSTRAINT chk_mcp_grant_expiry CHECK ({_CHECKS['chk_mcp_grant_expiry']}) ENFORCED",
            "ALTER TABLE mcp_delegated_grants "
            f"ADD CONSTRAINT chk_mcp_grant_ongoing CHECK ({_CHECKS['chk_mcp_grant_ongoing']}) ENFORCED",
            "ALTER TABLE mcp_oauth_tokens MODIFY COLUMN expires_at DATETIME(6) NULL, "
            f"ADD CONSTRAINT chk_mcp_oauth_token_expiry CHECK ({_CHECKS['chk_mcp_oauth_token_expiry']}) ENFORCED",
        ]
        for statement in partial[:applied_prefix]:
            await conn.exec_driver_sql(statement)
    before = await _snapshot(engine, _MCP_TABLES, legacy_columns=True)
    assert await bootstrap_database(url) is (applied_prefix < 5)
    await verify_database(url)
    assert await _snapshot(engine, _MCP_TABLES, legacy_columns=True) == before
    async with engine.connect() as conn:
        assert (
            await conn.exec_driver_sql(
                "SELECT COUNT(*) FROM mcp_delegated_grants WHERE oauth_ongoing = 0 AND issued_role_ceiling IS NULL"
            )
        ).scalar_one() == 3
    ddl = await _ddl(engine)
    assert await bootstrap_database(url) is False
    assert await _snapshot(engine, _MCP_TABLES, legacy_columns=True) == before
    assert await _ddl(engine) == ddl


@pytest.mark.db
@pytest.mark.asyncio
async def test_mysql_checks_reject_invalid_authority_and_allow_only_explicit_ongoing(mysql_schema):
    url, engine, metadata = mysql_schema
    await bootstrap_database(url)
    await _seed_mcp(engine, metadata)
    ceiling = json.dumps({"project-before-bootstrap": [{"id": "reader-id", "name": "reader"}]})
    async with engine.begin() as conn:
        for source, expiry, ongoing, saved in (
            ("oauth", None, 0, None),
            ("oauth", None, 1, None),
            ("oauth", None, 1, "null"),
            ("oauth", None, 1, "[]"),
            ("lumen", None, 1, ceiling),
            ("personal_token", None, 1, ceiling),
            ("oauth", "2026-12-01", 1, ceiling),
        ):
            with pytest.raises(DBAPIError) as rejected:
                await conn.execute(
                    text(
                        "UPDATE mcp_delegated_grants SET source=:source, expires_at=:expiry, "
                        "oauth_ongoing=:ongoing, issued_role_ceiling=:ceiling WHERE id='oauth'"
                    ),
                    {"source": source, "expiry": expiry, "ongoing": ongoing, "ceiling": saved},
                )
            assert rejected.value.orig.args[0] == 3819
        with pytest.raises(DBAPIError) as rejected:
            await conn.exec_driver_sql("UPDATE mcp_oauth_tokens SET expires_at=NULL WHERE id='access'")
        assert rejected.value.orig.args[0] == 3819
        await conn.execute(
            text(
                "UPDATE mcp_delegated_grants SET expires_at=NULL, oauth_ongoing=1, "
                "issued_role_ceiling=:ceiling WHERE id='oauth'"
            ),
            {"ceiling": ceiling},
        )
        await conn.exec_driver_sql("UPDATE mcp_oauth_tokens SET expires_at=NULL WHERE id='refresh'")
    before = await _snapshot(engine)
    await verify_database(url)
    assert await bootstrap_database(url) is False
    assert await _snapshot(engine) == before


@pytest.mark.db
@pytest.mark.asyncio
@pytest.mark.parametrize("constraint", list(_CHECKS))
async def test_mysql_verify_rejects_unenforced_guards_and_bootstrap_restores_them(mysql_schema, constraint):
    url, engine, metadata = mysql_schema
    await bootstrap_database(url)
    await _seed_mcp(engine, metadata)
    table = "mcp_oauth_tokens" if constraint == "chk_mcp_oauth_token_expiry" else "mcp_delegated_grants"
    async with engine.begin() as conn:
        await conn.exec_driver_sql(f"ALTER TABLE `{table}` ALTER CHECK `{constraint}` NOT ENFORCED")
    before, ddl = await _snapshot(engine), await _ddl(engine)
    with pytest.raises(MigrationLedgerError, match="SQL106 schema verification failed"):
        await verify_database(url)
    assert await _snapshot(engine) == before
    assert await _ddl(engine) == ddl
    assert await bootstrap_database(url) is True
    await verify_database(url)
    assert await _snapshot(engine) == before
    assert await bootstrap_database(url) is False


@pytest.mark.db
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("statement", "error"),
    [
        ("ALTER TABLE mcp_delegated_grants ALTER COLUMN oauth_ongoing SET DEFAULT 1", "BOOLEAN"),
        (
            "ALTER TABLE instance_usage_extension_requests DROP INDEX idx_instance_usage_request_target",
            "indexes are incompatible",
        ),
        ("ALTER TABLE experience_operation_links MODIFY context LONGTEXT NOT NULL", "JSON guard is incompatible"),
        ("ALTER TABLE experience_operation_links MODIFY kind VARCHAR(31) NOT NULL", "type is incompatible"),
        (
            "ALTER TABLE experience_operation_links MODIFY kind VARCHAR(32) "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL",
            "column collation is incompatible",
        ),
        (
            "ALTER TABLE experience_operation_links MODIFY kind VARCHAR(32) "
            "CHARACTER SET latin1 COLLATE latin1_bin NOT NULL",
            "column collation is incompatible",
        ),
        (
            "ALTER TABLE experience_operation_links DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci",
            "engine or exact-identity collation is incompatible",
        ),
    ],
)
async def test_mysql_verification_and_bootstrap_refuse_incompatible_schema_without_data_loss(
    mysql_schema, statement, error
):
    url, engine, metadata = mysql_schema
    await bootstrap_database(url)
    await _seed_mcp(engine, metadata)
    async with engine.begin() as conn:
        await conn.exec_driver_sql(statement)
    before, ddl = await _snapshot(engine), await _ddl(engine)
    with pytest.raises(MigrationLedgerError, match=error):
        await verify_database(url)
    assert await _ddl(engine) == ddl
    with pytest.raises(MigrationLedgerError, match=error):
        await bootstrap_database(url)
    assert await _snapshot(engine) == before
    assert await _ddl(engine) == ddl


@pytest.mark.db
@pytest.mark.asyncio
@pytest.mark.parametrize("version", ["5.7.44", "8.0.18", "not-mysql"])
@pytest.mark.parametrize("verify_only", [False, True])
async def test_mysql_invalid_version_fails_before_any_schema_ddl(mysql_schema, monkeypatch, version, verify_only):
    url, engine, _ = mysql_schema
    statements = []

    def intercept(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)
        if statement == "SELECT VERSION()":
            return "SELECT %s", (version,)
        return statement, parameters

    event.listen(engine.sync_engine, "before_cursor_execute", intercept, retval=True)
    monkeypatch.setattr(bootstrap_schema, "create_async_engine", lambda *args, **kwargs: engine)
    try:
        with pytest.raises(MigrationLedgerError, match=r"MySQL 8\.0\.19\+"):
            await (verify_database(url) if verify_only else bootstrap_database(url))
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", intercept)
    assert not any(statement.lstrip().upper().startswith(("CREATE ", "ALTER ", "DROP ")) for statement in statements)
    async with engine.connect() as conn:
        assert await conn.run_sync(lambda sync: inspect(sync).get_table_names()) == []


@pytest.mark.db
@pytest.mark.asyncio
async def test_mysql_checked_token_precision_upgrade_is_atomic_and_preserves_deadlines(mysql_schema):
    url, engine, metadata = mysql_schema
    await bootstrap_database(url)
    await _seed_mcp(engine, metadata)
    async with engine.begin() as conn:
        await conn.exec_driver_sql(
            "ALTER TABLE mcp_oauth_tokens DROP CHECK chk_mcp_oauth_token_expiry, "
            "MODIFY COLUMN expires_at DATETIME NOT NULL, "
            f"ADD CONSTRAINT chk_mcp_oauth_token_expiry CHECK ({_CHECKS['chk_mcp_oauth_token_expiry']}) ENFORCED"
        )
    before = await _snapshot(engine)
    with pytest.raises(MigrationLedgerError, match="DATETIME precision"):
        await verify_database(url)
    assert await bootstrap_database(url) is True
    await verify_database(url)
    assert await _snapshot(engine) == before
    assert await bootstrap_database(url) is False


@pytest.mark.db
@pytest.mark.asyncio
async def test_mysql_invalid_existing_row_fails_without_dropping_or_rewriting_original_guard(mysql_schema):
    url, engine, metadata = mysql_schema
    await bootstrap_database(url)
    await _seed_mcp(engine, metadata)
    async with engine.begin() as conn:
        await conn.exec_driver_sql("ALTER TABLE mcp_delegated_grants ALTER CHECK chk_mcp_grant_expiry NOT ENFORCED")
        await conn.exec_driver_sql("UPDATE mcp_delegated_grants SET expires_at=NULL WHERE id='oauth'")
    before, ddl = await _snapshot(engine), await _ddl(engine)
    with pytest.raises(DBAPIError) as rejected:
        await bootstrap_database(url)
    assert rejected.value.orig.args[0] == 3819
    assert await _snapshot(engine) == before
    assert await _ddl(engine) == ddl
    with pytest.raises(MigrationLedgerError, match="SQL106 schema verification failed"):
        await verify_database(url)


@pytest.mark.db
@pytest.mark.asyncio
async def test_mysql_schema_lock_serializes_bootstrap_and_releases_after_failure(mysql_schema):
    _, engine, _ = mysql_schema
    async with engine.connect() as first, engine.connect() as second:
        with pytest.raises(RuntimeError, match="owned failure"):
            async with bootstrap_schema.schema_lock(first):
                with pytest.raises(MigrationLedgerError, match="lock was not acquired"):
                    async with bootstrap_schema.schema_lock(second, timeout=0):
                        pytest.fail("a second bootstrap acquired the same schema lock")
                raise RuntimeError("owned failure")
        async with bootstrap_schema.schema_lock(second, timeout=0):
            assert (await second.exec_driver_sql("SELECT 1")).scalar_one() == 1


@pytest.mark.db
@pytest.mark.asyncio
@pytest.mark.parametrize("non_innodb", ["mcp_delegated_grants", "mcp_oauth_tokens"])
async def test_mysql_non_innodb_sql106_tables_are_refused_without_ddl_or_row_changes(mysql_schema, non_innodb):
    url, engine, _ = mysql_schema
    tables = ("mcp_delegated_grants", "mcp_oauth_tokens")
    async with engine.begin() as conn:
        for table in tables:
            engine_name = "MyISAM" if table == non_innodb else "InnoDB"
            await conn.exec_driver_sql(
                f"CREATE TABLE `{table}` (id VARCHAR(36) PRIMARY KEY, expires_at DATETIME(6) NULL) ENGINE={engine_name}"
            )
            await conn.exec_driver_sql(
                f"INSERT INTO `{table}` VALUES ('preserve-original', '2026-12-01 12:34:56.123456')"
            )
        before_ddl = {table: (await conn.exec_driver_sql(f"SHOW CREATE TABLE `{table}`")).one()[1] for table in tables}
    before = await _snapshot(engine, tables)
    for operation in (verify_database, bootstrap_database):
        with pytest.raises(MigrationLedgerError, match=f"SQL106 MySQL tables require InnoDB: {non_innodb}"):
            await operation(url)
        assert await _snapshot(engine, tables) == before
        async with engine.connect() as conn:
            assert set(await conn.run_sync(lambda sync: inspect(sync).get_table_names())) == set(tables)
            assert {
                table: (await conn.exec_driver_sql(f"SHOW CREATE TABLE `{table}`")).one()[1] for table in tables
            } == before_ddl


@pytest.mark.db
@pytest.mark.asyncio
@pytest.mark.parametrize("incompatible", ["sql106", "sql107", "sql108"])
async def test_mysql_preflight_refuses_known_incompatibilities_before_any_pending_ddl(
    mysql_schema, monkeypatch, incompatible
):
    url, engine, metadata = mysql_schema
    await bootstrap_database(url)
    await _seed_mcp(engine, metadata)
    async with engine.begin() as conn:
        await conn.exec_driver_sql("DROP TABLE experience_maintenance")
        if incompatible == "sql106":
            await conn.exec_driver_sql("ALTER TABLE mcp_delegated_grants ALTER COLUMN oauth_ongoing SET DEFAULT 1")
            error = "BOOLEAN"
        else:
            await conn.exec_driver_sql(
                "ALTER TABLE mcp_delegated_grants DROP CHECK chk_mcp_grant_expiry, "
                "DROP CHECK chk_mcp_grant_ongoing, DROP COLUMN oauth_ongoing, DROP COLUMN issued_role_ceiling, "
                "ADD CONSTRAINT chk_mcp_grant_expiry "
                "CHECK (expires_at IS NOT NULL OR source = 'personal_token') ENFORCED"
            )
            await conn.exec_driver_sql(
                "ALTER TABLE mcp_oauth_tokens DROP CHECK chk_mcp_oauth_token_expiry, "
                "MODIFY COLUMN expires_at DATETIME NOT NULL"
            )
            if incompatible == "sql107":
                await conn.exec_driver_sql("ALTER TABLE experience_operation_links MODIFY kind VARCHAR(31) NOT NULL")
                error = "type is incompatible"
            else:
                await conn.exec_driver_sql(
                    "ALTER TABLE instance_usage_extension_requests DROP INDEX idx_instance_usage_request_target"
                )
                error = "indexes are incompatible"
        tables = await conn.run_sync(lambda sync: inspect(sync).get_table_names())
    before, ddl = await _snapshot(engine, tables), await _ddl(engine, tables)
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", capture)
    monkeypatch.setattr(bootstrap_schema, "create_async_engine", lambda *args, **kwargs: engine)
    try:
        with pytest.raises(MigrationLedgerError, match=error):
            await bootstrap_database(url)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", capture)
    assert not any(statement.lstrip().upper().startswith(("CREATE ", "ALTER ", "DROP ")) for statement in statements)
    assert await _snapshot(engine, tables) == before
    assert await _ddl(engine, tables) == ddl
    async with engine.connect() as conn:
        assert await conn.run_sync(lambda sync: inspect(sync).get_table_names()) == tables


@pytest.mark.db
@pytest.mark.asyncio
@pytest.mark.parametrize("precreate_sql107", [False, True], ids=["fresh-canonical", "explicit-sql107-models"])
async def test_mysql_non_innodb_default_still_creates_transactional_canonical_tables(
    mysql_schema, monkeypatch, precreate_sql107
):
    url, engine, metadata = mysql_schema

    def nontransactional_default(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("SET SESSION default_storage_engine = 'MyISAM'")
        finally:
            cursor.close()

    event.listen(engine.sync_engine, "connect", nontransactional_default)
    await engine.dispose()
    monkeypatch.setattr(bootstrap_schema, "create_async_engine", lambda *args, **kwargs: engine)
    try:
        async with engine.begin() as conn:
            assert (await conn.exec_driver_sql("SELECT @@SESSION.default_storage_engine")).scalar_one() == "MyISAM"
            if precreate_sql107:
                await conn.run_sync(
                    lambda sync: metadata.create_all(
                        sync, tables=[metadata.tables[name] for name in bootstrap_schema._EXPERIENCE_TABLES]
                    )
                )
                assert set(
                    (
                        await conn.exec_driver_sql(
                            "SELECT ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE()"
                        )
                    ).scalars()
                ) == {"InnoDB"}
        assert await bootstrap_database(url) is False
        await _seed_mcp(engine, metadata)
        async with engine.connect() as conn:
            # A fresh connection still inherits the deliberately non-InnoDB
            # default; bootstrap did not alter global/server configuration.
            assert (await conn.exec_driver_sql("SELECT @@SESSION.default_storage_engine")).scalar_one() == "MyISAM"
            engines = dict(
                (
                    await conn.exec_driver_sql(
                        "SELECT TABLE_NAME, ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE()"
                    )
                ).all()
            )
            assert set(engines) == set(metadata.tables)
            assert set(engines.values()) == {"InnoDB"}
        before, ddl = await _snapshot(engine), await _ddl(engine)
        await verify_database(url)
        assert await bootstrap_database(url) is False
        assert await _snapshot(engine) == before
        assert await _ddl(engine) == ddl
    finally:
        event.remove(engine.sync_engine, "connect", nontransactional_default)
