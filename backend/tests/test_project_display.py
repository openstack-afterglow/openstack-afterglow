"""Owner label behavior through the API and installed SDK's native JSON transport."""

import asyncio
import copy
import json
import threading
from contextlib import asynccontextmanager
from types import SimpleNamespace
from urllib.parse import urlsplit

import openstack.connection
import pytest
import pytest_asyncio
import requests
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from keystoneauth1 import session as ks_session
from keystoneauth1.noauth import NoAuth
from openstack.identity.v3.project import Project as SdkProject
from requests.adapters import BaseAdapter

from app.api.deps import get_token_info
from app.api.identity import projects
from app.services import account_spaces, identity_roles, keystone, project_display
from app.services.native_operation import NativeOperation
from tests.test_domain_iam import directory as directory
from tests.test_domain_iam import enrollments as enrollments
from tests.test_project_membership_roles import PROJECT, rid


class NativeLabels(BaseAdapter):
    """Mutable Keystone extra storage, independent of response/request assertions."""

    def __init__(self, directory):
        self.directory = directory
        self.requests = []
        self.opened = 0
        self.closed = 0
        self.mode = None
        self.after_patch = None

    def send(self, request, **kwargs):
        parsed = urlsplit(request.url)
        path = parsed.path.rstrip("/")
        self.requests.append((request.method, path, request.body))
        status = 200
        if parsed.netloc != "native.test":
            raise AssertionError("Delegated identity transport left its configured endpoint")
        if path == "/v3":
            body = {
                "version": {
                    "id": "v3.14",
                    "status": "stable",
                    "links": [{"rel": "self", "href": "http://native.test/v3/"}],
                }
            }
        else:
            project_id = path.rsplit("/", 1)[-1]
            native = self.directory.ks.projects.get(project_id)
            if request.method == "PATCH":
                if self.mode == "failure":
                    status = 503
                elif self.mode != "unpersisted":
                    for key, value in json.loads(request.body)["project"].items():
                        setattr(native, key, value)
                if self.after_patch:
                    self.after_patch()
            body = {"project": copy.deepcopy(vars(native))}
            if self.mode == "substitute" and request.method == "PATCH":
                body["project"]["id"] = "foreign-project"
            if self.mode == "readback_substitute" and any(method == "PATCH" for method, _, _ in self.requests):
                if request.method == "GET":
                    body["project"]["id"] = "foreign-project"
            if self.mode == "mutate_extra" and request.method == "PATCH":
                native.unrelated = {"lost": True}
            if self.mode == "redirect" and request.method == "PATCH":
                status = 302
        response = requests.Response()
        response.status_code = status
        response._content = json.dumps(body).encode()
        response.headers["Content-Type"] = "application/json"
        if status == 302:
            response.headers["Location"] = "http://attacker.invalid/collect"
        response.request = request
        response.url = request.url
        return response

    def connection(self):
        self.opened += 1
        transport = requests.Session()
        transport.mount("http://", self)
        transport.mount("https://", self)
        endpoint = "http://native.test/v3"
        conn = openstack.connection.Connection(
            session=ks_session.Session(auth=NoAuth(endpoint=endpoint), session=transport),
            identity_endpoint_override=endpoint,
            identity_api_version="3",
        )
        close = conn.close

        def close_once():
            self.closed += 1
            close()

        conn.close = close_once
        return conn

    def close(self):
        pass


@pytest_asyncio.fixture
async def label_target(directory, enrollments, monkeypatch):
    project = await account_spaces.ensure_personal_project("foreign")
    native = directory.personal_projects[project["id"]]
    native.unrelated = {"nested": [1, "preserved"]}
    transport = NativeLabels(directory)
    monkeypatch.setattr(keystone, "get_admin_project_connection", transport.connection)
    actor = {
        "user_id": "foreign",
        "identity_domain_id": "other",
        "domain_id": project["domain_id"],
        "project_id": project["id"],
        "token": "verified-caller",
        "is_system_admin": False,
    }
    app = FastAPI()
    app.include_router(projects.router, prefix="/api/v1/projects")
    app.dependency_overrides[get_token_info] = lambda: actor
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield SimpleNamespace(
            directory=directory,
            native=native,
            actor=actor,
            transport=transport,
            client=client,
            path=f"/api/v1/projects/{project['id']}/display-name",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("historical_owner", [False, True])
async def test_personal_owner_label_persists_without_native_identity_authority_or_quota_changes(
    label_target, historical_owner
):
    target = label_target
    directory, native = target.directory, target.native
    if historical_owner:
        directory.ks.roles.revoke(rid("member"), user="foreign", project=native.id)
        directory.ks.roles.grant(rid("project_owner"), user="foreign", project=native.id)
    before = copy.deepcopy(vars(native))
    grants = copy.deepcopy(directory.personal_direct)
    quota_limits = copy.deepcopy(directory.quota_limits)
    native_calls = copy.deepcopy(directory.calls)
    quota_writes = copy.deepcopy(directory.quota_writes)
    initial = await target.client.get(target.path)
    assert initial.status_code == 200, initial.text
    assert initial.json() == {
        "project_id": native.id,
        "native_name": native.name,
        "display_name": native.name,
        "can_edit": True,
    }
    assert target.transport.opened == 0
    response = await target.client.put(target.path, json={"display_name": "  My Personal laboratory  "})
    assert response.status_code == 200, response.text
    assert response.json() == {
        "project_id": native.id,
        "native_name": before["name"],
        "display_name": "My Personal laboratory",
        "can_edit": True,
    }
    assert (await target.client.get(target.path)).json() == response.json()
    assert vars(native) == {**before, "afterglow_display_name": "My Personal laboratory"}
    assert directory.personal_direct == grants
    assert directory.quota_limits == quota_limits and directory.quota_writes == quota_writes
    assert directory.calls == native_calls
    patches = [json.loads(body) for method, _, body in target.transport.requests if method == "PATCH"]
    assert patches == [{"project": {"afterglow_display_name": "My Personal laboratory"}}]
    assert target.transport.opened == target.transport.closed == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        "foreign_project",
        "foreign_user",
        "admin_only",
        "wrong_home",
        "wrong_domain",
        "disabled_user",
        "disabled_home",
        "disabled_project",
        "revoked_member",
        "foreign_owner",
        "missing_provenance",
    ],
)
async def test_label_edit_never_uses_admin_claim_as_membership_or_owner_bypass(label_target, case):
    target = label_target
    native, directory = target.native, target.directory
    if case == "foreign_project":
        target.actor["project_id"] = PROJECT
    elif case in {"foreign_user", "admin_only"}:
        target.actor.update(
            user_id="system-admin" if case == "admin_only" else "member",
            identity_domain_id="domain",
            is_system_admin=True,
        )
    elif case == "wrong_home":
        target.actor["identity_domain_id"] = "domain"
    elif case == "wrong_domain":
        target.actor["domain_id"] = "domain"
    elif case == "disabled_user":
        directory.users["foreign"].enabled = False
    elif case == "disabled_home":
        directory.personal_domains["other"] = SimpleNamespace(id="other", name="Other", enabled=False)
    elif case == "disabled_project":
        native.enabled = False
    elif case == "revoked_member":
        directory.ks.roles.revoke(rid("member"), user="foreign", project=native.id)
    elif case == "foreign_owner":
        native.afterglow_personal_user_id = "member"
    else:
        del native.afterglow_personal_primary
    response = await target.client.put(target.path, json={"display_name": "No access"})
    assert response.status_code in {403, 503}, response.text
    assert not hasattr(native, "afterglow_display_name")
    assert target.transport.opened == 0


@pytest.mark.asyncio
async def test_current_organization_member_can_read_label_but_cannot_delegate_writer(label_target):
    target = label_target
    target.actor.update(user_id="member", identity_domain_id="domain", domain_id="domain", project_id=PROJECT)
    target.directory.project.afterglow_display_name = "Organization workspace"
    path = f"/api/v1/projects/{PROJECT}/display-name"
    response = await target.client.get(path)
    assert response.status_code == 200, response.text
    assert response.json()["display_name"] == "Organization workspace"
    assert response.json()["can_edit"] is False
    assert (await target.client.put(path, json={"display_name": "Unauthorized"})).status_code == 403
    assert target.transport.opened == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {"display_name": ""},
        {"display_name": "  "},
        {"display_name": "x" * 65},
        {"display_name": "new\nline"},
        {"display_name": "newline\n"},
        {"display_name": "tab\t"},
        {"display_name": "hidden\u200b"},
        {"display_name": "null\x00"},
        {"display_name": 7},
        {"display_name": None},
        {"display_name": "Safe", "name": "native rename"},
        {"display_name": "Safe", "afterglow_personal_user_id": "other"},
        {},
    ],
)
async def test_label_payload_rejects_invalid_names_and_unexpected_mutations(label_target, body):
    target = label_target
    response = await target.client.put(target.path, json=body)
    assert response.status_code == 422, response.text
    assert not hasattr(target.native, "afterglow_display_name")
    assert target.transport.opened == 0


@pytest.mark.asyncio
async def test_label_length_counts_unicode_codepoints_and_extra_personal_projects_are_editable(label_target):
    target = label_target
    # Extra projects share the same verified direct-member owner boundary.
    target.native.afterglow_personal_primary = False
    label = "🧪" * 64
    response = await target.client.put(target.path, json={"display_name": label})
    assert response.status_code == 200, response.text
    assert (await target.client.get(target.path)).json()["display_name"] == label


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode", ["failure", "unpersisted", "substitute", "readback_substitute", "mutate_extra", "redirect"]
)
async def test_label_native_failure_or_substituted_response_is_not_published(label_target, mode):
    target = label_target
    target.transport.mode = mode
    response = await target.client.put(target.path, json={"display_name": "Not confirmed"})
    assert response.status_code == 503, response.text
    assert target.transport.opened == target.transport.closed == 1
    assert sum(method == "PATCH" for method, _, _ in target.transport.requests) == 1


@pytest.mark.asyncio
async def test_owner_revocation_during_graph_lease_acquisition_prevents_patch(label_target, monkeypatch):
    target = label_target
    lock = identity_roles._graph_lock

    @asynccontextmanager
    async def revoke_before_lock(connection):
        target.directory.ks.roles.revoke(rid("member"), user="foreign", project=target.native.id)
        async with lock(connection) as lease:
            yield lease

    monkeypatch.setattr(identity_roles, "_graph_lock", revoke_before_lock)
    response = await target.client.put(target.path, json={"display_name": "Denied"})
    assert response.status_code == 403, response.text
    assert not target.transport.requests
    assert target.transport.opened == target.transport.closed == 1


@pytest.mark.asyncio
async def test_owner_revocation_after_native_write_prevents_success_publication(label_target):
    target = label_target
    target.transport.after_patch = lambda: target.directory.ks.roles.revoke(
        rid("member"), user="foreign", project=target.native.id
    )
    response = await target.client.put(target.path, json={"display_name": "Stored but not authorized"})
    assert response.status_code == 403, response.text
    assert target.transport.opened == target.transport.closed == 1
    assert (await target.client.get(target.path)).status_code == 403


@pytest.mark.asyncio
async def test_sdk_projection_and_fresh_native_token_project_name_keep_persistent_label(label_target, monkeypatch):
    target = label_target
    native = target.native
    response = await target.client.put(target.path, json={"display_name": "Readable project"})
    assert response.status_code == 200, response.text
    sdk_project = SdkProject.existing(id=native.id, name=native.name, domain_id=native.domain_id)
    assert project_display.display_name(sdk_project) == "Readable project"
    from keystoneclient.v3 import client as ks_client

    monkeypatch.setattr(ks_client, "Client", lambda **kwargs: target.directory.ks)
    access = SimpleNamespace(
        user_id="foreign",
        user_domain_id="other",
        username="foreign",
        auth_token="caller-native-token",
        project_id=native.id,
        project_domain_id=native.domain_id,
        project_name=native.name,
        role_names=["member"],
        expires=None,
    )
    with NativeOperation() as operation:
        operation.subjects["caller-native-token"] = (access, object())
        listed = keystone.list_projects("caller-native-token", native.domain_id, operation=operation)
        published = keystone._access_info(access, operation=operation)
    assert next(row for row in listed if row["id"] == native.id)["name"] == "Readable project"
    assert published["project_name"] == "Readable project"
    assert published["project_id"] == native.id
    assert published["token"] == "caller-native-token" and published["roles"] == ["member"]
    assert access.project_name == native.name


@pytest.mark.parametrize("metadata", ["", " padded ", "x" * 65, {"name": "invalid"}, "hidden\u200b", "newline\n"])
def test_malformed_native_display_metadata_fails_closed(metadata):
    with pytest.raises(HTTPException) as exc:
        project_display.display_name({"id": "project", "name": "immutable-native", "afterglow_display_name": metadata})
    assert exc.value.status_code == 503


def test_sdk_project_substitution_cannot_supply_a_display_label(directory):
    sdk_project = SdkProject.existing(id=PROJECT, name="substituted-name", domain_id="domain")
    with pytest.raises(HTTPException) as exc:
        project_display.display_name(sdk_project)
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_label_metadata_capacity_preserves_existing_extras_without_dispatch(label_target):
    target = label_target
    target.native.unrelated = {"existing": "x" * 60_000}
    before = copy.deepcopy(vars(target.native))
    response = await target.client.put(target.path, json={"display_name": "Bounded"})
    assert response.status_code == 422, response.text
    assert vars(target.native) == before
    assert not any(method == "PATCH" for method, _, _ in target.transport.requests)
    assert target.transport.opened == target.transport.closed == 1


@pytest.mark.asyncio
async def test_personal_owner_with_unexpected_native_grant_cannot_use_label_writer(label_target):
    target = label_target
    target.directory.ks.roles.grant(rid("project_admin"), user="foreign", project=target.native.id)
    before = copy.deepcopy(target.directory.personal_direct)
    response = await target.client.put(target.path, json={"display_name": "Not authorized"})
    assert response.status_code in {403, 503}, response.text
    assert target.directory.personal_direct == before
    assert target.transport.opened == 0


@pytest.mark.asyncio
async def test_native_project_substitution_fails_before_writer_acquisition(label_target, monkeypatch):
    target = label_target
    native_get = target.directory.ks.projects.get

    def substituted(project_id):
        if project_id == target.native.id:
            return SimpleNamespace(**{**vars(target.native), "id": "foreign-project"})
        return native_get(project_id)

    monkeypatch.setattr(target.directory.ks.projects, "get", substituted)
    response = await target.client.put(target.path, json={"display_name": "Not authorized"})
    assert response.status_code == 503, response.text
    assert target.transport.opened == 0


@pytest.mark.asyncio
async def test_native_directory_failure_does_not_open_delegated_writer(label_target):
    target = label_target
    target.directory.fail = True
    response = await target.client.put(target.path, json={"display_name": "Not authorized"})
    assert response.status_code == 503, response.text
    assert target.transport.opened == 0


@pytest.mark.asyncio
async def test_cancelled_label_read_drains_native_thread_before_closing_owned_session(label_target, monkeypatch):
    target = label_target
    entered = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    closures = []
    native_get = target.directory.ks.projects.get

    def blocking_get(project_id):
        entered.set()
        if not release.wait(timeout=5):
            raise RuntimeError("Native read was not released")
        try:
            return native_get(project_id)
        finally:
            finished.set()

    def close_session():
        closures.append(finished.is_set())

    monkeypatch.setattr(target.directory.ks.projects, "get", blocking_get)
    monkeypatch.setattr(
        target.directory.ks, "session", SimpleNamespace(session=SimpleNamespace(close=close_session)), raising=False
    )
    task = asyncio.create_task(project_display.get_display_name(target.native.id, target.actor))
    try:
        assert await asyncio.to_thread(entered.wait, 5)
        task.cancel()
        await asyncio.sleep(0)
        assert closures == []
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert finished.is_set()
    assert closures == [True]
    assert target.transport.opened == 0
