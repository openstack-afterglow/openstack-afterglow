import re

from pydantic import BaseModel, field_validator


class ClusterTemplateInfo(BaseModel):
    id: str
    name: str
    coe: str  # kubernetes, swarm, mesos
    image_id: str | None = None
    flavor_id: str | None = None
    master_flavor_id: str | None = None
    network_driver: str | None = None
    public: bool = False
    hidden: bool = False
    created_at: str | None = None


class ClusterInfo(BaseModel):
    id: str
    name: str
    status: str
    status_reason: str | None = None
    cluster_template_id: str | None = None
    master_count: int = 1
    node_count: int = 1
    api_address: str | None = None
    coe_version: str | None = None
    keypair: str | None = None
    create_timeout: int | None = None
    created_at: str | None = None
    updated_at: str | None = None
    stack_id: str | None = None


_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,62}$")


def _validate_resource_name(v: str) -> str:
    if not _NAME_RE.match(v):
        raise ValueError("name은 영문자/숫자로 시작하고, 영문자·숫자·하이픈·언더스코어만 허용되며 최대 63자입니다")
    return v


class CreateClusterRequest(BaseModel):
    name: str
    cluster_template_id: str
    node_count: int = 1
    master_count: int = 1
    keypair: str | None = None
    create_timeout: int | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return _validate_resource_name(v)


class ZunContainerInfo(BaseModel):
    uuid: str
    name: str
    status: str
    status_reason: str | None = None
    image: str | None = None
    command: str | None = None
    cpu: float | None = None
    memory: str | None = None
    created_at: str | None = None
    addresses: dict | None = None
    host: str | None = None
    project_id: str | None = None


class PortMapping(BaseModel):
    container_port: int
    host_port: int | None = None
    protocol: str = "tcp"


class CreateZunContainerRequest(BaseModel):
    name: str
    image: str
    command: str | None = None
    cpu: float | None = None
    memory: str | None = None
    environment: dict[str, str] | None = None
    ports: list[PortMapping] | None = None
    auto_remove: bool = False

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return _validate_resource_name(v)


class ContainerListResponse(BaseModel):
    items: list[ZunContainerInfo]
    service_available: bool = True
    message: str = ""


class StackResourceInfo(BaseModel):
    resource_name: str
    resource_type: str
    physical_resource_id: str
    resource_status: str
    resource_status_reason: str | None = None
    created_at: str | None = None


class StackEventInfo(BaseModel):
    resource_name: str
    resource_status: str
    resource_status_reason: str | None = None
    event_time: str
    logical_resource_id: str | None = None
    physical_resource_id: str | None = None
