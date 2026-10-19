"""Durable automatic Cinder snapshots in a separate provider and journal lane.

Only the snapshot lane's explicit ownership metadata authorizes reconciliation
or retention. Manual snapshots and all backup resources remain outside it.
"""

from datetime import datetime

from app.services import auto_backup as engine

PolicySettings = engine.PolicySettings
_PREFIX = "afterglow:auto_snapshot"
_ALL_KEY = f"{_PREFIX}:all_configs"


def _binding():
    return engine.using_engine(engine.RecoveryPointEngine(_PREFIX, "snapshot"))


def _key(kind: str, project_id: str, volume_id: str) -> str:
    return f"{_PREFIX}:{kind}:{project_id}:{volume_id}"


def build_policy(project_id: str, volume_id: str, *, now: datetime | None = None, **settings) -> dict:
    with _binding():
        return engine.build_policy(project_id, volume_id, now=now, **settings)


async def get_auto_snapshot_config(project_id: str, volume_id: str, *, now: datetime | None = None) -> dict | None:
    with _binding():
        return await engine.get_auto_backup_config(project_id, volume_id, now=now)


async def enable_auto_snapshot(
    project_id: str,
    volume_id: str,
    max_daily: int = 2,
    max_weekly: int = 2,
    max_monthly: int = 1,
    **settings,
) -> dict:
    with _binding():
        return await engine.enable_auto_backup(project_id, volume_id, max_daily, max_weekly, max_monthly, **settings)


async def disable_auto_snapshot(project_id: str, volume_id: str) -> None:
    with _binding():
        await engine.disable_auto_backup(project_id, volume_id)


async def list_auto_snapshot_configs(project_id: str) -> list[dict]:
    with _binding():
        return await engine.list_auto_backup_configs(project_id)


async def run_snapshot_cycle(conn, project_id: str, volume_id: str, *, now: datetime | None = None) -> None:
    with _binding():
        await engine.run_backup_cycle(conn, project_id, volume_id, now=now)


async def scheduler_tick(*, now: datetime | None = None, connection_factory=None, dispatcher=None) -> None:
    with _binding():
        await engine.scheduler_tick(now=now, connection_factory=connection_factory, dispatcher=dispatcher)


async def scheduler_loop() -> None:
    with _binding():
        await engine.scheduler_loop()
