"""Canonical deployment bootstrap against an explicitly isolated, empty MariaDB schema.

Only tables created by these tests are removed. Existing schemas are refused rather
than cleared; no database, cloud resource, or application service is provisioned.
"""

from __future__ import annotations

import os
from datetime import datetime

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.ext.asyncio import create_async_engine

from scripts.baseline_migrations import MigrationLedgerError
from scripts.bootstrap_schema import bootstrap_database, load_sql108, model_metadata, verify_database
from tests.db_target_safety import assert_isolated_test_database

pytestmark = [pytest.mark.db, pytest.mark.asyncio]

_GOVERNANCE_TABLES = ("instance_usage_policies", "instance_usage_extension_requests")


@pytest.fixture
async def canonical_schema():
    url = os.environ.get("AFTERGLOW_TEST_BOOTSTRAP_DATABASE_URL")
    if not url:
        pytest.skip("AFTERGLOW_TEST_BOOTSTRAP_DATABASE_URL requires a separate empty schema")

    from app.config import get_settings

    # Unlike row-scoped tests, canonical bootstrap owns every table it creates.
    # Never honor the shared-schema override for this test's cleanup boundary.
    assert_isolated_test_database(
        test_database_url=url,
        application_database_url=get_settings().database_url,
        allow_shared=False,
    )
    assert_isolated_test_database(
        test_database_url=url,
        application_database_url=os.environ.get("AFTERGLOW_TEST_DATABASE_URL", ""),
        allow_shared=False,
    )
    metadata = model_metadata()
    engine = create_async_engine(url, hide_parameters=True)
    owns_schema_tables = False
    try:
        async with engine.connect() as conn:
            version = (await conn.execute(text("SELECT VERSION()"))).scalar_one()
            assert "mariadb" in version.lower(), "Canonical bootstrap requires real MariaDB"
            existing = await conn.run_sync(
                lambda sync: inspect(sync).get_table_names() + inspect(sync).get_view_names()
            )
            assert not existing, "Canonical bootstrap tests require an empty, dedicated test schema"
        owns_schema_tables = True
        yield url, engine, metadata
    finally:
        try:
            if owns_schema_tables:
                async with engine.begin() as conn:
                    # Explicit table ownership: never DROP DATABASE or discover
                    # and delete resources outside the registered model set.
                    await conn.run_sync(lambda sync: metadata.drop_all(sync, tables=list(metadata.sorted_tables)))
        finally:
            await engine.dispose()


async def _seed_governance_rows(engine, metadata):
    now = datetime(2026, 11, 4, 12, 34, 56)
    async with engine.begin() as conn:
        await conn.execute(
            metadata.tables["instance_usage_policies"].insert(),
            {
                "cloud_id": "cloud-before-bootstrap",
                "domain_id": "domain-before-bootstrap",
                "review_required": True,
                "revision": "a" * 32,
                "updated_by": "policy-owner",
                "updated_at": now,
            },
        )
        await conn.execute(
            metadata.tables["instance_usage_extension_requests"].insert(),
            {
                "id": "b" * 32,
                "cloud_id": "cloud-before-bootstrap",
                "domain_id": "domain-before-bootstrap",
                "project_id": "project-before-bootstrap",
                "instance_id": "instance-before-bootstrap",
                "instance_name": "Keep this instance",
                "requested_by": "request-owner",
                "requested_at": now,
                "expires_at": datetime(2026, 12, 4, 12, 34, 56),
                "reason": "Preserve the existing reviewed extension",
                "schedule_revision": "c" * 32,
                "policy_revision": "a" * 32,
                "revision": "d" * 32,
                "status": "approved",
                "reviewed_by": "domain-manager",
                "reviewed_at": now,
                "applied_schedule": {"expires_at": "2026-12-04T12:34:56Z", "revision": "e" * 32},
            },
        )


async def _governance_snapshot(engine, metadata):
    async with engine.connect() as conn:
        rows = {}
        ddl = {}
        for name in _GOVERNANCE_TABLES:
            table = metadata.tables[name]
            rows[name] = [dict(row) for row in (await conn.execute(select(table))).mappings()]
            ddl[name] = (await conn.exec_driver_sql(f"SHOW CREATE TABLE `{name}`")).one()[1]
        return rows, ddl


@pytest.mark.parametrize("existing_governance", [False, True], ids=["fresh", "existing-sql108"])
async def test_canonical_bootstrap_creates_sql108_and_repeats_without_changing_rows(
    canonical_schema, existing_governance
):
    url, engine, metadata = canonical_schema
    if existing_governance:
        async with engine.begin() as conn:
            for statement in load_sql108():
                await conn.exec_driver_sql(statement)
        await _seed_governance_rows(engine, metadata)
        before = await _governance_snapshot(engine, metadata)

    # No metadata override: exercise the exact canonical SQL106/107/108 path
    # used by deployment, including registered-model creation and schema lock.
    assert await bootstrap_database(url) is False
    async with engine.connect() as conn:
        actual_tables = set(await conn.run_sync(lambda sync: inspect(sync).get_table_names()))
        assert actual_tables == set(metadata.tables)
        for name in _GOVERNANCE_TABLES:
            actual_columns = await conn.run_sync(lambda sync, name=name: inspect(sync).get_columns(name))
            assert {column["name"] for column in actual_columns} == set(metadata.tables[name].c.keys())
        indexes = await conn.run_sync(lambda sync: inspect(sync).get_indexes("instance_usage_extension_requests"))
        assert {index["name"]: (tuple(index["column_names"]), bool(index["unique"])) for index in indexes} == {
            "idx_instance_usage_request_scope": (("cloud_id", "domain_id", "project_id", "requested_at"), False),
            "idx_instance_usage_request_target": (("cloud_id", "project_id", "instance_id", "status"), False),
        }

    if existing_governance:
        assert await _governance_snapshot(engine, metadata) == before
    else:
        await _seed_governance_rows(engine, metadata)
        before = await _governance_snapshot(engine, metadata)
    assert len(before[0]["instance_usage_policies"]) == 1
    assert len(before[0]["instance_usage_extension_requests"]) == 1
    assert await bootstrap_database(url) is False
    assert await _governance_snapshot(engine, metadata) == before


async def test_read_only_verifier_rejects_missing_and_incompatible_schema_without_repair(canonical_schema):
    url, engine, metadata = canonical_schema
    with pytest.raises(MigrationLedgerError):
        await verify_database(url)
    async with engine.connect() as conn:
        assert await conn.run_sync(lambda sync: inspect(sync).get_table_names()) == []
    await bootstrap_database(url)
    await _seed_governance_rows(engine, metadata)
    before = await _governance_snapshot(engine, metadata)
    await verify_database(url)
    assert await _governance_snapshot(engine, metadata) == before
    async with engine.begin() as conn:
        await conn.exec_driver_sql(
            "ALTER TABLE instance_usage_extension_requests DROP INDEX idx_instance_usage_request_target"
        )
    incompatible = await _governance_snapshot(engine, metadata)
    with pytest.raises(MigrationLedgerError):
        await verify_database(url)
    assert await _governance_snapshot(engine, metadata) == incompatible


@pytest.mark.parametrize(
    ("incompatible_ddl", "error"),
    [
        (
            "ALTER TABLE instance_usage_extension_requests MODIFY reason VARCHAR(254) NOT NULL",
            r"type is incompatible: instance_usage_extension_requests\.reason",
        ),
        (
            "ALTER TABLE instance_usage_extension_requests MODIFY reviewed_by VARCHAR(64) NOT NULL",
            r"nullability is incompatible: instance_usage_extension_requests\.reviewed_by",
        ),
        (
            "ALTER TABLE instance_usage_extension_requests DROP INDEX idx_instance_usage_request_target",
            "indexes are incompatible: instance_usage_extension_requests",
        ),
        (
            "ALTER TABLE instance_usage_policies COLLATE=utf8mb4_general_ci",
            r"(type is incompatible: instance_usage_policies\.cloud_id|engine or exact-identity collation is incompatible: instance_usage_policies)",
        ),
    ],
    ids=["column-type", "nullability", "missing-index", "identity-collation"],
)
async def test_canonical_bootstrap_refuses_incompatible_sql108_without_repairing_or_losing_rows(
    canonical_schema, incompatible_ddl, error
):
    url, engine, metadata = canonical_schema
    async with engine.begin() as conn:
        for statement in load_sql108():
            await conn.exec_driver_sql(statement)
    await _seed_governance_rows(engine, metadata)
    async with engine.begin() as conn:
        await conn.exec_driver_sql(incompatible_ddl)
    before = await _governance_snapshot(engine, metadata)

    with pytest.raises(MigrationLedgerError, match=error):
        await bootstrap_database(url)

    # CREATE IF NOT EXISTS must not disguise an incompatible existing schema;
    # rejection must leave the original rows and incompatible DDL intact.
    assert await _governance_snapshot(engine, metadata) == before
