"""Waygate action gates: verified-principal units and native-authority BFF regressions."""

import asyncio

import httpx
import pytest
from fastapi import FastAPI, HTTPException, Request

from app.api import deps
from app.api.waygate.proxy import router as waygate_proxy_router
from app.services import domain_scope, keystone, service_proxy
from app.services.service_permissions import ROLE_IMPLICATIONS, ROLE_PRESETS
from app.services.waygate_authorization import authorize_waygate_request

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


def _request(method: str, body: bytes = b"") -> Request:
    delivered = False

    async def receive():
        nonlocal delivered
        if delivered:
            return {"type": "http.disconnect"}
        delivered = True
        return {"type": "http.request", "body": body, "more_body": False}

    scope = {
        "type": "http",
        "method": method,
        "path": "/",
        "query_string": b"",
        "headers": [(b"content-type", b"application/json")],
    }
    return Request(scope, receive)


async def _allowed(method: str, path: str, roles: list[str], body: bytes = b"", *, system: bool = False) -> bool:
    """Exercise only the action policy; system=True represents an already-verified principal."""
    principal = {"user_id": USER, "project_id": PROJECT, "roles": roles, "is_system_admin": system}
    try:
        await authorize_waygate_request(_request(method, body), path, principal)
    except HTTPException as exc:
        assert exc.status_code == 403
        return False
    return True


@pytest.mark.parametrize(
    "method,path,leaves",
    [
        ("GET", "/v1/", [INVENTORY]),
        ("GET", "/v1/health", [INVENTORY]),
        ("GET", "/v1/servers", [INVENTORY]),
        ("GET", "/v1/servers/", [INVENTORY]),
        ("HEAD", SERVERS, [INVENTORY]),
        ("GET", f"{SERVERS}/clients", [INVENTORY]),
        ("GET", f"{SERVERS}/networks", [INVENTORY]),
        ("GET", f"{SERVERS}/clients/{CLIENT}/config", [CONNECT]),
        ("POST", "/v1/servers", [GATEWAYS_EDITOR]),
        ("PATCH", SERVERS, [GATEWAYS_EDITOR]),
        ("POST", f"{SERVERS}/clients", [CLIENTS_EDITOR]),
        ("DELETE", SERVERS, [GATEWAYS_ADMIN]),
        ("POST", f"{SERVERS}/agent-token/rotate", [GATEWAYS_ADMIN]),
        ("DELETE", f"{SERVERS}/clients/{CLIENT}", [CLIENTS_ADMIN]),
        ("POST", f"{SERVERS}/networks", [ROUTING_ADMIN]),
        ("DELETE", f"{SERVERS}/networks/7", [ROUTING_ADMIN]),
        ("POST", f"{SERVERS}/export", [CLIENTS_ADMIN, ROUTING_ADMIN]),
        ("POST", f"{SERVERS}/import", [CLIENTS_ADMIN, ROUTING_ADMIN]),
    ],
)
async def test_exact_native_leaves_without_parent_or_raw_admin_shortcut(method, path, leaves):
    assert await _allowed(method, path, ["member", *leaves])
    for missing in leaves:
        assert not await _allowed(method, path, ["member", *[leaf for leaf in leaves if leaf != missing]])
    assert not await _allowed(method, path, ["member", "waygate_admin", "project_owner", "project_admin"])
    # Unverified raw admin/manager never acts as a service grade, even beside leaves.
    assert not await _allowed(method, path, ["member", "admin", *leaves])
    assert not await _allowed(method, path, ["member", "manager", *leaves])


@pytest.mark.parametrize(
    "method,path,user,editor",
    [
        ("GET", f"{SERVERS}/clients/{CLIENT}/config", True, True),
        ("POST", "/v1/servers", False, True),
        ("PATCH", SERVERS, False, True),
        ("POST", f"{SERVERS}/clients", False, True),
        ("DELETE", SERVERS, False, False),
        ("DELETE", f"{SERVERS}/clients/{CLIENT}", False, False),
        ("POST", f"{SERVERS}/agent-token/rotate", False, False),
        ("POST", f"{SERVERS}/networks", False, False),
        ("DELETE", f"{SERVERS}/networks/7", False, False),
        ("POST", f"{SERVERS}/export", False, False),
        ("POST", f"{SERVERS}/import", False, False),
    ],
)
async def test_grade_bundles_connect_edit_and_admin_actions(method, path, user, editor):
    assert await _allowed(method, path, ["member", *USER_GRADE]) is user
    assert await _allowed(method, path, ["member", *EDITOR_GRADE]) is editor
    assert await _allowed(method, path, ["member", *ADMIN_GRADE])


async def test_reader_baseline_admits_inventory_but_not_connect():
    assert await _allowed("GET", "/v1/servers", ["reader", INVENTORY])
    assert not await _allowed("GET", f"{SERVERS}/clients/{CLIENT}/config", ["reader", INVENTORY, CONNECT])


@pytest.mark.parametrize(
    "body,roles,allowed",
    [
        (b'{"name": "laptop"}', [CLIENTS_EDITOR], True),
        (b'{"owner_user_id": "u"}', [CLIENTS_EDITOR], True),
        (b'{"enabled": false}', [CLIENTS_EDITOR], False),
        (b'{"enabled": true}', [CLIENTS_ADMIN], True),
        (b'{"name": "laptop"}', [CLIENTS_ADMIN], False),
        (b'{"name": "laptop", "enabled": false}', [CLIENTS_ADMIN], False),
        (b'{"name": "laptop", "enabled": false}', [CLIENTS_EDITOR, CLIENTS_ADMIN], True),
        (b"{}", [CLIENTS_EDITOR], True),
        (b"{}", [CONNECT, INVENTORY], False),
    ],
)
async def test_client_patch_separates_editing_from_revocation(body, roles, allowed):
    path = f"{SERVERS}/clients/{CLIENT}"
    assert await _allowed("PATCH", path, ["member", *roles], body) is allowed


async def test_client_patch_body_remains_replayable_for_forwarding():
    body = b'{"name": "laptop", "enabled": false}'
    request = _request("PATCH", body)
    principal = {"roles": ["member", CLIENTS_EDITOR, CLIENTS_ADMIN], "is_system_admin": False}
    await authorize_waygate_request(request, f"{SERVERS}/clients/{CLIENT}", principal)
    assert b"".join([chunk async for chunk in request.stream()]) == body


async def test_platform_policies_are_verified_system_only():
    for method, path in (
        ("GET", "/v1/admin/resource-policies"),
        ("GET", "/v1/admin/resource-policies/catalog/waygate.flavor"),
        ("PUT", "/v1/admin/resource-policies/waygate.flavor"),
    ):
        assert not await _allowed(method, path, ["member", *ADMIN_GRADE])
        assert not await _allowed(method, path, ["member", "admin", *ADMIN_GRADE])
        assert await _allowed(method, path, [], system=True)


async def test_verified_system_admin_bypasses_project_grade_gates():
    assert await _allowed("POST", f"{SERVERS}/import", [], system=True)
    assert await _allowed("DELETE", SERVERS, [], system=True)


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", f"{SERVERS}/agent/register"),
        ("GET", f"{SERVERS}/agent/desired-state"),
        ("POST", f"{SERVERS}/agent/status"),
        ("PUT", SERVERS),
        ("GET", "/v1/admin"),
        ("GET", "/v2/servers"),
        ("GET", f"/v1/servers/{SERVER}/../../admin/resource-policies"),
        ("DELETE", "/v1/servers/./x"),
        ("DELETE", f"/v1/servers/{SERVER}%2Fclients%2F{CLIENT}"),
        ("GET", "/v1/servers//clients"),
        ("GET", f"/v1/servers/{SERVER}?x/clients"),
        ("GET", "/v1/v1/servers"),
    ],
)
async def test_unknown_machine_and_ambiguous_paths_fail_closed_even_for_system(method, path):
    assert not await _allowed(method, path, ["member", *ADMIN_GRADE])
    assert not await _allowed(method, path, [], system=True)


async def test_options_preflight_has_no_action_guard():
    assert await _allowed("OPTIONS", f"{SERVERS}/import", [])


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
    directory.roles.extend(
        {"id": f"{row['name']}-role", "name": row["name"], "domain_id": None} for row in ROLE_PRESETS
    )
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


async def test_current_downgrade_denies_before_upstream(bff):
    client, directory, upstream, _ = bff
    directory.assignments = _project_grants("member", INVENTORY)
    base = f"/api/v1/waygate/servers/{SERVER}"
    assert (await client.delete(base)).status_code == 403
    assert (await client.post(f"{base}/import", content=b"{}")).status_code == 403
    assert (await client.get(f"{base}/clients/{CLIENT}/config")).status_code == 403
    assert (await client.get("/api/v1/waygate/admin/resource-policies")).status_code == 403
    assert upstream == []
    assert (await client.get(f"{base}/clients")).status_code == 200
    assert [request.url.path for request in upstream] == [f"/v1/servers/{SERVER}/clients"]
    assert upstream[-1].method == "GET"
    assert upstream[-1].headers["x-auth-token"] == "keystone-token"
    assert upstream[-1].headers["x-project-id"] == PROJECT
    assert "x-target-project-id" not in upstream[-1].headers


async def test_editor_patch_forwards_exact_body_and_revocation_needs_admin(bff):
    client, directory, upstream, _ = bff
    directory.assignments = _project_grants("member", "waygate_editor")
    path = f"/api/v1/waygate/servers/{SERVER}/clients/{CLIENT}"
    body = b'{"name": "laptop", "dns": ["10.0.0.2"]}'
    response = await client.patch(path, content=body, headers={"content-type": "application/json"})
    assert response.status_code == 200
    assert upstream[-1].method == "PATCH"
    assert upstream[-1].url.path == f"/v1/servers/{SERVER}/clients/{CLIENT}"
    assert upstream[-1].headers["x-auth-token"] == "keystone-token"
    assert upstream[-1].headers["x-project-id"] == PROJECT
    assert upstream[-1].content == body
    revoked = await client.patch(path, content=b'{"enabled": false}', headers={"content-type": "application/json"})
    assert revoked.status_code == 403
    assert len(upstream) == 1


async def test_credential_import_stream_is_not_parsed_or_damaged(bff):
    client, directory, upstream, _ = bff
    path = f"/api/v1/waygate/servers/{SERVER}/import"
    body = b"\x00not-json-bundle\xff" * 64
    directory.assignments = _project_grants("member", CLIENTS_ADMIN)
    assert (await client.post(path, content=body)).status_code == 403
    assert upstream == []
    directory.assignments = _project_grants("member", CLIENTS_ADMIN, ROUTING_ADMIN)
    assert (await client.post(path, content=body)).status_code == 200
    assert upstream[-1].content == body
    assert upstream[-1].method == "POST"
    assert upstream[-1].url.path == f"/v1/servers/{SERVER}/import"
    assert upstream[-1].headers["x-auth-token"] == "keystone-token"
    assert upstream[-1].headers["x-project-id"] == PROJECT


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


async def test_current_group_membership_and_role_id_edges_drive_bff(bff):
    client, directory, upstream, _ = bff
    directory.groups["editors"] = {"id": "editors", "name": "editors", "domain_id": "default"}
    directory.memberships.add((USER, "editors"))
    directory.assignments.append(
        {
            "group": {"id": "editors"},
            "role": {"id": "waygate_editor-role"},
            "scope": {"project": {"id": PROJECT}},
        }
    )
    path = f"/api/v1/waygate/servers/{SERVER}/clients/{CLIENT}"
    body = b'{"name":"group-owned-laptop"}'
    assert (await client.patch(path, content=body)).status_code == 200
    assert upstream[-1].method == "PATCH"
    assert upstream[-1].url.path == f"/v1/servers/{SERVER}/clients/{CLIENT}"
    assert upstream[-1].content == body
    assert upstream[-1].headers["x-project-id"] == PROJECT

    directory.memberships.remove((USER, "editors"))
    upstream.clear()
    assert (await client.patch(path, content=body)).status_code == 403
    assert upstream == []

    directory.memberships.add((USER, "editors"))
    directory.inferences = [
        edge
        for edge in directory.inferences
        if not (
            edge["prior_role"]["id"] == "waygate_editor-role" and {"id": f"{CLIENTS_EDITOR}-role"} in edge["implies"]
        )
    ]
    assert (await client.patch(path, content=body)).status_code == 403
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
