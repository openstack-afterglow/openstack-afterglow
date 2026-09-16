"""production + AFTERGLOW_ALLOW_INSECURE 결합 부팅 차단 검증.

`warn_insecure_defaults` model_validator 가 다음을 보장:
1) AFTERGLOW_ENV=production + AFTERGLOW_ALLOW_INSECURE=1 → 즉시 ValueError
2) AFTERGLOW_ENV=production + secret_key=default → ValueError
3) dev 환경 + INSECURE=1 + secret_key=default → 경고만 (부팅 허용)
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest


def _build_settings_with_env(env: dict[str, str]):
    """환경과 `.env`의 설정 누수를 차단한 Settings 인스턴스를 생성한다."""
    from app.config import Settings

    # env 안의 None 은 변수 삭제 의미
    target_env = {k: v for k, v in env.items() if v is not None}
    clear_env = [k for k, v in env.items() if v is None]
    with patch.dict(os.environ, target_env, clear=True):
        # 명시적 None 삭제
        for k in clear_env:
            os.environ.pop(k, None)
        return Settings(_env_file=None)


def test_production_with_insecure_flag_fails_fast():
    """AFTERGLOW_ENV=production + AFTERGLOW_ALLOW_INSECURE=1 → ValueError."""
    with pytest.raises(ValueError, match="AFTERGLOW_ALLOW_INSECURE=1 must NOT be set"):
        _build_settings_with_env(
            {
                "AFTERGLOW_ENV": "production",
                "AFTERGLOW_ALLOW_INSECURE": "1",
                # secret_key 는 default 든 아니든 INSECURE 자체로 거부
                "SECRET_KEY": "real-strong-key-1234567890",
            }
        )


def test_production_with_default_secret_fails_fast():
    """AFTERGLOW_ENV=production + secret_key=default → ValueError."""
    with pytest.raises(ValueError, match="while AFTERGLOW_ENV=production"):
        _build_settings_with_env(
            {
                "AFTERGLOW_ENV": "production",
                "AFTERGLOW_ALLOW_INSECURE": "",
                "SECRET_KEY": "change-me-in-production",
            }
        )


def test_development_with_insecure_flag_succeeds():
    """dev 환경에서는 INSECURE=1 + default secret 가 경고만 — 부팅 허용."""
    settings = _build_settings_with_env(
        {
            "AFTERGLOW_ENV": "development",
            "AFTERGLOW_ALLOW_INSECURE": "1",
            "SECRET_KEY": "change-me-in-production",
        }
    )
    assert settings.secret_key == "change-me-in-production"


def test_development_without_insecure_or_real_key_fails():
    """dev 환경이라도 INSECURE 미설정 + default secret 이면 거부."""
    with pytest.raises(ValueError, match="default value"):
        _build_settings_with_env(
            {
                "AFTERGLOW_ENV": "development",
                "AFTERGLOW_ALLOW_INSECURE": "",
                "SECRET_KEY": "change-me-in-production",
            }
        )


def test_production_with_short_nondefault_key_fails_fast():
    """production + 비기본이지만 32자 미만 약한 키 → ValueError (엔트로피 게이트)."""
    with pytest.raises(ValueError, match="too short"):
        _build_settings_with_env(
            {
                "AFTERGLOW_ENV": "production",
                "AFTERGLOW_ALLOW_INSECURE": "",
                "SECRET_KEY": "short-but-not-default",  # 21 chars < 32
            }
        )


def test_production_with_strong_key_succeeds():
    """production + 32자 이상 강한 키 → 부팅 허용."""
    strong = "a" * 64  # e.g. openssl rand -hex 32
    settings = _build_settings_with_env(
        {
            "AFTERGLOW_ENV": "production",
            "AFTERGLOW_ALLOW_INSECURE": "",
            "SECRET_KEY": strong,
        }
    )
    assert settings.secret_key == strong


def test_development_with_short_nondefault_key_succeeds():
    """dev 환경에서는 짧은 비기본 키가 경고만 — 부팅 허용 (워크플로 비파괴)."""
    settings = _build_settings_with_env(
        {
            "AFTERGLOW_ENV": "development",
            "AFTERGLOW_ALLOW_INSECURE": "",
            "SECRET_KEY": "dev-short-key",
        }
    )
    assert settings.secret_key == "dev-short-key"


def test_production_with_docker_worker_runtime_fails_fast():
    """production + worker_runtime.mode=docker → ValueError.

    docker 모드는 호스트 Docker 소켓(root 등가) 마운트가 필요하므로 멀티테넌트 프로덕션
    부팅을 fail-closed 로 거부한다. 강한 키를 줘 docker 가드만 격리 검증한다.
    """
    with pytest.raises(ValueError, match="worker_runtime.mode='docker'"):
        _build_settings_with_env(
            {
                "AFTERGLOW_ENV": "production",
                "AFTERGLOW_ALLOW_INSECURE": "",
                "SECRET_KEY": "a" * 64,
                "WORKER_RUNTIME_MODE": "docker",
            }
        )


def test_production_with_kubernetes_worker_runtime_succeeds():
    """production + worker_runtime.mode=kubernetes → 부팅 허용 (docker 가드 오탐 없음)."""
    settings = _build_settings_with_env(
        {
            "AFTERGLOW_ENV": "production",
            "AFTERGLOW_ALLOW_INSECURE": "",
            "SECRET_KEY": "a" * 64,
            "WORKER_RUNTIME_MODE": "kubernetes",
        }
    )
    assert settings.worker_runtime_mode == "kubernetes"


def test_development_with_docker_worker_runtime_succeeds():
    """dev 환경에서는 docker 모드가 허용된다(단일 신뢰 호스트 개발 경로)."""
    settings = _build_settings_with_env(
        {
            "AFTERGLOW_ENV": "development",
            "AFTERGLOW_ALLOW_INSECURE": "1",
            "SECRET_KEY": "a" * 64,
            "WORKER_RUNTIME_MODE": "docker",
        }
    )
    assert settings.worker_runtime_mode == "docker"


def test_development_service_internal_override_is_normalized():
    settings = _build_settings_with_env(
        {
            "AFTERGLOW_ENV": "development",
            "AFTERGLOW_ALLOW_INSECURE": "",
            "SECRET_KEY": "a" * 64,
            "SERVICE_LUMEN_INTERNAL_URL": "http://lumen-api:8012/",
        }
    )

    assert settings.service_lumen_internal_url == "http://lumen-api:8012"


def test_production_service_internal_override_requires_https():
    with pytest.raises(ValueError, match="services.lumen_internal_url requires an absolute HTTPS"):
        _build_settings_with_env(
            {
                "AFTERGLOW_ENV": "production",
                "AFTERGLOW_ALLOW_INSECURE": "",
                "SECRET_KEY": "a" * 64,
                "SERVICE_LUMEN_INTERNAL_URL": "http://lumen.internal:8012",
            }
        )


def test_production_empty_service_internal_override_retains_catalog_lookup():
    settings = _build_settings_with_env(
        {
            "AFTERGLOW_ENV": "production",
            "AFTERGLOW_ALLOW_INSECURE": "",
            "SECRET_KEY": "a" * 64,
            "SERVICE_WAYGATE_INTERNAL_URL": "",
            "SERVICE_DROVER_INTERNAL_URL": "",
            "SERVICE_LUMEN_INTERNAL_URL": "",
            "SERVICE_PALIMPSEST_INTERNAL_URL": "",
        }
    )

    assert settings.service_waygate_internal_url == ""
    assert settings.service_drover_internal_url == ""
    assert settings.service_lumen_internal_url == ""
    assert settings.service_palimpsest_internal_url == ""


def test_production_valid_https_service_internal_override_succeeds():
    settings = _build_settings_with_env(
        {
            "AFTERGLOW_ENV": "production",
            "AFTERGLOW_ALLOW_INSECURE": "",
            "SECRET_KEY": "a" * 64,
            "SERVICE_LUMEN_INTERNAL_URL": "https://lumen-internal.example.com:8012",
        }
    )

    assert settings.service_lumen_internal_url == "https://lumen-internal.example.com:8012"


def test_production_mcp_requires_absolute_https_public_api_base():
    with pytest.raises(ValueError, match="services.mcp requires an absolute HTTPS"):
        _build_settings_with_env(
            {
                "AFTERGLOW_ENV": "production",
                "AFTERGLOW_ALLOW_INSECURE": "",
                "SECRET_KEY": "a" * 64,
                "SERVICE_MCP_ENABLED": "true",
                "PUBLIC_API_BASE": "http://api.example.test",
            }
        )


def test_development_mcp_allows_absolute_http_public_api_base():
    settings = _build_settings_with_env(
        {
            "AFTERGLOW_ENV": "development",
            "AFTERGLOW_ALLOW_INSECURE": "",
            "SECRET_KEY": "a" * 64,
            "SERVICE_MCP_ENABLED": "true",
            "PUBLIC_API_BASE": "http://127.0.0.1:8000",
            "FRONTEND_BASE_URL": "http://127.0.0.1:5173",
        }
    )
    assert settings.service_mcp_enabled is True
