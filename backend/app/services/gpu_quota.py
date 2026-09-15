"""Local GPU Quota Authority Service for Afterglow.

Defines persistence, effective quota resolution, usage calculation, and admission prechecks
without Drover dependencies.
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session_factory, is_db_available, mark_db_unhealthy
from app.models.db import GpuQuota, GpuQuotaReservation

_logger = logging.getLogger(__name__)

DEFAULT_PROJECT_ID = "__default__"


class GpuQuotaDenied(Exception):
    """GPU quota limit reached or quota denied for requested resources."""


class GpuQuotaUnavailable(Exception):
    """Database authority is unavailable; callers must fail closed."""


def normalize_gpu_alias(alias: str) -> str:
    """Normalize a GPU PCI alias string into a canonical uppercase token.

    Punctuation (hyphens, underscores, spaces) is stripped.
    Blank aliases, aliases containing 'audio' (case-insensitive), or normalized
    strings longer than 64 characters return empty string.
    """
    if not alias or not isinstance(alias, str):
        return ""
    stripped = alias.strip()
    if not stripped or "audio" in stripped.lower():
        return ""
    norm = re.sub(r"[^a-zA-Z0-9]", "", stripped).upper()
    if not norm or len(norm) > 64 or "AUDIO" in norm:
        return ""
    return norm


def _normalized_limit(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < -1:
        return 0
    return value


def _merge_quota_limits(rows: list[GpuQuota]) -> int:
    limits = [_normalized_limit(row.limit) for row in rows]
    finite = [limit for limit in limits if limit != -1]
    return min(finite) if finite else -1


def _normalized_quota_groups(rows: list[GpuQuota]) -> dict[str, list[GpuQuota]]:
    groups: dict[str, list[GpuQuota]] = {}
    for row in rows:
        gpu_type = normalize_gpu_alias(row.gpu_type)
        if gpu_type:
            groups.setdefault(gpu_type, []).append(row)
    return groups


def _canonical_quota_row(rows: list[GpuQuota]) -> GpuQuota:
    return min(rows, key=lambda row: (row.id is None, row.id or 0))


async def _execute_db_op(op_func, session_override: AsyncSession | None = None):
    if session_override is not None:
        return await op_func(session_override)
    if not is_db_available():
        raise GpuQuotaUnavailable("GPU quota database authority is unavailable")
    factory = get_session_factory()
    if factory is None:
        raise GpuQuotaUnavailable("GPU quota database session factory is unavailable")
    try:
        async with factory() as session:
            return await op_func(session)
    except GpuQuotaUnavailable:
        raise
    except Exception as exc:
        mark_db_unhealthy(exc)
        raise GpuQuotaUnavailable("GPU quota database operation failed") from exc


async def get_project_gpu_quotas(
    conn: Any, project_id: str, *, session: AsyncSession | None = None
) -> list[dict[str, Any]]:
    """Get stored GPU quotas for default or a specific project."""
    if not project_id or not isinstance(project_id, str):
        raise ValueError("project_id must be a non-empty string")

    async def _op(sess: AsyncSession) -> list[dict[str, Any]]:
        result = await sess.execute(select(GpuQuota).where(GpuQuota.project_id == project_id))
        groups = _normalized_quota_groups(list(result.scalars().all()))
        usage = await get_project_gpu_usage(conn, project_id) if conn and project_id != DEFAULT_PROJECT_ID else {}
        quotas = []
        for gpu_type in sorted(groups):
            rows = groups[gpu_type]
            row = _canonical_quota_row(rows)
            limit = _merge_quota_limits(rows)
            quota = {
                "id": row.id,
                "project_id": project_id,
                "gpu_type": gpu_type,
                "limit": limit,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
            if project_id != DEFAULT_PROJECT_ID:
                in_use = usage.get(gpu_type, 0)
                quota.update(
                    {
                        "in_use": in_use,
                        "available": max(0, limit - in_use) if limit >= 0 else -1,
                    }
                )
            quotas.append(quota)
        return quotas

    return await _execute_db_op(_op, session_override=session)


async def set_project_gpu_quota(
    conn: Any, project_id: str, gpu_type: str, limit: int, *, session: AsyncSession | None = None
) -> dict[str, Any]:
    """Create or update a GPU quota entry for a project or default baseline."""
    if not project_id or not isinstance(project_id, str) or len(project_id) > 64:
        raise ValueError("project_id must be a non-empty string <= 64 chars")
    if not isinstance(limit, int) or limit < -1:
        raise ValueError("limit must be an integer >= -1")
    norm_type = normalize_gpu_alias(gpu_type)
    if not norm_type or len(norm_type) > 64:
        raise ValueError(f"Invalid GPU type alias: {gpu_type}")

    async def _op(sess: AsyncSession) -> dict[str, Any]:
        res = await sess.execute(select(GpuQuota).where(GpuQuota.project_id == project_id).with_for_update())
        matches = [row for row in res.scalars().all() if normalize_gpu_alias(row.gpu_type) == norm_type]
        now = datetime.now(UTC)
        if matches:
            row = _canonical_quota_row(matches)
            row.gpu_type = norm_type
            row.limit = limit
            row.updated_at = now
            for duplicate in matches:
                if duplicate is not row:
                    await sess.delete(duplicate)
        else:
            row = GpuQuota(
                project_id=project_id,
                gpu_type=norm_type,
                limit=limit,
                created_at=now,
                updated_at=now,
            )
            sess.add(row)
        await sess.commit()
        await sess.refresh(row)
        return {
            "id": row.id,
            "project_id": row.project_id,
            "gpu_type": row.gpu_type,
            "limit": row.limit,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    return await _execute_db_op(_op, session_override=session)


async def delete_project_gpu_quota(
    conn: Any, project_id: str, gpu_type: str, *, session: AsyncSession | None = None
) -> bool:
    """Delete a project GPU quota entry."""
    norm_type = normalize_gpu_alias(gpu_type)
    if not norm_type:
        return False

    async def _op(sess: AsyncSession) -> bool:
        res = await sess.execute(select(GpuQuota).where(GpuQuota.project_id == project_id).with_for_update())
        matches = [row for row in res.scalars().all() if normalize_gpu_alias(row.gpu_type) == norm_type]
        for row in matches:
            await sess.delete(row)
        await sess.commit()
        return bool(matches)

    return await _execute_db_op(_op, session_override=session)


async def get_effective_gpu_quotas(
    conn: Any, project_id: str, *, session: AsyncSession | None = None
) -> dict[str, int]:
    """Get merged effective GPU quotas where project entries override default project baseline."""

    async def _op(sess: AsyncSession) -> dict[str, int]:
        result = await sess.execute(select(GpuQuota).where(GpuQuota.project_id.in_((DEFAULT_PROJECT_ID, project_id))))
        rows_by_project: dict[str, list[GpuQuota]] = {DEFAULT_PROJECT_ID: [], project_id: []}
        for row in result.scalars().all():
            rows_by_project.setdefault(row.project_id, []).append(row)

        defaults = {
            gpu_type: _merge_quota_limits(rows)
            for gpu_type, rows in _normalized_quota_groups(rows_by_project[DEFAULT_PROJECT_ID]).items()
        }
        if project_id == DEFAULT_PROJECT_ID:
            return defaults

        project_quotas = {
            gpu_type: _merge_quota_limits(rows)
            for gpu_type, rows in _normalized_quota_groups(rows_by_project[project_id]).items()
        }
        return {**defaults, **project_quotas}

    return await _execute_db_op(_op, session_override=session)


async def get_effective_gpu_quota_status(
    conn: Any, project_id: str, *, session: AsyncSession | None = None
) -> list[dict[str, Any]]:
    """Return effective limits and current use for a project's GPU aliases."""
    if conn is None:
        raise GpuQuotaUnavailable("GPU quota usage inventory is unavailable")

    effective = await get_effective_gpu_quotas(conn, project_id, session=session)
    usage = await get_project_gpu_usage(conn, project_id)
    return [
        {
            "project_id": project_id,
            "gpu_type": gpu_type,
            "limit": effective.get(gpu_type, 0),
            "in_use": usage.get(gpu_type, 0),
            "available": (
                -1 if effective.get(gpu_type, 0) == -1 else max(0, effective.get(gpu_type, 0) - usage.get(gpu_type, 0))
            ),
        }
        for gpu_type in sorted(set(effective) | set(usage))
    ]


def _get_project_gpu_usage(conn: Any, project_id: str) -> dict[str, int]:
    """Synchronously count active project GPU use from Nova."""
    usage: dict[str, int] = {}
    if not conn:
        return usage

    is_system_admin = getattr(conn, "_afterglow_is_system_admin", False) is True
    try:
        if is_system_admin:
            try:
                servers = conn.compute.servers(details=True, all_projects=True, project_id=project_id)
            except TypeError:
                servers = conn.compute.servers(details=True, all_projects=True)
        else:
            servers = conn.compute.servers(details=True)
    except Exception as exc:
        raise GpuQuotaUnavailable("GPU quota usage inventory is unavailable") from exc

    allowed_statuses = {
        "ACTIVE",
        "BUILD",
        "MIGRATING",
        "PASSWORD",
        "PAUSED",
        "REBUILD",
        "REVERT_RESIZE",
        "RESIZE",
        "SHUTOFF",
        "SUSPENDED",
        "VERIFY_RESIZE",
    }
    flavor_cache: dict[str, dict[str, Any]] = {}

    for s in servers:
        s_proj = getattr(s, "project_id", getattr(s, "tenant_id", None))
        if is_system_admin and not s_proj:
            raise GpuQuotaUnavailable("GPU quota server ownership is unavailable")
        if s_proj and s_proj != project_id:
            continue

        st = (getattr(s, "status", "") or "").upper()
        if st not in allowed_statuses:
            continue

        flavor_info = getattr(s, "flavor", None) or {}
        extra_specs = {}
        flavor_id = None
        embedded_specs_are_authoritative = False

        if isinstance(flavor_info, dict):
            extra_specs = flavor_info.get("extra_specs") or {}
            flavor_id = flavor_info.get("id")
            embedded_specs_are_authoritative = "original_name" in flavor_info and "extra_specs" in flavor_info
        else:
            extra_specs = getattr(flavor_info, "extra_specs", None) or {}
            flavor_id = getattr(flavor_info, "id", None)

        if not extra_specs and flavor_id and not embedded_specs_are_authoritative:
            if flavor_id in flavor_cache:
                extra_specs = flavor_cache[flavor_id]
            else:
                try:
                    fl_obj = conn.compute.get_flavor(flavor_id)
                    fl_specs = getattr(fl_obj, "extra_specs", None) or (
                        fl_obj.get("extra_specs") if isinstance(fl_obj, dict) else {}
                    )
                    extra_specs = dict(fl_specs) if fl_specs else {}
                    flavor_cache[flavor_id] = extra_specs
                except Exception as exc:
                    raise GpuQuotaUnavailable("GPU quota flavor metadata is unavailable") from exc

        alias_str = str(extra_specs.get("pci_passthrough:alias", ""))
        if not alias_str:
            continue

        for entry in alias_str.split(","):
            entry = entry.strip()
            if not entry:
                continue
            if ":" in entry:
                alias_raw, _, count_str = entry.rpartition(":")
                try:
                    count = int(count_str.strip())
                    if count <= 0:
                        count = 1
                except ValueError:
                    count = 1
            else:
                alias_raw = entry
                count = 1

            gpu_type = normalize_gpu_alias(alias_raw)
            if gpu_type:
                usage[gpu_type] = usage.get(gpu_type, 0) + count

    return usage


async def get_project_gpu_usage(conn: Any, project_id: str) -> dict[str, int]:
    """Count GPU use without blocking the application event loop."""
    return await asyncio.to_thread(_get_project_gpu_usage, conn, project_id)


async def check_gpu_quota(
    conn: Any, project_id: str, requested_gpus: dict[str, int], *, session: AsyncSession | None = None
) -> None:
    """Check whether requested GPUs exceed effective project quota limits.

    Raises:
        GpuQuotaDenied: if requested count exceeds available quota.
        GpuQuotaUnavailable: if DB is unavailable.
    """
    if conn is None:
        raise GpuQuotaUnavailable("GPU quota usage inventory is unavailable")
    effective = await get_effective_gpu_quotas(conn, project_id, session=session)
    usage = await get_project_gpu_usage(conn, project_id)

    for raw_alias, req_count in requested_gpus.items():
        if req_count <= 0:
            continue
        gpu_type = normalize_gpu_alias(raw_alias)
        if not gpu_type:
            continue

        limit = effective.get(gpu_type, 0)  # Absent quota is zero / denied
        if limit == -1:
            continue  # Unlimited

        in_use = usage.get(gpu_type, 0)
        if limit == 0 or (in_use + req_count > limit):
            raise GpuQuotaDenied(
                f"GPU quota exceeded for project {project_id} (gpu_type={gpu_type}): "
                f"limit={limit}, in_use={in_use}, requested={req_count}"
            )


async def reserve_gpu_quota(
    conn: Any,
    project_id: str,
    requested_gpus: dict[str, int],
    *,
    ttl_seconds: int = 300,
    session: AsyncSession | None = None,
) -> str | None:
    """Atomically claim limited GPU headroom for one Afterglow admission.

    This coordinates Afterglow-controlled requests only. Direct Nova creates
    do not participate in these reservations.
    """
    if conn is None:
        raise GpuQuotaUnavailable("GPU quota usage inventory is unavailable")
    if session is None and not is_db_available():
        return None
    normalized = {
        gpu_type: int(amount)
        for raw_alias, amount in requested_gpus.items()
        if (gpu_type := normalize_gpu_alias(raw_alias)) and int(amount) > 0
    }
    if not normalized:
        return None
    usage = await get_project_gpu_usage(conn, project_id)
    reservation_id = str(uuid.uuid4())
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=max(30, ttl_seconds))

    async def _op(sess: AsyncSession) -> str | None:
        await sess.execute(delete(GpuQuotaReservation).where(GpuQuotaReservation.expires_at <= now))
        quota_result = await sess.execute(
            select(GpuQuota).where(GpuQuota.project_id.in_((DEFAULT_PROJECT_ID, project_id))).with_for_update()
        )
        quota_rows_by_project: dict[str, list[GpuQuota]] = {DEFAULT_PROJECT_ID: [], project_id: []}
        for row in quota_result.scalars().all():
            quota_rows_by_project.setdefault(row.project_id, []).append(row)
        defaults = {
            gpu_type: _merge_quota_limits(rows)
            for gpu_type, rows in _normalized_quota_groups(quota_rows_by_project[DEFAULT_PROJECT_ID]).items()
            if gpu_type in normalized
        }
        project_limits = {
            gpu_type: _merge_quota_limits(rows)
            for gpu_type, rows in _normalized_quota_groups(quota_rows_by_project[project_id]).items()
            if gpu_type in normalized
        }
        reservation_result = await sess.execute(
            select(GpuQuotaReservation)
            .where(
                GpuQuotaReservation.project_id == project_id,
                GpuQuotaReservation.gpu_type.in_(tuple(normalized)),
                GpuQuotaReservation.status == "pending",
                GpuQuotaReservation.expires_at > now,
            )
            .with_for_update()
        )
        reserved: dict[str, int] = {}
        for row in reservation_result.scalars().all():
            reserved[row.gpu_type] = reserved.get(row.gpu_type, 0) + row.amount

        limited: dict[str, int] = {}
        for gpu_type, requested in normalized.items():
            limit = project_limits.get(gpu_type, defaults.get(gpu_type, 0))
            if limit == -1:
                continue
            in_use = usage.get(gpu_type, 0)
            held = reserved.get(gpu_type, 0)
            if limit == 0 or in_use + held + requested > limit:
                raise GpuQuotaDenied(
                    f"GPU quota exceeded for project {project_id} (gpu_type={gpu_type}): "
                    f"limit={limit}, in_use={in_use}, reserved={held}, requested={requested}"
                )
            limited[gpu_type] = requested

        if not limited:
            await sess.commit()
            return None
        for gpu_type, amount in limited.items():
            sess.add(
                GpuQuotaReservation(
                    reservation_id=reservation_id,
                    project_id=project_id,
                    gpu_type=gpu_type,
                    amount=amount,
                    status="pending",
                    expires_at=expires_at,
                )
            )
        await sess.commit()
        return reservation_id

    return await _execute_db_op(_op, session_override=session)


async def release_gpu_reservation(
    reservation_id: str | None,
    *,
    session: AsyncSession | None = None,
) -> None:
    """Release a completed or failed Afterglow admission claim."""
    if not reservation_id:
        return

    async def _op(sess: AsyncSession) -> None:
        await sess.execute(delete(GpuQuotaReservation).where(GpuQuotaReservation.reservation_id == reservation_id))
        await sess.commit()

    await _execute_db_op(_op, session_override=session)
