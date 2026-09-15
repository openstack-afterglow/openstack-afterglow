from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from scripts.baseline_migrations import load_manifest

_MIGRATION = Path(__file__).parents[1] / "migrations" / "021_gpu_quota_normalization.sql"


def test_gpu_quota_normalization_has_immutable_manifest_identity():
    migration = next(item for item in load_manifest() if item.logical_id == "021-gpu-quota-normalization")

    assert Path(migration.relative_path).name == _MIGRATION.name
    assert migration.sha256 == hashlib.sha256(_MIGRATION.read_bytes()).hexdigest()


@pytest.mark.db
@pytest.mark.asyncio
async def test_gpu_quota_normalization_repairs_legacy_rows_idempotently():
    database_url = os.environ.get("AFTERGLOW_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("AFTERGLOW_TEST_DATABASE_URL is required for the MariaDB migration regression")

    table_name = f"gpu_quotas_{uuid.uuid4().hex[:12]}"
    migration_sql = _MIGRATION.read_text(encoding="utf-8").replace("gpu_quotas", table_name)
    statements = [
        statement.strip()
        for statement in "\n".join(
            line for line in migration_sql.splitlines() if not line.lstrip().startswith("--")
        ).split(";")
        if statement.strip()
    ]
    engine = create_async_engine(database_url, pool_pre_ping=True)

    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    f"""
                    CREATE TABLE `{table_name}` (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        project_id VARCHAR(64) NULL,
                        gpu_type VARCHAR(64) NULL,
                        `limit` INT NULL,
                        created_at DATETIME(6) NULL,
                        updated_at DATETIME(6) NULL,
                        KEY idx_{table_name}_project_id (project_id)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
            )
            await connection.execute(
                text(
                    f"""
                    INSERT INTO `{table_name}` (project_id, gpu_type, `limit`, created_at, updated_at)
                    VALUES
                        (' project-a ', 'rtx-3090', -1, NULL, NULL),
                        ('project-a', 'RTX_3090', 4, CURRENT_TIMESTAMP(6), CURRENT_TIMESTAMP(6)),
                        ('project-a', 'RTX3090', 2, CURRENT_TIMESTAMP(6), CURRENT_TIMESTAMP(6)),
                        ('project-a', 'H-100', NULL, NULL, NULL),
                        (NULL, 'A100', 8, NULL, NULL),
                        ('project-a', 'gpu_audio', 8, NULL, NULL)
                    """
                )
            )
            for _ in range(2):
                for statement in statements:
                    await connection.execute(text(statement))

        async with engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(f"SELECT id, project_id, gpu_type, `limit` FROM `{table_name}` ORDER BY gpu_type")
                )
            ).all()
            columns = (
                await connection.execute(
                    text(
                        """
                        SELECT column_name, is_nullable
                        FROM information_schema.columns
                        WHERE table_schema = DATABASE() AND table_name = :table_name
                          AND column_name IN ('project_id', 'gpu_type', 'limit', 'created_at', 'updated_at')
                        """
                    ),
                    {"table_name": table_name},
                )
            ).all()
            unique_columns = (
                (
                    await connection.execute(
                        text(
                            """
                        SELECT column_name
                        FROM information_schema.statistics
                        WHERE table_schema = DATABASE() AND table_name = :table_name
                          AND index_name = :index_name AND non_unique = 0
                        ORDER BY seq_in_index
                        """
                        ),
                        {
                            "table_name": table_name,
                            "index_name": f"uq_{table_name}_project_gpu_type",
                        },
                    )
                )
                .scalars()
                .all()
            )

        assert [(row.project_id, row.gpu_type, row.limit) for row in rows] == [
            ("project-a", "H100", 0),
            ("project-a", "RTX3090", 2),
        ]
        assert {column: nullable for column, nullable in columns} == {
            "project_id": "NO",
            "gpu_type": "NO",
            "limit": "NO",
            "created_at": "NO",
            "updated_at": "NO",
        }
        assert unique_columns == ["project_id", "gpu_type"]
    finally:
        async with engine.begin() as connection:
            await connection.execute(text(f"DROP TABLE IF EXISTS `{table_name}`"))
        await engine.dispose()
