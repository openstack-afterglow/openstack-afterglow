"""셀프서비스 프로젝트 생성 + 이메일 초대 비즈니스 로직."""

import asyncio
import hashlib
import logging
import secrets
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import ProjectInvitation, ProjectRole
from app.services import activity, cache, identity_roles, keystone
from app.services.cache import keys
from app.services.service_permissions import ROLE_PRESETS, SERVICE_ROLE_GRADES

_logger = logging.getLogger(__name__)


# ─── 프로젝트 생성 ────────────────────────────────────────────────────────────


async def create_project_for_user(
    name: str,
    description: str,
    user_id: str,
    username: str,
) -> dict:
    """Create a project and explicitly grant its creator the existing owner role."""
    from app.config import get_settings
    from app.services import keystone

    settings = get_settings()

    # 1. keystoneclient admin으로 Keystone 프로젝트 생성
    def _create_keystone_project():
        ks = keystone._get_admin_ks_client()
        kwargs: dict = {"name": name}
        if description:
            kwargs["description"] = description
        p = ks.projects.create(**kwargs)
        return {"id": p.id, "name": p.name or "", "description": getattr(p, "description", "") or ""}

    project = await asyncio.to_thread(_create_keystone_project)
    project_id = project["id"]

    # Grant the existing safe project hierarchy; never infer ownership from DB rows.
    try:
        await _grant_project_role(project_id, user_id, "project_owner", require_hierarchy=True)
    except Exception:
        _logger.warning("Project owner assignment failed; compensating project creation", exc_info=True)
        await _compensate_delete_keystone_project(project_id)
        raise

    # (best-effort) monitoring SG 자동 생성
    try:
        if settings.monitoring_auto_sg_enabled and settings.monitoring_scrape_cidr:
            from app.services import neutron

            def _ensure_sgs():
                conn = keystone.get_admin_connection_for_project(project_id)
                try:
                    neutron.ensure_node_exporter_sg(
                        conn,
                        project_id,
                        settings.node_exporter_sg_name,
                        settings.monitoring_scrape_cidr,
                    )
                    neutron.ensure_dcgm_exporter_sg(
                        conn,
                        project_id,
                        settings.dcgm_exporter_sg_name,
                        settings.monitoring_scrape_cidr,
                    )
                finally:
                    conn.close()

            await asyncio.to_thread(_ensure_sgs)
    except Exception:
        _logger.warning("모니터링 SG 자동 생성 실패 (계속 진행)", exc_info=True)

    await activity.record(
        project_id=project_id,
        user_id=user_id,
        username=username,
        resource_type="project",
        action="project_create",
        status="success",
        resource_id=project_id,
        resource_name=name,
    )

    await cache.invalidate(keys.user_key(user_id, "projects"))
    await cache.invalidate("afterglow:admin:projects")
    await cache.invalidate("afterglow:admin:project_names")
    return project


async def _compensate_delete_keystone_project(project_id: str) -> None:
    """Compensate failed initial owner assignment by deleting the new project."""
    from app.services import keystone

    try:

        def _delete():
            ks = keystone._get_admin_ks_client()
            ks.projects.delete(project_id)

        await asyncio.to_thread(_delete)
        _logger.info("보상 트랜잭션: Keystone 프로젝트 삭제 완료 (%s)", project_id)
    except Exception:
        _logger.error("보상 트랜잭션 실패: Keystone 프로젝트 삭제 불가 (%s)", project_id, exc_info=True)


# ─── 초대 ─────────────────────────────────────────────────────────────────────


async def create_invitation(
    project_id: str,
    project_name: str,
    invited_email: str,
    invited_by: str,
    invited_by_name: str,
    session: AsyncSession,
    keystone_role: str = "project_member",
) -> dict:
    """초대 생성 + 이메일 발송 (이메일 열거 방지: 항상 201 반환)."""
    from app.config import get_settings

    if keystone_role not in {"project_member", "project_reader"}:
        raise HTTPException(status_code=403, detail="초대에는 일반 프로젝트 역할만 사용할 수 있습니다")

    settings = get_settings()
    expiry_days = settings.smtp_invitation_token_expiry_days
    expires_at = datetime.now(UTC) + timedelta(days=expiry_days)

    # Keystone 사용자 이메일 조회
    keystone_user = await _find_keystone_user_by_email(invited_email)

    # 토큰 생성 + 해시
    plaintext_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(plaintext_token.encode()).hexdigest()

    status = "pending" if keystone_user else "no_user"
    now = datetime.now(UTC)
    invitation = ProjectInvitation(
        project_id=project_id,
        invited_email=invited_email,
        invited_user_id=keystone_user["id"] if keystone_user else None,
        invited_by=invited_by,
        invited_by_name=invited_by_name,
        token_hash=token_hash,
        keystone_role=keystone_role,
        status=status,
        expires_at=expires_at,
        created_at=now,
        updated_at=now,
    )
    session.add(invitation)
    await session.commit()
    await session.refresh(invitation)

    # 이메일 발송 (사용자가 존재할 때만)
    if keystone_user and settings.smtp_enabled:
        from app.services.email_service import send_invitation_email

        frontend_base = settings.frontend_base_url.rstrip("/")
        accept_url = f"{frontend_base}/invitations/{plaintext_token}"
        asyncio.create_task(
            send_invitation_email(
                to_email=invited_email,
                project_name=project_name,
                inviter_name=invited_by_name,
                accept_url=accept_url,
                expires_at=expires_at,
            )
        )

    await activity.record(
        project_id=project_id,
        user_id=invited_by,
        username=invited_by_name,
        resource_type="invitation",
        action="invitation_create",
        status="success",
        resource_id=str(invitation.id),
        extra={"invited_email": invited_email, "has_user": keystone_user is not None},
    )

    return {
        "id": invitation.id,
        "project_id": project_id,
        "invited_email": invited_email,
        "status": status,
        "expires_at": expires_at.isoformat(),
        "created_at": invitation.created_at.isoformat(),
    }


async def accept_invitation(
    plaintext_token: str,
    accepting_user_id: str,
    accepting_email: str,
    session: AsyncSession,
) -> dict:
    """초대 수락 — 이메일 일치 검증 + Keystone role 할당."""
    token_hash = hashlib.sha256(plaintext_token.encode()).hexdigest()

    result = await session.execute(select(ProjectInvitation).where(ProjectInvitation.token_hash == token_hash))
    inv = result.scalar_one_or_none()
    if inv is None:
        raise HTTPException(status_code=404, detail="유효하지 않은 초대 링크입니다")

    if inv.status == "accepted":
        return {"status": "accepted", "project_id": inv.project_id}

    if inv.status in ("declined", "revoked", "expired"):
        raise HTTPException(status_code=410, detail="이미 처리되었거나 만료된 초대입니다")

    now = datetime.now(UTC)
    if inv.expires_at.replace(tzinfo=UTC) < now:
        inv.status = "expired"
        await session.commit()
        raise HTTPException(status_code=410, detail="초대 링크가 만료되었습니다")

    # 이메일 일치 검증
    if inv.invited_email.lower() != accepting_email.lower():
        raise HTTPException(status_code=403, detail="이 초대는 다른 이메일 주소로 발송되었습니다")

    if inv.keystone_role not in {"project_member", "project_reader"}:
        raise HTTPException(status_code=403, detail="이 초대의 역할은 시스템 관리자 검토가 필요합니다")

    # Keystone role 할당
    try:
        await _grant_project_role(inv.project_id, accepting_user_id, inv.keystone_role, require_hierarchy=True)
    except HTTPException:
        raise
    except Exception:
        _logger.error("초대 수락 Keystone role 할당 실패", exc_info=True)
        raise HTTPException(status_code=500, detail="프로젝트 멤버 등록 중 오류가 발생했습니다")

    inv.status = "accepted"
    inv.accepted_at = now
    await session.commit()

    await activity.record(
        project_id=inv.project_id,
        user_id=accepting_user_id,
        username=accepting_email,
        resource_type="invitation",
        action="invitation_accept",
        status="success",
        resource_id=str(inv.id),
    )

    return {"status": "accepted", "project_id": inv.project_id}


async def decline_invitation(plaintext_token: str, session: AsyncSession) -> dict:
    """초대 거절."""
    token_hash = hashlib.sha256(plaintext_token.encode()).hexdigest()

    result = await session.execute(select(ProjectInvitation).where(ProjectInvitation.token_hash == token_hash))
    inv = result.scalar_one_or_none()
    if inv is None:
        raise HTTPException(status_code=404, detail="유효하지 않은 초대 링크입니다")

    if inv.status in ("accepted", "declined", "revoked"):
        return {"status": inv.status}

    inv.status = "declined"
    await session.commit()
    return {"status": "declined"}


async def _find_keystone_user_by_email(email: str) -> dict | None:
    """이메일로 Keystone 사용자 조회. 미발견 시 None."""
    from app.services import keystone

    def _lookup():
        ks = keystone._get_admin_ks_client()
        users = ks.users.list(email=email)
        if users:
            u = users[0]
            return {"id": u.id, "name": u.name, "email": getattr(u, "email", email)}
        return None

    try:
        return await asyncio.to_thread(_lookup)
    except Exception:
        _logger.warning("Keystone 사용자 이메일 조회 실패 (email=%s)", email, exc_info=True)
        return None


# ─── 초대 정보 공개 조회 ──────────────────────────────────────────────────────


async def get_invitation_info(plaintext_token: str, session: AsyncSession) -> dict:
    """토큰으로 초대 정보 조회 (공개 엔드포인트용)."""
    token_hash = hashlib.sha256(plaintext_token.encode()).hexdigest()

    result = await session.execute(select(ProjectInvitation).where(ProjectInvitation.token_hash == token_hash))
    inv = result.scalar_one_or_none()
    if inv is None:
        raise HTTPException(status_code=404, detail="유효하지 않은 초대 링크입니다")

    # 만료 여부 업데이트
    now = datetime.now(UTC)
    if inv.status == "pending" and inv.expires_at.replace(tzinfo=UTC) < now:
        inv.status = "expired"
        await session.commit()

    # 프로젝트 이름 조회
    project_name = await _get_project_name(inv.project_id)

    return {
        "project_id": inv.project_id,
        "project_name": project_name,
        "inviter_name": inv.invited_by_name,
        "invited_email": inv.invited_email,
        "status": inv.status,
        "expires_at": inv.expires_at.isoformat(),
    }


async def _get_project_name(project_id: str) -> str:
    """Keystone에서 프로젝트 이름 조회."""
    from app.services import keystone

    def _lookup():
        ks = keystone._get_admin_ks_client()
        try:
            p = ks.projects.get(project_id)
            return p.name or project_id
        except Exception:
            return project_id

    try:
        return await asyncio.to_thread(_lookup)
    except Exception:
        return project_id


# Keystone project membership. ProjectRole is intentionally used only by the
# explicit legacy migration below; it never participates in authorization.
_PROJECT_GRADES = {
    "project_owner": "owner",
    "project_admin": "admin",
    "project_member": "member",
    "project_reader": "reader",
}


async def _provider_call(fn, *args, **kwargs):
    try:
        return await asyncio.to_thread(fn, *args, **kwargs)
    except Exception as exc:
        raise identity_roles._provider_error(exc) from exc


def _assignment_rows(ks, project_id, *, effective=False):
    query = {"project": project_id}
    if effective:
        query["effective"] = True
    rows = list(ks.role_assignments.list(**query))
    for row in rows:
        scope = identity_roles._field(row, "scope", {})
        if identity_roles._field(identity_roles._field(scope, "project", {}), "id") != project_id:
            raise identity_roles._unavailable("Keystone returned assignments outside the requested project")
        if not isinstance(_principal(row, "role"), str) or not _principal(row, "role"):
            raise identity_roles._unavailable("Malformed project role assignment")
        for kind in ("user", "group"):
            principal_id = _principal(row, kind)
            if principal_id is not None and (not isinstance(principal_id, str) or not principal_id):
                raise identity_roles._unavailable("Malformed project assignment principal")
        if effective and not _principal(row, "user"):
            raise identity_roles._unavailable("Effective project assignment did not resolve its user")
        if not effective and not (_principal(row, "user") or _principal(row, "group")):
            raise identity_roles._unavailable("Project assignment did not resolve its principal")
    return rows


def _principal(row, key):
    return identity_roles._field(identity_roles._field(row, key, {}), "id")


def _expanded_role_ids(rows, catalog, user_id):
    by_id = {role["id"]: role for role in catalog}
    canonical = {row["name"] for row in ROLE_PRESETS} | {"admin", "manager", "member", "reader"}
    bindings = {}
    for role in catalog:
        folded = role["name"].casefold()
        if role["domain_id"] is None and folded in canonical:
            bindings.setdefault(folded, []).append(role)
    result, active = set(), set()

    def visit(rid):
        if rid not in by_id:
            raise identity_roles._unavailable("Assigned role graph references an unknown role")
        if rid in active:
            raise identity_roles._unavailable("Assigned role graph contains a cycle")
        if rid in result:
            return
        role = by_id[rid]
        name = role["name"]
        if name.casefold() in canonical:
            matches = bindings.get(name.casefold(), ())
            if name != name.casefold() or role["domain_id"] is not None or len(matches) != 1 or matches[0]["id"] != rid:
                raise identity_roles._unavailable("Effective authority must bind a unique canonical global role ID")
        active.add(rid)
        for child in role["implied_role_ids"]:
            visit(child)
        active.remove(rid)
        result.add(rid)

    for row in rows:
        if _principal(row, "user") == user_id:
            visit(_principal(row, "role"))
    return result


def _access(rows, catalog, user_id):
    ids = _expanded_role_ids(rows, catalog, user_id)
    names = sorted(role["name"] for role in catalog if role["id"] in ids)
    if {"project_owner", "project_admin"} & set(names):
        safe = _managed_roles(catalog)
        for name in {"project_owner", "project_admin"} & set(names):
            matches = [row for row in catalog if row["domain_id"] is None and row["name"] == name]
            if len(matches) != 1 or matches[0]["id"] not in safe:
                raise identity_roles._unavailable("Project management role graph is unsafe")
    return {
        "is_owner": "project_owner" in names,
        "is_manager": bool({"project_owner", "project_admin"} & set(names)),
        "roles": names,
    }


async def get_project_access(project_id: str, user_id: str) -> dict:
    """Uncached trusted effective assignments are the sole management authority.

    Provider/graph failures are errors, never stale DB or token-role fallbacks.
    """
    ks = await _provider_call(keystone._get_admin_ks_client)
    catalog = await _provider_call(identity_roles._trusted_catalog)
    rows = await _provider_call(_assignment_rows, ks, project_id, effective=True)
    return _access(rows, catalog, user_id)


@asynccontextmanager
async def _membership_write(project_id):
    # Identity management uses the configured admin project, not a newly created
    # tenant where the service user has no assignment yet. Target scope is always
    # supplied explicitly to the trusted role-assignment API.
    conn = await _provider_call(keystone.get_admin_project_connection)
    try:
        async with identity_roles._graph_lock(conn) as lease:
            ks = await _provider_call(keystone._get_admin_ks_client)
            catalog = await _provider_call(identity_roles.load_catalog, conn)
            effective = await _provider_call(_assignment_rows, ks, project_id, effective=True)
            direct = await _provider_call(_assignment_rows, ks, project_id)
            yield lease, ks, catalog, effective, direct
    finally:
        await asyncio.to_thread(conn.close)


def _check_scope(project_id, token_info):
    if token_info.get("is_system_admin") is not True and token_info.get("project_id") != project_id:
        raise HTTPException(status_code=403, detail="Membership changes require the current project")


def _authorize(project_id, token_info, effective, catalog):
    _check_scope(project_id, token_info)
    access = _access(effective, catalog, token_info["user_id"])
    if not access["is_manager"] and token_info.get("is_system_admin") is not True:
        raise HTTPException(status_code=403, detail="Project management role required")
    return access


def _direct_ids(rows, user_id):
    return {
        _principal(row, "role")
        for row in rows
        if _principal(row, "user") == user_id
        and not identity_roles._field(identity_roles._field(row, "scope", {}), "OS-INHERIT:inherited_to")
    }


def _group_ids(row):
    group_id = _principal(row, "group")
    if group_id:
        return {group_id}
    membership = identity_roles._field(identity_roles._field(row, "links", {}), "membership")
    if not membership:
        return set()
    if not isinstance(membership, str):
        raise identity_roles._unavailable("Malformed effective group assignment")
    parts = urlparse(membership).path.split("/")
    if "groups" not in parts or parts.index("groups") + 1 >= len(parts):
        raise identity_roles._unavailable("Malformed effective group assignment")
    return {parts[parts.index("groups") + 1]}


def _inherited_assignment(row):
    scope = identity_roles._field(row, "scope", {})
    links = identity_roles._field(row, "links", {})
    assignment = identity_roles._field(links, "assignment", "") or ""
    if not isinstance(assignment, str):
        raise identity_roles._unavailable("Malformed inherited assignment source")
    return bool(
        identity_roles._field(scope, "OS-INHERIT:inherited_to")
        or "/domains/" in assignment
        or "/OS-INHERIT/" in assignment
    )


async def _member(ks, user_id, catalog, effective, direct):
    effective_ids = _expanded_role_ids(effective, catalog, user_id)
    direct_ids = _direct_ids(direct, user_id)
    if not direct_ids <= {row["id"] for row in catalog}:
        raise identity_roles._unavailable("Direct assignment role is absent from the current catalog")
    user = await _provider_call(ks.users.get, user_id)
    groups = set()
    inherited = False
    external = []
    for row in effective:
        if _principal(row, "user") == user_id:
            row_groups = _group_ids(row)
            row_inherited = _inherited_assignment(row)
            groups.update(row_groups)
            inherited = inherited or row_inherited
            if row_groups or row_inherited:
                external.append(row)
    group_names = []
    for gid in sorted(groups):
        group = await _provider_call(ks.groups.get, gid)
        group_names.append(identity_roles._field(group, "name") or gid)
    access = _access(effective, catalog, user_id)
    source = (
        "mixed"
        if direct_ids and (groups or inherited)
        else "direct"
        if direct_ids
        else "group"
        if groups
        else "inherited"
    )
    result = {
        "user_id": user_id,
        "username": identity_roles._field(user, "name") or "",
        "email": identity_roles._field(user, "email") or "",
        "source": source,
        **access,
        "direct_role_ids": sorted(direct_ids),
        "effective_role_ids": sorted(effective_ids),
        "external_role_ids": sorted(_expanded_role_ids(external, catalog, user_id)),
    }
    if group_names:
        result["group_name"] = ", ".join(group_names)
    return result


async def list_members(project_id, token_info):
    _check_scope(project_id, token_info)
    ks = await _provider_call(keystone._get_admin_ks_client)
    catalog = await _provider_call(identity_roles._trusted_catalog)
    effective = await _provider_call(_assignment_rows, ks, project_id, effective=True)
    _authorize(project_id, token_info, effective, catalog)
    direct = await _provider_call(_assignment_rows, ks, project_id)
    users = {_principal(row, "user") for row in effective + direct}
    users.discard(None)
    return {"items": [await _member(ks, uid, catalog, effective, direct) for uid in sorted(users)]}


def _managed_roles(catalog):
    """Only exact global preset identities with non-elevating real descendants."""
    definitions = {row["name"]: row for row in ROLE_PRESETS}
    by_id = {row["id"]: row for row in catalog}
    by_name = {}
    for row in catalog:
        if row["domain_id"] is None:
            by_name.setdefault(row["name"].casefold(), []).append(row)
    result = {}
    for name, definition in definitions.items():
        matches = by_name.get(name, [])
        if not matches:
            continue
        if len(matches) != 1 or matches[0]["name"] != name:
            raise identity_roles._unavailable("Managed role binding is ambiguous")
        row = matches[0]
        area, grade = definition["area"], definition["grade"]
        if name in _PROJECT_GRADES:
            order = ["project_owner", "project_admin", "project_member", "project_reader"]
            allowed = set(order[order.index(name) :]) | {"member", "reader"}
            if name == "project_reader":
                allowed.discard("member")
        else:
            grades = SERVICE_ROLE_GRADES.get(area, {})
            order = ["admin", "editor", "user", "reader"]
            if grade not in order or grade not in grades:
                continue
            if name != f"{area}_{grade}":
                # Fine-grained grants may acquire their own service's read-only
                # discovery bundle, never another use/write capability.
                allowed = {name}
                if grade != "reader":
                    allowed.add(f"{area}_reader")
                    allowed.update(grades.get("reader", ()))
            else:
                lower = order[order.index(grade) :]
                allowed = {f"{area}_{level}" for level in lower}
                allowed.update(leaf for level in lower for leaf in grades.get(level, ()))
        descendant_ids = row["inherited_role_ids"]
        descendants = {by_id[rid]["name"] for rid in descendant_ids}
        cyclic = any(
            rid == row["id"] or row["id"] in by_id[rid]["inherited_role_ids"] for rid in row["implied_role_ids"]
        )
        if row["system_only"] or cyclic or not descendants <= allowed:
            continue
        # Reject a domain-specific/duplicate descendant, even when its label is safe.
        if any(
            by_id[rid]["domain_id"] is not None or len(by_name.get(by_id[rid]["name"], ())) != 1
            for rid in descendant_ids
        ):
            continue
        result[row["id"]] = {**row, "area": area, "grade": grade}
    return result


def _required_project_role(catalog, name, *, require_hierarchy=False):
    managed = _managed_roles(catalog)
    matches = [row for row in managed.values() if row["name"] == name]
    if len(matches) != 1:
        raise HTTPException(status_code=409, detail="Apply the safe project role preset before assigning membership")
    row = matches[0]
    if require_hierarchy:
        order = ["project_owner", "project_admin", "project_member", "project_reader"]
        expected = set(order[order.index(name) + 1 :]) | {"reader"}
        if name != "project_reader":
            expected.add("member")
        by_id = {item["id"]: item for item in catalog}
        descendants = {by_id[rid]["name"] for rid in row["inherited_role_ids"]}
        if not expected <= descendants:
            raise HTTPException(status_code=409, detail="Project role hierarchy is incomplete")
    return row


async def assignable_roles(project_id, token_info):
    _check_scope(project_id, token_info)
    ks = await _provider_call(keystone._get_admin_ks_client)
    catalog = await _provider_call(identity_roles._trusted_catalog)
    effective = await _provider_call(_assignment_rows, ks, project_id, effective=True)
    access = _authorize(project_id, token_info, effective, catalog)
    roles = _managed_roles(catalog).values()
    return {
        "roles": [row for row in roles if access["is_owner"] or row["name"] not in {"project_owner", "project_admin"}],
        "is_owner": access["is_owner"],
    }


def _ensure_owner_remains(project_id, user_id, catalog, effective, direct, desired):
    by_id = {row["id"]: row for row in catalog}
    retained = _direct_ids(direct, user_id) - set(_managed_roles(catalog)) | desired
    if any(
        by_id[rid]["name"] == "project_owner"
        or any(by_id[child]["name"] == "project_owner" for child in by_id[rid]["inherited_role_ids"])
        for rid in retained
    ):
        return
    for row in effective:
        uid = _principal(row, "user")
        if not uid or not _access([row], catalog, uid)["is_owner"]:
            continue
        if uid != user_id or _group_ids(row) or _inherited_assignment(row):
            return
    raise HTTPException(status_code=409, detail="The last effective project owner cannot be removed")


def _validate_reader_roles(catalog, effective_ids):
    by_id = {row["id"]: row for row in catalog}
    names = {by_id[rid]["name"] for rid in effective_ids}
    write_roles = set()
    for area, grades in SERVICE_ROLE_GRADES.items():
        for grade in ("user", "editor", "admin"):
            write_roles.add(f"{area}_{grade}")
            write_roles.update(grades.get(grade, ()))
    if names & write_roles and "member" not in names:
        raise HTTPException(
            status_code=409,
            detail="Write-service roles require effective native member membership, not reader membership",
        )


@identity_roles._complete_mutation
async def replace_member_roles(project_id, user_id, role_ids, token_info, *, remove=False):
    _check_scope(project_id, token_info)
    async with _membership_write(project_id) as (lease, ks, catalog, effective, direct):
        access = _authorize(project_id, token_info, effective, catalog)
        target = _access(effective, catalog, user_id)
        if not target["roles"]:
            raise HTTPException(status_code=404, detail="User is not an effective member of this project")
        if target["is_owner"] and not access["is_owner"]:
            raise HTTPException(status_code=403, detail="Only an owner may edit another owner's assignments")
        managed = _managed_roles(catalog)
        direct_ids = _direct_ids(direct, user_id)
        if not direct_ids <= {row["id"] for row in catalog}:
            raise identity_roles._unavailable("Direct assignment role is absent from the current catalog")
        current = direct_ids & set(managed)
        requested = set(role_ids)
        if len(role_ids) != len(requested) or not requested <= set(managed) | direct_ids:
            raise HTTPException(
                status_code=422, detail="Select unique safe assignable role IDs; unrelated grants are read-only"
            )
        # The full direct selection may include immutable existing native/custom
        # grants. They are neither added nor removed by this managed replacement.
        desired = requested & set(managed)
        for rid in desired:
            if managed[rid]["name"] in _PROJECT_GRADES:
                _required_project_role(catalog, managed[rid]["name"], require_hierarchy=True)
        protected = {rid for rid, row in managed.items() if row["name"] in {"project_owner", "project_admin"}}
        if not access["is_owner"] and (desired ^ current) & protected:
            raise HTTPException(status_code=403, detail="Only an owner may change project owner/admin grants")
        if target["is_owner"] and (current - desired) & protected:
            _ensure_owner_remains(project_id, user_id, catalog, effective, direct, desired)
        # Simulate effective grants without the direct grants being replaced. Group
        # and inherited roles remain immutable and count toward reader restrictions.
        remaining = []
        for row in effective:
            if _principal(row, "user") != user_id:
                continue
            if _group_ids(row) or _inherited_assignment(row):
                remaining.append(row)
        projected = _expanded_role_ids(remaining, catalog, user_id)
        by_id = {row["id"]: row for row in catalog}
        for rid in desired | (_direct_ids(direct, user_id) - set(managed)):
            projected.add(rid)
            projected.update(by_id[rid]["inherited_role_ids"])
        if not remove:
            _validate_reader_roles(catalog, projected)
        await identity_roles._session_ready({user_id} if current - desired else ())
        changed = False
        try:
            for rid in sorted(desired - current):
                changed = True
                await identity_roles._write(lease, ks.roles.grant, rid, user=user_id, project=project_id)
            for rid in sorted(current - desired):
                changed = True
                await identity_roles._write(lease, ks.roles.revoke, rid, user=user_id, project=project_id)
        finally:
            if changed:
                await cache.invalidate(keys.user_key(user_id, "projects"))
                await identity_roles._applied(
                    None,
                    catalog,
                    None,
                    {user_id} if current - desired else (),
                    token_info,
                    "project_member_remove" if remove else "project_member_roles",
                    {"project_id": project_id, "user_id": user_id},
                )
        fresh_effective = await _provider_call(_assignment_rows, ks, project_id, effective=True)
        fresh_direct = await _provider_call(_assignment_rows, ks, project_id)
        return await _member(ks, user_id, catalog, fresh_effective, fresh_direct)


@identity_roles._complete_mutation
async def _grant_project_role(project_id, user_id, name, *, require_hierarchy=False):
    async with _membership_write(project_id) as (lease, ks, catalog, effective, direct):
        role = _required_project_role(catalog, name, require_hierarchy=require_hierarchy)
        await _provider_call(ks.users.get, user_id)
        if role["id"] not in _direct_ids(direct, user_id):
            await identity_roles._write(lease, ks.roles.grant, role["id"], user=user_id, project=project_id)
        await cache.invalidate(keys.user_key(user_id, "projects"))


@identity_roles._complete_mutation
async def migrate_legacy_managers(project_id, owner_user_id, token_info, session):
    if token_info.get("is_system_admin") is not True:
        raise HTTPException(status_code=403, detail="Verified system administrator required for legacy migration")
    if not owner_user_id:
        raise HTTPException(status_code=422, detail="Choose owner_user_id explicitly")
    async with _membership_write(project_id) as (lease, ks, catalog, effective, direct):
        owner = _required_project_role(catalog, "project_owner", require_hierarchy=True)
        admin = _required_project_role(catalog, "project_admin", require_hierarchy=True)
        result = await session.execute(
            select(ProjectRole)
            .where(ProjectRole.project_id == project_id, ProjectRole.role == "manager")
            .with_for_update()
        )
        rows = list(result.scalars().all())
        if not rows:
            raise HTTPException(status_code=409, detail="No legacy manager rows remain to migrate")
        users = {row.user_id for row in rows} | {owner_user_id}
        for uid in sorted(users):
            await _provider_call(ks.users.get, uid)
            if not _access(effective, catalog, uid)["roles"]:
                raise HTTPException(
                    status_code=409,
                    detail="Every migrated manager and the chosen owner must be a verified effective project member",
                )
        for uid in sorted(users):
            role = owner if uid == owner_user_id else admin
            if role["id"] not in _direct_ids(direct, uid):
                await identity_roles._write(lease, ks.roles.grant, role["id"], user=uid, project=project_id)
        verified = await _provider_call(_assignment_rows, ks, project_id, effective=True)
        for uid in users:
            access = _access(verified, catalog, uid)
            if not access["is_manager"] or (uid == owner_user_id and not access["is_owner"]):
                raise identity_roles._unavailable(
                    "Migration assignments could not be verified; legacy rows were retained"
                )
        await lease.assert_owned()
        for row in rows:
            await session.delete(row)
        await session.commit()
        for uid in users:
            await cache.invalidate(keys.user_key(uid, "projects"))
        return {
            "project_id": project_id,
            "owner_user_id": owner_user_id,
            "migrated_user_ids": sorted({row.user_id for row in rows}),
            "deleted_legacy_rows": len(rows),
        }
