from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.services.gpu_quota import (
    delete_project_gpu_quota,
    get_effective_gpu_quotas,
    get_project_gpu_quotas,
    get_project_gpu_usage,
    set_project_gpu_quota,
)


@pytest.mark.asyncio
async def test_system_admin_usage_uses_global_inventory_and_modern_embedded_flavor():
    conn = MagicMock()
    conn._afterglow_is_system_admin = True
    server = MagicMock()
    server.project_id = "project-a"
    server.status = "ACTIVE"
    server.flavor = {
        "original_name": "gpu.nvidia-l40s",
        "extra_specs": {"pci_passthrough:alias": "NVIDIA_L40S:2"},
    }
    conn.compute.servers.return_value = [server]

    usage = await get_project_gpu_usage(conn, "project-a")

    assert usage == {"NVIDIAL40S": 2}
    conn.compute.servers.assert_called_once_with(details=True, all_projects=True, project_id="project-a")
    conn.compute.get_flavor.assert_not_called()


@pytest.mark.asyncio
async def test_project_scoped_usage_does_not_request_global_inventory():
    conn = MagicMock()
    conn._afterglow_is_system_admin = False
    server = MagicMock()
    server.project_id = "project-a"
    server.status = "ACTIVE"
    server.flavor = {
        "original_name": "gpu.nvidia-l40s",
        "extra_specs": {"pci_passthrough:alias": "NVIDIA_L40S:1"},
    }
    conn.compute.servers.return_value = [server]

    usage = await get_project_gpu_usage(conn, "project-a")

    assert usage == {"NVIDIAL40S": 1}
    conn.compute.servers.assert_called_once_with(details=True)


@pytest.mark.asyncio
async def test_legacy_null_and_duplicate_quota_rows_normalize_and_mutations_converge():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    now = datetime.now(UTC)
    async with engine.begin() as connection:
        await connection.exec_driver_sql(
            """
            CREATE TABLE gpu_quotas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id VARCHAR(64),
                gpu_type VARCHAR(64),
                `limit` INTEGER,
                created_at DATETIME,
                updated_at DATETIME
            )
            """
        )
        await connection.execute(
            text(
                """
                INSERT INTO gpu_quotas (project_id, gpu_type, `limit`, created_at, updated_at)
                VALUES
                    ('__default__', 'RTX-3090', -1, :now, :now),
                    ('__default__', 'RTX_3090', 6, :now, :now),
                    ('project-a', 'RTX-3090', NULL, :now, :now),
                    ('project-a', 'RTX3090', 4, :now, :now),
                    ('project-a', NULL, 9, :now, :now),
                    ('project-a', 'H-100', NULL, :now, :now),
                    ('project-a', 'H100', 3, :now, :now)
                """
            ),
            {"now": now},
        )

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with session_factory() as session:
            quotas = await get_project_gpu_quotas(None, "project-a", session=session)
            assert [(row["gpu_type"], row["limit"]) for row in quotas] == [("H100", 0), ("RTX3090", 0)]
            assert await get_effective_gpu_quotas(None, "project-a", session=session) == {
                "RTX3090": 0,
                "H100": 0,
            }

            updated = await set_project_gpu_quota(None, "project-a", "rtx 3090", 5, session=session)
            assert updated["gpu_type"] == "RTX3090"
            assert updated["limit"] == 5
            assert await delete_project_gpu_quota(None, "project-a", "h_100", session=session) is True

            rows = (
                await session.execute(
                    text(
                        "SELECT project_id, gpu_type, `limit` FROM gpu_quotas "
                        "WHERE project_id = 'project-a' AND gpu_type IS NOT NULL ORDER BY gpu_type, id"
                    )
                )
            ).all()
            assert rows == [("project-a", "RTX3090", 5)]
    finally:
        await engine.dispose()
