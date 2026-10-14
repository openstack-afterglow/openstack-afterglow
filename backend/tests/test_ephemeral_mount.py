"""임시 Builder VM Manila 마운트 서비스 및 smoke-mount 엔드포인트 단위 테스트."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------


def _make_settings(**kwargs) -> MagicMock:
    s = MagicMock()
    s.os_manila_nfs_share_type = kwargs.get("os_manila_nfs_share_type", "nfstype")
    s.os_manila_share_type = kwargs.get("os_manila_share_type", "cephfstype")
    s.os_manila_share_network_id = kwargs.get("os_manila_share_network_id", "net-manila")
    return s


def _make_vm(
    server_id: str = "srv-xyz",
    host: str = "5.5.5.5",
    internal_ip: str = "10.0.0.7",
) -> MagicMock:
    from app.services.builder_vm import EphemeralBuilderVM

    return EphemeralBuilderVM(
        server_id=server_id,
        host=host,
        username="ubuntu",
        key_path="/tmp/k.key",
        internal_ip=internal_ip,
        keypair_name="builder-keypair",
        fip_id="fip-xyz",
    )


# ---------------------------------------------------------------------------
# add_vm_access_rule
# ---------------------------------------------------------------------------


class TestAddVmAccessRule:
    @pytest.mark.asyncio
    async def test_nfs_creates_ip_access_rule(self):
        """NFS는 access_type='ip', access_to=VM IP로 rule을 생성한다."""
        svc_conn = MagicMock()
        mock_rule = {"access_id": "rule-nfs-1", "access_key": "", "access_to": "10.0.0.7", "access_level": "rw"}

        with patch(
            "app.services.ephemeral_mount.manila.create_access_rule",
            return_value=mock_rule,
        ) as mock_create:
            from app.services.ephemeral_mount import add_vm_access_rule

            result = await add_vm_access_rule(svc_conn, "share-abc", "10.0.0.7", "NFS")

        assert result["access_id"] == "rule-nfs-1"
        _, pos_args, kw = mock_create.mock_calls[0]
        # positional: conn, share_id, access_to, access_level, access_type
        assert pos_args[2] == "10.0.0.7"  # access_to = VM IP
        assert pos_args[3] == "rw"
        assert pos_args[4] == "ip"

    @pytest.mark.asyncio
    async def test_cephfs_creates_cephx_access_rule(self):
        """CephFS는 access_type='cephx', access_to=cephx_user로 rule을 생성한다."""
        svc_conn = MagicMock()
        mock_rule = {
            "access_id": "rule-ceph-1",
            "access_key": "AQBsecret==",
            "access_to": "builder-shareabc",
            "access_level": "rw",
        }

        with patch(
            "app.services.ephemeral_mount.manila.create_access_rule",
            return_value=mock_rule,
        ) as mock_create:
            from app.services.ephemeral_mount import add_vm_access_rule

            result = await add_vm_access_rule(svc_conn, "shareabc1234", "10.0.0.7", "CEPHFS", cephx_user="my-builder")

        assert result["access_id"] == "rule-ceph-1"
        assert result["access_key"] == "AQBsecret=="
        _, pos_args, _ = mock_create.mock_calls[0]
        assert pos_args[2] == "my-builder"  # 지정한 cephx_user
        assert pos_args[4] == "cephx"

    @pytest.mark.asyncio
    async def test_cephfs_generates_default_cephx_user(self):
        """cephx_user 미지정 시 share_id 앞 8자로 자동 생성한다."""
        svc_conn = MagicMock()
        mock_rule = {
            "access_id": "rule-auto",
            "access_key": "AQsecret==",
            "access_to": "builder-share123",
            "access_level": "rw",
        }

        with patch(
            "app.services.ephemeral_mount.manila.create_access_rule",
            return_value=mock_rule,
        ) as mock_create:
            from app.services.ephemeral_mount import add_vm_access_rule

            await add_vm_access_rule(svc_conn, "share1234abcd", "10.0.0.7", "CEPHFS")

        _, pos_args, _ = mock_create.mock_calls[0]
        assert pos_args[2] == "builder-share123"  # share_id[:8] = "share123"


# ---------------------------------------------------------------------------
# build_mount_command
# ---------------------------------------------------------------------------


class TestBuildMountCommand:
    @pytest.mark.asyncio
    async def test_nfs_command_contains_export_path(self):
        """NFS 마운트 명령에 export_location이 포함된다."""
        svc_conn = MagicMock()

        with patch(
            "app.services.ephemeral_mount.manila.get_export_locations",
            return_value=["10.10.10.5:/shares/share-abc"],
        ):
            from app.services.ephemeral_mount import build_mount_command

            cmd = await build_mount_command(svc_conn, "share-abc", "NFS", {})

        assert "mount -t nfs" in cmd
        assert "10.10.10.5:/shares/share-abc" in cmd
        assert "/mnt/lib-output" in cmd
        assert "sudo" in cmd

    @pytest.mark.asyncio
    async def test_cephfs_command_contains_user_and_secret(self):
        """CephFS 마운트 명령에 cephx user와 base64 secret이 포함된다."""
        svc_conn = MagicMock()
        access_rule = {"access_to": "builder-x", "access_key": "mysecret"}

        with patch(
            "app.services.ephemeral_mount.manila.get_export_locations",
            return_value=["10.10.10.1,10.10.10.2:/volumes/vol1"],
        ):
            from app.services.ephemeral_mount import build_mount_command

            cmd = await build_mount_command(svc_conn, "share-abc", "CEPHFS", access_rule)

        assert "mount -t ceph" in cmd
        assert "builder-x" in cmd
        assert "secretfile" in cmd
        import base64

        assert base64.b64encode(b"mysecret").decode() in cmd

    @pytest.mark.asyncio
    async def test_raises_when_no_export_locations(self):
        """export_location이 없으면 RuntimeError."""
        svc_conn = MagicMock()

        with patch(
            "app.services.ephemeral_mount.manila.get_export_locations",
            return_value=[],
        ):
            from app.services.ephemeral_mount import build_mount_command

            with pytest.raises(RuntimeError, match="export location"):
                await build_mount_command(svc_conn, "share-abc", "NFS", {})


# ---------------------------------------------------------------------------
# build_mount_command — 쉘 인젝션 방어 (보안)
# ---------------------------------------------------------------------------


class TestBuildMountCommandInjection:
    """Manila API 반환값(export_path/cephx_user)에 쉘 메타문자가 섞여도
    SSH 명령에서 명령 주입이 일어나지 않도록 shlex.quote 적용을 검증한다."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "malicious",
        [
            "host:/p;rm -rf /",
            "host:/p$(whoami)",
            "host:/p`id`",
            "host:/p\nsudo evil",
            "host:/p && curl evil",
        ],
    )
    async def test_nfs_export_path_is_quoted(self, malicious):
        """악의적 export_path가 단일 토큰으로 따옴표 래핑되어 명령 분리가 차단된다."""
        svc_conn = MagicMock()

        with patch(
            "app.services.ephemeral_mount.manila.get_export_locations",
            return_value=[malicious],
        ):
            from app.services.ephemeral_mount import build_mount_command

            cmd = await build_mount_command(svc_conn, "share-abc", "NFS", {})

        # 위험 시퀀스가 따옴표 밖에서 raw로 노출되지 않아야 한다.
        mount_line = next(line for line in cmd.splitlines() if "mount -t nfs" in line)
        assert "'" in mount_line  # shlex.quote가 작은따옴표로 래핑
        for token in (";", "$(", "`", "&&"):
            if token in malicious:
                # 메타문자는 반드시 따옴표 안에만 존재 (raw 분리 불가)
                assert f" {token}" not in mount_line.replace(f"'{malicious}'", "")

    @pytest.mark.asyncio
    async def test_cephfs_user_and_mons_quoted(self):
        """cephx_user / ceph_mons:path 가 shlex.quote 처리된다."""
        svc_conn = MagicMock()
        access_rule = {"access_to": "evil$(id)", "access_key": "sec"}

        with patch(
            "app.services.ephemeral_mount.manila.get_export_locations",
            return_value=["m1,m2:/v;reboot"],
        ):
            from app.services.ephemeral_mount import build_mount_command

            cmd = await build_mount_command(svc_conn, "share-abc", "CEPHFS", access_rule)

        mount_line = next(line for line in cmd.splitlines() if "mount -t ceph" in line)
        assert "'evil$(id)'" in mount_line
        assert "'m1,m2:/v;reboot'" in mount_line


# ---------------------------------------------------------------------------
# verify_mount_via_ssh
# ---------------------------------------------------------------------------


class TestVerifyMountViaSsh:
    @pytest.mark.asyncio
    async def test_returns_mounted_true_on_success(self):
        """mount + verify 모두 성공 시 mounted=True."""
        vm = _make_vm()

        with patch(
            "app.services.ephemeral_mount.run_command",
            new_callable=AsyncMock,
            side_effect=[
                (0, "", ""),  # mount 성공
                (0, "Filesystem ...\nMOUNT_OK", ""),  # verify 성공
                (0, "", ""),  # umount
            ],
        ):
            from app.services.ephemeral_mount import verify_mount_via_ssh

            result = await verify_mount_via_ssh(vm, "sudo mount ...\n")

        assert result["mounted"] is True
        assert "MOUNT_OK" in result["df_output"]
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_returns_mounted_false_on_mount_failure(self):
        """mount 실패 시 mounted=False, error 포함."""
        vm = _make_vm()

        with patch(
            "app.services.ephemeral_mount.run_command",
            new_callable=AsyncMock,
            return_value=(1, "", "mount: bad option"),
        ):
            from app.services.ephemeral_mount import verify_mount_via_ssh

            result = await verify_mount_via_ssh(vm, "sudo mount ...\n")

        assert result["mounted"] is False
        assert "mount 실패" in result["error"]

    @pytest.mark.asyncio
    async def test_umount_called_even_on_verify_failure(self):
        """검증 실패해도 umount는 항상 호출된다."""
        vm = _make_vm()
        mock_run = AsyncMock(
            side_effect=[
                (0, "", ""),  # mount 성공
                (1, "", "err"),  # verify 실패
                (0, "", ""),  # umount
            ]
        )

        with patch("app.services.ephemeral_mount.run_command", mock_run):
            from app.services.ephemeral_mount import verify_mount_via_ssh

            result = await verify_mount_via_ssh(vm, "sudo mount ...\n")

        assert result["mounted"] is False
        assert mock_run.call_count == 3  # mount + verify + umount
