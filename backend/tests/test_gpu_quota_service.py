"""Deterministic unit tests for Afterglow local GPU quota authority service."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

import openstack.exceptions
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.db import GpuQuota
from app.services.gpu_quota import (
    DEFAULT_PROJECT_ID,
    GpuQuotaDenied,
    GpuQuotaUnavailable,
    check_gpu_quota,
    delete_project_gpu_quota,
    get_effective_gpu_quota_status,
    get_effective_gpu_quotas,
    get_project_gpu_quotas,
    get_project_gpu_usage,
    normalize_gpu_alias,
    set_project_gpu_quota,
)


def test_normalize_gpu_alias_canonicalization():
    assert normalize_gpu_alias("RTX3090") == "RTX3090"
    assert normalize_gpu_alias("rtx 3090 ti") == "RTX3090TI"
    assert normalize_gpu_alias("A100_80GB") == "A10080GB"
    assert normalize_gpu_alias("gpu_audio:1") == ""
    assert normalize_gpu_alias("audio_card") == ""
    assert normalize_gpu_alias("") == ""
    assert normalize_gpu_alias("X" * 70) == ""


@pytest.mark.asyncio
async def test_db_unavailable_fails_closed():
    with patch("app.services.gpu_quota.is_db_available", return_value=False):
        with pytest.raises(GpuQuotaUnavailable):
            await get_project_gpu_quotas(None, "p1")

        with pytest.raises(GpuQuotaUnavailable):
            await set_project_gpu_quota(None, "p1", "RTX3090", 2)

        with pytest.raises(GpuQuotaUnavailable):
            await delete_project_gpu_quota(None, "p1", "RTX3090")

        with pytest.raises(GpuQuotaUnavailable):
            await get_effective_gpu_quotas(None, "p1")

        with pytest.raises(GpuQuotaUnavailable):
            await check_gpu_quota(None, "p1", {"RTX3090": 1})


@pytest.mark.asyncio
async def test_set_project_gpu_quota_validation_errors():
    with patch("app.services.gpu_quota.is_db_available", return_value=True):
        with pytest.raises(ValueError, match="limit"):
            await set_project_gpu_quota(None, "p1", "RTX3090", -2)

        with pytest.raises(ValueError, match="Invalid GPU type"):
            await set_project_gpu_quota(None, "p1", "gpu_audio:1", 2)

        with pytest.raises(ValueError, match="project_id"):
            await set_project_gpu_quota(None, "", "RTX3090", 2)


@pytest.mark.asyncio
async def test_in_memory_quota_crud_and_effective_override():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(GpuQuota.__table__.create)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with session_factory() as session:
        # Set default baseline: RTX3090=4, H100=2
        d1 = await set_project_gpu_quota(None, DEFAULT_PROJECT_ID, "RTX3090", 4, session=session)
        assert d1["gpu_type"] == "RTX3090"
        assert d1["limit"] == 4

        await set_project_gpu_quota(None, DEFAULT_PROJECT_ID, "H100", 2, session=session)

        # Set project p1 override: RTX3090=1
        p1 = await set_project_gpu_quota(None, "proj-1", "RTX3090", 1, session=session)
        assert p1["project_id"] == "proj-1"
        assert p1["limit"] == 1

        # Effective quotas for proj-1: RTX3090 overridden to 1, H100 inherited as 2
        eff = await get_effective_gpu_quotas(None, "proj-1", session=session)
        assert eff == {"RTX3090": 1, "H100": 2}

        status = await get_effective_gpu_quota_status(MagicMock(), "proj-1", session=session)
        assert status == [
            {"project_id": "proj-1", "gpu_type": "H100", "limit": 2, "in_use": 0, "available": 2},
            {"project_id": "proj-1", "gpu_type": "RTX3090", "limit": 1, "in_use": 0, "available": 1},
        ]
        # Delete project override for proj-1
        deleted = await delete_project_gpu_quota(None, "proj-1", "RTX3090", session=session)
        assert deleted is True

        # Effective quota reverts to default baseline (RTX3090=4)
        eff_after = await get_effective_gpu_quotas(None, "proj-1", session=session)
        assert eff_after == {"RTX3090": 4, "H100": 2}

    await engine.dispose()


@pytest.mark.asyncio
async def test_gpu_usage_calculation_filters_status_and_extracts_pci():
    mock_conn = MagicMock()

    s_active = MagicMock()
    s_active.project_id = "p1"
    s_active.status = "ACTIVE"
    s_active.flavor = {"extra_specs": {"pci_passthrough:alias": "RTX3090:2"}}

    s_paused = MagicMock()
    s_paused.project_id = "p1"
    s_paused.status = "PAUSED"
    s_paused.flavor = {"extra_specs": {"pci_passthrough:alias": "H100:1"}}

    s_shutoff = MagicMock()
    s_shutoff.project_id = "p1"
    s_shutoff.status = "SHUTOFF"
    s_shutoff.flavor = {"extra_specs": {"pci_passthrough:alias": "RTX3090:1"}}

    s_deleted = MagicMock()
    s_deleted.project_id = "p1"
    s_deleted.status = "DELETED"
    s_deleted.flavor = {"extra_specs": {"pci_passthrough:alias": "RTX3090:5"}}

    s_other_proj = MagicMock()
    s_other_proj.project_id = "p2"
    s_other_proj.status = "ACTIVE"
    s_other_proj.flavor = {"extra_specs": {"pci_passthrough:alias": "RTX3090:10"}}

    mock_conn.compute.servers.return_value = [
        s_active,
        s_paused,
        s_shutoff,
        s_deleted,
        s_other_proj,
    ]

    usage = await get_project_gpu_usage(mock_conn, "p1")
    assert usage == {"RTX3090": 3, "H100": 1}


@pytest.mark.asyncio
async def test_check_gpu_quota_pass_and_denied():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(GpuQuota.__table__.create)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with session_factory() as session:
        # Default: RTX3090=2, H100=-1 (unlimited)
        await set_project_gpu_quota(None, DEFAULT_PROJECT_ID, "RTX3090", 2, session=session)
        await set_project_gpu_quota(None, DEFAULT_PROJECT_ID, "H100", -1, session=session)

        mock_conn = MagicMock()
        s_active = MagicMock()
        s_active.project_id = "p1"
        s_active.status = "ACTIVE"
        s_active.flavor = {"extra_specs": {"pci_passthrough:alias": "RTX3090:1"}}
        mock_conn.compute.servers.return_value = [s_active]

        # Requesting 1 RTX3090 (usage 1 + req 1 = 2 <= limit 2) -> PASS
        await check_gpu_quota(mock_conn, "p1", {"RTX3090": 1}, session=session)

        # Requesting 100 H100 (unlimited) -> PASS
        await check_gpu_quota(mock_conn, "p1", {"H100": 100}, session=session)

        # Requesting 2 RTX3090 (usage 1 + req 2 = 3 > limit 2) -> DENIED
        with pytest.raises(GpuQuotaDenied, match="quota exceeded"):
            await check_gpu_quota(mock_conn, "p1", {"RTX3090": 2}, session=session)

        # Requesting A100 (absent quota = 0) -> DENIED
        with pytest.raises(GpuQuotaDenied, match="quota exceeded"):
            await check_gpu_quota(mock_conn, "p1", {"A100": 1}, session=session)

    await engine.dispose()


def _gpu_server(project_id: str = "p1", **flavor: Any) -> MagicMock:
    server = MagicMock()
    server.project_id = project_id
    server.status = "ACTIVE"
    server.flavor = flavor
    return server


@pytest.mark.asyncio
async def test_gpu_usage_uses_project_scoped_listing_for_own_project():
    mock_conn = MagicMock()
    mock_conn._afterglow_authenticated_project_id = "p1"
    mock_conn.compute.servers.return_value = [
        _gpu_server(original_name="gpu.3090", extra_specs={"pci_passthrough:alias": "RTX-3090:1"})
    ]

    assert await get_project_gpu_usage(mock_conn, "p1") == {"RTX3090": 1}
    mock_conn.compute.servers.assert_called_once_with(details=True)


@pytest.mark.asyncio
async def test_gpu_usage_uses_all_projects_listing_for_foreign_project():
    mock_conn = MagicMock()
    mock_conn._afterglow_authenticated_project_id = "admin"
    mock_conn.compute.servers.return_value = []

    assert await get_project_gpu_usage(mock_conn, "p1") == {}
    mock_conn.compute.servers.assert_called_once_with(details=True, all_projects=True, project_id="p1")


@pytest.mark.asyncio
async def test_gpu_usage_wraps_listing_forbidden_raised_during_iteration():
    """openstacksdk returns a generator, so the policy error surfaces while consuming it."""
    mock_conn = MagicMock()
    mock_conn._afterglow_authenticated_project_id = "admin"

    def _forbidden_generator(**_kwargs):
        yield _gpu_server(original_name="cpu.2c_4g", extra_specs={})
        raise openstack.exceptions.ForbiddenException(
            "Policy doesn't allow os_compute_api:servers:detail:get_all_tenants"
        )

    mock_conn.compute.servers.side_effect = _forbidden_generator

    with pytest.raises(GpuQuotaUnavailable):
        await get_project_gpu_usage(mock_conn, "p1")


@pytest.mark.asyncio
async def test_gpu_usage_trusts_embedded_snapshot_without_extra_specs():
    """Microversion 2.47+ embeds original_name; flavor.id is the name and must not be looked up."""
    mock_conn = MagicMock()
    mock_conn._afterglow_authenticated_project_id = "p1"
    mock_conn.compute.servers.return_value = [_gpu_server(id="cpu.2c_4g", original_name="cpu.2c_4g", extra_specs={})]

    assert await get_project_gpu_usage(mock_conn, "p1") == {}
    mock_conn.compute.get_flavor.assert_not_called()


@pytest.mark.asyncio
async def test_gpu_usage_legacy_snapshot_falls_back_to_flavor_lookup():
    mock_conn = MagicMock()
    mock_conn._afterglow_authenticated_project_id = "p1"
    mock_conn.compute.servers.return_value = [_gpu_server(id="uuid-1")]
    mock_conn.compute.get_flavor.return_value = MagicMock(extra_specs={"pci_passthrough:alias": "RTX-3090:1"})

    assert await get_project_gpu_usage(mock_conn, "p1") == {"RTX3090": 1}
    mock_conn.compute.get_flavor.assert_called_once_with("uuid-1")


@pytest.mark.asyncio
async def test_effective_quotas_normalize_legacy_keys_with_latest_updated_at_winning():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(GpuQuota.__table__.create)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    older = datetime(2026, 6, 1, tzinfo=UTC)
    newer = datetime(2026, 7, 1, tzinfo=UTC)

    try:
        async with session_factory() as session:
            session.add_all(
                [
                    # A newer unlimited grant must not be downgraded by an older finite row.
                    GpuQuota(
                        project_id=DEFAULT_PROJECT_ID,
                        gpu_type="GTX_TITAN_X",
                        limit=2,
                        created_at=older,
                        updated_at=older,
                    ),
                    GpuQuota(
                        project_id=DEFAULT_PROJECT_ID,
                        gpu_type="GTXTITANX",
                        limit=-1,
                        created_at=newer,
                        updated_at=newer,
                    ),
                    # Equal timestamps: the highest id wins.
                    GpuQuota(
                        project_id=DEFAULT_PROJECT_ID, gpu_type="GTX1080Ti", limit=0, created_at=older, updated_at=older
                    ),
                    GpuQuota(
                        project_id=DEFAULT_PROJECT_ID,
                        gpu_type="GTX-1080-TI",
                        limit=3,
                        created_at=older,
                        updated_at=older,
                    ),
                    GpuQuota(project_id="p1", gpu_type="RTX3090Ti", limit=1, created_at=older, updated_at=older),
                ]
            )
            await session.commit()

            assert await get_effective_gpu_quotas(None, "p1", session=session) == {
                "GTXTITANX": -1,
                "GTX1080TI": 3,
                "RTX3090TI": 1,
            }
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_set_and_delete_converge_legacy_duplicates_under_unique_constraint():
    """The real table enforces (project_id, gpu_type); duplicates must be removed before renaming."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(GpuQuota.__table__.create)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    older = datetime(2026, 6, 1, tzinfo=UTC)
    newer = datetime(2026, 7, 1, tzinfo=UTC)

    try:
        async with session_factory() as session:
            session.add_all(
                [
                    GpuQuota(project_id="p1", gpu_type="RTX3090TI", limit=1, created_at=older, updated_at=older),
                    GpuQuota(project_id="p1", gpu_type="RTX-3090ti", limit=-1, created_at=newer, updated_at=newer),
                ]
            )
            await session.commit()

            updated = await set_project_gpu_quota(None, "p1", "rtx 3090 TI", 2, session=session)
            assert (updated["gpu_type"], updated["limit"]) == ("RTX3090TI", 2)

            rows = (await session.execute(select(GpuQuota).where(GpuQuota.project_id == "p1"))).scalars().all()
            assert [(row.gpu_type, row.limit) for row in rows] == [("RTX3090TI", 2)]

            assert await delete_project_gpu_quota(None, "p1", "RTX-3090-ti", session=session) is True
            remaining = (await session.execute(select(GpuQuota).where(GpuQuota.project_id == "p1"))).scalars().all()
            assert list(remaining) == []
    finally:
        await engine.dispose()
