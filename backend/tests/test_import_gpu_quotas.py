"""Deterministic unit tests for CLI GPU quota importer without real databases."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from sqlalchemy import (
    INT,
    VARCHAR,
    Column,
    DateTime,
    MetaData,
    Table,
    UniqueConstraint,
    create_engine,
    select,
)

from scripts import import_gpu_quotas
from scripts.import_gpu_quotas import run_import


def _create_test_table(engine) -> Table:
    meta = MetaData()
    tbl = Table(
        "gpu_quotas",
        meta,
        Column("id", INT, primary_key=True, autoincrement=True),
        Column("project_id", VARCHAR(64), nullable=False),
        Column("gpu_type", VARCHAR(64), nullable=False),
        Column("limit", INT, nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("updated_at", DateTime(timezone=True), nullable=False),
        UniqueConstraint("project_id", "gpu_type", name="uq_gpu_quotas_project_gpu_type"),
    )
    meta.create_all(engine)
    return tbl


def test_import_gpu_quotas_success_and_dry_run(tmp_path):
    source_db = tmp_path / "source.db"
    target_db = tmp_path / "target.db"

    source_url = f"sqlite:///{source_db}"
    target_url = f"sqlite:///{target_db}"

    src_engine = create_engine(source_url)
    tgt_engine = create_engine(target_url)

    src_tbl = _create_test_table(src_engine)
    tgt_tbl = _create_test_table(tgt_engine)

    now = datetime.now(UTC)
    with src_engine.begin() as conn:
        conn.execute(
            src_tbl.insert(),
            [
                {
                    "id": 1,
                    "project_id": "__default__",
                    "gpu_type": "RTX3090",
                    "limit": 4,
                    "created_at": now,
                    "updated_at": now,
                },
                {
                    "id": 2,
                    "project_id": "p1",
                    "gpu_type": "A100_80GB",
                    "limit": 2,
                    "created_at": now,
                    "updated_at": now,
                },
            ],
        )

    # 1. Dry run should report success and leave target untouched
    res_dry = run_import(source_url, target_url, dry_run=True)
    assert res_dry == 0

    tgt_inspector_engine = create_engine(target_url)
    with tgt_inspector_engine.connect() as conn:
        rows_dry = list(conn.execute(select(tgt_tbl)).mappings().all())
    assert len(rows_dry) == 0

    # 2. Live import should insert exact rows
    res_live = run_import(source_url, target_url, dry_run=False)
    assert res_live == 0

    with tgt_inspector_engine.connect() as conn:
        rows_live = list(conn.execute(select(tgt_tbl)).mappings().all())

    assert len(rows_live) == 2
    by_id = {r["id"]: r for r in rows_live}

    assert by_id[1]["project_id"] == "__default__"
    assert by_id[1]["gpu_type"] == "RTX3090"
    assert by_id[1]["limit"] == 4

    assert by_id[2]["project_id"] == "p1"
    assert by_id[2]["gpu_type"] == "A10080GB"  # Canonicalized from A100_80GB
    assert by_id[2]["limit"] == 2

    # 3. Running live import again (idempotent) should succeed with 0 new insertions
    res_repeat = run_import(source_url, target_url, dry_run=False)
    assert res_repeat == 0


def test_import_gpu_quotas_source_collision_fails(tmp_path):
    source_db = tmp_path / "source.db"
    target_db = tmp_path / "target.db"

    source_url = f"sqlite:///{source_db}"
    target_url = f"sqlite:///{target_db}"

    tgt_engine = create_engine(target_url)
    src_engine = create_engine(source_url)
    src_tbl = _create_test_table(src_engine)

    _create_test_table(tgt_engine)
    now = datetime.now(UTC)
    with src_engine.begin() as conn:
        conn.execute(
            src_tbl.insert(),
            [
                {
                    "id": 1,
                    "project_id": "p1",
                    "gpu_type": "RTX3090",
                    "limit": 2,
                    "created_at": now,
                    "updated_at": now,
                },
                {
                    "id": 2,
                    "project_id": "p1",
                    "gpu_type": "RTX_3090",  # Normalizes to RTX3090 -> Collision!
                    "limit": 4,
                    "created_at": now,
                    "updated_at": now,
                },
            ],
        )

    res = run_import(source_url, target_url, dry_run=False)
    assert res == 1


def test_import_gpu_quotas_target_divergence_fails(tmp_path):
    source_db = tmp_path / "source.db"
    target_db = tmp_path / "target.db"

    source_url = f"sqlite:///{source_db}"
    target_url = f"sqlite:///{target_db}"

    src_engine = create_engine(source_url)
    tgt_engine = create_engine(target_url)

    src_tbl = _create_test_table(src_engine)
    tgt_tbl = _create_test_table(tgt_engine)

    now = datetime.now(UTC)
    with src_engine.begin() as conn:
        conn.execute(
            src_tbl.insert(),
            [
                {
                    "id": 1,
                    "project_id": "p1",
                    "gpu_type": "RTX3090",
                    "limit": 2,
                    "created_at": now,
                    "updated_at": now,
                }
            ],
        )

    with tgt_engine.begin() as conn:
        conn.execute(
            tgt_tbl.insert(),
            [
                {
                    "id": 1,
                    "project_id": "p1",
                    "gpu_type": "RTX3090",
                    "limit": 10,  # Divergent limit!
                    "created_at": now,
                    "updated_at": now,
                }
            ],
        )

    res = run_import(source_url, target_url, dry_run=False)
    assert res == 1


def test_import_gpu_quotas_invalid_source_values_fail(tmp_path):
    source_db = tmp_path / "source.db"
    target_db = tmp_path / "target.db"

    source_url = f"sqlite:///{source_db}"
    target_url = f"sqlite:///{target_db}"

    tgt_engine = create_engine(target_url)
    src_engine = create_engine(source_url)
    src_tbl = _create_test_table(src_engine)
    _create_test_table(tgt_engine)

    now = datetime.now(UTC)
    with src_engine.begin() as conn:
        conn.execute(
            src_tbl.insert(),
            [
                {
                    "id": 1,
                    "project_id": "p1",
                    "gpu_type": "RTX3090",
                    "limit": -5,  # Limit < -1 is invalid!
                    "created_at": now,
                    "updated_at": now,
                }
            ],
        )

    res = run_import(source_url, target_url, dry_run=False)
    assert res == 1


def test_import_gpu_quotas_rejects_target_alias_collision(tmp_path):
    source_url = f"sqlite:///{tmp_path / 'source.db'}"
    target_url = f"sqlite:///{tmp_path / 'target.db'}"
    src_engine = create_engine(source_url)
    tgt_engine = create_engine(target_url)
    src_tbl = _create_test_table(src_engine)
    tgt_tbl = _create_test_table(tgt_engine)
    now = datetime.now(UTC)

    with src_engine.begin() as conn:
        conn.execute(
            src_tbl.insert().values(
                id=1,
                project_id="p1",
                gpu_type="RTX3090",
                limit=2,
                created_at=now,
                updated_at=now,
            )
        )
    with tgt_engine.begin() as conn:
        conn.execute(
            tgt_tbl.insert().values(
                id=2,
                project_id="p1",
                gpu_type="RTX-3090",
                limit=2,
                created_at=now,
                updated_at=now,
            )
        )
    assert run_import(source_url, target_url, dry_run=False) == 1


def test_import_gpu_quotas_rejects_target_primary_key_collision(tmp_path):
    source_url = f"sqlite:///{tmp_path / 'source.db'}"
    target_url = f"sqlite:///{tmp_path / 'target.db'}"
    src_engine = create_engine(source_url)
    tgt_engine = create_engine(target_url)
    src_tbl = _create_test_table(src_engine)
    tgt_tbl = _create_test_table(tgt_engine)
    now = datetime.now(UTC)

    with src_engine.begin() as conn:
        conn.execute(
            src_tbl.insert().values(
                id=1,
                project_id="p1",
                gpu_type="RTX3090",
                limit=2,
                created_at=now,
                updated_at=now,
            )
        )
    with tgt_engine.begin() as conn:
        conn.execute(
            tgt_tbl.insert().values(
                id=1,
                project_id="p2",
                gpu_type="H100",
                limit=2,
                created_at=now,
                updated_at=now,
            )
        )

    assert run_import(source_url, target_url, dry_run=False) == 1


def test_importer_converts_configured_async_mysql_url_to_sync_driver():
    engine = MagicMock()
    with patch("scripts.import_gpu_quotas.create_engine", return_value=engine) as create_engine_mock:
        assert import_gpu_quotas._open_sync_engine("mysql+aiomysql://user:secret@db/quota", "Source") is engine

    url = create_engine_mock.call_args.args[0]
    assert url.drivername == "mysql+pymysql"
