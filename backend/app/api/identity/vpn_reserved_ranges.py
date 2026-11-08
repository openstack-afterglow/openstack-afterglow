"""Per-domain VPN reserved ranges: domain managers for their domain, system admins for any."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import get_admin_os_conn, require_admin, require_domain_manager
from app.api.identity.iam import IamRoute
from app.services import vpn_reserved_ranges as svc

router = APIRouter(route_class=IamRoute)


class VpnReservedRangesUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # The service enforces the documented 16-entry limit with a stable code.
    vpn_reserved_cidrs: list[str] = Field(max_length=64)
    revision: int = Field(strict=True, ge=0)


@router.get("/iam/vpn-reserved-ranges")
async def manager_view(token_info: dict = Depends(require_domain_manager)):
    return await svc.policy_view(token_info["domain_id"])


@router.put("/iam/vpn-reserved-ranges")
async def manager_update(req: VpnReservedRangesUpdate, token_info: dict = Depends(require_domain_manager)):
    return await svc.update_policy(
        token_info["domain_id"],
        actor_user_id=token_info["user_id"],
        cidrs=req.vpn_reserved_cidrs,
        expected_revision=req.revision,
    )


async def _existing_domain(conn, domain_id: str) -> None:
    try:
        domain = await asyncio.to_thread(conn.identity.get_domain, domain_id)
    except Exception as exc:
        status = getattr(exc, "status_code", None) or getattr(exc, "http_status", None)
        if status == 404:
            raise HTTPException(404, "domain_not_found") from None
        raise HTTPException(503, "Domain directory is unavailable") from None
    if domain is None:
        raise HTTPException(404, "domain_not_found")
    if getattr(domain, "id", None) != domain_id:
        raise HTTPException(503, "Domain identity cannot be verified")


DomainId = Annotated[str, Path(min_length=1, max_length=64)]


@router.get("/admin/domains/{domain_id}/vpn-reserved-ranges")
async def admin_view(domain_id: DomainId, conn=Depends(get_admin_os_conn)):
    await _existing_domain(conn, domain_id)
    return await svc.policy_view(domain_id)


@router.put("/admin/domains/{domain_id}/vpn-reserved-ranges")
async def admin_update(
    req: VpnReservedRangesUpdate,
    domain_id: DomainId,
    token_info: dict = Depends(require_admin),
    conn=Depends(get_admin_os_conn),
):
    await _existing_domain(conn, domain_id)
    return await svc.update_policy(
        domain_id, actor_user_id=token_info["user_id"], cidrs=req.vpn_reserved_cidrs, expected_revision=req.revision
    )
