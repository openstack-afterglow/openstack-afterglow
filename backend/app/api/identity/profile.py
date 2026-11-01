"""사용자 본인 프로필 관리 엔드포인트."""

import asyncio
import logging
from typing import Literal
from urllib.parse import quote

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
):
    """Change an existing credential using Keystone's self-service policy."""
    from keystoneauth1.exceptions.http import Forbidden, Unauthorized

    from app.services.native_operation import NativeOperation

    async with NativeOperation() as operation:
        try:
            current = await operation.run(
                keystone.authenticate,
                token_info["username"],
                req.current_password,
                "",
                token_info["identity_domain_id"],
                unscoped_only=True,
                operation=operation,
            )
        except keystone.PasswordRejected as exc:
            raise HTTPException(401, "password_current_invalid") from exc
        except Unauthorized as exc:
            raise HTTPException(403, "password_identity_mismatch") from exc
        except Forbidden as exc:
            raise HTTPException(403, "password_change_forbidden") from exc
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(503, "password_verification_unavailable") from exc

        if (
            current.get("user_id") != token_info["user_id"]
            or current.get("identity_domain_id") != token_info["identity_domain_id"]
        ):
            raise HTTPException(403, "password_identity_mismatch")
        proof = current.get("token")
        if not isinstance(proof, str) or not proof:
            raise HTTPException(503, "password_verification_unavailable")

        def _change():
            settings = keystone.get_settings()
            session = operation.own_session(
                keystone.native_transport.create_session(timeout=30, verify=settings.ssl_verify)
            )
            # Stock Keystone permits self-service POST, not generic user PATCH.
            # Explicit auth prevents exchanging this proof into another token.
            # Credential bodies and native errors must never enter debug logs.
            try:
                response = session.post(
                    f"{settings.os_auth_url.rstrip('/')}/users/{quote(token_info['user_id'], safe='')}/password",
                    json={"user": {"original_password": req.current_password, "password": req.new_password}},
                    headers={"X-Auth-Token": proof},
                    authenticated=False,
                    allow_reauth=False,
                    redirect=False,
                    connect_retries=0,
                    status_code_retries=0,
                    log=False,
                    raise_exc=False,
                )
            except Exception as exc:
                # The provider may have committed before the response was lost.
                # Do not retry or expose exception text containing credentials.
                raise HTTPException(502, "password_change_outcome_unknown") from exc
            if response.status_code == 204:
                return {"status": "changed"}
            if response.status_code == 401:
                raise HTTPException(401, "password_current_invalid")
            if response.status_code == 403:
                raise HTTPException(403, "password_change_forbidden")
            if response.status_code in {400, 409, 422}:
                raise HTTPException(400, "password_change_rejected")
            raise HTTPException(502, "password_change_outcome_unknown")

        return await operation.run(_change)
