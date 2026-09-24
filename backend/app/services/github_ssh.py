"""Fail-closed GitHub public SSH lookup and user-scoped verified history."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from urllib.parse import quote, urlsplit

import httpx
from sqlalchemy import delete, select

from app.database import get_session_factory
from app.models.db import VmGithubSshUser
from app.services.cache import cached_call
from app.services.ssh_access import normalize_github_username

_API_ORIGIN = "https://api.github.com"
_CACHE_TTL_SECONDS = 600
_HISTORY_LIMIT = 20
_MAX_RESPONSE_BYTES = 262_144
_TIMEOUT = httpx.Timeout(5.0, connect=2.0)
_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "afterglow-github-ssh",
}


class GitHubSshUnavailable(RuntimeError):
    pass


class GitHubSshHistoryUnavailable(GitHubSshUnavailable):
    pass


class GitHubSshInvalid(ValueError):
    pass


class GitHubSshNotFound(GitHubSshInvalid):
    pass


class GitHubSshRateLimited(GitHubSshUnavailable):
    def __init__(self, retry_after: int | None) -> None:
        super().__init__("GitHub API 요청 한도에 도달했습니다. 잠시 후 다시 시도하세요.")
        self.retry_after = retry_after


def _normalize_username(username: str) -> str:
    try:
        normalized = normalize_github_username(username)
    except ValueError as exc:
        raise GitHubSshInvalid("GitHub 사용자 ID 형식이 유효하지 않습니다.") from exc
    if not normalized:
        raise GitHubSshInvalid("GitHub 사용자 ID 형식이 유효하지 않습니다.")
    return normalized


def _retry_after(headers: httpx.Headers) -> int | None:
    raw = headers.get("retry-after")
    if raw:
        try:
            return max(1, min(int(raw), 86_400))
        except ValueError:
            pass
    reset = headers.get("x-ratelimit-reset")
    if reset:
        try:
            return max(1, min(int(reset) - int(time.time()), 86_400))
        except ValueError:
            pass
    return None


async def _json_get(client: httpx.AsyncClient, path: str) -> object:
    try:
        async with client.stream("GET", path) as response:
            if response.is_redirect:
                raise GitHubSshUnavailable("GitHub 조회가 안전하지 않은 리디렉션을 반환했습니다.")
            if response.status_code in {403, 429}:
                raise GitHubSshRateLimited(_retry_after(response.headers))
            if response.status_code == 404:
                raise GitHubSshNotFound("GitHub 사용자를 찾을 수 없습니다.")
            if response.status_code >= 500:
                raise GitHubSshUnavailable("GitHub 공개키 조회를 사용할 수 없습니다.")
            if response.status_code >= 400:
                raise GitHubSshUnavailable("GitHub 공개키 조회를 사용할 수 없습니다.")
            content_length = response.headers.get("content-length")
            if content_length:
                try:
                    if int(content_length) > _MAX_RESPONSE_BYTES:
                        raise GitHubSshUnavailable("GitHub 응답이 유효하지 않습니다.")
                except ValueError as exc:
                    raise GitHubSshUnavailable("GitHub 응답이 유효하지 않습니다.") from exc
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > _MAX_RESPONSE_BYTES:
                    raise GitHubSshUnavailable("GitHub 응답이 유효하지 않습니다.")
    except GitHubSshInvalid:
        raise
    except GitHubSshUnavailable:
        raise
    except httpx.TimeoutException as exc:
        raise GitHubSshUnavailable("GitHub 공개키 조회 시간이 초과되었습니다.") from exc
    except httpx.HTTPError as exc:
        raise GitHubSshUnavailable("GitHub 공개키 조회를 사용할 수 없습니다.") from exc
    try:
        return json.loads(body)
    except (TypeError, ValueError) as exc:
        raise GitHubSshUnavailable("GitHub 응답이 유효하지 않습니다.") from exc


def _optional_public_text(payload: dict, key: str, *, max_length: int) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise GitHubSshUnavailable("GitHub 응답이 유효하지 않습니다.")
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > max_length or any(char in normalized for char in ("\r", "\n", "\x00")):
        raise GitHubSshUnavailable("GitHub 응답이 유효하지 않습니다.")
    return normalized


def _parse_profile(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise GitHubSshUnavailable("GitHub 응답이 유효하지 않습니다.")
    github_user_id = payload.get("id")
    if isinstance(github_user_id, bool) or not isinstance(github_user_id, int) or github_user_id <= 0:
        raise GitHubSshUnavailable("GitHub 응답이 유효하지 않습니다.")
    raw_login = payload.get("login")
    if not isinstance(raw_login, str):
        raise GitHubSshUnavailable("GitHub 응답이 유효하지 않습니다.")
    try:
        login = _normalize_username(raw_login)
    except GitHubSshInvalid as exc:
        raise GitHubSshUnavailable("GitHub 응답이 유효하지 않습니다.") from exc
    if payload.get("type") != "User":
        raise GitHubSshInvalid("개인 GitHub 사용자만 SSH 접근에 사용할 수 있습니다.")
    html_url = payload.get("html_url")
    if not isinstance(html_url, str):
        raise GitHubSshUnavailable("GitHub 응답이 유효하지 않습니다.")
    parsed = urlsplit(html_url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "github.com"
        or parsed.port is not None
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path.strip("/").lower() != login.lower()
    ):
        raise GitHubSshUnavailable("GitHub 응답이 유효하지 않습니다.")
    return {
        "id": github_user_id,
        "login": login,
        "name": _optional_public_text(payload, "name", max_length=255),
        "public_email": _optional_public_text(payload, "email", max_length=320),
        "html_url": html_url,
        "has_public_keys": True,
    }


def _validate_public_keys(payload: object) -> None:
    if not isinstance(payload, list):
        raise GitHubSshUnavailable("GitHub 응답이 유효하지 않습니다.")
    if not payload:
        raise GitHubSshInvalid("GitHub 계정에 공개 SSH 키가 없습니다.")
    record = payload[0]
    if not isinstance(record, dict):
        raise GitHubSshUnavailable("GitHub 응답이 유효하지 않습니다.")
    key = record.get("key")
    if not isinstance(key, str) or not key.strip() or any(char in key for char in ("\r", "\n", "\x00")):
        raise GitHubSshUnavailable("GitHub 응답이 유효하지 않습니다.")


async def _resolve_origin(username: str) -> dict[str, object]:
    encoded = quote(username, safe="")
    async with httpx.AsyncClient(
        base_url=_API_ORIGIN,
        timeout=_TIMEOUT,
        follow_redirects=False,
        trust_env=False,
        headers=_HEADERS,
    ) as client:
        profile = _parse_profile(await _json_get(client, f"/users/{encoded}"))
        _validate_public_keys(await _json_get(client, f"/users/{encoded}/keys?per_page=1"))
    return profile


async def resolve_profile(username: str) -> dict[str, object]:
    normalized = _normalize_username(username)

    async def load() -> dict[str, object]:
        return await _resolve_origin(normalized)

    return await cached_call(
        f"afterglow:github_ssh:{normalized.lower()}",
        _CACHE_TTL_SECONDS,
        load,
    )


def _isoformat(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


async def _upsert_history(*, user_id: str, profile: dict[str, object]) -> str:
    factory = get_session_factory()
    if factory is None:
        raise GitHubSshHistoryUnavailable("GitHub 사용자 기록 저장소를 사용할 수 없습니다.")
    verified_at = datetime.now(UTC)
    try:
        async with factory() as session, session.begin():
            row = await session.scalar(
                select(VmGithubSshUser).where(
                    VmGithubSshUser.user_id == user_id,
                    VmGithubSshUser.github_user_id == int(profile["id"]),
                )
            )
            if row is None:
                row = VmGithubSshUser(
                    user_id=user_id,
                    github_user_id=int(profile["id"]),
                    github_login=str(profile["login"]),
                    verified_at=verified_at,
                )
                session.add(row)
            else:
                row.github_login = str(profile["login"])
                row.verified_at = verified_at
            await session.flush()
            old_ids = list(
                (
                    await session.execute(
                        select(VmGithubSshUser.id)
                        .where(VmGithubSshUser.user_id == user_id)
                        .order_by(VmGithubSshUser.verified_at.desc(), VmGithubSshUser.id.desc())
                        .offset(_HISTORY_LIMIT)
                    )
                ).scalars()
            )
            if old_ids:
                await session.execute(delete(VmGithubSshUser).where(VmGithubSshUser.id.in_(old_ids)))
    except GitHubSshUnavailable:
        raise
    except Exception as exc:
        raise GitHubSshHistoryUnavailable("GitHub 사용자 기록을 저장하지 못했습니다.") from exc
    return _isoformat(verified_at)


async def verify_and_record(*, user_id: str, username: str) -> dict[str, object]:
    profile = await resolve_profile(username)
    verified_at = await _upsert_history(user_id=user_id, profile=profile)
    return {**profile, "verified_at": verified_at}


async def list_history(*, user_id: str) -> list[dict[str, object]]:
    factory = get_session_factory()
    if factory is None:
        raise GitHubSshHistoryUnavailable("GitHub 사용자 기록 저장소를 사용할 수 없습니다.")
    try:
        async with factory() as session:
            rows = list(
                (
                    await session.execute(
                        select(VmGithubSshUser)
                        .where(VmGithubSshUser.user_id == user_id)
                        .order_by(VmGithubSshUser.verified_at.desc(), VmGithubSshUser.id.desc())
                        .limit(_HISTORY_LIMIT)
                    )
                ).scalars()
            )
    except Exception as exc:
        raise GitHubSshHistoryUnavailable("GitHub 사용자 기록을 불러오지 못했습니다.") from exc
    return [
        {"id": row.github_user_id, "login": row.github_login, "verified_at": _isoformat(row.verified_at)}
        for row in rows
    ]
