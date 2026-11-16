"""Default SSH key endpoints use caller inventory and immutable account identity."""

from unittest.mock import AsyncMock, patch

import pytest

from app.api.deps import get_token_info
from app.main import app
from app.services import ssh_key_preferences

PATH = "/api/v1/profile/ssh-key-preference"


@pytest.mark.asyncio
async def test_get_set_clear(client, mock_conn):
    response = await client.get(PATH)
    assert response.status_code == 200
    assert response.json() == {"keypair_name": None}
    assert response.headers["cache-control"] == "private, no-store"
    with patch("app.services.nova.list_keypairs", return_value=[{"name": "my-key"}]) as inventory:
        response = await client.put(PATH, json={"keypair_name": "my-key"})
    inventory.assert_called_once_with(mock_conn)
    assert response.status_code == 200
    assert (await client.get(PATH)).json() == {"keypair_name": "my-key"}
    assert (await client.put(PATH, json={"keypair_name": None})).status_code == 200
    assert (await client.get(PATH)).json() == {"keypair_name": None}


@pytest.mark.asyncio
async def test_unknown_key_does_not_replace_default(client):
    with patch("app.services.nova.list_keypairs", return_value=[{"name": "mine"}]):
        assert (await client.put(PATH, json={"keypair_name": "mine"})).status_code == 200
        response = await client.put(PATH, json={"keypair_name": "foreign"})
    assert response.status_code == 404
    assert (await client.get(PATH)).json() == {"keypair_name": "mine"}


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["", 42, "x" * 256])
async def test_invalid_name(client, name):
    assert (await client.put(PATH, json={"keypair_name": name})).status_code == 422


@pytest.mark.asyncio
async def test_missing_field_does_not_implicitly_clear(client):
    assert (await client.put(PATH, json={})).status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["get", "put"])
async def test_redis_failure_is_unavailable(client, method):
    with patch("app.services.cache._get_redis", new=AsyncMock(side_effect=RuntimeError("unavailable"))):
        response = await client.get(PATH) if method == "get" else await client.put(PATH, json={"keypair_name": None})
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_identity_and_home_isolation_across_projects(client):
    previous = app.dependency_overrides.copy()
    try:
        identity = {"user_id": "alice", "identity_domain_id": "home", "project_id": "first"}
        app.dependency_overrides[get_token_info] = lambda: identity.copy()
        with patch("app.services.nova.list_keypairs", return_value=[{"name": "mine"}]):
            assert (await client.put(PATH, json={"keypair_name": "mine"})).status_code == 200
        identity["project_id"] = "second"
        assert (await client.get(PATH)).json() == {"keypair_name": "mine"}
        identity["user_id"] = "bob"
        assert (await client.get(PATH)).json() == {"keypair_name": None}
        identity.update(user_id="alice", identity_domain_id="other-home")
        assert (await client.get(PATH)).json() == {"keypair_name": None}
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


@pytest.mark.asyncio
async def test_delete_default_clears_preference_but_other_key_does_not(client):
    with (
        patch("app.services.nova.list_keypairs", return_value=[{"name": "mine"}]),
        patch("app.api.compute.keypairs.nova.delete_keypair"),
        patch("app.api.compute.keypairs.patch_list", new=AsyncMock()),
        patch("app.api.compute.keypairs.invalidation.invalidate_mutation_count", new=AsyncMock()),
    ):
        assert (await client.put(PATH, json={"keypair_name": "mine"})).status_code == 200
        assert (await client.delete("/api/v1/keypairs/other")).status_code == 204
        assert (await client.get(PATH)).json() == {"keypair_name": "mine"}
        assert (await client.delete("/api/v1/keypairs/mine")).status_code == 204
        assert (await client.get(PATH)).json() == {"keypair_name": None}


@pytest.mark.asyncio
async def test_pending_deletion_does_not_clear_new_default():
    await ssh_key_preferences.save("alice", "home", "new-key")
    await ssh_key_preferences.clear_deleted("alice", "home", "old-key")
    assert await ssh_key_preferences.read("alice", "home") == {"keypair_name": "new-key"}
