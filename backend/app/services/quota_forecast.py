"""Pure daily-allocation trend engine shared by project and domain reports."""

import math
from collections.abc import Callable
from datetime import datetime

_FORECAST_WINDOW_DAYS = 7
_FORECAST_HORIZON_DAYS = 30


def _quota_pct(in_use: float, limit: float) -> float | None:
    """Return a bounded percentage, or None for unlimited/unknown limits."""
    if limit > 0:
        return min(100.0, round(in_use / limit * 100, 1))
    return None


def _allocation_series(rows: list[dict], sample_times: list[datetime], weight: Callable[[dict], float]) -> list[float]:
    """Sum the allocation weight of usage rows alive at each sample time."""
    return [
        round(
            sum(
                weight(row)
                for row in rows
                if row["started"] is not None
                and row["started"] <= sample
                and (row["ended"] is None or row["ended"] > sample)
            ),
            2,
        )
        for sample in sample_times
    ]


def _linear_forecast(
    series: list[float],
    *,
    in_use: float,
    limit: float,
    has_rows: bool,
    window_days: int = _FORECAST_WINDOW_DAYS,
    horizon_days: int = _FORECAST_HORIZON_DAYS,
) -> dict:
    """Extend the least-squares daily slope of the recent allocation window."""
    points = series[-window_days:]
    trend_available = has_rows and len(points) >= 2
    slope = None
    if trend_available:
        count = len(points)
        x_mean = (count - 1) / 2
        y_mean = sum(points) / count
        denominator = sum((x - x_mean) ** 2 for x in range(count))
        slope = round(sum((x - x_mean) * (y - y_mean) for x, y in enumerate(points)) / denominator, 2)
    projected_pct = None
    days_to_limit = None
    if limit > 0 and slope is not None:
        projected_pct = max(0.0, min(100.0, round((in_use + slope * horizon_days) / limit * 100, 1)))
        if in_use >= limit:
            days_to_limit = 0
        elif slope > 0:
            days_to_limit = math.ceil((limit - in_use) / slope)
    return {
        "current_pct": _quota_pct(in_use, limit),
        "slope_per_day": slope,
        "projected_pct": projected_pct,
        "days_to_limit": days_to_limit,
        "trend_available": trend_available,
        "series": series,
    }
