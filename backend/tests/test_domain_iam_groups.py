"""Domain-manager group CRUD and membership through the real /api/v1/iam routes.

Keystone is the deterministic native-directory adapter from test_domain_iam; the
real require_domain_manager dependency, graph-lease membership path and domain
boundary checks run unmodified.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_token_info
from app.api.identity import iam
from app.services import domain_auth, domain_iam_groups, identity_roles, keystone
from tests.ownership_journal import ownership_journal as ownership_journal
from tests.test_domain_iam import directory as directory
from tests.test_domain_iam import manager
from tests.test_project_membership_roles import PROJECT, rid

pytestmark = pytest.mark.usefixtures("ownership_journal")

PROJECTION = SimpleNamespace(
    id="projection",
    name="afterglow-default-managers-domain",
    description="afterglow:default-manager-reader:v1:domain",
    domain_id="domain",
)


def grant(group, role, scope):
    return {"group": {"id": group}, "role": {"id": rid(role)}, "scope": scope}


@pytest.fixture
def native(directory, monkeypatch):
    state = directory
    state.group_rows = {
        "team": SimpleNamespace(id="team", name="Team", description="Builders", domain_id="domain"),
        "privileged": SimpleNamespace(id="privileged", name="Operators", description="", domain_id="domain"),
        "foreign-grant": SimpleNamespace(id="foreign-grant", name="Partners", description="", domain_id="domain"),
        "other-team": SimpleNamespace(id="other-team", name="Other", description="", domain_id="other"),
        "projection": PROJECTION,
    }
    state.groups.update({"team": ["member", "owner"], "privileged": [], "foreign-grant": [], "other-team": []})
    state.group_grants = [
        grant("team", "project_member", {"project": {"id": PROJECT}}),
        grant("privileged", "admin", {"system": {"all": True}}),
        grant("foreign-grant", "project_member", {"project": {"id": "foreign-project"}}),
    ]
    state.group_writes = []

    def get_group(gid):
        if gid not in state.group_rows:
            raise HTTPException(404, "Group not found")
        return state.group_rows[gid]

    def list_groups(domain=None, user=None):
        return [
            row
            for gid, row in state.group_rows.items()
            if (domain is None or row.domain_id == domain) and (user is None or user in state.groups.get(gid, []))
        ]

    def create_group(name, domain, description=""):
        gid = f"created-group-{len(state.group_writes)}"
        state.group_rows[gid] = SimpleNamespace(id=gid, name=name, description=description, domain_id=domain)
        state.groups[gid] = []
        state.group_writes.append(("create", gid))
        return state.group_rows[gid]

    def update_group(gid, **attrs):
        state.group_writes.append(("update", gid, attrs))
        for key, value in attrs.items():
            setattr(state.group_rows[gid], key, value)
        return state.group_rows[gid]

    state.ks.groups = SimpleNamespace(get=get_group, list=list_groups, create=create_group, update=update_group)
    ungrouped = state.ks.role_assignments.list

    def assignments(group=None, system=None, **kwargs):
        if group is None:
            return ungrouped(system=system, **kwargs)
        return [
            row
            for row in state.group_grants
            if row["group"]["id"] == group and (not system or "system" in row["scope"])
        ]

    state.ks.role_assignments.list = assignments

    def add_user(uid, gid):
        state.group_writes.append(("add", gid, uid))
        state.groups[gid].append(uid)

    def remove_user(uid, gid):
        state.group_writes.append(("remove", gid, uid))
        state.groups[gid].remove(uid)

    def delete_group(gid, ignore_missing=True):
        assert ignore_missing is False
        state.group_writes.append(("delete", gid))
        state.group_rows.pop(gid)
        state.groups.pop(gid, None)

    conn = SimpleNamespace(
        close=lambda: None,
        identity=SimpleNamespace(
            role_assignments=lambda group_id: assignments(group=group_id),
            group_users=lambda gid: [state.users[uid] for uid in state.groups.get(gid, [])],
            add_user_to_group=add_user,
            remove_user_from_group=remove_user,
            delete_group=delete_group,
        ),
    )
    monkeypatch.setattr(keystone, "get_admin_project_connection", lambda: conn)
    state.invalidation = AsyncMock()
    monkeypatch.setattr(identity_roles, "_assignment_invalidation", state.invalidation)
    monkeypatch.setattr(domain_iam_groups, "invalidate", AsyncMock())
    monkeypatch.setattr(domain_iam_groups.activity, "record", AsyncMock())
    # The configured organization SSO provider's native mapping, resolved by name like login does.
    state.sso_rules = [
        {
            "local": [{"user": {"name": "{0}", "email": "{1}", "type": "local", "domain": {"name": "Accounts"}}}],
            "remote": [{"type": "OIDC-preferred_username"}, {"type": "OIDC-email"}],
        }
    ]
    state.mapping_error = False

    def get_mapping(mapping_id):
        if state.mapping_error:
            raise RuntimeError("Keystone unavailable")
        assert mapping_id == "org-mapping"
        return SimpleNamespace(id=mapping_id, rules=state.sso_rules)

    def get_protocol(idp_id, protocol_id):
        assert (idp_id, protocol_id) == ("org-idp", "oidc")
        return SimpleNamespace(id=protocol_id, mapping_id="org-mapping")

    state.ks.federation = SimpleNamespace(
        protocols=SimpleNamespace(get=get_protocol), mappings=SimpleNamespace(get=get_mapping)
    )
    provider = SimpleNamespace(keystone_idp_id="org-idp", keystone_protocol_id="oidc")
    monkeypatch.setattr(
        domain_auth, "_selected_config_providers", lambda did: {"cfg:org": provider} if did == "domain" else {}
    )
    state.identity = manager()
    return state


@pytest.fixture
async def client(native):
    app = FastAPI()
    app.include_router(iam.router, prefix="/api/v1/iam")
    # The real require_domain_manager runs against the native directory.
    app.dependency_overrides[get_token_info] = lambda: native.identity
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


ROOT = "/api/v1/iam/groups"


@pytest.mark.asyncio
async def test_list_hides_projection_and_marks_groups_outside_domain_authority(client, native):
    response = await client.get(ROOT)
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store, private"
    items = response.json()["items"]
    assert [item["id"] for item in items] == ["privileged", "foreign-grant", "team"]
    by_id = {item["id"]: item for item in items}
    assert by_id["team"] == {
        "id": "team",
        "name": "Team",
        "description": "Builders",
        "domain_id": "domain",
        "member_count": 2,
        "protected": False,
        "sso_mapped": False,
    }
    assert by_id["privileged"]["protected"] and by_id["foreign-grant"]["protected"]


@pytest.mark.asyncio
async def test_list_fails_closed_on_foreign_directory_rows(client, native):
    native.ks.groups.list = lambda **kwargs: [native.group_rows["other-team"]]
    response = await client.get(ROOT)
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_create_group_uses_session_domain_and_rejects_duplicates_and_reserved_names(client, native):
    response = await client.post(ROOT, json={"name": "Builders", "description": "Release crew"})
    assert response.status_code == 201
    created = response.json()
    assert created["name"] == "Builders" and created["domain_id"] == "domain"
    assert created["member_count"] == 0 and created["protected"] is False
    assert native.group_rows[created["id"]].domain_id == "domain"
    writes = list(native.group_writes)

    duplicate = await client.post(ROOT, json={"name": "team"})
    assert duplicate.status_code == 409 and duplicate.json()["detail"] == "domain_group_name_exists"
    reserved = await client.post(ROOT, json={"name": "afterglow-default-managers-domain"})
    assert reserved.status_code == 403 and reserved.json()["detail"] == "domain_manager_projection_is_private"
    marker = await client.post(ROOT, json={"name": "x", "description": "afterglow:default-manager-reader:v1:domain"})
    assert marker.status_code == 403
    injected = await client.post(ROOT, json={"name": "Elsewhere", "domain_id": "other"})
    assert injected.status_code == 422
    blank = await client.post(ROOT, json={"name": " padded "})
    assert blank.status_code == 422
    assert native.group_writes == writes


@pytest.mark.asyncio
async def test_update_group_boundaries(client, native):
    response = await client.patch(f"{ROOT}/team", json={"name": "Renamed", "description": ""})
    assert response.status_code == 200
    assert response.json()["name"] == "Renamed" and response.json()["member_count"] == 2
    assert native.group_writes == [("update", "team", {"name": "Renamed", "description": ""})]

    for gid, body, status, detail in [
        ("team", {"name": "operators"}, 409, "domain_group_name_exists"),
        ("other-team", {"name": "Mine"}, 403, None),
        ("projection", {"description": "public"}, 403, "domain_manager_projection_is_private"),
        ("missing", {"name": "Ghost"}, 404, "domain_group_not_found"),
        ("privileged", {"name": "Mine"}, 403, "domain_group_read_only"),
        ("foreign-grant", {"name": "Mine"}, 403, "domain_group_read_only"),
        ("team", {}, 422, None),
        ("team", {"name": None}, 422, None),
    ]:
        denied = await client.patch(f"{ROOT}/{gid}", json=body)
        assert denied.status_code == status, (gid, body)
        if detail:
            assert denied.json()["detail"] == detail
    assert len(native.group_writes) == 1


@pytest.mark.asyncio
async def test_member_listing_and_membership_changes(client, native):
    members = await client.get(f"{ROOT}/team/members")
    assert members.status_code == 200
    assert {row["id"] for row in members.json()["items"]} == {"member", "owner"}
    assert all(row["protected"] is False and row["identity_read_only"] is False for row in members.json()["items"])

    added = await client.put(f"{ROOT}/team/members/admin")
    assert added.status_code == 204
    assert native.groups["team"] == ["member", "owner", "admin"]
    assert native.invalidation.await_args.args[1] == "group_member_add"

    for uid, status, detail in [
        ("admin", 409, "domain_group_member_exists"),
        ("foreign", 403, "User has not joined this domain"),
        ("system-admin", 403, "Privileged accounts are read-only in domain IAM"),
    ]:
        denied = await client.put(f"{ROOT}/team/members/{uid}")
        assert denied.status_code == status and denied.json()["detail"] == detail

    native.users["admin"].enabled = False
    native.groups["team"].remove("admin")
    disabled = await client.put(f"{ROOT}/team/members/admin")
    assert disabled.status_code == 403
    native.users["admin"].enabled = True
    native.groups["team"].append("admin")

    removed = await client.delete(f"{ROOT}/team/members/admin")
    assert removed.status_code == 204 and native.groups["team"] == ["member", "owner"]
    missing = await client.delete(f"{ROOT}/team/members/admin")
    assert missing.status_code == 404 and missing.json()["detail"] == "domain_group_member_not_found"

    for gid, status in [("projection", 403), ("other-team", 403), ("privileged", 403), ("missing", 404)]:
        assert (await client.put(f"{ROOT}/{gid}/members/member")).status_code == status
        assert (await client.delete(f"{ROOT}/{gid}/members/member")).status_code == status
    for gid, status in [("projection", 403), ("other-team", 403), ("missing", 404)]:
        assert (await client.get(f"{ROOT}/{gid}/members")).status_code == status
    assert [write[0] for write in native.group_writes] == ["add", "remove"]


@pytest.mark.asyncio
async def test_privileged_member_cannot_be_removed(client, native):
    native.groups["team"].append("system-admin")
    listed = await client.get(f"{ROOT}/team/members")
    assert next(row for row in listed.json()["items"] if row["id"] == "system-admin")["protected"] is True
    denied = await client.delete(f"{ROOT}/team/members/system-admin")
    assert denied.status_code == 403
    deleted = await client.delete(f"{ROOT}/team")
    assert deleted.status_code == 403
    assert not native.group_writes


@pytest.mark.asyncio
async def test_delete_group_boundaries_and_shared_owner_protection(client, native):
    for gid, status in [("projection", 403), ("other-team", 403), ("privileged", 403), ("missing", 404)]:
        assert (await client.delete(f"{ROOT}/{gid}")).status_code == status
    native.group_grants.append(grant("team", "project_owner", {"project": {"id": PROJECT}}))
    owner_bearing = await client.delete(f"{ROOT}/team")
    assert owner_bearing.status_code == 409
    assert not native.group_writes

    native.group_grants.pop()
    deleted = await client.delete(f"{ROOT}/team")
    assert deleted.status_code == 204
    assert native.group_writes == [("delete", "team")] and "team" not in native.group_rows
    assert native.invalidation.await_args.args[1] == "group_delete"
    domain_iam_groups.invalidate.assert_awaited_with("afterglow:admin:groups:*")


@pytest.mark.asyncio
@pytest.mark.parametrize("uid", ["member", "owner", "admin"])
async def test_non_manager_is_denied_every_group_endpoint(client, native, uid):
    native.identity = manager(uid)
    for method, path, body in [
        ("GET", ROOT, None),
        ("POST", ROOT, {"name": "Builders"}),
        ("PATCH", f"{ROOT}/team", {"name": "Renamed"}),
        ("DELETE", f"{ROOT}/team", None),
        ("GET", f"{ROOT}/team/members", None),
        ("PUT", f"{ROOT}/team/members/admin", None),
        ("DELETE", f"{ROOT}/team/members/member", None),
    ]:
        response = await client.request(method, path, json=body)
        assert response.status_code == 403, (method, path)
    assert not native.group_writes


def map_group(name, domain="domain"):
    return {
        "local": [{"group": {"name": name, "domain": {"id": domain}}}],
        "remote": [{"type": "OIDC-groups", "any_one_of": ["engineering"]}],
    }


@pytest.mark.asyncio
async def test_sso_mapped_group_name_cannot_be_renamed_deleted_or_reassigned(client, native):
    # Login requires exactly one group with this name; renaming/deleting it breaks domain SSO.
    native.sso_rules += [map_group("Team"), map_group("Mapped later"), map_group("Partners", domain="other")]
    listed = {item["id"]: item for item in (await client.get(ROOT)).json()["items"]}
    assert listed["team"]["sso_mapped"] is True and listed["team"]["protected"] is False
    assert listed["foreign-grant"]["sso_mapped"] is False

    for method, path, body, detail in [
        ("PATCH", f"{ROOT}/team", {"name": "Renamed"}, "domain_group_read_only"),
        ("PATCH", f"{ROOT}/team", {"name": "team"}, "domain_group_read_only"),
        ("DELETE", f"{ROOT}/team", None, "domain_group_read_only"),
        ("POST", ROOT, {"name": "mapped LATER"}, "domain_group_name_reserved"),
    ]:
        denied = await client.request(method, path, json=body)
        assert denied.status_code == 403 and denied.json()["detail"] == detail, (method, path, body)
    assert not native.group_writes

    native.group_rows["spare"] = SimpleNamespace(id="spare", name="Spare", description="", domain_id="domain")
    native.groups["spare"] = []
    reassigned = await client.patch(f"{ROOT}/spare", json={"name": "Mapped later"})
    assert reassigned.status_code == 403 and reassigned.json()["detail"] == "domain_group_name_reserved"
    assert not native.group_writes

    # The mapping resolves by name only: description and local membership stay manageable.
    described = await client.patch(f"{ROOT}/team", json={"description": "Engineering SSO"})
    assert described.status_code == 200 and described.json()["sso_mapped"] is True
    assert (await client.put(f"{ROOT}/team/members/admin")).status_code == 204
    assert [write[0] for write in native.group_writes] == ["update", "add"]


@pytest.mark.asyncio
async def test_unreadable_sso_mapping_fails_closed(client, native):
    native.mapping_error = True
    assert (await client.get(ROOT)).status_code == 503
    for method, path, body in [
        ("PATCH", f"{ROOT}/team", {"name": "Renamed"}),
        ("DELETE", f"{ROOT}/team", None),
        ("POST", ROOT, {"name": "Builders"}),
    ]:
        assert (await client.request(method, path, json=body)).status_code == 503, (method, path)
    assert not native.group_writes
