"""Afterglow domain policy, stock API accounting and authenticated mutation behavior."""

import asyncio
import copy
import json
from contextlib import asynccontextmanager
from threading import Event, Lock
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import requests
from fastapi import FastAPI, HTTPException
from pydantic import ValidationError

from app.api.deps import get_admin_os_conn, require_admin, require_domain_manager
from app.api.identity.compute_pools import router
from app.models.compute_pools import PoolUpdate, ProjectLimitsUpdate
from app.services import compute_pools as pools
from app.services import domain_iam, flavor_automation_policy, gpu_inventory, identity_roles

GPU = "CUSTOM_PCI_10DE_2504"
AUDIO = "CUSTOM_PCI_10DE_228E"
ACTOR = {
    "user_id": "manager",
    "domain_id": "org",
    "identity_domain_id": "accounts",
    "is_domain_manager": True,
    "is_system_admin": True,
}


def policy(**updates):
    return {
        "schema": 1,
        "revision": 0,
        "enabled": True,
        "limits": {"CPU": 20, "MEMORY_MB": 65536, GPU: 4},
        "project_limits": {},
        **updates,
    }


def capability():
    gpu = {
        "name": "GA106",
        "resource_class": GPU,
        "classification_verified": True,
        "is_gpu": True,
        "is_audio": False,
    }
    companion = {
        "name": "GA106-audio",
        "resource_class": AUDIO,
        "classification_verified": True,
        "is_gpu": False,
        "is_audio": True,
    }
    return {
        "schema": 1,
        "policy_ready": True,
        "control_scope": "afterglow",
        "aliases": [gpu],
        "pci_aliases": [gpu, companion],
        "resource_kinds": {GPU: "gpu", AUDIO: "companion"},
        "gpu_profiles": [
            {
                "name": "3060lhr",
                "display_name": "3060 LHR",
                "resource_class": GPU,
                "resource_requirements": {GPU: 1, AUDIO: 1},
            }
        ],
        "unsupported_aliases": [],
    }


class NativeProvider:
    def __init__(self):
        self.domain = {"id": "org", "enabled": True, pools.POLICY_KEY: policy()}
        self.projects = [
            {"id": "p1", "name": "active", "enabled": True, "domain_id": "org"},
            {"id": "p2", "name": "disabled", "enabled": False, "domain_id": "org"},
        ]
        self.usages = {
            "p1": {"VCPU": 3, "PCPU": 2, "MEMORY_MB": 8192, GPU: 1, AUDIO: 1},
            "p2": {"PCPU": 4, "MEMORY_MB": 4096, GPU: 1},
        }
        self.capabilities = capability()
        self.calls = []
        self.patch_timeout = False
        self.ignore_patch = False
        self.list_links = {"next": None}
        self.list_flags = {}
        self.authorizations = 0
        self.exact_status = {}
        self.delete_timeout = False
        self.delete_observations = []
        self.conn = SimpleNamespace(
            identity=SimpleNamespace(get_endpoint_data=lambda: SimpleNamespace(url="https://native.invalid/v3")),
            compute=SimpleNamespace(get_endpoint=lambda: "https://nova.invalid/v2.1"),
            placement=SimpleNamespace(get_endpoint=lambda: "https://placement.invalid"),
            session=self,
            close=lambda: None,
        )

    def request(self, url, method, **kwargs):
        self.calls.append((method, url, kwargs))
        parsed = urlsplit(url)
        path = parsed.path
        status = 200
        if path == "/v3/domains/org":
            if method == "PATCH":
                if not self.ignore_patch:
                    self.domain[pools.POLICY_KEY] = copy.deepcopy(kwargs["json"]["domain"][pools.POLICY_KEY])
                if self.patch_timeout:
                    raise requests.Timeout("lost reply")
            body = {"domain": self.domain}
        elif path.startswith("/v3/projects/"):
            pid = path.rsplit("/", 1)[1]
            if method == "DELETE":
                self.delete_observations.append(copy.deepcopy(self.domain[pools.POLICY_KEY]))
                self.projects = [project for project in self.projects if project["id"] != pid]
                self.usages[pid] = {}
                if self.delete_timeout:
                    raise requests.Timeout("project deletion reply lost")
                status, body = 204, {}
            else:
                rows = [p for p in self.projects if p["id"] == pid]
                status = self.exact_status.get(pid, 200 if rows else 404)
                body = {"project": rows[0]} if rows and status == 200 else {}
        elif path == "/v3/projects":
            body = {"projects": self.projects, "links": self.list_links, **self.list_flags}
        elif path == "/usages":
            pid = parse_qs(parsed.query)["project_id"][0]
            body = {"usages": self.usages[pid]}
        else:
            status, body = 404, {}
        response = requests.Response()
        response.status_code = status
        response._content = json.dumps(body).encode()
        response._content_consumed = True
        return response


@pytest.fixture
def native(monkeypatch):
    provider = NativeProvider()
    provider.invalidated = []

    async def invalidate(key):
        provider.invalidated.append(key)

    monkeypatch.setattr("app.services.cache.invalidate", invalidate)

    async def capabilities():
        return copy.deepcopy(provider.capabilities)

    monkeypatch.setattr(flavor_automation_policy, "capabilities", capabilities)

    @asynccontextmanager
    async def operator():
        yield provider.conn

    lock = asyncio.Lock()

    @asynccontextmanager
    async def graph(_conn):
        async with lock:

            class Lease:
                async def assert_owned(self):
                    return None

            yield Lease()

    async def fresh_manager(info):
        provider.authorizations += 1
        if not info.get("is_domain_manager"):
            raise HTTPException(403, "manager_revoked")
        return {"domain_id": info["domain_id"], "is_domain_manager": True}

    async def fresh_admin(info):
        provider.authorizations += 1
        if not info.get("is_system_admin"):
            raise HTTPException(403, "admin_revoked")
        return info

    monkeypatch.setattr(pools, "_operator", operator)
    monkeypatch.setattr(identity_roles, "_graph_lock", graph)
    monkeypatch.setattr(domain_iam, "context", fresh_manager)
    monkeypatch.setattr("app.api.deps.require_admin", fresh_admin)
    return provider


@pytest.fixture
async def parallel_native(native, monkeypatch):
    """Independent sessions with a controllable provider read boundary."""
    loop = asyncio.get_running_loop()
    ready = asyncio.Event()
    release = Event()
    lock = Lock()
    state = SimpleNamespace(active=0, peak=0, sessions=[], completed=set(), ready=ready, release=release)
    native.projects = [
        {"id": f"p{i}", "name": f"project-{i}", "enabled": i != 8, "domain_id": "org"} for i in range(1, 10)
    ]
    native.usages = {p["id"]: {"VCPU": 1, "PCPU": 2, "MEMORY_MB": 1024, GPU: 1, AUDIO: 1} for p in native.projects}

    @asynccontextmanager
    async def operator():
        session = SimpleNamespace(active=False, closed=False)
        state.sessions.append(session)

        def request(url, method, **kwargs):
            if urlsplit(url).path != "/usages":
                return native.request(url, method, **kwargs)
            pid = parse_qs(urlsplit(url).query)["project_id"][0]
            with lock:
                assert not session.active and not session.closed
                session.active = True
                state.active += 1
                state.peak = max(state.peak, state.active)
                if state.active == 4:
                    loop.call_soon_threadsafe(ready.set)
            try:
                assert release.wait(5), "test did not release native reads"
                return native.request(url, method, **kwargs)
            finally:
                with lock:
                    session.active = False
                    state.active -= 1
                    state.completed.add(pid)

        connection = SimpleNamespace(
            identity=native.conn.identity,
            placement=native.conn.placement,
            session=SimpleNamespace(request=request),
        )
        try:
            yield connection
        finally:
            assert not session.active
            session.closed = True

    monkeypatch.setattr(pools, "_operator", operator)
    return state


@pytest.mark.asyncio
async def test_pool_usage_parallel_reads_are_bounded_complete_and_session_isolated(native, parallel_native):
    state = parallel_native
    task = asyncio.create_task(pools.read_pool(None, "org"))
    try:
        await asyncio.wait_for(state.ready.wait(), 3)
        assert not task.done()
        state.release.set()
        result = await task
    finally:
        state.release.set()
        await asyncio.gather(task, return_exceptions=True)
    assert result["usage"] == {"CPU": 27, "MEMORY_MB": 9216, GPU: 9}
    assert result["available"] == {"CPU": 0, "MEMORY_MB": 56320, GPU: 0}
    assert len(result["projects"]) == 9 and not result["projects"][7]["enabled"]
    assert state.peak == 4 and state.active == 0
    assert state.completed == {p["id"] for p in native.projects}
    assert all(session.closed for session in state.sessions)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["unknown_pci", "transport"])
async def test_pool_parallel_failure_never_returns_partial_usage(native, parallel_native, monkeypatch, failure):
    state = parallel_native
    if failure == "unknown_pci":
        native.usages["p1"]["CUSTOM_PCI_1234_ABCD"] = 1
        message = "gpu_accounting_unqualified"
    else:
        request = native.request

        def failing_request(url, method, **kwargs):
            if urlsplit(url).path == "/usages" and parse_qs(urlsplit(url).query)["project_id"] == ["p1"]:
                raise requests.Timeout("native read unavailable")
            return request(url, method, **kwargs)

        monkeypatch.setattr(native, "request", failing_request)
        message = "native_transport_unavailable"
    task = asyncio.create_task(pools.read_pool(None, "org"))
    try:
        await asyncio.wait_for(state.ready.wait(), 3)
        state.release.set()
        with pytest.raises(pools.ComputePoolUnavailable, match=message):
            await task
    finally:
        state.release.set()
        await asyncio.gather(task, return_exceptions=True)
    assert state.completed == {p["id"] for p in native.projects}
    assert state.active == 0 and all(session.closed for session in state.sessions)


@pytest.mark.asyncio
async def test_pool_cancellation_drains_native_reads_before_closing_sessions(native, parallel_native):
    state = parallel_native
    task = asyncio.create_task(pools.read_pool(None, "org"))
    try:
        await asyncio.wait_for(state.ready.wait(), 3)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        assert not any(session.closed for session in state.sessions)
        state.release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        state.release.set()
        await asyncio.gather(task, return_exceptions=True)
    assert state.completed == {p["id"] for p in native.projects}
    assert state.active == 0 and all(session.closed for session in state.sessions)


@pytest.mark.parametrize(
    "body",
    [
        {"revision": True, "enabled": True, "limits": {}},
        {"revision": 0, "enabled": "true", "limits": {}},
        {"revision": 0, "enabled": True, "limits": {"CPU": True}},
        {"revision": 0, "enabled": True, "limits": {"CPU": "4"}},
        {"revision": 0, "enabled": True, "limits": {"CPU": -2}},
        {"revision": 0, "enabled": True, "limits": {"CPU": 2**31}},
        {"revision": 0, "enabled": True, "limits": {"VCPU": 4}},
        {"revision": 0, "enabled": True, "limits": {"VGPU": 1}},
        {"revision": 0, "enabled": True, "limits": {}, "project_limits": {}},
    ],
)
def test_request_bodies_forbid_coercion_unknown_fields_and_unbounded_limits(body):
    with pytest.raises(ValidationError):
        PoolUpdate.model_validate(body)
    with pytest.raises(ValidationError):
        ProjectLimitsUpdate.model_validate({"revision": 0, "limits": {}, "enabled": True})


def test_native_policy_is_strict_and_immutable(native):
    raw = policy(project_limits={"p1": {"CPU": 7}})
    normalized = pools.normalize_policy(raw)
    normalized["project_limits"]["p1"]["CPU"] = 1
    assert raw["project_limits"]["p1"]["CPU"] == 7
    assert pools.parse_domain_policy(SimpleNamespace(_info={pools.POLICY_KEY: raw}))["schema"] == 1
    for invalid in [
        policy(schema=True),
        policy(extra=1),
        policy(project_limits={"p1": {"CPU": 21}}),
        policy(project_limits={"p1": {GPU: -1}}),
        policy(project_limits={"/wrong": {"CPU": 1}}),
    ]:
        with pytest.raises(pools.ComputePoolUnavailable):
            pools.normalize_policy(invalid)


@pytest.mark.asyncio
async def test_usage_aggregates_vcpu_pcpu_and_disabled_projects_without_audio(native):
    result = await pools.read_pool(object(), "org")
    assert result["usage"] == {"CPU": 9, "MEMORY_MB": 12288, GPU: 2}
    assert result["available"] == {"CPU": 11, "MEMORY_MB": 53248, GPU: 2}
    assert [p["enabled"] for p in result["projects"]] == [True, False]
    assert result["policy_ready"] is True and result["control_scope"] == "afterglow"
    assert result["gpu_profiles"][0]["name"] == "3060lhr"
    assert not any("os-domain-compute" in url for _, url, _ in native.calls)
    assert {
        parse_qs(urlsplit(url).query)["project_id"][0]
        for method, url, _ in native.calls
        if urlsplit(url).path == "/usages"
    } == {"p1", "p2"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "corruption",
    [
        "wrong_domain",
        "duplicate",
        "enabled_string",
        "usage_bool",
        "usage_missing",
        "usage_vgpu",
        "missing_next",
        "external_next",
        "wrong_exact",
        "truncated",
        "limited",
        "first_page_previous",
    ],
)
async def test_incomplete_wrong_identity_and_malformed_usage_fail_closed(native, corruption):
    if corruption == "wrong_domain":
        native.projects[1]["domain_id"] = "foreign"
    elif corruption == "duplicate":
        native.projects.append(copy.deepcopy(native.projects[0]))
    elif corruption == "enabled_string":
        native.projects[1]["enabled"] = "false"
    elif corruption == "usage_bool":
        native.usages["p2"]["VCPU"] = True
    elif corruption == "usage_missing":
        native.usages["p2"] = None
    elif corruption == "usage_vgpu":
        native.usages["p2"]["VGPU"] = 1
    elif corruption == "missing_next":
        native.list_links = {}
    elif corruption == "external_next":
        native.list_links = {"next": "https://attacker.invalid/projects"}
    elif corruption in {"truncated", "limited"}:
        native.list_flags = {corruption: True}
    elif corruption == "first_page_previous":
        native.list_links = {"next": None, "previous": "https://native.invalid/v3/projects?marker=hidden"}
    else:
        native.domain["id"] = "wrong"
    with pytest.raises(pools.ComputePoolUnavailable):
        await pools.read_pool(None, "org")
    assert all("attacker" not in url for _, url, _ in native.calls)


@pytest.mark.asyncio
async def test_single_snapshot_cpu_gpu_share_policy_project_caps_are_not_allocations(native):
    native.domain[pools.POLICY_KEY]["project_limits"] = {"p1": {"CPU": 7, GPU: 1}, "p2": {"CPU": 20}}
    snapshot = await pools.project_pool_snapshot(None, "p1")
    before_calls = len(native.calls)
    result = pools.evaluate_pool_snapshot(snapshot, {"VCPU": 3, GPU: 1})
    assert result["selectable"] is False
    assert {b["resource"] for b in result["blockers"]} == {"CPU", GPU}
    assert all(b["code"] == "project_pool_ceiling_exhausted" for b in result["blockers"])
    assert pools.evaluate_pool_snapshot(snapshot, {"CPU": 2})["selectable"] is True
    assert pools.evaluate_pool_snapshot(snapshot, {GPU: 1}, {GPU: 1})["selectable"] is True
    assert len(native.calls) == before_calls


@pytest.mark.asyncio
async def test_missing_pool_resource_zero_unlimited_and_unmanaged_legacy(native):
    native.domain[pools.POLICY_KEY]["limits"] = {"CPU": -1}
    snapshot = await pools.project_pool_snapshot(None, "p1")
    assert snapshot["available"]["CPU"] == -1
    assert pools.evaluate_pool_snapshot(snapshot, {"CPU": 1000})["selectable"] is True
    assert pools.evaluate_pool_snapshot(snapshot, {GPU: 1})["blockers"][0]["available"] == 0
    native.domain.pop(pools.POLICY_KEY)
    native.calls.clear()
    assert (await pools.evaluate_project_pool(None, "p1", {"VGPU": 1}))["enabled"] is False
    assert not any(urlsplit(url).path == "/usages" for _, url, _ in native.calls)


@pytest.mark.asyncio
async def test_explicit_disabled_policy_pauses_afterglow_admission_not_native_allocations(native):
    native.domain[pools.POLICY_KEY]["enabled"] = False
    snapshot = await pools.project_pool_snapshot(None, "p1")
    assert snapshot["state"] == "paused"
    assert pools.domain_pool_state(native.domain) == "paused"
    result = pools.evaluate_pool_snapshot(snapshot, {"CPU": 1})
    assert result["selectable"] is False
    assert result["blockers"][0]["code"] == "domain_pool_paused"
    with pytest.raises(pools.ComputePoolDenied):
        await pools.require_project_pool(None, "p1", {"CPU": 1})
    native.domain.pop(pools.POLICY_KEY)
    assert pools.domain_pool_state(native.domain) == "unmanaged"
    native.domain[pools.POLICY_KEY] = None
    with pytest.raises(pools.ComputePoolUnavailable):
        pools.domain_pool_state(native.domain)


@pytest.mark.asyncio
async def test_manager_cannot_implicitly_create_or_pause_unmanaged_domain(native):
    native.domain.pop(pools.POLICY_KEY)
    with pytest.raises(HTTPException) as caught:
        await pools.update_project_limits(None, "org", "p1", 0, {"CPU": 1}, token_info=ACTOR)
    assert caught.value.status_code == 409
    assert caught.value.detail == "compute_pool_not_configured"
    assert not any(method == "PATCH" for method, _, _ in native.calls)


@pytest.mark.asyncio
async def test_unready_afterglow_policy_never_permits_admission_or_metadata_writes(native):
    native.capabilities["policy_ready"] = False
    assert (await pools.read_pool(None, "org"))["policy_ready"] is False
    with pytest.raises(pools.ComputePoolUnavailable, match="policy_unavailable"):
        await pools.require_project_pool(None, "p1", {"CPU": 1})
    for enabled in (True, False):
        with pytest.raises(HTTPException) as caught:
            await pools.update_pool(None, "org", 0, enabled, {"CPU": 20}, token_info=ACTOR)
        assert caught.value.status_code == 409
    with pytest.raises(HTTPException) as caught:
        await pools.update_project_limits(None, "org", "p1", 0, {"CPU": 1}, token_info=ACTOR)
    assert caught.value.status_code == 409
    assert not any(method == "PATCH" for method, _, _ in native.calls)


@pytest.mark.asyncio
async def test_flavor_demands_exact_approved_alias_companions_and_explicit_resources(native):
    snapshot = await pools.project_pool_snapshot(None, "p1")
    flavor = {
        "vcpus": 4,
        "ram": 8192,
        "extra_specs": {
            "pci_passthrough:alias": "GA106:2,GA106-audio:2",
            "resources:PCPU": "6",
            "resources:MEMORY_MB": "16384",
        },
    }
    assert await pools.flavor_pool_requirements(None, flavor, 2, snapshot=snapshot) == {
        "CPU": 12,
        "MEMORY_MB": 32768,
        GPU: 4,
    }
    for specs in [
        {"pci_passthrough:alias": "unknown:1"},
        {"resources1:VGPU": "1"},
        {"hw:cpu_policy": "dedicated", "hw:emulator_threads_policy": "isolate"},
        {"hw:cpu_policy": "mixed"},
        {"resources:VGPU": "1"},
        {"resources:CUSTOM_GPU_CARD": "1"},
        {"pci_passthrough:alias": "GA106:1", "resources:" + GPU: "2"},
    ]:
        with pytest.raises(pools.ComputePoolUnavailable):
            await pools.flavor_pool_requirements(None, {**flavor, "extra_specs": specs}, snapshot=snapshot)


@pytest.mark.asyncio
async def test_fresh_manager_exact_domain_and_project_are_rechecked_under_lease(native):
    with pytest.raises(HTTPException) as caught:
        await pools.update_project_limits(None, "org", "p1", 0, {"CPU": 5}, token_info={**ACTOR, "domain_id": "other"})
    assert caught.value.status_code == 403
    with pytest.raises(HTTPException) as caught:
        await pools.update_project_limits(
            None, "org", "p1", 0, {"CPU": 5}, token_info={**ACTOR, "is_domain_manager": False}
        )
    assert caught.value.status_code == 403
    native.projects[0]["domain_id"] = "other"
    with pytest.raises(pools.ComputePoolUnavailable):
        await pools.update_project_limits(None, "org", "p1", 0, {"CPU": 5}, token_info=ACTOR)
    assert not any(method == "PATCH" for method, _, _ in native.calls)


@pytest.mark.asyncio
async def test_project_cap_ceiling_pool_lowering_and_explicit_removal(native):
    result = await pools.update_project_limits(None, "org", "p1", 0, {"CPU": 7}, token_info=ACTOR)
    assert result["revision"] == 1 and result["project_limits"] == {"p1": {"CPU": 7}}
    with pytest.raises(HTTPException) as caught:
        await pools.update_pool(None, "org", 1, True, {"CPU": 6}, token_info=ACTOR)
    assert caught.value.status_code == 422
    result = await pools.delete_project_limits(None, "org", "p1", 1, token_info=ACTOR)
    assert result["revision"] == 2 and result["project_limits"] == {}
    result = await pools.update_pool(None, "org", 2, True, {"CPU": 6}, token_info=ACTOR)
    assert result["revision"] == 3 and result["limits"] == {"CPU": 6}
    assert native.authorizations >= 6


@pytest.mark.asyncio
async def test_simultaneous_revision_updates_have_one_winner(native):
    results = await asyncio.gather(
        pools.update_project_limits(None, "org", "p1", 0, {"CPU": 7}, token_info=ACTOR),
        pools.update_project_limits(None, "org", "p1", 0, {"CPU": 8}, token_info=ACTOR),
        return_exceptions=True,
    )
    assert sum(isinstance(result, dict) for result in results) == 1
    conflicts = [result for result in results if isinstance(result, HTTPException)]
    assert len(conflicts) == 1 and conflicts[0].status_code == 409
    assert sum(method == "PATCH" for method, _, _ in native.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("lost_reply", [True, False])
async def test_timeout_and_failed_exact_readback_are_unknown_never_retried(native, lost_reply):
    native.patch_timeout = lost_reply
    native.ignore_patch = not lost_reply
    with pytest.raises(HTTPException) as caught:
        await pools.update_project_limits(None, "org", "p1", 0, {"CPU": 7}, token_info=ACTOR)
    assert caught.value.status_code == 503
    assert caught.value.detail == "compute_pool_mutation_outcome_unknown"
    assert sum(method == "PATCH" for method, _, _ in native.calls) == 1
    assert native.domain[pools.POLICY_KEY]["revision"] == (1 if lost_reply else 0)


@pytest.fixture
def api(native):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[require_admin] = lambda: dict(ACTOR)
    app.dependency_overrides[require_domain_manager] = lambda: dict(ACTOR)
    app.dependency_overrides[get_admin_os_conn] = lambda: native.conn
    return app


@pytest.mark.asyncio
async def test_real_routes_strict_bodies_full_snapshots_conflicts_and_no_store(api, native):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api), base_url="http://test") as client:
        response = await client.get("/api/v1/admin/domains/org/compute-pool")
        assert response.status_code == 200 and response.json()["usage"]["CPU"] == 9
        assert "no-store" in response.headers["cache-control"]
        response = await client.put("/api/v1/iam/compute-pool/projects/p1", json={"revision": 0, "limits": {"CPU": 7}})
        assert response.status_code == 200 and response.json()["revision"] == 1
        assert response.json()["usage"] == {"CPU": 9, "MEMORY_MB": 12288, GPU: 2}
        assert response.json()["project_limits"] == {"p1": {"CPU": 7}}
        response = await client.put("/api/v1/iam/compute-pool/projects/p1", json={"revision": 0, "limits": {"CPU": 8}})
        assert response.status_code == 409
        response = await client.delete("/api/v1/iam/compute-pool/projects/p1?revision=1")
        assert response.status_code == 200 and response.json()["project_limits"] == {}
        response = await client.put(
            "/api/v1/admin/domains/org/compute-pool",
            json={"revision": 2, "enabled": True, "limits": {"CPU": 24, "MEMORY_MB": 65536, GPU: 4}},
        )
        assert response.status_code == 200 and response.json()["revision"] == 3
        assert response.json()["usage"] == {"CPU": 9, "MEMORY_MB": 12288, GPU: 2}
        assert response.json()["available"]["CPU"] == 15
        response = await client.put(
            "/api/v1/admin/domains/org/compute-pool", json={"revision": 2, "enabled": True, "limits": {"CPU": True}}
        )
        assert response.status_code == 422
        response = await client.delete("/api/v1/iam/compute-pool/projects/p1")
        assert response.status_code == 422
        response = await client.put(
            "/api/v1/iam/compute-pool/projects/p1", json={"revision": 2, "limits": {}, "domain_id": "other"}
        )
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_admin_and_manager_guards_cannot_be_replaced_by_body_flags(api, native):
    async def denied():
        raise HTTPException(403, "not_current_manager")

    api.dependency_overrides[require_domain_manager] = denied
    api.dependency_overrides[require_admin] = denied
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api), base_url="http://test") as client:
        assert (await client.get("/api/v1/iam/compute-pool")).status_code == 403
        assert (await client.get("/api/v1/admin/domains/org/compute-pool")).status_code == 403
        assert (
            await client.put(
                "/api/v1/admin/domains/org/compute-pool", json={"revision": 0, "enabled": False, "limits": {}}
            )
        ).status_code == 403
    assert not any(method == "PATCH" for method, _, _ in native.calls)


class HeldLease:
    async def assert_owned(self):
        return None


@pytest.mark.asyncio
async def test_stale_caps_are_visible_but_admission_stays_fail_closed(native):
    native.domain[pools.POLICY_KEY]["project_limits"] = {"deleted": {"CPU": 3}}
    result = await pools.read_pool(None, "org")
    assert result["revision"] == 0
    assert result["stale_project_caps"] == ["deleted"]
    assert result["projection_unavailable"] is True
    assert result["usage"] == result["available"] == {}
    assert result["policy_ready"] is False and result["control_scope"] == "afterglow"
    with pytest.raises(pools.ComputePoolUnavailable, match="directory_mismatch"):
        await pools.project_pool_snapshot(None, "p1")


@pytest.mark.asyncio
async def test_deleted_cap_cleanup_requires_positive_absence_then_monotonic_readback(native):
    native.domain[pools.POLICY_KEY]["project_limits"] = {"p1": {"CPU": 7}, "p2": {"CPU": 5}}
    lease = HeldLease()
    with pytest.raises(HTTPException):
        await pools.cleanup_deleted_project_limits("org", "p1", lease=lease)
    assert not any(method == "PATCH" for method, _, _ in native.calls)
    native.request("https://native.invalid/v3/projects/p1", "DELETE")
    result = await pools.cleanup_deleted_project_limits("org", "p1", lease=lease)
    assert result == {"domain_id": "org", "project_id": "p1", "revision": 1, "changed": True}
    assert native.delete_observations[0]["project_limits"]["p1"] == {"CPU": 7}
    assert native.domain[pools.POLICY_KEY]["project_limits"] == {"p2": {"CPU": 5}}
    assert (await pools.read_pool(None, "org"))["usage"]["CPU"] == 4


@pytest.mark.asyncio
async def test_recover_multiple_deleted_caps_one_exact_target_at_a_time(native):
    native.domain[pools.POLICY_KEY]["project_limits"] = {"gone1": {"CPU": 7}, "gone2": {"CPU": 5}}
    native.usages.update(gone1={}, gone2={})
    first = await pools.delete_project_limits(None, "org", "gone1", 0, token_info=ACTOR)
    assert first["revision"] == 1 and first["stale_project_caps"] == ["gone2"]
    assert first["usage"] == first["available"] == {}
    second = await pools.delete_project_limits(None, "org", "gone2", 1, token_info=ACTOR)
    assert second["revision"] == 2 and second["project_limits"] == {}
    assert second["policy_ready"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", ["native403", "native503", "directory_present", "usage_nonzero", "usage_malformed", "moved"]
)
async def test_stale_cap_recovery_never_ignores_unknown_or_moved_principal(native, failure):
    native.domain[pools.POLICY_KEY]["project_limits"] = {"gone": {"CPU": 7}}
    native.usages["gone"] = {}
    if failure.startswith("native"):
        native.exact_status["gone"] = int(failure.removeprefix("native"))
    elif failure == "directory_present":
        native.projects.append({"id": "gone", "name": "gone", "domain_id": "org", "enabled": True})
        native.exact_status["gone"] = 404
    elif failure == "usage_nonzero":
        native.usages["gone"] = {"DISK_GB": 1}
    elif failure == "usage_malformed":
        native.usages["gone"] = {"DISK_GB": False}
    else:
        native.projects.append({"id": "gone", "name": "moved", "domain_id": "foreign", "enabled": True})
    with pytest.raises((pools.ComputePoolUnavailable, HTTPException)):
        await pools.delete_project_limits(None, "org", "gone", 0, token_info=ACTOR)
    assert native.domain[pools.POLICY_KEY]["project_limits"] == {"gone": {"CPU": 7}}
    assert not any(method == "PATCH" for method, _, _ in native.calls)


@pytest.mark.asyncio
async def test_approved_classification_accepts_new_gpu_without_local_display_catalog(native, monkeypatch):
    resource = "CUSTOM_PCI_ABCD_0123"
    monkeypatch.setattr(gpu_inventory, "PCI_DEVICE_MAP", {})
    native.capabilities["aliases"] = [
        {
            "name": "new-gpu",
            "resource_class": resource,
            "vendor_id": "abcd",
            "product_id": "0123",
            "classification_verified": True,
            "is_gpu": True,
            "is_audio": False,
        }
    ]
    native.capabilities["pci_aliases"] = copy.deepcopy(native.capabilities["aliases"])
    native.capabilities["resource_kinds"] = {resource: "gpu"}
    native.domain[pools.POLICY_KEY]["limits"] = {"CPU": 20, "MEMORY_MB": 65536, resource: 3}
    native.usages = {"p1": {"VCPU": 2, resource: 1}, "p2": {}}
    snapshot = await pools.project_pool_snapshot(None, "p1")
    assert snapshot["usage"][resource] == 1
    assert pools.evaluate_pool_snapshot(snapshot, {resource: 1})["selectable"] is True
    flavor = {"vcpus": 2, "ram": 4096, "extra_specs": {"pci_passthrough:alias": "new-gpu:1"}}
    assert (await pools.flavor_pool_requirements(None, flavor, snapshot=snapshot))[resource] == 1


@pytest.mark.asyncio
async def test_audio_budget_and_unclassified_custom_usage_fail_closed(native):
    assert pools.normalize_policy(policy(limits={AUDIO: 1}))["limits"] == {AUDIO: 1}
    with pytest.raises(HTTPException) as caught:
        await pools.update_pool(None, "org", 0, True, {AUDIO: 1}, token_info=ACTOR)
    assert caught.value.detail == "compute_pool_gpu_alias_unverified"
    native.usages["p1"]["CUSTOM_NETWORK_DEVICE"] = 1
    with pytest.raises(pools.ComputePoolUnavailable, match="unsupported"):
        await pools.read_pool(None, "org")


@pytest.mark.asyncio
async def test_approved_companion_does_not_depend_on_local_catalog(native, monkeypatch):
    monkeypatch.setattr(gpu_inventory, "PCI_DEVICE_MAP", {})
    snapshot = await pools.project_pool_snapshot(None, "p1")
    assert [row["name"] for row in snapshot["_pci_aliases"] if row["is_audio"]] == ["GA106-audio"]
    demand = await pools.flavor_pool_requirements(
        None,
        {"vcpus": 2, "ram": 4096, "extra_specs": {"pci_passthrough:alias": "GA106:1,GA106-audio:1"}},
        snapshot=snapshot,
    )
    assert demand == {"CPU": 2, "MEMORY_MB": 4096, GPU: 1}


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["manager", "admin", "admin_child"])
@pytest.mark.parametrize("unknown_delete", [False, True])
async def test_project_deletion_cleans_cap_only_after_confirmed_native_delete(
    native, monkeypatch, path, unknown_delete
):
    from app.api.identity import admin_identity
    from app.services import domain_projects, domain_scope, project_ownership_journal, project_service

    native.domain[pools.POLICY_KEY]["project_limits"] = {"p1": {"CPU": 7}}
    native.usages["p1"] = {}
    native.delete_timeout = unknown_delete
    lease = HeldLease()

    async def noop(*args, **kwargs):
        return None

    async def check(*args, **kwargs):
        return {"can_delete": True, "resources": []}

    async def forbidden_nested_lock(*args, **kwargs):
        raise AssertionError("cleanup must not recursively acquire graph lease")

    def project(*args, **kwargs):
        return SimpleNamespace(id="p1", domain_id="org", parent_id="parent")

    def delete(project_id, **kwargs):
        return native.request("https://native.invalid/v3/projects/" + project_id, "DELETE")

    @asynccontextmanager
    async def membership_write(project_id):
        yield lease, SimpleNamespace(projects=SimpleNamespace(get=project, delete=delete)), {}, [], []

    monkeypatch.setattr(identity_roles, "_graph_lock", forbidden_nested_lock)
    monkeypatch.setattr(domain_projects, "assert_default_immutable", lambda *args, **kwargs: None)
    monkeypatch.setattr(domain_scope, "invalidate_authority", noop)
    monkeypatch.setattr(project_service, "invalidate_project_lists", noop)
    monkeypatch.setattr(project_service, "_membership_write", membership_write)
    monkeypatch.setattr(project_service, "project_deletion_check", check)
    monkeypatch.setattr(project_service, "project_ownership", check)
    monkeypatch.setattr(admin_identity, "_native_object", project)
    monkeypatch.setattr(
        admin_identity, "_project_deletion_inventory", lambda *args: {"can_delete": True, "resources": []}
    )
    monkeypatch.setattr(admin_identity, "invalidate_authority", noop)
    monkeypatch.setattr(admin_identity, "invalidate", noop)
    monkeypatch.setattr(project_ownership_journal, "assert_resolved", noop)
    monkeypatch.setattr(native.conn.identity, "delete_project", delete, raising=False)
    monkeypatch.setattr(admin_identity.project_cleanup, "delete_project_native", lambda proxy, pid: delete(pid))
    if path == "manager":
        operation = project_service.delete_empty_project("p1", ACTOR)
    else:
        operation = admin_identity._delete_project_under_lease(
            native.conn,
            native.conn,
            "p1",
            lease,
            **({"expected_parent": "parent", "expected_domain": "org"} if path == "admin_child" else {}),
        )
    if unknown_delete:
        with pytest.raises(HTTPException):
            await operation
        assert native.domain[pools.POLICY_KEY]["project_limits"] == {"p1": {"CPU": 7}}
        assert not any(method == "PATCH" for method, _, _ in native.calls)
    else:
        await operation
        assert native.domain[pools.POLICY_KEY]["revision"] == 1
        assert native.domain[pools.POLICY_KEY]["project_limits"] == {}
    assert native.delete_observations[0]["project_limits"] == {"p1": {"CPU": 7}}
    writes = [method for method, _, _ in native.calls if method != "GET"]
    assert writes == (["DELETE"] if unknown_delete else ["DELETE", "PATCH"])


@pytest.mark.asyncio
async def test_public_policy_snapshot_and_stale_cap_delete_recovery(api, native):
    native.domain[pools.POLICY_KEY]["project_limits"] = {"gone": {"CPU": 3}}
    native.usages["gone"] = {"DISK_GB": 1}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api), base_url="http://test") as client:
        response = await client.get("/api/v1/iam/compute-pool")
        assert response.status_code == 200
        assert response.json()["stale_project_caps"] == ["gone"]
        assert response.json()["projection_unavailable"] is True
        assert "no-store" in response.headers["cache-control"]
        response = await client.delete("/api/v1/iam/compute-pool/projects/gone?revision=0")
        assert response.status_code == 503
        assert native.domain[pools.POLICY_KEY]["project_limits"] == {"gone": {"CPU": 3}}
        native.usages["gone"] = {}
        response = await client.delete("/api/v1/iam/compute-pool/projects/gone?revision=0")
        assert response.status_code == 200 and response.json()["revision"] == 1
        assert response.json()["project_limits"] == {}


@pytest.mark.asyncio
async def test_gpu_only_domain_allocation_keeps_native_cpu_ram_authority(native):
    native.domain[pools.POLICY_KEY]["limits"] = {GPU: 4}
    snapshot = await pools.project_pool_snapshot(None, "p1")
    assert snapshot["available"]["CPU"] == snapshot["available"]["MEMORY_MB"] == -1
    assert pools.evaluate_pool_snapshot(snapshot, {"CPU": 100, "MEMORY_MB": 262144, GPU: 1})["selectable"]
    native.domain[pools.POLICY_KEY]["limits"]["CPU"] = 0
    snapshot = await pools.project_pool_snapshot(None, "p1")
    assert not pools.evaluate_pool_snapshot(snapshot, {"CPU": 1, GPU: 1})["selectable"]


@pytest.mark.asyncio
@pytest.mark.parametrize("overlap", [GPU, AUDIO])
async def test_alias_resource_overlap_is_rejected_even_when_counts_match(native, overlap):
    snapshot = await pools.project_pool_snapshot(None, "p1")
    flavor = {
        "vcpus": 4,
        "ram": 8192,
        "extra_specs": {
            "resourcescard:" + overlap: "2",
            "pci_passthrough:alias": "GA106:2,GA106-audio:2",
        },
    }
    with pytest.raises(pools.ComputePoolUnavailable, match="contradiction"):
        await pools.flavor_pool_requirements(None, flavor, snapshot=snapshot)


@pytest.mark.asyncio
async def test_disjoint_alias_and_grouped_companion_resources_keep_exact_gpu_demand(native):
    snapshot = await pools.project_pool_snapshot(None, "p1")
    demand = await pools.flavor_pool_requirements(
        None,
        {
            "vcpus": 4,
            "ram": 8192,
            "extra_specs": {
                "resourcesaudio:" + AUDIO: "2",
                "pci_passthrough:alias": "GA106:2",
            },
        },
        snapshot=snapshot,
    )
    assert demand == {"CPU": 4, "MEMORY_MB": 8192, GPU: 2}


@pytest.mark.asyncio
async def test_unapproved_gpu_accounting_blocks_policy_writes(native):
    native.usages["p1"]["CUSTOM_PCI_ABCD_0001"] = 1
    with pytest.raises(pools.ComputePoolUnavailable, match="accounting"):
        await pools.update_pool(None, "org", 0, True, {GPU: 4}, token_info=ACTOR)
    assert not any(method == "PATCH" for method, _, _ in native.calls)


@pytest.mark.asyncio
async def test_gpu_only_domain_accepts_optional_finite_cpu_ram_project_caps(native):
    native.domain[pools.POLICY_KEY]["limits"] = {GPU: 4}
    result = await pools.update_project_limits(None, "org", "p1", 0, {"CPU": 6, "MEMORY_MB": 12288}, token_info=ACTOR)
    assert result["project_limits"]["p1"] == {"CPU": 6, "MEMORY_MB": 12288}
    snapshot = await pools.project_pool_snapshot(None, "p1")
    assert snapshot["project_available"]["CPU"] == 1
    assert not pools.evaluate_pool_snapshot(snapshot, {"CPU": 2, GPU: 1})["selectable"]


@pytest.mark.asyncio
async def test_resource_only_profile_display_name_never_authorizes_pci_alias(native):
    native.capabilities["pci_aliases"][0]["display_only"] = True
    snapshot = await pools.project_pool_snapshot(None, "p1")
    flavor = {"vcpus": 2, "ram": 4096, "extra_specs": {"resources:" + GPU: "1"}}
    assert (await pools.flavor_pool_requirements(None, flavor, snapshot=snapshot))[GPU] == 1
    flavor["extra_specs"] = {"pci_passthrough:alias": "GA106:1"}
    with pytest.raises(pools.ComputePoolUnavailable, match="alias_unverified"):
        await pools.flavor_pool_requirements(None, flavor, snapshot=snapshot)


@pytest.mark.asyncio
@pytest.mark.parametrize("resource", ["VCPU", "PCPU", "MEMORY_MB"])
async def test_numbered_cpu_ram_groups_cannot_replace_base_flavor_accounting(native, resource):
    snapshot = await pools.project_pool_snapshot(None, "p1")
    flavor = {"vcpus": 4, "ram": 8192, "extra_specs": {"resourcesextra:" + resource: "1"}}
    with pytest.raises(pools.ComputePoolUnavailable, match="grouped_base_resources_unsupported"):
        await pools.flavor_pool_requirements(None, flavor, snapshot=snapshot)
