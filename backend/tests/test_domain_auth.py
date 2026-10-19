"""Domain login policy/provider authority: persisted SQL, fakeredis state, signed
OIDC tokens and a scripted IdP/Keystone wire. No real provider or cloud is used."""

from __future__ import annotations

import base64
import hashlib
import json
import time
from contextlib import asynccontextmanager
from types import SimpleNamespace
from urllib.parse import parse_qs, unquote_plus, urlsplit

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from keystoneauth1.exceptions.http import NotFound
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app import database
from app.models.domain_auth import DomainIdentityProvider, DomainLoginPolicy
from app.models.domain_iam import DomainEnrollment
from app.models.domain_quotas import DomainQuotaPolicy
from app.models.enrollment_policy import EnrollmentPolicy, SignupRequest
from app.services import domain_auth as svc
from app.services.mcp_control_plane import ssrf

ISSUER = "https://idp.example.com"
CLIENT_ID = "afterglow-client"
SECRET = "super-secret-client-value-0123456789"


# ── fixtures ────────────────────────────────────────────────────────────────


class FakeKeystone:
    """Native Keystone admin read surface for domains and federation config."""

    def __init__(self):
        self.domain_rows = {
            "dom-a": SimpleNamespace(id="dom-a", name="Alpha", enabled=True),
            "dom-b": SimpleNamespace(id="dom-b", name="Beta", enabled=True),
            "dom-off": SimpleNamespace(id="dom-off", name="Off", enabled=False),
        }
        self.idps = {
            "idp-a": SimpleNamespace(id="idp-a", domain_id="dom-a", enabled=True),
            "idp-b": SimpleNamespace(id="idp-b", domain_id="dom-b", enabled=True),
        }
        self.user_rows = {
            "fed-user": SimpleNamespace(
                id="fed-user",
                name="dev",
                domain_id="dom-a",
                enabled=True,
                email="Dev@corp.example",
                federated=[
                    {
                        "idp_id": "idp-a",
                        "protocols": [
                            {"protocol_id": "openid", "unique_id": "subject-1"},
                            {"protocol_id": "github", "unique_id": "123"},
                        ],
                    }
                ],
                afterglow_external_identities=[
                    {"issuer": ISSUER, "subject": "subject-1"},
                    {"issuer": "https://api.github.com", "subject": "123"},
                ],
            )
        }
        self.user_writes = []
        self.domain_writes = []
        self.project_writes = []
        self.project_rows = {}
        self.assignments = []
        self.catalog = []
        self.mapping_rules = [{"local": [{"user": {"id": "{0}", "name": "{0}"}}], "remote": [{"type": "OIDC-sub"}]}]
        outer = self

        class Domains:
            def get(self, name_or_id):
                if name_or_id in outer.domain_rows:
                    return outer.domain_rows[name_or_id]
                raise NotFound()

            def list(self, name=None):
                return [row for row in outer.domain_rows.values() if name is None or row.name == name]

            def create(self, name, **kwargs):
                did = f"personal-domain-{len(outer.domain_writes)}"
                outer.domain_writes.append(("create", did, kwargs))
                outer.domain_rows[did] = SimpleNamespace(id=did, name=name, **kwargs)
                return outer.domain_rows[did]

            def update(self, did, **kwargs):
                for key, value in kwargs.items():
                    setattr(outer.domain_rows[did], key, value)
                return outer.domain_rows[did]

            def delete(self, did):
                del outer.domain_rows[did]

        class Idps:
            def get(self, idp_id):
                if idp_id in outer.idps:
                    return outer.idps[idp_id]
                raise NotFound()

        class Protocols:
            def get(self, idp_id, protocol_id):
                if protocol_id not in {"openid", "team_oidc", "github"}:
                    raise NotFound()
                return SimpleNamespace(id=protocol_id, mapping_id="stable-subject")

        self.domains = Domains()
        self.federation = SimpleNamespace(
            identity_providers=Idps(),
            protocols=Protocols(),
            mappings=SimpleNamespace(get=lambda _: SimpleNamespace(rules=outer.mapping_rules)),
        )

        class Users:
            def get(self, uid):
                if uid not in outer.user_rows:
                    raise NotFound()
                return outer.user_rows[uid]

            def list(self, domain=None, name=None, **kwargs):
                rows = [
                    user
                    for user in outer.user_rows.values()
                    if (domain is None or user.domain_id == domain) and (name is None or user.name == name)
                ]
                if "unique_id" in kwargs:
                    rows = [
                        user
                        for user in rows
                        if any(
                            item["idp_id"] == kwargs["idp_id"]
                            and any(
                                protocol["protocol_id"] == kwargs["protocol_id"]
                                and protocol["unique_id"] == kwargs["unique_id"]
                                for protocol in item["protocols"]
                            )
                            for item in getattr(user, "federated", [])
                        )
                    ]
                return rows

            def update(self, uid, **kwargs):
                outer.user_writes.append(("update", uid, kwargs))
                for key, value in kwargs.items():
                    setattr(outer.user_rows[uid], key, value)
                return outer.user_rows[uid]

            def create(self, name, domain, **kwargs):
                outer.user_writes.append(("create", "new-user", kwargs))
                user = SimpleNamespace(id="new-user", name=name, domain_id=domain, **kwargs)
                outer.user_rows[user.id] = user
                return user

            def delete(self, uid):
                del outer.user_rows[uid]

        self.users = Users()

        class Projects:
            def list(self, domain=None, **kwargs):
                return [p for p in outer.project_rows.values() if domain is None or p.domain_id == domain]

            def get(self, pid):
                if pid not in outer.project_rows:
                    raise NotFound()
                return outer.project_rows[pid]

            def create(self, name, domain, **kwargs):
                pid = f"personal-project-{len(outer.project_writes)}"
                outer.project_writes.append(("create", pid, kwargs))
                outer.project_rows[pid] = SimpleNamespace(id=pid, name=name, domain_id=domain, **kwargs)
                return outer.project_rows[pid]

            def update(self, pid, **kwargs):
                outer.project_writes.append(("update", pid, kwargs))
                for key, value in kwargs.items():
                    setattr(outer.project_rows[pid], key, value)
                return outer.project_rows[pid]

            def delete(self, pid):
                del outer.project_rows[pid]

        def assignments(project=None, user=None, **kwargs):
            return [
                row
                for row in outer.assignments
                if (project is None or row["scope"]["project"]["id"] == project)
                and (user is None or row["user"]["id"] == user)
            ]

        def grant(role_id, *, user, project):
            row = {"user": {"id": user}, "role": {"id": role_id}, "scope": {"project": {"id": project}}}
            if row not in outer.assignments:
                outer.assignments.append(row)

        def revoke(role_id, *, user, project):
            outer.assignments[:] = [
                row
                for row in outer.assignments
                if not (
                    row["role"]["id"] == role_id
                    and row["user"]["id"] == user
                    and row["scope"]["project"]["id"] == project
                )
            ]

        self.projects = Projects()
        self.role_assignments = SimpleNamespace(list=assignments)
        self.roles = SimpleNamespace(list=lambda: outer.catalog, grant=grant, revoke=revoke)
        self.inference_rules = SimpleNamespace(
            list_inference_roles=lambda: [
                {"prior_role": {"id": row["id"]}, "implies": [{"id": child} for child in row["implied_role_ids"]]}
                for row in outer.catalog
            ]
        )


@pytest.fixture
def settings(monkeypatch):
    value = SimpleNamespace(
        smtp_enabled=False,
        smtp_host="",
        frontend_base_url="https://cloud.example.com",
        public_api_base="https://api.example.com",
        os_auth_url="https://keystone.test/v3",
        os_user_domain_name="dom-a",
        ssl_verify=True,
    )
    monkeypatch.setattr(svc, "get_settings", lambda: value)
    return value


@pytest.fixture
def keystone_admin(monkeypatch):
    from app.services import keystone

    fake = FakeKeystone()
    monkeypatch.setattr(keystone, "_get_admin_ks_client", lambda: fake)
    revoked = []
    monkeypatch.setattr(keystone, "revoke_token", lambda token: revoked.append(token))
    fake.revoked = revoked
    return fake


@pytest.fixture(autouse=True)
def public_dns(monkeypatch):
    """Public names resolve to a public address; private literals stay blocked."""
    monkeypatch.setattr(ssrf, "_resolve_public_addresses_sync", lambda host, port: ["93.184.216.34"])


@pytest.fixture
async def db(monkeypatch, tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'domain-auth.sqlite'}")
    async with engine.begin() as connection:
        await connection.run_sync(DomainLoginPolicy.__table__.create)
        await connection.run_sync(DomainIdentityProvider.__table__.create)
        await connection.run_sync(DomainEnrollment.__table__.create)
        await connection.run_sync(DomainQuotaPolicy.__table__.create)
        await connection.run_sync(EnrollmentPolicy.__table__.create)
        await connection.run_sync(SignupRequest.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, "is_db_available", lambda: True)
    monkeypatch.setattr(database, "get_session_factory", lambda: factory)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.fixture
def env(settings, keystone_admin, db, wire, monkeypatch):
    from app.services import domain_iam

    class Lease:
        async def assert_owned(self):
            pass

    @asynccontextmanager
    async def graph():
        yield Lease(), keystone_admin, keystone_admin.catalog

    monkeypatch.setattr(domain_iam, "_iam_write", graph)
    return SimpleNamespace(settings=settings, keystone=keystone_admin, db=db, wire=wire)


def oidc_fields(**overrides):
    fields = {
        "name": "Corp SSO",
        "kind": "oidc",
        "issuer_url": ISSUER,
        "client_id": CLIENT_ID,
        "client_secret": SECRET,
        "keystone_idp_id": "idp-a",
        "keystone_protocol_id": "openid",
    }
    fields.update(overrides)
    if fields["kind"] == "github" and "keystone_protocol_id" not in overrides:
        fields["keystone_protocol_id"] = "github"
    return fields


def configure_file_auth(settings, *, providers=None, default=None, domains=None):
    """Use the real shared config model, not a parallel runtime-only fixture DTO."""
    from app.config import AuthSettings

    settings.auth = AuthSettings.model_validate(
        {
            "providers": {"corp": oidc_fields()} if providers is None else providers,
            "default": {"allow_providers": default},
            "domain": {key: {"allow_providers": value} for key, value in (domains or {}).items()},
        }
    )
    return settings.auth


class FakeIdp:
    """Scripted OIDC/GitHub wire that really signs ID tokens and checks PKCE."""

    def __init__(self):
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
        jwk.update(kid="k1", use="sig", alg="RS256")
        self.jwks = {"keys": [jwk]}
        self.nonce = None
        self.challenge = None
        self.claims: dict = {}
        self.signing_key = self.key
        self.github_emails = [{"email": "dev@corp.example", "primary": True, "verified": True}]
        self.requests: list[httpx.Request] = []
        self.token_redirect = False
        self.client_secret = SECRET
        self.issuer = ISSUER
        self.auth_methods = None
        self.userinfo_enabled = False
        self.userinfo_subject = "subject-1"
        self.authorization_query = ""
        self.token_query = ""

    def remember(self, authorize_url: str):
        query = parse_qs(urlsplit(authorize_url).query)
        self.nonce = query.get("nonce", [None])[0]
        self.challenge = query["code_challenge"][0]
        return query["state"][0]

    def id_token(self):
        now = int(time.time())
        claims = {
            "iss": ISSUER,
            "aud": CLIENT_ID,
            "sub": "subject-1",
            "iat": now,
            "exp": now + 300,
            "nonce": self.nonce,
            "email": "Dev@Corp.Example",
            "email_verified": True,
        }
        claims.update(self.claims)
        claims = {k: v for k, v in claims.items() if v is not None}
        return jwt.encode(claims, self.signing_key, algorithm="RS256", headers={"kid": "k1"})

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url)
        bare_url = url.split("?", 1)[0]
        if bare_url == f"{self.issuer}/.well-known/openid-configuration":
            document = {
                "issuer": self.issuer,
                "authorization_endpoint": f"{self.issuer}/authorize" + self.authorization_query,
                "token_endpoint": f"{self.issuer}/token" + self.token_query,
                "jwks_uri": f"{self.issuer}/jwks",
                "code_challenge_methods_supported": ["S256"],
            }
            if self.auth_methods is not None:
                document["token_endpoint_auth_methods_supported"] = self.auth_methods
            if self.userinfo_enabled:
                document["userinfo_endpoint"] = f"{self.issuer}/userinfo"
            return httpx.Response(200, json=document)
        if bare_url == f"{self.issuer}/jwks":
            return httpx.Response(200, json=self.jwks)
        if bare_url == f"{self.issuer}/userinfo":
            assert request.headers["authorization"] == "Bearer at"
            return httpx.Response(
                200, json={"sub": self.userinfo_subject, "email": "Dev@corp.example", "email_verified": True}
            )
        if bare_url in (f"{self.issuer}/token", "https://github.com/login/oauth/access_token"):
            if self.token_redirect:
                return httpx.Response(302, headers={"Location": "http://169.254.169.254/latest/meta-data/"})
            form = parse_qs(request.content.decode())
            verifier = form["code_verifier"][0]
            derived = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
            if "authorization" in request.headers:
                assert "client_secret" not in form and "client_id" not in form
                raw = base64.b64decode(request.headers["authorization"].split(" ")[1]).decode()
                client_id, secret = (unquote_plus(value) for value in raw.split(":", 1))
            else:
                client_id, secret = form["client_id"][0], form["client_secret"][0]
            if (
                derived != self.challenge
                or client_id != CLIENT_ID
                or secret != self.client_secret
                or form["code"][0] != "good-code"
            ):
                return httpx.Response(400, json={"error": "invalid_grant"})
            if form["redirect_uri"][0] != "https://cloud.example.com/auth/callback":
                return httpx.Response(400, json={"error": "invalid_grant"})
            if "github" in url:
                return httpx.Response(200, json={"access_token": "gh-access", "token_type": "bearer"})
            return httpx.Response(200, json={"access_token": "at", "id_token": self.id_token()})
        if url == "https://api.github.com/user/emails":
            assert request.headers["authorization"] == "Bearer gh-access"
            return httpx.Response(200, json=self.github_emails)
        if url == "https://api.github.com/user":
            assert request.headers["authorization"] == "Bearer gh-access"
            return httpx.Response(200, json={"id": 123, "login": "mutable-login"})
        return httpx.Response(404)


class FakeFederation:
    def __init__(self):
        self.domain_id = "dom-a"
        self.idp_id = "idp-a"
        self.protocol_id = None
        self.user_id = "fed-user"
        self.status = 201
        self.calls: list[httpx.Request] = []
        self.federation_block = True
        self.native_users = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        if self.status != 201:
            return httpx.Response(self.status)
        user = {
            "id": self.user_id,
            "name": "dev",
            "domain": {"id": self.domain_id, "name": "Alpha"},
        }
        if self.native_users is not None and self.user_id in self.native_users:
            native = self.native_users[self.user_id]
            user["domain"] = {"id": native.domain_id}
            user["name"] = native.name
        if self.federation_block:
            user["OS-FEDERATION"] = {
                "identity_provider": {"id": self.idp_id},
                "protocol": {"id": self.protocol_id or request.url.path.split("/")[-2]},
            }
        return httpx.Response(201, headers={"X-Subject-Token": "unscoped-fed"}, json={"token": {"user": user}})


@pytest.fixture
def wire(monkeypatch):
    idp, federation = FakeIdp(), FakeFederation()
    monkeypatch.setattr(svc, "_provider_transport", lambda: httpx.MockTransport(idp.handler))
    monkeypatch.setattr(
        svc, "_keystone_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(federation.handler))
    )
    return SimpleNamespace(idp=idp, federation=federation)


async def start(idp: FakeIdp, provider_id: str, domain_id: str = "dom-a"):
    begun = await svc.start_authorization(domain_id, provider_id)
    state = idp.remember(begun.authorize_url)
    return state, begun.browser_binding


# ── email policy ────────────────────────────────────────────────────────────


def test_email_policy_is_exact_normalized_and_signup_is_opt_in():
    policy = svc.LoginPolicy("dom-a", allowed_email_domains=("corp.example",))
    assert svc.enforce_email(policy, " Dev@CORP.example ") == "Dev@corp.example"
    for denied in ("dev@sub.corp.example", "dev@corp.example.evil", "dev@evilcorp.example", "no-at", ""):
        with pytest.raises(svc.DomainAuthDenied):
            svc.enforce_email(policy, denied)
    assert svc.enforce_email(svc.LoginPolicy("dom-a"), "anyone@else.example") == "anyone@else.example"
    with pytest.raises(svc.DomainAuthDenied) as exc:
        svc.enforce_email(policy, "dev@corp.example", signup=True)
    assert exc.value.code == "signup_disabled"
    signup = svc.LoginPolicy(
        "dom-a",
        allowed_email_domains=("corp.example", "partner.example"),
        signup_enabled=True,
        signup_email_domains=("corp.example",),
    )
    assert svc.enforce_email(signup, "new@corp.example", signup=True) == "new@corp.example"
    with pytest.raises(svc.DomainAuthDenied):
        svc.enforce_email(signup, "new@partner.example", signup=True)
    for bad in ("*.corp.example", "user@corp.example", "localhost", "corp"):
        with pytest.raises(svc.DomainAuthInvalid):
            svc.normalize_email_domain(bad)


async def test_unconfigured_domain_defaults_and_password_policy(env):
    policy = await svc.get_policy("dom-a")
    assert (policy.password_enabled, policy.signup_enabled, policy.allowed_email_domains, policy.configured) == (
        True,
        False,
        (),
        False,
    )
    # Unrestricted allowlist does not require an email for existing accounts.
    assert (await svc.require_password("dom-a", None)).password_enabled is True
    await svc.update_policy(
        "dom-a",
        actor_user_id="mgr",
        password_enabled=True,
        allowed_email_domains=["Corp.Example"],
        signup_enabled=False,
        signup_email_domains=[],
    )
    await svc.require_password("dom-a", "a@corp.example")
    for email in (None, "a@other.example"):
        with pytest.raises(svc.DomainAuthDenied):
            await svc.require_password("dom-a", email)
    # Another domain's policy is independent.
    await svc.require_password("dom-b", "a@other.example")


async def test_policy_cannot_remove_last_login_method_or_fake_smtp(env):
    with pytest.raises(svc.DomainAuthConflict) as exc:
        await svc.update_policy(
            "dom-a",
            actor_user_id="mgr",
            password_enabled=False,
            allowed_email_domains=[],
            signup_enabled=False,
            signup_email_domains=[],
        )
    assert exc.value.code == "last_login_method"
    with pytest.raises(svc.DomainAuthConflict) as exc:
        await svc.update_policy(
            "dom-a",
            actor_user_id="mgr",
            password_enabled=True,
            allowed_email_domains=[],
            signup_enabled=True,
            signup_email_domains=["corp.example"],
        )
    assert exc.value.code == "smtp_not_configured"
    env.settings.smtp_enabled, env.settings.smtp_host = True, "smtp.example"
    with pytest.raises(svc.DomainAuthInvalid) as exc:
        await svc.update_policy(
            "dom-a",
            actor_user_id="mgr",
            password_enabled=True,
            allowed_email_domains=["corp.example"],
            signup_enabled=True,
            signup_email_domains=["other.example"],
        )
    assert exc.value.code == "signup_domain_not_allowed"
    saved = await svc.update_policy(
        "dom-a",
        actor_user_id="mgr",
        password_enabled=True,
        allowed_email_domains=["corp.example"],
        signup_enabled=True,
        signup_email_domains=["corp.example"],
    )
    assert saved["revision"] == 1 and saved["smtp_configured"] is True and saved["configured"] is True
    with pytest.raises(svc.DomainAuthConflict) as exc:
        await svc.update_policy(
            "dom-a",
            actor_user_id="mgr",
            password_enabled=True,
            allowed_email_domains=[],
            signup_enabled=False,
            signup_email_domains=[],
            expected_revision=0,
        )
    assert exc.value.code == "revision_conflict"


async def test_db_unavailable_fails_closed(monkeypatch):
    monkeypatch.setattr(database, "is_db_available", lambda: False)
    with pytest.raises(svc.DomainAuthUnavailable):
        await svc.get_policy("dom-a")
    with pytest.raises(svc.DomainAuthUnavailable):
        await svc.require_password("dom-a", "a@corp.example")


# ── provider configuration ──────────────────────────────────────────────────


async def test_provider_secret_is_write_only_and_domain_bound(env):
    created = await svc.create_provider("dom-a", actor_user_id="mgr", fields=oidc_fields())
    assert created["client_secret_configured"] is True
    assert SECRET not in json.dumps(created) and "client_secret" not in created
    async with env.db() as session:
        row = (await session.execute(select(DomainIdentityProvider))).scalar_one()
    assert SECRET not in row.client_secret_ciphertext
    assert svc.decrypt_client_secret(row.client_secret_ciphertext, domain_id="dom-a", provider_id=row.id) == SECRET
    with pytest.raises(svc.DomainAuthUnavailable):
        svc.decrypt_client_secret(row.client_secret_ciphertext, domain_id="dom-b", provider_id=row.id)
    listed = await svc.list_providers("dom-a")
    assert SECRET not in json.dumps(listed)
    assert await svc.list_providers("dom-b") == []


@pytest.mark.parametrize(
    "issuer",
    [
        "http://idp.example.com",
        "https://169.254.169.254",
        "https://10.0.0.5",
        "https://localhost",
        "https://metadata.google.internal",
        "https://user:pw@idp.example.com",
        "https://idp.example.com:8443",
    ],
)
async def test_provider_urls_reject_unsafe_destinations(env, issuer):
    with pytest.raises(svc.DomainAuthInvalid) as exc:
        await svc.create_provider("dom-a", actor_user_id="mgr", fields=oidc_fields(issuer_url=issuer))
    assert exc.value.code == "unsafe_url"


async def test_provider_dns_to_private_address_is_rejected(env, monkeypatch):
    def private(host, port):
        raise ssrf.SsrfBlocked("hostname resolves to a private or internal IP address")

    monkeypatch.setattr(ssrf, "_resolve_public_addresses_sync", private)
    with pytest.raises(svc.DomainAuthInvalid) as exc:
        await svc.create_provider("dom-a", actor_user_id="mgr", fields=oidc_fields())
    assert exc.value.code == "unsafe_url"


async def test_provider_origin_is_independent_of_native_idp_domain_but_requires_protocol(env):
    created = await svc.create_provider("dom-a", actor_user_id="mgr", fields=oidc_fields(keystone_idp_id="idp-b"))
    assert created["domain_id"] == "dom-a" and created["keystone_idp_id"] == "idp-b"
    with pytest.raises(svc.DomainAuthInvalid) as exc:
        await svc.create_provider("dom-a", actor_user_id="mgr", fields=oidc_fields(keystone_protocol_id="saml2"))
    assert exc.value.code == "idp_not_found"


async def test_provider_revision_and_foreign_domain_boundaries(env):
    created = await svc.create_provider("dom-a", actor_user_id="mgr", fields=oidc_fields())
    renamed = await svc.update_provider("dom-a", created["id"], actor_user_id="mgr", fields={"name": "Renamed"})
    assert renamed["revision"] == created["revision"]
    rotated = await svc.update_provider(
        "dom-a", created["id"], actor_user_id="mgr", fields={"client_secret": "rotated-secret"}
    )
    assert rotated["revision"] == created["revision"] + 1
    with pytest.raises(svc.DomainAuthNotFound):
        await svc.update_provider("dom-b", created["id"], actor_user_id="other", fields={"enabled": False})
    with pytest.raises(svc.DomainAuthNotFound):
        await svc.delete_provider("dom-b", created["id"])
    with pytest.raises(svc.DomainAuthInvalid) as exc:
        await svc.update_provider("dom-a", created["id"], actor_user_id="mgr", fields={"kind": "github"})
    assert exc.value.code == "kind_immutable"


async def test_last_provider_cannot_be_disabled_or_deleted_when_password_is_off(env):
    created = await svc.create_provider("dom-a", actor_user_id="mgr", fields=oidc_fields())
    # Seed the post-session-issuance marker for this focused SQL guard test.
    await svc.mark_provider_verified("dom-a", created["id"], created["revision"])
    await svc.update_policy(
        "dom-a",
        actor_user_id="mgr",
        password_enabled=False,
        allowed_email_domains=[],
        signup_enabled=False,
        signup_email_domains=[],
    )
    for action in (
        svc.update_provider("dom-a", created["id"], actor_user_id="mgr", fields={"enabled": False}),
        svc.delete_provider("dom-a", created["id"]),
    ):
        with pytest.raises(svc.DomainAuthConflict) as exc:
            await action
        assert exc.value.code == "last_login_method"
    methods = await svc.public_methods("dom-a")
    assert methods["password_enabled"] is False and [p["id"] for p in methods["providers"]] == [created["id"]]


# ── authorize / callback ────────────────────────────────────────────────────


async def test_oidc_login_verifies_signed_identity_and_native_federation(env, wire):
    provider = await svc.create_provider("dom-a", actor_user_id="mgr", fields=oidc_fields())
    state, binding = await start(wire.idp, provider["id"])
    login = await svc.complete_authorization("good-code", state, binding)
    assert (login.user_id, login.domain_id, login.domain_name, login.login_email) == (
        "fed-user",
        "dom-a",
        "Alpha",
        "Dev@corp.example",
    )
    assert login.provider_id == provider["id"] and login.provider_revision == provider["revision"]
    assert login.unscoped_token == "unscoped-fed"
    call = wire.federation.calls[0]
    assert str(call.url).endswith("/OS-FEDERATION/identity_providers/idp-a/protocols/openid/auth")
    assert call.headers["authorization"].startswith("Bearer ey")
    # One-use state: replay is rejected.
    with pytest.raises(svc.DomainAuthUnauthenticated):
        await svc.complete_authorization("good-code", state, binding)
    # Refresh authority follows the same provider binding.
    await svc.require_provider("dom-a", provider["id"], provider["revision"], login.login_email)


async def test_state_is_browser_bound(env, wire):
    provider = await svc.create_provider("dom-a", actor_user_id="mgr", fields=oidc_fields())
    state, _binding = await start(wire.idp, provider["id"])
    with pytest.raises(svc.DomainAuthUnauthenticated) as exc:
        await svc.complete_authorization("good-code", state, "attacker-browser")
    assert exc.value.code == "invalid_state"
    assert wire.federation.calls == []


async def test_provider_change_invalidates_pending_state_and_sessions(env, wire):
    provider = await svc.create_provider("dom-a", actor_user_id="mgr", fields=oidc_fields())
    state, binding = await start(wire.idp, provider["id"])
    await svc.update_provider("dom-a", provider["id"], actor_user_id="mgr", fields={"client_id": "new-client"})
    with pytest.raises(svc.DomainAuthConflict) as exc:
        await svc.complete_authorization("good-code", state, binding)
    assert exc.value.code == "provider_changed"
    with pytest.raises(svc.DomainAuthDenied):
        await svc.require_provider("dom-a", provider["id"], provider["revision"], "dev@corp.example")
    assert wire.federation.calls == []


async def test_disabled_provider_cannot_be_used_directly(env, wire):
    provider = await svc.create_provider("dom-a", actor_user_id="mgr", fields=oidc_fields(enabled=False))
    with pytest.raises(svc.DomainAuthNotFound):
        await svc.start_authorization("dom-a", provider["id"])
    # Provider of domain A cannot be started through domain B.
    enabled = await svc.create_provider("dom-a", actor_user_id="mgr", fields=oidc_fields(name="Enabled"))
    with pytest.raises(svc.DomainAuthNotFound):
        await svc.start_authorization("dom-b", enabled["id"])
    state, binding = await start(wire.idp, enabled["id"])
    await svc.update_provider("dom-a", enabled["id"], actor_user_id="mgr", fields={"enabled": False})
    with pytest.raises(svc.DomainAuthDenied) as exc:
        await svc.complete_authorization("good-code", state, binding)
    assert exc.value.code == "provider_disabled"
    with pytest.raises(svc.DomainAuthDenied) as exc:
        await svc.start_authorization("dom-off", enabled["id"])
    assert exc.value.code == "domain_disabled"


async def test_foreign_domain_federation_result_is_denied_and_revoked(env, wire):
    provider = await svc.create_provider("dom-a", actor_user_id="mgr", fields=oidc_fields())
    wire.federation.domain_id = "dom-b"
    state, binding = await start(wire.idp, provider["id"])
    with pytest.raises(svc.DomainAuthDenied) as exc:
        await svc.complete_authorization("good-code", state, binding)
    assert exc.value.code == "canonical_subject_mismatch"
    assert env.keystone.revoked == ["unscoped-fed"]


@pytest.mark.parametrize(
    ("claims", "code"),
    [
        ({"nonce": "replayed-nonce"}, "invalid_id_token"),
        ({"aud": "other-client"}, "invalid_id_token"),
        ({"iss": "https://evil.example.com"}, "invalid_id_token"),
        ({"exp": int(time.time()) - 3600, "iat": int(time.time()) - 7200}, "invalid_id_token"),
        ({"email_verified": False}, "email_not_verified"),
        ({"email_verified": "true"}, "email_not_verified"),
        ({"email": None}, "email_not_verified"),
    ],
)
async def test_oidc_id_token_claims_are_enforced(env, wire, claims, code):
    provider = await svc.create_provider("dom-a", actor_user_id="mgr", fields=oidc_fields())
    state, binding = await start(wire.idp, provider["id"])
    wire.idp.claims = claims
    with pytest.raises(svc.DomainAuthError) as exc:
        await svc.complete_authorization("good-code", state, binding)
    assert exc.value.code == code
    assert wire.federation.calls == []


async def test_oidc_signature_from_unknown_key_is_rejected(env, wire):
    provider = await svc.create_provider("dom-a", actor_user_id="mgr", fields=oidc_fields())
    state, binding = await start(wire.idp, provider["id"])
    wire.idp.signing_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(svc.DomainAuthProviderError) as exc:
        await svc.complete_authorization("good-code", state, binding)
    assert exc.value.code == "invalid_id_token"
    assert wire.federation.calls == []


async def test_login_email_allowlist_is_enforced_before_federation(env, wire):
    provider = await svc.create_provider("dom-a", actor_user_id="mgr", fields=oidc_fields())
    await svc.update_policy(
        "dom-a",
        actor_user_id="mgr",
        password_enabled=True,
        allowed_email_domains=["partner.example"],
        signup_enabled=False,
        signup_email_domains=[],
    )
    state, binding = await start(wire.idp, provider["id"])
    with pytest.raises(svc.DomainAuthDenied) as exc:
        await svc.complete_authorization("good-code", state, binding)
    assert exc.value.code == "email_domain_not_allowed"
    assert wire.federation.calls == []
    with pytest.raises(svc.DomainAuthDenied):
        await svc.require_provider("dom-a", provider["id"], provider["revision"], "dev@corp.example")


async def test_github_uses_verified_primary_email(env, wire):
    provider = await svc.create_provider(
        "dom-a",
        actor_user_id="mgr",
        fields={
            "name": "GitHub",
            "kind": "github",
            "client_id": CLIENT_ID,
            "client_secret": SECRET,
            "keystone_idp_id": "idp-a",
            "keystone_protocol_id": "github",
        },
    )
    assert provider["api_url"] == "https://api.github.com" and provider["scopes"] == ["read:user", "user:email"]
    state, binding = await start(wire.idp, provider["id"])
    login = await svc.complete_authorization("good-code", state, binding)
    assert login.login_email == "dev@corp.example" and login.provider_kind == "github"
    assert wire.federation.calls[0].headers["authorization"] == "Bearer gh-access"

    wire.idp.github_emails = [
        {"email": "dev@corp.example", "primary": True, "verified": False},
        {"email": "other@corp.example", "primary": False, "verified": True},
    ]
    state, binding = await start(wire.idp, provider["id"])
    with pytest.raises(svc.DomainAuthDenied) as exc:
        await svc.complete_authorization("good-code", state, binding)
    assert exc.value.code == "email_not_verified"


async def test_local_mapping_without_federation_block_keeps_native_identity(env, wire):
    provider = await svc.create_provider("dom-a", actor_user_id="mgr", fields=oidc_fields())
    wire.federation.federation_block = False
    state, binding = await start(wire.idp, provider["id"])
    login = await svc.complete_authorization("good-code", state, binding)
    assert login.user_id == "fed-user" and login.domain_id == "dom-a"

    wire.federation.federation_block, wire.federation.idp_id = True, "idp-b"
    state, binding = await start(wire.idp, provider["id"])
    with pytest.raises(svc.DomainAuthDenied) as exc:
        await svc.complete_authorization("good-code", state, binding)
    assert exc.value.code == "canonical_subject_mismatch"
    assert env.keystone.revoked == ["unscoped-fed"]


async def test_jwks_key_type_mismatch_is_invalid_token_not_crash(env, wire):
    from cryptography.hazmat.primitives.asymmetric import ec

    provider = await svc.create_provider("dom-a", actor_user_id="mgr", fields=oidc_fields())
    ec_jwk = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(ec.generate_private_key(ec.SECP256R1()).public_key()))
    ec_jwk.update(kid="k1", use="sig")
    wire.idp.jwks = {"keys": [ec_jwk]}
    state, binding = await start(wire.idp, provider["id"])
    with pytest.raises(svc.DomainAuthProviderError) as exc:
        await svc.complete_authorization("good-code", state, binding)
    assert exc.value.code == "invalid_id_token"
    assert wire.federation.calls == []


async def test_provider_redirect_is_not_followed(env, wire):
    provider = await svc.create_provider("dom-a", actor_user_id="mgr", fields=oidc_fields())
    state, binding = await start(wire.idp, provider["id"])
    wire.idp.token_redirect = True
    wire.idp.requests.clear()
    with pytest.raises(svc.DomainAuthProviderError):
        await svc.complete_authorization("good-code", state, binding)
    urls = [str(request.url) for request in wire.idp.requests]
    assert urls.count(f"{ISSUER}/token") == 1
    assert not any("169.254.169.254" in url for url in urls)
    assert wire.federation.calls == []


async def test_secrets_codes_and_tokens_are_not_logged(env, wire, caplog):
    import logging

    caplog.set_level(logging.DEBUG)
    provider = await svc.create_provider("dom-a", actor_user_id="mgr", fields=oidc_fields())
    await svc.update_provider("dom-a", provider["id"], actor_user_id="mgr", fields={"client_secret": SECRET + "-2"})
    wire.idp.client_secret = SECRET + "-2"
    state, binding = await start(wire.idp, provider["id"])
    wire.idp.claims = {"aud": "other-client"}
    with pytest.raises(svc.DomainAuthProviderError) as exc:
        await svc.complete_authorization("good-code", state, binding)
    assert exc.value.code == "invalid_id_token"
    wire.idp.claims = {}
    wire.federation.domain_id = "dom-b"
    state2, binding2 = await start(wire.idp, provider["id"])
    with pytest.raises(svc.DomainAuthDenied):
        await svc.complete_authorization("good-code", state2, binding2)
    for value in (SECRET, "good-code", state, binding, state2, binding2, "unscoped-fed", "eyJ"):
        assert value not in caplog.text


async def test_direct_authorize_on_unusable_provider_writes_no_state(env, wire):
    from app.services import cache

    disabled = await svc.create_provider("dom-a", actor_user_id="mgr", fields=oidc_fields(enabled=False))
    for domain_id in ("dom-a", "dom-b"):
        with pytest.raises(svc.DomainAuthNotFound):
            await svc.start_authorization(domain_id, disabled["id"])
    redis = await cache._get_redis()
    assert [key async for key in redis.scan_iter("afterglow:domain_auth:state:*")] == []


async def test_password_disabled_policy_denies_password_authority(env):
    created = await svc.create_provider("dom-a", actor_user_id="mgr", fields=oidc_fields())
    await svc.mark_provider_verified("dom-a", created["id"], created["revision"])
    await svc.update_policy(
        "dom-a",
        actor_user_id="mgr",
        password_enabled=False,
        allowed_email_domains=[],
        signup_enabled=False,
        signup_email_domains=[],
    )
    with pytest.raises(svc.DomainAuthDenied) as exc:
        await svc.require_password("dom-a", "dev@corp.example")
    assert exc.value.code == "password_disabled"


async def test_state_storage_failure_fails_closed(env, wire, monkeypatch):
    provider = await svc.create_provider("dom-a", actor_user_id="mgr", fields=oidc_fields())

    async def broken():
        raise ConnectionError("redis down")

    monkeypatch.setattr(svc, "_redis", broken)
    with pytest.raises(svc.DomainAuthUnavailable):
        await svc.start_authorization("dom-a", provider["id"])
    with pytest.raises(svc.DomainAuthUnavailable):
        await svc.complete_authorization("good-code", "s" * 43, "binding")


async def test_unconfigured_callback_url_is_reported(env, wire):
    provider = await svc.create_provider("dom-a", actor_user_id="mgr", fields=oidc_fields())
    env.settings.frontend_base_url = ""
    with pytest.raises(svc.DomainAuthUnavailable) as exc:
        await svc.start_authorization("dom-a", provider["id"])
    assert exc.value.code == "redirect_not_configured"


# ── HTTP routes ─────────────────────────────────────────────────────────────


@pytest.fixture
def api(env, wire, monkeypatch):
    from app.api.deps import require_domain_manager
    from app.api.identity import auth
    from app.api.identity import domain_auth as routes
    from app.rate_limit import limiter
    from app.services import activity, domain_projects, domain_scope, keystone

    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(routes.public_router, prefix="/api/v1/auth")
    app.include_router(routes.iam_router, prefix="/api/v1/iam")
    app.dependency_overrides[require_domain_manager] = lambda: {"user_id": "mgr", "domain_id": "dom-a"}
    native_validations = []
    native_preparations = []
    default = {"id": "default-a", "name": "Default", "domain_id": "dom-a", "enabled": True}
    reader = {"user": {"id": "fed-user"}, "role": {"id": "reader-role"}, "scope": {"project": {"id": default["id"]}}}

    def project_get(project_id):
        if project_id != default["id"]:
            raise NotFound()
        return default.copy()

    def project_list(domain=None, user=None):
        return [default.copy()] if domain in (None, "dom-a") and user in (None, "fed-user") else []

    def assignments(**query):
        if query.get("user", "fed-user") != "fed-user" or query.get("project", default["id"]) != default["id"]:
            return []
        return [] if any(key in query for key in ("domain", "system", "group")) else [reader]

    # Read-only native state is local to API consumers, not global role seeding.
    # Manager exists only to prove this reader has no Default manager authority.
    env.keystone.projects = SimpleNamespace(get=project_get, list=project_list)
    env.keystone.roles = SimpleNamespace(
        list=lambda: [{"id": name + "-role", "name": name, "domain_id": None} for name in ("manager", "reader")]
    )
    env.keystone.role_assignments = SimpleNamespace(list=assignments)

    async def existing_login_access(user_id, domain_id, *, operation=None):
        assert (user_id, domain_id) == ("fed-user", "dom-a")
        native_preparations.append((user_id, domain_id))
        domain_projects.assert_project_membership(user_id, default["id"], operation=operation)

    async def native_dashboard_prewarm(token, project_id):
        # Dashboard reads/default-network provisioning are a separate native
        # boundary; never open a cloud connection from these session consumers.
        assert (token, project_id) == ("scoped-fed", default["id"])

    def validate_native(token, project_id="", *, operation=None):
        native_validations.append((token, project_id))
        assert token == "unscoped-fed" and project_id in ("", default["id"])
        return {
            "token": "scoped-fed" if project_id else token,
            "user_id": "fed-user",
            "username": "dev",
            "project_id": project_id,
            "project_name": default["name"] if project_id else "",
            "domain_id": "dom-a",
            "domain_name": "Alpha",
            "identity_domain_id": "dom-a",
            "identity_domain_name": "Alpha",
            "is_domain_manager": False,
            "is_system_admin": False,
            "roles": ["reader"] if project_id else [],
            "email": "",
            "default_project_id": "",
        }

    # Isolate only native provisioning/transport, like the static auth_directory
    # fixture. OIDC/federation, scope preparation/fences, provider policy, JWTs
    # and Redis session persistence/revocation all execute their real paths.
    monkeypatch.setattr(domain_projects, "ensure_login_access", existing_login_access)
    monkeypatch.setattr(auth, "_prewarm_dashboard", native_dashboard_prewarm)
    monkeypatch.setattr(keystone, "validate_token", validate_native)

    def native_projects(token, domain_id, *, operation=None):
        assert (token, domain_id) == ("unscoped-fed", "dom-a")
        return project_list(domain=domain_id, user="fed-user")

    monkeypatch.setattr(keystone, "list_projects", native_projects)
    monkeypatch.setattr(
        keystone,
        "get_identity_user",
        lambda uid, *, operation=None: {
            "id": uid,
            "domain_id": "dom-a",
            "email": "Dev@corp.example",
        },
    )
    monkeypatch.setattr(domain_scope, "has_scope_authority", lambda uid, **kwargs: False)
    monkeypatch.setattr(activity, "is_db_available", lambda: False)
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="https://api.example.com",
        headers={"Origin": "https://cloud.example.com", "Sec-Fetch-Site": "same-site"},
    )
    return SimpleNamespace(
        app=app, client=client, native_validations=native_validations, native_preparations=native_preparations
    )


@pytest.mark.parametrize("filtered", [False, True], ids=["unrestricted", "effective-allowlist"])
async def test_api_login_options_exact_origins_and_safe_provider_summaries(api, env, monkeypatch, filtered):
    # Display labels deliberately collide; native IDs alone select an origin.
    for domain_id in ("dom-a", "dom-b"):
        env.keystone.domain_rows[domain_id].afterglow_display_name = "Shared"
    env.keystone.domain_rows["dom-empty"] = SimpleNamespace(id="dom-empty", name="Empty", enabled=True)
    env.keystone.domain_rows["dom-truthy"] = SimpleNamespace(id="dom-truthy", name="Truthy", enabled=1)
    a = await svc.create_provider("dom-a", actor_user_id="mgr", fields=oidc_fields(name="Shared provider"))
    b = await svc.create_provider("dom-b", actor_user_id="mgr", fields=oidc_fields(name="Shared provider"))
    hidden = await svc.create_provider("dom-a", actor_user_id="mgr", fields=oidc_fields(name="Filtered SQL"))
    await svc.create_provider("dom-a", actor_user_id="mgr", fields=oidc_fields(name="Disabled SQL", enabled=False))
    incomplete = await svc.create_provider("dom-a", actor_user_id="mgr", fields=oidc_fields(name="No secret"))
    for domain_id in ("dom-off", "dom-truthy", "no-native-domain"):
        await svc.create_provider(domain_id, actor_user_id="mgr", fields=oidc_fields())
    async with env.db() as session:
        row = await session.get(DomainIdentityProvider, incomplete["id"])
        row.client_secret_ciphertext = ""
        await session.commit()
    assert a["verified"] is False and b["verified"] is False
    configure_file_auth(
        env.settings,
        providers={
            "corp": oidc_fields(name="Shared provider"),
            "github": oidc_fields(kind="github", issuer_url=None, name="GitHub"),
            "off": oidc_fields(name="Disabled config", enabled=False),
        },
        default=["corp", b["id"], "github", "off"] if filtered else None,
        # A display-name key must never shadow the exact domain's policy.
        domains={
            "Shared": [],
            "dom-a": [a["id"], "corp", a["id"], b["id"], "off"] if filtered else None,
            "dom-empty": [],
        },
    )
    env.wire.idp.requests.clear()
    env.wire.federation.calls.clear()

    def forbidden(*args, **kwargs):
        pytest.fail("Public login options must not perform account lookup, discovery or secret decryption")

    monkeypatch.setattr(env.keystone.users, "list", forbidden)
    monkeypatch.setattr(env.keystone.users, "get", forbidden)
    monkeypatch.setattr(svc, "_provider_client", forbidden)
    monkeypatch.setattr(svc, "_load_provider", forbidden)
    monkeypatch.setattr(svc, "decrypt_client_secret", forbidden)
    async with api.client as client:
        client.headers.pop("Origin")
        client.headers.pop("Sec-Fetch-Site")
        response = await client.get("/api/v1/auth/login-options")
        assert response.status_code == 200
        config = [
            {"id": "cfg:corp", "name": "Shared provider", "kind": "oidc"},
            {"id": "cfg:github", "name": "GitHub", "kind": "github"},
        ]
        sql_a = {"id": a["id"], "name": a["name"], "kind": a["kind"]}
        sql_b = {"id": b["id"], "name": b["name"], "kind": b["kind"]}
        expected_a = (
            [sql_a, config[0]]
            if filtered
            else config
            + [
                {"id": hidden["id"], "name": hidden["name"], "kind": hidden["kind"]},
                sql_a,
            ]
        )
        expected_b = [config[0], sql_b, config[1]] if filtered else config + [sql_b]
        assert response.json() == {
            "providers": [
                {**provider, "domain_id": domain_id, "domain_name": "Shared"}
                for domain_id, providers in (("dom-a", expected_a), ("dom-b", expected_b))
                for provider in providers
            ]
        }
        assert all(
            set(provider) == {"id", "name", "kind", "domain_id", "domain_name"}
            for provider in response.json()["providers"]
        )
        assert response.headers["cache-control"] == "no-store, private"
        assert response.headers["pragma"] == "no-cache"
        assert response.headers["referrer-policy"] == "no-referrer"
        for private in (
            SECRET,
            CLIENT_ID,
            ISSUER,
            "client_secret",
            "ciphertext",
            "issuer_url",
            "authorization_url",
            "token_url",
            "keystone_idp_id",
            "scopes",
            "revision",
        ):
            assert private not in response.text
        assert "password_enabled" not in response.text
        assert "signup_enabled" not in response.text
    assert env.wire.idp.requests == [] and env.wire.federation.calls == []
    assert api.native_validations == [] and api.native_preparations == []
    async with env.db() as session:
        assert (await session.get(DomainIdentityProvider, a["id"])).verified_revision is None


async def test_api_login_options_personal_homes_do_not_multiply_common_registrations(api, env, monkeypatch):
    env.settings.os_user_domain_name = "Alpha"  # Canonicalize the server's original domain name.
    for index in range(40):
        domain_id = f"personal-home-{index}"
        env.keystone.domain_rows[domain_id] = SimpleNamespace(id=domain_id, name=domain_id, enabled=True)
    # SQL ownership is an explicit origin even without an auth.domain override.
    sql = await svc.create_provider("dom-b", actor_user_id="mgr", fields=oidc_fields(name="Independent SQL"))
    configure_file_auth(
        env.settings,
        providers={"corp": oidc_fields(name="Corp SSO"), "team": oidc_fields(name="Independent OIDC")},
        default=["corp", "team", sql["id"]],
        domains={"personal-home-0": ["team"]},
    )
    original_get = env.keystone.domains.get
    hydrated = []

    def exact(domain_id):
        hydrated.append(domain_id)
        if domain_id.startswith("personal-home-") and domain_id != "personal-home-0":
            pytest.fail("Inherited common providers must not hydrate or expose every personal home")
        return original_get(domain_id)

    monkeypatch.setattr(env.keystone.domains, "get", exact)
    env.wire.idp.requests.clear()
    async with api.client as client:
        response = await client.get("/api/v1/auth/login-options")
    assert response.status_code == 200, response.text
    providers = response.json()["providers"]
    assert [(row["id"], row["domain_id"]) for row in providers] == [
        ("cfg:corp", "dom-a"),
        ("cfg:team", "dom-a"),
        ("cfg:corp", "dom-b"),
        ("cfg:team", "dom-b"),
        (sql["id"], "dom-b"),
        ("cfg:team", "personal-home-0"),
    ]
    assert not ({f"personal-home-{index}" for index in range(1, 40)} & set(hydrated))
    assert env.wire.idp.requests == []


async def test_api_login_options_requires_complete_native_transport_inventory(api, env, monkeypatch):
    calls = []

    def native_get(path):
        calls.append(path)
        return None, {
            "domains": [{"id": "dom-b", "enabled": True}, {"id": "dom-a", "enabled": True}],
            "links": {"next": None},
        }

    monkeypatch.setattr(env.keystone.domains, "client", SimpleNamespace(get=native_get), raising=False)
    configure_file_auth(env.settings, default=["corp"], domains={"dom-b": ["corp"]})
    async with api.client as client:
        response = await client.get("/api/v1/auth/login-options")
    assert response.status_code == 200
    assert response.json() == {
        "providers": [
            {"id": "cfg:corp", "name": "Corp SSO", "kind": "oidc", "domain_id": domain_id, "domain_name": name}
            for domain_id, name in (("dom-a", "Alpha"), ("dom-b", "Beta"))
        ]
    }
    assert calls == ["/domains"]
    assert env.wire.idp.requests == []


async def test_api_login_options_rechecks_exact_native_enabled_state(api, env, monkeypatch):
    configure_file_auth(env.settings, default=["corp"], domains={"dom-b": ["corp"]})
    # The collection still says enabled, but its current exact resource is not.
    original_get = env.keystone.domains.get

    def current(domain_id):
        if domain_id == "dom-a":
            return SimpleNamespace(id=domain_id, name="Alpha", enabled=False)
        return original_get(domain_id)

    monkeypatch.setattr(env.keystone.domains, "get", current)
    async with api.client as client:
        response = await client.get("/api/v1/auth/login-options")
    assert response.status_code == 200
    assert response.json() == {
        "providers": [
            {"id": "cfg:corp", "name": "Corp SSO", "kind": "oidc", "domain_id": "dom-b", "domain_name": "Beta"}
        ]
    }


@pytest.mark.parametrize(
    "failure",
    [
        "native-outage",
        "native-iteration",
        "native-next",
        "native-truncated",
        "native-limited",
        "native-duplicate",
        "native-missing-id",
        "native-wrong-id",
        "native-missing-resource",
        "native-invalid-label",
        "native-raw-next",
        "native-raw-missing-links",
        "native-raw-invalid",
        "native-raw-truncated",
        "db-unavailable",
        "db-query",
    ],
)
async def test_api_login_options_fail_closed_no_store_safe_error(api, env, monkeypatch, failure):
    from sqlalchemy.exc import SQLAlchemyError

    configure_file_auth(env.settings, default=["corp"])
    error_secret = "storage-or-native-secret-sentinel"

    def broken(*args, **kwargs):
        raise RuntimeError(error_secret)

    if failure == "native-outage":
        monkeypatch.setattr(env.keystone.domains, "list", broken)
    elif failure == "native-iteration":

        def partial():
            yield env.keystone.domain_rows["dom-a"]
            raise RuntimeError(error_secret)

        monkeypatch.setattr(env.keystone.domains, "list", partial)
    elif failure in {"native-next", "native-truncated", "native-limited"}:

        class Incomplete(list):
            pass

        rows = Incomplete([env.keystone.domain_rows["dom-a"]])
        setattr(rows, failure.removeprefix("native-"), True)
        monkeypatch.setattr(env.keystone.domains, "list", lambda: rows)
    elif failure in {"native-duplicate", "native-missing-id"}:
        row = env.keystone.domain_rows["dom-a"]
        rows = [row, row] if failure == "native-duplicate" else [SimpleNamespace(enabled=True)]
        monkeypatch.setattr(env.keystone.domains, "list", lambda: rows)
    elif failure == "native-wrong-id":
        monkeypatch.setattr(env.keystone.domains, "get", lambda _: env.keystone.domain_rows["dom-b"])
    elif failure == "native-missing-resource":
        monkeypatch.setattr(env.keystone.domains, "get", broken)
    elif failure == "native-invalid-label":
        env.keystone.domain_rows["dom-a"].afterglow_display_name = ""
    elif failure.startswith("native-raw-"):
        body = {"domains": [{"id": "dom-a", "enabled": True}], "links": {"next": None}}
        if failure == "native-raw-next":
            body["links"]["next"] = "https://untrusted.example/domains?page=2"
        elif failure == "native-raw-missing-links":
            body.pop("links")
        elif failure == "native-raw-invalid":
            body["domains"] = None
        else:
            body["truncated"] = True
        monkeypatch.setattr(env.keystone.domains, "client", SimpleNamespace(get=lambda _: (None, body)), raising=False)
    elif failure == "db-unavailable":
        monkeypatch.setattr(database, "is_db_available", lambda: False)
    else:
        from sqlalchemy.ext.asyncio import AsyncSession

        async def broken_execute(*args, **kwargs):
            raise SQLAlchemyError(error_secret)

        monkeypatch.setattr(AsyncSession, "execute", broken_execute)
    async with api.client as client:
        response = await client.get("/api/v1/auth/login-options")
    assert response.status_code == 503
    assert response.json() == {
        "detail": "Domain directory is unavailable or incomplete"
        if failure.startswith("native-")
        else "Login policy storage is unavailable",
        "code": "unavailable",
    }
    assert response.headers["cache-control"] == "no-store, private"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert error_secret not in response.text and SECRET not in response.text
    assert "providers" not in response.json()
    assert env.wire.idp.requests == [] and env.wire.federation.calls == []


async def test_api_login_options_empty_inventory_still_requires_storage(api, env, monkeypatch):
    env.keystone.domain_rows.clear()
    configure_file_auth(env.settings, default=["corp"])
    async with api.client as client:
        response = await client.get("/api/v1/auth/login-options")
        assert response.status_code == 200 and response.json() == {"providers": []}
        monkeypatch.setattr(database, "is_db_available", lambda: False)
        unavailable = await client.get("/api/v1/auth/login-options")
        assert unavailable.status_code == 503
        assert unavailable.headers["cache-control"] == "no-store, private"


async def test_api_provider_crud_never_returns_secret_and_is_no_store(api):
    async with api.client as client:
        created = await client.post("/api/v1/iam/providers", json=oidc_fields())
        assert created.status_code == 201
        assert SECRET not in created.text and created.json()["client_secret_configured"] is True
        assert created.headers["cache-control"].startswith("no-store")
        bad = await client.post("/api/v1/iam/providers", json={**oidc_fields(), "client_secret": "", "x": SECRET})
        assert bad.status_code == 422 and SECRET not in bad.text
        assert bad.json()["code"] == "identity_invalid_input"
        listed = await client.get("/api/v1/iam/providers")
        assert SECRET not in listed.text and len(listed.json()["items"]) == 1
        foreign = await client.put(
            "/api/v1/iam/login-policy",
            json={"domain_id": "dom-b", "password_enabled": True, "signup_enabled": False},
        )
        assert foreign.status_code == 422
        off = await client.put(
            "/api/v1/iam/login-policy",
            json={"password_enabled": False, "signup_enabled": False},
        )
        assert off.status_code == 409 and off.json()["code"] == "last_login_method"
        last = await client.delete(f"/api/v1/iam/providers/{created.json()['id']}")
        assert last.status_code == 204


async def test_api_duplicate_domain_labels_require_exact_id(api, keystone_admin):
    for domain_id in ("dom-a", "dom-b"):
        keystone_admin.domain_rows[domain_id].afterglow_display_name = "Shared"
    async with api.client as client:
        ambiguous = await client.get("/api/v1/auth/domains/resolve", params={"name": "Shared"})
        assert ambiguous.status_code == 409
        assert ambiguous.json()["code"] == "domain_ambiguous"
        for domain_id in ("dom-a", "dom-b"):
            resolved = await client.get("/api/v1/auth/domains/resolve", params={"name": domain_id})
            assert resolved.status_code == 200
            assert resolved.json()["domain_id"] == domain_id
            assert resolved.json()["domain_name"] == "Shared"


async def test_api_resolve_and_browser_bound_callback(api, wire):
    provider = await svc.create_provider("dom-a", actor_user_id="mgr", fields=oidc_fields())
    await svc.create_provider("dom-a", actor_user_id="mgr", fields=oidc_fields(name="Hidden", enabled=False))
    async with api.client as client:
        resolved = await client.get("/api/v1/auth/domains/resolve", params={"name": "Alpha"})
        assert resolved.json() == {
            "domain_id": "dom-a",
            "domain_name": "Alpha",
            "password_enabled": True,
            "providers": [{"id": provider["id"], "name": "Corp SSO", "kind": "oidc"}],
            "signup_enabled": False,
        }
        assert (await client.get("/api/v1/auth/domains/resolve", params={"name": "Off"})).status_code == 403
        assert (await client.get("/api/v1/auth/domains/resolve", params={"name": "Nope"})).status_code == 404

        started = await client.post(f"/api/v1/auth/domains/dom-a/providers/{provider['id']}/authorize")
        assert started.status_code == 200
        cookie = started.headers["set-cookie"]
        assert "HttpOnly" in cookie and "Path=/api/v1/auth/providers" in cookie
        state = wire.idp.remember(started.json()["authorize_url"])
        binding = client.cookies.get(svc.STATE_COOKIE)
        client.cookies.clear()
        missing = await client.post("/api/v1/auth/providers/callback", json={"code": "good-code", "state": state})
        assert missing.status_code == 401 and missing.json()["code"] == "invalid_state"
        assert api.native_validations == []
        assert api.native_preparations == []

        started = await client.post(f"/api/v1/auth/domains/dom-a/providers/{provider['id']}/authorize")
        state = wire.idp.remember(started.json()["authorize_url"])
        done = await client.post("/api/v1/auth/providers/callback", json={"code": "good-code", "state": state})
        assert done.status_code == 200 and done.json()["domain_id"] == "dom-a"
        assert done.json()["project_id"] == done.json()["default_project_id"] == "default-a"
        assert done.json()["project_name"] == "Default" and done.json()["roles"] == ["reader"]
        assert done.json()["is_domain_manager"] is False and done.json()["can_write"] is False
        assert api.native_preparations == [("fed-user", "dom-a")]
        from app.services import jwt_service, session_store

        claims = jwt_service.verify_refresh(done.json()["refresh_token"])
        session = await session_store.get_session(claims["jti"])
        assert session["provider_id"] == provider["id"] and session["login_email"] == "Dev@corp.example"
        assert session["project_id"] == "default-a"
        assert session["domain_id"] == session["identity_domain_id"] == "dom-a"
        assert session["provider_revision"] == provider["revision"] and session["auth_method"] == "federated"
        assert binding and binding not in done.text
        policy = await client.put("/api/v1/iam/login-policy", json={"password_enabled": False, "signup_enabled": False})
        assert policy.status_code == 200 and policy.json()["usable_provider_count"] == 1
        metadata = (await client.get("/api/v1/iam/providers")).json()["items"]
        verified = next(item for item in metadata if item["id"] == provider["id"])
        assert verified["verified"] is True and verified["verified_revision"] == provider["revision"]
        blocked = await client.patch(f"/api/v1/iam/providers/{provider['id']}", json={"client_id": "bad-client"})
        assert blocked.status_code == 409 and blocked.json()["code"] == "last_login_method"


async def test_api_unavailable_state_storage_keeps_truthful_code(api, monkeypatch):
    provider = await svc.create_provider("dom-a", actor_user_id="mgr", fields=oidc_fields())

    async def broken():
        raise ConnectionError("redis down")

    monkeypatch.setattr(svc, "_redis", broken)
    async with api.client as client:
        response = await client.post(f"/api/v1/auth/domains/dom-a/providers/{provider['id']}/authorize")
    assert response.status_code == 503 and response.json()["code"] == "unavailable"
    assert svc.STATE_COOKIE not in response.headers.get("set-cookie", "")


async def test_unverified_provider_cannot_replace_password_even_after_idp_exchange(env, wire):
    provider = await svc.create_provider("dom-a", actor_user_id="mgr", fields=oidc_fields())
    assert provider["verified"] is False
    state, binding = await start(wire.idp, provider["id"])
    await svc.complete_authorization("good-code", state, binding)
    # IdP verification and native federation exchange alone are insufficient;
    # the final native token/session issuance boundary must also succeed.
    assert (await svc.list_providers("dom-a"))[0]["verified"] is False
    with pytest.raises(svc.DomainAuthConflict) as exc:
        await svc.update_policy(
            "dom-a",
            actor_user_id="mgr",
            password_enabled=False,
            allowed_email_domains=[],
            signup_enabled=False,
            signup_email_domains=[],
        )
    assert exc.value.code == "last_login_method"


async def test_failed_native_session_issuance_never_marks_verified(api, wire, monkeypatch):
    from app.services import keystone

    provider = await svc.create_provider("dom-a", actor_user_id="mgr", fields=oidc_fields())
    original = keystone.validate_token

    def foreign(token, project_id="", **kwargs):
        return {**original(token, project_id, **kwargs), "domain_id": "dom-b"}

    monkeypatch.setattr(keystone, "validate_token", foreign)
    async with api.client as client:
        started = await client.post(f"/api/v1/auth/domains/dom-a/providers/{provider['id']}/authorize")
        state = wire.idp.remember(started.json()["authorize_url"])
        denied = await client.post("/api/v1/auth/providers/callback", json={"code": "good-code", "state": state})
        assert denied.status_code == 403
        metadata = (await client.get("/api/v1/iam/providers")).json()["items"][0]
        assert metadata["verified"] is False and metadata["verified_revision"] is None
        off = await client.put("/api/v1/iam/login-policy", json={"password_enabled": False, "signup_enabled": False})
        assert off.status_code == 409


async def test_revision_race_after_session_store_revokes_session_and_does_not_verify(api, wire, monkeypatch):
    from app.services import session_store

    provider = await svc.create_provider("dom-a", actor_user_id="mgr", fields=oidc_fields())
    original = session_store.store_session
    saved_jtis = []

    async def change_during_issuance(**kwargs):
        stored = await original(**kwargs)
        assert stored is not False
        session = await session_store.get_session(kwargs["jti"])
        assert session["project_id"] == "default-a"
        assert session["provider_id"] == provider["id"] and session["provider_revision"] == provider["revision"]
        saved_jtis.append(kwargs["jti"])
        await svc.update_provider("dom-a", provider["id"], actor_user_id="mgr", fields={"client_id": "new-client"})
        return stored

    monkeypatch.setattr(session_store, "store_session", change_during_issuance)
    async with api.client as client:
        started = await client.post(f"/api/v1/auth/domains/dom-a/providers/{provider['id']}/authorize")
        state = wire.idp.remember(started.json()["authorize_url"])
        rejected = await client.post("/api/v1/auth/providers/callback", json={"code": "good-code", "state": state})
        assert rejected.status_code == 409 and rejected.json()["code"] == "provider_changed"
    assert saved_jtis and await session_store.get_session(saved_jtis[0]) is None
    assert api.native_preparations == [("fed-user", "dom-a")]
    assert (await svc.list_providers("dom-a"))[0]["verified"] is False


async def test_security_edit_clears_exact_revision_verification(env):
    provider = await svc.create_provider("dom-a", actor_user_id="mgr", fields=oidc_fields())
    await svc.mark_provider_verified("dom-a", provider["id"], provider["revision"])
    renamed = await svc.update_provider("dom-a", provider["id"], actor_user_id="mgr", fields={"name": "Renamed"})
    assert renamed["verified"] is True
    edited = await svc.update_provider("dom-a", provider["id"], actor_user_id="mgr", fields={"client_id": "new-client"})
    assert edited["verified"] is False and edited["verified_revision"] is None and edited["verified_at"] is None
    with pytest.raises(svc.DomainAuthConflict):
        await svc.mark_provider_verified("dom-a", provider["id"], provider["revision"])


@pytest.mark.parametrize("destination", ["oidc", "github"])
async def test_destination_change_requires_explicit_replacement_credentials(env, wire, destination):
    if destination == "oidc":
        fields = oidc_fields()
        changes = {"issuer_url": "https://replacement.example.com"}
    else:
        fields = {**oidc_fields(kind="github", issuer_url=None), "name": "GitHub"}
        changes = {"token_url": "https://replacement.example.com/token"}
    provider = await svc.create_provider("dom-a", actor_user_id="mgr", fields=fields)
    if destination == "oidc":
        wire.idp.issuer = changes["issuer_url"]
    with pytest.raises(svc.DomainAuthInvalid) as exc:
        await svc.update_provider("dom-a", provider["id"], actor_user_id="mgr", fields=changes)
    assert exc.value.code == "client_secret_replacement_required"
    unchanged = (await svc.list_providers("dom-a"))[0]
    assert unchanged["token_url"] == provider["token_url"] and unchanged["revision"] == provider["revision"]
    assert not any(request.method == "POST" for request in wire.idp.requests)
    updated = await svc.update_provider(
        "dom-a",
        provider["id"],
        actor_user_id="mgr",
        fields={**changes, "client_secret": "replacement-secret"},
    )
    assert updated["revision"] == provider["revision"] + 1 and updated["verified"] is False


async def test_discovery_drift_cannot_send_retained_secret_to_new_token_endpoint(env, wire):
    provider = await svc.create_provider("dom-a", actor_user_id="mgr", fields=oidc_fields())
    state, binding = await start(wire.idp, provider["id"])
    wire.idp.token_query = "?tenant=other"
    wire.idp.requests.clear()
    with pytest.raises(svc.DomainAuthConflict) as exc:
        await svc.complete_authorization("good-code", state, binding)
    assert exc.value.code == "provider_changed" and not any(request.method == "POST" for request in wire.idp.requests)


@pytest.mark.parametrize(
    ("advertised", "configured", "expected"),
    [
        (None, None, "client_secret_basic"),
        (["client_secret_post"], None, "client_secret_post"),
        (["client_secret_basic", "client_secret_post"], "client_secret_post", "client_secret_post"),
    ],
)
async def test_oidc_token_authentication_uses_discovery_contract(env, wire, advertised, configured, expected):
    wire.idp.auth_methods = advertised
    provider = await svc.create_provider(
        "dom-a",
        actor_user_id="mgr",
        fields=oidc_fields(token_endpoint_auth_method=configured),
    )
    assert provider["token_endpoint_auth_method"] == expected
    state, binding = await start(wire.idp, provider["id"])
    await svc.complete_authorization("good-code", state, binding)
    exchange = next(request for request in wire.idp.requests if request.method == "POST")
    form = parse_qs(exchange.content.decode())
    assert ("authorization" in exchange.headers) == (expected == "client_secret_basic")
    assert ("client_secret" in form) == (expected == "client_secret_post")


async def test_unsupported_token_auth_is_rejected_before_provider_creation(env, wire):
    wire.idp.auth_methods = ["private_key_jwt"]
    with pytest.raises(svc.DomainAuthInvalid) as exc:
        await svc.create_provider("dom-a", actor_user_id="mgr", fields=oidc_fields())
    assert exc.value.code == "unsupported_token_auth_method"
    assert await svc.list_providers("dom-a") == []


async def test_access_token_federation_binds_userinfo_to_verified_id_token_subject(env, wire):
    wire.idp.userinfo_enabled = True
    provider = await svc.create_provider(
        "dom-a",
        actor_user_id="mgr",
        fields=oidc_fields(federation_token_type="access_token"),
    )
    state, binding = await start(wire.idp, provider["id"])
    await svc.complete_authorization("good-code", state, binding)
    assert wire.federation.calls[0].headers["authorization"] == "Bearer at"
    wire.federation.calls.clear()
    wire.idp.userinfo_subject = "different-subject"
    state, binding = await start(wire.idp, provider["id"])
    with pytest.raises(svc.DomainAuthProviderError) as exc:
        await svc.complete_authorization("good-code", state, binding)
    assert exc.value.code == "invalid_id_token" and wire.federation.calls == []


async def test_access_token_federation_requires_subject_binding_endpoint(env):
    with pytest.raises(svc.DomainAuthInvalid) as exc:
        await svc.create_provider(
            "dom-a", actor_user_id="mgr", fields=oidc_fields(federation_token_type="access_token")
        )
    assert exc.value.code == "userinfo_required"


async def test_safe_endpoint_queries_are_preserved(env, wire):
    wire.idp.authorization_query = "?tenant=alpha%20tenant"
    wire.idp.token_query = "?tenant=alpha"
    provider = await svc.create_provider("dom-a", actor_user_id="mgr", fields=oidc_fields())
    begun = await svc.start_authorization("dom-a", provider["id"])
    query = parse_qs(urlsplit(begun.authorize_url).query)
    assert query["tenant"] == ["alpha tenant"] and len(query["state"]) == 1
    state = wire.idp.remember(begun.authorize_url)
    await svc.complete_authorization("good-code", state, begun.browser_binding)
    exchange = next(request for request in wire.idp.requests if request.method == "POST")
    assert str(exchange.url).endswith("/token?tenant=alpha")


@pytest.mark.parametrize(
    ("field", "query"),
    [
        ("authorization_query", "?state=forged"),
        ("authorization_query", "?%63lient_id=other"),
        ("token_query", "?client_secret=retained"),
        ("token_query", "?code=fixed"),
    ],
)
async def test_endpoint_queries_reject_conflicting_protocol_parameters(env, wire, field, query):
    setattr(wire.idp, field, query)
    with pytest.raises(svc.DomainAuthInvalid) as exc:
        await svc.create_provider("dom-a", actor_user_id="mgr", fields=oidc_fields())
    assert exc.value.code == "unsafe_url"


async def test_cross_site_browser_configuration_is_rejected_clearly(api, env, wire):
    provider = await svc.create_provider("dom-a", actor_user_id="mgr", fields=oidc_fields())
    env.settings.frontend_base_url = "https://console.example.net"
    async with api.client as client:
        client.headers.update({"Origin": "https://console.example.net", "Sec-Fetch-Site": "cross-site"})
        started = await client.post(f"/api/v1/auth/domains/dom-a/providers/{provider['id']}/authorize")
        assert started.status_code == 503 and started.json()["code"] == "cross_site_callback_unsupported"
        assert "set-cookie" not in started.headers
        callback = await client.post("/api/v1/auth/providers/callback", json={"code": "good-code", "state": "s" * 43})
        assert callback.status_code == 503 and callback.json()["code"] == "cross_site_callback_unsupported"


def test_same_host_ports_and_browser_proven_subdomains_are_supported(settings):
    from starlette.requests import Request

    settings.frontend_base_url = "http://localhost:3080"
    settings.public_api_base = "http://localhost:8088"
    svc.require_same_site_browser(Request({"type": "http", "headers": [(b"origin", b"http://localhost:3080")]}))
    settings.frontend_base_url = "https://cloud.example.com"
    settings.public_api_base = "https://api.example.com"
    svc.require_same_site_browser(
        Request(
            {
                "type": "http",
                "headers": [
                    (b"origin", b"https://cloud.example.com"),
                    (b"sec-fetch-site", b"same-site"),
                ],
            }
        )
    )


# ── operator-owned static providers through the existing consumer surface ────


async def test_unrestricted_file_providers_keep_same_kind_instances_and_domain_sql(env):
    sql = await svc.create_provider("dom-a", actor_user_id="mgr", fields=oidc_fields(name="SQL provider"))
    configure_file_auth(
        env.settings,
        providers={
            "gitlab_com": oidc_fields(name="GitLab.com", issuer_url="https://gitlab.com"),
            "dmslab_gitlab": oidc_fields(name="DMSLab GitLab", issuer_url="https://git.dmslab.re.kr"),
            "off": oidc_fields(name="Disabled", enabled=False),
        },
        domains={"dom-b": None, "Alpha": []},
    )
    env.wire.idp.requests.clear()
    resolved = await svc.resolve_login_domain("Alpha")
    assert resolved["domain_id"] == "dom-a"
    expected = [
        {"id": "cfg:gitlab_com", "name": "GitLab.com", "kind": "oidc"},
        {"id": "cfg:dmslab_gitlab", "name": "DMSLab GitLab", "kind": "oidc"},
    ]
    assert resolved["providers"] == expected + [{"id": sql["id"], "name": "SQL provider", "kind": "oidc"}]
    assert (await svc.public_methods("dom-b"))["providers"] == expected
    assert SECRET not in json.dumps(resolved)
    assert "client_id" not in json.dumps(resolved) and "issuer_url" not in json.dumps(resolved)
    assert env.wire.idp.requests == []
    assert [row["id"] for row in await svc.list_providers("dom-a")] == [sql["id"]]


@pytest.mark.parametrize(
    "default,domains,domain_id,expected",
    [
        (None, {"dom-a": []}, "dom-a", []),
        (["common"], {"dom-a": None}, "dom-a", ["common"]),
        (["common"], {"dom-a": ["local", "local", "off"]}, "dom-a", ["local"]),
        ([], {"dom-a": ["local", "common"]}, "dom-a", ["local", "common"]),
        (["common"], {"dom-a": ["local"]}, "dom-b", ["common"]),
    ],
)
async def test_domain_allowlists_replace_inherit_deduplicate_and_block_direct_auth(
    env, default, domains, domain_id, expected
):
    configure_file_auth(
        env.settings,
        providers={
            "common": oidc_fields(name="Common"),
            "local": oidc_fields(name="Local"),
            "off": oidc_fields(name="Disabled", enabled=False),
        },
        default=default,
        domains=domains,
    )
    assert [row["id"] for row in (await svc.public_methods(domain_id))["providers"]] == [
        "cfg:" + key for key in expected
    ]
    env.wire.idp.requests.clear()
    for key in {"common", "local", "off", "missing"} - set(expected):
        with pytest.raises(svc.DomainAuthNotFound):
            await svc.start_authorization(domain_id, "cfg:" + key)
    assert env.wire.idp.requests == []
    redis = await svc._redis()
    assert [key async for key in redis.scan_iter("afterglow:domain_auth:state:*")] == []


async def test_allowlist_orders_file_and_sql_instances_without_foreign_domain_access(env):
    local = await svc.create_provider("dom-a", actor_user_id="mgr", fields=oidc_fields(name="Local SQL"))
    foreign = await svc.create_provider(
        "dom-b", actor_user_id="mgr", fields=oidc_fields(name="Foreign SQL", keystone_idp_id="idp-b")
    )
    configure_file_auth(
        env.settings,
        default=["corp", foreign["id"]],
        domains={"dom-a": [local["id"], "corp", local["id"], foreign["id"]]},
    )
    assert [row["id"] for row in (await svc.public_methods("dom-a"))["providers"]] == [local["id"], "cfg:corp"]
    assert [row["id"] for row in (await svc.public_methods("dom-b"))["providers"]] == ["cfg:corp", foreign["id"]]
    with pytest.raises(svc.DomainAuthNotFound):
        await svc.start_authorization("dom-a", foreign["id"])
    state, binding = await start(env.wire.idp, local["id"])
    login = await svc.complete_authorization("good-code", state, binding)
    assert login.provider_id == local["id"] and login.domain_id == "dom-a"


async def test_sql_allowlist_removal_denies_pending_login_refresh_and_password_fallback(env):
    provider = await svc.create_provider("dom-a", actor_user_id="mgr", fields=oidc_fields())
    # Seed the post-session-issuance marker, as in the existing SQL policy guard test.
    await svc.mark_provider_verified("dom-a", provider["id"], provider["revision"])
    assert (await svc.policy_view("dom-a"))["usable_provider_count"] == 1
    state, binding = await start(env.wire.idp, provider["id"])
    configure_file_auth(env.settings, providers={}, default=[])
    assert (await svc.public_methods("dom-a"))["providers"] == []
    assert (await svc.policy_view("dom-a"))["usable_provider_count"] == 0
    with pytest.raises(svc.DomainAuthNotFound):
        await svc.start_authorization("dom-a", provider["id"])
    with pytest.raises(svc.DomainAuthDenied) as callback:
        await svc.complete_authorization("good-code", state, binding)
    assert callback.value.code == "provider_disabled"
    with pytest.raises(svc.DomainAuthDenied):
        await svc.require_provider("dom-a", provider["id"], provider["revision"], "dev@corp.example")
    with pytest.raises(svc.DomainAuthConflict):
        await svc.mark_provider_verified("dom-a", provider["id"], provider["revision"])
    with pytest.raises(svc.DomainAuthConflict):
        await svc.update_policy(
            "dom-a",
            actor_user_id="mgr",
            password_enabled=False,
            allowed_email_domains=[],
            signup_enabled=False,
            signup_email_domains=[],
        )
    assert (await svc.get_policy("dom-a")).password_enabled is True
    assert [row["id"] for row in await svc.list_providers("dom-a")] == [provider["id"]]
    assert env.wire.federation.calls == []


@pytest.mark.parametrize("kind", ["oidc", "github"])
async def test_file_provider_completes_native_flow_without_sql_verified_fallback(env, kind):
    fields = oidc_fields() if kind == "oidc" else oidc_fields(kind="github", issuer_url=None)
    configure_file_auth(env.settings, providers={"corp": fields}, default=["corp"])
    await svc.update_policy(
        "dom-a",
        actor_user_id="mgr",
        password_enabled=True,
        allowed_email_domains=["corp.example"],
        signup_enabled=False,
        signup_email_domains=[],
    )
    state, binding = await start(env.wire.idp, "cfg:corp")
    login = await svc.complete_authorization("good-code", state, binding)
    assert login.provider_id == "cfg:corp" and login.provider_kind == kind
    assert login.domain_id == "dom-a" and login.unscoped_token == "unscoped-fed"
    assert 0 < login.provider_revision < 2**44
    await svc.mark_provider_verified("dom-a", login.provider_id, login.provider_revision)
    await svc.require_provider("dom-a", login.provider_id, login.provider_revision, login.login_email)
    with pytest.raises(svc.DomainAuthDenied) as email_denied:
        await svc.require_provider("dom-a", login.provider_id, login.provider_revision, "dev@other.example")
    assert email_denied.value.code == "email_domain_not_allowed"
    with pytest.raises(svc.DomainAuthUnauthenticated):
        await svc.complete_authorization("good-code", state, binding)
    assert await svc.list_providers("dom-a") == []
    assert (await svc.policy_view("dom-a"))["usable_provider_count"] == 0
    with pytest.raises(svc.DomainAuthConflict) as last_method:
        await svc.update_policy(
            "dom-a",
            actor_user_id="mgr",
            password_enabled=False,
            allowed_email_domains=[],
            signup_enabled=False,
            signup_email_domains=[],
        )
    assert last_method.value.code == "last_login_method"
    sql = await svc.create_provider("dom-a", actor_user_id="mgr", fields=oidc_fields(name="SQL fallback"))
    configure_file_auth(env.settings, providers={"corp": fields}, default=["corp", sql["id"]])
    await svc.mark_provider_verified("dom-a", sql["id"], sql["revision"])
    await svc.update_policy(
        "dom-a",
        actor_user_id="mgr",
        password_enabled=False,
        allowed_email_domains=[],
        signup_enabled=False,
        signup_email_domains=[],
    )
    # Even a completed file-provider login cannot replace SQL's proven fallback.
    with pytest.raises(svc.DomainAuthConflict) as sql_guard:
        await svc.delete_provider("dom-a", sql["id"])
    assert sql_guard.value.code == "last_login_method"
    # A selected provider does not authorize admission into another workspace.
    state, binding = await start(env.wire.idp, "cfg:corp", "dom-b")
    with pytest.raises(svc.DomainAuthDenied) as foreign:
        await svc.complete_authorization("good-code", state, binding)
    assert foreign.value.code == "invitation_required" and env.keystone.revoked == []


async def test_same_issuer_instances_keep_one_canonical_subject_across_authorized_domains(env, monkeypatch):
    from app.services import domain_projects

    monkeypatch.setattr(domain_projects, "assert_membership", lambda uid, did, **_: None)
    configure_file_auth(
        env.settings,
        providers={
            "home_sso": oidc_fields(),
            "team_sso": oidc_fields(keystone_protocol_id="team_oidc"),
        },
        default=[],
        domains={"dom-a": ["home_sso"], "dom-b": ["team_sso"]},
    )
    logins = []
    for domain_id, key, protocol, user_id, denied in (
        ("dom-a", "home_sso", "openid", "fed-user", "team_sso"),
        ("dom-b", "team_sso", "team_oidc", "fed-user", "home_sso"),
    ):
        methods = await svc.resolve_login_domain(domain_id)
        assert methods["providers"] == [{"id": f"cfg:{key}", "name": "Corp SSO", "kind": "oidc"}]
        with pytest.raises(svc.DomainAuthNotFound):
            await svc.start_authorization(domain_id, f"cfg:{denied}")
        env.wire.federation.domain_id = "dom-a"
        env.wire.federation.protocol_id = protocol
        env.wire.federation.user_id = user_id
        state, binding = await start(env.wire.idp, f"cfg:{key}", domain_id)
        login = await svc.complete_authorization("good-code", state, binding)
        assert (login.domain_id, login.user_id, login.provider_id) == (domain_id, user_id, f"cfg:{key}")
        assert env.wire.federation.calls[-1].url.path.endswith(f"/idp-a/protocols/{protocol}/auth")
        await svc.require_provider(domain_id, login.provider_id, login.provider_revision, login.login_email)
        logins.append(login)
    assert logins[0].provider_revision != logins[1].provider_revision
    assert env.keystone.revoked == []
    assert list(env.keystone.user_rows) == ["fed-user"]
    assert not any(kind == "create" for kind, _, _ in env.keystone.user_writes)


@pytest.mark.parametrize(
    ("native_domain", "native_idp", "native_protocol"),
    [
        ("dom-b", "idp-a", "team_oidc"),
        ("dom-b", "idp-b", "team_oidc"),
        ("dom-b", "idp-a", "openid"),
    ],
)
async def test_configured_native_binding_does_not_accept_another_mapping(
    env, native_domain, native_idp, native_protocol, monkeypatch
):
    from app.services import domain_projects

    monkeypatch.setattr(domain_projects, "assert_membership", lambda uid, did, **_: None)
    configure_file_auth(
        env.settings,
        providers={"team_sso": oidc_fields(keystone_protocol_id="team_oidc")},
        default=[],
        domains={"dom-b": ["team_sso"]},
    )
    env.wire.federation.domain_id = native_domain
    env.wire.federation.idp_id = native_idp
    env.wire.federation.protocol_id = native_protocol
    state, binding = await start(env.wire.idp, "cfg:team_sso", "dom-b")
    with pytest.raises(svc.DomainAuthDenied) as rejected:
        await svc.complete_authorization("good-code", state, binding)
    assert rejected.value.code == "canonical_subject_mismatch"
    assert env.keystone.revoked == ["unscoped-fed"]
    with pytest.raises(svc.DomainAuthUnauthenticated):
        await svc.complete_authorization("good-code", state, binding)


async def test_adding_login_option_preserves_existing_pending_login_and_provider_session(env):
    configure_file_auth(env.settings, default=["corp"])
    state, binding = await start(env.wire.idp, "cfg:corp")
    configure_file_auth(
        env.settings,
        providers={
            "corp": oidc_fields(),
            "code_host": oidc_fields(name="Code host", kind="github", issuer_url=None),
        },
        default=["corp", "code_host"],
    )
    login = await svc.complete_authorization("good-code", state, binding)
    state, binding = await start(env.wire.idp, "cfg:code_host")
    added = await svc.complete_authorization("good-code", state, binding)
    assert (added.provider_id, added.provider_kind, added.login_email) == (
        "cfg:code_host",
        "github",
        "dev@corp.example",
    )
    await svc.require_provider("dom-a", login.provider_id, login.provider_revision, login.login_email)
    assert env.keystone.revoked == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("client_secret", SECRET + "-rotated"),
        ("client_id", "replacement-client"),
        ("scopes", ["openid", "email"]),
        ("keystone_protocol_id", "saml"),
    ],
)
async def test_file_security_revision_invalidates_pending_state_refresh_and_verified_marker(env, field, value):
    configure_file_auth(env.settings, domains={"dom-a": ["corp"]})
    state, binding = await start(env.wire.idp, "cfg:corp")
    original = await svc._load_provider("dom-a", "cfg:corp")
    # Build a fresh validated settings object, as a restart/reload would.
    configure_file_auth(env.settings, providers={"corp": oidc_fields(**{field: value})}, domains={"dom-a": ["corp"]})
    env.wire.idp.requests.clear()
    with pytest.raises(svc.DomainAuthConflict) as callback:
        await svc.complete_authorization("good-code", state, binding)
    assert callback.value.code == "provider_changed"
    with pytest.raises(svc.DomainAuthDenied) as refresh:
        await svc.require_provider("dom-a", "cfg:corp", original.revision, "Dev@corp.example")
    assert refresh.value.code == "provider_changed"
    with pytest.raises(svc.DomainAuthConflict) as verified:
        await svc.mark_provider_verified("dom-a", "cfg:corp", original.revision)
    assert verified.value.code == "provider_changed"
    assert not any(request.method == "POST" for request in env.wire.idp.requests)
    assert env.wire.federation.calls == []


@pytest.mark.parametrize("change", ["disabled", "removed", "unselected"])
async def test_file_membership_is_rechecked_at_every_authority_boundary(env, change):
    configure_file_auth(env.settings, domains={"dom-a": ["corp"]})
    original = await svc._load_provider("dom-a", "cfg:corp")
    state, binding = await start(env.wire.idp, "cfg:corp")
    configure_file_auth(
        env.settings,
        providers={} if change == "removed" else {"corp": oidc_fields(enabled=change != "disabled")},
        domains={"dom-a": ["corp"] if change == "disabled" else []},
    )
    assert (await svc.public_methods("dom-a"))["providers"] == []
    with pytest.raises(svc.DomainAuthNotFound):
        await svc.start_authorization("dom-a", "cfg:corp")
    with pytest.raises(svc.DomainAuthDenied) as callback:
        await svc.complete_authorization("good-code", state, binding)
    assert callback.value.code == "provider_disabled"
    with pytest.raises(svc.DomainAuthDenied) as refresh:
        await svc.require_provider("dom-a", "cfg:corp", original.revision, "Dev@corp.example")
    assert refresh.value.code == "provider_disabled"
    with pytest.raises(svc.DomainAuthConflict):
        await svc.mark_provider_verified("dom-a", "cfg:corp", original.revision)
    assert env.wire.federation.calls == []


async def test_file_revision_is_stable_on_reload_and_label_edits_and_secret_is_domain_bound(env):
    configure_file_auth(env.settings, default=["corp"])
    original = await svc._load_provider("dom-a", "cfg:corp")
    state, binding = await start(env.wire.idp, "cfg:corp")
    configure_file_auth(env.settings, providers={"corp": oidc_fields(name="A new label")}, default=["corp"])
    reloaded = await svc._load_provider("dom-a", "cfg:corp")
    foreign = await svc._load_provider("dom-b", "cfg:corp")
    assert reloaded.revision == original.revision != foreign.revision
    assert reloaded.client_secret_ciphertext != original.client_secret_ciphertext
    assert SECRET not in reloaded.client_secret_ciphertext
    assert (
        svc.decrypt_client_secret(reloaded.client_secret_ciphertext, domain_id="dom-a", provider_id="cfg:corp")
        == SECRET
    )
    for domain_id, provider_id in (("dom-b", "cfg:corp"), ("dom-a", "cfg:other")):
        with pytest.raises(svc.DomainAuthUnavailable):
            svc.decrypt_client_secret(reloaded.client_secret_ciphertext, domain_id=domain_id, provider_id=provider_id)
    assert (await svc.complete_authorization("good-code", state, binding)).provider_revision == original.revision
    with pytest.raises(svc.DomainAuthDenied):
        await svc.require_provider("dom-b", "cfg:corp", original.revision, "Dev@corp.example")


async def test_file_discovery_cannot_move_credentials_even_across_domains_and_nonsecret_edits(env):
    configure_file_auth(env.settings, default=["corp"])
    original = await svc._load_provider("dom-a", "cfg:corp")
    state, binding = await start(env.wire.idp, "cfg:corp")
    env.wire.idp.token_query = "?destination=replacement"
    env.wire.idp.requests.clear()
    for domain_id in ("dom-a", "dom-b"):
        with pytest.raises(svc.DomainAuthConflict) as moved:
            await svc.start_authorization(domain_id, "cfg:corp")
        assert moved.value.code == "provider_changed"
    with pytest.raises(svc.DomainAuthConflict):
        await svc.complete_authorization("good-code", state, binding)
    with pytest.raises(svc.DomainAuthConflict):
        await svc.require_provider("dom-a", "cfg:corp", original.revision, "Dev@corp.example")
    configure_file_auth(
        env.settings, providers={"corp": oidc_fields(name="Renamed", scopes=["openid", "email"])}, default=["corp"]
    )
    with pytest.raises(svc.DomainAuthConflict):
        await svc.start_authorization("dom-a", "cfg:corp")
    assert not any(request.method == "POST" for request in env.wire.idp.requests)
    # Deliberate secret rotation establishes a fresh destination binding.
    configure_file_auth(env.settings, providers={"corp": oidc_fields(client_secret=SECRET + "-2")}, default=["corp"])
    env.wire.idp.client_secret = SECRET + "-2"
    state, binding = await start(env.wire.idp, "cfg:corp")
    assert (await svc.complete_authorization("good-code", state, binding)).provider_revision != original.revision


async def test_file_provider_does_not_bypass_database_or_discovery_binding_outages(env, monkeypatch):
    configure_file_auth(env.settings, domains={"dom-a": ["corp"]})
    original = await svc._load_provider("dom-a", "cfg:corp")
    state, binding = await start(env.wire.idp, "cfg:corp")
    monkeypatch.setattr(database, "is_db_available", lambda: False)
    for operation in (
        svc.public_methods("dom-a"),
        svc.start_authorization("dom-a", "cfg:corp"),
        svc.complete_authorization("good-code", state, binding),
        svc.require_provider("dom-a", "cfg:corp", original.revision, "Dev@corp.example"),
        svc.mark_provider_verified("dom-a", "cfg:corp", original.revision),
    ):
        with pytest.raises(svc.DomainAuthUnavailable):
            await operation
    monkeypatch.setattr(database, "is_db_available", lambda: True)

    async def broken_redis():
        raise ConnectionError("redis down")

    monkeypatch.setattr(svc, "_redis", broken_redis)
    with pytest.raises(svc.DomainAuthUnavailable):
        await svc.require_provider("dom-a", "cfg:corp", original.revision, "Dev@corp.example")


async def test_api_file_login_session_revision_survives_real_rotation(api, env):
    from app.services import jwt_service, session_store

    configure_file_auth(env.settings, domains={"dom-a": ["corp"]})
    async with api.client as client:
        resolved = await client.get("/api/v1/auth/domains/resolve", params={"name": "Alpha"})
        assert resolved.json()["providers"] == [{"id": "cfg:corp", "name": "Corp SSO", "kind": "oidc"}]
        assert SECRET not in resolved.text
        begun = await client.post("/api/v1/auth/domains/dom-a/providers/cfg:corp/authorize")
        assert begun.status_code == 200
        state = env.wire.idp.remember(begun.json()["authorize_url"])
        done = await client.post("/api/v1/auth/providers/callback", json={"code": "good-code", "state": state})
        assert done.status_code == 200 and done.json()["domain_id"] == "dom-a"
        assert done.json()["project_id"] == done.json()["default_project_id"] == "default-a"
        claims = jwt_service.verify_refresh(done.json()["refresh_token"])
        original = await session_store.get_session(claims["jti"])
        assert original["provider_id"] == "cfg:corp"
        assert original["project_id"] == "default-a"
        assert original["domain_id"] == original["identity_domain_id"] == "dom-a"
        rotated = await session_store.store_session(
            "file-provider-rotated",
            original["keystone_token"],
            original["project_id"],
            original["user_id"],
            int(time.time()) + 300,
            domain_id=original["domain_id"],
            identity_domain_id=original["identity_domain_id"],
            previous_jti=claims["jti"],
            timeout_seconds=3600,
        )
        assert rotated is True and await session_store.get_session(claims["jti"]) is None
        current = await session_store.get_session("file-provider-rotated")
        assert current["provider_revision"] == original["provider_revision"]
        assert current["provider_id"] == "cfg:corp" and current["login_email"] == "Dev@corp.example"
        assert current["project_id"] == "default-a"
        assert current["domain_id"] == current["identity_domain_id"] == "dom-a"
        await svc.require_provider(
            "dom-a", current["provider_id"], current["provider_revision"], current["login_email"]
        )
        assert api.native_preparations == [("fed-user", "dom-a")]
        assert (await svc.policy_view("dom-a"))["usable_provider_count"] == 0
        configure_file_auth(
            env.settings,
            providers={"corp": oidc_fields(client_secret=SECRET + "-rotated")},
            domains={"dom-a": ["corp"]},
        )
        with pytest.raises(svc.DomainAuthDenied) as refresh:
            await svc.require_provider(
                "dom-a", current["provider_id"], current["provider_revision"], current["login_email"]
            )
        assert refresh.value.code == "provider_changed"
