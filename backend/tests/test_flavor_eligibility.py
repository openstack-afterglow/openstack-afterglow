"""Unit tests for flavor quota eligibility evaluator and admission reservations."""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.compute import FlavorInfo
from app.models.db import GpuQuota, GpuQuotaReservation
from app.services.flavor_eligibility import (
    FlavorEligibilityDenied,
    FlavorEligibilityUnavailable,
    evaluate_flavor,
    flavor_demand,
    parse_gpu_demand,
    require_flavor_eligible,
)
from app.services.gpu_quota import (
    DEFAULT_PROJECT_ID,
    GpuQuotaDenied,
    release_gpu_reservation,
    reserve_gpu_quota,
    set_project_gpu_quota,
)


def test_parse_gpu_demand_extracts_counts_and_ignores_audio():
    flavor = FlavorInfo(
        id="fl-multi",
        name="gpu.multi",
        vcpus=16,
        ram=32768,
        disk=100,
        extra_specs={"pci_passthrough:alias": "RTX-3090:2, audio_card:1, H100:1"},
    )
    assert parse_gpu_demand(flavor) == {"RTX3090": 2, "H100": 1}


def test_flavor_demand_handles_multiplied_nodes_and_resize_delta():
    base = FlavorInfo(
        id="fl-base",
        name="gpu.small",
        vcpus=4,
        ram=8192,
        disk=40,
        extra_specs={"pci_passthrough:alias": "RTX-3090:1"},
    )
    target = FlavorInfo(
        id="fl-target",
        name="gpu.large",
        vcpus=8,
        ram=16384,
        disk=40,
        extra_specs={"pci_passthrough:alias": "RTX-3090:2"},
    )

    mult = flavor_demand(base, count=3)
    assert mult.instances == 3
    assert mult.cores == 12
    assert mult.ram_mb == 24576
    assert mult.gpus == {"RTX3090": 3}

    resize = flavor_demand(target, count=1, current_flavor=base)
    assert resize.instances == 0
    assert resize.cores == 4
    assert resize.ram_mb == 8192
    assert resize.gpus == {"RTX3090": 1}


def test_evaluate_flavor_flags_blockers_accurately():
    flavor = FlavorInfo(
        id="fl-gpu",
        name="gpu.test",
        vcpus=8,
        ram=16384,
        disk=40,
        extra_specs={"pci_passthrough:alias": "RTX3090:2"},
    )
    compute_quota = {
        "instances": {"limit": 10, "in_use": 9},  # remaining 1 -> pass
        "cores": {"limit": 16, "in_use": 12},  # remaining 4 < 8 -> blocker
        "ram": {"limit": 32768, "in_use": 8192},  # remaining 24576 >= 16384 -> pass
    }
    gpu_status = {
        "RTX3090": {"limit": 2, "in_use": 1, "available": 1},  # remaining 1 < 2 -> blocker
    }

    el = evaluate_flavor(flavor, compute_quota=compute_quota, gpu_status=gpu_status)
    assert el.selectable is False
    codes = {b.code for b in el.blockers}
    assert codes == {"cores_insufficient", "gpu_insufficient"}


def test_evaluate_flavor_handles_failures_as_unavailable():
    flavor = FlavorInfo(
        id="fl-gpu",
        name="gpu.test",
        vcpus=4,
        ram=8192,
        disk=40,
        extra_specs={"pci_passthrough:alias": "RTX3090:1"},
    )
    el = evaluate_flavor(
        flavor,
        compute_quota=None,
        gpu_status=None,
        compute_error=True,
        gpu_error=True,
    )
    assert el.selectable is False
    codes = {b.code for b in el.blockers}
    assert codes == {"compute_quota_unavailable", "gpu_quota_unavailable"}


@pytest.mark.asyncio
async def test_require_flavor_eligible_raises_typed_exceptions():
    conn = MagicMock()
    flavor = FlavorInfo(id="fl-cpu", name="cpu.small", vcpus=4, ram=4096, disk=20)

    with patch(
        "app.services.flavor_eligibility.nova.get_project_quota",
        return_value={
            "instances": {"limit": 1, "in_use": 1},
            "cores": {"limit": 4, "in_use": 0},
            "ram": {"limit": 8192, "in_use": 0},
        },
    ):
        with pytest.raises(FlavorEligibilityDenied):
            await require_flavor_eligible(conn, "p1", flavor)

    with patch("app.services.flavor_eligibility.nova.get_project_quota", side_effect=RuntimeError("lost")):
        with pytest.raises(FlavorEligibilityUnavailable):
            await require_flavor_eligible(conn, "p1", flavor)


@pytest.mark.asyncio
async def test_gpu_quota_reservations_and_concurrency():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(GpuQuota.__table__.create)
        await conn.run_sync(GpuQuotaReservation.__table__.create)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with session_factory() as session:
        # Default: RTX3090 limit = 2
        await set_project_gpu_quota(None, DEFAULT_PROJECT_ID, "RTX3090", 2, session=session)

        mock_conn = MagicMock()
        with patch("app.services.gpu_quota.get_project_gpu_usage", return_value={"RTX3090": 1}):
            # Usage is 1, limit is 2 -> headroom is 1
            res_id_1 = await reserve_gpu_quota(mock_conn, "p1", {"RTX3090": 1}, session=session)
            assert res_id_1 is not None

            # Second admission competing for RTX3090 (usage 1 + reserved 1 + req 1 = 3 > 2) -> Denied
            with pytest.raises(GpuQuotaDenied):
                await reserve_gpu_quota(mock_conn, "p1", {"RTX3090": 1}, session=session)

            # Releasing first reservation frees the headroom
            await release_gpu_reservation(res_id_1, session=session)

            res_id_2 = await reserve_gpu_quota(mock_conn, "p1", {"RTX3090": 1}, session=session)
            assert res_id_2 is not None

    await engine.dispose()
