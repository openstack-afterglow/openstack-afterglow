"""임시 Builder VM에 Manila share(NFS/CephFS)를 마운트하고 검증하는 서비스."""

from __future__ import annotations

import asyncio
import base64
import logging
import shlex

from app.services import manila
from app.services.builder_vm import EphemeralBuilderVM
from app.services.ssh_executor import run_command

_logger = logging.getLogger(__name__)

MOUNT_POINT = "/mnt/lib-output"


async def add_vm_access_rule(
    svc_conn,
    share_id: str,
    vm_internal_ip: str,
    share_proto: str,
    cephx_user: str | None = None,
) -> dict:
    """VM이 share에 RW 접근할 수 있도록 access rule을 추가하고 rule 정보를 반환한다.

    NFS:   access_type="ip",    access_to=<VM internal IP>
    CephFS: access_type="cephx", access_to=<cephx_user>
    반환: create_access_rule과 동일 { access_id, access_key, access_to, access_level }
    """
    proto_upper = share_proto.upper()

    if proto_upper == "NFS":
        # root_squash 해제 — 빌드 VM은 root로 파일 시스템 조작 필요
        rule = await asyncio.to_thread(
            manila.create_access_rule,
            svc_conn,
            share_id,
            vm_internal_ip,
            "rw",
            "ip",
            {"auth_flavor_list": ["sys"]},
        )
        _logger.info("[ephemeral_mount] NFS access rule 추가: ip=%s, share=%s", vm_internal_ip, share_id)
    else:
        user = cephx_user or f"builder-{share_id[:8]}"
        rule = await asyncio.to_thread(
            manila.create_access_rule,
            svc_conn,
            share_id,
            user,
            "rw",
            "cephx",
        )
        _logger.info("[ephemeral_mount] CephX access rule 추가: user=%s, share=%s", user, share_id)

    return rule


async def build_mount_command(
    svc_conn,
    share_id: str,
    share_proto: str,
    access_rule: dict,
    mount_point: str = MOUNT_POINT,
) -> str:
    """SSH에서 실행할 마운트 스크립트(문자열)를 생성한다.

    export_location을 Manila API에서 조회해 프로토콜별 mount 명령을 구성한다.
    """
    proto_upper = share_proto.upper()
    export_locations = await asyncio.to_thread(manila.get_export_locations, svc_conn, share_id)
    if not export_locations:
        raise RuntimeError(f"Share {share_id}의 export location이 없습니다")

    export_path = export_locations[0]

    # 쉘 보간 값은 출처(Manila API)와 무관하게 전부 shlex.quote — 심층 방어
    q_mount_point = shlex.quote(mount_point)

    if proto_upper == "NFS":
        return (
            f"sudo mkdir -p {q_mount_point}\n"
            f"sudo mount -t nfs {shlex.quote(export_path)} {q_mount_point} -o rw,hard,intr\n"
        )
    else:
        # CephFS export 형식: "mon1,mon2,mon3:/subpath"
        if ":" in export_path:
            ceph_mons, ceph_path = export_path.rsplit(":", 1)
        else:
            ceph_mons, ceph_path = export_path, "/"

        cephx_user = access_rule.get("access_to", "")
        cephx_secret = access_rule.get("access_key", "")
        secret_b64 = base64.b64encode(cephx_secret.encode()).decode()

        return (
            f"sudo mkdir -p {q_mount_point}\n"
            "SECRET_FILE=$(mktemp /tmp/ceph.XXXXXX)\n"
            f"printf '%s' {shlex.quote(secret_b64)} | base64 -d > \"$SECRET_FILE\"\n"
            'sudo chmod 600 "$SECRET_FILE"\n'
            f"sudo mount -t ceph {shlex.quote(f'{ceph_mons}:{ceph_path}')} {q_mount_point} "
            f'-o name={shlex.quote(cephx_user)},secretfile="$SECRET_FILE"\n'
            'rm -f "$SECRET_FILE"\n'
        )


async def verify_mount_via_ssh(
    vm: EphemeralBuilderVM,
    mount_command: str,
    mount_point: str = MOUNT_POINT,
) -> dict:
    """SSH로 share를 마운트하고 mountpoint·df로 검증한 뒤 umount한다.

    Returns:
        {
          "mounted": bool,
          "df_output": str,      # df -h 출력 (마운트 성공 시)
          "error": str | None,   # 실패 시 오류 메시지
        }
    """
    # 마운트 실행
    rc, _, stderr = await run_command(
        vm.host,
        vm.key_path,
        f"set -e\n{mount_command}",
        username=vm.username,
        timeout=60,
    )
    if rc != 0:
        return {
            "mounted": False,
            "df_output": "",
            "error": f"mount 실패 (exit={rc}): {stderr.strip()}",
        }

    # 검증: mountpoint + df
    verify_cmd = f"mountpoint -q {mount_point} && df -h {mount_point} && echo MOUNT_OK"
    rc2, stdout2, stderr2 = await run_command(
        vm.host,
        vm.key_path,
        verify_cmd,
        username=vm.username,
        timeout=30,
    )
    mounted = rc2 == 0 and "MOUNT_OK" in stdout2

    # umount (best-effort, 실패해도 무시)
    await run_command(
        vm.host,
        vm.key_path,
        f"sudo umount {mount_point} 2>/dev/null || true",
        username=vm.username,
        timeout=30,
    )

    return {
        "mounted": mounted,
        "df_output": stdout2.strip(),
        "error": stderr2.strip() if not mounted else None,
    }
