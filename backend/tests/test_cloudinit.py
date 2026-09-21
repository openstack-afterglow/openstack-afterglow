"""cloudinit.generate_userdata() 헬스체크 주입 테스트."""

import base64
from email import policy
from email.parser import BytesParser

import pytest
import yaml

from app.services.cloudinit import compose_userdata, generate_github_ssh_userdata, generate_userdata

_COMMON_ARGS = dict(
    libraries=[],
    strategy="prebuilt",
    file_storages=[],
    upper_device="/dev/vdb",
    ceph_monitors="192.168.1.1:6789",
    gpu_available=False,
)

_LAYER_STORAGE = [
    {
        "name": "python311",
        "share_proto": "NFS",
        "nfs_export_location": "10.0.0.1:/layers/python311",
        "mount_options": "ro,nosuid,nodev,noexec",
    }
]
_LAYER_ARGS = {**_COMMON_ARGS, "libraries": ["python311"], "file_storages": _LAYER_STORAGE}


def _decode_userdata(encoded: str) -> str:
    return base64.b64decode(encoded).decode()


_LAYER_MARKERS = (
    "/opt/union/overlay_setup.sh",
    "/etc/profile.d/union-env.sh",
    "/etc/systemd/system/union-overlay.service",
    "/etc/envmgr-union.conf",
    "union-health.timer",
)


def test_plain_userdata_has_list_packages_and_no_layer_bootstrap():
    yaml_str = _decode_userdata(generate_userdata(**_COMMON_ARGS))
    document = yaml.safe_load(yaml_str)

    assert document["packages"] == []
    assert document["write_files"] == []
    assert document["runcmd"] == []
    assert all(marker not in yaml_str for marker in _LAYER_MARKERS)


def test_gpu_only_userdata_keeps_gpu_bootstrap_without_layer_bootstrap():
    yaml_str = _decode_userdata(generate_userdata(**{**_COMMON_ARGS, "gpu_available": True}))

    assert "/opt/afterglow/install_gpu_monitoring.sh" in yaml_str
    assert all(marker not in yaml_str for marker in _LAYER_MARKERS)


def test_data_mount_only_userdata_keeps_mount_bootstrap_without_layer_bootstrap():
    data_mount = {
        "file_storage_id": "share-data",
        "share_proto": "NFS",
        "nfs_export_location": "10.0.0.2:/data",
        "mount_point": "/mnt/data",
        "mount_options": "ro,nosuid,nodev,noexec",
    }
    yaml_str = _decode_userdata(generate_userdata(**_COMMON_ARGS, data_mounts=[data_mount]))

    assert "/opt/union/data_mounts.sh" in yaml_str
    assert "afterglow-data-mounts.service" in yaml_str
    assert all(marker not in yaml_str for marker in _LAYER_MARKERS)


def test_layer_userdata_includes_overlay_environment_and_health_bootstrap():
    yaml_str = _decode_userdata(
        generate_userdata(
            **_LAYER_ARGS,
            instance_id="layer-instance",
            report_url="https://backend.example.com",
            report_token="layer-token",
        )
    )

    assert "/opt/union/overlay_setup.sh" in yaml_str
    assert "/etc/profile.d/union-env.sh" in yaml_str
    assert "union-overlay.service" in yaml_str
    assert "union-health.timer" in yaml_str


def test_userdata_without_health_check():
    """report_url 없으면 헬스체크 섹션 미포함."""
    encoded = generate_userdata(**_COMMON_ARGS)
    yaml_str = _decode_userdata(encoded)
    assert "union-health.timer" not in yaml_str
    assert "health-check.sh" not in yaml_str


def test_userdata_with_health_check():
    """report_url+instance_id+report_token 지정 시 헬스체크 섹션 포함."""
    encoded = generate_userdata(
        **_LAYER_ARGS,
        instance_id="test-inst-uuid",
        report_url="https://backend.example.com",
        report_token="test-token-abc",
    )
    yaml_str = _decode_userdata(encoded)
    assert "union-health.timer" in yaml_str
    assert "health-check.sh" in yaml_str
    assert "systemctl enable --now union-health.timer" in yaml_str


def test_health_check_script_contains_url_and_token():
    """health_check.sh.j2 에 report_url / instance_id / report_token이 치환됐는지."""
    encoded = generate_userdata(
        **_LAYER_ARGS,
        instance_id="my-instance-uuid",
        report_url="https://api.example.com",
        report_token="secret-report-token",
    )
    yaml_str = _decode_userdata(encoded)
    assert "https://api.example.com" in yaml_str
    assert "my-instance-uuid" in yaml_str
    assert "secret-report-token" in yaml_str


def test_health_check_includes_file_storages():
    """file_storages가 있을 때 헬스체크 스크립트에 share 이름 포함."""
    fs = [
        {"name": "torch", "share_proto": "NFS", "nfs_export_location": "10.0.0.1:/vol", "mount_options": ""},
    ]
    encoded = generate_userdata(
        libraries=[],
        strategy="prebuilt",
        file_storages=fs,
        upper_device="/dev/vdb",
        ceph_monitors="",
        gpu_available=False,
        instance_id="inst-uuid",
        report_url="https://backend.example.com",
        report_token="tok",
    )
    yaml_str = _decode_userdata(encoded)
    assert "lower_torch" in yaml_str


def test_userdata_partial_health_params_excluded():
    """report_url만 있고 token 없으면 헬스체크 미포함."""
    encoded = generate_userdata(
        **_COMMON_ARGS,
        instance_id="some-id",
        report_url="https://backend.example.com",
        report_token="",  # 빈 토큰 → 미포함
    )
    yaml_str = _decode_userdata(encoded)
    assert "union-health.timer" not in yaml_str


def test_nfs_mount_options_include_security_flags():
    """NFS 마운트 옵션에 nosuid,nodev,noexec 포함되어야 한다."""
    fs = [
        {
            "name": "python311",
            "share_proto": "NFS",
            "nfs_export_location": "10.0.0.1:/vol",
            "mount_options": "hard,intr,noatime,nosuid,nodev,noexec,_netdev,timeo=10,retrans=3",
            "export_path": "",
            "cephx_id": "",
            "cephx_key": "",
        }
    ]
    encoded = generate_userdata(
        libraries=[],
        strategy="prebuilt",
        file_storages=fs,
        upper_device="/dev/vdb",
        ceph_monitors="",
        gpu_available=False,
    )
    yaml_str = _decode_userdata(encoded)
    assert "nosuid" in yaml_str
    assert "nodev" in yaml_str
    assert "noexec" in yaml_str


def test_union_ro_share_export_injected_to_write_files():
    """union_ro_share_export가 지정되면 write_files에 LAYER_STORE_RO_EXPORT 포함."""
    encoded = generate_userdata(
        **_LAYER_ARGS,
        union_ro_share_export="10.0.0.1:6789:/volumes/_nogroup/abc123",
    )
    yaml_str = _decode_userdata(encoded)
    assert "LAYER_STORE_RO_EXPORT" in yaml_str
    assert "10.0.0.1:6789:/volumes/_nogroup/abc123" in yaml_str


@pytest.mark.parametrize(
    "malicious",
    [
        '10.0.0.1:/vol"\nruncmd:\n  - rm -rf /',  # 개행 → YAML 구조 주입
        '10.0.0.1:/vol"; touch /tmp/pwned; echo "',  # 따옴표/세미콜론 → conf 주입
        "10.0.0.1:/vol$(id)",  # 명령 치환
        "10.0.0.1:/vol`id`",  # 백틱 치환
    ],
)
def test_union_ro_share_export_rejects_injection(malicious):
    """union_ro_share_export에 개행/따옴표/쉘 메타문자가 있으면 ValueError로 거부."""
    with pytest.raises(ValueError):
        generate_userdata(**_COMMON_ARGS, union_ro_share_export=malicious)


def test_union_manifest_share_export_rejects_injection():
    """union_manifest_share_export도 동일하게 인젝션 값을 거부."""
    with pytest.raises(ValueError):
        generate_userdata(
            **_COMMON_ARGS,
            union_manifest_share_export='x"\nwrite_files:\n  - path: /tmp/x',
        )


@pytest.mark.parametrize(
    "value",
    [
        "10.0.0.1:/vol\n",  # trailing newline — Python `$` gotcha 회귀 방지(\Z 필요)
        "10.0.0.1:/vol\nfoo",  # 중간 개행 (그 외 문자는 정상)
        "10.0.0.1:/vol\r",  # trailing CR
    ],
)
def test_union_ro_share_export_rejects_newline_only(value):
    """char-class에 걸리지 않는 순수 개행 값도 거부되어야 한다(\\Z 앵커 검증)."""
    with pytest.raises(ValueError):
        generate_userdata(**_COMMON_ARGS, union_ro_share_export=value)


def test_union_exports_accept_valid_cephfs_and_nfs_paths():
    """정상 CephFS/NFS export 경로는 레이어 VM 설정에 반영된다."""
    encoded = generate_userdata(
        **_LAYER_ARGS,
        union_ro_share_export="10.0.0.1:6789:/volumes/_nogroup/abc123",
        union_manifest_share_export="10.0.0.5:/exports/manifest_store",
    )
    yaml_str = _decode_userdata(encoded)
    assert "LAYER_STORE_RO_EXPORT" in yaml_str
    assert "MANIFEST_STORE_EXPORT" in yaml_str


def test_userdata_without_gpu_skips_dcgm():
    """gpu_available=False 인스턴스에는 DCGM Exporter 관련 내용이 없어야 한다."""
    encoded = generate_userdata(**{**_COMMON_ARGS, "gpu_available": False})
    yaml_str = _decode_userdata(encoded)
    assert "dcgm-exporter" not in yaml_str
    assert "install_dcgm_exporter.sh" not in yaml_str


def test_userdata_with_gpu_installs_supported_dcgm_packages():
    """GPU bootstrap uses NVIDIA's packaged DCGM daemon and exporter."""
    encoded = generate_userdata(**{**_COMMON_ARGS, "gpu_available": True})
    yaml_str = _decode_userdata(encoded)
    assert "datacenter-gpu-manager" in yaml_str
    assert "datacenter-gpu-manager-exporter" in yaml_str
    assert "systemctl enable --now nvidia-dcgm.service" in yaml_str
    assert "systemctl enable --now nvidia-dcgm-exporter.service" in yaml_str
    assert "github.com/NVIDIA/dcgm-exporter/releases" not in yaml_str
    assert "/usr/local/bin/dcgm-exporter" not in yaml_str


def test_userdata_with_gpu_maps_supported_repository_architectures():
    encoded = generate_userdata(**{**_COMMON_ARGS, "gpu_available": True})
    yaml_str = _decode_userdata(encoded)

    assert "amd64) CUDA_REPO_ARCH=x86_64" in yaml_str
    assert "arm64) CUDA_REPO_ARCH=sbsa" in yaml_str
    assert '*) echo "unsupported NVIDIA repository architecture:' in yaml_str
    assert "${DISTRO}/${CUDA_REPO_ARCH}/${KEYRING_PKG}" in yaml_str


def test_userdata_with_gpu_installs_driver_and_dcgm_daemon():
    """gpu_available=True installs a driver when absent before packaged DCGM services."""
    encoded = generate_userdata(**{**_COMMON_ARGS, "gpu_available": True})
    yaml_str = _decode_userdata(encoded)
    assert "ubuntu-drivers autoinstall" in yaml_str
    assert "command -v nvidia-smi" in yaml_str
    assert "cuda-keyring" in yaml_str
    assert "systemctl enable --now nvidia-dcgm.service" in yaml_str


def test_rotate_key_script_not_injected_when_disabled():
    """union_cephx_rotate_hours=0 이면 rotate-key 스크립트 미포함."""
    encoded = generate_userdata(**{**_COMMON_ARGS, "union_cephx_rotate_hours": 0})
    yaml_str = _decode_userdata(encoded)
    assert "envmgr-rotate-key.sh" not in yaml_str
    assert "union-rotate-key.service" not in yaml_str


def test_rotate_key_script_injected_to_write_files():
    """union_cephx_rotate_hours > 0 이면 /usr/local/bin/envmgr-rotate-key.sh 주입."""
    encoded = generate_userdata(**{**_LAYER_ARGS, "union_cephx_rotate_hours": 24})
    yaml_str = _decode_userdata(encoded)
    assert "path: /usr/local/bin/envmgr-rotate-key.sh" in yaml_str
    assert 'permissions: "0750"' in yaml_str
    assert "CephX 키 회전" in yaml_str


def test_rotate_key_systemd_unit_present_when_enabled():
    """union_cephx_rotate_hours > 0 이면 systemd service/timer 항목도 포함."""
    encoded = generate_userdata(**{**_LAYER_ARGS, "union_cephx_rotate_hours": 24})
    yaml_str = _decode_userdata(encoded)
    assert "union-rotate-key.service" in yaml_str
    assert "union-rotate-key.timer" in yaml_str
    assert "ExecStart=/usr/local/bin/envmgr-rotate-key.sh" in yaml_str


def test_rotate_key_script_before_systemd_unit():
    """write_files에서 rotate-key.sh 주입이 systemd unit 선언보다 먼저 나와야 한다."""
    encoded = generate_userdata(**{**_LAYER_ARGS, "union_cephx_rotate_hours": 24})
    yaml_str = _decode_userdata(encoded)
    script_pos = yaml_str.find("path: /usr/local/bin/envmgr-rotate-key.sh")
    service_pos = yaml_str.find("path: /etc/systemd/system/union-rotate-key.service")
    assert script_pos < service_pos, "rotate-key.sh write_files 항목이 service 선언보다 앞서야 함"


# ─────────────────────────────────────────────────────────────────
# Shell 인젝션 회귀 방지
# ─────────────────────────────────────────────────────────────────


def test_health_check_quotes_malicious_share_name():
    """share name 에 shell 메타문자가 들어와도 single-quote 로 감싸 인젝션 차단."""
    fs = [
        {
            "name": "'\"; rm -rf / #",  # 악성 share name 시도
            "share_proto": "NFS",
            "nfs_export_location": "10.0.0.1:/vol",
            "mount_options": "",
        }
    ]
    encoded = generate_userdata(
        libraries=[],
        strategy="prebuilt",
        file_storages=fs,
        upper_device="/dev/vdb",
        ceph_monitors="",
        gpu_available=False,
        instance_id="inst-uuid",
        report_url="https://backend.example.com",
        report_token="tok",
    )
    yaml_str = _decode_userdata(encoded)
    # raw 한 `; rm -rf` 시퀀스가 unquoted 로 들어가면 안 된다 — single-quote 안에 들어가야
    # 매 줄을 검사: SHARE_NAME= 라인을 찾아 unquoted 메타문자가 없는지.
    for line in yaml_str.splitlines():
        if line.strip().startswith("SHARE_NAME="):
            value = line.strip().removeprefix("SHARE_NAME=")
            # shlex.quote 결과는 single-quote 로 감싸진 형태여야 함
            assert value.startswith("'") and value.endswith("'"), (
                f"SHARE_NAME 값이 single-quote 로 감싸져 있지 않음: {value!r}"
            )


def test_health_check_quotes_report_url_and_token():
    """report_url / instance_id / report_token 에 메타문자가 와도 quote."""
    encoded = generate_userdata(
        **_LAYER_ARGS,
        instance_id="id'; touch /tmp/pwn",
        report_url="https://x'; whoami",
        report_token="$(whoami)",
    )
    yaml_str = _decode_userdata(encoded)
    # 각 변수 라인이 single-quote 로 감싸졌는지
    for prefix in ("REPORT_URL=", "INSTANCE_ID=", "REPORT_TOKEN="):
        line = next((ln.strip() for ln in yaml_str.splitlines() if ln.strip().startswith(prefix)), None)
        assert line is not None, f"{prefix} 라인 미발견"
        value = line.removeprefix(prefix)
        assert value.startswith("'") and value.endswith("'"), f"{prefix} 값이 quote 되지 않음: {value!r}"


def test_envmgr_rotate_key_uses_printf_not_heredoc():
    """envmgr_rotate_key.sh.j2 가 cat << EOF 가 아니라 printf 로 키링을 작성하는지."""
    encoded = generate_userdata(**{**_LAYER_ARGS, "union_cephx_rotate_hours": 24})
    yaml_str = _decode_userdata(encoded)
    # 키링 작성 부분에 cat << EOF 헤어독이 사라지고 printf 가 사용되어야 함
    assert "printf '[client.%s]\\n'" in yaml_str
    assert "printf '    key = %s\\n'" in yaml_str
    # 형식 검증 라인 존재
    assert "NEW_KEY 형식이 invalid" in yaml_str


# ---------------------------------------------------------------------------
# cloud-init 보간 값 형식 검증 (YAML 인젝션 방어 — 보안)
# ---------------------------------------------------------------------------


def _ceph_fs(**over) -> dict:
    base = {
        "name": "torch",
        "share_proto": "CEPHFS",
        "export_path": "",
        "cephx_id": "builder-abc",
        "cephx_key": "QVFCc2VjcmV0Kz09",  # 유효 base64
        "mount_options": "",
    }
    base.update(over)
    return base


def test_cephx_key_with_newline_rejected():
    """개행이 섞인 cephx_key는 YAML 구조 파괴를 유발하므로 거부된다."""
    import pytest

    fs = [_ceph_fs(cephx_key="QVFC\nkey2: stolen")]
    with pytest.raises(ValueError, match="cephx_key"):
        generate_userdata(
            libraries=[],
            strategy="prebuilt",
            file_storages=fs,
            upper_device="/dev/vdb",
            ceph_monitors="10.0.0.1:6789",
            gpu_available=False,
        )


def test_cephx_id_with_shell_meta_rejected():
    """cephx_id에 경로/특수문자가 섞이면 거부된다."""
    import pytest

    fs = [_ceph_fs(cephx_id="../../etc/evil")]
    with pytest.raises(ValueError, match="cephx_id"):
        generate_userdata(
            libraries=[],
            strategy="prebuilt",
            file_storages=fs,
            upper_device="/dev/vdb",
            ceph_monitors="10.0.0.1:6789",
            gpu_available=False,
        )


def test_ceph_monitors_with_newline_rejected():
    """개행이 섞인 ceph_monitors는 거부된다."""
    import pytest

    with pytest.raises(ValueError, match="ceph_monitors"):
        generate_userdata(
            **{**_COMMON_ARGS, "ceph_monitors": "10.0.0.1:6789\nmalicious: true"},
        )


def test_valid_ceph_inputs_pass():
    """정상 형식의 cephx_id/cephx_key/ceph_monitors는 통과한다."""
    fs = [_ceph_fs()]
    encoded = generate_userdata(
        libraries=[],
        strategy="prebuilt",
        file_storages=fs,
        upper_device="/dev/vdb",
        ceph_monitors="10.0.0.1:6789,10.0.0.2:6789",
        gpu_available=False,
    )
    yaml_str = _decode_userdata(encoded)
    assert "builder-abc" in yaml_str


def test_github_ssh_userdata_is_base64_string_with_structured_import() -> None:
    encoded = generate_github_ssh_userdata("octocat")
    assert isinstance(encoded, str)
    assert yaml.safe_load(_decode_userdata(encoded)) == {"ssh_import_id": ["gh:octocat"]}


def test_generated_userdata_includes_github_ssh_import() -> None:
    encoded = generate_userdata(**_COMMON_ARGS, github_username="octocat")
    assert isinstance(encoded, str)
    assert yaml.safe_load(_decode_userdata(encoded))["ssh_import_id"] == ["gh:octocat"]


def test_github_ssh_import_preserves_custom_cloud_config_as_multipart() -> None:
    encoded = compose_userdata(
        None,
        "#cloud-config\nruncmd:\n  - echo hello\n",
        "octocat",
    )
    assert isinstance(encoded, str)
    message = BytesParser(policy=policy.default).parsebytes(base64.b64decode(encoded))
    assert message.is_multipart()
    parts = list(message.iter_parts())
    assert yaml.safe_load(parts[0].get_content()) == {"ssh_import_id": ["gh:octocat"]}
    assert yaml.safe_load(parts[1].get_content()) == {"runcmd": ["echo hello"]}


def test_custom_shell_userdata_is_base64_encoded_without_managed_feature() -> None:
    script = "#!/bin/sh\necho hello\n"
    encoded = compose_userdata(None, script)
    assert isinstance(encoded, str)
    assert base64.b64decode(encoded).decode() == script
