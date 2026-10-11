"""Persistent OAuth 2.1 authorization-code and refresh-token authority for MCP."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.models.mcp_authority import (
    McpDelegatedGrant,
    McpOAuthAuthorizationRequest,
    McpOAuthClient,
    McpOAuthCode,
    McpOAuthToken,
    McpOAuthTokenFamily,
    McpProjectCredential,
)
from app.services.mcp_control_plane.authority import (
    PENDING_ORPHAN_RECOVERY_GRACE,
    McpAuthorityError,
    _as_utc,
    _audit,
    _count_dispatchable_grants,
    _lock_grant,
    _now,
    _prepare_connection_projects,
    abandon_grant_credentials,
    close_project_authority,
    create_grant_credentials,
    default_grant_lifetime,
    lock_owner,
    max_grant_lifetime,
    recover_stale_pending_orphans,
)
from app.services.mcp_control_plane.oauth import (
    McpOAuthError,
    fetch_cimd,
    hash_oauth_value,
    new_oauth_value,
    pkce_s256,
    redirect_uri_matches,
    require_exact_resource,
    validate_pkce_s256,
    validate_redirect_uris,
    validate_scopes,
)

_CODE_LIFETIME = timedelta(minutes=5)
_DYNAMIC_CLIENT_LIFETIME = timedelta(days=30)
_CIMD_CACHE_LIFETIME = timedelta(hours=1)


def _ticket_lifetime() -> timedelta:
    return timedelta(seconds=get_settings().mcp_authorization_ticket_ttl_seconds)


def _access_token_lifetime() -> timedelta:
    return timedelta(seconds=get_settings().mcp_access_token_ttl_seconds)


class McpOAuthAuthorityError(McpAuthorityError):
    """A safe OAuth protocol error with no credential-bearing detail."""


@dataclass(frozen=True)
class AuthorizationTicket:
    ticket: str
    redirect_uri: str
    state: str | None


@dataclass(frozen=True)
class ConsentTicket:
    client_id: str
    client_name: str
    redirect_uri: str
    scopes: tuple[str, ...]
    grant_deadline: object


@dataclass(frozen=True)
class AuthorizationCodeResult:
    code: str
    redirect_uri: str
    state: str | None


@dataclass(frozen=True)
class TokenResult:
    access_token: str
    refresh_token: str
    expires_in: int
    scope: str


def _consent_scopes(requested: object, access_level: str | None) -> tuple[str, tuple[str, ...]]:
    scopes = validate_scopes(requested)
    chosen = access_level if access_level is not None else ("manage" if "mcp:write" in scopes else "read")
    if chosen not in {"read", "manage"}:
        raise McpOAuthAuthorityError("access level must be read or manage")
    approved = ("mcp:read", "mcp:write") if chosen == "manage" else ("mcp:read",)
    if not set(approved).issubset(scopes):
        raise McpOAuthAuthorityError("consent may not expand the requested scopes")
    return chosen, approved


def _db_time(value):
    return value.replace(tzinfo=None)


def _fingerprint(metadata: dict) -> str:
    return hashlib.sha256(
        json.dumps(metadata, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


def _client_name(metadata: dict, client_id: str) -> str:
    candidate = metadata.get("client_name")
    if isinstance(candidate, str) and candidate.strip():
        return candidate.strip()[:100]
    return client_id[:100]


def _validate_public_client_metadata(metadata: object, *, expected_client_id: str | None = None) -> dict:
    if not isinstance(metadata, dict):
        raise McpOAuthAuthorityError("OAuth client metadata must be an object")
    client_id = metadata.get("client_id")
    if expected_client_id is not None and client_id != expected_client_id:
        raise McpOAuthAuthorityError("OAuth client metadata does not match client_id")
    if client_id is not None and (not isinstance(client_id, str) or not client_id or len(client_id) > 512):
        raise McpOAuthAuthorityError("OAuth client_id is invalid")
    if metadata.get("token_endpoint_auth_method") != "none":
        raise McpOAuthAuthorityError("MCP OAuth clients must be public")
    if set(metadata.get("grant_types", [])) != {"authorization_code", "refresh_token"}:
        raise McpOAuthAuthorityError("OAuth client must use authorization_code and refresh_token only")
    redirects = list(validate_redirect_uris(metadata.get("redirect_uris")))
    name = metadata.get("client_name")
    if name is not None and (not isinstance(name, str) or len(name.strip()) > 100):
        raise McpOAuthAuthorityError("OAuth client_name is invalid")
    return {
        "client_id": client_id,
        "client_name": name.strip() if isinstance(name, str) else None,
        "redirect_uris": redirects,
        "grant_types": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_method": "none",
    }


async def register_public_client(
    session_factory: async_sessionmaker[AsyncSession], *, metadata: object
) -> McpOAuthClient:
    normalized = _validate_public_client_metadata(metadata)
    if normalized["client_id"] is not None:
        raise McpOAuthAuthorityError("dynamic registration must not choose client_id")
    client_id = f"afterglow-dcr-{new_oauth_value()}"
    normalized["client_id"] = client_id
    now = _now()
    async with session_factory() as session, session.begin():
        client = McpOAuthClient(
            client_id=client_id,
            metadata_json=normalized,
            redirect_uris=normalized["redirect_uris"],
            client_id_issued_at=now,
            expires_at=now + _DYNAMIC_CLIENT_LIFETIME,
        )
        session.add(client)
    return client


async def _find_client(session_factory: async_sessionmaker[AsyncSession], *, client_id: str) -> McpOAuthClient | None:
    now = _now()
    async with session_factory() as session, session.begin():
        client = await session.scalar(
            select(McpOAuthClient).where(McpOAuthClient.client_id == client_id).with_for_update()
        )
        if client is None or client.revoked_at is not None:
            return None
        if client.expires_at is not None and _as_utc(client.expires_at) <= now:
            return None
        client.last_used_at = now
        return client


async def resolve_public_client(session_factory: async_sessionmaker[AsyncSession], *, client_id: str) -> McpOAuthClient:
    if not isinstance(client_id, str) or not client_id or len(client_id) > 512:
        raise McpOAuthAuthorityError("OAuth client_id is invalid")
    client = await _find_client(session_factory, client_id=client_id)
    if client is not None and not client_id.startswith("https://"):
        return client
    if client is not None and _as_utc(client.client_id_issued_at) > _now() - _CIMD_CACHE_LIFETIME:
        return client
    if not client_id.startswith("https://"):
        raise McpOAuthAuthorityError("OAuth client is not registered")
    try:
        metadata = _validate_public_client_metadata(await fetch_cimd(client_id), expected_client_id=client_id)
    except McpOAuthError as exc:
        raise McpOAuthAuthorityError(str(exc)) from exc
    now = _now()
    async with session_factory() as session, session.begin():
        existing = await session.scalar(
            select(McpOAuthClient).where(McpOAuthClient.client_id == client_id).with_for_update()
        )
        if existing is None:
            existing = McpOAuthClient(
                client_id=client_id,
                metadata_json=metadata,
                redirect_uris=metadata["redirect_uris"],
                client_id_issued_at=now,
                expires_at=now + _DYNAMIC_CLIENT_LIFETIME,
            )
            session.add(existing)
        else:
            existing.metadata_json = metadata
            existing.redirect_uris = metadata["redirect_uris"]
            existing.client_id_issued_at = now
            existing.revoked_at = None
            existing.last_used_at = now
        return existing


async def create_authorization_ticket(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    client_id: str,
    redirect_uri: str,
    response_type: str,
    resource: str | None,
    urls,
    scope: str,
    code_challenge: str | None,
    code_challenge_method: str | None,
    state: str | None,
) -> AuthorizationTicket:
    if response_type != "code":
        raise McpOAuthAuthorityError("response_type must be code")
    require_exact_resource(resource, urls)
    scopes = validate_scopes(scope)
    challenge = validate_pkce_s256(code_challenge, code_challenge_method)
    if state is not None and (not isinstance(state, str) or len(state) > 2048):
        raise McpOAuthAuthorityError("state is invalid")
    client = await resolve_public_client(session_factory, client_id=client_id)
    if not redirect_uri_matches(next(iter(client.redirect_uris), ""), redirect_uri) and not any(
        redirect_uri_matches(registered, redirect_uri) for registered in client.redirect_uris
    ):
        raise McpOAuthAuthorityError("redirect_uri is not registered")
    ticket = new_oauth_value()
    now = _now()
    async with session_factory() as session, session.begin():
        session.add(
            McpOAuthAuthorizationRequest(
                ticket_hash=hash_oauth_value(ticket),
                client_id=client.client_id,
                client_fingerprint=_fingerprint(client.metadata_json),
                redirect_uri=redirect_uri,
                resource=urls.resource,
                scopes=list(scopes),
                code_challenge=challenge,
                state=state,
                expires_at=now + _ticket_lifetime(),
            )
        )
    return AuthorizationTicket(ticket=ticket, redirect_uri=redirect_uri, state=state)


async def load_consent_ticket(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    ticket: str,
    owner_user_id: str,
    owner_project_id: str,
) -> ConsentTicket:
    ticket_hash = hash_oauth_value(ticket)
    async with session_factory() as session:
        hint = await session.scalar(
            select(McpOAuthAuthorizationRequest).where(McpOAuthAuthorizationRequest.ticket_hash == ticket_hash)
        )
    if hint is None:
        raise McpOAuthAuthorityError("authorization ticket is invalid")
    now = _now()
    async with session_factory() as session, session.begin():
        await lock_owner(session, owner_user_id=owner_user_id, owner_project_id=owner_project_id)
        request = await session.scalar(
            select(McpOAuthAuthorizationRequest)
            .where(McpOAuthAuthorizationRequest.ticket_hash == ticket_hash)
            .with_for_update()
        )
        if request is None or request.status != "pending" or _as_utc(request.expires_at) <= now:
            if request is not None and request.status == "pending":
                request.status = "expired"
                request.used_at = now
            raise McpOAuthAuthorityError("authorization ticket is expired")
        if request.owner_user_id is None and request.owner_project_id is None:
            request.owner_user_id = owner_user_id
            request.owner_project_id = owner_project_id
            request.grant_deadline = now + default_grant_lifetime()
        if request.owner_user_id != owner_user_id or request.owner_project_id != owner_project_id:
            raise McpOAuthAuthorityError("authorization ticket belongs to a different project")
        client = await session.scalar(
            select(McpOAuthClient).where(McpOAuthClient.client_id == request.client_id).with_for_update()
        )
        if (
            client is None
            or client.revoked_at is not None
            or _fingerprint(client.metadata_json) != request.client_fingerprint
        ):
            raise McpOAuthAuthorityError("OAuth client metadata changed")
        return ConsentTicket(
            client_id=request.client_id,
            client_name=_client_name(client.metadata_json, request.client_id),
            redirect_uri=request.redirect_uri,
            scopes=tuple(request.scopes),
            grant_deadline=request.grant_deadline,
        )


async def deny_consent_ticket(
    session_factory: async_sessionmaker[AsyncSession], *, ticket: str, owner_user_id: str, owner_project_id: str
) -> AuthorizationTicket:
    ticket_hash = hash_oauth_value(ticket)
    async with session_factory() as session:
        hint = await session.scalar(
            select(McpOAuthAuthorizationRequest).where(McpOAuthAuthorizationRequest.ticket_hash == ticket_hash)
        )
    if hint is None:
        raise McpOAuthAuthorityError("authorization ticket is invalid")
    async with session_factory() as session, session.begin():
        await lock_owner(session, owner_user_id=owner_user_id, owner_project_id=owner_project_id)
        request = await session.scalar(
            select(McpOAuthAuthorizationRequest)
            .where(McpOAuthAuthorizationRequest.ticket_hash == ticket_hash)
            .with_for_update()
        )
        if (
            request is None
            or request.status != "pending"
            or request.owner_user_id != owner_user_id
            or request.owner_project_id != owner_project_id
        ):
            raise McpOAuthAuthorityError("authorization ticket is not available")
        request.status = "denied"
        request.used_at = _now()
        return AuthorizationTicket(ticket=ticket, redirect_uri=request.redirect_uri, state=request.state)


async def approve_consent_ticket(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    ticket: str,
    owner_user_id: str,
    owner_project_id: str,
    username: str,
    roles: object,
    conn: Any,
    project_scope: str = "current",
    project_ids: list[str] | None = None,
    access_level: str | None = None,
) -> AuthorizationCodeResult:
    """Commit an OAuth grant and one code only after the restricted credential is durable."""
    if (
        getattr(conn, "_afterglow_user_id", None) != owner_user_id
        or getattr(conn, "_afterglow_project_id", None) != owner_project_id
    ):
        raise McpOAuthAuthorityError("scoped connection does not match the OAuth consent owner")
    ticket_hash = hash_oauth_value(ticket)
    now = _now()
    await recover_stale_pending_orphans(
        session_factory,
        conn=conn,
        owner_user_id=owner_user_id,
        owner_project_id=owner_project_id,
        username=username,
    )
    async with session_factory() as session:
        hint = await session.scalar(
            select(McpOAuthAuthorizationRequest).where(McpOAuthAuthorizationRequest.ticket_hash == ticket_hash)
        )
    if hint is None:
        raise McpOAuthAuthorityError("authorization ticket is invalid")
    if (
        hint.status != "pending"
        or _as_utc(hint.expires_at) <= now
        or hint.owner_user_id != owner_user_id
        or hint.owner_project_id != owner_project_id
    ):
        raise McpOAuthAuthorityError("authorization ticket is not available")
    chosen_access_level, approved_scopes = _consent_scopes(hint.scopes, access_level)

    projects = await _prepare_connection_projects(
        conn,
        owner_user_id,
        owner_project_id,
        roles,
        project_scope,
        project_ids,
        chosen_access_level,
    )
    grant_id = str(uuid4())
    credentials_ready = False
    try:
        async with session_factory() as session, session.begin():
            await lock_owner(session, owner_user_id=owner_user_id, owner_project_id=owner_project_id)
            reservation_now = _now()
            request = await session.scalar(
                select(McpOAuthAuthorizationRequest)
                .where(McpOAuthAuthorizationRequest.ticket_hash == ticket_hash)
                .with_for_update()
            )
            if (
                request is None
                or request.status != "pending"
                or request.owner_user_id != owner_user_id
                or request.owner_project_id != owner_project_id
                or request.grant_deadline is None
                or _as_utc(request.expires_at) <= reservation_now
            ):
                raise McpOAuthAuthorityError("authorization ticket is not available")
            if _as_utc(request.grant_deadline) > reservation_now + max_grant_lifetime():
                raise McpOAuthAuthorityError("authorization ticket grant deadline is invalid")
            if request.grant_id is not None:
                raise McpOAuthAuthorityError("authorization ticket is already being processed")
            if (
                await _count_dispatchable_grants(
                    session, owner_user_id=owner_user_id, owner_project_id=owner_project_id
                )
                >= get_settings().mcp_max_delegated_grants
            ):
                raise McpOAuthAuthorityError("the project already has the maximum number of active MCP grants")
            chosen_access_level, approved_scopes = _consent_scopes(request.scopes, access_level)
            request.grant_id = grant_id
            session.add(
                McpDelegatedGrant(
                    id=grant_id,
                    owner_user_id=owner_user_id,
                    owner_project_id=owner_project_id,
                    upstream_credential_name=f"afterglow-mcp-{grant_id}",
                    display_name=f"OAuth: {request.client_id[:90]}",
                    source="oauth",
                    access_level=chosen_access_level,
                    project_scope=project_scope,
                    approved_projects=[project.metadata() for project in projects],
                    status="pending",
                    expires_at=request.grant_deadline,
                    cleanup_pending=True,
                    orphan_recovery_after=reservation_now + PENDING_ORPHAN_RECOVERY_GRACE,
                )
            )
            deadline = request.grant_deadline

        await create_grant_credentials(
            session_factory,
            grant_id=grant_id,
            owner_user_id=owner_user_id,
            owner_project_id=owner_project_id,
            username=username,
            projects=projects,
            expires_at=deadline,
        )
        credentials_ready = True

        code = new_oauth_value()
        redirect_uri: str | None = None
        state: str | None = None
        async with session_factory() as session, session.begin():
            await lock_owner(session, owner_user_id=owner_user_id, owner_project_id=owner_project_id)
            activation_now = _now()
            grant = await _lock_grant(
                session, grant_id=grant_id, owner_user_id=owner_user_id, owner_project_id=owner_project_id
            )
            request = await session.scalar(
                select(McpOAuthAuthorizationRequest)
                .where(McpOAuthAuthorizationRequest.ticket_hash == ticket_hash)
                .with_for_update()
            )
            if (
                request is None
                or request.status != "pending"
                or request.grant_id != grant_id
                or grant.status != "pending"
                or grant.orphan_recovery_nonce is not None
                or _as_utc(request.expires_at) <= activation_now
                or grant.expires_at is None
                or _as_utc(grant.expires_at) <= activation_now
            ):
                raise McpOAuthAuthorityError("authorization ticket changed before activation")
            grant.status = "active"
            grant.issued_at = activation_now
            grant.cleanup_pending = False
            grant.orphan_recovery_after = None
            grant.orphan_recovery_nonce = None
            request.status = "approved"
            request.used_at = activation_now
            session.add(
                McpOAuthCode(
                    code_hash=hash_oauth_value(code),
                    grant_id=grant_id,
                    client_id=request.client_id,
                    redirect_uri=request.redirect_uri,
                    resource=request.resource,
                    scopes=list(approved_scopes),
                    code_challenge=request.code_challenge,
                    expires_at=activation_now + _CODE_LIFETIME,
                )
            )
            _audit(
                session,
                owner_user_id=owner_user_id,
                owner_project_id=owner_project_id,
                username=username,
                action="mcp_grant.create",
                grant=grant,
                extra={
                    "source": "oauth",
                    "access_level": grant.access_level,
                    "project_scope": grant.project_scope,
                    "credential_epoch": grant.credential_epoch,
                },
            )
            redirect_uri = request.redirect_uri
            state = request.state
        assert redirect_uri is not None
        return AuthorizationCodeResult(code=code, redirect_uri=redirect_uri, state=state)
    except BaseException:
        if credentials_ready:
            await abandon_grant_credentials(
                session_factory,
                conn=projects[0].conn,
                grant_id=grant_id,
                owner_user_id=owner_user_id,
                owner_project_id=owner_project_id,
                username=username,
            )
        raise
    finally:
        await close_project_authority(projects)


async def exchange_authorization_code(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    code: str,
    client_id: str,
    redirect_uri: str,
    resource: str | None,
    urls,
    code_verifier: str,
) -> TokenResult:
    require_exact_resource(resource, urls)
    code_hash = hash_oauth_value(code)
    async with session_factory() as session:
        code_hint = await session.scalar(select(McpOAuthCode).where(McpOAuthCode.code_hash == code_hash))
        if code_hint is None:
            raise McpOAuthAuthorityError("authorization code is invalid")
        grant_hint = await session.scalar(select(McpDelegatedGrant).where(McpDelegatedGrant.id == code_hint.grant_id))
    if grant_hint is None:
        raise McpOAuthAuthorityError("authorization code is invalid")
    now = _now()
    async with session_factory() as session, session.begin():
        await lock_owner(session, owner_user_id=grant_hint.owner_user_id, owner_project_id=grant_hint.owner_project_id)
        grant = await _lock_grant(
            session,
            grant_id=grant_hint.id,
            owner_user_id=grant_hint.owner_user_id,
            owner_project_id=grant_hint.owner_project_id,
        )
        family = await session.scalar(
            select(McpOAuthTokenFamily).where(McpOAuthTokenFamily.grant_id == grant.id).with_for_update()
        )
        if family is None:
            family = McpOAuthTokenFamily(grant_id=grant.id)
            session.add(family)
            await session.flush()
        oauth_code = await session.scalar(
            select(McpOAuthCode).where(McpOAuthCode.code_hash == code_hash).with_for_update()
        )
        if (
            oauth_code is None
            or not hmac.compare_digest(oauth_code.code_hash, code_hash)
            or oauth_code.used_at is not None
            or _as_utc(oauth_code.expires_at) <= now
            or grant.status != "active"
            or grant.expires_at is None
            or _as_utc(grant.expires_at) <= now
            or oauth_code.client_id != client_id
            or oauth_code.redirect_uri != redirect_uri
            or oauth_code.resource != urls.resource
            or pkce_s256(code_verifier) != oauth_code.code_challenge
        ):
            raise McpOAuthAuthorityError("authorization code is invalid")
        access_token = new_oauth_value()
        refresh_token = new_oauth_value()
        access_expiry = min(now + _access_token_lifetime(), _as_utc(grant.expires_at))
        oauth_code.used_at = now
        session.add_all(
            [
                McpOAuthToken(
                    family_id=family.id,
                    token_hash=hash_oauth_value(access_token),
                    token_type="access",
                    resource=urls.resource,
                    scopes=list(oauth_code.scopes),
                    generation=family.generation,
                    expires_at=access_expiry,
                ),
                McpOAuthToken(
                    family_id=family.id,
                    token_hash=hash_oauth_value(refresh_token),
                    token_type="refresh",
                    resource=urls.resource,
                    scopes=list(oauth_code.scopes),
                    generation=family.generation,
                    expires_at=grant.expires_at,
                ),
            ]
        )
        return TokenResult(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=max(1, int((access_expiry - now).total_seconds())),
            scope=" ".join(oauth_code.scopes),
        )


async def refresh_tokens(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    refresh_token: str,
    resource: str | None,
    urls,
    scope: str | None,
    client_id: str | None = None,
) -> TokenResult:
    require_exact_resource(resource, urls)
    if not client_id:
        raise McpOAuthAuthorityError("refresh token client_id is required")
    token_hash = hash_oauth_value(refresh_token)
    async with session_factory() as session:
        token_hint = await session.scalar(select(McpOAuthToken).where(McpOAuthToken.token_hash == token_hash))
        if token_hint is None:
            raise McpOAuthAuthorityError("refresh token is invalid")
        family_hint = await session.scalar(
            select(McpOAuthTokenFamily).where(McpOAuthTokenFamily.id == token_hint.family_id)
        )
        grant_hint = (
            await session.scalar(select(McpDelegatedGrant).where(McpDelegatedGrant.id == family_hint.grant_id))
            if family_hint is not None
            else None
        )
    if family_hint is None or grant_hint is None:
        raise McpOAuthAuthorityError("refresh token is invalid")
    now = _now()
    replay_detected = False
    async with session_factory() as session, session.begin():
        await lock_owner(session, owner_user_id=grant_hint.owner_user_id, owner_project_id=grant_hint.owner_project_id)
        grant = await _lock_grant(
            session,
            grant_id=grant_hint.id,
            owner_user_id=grant_hint.owner_user_id,
            owner_project_id=grant_hint.owner_project_id,
        )
        family = await session.scalar(
            select(McpOAuthTokenFamily).where(McpOAuthTokenFamily.id == family_hint.id).with_for_update()
        )
        token = await session.scalar(
            select(McpOAuthToken).where(McpOAuthToken.token_hash == token_hash).with_for_update()
        )
        # Consumed codes retain the issuing client beyond code/ticket expiry.
        issuing_clients = (
            await session.scalars(select(McpOAuthCode.client_id).where(McpOAuthCode.grant_id == grant.id).limit(2))
        ).all()
        if len(issuing_clients) != 1 or issuing_clients[0] != client_id:
            raise McpOAuthAuthorityError("refresh token is invalid")
        replay = (
            token is None
            or not hmac.compare_digest(token.token_hash, token_hash)
            or token.token_type != "refresh"
            or token.resource != urls.resource
            or token.rotated_at is not None
            or token.revoked_at is not None
            or _as_utc(token.expires_at) <= now
            or family is None
            or family.revoked_at is not None
            or token.generation != family.generation
            or grant.status != "active"
            or grant.expires_at is None
            or _as_utc(grant.expires_at) <= now
        )
        if replay:
            if family is not None:
                family.revoked_at = now
            if grant.status == "active":
                grant.status = "revoked"
                grant.revoked_at = now
                grant.credential_epoch += 1
                additional = (
                    await session.scalars(
                        select(McpProjectCredential).where(McpProjectCredential.grant_id == grant.id).with_for_update()
                    )
                ).all()
                for cred in additional:
                    cred.cleanup_pending = True
                grant.cleanup_pending = (
                    bool(grant.application_credential_id) or grant.cleanup_pending or bool(additional)
                )
            for issued in (
                await session.scalars(
                    select(McpOAuthToken).where(McpOAuthToken.family_id == family_hint.id).with_for_update()
                )
            ).all():
                issued.revoked_at = issued.revoked_at or now
            _audit(
                session,
                owner_user_id=grant.owner_user_id,
                owner_project_id=grant.owner_project_id,
                username="oauth:refresh-replay",
                action="mcp_grant.revoke",
                grant=grant,
                extra={"reason": "refresh_token_replay", "credential_epoch": grant.credential_epoch},
            )
            replay_detected = True
        else:
            requested_scopes = tuple(token.scopes) if scope is None else validate_scopes(scope)
            if not set(requested_scopes).issubset(set(token.scopes)):
                raise McpOAuthAuthorityError("refresh token may not expand scope")
            token.rotated_at = now
            family.generation += 1
            access_token = new_oauth_value()
            next_refresh_token = new_oauth_value()
            access_expiry = min(now + _access_token_lifetime(), _as_utc(grant.expires_at))
            session.add_all(
                [
                    McpOAuthToken(
                        family_id=family.id,
                        token_hash=hash_oauth_value(access_token),
                        token_type="access",
                        resource=urls.resource,
                        scopes=list(requested_scopes),
                        generation=family.generation,
                        expires_at=access_expiry,
                    ),
                    McpOAuthToken(
                        family_id=family.id,
                        token_hash=hash_oauth_value(next_refresh_token),
                        token_type="refresh",
                        resource=urls.resource,
                        scopes=list(requested_scopes),
                        generation=family.generation,
                        expires_at=grant.expires_at,
                    ),
                ]
            )
            result = TokenResult(
                access_token=access_token,
                refresh_token=next_refresh_token,
                expires_in=max(1, int((access_expiry - now).total_seconds())),
                scope=" ".join(requested_scopes),
            )
    if replay_detected:
        raise McpOAuthAuthorityError("refresh token is invalid")
    return result


async def revoke_oauth_token(session_factory: async_sessionmaker[AsyncSession], *, token: str) -> None:
    """RFC 7009 is deliberately idempotent; absent or malformed values are accepted."""
    token_hash = hash_oauth_value(token)
    async with session_factory() as session:
        token_hint = await session.scalar(select(McpOAuthToken).where(McpOAuthToken.token_hash == token_hash))
        if token_hint is None:
            return
        family_hint = await session.scalar(
            select(McpOAuthTokenFamily).where(McpOAuthTokenFamily.id == token_hint.family_id)
        )
        grant_hint = (
            await session.scalar(select(McpDelegatedGrant).where(McpDelegatedGrant.id == family_hint.grant_id))
            if family_hint is not None
            else None
        )
    if family_hint is None or grant_hint is None:
        return
    now = _now()
    async with session_factory() as session, session.begin():
        await lock_owner(session, owner_user_id=grant_hint.owner_user_id, owner_project_id=grant_hint.owner_project_id)
        grant = await _lock_grant(
            session,
            grant_id=grant_hint.id,
            owner_user_id=grant_hint.owner_user_id,
            owner_project_id=grant_hint.owner_project_id,
        )
        family = await session.scalar(
            select(McpOAuthTokenFamily).where(McpOAuthTokenFamily.id == family_hint.id).with_for_update()
        )
        if family is not None:
            family.revoked_at = family.revoked_at or now
        if grant.status not in {"revoked", "expired"}:
            grant.status = "revoked"
            grant.revoked_at = now
            grant.credential_epoch += 1
        additional = (
            await session.scalars(
                select(McpProjectCredential).where(McpProjectCredential.grant_id == grant.id).with_for_update()
            )
        ).all()
        for cred in additional:
            cred.cleanup_pending = True
        grant.cleanup_pending = bool(grant.application_credential_id) or grant.cleanup_pending or bool(additional)
        for issued in (
            await session.scalars(
                select(McpOAuthToken).where(McpOAuthToken.family_id == family_hint.id).with_for_update()
            )
        ).all():
            issued.revoked_at = issued.revoked_at or now
        _audit(
            session,
            owner_user_id=grant.owner_user_id,
            owner_project_id=grant.owner_project_id,
            username="oauth:revoke",
            action="mcp_grant.revoke",
            grant=grant,
            extra={"reason": "oauth_token_revocation", "credential_epoch": grant.credential_epoch},
        )


async def resolve_oauth_access_token(
    session: AsyncSession, *, raw_token: str, resource: str
) -> tuple[McpDelegatedGrant, tuple[str, ...]]:
    """Resolve an exact-resource access token under owner → grant → family locks."""
    digest = hash_oauth_value(raw_token)
    token_hint = await session.scalar(select(McpOAuthToken).where(McpOAuthToken.token_hash == digest))
    if (
        token_hint is None
        or token_hint.token_type != "access"
        or not hmac.compare_digest(token_hint.token_hash, digest)
    ):
        raise McpOAuthAuthorityError("access token is invalid")
    family_hint = await session.scalar(
        select(McpOAuthTokenFamily).where(McpOAuthTokenFamily.id == token_hint.family_id)
    )
    grant_hint = (
        await session.scalar(select(McpDelegatedGrant).where(McpDelegatedGrant.id == family_hint.grant_id))
        if family_hint is not None
        else None
    )
    if family_hint is None or grant_hint is None:
        raise McpOAuthAuthorityError("access token is invalid")
    await lock_owner(session, owner_user_id=grant_hint.owner_user_id, owner_project_id=grant_hint.owner_project_id)
    grant = await _lock_grant(
        session,
        grant_id=grant_hint.id,
        owner_user_id=grant_hint.owner_user_id,
        owner_project_id=grant_hint.owner_project_id,
    )
    family = await session.scalar(
        select(McpOAuthTokenFamily).where(McpOAuthTokenFamily.id == family_hint.id).with_for_update()
    )
    token = await session.scalar(select(McpOAuthToken).where(McpOAuthToken.token_hash == digest).with_for_update())
    now = _now()
    if (
        token is None
        or not hmac.compare_digest(token.token_hash, digest)
        or token.token_type != "access"
        or token.resource != resource
        or token.revoked_at is not None
        or _as_utc(token.expires_at) <= now
        or family is None
        or family.revoked_at is not None
        or token.generation != family.generation
        or grant.status != "active"
        or grant.expires_at is None
        or _as_utc(grant.expires_at) <= now
    ):
        raise McpOAuthAuthorityError("access token is invalid")
    return grant, tuple(token.scopes)
