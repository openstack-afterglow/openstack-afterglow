from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=1, max_length=1024)
    project_name: str = Field("", max_length=255)
    domain_name: str = Field("Default", max_length=255)


class TokenResponse(BaseModel):
    token: str  # access JWT (신규 클라이언트) — 이전 Keystone 토큰 필드명 유지
    refresh_token: str | None = None
    project_id: str
    project_name: str
    user_id: str
    username: str
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


class GitLabCallbackRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=2048)
    state: str = Field(..., min_length=1, max_length=256)
