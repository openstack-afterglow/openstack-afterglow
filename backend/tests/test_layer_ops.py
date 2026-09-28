"""squashfs 레이어 빌드/소비 API 테스트.

커버 범위:
  - LayerBuildRequest / LayerConsumeRequest Pydantic 화이트리스트 검증 (명령주입 차단)
  - require_admin 인증 가드 (비인증 → 401, 일반 사용자 → 403)
  - POST /api/v1/admin/libraries/build 성공 흐름 (layer_builder.start_layer_build mock)
  - GET  /api/v1/admin/libraries/builds 목록 (DB mock)
  - GET  /api/v1/admin/libraries/builds/{id} 상세 (DB mock)
  - POST /api/v1/admin/libraries/builds/{id}/cancel 취소 (layer_builder.cancel_layer_build mock)
  - POST /api/v1/admin/libraries/consume 성공 흐름 (run_layer_consume mock)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.api.union.layer_ops import (
    LayerBuildRequest,
    LayerConsumeRequest,
    LayerProfileRequest,
    _artifact_delete_preview,
)
from app.config import get_settings
from app.main import app

BASE = "/api/v1/admin/libraries"
OLD_BASE = "/api/v1/admin/layers"


def _scalars_result(rows):
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    return result


def _scalar_result(row):
    result = MagicMock()
    result.scalar_one_or_none.return_value = row
    return result


def _row(**attrs):
    row = MagicMock()
    for key, value in attrs.items():
        setattr(row, key, value)
    return row


def _artifact(
    artifact_id: int,
    name: str,
    *,
    kind: str = "python",
    python_version: str | None = "3.11",
    parent_id: int | None = None,
    is_sealed: bool = True,
    pip_packages: list[str] | None = None,
    apt_packages: list[str] | None = None,
    ubuntu_base: str = "ubuntu-24.04-server-2026-04-15",
):
    row = MagicMock()
    row.id = artifact_id
    row.name = name
    row.kind = kind
    row.python_version = python_version
    row.pip_packages = pip_packages or []
    row.apt_packages = apt_packages or []
    row.ubuntu_base = ubuntu_base
    row.base_image_id = "img-24"
    row.base_image_name = "ubuntu-24.04"
    row.base_image_checksum = None
    row.base_image_os_hash_algo = None
    row.base_image_os_hash_value = None
    row.base_image_min_disk = 20
    row.base_image_visibility = "shared"
    row.base_image_owner = "admin"
    row.source_metadata = None
    row.sqsh_filename = f"{name}-latest.sqsh"
    row.share_id = f"share-{artifact_id}"
    row.build_id = artifact_id * 10
    row.size_bytes = None
    row.parent_id = parent_id
    row.is_sealed = is_sealed
    row.created_at = None
    return row


def _profile(profile_id: int = 10, name: str = "default", layers: list[str] | None = None):
    return _row(
        id=profile_id,
        name=name,
        layers=layers or ["python311"],
        created_at=None,
        updated_at=None,
    )


def _consume(
    consume_id: int = 11,
    profile_name: str = "default",
    *,
    status: str = "active",
    server_id: str | None = "srv-1",
    artifact_ids: list[int] | None = None,
):
    return _row(
        id=consume_id,
        profile_name=profile_name,
        status=status,
        server_id=server_id,
        port_id=None,
        server_name=f"consumer-{consume_id}",
        share_id="share-ro",
        error_message=None,
        artifact_ids=artifact_ids,
        created_at=None,
        completed_at=None,
    )


# ============================================================================
# Part 0: Pydantic 화이트리스트 검증 — LayerBuildRequest
# ============================================================================


class TestLayerBuildRequestValidation:
    """LayerBuildRequest 입력값과 uv → python → pip 계약 검증."""

    def test_kind_uv_accepts_no_parent_python_or_packages(self):
        req = LayerBuildRequest(layer_name="uv", kind="uv", base_image_id="img-24")
        assert req.layer_name == "uv"
        assert req.kind == "uv"
        assert req.python_version is None
        assert req.pip_packages == []
        assert req.apt_packages == []

    @pytest.mark.parametrize(
        "extra",
        [
            {"parent_artifact_id": 7},
            {"python_version": "3.11"},
            {"pip_packages": ["numpy==1.26.4"]},
            {"apt_packages": ["curl"]},
        ],
    )
    def test_kind_uv_rejects_parent_python_or_packages(self, extra):
        with pytest.raises(ValidationError):
            LayerBuildRequest(layer_name="uv", kind="uv", base_image_id="img-24", **extra)

    def test_kind_system_accepts_apt_packages_without_parent(self):
        req = LayerBuildRequest(
            layer_name="sys-tools",
            kind="system",
            apt_packages=["curl", "nfs-common", "squashfs-tools"],
            base_image_id="img-20",
        )
        assert req.kind == "system"
        assert req.parent_artifact_id is None
        assert req.apt_packages == ["curl", "nfs-common", "squashfs-tools"]

    @pytest.mark.parametrize(
        "kwargs",
        [
            {},
            {"apt_packages": []},
            {"parent_artifact_id": 7, "apt_packages": ["curl"]},
            {"python_version": "3.11", "apt_packages": ["curl"]},
            {"pip_packages": ["numpy"], "apt_packages": ["curl"]},
            {"pip_index_url": "https://pypi.org/simple", "apt_packages": ["curl"]},
            {"pip_extra_index_urls": ["https://pypi.org/simple"], "apt_packages": ["curl"]},
            {"pip_find_links": ["https://download.pytorch.org/whl/cpu"], "apt_packages": ["curl"]},
        ],
    )
    def test_kind_system_rejects_invalid_combinations(self, kwargs):
        with pytest.raises(ValidationError):
            LayerBuildRequest(layer_name="sys-tools", kind="system", base_image_id="img-20", **kwargs)

    @pytest.mark.parametrize("package", ["Curl", "curl;rm", "curl\nnfs-common", "../curl"])
    def test_kind_system_rejects_invalid_apt_names(self, package):
        with pytest.raises(ValidationError):
            LayerBuildRequest(layer_name="sys-tools", kind="system", apt_packages=[package], base_image_id="img-20")

    def test_kind_nvidia_accepts_default_driver_branch_without_parent(self):
        req = LayerBuildRequest(layer_name="nvidia-driver", kind="nvidia", base_image_id="img-24")
        assert req.kind == "nvidia"
        assert req.parent_artifact_id is None
        assert req.apt_packages == []
        assert req.nvidia_driver_branch == "580"

    @pytest.mark.parametrize("kind", ["uv", "system", "nvidia"])
    @pytest.mark.parametrize("ubuntu_base", ["ubuntu-18.04", "ubuntu-20.04", "ubuntu-22.04", "ubuntu-24.04"])
    def test_root_kinds_accept_supported_ubuntu_bases(self, kind, ubuntu_base):
        kwargs = {"apt_packages": ["curl"]} if kind == "system" else {}
        req = LayerBuildRequest(
            layer_name=f"{kind}-root", kind=kind, ubuntu_base=ubuntu_base, base_image_id="img-root", **kwargs
        )
        assert req.ubuntu_base == ubuntu_base

    @pytest.mark.parametrize("ubuntu_base", ["ubuntu-16.04", "Ubuntu 24", "ubuntu-24.04;rm"])
    def test_rejects_invalid_ubuntu_base(self, ubuntu_base):
        with pytest.raises(ValidationError):
            LayerBuildRequest(layer_name="uv", kind="uv", ubuntu_base=ubuntu_base, base_image_id="img-24")

    def test_kind_nvidia_accepts_allowed_driver_branch(self):
        req = LayerBuildRequest(
            layer_name="nvidia-driver-570", kind="nvidia", nvidia_driver_branch="570", base_image_id="img-24"
        )
        assert req.nvidia_driver_branch == "570"

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"parent_artifact_id": 7},
            {"python_version": "3.11"},
            {"pip_packages": ["numpy"]},
            {"apt_packages": ["nvidia-dkms-580-open"]},
            {"pip_index_url": "https://pypi.org/simple"},
            {"nvidia_driver_branch": "123"},
            {"nvidia_driver_branch": "580;rm"},
        ],
    )
    def test_kind_nvidia_rejects_invalid_combinations(self, kwargs):
        with pytest.raises(ValidationError):
            LayerBuildRequest(layer_name="nvidia-driver", kind="nvidia", base_image_id="img-24", **kwargs)

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"kind": "uv"},
            {"kind": "nvidia"},
            {"kind": "python", "python_version": "3.11", "parent_artifact_id": 7},
            {"kind": "pip", "pip_packages": ["numpy"], "parent_artifact_id": 7},
        ],
    )
    def test_non_system_kinds_reject_apt_packages(self, kwargs):
        with pytest.raises(ValidationError):
            LayerBuildRequest(layer_name="not-system", apt_packages=["curl"], **kwargs)

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"kind": "python", "python_version": "3.11", "parent_artifact_id": 7},
            {"kind": "pip", "pip_packages": ["numpy"], "parent_artifact_id": 7},
        ],
    )
    def test_non_nvidia_kinds_reject_nvidia_driver_branch(self, kwargs):
        with pytest.raises(ValidationError):
            LayerBuildRequest(layer_name="not-nvidia", nvidia_driver_branch="580", **kwargs)

    def test_kind_python_accepts_parent_and_version(self):
        req = LayerBuildRequest(layer_name="python311", kind="python", python_version="3.11", parent_artifact_id=7)
        assert req.layer_name == "python311"
        assert req.kind == "python"
        assert req.python_version == "3.11"
        assert req.parent_artifact_id == 7
        assert req.pip_packages == []

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"python_version": "3.11"},
            {"parent_artifact_id": 7},
            {"python_version": "3.11", "parent_artifact_id": 7, "pip_packages": ["numpy==1.26.4"]},
        ],
    )
    def test_kind_python_rejects_missing_parent_missing_version_or_packages(self, kwargs):
        with pytest.raises(ValidationError):
            LayerBuildRequest(layer_name="python311", kind="python", **kwargs)

    def test_kind_pip_accepts_parent_and_pinned_packages(self):
        req = LayerBuildRequest(
            layer_name="numpy-stack",
            kind="pip",
            parent_artifact_id=7,
            pip_packages=["numpy==1.26.4", "pandas==2.2.2", "scikit-learn~=1.5"],
        )
        assert req.kind == "pip"
        assert req.python_version is None
        assert req.pip_packages == ["numpy==1.26.4", "pandas==2.2.2", "scikit-learn~=1.5"]

    def test_kind_pip_accepts_structured_source_urls(self):
        req = LayerBuildRequest(
            layer_name="torch-stack",
            kind="pip",
            parent_artifact_id=7,
            pip_packages=["torch", "torchvision"],
            pip_index_url="https://download.pytorch.org/whl/cpu",
            pip_extra_index_urls=["https://pypi.org/simple"],
            pip_find_links=["https://download.pytorch.org/whl/cpu/torch_stable.html"],
        )
        assert req.pip_index_url == "https://download.pytorch.org/whl/cpu"
        assert req.pip_extra_index_urls == ["https://pypi.org/simple"]
        assert req.pip_find_links == ["https://download.pytorch.org/whl/cpu/torch_stable.html"]

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"pip_index_url": "https://token:secret@download.pytorch.org/whl/cpu"},
            {"pip_index_url": "https://download.pytorch.org/whl/cpu?token=secret"},
            {"pip_extra_index_urls": ["https://pypi.org/simple;rm"]},
            {"pip_find_links": ["ftp://download.pytorch.org/whl/cpu"]},
        ],
    )
    def test_kind_pip_rejects_invalid_source_urls(self, kwargs):
        with pytest.raises(ValidationError):
            LayerBuildRequest(
                layer_name="torch-stack",
                kind="pip",
                parent_artifact_id=7,
                pip_packages=["torch"],
                **kwargs,
            )

    @pytest.mark.parametrize("kind", ["uv", "python"])
    def test_non_pip_kinds_reject_source_urls(self, kind):
        kwargs = {"kind": kind, "pip_index_url": "https://download.pytorch.org/whl/cpu"}
        if kind == "python":
            kwargs.update({"python_version": "3.11", "parent_artifact_id": 7})
        with pytest.raises(ValidationError):
            LayerBuildRequest(layer_name=f"{kind}-layer", **kwargs)

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"pip_packages": ["numpy==1.26.4"]},
            {"parent_artifact_id": 7, "pip_packages": []},
            {"parent_artifact_id": 7, "python_version": "3.11", "pip_packages": ["numpy==1.26.4"]},
        ],
    )
    def test_kind_pip_rejects_missing_parent_empty_packages_or_python_version(self, kwargs):
        with pytest.raises(ValidationError):
            LayerBuildRequest(layer_name="numpy-stack", kind="pip", **kwargs)

    def test_custom_kind_rejected(self):
        with pytest.raises(ValidationError):
            LayerBuildRequest(layer_name="torch-layer", kind="torch", parent_artifact_id=7, pip_packages=["torch"])

    def test_valid_layer_name_with_dots_and_hyphens(self):
        req = LayerBuildRequest(layer_name="uv-py3.11", kind="python", python_version="3.11", parent_artifact_id=7)
        assert req.layer_name == "uv-py3.11"

    # --- layer_name 명령주입 차단 ---

    def test_layer_name_with_semicolon_rejected(self):
        with pytest.raises(ValidationError):
            LayerBuildRequest(layer_name="name;evil", kind="python", python_version="3.11", parent_artifact_id=7)

    def test_layer_name_with_newline_rejected(self):
        with pytest.raises(ValidationError):
            LayerBuildRequest(layer_name="name\nevil", kind="python", python_version="3.11", parent_artifact_id=7)

    def test_layer_name_with_backtick_rejected(self):
        with pytest.raises(ValidationError):
            LayerBuildRequest(layer_name="`rm -rf /`", kind="python", python_version="3.11", parent_artifact_id=7)

    def test_layer_name_with_dollar_rejected(self):
        with pytest.raises(ValidationError):
            LayerBuildRequest(layer_name="$(id)", kind="python", python_version="3.11", parent_artifact_id=7)

    def test_layer_name_with_slash_rejected(self):
        with pytest.raises(ValidationError):
            LayerBuildRequest(layer_name="a/b", kind="python", python_version="3.11", parent_artifact_id=7)

    def test_layer_name_starting_with_hyphen_rejected(self):
        with pytest.raises(ValidationError):
            LayerBuildRequest(layer_name="-bad", kind="python", python_version="3.11", parent_artifact_id=7)

    # --- python_version 형식 검증 ---

    def test_python_version_major_minor_only_accepted(self):
        req = LayerBuildRequest(layer_name="test", kind="python", python_version="3.12", parent_artifact_id=7)
        assert req.python_version == "3.12"

    def test_python_version_with_patch_rejected(self):
        with pytest.raises(ValidationError):
            LayerBuildRequest(layer_name="test", kind="python", python_version="3.11.2", parent_artifact_id=7)

    def test_python_version_text_rejected(self):
        with pytest.raises(ValidationError):
            LayerBuildRequest(layer_name="test", kind="python", python_version="latest", parent_artifact_id=7)

    def test_python_version_with_injection_rejected(self):
        with pytest.raises(ValidationError):
            LayerBuildRequest(layer_name="test", kind="python", python_version="3.11;evil", parent_artifact_id=7)

    # --- pip_packages 명령주입 차단 ---

    def test_valid_pip_packages_accepted(self):
        req = LayerBuildRequest(
            layer_name="test",
            kind="pip",
            parent_artifact_id=7,
            pip_packages=["numpy>=1.24", "pandas[excel]", "scikit-learn~=1.0"],
        )
        assert len(req.pip_packages) == 3

    def test_pip_package_with_semicolon_rejected(self):
        with pytest.raises(ValidationError):
            LayerBuildRequest(layer_name="test", kind="pip", parent_artifact_id=7, pip_packages=["numpy;rm -rf /"])

    def test_pip_package_with_dollar_rejected(self):
        with pytest.raises(ValidationError):
            LayerBuildRequest(layer_name="test", kind="pip", parent_artifact_id=7, pip_packages=["$(evil)"])

    def test_pip_package_with_newline_rejected(self):
        with pytest.raises(ValidationError):
            LayerBuildRequest(layer_name="test", kind="pip", parent_artifact_id=7, pip_packages=["numpy\nevil"])

    def test_kind_with_uppercase_rejected(self):
        with pytest.raises(ValidationError):
            LayerBuildRequest(layer_name="test", kind="Shell", python_version="3.11", parent_artifact_id=7)

    def test_kind_with_injection_chars_rejected(self):
        with pytest.raises(ValidationError):
            LayerBuildRequest(layer_name="test", kind="sh;ell", python_version="3.11", parent_artifact_id=7)


# ============================================================================
# Part 1: Pydantic 화이트리스트 검증 — LayerConsumeRequest
# ============================================================================


class TestLayerConsumeRequestValidation:
    """LayerConsumeRequest 입력값 화이트리스트 검증."""

    def test_valid_request_accepted(self):
        req = LayerConsumeRequest(
            profile_name="default",
            server_name="consumer-01",
            flavor_id="m1.small",
        )
        assert req.profile_name == "default"
        assert req.server_name == "consumer-01"

    def test_empty_server_name_uses_auto_generation(self):
        req = LayerConsumeRequest(
            profile_name="default",
            server_name="",
            flavor_id="m1.small",
        )
        assert req.server_name is None

    def test_exact_job_selector_excludes_profile_and_rejects_invalid_ids(self):
        assert LayerConsumeRequest(import_id=12, flavor_id="m1.small").import_id == 12
        for body in ({}, {"profile_name": "default", "import_id": 12}, {"import_id": 0}, {"import_id": -1}):
            with pytest.raises(ValidationError):
                LayerConsumeRequest(flavor_id="m1.small", **body)

    # --- server_name 검증 ---

    def test_server_name_with_semicolon_rejected(self):
        with pytest.raises(ValidationError):
            LayerConsumeRequest(
                profile_name="default",
                server_name="evil;rm",
                flavor_id="m1.small",
            )

    def test_server_name_too_long_rejected(self):
        with pytest.raises(ValidationError):
            LayerConsumeRequest(
                profile_name="default",
                server_name="a" * 64,
                flavor_id="m1.small",
            )

    def test_server_name_starting_with_hyphen_rejected(self):
        with pytest.raises(ValidationError):
            LayerConsumeRequest(
                profile_name="default",
                server_name="-bad-name",
                flavor_id="m1.small",
            )

    def test_server_name_with_newline_rejected(self):
        with pytest.raises(ValidationError):
            LayerConsumeRequest(
                profile_name="default",
                server_name="server\nevil",
                flavor_id="m1.small",
            )

    # --- flavor_id 검증 ---

    def test_flavor_id_with_semicolon_rejected(self):
        with pytest.raises(ValidationError):
            LayerConsumeRequest(
                profile_name="default",
                server_name="test",
                flavor_id="m1.small;evil",
            )

    def test_flavor_id_with_space_rejected(self):
        with pytest.raises(ValidationError):
            LayerConsumeRequest(
                profile_name="default",
                server_name="test",
                flavor_id="m1 small",
            )

    # --- profile_name 검증 ---

    def test_consume_profile_name_with_injection_rejected(self):
        with pytest.raises(ValidationError):
            LayerConsumeRequest(
                profile_name="default$(id)",
                server_name="test",
                flavor_id="m1.small",
            )

    def test_ssh_username_without_key_name_rejected(self):
        with pytest.raises(ValidationError):
            LayerConsumeRequest(
                profile_name="default",
                server_name="consumer-01",
                flavor_id="m1.small",
                ssh_username="ubuntu",
            )

    def test_ssh_username_with_manual_public_key_accepted(self):
        req = LayerConsumeRequest(
            profile_name="default",
            server_name="consumer-01",
            flavor_id="m1.small",
            ssh_public_key="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITest termius by jung:admin #note",
            ssh_username="ubuntu",
        )
        assert req.ssh_username == "ubuntu"


# ============================================================================
# Part 2: 인증/인가 가드 — 비인증(401) · 일반 사용자(403)
# ============================================================================


@pytest.mark.asyncio
async def test_old_admin_layers_prefix_not_mounted(admin_client):
    """Clean cutover: legacy admin layers API prefix is not mounted."""
    resp = await admin_client.get(f"{OLD_BASE}/builds")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_base_images_filters_active_ubuntu(admin_client, mock_conn):
    mock_conn.image.images.return_value = iter(
        [
            SimpleNamespace(
                id="img-22",
                name="ubuntu-22.04-gpu",
                status="active",
                os_distro="ubuntu",
                os_version="22.04",
                size=1,
                min_disk=20,
                min_ram=1024,
                disk_format="qcow2",
                visibility="shared",
                owner="admin",
                checksum="sum",
                os_hash_algo="sha256",
                os_hash_value="hash",
                created_at=None,
            ),
            SimpleNamespace(
                id="img-inactive", name="ubuntu-22.04", status="queued", os_distro="ubuntu", os_version="22.04"
            ),
            SimpleNamespace(id="img-debian", name="debian-12", status="active", os_distro="debian", os_version="12"),
        ]
    )

    resp = await admin_client.get(f"{BASE}/base-images")

    assert resp.status_code == 200
    assert resp.json() == [
        {
            "id": "img-22",
            "name": "ubuntu-22.04-gpu",
            "status": "active",
            "ubuntu_base": "ubuntu-22.04",
            "size": 1,
            "min_disk": 20,
            "min_ram": 1024,
            "disk_format": "qcow2",
            "visibility": "shared",
            "owner": "admin",
            "checksum": "sum",
            "os_hash_algo": "sha256",
            "os_hash_value": "hash",
            "created_at": None,
        }
    ]


@pytest.mark.asyncio
async def test_options_preflight_works_without_catchall_route():
    """CORS middleware handles OPTIONS without a catch-all route that masks 404s."""
    origin = get_settings().cors_origin_list[0]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.options(OLD_BASE, headers={"origin": origin})
    assert resp.status_code == 200
    assert resp.headers["Access-Control-Allow-Origin"] == origin


@pytest.mark.asyncio
async def test_build_requires_auth():
    """비인증 요청은 401을 반환한다."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(f"{BASE}/build", json={"layer_name": "uv", "kind": "uv"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_builds_list_requires_auth():
    """GET /builds 비인증 → 401."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(f"{BASE}/builds")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_consume_requires_auth():
    """POST /consume 비인증 → 401."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            f"{BASE}/consume",
            json={"profile_name": "default", "server_name": "test", "flavor_id": "m1.small"},
        )
    assert resp.status_code == 401
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(f"{BASE}/consume", json={"import_id": 7, "flavor_id": "m1.small"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_build_requires_admin_role(non_admin_client):
    """admin 역할 없는 사용자는 403을 반환한다."""
    resp = await non_admin_client.post(
        f"{BASE}/build",
        json={"layer_name": "uv", "kind": "uv"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_builds_list_requires_admin_role(non_admin_client):
    """GET /builds — admin 역할 없는 사용자는 403."""
    resp = await non_admin_client.get(f"{BASE}/builds")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_import_consume_requires_admin_role(non_admin_client):
    response = await non_admin_client.post(f"{BASE}/consume", json={"import_id": 7, "flavor_id": "m1.small"})
    assert response.status_code == 403


# ============================================================================
# Part 3: 빌드 트리거 성공 흐름
# ============================================================================


@pytest.mark.asyncio
async def test_trigger_build_success(admin_client, mock_conn):
    """POST /build → root uv 빌드는 Glance base image를 검증해 start_layer_build를 호출한다."""
    mock_result = {"build_id": 42, "layer_name": "uv", "status": "queued"}
    mock_conn.image.get_image.return_value = SimpleNamespace(
        id="img-22",
        name="ubuntu-22.04",
        status="active",
        os_distro="ubuntu",
        os_version="22.04",
        checksum="sum",
        os_hash_algo="sha256",
        os_hash_value="hash",
        min_disk=20,
        visibility="shared",
        owner="admin",
    )

    with patch(
        "app.services.layer_builder.start_layer_build",
        new_callable=AsyncMock,
        return_value=mock_result,
    ) as mock_start:
        resp = await admin_client.post(
            f"{BASE}/build",
            json={"layer_name": "uv", "kind": "uv", "ubuntu_base": "ubuntu-22.04", "base_image_id": "img-22"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["build_id"] == 42
    assert data["layer_name"] == "uv"
    assert data["status"] == "queued"
    assert mock_start.await_args.kwargs["kind"] == "uv"
    assert mock_start.await_args.kwargs["parent_artifact_id"] is None
    assert mock_start.await_args.kwargs["ubuntu_base"] == "ubuntu-22.04"
    assert mock_start.await_args.kwargs["base_image_snapshot"]["base_image_id"] == "img-22"


@pytest.mark.asyncio
async def test_trigger_system_build_success(admin_client, mock_conn):
    """POST /build kind=system forwards apt packages without a parent."""
    mock_result = {"build_id": 43, "layer_name": "sys-tools", "status": "queued"}
    mock_conn.image.get_image.return_value = SimpleNamespace(
        id="img-20",
        name="ubuntu-20.04",
        status="active",
        os_distro="ubuntu",
        os_version="20.04",
        checksum="sum",
        os_hash_algo="sha256",
        os_hash_value="hash",
        min_disk=20,
        visibility="shared",
        owner="admin",
    )

    with patch(
        "app.services.layer_builder.start_layer_build",
        new_callable=AsyncMock,
        return_value=mock_result,
    ) as mock_start:
        resp = await admin_client.post(
            f"{BASE}/build",
            json={
                "layer_name": "sys-tools",
                "kind": "system",
                "apt_packages": ["curl", "nfs-common"],
                "ubuntu_base": "ubuntu-20.04",
                "base_image_id": "img-20",
            },
        )

    assert resp.status_code == 200
    assert mock_start.await_args.kwargs["kind"] == "system"
    assert mock_start.await_args.kwargs["apt_packages"] == ["curl", "nfs-common"]
    assert mock_start.await_args.kwargs["parent_artifact_id"] is None
    assert mock_start.await_args.kwargs["ubuntu_base"] == "ubuntu-20.04"


@pytest.mark.asyncio
async def test_trigger_nvidia_build_success_forwards_safe_template_metadata(admin_client, mock_conn):
    """POST /build kind=nvidia forwards branch and computed apt metadata without a parent."""
    mock_result = {"build_id": 44, "layer_name": "nvidia-driver", "status": "queued"}
    mock_conn.image.get_image.return_value = SimpleNamespace(
        id="img-24",
        name="ubuntu-24.04",
        status="active",
        os_distro="ubuntu",
        os_version="24.04",
        checksum="sum",
        os_hash_algo="sha256",
        os_hash_value="hash",
        min_disk=20,
        visibility="shared",
        owner="admin",
    )

    with patch(
        "app.services.layer_builder.start_layer_build",
        new_callable=AsyncMock,
        return_value=mock_result,
    ) as mock_start:
        resp = await admin_client.post(
            f"{BASE}/build",
            json={
                "layer_name": "nvidia-driver",
                "kind": "nvidia",
                "nvidia_driver_branch": "570",
                "ubuntu_base": "ubuntu-24.04",
                "base_image_id": "img-24",
            },
        )

    assert resp.status_code == 200
    kwargs = mock_start.await_args.kwargs
    assert kwargs["kind"] == "nvidia"
    assert kwargs["nvidia_driver_branch"] == "570"
    assert kwargs["apt_packages"] == [
        "ca-certificates",
        "curl",
        "gnupg",
        "linux-headers-$(uname -r)",
        "dkms",
        "kmod",
        "nvidia-dkms-570-open",
        "libnvidia-compute-570",
        "nvidia-utils-570",
    ]
    assert kwargs["parent_artifact_id"] is None
    assert kwargs["ubuntu_base"] == "ubuntu-24.04"
    assert kwargs["base_image_snapshot"]["base_image_id"] == "img-24"


@pytest.mark.asyncio
async def test_trigger_system_build_rejects_parent(admin_client):
    """kind=system is a root layer and rejects parent before starting a build."""
    with patch("app.services.layer_builder.start_layer_build", new_callable=AsyncMock) as mock_start:
        resp = await admin_client.post(
            f"{BASE}/build",
            json={"layer_name": "sys-tools", "kind": "system", "apt_packages": ["curl"], "parent_artifact_id": 7},
        )

    assert resp.status_code == 422
    mock_start.assert_not_awaited()


@pytest.mark.asyncio
async def test_trigger_build_invalid_layer_name(admin_client):
    """유효하지 않은 layer_name(명령주입)은 422를 반환한다."""
    resp = await admin_client.post(
        f"{BASE}/build",
        json={"layer_name": "evil$(id)", "python_version": "3.11"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_trigger_build_invalid_python_version(admin_client):
    """유효하지 않은 python_version 형식은 422를 반환한다."""
    resp = await admin_client.post(
        f"{BASE}/build",
        json={"layer_name": "test", "kind": "python", "python_version": "3.11.2", "parent_artifact_id": 7},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_trigger_build_invalid_pip_package(admin_client):
    """pip 패키지에 셸 메타문자가 포함되면 422를 반환한다."""
    resp = await admin_client.post(
        f"{BASE}/build",
        json={
            "layer_name": "test",
            "kind": "pip",
            "parent_artifact_id": 7,
            "pip_packages": ["numpy;rm -rf /"],
        },
    )
    assert resp.status_code == 422


# ============================================================================
# Part 4: 빌드 목록 / 상세 조회
# ============================================================================


def _make_build_row(build_id: int = 1) -> MagicMock:
    row = MagicMock()
    row.id = build_id
    row.layer_name = "uvpy311"
    row.python_version = "3.11"
    row.profile_name = "smoke"
    row.kind = "python"
    row.pip_packages = []
    row.apt_packages = []
    row.ubuntu_base = "ubuntu-24.04-server-2026-04-15"
    row.share_id = "share-rw-uuid"
    row.server_id = None
    row.port_id = None
    row.build_token = None
    row.cloud_init_status = "queued"
    row.status = "queued"
    row.progress_step = "빌드 대기"
    row.progress_pct = 0
    row.error_message = None
    row.console_log_excerpt = None
    row.started_at = None
    row.completed_at = None
    row.created_at = MagicMock()
    row.created_at.isoformat.return_value = "2026-06-18T00:00:00+00:00"
    return row


@pytest.mark.asyncio
async def test_list_builds_success(admin_client):
    """GET /builds → 목록 반환."""
    mock_row = _make_build_row()

    with patch("app.api.union.layer_ops.get_session_factory") as mock_factory:
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[mock_row]))))
        )
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value.return_value = mock_cm

        resp = await admin_client.get(f"{BASE}/builds")

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert data[0]["kind"] == "python"
    assert data[0]["apt_packages"] == []
    assert data[0]["ubuntu_base"] == "ubuntu-24.04"


@pytest.mark.asyncio
async def test_get_build_detail_not_found(admin_client):
    """GET /builds/{id} — 존재하지 않는 빌드 ID → 404."""
    with patch("app.api.union.layer_ops.get_session_factory") as mock_factory:
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value.return_value = mock_cm

        resp = await admin_client.get(f"{BASE}/builds/9999")

    assert resp.status_code == 404


# ============================================================================
# Part 5: 빌드 취소
# ============================================================================


@pytest.mark.asyncio
async def test_cancel_build_success(admin_client):
    """POST /builds/{id}/cancel → 취소 성공."""
    mock_result = {"cancelled": True, "layer_name": "uvpy311"}

    with patch(
        "app.services.layer_builder.cancel_layer_build",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        resp = await admin_client.post(f"{BASE}/builds/1/cancel")

    assert resp.status_code == 200
    data = resp.json()
    assert data["cancelled"] is True


@pytest.mark.asyncio
async def test_cancel_build_not_found(admin_client):
    """POST /builds/{id}/cancel — 없는 빌드 ID → 404."""
    with patch(
        "app.services.layer_builder.cancel_layer_build",
        new_callable=AsyncMock,
        side_effect=KeyError("빌드 9999를 찾을 수 없습니다"),
    ):
        resp = await admin_client.post(f"{BASE}/builds/9999/cancel")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cancel_build_already_terminal(admin_client):
    """POST /builds/{id}/cancel — 이미 완료된 빌드 → 409."""
    with patch(
        "app.services.layer_builder.cancel_layer_build",
        new_callable=AsyncMock,
        side_effect=ValueError("이미 종료된 빌드입니다 (상태: complete)"),
    ):
        resp = await admin_client.post(f"{BASE}/builds/1/cancel")

    assert resp.status_code == 409


# ============================================================================
# Part 6: 소비 인스턴스 생성
# ============================================================================


@pytest.mark.asyncio
async def test_trigger_consume_invalid_server_name(admin_client):
    """유효하지 않은 server_name → 422."""
    resp = await admin_client.post(
        f"{BASE}/consume",
        json={
            "profile_name": "default",
            "server_name": "evil;evil",
            "flavor_id": "m1.small",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_trigger_consume_invalid_profile_name(admin_client):
    """profile_name 명령주입 → 422."""
    resp = await admin_client.post(
        f"{BASE}/consume",
        json={
            "profile_name": "default$(id)",
            "server_name": "consumer-01",
            "flavor_id": "m1.small",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_trigger_consume_propagates_runner_errors(admin_client):
    snapshot = {
        "network": {"id": "net-1", "name": "network"},
        "flavor": {"id": "flavor-1", "name": "m1.small"},
        "openstack.service_project": {"id": "service-project", "name": "service"},
    }
    with (
        patch(
            "app.services.layer_build.resolve_layer_consume_resource_snapshot",
            new_callable=AsyncMock,
            return_value=snapshot,
        ),
        patch("app.database.get_session_factory", return_value=None),
        patch(
            "app.services.layer_build.run_layer_consume",
            new_callable=AsyncMock,
            side_effect=RuntimeError("consume resource snapshot is incomplete"),
        ),
        patch(
            "app.services.layer_build.resolve_admin_consume_artifacts", new_callable=AsyncMock, return_value=[{"id": 1}]
        ),
        patch("app.services.layer_build.validate_consume_image_identity", new_callable=AsyncMock),
        patch("app.services.keystone.get_admin_connection_for_project", return_value=MagicMock()),
    ):
        resp = await admin_client.post(
            f"{BASE}/consume",
            json={"profile_name": "default", "server_name": "consumer-01", "flavor_id": "m1.small"},
        )

    assert resp.status_code == 400
    assert "resource snapshot" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_trigger_consume_uses_completed_job_artifact_ids_not_current_profile(admin_client):
    snapshot = {
        "network": {"id": "net-1", "name": "network"},
        "flavor": {"id": "flavor-1", "name": "m1.small"},
        "openstack.service_project": {"id": "service-project", "name": "service"},
    }
    with (
        patch(
            "app.services.layer_build.resolve_layer_consume_resource_snapshot",
            new_callable=AsyncMock,
            return_value=snapshot,
        ),
        patch(
            "app.services.layer_build.resolve_import_consume_artifacts",
            new_callable=AsyncMock,
            return_value=("historical-profile", [{"id": 1}, {"id": 4}]),
        ) as resolve,
        patch("app.services.layer_build.resolve_admin_consume_artifacts", new_callable=AsyncMock) as current_profile,
        patch("app.services.layer_build.validate_consume_image_identity", new_callable=AsyncMock),
        patch("app.services.layer_build.run_layer_consume", new_callable=AsyncMock, return_value="vm-1") as run,
        patch("app.services.keystone.get_admin_connection_for_project", return_value=MagicMock()),
        patch("app.database.get_session_factory", return_value=None),
    ):
        response = await admin_client.post(f"{BASE}/consume", json={"import_id": 7, "flavor_id": "m1.small"})
    assert response.status_code == 200
    resolve.assert_awaited_once_with(7)
    current_profile.assert_not_awaited()
    assert run.await_args.kwargs["resolved_artifacts"] == [{"id": 1}, {"id": 4}]
    assert run.await_args.kwargs["profile_name"] == "historical-profile"


@pytest.mark.asyncio
async def test_trigger_consume_unknown_flavor_returns_400(admin_client):
    with patch(
        "app.services.layer_build.resolve_layer_consume_resource_snapshot",
        new_callable=AsyncMock,
        side_effect=RuntimeError("플레이버를 찾을 수 없습니다: 'cpu.4c_8g'"),
    ):
        resp = await admin_client.post(
            f"{BASE}/consume",
            json={"profile_name": "default", "server_name": "consumer-01", "flavor_id": "cpu.4c_8g"},
        )

    assert resp.status_code == 400
    assert "플레이버를 찾을 수 없습니다" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_trigger_consume_unknown_keypair_returns_400(admin_client, mock_conn):
    """선택한 keypair의 공개키를 못 찾으면 DB 생성 전에 400으로 거부한다."""
    mock_conn.compute.get_keypair.side_effect = Exception("missing")
    mock_conn.compute.find_keypair.return_value = None

    with (
        patch("app.config.get_settings") as mock_settings,
        patch("app.database.get_session_factory") as mock_factory,
        patch("app.services.layer_build.run_layer_consume", new_callable=AsyncMock) as mock_consume,
    ):
        mock_settings.return_value = MagicMock(union_layer_store_ro_share_id="share-ro-1")
        mock_factory.return_value = MagicMock()

        resp = await admin_client.post(
            f"{BASE}/consume",
            json={
                "profile_name": "default",
                "server_name": "consumer-01",
                "flavor_id": "cpu.4c_8g",
                "key_name": "missing-keypair",
            },
        )

    assert resp.status_code == 400
    assert "공개키를 조회할 수 없습니다" in resp.json()["detail"]
    mock_factory.assert_not_called()
    mock_consume.assert_not_awaited()


# ============================================================================
# Part 7: Pydantic 화이트리스트 검증 — LayerProfileRequest
# ============================================================================


class TestLayerProfileRequestValidation:
    """LayerProfileRequest 입력값 화이트리스트 검증."""

    def test_valid_request_accepted(self):
        req = LayerProfileRequest(name="default", layers=["uv-latest", "python-latest"])
        assert req.name == "default"
        assert req.layers == ["uv-latest", "python-latest"]

    def test_name_with_injection_rejected(self):
        with pytest.raises(ValidationError):
            LayerProfileRequest(name="profile$(id)", layers=["uv-latest"])

    def test_name_with_newline_rejected(self):
        with pytest.raises(ValidationError):
            LayerProfileRequest(name="profile\nevil", layers=["uv-latest"])

    def test_empty_layers_rejected(self):
        with pytest.raises(ValidationError):
            LayerProfileRequest(name="default", layers=[])

    def test_layer_with_injection_rejected(self):
        with pytest.raises(ValidationError):
            LayerProfileRequest(name="default", layers=["uv-latest;evil"])

    def test_layer_with_newline_rejected(self):
        with pytest.raises(ValidationError):
            LayerProfileRequest(name="default", layers=["uv\nevil"])


# ============================================================================
# Part 8: GET /artifacts 엔드포인트
# ============================================================================


class TestListArtifacts:
    """GET /artifacts — 아티팩트 목록."""

    @pytest.mark.asyncio
    async def test_list_artifacts_requires_admin(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(f"{BASE}/artifacts")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_list_artifacts_success(self, admin_client):
        from app.models.db import LayerArtifact

        with patch("app.api.union.layer_ops.get_session_factory") as mock_factory:
            mock_session = AsyncMock()
            mock_row = MagicMock(spec=LayerArtifact)
            mock_row.id = 1
            mock_row.name = "uv"
            mock_row.kind = "uv"
            mock_row.python_version = None
            mock_row.sqsh_filename = "uv-latest.sqsh"
            mock_row.share_id = "share-abc"
            mock_row.build_id = 1
            mock_row.size_bytes = None
            mock_row.created_at = None
            mock_row.ubuntu_base = "ubuntu-24.04"
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_row]
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cm.__aexit__ = AsyncMock(return_value=False)
            mock_factory.return_value.return_value = mock_cm

            resp = await admin_client.get(f"{BASE}/artifacts")

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert data[0]["name"] == "uv"
        assert data[0]["kind"] == "uv"


# ============================================================================
# Part 9: POST /profiles 엔드포인트
# ============================================================================


class TestUpsertProfile:
    """POST /profiles — 레이어 프로필 upsert."""

    @pytest.mark.asyncio
    async def test_upsert_profile_requires_admin(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(f"{BASE}/profiles", json={"name": "default", "layers": ["uv-latest"]})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_upsert_profile_name_injection_rejected(self, admin_client):
        """프로필 이름 인젝션 — 422 Unprocessable Entity."""
        resp = await admin_client.post(
            f"{BASE}/profiles",
            json={"name": "evil$(id)", "layers": ["uv-latest"]},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_upsert_profile_empty_layers_rejected(self, admin_client):
        """빈 레이어 리스트 — 422."""
        resp = await admin_client.post(
            f"{BASE}/profiles",
            json={"name": "default", "layers": []},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_upsert_profile_missing_artifact_rejected(self, admin_client):
        """존재하지 않는 레이어 참조 — 400."""
        with patch("app.api.union.layer_ops.get_session_factory") as mock_factory:
            mock_session = AsyncMock()
            # artifact 조회 → 빈 결과
            mock_art_result = MagicMock()
            mock_art_result.scalars.return_value.all.return_value = []
            # profile 조회 → 없음
            mock_prof_result = MagicMock()
            mock_prof_result.scalar_one_or_none.return_value = None
            mock_session.execute = AsyncMock(side_effect=[mock_art_result, mock_prof_result])
            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cm.__aexit__ = AsyncMock(return_value=False)
            mock_factory.return_value.return_value = mock_cm

            resp = await admin_client.post(
                f"{BASE}/profiles",
                json={"name": "default", "layers": ["nonexistent-latest"]},
            )
        assert resp.status_code == 400
        assert "존재하지 않는 레이어" in resp.json()["detail"]


class TestDeleteProfile:
    """DELETE /profiles/{profile_name} — live consume 보호 + stale consume 정리."""

    @pytest.mark.asyncio
    async def test_delete_profile_requires_admin(self, non_admin_client):
        resp = await non_admin_client.delete(f"{BASE}/profiles/default")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_profile_missing_returns_404(self, admin_client):
        with patch("app.api.union.layer_ops.get_session_factory") as mock_factory:
            mock_session = AsyncMock()
            mock_session.execute = AsyncMock(return_value=_scalar_result(None))
            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cm.__aexit__ = AsyncMock(return_value=False)
            mock_factory.return_value.return_value = mock_cm

            resp = await admin_client.delete(f"{BASE}/profiles/missing")

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_profile_blocks_active_consume_vm(self, admin_client):
        profile = _profile(layers=["python311"])
        consume = _consume(status="active", server_id="srv-1")
        conn = MagicMock()
        conn.compute.get_server.return_value = MagicMock(status="ACTIVE")

        with (
            patch("app.api.union.layer_ops.get_session_factory") as mock_factory,
            patch("app.services.keystone.get_service_project_connection", return_value=conn),
        ):
            mock_session = AsyncMock()
            mock_session.execute = AsyncMock(
                side_effect=[
                    _scalar_result(profile),
                    _scalars_result([consume]),
                ]
            )
            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cm.__aexit__ = AsyncMock(return_value=False)
            mock_factory.return_value.return_value = mock_cm

            resp = await admin_client.delete(f"{BASE}/profiles/default")

        assert resp.status_code == 409
        body = resp.json()["detail"]
        assert body["message"] == "프로필을 사용 중인 소비 인스턴스가 있습니다"
        assert body["active_consume_references"][0]["id"] == consume.id
        mock_session.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_profile_marks_stale_consume_deleted_then_deletes(self, admin_client):
        from openstack import exceptions as openstack_exceptions

        profile = _profile(layers=["python311"])
        consume = _consume(status="active", server_id="srv-1")
        conn = MagicMock()
        conn.compute.get_server.side_effect = openstack_exceptions.NotFoundException("missing")

        with (
            patch("app.api.union.layer_ops.get_session_factory") as mock_factory,
            patch("app.services.keystone.get_service_project_connection", return_value=conn),
        ):
            mock_session = AsyncMock()
            mock_session.execute = AsyncMock(
                side_effect=[
                    _scalar_result(profile),
                    _scalars_result([consume]),
                ]
            )
            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cm.__aexit__ = AsyncMock(return_value=False)
            mock_factory.return_value.return_value = mock_cm

            resp = await admin_client.delete(f"{BASE}/profiles/default")

        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        assert consume.status == "deleted"
        assert consume.completed_at is not None
        mock_session.delete.assert_awaited_once_with(profile)
        assert mock_session.commit.await_count == 2


@pytest.mark.asyncio
async def test_nova_active_or_reboot_does_not_publish_unverified_consume():
    from app.api.union.layer_ops import _sync_consume_rows_with_nova

    row = _consume(status="creating", server_id="srv-1")
    conn = MagicMock()
    session = AsyncMock()
    with patch("app.services.keystone.get_service_project_connection", return_value=conn):
        for nova_state in ("ACTIVE", "SHUTOFF", "ACTIVE"):
            conn.compute.get_server.return_value = MagicMock(status=nova_state)
            await _sync_consume_rows_with_nova(session, [row])
    assert row.status == "creating"
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_consumes_marks_missing_server_deleted(admin_client):
    """GET /consumes — active DB row라도 Nova 서버가 없으면 deleted로 동기화한다."""
    consume = _consume(status="active", server_id="srv-1")
    conn = MagicMock()
    conn.compute.get_server.return_value = None

    with (
        patch("app.api.union.layer_ops.get_session_factory") as mock_factory,
        patch("app.services.keystone.get_service_project_connection", return_value=conn),
    ):
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=_scalars_result([consume]))
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value.return_value = mock_cm

        resp = await admin_client.get(f"{BASE}/consumes")

    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["status"] == "deleted"
    assert "vm_status" not in data[0]
    assert consume.completed_at is not None


@pytest.mark.asyncio
async def test_list_consumes_marks_stale_no_server_consume_deleted(admin_client):
    """GET /consumes — server_id 없이 오래 멈춘 creating row는 orphan으로 보고 deleted 처리한다."""
    old = datetime.now(UTC) - timedelta(hours=2)
    consume = _consume(status="creating", server_id=None)
    consume.created_at = old
    consume.updated_at = old

    with patch("app.api.union.layer_ops.get_session_factory") as mock_factory:
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=_scalars_result([consume]))
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value.return_value = mock_cm

        resp = await admin_client.get(f"{BASE}/consumes")

    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["status"] == "deleted"
    assert consume.completed_at is not None
    mock_session.commit.assert_awaited_once()


def test_delete_preview_ignores_deleted_consume_reference():
    """삭제된 consume은 artifact 삭제의 active consume blocker가 아니다."""
    target = _artifact(2, "python311", pip_packages=["numpy"])
    profile = _profile(layers=["python311"])
    consume = _consume(status="deleted", server_id="srv-1")

    preview = _artifact_delete_preview(target, [target], [profile], [consume], [])

    assert preview["active_consume_references"] == []
    assert {b["type"] for b in preview["delete_blockers"]} == {"profile_references"}


def test_delete_preview_blocks_direct_consume_artifact_reference():
    """직접 public consume이 artifact_ids로 참조 중인 artifact 삭제를 차단한다."""
    target = _artifact(2, "python311", pip_packages=["numpy"])
    consume = _consume(profile_name="direct-ab12cd34", status="active", server_id="srv-1", artifact_ids=[1, 2])

    preview = _artifact_delete_preview(target, [target], [], [consume], [])

    assert preview["can_delete"] is False
    assert preview["active_consume_references"][0]["artifact_ids"] == [1, 2]
    assert {b["type"] for b in preview["delete_blockers"]} == {"active_consume_references"}


# ============================================================================
# Part 10: Stacked 빌드 — parent 필드 검증 + 부모 artifact 조회
# ============================================================================


class TestLayerBuildRequestParentValidation:
    """LayerBuildRequest.parent 필드 및 stacked 빌드 관련 Pydantic 검증."""

    def test_valid_parent_name_accepted_for_python_runtime(self):
        req = LayerBuildRequest(
            layer_name="python311",
            kind="python",
            python_version="3.11",
            parent="uv-base",
        )
        assert req.parent == "uv-base"
        assert req.python_version == "3.11"

    def test_parent_with_injection_rejected(self):
        with pytest.raises(ValidationError):
            LayerBuildRequest(layer_name="torch", kind="pip", parent="$(id)", pip_packages=["torch"])

    def test_parent_with_newline_rejected(self):
        with pytest.raises(ValidationError):
            LayerBuildRequest(layer_name="torch", kind="pip", parent="uv\nevil", pip_packages=["torch"])

    def test_parent_with_slash_rejected(self):
        with pytest.raises(ValidationError):
            LayerBuildRequest(layer_name="torch", kind="pip", parent="uv/evil", pip_packages=["torch"])

    def test_parent_artifact_id_accepted_with_python_version(self):
        req = LayerBuildRequest(layer_name="python311", kind="python", python_version="3.11", parent_artifact_id=7)
        assert req.parent_artifact_id == 7
        assert req.python_version == "3.11"

    def test_parent_and_parent_artifact_id_together_rejected(self):
        with pytest.raises(ValidationError):
            LayerBuildRequest(
                layer_name="python311",
                kind="python",
                python_version="3.11",
                parent="uv",
                parent_artifact_id=7,
            )

    def test_parent_artifact_id_must_be_positive(self):
        with pytest.raises(ValidationError):
            LayerBuildRequest(layer_name="torch", kind="pip", parent_artifact_id=0, pip_packages=["torch"])

    def test_python_kind_with_parent_no_version_rejected(self):
        with pytest.raises(ValidationError):
            LayerBuildRequest(layer_name="py311-stacked", kind="python", parent="uv-base")


@pytest.mark.asyncio
async def test_trigger_build_stacked_parent_not_found(admin_client):
    """POST /build — parent 지정했지만 봉인된 artifact 없음 → 404."""
    with patch("app.api.union.layer_ops.get_session_factory") as mock_factory:
        mock_session = AsyncMock()
        # 부모 조회 결과 없음
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value.return_value = mock_cm

        resp = await admin_client.post(
            f"{BASE}/build",
            json={
                "layer_name": "torch",
                "kind": "pip",
                "parent": "nonexistent-uv",
                "pip_packages": ["torch"],
            },
        )

    assert resp.status_code == 404
    assert "nonexistent-uv" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_trigger_python_build_requires_direct_uv_parent(admin_client):
    """kind=python은 직접 uv 부모에서만 시작된다."""
    parent = _artifact(7, "uv", kind="uv", python_version=None)
    mock_result = {"build_id": 99, "layer_name": "python311", "parent_artifact_id": 7, "status": "queued"}

    with (
        patch("app.api.union.layer_ops.get_session_factory") as mock_factory,
        patch(
            "app.services.layer_builder.start_layer_build",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_start,
    ):
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=parent)
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value.return_value = mock_cm

        resp = await admin_client.post(
            f"{BASE}/build",
            json={"layer_name": "python311", "kind": "python", "python_version": "3.11", "parent_artifact_id": 7},
        )

    assert resp.status_code == 200
    assert mock_start.await_args.kwargs["kind"] == "python"
    assert mock_start.await_args.kwargs["python_version"] == "3.11"
    assert mock_start.await_args.kwargs["pip_packages"] == []
    assert mock_start.await_args.kwargs["parent_artifact_id"] == 7
    assert mock_start.await_args.kwargs["ubuntu_base"] == "ubuntu-24.04"


@pytest.mark.asyncio
async def test_trigger_python_build_inherits_parent_ubuntu_base(admin_client):
    """kind=python derives ubuntu_base from its direct uv parent."""
    parent = _artifact(7, "uv", kind="uv", python_version=None, ubuntu_base="ubuntu-20.04")
    mock_result = {"build_id": 102, "layer_name": "python311", "parent_artifact_id": 7, "status": "queued"}

    with (
        patch("app.api.union.layer_ops.get_session_factory") as mock_factory,
        patch(
            "app.services.layer_builder.start_layer_build",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_start,
    ):
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=parent)
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value.return_value = mock_cm

        resp = await admin_client.post(
            f"{BASE}/build",
            json={"layer_name": "python311", "kind": "python", "python_version": "3.11", "parent_artifact_id": 7},
        )

    assert resp.status_code == 200
    assert mock_start.await_args.kwargs["ubuntu_base"] == "ubuntu-20.04"


@pytest.mark.asyncio
async def test_trigger_python_build_rejects_explicit_ubuntu_base_mismatch(admin_client):
    """Child ubuntu_base cannot override the parent OS lineage."""
    parent = _artifact(7, "uv", kind="uv", python_version=None, ubuntu_base="ubuntu-20.04")

    with (
        patch("app.api.union.layer_ops.get_session_factory") as mock_factory,
        patch("app.services.layer_builder.start_layer_build", new_callable=AsyncMock) as mock_start,
    ):
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=parent)
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value.return_value = mock_cm

        resp = await admin_client.post(
            f"{BASE}/build",
            json={
                "layer_name": "python311",
                "kind": "python",
                "python_version": "3.11",
                "parent_artifact_id": 7,
                "ubuntu_base": "ubuntu-22.04",
            },
        )

    assert resp.status_code == 400
    assert "ubuntu_base" in resp.json()["detail"]
    mock_start.assert_not_awaited()


@pytest.mark.asyncio
async def test_trigger_python_build_rejects_non_uv_direct_parent(admin_client):
    """kind=python + 직접 parent kind=python은 400이고 빌드를 시작하지 않는다."""
    parent = _artifact(7, "python311", kind="python", python_version="3.11")

    with (
        patch("app.api.union.layer_ops.get_session_factory") as mock_factory,
        patch("app.services.layer_builder.start_layer_build", new_callable=AsyncMock) as mock_start,
    ):
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=parent)
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value.return_value = mock_cm

        resp = await admin_client.post(
            f"{BASE}/build",
            json={"layer_name": "python312", "kind": "python", "python_version": "3.12", "parent_artifact_id": 7},
        )

    assert resp.status_code == 400
    assert "Python 레이어의 부모는 uv 레이어여야 합니다" in resp.json()["detail"]
    mock_start.assert_not_awaited()


@pytest.mark.asyncio
async def test_trigger_python_build_rejects_system_direct_parent(admin_client):
    """kind=python still requires a direct uv parent, not a system apt root layer."""
    parent = _artifact(7, "sys-tools", kind="system", python_version=None, apt_packages=["curl"])

    with (
        patch("app.api.union.layer_ops.get_session_factory") as mock_factory,
        patch("app.services.layer_builder.start_layer_build", new_callable=AsyncMock) as mock_start,
    ):
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=parent)
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value.return_value = mock_cm

        resp = await admin_client.post(
            f"{BASE}/build",
            json={"layer_name": "python312", "kind": "python", "python_version": "3.12", "parent_artifact_id": 7},
        )

    assert resp.status_code == 400
    assert "Python 레이어의 부모는 uv 레이어여야 합니다" in resp.json()["detail"]
    mock_start.assert_not_awaited()


@pytest.mark.asyncio
async def test_trigger_pip_build_accepts_direct_python_parent(admin_client):
    """kind=pip + 직접 parent kind=python이면 package delta 빌드를 시작한다."""
    parent = _artifact(7, "python311", kind="python", python_version="3.11")
    mock_result = {"build_id": 100, "layer_name": "numpy-stack", "parent_artifact_id": 7, "status": "queued"}

    with (
        patch("app.api.union.layer_ops.get_session_factory") as mock_factory,
        patch(
            "app.services.layer_builder.start_layer_build", new_callable=AsyncMock, return_value=mock_result
        ) as mock_start,
    ):
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=parent)
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value.return_value = mock_cm

        resp = await admin_client.post(
            f"{BASE}/build",
            json={
                "layer_name": "numpy-stack",
                "kind": "pip",
                "parent_artifact_id": 7,
                "pip_packages": ["numpy==1.26.4"],
                "pip_index_url": "https://download.pytorch.org/whl/cpu",
                "pip_extra_index_urls": ["https://pypi.org/simple"],
                "pip_find_links": ["https://download.pytorch.org/whl/cpu/torch_stable.html"],
            },
        )

    assert resp.status_code == 200
    assert mock_start.await_args.kwargs["kind"] == "pip"
    assert mock_start.await_args.kwargs["python_version"] is None
    assert mock_start.await_args.kwargs["pip_packages"] == ["numpy==1.26.4"]
    assert mock_start.await_args.kwargs["parent_artifact_id"] == 7
    assert mock_start.await_args.kwargs["pip_index_url"] == "https://download.pytorch.org/whl/cpu"
    assert mock_start.await_args.kwargs["pip_extra_index_urls"] == ["https://pypi.org/simple"]
    assert mock_start.await_args.kwargs["pip_find_links"] == ["https://download.pytorch.org/whl/cpu/torch_stable.html"]
    assert mock_start.await_args.kwargs["ubuntu_base"] == "ubuntu-24.04"


@pytest.mark.asyncio
async def test_trigger_pip_build_accepts_package_parent_with_python_ancestor(admin_client):
    """kind=pip은 직접 pip 부모라도 lineage에 python ancestor가 있으면 허용한다."""
    direct_parent = _artifact(8, "numpy-stack", kind="pip", python_version=None, parent_id=7, pip_packages=["numpy"])
    python_parent = _artifact(7, "python311", kind="python", python_version="3.11")
    mock_result = {"build_id": 101, "layer_name": "scipy-stack", "parent_artifact_id": 8, "status": "queued"}

    with (
        patch("app.api.union.layer_ops.get_session_factory") as mock_factory,
        patch(
            "app.services.layer_builder.start_layer_build", new_callable=AsyncMock, return_value=mock_result
        ) as mock_start,
    ):
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(side_effect=[direct_parent, python_parent])
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value.return_value = mock_cm

        resp = await admin_client.post(
            f"{BASE}/build",
            json={
                "layer_name": "scipy-stack",
                "kind": "pip",
                "parent_artifact_id": 8,
                "pip_packages": ["scipy==1.13.1"],
            },
        )

    assert resp.status_code == 200
    assert mock_start.await_args.kwargs["kind"] == "pip"
    assert mock_start.await_args.kwargs["parent_artifact_id"] == 8
    assert mock_start.await_args.kwargs["ubuntu_base"] == "ubuntu-24.04"


@pytest.mark.asyncio
async def test_trigger_pip_build_rejects_mixed_ubuntu_lineage(admin_client):
    """kind=pip rejects parent lineage whose artifacts were built on different Ubuntu bases."""
    direct_parent = _artifact(
        8, "numpy-stack", kind="pip", python_version=None, parent_id=7, ubuntu_base="ubuntu-22.04"
    )
    python_parent = _artifact(7, "python311", kind="python", python_version="3.11", ubuntu_base="ubuntu-20.04")

    with (
        patch("app.api.union.layer_ops.get_session_factory") as mock_factory,
        patch("app.services.layer_builder.start_layer_build", new_callable=AsyncMock) as mock_start,
    ):
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(side_effect=[direct_parent, python_parent])
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value.return_value = mock_cm

        resp = await admin_client.post(
            f"{BASE}/build",
            json={
                "layer_name": "scipy-stack",
                "kind": "pip",
                "parent_artifact_id": 8,
                "pip_packages": ["scipy==1.13.1"],
            },
        )

    assert resp.status_code == 400
    assert "Ubuntu base" in resp.json()["detail"]
    mock_start.assert_not_awaited()


@pytest.mark.asyncio
async def test_trigger_pip_build_rejects_uv_only_lineage(admin_client):
    """kind=pip + uv-only lineage는 400이고 빌드를 시작하지 않는다."""
    parent = _artifact(7, "uv", kind="uv", python_version=None)

    with (
        patch("app.api.union.layer_ops.get_session_factory") as mock_factory,
        patch("app.services.layer_builder.start_layer_build", new_callable=AsyncMock) as mock_start,
    ):
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=parent)
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value.return_value = mock_cm

        resp = await admin_client.post(
            f"{BASE}/build",
            json={
                "layer_name": "numpy-stack",
                "kind": "pip",
                "parent_artifact_id": 7,
                "pip_packages": ["numpy==1.26.4"],
            },
        )

    assert resp.status_code == 400
    assert "Python 레이어" in resp.json()["detail"]
    mock_start.assert_not_awaited()


@pytest.mark.asyncio
async def test_trigger_python_build_legacy_parent_rejects_python_parent(admin_client):
    """legacy parent 이름 경로도 직접 Python 부모를 kind=python 부모로 허용하지 않는다."""
    parent = _artifact(7, "python311", kind="python", python_version="3.11")

    with (
        patch("app.api.union.layer_ops.get_session_factory") as mock_factory,
        patch("app.services.layer_builder.start_layer_build", new_callable=AsyncMock) as mock_start,
    ):
        mock_session = AsyncMock()
        mock_db_result = MagicMock()
        mock_db_result.scalar_one_or_none.return_value = parent
        mock_session.execute = AsyncMock(return_value=mock_db_result)
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value.return_value = mock_cm

        resp = await admin_client.post(
            f"{BASE}/build",
            json={"layer_name": "python312", "kind": "python", "python_version": "3.12", "parent": "python311"},
        )

    assert resp.status_code == 400
    assert "Python 레이어의 부모는 uv 레이어여야 합니다" in resp.json()["detail"]
    mock_start.assert_not_awaited()


@pytest.mark.asyncio
async def test_trigger_build_parent_artifact_id_rejects_unsealed(admin_client):
    """POST /build — unsealed parent_artifact_id는 stacked 빌드 부모로 거부한다."""
    parent = _artifact(7, "uv", kind="uv", python_version=None, is_sealed=False)

    with patch("app.api.union.layer_ops.get_session_factory") as mock_factory:
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=parent)
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value.return_value = mock_cm

        resp = await admin_client.post(
            f"{BASE}/build",
            json={"layer_name": "python311", "kind": "python", "python_version": "3.11", "parent_artifact_id": 7},
        )

    assert resp.status_code == 400
    assert "봉인" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_artifact_list_returns_lineage_and_delete_metadata(admin_client):
    """GET /artifacts — lineage, requested packages, delete blockers를 함께 반환한다."""
    root = _artifact(1, "uv", kind="uv", python_version=None)
    parent = _artifact(2, "python311", parent_id=1, pip_packages=["numpy"])
    child = _artifact(3, "torch", kind="pip", python_version=None, parent_id=2, pip_packages=["torch"])
    profile = _profile(layers=["python311"])
    consume = _consume(status="active", server_id="srv-1")
    build = _row(id=12, layer_name="scipy", status="queued", parent_artifact_id=2)
    conn = MagicMock()
    conn.compute.get_server.return_value = MagicMock(status="ACTIVE")

    with (
        patch("app.api.union.layer_ops.get_session_factory") as mock_factory,
        patch("app.services.keystone.get_service_project_connection", return_value=conn),
    ):
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            side_effect=[
                _scalars_result([child, parent, root]),
                _scalars_result([profile]),
                _scalars_result([consume]),
                _scalars_result([build]),
            ]
        )
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value.return_value = mock_cm

        resp = await admin_client.get(f"{BASE}/artifacts")

    assert resp.status_code == 200
    by_id = {row["id"]: row for row in resp.json()}
    assert [node["id"] for node in by_id[3]["lineage"]] == [1, 2, 3]
    assert by_id[3]["requested_packages"] == ["torch"]
    assert by_id[3]["apt_packages"] == []
    assert by_id[3]["ubuntu_base"] == "ubuntu-24.04"
    assert by_id[3]["lineage"][-1]["ubuntu_base"] == "ubuntu-24.04"
    assert by_id[2]["child_count"] == 1
    assert {b["type"] for b in by_id[2]["delete_blockers"]} == {
        "direct_children",
        "profile_references",
        "active_consume_references",
        "active_build_references",
    }


def test_delete_preview_ignores_timed_out_parent_build():
    """GET /artifacts/{id}/delete-preview — timeout 빌드는 terminal 상태라 삭제를 막지 않는다."""
    target = _artifact(2, "python311", pip_packages=["numpy"])
    timed_out_build = _row(id=12, layer_name="torch", status="timeout", parent_artifact_id=2)

    preview = _artifact_delete_preview(target, [target], [], [], [timed_out_build])

    assert preview["can_delete"] is True
    assert preview["active_build_references"] == []
    assert preview["delete_blockers"] == []


@pytest.mark.asyncio
async def test_list_builds_marks_stale_no_server_build_timeout(admin_client):
    """GET /builds — server_id 없이 오래 갱신되지 않은 active build는 timeout으로 동기화한다."""
    old = datetime.now(UTC) - timedelta(hours=3)
    build = _row(
        id=12,
        layer_name="torch",
        kind="pip",
        python_version=None,
        status="queued",
        cloud_init_status=None,
        progress_step="queued",
        progress_pct=0,
        error_message=None,
        console_log_excerpt=None,
        share_id=None,
        server_id=None,
        port_id=None,
        build_token=None,
        parent_artifact_id=2,
        started_at=old,
        completed_at=None,
        created_at=old,
        updated_at=old,
        ubuntu_base="ubuntu-24.04",
    )

    with patch("app.api.union.layer_ops.get_session_factory") as mock_factory:
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=_scalars_result([build]))
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value.return_value = mock_cm

        resp = await admin_client.get(f"{BASE}/builds")

    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["status"] == "timeout"
    assert build.completed_at is not None
    mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_builds_cleans_stale_build_resources_before_timeout(admin_client):
    """GET /builds — server/port/RW rule을 가진 stale build는 리소스 정리 후 timeout 처리한다."""
    old = datetime.now(UTC) - timedelta(hours=3)
    build = _row(
        id=12,
        layer_name="torch",
        kind="pip",
        python_version=None,
        status="creating_vm",
        cloud_init_status=None,
        progress_step="creating_vm",
        progress_pct=20,
        error_message=None,
        console_log_excerpt=None,
        share_id="share-12",
        server_id="srv-12",
        port_id="port-12",
        build_token=None,
        parent_artifact_id=2,
        started_at=old,
        completed_at=None,
        created_at=old,
        updated_at=old,
        ubuntu_base="ubuntu-24.04",
    )
    conn = MagicMock()
    conn.compute.get_server.return_value = MagicMock(status="BUILD")

    with (
        patch("app.api.union.layer_ops.get_session_factory") as mock_factory,
        patch("app.services.keystone.get_service_project_connection", return_value=conn),
        patch("app.services.neutron.delete_port") as mock_delete_port,
        patch(
            "app.services.manila.list_access_rules",
            return_value=[
                {"id": "rw-rule", "access_type": "ip", "access_level": "rw"},
                {"id": "ro-rule", "access_type": "ip", "access_level": "ro"},
            ],
        ),
        patch("app.services.manila.revoke_access_rule") as mock_revoke_access_rule,
    ):
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=_scalars_result([build]))
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value.return_value = mock_cm

        resp = await admin_client.get(f"{BASE}/builds")

    assert resp.status_code == 200
    assert resp.json()[0]["status"] == "timeout"
    conn.compute.delete_server.assert_called_once_with("srv-12")
    mock_delete_port.assert_called_once_with(conn, "port-12")
    mock_revoke_access_rule.assert_called_once_with(conn, "share-12", "rw-rule")
    assert build.completed_at is not None


@pytest.mark.asyncio
async def test_delete_preview_blocks_profile_and_active_consume(admin_client):
    """GET /artifacts/{id}/delete-preview — 이름 기반 profile/consume 참조를 차단한다."""
    target = _artifact(2, "python311", pip_packages=["numpy"])
    profile = _profile(layers=["python311"])
    consume = _consume(status="active", server_id="srv-1")
    conn = MagicMock()
    conn.compute.get_server.return_value = MagicMock(status="ACTIVE")

    with (
        patch("app.api.union.layer_ops.get_session_factory") as mock_factory,
        patch("app.services.keystone.get_service_project_connection", return_value=conn),
    ):
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=target)
        mock_session.execute = AsyncMock(
            side_effect=[
                _scalars_result([target]),
                _scalars_result([profile]),
                _scalars_result([consume]),
                _scalars_result([]),
            ]
        )
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value.return_value = mock_cm

        resp = await admin_client.get(f"{BASE}/artifacts/2/delete-preview")

    assert resp.status_code == 200
    body = resp.json()
    assert body["can_delete"] is False
    assert {b["type"] for b in body["delete_blockers"]} == {"profile_references", "active_consume_references"}


@pytest.mark.asyncio
async def test_delete_artifact_executes_manila_delete_after_empty_preview(admin_client):
    """DELETE /artifacts/{id} — blockers가 없을 때 access rule 회수 후 Manila share와 DB row를 삭제한다."""
    target = _artifact(9, "leaf", kind="pip", python_version=None, pip_packages=["pytest"])

    with (
        patch("app.api.union.layer_ops.get_session_factory") as mock_factory,
        patch("app.services.keystone.get_service_project_connection", return_value=MagicMock()),
        patch("app.services.manila.list_access_rules", return_value=[{"id": "rule-1"}]) as mock_rules,
        patch("app.services.manila.revoke_access_rule") as mock_revoke,
        patch("app.services.manila.delete_file_storage") as mock_delete_share,
    ):
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=target)
        mock_session.execute = AsyncMock(
            side_effect=[
                _scalars_result([target]),
                _scalars_result([]),
                _scalars_result([]),
                _scalars_result([]),
            ]
        )
        mock_session.delete = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value.return_value = mock_cm

        resp = await admin_client.delete(f"{BASE}/artifacts/9")

    assert resp.status_code == 200
    assert resp.json()["deleted"] is True
    mock_rules.assert_called_once()
    mock_revoke.assert_called_once()
    mock_delete_share.assert_called_once()
    mock_session.delete.assert_awaited_once_with(target)


@pytest.mark.asyncio
async def test_delete_artifact_refuses_before_manila_when_blocked(admin_client):
    """DELETE /artifacts/{id} — child blocker가 있으면 Manila 호출 전 409로 중단한다."""
    target = _artifact(2, "python311")
    child = _artifact(3, "torch", parent_id=2)

    with (
        patch("app.api.union.layer_ops.get_session_factory") as mock_factory,
        patch("app.services.manila.delete_file_storage") as mock_delete_share,
    ):
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=target)
        mock_session.execute = AsyncMock(
            side_effect=[
                _scalars_result([target, child]),
                _scalars_result([]),
                _scalars_result([]),
                _scalars_result([]),
            ]
        )
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value.return_value = mock_cm

        resp = await admin_client.delete(f"{BASE}/artifacts/2")

    assert resp.status_code == 409
    assert resp.json()["detail"]["can_delete"] is False
    mock_delete_share.assert_not_called()


# ============================================================================
# Part 11: artifact 응답에 parent_id / is_sealed 포함 확인
# ============================================================================


@pytest.mark.asyncio
async def test_artifact_response_includes_parent_id_and_sealed(admin_client):
    """GET /artifacts — parent_id, is_sealed 필드가 응답에 포함된다."""
    from app.models.db import LayerArtifact

    with patch("app.api.union.layer_ops.get_session_factory") as mock_factory:
        mock_session = AsyncMock()
        mock_row = MagicMock(spec=LayerArtifact)
        mock_row.id = 5
        mock_row.name = "torch"
        mock_row.kind = "pip"
        mock_row.python_version = None
        mock_row.pip_packages = ["torch"]
        mock_row.apt_packages = []
        mock_row.ubuntu_base = "ubuntu-24.04-server-2026-04-15"
        mock_row.sqsh_filename = "torch-latest.sqsh"
        mock_row.share_id = "share-xyz"
        mock_row.build_id = 3
        mock_row.size_bytes = 1024
        mock_row.parent_id = 2  # stacked: 부모 artifact ID
        mock_row.is_sealed = True
        mock_row.created_at = None
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_row]
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value.return_value = mock_cm

        resp = await admin_client.get(f"{BASE}/artifacts")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    artifact = data[0]
    assert artifact["parent_id"] == 2
    assert artifact["is_sealed"] is True
    assert artifact["kind"] == "pip"
    assert artifact["pip_packages"] == ["torch"]
    assert artifact["apt_packages"] == []
    assert artifact["ubuntu_base"] == "ubuntu-24.04"
