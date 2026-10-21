"""Fresh identity and verified system boundaries around native Waygate policy."""

import asyncio

import httpx
import pytest
from fastapi import FastAPI, Request

from app.api import deps
from app.api.waygate.proxy import router as waygate_proxy_router
from app.services import domain_scope, keystone, service_proxy
from app.services.service_permissions import ROLE_IMPLICATIONS

PROJECT = "11111111111141118111111111111111"
USER = "33333333333343338333333333333333"
SERVER = "44444444-4444-4444-8444-444444444444"
CLIENT = "55555555-5555-4555-8555-555555555555"
INVENTORY = "waygate-inventory_reader"
CONNECT = "waygate-connect_user"
CLIENTS_EDITOR = "waygate-clients_editor"
GATEWAYS_EDITOR = "waygate-gateways_editor"
CLIENTS_ADMIN = "waygate-clients_admin"
GATEWAYS_ADMIN = "waygate-gateways_admin"
ROUTING_ADMIN = "waygate-routing_admin"
USER_GRADE = [INVENTORY, CONNECT]
EDITOR_GRADE = [*USER_GRADE, CLIENTS_EDITOR, GATEWAYS_EDITOR]
ADMIN_GRADE = [*EDITOR_GRADE, CLIENTS_ADMIN, GATEWAYS_ADMIN, ROUTING_ADMIN]
SERVERS = f"/v1/servers/{SERVER}"


def _project_grants(*roles: str) -> list[dict]:
    return [
        {"user": {"id": USER}, "role": {"id": f"{role}-role"}, "scope": {"project": {"id": PROJECT}}} for role in roles
    ]


@pytest.fixture
async def bff(monkeypatch, auth_directory, native_auth):
    """Synthetic session/provider I/O; native identity, membership and authority checks run."""
    real_client = httpx.AsyncClient
    upstream: list[httpx.Request] = []
    directory = auth_directory
    directory.users[USER] = {
        "id": USER,
        "name": "waygate-user",
        "domain_id": "default",
        "enabled": True,
        "email": "waygate@example.test",
        "default_project_id": PROJECT,
    }
    directory.projects[PROJECT] = {
        "id": PROJECT,
        "name": "waygate-project",
        "domain_id": "default",
        "enabled": True,
        "parent_id": "default",
    }
    directory.grants = {}
    directory.assignments = _project_grants("member")
    directory.inferences = [
        {"prior_role": {"id": f"{prior}-role"}, "implies": [{"id": f"{implied}-role"}]}
        for prior, implied in ROLE_IMPLICATIONS
    ]
    directory.groups = {}
    directory.memberships = set()
    ks = keystone._get_admin_ks_client()

    def groups_list(user=None, domain=None):
        return [
            group
            for gid, group in directory.groups.items()
            if (user is None or (user, gid) in directory.memberships)
            and (domain is None or group["domain_id"] == domain)
        ]

    def users_list(domain=None, name=None, group=None):
        return [
            user
            for uid, user in directory.users.items()
            if (domain is None or user["domain_id"] == domain)
            and (name is None or user["name"] == name)
            and (group is None or (uid, group) in directory.memberships)
        ]

    def assignments(effective=False, **query):
        rows = []
        for row in directory.assignments:
            if not effective:
                rows.append(row)
            elif "system" not in row["scope"]:
                # Keystone effective project grants resolve group members to users;
                # system authority must instead use raw grants and live groups.
                if "group" in row:
                    rows.extend(
                        {"user": {"id": uid}, "role": row["role"], "scope": row["scope"]}
                        for uid, gid in directory.memberships
                        if gid == row["group"]["id"]
                    )
                else:
                    rows.append(row)
        for key in ("user", "group"):
            if key in query:
                rows = [row for row in rows if row.get(key, {}).get("id") == query[key]]
        for key in ("project", "domain"):
            if key in query:
                rows = [row for row in rows if row["scope"].get(key, {}).get("id") == query[key]]
        if "system" in query:
            rows = [row for row in rows if row["scope"].get("system") == {query["system"]: True}]
        return rows

    monkeypatch.setattr(ks.groups, "get", directory.groups.__getitem__, raising=False)
    monkeypatch.setattr(ks.groups, "list", groups_list)
    monkeypatch.setattr(ks.users, "list", users_list)
    monkeypatch.setattr(ks.role_assignments, "list", assignments)
    native_auth.user_id = USER
    native_auth.token = "keystone-token"
    # Deliberately stale token roles must never replace current assignments.
    native_auth.roles = ["member", *ADMIN_GRADE]
    session = {"system_claim": False}

    async def handler(request: httpx.Request) -> httpx.Response:
        upstream.append(request)
        # Network responses stay unread until the BFF's aiter_raw bridge consumes them.
        return httpx.Response(
            200, stream=httpx.ByteStream(b'{"ok":true}'), headers={"content-type": "application/json"}
        )

    def upstream_client(**kwargs):
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    async def identity(request: Request):
        # Replace session storage/transport, not native authority. Validation also
        # checks the enabled user/home/project and current project membership.
        await asyncio.to_thread(domain_scope.domain_context, USER, "default")
        info = await asyncio.to_thread(keystone.validate_token, native_auth.token, project_id=PROJECT)
        # A stale positive claim is only a candidate: require_admin must recheck it.
        info["is_system_admin"] = info["is_system_admin"] or session["system_claim"]
        request.state.token_info = info
        return info

    app = FastAPI()
    app.include_router(waygate_proxy_router, prefix="/api/v1/waygate")
    app.dependency_overrides[deps.get_token_info] = identity
    monkeypatch.setattr(service_proxy, "_get_internal_endpoint", lambda *_: "http://waygate.internal/v1")
    monkeypatch.setattr(httpx, "AsyncClient", upstream_client)
    async with real_client(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client, directory, upstream, session


@pytest.mark.parametrize("via_group", [False, True], ids=["direct", "group"])
async def test_current_native_system_grant_admits_platform_policy_then_revocation_denies(bff, via_group):
    client, directory, upstream, session = bff
    grant = {"role": {"id": "admin-role"}, "scope": {"system": {"all": True}}}
    if via_group:
        directory.groups["operators"] = {"id": "operators", "name": "operators", "domain_id": "default"}
        directory.memberships.add((USER, "operators"))
        grant["group"] = {"id": "operators"}
    else:
        grant["user"] = {"id": USER}
    directory.assignments.append(grant)
    path = "/api/v1/waygate/admin/resource-policies"
    response = await client.get(path)
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert [request.url.path for request in upstream] == ["/v1/admin/resource-policies"]
    assert upstream[-1].method == "GET"
    assert upstream[-1].headers["x-auth-token"] == "keystone-token"
    assert upstream[-1].headers["x-project-id"] == PROJECT
    assert "x-target-project-id" not in upstream[-1].headers

    # Leave the old positive claim behind after revoking the real authority.
    session["system_claim"] = True
    if via_group:
        directory.memberships.remove((USER, "operators"))
    else:
        directory.assignments.remove(grant)
    upstream.clear()
    assert (await client.get(path)).status_code == 403
    assert upstream == []


async def test_stale_system_claim_and_project_admin_never_admit_platform_policy(bff):
    client, directory, upstream, session = bff
    session["system_claim"] = True
    directory.assignments = _project_grants("member", "admin", "waygate_admin")
    assert (await client.get("/api/v1/waygate/admin/resource-policies")).status_code == 403
    assert upstream == []


@pytest.mark.parametrize("resource", ["user", "home", "project", "membership"])
async def test_current_native_identity_and_membership_required_before_forwarding(bff, resource):
    client, directory, upstream, _ = bff
    directory.assignments = _project_grants("member", INVENTORY)
    if resource == "user":
        directory.users[USER]["enabled"] = False
    elif resource == "home":
        directory.domains["default"]["enabled"] = False
    elif resource == "project":
        directory.projects[PROJECT]["enabled"] = False
    else:
        directory.assignments.clear()
    # Native invalid identity is 401; disabled scopes/revoked membership are 403.
    response = await client.get(f"/api/v1/waygate/servers/{SERVER}/clients")
    assert response.status_code == (401 if resource == "user" else 403)
    assert upstream == []
