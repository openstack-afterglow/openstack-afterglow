"""squashfs NFS 레이어 빌드/소비 관리 API.

/api/v1/admin/libraries 접두사로 마운트. 전 엔드포인트 require_admin.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from sqlalchemy import desc, select

from app.api.deps import get_os_conn, require_admin
from app.database import get_session_factory
from app.services.cache import invalidate
from app.services.layer_base_images import (
    legacy_snapshot_for_ubuntu_base,
    list_base_images,
    resolve_base_image_snapshot,
    validate_base_image_id,
)
from app.services.layer_ubuntu import normalize_ubuntu_base
from app.utils.ssh_keys import validate_ssh_public_key

_logger = logging.getLogger(__name__)


def _iso(dt: datetime | None) -> str | None:
    """datetime → ISO 8601 문자열. naive datetime은 UTC로 간주하고 'Z' suffix 부착."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat().replace("+00:00", "Z")


router = APIRouter()

# ---------------------------------------------------------------------------
# 입력 모델 (Pydantic 화이트리스트 validator)
# ---------------------------------------------------------------------------

_LAYER_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9.+\-]*$")
_PY_VERSION_RE = re.compile(r"^\d+\.\d+$")
_PIP_SPEC_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\[\],<>=!~+*\-]*$")
_APT_PACKAGE_RE = re.compile(r"^[a-z0-9][a-z0-9.+-]*$")
_LAYER_KIND_VALUES = {"uv", "system", "nvidia", "python", "pip"}
_ROOT_LAYER_KIND_VALUES = {"uv", "system", "nvidia"}
_NVIDIA_DRIVER_BRANCH_RE = re.compile(r"^\d{3}$")
_DEFAULT_NVIDIA_DRIVER_BRANCH = "580"
_NVIDIA_DRIVER_BRANCH_VALUES = {"550", "570", "575", "580"}
_SERVER_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9\-_.]*$")
_FLAVOR_ID_RE = re.compile(r"^[a-zA-Z0-9\-_.]+$")
_SSH_USERNAME_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")

_CONSUME_BLOCKING_STATUSES = {"creating", "active", "stopped", "stop", "shutoff", "error"}
_CONSUME_DELETED_STATUS = "deleted"
_CONSUME_STALE_NO_SERVER_AFTER = timedelta(hours=1)
_BUILD_TERMINAL_STATUSES = {"complete", "error", "cancelled", "failure", "timeout", None}
_BUILD_STALE_ACTIVE_AFTER = timedelta(hours=2)
_PIP_SOURCE_URL_FIELDS = "pip_index_url, pip_extra_index_urls, pip_find_links"


def _validate_pip_source_url(value: str) -> str:
    url = str(value).strip()
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"pip source URL은 http(s) URL이어야 합니다: {value!r}")
    if parsed.username or parsed.password:
        raise ValueError("pip source URL에는 사용자명/비밀번호를 포함할 수 없습니다")
    if parsed.query or parsed.fragment:
        raise ValueError("pip source URL에는 query 또는 fragment를 포함할 수 없습니다")
    if any(ch in url for ch in "\r\n\t '\"`$\\;|<>"):
        raise ValueError(f"pip source URL에 허용되지 않는 문자가 있습니다: {value!r}")
    return url


class LayerBuildRequest(BaseModel):
    """레이어 빌드 요청 — uv → python → pip 순서의 squashfs 레이어 빌드."""

    layer_name: str
    kind: str = "python"
    python_version: str | None = None
    pip_packages: list[str] = []
    apt_packages: list[str] = []
    pip_index_url: str | None = None
    pip_extra_index_urls: list[str] = []
    pip_find_links: list[str] = []
    ubuntu_base: str | None = None
    base_image_id: str | None = None
    # 부모 레이어 이름 — legacy selector. 신규 UI/API는 parent_artifact_id를 사용한다.
    parent: str | None = None
    # 안정적인 부모 artifact ID.
    parent_artifact_id: int | None = None
    # Curated NVIDIA driver template branch (e.g. 580).
    nvidia_driver_branch: str | None = None

    @field_validator("layer_name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not _LAYER_NAME_RE.match(v):
            raise ValueError(f"유효하지 않은 이름 (소문자·숫자·점·하이픈만 허용): {v!r}")
        return v

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, v: str) -> str:
        if v not in _LAYER_KIND_VALUES:
            raise ValueError(f"지원하지 않는 layer kind: {v!r}")
        return v

    @field_validator("ubuntu_base")
    @classmethod
    def validate_ubuntu_base(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        return normalize_ubuntu_base(v)

    @field_validator("base_image_id")
    @classmethod
    def validate_base_image_id_field(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        return validate_base_image_id(v)

    @field_validator("parent")
    @classmethod
    def validate_parent(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not _LAYER_NAME_RE.match(v):
            raise ValueError(f"유효하지 않은 부모 레이어 이름: {v!r}")
        return v

    @field_validator("parent_artifact_id")
    @classmethod
    def validate_parent_artifact_id(cls, v: int | None) -> int | None:
        if v is not None and v <= 0:
            raise ValueError("parent_artifact_id는 양의 정수여야 합니다")
        return v

    @field_validator("python_version")
    @classmethod
    def validate_python_version(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not _PY_VERSION_RE.match(v):
            raise ValueError(f"유효하지 않은 Python 버전 (예: '3.11'): {v!r}")
        return v

    @field_validator("pip_packages", mode="before")
    @classmethod
    def validate_pip_packages(cls, v: list) -> list:
        for pkg in v:
            if not _PIP_SPEC_RE.match(str(pkg)):
                raise ValueError(f"유효하지 않은 pip 스펙: {pkg!r}")
        return v

    @field_validator("apt_packages", mode="before")
    @classmethod
    def validate_apt_packages(cls, v: list[str] | str | None) -> list[str]:
        if v is None or v == "":
            return []
        values = [v] if isinstance(v, str) else v
        packages = [str(pkg) for pkg in values]
        for pkg in packages:
            if not _APT_PACKAGE_RE.match(pkg):
                raise ValueError(f"유효하지 않은 apt 패키지명: {pkg!r}")
        return packages

    @field_validator("pip_index_url")
    @classmethod
    def validate_pip_index_url(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        return _validate_pip_source_url(v)

    @field_validator("pip_extra_index_urls", "pip_find_links", mode="before")
    @classmethod
    def validate_pip_source_url_list(cls, v: list[str] | str | None) -> list[str]:
        if v is None or v == "":
            return []
        values = [v] if isinstance(v, str) else v
        return [_validate_pip_source_url(str(item)) for item in values]

    @field_validator("nvidia_driver_branch")
    @classmethod
    def validate_nvidia_driver_branch(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if not _NVIDIA_DRIVER_BRANCH_RE.match(v) or v not in _NVIDIA_DRIVER_BRANCH_VALUES:
            allowed = ", ".join(sorted(_NVIDIA_DRIVER_BRANCH_VALUES))
            raise ValueError(f"nvidia_driver_branch는 지원 브랜치({allowed}) 중 하나여야 합니다")
        return v

    @model_validator(mode="after")
    def validate_kind_requirements(self) -> LayerBuildRequest:
        if self.parent and self.parent_artifact_id is not None:
            raise ValueError("parent와 parent_artifact_id는 동시에 사용할 수 없습니다")
        has_parent = self.parent is not None or self.parent_artifact_id is not None
        has_base_image = self.base_image_id is not None
        has_pip_sources = self.pip_index_url is not None or bool(self.pip_extra_index_urls) or bool(self.pip_find_links)
        has_apt_packages = bool(self.apt_packages)
        has_nvidia_branch = self.nvidia_driver_branch is not None
        if self.kind == "uv":
            if not has_base_image:
                raise ValueError("root layer build에는 base_image_id가 필요합니다")
            if has_parent:
                raise ValueError("kind='uv'일 때 parent 또는 parent_artifact_id는 사용할 수 없습니다")
            if self.python_version is not None:
                raise ValueError("kind='uv'일 때 python_version은 사용할 수 없습니다")
            if self.pip_packages:
                raise ValueError("kind='uv'일 때 pip_packages는 사용할 수 없습니다")
            if has_apt_packages:
                raise ValueError("kind='uv'일 때 apt_packages는 사용할 수 없습니다")
            if has_pip_sources:
                raise ValueError(f"kind='uv'일 때 {_PIP_SOURCE_URL_FIELDS}는 사용할 수 없습니다")
            if has_nvidia_branch:
                raise ValueError("kind='uv'일 때 nvidia_driver_branch는 사용할 수 없습니다")
        elif self.kind == "system":
            if not has_base_image:
                raise ValueError("root layer build에는 base_image_id가 필요합니다")
            if has_parent:
                raise ValueError("kind='system'일 때 parent 또는 parent_artifact_id는 사용할 수 없습니다")
            if self.python_version is not None:
                raise ValueError("kind='system'일 때 python_version은 사용할 수 없습니다")
            if self.pip_packages:
                raise ValueError("kind='system'일 때 pip_packages는 사용할 수 없습니다")
            if has_pip_sources:
                raise ValueError(f"kind='system'일 때 {_PIP_SOURCE_URL_FIELDS}는 사용할 수 없습니다")
            if has_nvidia_branch:
                raise ValueError("kind='system'일 때 nvidia_driver_branch는 사용할 수 없습니다")
            if not has_apt_packages:
                raise ValueError("kind='system'일 때 apt_packages는 최소 1개 이상 필요합니다")
        elif self.kind == "nvidia":
            if not has_base_image:
                raise ValueError("root layer build에는 base_image_id가 필요합니다")
            if has_parent:
                raise ValueError("kind='nvidia'일 때 parent 또는 parent_artifact_id는 사용할 수 없습니다")
            if self.python_version is not None:
                raise ValueError("kind='nvidia'일 때 python_version은 사용할 수 없습니다")
            if self.pip_packages:
                raise ValueError("kind='nvidia'일 때 pip_packages는 사용할 수 없습니다")
            if has_apt_packages:
                raise ValueError("kind='nvidia'일 때 apt_packages는 서버 템플릿이 생성하므로 입력할 수 없습니다")
            if has_pip_sources:
                raise ValueError(f"kind='nvidia'일 때 {_PIP_SOURCE_URL_FIELDS}는 사용할 수 없습니다")
            self.nvidia_driver_branch = self.nvidia_driver_branch or _DEFAULT_NVIDIA_DRIVER_BRANCH
        elif self.kind == "python":
            if has_base_image:
                raise ValueError("child layer build에서는 base_image_id를 지정할 수 없습니다")
            if not has_parent:
                raise ValueError("kind='python'일 때 parent 또는 parent_artifact_id가 필요합니다")
            if not self.python_version:
                raise ValueError("kind='python'일 때 python_version은 필수입니다")
            if self.pip_packages:
                raise ValueError("kind='python'일 때 pip_packages는 사용할 수 없습니다")
            if has_apt_packages:
                raise ValueError("kind='python'일 때 apt_packages는 사용할 수 없습니다")
            if has_pip_sources:
                raise ValueError(f"kind='python'일 때 {_PIP_SOURCE_URL_FIELDS}는 사용할 수 없습니다")
            if has_nvidia_branch:
                raise ValueError("kind='python'일 때 nvidia_driver_branch는 사용할 수 없습니다")
        elif self.kind == "pip":
            if has_base_image:
                raise ValueError("child layer build에서는 base_image_id를 지정할 수 없습니다")
            if not has_parent:
                raise ValueError("kind='pip'일 때 parent 또는 parent_artifact_id가 필요합니다")
            if self.python_version is not None:
                raise ValueError("kind='pip'일 때 python_version은 사용할 수 없습니다")
            if not self.pip_packages:
                raise ValueError("kind='pip'일 때 pip_packages는 최소 1개 이상 필요합니다")
            if has_apt_packages:
                raise ValueError("kind='pip'일 때 apt_packages는 사용할 수 없습니다")
            if has_nvidia_branch:
                raise ValueError("kind='pip'일 때 nvidia_driver_branch는 사용할 수 없습니다")
        return self


class LayerConsumeRequest(BaseModel):
    """레이어 소비 인스턴스 생성 요청."""

    profile_name: str
    server_name: str | None = None
    flavor_id: str
    image_id: str | None = None
    network_id: str | None = None
    key_name: str | None = None
    ssh_public_key: str | None = None
    ssh_username: str | None = None

    @field_validator("profile_name")
    @classmethod
    def validate_profile(cls, v: str) -> str:
        if not _LAYER_NAME_RE.match(v):
            raise ValueError(f"유효하지 않은 프로필 이름: {v!r}")
        return v

    @field_validator("server_name")
    @classmethod
    def validate_server_name(cls, v: str | None) -> str | None:
        from app.services.instance_names import normalize_requested_instance_name

        return normalize_requested_instance_name(v)

    @field_validator("flavor_id")
    @classmethod
    def validate_flavor_id(cls, v: str) -> str:
        if not _FLAVOR_ID_RE.match(v):
            raise ValueError(f"유효하지 않은 flavor_id: {v!r}")
        return v

    @field_validator("key_name")
    @classmethod
    def validate_key_name(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if len(v) > 255 or any(ch in v for ch in "\n\r\t"):
            raise ValueError(f"유효하지 않은 key_name: {v!r}")
        return v

    @field_validator("ssh_public_key")
    @classmethod
    def validate_ssh_public_key(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if v == "":
            return None
        validate_ssh_public_key(v)
        return v

    @field_validator("ssh_username")
    @classmethod
    def validate_ssh_username(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if not _SSH_USERNAME_RE.match(v):
            raise ValueError(f"유효하지 않은 SSH 사용자명: {v!r}")
        if v == "root":
            raise ValueError("root SSH 사용자는 허용되지 않습니다")
        return v

    @model_validator(mode="after")
    def validate_ssh_options(self) -> LayerConsumeRequest:
        if self.ssh_username and not (self.key_name or self.ssh_public_key):
            raise ValueError("ssh_username은 key_name 또는 ssh_public_key와 함께 사용해야 합니다")
        return self


class LayerProfileRequest(BaseModel):
    """레이어 프로필 구성 요청 — 여러 레이어를 묶어 named 프로필로 저장."""

    name: str
    layers: list[str]  # 순서 있는 레이어 이름 리스트 (OverlayFS lowerdir 위→아래)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not _LAYER_NAME_RE.match(v):
            raise ValueError(f"유효하지 않은 프로필 이름: {v!r}")
        return v

    @field_validator("layers", mode="before")
    @classmethod
    def validate_layers(cls, v: list) -> list:
        if not v:
            raise ValueError("layers는 최소 1개 이상이어야 합니다")
        for layer in v:
            if not _LAYER_NAME_RE.match(str(layer)):
                raise ValueError(f"유효하지 않은 레이어 이름: {layer!r}")
        return v


class DockerfileImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    github_url: str
    ref: str | None = None
    dockerfile_path: str = "Dockerfile"
    layer_prefix: str
    profile_name: str | None = None


class PublicationRequest(BaseModel):
    is_published: bool


async def _validate_profile_publication(session, profile) -> None:
    from app.config import get_settings
    from app.models.db import LayerArtifact

    layer_names = list(getattr(profile, "layers", None) or [])
    if not layer_names:
        raise HTTPException(status_code=400, detail="빈 프로필은 공개할 수 없습니다")

    rows = (
        (
            await session.execute(
                select(LayerArtifact)
                .where(LayerArtifact.name.in_(layer_names))
                .where(LayerArtifact.is_published.is_(True))
                .where(LayerArtifact.is_sealed.is_(True))
            )
        )
        .scalars()
        .all()
    )
    by_name: dict[str, list[object]] = {}
    for row in rows:
        by_name.setdefault(row.name, []).append(row)

    resolved: list[object] = []
    for layer_name in layer_names:
        matches = by_name.get(layer_name, [])
        if not matches:
            raise HTTPException(status_code=400, detail=f"프로필 레이어가 공개/봉인되어 있지 않습니다: {layer_name!r}")
        if len(matches) > 1:
            raise HTTPException(status_code=409, detail=f"프로필 레이어 이름이 중복되어 모호합니다: {layer_name!r}")
        resolved.append(matches[0])

    settings = get_settings()
    snapshots: list[dict] = []
    for row in resolved:
        snapshot = _artifact_base_image_snapshot(row)
        if not snapshot.get("base_image_id"):
            try:
                snapshot = legacy_snapshot_for_ubuntu_base(settings, snapshot.get("ubuntu_base"))
            except (RuntimeError, ValueError) as exc:
                raise HTTPException(
                    status_code=400,
                    detail=f"프로필 레이어의 base image를 확인할 수 없습니다: {getattr(row, 'name', None)!r}",
                ) from exc
        snapshots.append(snapshot)

    base_image_ids = {str(snapshot["base_image_id"]) for snapshot in snapshots if snapshot.get("base_image_id")}
    if len(base_image_ids) != 1:
        raise HTTPException(status_code=400, detail="프로필 레이어의 base image가 일치하지 않습니다")


# ---------------------------------------------------------------------------
# 빌드 엔드포인트
# ---------------------------------------------------------------------------


async def _artifact_lineage_rows(session, row) -> list[object]:
    """직계 부모 row부터 parent_id 체인을 따라 artifact lineage를 반환한다(child-first).

    구현은 `palimpsest_layers.load_lineage` 하나로 통일한다 — 허브 번들과 chain_id 계산이
    같은 순회를 쓰므로 계보 해석이 두 벌 존재하면 안 된다.
    """
    from app.services.palimpsest_layers import load_lineage

    return await load_lineage(session, row)


def _validate_build_parent_contract(req: LayerBuildRequest, parent_row, lineage: list[object]) -> None:
    """요청 kind와 부모 artifact lineage의 uv → python → pip 계약을 검증한다."""
    if req.kind in _ROOT_LAYER_KIND_VALUES:
        return
    if parent_row is None or not lineage:
        raise HTTPException(status_code=400, detail="부모 artifact lineage를 확인할 수 없습니다")
    direct_parent_kind = getattr(parent_row, "kind", None)
    if req.kind == "python":
        if direct_parent_kind != "uv":
            raise HTTPException(status_code=400, detail="Python 레이어의 부모는 uv 레이어여야 합니다")
        return
    if req.kind == "pip":
        if not any(getattr(artifact, "kind", None) == "python" for artifact in lineage):
            raise HTTPException(
                status_code=400, detail="pip 레이어의 부모 lineage에는 Python 레이어가 포함되어야 합니다"
            )
        return
    raise HTTPException(status_code=400, detail=f"지원하지 않는 layer kind: {req.kind}")


def _artifact_base_image_snapshot(row) -> dict:
    return {
        "base_image_id": getattr(row, "base_image_id", None),
        "base_image_name": getattr(row, "base_image_name", None),
        "base_image_checksum": getattr(row, "base_image_checksum", None),
        "base_image_os_hash_algo": getattr(row, "base_image_os_hash_algo", None),
        "base_image_os_hash_value": getattr(row, "base_image_os_hash_value", None),
        "base_image_min_disk": getattr(row, "base_image_min_disk", None),
        "base_image_visibility": getattr(row, "base_image_visibility", None),
        "base_image_owner": getattr(row, "base_image_owner", None),
        "ubuntu_base": normalize_ubuntu_base(getattr(row, "ubuntu_base", None)),
        "source_metadata": getattr(row, "source_metadata", None),
    }


def _resolved_lineage_base_image_snapshots(lineage: list[object]) -> list[dict]:
    from app.config import get_settings

    settings = get_settings()
    snapshots: list[dict] = []
    for artifact in lineage:
        snapshot = _artifact_base_image_snapshot(artifact)
        if not snapshot.get("base_image_id"):
            snapshot = legacy_snapshot_for_ubuntu_base(settings, snapshot.get("ubuntu_base"))
        snapshots.append(snapshot)
    base_image_ids = {str(snapshot["base_image_id"]) for snapshot in snapshots if snapshot.get("base_image_id")}
    if len(base_image_ids) != 1:
        raise HTTPException(
            status_code=400,
            detail=f"부모 lineage의 base image가 일치하지 않습니다: {', '.join(sorted(base_image_ids))}",
        )
    return snapshots


def _effective_build_ubuntu_base(req: LayerBuildRequest, parent_row, lineage: list[object]) -> str:
    """Root builds use the request base; children inherit a single normalized parent base."""
    if req.kind in _ROOT_LAYER_KIND_VALUES:
        return normalize_ubuntu_base(req.ubuntu_base)
    if parent_row is None or not lineage:
        raise HTTPException(status_code=400, detail="부모 artifact Ubuntu base를 확인할 수 없습니다")
    parent_base = normalize_ubuntu_base(getattr(parent_row, "ubuntu_base", None))
    if req.ubuntu_base and normalize_ubuntu_base(req.ubuntu_base) != parent_base:
        raise HTTPException(
            status_code=400,
            detail=f"요청 ubuntu_base가 부모 artifact와 일치하지 않습니다: {req.ubuntu_base} != {parent_base}",
        )
    lineage_bases = {normalize_ubuntu_base(getattr(artifact, "ubuntu_base", None)) for artifact in lineage}
    if req.kind == "pip" and len(lineage_bases) != 1:
        raise HTTPException(
            status_code=400,
            detail=f"부모 lineage의 Ubuntu base가 일치하지 않습니다: {', '.join(sorted(lineage_bases))}",
        )
    return parent_base


@router.get("/base-images", dependencies=[Depends(require_admin)])
async def list_layer_base_images(conn=Depends(get_os_conn)) -> list[dict]:
    """Active Ubuntu Glance images that can boot layer builder/consumer VMs."""

    try:
        return await asyncio.to_thread(list_base_images, conn)

    except Exception:
        _logger.warning("[layer_ops] base image 목록 조회 실패", exc_info=True)
        raise HTTPException(status_code=500, detail="base image 목록 조회 실패")


@router.post("/imports/dockerfile", dependencies=[Depends(require_admin)])
async def create_dockerfile_import(req: DockerfileImportRequest, conn=Depends(get_os_conn)) -> dict:
    from app.services.dockerfile_import import DockerfileImportError, create_import_job, prepare_dockerfile_import

    try:
        plan = await asyncio.to_thread(
            prepare_dockerfile_import,
            conn,
            github_url=req.github_url,
            ref=req.ref,
            dockerfile_path=req.dockerfile_path,
            layer_prefix=req.layer_prefix,
            profile_name=req.profile_name,
        )
        return await create_import_job(plan)
    except (DockerfileImportError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/imports", dependencies=[Depends(require_admin)])
async def list_dockerfile_imports(limit: int = 50) -> list[dict]:
    from app.services.dockerfile_import import DockerfileImportError, list_import_jobs

    try:
        return await list_import_jobs(limit=limit)
    except DockerfileImportError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/imports/{import_id}", dependencies=[Depends(require_admin)])
async def get_dockerfile_import(import_id: int) -> dict:
    from app.services.dockerfile_import import DockerfileImportError, get_import_job

    try:
        item = await get_import_job(import_id)
    except DockerfileImportError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail=f"import {import_id}를 찾을 수 없습니다")
    return item


@router.post("/build", dependencies=[Depends(require_admin)])
async def trigger_layer_build(req: LayerBuildRequest, conn=Depends(get_os_conn)) -> dict:
    """squashfs 레이어 빌드를 시작한다. 백그라운드 태스크로 실행.

    parent 지정 시 stacked 빌드: 부모 체인 share를 RO 마운트 → delta squash.
    """
    from app.models.db import LayerArtifact
    from app.services import layer_builder
    from app.services.layer_build import nvidia_driver_apt_packages

    _logger.info(
        "[layer_ops] 빌드 요청: layer=%s kind=%s ubuntu_base=%s python=%s parent=%s parent_id=%s pip_count=%d apt_count=%d pip_sources=%d",
        req.layer_name,
        req.kind,
        normalize_ubuntu_base(req.ubuntu_base),
        req.python_version or "-",
        req.parent or "-",
        req.parent_artifact_id or "-",
        len(req.pip_packages or []),
        len(req.apt_packages or []),
        int(req.pip_index_url is not None) + len(req.pip_extra_index_urls or []) + len(req.pip_find_links or []),
    )

    parent_artifact_id: int | None = None
    base_image_snapshot: dict | None = None
    effective_ubuntu_base = normalize_ubuntu_base(req.ubuntu_base)
    if req.kind in _ROOT_LAYER_KIND_VALUES:
        try:
            base_image_snapshot = await asyncio.to_thread(
                resolve_base_image_snapshot, conn, req.base_image_id or "", req.ubuntu_base
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        effective_ubuntu_base = normalize_ubuntu_base(base_image_snapshot["ubuntu_base"])
    if req.parent_artifact_id is not None:
        async with get_session_factory()() as session:
            parent_row = await session.get(LayerArtifact, req.parent_artifact_id)
            if parent_row is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"부모 artifact {req.parent_artifact_id}를 찾을 수 없습니다",
                )
            if not parent_row.is_sealed:
                raise HTTPException(
                    status_code=400,
                    detail=f"부모 artifact {req.parent_artifact_id}는 아직 봉인되지 않았습니다",
                )
            lineage = await _artifact_lineage_rows(session, parent_row)
            _validate_build_parent_contract(req, parent_row, lineage)
            effective_ubuntu_base = _effective_build_ubuntu_base(req, parent_row, lineage)
            base_image_snapshot = _resolved_lineage_base_image_snapshots(lineage)[0]
            parent_artifact_id = parent_row.id
    elif req.parent:
        async with get_session_factory()() as session:
            parent_row = (
                await session.execute(
                    select(LayerArtifact)
                    .where(LayerArtifact.name == req.parent)
                    .where(LayerArtifact.is_sealed.is_(True))
                    .order_by(desc(LayerArtifact.id))
                    .limit(1)
                )
            ).scalar_one_or_none()
            if parent_row is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"부모 레이어 {req.parent!r}를 찾을 수 없습니다 (봉인된 artifact 필요)",
                )
            lineage = await _artifact_lineage_rows(session, parent_row)
            _validate_build_parent_contract(req, parent_row, lineage)
            effective_ubuntu_base = _effective_build_ubuntu_base(req, parent_row, lineage)
            base_image_snapshot = _resolved_lineage_base_image_snapshots(lineage)[0]
            parent_artifact_id = parent_row.id

    build_apt_packages = (
        nvidia_driver_apt_packages(req.nvidia_driver_branch) if req.kind == "nvidia" else req.apt_packages
    )

    result = await layer_builder.start_layer_build(
        layer_name=req.layer_name,
        kind=req.kind,
        python_version=req.python_version,
        pip_packages=req.pip_packages,
        apt_packages=build_apt_packages,
        pip_index_url=req.pip_index_url,
        pip_extra_index_urls=req.pip_extra_index_urls,
        pip_find_links=req.pip_find_links,
        parent_artifact_id=parent_artifact_id,
        nvidia_driver_branch=req.nvidia_driver_branch,
        ubuntu_base=effective_ubuntu_base,
        base_image_snapshot=base_image_snapshot,
    )
    _logger.info("[layer_ops] 빌드 등록 완료: build_id=%s layer=%s", result.get("build_id"), req.layer_name)
    return result


@router.get("/builds", dependencies=[Depends(require_admin)])
async def list_layer_builds(limit: int = 50) -> list[dict]:
    """최근 레이어 빌드 목록 (최대 50건). 모니터링용."""
    from app.models.db import LayerBuild

    async with get_session_factory()() as session:
        rows = (
            (await session.execute(select(LayerBuild).order_by(desc(LayerBuild.created_at)).limit(min(limit, 100))))
            .scalars()
            .all()
        )
        await _sync_build_rows_timeouts(session, rows)

    return [_build_row_to_dict(r) for r in rows]


@router.get("/builds/{build_id}", dependencies=[Depends(require_admin)])
async def get_layer_build(build_id: int) -> dict:
    """빌드 상세 + 라이브 VM 상태 + 콘솔 로그."""
    import asyncio

    from app.models.db import LayerBuild
    from app.services import nova
    from app.services.keystone import get_service_project_connection

    async with get_session_factory()() as session:
        row = (await session.execute(select(LayerBuild).where(LayerBuild.id == build_id))).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail=f"빌드 {build_id}를 찾을 수 없습니다")
        await _sync_build_rows_timeouts(session, [row])

    result = _build_row_to_dict(row)

    # 진행 중인 빌드의 경우 라이브 VM 상태 + 콘솔 조회
    if row.server_id and _is_active_build(row):
        try:
            conn = await asyncio.to_thread(get_service_project_connection)
            server = await asyncio.to_thread(conn.compute.get_server, row.server_id)
            result["vm_status"] = server.status
            result["vm_ip"] = next(
                (addr["addr"] for addrs in (server.addresses or {}).values() for addr in addrs),
                None,
            )
            try:
                result["live_console"] = await asyncio.to_thread(nova.get_console_output, conn, row.server_id, 200)
            except Exception:
                result["live_console"] = None
        except Exception:
            _logger.debug("[layer_ops] VM 상태 조회 실패: server=%s", row.server_id)

    return result


@router.post("/builds/{build_id}/cancel", dependencies=[Depends(require_admin)])
async def cancel_layer_build(build_id: int) -> dict:
    """진행 중인 레이어 빌드를 취소한다."""
    from app.services import layer_builder

    _logger.info("[layer_ops] 빌드 취소 요청: build_id=%d", build_id)
    try:
        result = await layer_builder.cancel_layer_build(build_id)
        _logger.info("[layer_ops] 빌드 취소 완료: build_id=%d", build_id)
        return result
    except KeyError as e:
        _logger.warning("[layer_ops] 빌드 취소 실패 — not found: build_id=%d", build_id)
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        _logger.warning("[layer_ops] 빌드 취소 실패 — 상태 불일치: build_id=%d err=%s", build_id, e)
        raise HTTPException(status_code=409, detail=str(e)) from e


# ---------------------------------------------------------------------------
# 소비 엔드포인트
# ---------------------------------------------------------------------------


@router.post("/consume", dependencies=[Depends(require_admin)])
async def trigger_layer_consume(req: LayerConsumeRequest, conn=Depends(get_os_conn)) -> dict:
    """레이어 소비 인스턴스를 생성한다.

    layer-store-ro NFS share를 RO 마운트하고 layer-activate.sh로
    squashfs + OverlayFS를 활성화하는 VM을 생성해 반환한다.
    """
    _logger.info(
        "[layer_ops] 소비 인스턴스 요청: profile=%s server_name=%s flavor=%s",
        req.profile_name,
        req.server_name,
        req.flavor_id,
    )

    from app.database import get_session_factory
    from app.models.db import LayerConsume
    from app.services.layer_build import (
        resolve_layer_consume_resource_snapshot,
        run_layer_consume,
    )

    try:
        ssh_public_key: str | None = req.ssh_public_key or None
        if req.key_name and not ssh_public_key:
            kp = None
            try:
                kp = await asyncio.to_thread(conn.compute.get_keypair, req.key_name)
            except Exception:
                try:
                    kp = await asyncio.to_thread(conn.compute.find_keypair, req.key_name)
                except Exception:
                    kp = None
            ssh_public_key = getattr(kp, "public_key", None) or ""
            if not ssh_public_key:
                raise RuntimeError(f"선택한 키페어의 공개키를 조회할 수 없습니다: {req.key_name!r}")
        resource_snapshot = await resolve_layer_consume_resource_snapshot(
            conn,
            flavor_ref=req.flavor_id,
            network_id=req.network_id,
        )

        # DB 레코드 생성
        consume_db_id: int | None = None
        factory = get_session_factory()
        if factory:
            async with factory() as session:
                row = LayerConsume(
                    profile_name=req.profile_name,
                    server_name=req.server_name,
                    artifact_ids=None,
                    resource_snapshot=resource_snapshot,
                    status="creating",
                )
                session.add(row)
                await session.commit()
                await session.refresh(row)
                consume_db_id = row.id

        server_id = await run_layer_consume(
            consume_db_id=consume_db_id,
            profile_name=req.profile_name,
            server_name=req.server_name,
            flavor_id=req.flavor_id,
            image_id=req.image_id,
            network_id=req.network_id,
            ssh_public_key=ssh_public_key,
            ssh_username=req.ssh_username,
            resource_snapshot=resource_snapshot,
        )
        return {"consume_id": consume_db_id, "server_id": server_id, "status": "active"}
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/consumes", dependencies=[Depends(require_admin)])
async def list_layer_consumes(limit: int = 50) -> list[dict]:
    """최근 소비 인스턴스 목록 (최대 50건)."""
    from app.models.db import LayerConsume

    async with get_session_factory()() as session:
        rows = (
            (await session.execute(select(LayerConsume).order_by(desc(LayerConsume.created_at)).limit(min(limit, 100))))
            .scalars()
            .all()
        )
        await _sync_consume_rows_with_nova(session, rows)

    return [_consume_row_to_dict(r) for r in rows]


@router.get("/consumes/{consume_id}", dependencies=[Depends(require_admin)])
async def get_layer_consume(consume_id: int) -> dict:
    """소비 인스턴스 상세 + 라이브 Nova 상태."""
    import asyncio

    from app.models.db import LayerConsume
    from app.services.keystone import get_service_project_connection

    async with get_session_factory()() as session:
        row = (await session.execute(select(LayerConsume).where(LayerConsume.id == consume_id))).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail=f"소비 인스턴스 {consume_id}를 찾을 수 없습니다")
        await _sync_consume_rows_with_nova(session, [row])

    result = _consume_row_to_dict(row)
    if row.status == _CONSUME_DELETED_STATUS:
        return result

    if row.server_id:
        try:
            conn = await asyncio.to_thread(get_service_project_connection)
            server = await asyncio.to_thread(conn.compute.get_server, row.server_id)
            result["vm_status"] = server.status
            result["vm_ip"] = next(
                (addr["addr"] for addrs in (server.addresses or {}).values() for addr in addrs),
                None,
            )
        except Exception:
            _logger.debug("[layer_ops] 소비 VM 상태 조회 실패: server=%s", row.server_id)

    return result


# ---------------------------------------------------------------------------
# 아티팩트 엔드포인트
# ---------------------------------------------------------------------------


@router.get("/artifacts", dependencies=[Depends(require_admin)])
async def list_layer_artifacts(limit: int = 100) -> list[dict]:
    """빌드된 레이어 아티팩트 목록 — lineage/delete metadata 포함."""
    from app.models.db import LayerArtifact, LayerBuild, LayerConsume, LayerProfile

    async with get_session_factory()() as session:
        all_artifacts = (
            (await session.execute(select(LayerArtifact).order_by(desc(LayerArtifact.created_at)))).scalars().all()
        )
        profiles = (await session.execute(select(LayerProfile).order_by(LayerProfile.name))).scalars().all()
        consumes = (await session.execute(select(LayerConsume))).scalars().all()
        builds = (await session.execute(select(LayerBuild))).scalars().all()
        await _sync_consume_rows_with_nova(session, consumes)
        await _sync_build_rows_timeouts(session, builds)
    visible_artifacts = all_artifacts[: min(limit, 200)]
    by_id = {row.id: row for row in all_artifacts}
    return [
        _artifact_row_to_dict(
            row,
            lineage=_artifact_lineage(row, by_id),
            delete_preview=_artifact_delete_preview(row, all_artifacts, profiles, consumes, builds),
        )
        for row in visible_artifacts
    ]


@router.get("/artifacts/{artifact_id}/delete-preview", dependencies=[Depends(require_admin)])
async def preview_delete_layer_artifact(artifact_id: int) -> dict:
    """레이어 아티팩트 삭제 가능 여부와 차단 사유를 반환한다."""
    from app.models.db import LayerArtifact, LayerBuild, LayerConsume, LayerProfile

    async with get_session_factory()() as session:
        target = await session.get(LayerArtifact, artifact_id)
        if target is None:
            raise HTTPException(status_code=404, detail=f"artifact {artifact_id}를 찾을 수 없습니다")
        all_artifacts = (
            (await session.execute(select(LayerArtifact).order_by(desc(LayerArtifact.created_at)))).scalars().all()
        )
        profiles = (await session.execute(select(LayerProfile).order_by(LayerProfile.name))).scalars().all()
        consumes = (await session.execute(select(LayerConsume))).scalars().all()
        builds = (await session.execute(select(LayerBuild))).scalars().all()
        await _sync_consume_rows_with_nova(session, consumes)
        await _sync_build_rows_timeouts(session, builds)
    by_id = {row.id: row for row in all_artifacts}
    preview = _artifact_delete_preview(target, all_artifacts, profiles, consumes, builds)
    return {
        "artifact": _artifact_summary(target),
        "lineage": _artifact_lineage(target, by_id),
        **preview,
    }


@router.patch("/artifacts/{artifact_id}/publication", dependencies=[Depends(require_admin)])
async def set_layer_artifact_publication(artifact_id: int, req: PublicationRequest) -> dict:
    """Publish or unpublish a sealed artifact for public squashfs consumption."""
    from app.models.db import LayerArtifact

    async with get_session_factory()() as session:
        row = await session.get(LayerArtifact, artifact_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"artifact {artifact_id}를 찾을 수 없습니다")
        if req.is_published and not bool(getattr(row, "is_sealed", False)):
            raise HTTPException(status_code=400, detail="봉인되지 않은 artifact는 공개할 수 없습니다")
        row.is_published = req.is_published
        await session.commit()
        await session.refresh(row)
        await invalidate("afterglow:union_layer:*")
        return _artifact_row_to_dict(row)


@router.delete("/artifacts/{artifact_id}", dependencies=[Depends(require_admin)])
async def delete_layer_artifact(artifact_id: int) -> dict:
    """차단 사유가 없는 leaf artifact만 Manila share 삭제 후 DB에서 제거한다."""
    from app.models.db import LayerArtifact, LayerBuild, LayerConsume, LayerProfile
    from app.services import manila
    from app.services.keystone import get_service_project_connection

    async with get_session_factory()() as session:
        target = await session.get(LayerArtifact, artifact_id)
        if target is None:
            raise HTTPException(status_code=404, detail=f"artifact {artifact_id}를 찾을 수 없습니다")
        all_artifacts = (
            (await session.execute(select(LayerArtifact).order_by(desc(LayerArtifact.created_at)))).scalars().all()
        )
        profiles = (await session.execute(select(LayerProfile).order_by(LayerProfile.name))).scalars().all()
        consumes = (await session.execute(select(LayerConsume))).scalars().all()
        builds = (await session.execute(select(LayerBuild))).scalars().all()
        await _sync_consume_rows_with_nova(session, consumes)
        await _sync_build_rows_timeouts(session, builds)
        preview = _artifact_delete_preview(target, all_artifacts, profiles, consumes, builds)
        if not preview["can_delete"]:
            raise HTTPException(
                status_code=409,
                detail={"message": "artifact 삭제가 차단되었습니다", **preview},
            )

        share_id = target.share_id
        artifact_summary = _artifact_summary(target)

        try:
            conn = await asyncio.to_thread(get_service_project_connection)
            try:
                rules = await asyncio.to_thread(manila.list_access_rules, conn, share_id)
            except Exception:
                _logger.warning("[layer_ops] artifact share access rule 조회 실패: share=%s", share_id, exc_info=True)
                rules = []
            for rule in rules:
                access_id = rule.get("id") or rule.get("access_id")
                if not access_id:
                    continue
                try:
                    await asyncio.to_thread(manila.revoke_access_rule, conn, share_id, access_id)
                except Exception:
                    _logger.warning(
                        "[layer_ops] artifact share access rule 회수 실패: share=%s access=%s",
                        share_id,
                        access_id,
                        exc_info=True,
                    )
            await asyncio.to_thread(manila.delete_file_storage, conn, share_id)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Manila share 삭제 실패: {exc}") from exc

        await session.delete(target)
        await session.commit()

    return {"deleted": True, "artifact": artifact_summary}


# ---------------------------------------------------------------------------
# 프로필 엔드포인트
# ---------------------------------------------------------------------------


@router.post("/profiles", dependencies=[Depends(require_admin)])
async def upsert_layer_profile(req: LayerProfileRequest) -> dict:
    """레이어 프로필을 생성하거나 갱신한다 (upsert).

    layers 리스트의 각 레이어가 LayerArtifact에 존재해야 한다.
    """
    _logger.info("[layer_ops] 프로필 upsert: name=%s layers=%s", req.name, req.layers)
    from app.models.db import LayerArtifact, LayerProfile

    async with get_session_factory()() as session:
        # 각 레이어 존재 여부 검증
        art_rows = (await session.execute(select(LayerArtifact.name).distinct())).scalars().all()
        existing_names: set[str] = set(art_rows)

        missing = [layer for layer in req.layers if layer not in existing_names]
        if missing:
            from fastapi import HTTPException as _HTTPException

            raise _HTTPException(
                status_code=400,
                detail=f"존재하지 않는 레이어: {missing}. 먼저 빌드하세요.",
            )

        # upsert
        existing = (
            await session.execute(select(LayerProfile).where(LayerProfile.name == req.name))
        ).scalar_one_or_none()

        if existing:
            existing.layers = req.layers
            profile = existing
        else:
            profile = LayerProfile(name=req.name, layers=req.layers)
            session.add(profile)

        await session.commit()
        await session.refresh(profile)

    return _profile_row_to_dict(profile)


@router.get("/profiles", dependencies=[Depends(require_admin)])
async def list_layer_profiles() -> list[dict]:
    """저장된 레이어 프로필 목록."""
    from app.models.db import LayerProfile

    async with get_session_factory()() as session:
        rows = (await session.execute(select(LayerProfile).order_by(LayerProfile.name))).scalars().all()

    return [_profile_row_to_dict(r) for r in rows]


@router.patch("/profiles/{profile_name}/publication", dependencies=[Depends(require_admin)])
async def set_layer_profile_publication(profile_name: str, req: PublicationRequest) -> dict:
    """Publish or unpublish a profile for public squashfs consumption."""
    from app.models.db import LayerProfile

    if not _LAYER_NAME_RE.match(profile_name):
        raise HTTPException(status_code=422, detail=f"유효하지 않은 프로필 이름: {profile_name!r}")

    async with get_session_factory()() as session:
        row = (
            await session.execute(select(LayerProfile).where(LayerProfile.name == profile_name))
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail=f"프로필 '{profile_name}'을 찾을 수 없습니다")
        if req.is_published:
            await _validate_profile_publication(session, row)
        row.is_published = req.is_published
        await session.commit()
        await session.refresh(row)
        await invalidate("afterglow:union_layer:*")
        return _profile_row_to_dict(row)


@router.get("/profiles/{profile_name}", dependencies=[Depends(require_admin)])
async def get_layer_profile(profile_name: str) -> dict:
    """레이어 프로필 상세."""
    from app.models.db import LayerProfile

    async with get_session_factory()() as session:
        row = (
            await session.execute(select(LayerProfile).where(LayerProfile.name == profile_name))
        ).scalar_one_or_none()

    if row is None:
        raise HTTPException(status_code=404, detail=f"프로필 '{profile_name}'을 찾을 수 없습니다")

    return _profile_row_to_dict(row)


@router.delete("/profiles/{profile_name}", dependencies=[Depends(require_admin)])
async def delete_layer_profile(profile_name: str) -> dict:
    """사용 중인 live consume이 없는 레이어 프로필만 삭제한다."""
    from app.models.db import LayerConsume, LayerProfile

    if not _LAYER_NAME_RE.match(profile_name):
        raise HTTPException(status_code=422, detail=f"유효하지 않은 프로필 이름: {profile_name!r}")

    async with get_session_factory()() as session:
        profile = (
            await session.execute(select(LayerProfile).where(LayerProfile.name == profile_name))
        ).scalar_one_or_none()
        if profile is None:
            raise HTTPException(status_code=404, detail=f"프로필 '{profile_name}'을 찾을 수 없습니다")

        consumes = (
            (await session.execute(select(LayerConsume).where(LayerConsume.profile_name == profile_name)))
            .scalars()
            .all()
        )
        await _sync_consume_rows_with_nova(session, consumes)
        blocking_consumes = [row for row in consumes if _is_blocking_consume(row)]
        if blocking_consumes:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "프로필을 사용 중인 소비 인스턴스가 있습니다",
                    "profile": _profile_row_to_dict(profile),
                    "active_consume_references": [
                        {
                            "id": row.id,
                            "profile_name": row.profile_name,
                            "status": row.status,
                            "server_id": row.server_id,
                        }
                        for row in blocking_consumes
                    ],
                },
            )

        profile_summary = _profile_row_to_dict(profile)
        await session.delete(profile)
        await session.commit()

    return {"deleted": True, "profile": profile_summary}


def _base_image_dict(row) -> dict:
    return {
        "base_image_id": getattr(row, "base_image_id", None),
        "base_image_name": getattr(row, "base_image_name", None),
        "base_image_checksum": getattr(row, "base_image_checksum", None),
        "base_image_os_hash_algo": getattr(row, "base_image_os_hash_algo", None),
        "base_image_os_hash_value": getattr(row, "base_image_os_hash_value", None),
        "base_image_min_disk": getattr(row, "base_image_min_disk", None),
        "base_image_visibility": getattr(row, "base_image_visibility", None),
        "base_image_owner": getattr(row, "base_image_owner", None),
        "source_metadata": getattr(row, "source_metadata", None),
    }


# ---------------------------------------------------------------------------
# 직렬화 헬퍼
# ---------------------------------------------------------------------------


def _build_row_to_dict(row) -> dict:
    return {
        "id": row.id,
        "layer_name": row.layer_name,
        "kind": row.kind,
        "python_version": row.python_version,
        "pip_packages": _json_list(getattr(row, "pip_packages", None)),
        "apt_packages": _json_list(getattr(row, "apt_packages", None)),
        "ubuntu_base": _ubuntu_base(getattr(row, "ubuntu_base", None)),
        **_base_image_dict(row),
        "parent_artifact_id": _int_or_none(getattr(row, "parent_artifact_id", None)),
        "profile_name": row.profile_name,
        "share_id": row.share_id,
        "server_id": row.server_id,
        "port_id": row.port_id,
        "build_token": row.build_token,
        "cloud_init_status": row.cloud_init_status,
        "status": row.status,
        "progress_step": row.progress_step,
        "progress_pct": row.progress_pct,
        "error_message": row.error_message,
        "console_log_excerpt": row.console_log_excerpt,
        "started_at": _iso(row.started_at),
        "completed_at": _iso(row.completed_at),
        "created_at": _iso(row.created_at),
    }


def _consume_row_to_dict(row) -> dict:
    return {
        "id": row.id,
        "profile_name": row.profile_name,
        "server_id": row.server_id,
        "port_id": row.port_id,
        "server_name": row.server_name,
        "share_id": row.share_id,
        "project_id": getattr(row, "project_id", None),
        "artifact_ids": _json_list(getattr(row, "artifact_ids", None)),
        "status": row.status,
        "error_message": row.error_message,
        "created_at": _iso(row.created_at),
        "completed_at": _iso(row.completed_at),
    }


def _json_list(value) -> list:
    return value if isinstance(value, list) else []


def _int_or_none(value) -> int | None:
    return value if isinstance(value, int) else None


def _bool_attr(row, name: str) -> bool:
    value = getattr(row, name, False)
    return value if isinstance(value, bool) else bool(value) if isinstance(value, int) else False


def _ubuntu_base(value) -> str:
    return normalize_ubuntu_base(value)


def _artifact_summary(row) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "kind": row.kind,
        "python_version": row.python_version,
        "parent_id": _int_or_none(getattr(row, "parent_id", None)),
        "is_sealed": bool(getattr(row, "is_sealed", False)),
        "pip_packages": _json_list(getattr(row, "pip_packages", None)),
        "apt_packages": _json_list(getattr(row, "apt_packages", None)),
        "is_published": _bool_attr(row, "is_published"),
        "ubuntu_base": _ubuntu_base(getattr(row, "ubuntu_base", None)),
        **_base_image_dict(row),
        "requested_packages": _json_list(getattr(row, "pip_packages", None)),
        "created_at": _iso(getattr(row, "created_at", None)),
    }


def _artifact_lineage(target, by_id: dict[int, object]) -> list[dict]:
    """Return root→...→target lineage with a cycle guard."""
    chain = []
    seen: set[int] = set()
    current = target
    while current is not None:
        current_id = getattr(current, "id", None)
        if not isinstance(current_id, int) or current_id in seen:
            break
        seen.add(current_id)
        chain.append(_artifact_summary(current))
        parent_id = getattr(current, "parent_id", None)
        if not isinstance(parent_id, int):
            break
        current = by_id.get(parent_id)
    chain.reverse()
    return chain


def _profile_layers(row) -> list[str]:
    layers = getattr(row, "layers", None)
    return layers if isinstance(layers, list) else []


def _is_blocking_consume(row) -> bool:
    status = str(getattr(row, "status", "") or "").lower()
    return status in _CONSUME_BLOCKING_STATUSES


def _consume_status_from_server(server) -> str:
    status = str(getattr(server, "status", "") or "").upper()
    if status == "ACTIVE":
        return "active"
    if status in {"SHUTOFF", "STOPPED", "PAUSED", "SUSPENDED"}:
        return "stopped"
    if status == "ERROR":
        return "error"
    if status in {"DELETED", "SOFT_DELETED"}:
        return _CONSUME_DELETED_STATUS
    return "creating"


def _is_openstack_not_found(exc: Exception) -> bool:
    from openstack import exceptions as openstack_exceptions

    not_found_types = tuple(
        exc_type
        for exc_type in (
            getattr(openstack_exceptions, "NotFoundException", None),
            getattr(openstack_exceptions, "ResourceNotFound", None),
        )
        if isinstance(exc_type, type)
    )
    return bool(not_found_types) and isinstance(exc, not_found_types)


def _mark_consume_deleted(row) -> bool:
    changed = getattr(row, "status", None) != _CONSUME_DELETED_STATUS
    row.status = _CONSUME_DELETED_STATUS
    if getattr(row, "completed_at", None) is None:
        row.completed_at = datetime.now(UTC)
        changed = True
    return changed


def _utc_datetime(value) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _freshest_timestamp(row, *names: str) -> datetime | None:
    values = [_utc_datetime(getattr(row, name, None)) for name in names]
    values = [value for value in values if value is not None]
    return max(values) if values else None


def _should_terminalize_no_server_consume(row, now: datetime) -> bool:
    if getattr(row, "server_id", None) or not _is_blocking_consume(row):
        return False
    status = str(getattr(row, "status", "") or "").lower()
    if status == "error":
        return True
    if status != "creating":
        return False
    started = _freshest_timestamp(row, "updated_at", "created_at")
    return started is not None and now - started >= _CONSUME_STALE_NO_SERVER_AFTER


async def _sync_consume_rows_with_nova(session, rows: list[object]) -> None:
    now = datetime.now(UTC)
    changed = False
    for row in rows:
        if _should_terminalize_no_server_consume(row, now):
            changed = _mark_consume_deleted(row) or changed

    blocking_rows = [row for row in rows if getattr(row, "server_id", None) and _is_blocking_consume(row)]
    if not blocking_rows:
        if changed:
            await session.commit()
        return

    from app.services.keystone import get_service_project_connection

    try:
        conn = await asyncio.to_thread(get_service_project_connection)
    except Exception:
        _logger.warning("[layer_ops] consume VM 상태 동기화 연결 생성 실패", exc_info=True)
        if changed:
            await session.commit()
        return

    for row in blocking_rows:
        try:
            server = await asyncio.to_thread(conn.compute.get_server, row.server_id)
        except Exception as exc:
            if _is_openstack_not_found(exc):
                changed = _mark_consume_deleted(row) or changed
            else:
                _logger.warning(
                    "[layer_ops] consume VM 상태 동기화 실패: consume=%s server=%s",
                    getattr(row, "id", None),
                    row.server_id,
                    exc_info=True,
                )
            continue

        if server is None:
            changed = _mark_consume_deleted(row) or changed
            continue

        new_status = _consume_status_from_server(server)
        if getattr(row, "status", None) != new_status:
            row.status = new_status
            changed = True
        if new_status == _CONSUME_DELETED_STATUS and getattr(row, "completed_at", None) is None:
            row.completed_at = datetime.now(UTC)
            changed = True

    if changed:
        await session.commit()


def _is_active_build(row) -> bool:
    return getattr(row, "status", None) not in _BUILD_TERMINAL_STATUSES


def _is_stale_active_build(row, now: datetime) -> bool:
    if not _is_active_build(row):
        return False
    touched = _freshest_timestamp(row, "updated_at", "started_at", "created_at")
    return touched is not None and now - touched >= _BUILD_STALE_ACTIVE_AFTER


def _mark_build_timeout(row) -> bool:
    changed = False
    if getattr(row, "status", None) != "timeout":
        row.status = "timeout"
        changed = True
    if getattr(row, "cloud_init_status", None) != "failure":
        row.cloud_init_status = "failure"
        changed = True
    if getattr(row, "progress_step", None) != "자동 타임아웃":
        row.progress_step = "자동 타임아웃"
        changed = True
    message = "진행 상태가 장시간 갱신되지 않아 자동 timeout 처리되었습니다"
    if getattr(row, "error_message", None) != message:
        row.error_message = message
        changed = True
    if getattr(row, "completed_at", None) is None:
        row.completed_at = datetime.now(UTC)
        changed = True
    return changed


async def _cleanup_stale_build_resources(conn, row) -> bool:
    from app.services import manila, neutron

    server_id = getattr(row, "server_id", None)
    if server_id:
        try:
            server = await asyncio.to_thread(conn.compute.get_server, server_id)
        except Exception as exc:
            if not _is_openstack_not_found(exc):
                _logger.warning(
                    "[layer_ops] stale build VM 조회 실패: build=%s server=%s",
                    getattr(row, "id", None),
                    server_id,
                    exc_info=True,
                )
                return False
        else:
            if server is not None:
                try:
                    await asyncio.to_thread(conn.compute.delete_server, server_id)
                except Exception:
                    _logger.warning(
                        "[layer_ops] stale build VM 삭제 실패: build=%s server=%s",
                        getattr(row, "id", None),
                        server_id,
                        exc_info=True,
                    )
                    return False

    port_id = getattr(row, "port_id", None)
    if port_id:
        try:
            await asyncio.to_thread(neutron.delete_port, conn, port_id)
        except Exception:
            _logger.warning(
                "[layer_ops] stale build port 삭제 실패: build=%s port=%s",
                getattr(row, "id", None),
                port_id,
                exc_info=True,
            )

    share_id = getattr(row, "share_id", None)
    if share_id:
        try:
            rules = await asyncio.to_thread(manila.list_access_rules, conn, share_id)
            for rule in rules:
                if rule.get("access_type") == "ip" and rule.get("access_level") == "rw":
                    await asyncio.to_thread(manila.revoke_access_rule, conn, share_id, rule["id"])
        except Exception:
            _logger.warning(
                "[layer_ops] stale build RW access rule 정리 실패: build=%s share=%s",
                getattr(row, "id", None),
                share_id,
                exc_info=True,
            )

    return True


async def _sync_build_rows_timeouts(session, rows: list[object]) -> None:
    now = datetime.now(UTC)
    stale_rows = [row for row in rows if _is_stale_active_build(row, now)]
    if not stale_rows:
        return

    rows_requiring_openstack = [
        row
        for row in stale_rows
        if getattr(row, "server_id", None) or getattr(row, "port_id", None) or getattr(row, "share_id", None)
    ]
    conn = None
    if rows_requiring_openstack:
        from app.services.keystone import get_service_project_connection

        try:
            conn = await asyncio.to_thread(get_service_project_connection)
        except Exception:
            _logger.warning("[layer_ops] stale build 리소스 정리 연결 생성 실패", exc_info=True)

    changed = False
    for row in stale_rows:
        has_server = bool(getattr(row, "server_id", None))
        has_resources = has_server or bool(getattr(row, "port_id", None)) or bool(getattr(row, "share_id", None))
        if has_resources and conn is not None:
            if not await _cleanup_stale_build_resources(conn, row) and has_server:
                continue
        elif has_server and conn is None:
            continue
        changed = _mark_build_timeout(row) or changed

    if changed:
        await session.commit()


def _artifact_delete_preview(target, artifacts, profiles, consumes, builds) -> dict:
    target_id = target.id
    target_name = target.name
    direct_children = [row for row in artifacts if getattr(row, "parent_id", None) == target_id]
    profile_refs = [row for row in profiles if target_name in _profile_layers(row)]
    profile_names = {row.name for row in profile_refs}
    profile_consume_refs = [
        row for row in consumes if _is_blocking_consume(row) and getattr(row, "profile_name", None) in profile_names
    ]
    direct_consume_refs = [
        row
        for row in consumes
        if _is_blocking_consume(row) and target_id in _json_list(getattr(row, "artifact_ids", None))
    ]
    active_consume_refs = profile_consume_refs + [row for row in direct_consume_refs if row not in profile_consume_refs]
    active_build_refs = [
        row for row in builds if _is_active_build(row) and getattr(row, "parent_artifact_id", None) == target_id
    ]

    blockers = []
    if direct_children:
        blockers.append(
            {
                "type": "direct_children",
                "message": "자식 artifact가 parent_id로 참조 중입니다",
                "items": [_artifact_summary(row) for row in direct_children],
            }
        )
    if profile_refs:
        blockers.append(
            {
                "type": "profile_references",
                "message": "이름 기반 프로필이 artifact name을 참조 중입니다",
                "items": [{"id": row.id, "name": row.name, "layers": _profile_layers(row)} for row in profile_refs],
            }
        )
    if active_consume_refs:
        blockers.append(
            {
                "type": "active_consume_references",
                "message": "활성 consume이 해당 artifact를 사용 중입니다",
                "items": [
                    {
                        "id": row.id,
                        "profile_name": row.profile_name,
                        "status": row.status,
                        "server_id": getattr(row, "server_id", None),
                        "artifact_ids": _json_list(getattr(row, "artifact_ids", None)),
                    }
                    for row in active_consume_refs
                ],
            }
        )
    if active_build_refs:
        blockers.append(
            {
                "type": "active_build_references",
                "message": "진행 중인 빌드가 parent_artifact_id로 참조 중입니다",
                "items": [
                    {
                        "id": row.id,
                        "layer_name": row.layer_name,
                        "status": row.status,
                    }
                    for row in active_build_refs
                ],
            }
        )

    return {
        "direct_children": [_artifact_summary(row) for row in direct_children],
        "child_count": len(direct_children),
        "profile_references": [
            {"id": row.id, "name": row.name, "layers": _profile_layers(row)} for row in profile_refs
        ],
        "active_consume_references": [
            {
                "id": row.id,
                "profile_name": row.profile_name,
                "status": row.status,
                "server_id": getattr(row, "server_id", None),
                "artifact_ids": _json_list(getattr(row, "artifact_ids", None)),
            }
            for row in active_consume_refs
        ],
        "active_build_references": [
            {"id": row.id, "layer_name": row.layer_name, "status": row.status} for row in active_build_refs
        ],
        "delete_blockers": blockers,
        "can_delete": not blockers,
    }


def _artifact_row_to_dict(row, *, lineage: list[dict] | None = None, delete_preview: dict | None = None) -> dict:
    lineage = lineage or [_artifact_summary(row)]
    preview = delete_preview or {}
    return {
        "id": row.id,
        "name": row.name,
        "kind": row.kind,
        "python_version": row.python_version,
        "pip_packages": _json_list(getattr(row, "pip_packages", None)),
        "apt_packages": _json_list(getattr(row, "apt_packages", None)),
        "ubuntu_base": _ubuntu_base(getattr(row, "ubuntu_base", None)),
        **_base_image_dict(row),
        "requested_packages": _json_list(getattr(row, "pip_packages", None)),
        "sqsh_filename": row.sqsh_filename,
        "share_id": row.share_id,
        "is_published": _bool_attr(row, "is_published"),
        "build_id": row.build_id,
        "size_bytes": row.size_bytes,
        "parent_id": _int_or_none(getattr(row, "parent_id", None)),
        "is_sealed": bool(getattr(row, "is_sealed", False)),
        "lineage": lineage,
        "ancestors": lineage[:-1],
        "direct_children": preview.get("direct_children", []),
        "child_count": preview.get("child_count", 0),
        "profile_references": preview.get("profile_references", []),
        "active_consume_references": preview.get("active_consume_references", []),
        "active_build_references": preview.get("active_build_references", []),
        "delete_blockers": preview.get("delete_blockers", []),
        "can_delete": preview.get("can_delete", True),
        "created_at": _iso(row.created_at),
    }


def _profile_row_to_dict(row) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "layers": row.layers,
        "is_published": _bool_attr(row, "is_published"),
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }
