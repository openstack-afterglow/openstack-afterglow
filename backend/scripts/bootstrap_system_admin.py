#!/usr/bin/env python3
"""
system:all 부트스트랩 스크립트

최초 시스템 관리자 생성 또는 관리자 lockout 복구용.
config의 admin credential로 Keystone에 직접 접속하여 지정 사용자에게
system:all admin role을 부여한다.

사용법:
  cd /path/to/afterglow
  python backend/scripts/bootstrap_system_admin.py --username admin_user
  python backend/scripts/bootstrap_system_admin.py --user-id <UUID>
  python backend/scripts/bootstrap_system_admin.py --list   # 현재 system admin 목록 조회
"""

import argparse
import os
import sys
import textwrap

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _get_settings():
    """afterglow.conf + 환경변수에서 설정 로드."""
    from app.config import get_settings

    return get_settings()


def _build_admin_conn():
    """admin credential로 admin 프로젝트 scoped 연결."""
    import openstack

    s = _get_settings()
    return openstack.connect(
        load_envvars=False,
        load_yaml_config=False,
        auth_url=s.os_auth_url,
        auth_type="password",
        username=s.os_username,
        password=s.os_password,
        project_name=s.os_project_name,
        user_domain_name=s.os_user_domain_name,
        project_domain_name=s.os_project_domain_name,
        region_name=s.os_region_name,
        interface=s.os_interface,
        api_timeout=30,
        verify=s.ssl_verify,
    )


def _resolve_admin_role_id(conn) -> str:
    """'admin' role ID 조회."""
    s = _get_settings()
    role_name = getattr(s, "os_admin_role", "admin")
    roles = list(conn.identity.roles(name=role_name))
    if not roles:
        print(f"[ERROR] '{role_name}' role을 찾을 수 없습니다.", file=sys.stderr)
        sys.exit(1)
    return roles[0].id


def _resolve_user(conn, username: str | None, user_id: str | None) -> object:
    """username 또는 user_id로 사용자 객체 반환."""
    if user_id:
        user = conn.identity.get_user(user_id)
        if not user:
            print(f"[ERROR] user_id={user_id} 사용자를 찾을 수 없습니다.", file=sys.stderr)
            sys.exit(1)
        return user
    if username:
        users = list(conn.identity.users(name=username))
        if not users:
            print(f"[ERROR] username={username!r} 사용자를 찾을 수 없습니다.", file=sys.stderr)
            sys.exit(1)
        if len(users) > 1:
            print(f"[WARNING] username={username!r}에 해당하는 사용자가 {len(users)}명. 첫 번째 선택.")
        return users[0]
    print("[ERROR] --username 또는 --user-id 필요.", file=sys.stderr)
    sys.exit(1)


def cmd_grant(conn, username: str | None, user_id: str | None) -> None:
    """사용자에게 system:all admin role 부여."""
    role_id = _resolve_admin_role_id(conn)
    user = _resolve_user(conn, username, user_id)

    # 이미 있는지 확인
    existing = list(conn.identity.role_assignments(role_id=role_id, user_id=user.id, system="all"))
    if existing:
        print(f"[INFO] {user.name} (id={user.id}) 이미 system:all admin role 보유.")
        return

    conn.identity.assign_system_role_to_user(user.id, role_id)
    print(f"[OK] {user.name} (id={user.id}) → system:all admin role 부여 완료.")


def cmd_list(conn) -> None:
    """현재 system:all admin 목록 출력."""
    role_id = _resolve_admin_role_id(conn)
    assignments = list(conn.identity.role_assignments(role_id=role_id, system="all"))
    if not assignments:
        print("[INFO] system:all admin role 보유자 없음.")
        return
    print(f"system:all admin role 보유자 ({len(assignments)}명):")
    for a in assignments:
        uid = getattr(a, "user", {}).get("id", "?")
        try:
            u = conn.identity.get_user(uid)
            name = u.name if u else uid
        except Exception:
            name = uid
        print(f"  - {name} (id={uid})")


def main():
    parser = argparse.ArgumentParser(
        description=textwrap.dedent(__doc__ or ""),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--username", help="대상 사용자 이름")
    parser.add_argument("--user-id", dest="user_id", help="대상 사용자 ID (UUID)")
    parser.add_argument("--list", action="store_true", help="현재 system admin 목록 조회")
    args = parser.parse_args()

    conn = _build_admin_conn()

    if args.list:
        cmd_list(conn)
    elif args.username or args.user_id:
        cmd_grant(conn, args.username, args.user_id)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
