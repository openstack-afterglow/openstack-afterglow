"""System-administrator tenant domain inventory, monitoring and manager bootstrap.

Mount under /api/v1/admin. Every route requires a verified system:all admin.
Keystone domain IDs are the isolation boundary; names are display metadata.
"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common.errors import public_service_error
from app.api.deps import get_os_conn, get_token_info, require_admin
from app.database import get_session
from app.services import (
    account_spaces,
    activity,
    domain_display,
    domain_iam,
    domain_monitoring,
    domain_projects,
    identity_roles,
    keystone,
    project_ownership_journal,
    project_service,
)
from app.services.domain_scope import invalidate_authority
from app.services.login_monitoring import Window

router = APIRouter(dependencies=[Depends(require_admin)])


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, HTTPException):
        return exc
    status = getattr(exc, "status_code", None) or getattr(exc, "http_status", None)
    if status in (401, 403):
        return HTTPException(403, "domain_native_denied")
    if status == 404:
        return HTTPException(404, "domain_not_found")
    if status == 409:
        return HTTPException(409, "domain_conflict")
    if status in (400, 422):
        return HTTPException(status, "domain_native_invalid")
    return public_service_error(503, "domain_unavailable")


async def _native(call, *args):
    try:
        return await asyncio.to_thread(call, *args)
    except Exception as exc:
        raise _error(exc) from exc


def _domain(row) -> dict:
    return {
        "kind": account_spaces.domain_kind(row),
        "id": row.id,
        "name": domain_display.display_name(row),
        "enabled": identity_roles._field(row, "enabled", identity_roles._field(row, "is_enabled")) is True,
        "description": getattr(row, "description", "") or "",
    }


def _exact_domain(conn, domain_id: str):
    domain = conn.identity.get_domain(domain_id)
    if domain is None:
        raise HTTPException(404, "domain_not_found")
    if getattr(domain, "id", None) != domain_id:
        raise public_service_error(503, "domain_unavailable")
    return domain


class CreateDomainRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=4096)
    enabled: bool = True


class UpdateDomainRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=4096)
    enabled: bool | None = None


class ManagerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    user_id: str = Field(min_length=1, max_length=255)
    role_id: str = Field(min_length=1, max_length=255)


class BootstrapDefaultRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    creator_id: str = Field(min_length=1, max_length=255)


async def _audit(token_info: dict, action: str, domain_id: str, **extra):
    await activity.record(
        project_id="",
        user_id=token_info["user_id"],
        username=token_info.get("username", ""),
        resource_type="domain",
        action=action,
        status="success",
        resource_id=domain_id,
        service="keystone",
        extra={"domain_id": domain_id, **extra},
    )


@router.get("/domains")
async def list_domains(conn=Depends(get_os_conn)):
    def fetch():
        return {"items": sorted((_domain(d) for d in conn.identity.domains()), key=lambda d: (d["name"], d["id"]))}

    return await _native(fetch)


@router.get("/domains/{domain_id}/members")
async def list_domain_members(domain_id: str, response: Response):
    """Membership candidates only; never widen home-domain credential administration."""
    response.headers["Cache-Control"] = "no-store, private"
    try:
        users = await domain_iam.directory_users(domain_id)
        return {
            "domain_id": domain_id,
            "items": [
                {key: value for key, value in domain_iam.user_dto(user).items() if key != "protected"}
                for user in users
                if identity_roles._field(user, "enabled") is True
            ],
        }
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/domains", status_code=201)
async def create_domain(req: CreateDomainRequest, conn=Depends(get_os_conn), token_info=Depends(get_token_info)):
    result = await domain_projects.create_domain(
        name=req.name, description=req.description, enabled=req.enabled, creator_id=token_info["user_id"]
    )
    await _audit(token_info, "domain.create", result["id"], name=result["name"])
    return result


@router.post("/domains/{domain_id}/default", status_code=201)
async def bootstrap_domain_default(domain_id: str, req: BootstrapDefaultRequest, token_info=Depends(get_token_info)):
    result = await domain_projects.bootstrap_default(domain_id, creator_id=req.creator_id)
    await _audit(token_info, "domain.default.bootstrap", domain_id, creator_id=req.creator_id)
    return result


@router.patch("/domains/{domain_id}")
@identity_roles._complete_mutation
async def update_domain(
    domain_id: str, req: UpdateDomainRequest, conn=Depends(get_os_conn), token_info=Depends(get_token_info)
):
    attrs = req.model_dump(exclude_unset=True, exclude_none=True)
    if not attrs:
        raise HTTPException(422, "domain_invalid_input")
    if "enabled" in attrs:
        attrs["is_enabled"] = attrs.pop("enabled")
    if "name" in attrs:
        attrs[domain_display.DISPLAY_ATTRIBUTE] = domain_display.validate_name(attrs.pop("name"))

    def update():
        original = ks.domains.get(domain_id)
        if identity_roles._field(original, "id") != domain_id:
            raise public_service_error(503, "domain_unavailable")
        native_name = identity_roles._field(original, "name")
        native_attrs = {("enabled" if key == "is_enabled" else key): value for key, value in attrs.items()}
        updated = ks.domains.update(domain_id, **native_attrs)
        if identity_roles._field(updated, "id") != domain_id:
            raise public_service_error(503, "domain_unavailable")
        checked = ks.domains.get(domain_id)
        if identity_roles._field(checked, "id") != domain_id:
            raise public_service_error(503, "domain_unavailable")
        if identity_roles._field(checked, "name") != native_name:
            raise public_service_error(503, "domain_native_identity_changed")
        if (
            domain_display.DISPLAY_ATTRIBUTE in attrs
            and domain_display.display_name(checked) != attrs[domain_display.DISPLAY_ATTRIBUTE]
        ):
            raise public_service_error(503, "domain_display_update_unavailable")
        return _domain(checked)

    async with identity_roles._graph_lock(conn) as lease:
        domain = await _native(lambda: _exact_domain(conn, domain_id))
        from app.services.account_spaces import domain_kind

        if domain_kind(domain) in {"account", "personal"}:
            raise HTTPException(403, "shared_domain_is_managed")
        ks = await _native(keystone._get_admin_ks_client)
        catalog = await _native(identity_roles.load_catalog, conn)
        affected = set()
        if attrs.get("is_enabled") is False:
            await project_ownership_journal.assert_domain_resolved(domain_id)
            await _native(lambda: identity_roles.assert_system_admin_remains(domain_id=domain_id))
            users = await _native(lambda: list(ks.users.list(domain=domain_id)))
            for user in users:
                uid = identity_roles._field(user, "id")
                if not isinstance(uid, str) or not uid or identity_roles._field(user, "domain_id") != domain_id:
                    raise public_service_error(503, "domain_unavailable")
                await project_ownership_journal.assert_user_resolved(uid)
                await _native(lambda uid=uid: project_service.assert_user_ownership_mutation_safe(uid, ks=ks))
            affected = await _native(
                lambda: domain_projects.assert_managers_remain(ks=ks, catalog=catalog, disabled_domain_id=domain_id)
            )
        elif attrs.get("is_enabled") is True:
            affected = await _native(
                lambda: domain_projects.assert_managers_remain(ks=ks, catalog=catalog, changed_domain_id=domain_id)
            )
            if await _native(lambda: domain_projects.default_project(domain_id, ks=ks)) is not None:
                affected.add(domain_id)
        try:
            result = await identity_roles._write(lease, update)
        finally:
            try:
                for affected_domain in sorted(affected):
                    await domain_projects.sync_manager_access(affected_domain, mutation=(lease, ks, catalog))
            finally:
                # A lost native reply does not prove that enablement stayed unchanged.
                await invalidate_authority()
    await _audit(token_info, "domain.update", domain_id, fields=sorted(attrs))
    return result


@router.get("/domains/{domain_id}/monitoring")
async def domain_monitoring_snapshot(domain_id: str, window: Window = Query("24h"), conn=Depends(get_os_conn)):
    return await domain_monitoring.snapshot(conn, domain_id, window)


def _managers(conn, domain_id: str) -> dict:
    _exact_domain(conn, domain_id)
    return domain_projects.managers(domain_id)


@router.get("/domains/{domain_id}/managers")
async def list_domain_managers(domain_id: str, conn=Depends(get_os_conn)):
    return await _native(_managers, conn, domain_id)


@router.post("/domains/{domain_id}/managers", status_code=201)
async def grant_domain_manager(
    domain_id: str, req: ManagerRequest, conn=Depends(get_os_conn), token_info=Depends(get_token_info)
):
    await domain_projects.change_manager(domain_id, req.user_id, req.role_id, remove=False, actor=token_info)
    await _audit(token_info, "domain.manager.grant", domain_id, target_user_id=req.user_id, role_id=req.role_id)
    return await list_domain_managers(domain_id, conn)


@router.delete("/domains/{domain_id}/managers", status_code=204)
async def revoke_domain_manager(
    domain_id: str,
    user_id: str = Query(..., min_length=1),
    role_id: str = Query(..., min_length=1),
    conn=Depends(get_os_conn),
    token_info=Depends(get_token_info),
):
    await domain_projects.change_manager(domain_id, user_id, role_id, remove=True, actor=token_info)
    await _audit(token_info, "domain.manager.revoke", domain_id, target_user_id=user_id, role_id=role_id)


@router.get("/domains/{domain_id}/enrollment-operations")
async def list_domain_enrollment_operations(
    domain_id: str, token_info=Depends(get_token_info), session: AsyncSession = Depends(get_session)
):
    return await domain_iam.list_invitations(token_info, session, operations=True, system_domain_id=domain_id)


@router.delete("/domains/{domain_id}/enrollment-operations/{operation_id}", status_code=204)
async def revoke_domain_enrollment_operation(
    domain_id: str, operation_id: str, token_info=Depends(get_token_info), session: AsyncSession = Depends(get_session)
):
    await domain_iam.revoke(operation_id, token_info, session, operation=True, system_domain_id=domain_id)


class EnrollmentSettlementRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    native_writes_settled: StrictBool


@router.post("/domains/{domain_id}/enrollment-operations/{operation_id}/reconcile")
async def settle_domain_enrollment_operation(
    domain_id: str,
    operation_id: str,
    req: EnrollmentSettlementRequest,
    token_info=Depends(get_token_info),
    session: AsyncSession = Depends(get_session),
):
    return await domain_iam.settle_enrollment_native_writes(
        operation_id, token_info, session, domain_id=domain_id, native_writes_settled=req.native_writes_settled
    )
