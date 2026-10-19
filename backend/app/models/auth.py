from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    username: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=1, max_length=1024)


class LoginProviderOption(BaseModel):
    id: str
    name: str
    kind: str
    domain_id: str
    domain_name: str


class LoginOptionsResponse(BaseModel):
    providers: list[LoginProviderOption] = Field(default_factory=list)


class DomainInfo(BaseModel):
    id: str
    name: str


class TokenResponse(BaseModel):
    token: str  # access JWT (신규 클라이언트) — 이전 Keystone 토큰 필드명 유지
    refresh_token: str | None = None
    project_id: str
    project_name: str
    user_id: str
    username: str
    domain_id: str
    domain_name: str
    is_domain_manager: bool = False
    identity_domain_id: str
    identity_domain_name: str
    available_domains: list[DomainInfo] = Field(default_factory=list)
    can_create_domain: bool = False
    expires_at: str  # access JWT 만료 ISO8601
    roles: list[str] = []
    default_project_id: str = ""
    is_system_admin: bool = False
    can_write: bool = False
    auth_method: str = "password"


class UserInfo(BaseModel):
    user_id: str
    username: str
    project_id: str
    project_name: str
    roles: list[str]
    domain_id: str
    domain_name: str
    is_domain_manager: bool = False
    identity_domain_id: str
    identity_domain_name: str
    available_domains: list[DomainInfo] = Field(default_factory=list)
    can_create_domain: bool = False
    is_system_admin: bool = False
    can_write: bool = False
    auth_method: str = "password"


class ProjectInfo(BaseModel):
    id: str
    name: str
    description: str = ""
    domain_id: str | None = None
    domain_name: str | None = None
    enabled: bool = True
    last_accessed_at: str | None = None


class WorkspaceInfo(BaseModel):
    domain: DomainInfo
    projects: list[ProjectInfo]
    default_project_id: str
    is_domain_manager: bool
    can_create_project: bool
