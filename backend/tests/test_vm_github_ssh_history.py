from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.compute.instances import _verify_github_ssh
from app.api.union import layer_public
from app.models.compute import CreateInstanceRequest
from app.services import github_ssh

_BASE_PAYLOAD = {
    "name": "github-vm",
    "image_id": "img-1",
    "flavor_id": "flavor-1",
    "network_id": "net-1",
    "github_username": "octocat",
}


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/api/v1/instances", "/api/v1/instances/async"])
async def test_user_create_rejects_unverified_github_before_openstack_mutation(client, path):
    error = github_ssh.GitHubSshInvalid("GitHub 계정에 공개 SSH 키가 없습니다.")
    with (
        patch("app.services.github_ssh.verify_and_record", AsyncMock(side_effect=error)) as verify,
        patch("app.api.compute.instances.cinder.create_volume_from_image") as create_volume,
        patch("app.api.compute.instances.nova.create_server") as create_server,
    ):
        response = await client.post(path, json=_BASE_PAYLOAD)

    assert response.status_code == 422
    assert response.json() == {"detail": "GitHub 계정에 공개 SSH 키가 없습니다."}
    verify.assert_awaited_once_with(user_id="test-user-123", username="octocat")
    create_volume.assert_not_called()
    create_server.assert_not_called()


@pytest.mark.asyncio
async def test_admin_create_rejects_unverified_github_before_target_connection(admin_client):
    error = github_ssh.GitHubSshUnavailable("GitHub 공개키 조회를 사용할 수 없습니다.")
    payload = {**_BASE_PAYLOAD, "project_id": "target-project-abc"}
    with (
        patch("app.services.github_ssh.verify_and_record", AsyncMock(side_effect=error)),
        patch("app.api.identity.admin_instances._make_admin_conn") as make_admin_conn,
        patch("app.api.identity.admin_instances.nova.create_server") as create_server,
    ):
        response = await admin_client.post("/api/v1/admin/instances/async", json=payload)

    assert response.status_code == 503
    make_admin_conn.assert_not_called()
    create_server.assert_not_called()


@pytest.mark.asyncio
async def test_public_squashfs_consume_rejects_unverified_github_before_database_or_openstack(monkeypatch):
    error = github_ssh.GitHubSshInvalid("GitHub 계정에 공개 SSH 키가 없습니다.")
    factory = MagicMock()
    monkeypatch.setattr(layer_public, "get_session_factory", lambda: factory)
    verify = AsyncMock(side_effect=error)
    monkeypatch.setattr(github_ssh, "verify_and_record", verify)
    run_consume = AsyncMock()
    monkeypatch.setattr("app.services.layer_build.run_layer_consume", run_consume)

    with pytest.raises(HTTPException) as exc:
        await layer_public.consume_public_squashfs(
            layer_public.PublicLayerConsumeRequest(
                artifact_ids=[1],
                server_name="github-vm",
                flavor_id="flavor-1",
                github_username="octocat",
            ),
            conn=MagicMock(_afterglow_project_id="project-a"),
            token_info={"project_id": "project-a", "user_id": "user-a"},
        )

    assert exc.value.status_code == 422
    verify.assert_awaited_once_with(user_id="user-a", username="octocat")
    factory.assert_not_called()
    run_consume.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_preflight_replaces_input_with_canonical_github_login():
    req = CreateInstanceRequest(**_BASE_PAYLOAD)
    profile = {
        "id": 583231,
        "login": "OctoCat",
        "name": None,
        "public_email": None,
        "html_url": "https://github.com/OctoCat",
        "has_public_keys": True,
        "verified_at": "2026-09-20T00:00:00+00:00",
    }
    with patch("app.services.github_ssh.verify_and_record", AsyncMock(return_value=profile)) as verify:
        updated = await _verify_github_ssh(req, token_info={"user_id": "user-a", "project_id": "project-a"})

    assert updated.github_username == "OctoCat"
    assert req.github_username == "octocat"
    verify.assert_awaited_once_with(user_id="user-a", username="octocat")
