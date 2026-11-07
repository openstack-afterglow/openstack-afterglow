"""Domain-manager project name/description edits through the IAM router."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_token_info, require_domain_manager
from app.api.identity import iam
from app.services import domain_iam_projects, project_service
from tests.ownership_journal import ownership_journal as ownership_journal
from tests.test_domain_iam import directory as directory
from tests.test_domain_iam import manager
from tests.test_project_membership_roles import PROJECT

pytestmark = pytest.mark.usefixtures("ownership_journal")


class NativeError(Exception):
    def __init__(self, status, message="native internal detail secret-endpoint"):
        super().__init__(message)
        self.http_status = status


def native_writes(directory, *, error=None, result=None):
    writes = []

    def update(pid, **attrs):
        writes.append((pid, attrs))
        if error is not None:
            raise error
        project = directory.ks.projects.get(pid)
        for key, value in attrs.items():
            setattr(project, key, value)
        return result if result is not None else project

    directory.ks.projects.update = update
    return writes


async def patch(path, body, *, token_info=None):
    app = FastAPI()
    app.include_router(iam.router, prefix="/api/v1/iam")
    if token_info is None:
        app.dependency_overrides[require_domain_manager] = manager
    else:
        app.dependency_overrides[get_token_info] = lambda: token_info
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.patch(path, json=body)


@pytest.mark.asyncio
async def test_manager_updates_native_name_and_description(directory):
    writes = native_writes(directory)
    response = await patch(f"/api/v1/iam/projects/{PROJECT}", {"name": "  Renamed  ", "description": "Team work"})
    assert response.status_code == 200
    assert response.json() == {"id": PROJECT, "name": "Renamed", "description": "Team work", "enabled": True}
    assert "no-store" in response.headers["Cache-Control"]
    assert writes == [(PROJECT, {"name": "Renamed", "description": "Team work"})]
    assert (directory.project.name, directory.project.description) == ("Renamed", "Team work")
    invalidated = {call.args[0] for call in project_service.cache.invalidate.await_args_list}
    assert {
        "afterglow:user:*:domain:domain:projects",
        "afterglow:admin:projects:*",
        "afterglow:admin:project_names:*",
        "afterglow:identity:domain-context:*",
    } <= invalidated
    recorded = project_service.activity.record.await_args.kwargs
    assert (recorded["action"], recorded["status"], recorded["resource_id"]) == ("project.update", "success", PROJECT)


@pytest.mark.asyncio
async def test_description_only_update_can_clear_and_keeps_name(directory):
    directory.project.description = "Old"
    writes = native_writes(directory)
    response = await patch(f"/api/v1/iam/projects/{PROJECT}", {"description": ""})
    assert response.status_code == 200
    assert response.json()["name"] == "Intended project" and response.json()["description"] == ""
    assert writes == [(PROJECT, {"description": ""})]


@pytest.mark.asyncio
@pytest.mark.parametrize("uid", ["member", "admin", "owner"])
async def test_non_manager_is_denied_before_native_write(directory, uid):
    writes = native_writes(directory)
    response = await patch(f"/api/v1/iam/projects/{PROJECT}", {"name": "Renamed"}, token_info=manager(uid))
    assert response.status_code == 403
    with pytest.raises(HTTPException) as denied:
        await domain_iam_projects.update_project(PROJECT, {"name": "Renamed"}, manager(uid))
    assert denied.value.status_code == 403
    assert not writes and directory.project.name == "Intended project"


@pytest.mark.asyncio
async def test_foreign_domain_project_is_denied(directory):
    writes = native_writes(directory)
    response = await patch("/api/v1/iam/projects/foreign-project", {"name": "Taken over"})
    assert response.status_code == 403
    assert response.json() == {"detail": "Resource is outside the current domain"}
    assert not writes


@pytest.mark.asyncio
async def test_missing_project_maps_to_safe_not_found(directory):
    directory.project = None
    writes = native_writes(directory)
    response = await patch(f"/api/v1/iam/projects/{PROJECT}", {"name": "Renamed"})
    assert response.status_code == 404
    assert response.json() == {"detail": "project_not_found"}
    assert not writes


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["Renamed", "default"])
async def test_default_project_name_is_immutable(directory, name):
    writes = native_writes(directory)
    response = await patch("/api/v1/iam/projects/default-project", {"name": name})
    assert response.status_code == 422
    assert response.json() == {"detail": "domain_default_is_immutable"}
    assert not writes


@pytest.mark.asyncio
async def test_default_project_description_follows_shared_contract(directory):
    writes = native_writes(directory)
    response = await patch("/api/v1/iam/projects/default-project", {"name": "Default", "description": "Authority"})
    assert response.status_code == 200
    assert writes == [("default-project", {"name": "Default", "description": "Authority"})]


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["Default", " default ", "DEFAULT"])
async def test_reserved_default_name_cannot_be_taken(directory, name):
    writes = native_writes(directory)
    response = await patch(f"/api/v1/iam/projects/{PROJECT}", {"name": name})
    assert response.status_code == 422
    assert response.json() == {"detail": "domain_default_is_immutable"}
    assert not writes and directory.project.name == "Intended project"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {},
        {"name": None},
        {"description": None},
        {"name": ""},
        {"name": "   "},
        {"name": "x" * 65},
        {"name": "bad\x00name"},
        {"name": "bad\u200bname"},
        {"name": 5},
        {"description": "d" * 4097},
        {"description": 7},
        {"enabled": False},
        {"domain_id": "other"},
        {"parent_id": "other"},
        {"name": "Renamed", "enabled": True},
    ],
)
async def test_invalid_input_is_rejected(directory, body):
    writes = native_writes(directory)
    response = await patch(f"/api/v1/iam/projects/{PROJECT}", body)
    assert response.status_code == 422
    assert response.json()["detail"] in {"Invalid IAM request", "Supply non-null project fields"}
    assert not writes


@pytest.mark.asyncio
async def test_boundary_lengths_are_accepted(directory):
    writes = native_writes(directory)
    response = await patch(f"/api/v1/iam/projects/{PROJECT}", {"name": "n" * 64, "description": "d" * 4096})
    assert response.status_code == 200
    assert writes == [(PROJECT, {"name": "n" * 64, "description": "d" * 4096})]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["applying", "unknown", "settled"])
async def test_unresolved_ownership_journal_blocks_edit(directory, ownership_journal, status):
    from app.models.project_ownership import ProjectOwnershipTransfer

    async with ownership_journal() as session:
        session.add(
            ProjectOwnershipTransfer(
                id="pending-transfer",
                project_id=PROJECT,
                domain_id="domain",
                from_user_id="owner",
                to_user_id="member",
                status=status,
                stage="grant",
            )
        )
        await session.commit()
    writes = native_writes(directory)
    response = await patch(f"/api/v1/iam/projects/{PROJECT}", {"name": "Renamed"})
    assert response.status_code == 409
    assert response.json() == {"detail": "project_ownership_native_operation_unresolved"}
    assert not writes


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "status", "detail"),
    [
        (NativeError(409), 409, "project_name_conflict"),
        (HTTPException(409, "Duplicate project name secret-endpoint"), 409, "project_name_conflict"),
        (NativeError(400), 422, "project_update_invalid"),
        (NativeError(403), 403, "project_update_denied"),
        (NativeError(404), 404, "project_not_found"),
        (NativeError(500), 503, "project_update_unavailable"),
        (RuntimeError("connection to secret-endpoint refused"), 503, "project_update_unavailable"),
    ],
)
async def test_native_failure_maps_to_safe_public_error(directory, error, status, detail):
    writes = native_writes(directory, error=error)
    response = await patch(f"/api/v1/iam/projects/{PROJECT}", {"name": "Renamed"})
    assert response.status_code == status
    assert response.json() == {"detail": detail}
    assert "secret" not in response.text
    assert writes == [(PROJECT, {"name": "Renamed"})]
    assert project_service.activity.record.await_args.kwargs["status"] == "failed"
    invalidated = {call.args[0] for call in project_service.cache.invalidate.await_args_list}
    assert "afterglow:admin:projects:*" in invalidated


@pytest.mark.asyncio
async def test_unconfirmed_native_result_fails_closed(directory):
    writes = native_writes(
        directory, result=SimpleNamespace(id=PROJECT, name="Renamed", domain_id="other", enabled=True)
    )
    response = await patch(f"/api/v1/iam/projects/{PROJECT}", {"name": "Renamed"})
    assert response.status_code == 503
    assert response.json() == {"detail": "project_update_unverified"}
    assert writes == [(PROJECT, {"name": "Renamed"})]
    assert project_service.activity.record.await_args.kwargs["status"] == "failed"
