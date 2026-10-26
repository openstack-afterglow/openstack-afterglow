"""JWT access + refresh 토큰 유틸리티.

access  : HS256, TTL=jwt_access_ttl (기본 15분), payload에 사용자·프로젝트 정보 포함
refresh : HS256, TTL=jwt_refresh_ttl (기본 7일), type="refresh" 구분자 포함

비밀키는 Settings.secret_key 재사용. 별도 키 회전이 필요해지면 jwt_secret 필드를 추가할 것.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import jwt

from app.config import get_settings


def _secret() -> str:
    return get_settings().secret_key


def sign_access(
    user_id: str,
    username: str,
    project_id: str,
    project_name: str,
    refresh_jti: str,
    *,
    expires_at: int | None = None,
) -> tuple[str, str, int]:
    """Access JWT 발급.

    권한 정보(roles, is_system_admin)는 payload에 포함하지 않는다.
    매 요청 Keystone live 검증으로 결정하며 요청 간 권한 proof를 재사용하지 않는다.

    expires_at bounds issuance by the original browser/native session deadline;
    it never extends the configured access lifetime.
    Returns:
        (token_str, access_jti, exp_unix_timestamp)
    """
    settings = get_settings()
    now = int(datetime.now(UTC).timestamp())
    exp = min(now + settings.jwt_access_ttl, expires_at) if expires_at is not None else now + settings.jwt_access_ttl
    jti = str(uuid.uuid4())
    payload: dict[str, Any] = {
        "sub": user_id,
        "jti": jti,
        "rjti": refresh_jti,
        "iat": now,
        "exp": exp,
        "username": username,
        "project_id": project_id,
        "project_name": project_name,
    }
    token = jwt.encode(payload, _secret(), algorithm="HS256")
    return token, jti, exp


def verify_access(token: str) -> dict:
    """Access JWT 서명·만료 검증 후 payload 반환.

    Raises:
        jwt.ExpiredSignatureError: 만료된 토큰
        jwt.InvalidTokenError: 서명 오류 등 기타 JWT 오류
    """
    return jwt.decode(token, _secret(), algorithms=["HS256"])


def sign_refresh(user_id: str, *, expires_at: int | None = None) -> tuple[str, str, int]:
    """Refresh JWT 발급.

    expires_at keeps rotation inside the original browser/native session window.

    Returns:
        (token_str, refresh_jti, exp_unix_timestamp)
    """
    settings = get_settings()
    now = int(datetime.now(UTC).timestamp())
    exp = min(now + settings.jwt_refresh_ttl, expires_at) if expires_at is not None else now + settings.jwt_refresh_ttl
    jti = str(uuid.uuid4())
    payload: dict[str, Any] = {
        "sub": user_id,
        "jti": jti,
        "iat": now,
        "exp": exp,
        "type": "refresh",
    }
    token = jwt.encode(payload, _secret(), algorithm="HS256")
    return token, jti, exp


def verify_refresh(token: str) -> dict:
    """Refresh JWT 서명·만료 검증 후 payload 반환.

    Raises:
        jwt.ExpiredSignatureError: 만료된 토큰
        jwt.InvalidTokenError: 서명 오류 또는 type != refresh
    """
    payload = jwt.decode(token, _secret(), algorithms=["HS256"])
    if payload.get("type") != "refresh":
        raise jwt.InvalidTokenError("type field is not 'refresh'")
    return payload
