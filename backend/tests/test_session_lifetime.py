"""Original-login browser deadlines, operator limits and native expiry caps."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import jwt
import pytest
from fastapi import HTTPException

from app import config
from app.api.identity import auth
from app.services import jwt_service

SEVEN_DAYS = 604800
NOW = 2_000_000_000


class FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls.fromtimestamp(NOW, tz=tz)


def _settings(**overrides):
    return config.Settings(
        _env_file=None,
        secret_key="session-lifetime-test-secret-key-32-characters",
        jwt_access_ttl=3600,
        jwt_refresh_ttl=SEVEN_DAYS,
        session_timeout_seconds=overrides.pop("session_timeout_seconds", SEVEN_DAYS),
        **overrides,
    )


def test_session_defaults_are_one_hour_and_seven_days(monkeypatch):
    for key in ("JWT_ACCESS_TTL", "JWT_REFRESH_TTL", "SESSION_TIMEOUT_SECONDS"):
        monkeypatch.delenv(key, raising=False)
    settings = config.Settings(_env_file=None, secret_key="session-lifetime-test-secret-key-32-characters")
    assert settings.jwt_access_ttl == 3600
    assert settings.jwt_refresh_ttl == settings.session_timeout_seconds == SEVEN_DAYS
    monkeypatch.setattr(config, "load_raw_toml", lambda: {"session": {}})
    flattened = config._load_toml()
    assert flattened["jwt_access_ttl"] == 3600
    assert flattened["jwt_refresh_ttl"] == flattened["session_timeout_seconds"] == SEVEN_DAYS


@pytest.mark.parametrize(
    "configured,expected",
    [(3600, 3600), (86400, 86400), (SEVEN_DAYS, SEVEN_DAYS), (SEVEN_DAYS * 2, SEVEN_DAYS)],
)
def test_absolute_lifetime_preserves_shorter_operator_policy(configured, expected):
    assert _settings(session_timeout_seconds=configured).session_timeout_seconds == expected


@pytest.fixture
def frozen_issuer(monkeypatch):
    settings = _settings()
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    monkeypatch.setattr(jwt_service, "get_settings", lambda: settings)
    monkeypatch.setattr(auth, "datetime", FrozenDatetime)
    monkeypatch.setattr(jwt_service, "datetime", FrozenDatetime)
    monkeypatch.setattr(
        auth, "_domain_metadata", AsyncMock(return_value={"available_domains": [], "can_create_domain": False})
    )
    monkeypatch.setattr(auth, "visible_role_names", AsyncMock(return_value=["member"]))
    store = AsyncMock(return_value=True)
    monkeypatch.setattr(auth.session_store, "store_session", store)
    return settings, store


async def _issue(**overrides):
    return await auth._build_token_response(
        keystone_token="synthetic-native-root",
        project_id="project-1",
        project_name="Project",
        user_id="user-1",
        username="alice",
        roles=["member"],
        is_system_admin=False,
        domain_id="domain-1",
        domain_name="Domain",
        is_domain_manager=False,
        identity_domain_id="accounts",
        identity_domain_name="Accounts",
        **overrides,
    )


def _claims(token):
    return jwt.decode(token, options={"verify_signature": False, "verify_exp": False})


@pytest.mark.asyncio
async def test_initial_tokens_use_one_hour_access_and_seven_day_refresh(frozen_issuer):
    result = await _issue(native_expires_at=datetime.fromtimestamp(NOW + SEVEN_DAYS, UTC).isoformat())
    assert _claims(result.token)["exp"] == NOW + 3600
    assert _claims(result.refresh_token)["exp"] == NOW + SEVEN_DAYS


@pytest.mark.asyncio
@pytest.mark.parametrize("previous_jti", [None, "previous-refresh"])
async def test_rotation_and_scope_publication_keep_original_login_deadline(frozen_issuer, previous_jti):
    started_at = NOW - SEVEN_DAYS + 90
    result = await _issue(
        started_at=started_at,
        previous_jti=previous_jti,
        native_expires_at=datetime.fromtimestamp(NOW + SEVEN_DAYS, UTC).isoformat(),
    )
    assert _claims(result.token)["exp"] == NOW + 90
    assert _claims(result.refresh_token)["exp"] == NOW + 90
    store = frozen_issuer[1]
    assert store.await_args.kwargs["started_at"] == started_at
    assert store.await_args.kwargs["previous_jti"] == previous_jti


@pytest.mark.asyncio
async def test_rotation_cannot_extend_previous_refresh_deadline(frozen_issuer):
    result = await _issue(
        started_at=NOW - 60,
        previous_jti="previous-refresh",
        previous_refresh_exp=NOW + 45,
        native_expires_at=datetime.fromtimestamp(NOW + SEVEN_DAYS, UTC).isoformat(),
    )
    assert _claims(result.token)["exp"] == _claims(result.refresh_token)["exp"] == NOW + 45


@pytest.mark.asyncio
async def test_native_expiry_caps_both_tokens(frozen_issuer):
    result = await _issue(native_expires_at=datetime.fromtimestamp(NOW + 30, UTC).isoformat())
    assert _claims(result.token)["exp"] == _claims(result.refresh_token)["exp"] == NOW + 30


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"started_at": NOW - SEVEN_DAYS},
        {"previous_refresh_exp": NOW},
        {"native_expires_at": datetime.fromtimestamp(NOW, UTC).isoformat()},
    ],
)
async def test_exact_deadline_rejects_publication_without_writing_session(frozen_issuer, overrides):
    with pytest.raises(HTTPException) as exc:
        await _issue(**overrides)
    assert exc.value.status_code == 401
    frozen_issuer[1].assert_not_awaited()


@pytest.mark.asyncio
async def test_shorter_operator_timeout_caps_both_tokens(frozen_issuer):
    frozen_issuer[0].session_timeout_seconds = 120
    result = await _issue(started_at=NOW - 30)
    assert _claims(result.token)["exp"] == _claims(result.refresh_token)["exp"] == NOW + 90
