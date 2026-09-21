"""GPU flavor 인스턴스의 cloud-init userdata 회귀 테스트.

flavor.is_gpu=True 인 plain instance (libraries=[]) 생성 시
NVIDIA 드라이버 + dcgm-exporter 설치 단계가 user-data 에 포함되는지 검증.

이 테스트는 사용자 보고 (gpu.1080ti_8c_16g flavor 인스턴스에서 GPU 메트릭 부재)
회귀 방지용 — 실제 미설치 원인이 cloud-init userdata 누락이 아님을 backend 단에서 보장.
"""

import base64

import yaml

from app.services import cloudinit


def _generate(gpu_available: bool) -> str:
    """generate_userdata 는 base64 인코딩된 결과 반환 → 디코드한 raw YAML 반환."""
    encoded = cloudinit.generate_userdata(
        libraries=[],
        strategy="prebuilt",
        file_storages=[],
        upper_device="/dev/vdb",
        ceph_monitors="",
        gpu_available=gpu_available,
    )
    return base64.b64decode(encoded).decode()


def test_gpu_userdata_includes_install_script():
    """gpu_available=True includes the packaged monitoring installer."""
    yaml = _generate(gpu_available=True)
    assert "/opt/afterglow/install_gpu_monitoring.sh" in yaml
    assert "ubuntu-drivers autoinstall" in yaml, "NVIDIA 드라이버 자동 설치 스크립트 누락"


def test_gpu_userdata_runcmd_runs_packaged_services():
    """GPU bootstrap runs its installer and enables NVIDIA's packaged services."""
    rendered = _generate(gpu_available=True)
    assert "/opt/afterglow/install_gpu_monitoring.sh" in rendered
    assert "systemctl enable --now nvidia-dcgm.service" in rendered
    assert "systemctl enable --now nvidia-dcgm-exporter.service" in rendered


def test_gpu_userdata_uses_supported_dcgm_packages_without_custom_unit():
    rendered = _generate(gpu_available=True)
    assert "datacenter-gpu-manager" in rendered
    assert "datacenter-gpu-manager-exporter" in rendered
    assert "/etc/systemd/system/dcgm-exporter.service" not in rendered
    assert "/usr/local/bin/dcgm-exporter" not in rendered


def test_non_gpu_userdata_omits_gpu_install():
    """gpu_available=False 시 NVIDIA / DCGM 설치 항목이 모두 부재."""
    yaml = _generate(gpu_available=False)
    assert "install_gpu_monitoring.sh" not in yaml
    assert "ubuntu-drivers" not in yaml
    assert "dcgm-exporter" not in yaml
    assert "nvidia" not in yaml.lower()


def test_gpu_only_userdata_omits_layer_environment():
    """GPU-only bootstrap must not create the retained layer environment."""
    rendered = _generate(gpu_available=True)
    assert "/etc/profile.d/union-env.sh" not in rendered
    assert "/opt/union/overlay_setup.sh" not in rendered
    assert "union-overlay.service" not in rendered


# ---------------------------------------------------------------------------
# Generated cloud-config contract for GPU-only instances
# ---------------------------------------------------------------------------


def test_gpu_only_userdata_is_structured_cloud_config():
    """The real renderer emits typed lists while retaining GPU bootstrap."""
    rendered = _generate(gpu_available=True)
    document = yaml.safe_load(rendered)

    assert document["packages"] == []
    assert isinstance(document["write_files"], list)
    assert isinstance(document["runcmd"], list)
    assert any(entry.get("path") == "/opt/afterglow/install_gpu_monitoring.sh" for entry in document["write_files"])
    assert "/opt/afterglow/install_gpu_monitoring.sh" in document["runcmd"]
