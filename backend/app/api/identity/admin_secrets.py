from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.common.admin_resource_scope import AdminResourceScope, admin_resource_scope
from app.api.deps import require_admin
from app.models.barbican import ProjectQuotaSetRequest
from app.rate_limit import limiter
from app.services import barbican as bsvc
from app.services.keystone import get_admin_project_connection

_logger = logging.getLogger(__name__)

router = APIRouter()


def _barbican_error(e: Exception, detail: str) -> HTTPException:
    http_status = getattr(e, "http_status", None) or getattr(getattr(e, "response", None), "status_code", None)
    if http_status == 403:
        return HTTPException(
            status_code=500,
            detail="Barbican에서 권한 거부됐습니다. OpenStack admin 사용자에게 key-manager:service-admin role을 부여하세요.",
        )
    return HTTPException(status_code=500, detail=f"{detail}: {e}")


@router.get("/key-manager/project-quotas", dependencies=[Depends(require_admin)])
async def list_project_quotas(scope: AdminResourceScope = Depends(admin_resource_scope)):
    conn = await asyncio.to_thread(get_admin_project_connection)
    try:
        return scope.filter(await asyncio.to_thread(bsvc.list_project_quotas, conn))
    except Exception as e:
        _logger.exception("Barbican project-quotas 조회 실패: %s", e)
        http_status = getattr(e, "http_status", None) or getattr(getattr(e, "response", None), "status_code", None)
        if http_status == 404:
            return []
        raise _barbican_error(e, "프로젝트 쿼터 목록 조회 실패")
    finally:
        await asyncio.to_thread(conn.close)


@router.get("/key-manager/project-quotas/{project_id}", dependencies=[Depends(require_admin)])
async def get_project_quota(project_id: str):
    conn = await asyncio.to_thread(get_admin_project_connection)
    try:
        return await asyncio.to_thread(bsvc.get_project_quota, conn, project_id)
    except Exception as e:
        _logger.exception("Barbican project-quota 조회 실패: %s", e)
        raise _barbican_error(e, "프로젝트 쿼터 조회 실패")
    finally:
        await asyncio.to_thread(conn.close)


@router.put("/key-manager/project-quotas/{project_id}", dependencies=[Depends(require_admin)])
@limiter.limit("30/minute")
async def set_project_quota(request: Request, project_id: str, req: ProjectQuotaSetRequest):
    quotas = {k: v for k, v in req.model_dump().items() if v is not None}
    if not quotas:
        raise HTTPException(status_code=422, detail="설정할 쿼터 값이 없습니다")
    conn = await asyncio.to_thread(get_admin_project_connection)
    try:
        return await asyncio.to_thread(bsvc.set_project_quota, conn, project_id, quotas)
    except Exception as e:
        _logger.exception("Barbican project-quota 설정 실패: %s", e)
        raise _barbican_error(e, "프로젝트 쿼터 설정 실패")
    finally:
        await asyncio.to_thread(conn.close)


@router.delete(
    "/key-manager/project-quotas/{project_id}",
    status_code=204,
    dependencies=[Depends(require_admin)],
)
@limiter.limit("30/minute")
async def delete_project_quota(request: Request, project_id: str):
    conn = await asyncio.to_thread(get_admin_project_connection)
    try:
        await asyncio.to_thread(bsvc.delete_project_quota, conn, project_id)
    except Exception as e:
        _logger.exception("Barbican project-quota 초기화 실패: %s", e)
        raise _barbican_error(e, "프로젝트 쿼터 초기화 실패")
    finally:
        await asyncio.to_thread(conn.close)
