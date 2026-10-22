"""Explicit personal quota convergence reuses durable unknown-write fences."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.api.deps import get_os_conn, get_token_info, require_admin
from app.api.identity import enrollment_policy as api
from app.models.account_spaces import PersonalProjectIntent
from app.models.domain_quotas import DomainQuotaOperation
from app.services import account_spaces, domain_quotas, enrollment_policy, quota_native
from tests.admin_gate import synthetic_verified_admin
from tests.test_domain_iam import directory as directory
from tests.test_domain_iam import enrollments as enrollments
from tests.test_domain_iam import manager


@pytest.fixture
async def quota_target(directory, enrollments, monkeypatch):
    project = await account_spaces.ensure_personal_project("foreign")
    async with enrollments() as sql:
        connection = await sql.connection()
        await connection.run_sync(DomainQuotaOperation.__table__.create)
        await sql.commit()
    monkeypatch.setattr(domain_quotas, "get_session_factory", lambda: enrollments)
    actor = manager("system-admin")
    conn = SimpleNamespace(
        identity=SimpleNamespace(get_project=directory.ks.projects.get, get_domain=directory.ks.domains.get)
    )
    usage, writes = {}, []

    def read(_, pid, section):
        return {
            key: {"limit": value, "in_use": usage.get(key, 0), "reserved": usage.get(key + ":reserved", 0)}
            for key, value in directory.quota_limits[pid, section].items()
        }

    def write(_, pid, section, values):
        writes.append((pid, section, dict(values)))
        directory.quota_limits[pid, section].update(values)

    monkeypatch.setattr(quota_native, "get_section", read)
    monkeypatch.setattr(quota_native, "update_section", write)
    return SimpleNamespace(project=project, conn=conn, actor=actor, usage=usage, writes=writes, read=read)


@pytest.mark.asyncio
async def test_preview_is_read_only_and_apply_uses_existing_journal_without_rewriting_frozen_intent(
    directory, enrollments, quota_target
):
    q = quota_target
    async with enrollments() as sql:
        frozen = (await sql.execute(select(PersonalProjectIntent))).scalar_one().personal_quotas.copy()
    directory.quota_limits[q.project["id"], "volume"]["gigabytes"] = 10
    preview = await enrollment_policy.preview_personal_quotas(q.conn, q.project["id"], q.actor)
    assert preview["can_apply"] and preview["limits"]["gigabytes"] == 1024
    assert preview["limits"]["cores"] == 2 and preview["limits"]["ram"] == 4096
    assert preview["current"]["gigabytes"]["limit"] == 10 and not q.writes
    result = await enrollment_policy.converge_personal_quotas(q.conn, q.project["id"], q.actor, preview["preview_id"])
    assert result["status"] == "updated" and result["operation_id"] and q.writes
    async with enrollments() as sql:
        assert (await sql.execute(select(PersonalProjectIntent))).scalar_one().personal_quotas == frozen
        operation = await sql.get(DomainQuotaOperation, result["operation_id"])
        assert operation.status == "updated" and operation.requested == preview["limits"]
    assert directory.personal_projects[q.project["id"]].enabled
    assert directory.users["foreign"].domain_id == "other"


@pytest.mark.asyncio
@pytest.mark.parametrize("metric", ["cores", "gigabytes"])
async def test_existing_usage_and_reservations_block_reduction_without_deleting_resources(quota_target, metric):
    q = quota_target
    q.usage[metric] = 1
    q.usage[metric + ":reserved"] = 2048
    preview = await enrollment_policy.preview_personal_quotas(q.conn, q.project["id"], q.actor)
    assert not preview["can_apply"] and metric in preview["blocked_fields"]
    with pytest.raises(HTTPException) as denied:
        await enrollment_policy.converge_personal_quotas(q.conn, q.project["id"], q.actor, preview["preview_id"])
    assert denied.value.status_code == 409 and not q.writes


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["usage", "reservation", "policy", "owner", "disabled", "admin"])
async def test_apply_rechecks_preview_policy_provenance_usage_and_live_admin(
    directory, enrollments, quota_target, change
):
    q = quota_target
    preview = await enrollment_policy.preview_personal_quotas(q.conn, q.project["id"], q.actor)
    if change == "usage":
        q.usage["cores"] = 1
    elif change == "reservation":
        q.usage["cores:reserved"] = 1
    elif change == "policy":
        await enrollment_policy.update_policy(
            q.conn,
            {"revision": 0, "public_signup_enabled": False, "approval_mode": "auto", "personal_quotas": {"cores": 1}},
            token_info=q.actor,
        )
    elif change == "owner":
        directory.personal_projects[q.project["id"]].afterglow_personal_user_id = "member"
    elif change == "disabled":
        directory.personal_projects[q.project["id"]].enabled = False
    else:
        directory.system_admins.clear()
    with pytest.raises(HTTPException):
        await enrollment_policy.converge_personal_quotas(q.conn, q.project["id"], q.actor, preview["preview_id"])
    assert not q.writes


@pytest.mark.asyncio
async def test_unknown_native_write_fences_future_preview_and_never_replays(
    directory, enrollments, quota_target, monkeypatch
):
    q = quota_target
    preview = await enrollment_policy.preview_personal_quotas(q.conn, q.project["id"], q.actor)

    def lost_reply(conn, pid, section, values):
        q.writes.append((pid, section, values))
        directory.quota_limits[pid, section].update(values)
        raise TimeoutError("private transport")

    monkeypatch.setattr(quota_native, "update_section", lost_reply)
    result = await enrollment_policy.converge_personal_quotas(q.conn, q.project["id"], q.actor, preview["preview_id"])
    assert result["status"] == "unknown" and len(q.writes) == 1
    with pytest.raises(HTTPException) as fenced:
        await enrollment_policy.preview_personal_quotas(q.conn, q.project["id"], q.actor)
    assert fenced.value.detail == "quota_native_operation_unresolved" and len(q.writes) == 1
    async with enrollments() as sql:
        assert (await sql.get(DomainQuotaOperation, result["operation_id"])).status == "unknown"


@pytest.mark.asyncio
async def test_policy_customization_is_preserved_not_overlaid_by_source_defaults(directory, enrollments, quota_target):
    q = quota_target
    await enrollment_policy.update_policy(
        q.conn,
        {
            "revision": 0,
            "public_signup_enabled": False,
            "approval_mode": "auto",
            "personal_quotas": {"cores": 7, "gigabytes": 2000},
        },
        token_info=q.actor,
    )
    policy = await enrollment_policy.read_policy()
    assert policy["personal_quota_source"] == "administrator"
    assert policy["personal_quotas"] == {"cores": 7, "gigabytes": 2000}
    assert policy["source_default_personal_quotas"]["cores"] == 2
    preview = await enrollment_policy.preview_personal_quotas(q.conn, q.project["id"], q.actor)
    assert preview["limits"] == {"cores": 7, "gigabytes": 2000}


@pytest.mark.asyncio
async def test_quota_endpoints_expose_every_personal_project_and_reject_arbitrary_provenance(directory, quota_target):
    q = quota_target
    app = FastAPI()
    app.include_router(api.router, prefix="/api/v1/admin")
    app.dependency_overrides[require_admin] = synthetic_verified_admin
    app.dependency_overrides[get_token_info] = lambda: {**q.actor, "is_system_admin": True}
    app.dependency_overrides[get_os_conn] = lambda: q.conn
    for index in range(101):
        directory.personal_projects[f"unmarked-{index:03d}"] = SimpleNamespace(
            id=f"unmarked-{index:03d}", name="Unmarked", domain_id=q.project["domain_id"], enabled=True
        )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.get("/api/v1/admin/personal-project-quotas")
        assert first.status_code == 200 and len(first.json()["items"]) == 100
        second = await client.get(
            "/api/v1/admin/personal-project-quotas", params={"cursor": first.json()["next_cursor"]}
        )
        assert second.status_code == 200 and len(second.json()["items"]) == 2
        denied = await client.get("/api/v1/admin/personal-project-quotas/unmarked-000/preview")
        assert denied.status_code == 409
        preview = await client.get(f"/api/v1/admin/personal-project-quotas/{q.project['id']}/preview")
        assert preview.status_code == 200 and not q.writes
        applied = await client.post(
            f"/api/v1/admin/personal-project-quotas/{q.project['id']}/apply",
            json={"preview_id": preview.json()["preview_id"]},
        )
        assert applied.status_code == 200 and applied.json()["status"] == "updated"


@pytest.mark.asyncio
async def test_verified_legacy_owner_primary_can_converge_without_inventing_enrollment_receipt(directory, quota_target):
    from tests.test_project_membership_roles import rid

    q = quota_target
    legacy = directory.ks.projects.create(
        name="Legacy",
        domain=q.project["domain_id"],
        enabled=True,
        afterglow_personal_user_id="member",
        afterglow_personal_primary=True,
    )
    directory.ks.roles.grant(rid("project_owner"), user="member", project=legacy.id)
    for section, fields in quota_native.QUOTA_FIELDS.items():
        directory.quota_limits[legacy.id, section] = {key: 100 for key in fields.values()}
    preview = await enrollment_policy.preview_personal_quotas(q.conn, legacy.id, q.actor)
    assert preview["can_apply"] and preview["provenance"]["kind"] == "native_owner_primary"
    result = await enrollment_policy.converge_personal_quotas(q.conn, legacy.id, q.actor, preview["preview_id"])
    assert result["status"] == "updated" and legacy.enabled
    assert directory.users["member"].domain_id == "domain"


@pytest.mark.asyncio
async def test_native_member_only_catalog_converges_without_project_owner_presets(directory, quota_target, monkeypatch):
    from app.services import identity_roles, project_service
    from tests.test_project_membership_roles import rid

    q = quota_target
    directory.catalog = identity_roles._catalog(
        [{"id": rid(name), "name": name} for name in ("admin", "member", "reader")], []
    )
    # Represent a cloud that never installed the optional Afterglow role DAG.
    directory.direct.clear()
    directory.default_direct.clear()
    directory.managers.clear()

    def hierarchy_forbidden(*args):
        raise AssertionError("Native member personal projects must not require project_owner presets")

    monkeypatch.setattr(project_service, "_ownership_state_sync", hierarchy_forbidden)
    preview = await enrollment_policy.preview_personal_quotas(q.conn, q.project["id"], q.actor)
    assert preview["can_apply"] and preview["owner_user_id"] == "foreign"
    result = await enrollment_policy.converge_personal_quotas(q.conn, q.project["id"], q.actor, preview["preview_id"])
    assert result["status"] == "updated" and q.writes
