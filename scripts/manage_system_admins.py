#!/usr/bin/env python3
"""
Afterglow system admin 계정 관리 CLI.

사용법:
  python3 scripts/manage_system_admins.py list
  python3 scripts/manage_system_admins.py grant <user_id_or_name>
  python3 scripts/manage_system_admins.py revoke <user_id_or_name>

Keystone secure-RBAC 환경(첫 grant 부트스트랩):
  python3 scripts/manage_system_admins.py --os-system-scope all grant <user_id>

환경변수:
  OS_AUTH_URL, OS_USERNAME, OS_PASSWORD, OS_PROJECT_NAME,
  OS_USER_DOMAIN_NAME (default: Default), OS_PROJECT_DOMAIN_NAME (default: Default)

주의: 이 CLI는 백엔드 lockout 가드를 우회한다 (부트스트랩/복구 수단).
"""
from __future__ import annotations

import argparse
import os
import sys

from keystoneauth1 import session as ks_session
from keystoneauth1.identity import v3 as ks_identity
from keystoneclient.v3 import client as ks_client


def _get_keystone_client(system_scope: bool = False) -> ks_client.Client:
    auth_url = os.environ.get("OS_AUTH_URL")
    if not auth_url:
        print("ERROR: OS_AUTH_URL 환경변수를 설정하세요.", file=sys.stderr)
        sys.exit(1)

    username = os.environ.get("OS_USERNAME")
    password = os.environ.get("OS_PASSWORD")
    project_name = os.environ.get("OS_PROJECT_NAME")
    user_domain_name = os.environ.get("OS_USER_DOMAIN_NAME", "Default")
    project_domain_name = os.environ.get("OS_PROJECT_DOMAIN_NAME", "Default")

    if system_scope:
        auth = ks_identity.Password(
            auth_url=auth_url,
            username=username,
            password=password,
            user_domain_name=user_domain_name,
            system_scope="all",
        )
    else:
        auth = ks_identity.Password(
            auth_url=auth_url,
            username=username,
            password=password,
            user_domain_name=user_domain_name,
            project_name=project_name,
            project_domain_name=project_domain_name,
        )

    sess = ks_session.Session(auth=auth)
    return ks_client.Client(session=sess)


def _resolve_admin_role_id(ks: ks_client.Client) -> str:
    roles = ks.roles.list(name="admin")
    if not roles:
        print("ERROR: 'admin' role을 Keystone에서 찾을 수 없습니다.", file=sys.stderr)
        sys.exit(1)
    return roles[0].id


def _resolve_user(ks: ks_client.Client, user_ref: str):
    """user_id 또는 name으로 사용자 객체 반환."""
    try:
        return ks.users.get(user_ref)
    except Exception:
        pass
    users = ks.users.list(name=user_ref)
    if not users:
        print(f"ERROR: 사용자를 찾을 수 없습니다: {user_ref}", file=sys.stderr)
        sys.exit(1)
    if len(users) > 1:
        print(f"ERROR: 사용자 이름이 중복됩니다: {user_ref}. user_id를 직접 지정하세요.", file=sys.stderr)
        sys.exit(1)
    return users[0]


def cmd_list(args: argparse.Namespace) -> None:
    ks = _get_keystone_client(system_scope=args.os_system_scope)
    admin_role_id = _resolve_admin_role_id(ks)

    assignments = ks.role_assignments.list(role=admin_role_id, system="all")
    user_ids = [a.user["id"] for a in assignments if hasattr(a, "user")]

    if not user_ids:
        print("(system admin 없음)")
        return

    rows = []
    for uid in user_ids:
        try:
            u = ks.users.get(uid)
            rows.append((uid, getattr(u, "name", ""), getattr(u, "email", ""), getattr(u, "enabled", False)))
        except Exception:
            rows.append((uid, "", "", False))

    col_w = [36, 24, 36, 8]
    header = (
        f"{'USER ID':<{col_w[0]}}  {'NAME':<{col_w[1]}}  {'EMAIL':<{col_w[2]}}  {'ENABLED':<{col_w[3]}}"
    )
    sep = "-" * len(header)
    print(header)
    print(sep)
    for uid, name, email, enabled in rows:
        print(f"{uid:<{col_w[0]}}  {name:<{col_w[1]}}  {email:<{col_w[2]}}  {str(enabled):<{col_w[3]}}")


def cmd_grant(args: argparse.Namespace) -> None:
    ks = _get_keystone_client(system_scope=args.os_system_scope)
    admin_role_id = _resolve_admin_role_id(ks)
    user = _resolve_user(ks, args.user)
    ks.roles.grant(role=admin_role_id, user=user.id, system="all")
    print(f"OK: system admin 부여 완료 — {user.id} ({getattr(user, 'name', '')})")


def cmd_revoke(args: argparse.Namespace) -> None:
    ks = _get_keystone_client(system_scope=args.os_system_scope)
    admin_role_id = _resolve_admin_role_id(ks)
    user = _resolve_user(ks, args.user)
    ks.roles.revoke(role=admin_role_id, user=user.id, system="all")
    print(f"OK: system admin 회수 완료 — {user.id} ({getattr(user, 'name', '')})")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Afterglow system admin 계정 관리 CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--os-system-scope",
        action="store_true",
        default=False,
        help="Keystone system-scope 토큰으로 인증 (secure-RBAC 환경의 첫 grant 부트스트랩용)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="현재 system admin 목록 출력")

    grant_p = sub.add_parser("grant", help="사용자에게 system admin 부여")
    grant_p.add_argument("user", help="user_id 또는 username")

    revoke_p = sub.add_parser("revoke", help="사용자로부터 system admin 회수 (lockout 가드 없음)")
    revoke_p.add_argument("user", help="user_id 또는 username")

    args = parser.parse_args()

    if args.command == "list":
        cmd_list(args)
    elif args.command == "grant":
        cmd_grant(args)
    elif args.command == "revoke":
        cmd_revoke(args)


if __name__ == "__main__":
    main()
