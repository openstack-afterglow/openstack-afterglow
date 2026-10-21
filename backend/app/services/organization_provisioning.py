"""Operator-bound OIDC organizations, with durable one-dispatch native fences.

SQL records correlation/uncertainty, never membership authority. Native enabled
user/home, exact organization markers, Default and grants are reread each time.
No request adopts an unknown tenant or replays an uncertain create. Additive
role grants use exact native check/write/readback, never a shared tenant lockout.
Display names and provider aliases are deliberately not identities.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.models.organization_provisioning import OrganizationBinding
from app.services import domain_projects, identity_roles
from app.services.domain_auth import (
    DomainAuthConflict,
    DomainAuthDenied,
    DomainAuthInvalid,
    DomainAuthNotFound,
    DomainAuthUnavailable,
    _factory,
)

_field = identity_roles._field


def binding_key(issuer, external_org_id):
    return hashlib.sha256(
        json.dumps([issuer, external_org_id], ensure_ascii=True, separators=(",", ":")).encode()
    ).hexdigest()


def _configuration(row, identity):
    organization = getattr(row, "_organization", None)
    if (
        not row.id.startswith("cfg:")
        or row.kind != "oidc"
        or organization is None
        or identity.issuer != row.issuer_url
        or not identity.subject
    ):
        raise DomainAuthDenied("Trusted organization configuration is required", code="organization_binding_invalid")
    return organization


def _check_binding(binding, row, organization, key):
    if binding.binding_key != key or binding.issuer_url != row.issuer_url or binding.external_org_id != organization.id:
        raise DomainAuthConflict("Organization trust binding changed", code="organization_binding_changed")
    if binding.status != "active" or not binding.domain_id:
        raise DomainAuthUnavailable(
            "Organization operation requires settlement", code="organization_operation_uncertain"
        )


def _native_domains(ks):
    """Inspect raw collection completeness before SDK projection discards it."""
    transport = getattr(ks.domains, "client", None)
    if transport is not None and callable(getattr(transport, "get", None)):
        _, body = transport.get("/domains")
        if (
            not isinstance(body, dict)
            or not isinstance(body.get("domains"), list)
            or not isinstance(body.get("links"), dict)
            or body["links"].get("next")
            or body.get("truncated")
            or body.get("limited")
        ):
            raise DomainAuthUnavailable("Organization inventory is incomplete")
        rows = body["domains"]
    else:
        rows = ks.domains.list()
        links = getattr(rows, "links", {})
        if (
            getattr(rows, "truncated", False)
            or getattr(rows, "limited", False)
            or getattr(rows, "next", None)
            or (isinstance(links, dict) and links.get("next"))
        ):
            raise DomainAuthUnavailable("Organization inventory is incomplete")
    ids, result = set(), []
    for row in rows:
        did = _field(row, "id")
        if not isinstance(did, str) or not did or did in ids:
            raise DomainAuthUnavailable("Organization inventory is invalid")
        ids.add(did)
        result.append(domain_projects._exact(ks.domains, did))
    return result


def _native_binding(ks, binding):
    """Exact bound domain only; inventory scans are reserved for pre-create uniqueness."""
    domain = domain_projects._exact(ks.domains, binding.domain_id)
    if _field(domain, "afterglow_organization_binding") != binding.binding_key:
        raise DomainAuthConflict(
            "Native organization binding is unknown or changed", code="organization_binding_changed"
        )
    if (
        _field(domain, "afterglow_domain_kind") != "organization"
        or _field(domain, "afterglow_organization_issuer") != binding.issuer_url
        or _field(domain, "afterglow_organization_id") != binding.external_org_id
        or _field(domain, "afterglow_organization_intent") != binding.intent_id
        or _field(domain, "afterglow_created_by") != binding.creator_user_id
    ):
        raise DomainAuthConflict("Native organization binding changed", code="organization_binding_changed")
    if not domain_projects._enabled(domain):
        raise DomainAuthDenied("Organization is disabled", code="organization_disabled")
    return domain


async def admit(row, identity, user, *, lease, ks, catalog):
    """Resolve/create trusted org then add reader and explicitly configured manager.

    Caller owns the identity graph lease. A committed creation intent survives
    cancellation, native timeout or SQL failure. Per-user grants never lock out
    unrelated organization members; current native state is their authority.
    """
    from app.services.account_identity import require_enrollment_complete
    from app.services.project_service import _assignment_rows, _direct_ids

    organization = _configuration(row, identity)
    uid = _field(user, "id")
    current = await asyncio.to_thread(domain_projects._active_user, ks, uid, authenticated=True)
    await require_enrollment_complete(current)
    key = binding_key(identity.issuer, organization.id)
    manager_subject = identity.subject in organization.manager_subjects
    factory = _factory()
    try:
        async with factory() as session:
            binding = await session.get(OrganizationBinding, key, with_for_update=True)
            if binding is None:
                if not manager_subject:
                    raise DomainAuthDenied(
                        "A configured manager must establish this organization", code="organization_manager_required"
                    )
                native = await asyncio.to_thread(_native_domains, ks)
                if any(_field(item, "afterglow_organization_binding") == key for item in native):
                    raise DomainAuthConflict(
                        "Organization has no confirmed durable binding", code="organization_binding_unknown"
                    )
                binding = OrganizationBinding(
                    binding_key=key,
                    issuer_url=identity.issuer,
                    external_org_id=organization.id,
                    client_id=row.client_id,
                    creator_user_id=uid,
                    intent_id=str(uuid4()),
                    status="creating",
                )
                session.add(binding)
                await session.commit()  # durable intent BEFORE native create
                try:
                    created = await domain_projects.create_domain(
                        name=organization.name,
                        description="",
                        enabled=True,
                        creator_id=uid,
                        mutation=(lease, ks, catalog),
                        metadata={
                            "afterglow_organization_binding": key,
                            "afterglow_organization_issuer": identity.issuer,
                            "afterglow_organization_id": organization.id,
                            "afterglow_organization_intent": binding.intent_id,
                        },
                    )
                except BaseException as exc:
                    if getattr(exc, "native_create_dispatched", None) is False:
                        await session.delete(binding)  # proven predispatch rejection, no native effect
                    else:
                        binding.status = "uncertain"
                        binding.updated_at = datetime.now(UTC)
                    await session.commit()
                    raise
                binding.domain_id = created["id"]
                await session.commit()  # retain exact returned ID even if native readback fails
                await asyncio.to_thread(_native_binding, ks, binding)
                binding.status = "active"
                binding.updated_at = datetime.now(UTC)
                await session.commit()
            else:
                _check_binding(binding, row, organization, key)
                await asyncio.to_thread(_native_binding, ks, binding)
            await asyncio.to_thread(_native_binding, ks, binding)
            await asyncio.to_thread(domain_projects._active_user, ks, uid, authenticated=True)
            project = await asyncio.to_thread(domain_projects.default_project, binding.domain_id, ks=ks)
            if project is None:
                raise DomainAuthConflict("Organization Default is missing", code="domain_default_required")
            await domain_projects._ensure_reader(lease, ks, catalog, project["id"], uid)
            manager, _ = domain_projects._roles(catalog)
            direct = await asyncio.to_thread(_assignment_rows, ks, project["id"])
            if manager_subject and manager["id"] not in _direct_ids(direct, uid):
                await identity_roles._write(lease, ks.roles.grant, manager["id"], user=uid, project=project["id"])
                await domain_projects._invalidate(binding.domain_id, {uid})
            await domain_projects._sync(binding.domain_id, lease, ks, catalog)
            await asyncio.to_thread(domain_projects.assert_membership, uid, binding.domain_id, ks=ks)
            if manager_subject and not await asyncio.to_thread(
                domain_projects.has_manager, uid, binding.domain_id, ks=ks, catalog=catalog
            ):
                raise DomainAuthUnavailable("Organization manager grant was not confirmed")
            await asyncio.to_thread(_native_binding, ks, binding)
            await asyncio.to_thread(domain_projects._active_user, ks, uid, authenticated=True)
            return binding.domain_id
    except IntegrityError:
        raise DomainAuthConflict("Organization binding already exists", code="organization_binding_conflict") from None
    except SQLAlchemyError:
        raise DomainAuthUnavailable("Organization binding storage is unavailable") from None


async def require_current(row, *, ks, user_id=None, subject=None):
    """Read-only final login/session fence; SQL never substitutes for native grants."""
    organization = getattr(row, "_organization", None)
    if organization is None:
        return
    key = binding_key(row.issuer_url, organization.id)
    try:
        async with _factory()() as session:
            binding = await session.get(OrganizationBinding, key)
            if binding is None:
                raise DomainAuthConflict("Organization binding is unknown", code="organization_binding_unknown")
            _check_binding(binding, row, organization, key)
            await asyncio.to_thread(_native_binding, ks, binding)
            if user_id is not None:
                await asyncio.to_thread(domain_projects.assert_membership, user_id, binding.domain_id, ks=ks)
                if subject in organization.manager_subjects and not await asyncio.to_thread(
                    domain_projects.has_manager, user_id, binding.domain_id, ks=ks
                ):
                    raise DomainAuthDenied(
                        "Organization manager authority changed", code="organization_membership_changed"
                    )
    except SQLAlchemyError:
        raise DomainAuthUnavailable("Organization binding storage is unavailable") from None


async def precheck(row, identity, *, ks):
    """Read-only denial before canonical account creation; admit() rechecks under lock."""
    organization = _configuration(row, identity)
    key = binding_key(identity.issuer, organization.id)
    try:
        async with _factory()() as session:
            binding = await session.get(OrganizationBinding, key)
    except SQLAlchemyError:
        raise DomainAuthUnavailable("Organization binding storage is unavailable") from None
    if binding is None:
        if identity.subject not in organization.manager_subjects:
            raise DomainAuthDenied(
                "A configured manager must establish this organization", code="organization_manager_required"
            )
        return
    _check_binding(binding, row, organization, key)
    await asyncio.to_thread(_native_binding, ks, binding)


def _public(binding, candidates=()):
    return {
        "binding_key": binding.binding_key,
        "issuer_url": binding.issuer_url,
        "external_org_id": binding.external_org_id,
        "client_id": binding.client_id,
        "intent_id": binding.intent_id,
        "status": binding.status,
        "domain_id": binding.domain_id,
        "creator_user_id": binding.creator_user_id,
        "native_candidates": list(candidates),
    }


def _candidates(ks, binding):
    return [
        _field(row, "id")
        for row in _native_domains(ks)
        if _field(row, "afterglow_organization_binding") == binding.binding_key
    ]


async def pending_bindings():
    """Secret-free unsettled creation fences with read-only native observations."""
    from sqlalchemy import select

    from app.services import keystone

    try:
        async with _factory()() as session:
            rows = (
                (
                    await session.execute(
                        select(OrganizationBinding)
                        .where(OrganizationBinding.status != "active")
                        .order_by(OrganizationBinding.created_at, OrganizationBinding.binding_key)
                        .limit(100)
                    )
                )
                .scalars()
                .all()
            )
    except SQLAlchemyError:
        raise DomainAuthUnavailable("Organization binding storage is unavailable") from None
    if not rows:
        return {"items": []}
    ks = await asyncio.to_thread(keystone._get_admin_ks_client)
    observed = {}
    for domain in await asyncio.to_thread(_native_domains, ks):
        observed.setdefault(_field(domain, "afterglow_organization_binding"), []).append(_field(domain, "id"))
    return {"items": [_public(row, observed.get(row.binding_key, [])) for row in rows]}


def _complete_organization(ks, catalog, binding, domain_id):
    """Exact intent markers plus enabled Default, creator manager and direct owner."""
    from app.services.project_service import _assignment_rows, _direct_ids, _required_project_role

    domain = domain_projects._exact(ks.domains, domain_id)
    if (
        _field(domain, "afterglow_organization_binding") != binding.binding_key
        or _field(domain, "afterglow_domain_kind") != "organization"
        or _field(domain, "afterglow_organization_issuer") != binding.issuer_url
        or _field(domain, "afterglow_organization_id") != binding.external_org_id
        or _field(domain, "afterglow_organization_intent") != binding.intent_id
        or _field(domain, "afterglow_created_by") != binding.creator_user_id
        or not domain_projects._enabled(domain)
    ):
        return False
    staged = [
        row
        for row in ks.projects.list(domain=domain_id)
        if _field(row, "name") == "Default" and _field(row, "enabled") is not True
    ]
    if staged:
        return False  # disabled staged Default: bootstrap is partial, not an outage
    project = domain_projects.default_project(domain_id, ks=ks)
    if project is None or project.get("enabled") is not True:
        return False
    owner = _required_project_role(catalog, "project_owner", require_hierarchy=True)
    rows = _assignment_rows(ks, project["id"])
    return owner["id"] in _direct_ids(rows, binding.creator_user_id) and domain_projects.has_manager(
        binding.creator_user_id, domain_id, ks=ks, catalog=catalog
    )


async def settle_binding(binding_key_value, *, intent_id, native_calls_settled, actor_user_id):
    """System-admin settlement after native calls are known finished; never replays/deletes.

    Exactly one complete observed organization with this exact intent becomes active.
    No native candidate and no recorded returned ID releases the intent so a manager
    may establish it again. Anything partial, foreign or ambiguous stays fenced.
    """
    from app.services import domain_iam, keystone

    if native_calls_settled is not True:
        raise DomainAuthInvalid(
            "Explicit native-call settlement confirmation required", code="settlement_confirmation_required"
        )
    async with domain_iam._iam_write() as (lease, ks, catalog):
        if not await asyncio.to_thread(keystone._is_system_admin, actor_user_id):
            raise DomainAuthDenied("System administrator authority is required", code="system_admin_required")
        try:
            async with _factory()() as session:
                binding = await session.get(OrganizationBinding, binding_key_value, with_for_update=True)
                if binding is None:
                    raise DomainAuthNotFound("Organization binding was not found")
                if binding.intent_id != intent_id:
                    raise DomainAuthConflict("Organization intent changed", code="organization_intent_changed")
                if binding.status == "active":
                    return _public(binding)
                candidates = await asyncio.to_thread(_candidates, ks, binding)
                if not candidates and binding.domain_id is None:
                    result = {**_public(binding), "status": "released"}
                    await session.delete(binding)
                    await session.commit()
                    return result
                if (
                    len(candidates) != 1
                    or (binding.domain_id is not None and candidates[0] != binding.domain_id)
                    or not await asyncio.to_thread(_complete_organization, ks, catalog, binding, candidates[0])
                ):
                    raise DomainAuthConflict(
                        "Observed organization is missing, partial or ambiguous",
                        code="organization_settlement_incomplete",
                    )
                await lease.assert_owned()
                binding.domain_id = candidates[0]
                binding.status = "active"
                binding.updated_at = datetime.now(UTC)
                await session.commit()
                return _public(binding, candidates)
        except IntegrityError:
            raise DomainAuthConflict(
                "Organization domain is already bound", code="organization_binding_conflict"
            ) from None
        except SQLAlchemyError:
            raise DomainAuthUnavailable("Organization binding storage is unavailable") from None
