"""프로젝트별 기본 네트워크 관리 서비스.

DB + Neutron을 결합한 비동기 함수 모음.
- ensure_default_network: DB 조회 → Neutron 조회/생성 → DB 기록
- get_default_network_id: DB에서 빠른 network_id 조회
- set_default_network: 사용자 지정 기본 네트워크 저장
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import openstack

from app.api.common.errors import public_service_error
from app.database import get_session_factory, is_db_available
from app.models.storage import NetworkInfo

_logger = logging.getLogger(__name__)


async def ensure_default_network(
    conn: openstack.connection.Connection,
    project_id: str,
    external_network_id: str,
    cidr: str = "192.168.0.0/24",
) -> NetworkInfo:
    """Return the persisted project network or provision one with an exact edge.

    A stale project record is actionable: it is not silently replaced by a
    different network during a provisioning request.
    """
    from app.services.neutron import _net_to_info, provision_default_network

    row = await _db_get(project_id)
    if row:
        network_id = row["network_id"]
        network = await asyncio.to_thread(conn.network.get_network, network_id)
        if network is None:
            raise RuntimeError("persisted project default network is unavailable")
        return _net_to_info(network)

    net_id, subnet_id, router_id, newly_created = await asyncio.to_thread(
        provision_default_network, conn, project_id, external_network_id, cidr
    )

    # ── 3. DB 기록 ────────────────────────────────────────────────────────────
    await _db_upsert(project_id, net_id, subnet_id, router_id, auto_created=newly_created)

    n = await asyncio.to_thread(conn.network.get_network, net_id)
    from app.services.neutron import _net_to_info

    return _net_to_info(n)


async def get_default_network_id(project_id: str) -> str | None:
    """DB에서 프로젝트의 Default 네트워크 ID를 조회한다."""
    row = await _db_get(project_id)
    return row["network_id"] if row else None


async def set_default_network(
    project_id: str,
    network_id: str,
    subnet_id: str | None = None,
) -> None:
    """사용자가 지정한 네트워크를 프로젝트의 Default 네트워크로 저장한다."""
    await _db_upsert(project_id, network_id, subnet_id, None, auto_created=False)


async def get_default_network_record(project_id: str) -> dict | None:
    """DB 레코드 전체를 반환 (API 응답용)."""
    return await _db_get(project_id)


# ---------------------------------------------------------------------------
# DB 헬퍼
# ---------------------------------------------------------------------------


async def _db_get(project_id: str) -> dict | None:
    if not is_db_available():
        raise public_service_error(503, "default_network_storage_unavailable")
    factory = get_session_factory()
    if factory is None:
        raise public_service_error(503, "default_network_storage_unavailable")

    from sqlalchemy import select

    from app.models.db import ProjectDefaultNetwork

    try:
        async with factory() as session:
            result = await session.execute(
                select(ProjectDefaultNetwork).where(ProjectDefaultNetwork.project_id == project_id)
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return {
                "project_id": row.project_id,
                "network_id": row.network_id,
                "subnet_id": row.subnet_id,
                "router_id": row.router_id,
                "auto_created": row.auto_created,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
    except Exception as exc:
        _logger.warning("DB Default 네트워크 조회 실패", exc_info=True)
        raise public_service_error(503, "default_network_storage_unavailable") from exc


async def _db_upsert(
    project_id: str,
    network_id: str,
    subnet_id: str | None,
    router_id: str | None,
    auto_created: bool,
) -> None:
    if not is_db_available():
        return
    factory = get_session_factory()
    if not factory:
        return

    from sqlalchemy import select

    from app.models.db import ProjectDefaultNetwork

    try:
        async with factory() as session:
            result = await session.execute(
                select(ProjectDefaultNetwork).where(ProjectDefaultNetwork.project_id == project_id)
            )
            row = result.scalar_one_or_none()
            now = datetime.now(UTC)
            if row:
                row.network_id = network_id
                row.subnet_id = subnet_id
                row.router_id = router_id
                row.auto_created = auto_created
                row.updated_at = now
            else:
                row = ProjectDefaultNetwork(
                    project_id=project_id,
                    network_id=network_id,
                    subnet_id=subnet_id,
                    router_id=router_id,
                    auto_created=auto_created,
                    created_at=now,
                )
                session.add(row)
            await session.commit()
    except Exception:
        _logger.warning("DB Default 네트워크 기록 실패 (non-critical)", exc_info=True)
