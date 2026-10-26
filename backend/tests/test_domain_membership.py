"""Domain eviction preserves identity/resources and unrelated authority."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from app.api.deps import require_domain_manager
from app.api.identity import iam
from app.services import domain_membership
from tests.ownership_journal import ownership_journal as ownership_journal
from tests.test_domain_iam import directory as directory
from tests.test_domain_iam import manager
from tests.test_project_membership_roles import PROJECT, assignment, rid

pytestmark = pytest.mark.usefixtures("ownership_journal")


@pytest.fixture(autouse=True)
def native_group_filters(directory, monkeypatch):
    original = directory.ks.role_assignments.list

    def assignments(*args, **kwargs):
        rows = original(*args, **kwargs)
        group = kwargs.get("group")
        return [row for row in rows if row.get("group", {}).get("id") == group] if group is not None else rows

    monkeypatch.setattr(directory.ks.role_assignments, "list", assignments)


@pytest.mark.asyncio
async def test_domain_eviction_removes_all_local_direct_sources_not_identity_or_foreign_access(directory):
    directory.direct.append(assignment("foreign", "project_member"))
    directory.default_direct.append(
        {
            "user": {"id": "foreign"},
            "role": {"id": rid("project_reader")},
            "scope": {"project": {"id": "default-project"}},
        }
    )
    directory.personal_projects["foreign-project"] = SimpleNamespace(
        id="foreign-project", name="Other", domain_id="other", enabled=True
    )
    foreign = {
        "user": {"id": "foreign"},
        "role": {"id": rid("project_member")},
        "scope": {"project": {"id": "foreign-project"}},
    }
    directory.personal_direct.append(foreign)
    user = directory.users["foreign"]
    app = FastAPI()
    app.include_router(iam.router, prefix="/api/v1/iam")
    app.dependency_overrides[require_domain_manager] = manager
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.delete("/api/v1/iam/users/foreign")
    assert response.status_code == 200, response.text
    assert response.json() == {"status": "removed", "domain_id": "domain", "user_id": "foreign"}
    assert directory.users["foreign"] is user and user.enabled and user.domain_id == "other"
    assert foreign in directory.personal_direct
    assert not any(r.get("user", {}).get("id") == "foreign" for r in directory.direct + directory.default_direct)
    assert directory.project.id == PROJECT
    assert response.headers["cache-control"] == "no-store, private"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "target,code",
    [
        ("member", "domain_eviction_identity_home"),
        ("domain-manager", "domain_eviction_self"),
        ("system-admin", "domain_eviction_protected"),
    ],
)
async def test_eviction_rejects_identity_home_self_and_system_account_before_write(directory, target, code):
    with pytest.raises(HTTPException) as error:
        await domain_membership.remove_user(target, manager())
    assert error.value.detail == code
    assert not directory.calls and not directory.updates


@pytest.mark.asyncio
async def test_eviction_preserves_project_ownership(directory):
    directory.direct.append(assignment("foreign", "project_owner"))
    with pytest.raises(HTTPException) as error:
        await domain_membership.remove_user("foreign", manager())
    assert error.value.detail == "domain_eviction_privileged_source"
    assert not directory.calls


@pytest.mark.asyncio
async def test_eviction_failed_readback_is_uncertain_never_success(directory, monkeypatch):
    directory.direct.append(assignment("foreign", "project_member"))
    original = directory.ks.role_assignments.list

    def unavailable(*args, **kwargs):
        if directory.calls:
            raise HTTPException(503, "native unavailable")
        return original(*args, **kwargs)

    monkeypatch.setattr(directory.ks.role_assignments, "list", unavailable)
    with pytest.raises(HTTPException) as error:
        await domain_membership.remove_user("foreign", manager())
    assert error.value.status_code == 503 and error.value.detail == "domain_eviction_uncertain"
    assert ("revoke", "foreign", rid("project_member")) in directory.calls


@pytest.mark.asyncio
async def test_eviction_revoked_manager_cannot_mutate(directory):
    directory.direct.append(assignment("foreign", "project_member"))
    directory.managers.clear()
    with pytest.raises(HTTPException) as error:
        await domain_membership.remove_user("foreign", manager())
    assert error.value.status_code == 403
    assert not directory.calls


@pytest.mark.asyncio
async def test_eviction_removes_only_current_domain_group_membership(directory, monkeypatch):
    directory.groups["team"] = ["foreign"]
    directory.direct.append(
        {"group": {"id": "team"}, "role": {"id": rid("project_reader")}, "scope": {"project": {"id": PROJECT}}}
    )
    removals = []

    def remove(uid, gid):
        removals.append((uid, gid))
        directory.groups[gid].remove(uid)

    monkeypatch.setattr(directory.ks.users, "remove_from_group", remove, raising=False)
    result = await domain_membership.remove_user("foreign", manager())
    assert result["status"] == "removed"
    assert removals == [("foreign", "team")]
    assert "foreign" in directory.users and directory.project.id == PROJECT


@pytest.mark.asyncio
async def test_eviction_does_not_remove_group_with_foreign_grant(directory, monkeypatch):
    directory.groups["team"] = ["foreign"]
    directory.direct.append(
        {"group": {"id": "team"}, "role": {"id": rid("project_reader")}, "scope": {"project": {"id": PROJECT}}}
    )
    directory.personal_direct.append(
        {
            "group": {"id": "team"},
            "role": {"id": rid("project_reader")},
            "scope": {"project": {"id": "foreign-project"}},
        }
    )
    with pytest.raises(HTTPException) as error:
        domain_membership._plan(directory.ks, directory.catalog, "domain", "foreign")
    assert error.value.detail == "domain_eviction_shared_group"
    assert directory.groups["team"] == ["foreign"] and not directory.calls


def test_eviction_preflight_ignores_unrelated_unknown_role_and_deleted_project(directory):
    directory.direct.append(assignment("foreign", "project_member"))
    directory.personal_direct.append(
        {
            "user": {"id": "unrelated-user"},
            "role": {"id": "unknown-role"},
            "scope": {"project": {"id": "deleted-project"}},
        }
    )
    direct, groups = domain_membership._plan(directory.ks, directory.catalog, "domain", "foreign")
    assert [(row["scope_id"], row["role_id"]) for row in direct] == [(PROJECT, rid("project_member"))]
    assert groups == []
    assert directory.personal_direct[-1]["role"]["id"] == "unknown-role"


def test_eviction_includes_disabled_project_omitted_by_native_list(directory, monkeypatch):
    project = SimpleNamespace(id="disabled-project", domain_id="domain", enabled=False)
    get = directory.ks.projects.get
    monkeypatch.setattr(directory.ks.projects, "get", lambda pid, **kwargs: project if pid == project.id else get(pid))
    directory.personal_direct.append(assignment("foreign", "project_reader", project_id=project.id))
    direct, groups = domain_membership._plan(directory.ks, directory.catalog, "domain", "foreign")
    assert [row["scope_id"] for row in direct] == [project.id] and groups == []


@pytest.mark.parametrize("subtree", [None, {"child-project": None}])
def test_native_null_subtree_leaves_are_valid_local_inheritance(directory, monkeypatch, subtree):
    directory.direct.append(assignment("foreign", "project_reader", inherited=True))
    get = directory.ks.projects.get

    def project(pid, **kwargs):
        if kwargs.get("subtree_as_ids"):
            return SimpleNamespace(id=pid, subtree=subtree)
        if pid == "child-project":
            return SimpleNamespace(id=pid, domain_id="domain", enabled=False)
        return get(pid)

    monkeypatch.setattr(directory.ks.projects, "get", project)
    direct, _ = domain_membership._plan(directory.ks, directory.catalog, "domain", "foreign")
    assert direct[0]["inherited"] is True and direct[0]["scope_id"] == PROJECT


def test_truncated_native_subject_inventory_fails_before_revokes(directory, monkeypatch):
    def get(path):
        return None, {
            "role_assignments": [assignment("foreign", "project_member")],
            "links": {"next": "https://native.invalid/next"},
        }

    monkeypatch.setattr(directory.ks.role_assignments, "client", SimpleNamespace(get=get), raising=False)
    with pytest.raises(HTTPException) as denied:
        domain_membership._plan(directory.ks, directory.catalog, "domain", "foreign")
    assert denied.value.status_code == 503
    assert not directory.calls
