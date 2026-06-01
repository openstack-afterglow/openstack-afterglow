from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import openstack

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import get_os_conn, get_token_info, require_admin
from app.models.barbican import ProjectQuotaSetRequest
from app.rate_limit import limiter
from app.services import barbican as bsvc

router = APIRouter()


@router.get("/key-manager/project-quotas", dependencies=[Depends(require_admin)])
async def list_project_quotas(
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    try:
        return await asyncio.to_thread(bsvc.list_project_quotas, conn)
    except Exception:
        raise HTTPException(status_code=500, detail="프로젝트 쿼터 목록 조회 실패")


@router.get("/key-manager/project-quotas/{project_id}", dependencies=[Depends(require_admin)])
async def get_project_quota(
    project_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    try:
        return await asyncio.to_thread(bsvc.get_project_quota, conn, project_id)
    except Exception:
        raise HTTPException(status_code=500, detail="프로젝트 쿼터 조회 실패")


@router.put("/key-manager/project-quotas/{project_id}", dependencies=[Depends(require_admin)])
@limiter.limit("30/minute")
async def set_project_quota(
    request: Request,
    project_id: str,
    req: ProjectQuotaSetRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    quotas = {k: v for k, v in req.model_dump().items() if v is not None}
    if not quotas:
        raise HTTPException(status_code=422, detail="설정할 쿼터 값이 없습니다")
    try:
        return await asyncio.to_thread(bsvc.set_project_quota, conn, project_id, quotas)
    except Exception:
        raise HTTPException(status_code=500, detail="프로젝트 쿼터 설정 실패")


@router.delete("/key-manager/project-quotas/{project_id}", status_code=204,
               dependencies=[Depends(require_admin)])
@limiter.limit("30/minute")
async def delete_project_quota(
    request: Request,
    project_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    try:
        await asyncio.to_thread(bsvc.delete_project_quota, conn, project_id)
    except Exception:
        raise HTTPException(status_code=500, detail="프로젝트 쿼터 초기화 실패")
