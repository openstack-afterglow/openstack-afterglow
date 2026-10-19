"""Domain login policy, provider administration and generic provider login.

``public_router`` is mounted under /api/v1/auth (global login options, domain
resolve, provider authorize/callback). ``iam_router`` is mounted under /api/v1/iam and requires
verified domain-manager (or system-admin) authority; the domain always comes from
the authenticated server-side context, never from the request body.
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.api.deps import get_token_info, require_domain_manager
from app.models.auth import LoginOptionsResponse, TokenResponse
from app.rate_limit import limiter
from app.services import domain_auth as svc
from app.utils.auth_diagnostics import authentication_operation, authentication_step

logger = logging.getLogger(__name__)

NO_STORE = {"Cache-Control": "no-store, private", "Pragma": "no-cache", "Referrer-Policy": "no-referrer"}


class DomainAuthRoute(APIRoute):
    """No-store responses, {detail, code} errors and input-free validation errors."""

    def get_route_handler(self):
        handler = super().get_route_handler()

        async def guarded(request):
            with authentication_operation(self.endpoint.__name__):
                try:
                    with authentication_step("request"):
                        response = await handler(request)
                except RequestValidationError:
                    # Pydantic input/ctx may echo a client secret; never reflect it.
                    response = JSONResponse(
                        {"detail": "identity_invalid_input", "code": "identity_invalid_input"}, status_code=422
                    )
                except svc.DomainAuthError as exc:
                    response = svc.domain_auth_error_response(exc)
                except HTTPException as exc:
                    response = JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)
                response.headers.update(NO_STORE)
                return response

        return guarded


public_router = APIRouter(route_class=DomainAuthRoute)
iam_router = APIRouter(route_class=DomainAuthRoute)


# ── DTOs ────────────────────────────────────────────────────────────────────


class ProviderSummary(BaseModel):
    id: str
    name: str
    kind: str


class DomainResolveResponse(BaseModel):
    domain_id: str
    domain_name: str
    password_enabled: bool
    providers: list[ProviderSummary]
    signup_enabled: bool


class AuthorizeResponse(BaseModel):
    authorize_url: str


class ProviderCallbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(..., min_length=1, max_length=2048)
    state: str = Field(..., min_length=16, max_length=256)


class ProviderLinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    link_token: str = Field(min_length=16, max_length=256)
    username: str = Field(min_length=1, max_length=255)
    password: SecretStr = Field(min_length=1, max_length=4096)


class AuthenticatedProviderLinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    link_token: str = Field(min_length=16, max_length=256)


class ProviderLinkResponse(BaseModel):
    linked: Literal[True]
    domain_id: str
    domain_name: str
    provider_id: str


class LoginPolicyResponse(BaseModel):
    domain_id: str
    password_enabled: bool
    allowed_email_domains: list[str]
    signup_enabled: bool
    signup_email_domains: list[str]
    revision: int
    configured: bool
    smtp_configured: bool
    usable_provider_count: int


class LoginPolicyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password_enabled: bool
    allowed_email_domains: list[str] = Field(default_factory=list, max_length=100)
    signup_enabled: bool
    signup_email_domains: list[str] = Field(default_factory=list, max_length=100)
    revision: int | None = Field(default=None, ge=0)


class ProviderResponse(BaseModel):
    id: str
    domain_id: str
    name: str
    kind: str
    issuer_url: str | None
    authorization_url: str | None
    token_url: str | None
    api_url: str | None
    client_id: str
    client_secret_configured: bool
    scopes: list[str]
    keystone_idp_id: str
    keystone_protocol_id: str
    enabled: bool
    revision: int
    verified: bool
    verified_revision: int | None
    verified_at: str | None
    federation_token_type: str
    token_endpoint_auth_method: str | None
    created_at: str | None
    updated_at: str | None


class ProviderList(BaseModel):
    items: list[ProviderResponse]


class ProviderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=64)
    kind: str = Field(..., pattern="^(oidc|github)$")
    issuer_url: str | None = Field(default=None, max_length=512)
    authorization_url: str | None = Field(default=None, max_length=512)
    token_url: str | None = Field(default=None, max_length=512)
    api_url: str | None = Field(default=None, max_length=512)
    client_id: str = Field(..., min_length=1, max_length=255)
    client_secret: SecretStr = Field(..., min_length=1, max_length=4096)
    scopes: list[str] | None = Field(default=None, max_length=20)
    keystone_idp_id: str = Field(..., min_length=1, max_length=64)
    keystone_protocol_id: str = Field(..., min_length=1, max_length=64)
    federation_token_type: str = Field(default="id_token", pattern="^(id_token|access_token)$")
    token_endpoint_auth_method: str | None = Field(default=None, pattern="^client_secret_(basic|post)$")
    enabled: bool = True


class ProviderUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=64)
    kind: str | None = Field(default=None, pattern="^(oidc|github)$")
    issuer_url: str | None = Field(default=None, max_length=512)
    authorization_url: str | None = Field(default=None, max_length=512)
    token_url: str | None = Field(default=None, max_length=512)
    api_url: str | None = Field(default=None, max_length=512)
    client_id: str | None = Field(default=None, min_length=1, max_length=255)
    client_secret: SecretStr | None = Field(default=None, min_length=1, max_length=4096)
    scopes: list[str] | None = Field(default=None, max_length=20)
    keystone_idp_id: str | None = Field(default=None, min_length=1, max_length=64)
    keystone_protocol_id: str | None = Field(default=None, min_length=1, max_length=64)
    federation_token_type: str | None = Field(default=None, pattern="^(id_token|access_token)$")
    token_endpoint_auth_method: str | None = Field(default=None, pattern="^client_secret_(basic|post)$")
    enabled: bool | None = None
    revision: int | None = Field(default=None, ge=0)


def _fields(model: BaseModel) -> dict:
    fields = model.model_dump(exclude_unset=True)
    for key, value in list(fields.items()):
        if value is None and key not in (
            "issuer_url",
            "authorization_url",
            "token_url",
            "api_url",
            "token_endpoint_auth_method",
        ):
            # Explicit null for non-clearable fields means "unchanged".
            fields.pop(key)
    secret = getattr(model, "client_secret", None)
    if isinstance(secret, SecretStr):
        fields["client_secret"] = secret.get_secret_value()
    return fields


# ── public login routes (/api/v1/auth) ──────────────────────────────────────


@public_router.get("/login-options", response_model=LoginOptionsResponse)
@limiter.limit("30/minute")
async def login_options(request: Request):
    """List offered registrations by exact origin, without identity lookup or discovery."""
    return await svc.login_options()


@public_router.get("/domains/resolve", response_model=DomainResolveResponse)
@limiter.limit("30/minute")
async def resolve_domain(request: Request, name: str = Query(..., min_length=1, max_length=255)):
    """Resolve an exact enabled domain and only its currently usable login methods."""
    with authentication_step("domain_resolution"):
        return await svc.resolve_login_domain(name)


@public_router.post("/domains/{domain_id}/providers/{provider_id}/authorize", response_model=AuthorizeResponse)
@limiter.limit("20/minute")
async def authorize(request: Request, domain_id: str, provider_id: str, response: Response):
    svc.require_same_site_browser(request)
    start = await svc.start_authorization(domain_id, provider_id)
    response.set_cookie(
        key=svc.STATE_COOKIE,
        value=start.browser_binding,
        max_age=svc.STATE_TTL_SECONDS,
        httponly=True,
        secure=svc.cookie_secure(),
        samesite="lax",
        path=svc.STATE_COOKIE_PATH,
    )
    return {"authorize_url": start.authorize_url}


def _clear_state_cookie(response: Response) -> None:
    response.delete_cookie(
        key=svc.STATE_COOKIE, path=svc.STATE_COOKIE_PATH, httponly=True, secure=svc.cookie_secure(), samesite="lax"
    )


@public_router.post("/providers/callback", response_model=TokenResponse)
@limiter.limit("10/minute")
async def provider_callback(
    request: Request, req: ProviderCallbackRequest, background_tasks: BackgroundTasks, response: Response
):
    """Complete a domain provider login with one-use, browser-bound state."""
    binding = request.cookies.get(svc.STATE_COOKIE, "")
    try:
        svc.require_same_site_browser(request)
        login = await svc.complete_authorization(req.code, req.state, binding)
    except svc.DomainAuthError as exc:
        failure = svc.domain_auth_error_response(exc)
        if not isinstance(exc, svc.AccountLinkRequired):
            _clear_state_cookie(failure)
        return failure
    return await _finish_provider_login(request, background_tasks, response, login)


@public_router.post("/providers/link", response_model=ProviderLinkResponse)
@limiter.limit("5/minute")
async def provider_link(request: Request, req: ProviderLinkRequest, response: Response):
    svc.require_same_site_browser(request)
    try:
        linked = await svc.complete_account_link(
            req.link_token,
            request.cookies.get(svc.STATE_COOKIE, ""),
            username=req.username,
            password=req.password.get_secret_value(),
        )
    except svc.DomainAuthError as exc:
        failure = svc.domain_auth_error_response(exc)
        _clear_state_cookie(failure)
        return failure
    _clear_state_cookie(response)
    return linked


@public_router.post("/providers/link/authenticated", response_model=ProviderLinkResponse)
@limiter.limit("5/minute")
async def provider_link_authenticated(
    request: Request,
    req: AuthenticatedProviderLinkRequest,
    response: Response,
    token_info: dict = Depends(get_token_info),
):
    svc.require_same_site_browser(request)
    try:
        linked = await svc.complete_account_link(
            req.link_token,
            request.cookies.get(svc.STATE_COOKIE, ""),
            authenticated=token_info,
        )
    except svc.DomainAuthError as exc:
        failure = svc.domain_auth_error_response(exc)
        _clear_state_cookie(failure)
        return failure
    _clear_state_cookie(response)
    return linked


async def _finish_provider_login(request, background_tasks, response, login):
    from app.api.identity.auth import issue_federated_login

    token = None
    try:
        token = await issue_federated_login(
            request,
            background_tasks,
            unscoped_token=login.unscoped_token,
            user_id=login.user_id,
            username=login.username,
            domain_id=login.domain_id,
            domain_name=login.domain_name,
            provider_id=login.provider_id,
            provider_revision=login.provider_revision,
            provider_kind=login.provider_kind,
            login_email=login.login_email,
        )
        await svc.mark_provider_verified(login.domain_id, login.provider_id, login.provider_revision)
    except Exception as exc:
        await svc._revoke_quietly(login.unscoped_token)
        if token is not None and token.refresh_token:
            from app.services import jwt_service, session_store

            try:
                claims = jwt_service.verify_refresh(token.refresh_token)
                await session_store.delete_session_owned(login.user_id, claims["jti"], revoke_keystone=True)
            except Exception:
                logger.warning("Failed to revoke rejected provider session", exc_info=False)
        if isinstance(exc, svc.DomainAuthError):
            failure = svc.domain_auth_error_response(exc)
            _clear_state_cookie(failure)
            return failure
        raise
    _clear_state_cookie(response)
    return token


# ── domain IAM policy/provider administration (/api/v1/iam) ─────────────────


@iam_router.get("/login-policy", response_model=LoginPolicyResponse)
async def get_login_policy(token_info: dict = Depends(require_domain_manager)):
    return await svc.policy_view(token_info["domain_id"])


@iam_router.put("/login-policy", response_model=LoginPolicyResponse)
async def put_login_policy(req: LoginPolicyUpdate, token_info: dict = Depends(require_domain_manager)):
    return await svc.update_policy(
        token_info["domain_id"],
        actor_user_id=token_info["user_id"],
        password_enabled=req.password_enabled,
        allowed_email_domains=req.allowed_email_domains,
        signup_enabled=req.signup_enabled,
        signup_email_domains=req.signup_email_domains,
        expected_revision=req.revision,
    )


@iam_router.get("/providers", response_model=ProviderList)
async def list_providers(token_info: dict = Depends(require_domain_manager)):
    return {"items": await svc.list_providers(token_info["domain_id"])}


@iam_router.post("/providers", response_model=ProviderResponse, status_code=201)
async def create_provider(req: ProviderCreate, token_info: dict = Depends(require_domain_manager)):
    return await svc.create_provider(token_info["domain_id"], actor_user_id=token_info["user_id"], fields=_fields(req))


@iam_router.patch("/providers/{provider_id}", response_model=ProviderResponse)
async def update_provider(provider_id: str, req: ProviderUpdate, token_info: dict = Depends(require_domain_manager)):
    return await svc.update_provider(
        token_info["domain_id"], provider_id, actor_user_id=token_info["user_id"], fields=_fields(req)
    )


@iam_router.delete("/providers/{provider_id}", status_code=204)
async def delete_provider(provider_id: str, token_info: dict = Depends(require_domain_manager)):
    await svc.delete_provider(token_info["domain_id"], provider_id)
    return Response(status_code=204)
