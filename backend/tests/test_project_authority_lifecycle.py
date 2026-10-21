"""Consumer-visible unique ownership, creator delegation and fail-closed lifecycle."""

import time

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_token_info
from app.api.identity.projects import router
from app.services import cache, identity_roles, project_service, session_store
from app.services.cache import invalidate as invalidate_cache
from app.services.identity_roles import _applied as complete_role_change
from app.services.identity_roles import _session_ready as validation_store_ready
from app.services.project_service import inspect_project_empty as native_inspect_project_empty
from tests.ownership_journal import ownership_journal as ownership_journal
from tests.test_domain_iam import directory as directory
from tests.test_project_membership_roles import PROJECT, assignment, rid, token

pytestmark = pytest.mark.usefixtures("ownership_journal")


@pytest.fixture
async def role_logins(directory, monkeypatch):
    # The directory remains synthetic; completion and family storage are real.
    monkeypatch.setattr(identity_roles, "_applied", complete_role_change)
    monkeypatch.setattr(identity_roles, "_session_ready", validation_store_ready)
    monkeypatch.setattr(cache, "invalidate", invalidate_cache)
    snapshots = {}
    for uid in ("owner", "member"):
        jti = "lifecycle-" + uid
        await session_store.store_session(jti, "unscoped-" + uid, PROJECT, uid, int(time.time()) + 3600)
        snapshots[uid] = await session_store.get_session(jti)
    return snapshots


async def assert_role_logins_preserved(snapshots):
    redis = await session_store._get_redis()
    for uid, before in snapshots.items():
        assert await session_store.get_session("lifecycle-" + uid) == before
        assert await redis.get("afterglow:session-family:" + before["family_id"]) == "lifecycle-" + uid


def app_for(user_id="owner"):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/projects")
    app.dependency_overrides[get_token_info] = lambda: token(user_id)
    return app


@pytest.fixture
def creator_grants(directory):
    grants = []
    assignments = directory.ks.role_assignments.list

    def rows(*, domain=None, user=None, **kwargs):
        if domain is not None:
            return [
                row
                for row in grants
                if row["scope"]["domain"]["id"] == domain and (user is None or row["user"]["id"] == user)
            ]
        if kwargs.get("project") is not None or kwargs.get("system") is not None or kwargs.get("group") is not None:
            return assignments(user=user, **kwargs)
        return assignments(user=user, **kwargs) + [row for row in grants if user is None or row["user"]["id"] == user]

    def grant(role_id, *, user, domain):
        row = {"user": {"id": user}, "role": {"id": role_id}, "scope": {"domain": {"id": domain}}}
        if row not in grants:
            grants.append(row)

    def revoke(role_id, *, user, domain):
        grants[:] = [
            row
            for row in grants
            if not (
                row["user"]["id"] == user and row["role"]["id"] == role_id and row["scope"]["domain"]["id"] == domain
            )
        ]

    directory.ks.role_assignments.list = rows
    directory.ks.roles.grant = grant
    directory.ks.roles.revoke = revoke
    return grants


@pytest.mark.asyncio
async def test_creator_capability_uses_current_native_domain_grant_not_project_grade(directory, creator_grants):
    creator_grants.append(
        {"user": {"id": "member"}, "role": {"id": rid("project_creator")}, "scope": {"domain": {"id": "domain"}}}
    )
    app = app_for("member")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        allowed = await client.get("/api/v1/projects/capabilities?domain_id=domain")
        assert allowed.status_code == 200
        assert allowed.json()["domain_id"] == "domain"
        assert allowed.json()["can_create_project"] is True
        creator_grants.clear()
        revoked = await client.get("/api/v1/projects/capabilities?domain_id=domain")
        assert revoked.json()["can_create_project"] is False
        directory.default_direct.append(assignment("member", "project_creator", project_id="default-project"))
        wrong_scope = await client.get("/api/v1/projects/capabilities?domain_id=domain")
        assert wrong_scope.json()["can_create_project"] is False
        assert (await client.get("/api/v1/projects/capabilities?domain_id=other")).status_code == 403
    assert not directory.calls


@pytest.mark.asyncio
async def test_generic_route_rejects_second_owner_and_last_owner_removal(directory):
    async with AsyncClient(transport=ASGITransport(app=app_for()), base_url="http://test") as client:
        second = await client.put(
            f"/api/v1/projects/{PROJECT}/members/member/roles", json={"role_ids": [rid("project_owner")]}
        )
        assert second.status_code == 409
        removed = await client.delete(f"/api/v1/projects/{PROJECT}/members/owner")
        assert removed.status_code == 409
        choices = await client.get(f"/api/v1/projects/{PROJECT}/assignable-roles")
        assert all(row["name"] != "project_owner" for row in choices.json()["roles"])
    assert not directory.calls


@pytest.mark.asyncio
async def test_legacy_multiple_owners_report_conflict_without_stripping_native_grants(directory):
    directory.direct.append(assignment("member", "project_owner"))
    async with AsyncClient(transport=ASGITransport(app=app_for()), base_url="http://test") as client:
        state = await client.get(f"/api/v1/projects/{PROJECT}/ownership")
        assert state.status_code == 200
        assert state.json()["status"] == "conflict"
        assert state.json()["owner_user_id"] is None
        assert {row["user_id"] for row in state.json()["owners"]} == {"owner", "member"}
        transfer = await client.post(f"/api/v1/projects/{PROJECT}/ownership-transfer", json={"user_id": "admin"})
        assert transfer.status_code == 409
    assert not directory.calls


@pytest.mark.asyncio
async def test_explicit_transfer_revokes_before_grant_and_keeps_single_native_owner(directory, role_logins):
    async with AsyncClient(transport=ASGITransport(app=app_for()), base_url="http://test") as client:
        response = await client.post(f"/api/v1/projects/{PROJECT}/ownership-transfer", json={"user_id": "member"})
        assert response.status_code == 200
        assert response.json()["status"] == "unique"
        assert response.json()["owner_user_id"] == "member"
    assert directory.calls == [("revoke", "owner", rid("project_owner")), ("grant", "member", rid("project_owner"))]
    assert response.json()["transfer_operation"]["status"] == "completed"
    assert not (await project_service.get_project_access(PROJECT, "owner"))["is_owner"]
    assert (await project_service.get_project_access(PROJECT, "member"))["is_owner"]
    await assert_role_logins_preserved(role_logins)


@pytest.mark.asyncio
async def test_transfer_response_loss_blocks_replay_until_explicit_settled_reconciliation(directory):
    revoke = directory.ks.roles.revoke

    def uncertain_revoke(role_id, **kwargs):
        revoke(role_id, **kwargs)
        raise RuntimeError("response lost after commit")

    directory.ks.roles.revoke = uncertain_revoke
    async with AsyncClient(transport=ASGITransport(app=app_for()), base_url="http://test") as client:
        lost = await client.post(f"/api/v1/projects/{PROJECT}/ownership-transfer", json={"user_id": "member"})
        assert lost.status_code == 503
        assert directory.calls == [("revoke", "owner", rid("project_owner"))]
        from app.services import project_ownership_journal as journal

        operation = await journal.get(PROJECT)
        assert operation["status"] == "unknown"
        replay = await client.post(f"/api/v1/projects/{PROJECT}/ownership-transfer", json={"user_id": "member"})
        assert replay.status_code == 409
        await project_service.reconcile_project_ownership(
            PROJECT,
            operation["id"],
            "domain",
            token("system-admin", system_admin=True),
            native_calls_settled=True,
        )
        resumed = await client.post(f"/api/v1/projects/{PROJECT}/ownership-transfer", json={"user_id": "member"})
        assert resumed.status_code == 200
        assert resumed.json()["owner_user_id"] == "member"
    assert directory.calls.count(("revoke", "owner", rid("project_owner"))) == 1
    assert directory.calls.count(("grant", "member", rid("project_owner"))) == 1


@pytest.mark.asyncio
async def test_group_owner_is_conflict_and_transfer_never_creates_direct_second_owner(directory):
    directory.groups["team"] = ["member"]
    directory.direct.append(assignment(None, "project_owner", group="team"))
    async with AsyncClient(transport=ASGITransport(app=app_for()), base_url="http://test") as client:
        state = await client.get(f"/api/v1/projects/{PROJECT}/ownership")
        assert state.status_code == 200
        assert state.json()["status"] == "conflict"
        assert any(row["source"] == "group_or_inherited" for row in state.json()["owners"])
        assert (
            await client.post(f"/api/v1/projects/{PROJECT}/ownership-transfer", json={"user_id": "admin"})
        ).status_code == 409
    assert not directory.calls


@pytest.mark.asyncio
async def test_owner_without_creator_cannot_delete_and_default_never_deletable(directory, monkeypatch):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    @asynccontextmanager
    async def write(pid):
        async with directory.lock:
            yield (
                SimpleNamespace(assert_owned=AsyncMock()),
                directory.ks,
                directory.catalog,
                project_service._assignment_rows(directory.ks, pid, effective=True),
                project_service._assignment_rows(directory.ks, pid),
            )

    monkeypatch.setattr(project_service, "_membership_write", write)
    async with AsyncClient(transport=ASGITransport(app=app_for()), base_url="http://test") as client:
        assert (await client.delete(f"/api/v1/projects/{PROJECT}")).status_code == 403
    async with AsyncClient(transport=ASGITransport(app=app_for("domain-manager")), base_url="http://test") as client:
        assert (await client.delete("/api/v1/projects/default-project")).status_code == 403
    assert not directory.calls


@pytest.mark.asyncio
async def test_child_projects_proof_is_exhaustive_and_unknown_is_not_empty(directory):
    def broken_children(*, parent):
        assert parent == PROJECT
        yield {"id": "child", "parent_id": PROJECT}
        raise RuntimeError("later page unavailable")

    directory.ks.projects.list = broken_children
    result = project_service.inspect_child_projects(directory.ks, PROJECT)
    assert result["status"] == "unavailable" and result["count"] is None


@pytest.mark.asyncio
async def test_manager_precedence_is_not_an_owner_inference_edge(directory):
    from app.services.service_permissions import ROLE_IMPLICATIONS, ROLE_PRESETS

    assert not any(prior == "manager" and implied == "project_owner" for prior, implied in ROLE_IMPLICATIONS)
    creator = next(row for row in ROLE_PRESETS if row["name"] == "project_creator")
    assert creator["area"] == "domain" and creator["parent"] is None
    state = await project_service.project_ownership(PROJECT, token("domain-manager"))
    assert state["owner_user_id"] == "owner" and state["can_transfer"] is True
    assert not (await project_service.get_project_access(PROJECT, "domain-manager"))["is_owner"]


@pytest.mark.asyncio
async def test_project_admin_adds_only_joined_users_without_foreign_credential_metadata(directory):
    directory.default_direct.append(assignment("foreign", "project_reader", project_id="default-project"))
    async with AsyncClient(transport=ASGITransport(app=app_for("admin")), base_url="http://test") as client:
        users = await client.get(f"/api/v1/projects/{PROJECT}/eligible-users")
        assert users.status_code == 200
        foreign = next(user for user in users.json() if user["id"] == "foreign")
        assert set(foreign) == {"id", "name", "email", "domain_id", "enabled"}
        assert foreign["domain_id"] == "other"
        added = await client.put(
            f"/api/v1/projects/{PROJECT}/members/foreign/roles", json={"role_ids": [rid("project_reader")]}
        )
        assert added.status_code == 200
        assert added.json()["identity_read_only"] is True


@pytest.mark.asyncio
async def test_unavailable_resource_connection_never_calls_project_delete(directory, monkeypatch):
    from unittest.mock import Mock

    delete = Mock()
    directory.ks.projects.delete = delete

    def unavailable():
        raise RuntimeError("native inventory unavailable")

    monkeypatch.setattr(project_service, "inspect_project_empty", native_inspect_project_empty)
    monkeypatch.setattr(project_service.keystone, "get_admin_project_connection", unavailable)
    async with AsyncClient(transport=ASGITransport(app=app_for("domain-manager")), base_url="http://test") as client:
        response = await client.delete(f"/api/v1/projects/{PROJECT}")
        assert response.status_code == 503
    delete.assert_not_called()


@pytest.mark.asyncio
async def test_only_domain_manager_can_delegate_native_domain_creator(directory, creator_grants, role_logins):
    async with AsyncClient(transport=ASGITransport(app=app_for()), base_url="http://test") as client:
        assert (await client.put("/api/v1/projects/creators/member", json={"enabled": True})).status_code == 403
    async with AsyncClient(transport=ASGITransport(app=app_for("domain-manager")), base_url="http://test") as client:
        granted = await client.put("/api/v1/projects/creators/member", json={"domain_id": "domain", "enabled": True})
        assert granted.status_code == 200
        assert granted.json()["role"] == {"id": rid("project_creator"), "name": "project_creator"}
        assert [row["id"] for row in granted.json()["users"]] == ["member"]
        assert creator_grants[0]["scope"] == {"domain": {"id": "domain"}}
        assert await project_service.can_create_project("member", "domain")
        await assert_role_logins_preserved(role_logins)
        revoked = await client.put("/api/v1/projects/creators/member", json={"enabled": False})
        assert revoked.status_code == 200 and revoked.json()["users"] == []
        assert not await project_service.can_create_project("member", "domain")
        await assert_role_logins_preserved(role_logins)


@pytest.mark.asyncio
async def test_system_creator_initialization_only_for_proven_new_disabled_project(directory):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    directory.users["system-admin"].domain_id = "other"
    directory.direct = []
    directory.project.enabled = False
    lease = SimpleNamespace(assert_owned=AsyncMock())
    await project_service.initialize_system_project_owner(
        PROJECT,
        "system-admin",
        "domain",
        lease=lease,
        ks=directory.ks,
        catalog=directory.catalog,
        previous_project_ids={"default-project"},
    )
    assert directory.calls == [("grant", "system-admin", rid("project_owner"))]
    assert (await project_service.get_project_access(PROJECT, "system-admin"))["is_owner"]


@pytest.mark.asyncio
async def test_delayed_timed_out_owner_grant_blocks_retry_and_new_transfer_until_settled(directory):
    import asyncio
    import threading

    from app.services import project_ownership_journal as journal

    grant = directory.ks.roles.grant
    release = threading.Event()
    finished = threading.Event()
    workers = []

    def delayed_grant(role_id, **kwargs):
        def controller():
            try:
                release.wait()
                grant(role_id, **kwargs)
            finally:
                finished.set()

        worker = threading.Thread(target=controller, daemon=True)
        workers.append(worker)
        worker.start()
        raise RuntimeError("HTTP timed out while native controller continues")

    directory.ks.roles.grant = delayed_grant
    try:
        async with AsyncClient(transport=ASGITransport(app=app_for()), base_url="http://test") as client:
            first = await client.post(f"/api/v1/projects/{PROJECT}/ownership-transfer", json={"user_id": "member"})
            assert first.status_code == 503
            assert (await project_service._ownership_state(directory.ks, directory.catalog, PROJECT))[
                "status"
            ] == "missing"
            operation = await journal.get(PROJECT)
            assert operation["status"] == "unknown"
            retry = await client.post(f"/api/v1/projects/{PROJECT}/ownership-transfer", json={"user_id": "member"})
            assert retry.status_code == 409
        async with AsyncClient(
            transport=ASGITransport(app=app_for("domain-manager")), base_url="http://test"
        ) as client:
            next_transfer = await client.post(
                f"/api/v1/projects/{PROJECT}/ownership-transfer", json={"user_id": "admin"}
            )
            assert next_transfer.status_code == 409
        release.set()
        assert await asyncio.to_thread(finished.wait, 2)
        assert (await project_service._ownership_state(directory.ks, directory.catalog, PROJECT))[
            "owner_user_id"
        ] == "member"
        # Even matching ownership after late commit is not implicit settlement.
        async with AsyncClient(transport=ASGITransport(app=app_for("member")), base_url="http://test") as client:
            assert (
                await client.post(f"/api/v1/projects/{PROJECT}/ownership-transfer", json={"user_id": "admin"})
            ).status_code == 409
            await project_service.reconcile_project_ownership(
                PROJECT,
                operation["id"],
                "domain",
                token("system-admin", system_admin=True),
                native_calls_settled=True,
            )
            directory.ks.roles.grant = grant
            transferred = await client.post(f"/api/v1/projects/{PROJECT}/ownership-transfer", json={"user_id": "admin"})
            assert transferred.status_code == 200
            assert transferred.json()["owner_user_id"] == "admin"
            assert len(transferred.json()["owners"]) == 1
    finally:
        release.set()
        for worker in workers:
            await asyncio.to_thread(worker.join, 2)
        assert all(not worker.is_alive() for worker in workers)


@pytest.mark.asyncio
async def test_reconcile_endpoint_requires_system_admin_exact_operation_and_settlement_confirmation(directory):
    from app.api.deps import require_admin
    from app.services import project_ownership_journal as journal
    from tests.admin_gate import synthetic_verified_admin

    revoke = directory.ks.roles.revoke

    def uncertain_revoke(role_id, **kwargs):
        revoke(role_id, **kwargs)
        raise RuntimeError("response lost after commit")

    directory.ks.roles.revoke = uncertain_revoke
    async with AsyncClient(transport=ASGITransport(app=app_for()), base_url="http://test") as client:
        assert (
            await client.post(f"/api/v1/projects/{PROJECT}/ownership-transfer", json={"user_id": "member"})
        ).status_code == 503
    operation = await journal.get(PROJECT)
    path = f"/api/v1/projects/{PROJECT}/ownership-transfer/reconcile"
    body = {"operation_id": operation["id"], "domain_id": "domain", "native_calls_settled": True}
    async with AsyncClient(transport=ASGITransport(app=app_for("domain-manager")), base_url="http://test") as client:
        assert (await client.post(path, json=body)).status_code == 403
    app = app_for("system-admin")
    app.dependency_overrides[get_token_info] = lambda: token("system-admin", system_admin=True)
    app.dependency_overrides[require_admin] = synthetic_verified_admin
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post(path, json={**body, "native_calls_settled": False})).status_code == 422
        assert (await client.post(path, json={**body, "operation_id": "stale"})).status_code == 404
        assert (await client.post(path, json={**body, "domain_id": "other"})).status_code == 403
        result = await client.post(path, json=body)
        assert result.status_code == 200
        assert result.json()["transfer_operation"]["status"] == "settled"
    assert directory.calls == [("revoke", "owner", rid("project_owner"))]


@pytest.mark.asyncio
async def test_settled_missing_initial_owner_allows_cleanup_but_never_activation(directory):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from fastapi import HTTPException

    from app.services import project_ownership_journal as journal

    directory.direct = []
    directory.project.enabled = False

    def lost_grant(role_id, **kwargs):
        raise RuntimeError("native outcome unavailable")

    directory.ks.roles.grant = lost_grant
    with pytest.raises(HTTPException) as unknown:
        await project_service.initialize_system_project_owner(
            PROJECT,
            "system-admin",
            "domain",
            lease=SimpleNamespace(assert_owned=AsyncMock()),
            ks=directory.ks,
            catalog=directory.catalog,
            previous_project_ids={"default-project"},
        )
    assert unknown.value.status_code == 503
    operation = await journal.get(PROJECT)
    assert operation["status"] == "unknown"
    with pytest.raises(HTTPException) as fenced:
        await journal.assert_resolved(PROJECT)
    assert fenced.value.status_code == 409
    reconciled = await project_service.reconcile_project_ownership(
        PROJECT,
        operation["id"],
        "domain",
        token("system-admin", system_admin=True),
        native_calls_settled=True,
    )
    assert reconciled["status"] == "missing"
    assert reconciled["transfer_operation"]["status"] == "completed"
    await journal.assert_resolved(PROJECT)
    with pytest.raises(HTTPException) as denied:
        await project_service.assert_project_activation_safe(PROJECT, ks=directory.ks, catalog=directory.catalog)
    assert denied.value.status_code == 409
    assert directory.project.enabled is False and not directory.calls
