"""Domain-manager allocations and explicit system-admin budget ceilings."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_admin_os_conn, require_admin, require_domain_manager
from app.api.identity.iam import IamRoute
from app.models.domain_quotas import DefaultsUpdate, OperationReconcile, PolicyUpdate, ProjectQuotaUpdate
from app.services import domain_monitoring, domain_quotas, quota_native

router = APIRouter(route_class=IamRoute)


@router.get("/iam/quotas")
async def domain_quotas_snapshot(token_info: dict = Depends(require_domain_manager)):
    async with domain_quotas.manager_connection(token_info) as (conn, domain_id):
        return await domain_quotas.snapshot(conn, domain_id)


@router.put("/iam/quotas/defaults")
async def set_project_defaults(req: DefaultsUpdate, token_info: dict = Depends(require_domain_manager)):
    async with domain_quotas.manager_connection(token_info) as (conn, domain_id):
        return await domain_quotas.update_policy(
            conn, domain_id, req.revision, req.defaults, defaults=True, token_info=token_info
        )


async def _exact_project(conn, domain_id, project_id):
    if await domain_quotas.project_domain(conn, project_id) != domain_id:
        raise HTTPException(403, "quota_project_domain_mismatch")


@router.get("/iam/projects/{project_id}/quotas")
async def project_quotas(project_id: str, token_info: dict = Depends(require_domain_manager)):
    async with domain_quotas.manager_connection(token_info) as (conn, domain_id):
        await _exact_project(conn, domain_id, project_id)
        return await quota_native.read_project(conn, project_id)


@router.put("/iam/projects/{project_id}/quotas")
async def set_project_quotas(
    project_id: str, req: ProjectQuotaUpdate, token_info: dict = Depends(require_domain_manager)
):
    async with domain_quotas.manager_connection(token_info) as (conn, domain_id):
        return await domain_quotas.update_project(
            conn, project_id, req.limits(), domain_id=domain_id, token_info=token_info
        )


@router.get("/iam/monitoring")
async def monitoring(token_info: dict = Depends(require_domain_manager)):
    async with domain_quotas.manager_connection(token_info) as (conn, domain_id):
        return await domain_monitoring.manager_workspace(conn, domain_id)


@router.get("/admin/domains/{domain_id}/quotas", dependencies=[Depends(require_admin)])
async def admin_domain_quotas(domain_id: str, conn=Depends(get_admin_os_conn)):
    return await domain_quotas.snapshot(conn, domain_id)


@router.put("/admin/domains/{domain_id}/quotas", dependencies=[Depends(require_admin)])
async def set_domain_ceiling(domain_id: str, req: PolicyUpdate, conn=Depends(get_admin_os_conn)):
    return await domain_quotas.update_policy(conn, domain_id, req.revision, req.ceilings)


@router.post(
    "/admin/domains/{domain_id}/quotas/operations/{operation_id}/reconcile", dependencies=[Depends(require_admin)]
)
async def reconcile_native_operation(
    domain_id: str, operation_id: str, req: OperationReconcile, conn=Depends(get_admin_os_conn)
):
    if not req.native_calls_settled:
        raise HTTPException(422, "quota_native_settlement_confirmation_required")
    return await domain_quotas.reconcile_operation(conn, domain_id, operation_id)
