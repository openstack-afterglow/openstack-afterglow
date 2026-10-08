"""Public role presentation must not change verified project authorization."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.deps import get_token_info, require_project_write
from app.api.identity.auth import _build_token_response
from app.database import get_session
from app.main import app
from app.services import keystone
from app.services.project_service import accept_invitation
from tests.conftest import make_token_info


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("roles", "system_admin", "visible", "can_write"),
    [
        (["admin", "manager", "member", "reader"], False, ["member", "reader"], True),
        (["ADMIN"], False, [], True),
        (["manager", "reader"], False, ["reader"], False),
        (["reader"], False, ["reader"], False),
        (["admin", "manager", "reader"], True, ["admin", "manager", "reader"], True),
    ],
)
@pytest.mark.parametrize("permissions_project", ["current", "foreign-project"])
@pytest.mark.parametrize("downgraded", [False, True])
async def test_public_identity_preserves_capability_without_exposing_system_roles(
    client, monkeypatch, roles, system_admin, visible, can_write, permissions_project, downgraded
):
    info = make_token_info(roles=roles, is_system_admin=system_admin)
    monkeypatch.setattr("app.database.get_session_factory", lambda: None)
    app.dependency_overrides[get_token_info] = lambda: info
    effective_project_id = info["project_id"] if permissions_project == "current" else permissions_project
    validate = AsyncMock(return_value={**info, "project_id": effective_project_id})
    monkeypatch.setattr("app.api.deps._cached_validate", validate)

    # Presentation uses verified token roles; permissions independently resolve
    # canonical role IDs from current provider assignments. Uppercase token admin
    # remains hidden, but uppercase *authority* bindings are not canonical.
    current_roles = ["reader"] if downgraded else [role.lower() for role in roles]
    catalog = [{"id": "role-" + name, "name": name} for name in ("admin", "manager", "member", "reader")]
    assignments = MagicMock(
        return_value=[
            {
                "user": {"id": info["user_id"]},
                "role": {"id": "role-" + name},
                "scope": {"project": {"id": effective_project_id}},
            }
            for name in current_roles
        ]
    )
    ks = SimpleNamespace(
        roles=SimpleNamespace(list=lambda: catalog),
        inference_rules=SimpleNamespace(list_inference_roles=lambda: []),
        role_assignments=SimpleNamespace(list=assignments),
    )
    monkeypatch.setattr(keystone, "_get_admin_ks_client", lambda: ks)

    me = await client.get("/api/v1/auth/me")
    permissions = await client.get(f"/api/v1/projects/{permissions_project}/permissions")
    credentials = await _build_token_response(
        keystone_token="synthetic-keystone-token",
        project_id=info["project_id"],
        project_name=info["project_name"],
        user_id=info["user_id"],
        username=info["username"],
        roles=roles,
        is_system_admin=system_admin,
    )

    assert me.status_code == permissions.status_code == 200
    for payload in (me.json(), credentials.model_dump()):
        assert payload["roles"] == visible
        assert payload["can_write"] is can_write
        assert payload["is_system_admin"] is system_admin
    assert permissions.json()["project_id"] == effective_project_id
    assert permissions.json()["roles"] == (["reader"] if downgraded else visible)
    assert permissions.json()["can_write"] is (system_admin if downgraded else can_write)
    assert permissions.json()["is_system_admin"] is system_admin
    if permissions_project != "current" and not system_admin:
        validate.assert_awaited_once_with(info["token"], effective_project_id)
    else:
        validate.assert_not_awaited()
    assert info["roles"] == roles
    assignments.assert_called_once_with(project=effective_project_id, effective=True)
    if can_write:
        assert require_project_write(info) is info
    else:
        with pytest.raises(HTTPException) as denied:
            require_project_write(info)
        assert denied.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["admin", "manager", "privileged-alias"])
async def test_self_service_invitation_rejects_privileged_role(client, monkeypatch, role):
    async def isolated_session():
        yield AsyncMock()

    monkeypatch.setitem(app.dependency_overrides, get_session, isolated_session)
    response = await client.post(
        "/api/v1/projects/test-project-123/invitations",
        json={"email": "invitee@example.test", "keystone_role": role},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["admin", "manager", "privileged-alias"])
async def test_legacy_privileged_invitation_cannot_grant_keystone_role(monkeypatch, role):
    invitation = SimpleNamespace(
        status="pending",
        invited_email="invitee@example.test",
        expires_at=datetime.now(UTC) + timedelta(days=1),
        keystone_role=role,
    )
    session = AsyncMock()
    session.execute.return_value = MagicMock(scalar_one_or_none=lambda: invitation)
    grant = AsyncMock()
    monkeypatch.setattr("app.services.project_service._grant_project_role", grant)

    with pytest.raises(HTTPException) as denied:
        await accept_invitation("invitation-token", "invitee", "invitee@example.test", session)

    assert denied.value.status_code == 403
    assert invitation.status == "pending"
    grant.assert_not_called()
    session.commit.assert_not_awaited()
