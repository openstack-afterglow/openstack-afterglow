"""Exact-domain manager requests and system-admin manual review."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Query

from app.api.deps import require_admin, require_domain_manager
from app.api.identity.iam import IamRoute
from app.models.gpu_quota_requests import CreateGpuQuotaRequest, ResolveGpuQuotaRequest
from app.services import gpu_quota_requests

router = APIRouter(route_class=IamRoute)
RequestId = Annotated[str, Path(pattern=r"^[0-9a-f]{32}$", min_length=32, max_length=32)]
Cursor = Annotated[str | None, Query(pattern=r"^[0-9a-f]{32}$", min_length=32, max_length=32)]
Status = Literal["pending", "fulfilled", "rejected", "all"]


@router.post("/iam/gpu-quota-requests", status_code=201)
async def create_request(req: CreateGpuQuotaRequest, token_info: dict = Depends(require_domain_manager)):
    return await gpu_quota_requests.create(token_info, req)


@router.get("/iam/gpu-quota-requests")
async def manager_requests(
    status: Status = "pending",
    cursor: Cursor = None,
    token_info: dict = Depends(require_domain_manager),
):
    return await gpu_quota_requests.list_requests(token_info, status=status, cursor=cursor)


@router.get("/admin/gpu-quota-requests")
async def admin_requests(
    status: Status = "pending",
    cursor: Cursor = None,
    token_info: dict = Depends(require_admin),
):
    return await gpu_quota_requests.list_requests(token_info, system=True, status=status, cursor=cursor)


@router.post("/admin/gpu-quota-requests/{request_id}/resolve")
async def resolve_request(
    request_id: RequestId,
    req: ResolveGpuQuotaRequest,
    token_info: dict = Depends(require_admin),
):
    return await gpu_quota_requests.resolve(token_info, request_id, req)
