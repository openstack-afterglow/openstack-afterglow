"""Native schedules and durable, domain-governed extension approvals."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from openstack.exceptions import HttpException, ResourceNotFound

from app.api.common.activity_recorder import rec
from app.api.deps import (
    get_admin_os_conn,
    get_os_conn,
    get_os_conn_write,
    get_token_info,
    require_admin,
    require_project_write,
)
from app.models.instance_usage import UsageScheduleExtension, UsageScheduleInfo, UsageScheduleUpdate
from app.models.instance_usage_governance import UsageExtensionReview, UsagePolicyUpdate
from app.services import instance_usage as usage
from app.services import instance_usage_governance as governance
from app.services.cache import invalidate
from app.services.waygate_managed import ensure_server_not_waygate_managed


def _private(response: Response):
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(dependencies=[Depends(_private)])
admin_router = APIRouter(dependencies=[Depends(require_admin), Depends(_private)])


async def get_governance_conn(token_info: dict = Depends(get_token_info)):
    """Fixed read executor; scoped native authority is proven by each handler."""
    from app.services import keystone

    conn = await governance.project_service._provider_call(keystone.get_admin_project_connection)
    conn._afterglow_project_id = token_info.get("project_id") or ""
    try:
        yield conn
    finally:
        await usage.sdk_call(conn.close)


def _field(resource, key):
    return resource.get(key) if isinstance(resource, dict) else getattr(resource, key, None)


async def read_server(conn, instance_id: str, *, project_scoped: bool = True):
    try:
        server = await usage.sdk_call(usage.safe_compute_proxy(conn).get_server, instance_id)
    except ResourceNotFound as exc:
        raise HTTPException(404, "인스턴스를 찾을 수 없습니다") from exc
    except HttpException as exc:
        raise HTTPException(403 if exc.status_code == 403 else 502, "인스턴스 일정을 조회할 수 없습니다") from exc
    except Exception as exc:
        raise HTTPException(502, "인스턴스 일정을 조회할 수 없습니다") from exc
    if server is None:
        raise HTTPException(404, "인스턴스를 찾을 수 없습니다")
    if _field(server, "id") != instance_id:
        raise HTTPException(502, "인스턴스 식별자를 확인할 수 없습니다")
    owners = [_field(server, key) for key in ("project_id", "tenant_id")]
    owners = [owner for owner in owners if owner is not None and owner != ""]
    if not owners or any(not isinstance(owner, str) for owner in owners) or len(set(owners)) != 1:
        raise HTTPException(502, "인스턴스 소유 프로젝트를 확인할 수 없습니다")
    if project_scoped:
        if owners[0] != getattr(conn, "_afterglow_project_id", None):
            raise HTTPException(404, "인스턴스를 찾을 수 없습니다")
        usage.require_server_scope(conn, server, instance_id=instance_id)
    return server


@router.get("/usage-schedules")
async def list_usage_schedules(conn=Depends(get_os_conn)):
    """Read current native metadata, including explicit per-instance parse errors."""
    try:
        servers = await usage.sdk_call(lambda: list(usage.safe_compute_proxy(conn).servers(details=True)))
    except Exception as exc:
        raise HTTPException(502, "인스턴스 일정 목록을 조회할 수 없습니다") from exc
    schedules, errors = [], []
    for server in servers:
        usage.require_server_scope(conn, server)
        try:
            schedule = usage.parse_schedule(server)
        except HTTPException:
            errors.append(
                {
                    "instance_id": _field(server, "id"),
                    "instance_name": _field(server, "name"),
                    "message": "인스턴스 일정 metadata가 올바르지 않습니다. 관리자에게 확인을 요청하세요.",
                }
            )
            continue
        if schedule is not None:
            schedules.append(schedule.model_copy(update={"instance_name": _field(server, "name")}))
    return {"schedules": schedules, "errors": errors}


@router.get("/usage-extension-policy")
async def get_extension_policy(
    domain_id: str | None = None,
    project_id: str | None = None,
    conn=Depends(get_governance_conn),
    token_info: dict = Depends(get_token_info),
):
    return await governance.get_policy(conn, token_info, domain_id=domain_id, project_id=project_id)


@router.put("/usage-extension-policy")
async def put_extension_policy(
    req: UsagePolicyUpdate,
    domain_id: str | None = None,
    project_id: str | None = None,
    conn=Depends(get_governance_conn),
    token_info: dict = Depends(get_token_info),
):
    return await governance.set_policy(conn, token_info, req, domain_id=domain_id, project_id=project_id)


@router.get("/usage-extension-requests")
async def get_extension_requests(
    domain_id: str | None = None,
    project_id: str | None = None,
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = Query(None, max_length=512),
    conn=Depends(get_governance_conn),
    token_info: dict = Depends(get_token_info),
):
    return await governance.list_requests(
        conn, token_info, domain_id=domain_id, project_id=project_id, limit=limit, cursor=cursor
    )


@router.post("/usage-extension-requests/{request_id}/review")
async def review_extension_request(
    request_id: str,
    req: UsageExtensionReview,
    conn=Depends(get_governance_conn),
    token_info: dict = Depends(get_token_info),
):
    result = await governance.review_request(conn, token_info, request_id, req)
    if result["status"] == "approved":
        await invalidate(f"afterglow:nova:{result['project_id']}:instances")
        await invalidate(f"afterglow:nova:{result['project_id']}:servers")
    await rec(
        token_info,
        conn,
        resource_type="instance",
        resource_id=result["instance_id"],
        resource_name=result["instance_name"],
        action="instance.usage.extension.review",
        status="success",
        extra={"request_id": result["id"], "decision": req.decision, "status": result["status"]},
    )
    return result


@router.get("/{instance_id}/usage-schedule", response_model=UsageScheduleInfo | None)
async def get_usage_schedule(instance_id: str, conn=Depends(get_os_conn)):
    return usage.parse_schedule(await read_server(conn, instance_id))


async def _change(conn, instance_id, req, token_info, *, extend: bool):
    server = await read_server(conn, instance_id)
    if not extend:
        # A schedule can stop or delete the VM at expiry; extension only prolongs it.
        ensure_server_not_waygate_managed(server)
    schedule = await governance.change_schedule(conn, server, req, token_info, extension_only=extend)
    if isinstance(schedule, dict) and schedule.get("status") == "pending":
        await rec(
            token_info,
            conn,
            resource_type="instance",
            resource_id=instance_id,
            resource_name=_field(server, "name"),
            action="instance.usage.extension.request",
            status="success",
            extra={"request_id": schedule["request"]["id"], "expires_at": schedule["request"]["expires_at"]},
        )
        return JSONResponse(jsonable_encoder(schedule), status_code=202)
    project_id = conn._afterglow_project_id
    await invalidate(f"afterglow:nova:{project_id}:instances")
    await invalidate(f"afterglow:nova:{project_id}:servers")
    await rec(
        token_info,
        conn,
        resource_type="instance",
        resource_id=instance_id,
        resource_name=_field(server, "name"),
        action="instance.usage.extend" if extend else "instance.usage.update",
        status="success",
        extra={"expires_at": schedule.expires_at, "expiry_action": schedule.expiry_action},
    )
    return schedule


@router.put("/{instance_id}/usage-schedule", response_model=UsageScheduleInfo)
async def update_usage_schedule(
    instance_id: str,
    req: UsageScheduleUpdate,
    conn=Depends(get_os_conn_write),
    token_info: dict = Depends(require_project_write),
):
    return await _change(conn, instance_id, req, token_info, extend=False)


@router.post("/{instance_id}/usage-schedule/extend", response_model=UsageScheduleInfo)
async def extend_usage_schedule(
    instance_id: str,
    req: UsageScheduleExtension,
    conn=Depends(get_os_conn_write),
    token_info: dict = Depends(require_project_write),
):
    return await _change(conn, instance_id, req, token_info, extend=True)


@admin_router.get("/instances/{instance_id}/usage-schedule", response_model=UsageScheduleInfo | None)
async def get_admin_usage_schedule(instance_id: str, conn=Depends(get_admin_os_conn)):
    return usage.parse_schedule(await read_server(conn, instance_id, project_scoped=False))


@asynccontextmanager
async def _admin_target(executor, instance_id: str, token_info: dict):
    # Global authority selects an observed owner; an input project cannot redirect it.
    from app.api.identity.admin_instances import _make_admin_conn

    server = await read_server(executor, instance_id, project_scoped=False)
    project_id = _field(server, "project_id") or _field(server, "tenant_id")
    conn = await usage.sdk_call(_make_admin_conn, project_id, token_info["user_id"])
    try:
        yield conn
    finally:
        await usage.sdk_call(conn.close)


@admin_router.put("/instances/{instance_id}/usage-schedule", response_model=UsageScheduleInfo)
async def update_admin_usage_schedule(
    instance_id: str,
    req: UsageScheduleUpdate,
    executor=Depends(get_admin_os_conn),
    token_info: dict = Depends(get_token_info),
):
    async with _admin_target(executor, instance_id, token_info) as conn:
        return await _change(conn, instance_id, req, token_info, extend=False)


@admin_router.post("/instances/{instance_id}/usage-schedule/extend", response_model=UsageScheduleInfo)
async def extend_admin_usage_schedule(
    instance_id: str,
    req: UsageScheduleExtension,
    executor=Depends(get_admin_os_conn),
    token_info: dict = Depends(get_token_info),
):
    async with _admin_target(executor, instance_id, token_info) as conn:
        return await _change(conn, instance_id, req, token_info, extend=True)
