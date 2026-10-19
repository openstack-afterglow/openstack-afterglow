"""Project trend input validation and finite JSON observations."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


def _patch_prom_query(return_value=None):
    """prom_query.query_range를 mock — 기본값: 빈 series."""
    if return_value is None:
        return_value = []
    return patch(
        "app.api.common.dashboard.prom_query.query_range",
        new_callable=AsyncMock,
        return_value=return_value,
    )


# ---------------------------------------------------------------------------
# Invalid range → 400
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trend_invalid_range_returns_400(client, mock_conn):
    """허용되지 않는 range 값은 400 반환."""
    with _patch_prom_query([]):
        resp = await client.get("/api/v1/dashboard/metrics/trend?range=30d")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# NaN 필터
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trend_nan_values_filtered(client, mock_conn):
    """NaN 포인트는 제거되며 Prometheus 자체는 reachable로 판정된다."""
    nan_series = [{"ts": 1000, "value": float("nan")}]
    with _patch_prom_query(nan_series):
        resp = await client.get("/api/v1/dashboard/metrics/trend?range=24h")

    data = resp.json()
    assert data["vcpu"]["data"] == []
    assert data["vcpu"]["available"] is False
    assert data["monitoring_available"] is True
