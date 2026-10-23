"""Reserved native topology. SQL journals fence writes, never grant authority."""

from __future__ import annotations

import re
import secrets
import unicodedata
from collections.abc import Mapping
from functools import wraps

from fastapi import HTTPException
from sqlalchemy import select

from app.database import get_session_factory
from app.models.account_spaces import PersonalProjectIntent, SharedDomainIntent

_NATIVE_NAMES = {"account": "Accounts", "personal": "Personal"}
_RESERVED = frozenset(_NATIVE_NAMES)


def _field(value, key, default=None):
    return value.get(key, default) if isinstance(value, Mapping) else getattr(value, key, default)


def _complete(fn):
    @wraps(fn)
    async def call(*args, **kwargs):
        from app.services import identity_roles

        return await identity_roles._to_completion(fn(*args, **kwargs))

    return call


def domain_kind(domain):
    marker = _field(domain, "afterglow_domain_kind")
    name = str(_field(domain, "name", "")).casefold()
    # An unmanaged reserved name is fenced too, never treated as an organization.
    if name == "accounts":
        return "account"
    if name in _RESERVED:
        return name
    return marker if marker in {"account", "personal", "organization"} else "legacy"


def _rows(manager, **kwargs):
    rows = manager.list(**kwargs)
    links = getattr(rows, "links", {})
    if (
        getattr(rows, "truncated", False)
        or getattr(rows, "limited", False)
        or getattr(rows, "next", None)
        or isinstance(links, dict)
        and links.get("next")
    ):
        raise HTTPException(503, "Native topology inventory is incomplete")
    return list(rows)


def shared_domain(kind, *, ks=None, operation=None, required=True):
    if kind not in _RESERVED:
        raise ValueError("Unknown shared domain kind")
    return _shared_domain(kind, _NATIVE_NAMES[kind], ks=ks, operation=operation, required=required)


def _shared_domain(kind, native_name, *, ks=None, operation=None, required=True):
    from app.services import keystone

    ks = operation.ks if operation is not None else ks or keystone._get_admin_ks_client()
    operator_domain = native_name in _NATIVE_NAMES.values()
    candidates = [
        d
        for d in _rows(ks.domains)
        if (
            str(_field(d, "name", "")).casefold() == native_name.casefold()
            if operator_domain
            else _field(d, "name") == native_name
        )
    ]
    if not candidates:
        if not required:
            return None
        raise HTTPException(503, "Shared domain is not provisioned")
    if len(candidates) != 1:
        raise HTTPException(503, "Shared domain identity is ambiguous")
    did = _field(candidates[0], "id")
    if not isinstance(did, str) or not did:
        raise HTTPException(503, "Shared domain identity is unavailable")
    checked = operation.get("domains", did) if operation is not None else ks.domains.get(did)
    if (
        _field(checked, "id") != did
        or _field(checked, "name") != native_name
        or (
            _field(checked, "afterglow_domain_kind") not in {None, kind}
            if operator_domain
            else _field(checked, "afterglow_domain_kind") != kind
        )
        or _field(checked, "enabled") is not True
    ):
        raise HTTPException(503, "Reserved domain provenance is unavailable")
    return checked


def project_name(username):
    value = unicodedata.normalize("NFKC", str(username or "personal")).strip()
    value = re.sub(r"[^\w.-]+", "-", value, flags=re.UNICODE).strip("-.") or "personal"
    letters = "".join(secrets.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(8))
    return value[:47] + "-" + letters + f"{secrets.randbelow(100_000_000):08d}"


def _personal_member_role(catalog):
    from app.services import domain_projects, identity_roles

    member = domain_projects._canonical(catalog, "member")
    by_id = {role["id"]: role for role in catalog}
    if member["system_only"] or any(
        by_id[rid]["name"].casefold() in {"manager", "project_owner", "project_admin"}
        for rid in identity_roles._descendant_ids(catalog, member["id"])
    ):
        raise HTTPException(503, "Native personal member role has unsafe implications")
    return member


def _member_sources(sources, catalog, user_id, project_id):
    member = _personal_member_role(catalog)
    return bool(sources) and all(
        source["role_id"] == member["id"]
        and source["user_id"] == user_id
        and not source["group_id"]
        and not source["inherited"]
        and source["kind"] == "project"
        and source["scope_id"] == project_id
        for source in sources
    )


def _verify_personal_member(ks, catalog, project, user_id):
    from app.services import domain_projects, identity_roles, project_service

    pid = _field(project, "id")
    sources = domain_projects._sources(ks, project, catalog)
    if not _member_sources(sources, catalog, user_id, pid):
        raise HTTPException(503, "Personal project contains unexpected native authority")
    member = _personal_member_role(catalog)
    rows = project_service._assignment_rows(ks, pid, effective=True)
    expected = {member["id"], *identity_roles._descendant_ids(catalog, member["id"])}
    if any(project_service._principal(row, "user") != user_id for row in rows) or (
        project_service._expanded_role_ids(rows, catalog, user_id) != expected
    ):
        raise HTTPException(503, "Personal project native member could not be verified")


def personal_project(user_id, *, ks=None, operation=None):
    from app.services import identity_roles, keystone, project_service

    ks = operation.ks if operation is not None else ks or keystone._get_admin_ks_client()
    domain = shared_domain("personal", ks=ks, operation=operation, required=False)
    if domain is None:
        return None
    did = _field(domain, "id")
    matches = []
    for row in _rows(ks.projects, domain=did):
        if _field(row, "domain_id") != did:
            raise HTTPException(503, "Personal project inventory has foreign scope")
        if (
            _field(row, "afterglow_personal_user_id") != user_id
            or _field(row, "afterglow_personal_primary") is not True
        ):
            continue
        pid = _field(row, "id")
        if not isinstance(pid, str) or not pid:
            raise HTTPException(503, "Personal project identity is unavailable")
        full = operation.get("projects", pid) if operation is not None else ks.projects.get(pid)
        if (
            _field(full, "id") != pid
            or _field(full, "domain_id") != did
            or _field(full, "afterglow_personal_user_id") != user_id
            or _field(full, "afterglow_personal_primary") is not True
            or type(_field(full, "enabled")) is not bool
        ):
            raise HTTPException(503, "Personal project provenance is unavailable")
        catalog = operation.catalog() if operation is not None else identity_roles._trusted_catalog()
        from app.services import domain_projects

        sources = domain_projects._sources(ks, full, catalog)
        if not domain_projects._personal_member(sources, catalog, user_id, pid):
            raise HTTPException(503, "Personal primary membership could not be verified")
        if any(source["role_id"] == _personal_member_role(catalog)["id"] for source in sources):
            _verify_personal_member(ks, catalog, full, user_id)
        else:
            # Preserve established owner-based projects without regranting or migrating them.
            ownership = project_service._ownership_state_sync(ks, catalog, pid)
            if ownership["status"] != "unique" or ownership["owner_user_id"] != user_id:
                raise HTTPException(503, "Personal primary ownership could not be verified")
        matches.append({key: _field(full, key) for key in ("id", "name", "domain_id", "enabled")})
    if len(matches) > 1:
        raise HTTPException(503, "Personal primary project is ambiguous")
    return matches[0] if matches else None


async def assert_user_deletion_safe(user_id, *, ks, enrollment_id=None):
    """Keep Personal ownership and unfinished provisioning out of account deletion.

    Call under the identity graph lease. Settled empty receipts and not-yet-sent
    deferred intents do not own a project and must not permanently block removal.
    """
    from app.models.domain_iam import DomainEnrollment
    from app.services.project_service import _provider_call

    def inventory():
        domain = shared_domain("personal", ks=ks, required=False)
        if domain is None:
            return {}
        did = _field(domain, "id")
        projects = {}
        for project in _rows(ks.projects, domain=did):
            pid = _field(project, "id")
            if not isinstance(pid, str) or not pid or pid in projects or _field(project, "domain_id") != did:
                raise HTTPException(503, "personal_project_provenance_unavailable")
            full = ks.projects.get(pid)
            if _field(full, "id") != pid or _field(full, "domain_id") != did:
                raise HTTPException(503, "personal_project_provenance_unavailable")
            projects[pid] = full
            if _field(full, "afterglow_personal_user_id") == user_id:
                raise HTTPException(409, "Remove owned Personal projects before deleting this identity")
        return projects

    projects = await _provider_call(inventory)
    async with _factory()() as session:
        intents = (
            (await session.execute(select(PersonalProjectIntent).where(PersonalProjectIntent.user_id == user_id)))
            .scalars()
            .all()
        )
        for intent in intents:
            if intent.personal_project_id in projects:
                raise HTTPException(409, "Remove owned Personal projects before deleting this identity")
            if (
                intent.project_creation_uncertain
                or intent.status not in {"accepted", "cancelled", "deferred"}
                or intent.status != "accepted"
                and intent.added_grants
            ):
                raise HTTPException(409, "Resolve Personal project provisioning before deleting this identity")
        enrollments = (
            (
                await session.execute(
                    select(DomainEnrollment).where(
                        (DomainEnrollment.user_id == user_id)
                        | (DomainEnrollment.token_hash == enrollment_id if enrollment_id else False)
                    )
                )
            )
            .scalars()
            .all()
        )
        for enrollment in enrollments:
            if enrollment.personal_project_id in projects:
                raise HTTPException(409, "Remove owned Personal projects before deleting this identity")
            if (
                enrollment.creation_uncertain
                or enrollment.domain_creation_uncertain
                or enrollment.project_creation_uncertain
                or enrollment.status
                not in {"accepted", "revoked", "failed", "pending", "delivery_pending", "delivery_failed"}
                or enrollment.status != "accepted"
                and (enrollment.added_grants or enrollment.added_role_ids)
            ):
                raise HTTPException(409, "Resolve account enrollment before deleting this identity")


def _factory():
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(503, "account_topology_storage_unavailable")
    return factory


async def ensure_shared_domains(*, mutation):
    """Resolve operator-owned domains; enrollment never creates shared domains."""
    from app.services.project_service import _provider_call

    lease, ks, _ = mutation
    await lease.assert_owned()
    return {kind: await _provider_call(shared_domain, kind, ks=ks) for kind in ("account", "personal")}


def _personal_retryable(row):
    if (
        row.status not in {"deferred", "creating", "project_ready", "grant_ready", "quotas_ready"}
        or row.project_creation_uncertain
        or any(g.get("phase") not in {"confirmed", "settled", "not_sent"} for g in row.added_grants)
    ):
        return False
    # Old creating rows with a project ID predate per-step quota/activation
    # receipts. Matching readback cannot establish that those calls have ended.
    return (
        (row.personal_project_id is None) if row.status in {"deferred", "creating"} else bool(row.personal_project_id)
    )


async def provision_primary(row, session, mutation):
    """Disabled staging with durable, non-replayable native phase boundaries."""
    from app.services import domain_iam, enrollment_policy, identity_roles
    from app.services.project_service import _provider_call

    lease, ks, catalog = mutation
    did = row.personal_domain_id
    primary = getattr(row, "primary", True)
    durable = isinstance(row, PersonalProjectIntent)
    member = _personal_member_role(catalog)
    snapshot = {key: getattr(row, key) for key in ("user_id", "added_grants")}

    async def save(**attrs):
        await domain_iam._save(row, session, snapshot, _lease=lease, **attrs)

    if durable and not _personal_retryable(row):
        raise HTTPException(503, "personal_project_recovery_required")
    pid = row.personal_project_id
    if pid is None:
        # A safe/not-sent retry keeps this exact name, marker and quota snapshot.
        # Any interruption after this commit needs explicit native settlement.
        marked = [
            p
            for p in await _provider_call(_rows, ks.projects, domain=did)
            if _field(p, "afterglow_enrollment_id") == row.token_hash
        ]
        if marked:
            await save(project_creation_uncertain=True)
            raise HTTPException(503, "personal_project_recovery_required")
        await save(project_creation_uncertain=True)
        project = await identity_roles._write(
            lease,
            ks.projects.create,
            name=row.personal_project_name,
            domain=did,
            enabled=False,
            description=getattr(row, "description", "") or "Personal project",
            afterglow_enrollment_id=row.token_hash,
            afterglow_personal_user_id=row.user_id,
            afterglow_personal_primary=primary,
        )
        pid = _field(project, "id")
        if not isinstance(pid, str) or not pid:
            raise HTTPException(503, "Personal project identity is unavailable")
    checked = await _provider_call(ks.projects.get, pid)
    if (
        _field(checked, "id") != pid
        or _field(checked, "domain_id") != did
        or _field(checked, "name") != row.personal_project_name
        or _field(checked, "afterglow_personal_user_id") != row.user_id
        or _field(checked, "afterglow_personal_primary") is not primary
        or _field(checked, "afterglow_enrollment_id") != row.token_hash
        or _field(checked, "enabled") is not False
    ):
        raise HTTPException(503, "Personal project creation provenance is unavailable")
    if row.personal_project_id is None:
        await save(
            personal_project_id=pid,
            project_creation_uncertain=False,
            **({"status": "project_ready"} if durable else {}),
        )
    if not durable or row.status == "project_ready":
        await domain_iam._grant_enrollment_role(row, session, snapshot, mutation, pid, did, member["id"])
        await _provider_call(_verify_personal_member, ks, catalog, checked, row.user_id)
        if durable:
            await save(status="grant_ready")
    if not durable or row.status == "grant_ready":
        if durable:
            await save(status="quotas_applying")
        await enrollment_policy.initialize_personal_quotas(pid, row.personal_quotas, lease=lease)
        if durable:
            await save(status="quotas_ready")
    await _provider_call(_verify_personal_member, ks, catalog, checked, row.user_id)
    if durable and not await _quota_matches(pid, row.personal_quotas, lease):
        raise HTTPException(503, "Personal project quota provenance changed")
    if durable:
        await save(status="activating")
    await identity_roles._write(lease, ks.projects.update, pid, enabled=True)
    checked = await _provider_call(ks.projects.get, pid)
    if (
        _field(checked, "id") != pid
        or _field(checked, "domain_id") != did
        or _field(checked, "afterglow_personal_user_id") != row.user_id
        or _field(checked, "afterglow_personal_primary") is not primary
        or _field(checked, "enabled") is not True
    ):
        raise HTTPException(503, "Personal project activation could not be verified")
    if durable:
        await save(status="accepted")
    return {key: _field(checked, key) for key in ("id", "name", "domain_id", "enabled")}


async def _human(user_id, mutation):
    from app.services import domain_projects, identity_roles, project_service
    from app.services.project_service import _provider_call

    _, ks, catalog = mutation
    user = await _provider_call(ks.users.get, user_id)
    if _field(user, "id") != user_id or _field(user, "enabled") is not True:
        raise HTTPException(403, "An enabled human identity is required")
    home_id = _field(user, "domain_id")
    if not isinstance(home_id, str) or not home_id:
        raise HTTPException(503, "Human identity home is unavailable")
    home = await _provider_call(ks.domains.get, home_id)
    if _field(home, "id") != home_id or _field(home, "enabled") is not True:
        raise HTTPException(403, "Human identity home is disabled")
    raw = await _provider_call(lambda: list(ks.role_assignments.list(user=user_id, effective=True)))
    expanded = project_service._expanded_role_ids(raw, catalog, user_id)
    # Keystone effective assignments omit system scope. Inspect exact native
    # user/group system sources as well; a configured operator *name* is not a
    # service identity and must not exempt an interactive Accounts administrator.
    if any(role["name"] == "service" and role["domain_id"] is None for role in catalog):
        system_rows = [
            (row, "user_id", user_id)
            for row in await _provider_call(lambda: list(ks.role_assignments.list(user=user_id, system="all")))
        ]
        groups = await _provider_call(lambda: list(ks.groups.list(user=user_id)))
        for group in groups:
            gid = _field(group, "id")
            if not isinstance(gid, str) or not gid:
                raise HTTPException(503, "Human identity group membership is unavailable")
            system_rows.extend(
                (row, "group_id", gid)
                for row in await _provider_call(lambda gid=gid: list(ks.role_assignments.list(group=gid, system="all")))
            )
        for row, principal, subject in system_rows:
            source = domain_projects._assignment(row, catalog)
            if source["kind"] == "system" and source[principal] == subject:
                expanded.update({source["role_id"], *identity_roles._descendant_ids(catalog, source["role_id"])})
    if any(r["id"] in expanded and r["name"] == "service" and r["domain_id"] is None for r in catalog):
        raise HTTPException(403, "service_identity_personal_forbidden")
    return user


async def personal_recovery_status(user_id, identity_domain_id):
    """Only call after fresh native subject proof; no credential or peer inventory."""
    async with _factory()() as session:
        row = (
            await session.execute(select(PersonalProjectIntent).where(PersonalProjectIntent.primary_user_id == user_id))
        ).scalar_one_or_none()
        if row is None or row.status == "accepted" or row.identity_domain_id != identity_domain_id:
            return None
        retryable = _personal_retryable(row)
        return {
            "code": "personal_project_retry_available" if retryable else "personal_project_recovery_required",
            "operation_id": row.token_hash,
            "retryable": retryable,
            "native_calls_settled_required": not retryable,
        }


async def _create_intent(user, session, mutation, *, primary, description="", personal_quotas=None):
    from app.services import enrollment_policy

    domains = await ensure_shared_domains(mutation=mutation)
    policy = await enrollment_policy.read_policy(session=session) if personal_quotas is None else None
    uid = _field(user, "id")
    intent = PersonalProjectIntent(
        user_id=uid,
        primary_user_id=uid if primary else None,
        primary=primary,
        token_hash=secrets.token_hex(32),
        status="creating",
        description=description,
        identity_domain_id=_field(user, "domain_id"),
        personal_domain_id=_field(domains["personal"], "id"),
        personal_project_name=project_name(_field(user, "name")),
        personal_quotas=dict(policy["personal_quotas"] if personal_quotas is None else personal_quotas),
        added_grants=[],
    )
    session.add(intent)
    await mutation[0].assert_owned()
    await session.commit()
    return await provision_primary(intent, session, mutation)


@_complete
async def ensure_personal_project(user_id, *, operation=None):
    """Verified human login only; do not move/reset native user or existing grants."""
    from app.services import domain_iam, project_service
    from app.services.project_service import _provider_call

    if operation is not None:
        operation.invalidate()
    async with domain_iam._iam_write() as mutation:
        _, ks, _ = mutation
        user = await _human(user_id, mutation)
        async with _factory()() as session:
            intent = (
                await session.execute(
                    select(PersonalProjectIntent)
                    .where(PersonalProjectIntent.primary_user_id == user_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            # An interrupted new-account enrollment may have created the user but
            # not the project; never turn the next login into a second provisioner.
            from app.models.domain_iam import DomainEnrollment

            enrollments = (
                (
                    await session.execute(
                        select(DomainEnrollment).where(
                            DomainEnrollment.user_id == user_id, DomainEnrollment.new_user.is_(True)
                        )
                    )
                )
                .scalars()
                .all()
            )
            if any(row.status != "accepted" for row in enrollments):
                raise HTTPException(503, "personal_project_recovery_required")
            if any(row.identity_domain_id not in {None, _field(user, "domain_id")} for row in enrollments):
                raise HTTPException(503, "Enrollment identity home changed")
            deferred = [row for row in enrollments if row.kind == "managed_create" and row.personal_project_id is None]
            if len(deferred) > 1:
                raise HTTPException(503, "Deferred personal enrollment is ambiguous")
            if deferred:
                enrollment = deferred[0]
                original = await session.get(PersonalProjectIntent, enrollment.token_hash)
                if (
                    original is None
                    or original.user_id != user_id
                    or original.identity_domain_id != _field(user, "domain_id")
                    or original.personal_domain_id != enrollment.personal_domain_id
                    or original.personal_quotas != enrollment.personal_quotas
                    or (intent is None and original.status != "cancelled")
                    or intent is not None
                    and (
                        intent.personal_quotas != enrollment.personal_quotas
                        or original.status != "cancelled"
                        and original.token_hash != intent.token_hash
                    )
                ):
                    raise HTTPException(503, "Deferred personal enrollment provenance changed")
            expected = [row for row in enrollments if row.personal_domain_id is not None and row not in deferred]
            if len(expected) > 1:
                raise HTTPException(503, "Accepted personal primary binding is ambiguous")
            if intent is not None:
                shared = await _provider_call(shared_domain, "personal", ks=ks)
                if (
                    intent.user_id != user_id
                    or intent.identity_domain_id != _field(user, "domain_id")
                    or intent.personal_domain_id != _field(shared, "id")
                ):
                    raise HTTPException(503, "Personal identity binding changed")
                if intent.status != "accepted":
                    await provision_primary(intent, session, mutation)
            existing = await _provider_call(personal_project, user_id, ks=ks)
            if (
                len(expected) > 1
                or expected
                and (
                    existing is None
                    or existing["id"] != expected[0].personal_project_id
                    or existing["domain_id"] != expected[0].personal_domain_id
                )
            ):
                raise HTTPException(503, "Accepted personal primary binding changed")
            if existing is not None:
                if not existing["enabled"] or intent is not None and intent.personal_project_id != existing["id"]:
                    raise HTTPException(503, "Personal primary binding is unavailable")
                if deferred:
                    deferred[0].personal_project_id = existing["id"]
                    deferred[0].personal_project_name = existing["name"]
                    await mutation[0].assert_owned()
                    await session.commit()
                return existing
            if intent is not None:
                raise HTTPException(503, "Personal primary binding is missing")
            restart_quotas = deferred[0].personal_quotas if deferred else None
            if restart_quotas is None:
                previous = (
                    await session.execute(
                        select(PersonalProjectIntent)
                        .where(
                            PersonalProjectIntent.user_id == user_id,
                            PersonalProjectIntent.primary.is_(True),
                            PersonalProjectIntent.status == "cancelled",
                        )
                        .order_by(PersonalProjectIntent.created_at.desc(), PersonalProjectIntent.token_hash.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if previous is not None:
                    if previous.identity_domain_id != _field(user, "domain_id"):
                        raise HTTPException(503, "Settled personal identity home changed")
                    restart_quotas = previous.personal_quotas
            result = await _create_intent(
                user,
                session,
                mutation,
                primary=True,
                personal_quotas=restart_quotas,
            )
            if deferred:
                deferred[0].personal_project_id = result["id"]
                deferred[0].personal_project_name = result["name"]
                await mutation[0].assert_owned()
                await session.commit()
            await project_service.invalidate_project_lists(user_id, result["domain_id"])
            if operation is not None:
                operation.invalidate()
            return result


@_complete
async def create_personal_project(user_id, *, description="", operation=None):
    """Create a generated non-primary project using the same quota and role fence."""
    from app.services import domain_iam, project_service

    if not isinstance(description, str) or len(description) > 255:
        raise HTTPException(422, "Personal project description is too long")
    if operation is not None:
        operation.invalidate()
    async with domain_iam._iam_write() as mutation:
        user = await _human(user_id, mutation)
        async with _factory()() as session:
            unresolved = (
                await session.execute(
                    select(PersonalProjectIntent.token_hash)
                    .where(
                        PersonalProjectIntent.user_id == user_id,
                        PersonalProjectIntent.status.not_in({"accepted", "cancelled"}),
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            if unresolved is not None:
                raise HTTPException(503, "personal_project_recovery_required")
            result = await _create_intent(user, session, mutation, primary=False, description=description)
            await project_service.invalidate_project_lists(user_id, result["domain_id"])
            if operation is not None:
                operation.invalidate()
            return result


async def settle_shared_domains(*, mutation, kind=None):
    """Settle native effects only after explicit system-operator acknowledgement."""
    from app.services.project_service import _provider_call

    lease, ks, _ = mutation
    async with _factory()() as session:
        query = select(SharedDomainIntent).with_for_update()
        if kind is not None:
            query = query.where(SharedDomainIntent.kind == kind)
        rows = (await session.execute(query)).scalars().all()
        for row in rows:
            semantic_kind = "account" if row.kind == "accounts" else row.kind
            existing = await _provider_call(_shared_domain, semantic_kind, row.kind, ks=ks, required=False)
            if row.status == "accepted" and (existing is None or _field(existing, "id") != row.domain_id):
                raise HTTPException(503, "Accepted shared domain binding changed")
            if existing is not None:
                if _field(existing, "afterglow_topology_id") != row.marker:
                    raise HTTPException(503, "Shared domain creation provenance changed")
                row.domain_id, row.status = _field(existing, "id"), "accepted"
            else:
                row.status = "settled_absent"
        await lease.assert_owned()
        await session.commit()


async def _system_actor(actor):
    from app.services import domain_scope
    from app.services.project_service import _provider_call

    if not await _provider_call(domain_scope.has_scope_authority, actor.get("user_id")):
        raise HTTPException(403, "System administrator required")


def _intent_dto(row):
    return {
        "id": row.token_hash,
        "user_id": row.user_id,
        "identity_domain_id": row.identity_domain_id,
        "personal_domain_id": row.personal_domain_id,
        "personal_project_id": row.personal_project_id,
        "personal_project_name": row.personal_project_name,
        "primary": row.primary,
        "status": row.status,
    }


async def topology_operations(actor, *, cursor=None):
    await _system_actor(actor)
    if cursor is not None and (not isinstance(cursor, str) or re.fullmatch(r"[a-f0-9]{64}", cursor) is None):
        raise HTTPException(422, "Invalid topology operation cursor")
    async with _factory()() as session:
        shared = (await session.execute(select(SharedDomainIntent))).scalars().all()
        query = select(PersonalProjectIntent).where(PersonalProjectIntent.status.not_in({"accepted", "cancelled"}))
        if cursor is not None:
            query = query.where(PersonalProjectIntent.token_hash > cursor)
        personal = (await session.execute(query.order_by(PersonalProjectIntent.token_hash).limit(101))).scalars().all()
        return {
            "shared_domains": [{"kind": row.kind, "domain_id": row.domain_id, "status": row.status} for row in shared],
            "personal_projects": [_intent_dto(row) for row in personal[:100]],
            "next_cursor": personal[99].token_hash if len(personal) > 100 else None,
        }


@_complete
async def settle_shared_domain(kind, actor, *, native_calls_settled):
    from app.services import domain_iam

    if native_calls_settled is not True:
        raise HTTPException(422, "Confirm native_calls_settled with strict boolean true")
    if kind not in _RESERVED | {"accounts"}:
        raise HTTPException(404, "Shared domain intent not found")
    async with domain_iam._iam_write() as mutation:
        await _system_actor(actor)
        async with _factory()() as session:
            if await session.get(SharedDomainIntent, kind) is None:
                raise HTTPException(404, "Shared domain intent not found")
        await settle_shared_domains(mutation=mutation, kind=kind)
        async with _factory()() as session:
            row = await session.get(SharedDomainIntent, kind)
            return {"kind": row.kind, "domain_id": row.domain_id, "status": row.status}


async def _quota_matches(project_id, quotas, lease):
    from app.config import get_settings
    from app.services import enrollment_policy, keystone, quota_native
    from app.services.project_service import _provider_call

    values = enrollment_policy._limits(quotas)
    conn = await _provider_call(keystone.get_admin_project_connection)
    try:
        for section, fields in quota_native.QUOTA_FIELDS.items():
            if section == "file_storage" and not get_settings().service_manila_enabled:
                continue
            selected = {native: values[key] for key, native in fields.items() if key in values}
            if selected:
                current = await _provider_call(quota_native.get_section, conn, project_id, section)
                if any(current.get(key, {}).get("limit") != value for key, value in selected.items()):
                    return False
        await lease.assert_owned()
        return True
    finally:
        await _provider_call(conn.close)


@_complete
async def settle_personal_project(operation_id, actor, *, native_calls_settled):
    """Acknowledge completed native work, then accept observed success or clean staging.

    Never replay creates/grants, mutate an existing user, or delete shared domains.
    Every cleanup write is preceded by a durable recovery state and fresh scope.
    """
    from app.services import domain_iam, domain_projects, identity_roles, project_service
    from app.services.project_service import _provider_call

    if native_calls_settled is not True:
        raise HTTPException(422, "Confirm native_calls_settled with strict boolean true")
    async with domain_iam._iam_write() as mutation:
        lease, ks, catalog = mutation
        await _system_actor(actor)
        async with _factory()() as session:
            row = (
                await session.execute(
                    select(PersonalProjectIntent)
                    .where(PersonalProjectIntent.token_hash == operation_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if row is None:
                raise HTTPException(404, "Personal project operation not found")
            if row.status == "cancelled":
                return _intent_dto(row)
            user = await _human(row.user_id, mutation)
            if _field(user, "domain_id") != row.identity_domain_id:
                raise HTTPException(503, "Personal identity home changed")
            shared = await _provider_call(shared_domain, "personal", ks=ks)
            if _field(shared, "id") != row.personal_domain_id:
                raise HTTPException(503, "Personal domain binding changed")
            projects = await _provider_call(_rows, ks.projects, domain=row.personal_domain_id)
            marked = [p for p in projects if _field(p, "afterglow_enrollment_id") == row.token_hash]
            if row.status == "accepted" and not marked:
                raise HTTPException(409, "Accepted personal project binding is missing")
            if len(marked) > 1:
                raise HTTPException(503, "Personal project creation is ambiguous")
            if not marked:
                if row.personal_project_id and any(_field(p, "id") == row.personal_project_id for p in projects):
                    raise HTTPException(503, "Personal project provenance changed")
                row.status, row.primary_user_id, row.project_creation_uncertain = "cancelled", None, False
                await lease.assert_owned()
                await session.commit()
                return _intent_dto(row)
            project = marked[0]
            pid = _field(project, "id")
            checked = await _provider_call(ks.projects.get, pid)
            if (
                not isinstance(pid, str)
                or not pid
                or row.personal_project_id not in {None, pid}
                or _field(checked, "id") != pid
                or _field(checked, "domain_id") != row.personal_domain_id
                or _field(checked, "name") != row.personal_project_name
                or _field(checked, "afterglow_enrollment_id") != row.token_hash
                or _field(checked, "afterglow_personal_user_id") != row.user_id
                or _field(checked, "afterglow_personal_primary") is not row.primary
                or type(_field(checked, "enabled")) is not bool
            ):
                raise HTTPException(503, "Personal project provenance changed")
            member = _personal_member_role(catalog)
            allowed = {member["id"]}
            planned = {grant["role_id"] for grant in row.added_grants if grant["project_id"] == pid}
            legacy = bool(planned - allowed)
            if legacy:
                owner = project_service._required_project_role(catalog, "project_owner", require_hierarchy=True)
                reader = project_service._required_project_role(catalog, "project_reader", require_hierarchy=True)
                allowed = {owner["id"], reader["id"]}
                if not planned <= allowed:
                    raise HTTPException(409, "Personal project recovery plan has unexpected authority")
            raw = await _provider_call(lambda: list(ks.role_assignments.list(project=pid)))
            for assignment in raw:
                meta = domain_projects._assignment(assignment, catalog)
                if (
                    meta["user_id"] != row.user_id
                    or meta["group_id"]
                    or meta["inherited"]
                    or meta["kind"] != "project"
                    or meta["scope_id"] != pid
                    or meta["role_id"] not in allowed
                ):
                    raise HTTPException(409, "Personal project has unowned authority")
            direct = project_service._direct_ids(raw, row.user_id)
            if _field(checked, "enabled") is True:
                if direct != allowed or not await _quota_matches(pid, row.personal_quotas, lease):
                    raise HTTPException(409, "Active personal project is not fully verified")
                if legacy:
                    await project_service._verify_unique_owner(ks, catalog, pid, row.user_id)
                else:
                    await _provider_call(_verify_personal_member, ks, catalog, checked, row.user_id)
                row.personal_project_id, row.project_creation_uncertain, row.status = pid, False, "accepted"
                row.added_grants = [{**grant, "phase": "settled"} for grant in row.added_grants]
                await lease.assert_owned()
                await session.commit()
                return _intent_dto(row)
            if row.status == "accepted":
                raise HTTPException(409, "Accepted personal project is no longer active")
            empty = await project_service.inspect_project_empty(pid)
            if empty.get("can_delete") is not True:
                raise HTTPException(409, "Personal project resource inventory is not empty")
            row.personal_project_id, row.project_creation_uncertain, row.status = pid, False, "recovering"
            await lease.assert_owned()
            await session.commit()
            for rid in sorted(direct):
                await identity_roles._write(lease, ks.roles.revoke, rid, user=row.user_id, project=pid)
                current = await _provider_call(project_service._assignment_rows, ks, pid)
                if rid in project_service._direct_ids(current, row.user_id):
                    raise HTTPException(503, "Personal project cleanup readback failed")
            if await _provider_call(lambda: list(ks.role_assignments.list(project=pid))):
                raise HTTPException(409, "Personal project authority changed during cleanup")
            checked = await _provider_call(ks.projects.get, pid)
            if (
                _field(checked, "id") != pid
                or _field(checked, "domain_id") != row.personal_domain_id
                or _field(checked, "name") != row.personal_project_name
                or _field(checked, "afterglow_personal_user_id") != row.user_id
                or _field(checked, "afterglow_personal_primary") is not row.primary
                or _field(checked, "enabled") is not False
                or _field(checked, "afterglow_enrollment_id") != row.token_hash
            ):
                raise HTTPException(409, "Personal project changed during cleanup")
            if (await project_service.inspect_project_empty(pid)).get("can_delete") is not True:
                raise HTTPException(409, "Personal project inventory changed during cleanup")
            await identity_roles._write(lease, ks.projects.delete, pid)
            if any(
                _field(p, "id") == pid for p in await _provider_call(_rows, ks.projects, domain=row.personal_domain_id)
            ):
                raise HTTPException(503, "Personal project cleanup could not be verified")
            row.status, row.primary_user_id = "cancelled", None
            row.added_grants = [{**grant, "phase": "settled"} for grant in row.added_grants]
            await lease.assert_owned()
            await session.commit()
            await project_service.invalidate_project_lists(row.user_id, row.personal_domain_id)
            return _intent_dto(row)
