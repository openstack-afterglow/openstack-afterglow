"""Lease-aware, fail-closed cleanup for delegated MCP authority state.

This worker never contacts Keystone.  It only terminalizes local rows and marks
owner-scoped credentials for a later confirmation through the same user's
project-scoped connection.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.mcp_authority import (
    McpDelegatedGrant,
    McpOAuthAuthorizationRequest,
    McpOAuthClient,
    McpOAuthCode,
    McpOAuthToken,
    McpOAuthTokenFamily,
    McpProjectCredential,
    McpToolInvocation,
)
from app.services.mcp_control_plane.authority import (
    _as_utc,
    _audit,
    _lock_grant,
    _now,
    lock_owner,
    mark_expired_grants_for_cleanup,
    schedule_grant_cleanup,
)
from app.services.mcp_control_plane.operations import reconcile_expired_invocation

_AUDIT_RETENTION = timedelta(days=90)


@dataclass(frozen=True)
class CleanupCounts:
    expired_grants: int = 0
    expired_tickets: int = 0
    expired_codes: int = 0
    expired_access_tokens: int = 0
    deleted_access_tokens: int = 0
    deleted_refresh_tombstones: int = 0
    scrubbed_ongoing_grants: int = 0
    revoked_clients: int = 0
    deleted_clients: int = 0
    deleted_authorization_requests: int = 0
    deleted_read_invocations: int = 0
    expired_mutation_leases: int = 0


def _db_time(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(tzinfo=None)


async def _lock_family(session: AsyncSession, family_id: str) -> McpOAuthTokenFamily | None:
    return await session.scalar(
        select(McpOAuthTokenFamily).where(McpOAuthTokenFamily.id == family_id).with_for_update()
    )


async def _scrub_terminal_ongoing_secrets(session_factory: async_sessionmaker[AsyncSession], *, now: datetime) -> int:
    """Retire local ciphertext, never a provider outcome or remote credential.

    Terminal authority rejects new decrypts under the same owner/grant lock.
    Already-loaded workers retain their own session secret; historical unknown
    ledger rows therefore do not require SQL ciphertext. IDs/retry state survive.
    """
    child_secret = (
        select(McpProjectCredential.grant_id)
        .where(
            McpProjectCredential.grant_id == McpDelegatedGrant.id,
            McpProjectCredential.credential_ciphertext.is_not(None),
        )
        .exists()
    )
    async with session_factory() as session:
        candidates = (
            await session.execute(
                select(McpDelegatedGrant.id, McpDelegatedGrant.owner_user_id, McpDelegatedGrant.owner_project_id).where(
                    McpDelegatedGrant.source == "oauth",
                    McpDelegatedGrant.oauth_ongoing.is_(True),
                    McpDelegatedGrant.status.in_(("revoked", "expired")),
                    McpDelegatedGrant.credential_ciphertext.is_not(None) | child_secret,
                )
            )
        ).all()
    scrubbed = 0
    for grant_id, user_id, project_id in candidates:
        async with session_factory() as session, session.begin():
            await lock_owner(session, owner_user_id=user_id, owner_project_id=project_id)
            grant = await _lock_grant(
                session,
                grant_id=grant_id,
                owner_user_id=user_id,
                owner_project_id=project_id,
            )
            if grant.source != "oauth" or not grant.oauth_ongoing or grant.status not in {"revoked", "expired"}:
                continue
            if grant.issued_at is None and (
                grant.orphan_recovery_after is None
                or _as_utc(grant.orphan_recovery_after) > now
                or grant.orphan_recovery_nonce is not None
            ):
                continue
            unresolved = await session.scalar(
                select(McpToolInvocation.id)
                .where(
                    McpToolInvocation.grant_id == grant.id,
                    McpToolInvocation.status.in_(("claimed", "dispatch_authorized")),
                    McpToolInvocation.lease_expires_at.is_(None) | (McpToolInvocation.lease_expires_at > _db_time(now)),
                )
                .limit(1)
            )
            if unresolved is not None:
                continue
            credentials = (
                await session.scalars(
                    select(McpProjectCredential).where(McpProjectCredential.grant_id == grant.id).with_for_update()
                )
            ).all()
            if grant.credential_ciphertext is None and all(cred.credential_ciphertext is None for cred in credentials):
                continue
            grant.credential_ciphertext = None
            for credential in credentials:
                credential.credential_ciphertext = None
            _audit(
                session,
                owner_user_id=user_id,
                owner_project_id=project_id,
                username="system:mcp-cleanup",
                action="mcp_grant.secret_retire",
                grant=grant,
                extra={"credential_epoch": grant.credential_epoch, "cleanup_pending": grant.cleanup_pending},
            )
            scrubbed += 1
    return scrubbed


async def sweep_delegated_authority(
    session_factory: async_sessionmaker[AsyncSession], *, now: datetime | None = None
) -> CleanupCounts:
    """Terminalize expired/tombstoned records without performing external cleanup."""
    now = now or _now()
    cutoff = now - _AUDIT_RETENTION
    expired_grants = await mark_expired_grants_for_cleanup(session_factory, now=now)

    ongoing_client = (
        select(McpOAuthCode.id)
        .join(McpDelegatedGrant, McpDelegatedGrant.id == McpOAuthCode.grant_id)
        .where(
            McpOAuthCode.client_id == McpOAuthClient.client_id,
            McpDelegatedGrant.source == "oauth",
            McpDelegatedGrant.oauth_ongoing.is_(True),
            McpDelegatedGrant.status == "active",
        )
        .exists()
    )
    async with session_factory() as session, session.begin():
        tickets = (
            await session.scalars(
                select(McpOAuthAuthorizationRequest)
                .where(
                    McpOAuthAuthorizationRequest.status == "pending",
                    McpOAuthAuthorizationRequest.expires_at <= _db_time(now),
                )
                .with_for_update()
            )
        ).all()
        for ticket in tickets:
            ticket.status = "expired"
            ticket.used_at = now

        stale_clients = (
            await session.scalars(
                select(McpOAuthClient)
                .where(
                    McpOAuthClient.revoked_at.is_(None),
                    ~ongoing_client,
                    (
                        (McpOAuthClient.expires_at.is_not(None) & (McpOAuthClient.expires_at <= _db_time(now)))
                        | (McpOAuthClient.last_used_at.is_not(None) & (McpOAuthClient.last_used_at <= _db_time(cutoff)))
                    ),
                )
                .with_for_update()
            )
        ).all()
        for client in stale_clients:
            client.revoked_at = now

        expired_request_retention = now - timedelta(days=1)
        stale_requests = (
            await session.scalars(
                select(McpOAuthAuthorizationRequest)
                .where(
                    McpOAuthAuthorizationRequest.status != "pending",
                    McpOAuthAuthorizationRequest.expires_at <= _db_time(expired_request_retention),
                )
                .with_for_update()
            )
        ).all()
        for request in stale_requests:
            await session.delete(request)

        deleted_clients = (
            await session.scalars(
                select(McpOAuthClient)
                .where(
                    McpOAuthClient.revoked_at.is_not(None),
                    ~ongoing_client,
                    McpOAuthClient.revoked_at <= _db_time(cutoff),
                )
                .with_for_update()
            )
        ).all()
        for client in deleted_clients:
            await session.delete(client)
    expired_codes = 0
    expired_access_tokens = 0
    deleted_refresh_tombstones = 0
    deleted_read_invocations = 0
    expired_mutation_leases = 0
    # Access hashes are not refresh replay tombstones. Their expiry already
    # invalidates them; after audit retention they can be removed in one SQL
    # operation, including on an ongoing active family.
    async with session_factory() as session, session.begin():
        removed = await session.execute(
            delete(McpOAuthToken).where(
                McpOAuthToken.token_type == "access",
                McpOAuthToken.expires_at <= _db_time(cutoff),
            )
        )
        deleted_access_tokens = removed.rowcount

    async with session_factory() as session:
        code_candidates = (
            await session.execute(
                select(McpOAuthCode.id, McpOAuthCode.grant_id).where(
                    McpOAuthCode.used_at.is_(None), McpOAuthCode.expires_at <= _db_time(now)
                )
            )
        ).all()
        token_candidates = (
            await session.execute(
                select(McpOAuthToken.id, McpOAuthToken.family_id, McpOAuthToken.token_type).where(
                    McpOAuthToken.revoked_at.is_(None), McpOAuthToken.expires_at <= _db_time(now)
                )
            )
        ).all()
        invocation_candidates = (
            await session.execute(
                select(McpToolInvocation.id, McpToolInvocation.grant_id).where(
                    McpToolInvocation.idempotency_key.is_(None), McpToolInvocation.created_at <= _db_time(cutoff)
                )
            )
        ).all()
        stale_mutation_candidates = (
            await session.execute(
                select(McpToolInvocation.id, McpToolInvocation.grant_id).where(
                    McpToolInvocation.idempotency_key.is_not(None),
                    McpToolInvocation.status.in_(("claimed", "dispatch_authorized")),
                    (
                        McpToolInvocation.lease_expires_at.is_(None)
                        | (McpToolInvocation.lease_expires_at <= _db_time(now))
                    ),
                )
            )
        ).all()
        refresh_candidates = (
            await session.execute(
                select(McpOAuthToken.id, McpOAuthToken.family_id)
                .join(McpOAuthTokenFamily, McpOAuthTokenFamily.id == McpOAuthToken.family_id)
                .join(McpDelegatedGrant, McpDelegatedGrant.id == McpOAuthTokenFamily.grant_id)
                .where(
                    McpOAuthToken.token_type == "refresh",
                    McpOAuthToken.rotated_at.is_not(None),
                    McpOAuthToken.rotated_at <= _db_time(cutoff),
                    (
                        (McpDelegatedGrant.expires_at <= _db_time(cutoff))
                        | (
                            McpDelegatedGrant.status.in_(("revoked", "expired"))
                            & (McpDelegatedGrant.revoked_at <= _db_time(cutoff))
                        )
                    ),
                )
            )
        ).all()

    for code_id, grant_id in code_candidates:
        async with session_factory() as session, session.begin():
            hint = await session.scalar(select(McpDelegatedGrant).where(McpDelegatedGrant.id == grant_id))
            if hint is None:
                continue
            await lock_owner(session, owner_user_id=hint.owner_user_id, owner_project_id=hint.owner_project_id)
            grant = await _lock_grant(
                session, grant_id=hint.id, owner_user_id=hint.owner_user_id, owner_project_id=hint.owner_project_id
            )
            code = await session.scalar(select(McpOAuthCode).where(McpOAuthCode.id == code_id).with_for_update())
            if code is not None and code.used_at is None and _as_utc(code.expires_at) <= now:
                code.used_at = now
                expired_codes += 1
                family = await session.scalar(
                    select(McpOAuthTokenFamily).where(McpOAuthTokenFamily.grant_id == grant.id).with_for_update()
                )
                if grant.source == "oauth" and grant.oauth_ongoing and grant.status == "active" and family is None:
                    grant.status = "revoked"
                    grant.revoked_at = now
                    grant.credential_epoch += 1
                    credentials = (
                        await session.scalars(
                            select(McpProjectCredential)
                            .where(McpProjectCredential.grant_id == grant.id)
                            .with_for_update()
                        )
                    ).all()
                    for credential in credentials:
                        credential.cleanup_pending = True
                    grant.cleanup_pending = (
                        bool(grant.application_credential_id) or grant.cleanup_pending or bool(credentials)
                    )
                    schedule_grant_cleanup(grant, now=now)
                    _audit(
                        session,
                        owner_user_id=grant.owner_user_id,
                        owner_project_id=grant.owner_project_id,
                        username="system:mcp-cleanup",
                        action="mcp_grant.revoke",
                        grant=grant,
                        extra={"reason": "unexchanged_authorization_code", "credential_epoch": grant.credential_epoch},
                    )

    for token_id, family_id, token_type in token_candidates:
        async with session_factory() as session, session.begin():
            family_hint = await session.scalar(select(McpOAuthTokenFamily).where(McpOAuthTokenFamily.id == family_id))
            if family_hint is None:
                continue
            grant_hint = await session.scalar(
                select(McpDelegatedGrant).where(McpDelegatedGrant.id == family_hint.grant_id)
            )
            if grant_hint is None:
                continue
            await lock_owner(
                session, owner_user_id=grant_hint.owner_user_id, owner_project_id=grant_hint.owner_project_id
            )
            await _lock_grant(
                session,
                grant_id=grant_hint.id,
                owner_user_id=grant_hint.owner_user_id,
                owner_project_id=grant_hint.owner_project_id,
            )
            family = await _lock_family(session, family_id)
            token = await session.scalar(select(McpOAuthToken).where(McpOAuthToken.id == token_id).with_for_update())
            if (
                family is not None
                and token is not None
                and token.revoked_at is None
                and token.expires_at is not None
                and _as_utc(token.expires_at) <= now
            ):
                token.revoked_at = now
                if token_type == "access":
                    expired_access_tokens += 1

    for token_id, family_id in refresh_candidates:
        async with session_factory() as session, session.begin():
            family_hint = await session.scalar(select(McpOAuthTokenFamily).where(McpOAuthTokenFamily.id == family_id))
            if family_hint is None:
                continue
            grant_hint = await session.scalar(
                select(McpDelegatedGrant).where(McpDelegatedGrant.id == family_hint.grant_id)
            )
            if grant_hint is None:
                continue
            await lock_owner(
                session, owner_user_id=grant_hint.owner_user_id, owner_project_id=grant_hint.owner_project_id
            )
            grant = await _lock_grant(
                session,
                grant_id=grant_hint.id,
                owner_user_id=grant_hint.owner_user_id,
                owner_project_id=grant_hint.owner_project_id,
            )
            family = await _lock_family(session, family_id)
            token = await session.scalar(select(McpOAuthToken).where(McpOAuthToken.id == token_id).with_for_update())
            retired = (grant.expires_at is not None and _as_utc(grant.expires_at) <= cutoff) or (
                grant.status in {"revoked", "expired"}
                and grant.revoked_at is not None
                and _as_utc(grant.revoked_at) <= cutoff
            )
            if (
                retired
                and family is not None
                and token is not None
                and token.rotated_at is not None
                and _as_utc(token.rotated_at) <= cutoff
            ):
                await session.delete(token)
                deleted_refresh_tombstones += 1

    for invocation_id, grant_id in stale_mutation_candidates:
        async with session_factory() as session, session.begin():
            hint = await session.get(McpDelegatedGrant, grant_id)
            if hint is None:
                continue
            await lock_owner(session, owner_user_id=hint.owner_user_id, owner_project_id=hint.owner_project_id)
            await _lock_grant(
                session, grant_id=hint.id, owner_user_id=hint.owner_user_id, owner_project_id=hint.owner_project_id
            )
            invocation = await session.scalar(
                select(McpToolInvocation).where(McpToolInvocation.id == invocation_id).with_for_update()
            )
            if invocation is not None and reconcile_expired_invocation(invocation, now=now):
                expired_mutation_leases += 1

    for invocation_id, grant_id in invocation_candidates:
        async with session_factory() as session, session.begin():
            hint = await session.scalar(select(McpDelegatedGrant).where(McpDelegatedGrant.id == grant_id))
            if hint is None:
                continue
            await lock_owner(session, owner_user_id=hint.owner_user_id, owner_project_id=hint.owner_project_id)
            await _lock_grant(
                session, grant_id=hint.id, owner_user_id=hint.owner_user_id, owner_project_id=hint.owner_project_id
            )
            invocation = await session.scalar(
                select(McpToolInvocation).where(McpToolInvocation.id == invocation_id).with_for_update()
            )
            if (
                invocation is not None
                and invocation.idempotency_key is None
                and _as_utc(invocation.created_at) <= cutoff
            ):
                await session.delete(invocation)
                deleted_read_invocations += 1
    scrubbed_ongoing_grants = await _scrub_terminal_ongoing_secrets(session_factory, now=now)

    return CleanupCounts(
        expired_grants=expired_grants,
        expired_tickets=len(tickets),
        expired_codes=expired_codes,
        expired_access_tokens=expired_access_tokens,
        deleted_access_tokens=deleted_access_tokens,
        deleted_refresh_tombstones=deleted_refresh_tombstones,
        scrubbed_ongoing_grants=scrubbed_ongoing_grants,
        revoked_clients=len(stale_clients),
        deleted_read_invocations=deleted_read_invocations,
        deleted_clients=len(deleted_clients),
        deleted_authorization_requests=len(stale_requests),
        expired_mutation_leases=expired_mutation_leases,
    )
