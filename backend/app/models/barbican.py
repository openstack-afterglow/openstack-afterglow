from __future__ import annotations
from typing import Any
from pydantic import BaseModel


class SecretInfo(BaseModel):
    id: str
    name: str | None = None
    secret_type: str = "opaque"
    status: str | None = None
    algorithm: str | None = None
    bit_length: int | None = None
    mode: str | None = None
    created: str | None = None
    expires: str | None = None
    content_types: dict | None = None
    system_managed: bool = False


class SecretCreateRequest(BaseModel):
    name: str
    secret_type: str = "opaque"
    payload: str | None = None
    payload_content_type: str = "text/plain"
    algorithm: str | None = None
    bit_length: int | None = None
    mode: str | None = None
    expiration: str | None = None


class ContainerInfo(BaseModel):
    id: str
    name: str | None = None
    type: str
    status: str | None = None
    created: str | None = None
    secret_refs: list[dict] = []


class ContainerCreateRequest(BaseModel):
    name: str
    container_type: str = "generic"
    secret_refs: list[dict] = []


class OrderInfo(BaseModel):
    id: str
    type: str
    status: str | None = None
    created: str | None = None
    secret_ref: str | None = None
    container_ref: str | None = None
    meta: dict = {}
    error_reason: str | None = None


class OrderCreateRequest(BaseModel):
    order_type: str
    meta: dict[str, Any]


class AclSetRequest(BaseModel):
    users: list[str] = []
    project_access: bool = True


class QuotaInfo(BaseModel):
    secrets: int = -1
    orders: int = -1
    containers: int = -1
    consumers: int = -1
    cas: int = -1


class ProjectQuotaSetRequest(BaseModel):
    secrets: int | None = None
    orders: int | None = None
    containers: int | None = None
    consumers: int | None = None
    cas: int | None = None
