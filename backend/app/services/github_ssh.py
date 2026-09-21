"""Fail-closed GitHub public-key lookup for VM SSH import."""

from __future__ import annotations

import httpx

from app.services.ssh_access import normalize_github_username


class GitHubSshUnavailable(RuntimeError):
    pass


class GitHubSshInvalid(ValueError):
    pass


async def resolve_profile(username: str) -> dict[str, str | int | None]:
    try:
        login = normalize_github_username(username)
    except ValueError as exc:
        raise GitHubSshInvalid("GitHub 사용자 ID 형식이 유효하지 않습니다.") from exc
    if not login:
        raise GitHubSshInvalid("GitHub 사용자 ID 형식이 유효하지 않습니다.")
    try:
        async with httpx.AsyncClient(
            timeout=5.0,
            follow_redirects=False,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "afterglow"},
        ) as client:
            user = await client.get(f"https://api.github.com/users/{login}")
            keys = await client.get(f"https://api.github.com/users/{login}/keys?per_page=100")
    except httpx.HTTPError as exc:
        raise GitHubSshUnavailable("GitHub 공개키 조회를 사용할 수 없습니다.") from exc
    if user.is_redirect or keys.is_redirect or user.status_code >= 500 or keys.status_code >= 500:
        raise GitHubSshUnavailable("GitHub 공개키 조회를 사용할 수 없습니다.")
    if user.status_code == 404 or keys.status_code == 404:
        raise GitHubSshInvalid("GitHub 사용자를 찾을 수 없습니다.")
    if user.status_code >= 400 or keys.status_code >= 400:
        raise GitHubSshUnavailable("GitHub 공개키 조회를 사용할 수 없습니다.")
    try:
        payload = user.json()
        key_payload = keys.json()
    except ValueError as exc:
        raise GitHubSshUnavailable("GitHub 응답이 유효하지 않습니다.") from exc
    if not isinstance(payload, dict) or not isinstance(key_payload, list):
        raise GitHubSshUnavailable("GitHub 응답이 유효하지 않습니다.")
    try:
        canonical = normalize_github_username(str(payload.get("login") or ""))
    except ValueError as exc:
        raise GitHubSshUnavailable("GitHub 응답이 유효하지 않습니다.") from exc
    if not canonical or not key_payload:
        raise GitHubSshInvalid("GitHub 사용자에게 공개 SSH 키가 없습니다.")
    return {
        "login": canonical,
        "name": str(payload["name"]) if payload.get("name") else None,
        "avatar_url": str(payload["avatar_url"]) if payload.get("avatar_url") else None,
        "public_key_count": len(key_payload),
    }
