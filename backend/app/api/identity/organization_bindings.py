"""System-admin settlement of fenced configured-organization creation intents."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import require_admin
from app.api.identity.iam import IamRoute
from app.services import organization_provisioning
from app.services.domain_auth import DomainAuthError, domain_auth_error_response

router = APIRouter(route_class=IamRoute)
BindingKey = Annotated[str, Path(pattern=r"^[0-9a-f]{64}$")]


class BindingSettlement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent_id: str = Field(min_length=36, max_length=36, strict=True)
    native_calls_settled: bool = Field(strict=True)


@router.get("/organization-bindings")
async def pending(token_info: dict = Depends(require_admin)):
    try:
        return await organization_provisioning.pending_bindings()
    except DomainAuthError as exc:
        return domain_auth_error_response(exc)


@router.post("/organization-bindings/{binding_key}/settle")
async def settle(binding_key: BindingKey, req: BindingSettlement, token_info: dict = Depends(require_admin)):
    try:
        return await organization_provisioning.settle_binding(
            binding_key,
            intent_id=req.intent_id,
            native_calls_settled=req.native_calls_settled,
            actor_user_id=token_info["user_id"],
        )
    except DomainAuthError as exc:
        return domain_auth_error_response(exc)
