"""Keystone-only membership authority and safe direct-assignment mutation."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_token_info
from app.api.identity.projects import router
from app.database import get_session
from app.services import identity_roles
from app.services import project_service as service
from app.services.service_permissions import ROLE_IMPLICATIONS, ROLE_PRESETS

PROJECT = "screenshot-project"


def rid(name):
    return f"existing-{name}-id"


def assignment(user_id, role, *, group=None, inherited=False, project_id=PROJECT):
    row = {"role": {"id": rid(role)}, "scope": {"project": {"id": project_id}}}
    if user_id:
        row["user"] = {"id": user_id}
    if group:
        if user_id:
            row["links"] = {"membership": f"https://identity/v3/groups/{group}/users/{user_id}"}
        else:
            row["group"] = {"id": group}
    if inherited:
        row["scope"]["OS-INHERIT:inherited_to"] = "projects"
        row["links"] = {
            "assignment": "https://identity/v3/OS-INHERIT/domains/domain/users/owner/roles/role/inherited_to_projects"
        }
    return row


def token(user_id="owner", *, system_admin=False, project_id=PROJECT):
    return {
        "user_id": user_id,
        "username": user_id,
        "project_id": project_id,
        "is_system_admin": system_admin,
        "roles": ["member"],
    }


class Membership:
    def __init__(self):
        rows = [{"id": rid(name), "name": name} for name in ["admin", "manager", "member", "reader", "unrelated"]]
        rows.extend({"id": rid(row["name"]), "name": row["name"]} for row in ROLE_PRESETS)
        edges = [
            {"prior_role": {"id": rid(prior)}, "implies": [{"id": rid(implied)}]}
            for prior, implied in ROLE_IMPLICATIONS
        ]
        self.catalog = identity_roles._catalog(rows, edges)
        self.direct = [
            assignment("owner", "project_owner"),
            assignment("admin", "project_admin"),
            assignment("member", "project_member"),
        ]
        self.inherited = []
        self.groups = {}
        self.calls = []
        self.lock = asyncio.Lock()
        self.active = 0
        self.max_active = 0
        self.fail = False
        self.ks = SimpleNamespace(
            role_assignments=SimpleNamespace(list=self.assignments),
            users=SimpleNamespace(get=lambda uid: SimpleNamespace(id=uid, name=uid, email=f"{uid}@test.invalid")),
            groups=SimpleNamespace(get=lambda gid: SimpleNamespace(name=f"group-{gid}")),
            roles=SimpleNamespace(grant=self.grant, revoke=self.revoke),
        )

    def assignments(self, project, effective=False):
        assert project == PROJECT
        if self.fail:
            raise RuntimeError("Keystone unavailable")
        if not effective:
            return list(self.direct)
        rows = list(self.inherited)
        for row in self.direct:
            if "user" in row:
                rows.append(row)
            else:
                gid = row["group"]["id"]
                name = next(role["name"] for role in self.catalog if role["id"] == row["role"]["id"])
                rows.extend(assignment(uid, name, group=gid) for uid in self.groups[gid])
        return rows

    def grant(self, role_id, *, user, project):
        assert project == PROJECT
        self.calls.append(("grant", user, role_id))
        if not any(row.get("user", {}).get("id") == user and row["role"]["id"] == role_id for row in self.direct):
            name = next(row["name"] for row in self.catalog if row["id"] == role_id)
            self.direct.append(assignment(user, name))

    def revoke(self, role_id, *, user, project):
        assert project == PROJECT
        self.calls.append(("revoke", user, role_id))
        self.direct = [
            row for row in self.direct if not (row.get("user", {}).get("id") == user and row["role"]["id"] == role_id)
        ]

    @asynccontextmanager
    async def write(self, project_id):
        assert project_id == PROJECT
        async with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            lease = SimpleNamespace(assert_owned=AsyncMock())
            try:
                yield (
                    lease,
                    self.ks,
                    self.catalog,
                    service._assignment_rows(self.ks, PROJECT, effective=True),
                    service._assignment_rows(self.ks, PROJECT),
                )
            finally:
                self.active -= 1


@pytest.fixture
def membership(monkeypatch):
    state = Membership()
    monkeypatch.setattr(service.keystone, "_get_admin_ks_client", lambda: state.ks)
    monkeypatch.setattr(identity_roles, "_trusted_catalog", lambda: state.catalog)
    monkeypatch.setattr(service, "_membership_write", state.write)
    monkeypatch.setattr(identity_roles, "_session_ready", AsyncMock())
    monkeypatch.setattr(identity_roles, "_applied", AsyncMock())
    monkeypatch.setattr(service.cache, "invalidate", AsyncMock())
    return state


@pytest.mark.asyncio
async def test_effective_assignment_revocation_removes_manager_without_db_authority(membership):
    access = await service.get_project_access(PROJECT, "admin")
    assert access["is_manager"] is True
    assert access["is_owner"] is False
    membership.revoke(rid("project_admin"), user="admin", project=PROJECT)
    # No ProjectRole/session argument is consulted even when legacy DB rows remain.
    assert await service.get_project_access(PROJECT, "admin") == {"is_owner": False, "is_manager": False, "roles": []}


@pytest.mark.asyncio
async def test_native_manager_does_not_authorize_project_membership(membership):
    membership.direct.append(assignment("native-manager", "manager"))
    access = await service.get_project_access(PROJECT, "native-manager")
    assert not access["is_manager"]
    with pytest.raises(HTTPException) as denied:
        await service.replace_member_roles(PROJECT, "member", [rid("project_reader")], token("native-manager"))
    assert denied.value.status_code == 403
    assert not membership.calls


@pytest.mark.asyncio
async def test_lookup_provider_failure_is_not_stale_or_empty_success(membership):
    membership.fail = True
    with pytest.raises(HTTPException) as unavailable:
        await service.get_project_access(PROJECT, "admin")
    assert unavailable.value.status_code == 503


@pytest.mark.asyncio
async def test_cross_project_mutation_denied_before_provider(membership):
    with pytest.raises(HTTPException) as denied:
        await service.replace_member_roles(PROJECT, "member", [], token(project_id="other-project"))
    assert denied.value.status_code == 403
    assert not membership.calls


@pytest.mark.asyncio
async def test_mixed_group_and_direct_membership_is_accurate(membership):
    membership.groups["team"] = ["member", "group-only"]
    membership.direct.append(assignment(None, "lumen_reader", group="team"))
    rows = (await service.list_members(PROJECT, token()))["items"]
    mixed = next(row for row in rows if row["user_id"] == "member")
    assert mixed["source"] == "mixed"
    assert mixed["direct_role_ids"] == [rid("project_member")]
    assert rid("lumen_reader") in mixed["effective_role_ids"]
    assert "lumen-inventory_reader" in mixed["roles"]
    assert mixed["group_name"] == "group-team"
    assert next(row for row in rows if row["user_id"] == "group-only")["source"] == "group"


@pytest.mark.asyncio
@pytest.mark.parametrize("origin", ["group", "inherited"])
async def test_member_http_preserves_external_grants_overlapping_direct_parent(membership, origin):
    membership.direct.append(assignment("member", "lumen_user"))
    if origin == "group":
        membership.groups["team"] = ["member"]
        membership.direct.append(assignment(None, "lumen_reader", group="team"))
    else:
        membership.inherited.append(assignment("member", "lumen_reader", inherited=True))
    app = FastAPI()
    app.include_router(router, prefix="/projects")
    app.dependency_overrides[get_token_info] = lambda: token()
    expected = sorted(rid(name) for name in ["lumen_reader", "lumen-inventory_reader", "lumen-history_reader"])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/projects/{PROJECT}/members")
        assert response.status_code == 200
        mixed = next(row for row in response.json()["items"] if row["user_id"] == "member")
        assert mixed["external_role_ids"] == expected
        assert set(expected) <= set(mixed["effective_role_ids"])
        assert set(mixed["direct_role_ids"]) == {rid("project_member"), rid("lumen_user")}
        updated = await client.put(
            f"/projects/{PROJECT}/members/member/roles", json={"role_ids": [rid("project_member")]}
        )
        assert updated.status_code == 200
        member = updated.json()
        assert member["direct_role_ids"] == [rid("project_member")]
        assert member["external_role_ids"] == expected
        assert set(expected) <= set(member["effective_role_ids"])
        assert rid("lumen_user") not in member["effective_role_ids"]


@pytest.mark.asyncio
async def test_direct_replacement_preserves_group_and_unrelated_native_grants(membership):
    membership.groups["team"] = ["member"]
    membership.direct.extend(
        [
            assignment(None, "lumen_reader", group="team"),
            assignment("member", "unrelated"),
            assignment("member", "reader"),
        ]
    )
    updated = await service.replace_member_roles(PROJECT, "member", [rid("project_reader")], token("admin"))
    assert updated["direct_role_ids"] == sorted([rid("project_reader"), rid("reader"), rid("unrelated")])
    assert "lumen_reader" in updated["roles"]
    assert updated["source"] == "mixed"
    assert membership.calls == [("grant", "member", rid("project_reader")), ("revoke", "member", rid("project_member"))]
    identity_roles._applied.assert_awaited_once()
    assert identity_roles._applied.call_args.args[3] == {"member"}


@pytest.mark.asyncio
async def test_member_removal_keeps_read_only_group_membership(membership):
    membership.groups["team"] = ["member"]
    membership.direct.append(assignment(None, "project_member", group="team"))
    updated = await service.replace_member_roles(PROJECT, "member", [], token("admin"), remove=True)
    assert updated["source"] == "group"
    assert updated["direct_role_ids"] == []
    assert "project_member" in updated["roles"]
    assert membership.calls == [("revoke", "member", rid("project_member"))]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "target,desired",
    [
        ("owner", ["project_member"]),
        ("admin", ["project_member"]),
        ("member", ["project_admin"]),
        ("member", ["project_owner"]),
    ],
)
async def test_admin_cannot_edit_owner_or_change_protected_grants(membership, target, desired):
    with pytest.raises(HTTPException) as denied:
        await service.replace_member_roles(PROJECT, target, [rid(name) for name in desired], token("admin"))
    assert denied.value.status_code == 403
    assert not membership.calls


@pytest.mark.asyncio
async def test_system_admin_without_effective_ownership_cannot_change_owner(membership):
    with pytest.raises(HTTPException) as denied:
        await service.replace_member_roles(PROJECT, "owner", [], token("platform", system_admin=True))
    assert denied.value.status_code == 403


@pytest.mark.asyncio
async def test_owner_may_assign_existing_admin_id(membership):
    result = await service.replace_member_roles(PROJECT, "member", [rid("project_admin")], token())
    assert result["is_manager"]
    assert not result["is_owner"]
    assert result["direct_role_ids"] == [rid("project_admin")]


@pytest.mark.asyncio
async def test_last_effective_owner_removal_blocked(membership):
    with pytest.raises(HTTPException) as conflict:
        await service.replace_member_roles(PROJECT, "owner", [], token(), remove=True)
    assert conflict.value.status_code == 409
    assert not membership.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["group", "domain"])
async def test_group_or_domain_effective_owner_counts_for_last_owner(membership, source):
    if source == "group":
        membership.groups["owners"] = ["group-owner"]
        membership.direct.append(assignment(None, "project_owner", group="owners"))
    else:
        membership.inherited.append(assignment("domain-owner", "project_owner", inherited=True))
    result = await service.replace_member_roles(PROJECT, "owner", [rid("project_member")], token())
    assert not result["is_owner"]
    assert (await service.get_project_access(PROJECT, f"{source}-owner"))["is_owner"]


@pytest.mark.asyncio
async def test_same_user_group_owner_is_preserved_when_direct_owner_removed(membership):
    membership.groups["owners"] = ["owner"]
    membership.direct.append(assignment(None, "project_owner", group="owners"))
    result = await service.replace_member_roles(PROJECT, "owner", [], token(), remove=True)
    assert result["is_owner"]
    assert result["source"] == "group"


@pytest.mark.asyncio
async def test_concurrent_owner_revocation_serializes_and_protects_last_owner(membership):
    membership.direct.append(assignment("second-owner", "project_owner"))
    # Each owner can initially edit themselves. The shared lease re-reads the
    # effective owners before each write; exactly one removal can succeed.
    results = await asyncio.gather(
        service.replace_member_roles(PROJECT, "owner", [], token(), remove=True),
        service.replace_member_roles(PROJECT, "second-owner", [], token("second-owner"), remove=True),
        return_exceptions=True,
    )
    assert sum(isinstance(result, dict) for result in results) == 1
    errors = [result for result in results if isinstance(result, HTTPException)]
    assert len(errors) == 1
    assert errors[0].status_code == 409
    assert membership.max_active == 1
    owners = [uid for uid in ["owner", "second-owner"] if (await service.get_project_access(PROJECT, uid))["is_owner"]]
    assert len(owners) == 1


@pytest.mark.asyncio
async def test_reader_write_service_combination_rejected_including_group_reader(membership):
    membership.direct = [row for row in membership.direct if row.get("user", {}).get("id") != "member"]
    membership.groups["readers"] = ["member"]
    membership.direct.append(assignment(None, "project_reader", group="readers"))
    with pytest.raises(HTTPException) as conflict:
        await service.replace_member_roles(PROJECT, "member", [rid("lumen-chat_user")], token())
    assert conflict.value.status_code == 409
    assert not membership.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["admin", "manager", "unrelated"])
async def test_native_and_unknown_roles_are_never_delegable(membership, role):
    with pytest.raises(HTTPException) as invalid:
        await service.replace_member_roles(PROJECT, "member", [rid(role)], token())
    assert invalid.value.status_code == 422
    assert not membership.calls


@pytest.mark.asyncio
async def test_service_alias_transitively_implying_native_admin_is_not_delegable(membership):
    reader = next(row for row in membership.catalog if row["name"] == "lumen_reader")
    reader["inherited_role_ids"].append(rid("admin"))
    reader["system_only"] = True
    roles = (await service.assignable_roles(PROJECT, token()))["roles"]
    assert rid("lumen_reader") not in {row["id"] for row in roles}
    with pytest.raises(HTTPException) as invalid:
        await service.replace_member_roles(PROJECT, "member", [rid("lumen_reader")], token())
    assert invalid.value.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("problem", ["duplicate-global", "assigned-domain"])
async def test_ambiguous_or_nonglobal_owner_authority_fails_closed(membership, problem):
    original = next(row for row in membership.catalog if row["name"] == "project_owner")
    if problem == "duplicate-global":
        membership.catalog.append({**original, "id": "duplicate-owner-id"})
    else:
        original["domain_id"] = "domain"
    with pytest.raises(HTTPException) as unavailable:
        await service.get_project_access(PROJECT, "owner")
    assert unavailable.value.status_code == 503


@pytest.mark.asyncio
async def test_creator_grant_uses_existing_owner_id_and_requires_safe_hierarchy(membership):
    await service._grant_project_role(PROJECT, "creator", "project_owner", require_hierarchy=True)
    assert membership.calls == [("grant", "creator", rid("project_owner"))]
    owner = next(row for row in membership.catalog if row["name"] == "project_owner")
    owner["inherited_role_ids"].remove(rid("member"))
    with pytest.raises(HTTPException) as incomplete:
        await service._grant_project_role(PROJECT, "other-creator", "project_owner", require_hierarchy=True)
    assert incomplete.value.status_code == 409


def legacy_session(*users):
    rows = [SimpleNamespace(user_id=uid) for uid in users]
    session = AsyncMock()
    session.execute.return_value = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: rows))
    return session, rows


@pytest.mark.asyncio
async def test_legacy_migration_requires_verified_system_admin_and_explicit_owner(membership):
    session, _ = legacy_session("admin")
    with pytest.raises(HTTPException) as denied:
        await service.migrate_legacy_managers(PROJECT, "owner", token(), session)
    assert denied.value.status_code == 403
    with pytest.raises(HTTPException) as missing:
        await service.migrate_legacy_managers(PROJECT, "", token(system_admin=True), session)
    assert missing.value.status_code == 422
    session.execute.assert_not_awaited()
    assert not membership.calls


@pytest.mark.asyncio
async def test_explicit_migration_verifies_members_and_deletes_only_migrated_rows(membership):
    session, rows = legacy_session("admin", "member")
    result = await service.migrate_legacy_managers(PROJECT, "member", token("platform", system_admin=True), session)
    assert result == {
        "project_id": PROJECT,
        "owner_user_id": "member",
        "migrated_user_ids": ["admin", "member"],
        "deleted_legacy_rows": 2,
    }
    assert (await service.get_project_access(PROJECT, "member"))["is_owner"]
    assert membership.calls == [("grant", "member", rid("project_owner"))]
    assert [call.args[0] for call in session.delete.await_args_list] == rows
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_migration_does_not_infer_owner_from_legacy_manager_or_granted_by(membership):
    session, rows = legacy_session("missing-member")
    rows[0].granted_by = "owner"
    with pytest.raises(HTTPException) as unverified:
        await service.migrate_legacy_managers(PROJECT, "member", token(system_admin=True), session)
    assert unverified.value.status_code == 409
    session.delete.assert_not_awaited()
    session.commit.assert_not_awaited()
    assert not membership.calls


@pytest.mark.asyncio
async def test_migration_provider_partial_failure_preserves_rows_for_explicit_retry(membership):
    session, _ = legacy_session("admin", "member")
    original_grant = membership.ks.roles.grant

    def broken_grant(role_id, **kwargs):
        original_grant(role_id, **kwargs)
        raise RuntimeError("Provider response lost")

    membership.ks.roles.grant = broken_grant
    with pytest.raises(HTTPException) as unavailable:
        await service.migrate_legacy_managers(PROJECT, "member", token(system_admin=True), session)
    assert unavailable.value.status_code == 503
    session.delete.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_assignment_query_rejects_wrong_project_and_malformed_effective_rows(membership):
    membership.inherited.append(assignment("owner", "project_owner", project_id="other-project"))
    with pytest.raises(HTTPException) as unavailable:
        await service.get_project_access(PROJECT, "owner")
    assert unavailable.value.status_code == 503
    membership.inherited = [assignment(None, "project_owner", group="owners")]
    with pytest.raises(HTTPException) as malformed:
        await service.get_project_access(PROJECT, "owner")
    assert malformed.value.status_code == 503


@pytest.mark.asyncio
async def test_membership_http_shapes_and_removed_manager_api(membership):
    app = FastAPI()
    app.include_router(router, prefix="/projects")
    app.dependency_overrides[get_token_info] = lambda: token()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        choices = await client.get(f"/projects/{PROJECT}/assignable-roles")
        assert choices.status_code == 200
        assert choices.json()["is_owner"] is True
        assert {"id", "name", "area", "grade"} <= choices.json()["roles"][0].keys()
        updated = await client.put(
            f"/projects/{PROJECT}/members/member/roles", json={"role_ids": [rid("project_reader")]}
        )
        assert updated.status_code == 200
        assert {
            "user_id",
            "username",
            "email",
            "source",
            "is_owner",
            "is_manager",
            "roles",
            "direct_role_ids",
            "effective_role_ids",
        } <= updated.json().keys()
        removed = await client.delete(f"/projects/{PROJECT}/members/member")
        assert removed.status_code == 200
        assert removed.json()["status"] == "removed"
        assert removed.json()["member"]["direct_role_ids"] == []
        old = await client.post(f"/projects/{PROJECT}/managers/member")
        assert old.status_code == 404


@pytest.mark.asyncio
async def test_migration_http_requires_owner_body_and_system_admin(membership):
    app = FastAPI()
    app.include_router(router, prefix="/projects")
    session, _ = legacy_session("member")

    async def db():
        yield session

    app.dependency_overrides[get_session] = db
    app.dependency_overrides[get_token_info] = lambda: token(system_admin=True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        missing = await client.post(f"/projects/{PROJECT}/members/migrate-legacy-managers", json={})
        assert missing.status_code == 422
        result = await client.post(
            f"/projects/{PROJECT}/members/migrate-legacy-managers", json={"owner_user_id": "member"}
        )
        assert result.status_code == 200
        assert result.json()["deleted_legacy_rows"] == 1
        app.dependency_overrides[get_token_info] = lambda: token()
        denied = await client.post(
            f"/projects/{PROJECT}/members/migrate-legacy-managers", json={"owner_user_id": "member"}
        )
        assert denied.status_code == 403


@pytest.mark.asyncio
async def test_full_direct_selection_preserves_immutable_native_roles(membership):
    membership.direct.append(assignment("member", "reader"))
    result = await service.replace_member_roles(
        PROJECT, "member", [rid("project_reader"), rid("reader")], token("admin")
    )
    assert result["direct_role_ids"] == sorted([rid("project_reader"), rid("reader")])
    assert all(role_id != rid("reader") for _, _, role_id in membership.calls)


@pytest.mark.asyncio
async def test_nonowner_can_preserve_existing_admin_while_editing_service_roles(membership):
    result = await service.replace_member_roles(
        PROJECT, "admin", [rid("project_admin"), rid("lumen-chat_user")], token("admin")
    )
    assert result["is_manager"]
    assert "lumen-chat_user" in result["roles"]
    assert membership.calls == [("grant", "admin", rid("lumen-chat_user"))]


@pytest.mark.asyncio
async def test_partial_revoke_response_failure_still_invalidates_sessions(membership):
    original_revoke = membership.ks.roles.revoke

    def uncertain_revoke(role_id, **kwargs):
        original_revoke(role_id, **kwargs)
        raise RuntimeError("Provider response lost after removal")

    membership.ks.roles.revoke = uncertain_revoke
    with pytest.raises(HTTPException) as unavailable:
        await service.replace_member_roles(PROJECT, "member", [], token("admin"), remove=True)
    assert unavailable.value.status_code == 503
    identity_roles._applied.assert_awaited_once()
    assert identity_roles._applied.call_args.args[3] == {"member"}
    assert (await service.get_project_access(PROJECT, "member"))["roles"] == []


@pytest.mark.asyncio
async def test_real_membership_write_uses_shared_graph_lease_and_admin_identity_scope(monkeypatch):
    state = Membership()
    conn = SimpleNamespace(close=MagicMock())
    events = []
    lease = SimpleNamespace(assert_owned=AsyncMock())

    @asynccontextmanager
    async def graph_lock(connection):
        assert connection is conn
        events.append("locked")
        yield lease
        events.append("unlocked")

    def load_catalog(connection):
        assert connection is conn
        assert events == ["locked"]
        return state.catalog

    def assignments(project, effective=False):
        assert events == ["locked"]
        return state.assignments(project, effective)

    state.ks.role_assignments.list = assignments
    admin_connection = MagicMock(return_value=conn)
    monkeypatch.setattr(service.keystone, "get_admin_project_connection", admin_connection)
    monkeypatch.setattr(service.keystone, "_get_admin_ks_client", lambda: state.ks)
    monkeypatch.setattr(identity_roles, "_graph_lock", graph_lock)
    monkeypatch.setattr(identity_roles, "load_catalog", load_catalog)
    async with service._membership_write(PROJECT) as snapshot:
        assert snapshot[0] is lease
        assert service._access(snapshot[3], snapshot[2], "owner")["is_owner"]
    assert events == ["locked", "unlocked"]
    admin_connection.assert_called_once_with()
    conn.close.assert_called_once_with()


@pytest.mark.asyncio
async def test_incomplete_project_hierarchy_invitation_fails_without_accepting(membership):
    member = next(row for row in membership.catalog if row["name"] == "project_member")
    member["inherited_role_ids"].remove(rid("member"))
    from datetime import UTC, datetime, timedelta

    invitation = SimpleNamespace(
        status="pending",
        invited_email="invitee@test.invalid",
        expires_at=datetime.now(UTC) + timedelta(days=1),
        keystone_role="project_member",
        project_id=PROJECT,
    )
    session = AsyncMock()
    session.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: invitation)
    with pytest.raises(HTTPException):
        await service.accept_invitation("token", "invitee", "invitee@test.invalid", session)
    assert invitation.status == "pending"
    assert not membership.calls
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_inherited_and_direct_member_view_preserves_read_only_provenance(membership):
    membership.inherited.append(assignment("member", "lumen_reader", inherited=True))
    rows = (await service.list_members(PROJECT, token()))["items"]
    member = next(row for row in rows if row["user_id"] == "member")
    assert member["source"] == "mixed"
    assert member["direct_role_ids"] == [rid("project_member")]
    removed = await service.replace_member_roles(PROJECT, "member", [], token("admin"), remove=True)
    assert removed["source"] == "inherited"
    assert removed["direct_role_ids"] == []
    assert "lumen_reader" in removed["roles"]


@pytest.mark.asyncio
async def test_granular_nonreader_leaf_is_assignable_with_only_same_service_discovery(membership):
    choices = await service.assignable_roles(PROJECT, token("admin"))
    assert rid("lumen-chat_user") in {row["id"] for row in choices["roles"]}
    updated = await service.replace_member_roles(
        PROJECT, "member", [rid("project_member"), rid("lumen-chat_user")], token("admin")
    )
    assert {"lumen-chat_user", "lumen_reader", "lumen-inventory_reader", "lumen-history_reader"} <= set(
        updated["roles"]
    )
    assert not {"lumen-images_user", "lumen-audio_user", "lumen-tools_user"} & set(updated["roles"])


@pytest.mark.asyncio
async def test_removed_parent_leaf_edge_does_not_regain_permissions_from_presets(membership):
    membership.direct.append(assignment("member", "lumen_user"))
    before = await service.get_project_access(PROJECT, "member")
    assert "lumen-chat_user" in before["roles"]
    user = next(row for row in membership.catalog if row["name"] == "lumen_user")
    user["implied_role_ids"].remove(rid("lumen-chat_user"))
    after = await service.get_project_access(PROJECT, "member")
    assert "lumen_user" in after["roles"]
    assert "lumen-chat_user" not in after["roles"]
    from app.services.service_permissions import service_permissions

    assert "lumen-chat_user" not in service_permissions({"roles": after["roles"]})["lumen"]


@pytest.mark.asyncio
@pytest.mark.parametrize("problem", ["domain", "duplicate", "case-alias", "unknown-child", "cycle"])
async def test_effective_service_identity_binding_and_graph_fail_closed(membership, problem):
    membership.direct.append(assignment("member", "lumen-chat_user"))
    leaf = next(row for row in membership.catalog if row["name"] == "lumen-chat_user")
    if problem == "domain":
        leaf["domain_id"] = "tenant-domain"
    elif problem == "duplicate":
        membership.catalog.append({**leaf, "id": "duplicate-global-leaf"})
    elif problem == "case-alias":
        membership.catalog.append({**leaf, "id": "uppercase-alias", "name": "LUMEN-CHAT_USER"})
    elif problem == "unknown-child":
        leaf["implied_role_ids"].append("missing-role-id")
    else:
        reader = next(row for row in membership.catalog if row["name"] == "lumen_reader")
        reader["implied_role_ids"].append(leaf["id"])
    with pytest.raises(HTTPException) as unavailable:
        await service.get_project_access(PROJECT, "member")
    assert unavailable.value.status_code == 503


@pytest.mark.asyncio
async def test_granular_leaf_cannot_acquire_another_write_leaf(membership):
    leaf = next(row for row in membership.catalog if row["name"] == "lumen-chat_user")
    leaf["inherited_role_ids"].append(rid("lumen-images_user"))
    leaf["implied_role_ids"].append(rid("lumen-images_user"))
    choices = await service.assignable_roles(PROJECT, token())
    assert leaf["id"] not in {row["id"] for row in choices["roles"]}
    with pytest.raises(HTTPException) as invalid:
        await service.replace_member_roles(PROJECT, "member", [leaf["id"]], token())
    assert invalid.value.status_code == 422


@pytest.mark.asyncio
async def test_unassigned_domain_alias_does_not_disable_global_owner_or_service_grants(membership):
    for name in ("project_owner", "member", "lumen-chat_user"):
        original = next(row for row in membership.catalog if row["name"] == name)
        membership.catalog.append({**original, "id": "domain-" + name, "domain_id": "domain"})
    membership.direct.append(assignment("member", "lumen-chat_user"))
    assert (await service.get_project_access(PROJECT, "owner"))["is_owner"] is True
    access = await service.get_project_access(PROJECT, "member")
    from app.services.service_permissions import service_permissions

    assert "lumen-chat_user" in service_permissions(access)["lumen"]
    choices = await service.assignable_roles(PROJECT, token())
    assert rid("project_owner") in {row["id"] for row in choices["roles"]}
    assert not any(row["id"].startswith("domain-") for row in choices["roles"])
