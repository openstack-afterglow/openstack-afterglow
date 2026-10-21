"""Per-domain login policy and federated OIDC/OAuth provider authority.

The working domain owns provider policy; native account home remains canonical.

* durable SQL login/signup policy (exact normalized email-domain allowlists);
* domain identity-provider configuration with write-only, domain/provider-bound
  AEAD client secrets;
* read-only registry providers selected by exact effective domain allowlists;
* browser-bound, one-use authorization state (nonce + PKCE + provider revision);
* OIDC ID-token verification (signature, issuer, audience, expiry, nonce,
  verified email) and GitHub verified-primary-email lookup;
* canonical issuer/subject association and explicit account-proof link tickets;
* native Keystone OS-FEDERATION returning the exact canonical account, even
  across authorized working domains. No service token impersonates that user.

Every external IdP request uses the DNS-pinned SSRF transport with redirects
disabled. Failures are fail-closed; secrets, codes and tokens are never logged.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qsl, quote_plus, urlencode, urlsplit
from uuid import uuid4

import httpx
import jwt
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app import database
from app.config import get_settings
from app.models.domain_auth import DomainIdentityProvider, DomainLoginPolicy
from app.services.k3s_crypto import derive_encryption_subkey
from app.services.mcp_control_plane import ssrf

logger = logging.getLogger(__name__)

STATE_TTL_SECONDS = 600
STATE_COOKIE = "afterglow_provider_auth"
STATE_COOKIE_PATH = "/api/v1/auth/providers"
_STATE_KEY_PREFIX = "afterglow:domain_auth:state:"
_CONFIG_PROVIDER_PREFIX = "cfg:"
_CONFIG_BINDING_KEY_PREFIX = "afterglow:domain_auth:config_binding:"
_MAX_EMAIL_DOMAINS = 100
_MAX_SCOPES = 20
_MAX_RESPONSE_BYTES = 1024 * 1024
_HTTP_TIMEOUT = httpx.Timeout(15.0, connect=10.0)
_JWT_LEEWAY_SECONDS = 60
_ALLOWED_JWT_ALGORITHMS = ("RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512", "EdDSA")
_JWT_KEY_TYPES = {alg: "RSA" for alg in _ALLOWED_JWT_ALGORITHMS if alg[:2] in ("RS", "PS")} | {
    "ES256": "EC",
    "ES384": "EC",
    "ES512": "EC",
    "EdDSA": "OKP",
}
_KEYSTONE_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_SCOPE_RE = re.compile(r"^[\x21\x23-\x5B\x5D-\x7E]{1,128}$")
_SECRET_PREFIX = "dap1:"
_SECRET_DOMAIN = b"domain_idp_client_secret"
KINDS = ("oidc", "github")
GITHUB_DEFAULTS = {
    "authorization_url": "https://github.com/login/oauth/authorize",
    "token_url": "https://github.com/login/oauth/access_token",
    "api_url": "https://api.github.com",
}
DEFAULT_SCOPES = {"oidc": ["openid", "email", "profile"], "github": ["read:user", "user:email"]}
_REQUIRED_SCOPES = {"oidc": ("openid", "email"), "github": ("user:email",)}
# Changes to these fields are security relevant: they bump the provider revision,
# invalidating pending authorization state and provider-bound sessions.
_REVISION_FIELDS = (
    "issuer_url",
    "authorization_url",
    "token_url",
    "api_url",
    "client_id",
    "federation_token_type",
    "token_endpoint_auth_method",
    "scopes",
    "keystone_idp_id",
    "keystone_protocol_id",
    "enabled",
)


# ── errors ──────────────────────────────────────────────────────────────────


class DomainAuthError(Exception):
    status_code = 400
    code = "invalid"

    def __init__(self, detail: str, *, code: str | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        if code:
            self.code = code


class DomainAuthDenied(DomainAuthError):
    status_code = 403
    code = "denied"


class DomainAuthUnauthenticated(DomainAuthError):
    status_code = 401
    code = "invalid_state"


class DomainAuthNotFound(DomainAuthError):
    status_code = 404
    code = "not_found"


class DomainAuthConflict(DomainAuthError):
    status_code = 409
    code = "conflict"


class AccountLinkRequired(DomainAuthConflict):
    code = "account_link_required"

    def __init__(self, link_token: str, domain_id: str):
        super().__init__("Sign in to the existing account to link this provider")
        self.link_token = link_token
        self.domain_id = domain_id


class DomainAuthInvalid(DomainAuthError):
    status_code = 422
    code = "invalid"


class DomainAuthProviderError(DomainAuthError):
    status_code = 502
    code = "provider_error"


class DomainAuthUnavailable(DomainAuthError):
    status_code = 503
    code = "unavailable"


def domain_auth_error_response(exc: DomainAuthError) -> JSONResponse:
    """Serialize a DomainAuthError as the frontend ApiError {detail, code} contract."""
    payload = {"detail": exc.detail, "code": exc.code}
    if isinstance(exc, AccountLinkRequired):
        payload.update(link_token=exc.link_token, domain_id=exc.domain_id)
    return JSONResponse(payload, status_code=exc.status_code)


# ── normalization ───────────────────────────────────────────────────────────


def normalize_email_domain(value: object) -> str:
    """Return one exact lowercase ASCII (IDNA) email host; no wildcard, no '@'."""
    from app.models.auth_settings import normalize_auth_email_domain

    try:
        return normalize_auth_email_domain(value)
    except ValueError as exc:
        raise DomainAuthInvalid("Email domain is invalid", code="invalid_email_domain") from exc


def normalize_email_domains(values: object) -> tuple[str, ...]:
    if values is None:
        return ()
    if not isinstance(values, (list, tuple)):
        raise DomainAuthInvalid("Email domains must be a list", code="invalid_email_domain")
    if len(values) > _MAX_EMAIL_DOMAINS:
        raise DomainAuthInvalid("Too many email domains", code="invalid_email_domain")
    return tuple(sorted({normalize_email_domain(value) for value in values}))


def normalize_email(value: object) -> str:
    """Return ``local@domain`` with the host normalized; the local part is kept verbatim."""
    if not isinstance(value, str):
        raise DomainAuthDenied("A verified email address is required", code="email_required")
    email = value.strip()
    if not email or len(email) > 320 or email.count("@") != 1 or any(c.isspace() or ord(c) < 32 for c in email):
        raise DomainAuthDenied("A verified email address is required", code="email_required")
    local, host = email.split("@")
    if not local:
        raise DomainAuthDenied("A verified email address is required", code="email_required")
    try:
        host = normalize_email_domain(host)
    except DomainAuthInvalid as exc:
        raise DomainAuthDenied("Email address is invalid", code="email_required") from exc
    return f"{local}@{host}"


# ── policy ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class LoginPolicy:
    domain_id: str
    password_enabled: bool = True
    allowed_email_domains: tuple[str, ...] = ()
    signup_enabled: bool = False
    signup_email_domains: tuple[str, ...] = ()
    revision: int = 0
    configured: bool = False


def smtp_configured() -> bool:
    """Truthful SMTP readiness, matching the email transport's own precondition."""
    settings = get_settings()
    return bool(settings.smtp_enabled and settings.smtp_host)


def enforce_email(policy: LoginPolicy, email: object, *, signup: bool = False) -> str:
    """Apply exact normalized email-domain policy; return the normalized email.

    Login: an empty allowlist is unrestricted. Signup additionally requires the
    domain's explicit opt-in and a non-empty signup allowlist; the address must
    also satisfy the login allowlist so a registered account can actually log in.
    """
    normalized = normalize_email(email)
    host = normalized.rsplit("@", 1)[1]
    if signup:
        if not policy.signup_enabled or not policy.signup_email_domains:
            raise DomainAuthDenied("Self-service signup is not enabled for this domain", code="signup_disabled")
        if host not in policy.signup_email_domains:
            raise DomainAuthDenied("Email domain is not allowed for signup", code="email_domain_not_allowed")
    if policy.allowed_email_domains and host not in policy.allowed_email_domains:
        raise DomainAuthDenied("Email domain is not allowed for this domain", code="email_domain_not_allowed")
    return normalized


def _require_domain_id(domain_id: object) -> str:
    if not isinstance(domain_id, str) or not domain_id or len(domain_id) > 64:
        raise DomainAuthDenied("An authoritative domain is required", code="domain_required")
    return domain_id


def _factory():
    if not database.is_db_available() or (factory := database.get_session_factory()) is None:
        raise DomainAuthUnavailable("Login policy storage is unavailable")
    return factory


def _storage_failure(exc: Exception) -> DomainAuthUnavailable:
    if isinstance(exc, OperationalError):
        database.mark_db_unhealthy(exc)
    logger.warning("domain auth storage failed: %s", type(exc).__name__)
    return DomainAuthUnavailable("Login policy storage is unavailable")


def _policy_from_row(domain_id: str, row: DomainLoginPolicy | None) -> LoginPolicy:
    if row is None:
        return LoginPolicy(domain_id=domain_id)
    return LoginPolicy(
        domain_id=domain_id,
        password_enabled=bool(row.password_enabled),
        allowed_email_domains=tuple(row.allowed_email_domains or ()),
        signup_enabled=bool(row.signup_enabled),
        signup_email_domains=tuple(row.signup_email_domains or ()),
        revision=int(row.revision),
        configured=True,
    )


async def get_policy(domain_id: str, *, session: AsyncSession | None = None) -> LoginPolicy:
    """Return the domain policy (documented defaults when never saved). Fail closed."""
    domain_id = _require_domain_id(domain_id)
    try:
        if session is not None:
            row = await session.get(DomainLoginPolicy, domain_id)
            return _policy_from_row(domain_id, row)
        async with _factory()() as own:
            row = await own.get(DomainLoginPolicy, domain_id)
            return _policy_from_row(domain_id, row)
    except DomainAuthError:
        raise
    except SQLAlchemyError as exc:
        raise _storage_failure(exc) from exc


async def require_password(domain_id: str, email: str | None, *, session: AsyncSession | None = None) -> LoginPolicy:
    """Password login/account authority: password method enabled and email allowed."""
    policy = await get_policy(domain_id, session=session)
    if not policy.password_enabled:
        raise DomainAuthDenied("Password login is disabled for this domain", code="password_disabled")
    # An empty allowlist is unrestricted: existing accounts without (valid) email keep working.
    if policy.allowed_email_domains:
        enforce_email(policy, email)
    return policy


def _configured(row: DomainIdentityProvider) -> bool:
    return bool(row.enabled and row.client_secret_ciphertext and row.client_id and row.kind in KINDS)


def _usable(row: DomainIdentityProvider) -> bool:
    # Login remains offered for an unverified provider so a manager can prove it
    # works while password login is still enabled. Only an exact revision that
    # completed native session issuance can replace another login method.
    return (
        _configured(row)
        and _provider_allowed(row.domain_id, row.id)
        and row.verified_revision == row.revision
        and row.verified_at is not None
    )


async def mark_provider_verified(domain_id: str, provider_id: str, revision: int) -> None:
    """Called only after native session issuance, never through a manager CRUD body."""
    if provider_id.startswith(_CONFIG_PROVIDER_PREFIX):
        row = await _load_provider(_require_domain_id(domain_id), provider_id)
        if row is None or not _configured(row) or row.revision != revision:
            raise DomainAuthConflict("Provider changed during login", code="provider_changed")
        # File providers are never SQL-verified fallbacks for the last-method guard.
        return
    try:
        async with _factory()() as session, session.begin():
            providers = await _locked_domain_providers(session, domain_id)
            row = next((p for p in providers if p.id == provider_id), None)
            if (
                row is None
                or not _configured(row)
                or row.revision != revision
                or not _provider_allowed(domain_id, provider_id)
            ):
                raise DomainAuthConflict("Provider changed during login", code="provider_changed")
            row.verified_revision = revision
            row.verified_at = datetime.now(UTC)
    except DomainAuthError:
        raise
    except SQLAlchemyError as exc:
        raise _storage_failure(exc) from exc


async def _locked_domain_providers(session: AsyncSession, domain_id: str) -> list[DomainIdentityProvider]:
    """Lock all provider rows of the domain in a stable order (policy/provider serialization)."""
    stmt = (
        select(DomainIdentityProvider)
        .where(DomainIdentityProvider.domain_id == domain_id)
        .order_by(DomainIdentityProvider.id)
        .with_for_update()
    )
    return list((await session.execute(stmt)).scalars().all())


async def policy_view(domain_id: str) -> dict[str, Any]:
    domain_id = _require_domain_id(domain_id)
    try:
        async with _factory()() as session:
            policy = _policy_from_row(domain_id, await session.get(DomainLoginPolicy, domain_id))
            stmt = select(DomainIdentityProvider).where(DomainIdentityProvider.domain_id == domain_id)
            rows = (await session.execute(stmt)).scalars().all()
    except DomainAuthError:
        raise
    except SQLAlchemyError as exc:
        raise _storage_failure(exc) from exc
    return _policy_public(policy, sum(1 for row in rows if _usable(row)))


def _policy_public(policy: LoginPolicy, usable_count: int) -> dict[str, Any]:
    return {
        "domain_id": policy.domain_id,
        "password_enabled": policy.password_enabled,
        "allowed_email_domains": list(policy.allowed_email_domains),
        "signup_enabled": policy.signup_enabled,
        "signup_email_domains": list(policy.signup_email_domains),
        "revision": policy.revision,
        "configured": policy.configured,
        "smtp_configured": smtp_configured(),
        "usable_provider_count": usable_count,
    }


async def update_policy(
    domain_id: str,
    *,
    actor_user_id: str,
    password_enabled: bool,
    allowed_email_domains: list[str],
    signup_enabled: bool,
    signup_email_domains: list[str],
    expected_revision: int | None = None,
) -> dict[str, Any]:
    domain_id = _require_domain_id(domain_id)
    allowed = normalize_email_domains(allowed_email_domains)
    signup_domains = normalize_email_domains(signup_email_domains)
    if signup_enabled:
        if not signup_domains:
            raise DomainAuthInvalid("Signup requires at least one email domain", code="signup_domains_required")
        if allowed and not set(signup_domains) <= set(allowed):
            raise DomainAuthInvalid(
                "Signup email domains must also be allowed for login", code="signup_domain_not_allowed"
            )
        if not smtp_configured():
            raise DomainAuthConflict("SMTP is not configured; signup cannot verify email", code="smtp_not_configured")
    try:
        async with _factory()() as session, session.begin():
            providers = await _locked_domain_providers(session, domain_id)
            row = await session.get(DomainLoginPolicy, domain_id, with_for_update=True)
            current = row.revision if row is not None else 0
            if expected_revision is not None and expected_revision != current:
                raise DomainAuthConflict("Login policy changed; reload and retry", code="revision_conflict")
            usable = sum(1 for provider in providers if _usable(provider))
            if not password_enabled and usable == 0:
                raise DomainAuthConflict(
                    "Disabling password requires a successful login with an enabled provider's current revision",
                    code="last_login_method",
                )
            if row is None:
                row = DomainLoginPolicy(domain_id=domain_id, revision=0, updated_by_user_id=actor_user_id)
                session.add(row)
            row.password_enabled = bool(password_enabled)
            row.allowed_email_domains = list(allowed)
            row.signup_enabled = bool(signup_enabled)
            row.signup_email_domains = list(signup_domains)
            row.revision = current + 1
            row.updated_by_user_id = actor_user_id
            policy = _policy_from_row(domain_id, row)
    except DomainAuthError:
        raise
    except IntegrityError as exc:
        raise DomainAuthConflict("Login policy changed; reload and retry", code="revision_conflict") from exc
    except SQLAlchemyError as exc:
        raise _storage_failure(exc) from exc
    return _policy_public(policy, usable)


# ── provider secrets ────────────────────────────────────────────────────────


def _secret_aad(domain_id: str, provider_id: str) -> bytes:
    if not all(isinstance(v, str) and v and "\x00" not in v for v in (domain_id, provider_id)):
        raise ValueError("provider identity is invalid")
    return b"afterglow-domain-idp-secret-v1\x00" + domain_id.encode() + b"\x00" + provider_id.encode()


def encrypt_client_secret(secret: str, *, domain_id: str, provider_id: str) -> str:
    if not isinstance(secret, str) or not secret:
        raise DomainAuthInvalid("Client secret is required", code="client_secret_required")
    nonce = os.urandom(12)
    sealed = AESGCM(derive_encryption_subkey(_SECRET_DOMAIN)).encrypt(
        nonce, secret.encode("utf-8"), _secret_aad(domain_id, provider_id)
    )
    return _SECRET_PREFIX + base64.urlsafe_b64encode(nonce + sealed).decode("ascii")


def decrypt_client_secret(ciphertext: str, *, domain_id: str, provider_id: str) -> str:
    """Decrypt only a secret sealed for exactly this domain/provider pair."""
    invalid = DomainAuthUnavailable("Provider secret is unavailable", code="provider_unconfigured")
    if not isinstance(ciphertext, str) or not ciphertext.startswith(_SECRET_PREFIX):
        raise invalid
    try:
        payload = base64.b64decode(ciphertext[len(_SECRET_PREFIX) :].encode("ascii"), altchars=b"-_", validate=True)
        if len(payload) < 13:
            raise invalid
        plain = AESGCM(derive_encryption_subkey(_SECRET_DOMAIN)).decrypt(
            payload[:12], payload[12:], _secret_aad(domain_id, provider_id)
        )
        secret = plain.decode("utf-8")
    except (ValueError, UnicodeDecodeError, binascii.Error, InvalidTag) as exc:
        raise invalid from exc
    if not secret:
        raise invalid
    return secret


# ── provider configuration ──────────────────────────────────────────────────


async def _check_public_url(url: object, *, field: str, resolve: bool = True) -> str:
    """HTTPS-only, credential-free, public-DNS URL accepted by the SSRF policy."""
    if not isinstance(url, str) or not url.strip() or len(url.strip()) > 512:
        raise DomainAuthInvalid(f"{field} must be an HTTPS URL", code="unsafe_url")
    value = url.strip()
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise DomainAuthInvalid(f"{field} is invalid", code="unsafe_url") from exc
    if parsed.scheme != "https" or parsed.fragment or (parsed.query and field in ("issuer_url", "api_url")):
        raise DomainAuthInvalid(f"{field} must be an HTTPS URL without fragment", code="unsafe_url")
    reserved = set()
    if field in ("authorization_url", "authorization_endpoint"):
        reserved = {
            "client_id",
            "redirect_uri",
            "response_type",
            "scope",
            "state",
            "nonce",
            "code_challenge",
            "code_challenge_method",
            "response_mode",
            "request",
            "request_uri",
        }
    elif field in ("token_url", "token_endpoint", "token"):
        reserved = {"client_id", "client_secret", "code", "code_verifier", "grant_type", "redirect_uri"}
    if any(key in reserved for key, _ in parse_qsl(parsed.query, keep_blank_values=True)):
        raise DomainAuthInvalid(f"{field} contains conflicting OAuth parameters", code="unsafe_url")
    try:
        if resolve:
            await asyncio.to_thread(ssrf.validate_url, value)
        else:
            ssrf._parse_and_validate_url(value)
    except ssrf.SsrfBlocked as exc:
        raise DomainAuthInvalid(f"{field} is not a permitted public HTTPS destination", code="unsafe_url") from exc
    return value


def _check_keystone_id(value: object, field: str) -> str:
    if not isinstance(value, str) or not _KEYSTONE_ID_RE.match(value):
        raise DomainAuthInvalid(f"{field} is invalid", code="invalid_keystone_federation")
    return value


def _check_scopes(kind: str, scopes: object) -> list[str]:
    if scopes is None:
        return list(DEFAULT_SCOPES[kind])
    if not isinstance(scopes, (list, tuple)) or not scopes or len(scopes) > _MAX_SCOPES:
        raise DomainAuthInvalid("Scopes are invalid", code="invalid_scopes")
    result: list[str] = []
    for scope in scopes:
        if not isinstance(scope, str) or not _SCOPE_RE.match(scope):
            raise DomainAuthInvalid("Scopes are invalid", code="invalid_scopes")
        if scope not in result:
            result.append(scope)
    missing = [scope for scope in _REQUIRED_SCOPES[kind] if scope not in result]
    if missing:
        raise DomainAuthInvalid(f"Scopes must include {', '.join(missing)}", code="invalid_scopes")
    return result


def _verify_keystone_federation_sync(idp_id: str, protocol_id: str) -> None:
    """Read-only native enabled IdP/protocol check, independent of working scope."""
    from keystoneauth1 import exceptions as ks_exc

    from app.services import keystone
    from app.services.identity_roles import _field

    try:
        ks = keystone._get_admin_ks_client()
        idp = ks.federation.identity_providers.get(idp_id)
        ks.federation.protocols.get(idp_id, protocol_id)
    except ks_exc.NotFound as exc:
        raise DomainAuthInvalid(
            "Keystone identity provider or protocol is not configured", code="idp_not_found"
        ) from exc
    except Exception as exc:
        logger.warning("keystone federation lookup failed: %s", type(exc).__name__)
        raise DomainAuthUnavailable("Keystone federation configuration is unavailable") from exc
    if _field(idp, "enabled") is not True:
        raise DomainAuthInvalid("Keystone identity provider is disabled", code="idp_disabled")


async def _verify_keystone_federation(idp_id: str, protocol_id: str) -> None:
    await asyncio.to_thread(_verify_keystone_federation_sync, idp_id, protocol_id)


def provider_public(row: DomainIdentityProvider) -> dict[str, Any]:
    """Provider metadata only. The client secret is reduced to a configured flag."""
    return {
        "id": row.id,
        "domain_id": row.domain_id,
        "name": row.name,
        "kind": row.kind,
        "issuer_url": row.issuer_url,
        "authorization_url": row.authorization_url,
        "token_url": row.token_url,
        "api_url": row.api_url,
        "client_id": row.client_id,
        "client_secret_configured": bool(row.client_secret_ciphertext),
        "scopes": list(row.scopes or []),
        "keystone_idp_id": row.keystone_idp_id,
        "keystone_protocol_id": row.keystone_protocol_id,
        "enabled": bool(row.enabled),
        "revision": int(row.revision),
        "verified": _usable(row),
        "verified_revision": row.verified_revision,
        "verified_at": row.verified_at.isoformat() if row.verified_at else None,
        "federation_token_type": row.federation_token_type,
        "token_endpoint_auth_method": row.token_endpoint_auth_method,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _check_name(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 64:
        raise DomainAuthInvalid("Provider name must be 1-64 characters", code="invalid_name")
    name = value.strip()
    if any(ord(c) < 32 for c in name):
        raise DomainAuthInvalid("Provider name must be 1-64 characters", code="invalid_name")
    return name


def _check_client_id(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 255:
        raise DomainAuthInvalid("Client ID must be 1-255 characters", code="invalid_client_id")
    client_id = value.strip()
    if any(c.isspace() or ord(c) < 32 for c in client_id):
        raise DomainAuthInvalid("Client ID must be 1-255 characters", code="invalid_client_id")
    return client_id


async def _normalized_endpoints(
    kind: str, fields: dict[str, Any], *, metadata: OidcMetadata | None = None
) -> dict[str, Any]:
    if kind == "oidc":
        if any(fields.get(key) for key in GITHUB_DEFAULTS):
            raise DomainAuthInvalid("OIDC endpoints are discovered from the issuer", code="invalid_endpoints")
        issuer = await _check_public_url(fields.get("issuer_url"), field="issuer_url", resolve=metadata is None)
        if metadata is None:
            async with _provider_client() as client:
                metadata = await _discover(client, issuer)
        method = _select_token_auth(metadata, fields.get("token_endpoint_auth_method"))
        bearer = fields.get("federation_token_type", "id_token")
        if bearer not in ("id_token", "access_token"):
            raise DomainAuthInvalid("Invalid federation token type", code="invalid_federation_token_type")
        if bearer == "access_token" and not metadata.userinfo_endpoint:
            raise DomainAuthInvalid(
                "Access-token federation requires UserInfo subject binding", code="userinfo_required"
            )
        return {
            "issuer_url": issuer,
            "authorization_url": metadata.authorization_endpoint,
            "token_url": metadata.token_endpoint,
            "api_url": None,
            "token_endpoint_auth_method": method,
            "federation_token_type": bearer,
        }
    if fields.get("issuer_url"):
        raise DomainAuthInvalid("GitHub providers do not use an issuer", code="invalid_endpoints")
    result: dict[str, Any] = {
        "issuer_url": None,
        "federation_token_type": "access_token",
        "token_endpoint_auth_method": "client_secret_post",
    }
    for key, default in GITHUB_DEFAULTS.items():
        result[key] = await _check_public_url(fields.get(key) or default, field=key)
    return result


def _provider_allowlist(domain_id: str) -> list[str] | None:
    """Exact domain overrides default; None means unrestricted, [] denies all."""
    auth = getattr(get_settings(), "auth", None)
    if auth is None:
        return None
    methods = auth.domain.get(domain_id)
    if methods is not None and methods.allow_providers is not None:
        return methods.allow_providers
    return auth.default.allow_providers


def _provider_allowed(domain_id: str, provider_id: str) -> bool:
    allowed = _provider_allowlist(domain_id)
    return allowed is None or provider_id.removeprefix(_CONFIG_PROVIDER_PREFIX) in allowed


async def provider_auto_join_allowed(domain_id: str, provider_id: str, email: str) -> bool:
    """Exact configured admission only; never imply account linking permission."""
    auth = getattr(get_settings(), "auth", None)
    if auth is None or not _provider_allowed(domain_id, provider_id):
        return False
    methods = auth.domain.get(domain_id)
    rules = methods.auto_join_email_domains if methods is not None else None
    if rules is None:
        rules = auth.default.auto_join_email_domains
    domains = (rules or {}).get(provider_id.removeprefix(_CONFIG_PROVIDER_PREFIX), [])
    return normalize_email(email).rsplit("@", 1)[1] in domains


def _selected_config_providers(domain_id: str) -> dict[str, Any]:
    """Select independent registry instances without contacting their issuers."""
    auth = getattr(get_settings(), "auth", None)
    if auth is None:
        return {}
    allowed = _provider_allowlist(domain_id)
    keys = dict.fromkeys(auth.providers if allowed is None else allowed)
    return {
        _CONFIG_PROVIDER_PREFIX + key: auth.providers[key]
        for key in keys
        if key in auth.providers and auth.providers[key].enabled
    }


def _config_fingerprint(fields: dict[str, Any]) -> str:
    # Key the fingerprint so public revisions cannot be used to guess weak secrets.
    serialized = json.dumps(fields, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hmac.new(derive_encryption_subkey(_SECRET_DOMAIN), serialized.encode(), hashlib.sha256).hexdigest()


async def _bind_config_discovery(fingerprint: str, metadata: OidcMetadata) -> None:
    """Pin discovery once per issuer/client credential pair, across workers.

    Bootstrap trusts issuer discovery just as SQL creation does. Subsequent
    discovery must not redirect these credentials (including a UserInfo bearer)
    to another public destination. Rotate the secret to establish a new pin.
    This is not a provider verification marker and never authorizes SQL policy.
    """
    key = _CONFIG_BINDING_KEY_PREFIX + fingerprint
    binding = json.dumps(
        [metadata.token_endpoint, metadata.authorization_endpoint, metadata.jwks_uri, metadata.userinfo_endpoint],
        separators=(",", ":"),
    )
    try:
        redis = await _redis()
        await redis.set(key, binding, nx=True)
        current = await redis.get(key)
    except Exception as exc:
        logger.warning("config provider discovery binding failed: %s", type(exc).__name__)
        raise DomainAuthUnavailable("Login state storage is unavailable") from None
    if isinstance(current, bytes):
        current = current.decode("utf-8", errors="replace")
    if current is None:
        raise DomainAuthUnavailable("Login state storage is unavailable")
    if current != binding:
        raise DomainAuthConflict(
            "OIDC credential destination changed; update provider configuration and secret", code="provider_changed"
        )


async def _load_config_provider(domain_id: str, provider_id: str) -> DomainIdentityProvider | None:
    provider = _selected_config_providers(domain_id).get(provider_id)
    if provider is None:
        return None
    fields = {key: getattr(provider, key) for key in _REVISION_FIELDS}
    fields["kind"] = provider.kind
    secret = provider.client_secret.get_secret_value()
    fingerprint_fields = {**fields, "domain_id": domain_id, "id": provider_id, "client_secret": secret}
    organization = provider.organization
    fingerprint_fields["organization"] = organization.model_dump() if organization is not None else None
    discovery_fingerprint = None
    metadata = None
    if provider.kind == "oidc":
        issuer = await _check_public_url(provider.issuer_url, field="issuer_url")
        async with _provider_client() as client:
            metadata = await _discover(client, issuer)
        discovery_fingerprint = _config_fingerprint(
            {"issuer_url": issuer, "client_id": provider.client_id, "client_secret": secret}
        )
        await _bind_config_discovery(discovery_fingerprint, metadata)
    # Reuse the SQL URL/DNS validation and discovery/authentication contract.
    endpoints = await _normalized_endpoints(provider.kind, fields, metadata=metadata)
    if metadata is not None:
        fingerprint_fields["discovery"] = {
            "authorization_endpoint": metadata.authorization_endpoint,
            "jwks_uri": metadata.jwks_uri,
            "userinfo_endpoint": metadata.userinfo_endpoint,
        }
    fingerprint_fields.update(endpoints)
    # Lua cjson defaults to 14 significant digits, even for IEEE754-safe ints.
    # Eleven hex digits stay exact through both decoding and decimal re-encoding.
    revision = int(_config_fingerprint(fingerprint_fields)[:11], 16) or 1
    row = DomainIdentityProvider(
        id=provider_id,
        domain_id=domain_id,
        name=provider.name,
        kind=provider.kind,
        client_id=provider.client_id,
        client_secret_ciphertext=encrypt_client_secret(secret, domain_id=domain_id, provider_id=provider_id),
        scopes=list(provider.scopes),
        keystone_idp_id=provider.keystone_idp_id,
        keystone_protocol_id=provider.keystone_protocol_id,
        enabled=True,
        revision=revision,
        **endpoints,
    )
    row._config_discovery_fingerprint = discovery_fingerprint
    row._organization = organization
    return row


async def list_providers(domain_id: str) -> list[dict[str, Any]]:
    domain_id = _require_domain_id(domain_id)
    try:
        async with _factory()() as session:
            stmt = (
                select(DomainIdentityProvider)
                .where(DomainIdentityProvider.domain_id == domain_id)
                .order_by(DomainIdentityProvider.name, DomainIdentityProvider.id)
            )
            return [provider_public(row) for row in (await session.execute(stmt)).scalars().all()]
    except DomainAuthError:
        raise
    except SQLAlchemyError as exc:
        raise _storage_failure(exc) from exc


async def create_provider(domain_id: str, *, actor_user_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    domain_id = _require_domain_id(domain_id)
    kind = fields.get("kind")
    if kind not in KINDS:
        raise DomainAuthInvalid("Provider kind must be oidc or github", code="invalid_kind")
    name = _check_name(fields.get("name"))
    client_id = _check_client_id(fields.get("client_id"))
    secret = fields.get("client_secret")
    if not isinstance(secret, str) or not secret or len(secret) > 4096:
        raise DomainAuthInvalid("Client secret is required", code="client_secret_required")
    scopes = _check_scopes(kind, fields.get("scopes"))
    idp_id = _check_keystone_id(fields.get("keystone_idp_id"), "keystone_idp_id")
    protocol_id = _check_keystone_id(fields.get("keystone_protocol_id"), "keystone_protocol_id")
    endpoints = await _normalized_endpoints(kind, fields)
    await _verify_keystone_federation(idp_id, protocol_id)
    provider_id = str(uuid4())
    row = DomainIdentityProvider(
        id=provider_id,
        domain_id=domain_id,
        name=name,
        kind=kind,
        client_id=client_id,
        client_secret_ciphertext=encrypt_client_secret(secret, domain_id=domain_id, provider_id=provider_id),
        scopes=scopes,
        keystone_idp_id=idp_id,
        keystone_protocol_id=protocol_id,
        enabled=bool(fields.get("enabled", True)),
        revision=1,
        created_by_user_id=actor_user_id,
        updated_by_user_id=actor_user_id,
        **endpoints,
    )
    try:
        async with _factory()() as session, session.begin():
            session.add(row)
        return provider_public(row)
    except IntegrityError as exc:
        raise DomainAuthConflict("A provider with this name already exists", code="provider_name_conflict") from exc
    except SQLAlchemyError as exc:
        raise _storage_failure(exc) from exc


async def _guard_last_method(
    session: AsyncSession, domain_id: str, providers: list[DomainIdentityProvider], *, removing: str
) -> None:
    policy = _policy_from_row(domain_id, await session.get(DomainLoginPolicy, domain_id))
    if policy.password_enabled:
        return
    if not any(_usable(row) for row in providers if row.id != removing):
        raise DomainAuthConflict(
            "This is the domain's last usable login method; enable password login first", code="last_login_method"
        )


async def update_provider(
    domain_id: str, provider_id: str, *, actor_user_id: str, fields: dict[str, Any]
) -> dict[str, Any]:
    domain_id = _require_domain_id(domain_id)
    try:
        async with _factory()() as session:
            current = await session.get(DomainIdentityProvider, provider_id)
            snapshot = provider_public(current) if current is not None and current.domain_id == domain_id else None
    except SQLAlchemyError as exc:
        raise _storage_failure(exc) from exc
    if snapshot is None:
        raise DomainAuthNotFound("Provider not found", code="provider_not_found")
    kind = snapshot["kind"]
    if "kind" in fields and fields["kind"] != kind:
        raise DomainAuthInvalid("Provider kind cannot be changed", code="kind_immutable")
    changes: dict[str, Any] = {}
    if "name" in fields:
        changes["name"] = _check_name(fields["name"])
    if "client_id" in fields:
        changes["client_id"] = _check_client_id(fields["client_id"])
    if "scopes" in fields:
        changes["scopes"] = _check_scopes(kind, fields["scopes"])
    if "enabled" in fields:
        if not isinstance(fields["enabled"], bool):
            raise DomainAuthInvalid("enabled must be a boolean", code="invalid_enabled")
        changes["enabled"] = fields["enabled"]
    endpoint_keys = ("issuer_url", *GITHUB_DEFAULTS)
    option_keys = ("federation_token_type", "token_endpoint_auth_method")
    if any(key in fields for key in (*endpoint_keys, *option_keys)):
        merged = {key: fields.get(key, snapshot[key]) for key in (*endpoint_keys, *option_keys)}
        if kind == "oidc":
            if any(fields.get(key) for key in GITHUB_DEFAULTS):
                raise DomainAuthInvalid("OIDC endpoints are discovered from the issuer", code="invalid_endpoints")
            for key in GITHUB_DEFAULTS:
                merged.pop(key, None)
        changes.update(await _normalized_endpoints(kind, merged))
    federation_changed = False
    for key in ("keystone_idp_id", "keystone_protocol_id"):
        if key in fields:
            changes[key] = _check_keystone_id(fields[key], key)
            federation_changed = federation_changed or changes[key] != snapshot[key]
    if federation_changed:
        await _verify_keystone_federation(
            changes.get("keystone_idp_id", snapshot["keystone_idp_id"]),
            changes.get("keystone_protocol_id", snapshot["keystone_protocol_id"]),
        )
    secret = fields.get("client_secret")
    if secret is not None and (not isinstance(secret, str) or not secret or len(secret) > 4096):
        raise DomainAuthInvalid("Client secret must be 1-4096 characters", code="client_secret_required")
    expected_revision = fields.get("revision")
    try:
        async with _factory()() as session, session.begin():
            providers = await _locked_domain_providers(session, domain_id)
            row = next((p for p in providers if p.id == provider_id), None)
            if row is None:
                raise DomainAuthNotFound("Provider not found", code="provider_not_found")
            # Validation outside the lock used this exact snapshot; never merge
            # endpoints into a concurrently changed credential configuration.
            if row.revision != snapshot["revision"] or (
                expected_revision is not None and expected_revision != row.revision
            ):
                raise DomainAuthConflict("Provider changed; reload and retry", code="revision_conflict")
            destination_changed = any(
                key in changes and changes[key] != getattr(row, key) for key in ("issuer_url", "token_url")
            )
            if destination_changed and secret is None:
                raise DomainAuthInvalid(
                    "Changing the credential destination requires a replacement client secret",
                    code="client_secret_replacement_required",
                )
            security_change = secret is not None or any(
                key in changes and changes[key] != getattr(row, key) for key in _REVISION_FIELDS
            )
            if security_change and _usable(row):
                await _guard_last_method(session, domain_id, providers, removing=row.id)
            for key, value in changes.items():
                setattr(row, key, value)
            if secret is not None:
                row.client_secret_ciphertext = encrypt_client_secret(secret, domain_id=domain_id, provider_id=row.id)
            if security_change:
                row.revision = int(row.revision) + 1
                row.verified_revision = None
                row.verified_at = None
            row.updated_by_user_id = actor_user_id
            await session.flush()
            result = provider_public(row)
        return result
    except DomainAuthError:
        raise
    except IntegrityError as exc:
        raise DomainAuthConflict("A provider with this name already exists", code="provider_name_conflict") from exc
    except SQLAlchemyError as exc:
        raise _storage_failure(exc) from exc


async def delete_provider(domain_id: str, provider_id: str) -> None:
    domain_id = _require_domain_id(domain_id)
    try:
        async with _factory()() as session, session.begin():
            providers = await _locked_domain_providers(session, domain_id)
            row = next((p for p in providers if p.id == provider_id), None)
            if row is None:
                raise DomainAuthNotFound("Provider not found", code="provider_not_found")
            await _guard_last_method(session, domain_id, providers, removing=row.id)
            await session.delete(row)
    except DomainAuthError:
        raise
    except SQLAlchemyError as exc:
        raise _storage_failure(exc) from exc


async def _load_provider(domain_id: str, provider_id: str) -> DomainIdentityProvider | None:
    if not isinstance(provider_id, str) or not provider_id or len(provider_id) > 36:
        return None
    if provider_id.startswith(_CONFIG_PROVIDER_PREFIX):
        # Configuration is additive, not a policy-storage outage bypass. Exercise
        # the SQL provider read too, so table/read failures retain their 503.
        try:
            async with _factory()() as session:
                await session.execute(
                    select(DomainIdentityProvider.id).where(DomainIdentityProvider.domain_id == domain_id).limit(1)
                )
        except SQLAlchemyError as exc:
            raise _storage_failure(exc) from exc
        return await _load_config_provider(domain_id, provider_id)
    try:
        async with _factory()() as session:
            row = await session.get(DomainIdentityProvider, provider_id)
    except SQLAlchemyError as exc:
        raise _storage_failure(exc) from exc
    if row is None or row.domain_id != domain_id or not _provider_allowed(domain_id, provider_id):
        return None
    return row


async def require_provider(domain_id: str, provider_id: str, revision: int, email: str) -> DomainIdentityProvider:
    """Session refresh authority for a provider-bound session (fail closed)."""
    domain_id = _require_domain_id(domain_id)
    row = await _load_provider(domain_id, provider_id)
    if row is None or not _configured(row):
        raise DomainAuthDenied("Login provider is disabled or removed", code="provider_disabled")
    if not isinstance(revision, int) or int(row.revision) != revision:
        raise DomainAuthDenied("Login provider configuration changed", code="provider_changed")
    enforce_email(await get_policy(domain_id), email)
    return row


# ── public methods / domain resolution ──────────────────────────────────────


def _http_to_domain_error(exc: HTTPException) -> DomainAuthError:
    if exc.status_code == 404:
        return DomainAuthNotFound("Domain not found", code="domain_not_found")
    if exc.status_code == 403:
        return DomainAuthDenied("Domain is disabled", code="domain_disabled")
    if exc.status_code == 409:
        return DomainAuthConflict("Domain display name is ambiguous; use the domain ID", code="domain_ambiguous")
    if exc.status_code == 400:
        return DomainAuthInvalid("An explicit domain is required", code="domain_required")
    return DomainAuthUnavailable("Domain lookup is unavailable")


async def resolve_enabled_domain(name_or_id: str) -> dict[str, Any]:
    from app.services import domain_scope

    try:
        return await asyncio.to_thread(domain_scope.resolve_domain, name_or_id)
    except HTTPException as exc:
        raise _http_to_domain_error(exc) from None
    except Exception as exc:
        logger.warning("domain resolution failed: %s", type(exc).__name__)
        raise DomainAuthUnavailable("Domain lookup is unavailable") from None


def _enabled_login_domains(origin_ids: set[str], default_origin: str | None) -> dict[str, str]:
    """Validate complete inventory, but hydrate only explicitly configured origins.

    Common registrations belong to the server's original user domain, exact
    domain overrides and eligible SQL owners, not every new personal home.
    Inspect collection metadata before an SDK can discard truncation hints.
    """
    from app.services.domain_display import display_name
    from app.services.domain_scope import resolve_domain
    from app.services.identity_roles import _field
    from app.services.native_operation import NativeOperation

    try:
        with NativeOperation() as operation:
            manager = operation.ks.domains
            transport = getattr(manager, "client", None)
            if transport is not None and callable(getattr(transport, "get", None)):
                _, body = transport.get("/domains")
                if not isinstance(body, dict) or not isinstance(body.get("domains"), list):
                    raise ValueError("Invalid domain inventory")
                links = body.get("links")
                if not isinstance(links, dict) or links.get("next") or body.get("truncated") or body.get("limited"):
                    raise ValueError("Incomplete domain inventory")
                rows = body["domains"]
            else:
                rows = manager.list()
                links = getattr(rows, "links", {})
                if (
                    getattr(rows, "truncated", False)
                    or getattr(rows, "limited", False)
                    or getattr(rows, "next", None)
                    or (isinstance(links, dict) and links.get("next"))
                ):
                    raise ValueError("Incomplete domain inventory")
            origin_ids = set(origin_ids)
            if default_origin:
                try:
                    default = resolve_domain(default_origin, operation=operation)
                except HTTPException as exc:
                    if exc.status_code not in (403, 404):
                        raise
                else:
                    origin_ids.add(default["id"])
            ids, enabled = set(), {}
            for row in rows:
                domain_id = _field(row, "id")
                if not isinstance(domain_id, str) or not domain_id or len(domain_id) > 64 or domain_id in ids:
                    raise ValueError("Invalid domain identity")
                ids.add(domain_id)
                if domain_id not in origin_ids:
                    continue
                domain = operation.get("domains", domain_id)
                if _field(row, "enabled") is True and _field(domain, "enabled") is True:
                    enabled[domain_id] = display_name(domain)
            return dict(sorted(enabled.items()))
    except Exception as exc:
        logger.warning("login domain inventory failed: %s", type(exc).__name__)
        raise DomainAuthUnavailable("Domain directory is unavailable or incomplete") from None


def _public_providers(domain_id: str, rows) -> list[dict[str, str]]:
    """Offer configured instances, not only verified ones; never load discovery."""
    configured = [
        {"id": provider_id, "name": provider.name, "kind": provider.kind}
        for provider_id, provider in _selected_config_providers(domain_id).items()
    ]
    providers = configured + [{"id": row.id, "name": row.name, "kind": row.kind} for row in rows if _configured(row)]
    allowed = _provider_allowlist(domain_id)
    if allowed is not None:
        available = {provider["id"].removeprefix(_CONFIG_PROVIDER_PREFIX): provider for provider in providers}
        providers = [available[key] for key in dict.fromkeys(allowed) if key in available]
    return providers


async def login_options() -> dict[str, Any]:
    """Public registrations at explicit origins, never multiplied by personal homes."""
    try:
        async with _factory()() as session:
            stmt = (
                select(DomainIdentityProvider)
                .where(DomainIdentityProvider.enabled.is_(True))
                .order_by(DomainIdentityProvider.name, DomainIdentityProvider.id)
            )
            rows = [
                row
                for row in (await session.execute(stmt)).scalars().all()
                if _configured(row) and _provider_allowed(row.domain_id, row.id)
            ]
    except DomainAuthError:
        raise
    except SQLAlchemyError as exc:
        raise _storage_failure(exc) from exc
    settings = get_settings()
    auth = getattr(settings, "auth", None)
    origin_ids = {row.domain_id for row in rows}
    if auth is not None:
        origin_ids.update(auth.domain)
    domains = await asyncio.to_thread(
        _enabled_login_domains, origin_ids, getattr(settings, "os_user_domain_name", None)
    )
    by_domain: dict[str, list[DomainIdentityProvider]] = {domain_id: [] for domain_id in domains}
    for row in rows:
        if row.domain_id in by_domain:
            by_domain[row.domain_id].append(row)
    return {
        "providers": [
            {**provider, "domain_id": domain_id, "domain_name": domains[domain_id]}
            for domain_id, rows in by_domain.items()
            for provider in _public_providers(domain_id, rows)
        ]
    }


async def public_methods(domain_id: str) -> dict[str, Any]:
    """Configured login methods offered for this domain, including testable unverified providers."""
    domain_id = _require_domain_id(domain_id)
    try:
        async with _factory()() as session:
            policy = _policy_from_row(domain_id, await session.get(DomainLoginPolicy, domain_id))
            stmt = (
                select(DomainIdentityProvider)
                .where(DomainIdentityProvider.domain_id == domain_id, DomainIdentityProvider.enabled.is_(True))
                .order_by(DomainIdentityProvider.name, DomainIdentityProvider.id)
            )
            rows = (await session.execute(stmt)).scalars().all()
    except DomainAuthError:
        raise
    except SQLAlchemyError as exc:
        raise _storage_failure(exc) from exc
    providers = _public_providers(domain_id, rows)
    return {
        "password_enabled": policy.password_enabled,
        "providers": providers,
        "signup_enabled": bool(policy.signup_enabled and policy.signup_email_domains and smtp_configured()),
    }


async def resolve_login_domain(name_or_id: str) -> dict[str, Any]:
    domain = await resolve_enabled_domain(name_or_id)
    methods = await public_methods(domain["id"])
    return {"domain_id": domain["id"], "domain_name": domain["name"], **methods}


# ── outbound IdP HTTP (SSRF-pinned, no redirects) ───────────────────────────


def _provider_transport() -> httpx.AsyncBaseTransport:
    return ssrf.SafeAsyncTransport(max_response_bytes=_MAX_RESPONSE_BYTES)


def _provider_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=_provider_transport(), timeout=_HTTP_TIMEOUT, follow_redirects=False)


async def _provider_json(
    client: httpx.AsyncClient, method: str, url: str, *, what: str, **kwargs: Any
) -> dict[str, Any] | list[Any]:
    await _check_public_url(url, field=what, resolve=False)
    try:
        response = await client.request(method, url, **kwargs)
    except ssrf.SsrfBlocked as exc:
        raise DomainAuthProviderError(f"{what} is not a permitted destination", code="unsafe_url") from exc
    except httpx.HTTPError as exc:
        logger.warning("identity provider %s request failed: %s", what, type(exc).__name__)
        raise DomainAuthProviderError(f"Identity provider {what} request failed") from exc
    if response.status_code != 200:
        logger.warning("identity provider %s returned HTTP %s", what, response.status_code)
        raise DomainAuthProviderError(f"Identity provider {what} request was rejected")
    try:
        return response.json()
    except ValueError as exc:
        raise DomainAuthProviderError(f"Identity provider {what} response is invalid") from exc


@dataclass(frozen=True)
class OidcMetadata:
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    userinfo_endpoint: str | None
    token_auth_methods: tuple[str, ...]


async def _discover(client: httpx.AsyncClient, issuer: str) -> OidcMetadata:
    url = issuer.rstrip("/") + "/.well-known/openid-configuration"
    doc = await _provider_json(client, "GET", url, what="discovery", headers={"Accept": "application/json"})
    if not isinstance(doc, dict) or doc.get("issuer") != issuer:
        raise DomainAuthProviderError("OIDC discovery issuer does not match configuration")
    methods = doc.get("code_challenge_methods_supported")
    if methods is not None and (not isinstance(methods, list) or "S256" not in methods):
        raise DomainAuthProviderError("OIDC provider does not support PKCE S256")
    auth_methods = doc.get("token_endpoint_auth_methods_supported", ["client_secret_basic"])
    if not isinstance(auth_methods, list) or not all(isinstance(method, str) for method in auth_methods):
        raise DomainAuthProviderError("OIDC token authentication metadata is invalid")
    if not set(auth_methods).intersection({"client_secret_basic", "client_secret_post"}):
        raise DomainAuthInvalid("OIDC token authentication method is unsupported", code="unsupported_token_auth_method")
    endpoints = {}
    for key in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
        endpoints[key] = await _check_public_url(doc.get(key), field=key, resolve=key == "authorization_endpoint")
    userinfo = doc.get("userinfo_endpoint")
    userinfo = await _check_public_url(userinfo, field="userinfo_endpoint", resolve=False) if userinfo else None
    return OidcMetadata(issuer=issuer, userinfo_endpoint=userinfo, token_auth_methods=tuple(auth_methods), **endpoints)


def _select_token_auth(metadata: OidcMetadata, selected: str | None) -> str:
    if selected is not None:
        if selected not in ("client_secret_basic", "client_secret_post") or selected not in metadata.token_auth_methods:
            raise DomainAuthInvalid("Token authentication method is unsupported", code="unsupported_token_auth_method")
        return selected
    return next(
        method for method in ("client_secret_basic", "client_secret_post") if method in metadata.token_auth_methods
    )


def _check_discovery_binding(row: DomainIdentityProvider, metadata: OidcMetadata) -> None:
    # Discovery can change without a manager PATCH. Never send stored credentials
    # to a newly advertised destination; a replacement secret must be supplied.
    if row.token_url != metadata.token_endpoint:
        raise DomainAuthConflict("OIDC token endpoint changed; update provider credentials", code="provider_changed")
    _select_token_auth(metadata, row.token_endpoint_auth_method)


def require_same_site_browser(request: Any) -> None:
    """Lax browser binding requires same-site fetches, not just CORS permission.

    Same-host deployments (ports may differ) are deterministic without a public
    suffix database. For subdomains the browser's Fetch Metadata is authoritative:
    only an exact configured frontend Origin and a same-site declaration pass.
    Genuinely cross-site deployments must use a first-party reverse proxy.
    """
    frontend = urlsplit(_redirect_uri())
    api = urlsplit(getattr(get_settings(), "public_api_base", "") or str(request.base_url))
    origin = request.headers.get("origin")
    try:
        expected_origin = (
            frontend.scheme,
            frontend.hostname,
            frontend.port or (443 if frontend.scheme == "https" else 80),
        )
        if origin:
            source = urlsplit(origin)
            actual_origin = (source.scheme, source.hostname, source.port or (443 if source.scheme == "https" else 80))
            if actual_origin != expected_origin:
                raise DomainAuthDenied("Browser origin does not match the configured frontend", code="origin_mismatch")
        same_host = frontend.scheme == api.scheme and frontend.hostname == api.hostname
        fetch_site = request.headers.get("sec-fetch-site", "")
        if fetch_site == "cross-site" or (
            not same_host and (not origin or fetch_site not in ("same-origin", "same-site"))
        ):
            raise DomainAuthUnavailable(
                "Provider login requires same-site frontend/API URLs or a first-party API proxy",
                code="cross_site_callback_unsupported",
            )
    except ValueError:
        raise DomainAuthUnavailable(
            "Frontend/API URL configuration is invalid", code="redirect_not_configured"
        ) from None


def _redirect_uri() -> str:
    settings = get_settings()
    base = (getattr(settings, "frontend_base_url", "") or "").strip().rstrip("/")
    parsed = urlsplit(base)
    production = os.environ.get("AFTERGLOW_ENV", "development").strip().lower() == "production"
    if (
        not base
        or parsed.scheme not in ("https", "http")
        or (production and parsed.scheme != "https")
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise DomainAuthUnavailable("Frontend callback URL is not configured", code="redirect_not_configured")
    return f"{base}/auth/callback"


def cookie_secure() -> bool:
    settings = get_settings()
    return (
        os.environ.get("AFTERGLOW_ENV", "development").strip().lower() == "production"
        or urlsplit(getattr(settings, "public_api_base", "") or "").scheme == "https"
    )


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _pkce_challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")


async def _redis():
    from app.services import cache

    return await cache._get_redis()


@dataclass(frozen=True)
class AuthorizationStart:
    authorize_url: str
    browser_binding: str


async def start_authorization(domain_id: str, provider_id: str) -> AuthorizationStart:
    """Create one-use state bound to browser, domain, provider and its revision."""
    domain = await resolve_enabled_domain(domain_id)
    if domain["id"] != domain_id:
        raise DomainAuthNotFound("Domain not found", code="domain_not_found")
    row = await _load_provider(domain_id, provider_id)
    if row is None or not _configured(row):
        raise DomainAuthNotFound("Login provider not found", code="provider_not_found")
    redirect_uri = _redirect_uri()
    if row.kind == "oidc":
        async with _provider_client() as client:
            metadata = await _discover(client, row.issuer_url or "")
        _check_discovery_binding(row, metadata)
        if fingerprint := getattr(row, "_config_discovery_fingerprint", None):
            await _bind_config_discovery(fingerprint, metadata)
        authorize_endpoint = metadata.authorization_endpoint
    else:
        authorize_endpoint = await _check_public_url(row.authorization_url, field="authorization_url", resolve=False)
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    binding = secrets.token_urlsafe(32)
    record = {
        "domain_id": domain_id,
        "provider_id": row.id,
        "revision": int(row.revision),
        "nonce": nonce,
        "code_verifier": verifier,
        "browser": _digest(binding),
        "redirect_uri": redirect_uri,
    }
    try:
        stored = await (await _redis()).set(
            _STATE_KEY_PREFIX + _digest(state), json.dumps(record), ex=STATE_TTL_SECONDS, nx=True
        )
    except Exception as exc:
        logger.warning("provider authorization state storage failed: %s", type(exc).__name__)
        raise DomainAuthUnavailable("Login state storage is unavailable") from None
    if not stored:
        raise DomainAuthUnavailable("Login state storage is unavailable")
    params = {
        "client_id": row.client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(row.scopes or DEFAULT_SCOPES[row.kind]),
        "state": state,
        "code_challenge": _pkce_challenge(verifier),
        "code_challenge_method": "S256",
    }
    if row.kind == "oidc":
        params["nonce"] = nonce
    separator = "&" if urlsplit(authorize_endpoint).query else "?"
    return AuthorizationStart(
        authorize_url=f"{authorize_endpoint}{separator}{urlencode(params)}", browser_binding=binding
    )


async def _consume_state(state: str, browser_binding: str) -> dict[str, Any]:
    invalid = DomainAuthUnauthenticated("Login state is invalid or expired", code="invalid_state")
    if not isinstance(state, str) or not 16 <= len(state) <= 256:
        raise invalid
    if not isinstance(browser_binding, str) or not browser_binding or len(browser_binding) > 256:
        raise invalid
    try:
        raw = await (await _redis()).getdel(_STATE_KEY_PREFIX + _digest(state))
    except Exception as exc:
        logger.warning("provider authorization state lookup failed: %s", type(exc).__name__)
        raise DomainAuthUnavailable("Login state storage is unavailable") from None
    if not raw:
        raise invalid
    try:
        record = json.loads(raw)
    except (TypeError, ValueError):
        raise invalid from None
    if not isinstance(record, dict) or not hmac.compare_digest(
        str(record.get("browser", "")), _digest(browser_binding)
    ):
        raise invalid
    return record


@dataclass(frozen=True)
class VerifiedIdentity:
    email: str
    bearer: str  # token presented to Keystone OS-FEDERATION (ID token or OAuth access token)
    issuer: str
    subject: str


async def _exchange_code(
    client: httpx.AsyncClient, row: DomainIdentityProvider, token_endpoint: str, code: str, record: dict[str, Any]
) -> dict[str, Any]:
    secret = decrypt_client_secret(row.client_secret_ciphertext, domain_id=row.domain_id, provider_id=row.id)
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": record["redirect_uri"],
        "code_verifier": record["code_verifier"],
    }
    method = row.token_endpoint_auth_method or "client_secret_basic"
    auth = None
    if method == "client_secret_basic":
        # RFC6749 §2.3.1 requires form encoding each credential before Basic.
        auth = httpx.BasicAuth(quote_plus(row.client_id), quote_plus(secret))
    elif method == "client_secret_post":
        data.update(client_id=row.client_id, client_secret=secret)
    else:
        raise DomainAuthInvalid("Unsupported token authentication method", code="unsupported_token_auth_method")
    payload = await _provider_json(
        client, "POST", token_endpoint, what="token", headers={"Accept": "application/json"}, data=data, auth=auth
    )
    if (
        not isinstance(payload, dict)
        or payload.get("error")
        or not isinstance(payload.get("access_token"), str)
        or not payload["access_token"]
    ):
        raise DomainAuthProviderError("Identity provider rejected the authorization code")
    return payload


def _verified_flag(value: object) -> bool:
    return value is True


async def _verify_id_token(
    client: httpx.AsyncClient, row: DomainIdentityProvider, metadata: OidcMetadata, id_token: object, nonce: str
) -> dict[str, Any]:
    if not isinstance(id_token, str) or id_token.count(".") != 2:
        raise DomainAuthProviderError("Identity provider did not return a signed ID token", code="invalid_id_token")
    try:
        header = jwt.get_unverified_header(id_token)
    except jwt.PyJWTError as exc:
        raise DomainAuthProviderError("ID token is malformed", code="invalid_id_token") from exc
    alg = header.get("alg")
    if alg not in _ALLOWED_JWT_ALGORITHMS:
        raise DomainAuthProviderError("ID token algorithm is not allowed", code="invalid_id_token")
    jwks = await _provider_json(client, "GET", metadata.jwks_uri, what="jwks", headers={"Accept": "application/json"})
    try:
        keyset = jwt.PyJWKSet.from_dict(jwks if isinstance(jwks, dict) else {})
    except jwt.PyJWTError as exc:
        raise DomainAuthProviderError("Identity provider signing keys are invalid", code="invalid_id_token") from exc
    kid = header.get("kid")
    key_type = _JWT_KEY_TYPES[alg]
    candidates = [
        key
        for key in keyset.keys
        if (kid is None or key.key_id == kid)
        and key.key_type == key_type
        and getattr(key, "public_key_use", None) in (None, "sig")
    ]
    if len(candidates) != 1:
        raise DomainAuthProviderError("ID token signing key is not uniquely identified", code="invalid_id_token")
    try:
        claims = jwt.decode(
            id_token,
            candidates[0].key,
            algorithms=[alg],
            audience=row.client_id,
            issuer=metadata.issuer,
            leeway=_JWT_LEEWAY_SECONDS,
            options={"require": ["exp", "iat", "iss", "aud", "sub", "nonce"]},
        )
    except (jwt.PyJWTError, TypeError, ValueError) as exc:
        raise DomainAuthProviderError("ID token verification failed", code="invalid_id_token") from exc
    aud = claims.get("aud")
    if isinstance(aud, list) and len(aud) > 1 and claims.get("azp") != row.client_id:
        raise DomainAuthProviderError("ID token authorized party mismatch", code="invalid_id_token")
    if "azp" in claims and claims.get("azp") != row.client_id:
        raise DomainAuthProviderError("ID token authorized party mismatch", code="invalid_id_token")
    token_nonce = claims.get("nonce")
    if not isinstance(token_nonce, str) or not hmac.compare_digest(token_nonce, nonce):
        raise DomainAuthProviderError("ID token nonce mismatch", code="invalid_id_token")
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject or len(subject) > 255 or any(ord(c) < 32 for c in subject):
        raise DomainAuthProviderError("ID token subject is invalid", code="invalid_id_token")
    return claims


async def _oidc_identity(
    client: httpx.AsyncClient, row: DomainIdentityProvider, code: str, record: dict[str, Any]
) -> VerifiedIdentity:
    metadata = await _discover(client, row.issuer_url or "")
    _check_discovery_binding(row, metadata)
    if fingerprint := getattr(row, "_config_discovery_fingerprint", None):
        await _bind_config_discovery(fingerprint, metadata)
    tokens = await _exchange_code(client, row, metadata.token_endpoint, code, record)
    claims = await _verify_id_token(client, row, metadata, tokens.get("id_token"), record["nonce"])
    email, verified = claims.get("email"), claims.get("email_verified")
    forward_access = row.federation_token_type == "access_token"
    if forward_access or (not email and metadata.userinfo_endpoint):
        if not metadata.userinfo_endpoint:
            raise DomainAuthProviderError(
                "Access token cannot be bound to the verified subject", code="invalid_id_token"
            )
        info = await _provider_json(
            client,
            "GET",
            metadata.userinfo_endpoint,
            what="userinfo",
            headers={"Authorization": f"Bearer {tokens['access_token']}", "Accept": "application/json"},
        )
        if not isinstance(info, dict) or info.get("sub") != claims.get("sub"):
            raise DomainAuthProviderError("UserInfo subject does not match the ID token", code="invalid_id_token")
        if not email:
            email, verified = info.get("email"), info.get("email_verified")
    if not email or not _verified_flag(verified):
        raise DomainAuthDenied("The identity provider did not verify this email", code="email_not_verified")
    bearer = tokens["access_token"] if forward_access else tokens["id_token"]
    return VerifiedIdentity(email=normalize_email(email), bearer=bearer, issuer=metadata.issuer, subject=claims["sub"])


async def _github_identity(
    client: httpx.AsyncClient, row: DomainIdentityProvider, code: str, record: dict[str, Any]
) -> VerifiedIdentity:
    token_url = await _check_public_url(row.token_url, field="token_url", resolve=False)
    tokens = await _exchange_code(client, row, token_url, code, record)
    api = (row.api_url or "").rstrip("/")
    emails = await _provider_json(
        client,
        "GET",
        f"{api}/user/emails",
        what="emails",
        headers={
            "Authorization": f"Bearer {tokens['access_token']}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    primary = [
        item
        for item in (emails if isinstance(emails, list) else [])
        if isinstance(item, dict) and item.get("primary") is True
    ]
    if len(primary) != 1 or primary[0].get("verified") is not True or not primary[0].get("email"):
        raise DomainAuthDenied("GitHub primary email is not verified", code="email_not_verified")
    account = await _provider_json(
        client,
        "GET",
        f"{api}/user",
        what="account",
        headers={"Authorization": f"Bearer {tokens['access_token']}", "Accept": "application/vnd.github+json"},
    )
    subject = account.get("id") if isinstance(account, dict) else None
    if type(subject) is not int or subject <= 0:
        raise DomainAuthProviderError("GitHub account subject is invalid")
    return VerifiedIdentity(
        email=normalize_email(primary[0]["email"]), bearer=tokens["access_token"], issuer=api, subject=str(subject)
    )


@dataclass(frozen=True)
class FederatedLogin:
    unscoped_token: str
    user_id: str
    username: str
    domain_id: str
    domain_name: str
    provider_id: str
    provider_revision: int
    provider_kind: str
    login_email: str


def _keystone_client() -> httpx.AsyncClient:
    settings = get_settings()
    return httpx.AsyncClient(timeout=30, verify=settings.ssl_verify, follow_redirects=False)


async def _revoke_quietly(token: str) -> None:
    from app.services import keystone

    try:
        await asyncio.to_thread(keystone.revoke_token, token)
    except Exception:
        logger.warning("failed to revoke rejected federated token", exc_info=False)


async def keystone_federate(row: DomainIdentityProvider, bearer: str) -> tuple[str, dict[str, Any]]:
    """Native Keystone OS-FEDERATION exchange; Keystone remains the identity authority."""
    settings = get_settings()
    idp_id = _check_keystone_id(row.keystone_idp_id, "keystone_idp_id")
    protocol_id = _check_keystone_id(row.keystone_protocol_id, "keystone_protocol_id")
    url = f"{settings.os_auth_url}/OS-FEDERATION/identity_providers/{idp_id}/protocols/{protocol_id}/auth"
    try:
        async with _keystone_client() as client:
            response = await client.post(url, headers={"Authorization": f"Bearer {bearer}"})
    except httpx.HTTPError as exc:
        logger.warning("keystone federation request failed: %s", type(exc).__name__)
        raise DomainAuthUnavailable("Keystone federation is unavailable") from None
    if response.status_code in (401, 403):
        raise DomainAuthDenied("Keystone federation rejected this identity", code="federation_denied")
    if response.status_code != 201 and response.status_code != 200:
        logger.warning("keystone federation returned HTTP %s", response.status_code)
        raise DomainAuthUnavailable("Keystone federation is unavailable")
    token = response.headers.get("X-Subject-Token", "")
    try:
        user = response.json().get("token", {}).get("user", {})
    except (ValueError, AttributeError):
        user = None
    if not token or not isinstance(user, dict):
        if token:
            await _revoke_quietly(token)
        raise DomainAuthUnavailable("Keystone federation response is invalid")
    return token, user


def _require_stable_native_mapping(ks, row) -> None:
    """Refuse mutable-name/email provisioning before native authentication."""
    from app.services.identity_roles import _field

    try:
        idp = ks.federation.identity_providers.get(row.keystone_idp_id)
        protocol = ks.federation.protocols.get(row.keystone_idp_id, row.keystone_protocol_id)
        mapping_id = _field(protocol, "mapping_id")
        mapping = ks.federation.mappings.get(mapping_id) if mapping_id else None
    except Exception as exc:
        logger.warning("native stable subject mapping lookup failed: %s", type(exc).__name__)
        raise DomainAuthUnavailable(
            "Native stable-subject mapping is unavailable", code="native_mapping_unsafe"
        ) from None
    if _field(idp, "enabled") is not True:
        raise DomainAuthDenied("Native identity provider is disabled", code="idp_disabled")
    rules = _field(mapping, "rules", [])
    attributes = {"OIDC-sub", "OIDC_CLAIM_sub", "HTTP_OIDC_SUB", "HTTP_OIDC_CLAIM_SUB", "sub"}
    if row.kind == "github":
        attributes |= {"HTTP_X_GITHUB_ID", "GITHUB_ID", "github_id", "id"}
    invalid = DomainAuthUnavailable(
        "Native mapping must use an immutable user-only subject and omit email/grants", code="native_mapping_unsafe"
    )
    if not isinstance(rules, list) or not rules:
        raise invalid
    for rule in rules:
        if not isinstance(rule, dict):
            raise invalid
        local, remote = rule.get("local"), rule.get("remote")
        if not isinstance(local, list) or not isinstance(remote, list):
            raise invalid
        if len(local) != 1 or not isinstance(local[0], dict) or set(local[0]) != {"user"}:
            raise invalid
        user = local[0]["user"]
        if not isinstance(user, dict):
            raise invalid
        index = re.fullmatch(r"\{([0-9]+)\}", str(user.get("id", "")))
        if (
            index is None
            or user.get("type", "ephemeral") != "ephemeral"
            or not set(user) <= {"id", "name", "type", "domain"}
        ):
            raise invalid
        position = int(index[1])
        if (
            position >= len(remote)
            or not isinstance(remote[position], dict)
            or any(not isinstance(value, dict) or set(value) != {"type"} for value in remote[:position])
        ):
            raise invalid
        attribute = remote[position]
        if attribute.get("type") not in attributes or set(attribute) != {"type"}:
            raise invalid


async def _current_provider(domain_id: str, provider_id: str, revision: int):
    row = await _load_provider(domain_id, provider_id)
    if row is None or not _configured(row):
        raise DomainAuthDenied("Login provider is disabled or removed", code="provider_disabled")
    if int(row.revision) != revision:
        raise DomainAuthConflict("Login provider changed; start login again", code="provider_changed")
    return row


async def _link_ticket(row, identity: VerifiedIdentity, user, browser_binding: str) -> str:
    from app.services.identity_roles import _field

    ticket = secrets.token_urlsafe(32)
    nonce = os.urandom(12)
    record = {
        "browser": _digest(browser_binding),
        "domain_id": row.domain_id,
        "provider_id": row.id,
        "revision": int(row.revision),
        "user_id": _field(user, "id"),
        "identity_domain_id": _field(user, "domain_id"),
        "email": identity.email,
        "issuer": identity.issuer,
        "subject": identity.subject,
        "bearer": identity.bearer,
    }
    key = derive_encryption_subkey(b"domain_idp_link_ticket")
    encrypted = AESGCM(key).encrypt(nonce, json.dumps(record).encode(), _digest(ticket).encode())
    try:
        await (await _redis()).set(
            "afterglow:domain_auth:link:" + _digest(ticket),
            base64.urlsafe_b64encode(nonce + encrypted).decode(),
            ex=STATE_TTL_SECONDS,
            nx=True,
        )
    except Exception:
        raise DomainAuthUnavailable("Account linking storage is unavailable") from None
    return ticket


async def _consume_link_ticket(ticket: str, browser_binding: str) -> dict:
    invalid = DomainAuthUnauthenticated("Account link is invalid or expired", code="invalid_link_token")
    if not isinstance(ticket, str) or not 16 <= len(ticket) <= 256 or not browser_binding:
        raise invalid
    try:
        raw = await (await _redis()).getdel("afterglow:domain_auth:link:" + _digest(ticket))
    except Exception:
        raise DomainAuthUnavailable("Account linking storage is unavailable") from None
    if not raw:
        raise invalid
    try:
        sealed = base64.urlsafe_b64decode(raw)
        record = json.loads(
            AESGCM(derive_encryption_subkey(b"domain_idp_link_ticket")).decrypt(
                sealed[:12], sealed[12:], _digest(ticket).encode()
            )
        )
    except (ValueError, TypeError, InvalidTag, binascii.Error):
        raise invalid from None
    if not isinstance(record, dict) or not hmac.compare_digest(record.get("browser", ""), _digest(browser_binding)):
        raise invalid
    return record


async def _canonical_federation(row, identity, user, domain, *, ks) -> FederatedLogin:
    from app.services.identity_roles import _field

    canonical_email = normalize_email(_field(user, "email")).casefold()
    canonical_id, canonical_home = _field(user, "id"), _field(user, "domain_id")
    unscoped, native = await keystone_federate(row, identity.bearer)
    raw_federation = native.get("OS-FEDERATION")
    mismatch = False
    if raw_federation is not None:
        federation = raw_federation if isinstance(raw_federation, dict) else {}
        idp = federation.get("identity_provider")
        protocol = federation.get("protocol")
        mismatch = (
            not isinstance(idp, dict)
            or not isinstance(protocol, dict)
            or idp.get("id") != row.keystone_idp_id
            or protocol.get("id") != row.keystone_protocol_id
        )
    native_domain = native.get("domain") if isinstance(native.get("domain"), dict) else {}
    if native.get("id") != canonical_id or native_domain.get("id") != canonical_home or mismatch:
        await _revoke_quietly(unscoped)
        raise DomainAuthDenied(
            "Native federation did not return the canonical account", code="canonical_subject_mismatch"
        )
    try:
        from app.services import keystone

        current = await asyncio.to_thread(keystone.get_identity_user, canonical_id)
        if current["id"] != canonical_id or current["domain_id"] != canonical_home:
            raise DomainAuthDenied("Native mapping changed canonical home", code="canonical_subject_mismatch")
        if normalize_email(current["email"]).casefold() != canonical_email:
            raise DomainAuthDenied("Native mapping changed canonical email", code="canonical_email_mismatch")
        await require_provider(domain["id"], row.id, int(row.revision), identity.email)
        from app.services import organization_provisioning

        await organization_provisioning.require_current(row, ks=ks, user_id=canonical_id, subject=identity.subject)
    except BaseException:
        await _revoke_quietly(unscoped)
        raise
    return FederatedLogin(
        unscoped_token=unscoped,
        user_id=canonical_id,
        username=_field(user, "name") or identity.email,
        domain_id=domain["id"],
        domain_name=domain["name"],
        provider_id=row.id,
        provider_revision=int(row.revision),
        provider_kind=row.kind,
        login_email=identity.email,
    )


async def _origin_admission_required(row, identity, ks) -> bool:
    """SQL origin needs membership; config origin only exact existing-domain autojoin."""
    if not row.id.startswith(_CONFIG_PROVIDER_PREFIX):
        return True
    if not await provider_auto_join_allowed(row.domain_id, row.id, identity.email):
        return False
    from app.services.account_spaces import domain_kind

    origin = await asyncio.to_thread(ks.domains.get, row.domain_id)
    return domain_kind(origin) not in {"account", "personal"}


async def _admit_verified_identity(row, identity, user, *, lease, ks, catalog):
    """Origin policy is not participation; configured organizations are explicit trust."""
    from app.services import account_identity, organization_provisioning

    if getattr(row, "_organization", None) is not None:
        await organization_provisioning.admit(row, identity, user, lease=lease, ks=ks, catalog=catalog)
    elif await _origin_admission_required(row, identity, ks):
        await account_identity.require_admission(
            account_identity._field(user, "id"),
            row.domain_id,
            row,
            identity.email,
            lease=lease,
            ks=ks,
            catalog=catalog,
        )


async def complete_authorization(code: str, state: str, browser_binding: str) -> FederatedLogin:
    """Resolve canonical ownership before the native exchange can create a user."""
    from app.services import account_identity, domain_iam

    record = await _consume_state(state, browser_binding)
    if not isinstance(code, str) or not code or len(code) > 2048:
        raise DomainAuthUnauthenticated("Authorization code is invalid", code="invalid_code")
    domain_id = record.get("domain_id")
    domain = await resolve_enabled_domain(domain_id)
    if domain["id"] != domain_id:
        raise DomainAuthDenied("Domain changed during login", code="foreign_domain")
    row = await _current_provider(domain_id, str(record.get("provider_id", "")), record.get("revision"))
    async with _provider_client() as client:
        identity = await (
            _oidc_identity(client, row, code, record)
            if row.kind == "oidc"
            else _github_identity(client, row, code, record)
        )
    enforce_email(await get_policy(domain_id), identity.email)
    async with domain_iam._iam_write() as (lease, ks, catalog):
        row = await _current_provider(domain_id, row.id, int(row.revision))
        await asyncio.to_thread(_require_stable_native_mapping, ks, row)
        bound, existing = await account_identity.directory(ks, identity, row)
        if bound is None and existing is not None:
            ticket = await _link_ticket(row, identity, existing, browser_binding)
            raise AccountLinkRequired(ticket, domain_id)
        if bound is None:
            if getattr(row, "_organization", None) is not None:
                from app.services import organization_provisioning

                await organization_provisioning.precheck(row, identity, ks=ks)
            elif await _origin_admission_required(row, identity, ks):
                await account_identity.require_admission(
                    "", domain_id, row, identity.email, lease=lease, ks=ks, catalog=catalog, new=True
                )
            bound = await account_identity.create_external(
                row, identity, lease=lease, ks=ks, catalog=catalog, admission_domain_id=None
            )
            await _admit_verified_identity(row, identity, bound, lease=lease, ks=ks, catalog=catalog)
        else:
            await account_identity.require_enrollment_complete(bound)
            organization = getattr(row, "_organization", None) is not None
            if organization:
                from app.services import organization_provisioning

                await organization_provisioning.precheck(row, identity, ks=ks)
            else:
                # Original ordering: admission decides before any native association write.
                await _admit_verified_identity(row, identity, bound, lease=lease, ks=ks, catalog=catalog)
            bound = await account_identity.attach(bound, row, identity, lease=lease, ks=ks)
            if organization:
                await _admit_verified_identity(row, identity, bound, lease=lease, ks=ks, catalog=catalog)
        return await _canonical_federation(row, identity, bound, domain, ks=ks)


async def complete_account_link(
    ticket: str, browser_binding: str, *, username: str = "", password: str = "", authenticated: dict | None = None
) -> dict[str, Any]:
    from app.services import account_identity, domain_iam, keystone
    from app.services.native_operation import NativeOperation

    record = await _consume_link_ticket(ticket, browser_binding)
    domain = await resolve_enabled_domain(record["domain_id"])
    row = await _current_provider(domain["id"], record["provider_id"], record["revision"])
    identity = VerifiedIdentity(record["email"], record["bearer"], record["issuer"], record["subject"])
    enforce_email(await get_policy(domain["id"]), identity.email)
    proof = None
    async with domain_iam._iam_write() as (lease, ks, catalog):
        try:
            if authenticated is not None:
                from keystoneauth1.exceptions.http import Unauthorized

                if (
                    authenticated.get("user_id") != record["user_id"]
                    or authenticated.get("identity_domain_id") != record["identity_domain_id"]
                ):
                    raise DomainAuthDenied("Sign in to the account owning this email", code="account_proof_mismatch")
                try:
                    proof = await asyncio.to_thread(keystone.validate_token, authenticated["token"])
                except Unauthorized:
                    raise DomainAuthUnauthenticated(
                        "Account proof was rejected", code="account_proof_invalid"
                    ) from None
            else:
                from keystoneauth1.exceptions.http import Unauthorized

                await require_password(record["identity_domain_id"], record["email"])
                try:
                    async with NativeOperation() as operation:
                        native_user = await operation.run(operation.get, "users", record["user_id"])
                        if (
                            account_identity._field(native_user, "domain_id") != record["identity_domain_id"]
                            or account_identity._field(native_user, "enabled") is not True
                        ):
                            raise DomainAuthConflict("Canonical account changed", code="account_changed")
                        account = {
                            "id": record["user_id"],
                            "name": account_identity._field(native_user, "name"),
                            "domain_id": record["identity_domain_id"],
                        }
                        proof = await account_identity.authenticate_password(
                            account, password, operation=operation, username=username
                        )
                except Unauthorized:
                    raise DomainAuthUnauthenticated(
                        "Account proof was rejected", code="account_proof_invalid"
                    ) from None
            if (
                proof.get("user_id") != record["user_id"]
                or proof.get("identity_domain_id") != record["identity_domain_id"]
                or normalize_email(proof.get("email", "")).casefold() != identity.email.casefold()
            ):
                raise DomainAuthDenied("Account proof does not match", code="account_proof_mismatch")
            if authenticated is None:
                from app.services import login_guard

                await login_guard.record_success(account["name"], account["domain_id"])
            row = await _current_provider(domain["id"], row.id, int(row.revision))
            await asyncio.to_thread(_require_stable_native_mapping, ks, row)
            bound, existing = await account_identity.directory(ks, identity, row)
            if existing is None or account_identity._field(existing, "id") != record["user_id"]:
                raise DomainAuthConflict("Canonical email ownership changed", code="account_changed")
            if bound is not None and account_identity._field(bound, "id") != record["user_id"]:
                raise DomainAuthConflict("External identity is already linked", code="native_binding_conflict")
            password_proven = authenticated is None
            if authenticated is not None:
                from app.services import session_store

                origin = await session_store.get_session(authenticated.get("refresh_jti", ""))
                if (
                    not origin
                    or origin.get("blacklisted")
                    or origin.get("user_id") != record["user_id"]
                    or origin.get("identity_domain_id") != record["identity_domain_id"]
                ):
                    raise DomainAuthUnauthenticated("Account session is no longer live", code="account_proof_invalid")
                try:
                    now = datetime.now(UTC).timestamp()
                    expired = (
                        now >= float(origin["exp"])
                        or now >= float(origin["started_at"]) + get_settings().session_timeout_seconds
                    )
                except (KeyError, TypeError, ValueError):
                    expired = True
                if expired:
                    raise DomainAuthUnauthenticated("Account session has expired", code="account_proof_invalid")
                password_proven = origin.get("auth_method") == "password"
            if not row.id.startswith(_CONFIG_PROVIDER_PREFIX):
                await account_identity.require_admission(
                    record["user_id"], domain["id"], row, identity.email, lease=lease, ks=ks, catalog=catalog
                )
            await account_identity.attach(
                existing, row, identity, lease=lease, ks=ks, password_proven=password_proven, explicit_proof=True
            )
            await require_provider(domain["id"], row.id, int(row.revision), identity.email)
            # Attachment readback is the commit boundary; login needs a fresh provider proof.
            return {"linked": True, "domain_id": domain["id"], "domain_name": domain["name"], "provider_id": row.id}
        finally:
            if proof and proof.get("token") and (authenticated is None or proof["token"] != authenticated["token"]):
                await _revoke_quietly(proof["token"])
