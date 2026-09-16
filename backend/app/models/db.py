"""SQLAlchemy ORM models for Afterglow-owned persistence."""

from datetime import UTC, datetime

from sqlalchemy import (
    BIGINT,
    BOOLEAN,
    CHAR,
    INT,
    JSON,
    TEXT,
    VARCHAR,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import DATETIME, MEDIUMBLOB, MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _now() -> datetime:
    return datetime.now(UTC)


class GpuDeviceCatalog(Base):
    """관리자가 추가한 GPU PCI 장치 카탈로그. 내장 기본값 + afterglow.conf 위에 overlay된다."""

    __tablename__ = "gpu_device_catalog"

    id: Mapped[int] = mapped_column(INT, primary_key=True, autoincrement=True)
    vendor_id: Mapped[str] = mapped_column(CHAR(4), nullable=False)  # PCI vendor (예: "10DE")
    device_id: Mapped[str] = mapped_column(CHAR(4), nullable=False)  # PCI product (예: "2204")
    name: Mapped[str] = mapped_column(VARCHAR(128), nullable=False)
    is_audio: Mapped[bool] = mapped_column(BOOLEAN, nullable=False, default=False)
    aliases: Mapped[list] = mapped_column(JSON, nullable=False, default=list)  # pci_passthrough alias 목록
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    __table_args__ = (Index("idx_gpu_device_vendor_device", "vendor_id", "device_id", unique=True),)


class NotionTarget(Base):
    """Notion 다중 연동 대상. API key는 AES-256-GCM 암호화 저장."""

    __tablename__ = "notion_targets"

    id: Mapped[int] = mapped_column(INT, primary_key=True, autoincrement=True)
    label: Mapped[str] = mapped_column(VARCHAR(64), nullable=False, default="기본")

    # 민감 정보 — AES-256-GCM 암호화
    api_key_encrypted: Mapped[str] = mapped_column(TEXT, nullable=False)

    # 데이터베이스 ID (인스턴스 DB 필수, 나머지 선택)
    database_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False, default="")
    users_database_id: Mapped[str | None] = mapped_column(VARCHAR(64))
    hypervisors_database_id: Mapped[str | None] = mapped_column(VARCHAR(64))
    gpu_spec_database_id: Mapped[str | None] = mapped_column(VARCHAR(64))

    # 동기화 설정
    enabled: Mapped[bool] = mapped_column(BOOLEAN, nullable=False, default=True)
    interval_minutes: Mapped[int] = mapped_column(INT, nullable=False, default=30)

    # 마지막 동기화 시각
    last_sync: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hypervisors_last_sync: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    gpu_spec_last_sync: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # 타임스탬프
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)


class ProjectDefaultNetwork(Base):
    """프로젝트별 기본 네트워크 설정. 자동 생성 또는 사용자가 직접 지정."""

    __tablename__ = "project_default_networks"

    id: Mapped[int] = mapped_column(INT, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(VARCHAR(64), unique=True, nullable=False, index=True)
    network_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    subnet_id: Mapped[str | None] = mapped_column(VARCHAR(64))
    router_id: Mapped[str | None] = mapped_column(VARCHAR(64))
    auto_created: Mapped[bool] = mapped_column(BOOLEAN, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)


class NotionConfig(Base):
    """Notion 연동 설정 (싱글톤, id=1 고정). API key는 AES-256-GCM 암호화 저장."""

    __tablename__ = "notion_config"

    id: Mapped[int] = mapped_column(INT, primary_key=True, autoincrement=True)

    # 민감 정보 — AES-256-GCM 암호화
    api_key_encrypted: Mapped[str] = mapped_column(TEXT, nullable=False)

    # 데이터베이스 ID
    database_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False, default="")
    users_database_id: Mapped[str | None] = mapped_column(VARCHAR(64))
    hypervisors_database_id: Mapped[str | None] = mapped_column(VARCHAR(64))
    gpu_spec_database_id: Mapped[str | None] = mapped_column(VARCHAR(64))

    # 동기화 설정
    enabled: Mapped[bool] = mapped_column(BOOLEAN, nullable=False, default=False)
    interval_minutes: Mapped[int] = mapped_column(INT, nullable=False, default=30)

    # 마지막 동기화 시각
    last_sync: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hypervisors_last_sync: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    gpu_spec_last_sync: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # 타임스탬프
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)


class LibraryRecipe(Base):
    """라이브러리별 빌드 레시피 — cloud-init ephemeral 빌드에 사용."""

    __tablename__ = "library_recipes"

    id: Mapped[int] = mapped_column(INT, primary_key=True, autoincrement=True)
    library_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False, index=True)
    version: Mapped[int] = mapped_column(INT, nullable=False, default=1)

    # [{step: str, progress_pct: int, script: str}]
    commands: Mapped[list | None] = mapped_column(JSON, nullable=True)
    apt_packages: Mapped[list | None] = mapped_column(JSON, nullable=True)
    pip_packages: Mapped[list | None] = mapped_column(JSON, nullable=True)

    base_image_id: Mapped[str | None] = mapped_column(VARCHAR(64))
    share_size_gb: Mapped[int] = mapped_column(INT, nullable=False, default=20)
    share_proto: Mapped[str] = mapped_column(VARCHAR(10), nullable=False, default="NFS")
    cloud_init_template_version: Mapped[int] = mapped_column(INT, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    __table_args__ = (Index("idx_library_recipes_lib_ver", "library_id", "version", unique=True),)


class LibraryBuild(Base):
    """라이브러리 사전빌드 작업 추적 — Manila share + 빌더 VM 상태를 DB에 기록."""

    __tablename__ = "library_builds"

    id: Mapped[int] = mapped_column(INT, primary_key=True, autoincrement=True)
    library_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False, index=True)
    file_storage_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    server_id: Mapped[str | None] = mapped_column(VARCHAR(64))

    # ephemeral 빌드 추가 필드
    recipe_id: Mapped[int | None] = mapped_column(INT, nullable=True)
    port_id: Mapped[str | None] = mapped_column(VARCHAR(64), nullable=True)
    build_token: Mapped[str | None] = mapped_column(CHAR(32), nullable=True, unique=True)
    console_log_excerpt: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    # queued/booting/installing/finalizing/success/failure/indeterminate
    cloud_init_status: Mapped[str | None] = mapped_column(VARCHAR(20), nullable=True)
    # OpenStack IDs/names selected before the build was queued.
    resource_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # 상태: pending, creating_share, creating_access, creating_vm, building, verifying, cleanup, complete, error, timeout
    status: Mapped[str] = mapped_column(VARCHAR(32), nullable=False, default="pending")
    progress_step: Mapped[str] = mapped_column(VARCHAR(64), nullable=False, default="")
    progress_pct: Mapped[int] = mapped_column(INT, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(TEXT)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)


# ---------------------------------------------------------------------------
# squashfs NFS 레이어 빌드/소비 추적
# ---------------------------------------------------------------------------


class LayerBuild(Base):
    """squashfs 레이어 빌드 작업 추적 — NFS Manila share에 .sqsh 파일 생성."""

    __tablename__ = "layer_builds"

    id: Mapped[int] = mapped_column(INT, primary_key=True, autoincrement=True)
    layer_name: Mapped[str] = mapped_column(VARCHAR(64), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(VARCHAR(16), nullable=False, server_default="python")
    python_version: Mapped[str | None] = mapped_column(VARCHAR(16))
    profile_name: Mapped[str | None] = mapped_column(VARCHAR(64))
    pip_packages: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    apt_packages: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    ubuntu_base: Mapped[str] = mapped_column(
        VARCHAR(255),
        nullable=False,
        default="ubuntu-24.04-server-2026-04-15",
        server_default="ubuntu-24.04-server-2026-04-15",
    )
    base_image_id: Mapped[str | None] = mapped_column(VARCHAR(128), nullable=True)
    base_image_name: Mapped[str | None] = mapped_column(VARCHAR(255), nullable=True)
    base_image_checksum: Mapped[str | None] = mapped_column(VARCHAR(128), nullable=True)
    base_image_os_hash_algo: Mapped[str | None] = mapped_column(VARCHAR(32), nullable=True)
    base_image_os_hash_value: Mapped[str | None] = mapped_column(VARCHAR(128), nullable=True)
    base_image_min_disk: Mapped[int | None] = mapped_column(INT, nullable=True)
    base_image_visibility: Mapped[str | None] = mapped_column(VARCHAR(32), nullable=True)
    base_image_owner: Mapped[str | None] = mapped_column(VARCHAR(128), nullable=True)
    source_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    parent_artifact_id: Mapped[int | None] = mapped_column(
        INT,
        ForeignKey("layer_artifacts.id", name="fk_layer_builds_parent_artifact", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )
    share_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    # OpenStack IDs/names selected before the build was queued.
    builder_flavor_id: Mapped[str | None] = mapped_column(VARCHAR(128), nullable=True)
    builder_network_id: Mapped[str | None] = mapped_column(VARCHAR(128), nullable=True)
    resource_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # 빌더 VM 추적
    server_id: Mapped[str | None] = mapped_column(VARCHAR(64))
    port_id: Mapped[str | None] = mapped_column(VARCHAR(64))
    build_token: Mapped[str | None] = mapped_column(CHAR(32), nullable=True, unique=True)
    console_log_excerpt: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    # queued/booting/installing/finalizing/success/failure/indeterminate
    cloud_init_status: Mapped[str | None] = mapped_column(VARCHAR(20), nullable=True)

    # 상태: queued/creating_access/creating_vm/building/verifying/complete/error/cancelled
    status: Mapped[str] = mapped_column(VARCHAR(32), nullable=False, default="pending")
    progress_step: Mapped[str] = mapped_column(VARCHAR(64), nullable=False, default="")
    progress_pct: Mapped[int] = mapped_column(INT, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(TEXT)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)


class LayerConsume(Base):
    """squashfs 레이어 소비 인스턴스 추적 — 관리자가 생성한 레이어 소비 VM."""

    __tablename__ = "layer_consumes"

    id: Mapped[int] = mapped_column(INT, primary_key=True, autoincrement=True)
    profile_name: Mapped[str] = mapped_column(VARCHAR(64), nullable=False, index=True)
    server_id: Mapped[str | None] = mapped_column(VARCHAR(64), index=True)
    port_id: Mapped[str | None] = mapped_column(VARCHAR(64))
    share_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    project_id: Mapped[str | None] = mapped_column(VARCHAR(64), nullable=True, index=True)
    artifact_ids: Mapped[list[int] | None] = mapped_column(JSON, nullable=True)
    resource_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    server_name: Mapped[str | None] = mapped_column(VARCHAR(128))

    # 상태: creating/active/error
    status: Mapped[str] = mapped_column(VARCHAR(32), nullable=False, default="creating")
    error_message: Mapped[str | None] = mapped_column(TEXT)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LayerArtifact(Base):
    """squashfs 레이어 빌드 성공 시 생성되는 아티팩트 레코드.

    레이어별 동적 Manila NFS share 방식(per-layer-share):
    빌드 시 자기 share를 생성하고 RW access rule로 `.sqsh`를 기록한 뒤 RO로 봉인(is_sealed=True).
    소비 시 프로필 레이어 체인의 N개 share를 각각 RO 마운트한다.

    기존 `layer_artifacts` 테이블에 행이 있는 경우 신규 컬럼을 수동 ALTER해야 한다:
      ALTER TABLE layer_artifacts
        ADD COLUMN parent_id INT NULL,
        ADD COLUMN is_sealed TINYINT(1) NOT NULL DEFAULT 0,
        ADD CONSTRAINT fk_layer_artifacts_parent
          FOREIGN KEY (parent_id) REFERENCES layer_artifacts(id) ON DELETE SET NULL;
    """

    __tablename__ = "layer_artifacts"

    id: Mapped[int] = mapped_column(INT, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(VARCHAR(64), nullable=False, index=True)
    # "uv" | "python" | 기타 사용자 정의 kind
    kind: Mapped[str] = mapped_column(VARCHAR(16), nullable=False, index=True)
    python_version: Mapped[str | None] = mapped_column(VARCHAR(16))
    pip_packages: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    apt_packages: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    ubuntu_base: Mapped[str] = mapped_column(
        VARCHAR(255),
        nullable=False,
        default="ubuntu-24.04-server-2026-04-15",
        server_default="ubuntu-24.04-server-2026-04-15",
    )
    base_image_id: Mapped[str | None] = mapped_column(VARCHAR(128), nullable=True)
    base_image_name: Mapped[str | None] = mapped_column(VARCHAR(255), nullable=True)
    base_image_checksum: Mapped[str | None] = mapped_column(VARCHAR(128), nullable=True)
    base_image_os_hash_algo: Mapped[str | None] = mapped_column(VARCHAR(32), nullable=True)
    base_image_os_hash_value: Mapped[str | None] = mapped_column(VARCHAR(128), nullable=True)
    base_image_min_disk: Mapped[int | None] = mapped_column(INT, nullable=True)
    base_image_visibility: Mapped[str | None] = mapped_column(VARCHAR(32), nullable=True)
    base_image_owner: Mapped[str | None] = mapped_column(VARCHAR(128), nullable=True)
    source_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    sqsh_filename: Mapped[str] = mapped_column(VARCHAR(256), nullable=False)
    # 이 레이어 전용 Manila NFS share ID (동적 생성, 봉인 후 RO)
    share_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    build_id: Mapped[int | None] = mapped_column(INT, ForeignKey("layer_builds.id", ondelete="SET NULL"))
    size_bytes: Mapped[int | None] = mapped_column(BIGINT)
    # ── Palimpsest 콘텐츠 주소화 (마이그레이션 057) ──────────────────────────
    # 레이어 정체성 = `.sqsh` blob 바이트의 sha256. 설계 근거는 docs/palimpsest.md §3.
    # UNIQUE 를 걸지 않는다 — 같은 콘텐츠가 서로 다른 Manila share 에 존재할 수 있고,
    # 중복 제거는 허브 계층의 책임이다.
    blob_digest: Mapped[str | None] = mapped_column(VARCHAR(71), nullable=True, index=True)
    # 외부 도구 호환용 보조 검색 키. 무결성 권위 아님 — 보안 용도 금지.
    blob_md5: Mapped[str | None] = mapped_column(CHAR(32), nullable=True)
    # 빌드 의도(name/kind/base/packages/parent digest)를 정규화한 sha256
    config_digest: Mapped[str | None] = mapped_column(VARCHAR(71), nullable=True)
    # 스택 전체의 정체성(OCI chainID 방식). 부모가 pending 이면 자식도 계산하지 않는다.
    chain_id: Mapped[str | None] = mapped_column(VARCHAR(71), nullable=True, index=True)
    # pending | ready | failed — digest 미확보 행도 소비는 계속 가능해야 한다
    # 빌드 캐시 키 = sha256(부모 참조 + "\n" + 정규화된 Dockerfile instruction).
    # 같은 부모 위에 같은 명령이면 기존 sealed artifact 를 재사용해 빌드를 건너뛴다.
    step_digest: Mapped[str | None] = mapped_column(VARCHAR(71), nullable=True, index=True)
    digest_state: Mapped[str] = mapped_column(VARCHAR(16), nullable=False, default="pending", server_default="pending")
    # 단일 부모 체인: child → parent → grandparent → ... → base(parent_id=NULL)
    parent_id: Mapped[int | None] = mapped_column(
        INT, ForeignKey("layer_artifacts.id", ondelete="SET NULL"), nullable=True
    )
    # 봉인 여부: 빌드 성공 후 RW rule 회수 완료 = True (소비 가능 상태)
    is_sealed: Mapped[bool] = mapped_column(BOOLEAN, nullable=False, default=False)
    is_published: Mapped[bool] = mapped_column(BOOLEAN, nullable=False, default=False, server_default="0", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)


class LayerImportJob(Base):
    """GitHub Dockerfile → squashfs layer chain import job."""

    __tablename__ = "layer_import_jobs"

    id: Mapped[int] = mapped_column(INT, primary_key=True, autoincrement=True)
    source_type: Mapped[str] = mapped_column(
        VARCHAR(32), nullable=False, default="github_dockerfile", server_default="github_dockerfile"
    )
    status: Mapped[str] = mapped_column(
        VARCHAR(32), nullable=False, default="queued", server_default="queued", index=True
    )
    progress_step: Mapped[str | None] = mapped_column(VARCHAR(64), nullable=True)
    progress_pct: Mapped[int] = mapped_column(INT, nullable=False, default=0, server_default="0")
    error_message: Mapped[str | None] = mapped_column(TEXT, nullable=True)

    # source_type='github_dockerfile' 일 때만 채워진다. inline 업로드는 전부 NULL. (마이그레이션 060)
    github_url: Mapped[str | None] = mapped_column(VARCHAR(512), nullable=True)
    repo_owner: Mapped[str | None] = mapped_column(VARCHAR(64), nullable=True)
    repo_name: Mapped[str | None] = mapped_column(VARCHAR(128), nullable=True)
    commit_sha: Mapped[str | None] = mapped_column(CHAR(40), nullable=True)
    # inline 업로드 원문과 그 sha256 — 감사·재현용. source_type='inline_dockerfile' 일 때 채워진다.
    dockerfile_text: Mapped[str | None] = mapped_column(MEDIUMTEXT, nullable=True)
    dockerfile_digest: Mapped[str | None] = mapped_column(VARCHAR(71), nullable=True)
    # FROM 이 기존 Palimpsest 레이어를 가리킬 때의 부모 blob digest
    parent_digest: Mapped[str | None] = mapped_column(VARCHAR(71), nullable=True)
    dockerfile_path: Mapped[str | None] = mapped_column(VARCHAR(255), nullable=True)

    layer_prefix: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    profile_name: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    ubuntu_base: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    base_image_id: Mapped[str] = mapped_column(VARCHAR(128), nullable=False)
    base_image_name: Mapped[str | None] = mapped_column(VARCHAR(255), nullable=True)
    base_image_checksum: Mapped[str | None] = mapped_column(VARCHAR(128), nullable=True)
    base_image_os_hash_algo: Mapped[str | None] = mapped_column(VARCHAR(32), nullable=True)
    base_image_os_hash_value: Mapped[str | None] = mapped_column(VARCHAR(128), nullable=True)
    base_image_min_disk: Mapped[int | None] = mapped_column(INT, nullable=True)

    planned_layers: Mapped[list | None] = mapped_column(JSON, nullable=True)
    artifact_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    build_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    resource_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LayerProfile(Base):
    """레이어 프로필 — 여러 레이어를 순서 있는 리스트로 묶어 DB에 저장.

    소비 VM cloud-init에서 이 레이어 리스트를 주입해 OverlayFS를 구성한다.
    NFS /profiles/*.conf 파일을 대체하는 DB-based source of truth.
    """

    __tablename__ = "layer_profiles"

    id: Mapped[int] = mapped_column(INT, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(VARCHAR(64), nullable=False, unique=True, index=True)
    # JSON 배열: ["uv-latest", "python-latest"]  순서 = OverlayFS lowerdir 위→아래
    layers: Mapped[list] = mapped_column(JSON, nullable=False)
    is_published: Mapped[bool] = mapped_column(BOOLEAN, nullable=False, default=False, server_default="0", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)


# ---------------------------------------------------------------------------
# Palimpsest 허브 — digest 로 주소화된 레이어 레지스트리 (마이그레이션 059)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# (폐기) 2세대 union ORM — UnionLayer / UnionTemplate / UnionUserMount
#
# 인프라(중앙 Manila share, CephX keyring, Builder VM)가 배포된 적이 없어
# Palimpsest 통합 과정에서 제거했다. `union_layers` / `union_templates` /
# `union_user_mounts` **테이블 자체는 데이터 보존을 위해 남긴다** — DROP 마이그레이션
# 없음. 레이어 정체성은 이제 `LayerArtifact.blob_digest` 다(docs/palimpsest.md §3).
# ---------------------------------------------------------------------------


class ProjectRole(Base):
    """afterglow 자체 프로젝트 관리자 역할 (Keystone role과 별개)."""

    __tablename__ = "project_roles"

    id: Mapped[int] = mapped_column(INT, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False, index=True)
    role: Mapped[str] = mapped_column(VARCHAR(32), nullable=False, default="manager")
    granted_by: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    from sqlalchemy import UniqueConstraint

    __table_args__ = (UniqueConstraint("project_id", "user_id", "role", name="uq_project_user_role"),)


class ProjectInvitation(Base):
    """프로젝트 이메일 초대 수명주기."""

    __tablename__ = "project_invitations"

    id: Mapped[int] = mapped_column(INT, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False, index=True)
    invited_email: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    invited_user_id: Mapped[str | None] = mapped_column(VARCHAR(64), nullable=True)
    invited_by: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    invited_by_name: Mapped[str] = mapped_column(VARCHAR(255), nullable=False, default="")
    token_hash: Mapped[str] = mapped_column(VARCHAR(64), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(VARCHAR(16), nullable=False, default="pending")
    keystone_role: Mapped[str] = mapped_column(VARCHAR(64), nullable=False, default="member")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    __table_args__ = (
        Index("idx_project_invitations_status", "project_id", "status"),
        Index("idx_project_invitations_email", "invited_email"),
    )


class LibraryCatalog(Base):
    """라이브러리 카탈로그 — 선택 가능한 라이브러리 정의 (이전: 코드 하드코딩)."""

    __tablename__ = "library_catalog"

    library_id: Mapped[str] = mapped_column(VARCHAR(64), primary_key=True)
    name: Mapped[str] = mapped_column(VARCHAR(128), nullable=False)
    version: Mapped[str] = mapped_column(VARCHAR(32), nullable=False)
    packages: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    depends_on: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    share_proto: Mapped[str] = mapped_column(VARCHAR(10), nullable=False, default="CEPHFS")
    ubuntu_versions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    visibility: Mapped[str] = mapped_column(VARCHAR(16), nullable=False, default="public")
    license_type: Mapped[str | None] = mapped_column(VARCHAR(64), nullable=True)
    max_concurrent_mounts: Mapped[int | None] = mapped_column(INT, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)


class SiteBrandingAsset(Base):
    """DB-backed public branding asset for login-page logo variants."""

    __tablename__ = "site_branding_assets"

    id: Mapped[int] = mapped_column(INT, primary_key=True, autoincrement=True)
    slot: Mapped[str] = mapped_column(VARCHAR(32), nullable=False, unique=True, index=True)
    filename: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    content_type: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(INT, nullable=False)
    sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    content: Mapped[bytes] = mapped_column(
        LargeBinary(length=1_048_576).with_variant(MEDIUMBLOB, "mysql", "mariadb"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)
    updated_by_user_id: Mapped[str | None] = mapped_column(VARCHAR(64), nullable=True)


class UserTutorialStatus(Base):
    """사용자별 튜토리얼(투어) 진행 이력. (user_id, tour_id) 복합 PK.

    status='completed'(완주) | 'dismissed'(무시/패스). 기록이 없으면 미체험 상태로,
    프론트엔드가 해당 페이지의 튜토리얼 버튼을 강조한다. 완료·무시 어느 쪽이든 기록되면 강조 해제.
    user_id 는 항상 서버가 token_info 로 계산하며 클라이언트 입력을 신뢰하지 않는다(IDOR 방지).
    """

    __tablename__ = "user_tutorial_statuses"

    user_id: Mapped[str] = mapped_column(VARCHAR(64), primary_key=True)
    tour_id: Mapped[str] = mapped_column(VARCHAR(64), primary_key=True)
    status: Mapped[str] = mapped_column(VARCHAR(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)


# ActivityLog 모델을 Base.metadata 에 등록 (create_tables 자동 감지)
from app.models.activity import ActivityLog  # noqa: E402,F401

# Announcement/AnnouncementRead 모델을 Base.metadata 에 등록 (create_tables 자동 감지)
from app.models.announcement import Announcement, AnnouncementRead  # noqa: E402,F401

# Afterglow owns only the MCP control-plane persistence. Lumen owns chat state.
from app.models.mcp_authority import (  # noqa: E402,F401
    McpDelegatedGrant,
    McpLumenSelection,
    McpOAuthAuthorizationRequest,
    McpOAuthClient,
    McpOAuthCode,
    McpOAuthToken,
    McpOAuthTokenFamily,
    McpOwnerLock,
    McpPersonalToken,
    McpToolInvocation,
)


class VmCloudInitSnippet(Base):
    """사용자별 VM cloud-init 실행 이력과 명명된 재사용 프리셋."""

    __tablename__ = "vm_cloud_init_snippets"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(VARCHAR(16), nullable=False)  # history | preset
    name: Mapped[str | None] = mapped_column(VARCHAR(100))
    content_encrypted: Mapped[str] = mapped_column(MEDIUMTEXT, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True).with_variant(DATETIME(fsp=6), "mysql").with_variant(DATETIME(fsp=6), "mariadb"),
        nullable=False,
        default=_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True).with_variant(DATETIME(fsp=6), "mysql").with_variant(DATETIME(fsp=6), "mariadb"),
        nullable=False,
        default=_now,
        onupdate=_now,
    )

    __table_args__ = (
        Index("idx_vm_cloud_init_snippets_user_kind_created", "user_id", "kind", "created_at"),
        UniqueConstraint("user_id", "kind", "name", name="uq_vm_cloud_init_snippet_user_kind_name"),
    )


class ResourcePolicy(Base):
    """Global admin-owned selection of a discovered OpenStack resource."""

    __tablename__ = "resource_policies"

    policy_key: Mapped[str] = mapped_column(VARCHAR(100), primary_key=True)
    resource_kind: Mapped[str] = mapped_column(VARCHAR(32), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(VARCHAR(128))
    resource_name: Mapped[str | None] = mapped_column(VARCHAR(255))
    constraints: Mapped[dict | None] = mapped_column(JSON)
    updated_by_user_id: Mapped[str | None] = mapped_column(VARCHAR(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    __table_args__ = (Index("idx_resource_policies_kind", "resource_kind"),)


class RuntimeSetting(Base):
    """Allowlisted scalar runtime settings owned by the administrator."""

    __tablename__ = "runtime_settings"

    setting_key: Mapped[str] = mapped_column(VARCHAR(100), primary_key=True)
    value_json: Mapped[object] = mapped_column(JSON, nullable=False)
    updated_by_user_id: Mapped[str | None] = mapped_column(VARCHAR(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)


class GpuQuota(Base):
    """프로젝트별 GPU 쿼타 설정 (Default project: __default__)."""

    __tablename__ = "gpu_quotas"

    id: Mapped[int] = mapped_column(INT, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    gpu_type: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    limit: Mapped[int] = mapped_column(INT, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    __table_args__ = (
        UniqueConstraint("project_id", "gpu_type", name="uq_gpu_quotas_project_gpu_type"),
        Index("idx_gpu_quotas_project_id", "project_id"),
    )


class GpuQuotaReservation(Base):
    """Short-lived GPU quota claim for an Afterglow-controlled admission."""

    __tablename__ = "gpu_quota_reservations"

    id: Mapped[int] = mapped_column(INT, primary_key=True, autoincrement=True)

    reservation_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    project_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    gpu_type: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    amount: Mapped[int] = mapped_column(INT, nullable=False)
    status: Mapped[str] = mapped_column(VARCHAR(16), nullable=False, default="pending")
    server_id: Mapped[str | None] = mapped_column(VARCHAR(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    __table_args__ = (
        UniqueConstraint("reservation_id", "gpu_type", name="uq_gpu_quota_reservation_type"),
        Index(
            "idx_gpu_quota_reservations_project_active",
            "project_id",
            "gpu_type",
            "status",
            "expires_at",
        ),
    )


class K3sProvisioningIntent(Base):
    """Durable, non-secret Stampede agent provisioning intent."""

    __tablename__ = "k3s_provisioning_intents"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    idempotency_key: Mapped[str] = mapped_column(VARCHAR(128), nullable=False, unique=True)
    project_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False, index=True)
    cluster_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    nodegroup_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    name: Mapped[str] = mapped_column(VARCHAR(128), nullable=False)
    flavor_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    image_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    network_id: Mapped[str] = mapped_column(VARCHAR(64), nullable=False)
    resource_metadata: Mapped[dict | None] = mapped_column("metadata", JSON)
    boot_volume_size_gb: Mapped[int] = mapped_column(INT, nullable=False)
    volume_availability_zone: Mapped[str] = mapped_column(VARCHAR(128), nullable=False)
    security_group_id: Mapped[str | None] = mapped_column(VARCHAR(64))
    config_drive: Mapped[bool] = mapped_column(BOOLEAN, nullable=False, default=False)
    request_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    state: Mapped[str] = mapped_column(VARCHAR(16), nullable=False, default="pending", index=True)
    error_message: Mapped[str | None] = mapped_column(TEXT)
    boot_volume_id: Mapped[str | None] = mapped_column(VARCHAR(64))
    server_id: Mapped[str | None] = mapped_column(VARCHAR(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    __table_args__ = (Index("idx_k3s_provisioning_intents_project_state", "project_id", "state"),)
