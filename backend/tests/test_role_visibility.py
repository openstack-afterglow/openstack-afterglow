"""Public role presentation must not change verified project authorization."""

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api.deps import get_token_info, require_project_write
from app.api.identity.auth import _build_token_response
from app.main import app
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
    client,
    monkeypatch,
    auth_directory,
    native_auth,
    roles,
    system_admin,
    visible,
    can_write,
    permissions_project,
    downgraded,
):
    info = make_token_info(roles=roles, is_system_admin=system_admin)
    info["identity_domain_id"] = auth_directory.users[info["user_id"]]["domain_id"]
    info["identity_domain_name"] = "Accounts"
    native_auth.roles = roles
    monkeypatch.setattr("app.database.get_session_factory", lambda: None)
    app.dependency_overrides[get_token_info] = lambda: dict(info)
    effective_project_id = info["project_id"] if permissions_project == "current" else permissions_project
    validate = AsyncMock(return_value={**info, "project_id": effective_project_id})
    monkeypatch.setattr("app.api.deps._cached_validate", validate)

    # Presentation uses verified token roles; permissions independently resolve
    # canonical role IDs from current provider assignments. Uppercase token admin
    # remains hidden, but uppercase *authority* bindings are not canonical.
    current_roles = ["reader"] if downgraded else [role.lower() for role in roles]
    auth_directory.roles = [{"id": "role-" + name, "name": name} for name in ("admin", "manager", "member", "reader")]
    auth_directory.inferences = []
    auth_directory.grants = {}
    auth_directory.projects[effective_project_id] = {
        "id": effective_project_id,
        "name": effective_project_id,
        "domain_id": info["domain_id"],
        "enabled": True,
    }
    auth_directory.assignments = [
        {
            "user": {"id": info["user_id"]},
            "role": {"id": "role-" + name},
            "scope": {"project": {"id": effective_project_id}},
        }
        for name in current_roles
    ]
    if effective_project_id != info["project_id"]:
        # The caller's original native token still needs its own current grant;
        # this is independent of the permission snapshot's selected project.
        auth_directory.assignments.append(
            {
                "user": {"id": info["user_id"]},
                "role": {"id": "role-reader"},
                "scope": {"project": {"id": info["project_id"]}},
            }
        )
    if system_admin:
        auth_directory.assignments.append(
            {
                "user": {"id": info["user_id"]},
                "role": {"id": "role-admin"},
                "scope": {"system": {"all": True}},
            }
        )

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
        domain_id=info["domain_id"],
        domain_name=info["domain_name"],
        is_domain_manager=info["is_domain_manager"],
        identity_domain_id=info["identity_domain_id"],
        identity_domain_name=info["identity_domain_name"],
    )

    assert me.status_code == permissions.status_code == 200
    for payload in (me.json(), credentials.model_dump()):
        assert payload["roles"] == visible
        assert payload["can_write"] is can_write
        assert payload["is_system_admin"] is system_admin
    assert permissions.json()["project_id"] == effective_project_id
    assert permissions.json()["roles"] == (["reader"] if downgraded else visible)
    assert permissions.json()["can_write"] is (False if downgraded else can_write)
    assert permissions.json()["is_system_admin"] is system_admin
    assert info["roles"] == roles
    if can_write:
        assert require_project_write(info) is info
    else:
        with pytest.raises(HTTPException) as denied:
            require_project_write(info)
        assert denied.value.status_code == 403
    if system_admin:
        # A cached presentation claim must not authorize after native revocation.
        auth_directory.assignments = [row for row in auth_directory.assignments if "system" not in row["scope"]]
        revoked = await client.get(f"/api/v1/projects/{permissions_project}/permissions")
        assert revoked.status_code == 403
        assert revoked.json()["detail"]["code"] == "system_admin_required"
