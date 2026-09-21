"""runcmd mkdir brace expansion 회귀 테스트.

cloud-init runcmd 는 Ubuntu 에서 `/bin/sh -c "..."` 로 실행되며,
/bin/sh 가 dash 인 환경에서는 brace expansion(`{lower,upper,work,merged}`)이
동작하지 않아 literal 디렉토리 이름으로 생성된다.
이 파일은 생성된 cloud-init YAML 의 runcmd mkdir 라인에
brace 패턴이 없고 4개 디렉토리가 개별 인자로 들어갔음을 보장한다.
"""

import base64

import yaml

from app.services.cloudinit import generate_userdata

_COMMON_ARGS = dict(
    libraries=[],
    strategy="prebuilt",
    upper_device="/dev/vdb",
    ceph_monitors="192.168.1.1:6789",
    gpu_available=False,
)

_REQUIRED_DIRS = [
    "/opt/layers/lower",
    "/opt/layers/upper",
    "/opt/layers/work",
    "/opt/layers/merged",
]


def _get_runcmd(encoded: str) -> list[str]:
    yaml_str = base64.b64decode(encoded).decode()
    doc = yaml.safe_load(yaml_str)
    return [str(cmd) for cmd in (doc.get("runcmd") or [])]


def _mkdir_lines(runcmd: list[str]) -> list[str]:
    return [cmd for cmd in runcmd if cmd.startswith("mkdir")]


def test_mkdir_runcmd_dirs_present_with_file_storages():
    """file_storages 가 있을 때도 기본 4개 디렉토리 인자는 유지된다."""
    fs = [
        {
            "name": "python311",
            "share_proto": "CEPHFS",
            "export_path": "192.168.1.1:6789:/volumes/_nogroup/abc",
            "cephx_id": "user-python311",
            "cephx_key": "AQAabc==",
            "nfs_export_location": "",
            "mount_options": "",
        }
    ]
    encoded = generate_userdata(**_COMMON_ARGS, file_storages=fs)
    mkdir_text = " ".join(_mkdir_lines(_get_runcmd(encoded)))
    for d in _REQUIRED_DIRS:
        assert d in mkdir_text, f"file_storages 있을 때 {d!r} 가 runcmd mkdir 에 없음"
    assert "{" not in mkdir_text, "file_storages 있을 때 brace 패턴 발견"
