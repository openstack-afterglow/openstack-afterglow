import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class IpAddress(BaseModel):
    addr: str
    type: str = "fixed"  # "fixed" | "floating"
    network_name: str = ""


class ImageInfo(BaseModel):
    id: str
    name: str
    status: str
    repository: str = ""
    tag: str = "latest"
    size: int | None = None
    min_disk: int = 0
    min_ram: int = 0
    disk_format: str | None = None
    os_type: str | None = None
    os_distro: str | None = None
    created_at: str | None = None
    owner: str | None = None
    visibility: str | None = None


class ImageDetail(ImageInfo):
    checksum: str | None = None
    container_format: str | None = None
    virtual_size: int | None = None
    updated_at: str | None = None
    protected: bool = False
    tags: list[str] = []
    properties: dict = {}
    os_hash_algo: str | None = None
    os_hash_value: str | None = None
    direct_url: str | None = None


class FlavorQuotaBlocker(BaseModel):
    code: str
    resource: str | None = None
    required: int | None = None
    remaining: int | None = None


class FlavorDemandInfo(BaseModel):
    instances: int
    cores: int
    ram_mb: int
    gpus: dict[str, int] = {}


class FlavorRemainingInfo(BaseModel):
    instances: int
    cores: int
    ram_mb: int
    gpus: dict[str, int] = {}


class FlavorEligibility(BaseModel):
    selectable: bool
    requirements: FlavorDemandInfo
    remaining: FlavorRemainingInfo
    blockers: list[FlavorQuotaBlocker] = []


class FlavorInfo(BaseModel):
    id: str
    name: str
    vcpus: int
    ram: int  # MB
    disk: int  # GB
    is_public: bool = True
    extra_specs: dict = {}
    eligibility: FlavorEligibility | None = None

    @property
    def is_gpu(self) -> bool:
        from app.services.gpu_inventory import is_gpu_flavor

        return is_gpu_flavor(self)

    @property
    def gpu_count(self) -> int:
        m = re.match(r"^gpu\.\w+?(?:x(\d+))?_", self.name)
        if not m:
            return 0
        return int(m.group(1)) if m.group(1) else 1


class InstanceInfo(BaseModel):
    id: str
    name: str
    status: str
    image_id: str | None = None
    image_name: str | None = None
    flavor_id: str | None = None
    flavor_name: str | None = None
    ip_addresses: list[IpAddress] = []
    created_at: str | None = None
    metadata: dict = {}
    # Union 전용 메타데이터
    union_libraries: list[str] = []
    union_strategy: str | None = None  # "prebuilt" | "dynamic"
    union_share_ids: list[str] = []
    union_upper_volume_id: str | None = None
    scheduling: str | None = None  # "standard" | "ha"
    key_name: str | None = None
    user_id: str | None = None
    project_id: str | None = None
    fault: dict | None = None  # OpenStack 서버 fault: {"message": "...", "code": 500, "created": "..."}
    host: str | None = None  # 현재 하이퍼바이저 호스트 (관리자 스코프에서만 채워짐)


class CreateInstanceRequest(BaseModel):
    name: str | None = None
    image_id: str | None = None
    flavor_id: str
    libraries: list[str] = []
    strategy: str | None = None  # "prebuilt" | "dynamic" | None (no libraries)
    scheduling: Literal["standard", "ha"] = "standard"
    network_id: str | None = None
    key_name: str | None = None
    github_username: str | None = None
    admin_pass: str | None = Field(None, min_length=8, max_length=128)
    availability_zone: str | None = None
    security_groups: list[str] = []
    userdata: str | None = None
    boot_volume_size_gb: int | None = Field(None, ge=1, le=16384)
    delete_boot_volume_on_termination: bool = False
    additional_volume_ids: list[str] = []
    new_volumes: list["NewVolumeRequest"] = []
    existing_upper_volume_id: str | None = None
    boot_volume_id: str | None = None  # 기존 부팅 볼륨 재사용 (image_id 와 상호 배타)
    data_mounts: list["DataMountSpec"] = []  # 기존 Manila share 직접 마운트 목록

    @model_validator(mode="after")
    def validate_boot_source(self) -> "CreateInstanceRequest":
        has_image = bool(self.image_id)
        has_volume = bool(self.boot_volume_id)
        if has_image and has_volume:
            raise ValueError("image_id와 boot_volume_id를 동시에 지정할 수 없습니다")
        if not has_image and not has_volume:
            raise ValueError("image_id 또는 boot_volume_id 중 하나는 반드시 지정해야 합니다")
        if self.github_username and self.key_name:
            raise ValueError("github_username과 key_name은 함께 사용할 수 없습니다")
        return self

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str | None) -> str | None:
        from app.services.instance_names import normalize_requested_instance_name

        return normalize_requested_instance_name(v)

    @field_validator("github_username")
    @classmethod
    def validate_github_username(cls, v: str | None) -> str | None:
        from app.services.ssh_access import normalize_github_username

        return normalize_github_username(v)


class NewVolumeRequest(BaseModel):
    name: str = ""
    size_gb: int = 50

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if v and not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,254}$", v):
            raise ValueError("볼륨 이름은 영문자/숫자로 시작해야 합니다")
        return v

    @field_validator("size_gb")
    @classmethod
    def validate_size(cls, v: int) -> int:
        if v < 1 or v > 16384:
            raise ValueError("볼륨 크기는 1~16384 GB 범위여야 합니다")
        return v


class CloudInitSnippetInfo(BaseModel):
    id: int
    kind: Literal["history", "preset"]
    name: str | None = None
    content: str
    created_at: str | None = None
    updated_at: str | None = None


class CloudInitSnippetLibrary(BaseModel):
    history: list[CloudInitSnippetInfo]
    presets: list[CloudInitSnippetInfo]


class CreateCloudInitPresetRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=65536)


_ALLOWED_MOUNT_PREFIXES = ("/mnt/", "/data/", "/srv/", "/home/")
_MOUNT_POINT_RE = re.compile(r"^/(mnt|data|srv|home)(/[A-Za-z0-9._-]+)*$")
_BLOCKED_MOUNT_PREFIXES = ("/opt/layers", "/opt/", "/etc/", "/usr/", "/var/", "/sys/", "/proc/", "/dev/", "/run/")


class DataMountSpec(BaseModel):
    """VM 생성/연결 시 기존 Manila share를 사용자 지정 경로에 마운트하는 스펙."""

    file_storage_id: str
    mount_point: str
    read_only: bool = False

    @field_validator("mount_point")
    @classmethod
    def validate_mount_point(cls, v: str) -> str:
        if not _MOUNT_POINT_RE.match(v):
            raise ValueError(
                "mount_point는 /mnt, /data, /srv, /home 하위 절대 경로여야 하며, "
                "영문자·숫자·점·하이픈·언더스코어만 허용됩니다 (예: /mnt/mydata)"
            )
        if any(seg in (".", "..") for seg in v.split("/")):
            raise ValueError("mount_point에 '..' 또는 '.' 세그먼트는 허용되지 않습니다")
        for blocked in _BLOCKED_MOUNT_PREFIXES:
            if v == blocked.rstrip("/") or v.startswith(blocked):
                raise ValueError(f"mount_point로 {blocked} 하위 경로는 허용되지 않습니다")
        return v


class StorageAttachRequest(BaseModel):
    file_storage_id: str
    mount_point: str
    read_only: bool = False

    @field_validator("mount_point")
    @classmethod
    def validate_mount_point(cls, v: str) -> str:
        if not _MOUNT_POINT_RE.match(v):
            raise ValueError("mount_point는 /mnt, /data, /srv, /home 하위 절대 경로여야 합니다 (예: /mnt/mydata)")
        if any(seg in (".", "..") for seg in v.split("/")):
            raise ValueError("mount_point에 '..' 또는 '.' 세그먼트는 허용되지 않습니다")
        for blocked in _BLOCKED_MOUNT_PREFIXES:
            if v == blocked.rstrip("/") or v.startswith(blocked):
                raise ValueError(f"mount_point로 {blocked} 하위 경로는 허용되지 않습니다")
        return v


class AttachVolumeRequest(BaseModel):
    volume_id: str


class UpdateVolumeAttachmentRequest(BaseModel):
    delete_on_termination: bool


class AttachInterfaceRequest(BaseModel):
    net_id: str


class UpdateSecurityGroupsRequest(BaseModel):
    security_group_ids: list[str] = []


class AdminPasswordRequest(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)


class AdminPasswordPrecheck(BaseModel):
    supported: bool
    reason: str | None = None
    os_admin_user: str | None = None
    server_status: str
