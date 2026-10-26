"""Operator-owned login registry; validation is static and never contacts an IdP."""

import ipaddress
import re
from typing import Annotated, Literal
from urllib.parse import parse_qsl, urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

# Single internal underscores only: trailing/doubled underscores collide with '__' env paths.
ProviderKey = Annotated[str, Field(max_length=32, pattern=r"^[a-z](?:[a-z0-9]|_[a-z0-9])*$", strict=True)]
DomainId = Annotated[str, Field(min_length=1, max_length=64, strict=True)]
KeystoneId = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.-]{1,64}$", strict=True)]
_DEFAULT_SCOPES = {"oidc": ["openid", "email", "profile"], "github": ["read:user", "user:email"]}
_GITHUB_ENDPOINTS = {
    "authorization_url": "https://github.com/login/oauth/authorize",
    "token_url": "https://github.com/login/oauth/access_token",
    "api_url": "https://api.github.com",
}
_RESERVED_QUERY = {
    "authorization_url": {
        "client_id",
        "redirect_uri",
        "response_type",
        "scope",
        "state",
        "nonce",
        "code_challenge",
        "code_challenge_method",
        "response_mode",
        "request",
        "request_uri",
    },
    "token_url": {"client_id", "client_secret", "code", "code_verifier", "grant_type", "redirect_uri"},
}


def _public_https_url(value: str, field: str) -> str:
    """Match runtime URL policy without DNS; runtime still checks/pins resolved IPs."""
    value = value.strip()
    invalid = ValueError("provider endpoints must be public HTTPS URLs without credentials or conflicting parameters")
    if not value or len(value) > 512 or any(char.isspace() or ord(char) < 32 for char in value):
        raise invalid
    try:
        parsed = urlsplit(value)
        hostname = (parsed.hostname or "").rstrip(".").encode("idna").decode("ascii").lower()
        port = parsed.port
    except (ValueError, UnicodeError):
        raise invalid from None
    if (
        parsed.scheme != "https"
        or not hostname
        or port not in (None, 443)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or (parsed.query and field in ("issuer_url", "api_url"))
        or hostname in {"localhost", "metadata", "metadata.google.internal"}
        or hostname.endswith(".localhost")
        or any(key in _RESERVED_QUERY.get(field, ()) for key, _ in parse_qsl(parsed.query, keep_blank_values=True))
    ):
        raise invalid
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        if not all(re.fullmatch(r"(?!-)[a-z0-9-]{1,63}(?<!-)", label) for label in hostname.split(".")):
            raise invalid from None
        if all(char in "0123456789." for char in hostname):
            raise invalid from None
    else:
        if not address.is_global or address.is_multicast:
            raise invalid
    return value


class _AuthModel(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class AuthOrganization(_AuthModel):
    """Operator trust boundary, never populated from arbitrary identity claims."""

    id: str = Field(min_length=1, max_length=255, strict=True)
    name: str = Field(min_length=1, max_length=64, strict=True)
    manager_subjects: list[str] = Field(min_length=1, max_length=100, strict=True)

    @field_validator("id", "name")
    @classmethod
    def exact_text(cls, value, info):
        if value != value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("organization identity and name must be exact nonempty text")
        if info.field_name == "name" and value.casefold() in {"account", "accounts", "personal"}:
            raise ValueError("reserved account spaces cannot name organizations")
        return value

    @field_validator("manager_subjects")
    @classmethod
    def stable_subjects(cls, values):
        if any(
            not isinstance(value, str)
            or not 1 <= len(value) <= 255
            or value != value.strip()
            or any(ord(char) < 32 or ord(char) == 127 for char in value)
            for value in values
        ):
            raise ValueError("organization managers require exact immutable OIDC subjects")
        return sorted(set(values))


class AuthNativeMapping(_AuthModel):
    """Exact operator pin for Keystone-owned ephemeral identity and project mapping."""

    mode: Literal["ephemeral"]
    mapping_id: KeystoneId
    sha256: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$", strict=True)
    account_domain_id: KeystoneId
    personal_domain_id: KeystoneId

    @model_validator(mode="after")
    def distinct_account_spaces(self):
        if self.account_domain_id == self.personal_domain_id:
            raise ValueError("native mapping account and personal domains must be distinct")
        return self


class AuthProvider(_AuthModel):
    name: str = Field(min_length=1, max_length=64, strict=True)
    kind: Literal["oidc", "github"]
    enabled: bool = True
    issuer_url: str | None = None
    authorization_url: str | None = None
    token_url: str | None = None
    api_url: str | None = None
    client_id: str = Field(min_length=1, max_length=255, strict=True)
    client_secret: SecretStr = Field(default=SecretStr(""), repr=False)
    scopes: list[str] = Field(default_factory=list)
    keystone_idp_id: KeystoneId
    keystone_protocol_id: KeystoneId
    federation_token_type: Literal["id_token", "access_token"] = "id_token"
    token_endpoint_auth_method: Literal["client_secret_basic", "client_secret_post"] = "client_secret_basic"
    organization: AuthOrganization | None = None
    native_mapping: AuthNativeMapping | None = None

    @model_validator(mode="before")
    @classmethod
    def kind_defaults(cls, value):
        if (
            not isinstance(value, dict)
            or not isinstance(value.get("kind"), str)
            or value["kind"] not in _DEFAULT_SCOPES
        ):
            return value
        value = dict(value)
        kind = value["kind"]
        value.setdefault("scopes", list(_DEFAULT_SCOPES[kind]))
        if kind == "github":
            value.setdefault("federation_token_type", "access_token")
            value.setdefault("token_endpoint_auth_method", "client_secret_post")
            for field, default in _GITHUB_ENDPOINTS.items():
                value.setdefault(field, default)
        return value

    @field_validator("enabled", mode="before")
    @classmethod
    def strict_boolean(cls, value):
        # Nested environment values arrive as strings; allow only TOML-style booleans.
        if isinstance(value, str) and value.lower() in ("true", "false"):
            return value.lower() == "true"
        if not isinstance(value, bool):
            raise ValueError("enabled must be a boolean")
        return value

    @field_validator("name", "client_id")
    @classmethod
    def bounded_text(cls, value: str, info) -> str:
        value = value.strip()
        if not value or any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("provider name and client ID must be nonempty text")
        if info.field_name == "client_id" and any(char.isspace() for char in value):
            raise ValueError("client ID must not contain whitespace")
        return value

    @field_validator("client_secret")
    @classmethod
    def bounded_secret(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) > 4096:
            raise ValueError("client secret exceeds maximum length")
        return value

    @model_validator(mode="after")
    def validate_provider(self):
        if self.native_mapping is not None:
            if self.kind != "oidc" or self.federation_token_type != "id_token":
                raise ValueError("native mapping requires OIDC id_token federation")
            if self.organization is not None:
                raise ValueError("native mapping owns organization grants and cannot configure organization")
        if self.enabled and not self.client_secret.get_secret_value().strip():
            raise ValueError("enabled providers require a client secret")
        if not 1 <= len(self.scopes) <= 20 or any(
            re.fullmatch(r"[\x21\x23-\x5B\x5D-\x7E]{1,128}", scope) is None for scope in self.scopes
        ):
            raise ValueError("provider scopes must be a bounded nonempty list of OAuth scope tokens")
        required = ("openid", "email") if self.kind == "oidc" else ("user:email",)
        if not all(scope in self.scopes for scope in required):
            raise ValueError("provider scopes must include the kind's required identity scopes")
        self.scopes = list(dict.fromkeys(self.scopes))
        if self.kind == "oidc":
            if any(getattr(self, field) is not None for field in _GITHUB_ENDPOINTS):
                raise ValueError("OIDC endpoints must be discovered from issuer_url")
            if self.issuer_url is None:
                raise ValueError("OIDC requires issuer_url")
            self.issuer_url = _public_https_url(self.issuer_url, "issuer_url")
        else:
            if self.organization is not None:
                raise ValueError("organization configuration requires a tenant-bound OIDC issuer/client")
            if self.issuer_url is not None:
                raise ValueError("GitHub providers must not configure issuer_url")
            if self.federation_token_type != "access_token" or self.token_endpoint_auth_method != "client_secret_post":
                raise ValueError("GitHub requires access_token federation and client_secret_post")
            for field in _GITHUB_ENDPOINTS:
                endpoint = getattr(self, field)
                if endpoint is None:
                    raise ValueError("GitHub endpoints must be public HTTPS URLs")
                setattr(self, field, _public_https_url(endpoint, field))
        return self


def normalize_auth_email_domain(value: object) -> str:
    """Static exact IDNA hostname normalization, shared with runtime policy."""
    if not isinstance(value, str):
        raise ValueError("Email domain must be a string")
    host = value.strip().rstrip(".")
    if not host or len(host) > 253 or "@" in host or "*" in host or any(c.isspace() for c in host):
        raise ValueError("Email domain is invalid")
    try:
        host = host.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise ValueError("Email domain is invalid") from exc
    labels = host.split(".")
    if (
        len(labels) < 2
        or not all(re.fullmatch(r"(?!-)[a-z0-9-]{1,63}(?<!-)", label) for label in labels)
        or labels[-1].isdigit()
    ):
        raise ValueError("Email domain is invalid")
    return host


def _auth_email_domains(values):
    if not isinstance(values, (list, tuple)) or len(values) > 100:
        raise ValueError("Email domains require a list of at most 100 exact hosts")
    return sorted({normalize_auth_email_domain(value) for value in values})


class AuthMethods(_AuthModel):
    # None inherits; an explicit empty list deliberately permits no provider.
    allow_providers: list[str] | None = Field(default=None, strict=True)
    auto_join_email_domains: dict[str, list[str]] | None = Field(default=None, strict=True)

    @field_validator("auto_join_email_domains")
    @classmethod
    def exact_auto_join_domains(cls, value):
        if value is None:
            return None
        return {key: _auth_email_domains(domains) for key, domains in value.items()}


class AuthSettings(_AuthModel):
    providers: dict[ProviderKey, AuthProvider] = Field(default_factory=dict)
    default: AuthMethods = Field(default_factory=AuthMethods)
    domain: dict[DomainId, AuthMethods] = Field(default_factory=dict)
    public_signup_enabled: bool = False
    public_signup_button_visible: bool = Field(default=True, strict=True)
    signup_email_domains: list[str] = Field(default_factory=list)
    organization_creation_enabled: bool = True
    max_organizations_per_user: int = Field(default=10, ge=0, le=10000, strict=True)

    @field_validator("public_signup_button_visible", mode="before")
    @classmethod
    def signup_button_boolean(cls, value):
        if isinstance(value, str) and value.lower() in {"true", "false"}:
            return value.lower() == "true"
        if not isinstance(value, bool):
            raise ValueError("public_signup_button_visible must be a boolean")
        return value

    @field_validator("organization_creation_enabled", mode="before")
    @classmethod
    def creation_boolean(cls, value):
        if isinstance(value, str) and value.lower() in {"true", "false"}:
            return value.lower() == "true"
        if not isinstance(value, bool):
            raise ValueError("organization_creation_enabled must be a boolean")
        return value

    @field_validator("max_organizations_per_user", mode="before")
    @classmethod
    def organization_limit(cls, value):
        if isinstance(value, str) and re.fullmatch(r"[0-9]+", value):
            return int(value)
        return value

    @field_validator("signup_email_domains")
    @classmethod
    def exact_signup_domains(cls, value):
        return _auth_email_domains(value)

    @model_validator(mode="after")
    def valid_references(self):
        for domain_id in self.domain:
            if domain_id != domain_id.strip() or any(char.isspace() or ord(char) < 32 for char in domain_id):
                raise ValueError("auth domain keys must be exact canonical Keystone domain IDs")
        organizations = {}
        for provider in self.providers.values():
            if provider.organization is None:
                continue
            identity = (provider.issuer_url, provider.organization.id)
            trust = provider.organization.model_dump()
            if organizations.setdefault(identity, trust) != trust:
                raise ValueError("one issuer organization requires one exact trust definition")
        for methods in (self.default, *self.domain.values()):
            for key in [*(methods.allow_providers or []), *(methods.auto_join_email_domains or {})]:
                if key in self.providers:
                    continue
                try:
                    if str(UUID(key)) == key:
                        continue
                except ValueError:
                    pass
                raise ValueError("auth provider selectors require a registry key or canonical SQL provider UUID")
        return self
