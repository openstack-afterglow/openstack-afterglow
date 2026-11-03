from dataclasses import replace
from pathlib import Path

import pytest

from scripts import bootstrap_schema
from scripts.baseline_migrations import MANIFEST, MIGRATIONS, MigrationLedgerError, baseline_pre037, load_manifest


def test_manifest_has_unique_logical_ids_and_checksums_for_duplicate_numeric_migrations():
    migrations = load_manifest()

    assert len(migrations) == len({migration.logical_id for migration in migrations})
    assert {migration.logical_id for migration in migrations if migration.logical_id.startswith("035-")} == {
        "035-chat-message-reasoning",
        "035-vm-cloud-init-snippets",
    }
    assert all(len(migration.sha256) == 64 for migration in migrations)


def test_manifest_tracks_every_sql_migration_file():
    manifest_paths = {Path(migration.relative_path).name for migration in load_manifest()}

    assert manifest_paths == {path.name for path in MIGRATIONS.glob("*.sql")}


def test_manifest_checksum_drift_is_fail_closed(tmp_path: Path):
    original = MANIFEST.read_text(encoding="utf-8")
    altered = original.replace("e4dbc0a2d7e4151ac945d9503a4e5eb3798b1e401b7f3888e05b963ff5e0b297", "0" * 64, 1)
    manifest = tmp_path / "manifest.txt"
    manifest.write_text(altered, encoding="utf-8")

    with pytest.raises(MigrationLedgerError, match="checksum drift"):
        load_manifest(manifest)


async def test_pre037_baseline_is_disabled_without_complete_schema_verifier():
    with pytest.raises(MigrationLedgerError, match="automatic pre-037 baselining is disabled"):
        await baseline_pre037("mysql+aiomysql://unused")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("logical_id", "106-reidentified"),
        ("relative_path", "backend/migrations/106_other.sql"),
        ("sha256", "0" * 64),
    ],
)
def test_sql106_bootstrap_rejects_manifest_identity_drift(monkeypatch, field, value):
    migrations = [
        replace(migration, **{field: value}) if migration.logical_id == "106-mcp-oauth-ongoing" else migration
        for migration in load_manifest()
    ]
    monkeypatch.setattr(bootstrap_schema, "load_manifest", lambda: migrations)
    with pytest.raises(MigrationLedgerError, match="immutable manifest identity"):
        bootstrap_schema.load_sql106()


def test_sql106_bootstrap_rechecks_the_payload_after_manifest_validation(monkeypatch, tmp_path):
    migrations = load_manifest()
    (tmp_path / "106_mcp_oauth_ongoing.sql").write_text("-- altered payload\n", encoding="utf-8")
    monkeypatch.setattr(bootstrap_schema, "load_manifest", lambda: migrations)
    monkeypatch.setattr(bootstrap_schema, "MIGRATIONS", tmp_path)
    with pytest.raises(MigrationLedgerError, match="immutable payload checksum"):
        bootstrap_schema.load_sql106()
