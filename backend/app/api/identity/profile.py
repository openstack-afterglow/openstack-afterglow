"""사용자 본인 프로필 관리 엔드포인트."""

import asyncio
import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import get_os_conn, get_token_info
from app.rate_limit import limiter
from app.services import keystone, profile_images

_logger = logging.getLogger(__name__)

router = APIRouter()


class UpdateProfileRequest(BaseModel):
    name: str | None = None
    email: str | None = None
    description: str | None = None
    default_project_id: str | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=1, max_length=1024)


class ProfileImageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["gravatar", "generated"]


async def _image_call(call, *args):
    try:
        return await asyncio.to_thread(call, *args)
    except HTTPException:
        raise
    except Exception as exc:
        if (
            getattr(getattr(exc, "response", None), "status_code", None) == 403
            or getattr(exc, "status_code", None) == 403
        ):
            raise HTTPException(403, "profile_image_forbidden") from exc
        raise HTTPException(503, "profile_image_unavailable") from exc


@router.get("/image")
async def get_profile_image(
    response: Response,
    token_info: dict = Depends(get_token_info),
    conn=Depends(get_os_conn),
):
    response.headers["Cache-Control"] = "private, no-store"
    return await _image_call(profile_images.get_image, conn, token_info["user_id"], token_info["identity_domain_id"])


@router.put("/image")
@limiter.limit("20/minute")
async def select_profile_image(
    request: Request,
    response: Response,
    req: ProfileImageRequest,
    token_info: dict = Depends(get_token_info),
    conn=Depends(get_os_conn),
):
    response.headers["Cache-Control"] = "private, no-store"
    return await _image_call(
        profile_images.save_image, conn, token_info["user_id"], token_info["identity_domain_id"], req.kind
    )


@router.put("/image/upload")
@limiter.limit("20/minute")
async def upload_profile_image(
    request: Request,
    response: Response,
    token_info: dict = Depends(get_token_info),
    conn=Depends(get_os_conn),
):
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > profile_images.MAX_UPLOAD_BYTES:
            raise HTTPException(413, "profile_image_size")
        content.extend(chunk)
    response.headers["Cache-Control"] = "private, no-store"
    return await _image_call(
        profile_images.save_image,
        conn,
        token_info["user_id"],
        token_info["identity_domain_id"],
        "upload",
        bytes(content),
    )


class LoginPreferenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    remember_last_workspace: bool = Field(strict=True)


@router.get("/login-preference")
async def get_login_preference(response: Response, token_info: dict = Depends(get_token_info)):
    from app.services import login_preferences

    response.headers["Cache-Control"] = "private, no-store"
    return await login_preferences.read(token_info["user_id"], token_info["identity_domain_id"])


@router.put("/login-preference")
async def update_login_preference(
    req: LoginPreferenceRequest, response: Response, token_info: dict = Depends(get_token_info)
):
    from app.services import domain_projects, domain_scope, login_preferences
    from app.services.native_operation import NativeOperation

    response.headers["Cache-Control"] = "private, no-store"
    async with NativeOperation() as operation:
        uid, home = token_info["user_id"], token_info["identity_domain_id"]
        did, pid = token_info["domain_id"], token_info.get("project_id", "")
        if req.remember_last_workspace:
            context = await operation.run(domain_scope.domain_context, uid, did, operation=operation)
            await operation.run(domain_projects.assert_membership, uid, did, operation=operation)
            domain_scope.assert_domain_resource(home, context["identity_domain_id"])
            await operation.run(domain_scope.assert_project_domain, did, pid, operation=operation)
            await operation.run(domain_projects.assert_project_membership, uid, pid, operation=operation)
        return await login_preferences.save(uid, home, req.remember_last_workspace, domain_id=did, project_id=pid)


@router.get("")
async def get_profile(
    token_info: dict = Depends(get_token_info),
    conn=Depends(get_os_conn),
):
    """본인 프로필 조회."""
    user_id = token_info["user_id"]

    def _get():
        try:
            u = conn.identity.get_user(user_id)
            return {
                "id": u.id,
                "name": u.name or "",
                "email": getattr(u, "email", None) or "",
                "description": getattr(u, "description", None) or "",
                "default_project_id": getattr(u, "default_project_id", None) or "",
            }
        except Exception:
            raise HTTPException(status_code=500, detail="프로필 조회 실패")

    try:
        return await asyncio.to_thread(_get)
    except HTTPException:
        raise


@router.patch("")
async def update_profile(
    req: UpdateProfileRequest,
    token_info: dict = Depends(get_token_info),
    conn=Depends(get_os_conn),
):
    """Update profile metadata; email ownership changes require a verified link."""
    user_id = token_info["user_id"]

    def _update():
        kwargs: dict = {}
        if req.name is not None:
            kwargs["name"] = req.name
        if req.email is not None:
            current = conn.identity.get_user(user_id)
            if req.email.strip().casefold() != (getattr(current, "email", "") or "").strip().casefold():
                raise HTTPException(status_code=409, detail="email_verification_required")
        if req.description is not None:
            kwargs["description"] = req.description
        if req.default_project_id is not None:
            kwargs["default_project_id"] = req.default_project_id
        if not kwargs:
            raise HTTPException(status_code=400, detail="수정할 항목이 없습니다")
        try:
            u = conn.identity.update_user(user_id, **kwargs)
            return {
                "id": u.id,
                "name": u.name or "",
                "email": getattr(u, "email", None) or "",
                "description": getattr(u, "description", None) or "",
                "default_project_id": getattr(u, "default_project_id", None) or "",
            }
        except HTTPException:
            raise
        except Exception as e:
            _logger.warning("프로필 수정 실패: %s", e)

            raise HTTPException(status_code=400, detail="프로필 수정 실패")

    try:
        return await asyncio.to_thread(_update)
    except HTTPException:
        raise


@router.post("/password")
@limiter.limit("5/minute")
async def change_password(
    request: Request,
    req: ChangePasswordRequest,
    token_info: dict = Depends(get_token_info),
    conn=Depends(get_os_conn),
):
    """패스워드 변경 (현재 패스워드 검증 후 변경)."""
    # 외부(federated) 로그인 사용자는 로컬 패스워드가 없으므로 변경 불가
    if token_info.get("auth_method") == "federated":
        raise HTTPException(status_code=403, detail="외부 로그인 사용자는 패스워드를 변경할 수 없습니다")

    user_id = token_info["user_id"]
    username = token_info["username"]

    # Reauthenticate in the immutable account namespace, not the working domain.
    from keystoneauth1.exceptions.http import Unauthorized

    try:
        current = await asyncio.to_thread(
            keystone.authenticate,
            username,
            req.current_password,
            "",
            token_info["identity_domain_id"],
            unscoped_only=True,
        )
    except Unauthorized as exc:
        raise HTTPException(status_code=401, detail="현재 패스워드가 올바르지 않습니다") from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="현재 패스워드를 검증할 수 없습니다") from exc
    if current.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Password identity does not match the current account")

    def _change():
        try:
            conn.identity.update_user(user_id, password=req.new_password)
            return {"status": "changed"}
        except Exception as e:
            _logger.warning("패스워드 변경 실패: %s", e)

            raise HTTPException(status_code=400, detail="패스워드 변경 실패")

    try:
        return await asyncio.to_thread(_change)
    except HTTPException:
        raise
