"""Admin orphan resource detection API.

운영 중 단계적 실패로 누적되는 고아 리소스를 한 화면에서 검색하고 안전하게
일괄 정리한다. 모든 작업은 admin 전용.

지원 종류:
  - floating_ip   : port_id NULL FIP
  - volume        : status=available + attachments=[] + age >= min_age_days
  - manila_share  : project가 Keystone에서 사라진 share (snapshot 보호)
  - security_group: afterglow description marker 부여 + port attach 0건 SG
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Query

from app.api.common.activity_recorder import rec
from app.api.deps import get_admin_os_conn, get_token_info, require_admin
from app.models.orphans import (
    OrphanCleanupRequest,
    OrphanCleanupResponse,
    OrphanScanResponse,
)
from app.services import orphans

if TYPE_CHECKING:
    import openstack

_logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/orphans",
    response_model=OrphanScanResponse,
    dependencies=[Depends(require_admin)],
)
async def list_orphans(
    min_age_days: int = Query(14, ge=1, le=365),
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
) -> OrphanScanResponse:
    """admin 전(全) 프로젝트 범위에서 orphan 후보를 반환."""
    return OrphanScanResponse(
        floating_ips=orphans.find_orphan_floating_ips(conn),
        volumes=orphans.find_orphan_volumes(conn, min_age_days),
        manila_shares=orphans.find_orphan_manila_shares(conn),
        security_groups=orphans.find_orphan_security_groups(conn),
    )


@router.post(
    "/orphans/cleanup",
    response_model=OrphanCleanupResponse,
    dependencies=[Depends(require_admin)],
)
async def cleanup_orphans(
    req: OrphanCleanupRequest,
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
    token_info: dict = Depends(get_token_info),
) -> OrphanCleanupResponse:
    """주어진 ID 목록을 일괄 정리. race-safe 검증 + 각 결과를 audit log 기록."""
    if req.kind == "floating_ip":
        deleted, failed = orphans.cleanup_floating_ips(conn, req.ids)
    elif req.kind == "volume":
        deleted, failed = orphans.cleanup_volumes(conn, req.ids)
    elif req.kind == "manila_share":
        deleted, failed = orphans.cleanup_manila_shares(conn, req.ids)
    else:  # "security_group"
        deleted, failed = orphans.cleanup_security_groups(conn, req.ids)

    for rid in deleted:
        await rec(
            token_info,
            conn,
            resource_type=req.kind,
            action="orphan.cleanup",
            resource_id=rid,
            status="success",
        )
    for f in failed:
        await rec(
            token_info,
            conn,
            resource_type=req.kind,
            action="orphan.cleanup",
            resource_id=f.get("id"),
            status="failed",
            error_message=f.get("error"),
        )

    return OrphanCleanupResponse(deleted=deleted, failed=failed)
