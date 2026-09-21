from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services import github_ssh

_PROFILE = {
    "id": 583231,
    "login": "OctoCat",
    "type": "User",
    "name": "The Octocat",
    "email": "octocat@example.com",
    "html_url": "https://github.com/OctoCat",
    "avatar_url": "https://avatars.githubusercontent.com/u/583231",
    "company": "GitHub",
}
_KEYS = [{"id": 7, "key": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITest"}]
_VERIFIED_AT = "2026-09-20T00:00:00+00:00"


def _install_transport(monkeypatch, handler):
    real_client = httpx.AsyncClient
    captured: list[dict] = []

    def factory(**kwargs):
        captured.append(kwargs)
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(github_ssh.httpx, "AsyncClient", factory)
    return captured


def _github_handler(*, profile=None, keys=None, profile_status=200, keys_status=200, headers=None):
    profile_payload = _PROFILE if profile is None else profile
    key_payload = _KEYS if keys is None else keys

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/keys"):
            return httpx.Response(keys_status, json=key_payload, headers=headers)
        return httpx.Response(profile_status, json=profile_payload, headers=headers)

    return handler


@pytest.mark.asyncio
async def test_resolver_uses_fixed_origin_minimal_mapping_and_cache(monkeypatch):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _github_handler()(request)

    captured = _install_transport(monkeypatch, handler)

    first = await github_ssh.resolve_profile("OctoCat")
    second = await github_ssh.resolve_profile("octocat")

    assert (
        first
        == second
        == {
            "id": 583231,
            "login": "OctoCat",
            "name": "The Octocat",
            "public_email": "octocat@example.com",
            "html_url": "https://github.com/OctoCat",
            "has_public_keys": True,
        }
    )
    assert [str(request.url) for request in requests] == [
        "https://api.github.com/users/OctoCat",
        "https://api.github.com/users/OctoCat/keys?per_page=1",
    ]
    assert captured[0]["follow_redirects"] is False
    assert captured[0]["trust_env"] is False
    assert requests[0].headers["x-github-api-version"] == "2022-11-28"


@pytest.mark.asyncio
async def test_resolver_rejects_invalid_username_before_network(monkeypatch):
    factory = AsyncMock()
    monkeypatch.setattr(github_ssh.httpx, "AsyncClient", factory)

    with pytest.raises(github_ssh.GitHubSshInvalid, match="형식"):
        await github_ssh.resolve_profile("-octocat")

    factory.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("keys", [[], [None], [{}], [{"key": ""}]])
async def test_resolver_requires_a_well_formed_public_key(monkeypatch, keys):
    _install_transport(monkeypatch, _github_handler(keys=keys))

    expected = github_ssh.GitHubSshInvalid if not keys else github_ssh.GitHubSshUnavailable
    with pytest.raises(expected):
        await github_ssh.resolve_profile(f"keycase{len(keys)}")


@pytest.mark.asyncio
async def test_resolver_rejects_non_user_profile(monkeypatch):
    _install_transport(monkeypatch, _github_handler(profile={**_PROFILE, "type": "Organization"}))

    with pytest.raises(github_ssh.GitHubSshInvalid, match="개인 GitHub 사용자"):
        await github_ssh.resolve_profile("octo-org")


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [500, 502])
async def test_resolver_maps_upstream_failures_to_unavailable(monkeypatch, status):
    _install_transport(monkeypatch, _github_handler(profile_status=status))

    with pytest.raises(github_ssh.GitHubSshUnavailable):
        await github_ssh.resolve_profile(f"upstream{status}")


@pytest.mark.asyncio
async def test_resolver_rejects_redirect(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(301, headers={"location": "https://example.invalid/user"}, request=request)

    _install_transport(monkeypatch, handler)

    with pytest.raises(github_ssh.GitHubSshUnavailable, match="리디렉션"):
        await github_ssh.resolve_profile("renamed-user")


@pytest.mark.asyncio
async def test_resolver_maps_timeout(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    _install_transport(monkeypatch, handler)

    with pytest.raises(github_ssh.GitHubSshUnavailable, match="초과"):
        await github_ssh.resolve_profile("slow-user")


@pytest.mark.asyncio
async def test_lookup_endpoint_persists_verified_profile(client, monkeypatch):
    _install_transport(monkeypatch, _github_handler())
    upsert = AsyncMock(return_value=_VERIFIED_AT)
    monkeypatch.setattr(github_ssh, "_upsert_history", upsert)

    response = await client.post("/api/v1/instances/github-users/lookup", json={"username": "octocat"})

    assert response.status_code == 200
    assert response.json() == {
        "id": 583231,
        "login": "OctoCat",
        "name": "The Octocat",
        "public_email": "octocat@example.com",
        "html_url": "https://github.com/OctoCat",
        "has_public_keys": True,
        "verified_at": _VERIFIED_AT,
    }
    upsert.assert_awaited_once()
    assert upsert.await_args.kwargs["user_id"] == "test-user-123"
    assert "avatar_url" not in response.json()


@pytest.mark.asyncio
async def test_lookup_endpoint_returns_422_for_invalid_username_without_calling_service(client):
    with patch("app.api.compute.instances.github_ssh.verify_and_record", new_callable=AsyncMock) as verify:
        response = await client.post("/api/v1/instances/github-users/lookup", json={"username": "-octocat"})

    assert response.status_code == 422
    verify.assert_not_awaited()


@pytest.mark.asyncio
async def test_lookup_endpoint_maps_malformed_provider_json_to_503(client, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/keys"):
            return httpx.Response(200, json=[None])
        return httpx.Response(200, json=_PROFILE)

    _install_transport(monkeypatch, handler)

    response = await client.post("/api/v1/instances/github-users/lookup", json={"username": "malformed-user"})

    assert response.status_code == 503
    assert response.json() == {"detail": "내부 서버 오류"}


@pytest.mark.asyncio
async def test_lookup_endpoint_maps_rate_limit_retry_after(client):
    error = github_ssh.GitHubSshRateLimited(17)
    with patch("app.api.compute.instances.github_ssh.verify_and_record", AsyncMock(side_effect=error)):
        response = await client.post("/api/v1/instances/github-users/lookup", json={"username": "octocat"})

    assert response.status_code == 429
    assert response.headers["retry-after"] == "17"


@pytest.mark.asyncio
async def test_lookup_endpoint_fails_when_history_cannot_be_saved(client):
    error = github_ssh.GitHubSshHistoryUnavailable("GitHub 사용자 기록을 저장하지 못했습니다.")
    with patch("app.api.compute.instances.github_ssh.verify_and_record", AsyncMock(side_effect=error)):
        response = await client.post("/api/v1/instances/github-users/lookup", json={"username": "octocat"})

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_history_endpoint_uses_authenticated_user_scope(client):
    history = [{"id": 583231, "login": "OctoCat", "verified_at": _VERIFIED_AT}]
    with patch("app.api.compute.instances.github_ssh.list_history", AsyncMock(return_value=history)) as list_history:
        response = await client.get("/api/v1/instances/github-users/history")

    assert response.status_code == 200
    assert response.json() == history
    list_history.assert_awaited_once_with(user_id="test-user-123")
