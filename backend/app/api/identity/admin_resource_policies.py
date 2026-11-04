"""Administrator-managed discovered-resource policies and runtime settings."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Annotated
from urllib.parse import quote

import openstack
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field, StrictBool, StringConstraints

from app.api.deps import get_token_info, require_admin
from app.config import get_settings
from app.services import resource_policies
from app.services import resource_policy_store as store
from app.services.keystone import get_admin_project_connection
from app.services.service_proxy import get_json, proxy

router = APIRouter()


class ResourcePolicyUpdate(BaseModel):
    resource_id: str | None = Field(default=None, max_length=128)


class RuntimeSettingUpdate(BaseModel):
    value: StrictBool | Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32)]


@asynccontextmanager
async def _admin_os_conn() -> AsyncIterator[openstack.connection.Connection]:
    """Use the backend administrative scope, never the browser user's project."""
    try:
        conn = await asyncio.to_thread(get_admin_project_connection)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="관리자 OpenStack 연결을 만들 수 없습니다") from exc
    try:
        yield conn
    finally:
        with suppress(Exception):
            await asyncio.to_thread(conn.close)


def _is_waygate_policy(policy_key: str) -> bool:
    return policy_key.startswith("waygate.")


def _is_drover_policy(policy_key: str) -> bool:
    return policy_key.startswith("k3s.")


def _is_drover_runtime_setting(setting_key: str) -> bool:
    return setting_key == "k3s.version"


def _require_waygate_enabled() -> None:
    if not get_settings().service_waygate_enabled:
        raise HTTPException(status_code=503, detail="waygate 서비스를 사용할 수 없습니다")


def _require_drover_enabled() -> None:
    if not get_settings().service_k3s_enabled:
        raise HTTPException(status_code=503, detail="drover 서비스를 사용할 수 없습니다")


@router.get("/resource-policies", dependencies=[Depends(require_admin)])
async def list_resource_policies(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    try:
        async with _admin_os_conn() as conn:
            local_policies = await store.inspect_policies(conn)
    except store.ResourcePolicyStorageUnavailable as exc:
        raise HTTPException(status_code=503, detail="리소스 정책 저장소를 사용할 수 없습니다") from exc

    local_policies = [
        policy
        for policy in local_policies
        if not _is_waygate_policy(str(policy.get("key") or "")) and not _is_drover_policy(str(policy.get("key") or ""))
    ]
    settings = get_settings()
    errors: list[dict] = []
    for service, enabled in (
        ("drover", settings.service_k3s_enabled),
        ("waygate", settings.service_waygate_enabled),
    ):
        if not enabled:
            continue
        try:
            policies = await get_json(service, request, "/v1/admin/resource-policies")
        except HTTPException as exc:
            errors.append({"service": service, "status": exc.status_code})
            continue
        if not isinstance(policies, list):
            errors.append({"service": service, "status": 502})
            continue
        local_policies.extend(policies)
    return {"policies": local_policies, "errors": errors}


def _catalog(spec: resource_policies.PolicySpec, options: list[dict]) -> dict:
    return {
        "key": spec.key,
        "resource_kind": spec.resource_kind,
        "group": spec.group,
        "execution_scope": spec.execution_scope,
        "dependency": spec.dependency,
        "constraints": {"external_only": spec.external_only, "shared_only": spec.shared_only},
        "options": options,
    }


@router.get("/resource-policies/catalog", dependencies=[Depends(require_admin)])
async def discover_resource_policy_catalogs(
    response: Response,
    keys: Annotated[list[str], Query(min_length=1, max_length=32)],
):
    """Batch local catalogs only; extracted services retain independent reads."""
    response.headers["Cache-Control"] = "no-store"
    keys = list(dict.fromkeys(keys))
    results: dict[str, dict] = {}
    local_keys = [key for key in keys if not _is_waygate_policy(key) and not _is_drover_policy(key)]

    def failure(key: str, status: int, detail: str) -> dict:
        return {"key": key, "error": {"status": status, "detail": detail}}

    for key in keys:
        if key not in local_keys:
            results[key] = failure(key, 404, "알 수 없는 리소스 정책입니다")

    async def local():
        if not local_keys:
            return
        try:
            async with _admin_os_conn() as conn:
                discovered = await resource_policies.discover_options_batch(conn, local_keys)
            for key, options in discovered.items():
                if isinstance(options, resource_policies.ResourcePolicyValidationError):
                    results[key] = failure(key, 404, "알 수 없는 리소스 정책입니다")
                elif isinstance(options, Exception):
                    results[key] = failure(key, 503, "OpenStack 리소스 목록을 조회할 수 없습니다")
                else:
                    results[key] = _catalog(resource_policies.get_spec(key), options)
        except Exception:
            for key in local_keys:
                results[key] = failure(key, 503, "OpenStack 리소스 목록을 조회할 수 없습니다")

    await local()
    return {"catalogs": [results[key] for key in keys]}


@router.get("/resource-policies/catalog/{policy_key}", dependencies=[Depends(require_admin)])
async def discover_resource_policy_options(policy_key: str, request: Request):
    if _is_waygate_policy(policy_key):
        _require_waygate_enabled()
        safe_key = quote(policy_key, safe="")
        return await get_json("waygate", request, f"/v1/admin/resource-policies/catalog/{safe_key}")
    if _is_drover_policy(policy_key):
        _require_drover_enabled()
        safe_key = quote(policy_key, safe="")
        return await get_json("drover", request, f"/v1/admin/resource-policies/catalog/{safe_key}")

    try:
        async with _admin_os_conn() as conn:
            spec = resource_policies.get_spec(policy_key)
            return _catalog(spec, await resource_policies.discover_options(conn, policy_key))
    except resource_policies.ResourcePolicyValidationError as exc:
        raise HTTPException(status_code=404, detail="알 수 없는 리소스 정책입니다") from exc
    except store.ResourcePolicyStorageUnavailable as exc:
        raise HTTPException(status_code=503, detail="리소스 정책 저장소를 사용할 수 없습니다") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="OpenStack 리소스 목록을 조회할 수 없습니다") from exc


@router.put("/resource-policies/{policy_key}", dependencies=[Depends(require_admin)])
async def update_resource_policy(
    policy_key: str,
    body: ResourcePolicyUpdate,
    request: Request,
    token_info: dict = Depends(get_token_info),
):
    if _is_waygate_policy(policy_key):
        _require_waygate_enabled()
        safe_key = quote(policy_key, safe="")
        return await proxy("waygate", request, f"/v1/admin/resource-policies/{safe_key}")
    if _is_drover_policy(policy_key):
        _require_drover_enabled()
        safe_key = quote(policy_key, safe="")
        return await proxy("drover", request, f"/v1/admin/resource-policies/{safe_key}")

    try:
        async with _admin_os_conn() as conn:
            return await store.set_policy(
                conn=conn,
                key=policy_key,
                resource_id=body.resource_id,
                updated_by_user_id=str(token_info.get("user_id") or ""),
            )
    except resource_policies.ResourcePolicyValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except store.ResourcePolicyStorageUnavailable as exc:
        raise HTTPException(status_code=503, detail="리소스 정책 저장소를 사용할 수 없습니다") from exc


@router.get("/runtime-settings", dependencies=[Depends(require_admin)])
async def list_runtime_settings(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    try:
        local_settings = await store.list_runtime_settings()
    except store.ResourcePolicyStorageUnavailable as exc:
        raise HTTPException(status_code=503, detail="런타임 설정 저장소를 사용할 수 없습니다") from exc

    local_settings = [
        setting for setting in local_settings if not _is_drover_runtime_setting(str(setting.get("key") or ""))
    ]
    errors: list[dict] = []
    if get_settings().service_k3s_enabled:
        try:
            drover_settings = await get_json("drover", request, "/v1/admin/runtime-settings")
        except HTTPException as exc:
            errors.append({"service": "drover", "status": exc.status_code})
        else:
            if isinstance(drover_settings, list):
                local_settings.extend(drover_settings)
            else:
                errors.append({"service": "drover", "status": 502})
    return {"settings": local_settings, "errors": errors}


@router.put("/runtime-settings/{setting_key}", dependencies=[Depends(require_admin)])
async def update_runtime_setting(
    setting_key: str,
    body: RuntimeSettingUpdate,
    request: Request,
    token_info: dict = Depends(get_token_info),
):
    if _is_drover_runtime_setting(setting_key):
        _require_drover_enabled()
        safe_key = quote(setting_key, safe="")
        return await proxy("drover", request, f"/v1/admin/runtime-settings/{safe_key}")
    try:
        return await store.set_runtime_setting(
            key=setting_key,
            value=body.value,
            updated_by_user_id=str(token_info.get("user_id") or ""),
        )
    except store.RuntimeSettingValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except store.ResourcePolicyStorageUnavailable as exc:
        raise HTTPException(status_code=503, detail="런타임 설정 저장소를 사용할 수 없습니다") from exc
