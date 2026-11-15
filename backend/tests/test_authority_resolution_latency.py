"""Request-local authority proof and delayed synthetic Keystone round trips.

The endpoint benchmark also runs unchanged against the baseline checkout with
AUTHORITY_BENCHMARK=1. Native token exchanges and Redis use existing auth fakes;
only directory REST operations below receive the artificial delay.
"""

from __future__ import annotations

import gc
import inspect
import json
import os
import threading
import time
import weakref
from collections import Counter
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import deps
from app.services import domain_projects, identity_roles, keystone, service_authorization
from app.services.identity_roles import _trusted_catalog
from app.services.native_operation import NativeOperation
from tests.test_auth_domain_boundaries import domain_client as domain_client
from tests.test_auth_domain_boundaries import login
from tests.test_domain_projects import domain_native as domain_native
from tests.test_domain_projects import grant, row


class Recorder:
    def __init__(self, monkeypatch, ks, delay=0.01):
        self.calls = []
        self.delay = delay
        self.active = self.peak = 0
        self.group_started = self.group_finished = None
        self.lock = threading.Lock()
        for kind, methods in {
            "users": ("get", "list"),
            "groups": ("get", "list"),
            "projects": ("get", "list"),
            "domains": ("get", "list"),
            "roles": ("list",),
            "inference_rules": ("list_inference_roles",),
            "role_assignments": ("list",),
        }.items():
            manager = getattr(ks, kind)
            for name in methods:
                if hasattr(manager, name):
                    monkeypatch.setattr(manager, name, self.wrap(kind + "." + name, getattr(manager, name)))

    def wrap(self, label, original):
        def call(*args, **kwargs):
            frame = inspect.currentframe().f_back
            while frame and not frame.f_globals.get("__name__", "").startswith("app."):
                frame = frame.f_back
            caller = frame.f_globals["__name__"] + "." + frame.f_code.co_name if frame else "unknown"
            del frame
            with self.lock:
                self.calls.append((label, args, tuple(sorted(kwargs.items())), caller))
                self.active += 1
                self.peak = max(self.peak, self.active)
                if label in {"groups.get", "users.list"} and self.group_started is None:
                    self.group_started = time.perf_counter()
            try:
                time.sleep(self.delay)
                return original(*args, **kwargs)
            finally:
                with self.lock:
                    self.active -= 1
                    if label in {"groups.get", "users.list"}:
                        self.group_finished = time.perf_counter()

        return call

    def reset(self):
        self.calls.clear()
        self.peak = 0
        self.group_started = self.group_finished = None

    def report(self, path, elapsed):
        return {
            "path": path,
            "delay_ms": self.delay * 1000,
            "calls": len(self.calls),
            "elapsed_ms": round(elapsed * 1000, 2),
            "peak": self.peak,
            "map": [
                {"method": label, "args": args, "query": dict(query), "caller": caller, "count": count}
                for (label, args, query, caller), count in sorted(Counter(self.calls).items())
            ],
        }


@pytest.fixture
async def delayed_browser(domain_client, monkeypatch):
    client, state = domain_client
    tokens = await login(client)
    ks = keystone._get_admin_ks_client()
    groups = {}
    members = {}
    for index in range(8):
        gid, pid = f"team-{index}", f"work-{index}"
        groups[gid] = {"id": gid, "name": gid, "description": "", "domain_id": "tenant-a", "enabled": True}
        members[gid] = {"user"}
        state.projects[pid] = {"id": pid, "name": pid, "domain_id": "tenant-a", "enabled": True}
        state.grants["user"].append(pid)
        state.assignments.append(
            {"group": {"id": gid}, "role": {"id": "reader-role"}, "scope": {"project": {"id": pid}}}
        )
    original = ks.role_assignments.list

    def assignments(**query):
        rows = original(**{key: value for key, value in query.items() if key != "user"})
        if query.get("effective"):
            rows = [
                {**{key: value for key, value in item.items() if key != "group"}, "user": {"id": uid}}
                for item in rows
                for uid in (members.get(item["group"]["id"], set()) if "group" in item else {item["user"]["id"]})
            ]
        if "user" in query:
            rows = [item for item in rows if item.get("user", {}).get("id") == query["user"]]
        return rows

    monkeypatch.setattr(ks.role_assignments, "list", assignments)
    monkeypatch.setattr(ks.groups, "get", lambda gid: groups[gid], raising=False)
    monkeypatch.setattr(ks.groups, "list", lambda domain=None, user=None: [] if user else list(groups.values()))
    original_users = ks.users.list
    monkeypatch.setattr(
        ks.users,
        "list",
        lambda group=None, **kwargs: (
            [state.users[uid] for uid in members[group]] if group else original_users(**kwargs)
        ),
    )
    # Keep the real trusted-catalog path, rather than the enclosing fixture's
    # precomputed catalog, so repeated standalone role graph reads are counted.
    monkeypatch.setattr(identity_roles, "_trusted_catalog", _trusted_catalog)
    recorder = Recorder(monkeypatch, ks)
    yield client, tokens, state, members, recorder


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/api/v1/auth/me", "/api/v1/projects/capabilities", "/api/v1/chat/conversations"])
async def test_endpoint_round_trip_benchmark(delayed_browser, monkeypatch, path):
    client, tokens, state, members, recorder = delayed_browser
    if path.startswith("/api/v1/chat/"):
        from fastapi.responses import JSONResponse

        from app.api.lumen import proxy as lumen_proxy

        async def proxy(service, request, upstream_path, **kwargs):
            await service_authorization.authorize_service_request(service, request, upstream_path)
            return JSONResponse([])

        monkeypatch.setattr(lumen_proxy, "proxy", proxy)
    started = time.perf_counter()
    response = await client.get(path, headers={"Authorization": "Bearer " + tokens["token"]})
    elapsed = time.perf_counter() - started
    assert response.status_code == 200, response.text
    print("AUTHORITY_BENCHMARK=" + json.dumps(recorder.report(path, elapsed), sort_keys=True))
    if os.environ.get("AUTHORITY_BENCHMARK"):
        return
    counts = Counter((label, args, query) for label, args, query, _ in recorder.calls)
    # These regressions guard physical I/O, not a projection of fake call totals.
    assert all(count == 1 for count in counts.values()), counts
    assert 2 <= recorder.peak <= 4
    assert len(recorder.calls) == 41
    if path == "/api/v1/projects/capabilities":
        assert response.json()["can_create_project"] is False
    if path == "/api/v1/auth/me":
        assert "_authority_operation" not in response.text


@pytest.mark.asyncio
async def test_second_browser_request_observes_group_membership_revocation(delayed_browser):
    client, tokens, state, members, recorder = delayed_browser
    # Remove the fixture's direct grants to these projects; only group evidence remains.
    state.grants["user"] = [pid for pid in state.grants["user"] if not pid.startswith("work-")]
    state.projects["only-group"] = {"id": "only-group", "name": "Group", "domain_id": "tenant-b", "enabled": True}
    state.assignments.append(
        {
            "group": {"id": "team-0"},
            "role": {"id": "reader-role"},
            "scope": {"project": {"id": "only-group"}},
        }
    )
    state.grants["user"] = [pid for pid in state.grants["user"] if pid != "foreign"]
    headers = {"Authorization": "Bearer " + tokens["token"]}
    before = await client.get("/api/v1/auth/me", headers=headers)
    assert before.status_code == 200, before.text
    assert "tenant-b" in {item["id"] for item in before.json()["available_domains"]}
    members["team-0"].clear()
    recorder.reset()
    after = await client.get("/api/v1/auth/me", headers=headers)
    assert after.status_code == 200, after.text
    assert "tenant-b" not in {item["id"] for item in after.json()["available_domains"]}
    assert any(
        label == "role_assignments.list" and dict(query) == {"effective": True, "user": "user"}
        for label, _, query, _ in recorder.calls
    )


@pytest.mark.parametrize("failure", ["group", "members", "projection", "disabled"])
def test_group_warmup_preserves_order_and_projection_skips(domain_native, monkeypatch, failure):
    n = domain_native
    for gid in ("first", "second", "third"):
        n.group_rows[gid] = row(id=gid, name=gid, description="", domain_id="home", enabled=gid != "third")
        n.members[gid] = {"creator"}
    n.raw = [grant("reader", group=gid, project="work-a") for gid in n.group_rows]
    if failure == "projection":
        n.group_rows["first"].name = "afterglow-default-managers-tenant-a"
    get, users = n.groups.get, n.users.list
    failed = []

    def group(gid):
        if failure == "group" and gid in {"first", "second"}:
            failed.append(gid)
            raise HTTPException(503, gid)
        return get(gid)

    def member_list(*, group=None, **kwargs):
        if failure == "members" and group in {"first", "second"}:
            failed.append(group)
            raise HTTPException(503, group)
        return users(group=group, **kwargs)

    monkeypatch.setattr(n.groups, "get", group)
    monkeypatch.setattr(n.users, "list", member_list)
    if failure in {"group", "members"}:
        with pytest.raises(HTTPException) as denied:
            domain_projects.accessible_domains("creator")
        assert denied.value.detail == "first"
        assert failed[-1] == "first", "ordered pass must reread first failed source"
    else:
        assert {d["id"] for d in domain_projects.accessible_domains("creator")} == {"home", "tenant-a"}
        counts = Counter(n.read_calls)
        if failure == "projection":
            assert counts[("group", "first")] == 1
            assert counts[("users.list", "first", None)] == 0
        # Keystone group rows have no normative enabled switch in this module.
        # Warming must preserve that existing behavior, not add a new policy.
        assert counts[("users.list", "third", None)] == 1


def test_two_credentials_never_share_identity_keyed_reads_after_gc():
    class Manager:
        def __init__(self, credential):
            self.credential = credential

        def get(self, object_id):
            return {"id": object_id, "credential": self.credential}

    with NativeOperation() as first, NativeOperation() as second:
        first._ks = SimpleNamespace(projects=Manager("credential-one"))
        second._ks = SimpleNamespace(projects=Manager("credential-two"))
        owner = weakref.ref(first.ks.projects)
        assert first.get("projects", "same")["credential"] == "credential-one"
        first._ks = None
        gc.collect()
        assert owner() is not None, "memo must retain manager until its read phase ends"
        assert second.get("projects", "same")["credential"] == "credential-two"
        # Even an explicitly replaced client in the same operation cannot collide.
        first._ks = SimpleNamespace(projects=Manager("credential-three"))
        assert first.get("projects", "same")["credential"] == "credential-three"
        first.invalidate()
        gc.collect()
        assert owner() is None


def test_catalog_identity_owner_remains_pinned_until_invalidation(domain_native):
    class Catalog(list):
        pass

    catalog = Catalog([])
    owner = weakref.ref(catalog)
    with NativeOperation() as operation:
        assert domain_projects._effective(domain_native, "work-a", catalog, operation=operation) == []
        del catalog
        gc.collect()
        assert owner() is not None
        operation.invalidate()
        gc.collect()
        assert owner() is None


@pytest.mark.asyncio
async def test_request_memo_does_not_survive_dependency_cleanup(delayed_browser, monkeypatch):
    client, tokens, _, _, _ = delayed_browser
    captured = []
    original = deps.request_native_operation

    def operation(request, principal):
        result = original(request, principal)
        if result is not None:
            captured.append(result)
        return result

    monkeypatch.setattr(deps, "request_native_operation", operation)
    response = await client.get("/api/v1/projects/capabilities", headers={"Authorization": "Bearer " + tokens["token"]})
    assert response.status_code == 200, response.text
    assert captured and captured[0]._ks is None and not captured[0].reads and not captured[0].subjects


def test_many_groups_scale_with_bounded_parallel_rounds(domain_native, monkeypatch):
    n = domain_native
    n.raw.clear()
    for index in range(12):
        gid, pid = f"group-{index}", f"project-{index}"
        n.group_rows[gid] = row(id=gid, name=gid, domain_id="home", description="")
        n.members[gid] = {"creator"}
        n.project_rows[pid] = row(id=pid, name=pid, domain_id="tenant-a", enabled=True, parent_id="tenant-a")
        n.raw.append(grant("reader", group=gid, project=pid))
    recorder = Recorder(monkeypatch, n, delay=0.02)
    started = time.perf_counter()
    parallel = domain_projects.accessible_domains("creator")
    elapsed = time.perf_counter() - started
    assert 2 <= recorder.peak <= 4
    # Twelve groups each need one exact GET and one membership list. They
    # overlap across projects: three two-read rounds, not twelve serial pairs.
    assert sum(label in {"groups.get", "users.list"} for label, *_ in recorder.calls) == 24
    assert recorder.group_finished - recorder.group_started < 24 * recorder.delay * 0.6
    recorder.reset()
    monkeypatch.setattr(domain_projects, "run_parallel", lambda *calls, **kwargs: [call() for call in calls])
    started = time.perf_counter()
    serial = domain_projects.accessible_domains("creator")
    serial_elapsed = time.perf_counter() - started
    assert serial == parallel
    assert elapsed < serial_elapsed * 0.7


@pytest.mark.asyncio
async def test_service_principal_rechecks_after_operation_invalidation(domain_native):
    from starlette.requests import Request

    from app.api.identity.auth import _domain_metadata_owner

    n = domain_native
    n.raw = [grant("reader", user="creator", project="work-a")]
    request = Request({"type": "http", "method": "GET", "path": "/api/v1/chat/conversations", "headers": []})
    info = {
        "user_id": "creator",
        "project_id": "work-a",
        "domain_id": "tenant-a",
        "identity_domain_id": "home",
        "token": "first",
        "is_system_admin": False,
    }
    async with NativeOperation() as operation:
        operation._ks = n
        request.state.token_info = info
        request.state._authority_operation = operation
        request.state._authority_owner = _domain_metadata_owner(info)
        assert deps.request_native_operation(request, info) is operation
        for key in ("user_id", "token", "project_id", "domain_id", "identity_domain_id"):
            assert deps.request_native_operation(request, {**info, key: "other"}) is None
        assert (await service_authorization.current_service_principal(request))["roles"] == ["reader"]
        n.raw.clear()
        operation.invalidate()
        with pytest.raises(HTTPException) as denied:
            await service_authorization.current_service_principal(request)
        assert denied.value.status_code == 403


def test_system_group_assignment_reads_share_four_way_warmup(domain_native, monkeypatch):
    from app.services import domain_scope

    n = domain_native
    for index in range(8):
        gid = f"system-group-{index}"
        n.group_rows[gid] = row(id=gid, name=gid, domain_id="home", description="")
        n.members[gid] = {"creator"}
    recorder = Recorder(monkeypatch, n, delay=0.02)
    started = time.perf_counter()
    with NativeOperation() as operation:
        assert not domain_scope.has_scope_authority("creator", operation=operation)
    elapsed = time.perf_counter() - started
    assert 2 <= recorder.peak <= 4
    assert len(recorder.calls) == 10
    assert elapsed < 10 * recorder.delay * 0.8


@pytest.mark.asyncio
async def test_direct_authenticated_ingestion_uses_plain_core(domain_client, monkeypatch):
    from unittest.mock import AsyncMock
    from uuid import uuid4

    from app.services import activity

    client, _ = domain_client
    tokens = await login(client)
    persist = AsyncMock()
    monkeypatch.setattr(activity, "record_interactions", persist)
    response = await client.post(
        "/api/v1/activity/interactions",
        json={
            "events": [
                {
                    "kind": "click",
                    "page": "/dashboard",
                    "control": "button",
                    "interaction_id": str(uuid4()),
                }
            ]
        },
        headers={"Authorization": "Bearer " + tokens["token"]},
    )
    assert response.status_code == 201, response.text
    assert response.json() == {"accepted": 1}
    assert persist.await_args.kwargs["actor"]["user_id"] == "user"
