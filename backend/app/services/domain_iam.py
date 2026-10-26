"""Domain manager IAM and email-verified, one-use account enrollment.

The shared native graph lease and SQL row locks serialize state transitions.
Durable intent/addition journals fence partial native effects across SQL commits;
failed or ambiguous creates are never retried as password resets.
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import secrets
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from fastapi import HTTPException
from sqlalchemy import or_, select

from app.config import get_settings
from app.models.domain_iam import DomainEnrollment
from app.services import (
    account_spaces,
    domain_projects,
    domain_scope,
    enrollment_policy,
    identity_roles,
    keystone,
    project_ownership_journal,
    project_service,
)
from app.services.project_service import _provider_call

_field = identity_roles._field


async def context(token_info):
    did = token_info.get("domain_id")
    if not did:
        raise HTTPException(403, "An authoritative domain is required")
    await organization_domain(did)
    result = await _provider_call(domain_scope.domain_context, token_info["user_id"], did)
    if not result["is_domain_manager"]:
        raise HTTPException(403, "Domain manager required")
    return result


async def domain(domain_id):
    result = await _provider_call(domain_scope.resolve_domain, domain_id)
    domain_scope.assert_domain_resource(domain_id, result["id"])
    return result


async def organization_domain(domain_id):
    result = await domain(domain_id)
    ks = await _provider_call(keystone._get_admin_ks_client)
    native = await _provider_call(ks.domains.get, domain_id)
    if account_spaces.domain_kind(native) in {"account", "personal"}:
        raise HTTPException(403, "Organization IAM is unavailable in reserved domains")
    return result


async def resource(kind, resource_id, domain_id):
    ks = await _provider_call(keystone._get_admin_ks_client)
    obj = await _provider_call(getattr(ks, kind).get, resource_id)
    if _field(obj, "id") != resource_id:
        raise HTTPException(503, "Native resource identity is unavailable")
    domain_scope.assert_domain_resource(domain_id, _field(obj, "domain_id"))
    if kind == "projects" and _field(obj, "enabled") is not True:
        raise HTTPException(403, "Project is disabled")
    return obj


async def protected_user(user, domain_id, *, credentials=True, system_services=False, membership_project_id=None):
    uid = _field(user, "id")
    if not isinstance(uid, str) or not uid:
        raise HTTPException(503, "Identity protection metadata is unavailable")
    ks = await _provider_call(keystone._get_admin_ks_client)
    user = await _provider_call(ks.users.get, uid)
    if _field(user, "id") != uid:
        raise HTTPException(503, "Identity protection readback is unavailable")
    if credentials and _field(user, "domain_id") != domain_id:
        return True
    if (credentials and _field(user, "federated")) or _field(user, "name") == get_settings().os_username:
        return True
    # Effective Keystone listings omit system grants. Protect those accounts
    # through the existing exact raw-system resolver, never a token claim.
    if await _provider_call(domain_scope.has_scope_authority, uid):
        return True
    catalog = await _provider_call(identity_roles._trusted_catalog)
    by_id = {role["id"]: role for role in catalog}
    protected = set()
    protected_names = {"admin", "manager", "service"} if credentials else {"admin", "service"}
    for name in protected_names:
        matches = [role for role in catalog if role["domain_id"] is None and role["name"].casefold() == name]
        if matches and (len(matches) != 1 or matches[0]["name"] != name):
            raise HTTPException(503, "Native privileged role binding is ambiguous")
        if matches:
            protected.add(matches[0]["id"])
    assignments = await _provider_call(lambda: list(ks.role_assignments.list(user=uid, effective=True)))
    for row in assignments:
        if project_service._principal(row, "user") != uid:
            raise HTTPException(503, "Effective user protection assignments are not attributable")
        scope = _field(row, "scope", {})
        scopes = set(scope) - {"OS-INHERIT:inherited_to"} if isinstance(scope, dict) else set()
        if len(scopes) != 1 or not scopes <= {"project", "domain", "system"}:
            raise HTTPException(503, "Effective user protection scope is unavailable")
        kind = next(iter(scopes))
        if kind == "system":
            if scope[kind] != {"all": True} or "OS-INHERIT:inherited_to" in scope:
                raise HTTPException(503, "Effective system protection scope is unavailable")
        elif not isinstance(_field(scope[kind], "id"), str) or not _field(scope[kind], "id"):
            raise HTTPException(503, "Effective scoped protection identity is unavailable")
        if "OS-INHERIT:inherited_to" in scope and scope["OS-INHERIT:inherited_to"] != "projects":
            raise HTTPException(503, "Effective inherited protection scope is unavailable")
    # Membership edits may remove the target project's native admin grant, but
    # never gain identity/system authority or edit other privileged bindings.
    if membership_project_id is not None and not credentials:
        assignments = [
            row
            for row in assignments
            if not (
                _field(_field(_field(row, "scope", {}), "project", {}), "id") == membership_project_id
                and by_id.get(project_service._principal(row, "role"), {}).get("name", "").casefold() == "admin"
            )
        ]
    expanded = project_service._expanded_role_ids(assignments, catalog, uid)
    if system_services:
        # Deletion additionally protects service-only raw system grants, which
        # Keystone's effective path omits. Other IAM consumers keep their reads.
        user_system = await _provider_call(lambda: list(ks.role_assignments.list(user=uid, system="all")))
        system_sources = [(row, "user_id", uid) for row in user_system]
        for group in await _provider_call(lambda: list(ks.groups.list(user=uid))):
            gid = _field(group, "id")
            if not isinstance(gid, str) or not gid:
                raise HTTPException(503, "Native identity group membership is unavailable")
            system_sources.extend(
                (row, "group_id", gid)
                for row in await _provider_call(lambda gid=gid: list(ks.role_assignments.list(group=gid, system="all")))
            )
        for row, principal, subject in system_sources:
            source = domain_projects._assignment(row, catalog)
            if source["kind"] != "system" or source[principal] != subject:
                raise HTTPException(503, "Native identity system protection scope is unavailable")
            expanded.update({source["role_id"], *identity_roles._descendant_ids(catalog, source["role_id"])})
    if credentials and any(by_id[rid]["domain_id"] not in {None, domain_id} for rid in expanded):
        raise HTTPException(503, "Foreign role graph cannot authorize identity edits")
    return bool(protected & expanded) or any(by_id[rid]["name"].casefold() in protected_names for rid in expanded)


def user_dto(user, protected=False):
    return {
        "id": _field(user, "id"),
        "name": _field(user, "name", ""),
        "email": _field(user, "email", "") or "",
        "enabled": _field(user, "enabled") is True,
        "domain_id": _field(user, "domain_id"),
        "protected": protected,
    }


async def directory_users(domain_id, *, ks=None, skip_missing=False):
    """Fresh home/joined directory; only display callers may omit absent users."""
    await organization_domain(domain_id)
    ks = ks or await _provider_call(keystone._get_admin_ks_client)
    catalog = await _provider_call(identity_roles._trusted_catalog)
    rows = await _provider_call(lambda: list(ks.users.list(domain=domain_id)))
    ids = set()
    for user in rows:
        domain_scope.assert_domain_resource(domain_id, _field(user, "domain_id"))
        ids.add(_field(user, "id"))
    home_ids = set(ids)
    projects = await _provider_call(lambda: list(ks.projects.list(domain=domain_id)))
    raw = await _provider_call(lambda: list(ks.role_assignments.list()))
    for project in projects:
        domain_scope.assert_domain_resource(domain_id, _field(project, "domain_id"))
        if not domain_projects._enabled(project):
            continue
        sources = await _provider_call(domain_projects._sources, ks, project, catalog, raw, exclude_projection=True)
        effective = await _provider_call(domain_projects._effective, ks, _field(project, "id"), catalog)
        effective_ids = {project_service._principal(row, "user") for row in effective}
        ids.update(uid for source in sources for uid in source["users"] if uid in effective_ids)
    if any(not isinstance(uid, str) or not uid for uid in ids):
        raise HTTPException(503, "Domain directory identity is unavailable")
    result = []
    for uid in sorted(ids):
        reads = {}
        try:
            user = await _provider_call(domain_projects._exact, ks.users, uid, reads=reads)
        except HTTPException as exc:
            # A dangling role assignment or a concurrently deleted list result
            # is not a candidate. Never soften home-domain or authority reads.
            if not skip_missing or exc.status_code != 404:
                raise
            continue
        if uid in home_ids:
            domain_scope.assert_domain_resource(domain_id, _field(user, "domain_id"))
            domain_projects._enabled(user)
        else:
            user = await _provider_call(domain_projects._active_user, ks, uid, reads=reads)
        if user is not None:
            result.append(user)
    return result


async def assert_joined_user(domain_id, user_id, *, ks=None):
    # Directory sources are native and reread for each mutation; no SQL/cache
    # membership is allowed to revive a revoked identity.
    for user in await directory_users(domain_id, ks=ks):
        if _field(user, "id") == user_id and _field(user, "enabled") is True:
            return user
    raise HTTPException(403, "User has not joined this domain")


async def list_resources(kind, token_info):
    ctx = await context(token_info)
    did = ctx["domain_id"]
    ks = await _provider_call(keystone._get_admin_ks_client)
    if kind == "users":
        rows = await directory_users(did)
    else:
        rows = await _provider_call(lambda: list(getattr(ks, kind).list(domain=did)))
    items = []
    for row in rows:
        if kind != "users":
            domain_scope.assert_domain_resource(did, _field(row, "domain_id"))
        if kind == "users":
            items.append(user_dto(row, await protected_user(row, did)))
        else:
            items.append(
                {
                    "id": _field(row, "id"),
                    "name": _field(row, "name", ""),
                    "description": _field(row, "description", "") or "",
                    "domain_id": did,
                    "enabled": _field(row, "enabled", True) is True,
                }
            )
    return {"items": items}


async def password_policy(domain_id, email, *, signup=False, password=True):
    from app.services.domain_auth import DomainAuthError, enforce_email, get_policy

    try:
        policy = await get_policy(domain_id)
        if password and not policy.password_enabled:
            raise HTTPException(403, "Password authentication is disabled")
        return enforce_email(policy, email, signup=signup)
    except DomainAuthError as exc:
        raise HTTPException(exc.status_code, exc.detail) from exc


def _email_key(email):
    from app.services.domain_auth import DomainAuthError, normalize_email

    try:
        return normalize_email(email).casefold()
    except DomainAuthError:
        # Invalid legacy directory entries cannot own a syntactically valid email.
        return None


def _account_name_key(name):
    if not name:
        return None
    # Email-shaped usernames share the same alias namespace as verified emails.
    # Keep ordinary native names intact apart from case-insensitive comparison.
    return _email_key(name) or name.casefold()


def _account_rows(ks, domain_id, *, operation=None):
    """Complete inventory with exact account metadata for every identity writer."""
    transport = getattr(ks.users, "client", None)
    if transport is not None and callable(getattr(transport, "get", None)):
        url = "/users" + ("?" + urlencode({"domain_id": domain_id}) if domain_id else "")
        _, body = transport.get(url)
        if not isinstance(body, dict) or not isinstance(body.get("users"), list):
            raise HTTPException(503, "Native account inventory is unavailable")
        links = body.get("links")
        if not isinstance(links, dict) or links.get("next") or body.get("truncated") or body.get("limited"):
            raise HTTPException(503, "Native account inventory is incomplete")
        rows = body["users"]
    else:
        # Provider adapters must preserve completeness before materialization.
        rows = ks.users.list(**({"domain": domain_id} if domain_id else {}))
        links = getattr(rows, "links", {})
        if (
            getattr(rows, "truncated", False)
            or getattr(rows, "limited", False)
            or getattr(rows, "next", None)
            or (isinstance(links, dict) and links.get("next"))
        ):
            raise HTTPException(503, "Native account inventory is incomplete")
    result, ids = [], set()
    for row in rows:
        uid = _field(row, "id")
        if not isinstance(uid, str) or not uid or uid in ids:
            raise HTTPException(503, "Native account inventory identity is invalid")
        ids.add(uid)
        try:
            full = operation.get("users", uid) if operation is not None else ks.users.get(uid)
        except Exception as exc:
            raise HTTPException(503, "Native account inventory changed during inspection") from exc
        home, projected_home = _field(full, "domain_id"), _field(row, "domain_id")
        if (
            _field(full, "id") != uid
            or not isinstance(home, str)
            or not home
            or (domain_id is not None and home != domain_id)
            or (projected_home is not None and projected_home != home)
        ):
            raise HTTPException(503, "Native account inventory changed during inspection")
        result.append(full)
    return result


async def _find_accounts(domain_id, *, email=None, name=None):
    ks = await _provider_call(keystone._get_admin_ks_client)
    # Native email filters can be case-sensitive. Check exact normalized email
    # ownership across identity domains before creating a new account; a known
    # external identity must accept while authenticated, never be duplicated.
    rows = await _provider_call(_account_rows, ks, domain_id)
    email_key = _email_key(email) if email else None
    name_key = _account_name_key(name)
    return [
        user
        for user in rows
        if (email_key and _email_key(_field(user, "email", "")) == email_key)
        or (name_key and _account_name_key(_field(user, "name", "")) == name_key)
    ]


@asynccontextmanager
async def _iam_write():
    """One lock order for enrollment state and native writes: graph, then SQL."""
    conn = await _provider_call(keystone.get_admin_project_connection)
    try:
        async with identity_roles._graph_lock(conn) as lease:
            ks = await _provider_call(keystone._get_admin_ks_client)
            catalog = await _provider_call(identity_roles.load_catalog, conn)
            yield lease, ks, catalog
    finally:
        await asyncio.to_thread(conn.close)


@identity_roles._complete_mutation
async def create_account(domain_id, name, email, password, *, enabled=True, marker=None, _mutation=None):
    await domain(domain_id)
    email = await password_policy(domain_id, email)
    if name == get_settings().os_username:
        raise HTTPException(403, "Operational account name is reserved")
    mutation = project_service._using_snapshot(_mutation) if _mutation is not None else _iam_write()
    async with mutation as (lease, ks, catalog):
        if (
            await _find_accounts(None, email=email, name=name)
            or await _find_accounts(None, name=email)
            or name
            and "@" in name
            and await _find_accounts(None, email=name)
        ):
            raise HTTPException(409, "Account already exists; sign in to accept an invitation")
        extra = {"afterglow_enrollment_id": marker} if marker else {}
        return await identity_roles._write(
            lease,
            ks.users.create,
            name=name,
            email=email,
            password=password,
            domain=domain_id,
            enabled=enabled,
            **extra,
            afterglow_local_password=True,
        )


@identity_roles._complete_mutation
async def create_managed_user(attrs, target_domain_id, actor, session):
    """System-admin human creation; operational provisioning uses native APIs."""
    if not await _provider_call(domain_scope.has_scope_authority, actor.get("user_id")):
        raise HTTPException(403, "System administrator required")
    from app.services.domain_auth import DomainAuthError, normalize_email

    attrs = dict(attrs)
    # The selected domain is an observation context, not organization admission
    # or the credential policy of the new global human identity.
    await domain(target_domain_id)
    try:
        email = normalize_email(attrs.get("email", ""))
    except DomainAuthError as exc:
        raise HTTPException(exc.status_code, exc.detail) from exc
    row = DomainEnrollment(
        kind="managed_create",
        domain_id=None,
        email=email,
        token_hash=secrets.token_hex(32),
        status="pending",
        role_ids=[],
        added_role_ids=[],
        added_grants=[],
        invited_by=actor["user_id"],
        requested_enabled=attrs.get("enabled", True),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        created_at=datetime.now(UTC),
    )
    async with _iam_write() as mutation:
        if not await _provider_call(domain_scope.has_scope_authority, actor["user_id"]):
            raise HTTPException(403, "System administrator required")
        session.add(row)
        await session.commit()
        await session.refresh(row)
        result = await _enroll(
            row,
            session,
            mutation,
            name=attrs["name"],
            password=attrs["password"],
            actor=actor,
            system_managed=True,
        )
        return {
            "id": result["user_id"],
            "name": attrs["name"],
            "email": email,
            "enabled": attrs.get("enabled", True),
            "protected": True,
            **result,
        }


@identity_roles._complete_mutation
async def update_user(user_id, attrs, token_info):
    ctx = await context(token_info)
    # Share the existing graph lease with role mutation: protected-account checks
    # and last-owner membership rules cannot race an Afterglow grant operation.
    conn = await _provider_call(keystone.get_admin_project_connection)
    try:
        async with identity_roles._graph_lock(conn) as lease:
            await context(token_info)
            # Joined foreign identities are membership-only; even enabled is an
            # identity credential control and must remain home-bound.
            user = await resource("users", user_id, ctx["domain_id"])
            if await protected_user(user, ctx["domain_id"], credentials=any(key != "enabled" for key in attrs)):
                raise HTTPException(403, "Privileged or service account is read-only in domain IAM")
            attrs = dict(attrs)
            if attrs.get("name") == get_settings().os_username:
                raise HTTPException(403, "Operational account name is reserved")
            email = attrs.get("email", _field(user, "email", "") or "")
            if "password" in attrs or "email" in attrs:
                email = await password_policy(ctx["domain_id"], email, password="password" in attrs)
                if "email" in attrs:
                    attrs["email"] = email
                    if any(_field(row, "id") != user_id for row in await _find_accounts(None, email=email)):
                        raise HTTPException(409, "Email belongs to another account")
            await identity_roles._session_ready({user_id})
            ks = await _provider_call(keystone._get_admin_ks_client)
            catalog = []
            affected = set()
            if "enabled" in attrs:
                catalog = await _provider_call(identity_roles.load_catalog, conn)
                if attrs["enabled"] is False:
                    await project_ownership_journal.assert_user_resolved(user_id)
                    await _provider_call(project_service.assert_user_ownership_mutation_safe, user_id, ks=ks)
                affected = await _provider_call(
                    domain_projects.assert_managers_remain,
                    user_id=user_id,
                    ks=ks,
                    catalog=catalog,
                    disabled_user_ids={user_id} if attrs["enabled"] is False else (),
                )
            succeeded = False
            try:
                if "password" in attrs:
                    # Password setters establish an explicit native credential capability.
                    attrs["afterglow_local_password"] = True
                updated = await identity_roles._write(lease, ks.users.update, user_id, **attrs)
                succeeded = True
            finally:
                try:
                    if "enabled" in attrs:
                        for did in affected:
                            await domain_projects.sync_manager_access(did, mutation=(lease, ks, catalog))
                finally:
                    await identity_roles._applied(
                        None,
                        catalog,
                        None,
                        {user_id},
                        token_info,
                        "domain_user_update",
                        {"user_id": user_id},
                        status="success" if succeeded else "failed",
                    )
            return user_dto(updated)
    finally:
        await asyncio.to_thread(conn.close)


async def validate_invitation_roles(project_id, role_ids, token_info):
    if not role_ids or len(role_ids) != len(set(role_ids)):
        raise HTTPException(422, "Choose unique project role IDs")
    allowed = await project_service.assignable_roles(project_id, token_info, domain_management=True)
    catalog = await _provider_call(identity_roles._trusted_catalog)
    safe = {row["id"] for row in allowed["roles"] if row["name"].casefold() != "admin"}
    if not set(role_ids) <= safe:
        raise HTTPException(403, "Role exceeds domain IAM project authority")
    by_id = {row["id"]: row for row in catalog}
    for rid in role_ids:
        if by_id[rid]["name"] in project_service._PROJECT_GRADES:
            project_service._required_project_role(catalog, by_id[rid]["name"], require_hierarchy=True)
    if not any(by_id[rid]["name"] in project_service._PROJECT_GRADES for rid in role_ids):
        raise HTTPException(422, "An explicit project membership role is required")


def _utc(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def enrollment_status(row):
    if row.status == "pending" and _utc(row.expires_at) <= datetime.now(UTC):
        return "expired"
    return row.status


RECOVERY_STATES = frozenset({"account_creating", "granting", "activating", "recovery_required"})


def enrollment_dto(row, project_name=""):
    return {
        "id": row.id,
        "domain_id": row.domain_id,
        "project_id": row.project_id,
        "project_name": project_name or row.project_name,
        "email": row.email,
        "role_ids": row.role_ids,
        "kind": row.kind,
        "user_id": row.user_id,
        "identity_domain_id": row.identity_domain_id,
        "personal_project_id": row.personal_project_id,
        "personal_project_name": row.personal_project_name,
        "personal_domain_id": row.personal_domain_id,
        "native_writes_settled": not (
            row.creation_uncertain
            or row.domain_creation_uncertain
            or row.project_creation_uncertain
            or row.added_role_ids
            or any(
                not isinstance(grant, dict) or grant.get("phase") not in {"confirmed", "settled", "not_sent"}
                for grant in row.added_grants or []
            )
        ),
        "recovery_required": row.status in RECOVERY_STATES,
        "status": enrollment_status(row),
        "expires_at": _utc(row.expires_at).isoformat(),
        "created_at": _utc(row.created_at).isoformat(),
        "accepted_at": _utc(row.accepted_at).isoformat() if row.accepted_at else None,
    }


async def _deliver(row, token, *, project_name="", inviter=""):
    from app.services.email_service import send_email, send_invitation_email

    settings = get_settings()
    base = settings.frontend_base_url.rstrip("/")
    if row.kind == "invitation":
        delivered = await send_invitation_email(
            row.email, project_name, inviter, f"{base}/invitations/{token}", row.expires_at
        )
    else:
        link = f"{base}/registrations/{token}"
        delivered = await send_email(
            row.email,
            "Verify your account email",
            f'<p><a href="{html.escape(link, quote=True)}">Verify email and create account</a></p>',
            f"Verify email and create account: {link}",
        )
    return delivered


async def issue_enrollment(
    session, *, kind, domain_id, email, project_id=None, role_ids=None, invited_by=None, project_name="", inviter=""
):
    if kind == "invitation":
        await organization_domain(domain_id)
    token = secrets.token_urlsafe(32)
    row = DomainEnrollment(
        kind=kind,
        domain_id=domain_id,
        email=email,
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        project_id=project_id,
        role_ids=role_ids or [],
        invited_by=invited_by,
        status="delivery_pending",
        project_name=project_name,
        added_role_ids=[],
        expires_at=datetime.now(UTC)
        + (
            timedelta(days=get_settings().smtp_invitation_token_expiry_days)
            if kind == "invitation"
            else timedelta(hours=1)
        ),
        created_at=datetime.now(UTC),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    delivered = await _deliver(row, token, project_name=project_name, inviter=inviter)
    row.status = "pending" if delivered else "delivery_failed"
    await session.commit()
    if not delivered:
        raise HTTPException(503, "Email delivery failed; no redeemable link was issued")
    return enrollment_dto(row, project_name)


async def invite(attrs, token_info, session):
    ctx = await context(token_info)
    pid = attrs.get("project_id")
    roles = attrs.get("role_ids") or []
    project = None
    if pid:
        await validate_invitation_roles(pid, roles, token_info)
        project = await resource("projects", pid, ctx["domain_id"])
    elif roles:
        raise HTTPException(422, "Additional roles require a project")
    email = await password_policy(ctx["domain_id"], attrs["email"], password=False)
    return await issue_enrollment(
        session,
        kind="invitation",
        domain_id=ctx["domain_id"],
        email=email,
        project_id=pid,
        role_ids=roles,
        invited_by=token_info["user_id"],
        project_name=_field(project, "name", ""),
        inviter=token_info.get("username", ""),
    )


async def _historical_project(project_id, domain_id):
    if not project_id:
        return None
    ks = await _provider_call(keystone._get_admin_ks_client)
    try:
        project = await _provider_call(ks.projects.get, project_id)
    except HTTPException as exc:
        if exc.status_code == 404:
            return None
        raise
    if _field(project, "id") != project_id:
        raise HTTPException(503, "Native project identity is unavailable")
    domain_scope.assert_domain_resource(domain_id, _field(project, "domain_id"))
    return project


async def _operation_context(token_info, system_domain_id=None):
    if system_domain_id is None:
        return await context(token_info)
    if not await _provider_call(domain_scope.has_scope_authority, token_info.get("user_id")):
        raise HTTPException(403, "System administrator required")
    await domain(system_domain_id)
    return {"domain_id": system_domain_id}


async def list_invitations(token_info, session, project_id=None, *, operations=False, system_domain_id=None):
    ctx = await _operation_context(token_info, system_domain_id)
    if project_id:
        await _historical_project(project_id, ctx["domain_id"])
    scope = DomainEnrollment.domain_id == ctx["domain_id"]
    if operations and system_domain_id is not None:
        # Global account creation has no organization admission. Only verified
        # system operators may inspect and settle these unassigned operations.
        scope = or_(
            scope,
            DomainEnrollment.kind.in_(("registration", "managed_create", "external"))
            & DomainEnrollment.domain_id.is_(None),
        )
    query = select(DomainEnrollment).where(scope)
    if operations:
        query = query.where(DomainEnrollment.status.in_(RECOVERY_STATES | {"failed"}))
    else:
        query = query.where(DomainEnrollment.kind == "invitation")
    if project_id:
        query = query.where(DomainEnrollment.project_id == project_id)
    rows = (await session.execute(query.order_by(DomainEnrollment.created_at.desc()))).scalars().all()
    items = []
    for row in rows:
        if row.domain_id is not None:
            domain_scope.assert_domain_resource(ctx["domain_id"], row.domain_id)
        project = await _historical_project(row.project_id, row.domain_id)
        items.append(enrollment_dto(row, _field(project, "name", "")))
    return {"items": items}


@identity_roles._complete_mutation
async def revoke(invitation_id, token_info, session, project_id=None, *, operation=False, system_domain_id=None):
    ctx = await _operation_context(token_info, system_domain_id)
    # Lock order matches redemption. The graph lease serializes native effects
    # across durable SQL commits, including crash-recovery compensation.
    await session.rollback()
    async with _iam_write() as mutation:
        await _operation_context(token_info, system_domain_id)
        row = await _locked_enrollment(invitation_id, session)
        if (
            (
                row.domain_id != ctx["domain_id"]
                and not (
                    operation
                    and system_domain_id is not None
                    and row.kind in {"registration", "managed_create", "external"}
                    and row.domain_id is None
                )
            )
            or (not operation and row.kind != "invitation")
            or (project_id and row.project_id != project_id)
        ):
            raise HTTPException(404, "Invitation or operation not found")
        await _historical_project(row.project_id, row.domain_id)
        if row.status in {"accepted", "revoked"}:
            raise HTTPException(409, "Accepted or revoked enrollment cannot be cancelled")
        snapshot = _snapshot(row)
        if (
            row.status in RECOVERY_STATES
            or row.user_id
            or row.added_role_ids
            or row.added_grants
            or row.identity_native_name
        ) and not await _compensate(snapshot, mutation, token_info):
            await mutation[0].assert_owned()
            row.status = "recovery_required"
            row.user_id = snapshot["user_id"]
            row.creation_uncertain = snapshot["creation_uncertain"]
            _set_recovery_metadata(row, snapshot)
            await session.commit()
            raise HTTPException(503, "Native effects remain; operation requires recovery")
        await mutation[0].assert_owned()
        row.status = "revoked"
        row.user_id = snapshot["user_id"]
        row.creation_uncertain = snapshot["creation_uncertain"]
        _set_recovery_metadata(row, snapshot)
        await session.commit()


def _set_recovery_metadata(row, snapshot):
    for key in (
        "identity_domain_id",
        "domain_creation_uncertain",
        "personal_project_id",
        "project_creation_uncertain",
        "personal_domain_id",
        "personal_project_name",
        "added_grants",
    ):
        setattr(row, key, snapshot.get(key))


@identity_roles._complete_mutation
async def settle_enrollment_native_writes(
    operation_id,
    actor,
    session,
    *,
    domain_id,
    native_writes_settled,
):
    """System operator confirms provider work is finished, then records readback.

    This acknowledgement is not a retry and never creates/grants/resets native
    state. It is required after lost replies: an absent role alone cannot prove
    that an outstanding native request will not commit later.
    """
    if native_writes_settled is not True:
        raise HTTPException(422, "Confirm native_writes_settled with the strict boolean true")
    await _operation_context(actor, domain_id)
    await session.rollback()
    async with _iam_write() as mutation:
        lease, ks, _ = mutation
        await _operation_context(actor, domain_id)
        row = await _locked_enrollment(operation_id, session)
        if row.domain_id != domain_id and not (
            row.kind in {"registration", "managed_create", "external"} and row.domain_id is None
        ):
            raise HTTPException(404, "Enrollment operation not found")
        if row.status not in RECOVERY_STATES | {"failed"}:
            raise HTTPException(409, "Only interrupted enrollment operations may be settled")
        snapshot = _snapshot(row)
        attrs = {}
        if row.domain_creation_uncertain and not row.identity_native_name:
            await account_spaces.settle_shared_domains(mutation=mutation)
            attrs["domain_creation_uncertain"] = False
        if row.personal_domain_id:
            shared = await _provider_call(account_spaces.shared_domain, "personal", ks=ks)
            if _field(shared, "id") != row.personal_domain_id:
                raise HTTPException(503, "Personal domain binding changed")
            projects = await _provider_call(lambda: list(ks.projects.list(domain=row.personal_domain_id)))
            marked = [p for p in projects if _field(p, "afterglow_enrollment_id") == row.token_hash]
            if len(marked) > 1 or any(
                _field(p, "domain_id") != row.personal_domain_id
                or _field(p, "name") != row.personal_project_name
                or _field(p, "afterglow_personal_user_id") != row.user_id
                or _field(p, "afterglow_personal_primary") is not True
                for p in marked
            ):
                raise HTTPException(503, "Personal project provenance is ambiguous")
            if marked and row.personal_project_id not in {None, _field(marked[0], "id")}:
                raise HTTPException(503, "Personal project identity changed")
            attrs.update(
                personal_project_id=_field(marked[0], "id") if marked else row.personal_project_id,
                project_creation_uncertain=False,
            )
        if row.identity_native_name:
            domains = await _provider_call(lambda: list(ks.domains.list()))
            owned = [d for d in domains if _field(d, "afterglow_enrollment_id") == row.token_hash]
            if len(owned) > 1 or any(
                _field(d, "name") != row.identity_native_name
                or not isinstance(_field(d, "id"), str)
                or not _field(d, "id")
                for d in owned
            ):
                raise HTTPException(503, "Personal domain provenance is ambiguous")
            if owned and row.identity_domain_id not in {None, _field(owned[0], "id")}:
                raise HTTPException(503, "Personal domain identity changed")
            if not owned and row.identity_domain_id and any(_field(d, "id") == row.identity_domain_id for d in domains):
                raise HTTPException(503, "Personal domain provenance changed")
            did = _field(owned[0], "id") if owned else row.identity_domain_id
            attrs.update(identity_domain_id=did, domain_creation_uncertain=False)
            projects = await _provider_call(lambda: list(ks.projects.list(domain=did))) if owned else []
            marked = [p for p in projects if _field(p, "afterglow_enrollment_id") == row.token_hash]
            if len(marked) > 1 or any(
                _field(p, "domain_id") != did
                or _field(p, "name") != "Default"
                or not isinstance(_field(p, "id"), str)
                or not _field(p, "id")
                for p in marked
            ):
                raise HTTPException(503, "Personal Default provenance is ambiguous")
            if marked and row.personal_project_id not in {None, _field(marked[0], "id")}:
                raise HTTPException(503, "Personal Default identity changed")
            if (
                not marked
                and row.personal_project_id
                and any(_field(p, "id") == row.personal_project_id for p in projects)
            ):
                raise HTTPException(503, "Personal Default provenance changed")
            attrs.update(
                personal_project_id=_field(marked[0], "id") if marked else row.personal_project_id,
                project_creation_uncertain=False,
            )
        home_id = attrs.get("identity_domain_id") or row.identity_domain_id or row.domain_id
        uid = row.user_id
        if row.new_user:
            users = await _find_accounts(home_id, email=row.email, name=row.account_name)
            owned = [u for u in users if _field(u, "afterglow_enrollment_id") == row.token_hash]
            if (
                len(owned) > 1
                or any(
                    not isinstance(_field(u, "id"), str)
                    or not _field(u, "id")
                    or _field(u, "domain_id") != home_id
                    or _field(u, "name") != row.account_name
                    or _email_key(_field(u, "email", "")) != _email_key(row.email)
                    for u in owned
                )
                or (owned and uid not in {None, _field(owned[0], "id")})
            ):
                raise HTTPException(503, "Native account provenance is ambiguous")
            if uid:
                current = await _native_user(ks, uid)
                if current is not None and (
                    _field(current, "afterglow_enrollment_id") != row.token_hash
                    or _field(current, "domain_id") != home_id
                ):
                    raise HTTPException(503, "Native account provenance changed")
            uid = _field(owned[0], "id") if owned else uid
            attrs.update(user_id=uid, creation_uncertain=False)
        grants = list(row.added_grants or [])
        grants.extend(
            {"project_id": row.project_id, "domain_id": row.domain_id, "role_id": rid, "phase": "unknown"}
            for rid in row.added_role_ids
        )
        settled = []
        for grant in grants:
            if (
                not isinstance(grant, dict)
                or any(
                    not isinstance(grant.get(key), str) or not grant[key]
                    for key in ("project_id", "domain_id", "role_id")
                )
                or not uid
            ):
                raise HTTPException(503, "Native grant journal is unavailable")
            if grant.get("phase") in {"confirmed", "settled", "not_sent"}:
                settled.append(grant)
                continue
            project = await _historical_project(grant["project_id"], grant["domain_id"])
            direct = await _provider_call(project_service._assignment_rows, ks, grant["project_id"]) if project else []
            settled.append(
                {
                    **grant,
                    "phase": "settled",
                    "native_present": grant["role_id"] in project_service._direct_ids(direct, uid),
                    "settled_by": actor["user_id"],
                    "settled_at": datetime.now(UTC).isoformat(),
                }
            )
        await _save(
            row,
            session,
            snapshot,
            _lease=lease,
            **attrs,
            added_grants=settled,
            added_role_ids=[],
            status="recovery_required",
        )
        return enrollment_dto(row)


async def lookup_token(token, kind, session, *, lock=False):
    query = select(DomainEnrollment).where(
        DomainEnrollment.token_hash == hashlib.sha256(token.encode()).hexdigest(), DomainEnrollment.kind == kind
    )
    query = query.with_for_update() if lock else query
    row = (await session.execute(query.execution_options(populate_existing=True))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Invalid enrollment link")
    if enrollment_status(row) != "pending":
        raise HTTPException(410, "Enrollment link is expired, revoked, or already used")
    _assert_public_registration(row)
    return row


async def _email_account_info(email):
    """Inspect canonical ownership under the caller's graph lease, never merge."""
    accounts = await _find_accounts(None, email=email)
    if len(accounts) > 1:
        raise HTTPException(409, "account_email_ambiguous")
    result = {"email": email, "account_exists": bool(accounts)}
    if accounts:
        home = await domain(_field(accounts[0], "domain_id"))
        result.update(identity_domain_id=home["id"], identity_domain_name=home["name"])
    return result


async def invitation_info(token, session):
    row = await lookup_token(token, "invitation", session)
    row_id = row.id
    await session.rollback()
    async with _iam_write():
        row = await _locked_enrollment(row_id, session)
        if enrollment_status(row) != "pending":
            raise HTTPException(410, "Enrollment link is expired, revoked, or already used")
        dom = await organization_domain(row.domain_id)
        project = await resource("projects", row.project_id, row.domain_id) if row.project_id else None
        result = {
            **await _email_account_info(row.email),
            "domain_id": row.domain_id,
            "domain_name": dom["name"],
            "expires_at": _utc(row.expires_at).isoformat(),
            "project_name": _field(project, "name", ""),
        }
        await session.rollback()
        return result


async def signup_options(*, session=None):
    from app.services.account_recovery import recovery_enabled

    policy = await enrollment_policy.read_policy(session=session)
    ready = recovery_enabled()
    return {
        "signup_enabled": bool(policy["public_signup_enabled"] and ready),
        "signup_button_visible": bool(
            policy["public_signup_button_visible"] and policy["public_signup_enabled"] and ready
        ),
        "smtp_configured": ready,
        "recovery_enabled": ready,
        "approval_mode": policy["approval_mode"],
    }


async def _public_signup_email(email, *, session=None):
    from app.services.domain_auth import DomainAuthError, normalize_email, normalize_email_domains

    policy = await enrollment_policy.read_policy(session=session)
    if not policy["public_signup_enabled"]:
        raise HTTPException(403, "signup_disabled")
    from app.services.account_recovery import recovery_enabled

    if not recovery_enabled():
        raise HTTPException(503, "smtp_not_configured")
    try:
        email = normalize_email(email)
        allowed = normalize_email_domains(get_settings().auth.signup_email_domains)
    except DomainAuthError as exc:
        raise HTTPException(exc.status_code, exc.detail) from exc
    if len(email) > 255:
        raise HTTPException(422, "Email address is too long")
    if allowed and email.rsplit("@", 1)[1] not in allowed:
        raise HTTPException(403, "email_domain_not_allowed")
    return email


async def registration_info(token, session):
    row = await lookup_token(token, "registration", session)
    email = row.email
    row_id = row.id
    await session.rollback()
    async with _iam_write():
        # Recheck under the graph lease and SQL row lock; inspection never consumes.
        row = await _locked_enrollment(row_id, session)
        _assert_public_registration(row)
        if enrollment_status(row) != "pending":
            raise HTTPException(410, "Enrollment link is expired, revoked, or already used")
        result = await _email_account_info(email)
        if not result["account_exists"]:
            await _public_signup_email(row.email, session=session)
            await enrollment_policy.require_signup_approval(session, source="email", email=row.email)
        await session.rollback()
        return result


async def register(email, session):
    email = await _public_signup_email(email, session=session)
    # Identical delivery for existing emails; no account lookup or native writes.
    await issue_enrollment(session, kind="registration", domain_id=None, email=email)
    return {"accepted": True}


def _assert_public_registration(row):
    if row.kind == "registration" and row.domain_id is not None:
        raise HTTPException(403, "invitation_required")


async def _locked_enrollment(row_id, session):
    query = (
        select(DomainEnrollment)
        .where(DomainEnrollment.id == row_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    row = (await session.execute(query)).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Enrollment operation not found")
    return row


def _snapshot(row):
    return {
        name: getattr(row, name)
        for name in (
            "id",
            "domain_id",
            "email",
            "project_id",
            "token_hash",
            "account_name",
            "new_user",
            "requested_enabled",
            "creation_uncertain",
            "user_id",
            "added_role_ids",
            "personal_domain_name",
            "identity_domain_id",
            "identity_native_name",
            "domain_creation_uncertain",
            "personal_project_id",
            "personal_domain_id",
            "personal_project_name",
            "project_creation_uncertain",
            "added_grants",
            "personal_quotas",
        )
    }


async def _save(row, session, snapshot, *, _lease, **attrs):
    await _lease.assert_owned()
    for key, value in attrs.items():
        setattr(row, key, value)
        if key in snapshot:
            snapshot[key] = value
    await session.commit()
    await _lease.assert_owned()


async def _native_user(ks, user_id):
    try:
        user = await _provider_call(ks.users.get, user_id)
        if _field(user, "id") != user_id:
            raise HTTPException(503, "Native user identity is unavailable")
        return user
    except HTTPException as exc:
        if exc.status_code == 404:
            return None
        raise


async def _grant_enrollment_role(row, session, snapshot, mutation, project_id, domain_id, role_id):
    lease, ks, _ = mutation
    project = await _provider_call(ks.projects.get, project_id)
    if _field(project, "id") != project_id:
        raise HTTPException(503, "Enrollment project identity is unavailable")
    domain_scope.assert_domain_resource(domain_id, _field(project, "domain_id"))
    direct = await _provider_call(project_service._assignment_rows, ks, project_id)
    if role_id in project_service._direct_ids(direct, row.user_id):
        return
    grant = {"project_id": project_id, "domain_id": domain_id, "role_id": role_id, "phase": "applying"}
    plan = [*(row.added_grants or []), grant]
    try:
        await _save(row, session, snapshot, _lease=lease, added_grants=plan)
    except Exception:
        # This process did not dispatch a native grant. A crash without this
        # in-memory fact still leaves the durable applying phase fenced.
        snapshot["added_grants"] = [*plan[:-1], {**grant, "phase": "not_sent"}]
        raise
    try:
        await identity_roles._write(lease, ks.roles.grant, role_id, user=row.user_id, project=project_id)
        checked = await _provider_call(project_service._assignment_rows, ks, project_id)
        if role_id not in project_service._direct_ids(checked, row.user_id):
            raise HTTPException(503, "Enrollment role grant could not be verified")
    except Exception:
        uncertain = [*plan[:-1], {**grant, "phase": "unknown"}]
        snapshot["added_grants"] = uncertain
        try:
            await _save(row, session, snapshot, _lease=lease, added_grants=uncertain)
        except Exception:
            # The earlier committed applying intent is already non-redeemable.
            pass
        raise
    await _save(
        row,
        session,
        snapshot,
        _lease=lease,
        added_grants=[*plan[:-1], {**grant, "phase": "confirmed"}],
    )


async def _create_personal_primary(row, session, snapshot, mutation):
    snapshot["_project_create_attempted"] = True
    try:
        return await account_spaces.provision_primary(row, session, mutation)
    finally:
        # The shared helper commits every phase; retain its latest evidence if a
        # later enrollment write fails. Never erase an applying/unknown request.
        for key in ("personal_project_id", "project_creation_uncertain", "added_grants"):
            snapshot[key] = getattr(row, key)


async def _owned_personal_resources(snapshot, ks):
    """Resolve only exact operation markers; absence after uncertainty is not proof."""
    if snapshot.get("personal_domain_id"):
        did = snapshot["personal_domain_id"]
        shared = await _provider_call(account_spaces.shared_domain, "personal", ks=ks)
        if _field(shared, "id") != did:
            raise HTTPException(503, "Personal domain binding changed")
        if snapshot.get("project_creation_uncertain"):
            raise HTTPException(503, "Personal project creation outcome is unknown")
        pid = snapshot.get("personal_project_id")
        if not pid:
            return None, None
        project = await _provider_call(ks.projects.get, pid)
        if (
            _field(project, "id") != pid
            or _field(project, "domain_id") != did
            or _field(project, "afterglow_enrollment_id") != snapshot["token_hash"]
            or _field(project, "afterglow_personal_user_id") != snapshot["user_id"]
            or _field(project, "afterglow_personal_primary") is not True
        ):
            raise HTTPException(503, "Personal project provenance changed")
        return None, project
    if not snapshot.get("identity_native_name"):
        if snapshot.get("domain_creation_uncertain"):
            raise HTTPException(503, "Shared domain creation outcome is unknown")
        return None, None
    domains = await _provider_call(lambda: list(ks.domains.list()))
    owned = [d for d in domains if _field(d, "afterglow_enrollment_id") == snapshot["token_hash"]]
    if len(owned) > 1:
        raise HTTPException(503, "Personal domain provenance is ambiguous")
    domain = owned[0] if owned else None
    did = snapshot.get("identity_domain_id")
    if domain is None:
        if snapshot.get("domain_creation_uncertain"):
            raise HTTPException(503, "Personal domain creation outcome is unknown")
        if did and any(_field(d, "id") == did for d in domains):
            raise HTTPException(503, "Personal domain provenance changed")
        return None, None
    if _field(domain, "name") != snapshot["identity_native_name"] or (did and _field(domain, "id") != did):
        raise HTTPException(503, "Personal domain provenance changed")
    did = snapshot["identity_domain_id"] = _field(domain, "id")
    snapshot["domain_creation_uncertain"] = False
    projects = await _provider_call(lambda: list(ks.projects.list(domain=did)))
    for project in projects:
        domain_scope.assert_domain_resource(did, _field(project, "domain_id"))
    owned_projects = [p for p in projects if _field(p, "afterglow_enrollment_id") == snapshot["token_hash"]]
    if len(owned_projects) > 1 or len(projects) != len(owned_projects):
        raise HTTPException(503, "Personal domain contains unowned projects")
    project = owned_projects[0] if owned_projects else None
    if project:
        if _field(project, "name") != "Default" or (
            snapshot.get("personal_project_id") and _field(project, "id") != snapshot["personal_project_id"]
        ):
            raise HTTPException(503, "Personal Default provenance changed")
        snapshot["personal_project_id"] = _field(project, "id")
        snapshot["project_creation_uncertain"] = False
    elif snapshot.get("project_creation_uncertain"):
        raise HTTPException(503, "Personal Default creation outcome is unknown")
    if await _provider_call(lambda: list(ks.groups.list(domain=did))):
        raise HTTPException(503, "Personal domain contains unowned groups")
    return domain, project


async def _compensate(snapshot, mutation, actor):
    """Compensate journaled additions only; uncertain provenance stays fenced."""
    lease, ks, catalog = mutation
    try:
        await lease.assert_owned()
        personal_domain, personal_project = await _owned_personal_resources(snapshot, ks)
        home_id = snapshot.get("identity_domain_id") or snapshot["domain_id"]
        if snapshot["new_user"] and not snapshot["user_id"]:
            matches = await _find_accounts(home_id, email=snapshot["email"], name=snapshot["account_name"])
            owned = [u for u in matches if _field(u, "afterglow_enrollment_id") == snapshot["token_hash"]]
            if len(owned) > 1:
                return False
            if owned:
                snapshot["user_id"] = _field(owned[0], "id")
                snapshot["creation_uncertain"] = False
            elif snapshot["creation_uncertain"]:
                return False
        uid = snapshot["user_id"]
        user = await _native_user(ks, uid) if uid else None
        grants = list(snapshot.get("added_grants") or [])
        grants.extend(
            {"project_id": snapshot["project_id"], "domain_id": snapshot["domain_id"], "role_id": rid}
            for rid in snapshot["added_role_ids"]
        )
        if user is not None and snapshot["new_user"]:
            domain_scope.assert_domain_resource(home_id, _field(user, "domain_id"))
            if _field(user, "afterglow_enrollment_id") != snapshot["token_hash"]:
                return False
            # Never delete an account another actor has since granted authority.
            allowed = {(g["project_id"], g["role_id"]) for g in grants if g.get("phase") != "not_sent"}
            raw = await _provider_call(lambda: list(ks.role_assignments.list(user=uid)))
            for assignment in raw:
                meta = domain_projects._assignment(assignment, catalog)
                if (
                    meta["user_id"] != uid
                    or meta["group_id"]
                    or meta["inherited"]
                    or meta["kind"] != "project"
                    or (meta["scope_id"], meta["role_id"]) not in allowed
                ):
                    return False
            if await _provider_call(lambda: list(ks.groups.list(user=uid))):
                return False
            if _field(user, "enabled") is True:
                await identity_roles._session_ready({uid})
                await identity_roles._write(lease, ks.users.update, uid, enabled=False)
                checked = await _native_user(ks, uid)
                if checked is not None and _field(checked, "enabled") is not False:
                    return False
        if any(grant.get("phase") not in {"confirmed", "settled", "not_sent"} for grant in grants):
            # A failed reply/readback can precede a delayed provider commit.
            # Current absence is never authority to revoke/delete/report clean.
            return False
        if personal_domain:
            users = await _provider_call(lambda: list(ks.users.list(domain=home_id)))
            if any(_field(u, "domain_id") != home_id or _field(u, "id") != uid for u in users):
                return False
        if personal_project:
            # Exact creation provenance never substitutes for complete current
            # resource/child inventory. Unknown inventory retains recovery state.
            check = await project_service.inspect_project_empty(_field(personal_project, "id"))
            if check.get("can_delete") is not True:
                return False
        if uid:
            await identity_roles._session_ready({uid})
        for grant in reversed(grants):
            pid, rid = grant["project_id"], grant["role_id"]
            if grant.get("phase") == "not_sent":
                continue
            project = await _historical_project(pid, grant["domain_id"])
            if project is None:
                continue
            direct = await _provider_call(project_service._assignment_rows, ks, pid)
            if rid not in project_service._direct_ids(direct, uid):
                continue
            is_personal = personal_project is not None and pid == _field(personal_project, "id")
            if not is_personal:
                if identity_roles._owner_bearing_role(catalog, rid):
                    return False
                manager = domain_projects._canonical(catalog, "manager")["id"]
                if manager in {rid} | identity_roles._descendant_ids(catalog, rid):
                    await _provider_call(
                        domain_projects.assert_managers_remain,
                        ks=ks,
                        catalog=catalog,
                        user_id=uid,
                        project_id=pid,
                        role_id=rid,
                        remove_assignment=True,
                    )
            await identity_roles._write(lease, ks.roles.revoke, rid, user=uid, project=pid)
            checked = await _provider_call(project_service._assignment_rows, ks, pid)
            if rid in project_service._direct_ids(checked, uid):
                return False
        if snapshot["new_user"] and user is not None:
            if await protected_user(user, home_id, credentials=False):
                return False
            if not snapshot.get("identity_native_name"):
                await _provider_call(domain_projects.assert_managers_remain, disabled_user_ids={uid}, ks=ks)
            await identity_roles._write(lease, ks.users.update, uid, enabled=False)
            checked = await _native_user(ks, uid)
            if checked is not None and _field(checked, "enabled") is not False:
                return False
            await identity_roles._write(lease, ks.users.delete, uid)
            if await _native_user(ks, uid) is not None:
                return False
        if personal_project:
            pid = _field(personal_project, "id")
            if await _provider_call(lambda: list(ks.role_assignments.list(project=pid))):
                return False
            await identity_roles._write(lease, ks.projects.delete, pid)
            if any(
                _field(p, "id") == pid
                for p in await _provider_call(
                    lambda: list(ks.projects.list(domain=_field(personal_project, "domain_id")))
                )
            ):
                return False
        if personal_domain:
            if account_spaces.domain_kind(personal_domain) in {"account", "personal"}:
                return False
            # Recheck complete inventory before deleting the exact marked domain.
            for manager in (ks.users, ks.groups, ks.projects):
                if await _provider_call(lambda manager=manager: list(manager.list(domain=home_id))):
                    return False
            await identity_roles._write(lease, ks.domains.update, home_id, enabled=False)
            checked = await _provider_call(ks.domains.get, home_id)
            if (
                _field(checked, "enabled") is not False
                or _field(checked, "afterglow_enrollment_id") != snapshot["token_hash"]
            ):
                return False
            await identity_roles._write(lease, ks.domains.delete, home_id)
            if any(_field(d, "id") == home_id for d in await _provider_call(lambda: list(ks.domains.list()))):
                return False
        if uid:
            await project_service.invalidate_project_lists(uid, snapshot["domain_id"])
            await identity_roles._applied(
                None,
                catalog,
                None,
                {uid},
                actor or {"user_id": uid, "domain_id": snapshot["domain_id"]},
                "domain_enrollment_compensate",
                {"operation_id": snapshot["id"]},
            )
        await lease.assert_owned()
        return True
    except Exception:
        return False


async def _create_external_user(row, identity, provider, *, lease, ks):
    """Create an external-only identity, disabled until its home is verified."""
    from urllib.parse import quote

    return await identity_roles._write(
        lease,
        ks.users.create,
        name=row.account_name,
        domain=row.identity_domain_id,
        email=row.email,
        enabled=False,
        afterglow_enrollment_id=row.token_hash,
        afterglow_local_password=False,
        afterglow_external_identities=[{"issuer": identity.issuer, "subject": identity.subject}],
        federated=[
            {
                "idp_id": provider.keystone_idp_id,
                "protocols": [{"protocol_id": provider.keystone_protocol_id, "unique_id": quote(identity.subject)}],
            }
        ],
    )


async def _enroll(
    row,
    session,
    mutation,
    *,
    name=None,
    password=None,
    actor=None,
    token_info=None,
    system_managed=False,
    external_provider=None,
    external_identity=None,
    confirmed_entry=False,
):
    if enrollment_status(row) != "pending":
        raise HTTPException(410, "Enrollment link is expired, revoked, or already used")
    lease, ks, catalog = mutation
    public_signup = row.kind == "registration"
    external = row.kind == "external"
    if external != (external_provider is not None and external_identity is not None):
        raise HTTPException(403, "External enrollment proof is required")
    account_home = None
    if confirmed_entry:
        if not external or external_provider.kind != "oidc" or not external_provider.id.startswith("cfg:"):
            raise HTTPException(403, "Operator account entry proof is required")
        account_home = _field(await _provider_call(account_spaces.shared_domain, "account", ks=ks), "id")
    if public_signup:
        _assert_public_registration(row)
        row.email = await _public_signup_email(row.email, session=session)
        if row.project_id or row.role_ids:
            raise HTTPException(403, "invitation_required")
        dom = None
    elif row.domain_id is not None:
        dom = await organization_domain(row.domain_id)
        row.email = await password_policy(row.domain_id, row.email, password=token_info is None and not external)
    else:
        dom = None
    if actor is not None and not system_managed:
        await context(actor)
    if row.project_id:
        await resource("projects", row.project_id, row.domain_id)
        await validate_invitation_roles(row.project_id, row.role_ids, actor)
    target_default = None
    if row.domain_id is not None:
        target_default = await _provider_call(domain_projects.default_project, row.domain_id, ks=ks)
        if target_default is None:
            raise HTTPException(409, "domain_default_bootstrap_required")
        _, reader = domain_projects._roles(catalog)
    approval_id = None
    if token_info is not None:
        if row.kind != "invitation":
            raise HTTPException(403, "Authenticated acceptance is only for invitations")
        user = await _provider_call(ks.users.get, token_info["user_id"])
        if _field(user, "id") != token_info["user_id"]:
            raise HTTPException(503, "Authenticated invitation identity could not be verified")
        await domain(_field(user, "domain_id"))
        if _field(user, "enabled") is not True or _email_key(_field(user, "email", "")) != _email_key(row.email):
            raise HTTPException(403, "Invitation email does not match authenticated account")
        accounts = await _find_accounts(None, email=row.email)
        if len(accounts) != 1 or _field(accounts[0], "id") != token_info["user_id"]:
            raise HTTPException(409, "account_email_ambiguous")
        if await protected_user(user, row.domain_id, credentials=False):
            raise HTTPException(403, "Privileged accounts cannot receive domain IAM grants")
    else:
        if name == get_settings().os_username:
            raise HTTPException(403, "Operational account name is reserved")
        if await _find_accounts(account_home, email=row.email, name=row.email):
            raise HTTPException(409, "Account already exists; sign in to accept an invitation")
        if (
            await _find_accounts(account_home, name=name)
            or name
            and "@" in name
            and await _find_accounts(account_home, email=name)
        ):
            raise HTTPException(409, "Username already belongs to an account")
        unresolved = (
            await session.execute(
                select(DomainEnrollment.email, DomainEnrollment.account_name).where(
                    DomainEnrollment.id != row.id,
                    DomainEnrollment.new_user.is_(True),
                    DomainEnrollment.status.in_(RECOVERY_STATES),
                )
            )
        ).all()
        identifiers = {_email_key(row.email), _account_name_key(name)} - {None}
        if any(
            identifiers & ({_email_key(email), _account_name_key(account_name)} - {None})
            for email, account_name in unresolved
        ):
            raise HTTPException(409, "signup_enrollment_recovery_required")
        if public_signup or external or row.kind == "invitation":
            approval_id = await enrollment_policy.require_signup_approval(
                session,
                source=external_provider.kind if external else "email",
                email=row.email,
                issuer=external_identity.issuer if external else "",
                subject=external_identity.subject if external else "",
                domain_id=external_provider.domain_id if external else None,
                provider_id=external_provider.id if external else None,
            )
        policy = await enrollment_policy.read_policy(session=session)
        if row.personal_quotas is None:
            row.personal_quotas = dict(policy["personal_quotas"])
        user = None
    snapshot = _snapshot(row)
    create_attempted = False
    deferred_acceptance_started = False
    try:
        # Persist intent before every external write. A process crash leaves an
        # explicit non-redeemable operation, never a pending/revocable invitation.
        await _save(
            row,
            session,
            snapshot,
            _lease=lease,
            status="account_creating" if user is None else "granting",
            account_name=name,
            new_user=user is None,
            user_id=_field(user, "id"),
            creation_uncertain=False,
            identity_domain_id=_field(user, "domain_id") if user is not None else None,
        )
        if user is None:
            domains = await account_spaces.ensure_shared_domains(mutation=mutation)
            await _save(
                row,
                session,
                snapshot,
                _lease=lease,
                domain_creation_uncertain=False,
                identity_domain_id=_field(domains["account"], "id"),
                personal_domain_id=_field(domains["personal"], "id"),
                personal_project_name=account_spaces.project_name(name),
            )
            await _save(row, session, snapshot, _lease=lease, creation_uncertain=True)
            create_attempted = True
            if external:
                user = await _create_external_user(row, external_identity, external_provider, lease=lease, ks=ks)
            else:
                user = await create_account(
                    row.identity_domain_id,
                    name,
                    row.email,
                    password,
                    enabled=False,
                    marker=row.token_hash,
                    _mutation=mutation,
                )
            await _save(
                row,
                session,
                snapshot,
                _lease=lease,
                user_id=_field(user, "id"),
                creation_uncertain=False,
                status="granting",
            )
            user = await _native_user(ks, row.user_id)
            if (
                user is None
                or _field(user, "afterglow_enrollment_id") != row.token_hash
                or _field(user, "domain_id") != row.identity_domain_id
                or _field(user, "name") != name
                or _email_key(_field(user, "email", "")) != _email_key(row.email)
                or _field(user, "enabled") is not False
                or _field(user, "afterglow_local_password") is not (not external)
            ):
                raise HTTPException(503, "Native account creation provenance is unavailable")
            if external:
                from app.services import account_identity

                if {
                    "issuer": external_identity.issuer,
                    "subject": external_identity.subject,
                } not in account_identity._bindings(user) or not account_identity.has_native_binding(
                    user, external_provider, external_identity.subject
                ):
                    raise HTTPException(503, "Native external account binding could not be verified")
        uid = _field(user, "id")
        deferred_personal = row.new_user and row.kind == "managed_create" and system_managed
        if row.new_user and not deferred_personal:
            await _create_personal_primary(row, session, snapshot, mutation)
        if target_default is not None:
            await _grant_enrollment_role(
                row,
                session,
                snapshot,
                mutation,
                target_default["id"],
                row.domain_id,
                reader["id"],
            )
        if row.project_id:
            # Requested roles were reauthorized against the fresh manager and
            # trusted graph above; ownership remains an explicit separate flow.
            for rid in row.role_ids:
                if identity_roles._owner_bearing_role(catalog, rid):
                    raise HTTPException(409, "Use explicit project ownership transfer")
                await _grant_enrollment_role(row, session, snapshot, mutation, row.project_id, row.domain_id, rid)
        if row.new_user:
            await _save(row, session, snapshot, _lease=lease, status="activating")
            await identity_roles._write(lease, ks.users.update, uid, enabled=row.requested_enabled)
            checked = await _native_user(ks, uid)
            if checked is None or _field(checked, "enabled") is not row.requested_enabled:
                raise HTTPException(503, "Native account activation could not be verified")
        identity = await domain(row.identity_domain_id)
        personal = await _provider_call(account_spaces.personal_project, uid, ks=ks)
        working = await domain(personal["domain_id"]) if personal else dom or identity
        await project_service.invalidate_project_lists(uid, row.domain_id)
        if row.new_user:
            await project_service.invalidate_project_lists(uid, row.identity_domain_id)
        await domain_scope.invalidate_authority()
        await identity_roles._applied(
            None,
            catalog,
            None,
            (),
            actor or token_info or {"user_id": uid, "domain_id": row.domain_id},
            "domain_enrollment_accept",
            {"operation_id": row.id, "identity_domain_id": row.identity_domain_id},
        )
        await enrollment_policy.consume_approval(session, approval_id, user_id=uid)
        if deferred_personal:
            from app.models.account_spaces import PersonalProjectIntent

            # Accepted identity enrollment and deferred project provenance commit
            # together. No project/native grant is dispatched at administrator create.
            session.add(
                PersonalProjectIntent(
                    token_hash=row.token_hash,
                    user_id=uid,
                    primary_user_id=uid,
                    primary=True,
                    status="deferred",
                    identity_domain_id=row.identity_domain_id,
                    personal_domain_id=row.personal_domain_id,
                    personal_project_name=row.personal_project_name,
                    personal_quotas=dict(row.personal_quotas),
                    added_grants=[],
                )
            )
            deferred_acceptance_started = True
        await _save(row, session, snapshot, _lease=lease, status="accepted", accepted_at=datetime.now(UTC))
        return {
            "user_id": uid,
            "domain_id": working["id"],
            "domain_name": working["name"],
            "personal_project_id": personal["id"] if personal else None,
            "personal_project_name": personal["name"] if personal else row.personal_project_name,
            "personal_domain_id": personal["domain_id"] if personal else row.personal_domain_id,
            "personal_project_deferred": deferred_personal,
            "identity_domain_id": identity["id"],
            "identity_domain_name": identity["name"],
        }
    except Exception as exc:
        if not snapshot.get("_domain_create_attempted"):
            snapshot["domain_creation_uncertain"] = False
        if not snapshot.get("_project_create_attempted"):
            snapshot["project_creation_uncertain"] = False
        if not snapshot["user_id"] and (
            not create_attempted or isinstance(exc, HTTPException) and exc.status_code < 500
        ):
            snapshot["creation_uncertain"] = False
        try:
            await session.rollback()
        except Exception:
            pass
        if deferred_acceptance_started:
            # The combined accepted identity/deferred intent may already have
            # committed. Never delete that identity or rewrite an unknown commit.
            raise HTTPException(
                503,
                f"Enrollment operation {snapshot['id']} acceptance outcome is unknown; "
                "sign in again or ask a system administrator to reconcile the enrollment",
            ) from exc
        compensated = await _compensate(snapshot, mutation, actor or token_info)
        try:
            await lease.assert_owned()
            persisted = await _locked_enrollment(snapshot["id"], session)
            persisted.status = "failed" if compensated else "recovery_required"
            persisted.user_id = snapshot["user_id"]
            persisted.creation_uncertain = snapshot["creation_uncertain"]
            _set_recovery_metadata(persisted, snapshot)
            persisted.accepted_at = None
            await session.commit()
        except Exception:
            # The previously committed intent and exact additions remain durable;
            # no success is returned while native/SQL disposition is unknown.
            pass
        raise HTTPException(
            503,
            f"Enrollment operation {snapshot['id']} failed; "
            + ("native changes compensated" if compensated else "recovery required"),
        ) from exc


@identity_roles._complete_mutation
async def enroll_external(provider, identity, *, lease, ks, catalog, admission_domain_id=None, confirmed_entry=False):
    """Provision one personal home under the callback's existing graph lease."""
    from app.database import get_session_factory

    factory = get_session_factory()
    if factory is None:
        raise HTTPException(503, "signup_policy_storage_unavailable")
    async with factory() as session:
        # No native or enrollment effects precede the administrator decision.
        await enrollment_policy.require_signup_approval(
            session,
            source=provider.kind,
            email=identity.email,
            issuer=identity.issuer,
            subject=identity.subject,
            domain_id=provider.domain_id,
            provider_id=provider.id,
        )
        digest = hashlib.sha256((identity.issuer + "\x00" + identity.subject).encode()).hexdigest()
        row = DomainEnrollment(
            kind="external",
            domain_id=admission_domain_id,
            email=identity.email,
            token_hash=secrets.token_hex(32),
            status="pending",
            role_ids=[],
            added_role_ids=[],
            added_grants=[],
            requested_enabled=True,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            created_at=datetime.now(UTC),
        )
        session.add(row)
        await lease.assert_owned()
        await session.commit()
        result = await _enroll(
            row,
            session,
            (lease, ks, catalog),
            name="external-" + digest,
            external_provider=provider,
            external_identity=identity,
            confirmed_entry=confirmed_entry,
        )
        checked = await _native_user(ks, result["user_id"])
        if (
            checked is None
            or _field(checked, "domain_id") != result["identity_domain_id"]
            or _field(checked, "enabled") is not True
            or _field(checked, "afterglow_local_password") is not False
        ):
            raise HTTPException(503, "Native external personal identity could not be verified")
        return checked


@identity_roles._complete_mutation
async def redeem(token, kind, session, *, name=None, password=None, token_info=None):
    row = await lookup_token(token, kind, session)
    row_id = row.id
    await session.rollback()
    async with _iam_write() as mutation:
        row = await _locked_enrollment(row_id, session)
        actor = {"user_id": row.invited_by, "domain_id": row.domain_id} if row.kind == "invitation" else None
        return await _enroll(
            row,
            session,
            mutation,
            name=name,
            password=password,
            actor=actor,
            token_info=token_info,
        )
