"""Managed backup member must not replace or invalidate a human Personal owner."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api import deps
from app.api.identity import projects
from app.services import account_spaces, backup_system_account, domain_projects, project_display, project_service
from tests.ownership_journal import ownership_journal as ownership_journal
from tests.test_domain_iam import directory as directory
from tests.test_domain_iam import enrollments as enrollments
from tests.test_project_membership_roles import rid

pytestmark = pytest.mark.usefixtures("ownership_journal")
SYSTEM_ID = "backup-machine"


@pytest.fixture
def personal_machine(directory, monkeypatch):
    monkeypatch.setattr(
        backup_system_account,
        "_cached_record",
        {
            "id": SYSTEM_ID,
            "domain_id": "domain",
            "domain_name": "Intended domain",
        },
    )
    monkeypatch.setattr(backup_system_account, "_cached_domain", ("domain", "Intended domain"))
    monkeypatch.setattr(
        backup_system_account, "get_settings", lambda: SimpleNamespace(os_user_domain_name="Intended domain")
    )
    directory.users[SYSTEM_ID] = SimpleNamespace(
        id=SYSTEM_ID,
        name=backup_system_account.ACCOUNT_NAME,
        domain_id="domain",
        enabled=True,
        email="machine@test.invalid",
    )
    return directory


@pytest.mark.parametrize("legacy_owner", [False, True])
async def test_personal_owner_keeps_login_capabilities_display_and_compute_write_authority(
    personal_machine,
    enrollments,
    monkeypatch,
    legacy_owner,
):
    state = personal_machine
    project = await account_spaces.ensure_personal_project("foreign")
    pid = project["id"]
    if legacy_owner:
        state.ks.roles.revoke(rid("member"), user="foreign", project=pid)
        state.ks.roles.grant(rid("project_owner"), user="foreign", project=pid)
    repair = AsyncMock(side_effect=AssertionError("Backup membership must never invoke owner repair"))
    monkeypatch.setattr(project_service, "_write_initial_owner", repair)
    before_owner = project_service._ownership_state_sync(state.ks, state.catalog, pid)
    state.ks.roles.grant(rid("member"), user=SYSTEM_ID, project=pid)
    calls = list(state.calls)
    actor = {
        "user_id": "foreign",
        "username": "foreign",
        "domain_id": project["domain_id"],
        "identity_domain_id": "other",
        "project_id": pid,
        "is_system_admin": False,
        "roles": ["member", "project_owner"] if legacy_owner else ["member"],
    }
    assert account_spaces.personal_project("foreign") == project
    domain_projects.assert_project_membership("foreign", pid)
    assert project["domain_id"] in {item["id"] for item in domain_projects.accessible_domains("foreign")}
    assert await project_service.can_create_project("foreign", project["domain_id"])
    assert deps.require_project_write(actor) is actor
    assert project_service._ownership_state_sync(state.ks, state.catalog, pid) == before_owner
    display = await project_display.get_display_name(pid, actor)
    assert display["can_edit"] is True
    application = FastAPI()
    application.include_router(projects.router, prefix="/api/v1/projects")
    application.dependency_overrides[deps.get_token_info] = lambda: actor
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
        capabilities = await client.get("/api/v1/projects/capabilities")
    assert capabilities.status_code == 200, capabilities.text
    assert capabilities.json()["can_create_project"] is True
    assert state.calls == calls
    state.ks.roles.revoke(rid("member"), user=SYSTEM_ID, project=pid)
    assert account_spaces.personal_project("foreign") == project
    assert project_service._ownership_state_sync(state.ks, state.catalog, pid) == before_owner
    repair.assert_not_awaited()


def source(uid="foreign", role="member", **extra):
    return {
        "role_id": rid(role),
        "user_id": uid,
        "group_id": None,
        "kind": "project",
        "scope_id": "personal-project",
        "inherited": False,
        "users": {uid},
        **extra,
    }


@pytest.mark.parametrize(
    "bad",
    [
        {"inherited": True},
        {"group_id": "team", "user_id": None},
        {"kind": "domain", "scope_id": "personal"},
        {"role_id": rid("reader")},
        {"role_id": rid("project_admin")},
        {"user_id": "unrelated", "users": {"unrelated"}},
        {"scope_id": "another-project"},
        {"users": {SYSTEM_ID, "unrelated"}},
    ],
)
def test_personal_exemption_rejects_every_noncanonical_source(personal_machine, bad):
    owner = source()
    machine = source(SYSTEM_ID, **bad)
    sources = [owner, machine]
    assert not account_spaces._member_sources(sources, personal_machine.catalog, "foreign", "personal-project")
    assert not domain_projects._personal_member(sources, personal_machine.catalog, "foreign", "personal-project")


def test_extra_machine_role_is_not_hidden_by_valid_member_grant(personal_machine):
    rows = [source(), source(SYSTEM_ID), source(SYSTEM_ID, role="reader")]
    assert not domain_projects._personal_member(rows, personal_machine.catalog, "foreign", "personal-project")
    legacy = [source(role="project_owner"), source(SYSTEM_ID), source(SYSTEM_ID, role="reader")]
    assert not domain_projects._personal_member(legacy, personal_machine.catalog, "foreign", "personal-project")


def test_cold_cache_never_guesses_canonical_user_by_reserved_name(personal_machine, monkeypatch):
    monkeypatch.setattr(backup_system_account, "_cached_record", None)
    rows = [source(), source(SYSTEM_ID)]
    assert not account_spaces._member_sources(rows, personal_machine.catalog, "foreign", "personal-project")
    assert not domain_projects._personal_member(rows, personal_machine.catalog, "foreign", "personal-project")


async def test_nonpersonal_member_does_not_change_unique_owner_or_manager_projection(personal_machine, enrollments):
    state = personal_machine
    project = await account_spaces.ensure_personal_project("foreign")
    # The existing organization is independent of Personal primary ownership.
    default = domain_projects.default_project("domain", ks=state.ks)
    before_managers = domain_projects._manager_users(state.ks, default, state.catalog)
    state.ks.roles.grant(rid("member"), user=SYSTEM_ID, project=default["id"])
    assert domain_projects._manager_users(state.ks, default, state.catalog) == before_managers
    assert SYSTEM_ID not in before_managers
    state.ks.roles.grant(rid("member"), user=SYSTEM_ID, project=project["id"])
    before = deepcopy(state.calls)
    assert account_spaces.personal_project("foreign") == project
    assert state.calls == before


@pytest.mark.parametrize(
    "extra",
    [
        source("unrelated"),
        source(None, group_id="team", users={"unrelated"}),
        source("foreign", inherited=True),
        source(SYSTEM_ID, kind="domain", scope_id="personal", inherited=True),
    ],
)
def test_legacy_owner_still_rejects_any_unmanaged_member_source(personal_machine, extra):
    rows = [source(role="project_owner"), source(SYSTEM_ID), extra]
    assert account_spaces.has_personal_member_source(rows, personal_machine.catalog, "personal-project")
    assert not domain_projects._personal_member(rows, personal_machine.catalog, "foreign", "personal-project")
