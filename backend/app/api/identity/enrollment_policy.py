"""System-admin-only enrollment policy and bounded, secret-free review queue."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import get_os_conn, require_admin
from app.api.identity.iam import IamRoute
from app.models.enrollment_policy import EnrollmentPolicyUpdate
from app.services import enrollment_policy

router = APIRouter(route_class=IamRoute)
RequestId = Annotated[str, Path(min_length=36, max_length=36)]


@router.get("/enrollment-policy")
async def policy(token_info: dict = Depends(require_admin)):
    return await enrollment_policy.read_policy()


@router.put("/enrollment-policy")
async def update_policy(
    req: EnrollmentPolicyUpdate,
    token_info: dict = Depends(require_admin),
    conn=Depends(get_os_conn),
):
    return await enrollment_policy.update_policy(conn, req.model_dump(), token_info=token_info)


class PersonalQuotaApply(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preview_id: str = Field(pattern=r"^[a-f0-9]{64}$")


@router.get("/personal-project-quotas")
async def personal_projects(
    cursor: str | None = Query(None, min_length=1, max_length=64),
    token_info: dict = Depends(require_admin),
):
    return await enrollment_policy.personal_quota_projects(token_info, cursor=cursor)


@router.get("/personal-project-quotas/{project_id}/preview")
async def preview_personal_project(
    project_id: str = Path(min_length=1, max_length=64),
    token_info: dict = Depends(require_admin),
    conn=Depends(get_os_conn),
):
    return await enrollment_policy.preview_personal_quotas(conn, project_id, token_info)


@router.post("/personal-project-quotas/{project_id}/apply")
async def apply_personal_project(
    req: PersonalQuotaApply,
    project_id: str = Path(min_length=1, max_length=64),
    token_info: dict = Depends(require_admin),
    conn=Depends(get_os_conn),
):
    return await enrollment_policy.converge_personal_quotas(conn, project_id, token_info, req.preview_id)


@router.get("/signup-requests")
async def requests(
    status: Literal["pending", "approved", "rejected", "all"] = Query("pending"),
    cursor: str | None = Query(None, min_length=36, max_length=36),
    token_info: dict = Depends(require_admin),
):
    return await enrollment_policy.list_requests(status=status, cursor=cursor)


@router.post("/signup-requests/{request_id}/approve")
async def approve(
    request_id: RequestId,
    token_info: dict = Depends(require_admin),
    conn=Depends(get_os_conn),
):
    return await enrollment_policy.review_request(conn, request_id, "approved", token_info=token_info)


@router.post("/signup-requests/{request_id}/reject")
async def reject(
    request_id: RequestId,
    token_info: dict = Depends(require_admin),
    conn=Depends(get_os_conn),
):
    return await enrollment_policy.review_request(conn, request_id, "rejected", token_info=token_info)
