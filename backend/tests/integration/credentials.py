"""통합 테스트 크리덴셜 로더.

우선순위: 환경변수 > credentials.toml > afterglow.conf [openstack]

사용법:
    from .credentials import admin_credentials, user_credentials
    creds = admin_credentials()   # 항상 반환
    user = user_credentials()     # 미설정 시 None → 테스트 skip

The returned native credentials retain project/domain settings for SDK callers
and explicit live-test workspace selection. HTTP password login must project
only username/password with conftest.password_login_payload.
"""

import os
import tomllib
from pathlib import Path


def _toml() -> dict:
    p = Path(__file__).parent / "credentials.toml"
    if p.exists():
        return tomllib.loads(p.read_text())
    return {}


def admin_credentials() -> dict:
    """admin 크리덴셜. 미설정 시 afterglow.conf [openstack] 값으로 폴백."""
    from app.config import get_settings

    t = _toml().get("admin", {})
    s = get_settings()
    return {
        "username": os.environ.get("AFTERGLOW_TEST_ADMIN_USERNAME") or t.get("username") or s.os_username,
        "password": os.environ.get("AFTERGLOW_TEST_ADMIN_PASSWORD") or t.get("password") or s.os_password,
        "project_name": os.environ.get("AFTERGLOW_TEST_ADMIN_PROJECT") or t.get("project_name") or s.os_project_name,
        "domain_name": os.environ.get("AFTERGLOW_TEST_ADMIN_DOMAIN") or t.get("domain_name") or s.os_user_domain_name,
    }


def admin_user_credentials() -> dict | None:
    """admin_user 크리덴셜 (admin 프로젝트 admin role 보유, default project ≠ admin 가능).

    [admin_user] 섹션 또는 AFTERGLOW_TEST_ADMIN_USER_* 환경변수 미설정 시 None → 테스트 skip.
    """
    t = _toml().get("admin_user", {})
    username = os.environ.get("AFTERGLOW_TEST_ADMIN_USER_USERNAME") or t.get("username")
    password = os.environ.get("AFTERGLOW_TEST_ADMIN_USER_PASSWORD") or t.get("password")
    if not username or not password:
        return None
    return {
        "username": username,
        "password": password,
        "project_name": os.environ.get("AFTERGLOW_TEST_ADMIN_USER_PROJECT") or t.get("project_name") or "",
        "domain_name": os.environ.get("AFTERGLOW_TEST_ADMIN_USER_DOMAIN") or t.get("domain_name") or "Default",
    }


def user_credentials() -> dict | None:
    """일반 유저 크리덴셜. username/password 미설정 시 None 반환 → 테스트 skip 트리거."""
    t = _toml().get("user", {})
    username = os.environ.get("AFTERGLOW_TEST_USER_USERNAME") or t.get("username")
    password = os.environ.get("AFTERGLOW_TEST_USER_PASSWORD") or t.get("password")
    if not username or not password:
        return None
    return {
        "username": username,
        "password": password,
        "project_name": os.environ.get("AFTERGLOW_TEST_USER_PROJECT") or t.get("project_name") or "",
        "domain_name": os.environ.get("AFTERGLOW_TEST_USER_DOMAIN") or t.get("domain_name") or "Default",
    }


def project_b_credentials() -> dict | None:
    """두 번째 프로젝트 크리덴셜 (격리 테스트용). 미설정 시 None → 테스트 skip."""
    t = _toml().get("project_b", {})
    username = os.environ.get("AFTERGLOW_TEST_PROJECT_B_USERNAME") or t.get("username")
    password = os.environ.get("AFTERGLOW_TEST_PROJECT_B_PASSWORD") or t.get("password")
    if not username or not password:
        return None
    return {
        "username": username,
        "password": password,
        "project_name": os.environ.get("AFTERGLOW_TEST_PROJECT_B_NAME") or t.get("project_name") or "",
        "domain_name": os.environ.get("AFTERGLOW_TEST_USER_DOMAIN") or t.get("domain_name") or "Default",
    }
