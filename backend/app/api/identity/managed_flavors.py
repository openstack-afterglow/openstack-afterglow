"""Fresh system administrator controls for opt-in managed Nova flavors."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from app.api.deps import get_admin_os_conn, get_token_info, require_admin
from app.services import managed_flavors

if TYPE_CHECKING:
    import openstack

router = APIRouter()


class FlavorAutomationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    revision: int = Field(ge=0)
    enabled: StrictBool


@router.get("/admin/flavor-automation", dependencies=[Depends(require_admin)])
async def get_flavor_automation():
    return await managed_flavors.status()


@router.put("/admin/flavor-automation", dependencies=[Depends(require_admin)])
async def put_flavor_automation(
    req: FlavorAutomationRequest,
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
    token_info: dict = Depends(get_token_info),
):
    return await managed_flavors.configure(
        conn, revision=req.revision, enabled=req.enabled, user_id=token_info["user_id"]
    )


@router.post("/admin/flavor-automation/reconcile", dependencies=[Depends(require_admin)])
async def reconcile_flavor_automation(
    conn: openstack.connection.Connection = Depends(get_admin_os_conn),
):
    return await managed_flavors.reconcile(conn)
