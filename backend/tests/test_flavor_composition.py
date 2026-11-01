"""Composer uses the real eligibility/capacity engine and narrow native publisher."""

import asyncio
import copy
import threading
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.models.compute import FlavorCapacityInfo, FlavorDemandInfo, FlavorEligibility, FlavorRemainingInfo
from app.models.flavor_composition import FlavorComposition
from app.services import flavor_capacity, flavor_eligibility, managed_flavors
from app.services import flavor_composition as svc
from tests.test_flavor_capacity import CPU_SHAPE, HOST_NAMES, ONE, ROOT_A, ROOT_B, ZONE, allocation
from tests.test_flavor_capacity import cloud as cloud
from tests.test_identity_graph_wait import graph_env as graph_env
from tests.test_managed_flavors import AUDIO, host, profile
from tests.test_managed_flavors import _graph_lock as real_graph_lock
from tests.test_managed_flavors import environment as environment

_authorize = svc._authorize


def request(**values):
    return FlavorComposition(vcpus=values.pop("vcpus", 2), ram_mb=values.pop("ram_mb", 4096), **values)


def variant(snapshot, profile_id=None, count=0):
    return next(row for row in snapshot.variants if row.gpu_profile_id == profile_id and row.gpu_count == count)


def fits(row, cpu, ram):
    return any(
        all(
            region.model_dump()[key]["min"] <= amount <= region.model_dump()[key]["max"]
            and amount % region.model_dump()[key]["step"] == 0
            for key, amount in (("vcpus", cpu), ("ram_mb", ram))
        )
        for region in row.regions
    )


def eligible(flavor):
    return flavor.model_copy(
        update={
            "eligibility": FlavorEligibility(
                selectable=True,
                requirements=FlavorDemandInfo(instances=1, cores=flavor.vcpus, ram_mb=flavor.ram),
                remaining=FlavorRemainingInfo(instances=10, cores=128, ram_mb=2097152),
                capacity=FlavorCapacityInfo(status="available", checked_at="2026-10-31T00:00:00+00:00"),
            )
        }
    )


@pytest.fixture
def composition_native(environment, monkeypatch):
    env = environment
    env.policy["hosts"] = [host(cpu=128, ram=2097152, gpu=16, audio=16)]
    env.inventory["hosts"] = copy.deepcopy(env.policy["hosts"])
    caller = SimpleNamespace(compute=SimpleNamespace())
    executor = SimpleNamespace(compute=env.compute)
    authorizations = []

    async def authorize(*args, **kwargs):
        authorizations.append(kwargs)
        return ("stable",)

    @asynccontextmanager
    async def operator(project_id, info):
        assert project_id == "p1"
        yield executor

    async def evaluate(conn, project_id, flavors, zone):
        assert conn is caller  # operator credentials never replace target quota/visibility
        return [eligible(flavor) for flavor in flavors]

    def visible(conn):
        assert conn is caller
        return [
            svc._flavor({**vars(row), "extra_specs": env.compute.specs[fid]})
            for fid, row in env.compute.rows.items()
            if "p1" in env.compute.access[fid]
        ]

    @asynccontextmanager
    async def lock(conn, *, wait=False):
        yield env.lease

    monkeypatch.setattr(svc, "_authorize", authorize)
    monkeypatch.setattr(svc, "_operator", operator)
    monkeypatch.setattr(svc, "_evaluate", evaluate)
    monkeypatch.setattr(svc.identity_roles, "_graph_lock", lock)
    monkeypatch.setattr(svc.nova, "list_flavors", visible)
    monkeypatch.setattr(
        managed_flavors,
        "_compute",
        lambda conn: env.compute if conn is executor else pytest.fail("caller used for privileged native writes"),
    )
    env.caller, env.executor, env.authorizations = caller, executor, authorizations
    env.info = {"user_id": "u1", "identity_domain_id": "home", "domain_id": "d1", "project_id": "p1"}
    return env


@pytest.fixture
def composition_wait(composition_native, graph_env, monkeypatch):
    """Real authority fences and Redis admission with synthetic cloud/session/SQL stores."""
    from app.api import deps
    from app.api.compute import flavors
    from app.api.identity import admin_instances
    from app.services import domain_scope

    env = composition_native
    env.graph = graph_env
    env.executor.endpoint_for = graph_env.conn.endpoint_for
    env.caller._afterglow_project_id = "p1"
    env.caller.close = lambda: None
    env.info.update(refresh_jti="composition-session", token="native-proof", roles=["member"])
    env.session = {**env.info, "family_id": "family", "scope_revision": 1, "keystone_token": "native-proof"}
    env.native = {**env.info}
    env.native_error = None
    env.target = {"id": "p1", "domain_id": "d1", "enabled": True}
    env.saves = []
    persist = managed_flavors._save

    async def save(value, **kwargs):
        env.saves.append(copy.deepcopy(value))
        await persist(value, **kwargs)

    class Operation:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def run(self, function, *args, **kwargs):
            return function(*args, **kwargs)

        def get(self, kind, pid):
            assert kind == "projects" and pid == "p1"
            return copy.deepcopy(env.target)

    def validate(token, **kwargs):
        assert token == "native-proof"
        if env.native_error:
            raise env.native_error
        return copy.deepcopy(env.native)

    monkeypatch.setattr(svc, "_authorize", _authorize)
    monkeypatch.setattr(svc.identity_roles, "_graph_lock", real_graph_lock)
    monkeypatch.setattr(svc, "NativeOperation", Operation)
    monkeypatch.setattr(svc.keystone, "validate_token", validate)
    monkeypatch.setattr(managed_flavors, "_save", save)
    monkeypatch.setattr(svc.session_store, "get_session", AsyncMock(side_effect=lambda _: copy.deepcopy(env.session)))
    monkeypatch.setattr(domain_scope, "resolve_domain", lambda domain, **kwargs: {"id": domain})
    monkeypatch.setattr(deps, "require_admin", AsyncMock())
    monkeypatch.setattr(admin_instances, "_make_admin_conn", lambda project, user: env.caller)
    env.app = FastAPI()
    env.app.include_router(flavors.router, prefix="/api/v1/flavors")
    env.app.include_router(admin_instances.router, prefix="/api/v1/admin")
    env.app.dependency_overrides[deps.get_os_conn] = lambda: env.caller
    env.app.dependency_overrides[deps.get_token_info] = lambda: dict(env.info)
    env.app.dependency_overrides[admin_instances.require_admin] = lambda: dict(env.info)
    return env


def composition_url(surface):
    if surface == "admin":
        return "/api/v1/admin/instances/flavor-compositions?project_id=p1"
    return "/api/v1/flavors/compositions"


async def finish_queued_save(task, resume):
    # save() shields native mutation completion, so release admission before draining
    # even when a test assertion fails; never cancel a live shielded save as cleanup.
    if resume is not None and not resume.done():
        resume.set_result(None)
    if task is not None:
        await asyncio.wait_for(task, timeout=5)


@pytest.mark.parametrize(
    "values",
    [
        {"vcpus": True},
        {"vcpus": 0},
        {"vcpus": 1},
        {"vcpus": 3},
        {"vcpus": 129},
        {"ram_mb": 4097},
        {"ram_mb": 2098176},
        {"gpu_count": 1},
        {"gpu_profile_id": "render"},
        {"extra_specs": {"resources:VCPU": "1"}},
        {"gpu_count": True},
        {"vcpus": "2"},
    ],
)
def test_resource_body_rejects_unvalidated_coordinates(values):
    with pytest.raises(ValidationError):
        request(**values)


@pytest.mark.parametrize(
    "body",
    [
        {"vcpus": True, "ram_mb": 4096},
        {"vcpus": 1, "ram_mb": 4096},
        {"vcpus": 3, "ram_mb": 4096},
        {"vcpus": 2, "ram_mb": 4096, "extra_specs": {"x": "y"}},
    ],
)
async def test_save_endpoint_rejects_raw_specs_and_booleans(client, body):
    response = await client.post("/api/v1/flavors/compositions", json=body)
    assert response.status_code == 422


async def test_custom_save_is_exact_native_executor_only_and_survives_rerun(composition_native, monkeypatch):
    env = composition_native
    monkeypatch.setattr(managed_flavors, "_manual_cpu_flavors", AsyncMock(side_effect=AssertionError("broad adoption")))
    saved = await svc.save(env.caller, "p1", env.info, request(vcpus=6, ram_mb=5120))
    assert saved.composition == request(vcpus=6, ram_mb=5120).model_dump()
    assert len(env.compute.rows) == 1
    assert env.state["custom_intents"] == {saved.id: saved.composition}
    assert len(env.authorizations) >= 4
    repeated = await svc.save(env.caller, "p1", env.info, request(vcpus=6, ram_mb=5120))
    assert repeated.id == saved.id
    assert [event for event in env.compute.events if event[0] == "create"] == [("create", saved.id)]
    # The ordinary periodic pass must retain nonstandard coordinates.
    monkeypatch.setattr(managed_flavors, "_manual_cpu_flavors", AsyncMock(return_value=[]))
    await managed_flavors.reconcile(env.executor)
    assert env.compute.specs[saved.id]["afterglow:frontend_visible"] == "true"
    assert env.compute.access[saved.id] == {"p1"}


async def test_standard_saved_identity_reuses_historical_native_name(composition_native):
    env = composition_native
    shape = managed_flavors.compose_shape(env.policy["hosts"], [], vcpus=2, ram_mb=4096)
    first = await svc.save(env.caller, "p1", env.info, request())
    legacy_name = f"cpu.ag.2c.4g.{first.id.replace('-', '')[:12]}"
    env.compute.rows[first.id].name = legacy_name
    repeated = await svc.save(env.caller, "p1", env.info, request())
    assert repeated.id == shape["id"] == first.id
    assert repeated.name == legacy_name
    assert len(env.compute.rows) == 1


async def test_history_is_actor_home_and_project_private(composition_native):
    env = composition_native
    saved = await svc.save(env.caller, "p1", env.info, request())
    own = await svc.history(env.caller, "p1", env.info)
    assert [row.id for row in own.items] == [saved.id]
    for info, project_id in [
        ({**env.info, "user_id": "other"}, "p1"),
        ({**env.info, "identity_domain_id": "other"}, "p1"),
        (env.info, "p2"),
    ]:
        assert (await svc.history(env.caller, project_id, info)).items == []
    public = managed_flavors._public(env.state, {"policy_ready": True})
    assert not {"claims", "cpu_claims", "composition_history", "custom_intents"} & public.keys()
    env.compute.access[saved.id].clear()
    assert (await svc.history(env.caller, "p1", env.info)).items == []


async def test_unknown_dispatch_is_not_replayed_and_does_not_save_history(composition_native, monkeypatch):
    env = composition_native
    calls = []

    def unknown(**attrs):
        calls.append(attrs)
        raise TimeoutError("response lost")

    monkeypatch.setattr(env.compute, "create_flavor", unknown)
    with pytest.raises(HTTPException, match="flavor_composition_native_outcome_unknown") as exc:
        await svc.save(env.caller, "p1", env.info, request(vcpus=6))
    assert exc.value.status_code == 503
    with pytest.raises(HTTPException, match="native_conflict"):
        await svc.save(env.caller, "p1", env.info, request(vcpus=6))
    assert len(calls) == 1
    assert env.state["composition_history"] == env.state["custom_intents"] == {}


async def test_native_id_collision_is_never_adopted(composition_native):
    env = composition_native
    shape = managed_flavors.compose_shape(env.policy["hosts"], [], vcpus=2, ram_mb=4096)
    env.compute.create_flavor(
        id=shape["id"], name=shape["name"], vcpus=2, ram=4096, disk=0, is_public=False, description="manual"
    )
    env.compute.events.clear()
    with pytest.raises(HTTPException, match="native_conflict"):
        await svc.save(env.caller, "p1", env.info, request())
    assert not [event for event in env.compute.events if event[0] in {"create", "spec_write", "grant", "revoke"}]
    assert env.state["composition_history"] == {}


async def test_failed_spec_readback_never_records_history(composition_native):
    env = composition_native
    env.compute.bad_specs = True
    with pytest.raises(HTTPException, match="native_conflict"):
        await svc.save(env.caller, "p1", env.info, request(vcpus=6))
    assert env.state["composition_history"] == {}
    assert all(not access for access in env.compute.access.values())


async def test_gpu_three_and_companion_request_group_limit(composition_native, monkeypatch):
    env = composition_native
    env.policy["gpu_profiles"] = [profile("render")]
    with pytest.raises(HTTPException, match="unsupported"):
        await svc.save(env.caller, "p1", env.info, request(gpu_profile_id="render", gpu_count=9))
    # Retirement cannot treat durable coordinates as authority.
    saved = await svc.save(env.caller, "p1", env.info, request(gpu_profile_id="render", gpu_count=3))
    env.policy["gpu_profiles"][0]["enabled"] = False
    monkeypatch.setattr(managed_flavors, "_manual_cpu_flavors", AsyncMock(return_value=[]))
    await managed_flavors.reconcile(env.executor)
    assert env.compute.access[saved.id] == set()
    assert env.compute.specs[saved.id]["afterglow:frontend_visible"] == "false"


@pytest.fixture
def live_options(cloud, monkeypatch):
    policy = {
        "revision": 1,
        "hosts": [{**host(cpu=128, ram=2097152), "id": root, "name": HOST_NAMES[root]} for root in (ROOT_A, ROOT_B)],
        "gpu_profiles": [],
    }
    monkeypatch.setattr(svc.flavor_automation_policy, "load_policy", AsyncMock(return_value=policy))
    monkeypatch.setattr(
        managed_flavors, "_load", AsyncMock(return_value={**managed_flavors._default(), "enabled": True})
    )
    monkeypatch.setattr(
        managed_flavors,
        "_pool_projects",
        AsyncMock(
            side_effect=lambda: {
                "p1": {
                    "domain_id": "d1",
                    "active": True,
                    "limits": {item["resource_class"]: -1 for item in policy["gpu_profiles"]},
                }
            }
        ),
    )
    monkeypatch.setattr(
        flavor_eligibility.compute_pools, "project_pool_snapshot", AsyncMock(return_value={"enabled": False})
    )
    quota = {name: {"limit": -1, "in_use": 0, "reserved": 0} for name in ("instances", "cores", "ram")}

    def quota_reader(*args, **kwargs):
        return copy.deepcopy(quota)

    monkeypatch.setattr(svc.nova, "get_project_quota", quota_reader)
    monkeypatch.setattr(
        "app.services.resource_policy_store.resolve_policies",
        AsyncMock(return_value={"nova.default_compute_availability_zone": ZONE}),
    )
    # conftest's generic capacity fixture is not authority for these integration tests.
    monkeypatch.setattr(flavor_capacity, "evaluate_flavor_capacities", NATIVE_CAPACITY)
    return quota


NATIVE_CAPACITY = flavor_capacity.evaluate_flavor_capacities


async def test_snapshot_preserves_crossed_hosts_usage_max_unit_and_one_candidate_call(cloud, live_options):
    cloud.add_host(ROOT_A, vcpu=(16, 12), ram=(65536, 0))
    cloud.add_host(ROOT_B, vcpu=(64, 0), ram=(65536, 61440))
    cloud.inventories[ROOT_A]["MEMORY_MB"]["max_unit"] = 32768
    cloud.answers[CPU_SHAPE] = [allocation({ROOT_A: ONE}), allocation({ROOT_B: ONE})]
    snapshot = await svc.options(SimpleNamespace(), "p1", availability_zone=ZONE)
    row = variant(snapshot)
    assert snapshot.status == row.status == "available"
    assert fits(row, 4, 32768) and fits(row, 64, 4096)
    assert not fits(row, 8, 8192)
    assert not fits(row, 64, 32768)
    assert not fits(row, 3, 4096)
    assert len(row.regions) == 2
    assert len(cloud.candidate_queries()) == 1


@pytest.mark.parametrize("failure", ["quota", "az", "placement"])
async def test_unknown_authority_is_not_zero_or_available(cloud, live_options, monkeypatch, failure):
    cloud.add_host(ROOT_A)
    cloud.answers[CPU_SHAPE] = [allocation({ROOT_A: ONE})]
    if failure == "quota":
        monkeypatch.setattr(svc.nova, "get_project_quota", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("quota")))
    elif failure == "az":
        monkeypatch.setattr(
            "app.services.resource_policy_store.resolve_policies", AsyncMock(side_effect=RuntimeError("AZ"))
        )
    else:
        cloud.failures["/placement/allocation_candidates"] = (503, b"unavailable")
    options = await svc.options(SimpleNamespace(), "p1")
    assert options.status == "unavailable"
    assert variant(options).regions == []
    assert variant(options).preview is not None and not variant(options).preview.eligibility.selectable


async def test_native_quota_remaining_limits_conditional_choices(cloud, live_options):
    cloud.add_host(ROOT_A, vcpu=(64, 0), ram=(131072, 0))
    cloud.answers[CPU_SHAPE] = [allocation({ROOT_A: ONE})]
    live_options["cores"] = {"limit": 12, "in_use": 7, "reserved": 1}
    live_options["ram"] = {"limit": 16384, "in_use": 4096, "reserved": 4096}
    options = await svc.options(SimpleNamespace(), "p1")
    row = variant(options)
    assert fits(row, 4, 8192)
    assert not fits(row, 6, 8192) and not fits(row, 4, 9216)
    assert row.preview.eligibility.remaining.cores == 4
    assert row.preview.eligibility.remaining.ram_mb == 8192


async def test_session_renewal_preserves_identity_scope_but_not_retarget(monkeypatch):
    info = {"user_id": "u", "identity_domain_id": "home", "domain_id": "d", "refresh_jti": "jti"}
    row = {**info, "project_id": "p", "family_id": "family", "scope_revision": 2, "keystone_token": "first"}
    monkeypatch.setattr(svc.session_store, "get_session", AsyncMock(side_effect=lambda _: copy.deepcopy(row)))
    before, _ = await svc._session(info)
    row["keystone_token"] = "renewed"
    assert (await svc._session(info))[0] == before
    row["scope_revision"] += 1
    assert (await svc._session(info))[0] != before
    row["blacklisted"] = True
    with pytest.raises(HTTPException) as exc:
        await svc._session(info)
    assert exc.value.status_code == 401


@pytest.mark.parametrize("roles,scope", [(["member"], True), (["admin"], False)])
def test_operator_requires_native_admin_project(roles, scope):
    access = SimpleNamespace(
        project_scoped=True,
        system_scoped=False,
        project_id="operator",
        auth_token="secret",
        is_admin_project=scope,
        role_names=roles,
        _data={"token": {"is_admin_project": scope}},
    )
    conn = SimpleNamespace(session=SimpleNamespace(auth=SimpleNamespace(get_access=lambda _: access)))
    with pytest.raises(HTTPException) as exc:
        svc._verify_operator(conn)
    assert exc.value.status_code == 503


@pytest.mark.parametrize(
    "case,code",
    [
        ("reader", 403),
        ("foreign_project", 403),
        ("foreign_home", 403),
        ("revoked", 401),
        ("disabled_target", 403),
        ("changed_scope", 401),
    ],
)
async def test_write_authority_revalidates_native_subject_and_target(monkeypatch, case, code):
    from keystoneauth1.exceptions.http import Unauthorized

    from app.services import domain_scope

    info = {"user_id": "u", "identity_domain_id": "home", "domain_id": "d", "project_id": "p", "token": "proof"}
    native = {**info, "roles": ["member"]}
    if case == "reader":
        native["roles"] = ["reader"]
    if case == "foreign_home":
        native["identity_domain_id"] = "foreign"
    if case == "foreign_project":
        info["project_id"] = "foreign"

    class Operation:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def run(self, function, *args, **kwargs):
            return function(*args, **kwargs)

        def get(self, kind, pid):
            assert kind == "projects"
            return {"id": pid, "domain_id": "d", "enabled": case != "disabled_target"}

    def validate(*args, **kwargs):
        if case == "revoked":
            raise Unauthorized("revoked")
        return native

    monkeypatch.setattr(svc, "NativeOperation", Operation)
    monkeypatch.setattr(svc.keystone, "validate_token", validate)
    monkeypatch.setattr(domain_scope, "resolve_domain", lambda *args, **kwargs: {"id": "d"})
    if case == "changed_scope":
        monkeypatch.setattr(svc, "_session", AsyncMock(side_effect=[(("old",), "proof"), (("new",), "proof")]))
    with pytest.raises(HTTPException) as exc:
        await svc._authorize(info, "p", write=True)
    assert exc.value.status_code == code


async def test_gpu_options_use_real_remaining_same_host_counts_and_keep_exhausted_profile(cloud, live_options):
    from tests.test_flavor_capacity import GPU_RC, shape

    approved = profile("render", GPU_RC)
    policy = svc.flavor_automation_policy.load_policy.return_value
    policy["gpu_profiles"] = [approved]
    policy["hosts"][0]["gpu"] = {GPU_RC: 16, AUDIO: 16}
    cloud.add_host(ROOT_A, vcpu=(16, 0), ram=(65536, 0))
    cloud.add_host(ROOT_B, vcpu=(128, 0), ram=(2097152, 0))
    devices = []
    for index in range(3):
        primary, companion = f"primary-{index}", f"companion-{index}"
        cloud.add_device(ROOT_A, primary, GPU_RC)
        cloud.add_device(ROOT_A, companion, AUDIO)
        devices.append((primary, companion))
    for count in range(1, 4):
        amounts = {ROOT_A: ONE}
        for primary, companion in devices[:count]:
            amounts[primary], amounts[companion] = {GPU_RC: 1}, {AUDIO: 1}
        cloud.answers[shape("VCPU:1,MEMORY_MB:1", *([GPU_RC, AUDIO] * count))] = [allocation(amounts)]
    capabilities = await svc.flavor_automation_policy.capabilities()
    snapshot = {
        "enabled": True,
        "state": "active",
        "domain_id": "d",
        "policy_ready": True,
        "control_scope": "afterglow",
        "limits": {},
        "usage": {},
        "available": {"CPU": 128, "MEMORY_MB": 2097152, GPU_RC: 16},
        "project_limits": {},
        "project_usage": {},
        "project_available": {},
        "_aliases": capabilities["aliases"],
        "_pci_aliases": capabilities["pci_aliases"],
        "_resource_kinds": capabilities["resource_kinds"],
    }
    svc.flavor_eligibility.compute_pools.project_pool_snapshot.return_value = snapshot
    options = await svc.options(SimpleNamespace(), "p1", availability_zone=ZONE)
    rows = [variant(options, "render", count) for count in range(1, 17)]
    assert [row.gpu_count for row in rows if row.status == "available"] == [1, 2, 3]
    assert all(not row.regions for row in rows[3:])
    assert rows[2].preview.composition["gpu_count"] == 3
    assert rows[2].preview.gpu_primary_aliases[0].count == 3
    assert fits(rows[0], 16, 65536)
    # Spare CPU/RAM on another host must not pair with the GPU root.
    assert not fits(rows[0], 32, 4096)
    assert len(cloud.candidate_queries()) == 9  # CPU-only plus eight two-function counts
    # A known empty Placement result preserves the exhausted approved profile.
    cloud.answers.clear()
    options = await svc.options(SimpleNamespace(), "p1", availability_zone=ZONE)
    assert options.gpu_profiles[0].id == "render"
    assert all(variant(options, "render", count).status == "insufficient" for count in range(1, 17))


async def test_history_bounds_and_storage_validation(composition_native, monkeypatch):
    env = composition_native
    for cpu in range(2, 46, 2):
        await svc.save(env.caller, "p1", env.info, request(vcpus=cpu))
    ids = env.state["composition_history"][svc._actor(env.info, "p1")]
    assert len(ids) == managed_flavors.MAX_HISTORY_ITEMS == 20
    assert managed_flavors._state(copy.deepcopy(env.state))["composition_history"]
    malicious = copy.deepcopy(env.state)
    malicious["custom_intents"][ids[0]]["extra_specs"] = {"resources:VCPU": "1"}
    with pytest.raises(HTTPException) as exc:
        managed_flavors._state(malicious)
    assert exc.value.status_code == 503
    monkeypatch.setattr(managed_flavors, "MAX_CUSTOM_INTENTS", len(env.state["custom_intents"]))
    with pytest.raises(HTTPException, match="intent_limit"):
        await svc.save(env.caller, "p1", env.info, request(vcpus=46))


async def test_disabled_automation_never_dispatches(composition_native):
    env = composition_native
    env.state["enabled"] = False
    with pytest.raises(HTTPException, match="automation_disabled"):
        await svc.save(env.caller, "p1", env.info, request())
    assert env.compute.events == []


async def test_revoked_authority_before_acl_never_publishes_or_saves_history(composition_native, monkeypatch):
    env = composition_native

    async def authorize(*args, **kwargs):
        if any(event[0] == "spec_write" for event in env.compute.events):
            raise HTTPException(403, "authority_revoked")
        return ("stable",)

    monkeypatch.setattr(svc, "_authorize", authorize)
    with pytest.raises(HTTPException, match="authority_revoked"):
        await svc.save(env.caller, "p1", env.info, request(vcpus=6))
    assert not [event for event in env.compute.events if event[0] == "grant"]
    assert env.state["composition_history"] == env.state["custom_intents"] == {}


async def test_consumer_http_save_reuses_native_shape_and_keeps_history_private(composition_native):
    from app.api import deps
    from app.api.compute import flavors

    env = composition_native
    env.caller._afterglow_project_id = "p1"
    principal = {**env.info, "roles": ["member"]}
    app = FastAPI()
    app.include_router(flavors.router, prefix="/api/v1/flavors")
    app.dependency_overrides[deps.get_os_conn] = lambda: env.caller
    app.dependency_overrides[deps.get_token_info] = lambda: dict(principal)
    coordinates = request(vcpus=6, ram_mb=5120).model_dump()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post("/api/v1/flavors/compositions", json=coordinates)
        assert created.status_code == 200
        fid = created.json()["id"]
        assert created.json()["composition"] == coordinates
        assert env.compute.rows[fid].vcpus == 6
        assert env.compute.rows[fid].ram == 5120
        assert env.compute.access[fid] == {"p1"}
        assert env.state["custom_intents"][fid] == coordinates
        actor = svc._actor(principal, "p1")
        assert env.state["composition_history"][actor] == [fid]

        repeated = await client.post("/api/v1/flavors/compositions", json=coordinates)
        assert repeated.status_code == 200
        assert repeated.json()["id"] == fid
        assert [event for event in env.compute.events if event[0] == "create"] == [("create", fid)]
        own_history = await client.get("/api/v1/flavors/compositions")
        assert own_history.status_code == 200
        assert [item["id"] for item in own_history.json()["items"]] == [fid]

        principal["user_id"] = "other-user"
        foreign_history = await client.get("/api/v1/flavors/compositions")
        assert foreign_history.status_code == 200
        assert foreign_history.json() == {"items": []}
        principal["user_id"] = env.info["user_id"]
        env.caller._afterglow_project_id = "p2"
        foreign_scope_history = await client.get("/api/v1/flavors/compositions")
        assert foreign_scope_history.status_code == 200
        assert foreign_scope_history.json() == {"items": []}

        env.caller._afterglow_project_id = "p1"
        principal["roles"] = ["reader"]
        before = copy.deepcopy(env.compute.events)
        denied = await client.post("/api/v1/flavors/compositions", json={**coordinates, "vcpus": 8})
        assert denied.status_code == 403
        assert env.compute.events == before
        assert env.state["composition_history"] == {actor: [fid]}


async def test_cpu_per_vm_max_unit_limits_options_despite_free_total(cloud, live_options):
    cloud.add_host(ROOT_A, vcpu=(128, 1), ram=(2097152, 0))
    cloud.inventories[ROOT_A]["VCPU"]["max_unit"] = 6
    cloud.answers[CPU_SHAPE] = [allocation({ROOT_A: ONE})]
    options = await svc.options(SimpleNamespace(), "p1", availability_zone=ZONE)
    row = variant(options)
    assert fits(row, 6, 2097152)
    assert not fits(row, 8, 1024) and not fits(row, 3, 1024)


async def test_admin_saved_flag_cannot_replace_fresh_native_authority(monkeypatch):
    from app.api import deps

    info = {
        "user_id": "u",
        "identity_domain_id": "home",
        "domain_id": "d",
        "project_id": "p",
        "token": "proof",
        "is_system_admin": True,
    }
    guard = AsyncMock(side_effect=HTTPException(403, "native_system_authority_revoked"))
    monkeypatch.setattr(deps, "require_admin", guard)
    with pytest.raises(HTTPException) as exc:
        await svc._authorize(info, "target", admin=True, write=True)
    assert exc.value.status_code == 403
    guard.assert_awaited_once()


@pytest.mark.parametrize("boundary", ["create", "specs"])
async def test_committed_native_response_failure_returns_503_then_exact_readback_recovers(
    composition_native, monkeypatch, boundary
):
    env = composition_native
    method = "create_flavor" if boundary == "create" else "create_flavor_extra_specs"
    original = getattr(env.compute, method)
    dispatched = []

    def committed_response_lost(*args, **kwargs):
        original(*args, **kwargs)
        dispatched.append(True)
        raise ValueError("native response readback unavailable; secret must not escape")

    monkeypatch.setattr(env.compute, method, committed_response_lost)
    coordinates = request(vcpus=6, ram_mb=5120)
    with pytest.raises(HTTPException) as exc:
        await svc.save(env.caller, "p1", env.info, coordinates)
    assert exc.value.status_code == 503
    assert exc.value.detail == "flavor_composition_native_outcome_unknown"
    assert len(dispatched) == 1
    assert len(env.compute.rows) == 1
    fid = next(iter(env.compute.rows))
    assert env.state["claims"][fid]["dispatched"] is True
    assert env.state["custom_intents"] == env.state["composition_history"] == {}
    assert not env.compute.access[fid]
    monkeypatch.setattr(env.compute, method, original)
    recovered = await svc.save(env.caller, "p1", env.info, coordinates)
    assert recovered.id == fid
    assert len([event for event in env.compute.events if event[0] == "create"]) == 1
    assert env.state["custom_intents"][fid] == coordinates.model_dump()


async def test_known_native_http_authority_failure_is_not_relabelled_unknown(composition_native, monkeypatch):
    env = composition_native

    def denied(**kwargs):
        raise HTTPException(403, "native_publication_denied")

    monkeypatch.setattr(env.compute, "create_flavor", denied)
    with pytest.raises(HTTPException) as exc:
        await svc.save(env.caller, "p1", env.info, request(vcpus=6))
    assert exc.value.status_code == 403
    assert exc.value.detail == "native_publication_denied"
    assert env.state["custom_intents"] == env.state["composition_history"] == {}


async def test_snapshot_honors_minimum_steps_and_crossed_minimum_quota(cloud, live_options):
    policy = svc.flavor_automation_policy.load_policy.return_value
    policy["hosts"][0]["cpu"] = {"min": 2, "step": 2, "capacity": 16}
    policy["hosts"][0]["ram"] = {"min": 8192, "step": 2048, "capacity": 65536}
    policy["hosts"][1]["cpu"] = {"min": 8, "step": 6, "capacity": 36}
    policy["hosts"][1]["ram"] = {"min": 1024, "step": 3072, "capacity": 65536}
    cloud.add_host(ROOT_A, vcpu=(16, 0))
    cloud.add_host(ROOT_B, vcpu=(36, 0))
    cloud.answers[CPU_SHAPE] = [allocation({ROOT_A: ONE}), allocation({ROOT_B: ONE})]
    live_options["ram"] = {"limit": 4096, "in_use": 0, "reserved": 0}
    snapshot = await svc.options(SimpleNamespace(), "p1", availability_zone=ZONE)
    row = variant(snapshot)
    assert row.status == "available"
    assert fits(row, 12, 3072) and fits(row, 36, 3072)
    assert not fits(row, 8, 3072) and not fits(row, 12, 2048)
    assert row.preview.vcpus == 12 and row.preview.ram == 3072
    assert row.preview.eligibility.selectable
    assert len(cloud.candidate_queries()) == 1


async def test_snapshot_policy_host_and_live_root_cannot_exchange_support(cloud, live_options):
    policy = svc.flavor_automation_policy.load_policy.return_value
    policy["hosts"][0]["cpu"]["capacity"] = 4
    policy["hosts"][0]["ram"]["capacity"] = 65536
    policy["hosts"][1]["cpu"]["capacity"] = 64
    policy["hosts"][1]["ram"]["capacity"] = 4096
    cloud.add_host(ROOT_A, vcpu=(64, 0), ram=(4096, 0))
    cloud.add_host(ROOT_B, vcpu=(4, 0), ram=(65536, 0))
    cloud.answers[CPU_SHAPE] = [allocation({ROOT_A: ONE}), allocation({ROOT_B: ONE})]
    row = variant(await svc.options(SimpleNamespace(), "p1", availability_zone=ZONE))
    assert fits(row, 4, 4096)
    assert not fits(row, 8, 4096) and not fits(row, 4, 8192)
    policy["hosts"][0]["id"] = "retired-other-root"
    policy["hosts"][1]["removed"] = True
    row = variant(await svc.options(SimpleNamespace(), "p1", availability_zone=ZONE))
    assert row.status == "insufficient" and not row.regions


@pytest.mark.parametrize("state", ["disabled", "paused", "no_instances", "wrong_zone", "disabled_host"])
async def test_snapshot_never_offers_unadmitted_regions(cloud, live_options, state):
    cloud.add_host(ROOT_A)
    cloud.answers[CPU_SHAPE] = [allocation({ROOT_A: ONE})]
    if state == "disabled":
        managed_flavors._load.return_value["enabled"] = False
    elif state == "paused":
        svc.flavor_eligibility.compute_pools.project_pool_snapshot.return_value = {
            "enabled": True,
            "state": "paused",
            "domain_id": "d",
        }
    elif state == "no_instances":
        live_options["instances"] = {"limit": 1, "in_use": 0, "reserved": 1}
    elif state == "wrong_zone":
        cloud.aggregates[0]["availability_zone"] = "other-zone"
        cloud.services[0]["zone"] = "other-zone"
    else:
        cloud.services[0]["status"] = "disabled"
    snapshot = await svc.options(SimpleNamespace(), "p1", availability_zone=ZONE)
    assert snapshot.status == ("unavailable" if state == "disabled" else "insufficient")
    assert not variant(snapshot).regions
    if state == "disabled":
        assert not cloud.candidate_queries()


async def test_consumer_snapshot_http_schema_is_complete_coordinate_independent_and_private(cloud, live_options):
    from app.api import deps
    from app.api.compute import flavors

    cloud.add_host(ROOT_A, vcpu=(16, 0), ram=(32768, 0))
    cloud.answers[CPU_SHAPE] = [allocation({ROOT_A: ONE})]
    app = FastAPI()
    app.include_router(flavors.router, prefix="/api/v1/flavors")
    app.dependency_overrides[deps.get_os_conn] = lambda: SimpleNamespace(_afterglow_project_id="p1")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/flavors/composer-options")
        other = await client.get("/api/v1/flavors/composer-options")
    assert response.status_code == other.status_code == 200
    body, second = response.json(), other.json()
    assert set(body) == {"checked_at", "status", "gpu_profiles", "variants"}
    assert body["variants"][0]["regions"] == second["variants"][0]["regions"]
    row = body["variants"][0]
    assert row["preview"]["id"] == "composer-preview"
    assert set(row["regions"][0]) == {"vcpus", "ram_mb"}
    assert all(set(axis) == {"min", "max", "step"} for axis in row["regions"][0].values())
    assert ROOT_A not in response.text and ROOT_B not in response.text
    assert len(cloud.candidate_queries()) == 2


async def test_legacy_odd_native_history_is_preserved_but_new_post_rejects_it(composition_native):
    from app.api import deps
    from app.api.compute import flavors

    env = composition_native
    coordinates = {"vcpus": 1, "ram_mb": 4096, "gpu_profile_id": None, "gpu_count": 0}
    shape = managed_flavors.compose_shape(env.policy["hosts"], [], **coordinates)
    env.compute.create_flavor(id=shape["id"], name=shape["name"], vcpus=1, ram=4096, disk=0, is_public=False)
    env.compute.specs[shape["id"]] = shape["extra_specs"]
    env.compute.access[shape["id"]] = {"p1"}
    env.state["custom_intents"][shape["id"]] = coordinates
    env.state["composition_history"][svc._actor(env.info, "p1")] = [shape["id"]]
    assert managed_flavors._state(copy.deepcopy(env.state))["custom_intents"][shape["id"]] == coordinates
    history = await svc.history(env.caller, "p1", env.info)
    assert history.items[0].id == shape["id"] and history.items[0].composition == coordinates
    env.caller._afterglow_project_id = "p1"
    app = FastAPI()
    app.include_router(flavors.router, prefix="/api/v1/flavors")
    app.dependency_overrides[deps.get_os_conn] = lambda: env.caller
    app.dependency_overrides[deps.get_token_info] = lambda: {**env.info, "roles": ["member"]}
    before = copy.deepcopy(env.compute.events)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/flavors/compositions", json=coordinates)
    assert response.status_code == 422
    assert env.compute.events == before
    assert env.state["custom_intents"][shape["id"]] == coordinates


async def test_snapshot_deadline_retains_all_known_profile_variants(cloud, live_options, monkeypatch):
    policy = svc.flavor_automation_policy.load_policy.return_value
    policy["gpu_profiles"] = [profile("render")]
    monkeypatch.setattr(svc, "_evaluate", AsyncMock(side_effect=TimeoutError))
    snapshot = await svc.options(SimpleNamespace(), "p1", availability_zone=ZONE)
    assert [row.id for row in snapshot.gpu_profiles] == ["render"]
    assert len(snapshot.variants) == 17
    assert all(row.status == "unavailable" and not row.regions for row in snapshot.variants)


def active_pool(capabilities, available, project_limits=None, project_usage=None):
    return {
        "enabled": True,
        "state": "active",
        "domain_id": "d",
        "policy_ready": True,
        "control_scope": "afterglow",
        "limits": {},
        "usage": {},
        "available": available,
        "project_limits": project_limits or {},
        "project_usage": project_usage or {},
        "project_available": {
            resource: -1 if limit == -1 else max(0, limit - (project_usage or {}).get(resource, 0))
            for resource, limit in (project_limits or {}).items()
        },
        "_aliases": capabilities["aliases"],
        "_pci_aliases": capabilities["pci_aliases"],
        "_resource_kinds": capabilities["resource_kinds"],
    }


async def test_domain_project_caps_intersect_each_region_and_preserve_unlimited(cloud, live_options):
    policy = svc.flavor_automation_policy.load_policy.return_value
    policy["hosts"][0]["ram"]["min"] = 8192
    cloud.add_host(ROOT_A)
    cloud.add_host(ROOT_B)
    cloud.answers[CPU_SHAPE] = [allocation({ROOT_A: ONE}), allocation({ROOT_B: ONE})]
    capabilities = await svc.flavor_automation_policy.capabilities()
    snapshot = active_pool(
        capabilities,
        {"CPU": -1, "MEMORY_MB": -1},
        project_limits={"CPU": 11, "MEMORY_MB": 4096},
        project_usage={"CPU": 3, "MEMORY_MB": 1024},
    )
    svc.flavor_eligibility.compute_pools.project_pool_snapshot.return_value = snapshot
    row = variant(await svc.options(SimpleNamespace(), "p1", availability_zone=ZONE))
    assert row.status == "available" and row.preview.eligibility.selectable
    assert fits(row, 8, 3072) and not fits(row, 10, 3072)
    assert not fits(row, 2, 4096)
    assert row.preview.eligibility.remaining.cores == 8
    assert row.preview.eligibility.remaining.ram_mb == 3072
    snapshot["project_limits"] = {}
    snapshot["project_available"] = {}
    row = variant(await svc.options(SimpleNamespace(), "p1", availability_zone=ZONE))
    assert fits(row, 32, 65536)
    assert row.preview.eligibility.remaining.cores == row.preview.eligibility.remaining.ram_mb == -1


async def test_nine_profile_snapshot_queries_only_supported_variants_once(cloud, live_options, monkeypatch):
    from tests.test_flavor_capacity import shape

    policy = svc.flavor_automation_policy.load_policy.return_value
    profiles = [profile(f"model-{index}", f"CUSTOM_PCI_10DE_{0x3000 + index:04X}") for index in range(9)]
    policy["gpu_profiles"] = profiles
    policy["hosts"] = [policy["hosts"][0]]
    policy["hosts"][0]["gpu"] = {AUDIO: 2, **{row["resource_class"]: 2 for row in profiles}}
    cloud.add_host(ROOT_A, vcpu=(32, 0), ram=(65536, 0))
    cloud.add_device(ROOT_A, "shared-companion", AUDIO)
    cloud.answers[CPU_SHAPE] = [allocation({ROOT_A: ONE})]
    for index, row in enumerate(profiles):
        resource = row["resource_class"]
        provider = f"primary-{index}"
        cloud.add_device(ROOT_A, provider, resource)
        cloud.answers[shape("VCPU:1,MEMORY_MB:1", resource, AUDIO)] = [
            allocation({ROOT_A: ONE, provider: {resource: 1}, "shared-companion": {AUDIO: 1}})
        ]
    capabilities = await svc.flavor_automation_policy.capabilities()
    svc.flavor_eligibility.compute_pools.project_pool_snapshot.return_value = active_pool(
        capabilities,
        {"CPU": -1, "MEMORY_MB": -1, **{row["resource_class"]: -1 for row in profiles}},
    )
    reads = []
    original = svc.nova.get_project_quota

    def read(*args, **kwargs):
        reads.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(svc.nova, "get_project_quota", read)
    snapshot = await svc.options(SimpleNamespace(), "p1", availability_zone=ZONE)
    assert len(snapshot.variants) == 145
    assert all(variant(snapshot, row["name"], 1).status == "available" for row in profiles)
    assert all(variant(snapshot, row["name"], 2).status == "insufficient" for row in profiles)
    assert all(variant(snapshot, row["name"], 16).status == "insufficient" for row in profiles)
    assert len(cloud.candidate_queries()) == 19
    assert len(reads) == 1
    svc.flavor_eligibility.compute_pools.project_pool_snapshot.assert_awaited_once()
    assert sum(path == "/compute/v2.1/os-services" for path, _, _ in cloud.calls) == 1
    assert sum(path == "/placement/resource_providers" for path, _, _ in cloud.calls) == 1
    assert sum(path == f"/placement/resource_providers/{ROOT_A}/inventories" for path, _, _ in cloud.calls) == 1


async def test_snapshot_gpu_companion_exhaustion_and_project_gpu_ceiling(cloud, live_options):
    from tests.test_flavor_capacity import GPU_RC, shape

    policy = svc.flavor_automation_policy.load_policy.return_value
    policy["gpu_profiles"] = [profile("render", GPU_RC)]
    policy["hosts"][0]["gpu"] = {GPU_RC: 2, AUDIO: 2}
    cloud.add_host(ROOT_A)
    cloud.add_device(ROOT_A, "primary", GPU_RC)
    cloud.add_device(ROOT_A, "companion", AUDIO, used=1)
    cloud.answers[shape("VCPU:1,MEMORY_MB:1", GPU_RC, AUDIO)] = [
        allocation({ROOT_A: ONE, "primary": {GPU_RC: 1}, "companion": {AUDIO: 1}})
    ]
    capabilities = await svc.flavor_automation_policy.capabilities()
    pool = active_pool(capabilities, {"CPU": -1, "MEMORY_MB": -1, GPU_RC: -1})
    svc.flavor_eligibility.compute_pools.project_pool_snapshot.return_value = pool
    snapshot = await svc.options(SimpleNamespace(), "p1", availability_zone=ZONE)
    assert variant(snapshot, "render", 1).status == "insufficient"
    cloud.usages["companion"][AUDIO] = 0
    pool["project_limits"] = {GPU_RC: 1}
    pool["project_usage"] = {GPU_RC: 1}
    pool["project_available"] = {GPU_RC: 0}
    snapshot = await svc.options(SimpleNamespace(), "p1", availability_zone=ZONE)
    assert variant(snapshot, "render", 1).status == "insufficient"
    pool["project_usage"] = {}
    pool["project_available"] = {GPU_RC: 1}
    snapshot = await svc.options(SimpleNamespace(), "p1", availability_zone=ZONE)
    assert variant(snapshot, "render", 1).status == "available"
    assert variant(snapshot, "render", 1).preview.eligibility.remaining.gpus[GPU_RC] == 1


async def test_snapshot_does_not_authorize_later_save(composition_native, monkeypatch):
    env = composition_native

    async def denied(conn, project, flavors, zone):
        return [
            eligible(row).model_copy(
                update={
                    "eligibility": eligible(row).eligibility.model_copy(
                        update={
                            "selectable": False,
                        }
                    )
                }
            )
            for row in flavors
        ]

    monkeypatch.setattr(svc, "_evaluate", denied)
    with pytest.raises(HTTPException, match="not_selectable") as exc:
        await svc.save(env.caller, "p1", env.info, request(vcpus=6))
    assert exc.value.status_code == 409
    assert not env.compute.events and not env.state["composition_history"]


async def test_unknown_gpu_shape_does_not_suppress_proven_cpu_variant(cloud, live_options):
    from tests.test_flavor_capacity import GPU_RC

    policy = svc.flavor_automation_policy.load_policy.return_value
    policy["gpu_profiles"] = [profile("render", GPU_RC)]
    policy["hosts"][0]["gpu"] = {GPU_RC: 1, AUDIO: 1}
    cloud.add_host(ROOT_A)
    cloud.answers[CPU_SHAPE] = [allocation({ROOT_A: ONE})]
    # Missing approved physical classes are unknown, never a known empty fleet.
    capabilities = await svc.flavor_automation_policy.capabilities()
    svc.flavor_eligibility.compute_pools.project_pool_snapshot.return_value = active_pool(
        capabilities,
        {"CPU": -1, "MEMORY_MB": -1, GPU_RC: -1},
    )
    snapshot = await svc.options(SimpleNamespace(), "p1", availability_zone=ZONE)
    assert snapshot.status == "available"
    assert variant(snapshot).status == "available" and fits(variant(snapshot), 2, 1024)
    assert variant(snapshot, "render", 1).status == "unavailable"
    assert not variant(snapshot, "render", 1).regions


@pytest.mark.parametrize("authorized", [True, False])
async def test_admin_snapshot_http_keeps_exact_target_authorization(cloud, live_options, monkeypatch, authorized):
    from app.api import deps
    from app.api.identity import admin_instances

    cloud.add_host(ROOT_A)
    cloud.answers[CPU_SHAPE] = [allocation({ROOT_A: ONE})]
    conn = SimpleNamespace(_afterglow_project_id="p1", close=lambda: None)
    principal = {"user_id": "admin", "project_id": "operator"}
    guard = AsyncMock()
    monkeypatch.setattr(svc, "_authorize", guard)
    monkeypatch.setattr(admin_instances, "_make_admin_conn", lambda project, user: conn)
    app = FastAPI()
    app.include_router(admin_instances.router, prefix="/api/v1/admin")
    app.dependency_overrides[deps.get_token_info] = lambda: dict(principal)
    if authorized:
        # This standalone router requires both native-admin dependency and exact
        # target authorization; supply only the former test authority explicitly.
        app.dependency_overrides[deps.require_admin] = lambda: dict(principal)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/admin/instances/flavor-composer-options?project_id=p1")
    assert response.status_code == (200 if authorized else 403)
    if authorized:
        assert response.json()["variants"][0]["status"] == "available"
        guard.assert_awaited_once_with(principal, "p1", admin=True)
    else:
        guard.assert_not_awaited()


async def test_gpu_dedicated_cpu_regions_require_retained_and_live_pcpu(cloud, live_options):
    from tests.test_flavor_capacity import GPU_RC, shape

    policy = svc.flavor_automation_policy.load_policy.return_value
    approved = profile("render", GPU_RC)
    approved["extra_specs"]["hw:cpu_policy"] = "dedicated"
    policy["gpu_profiles"] = [approved]
    policy["hosts"] = [policy["hosts"][0]]
    policy["hosts"][0]["gpu"] = {GPU_RC: 1, AUDIO: 1}
    policy["hosts"][0]["pcpu"] = {"min": 6, "step": 6, "capacity": 12}
    cloud.add_host(ROOT_A, vcpu=(128, 0), pcpu=(12, 0))
    cloud.add_device(ROOT_A, "primary", GPU_RC)
    cloud.add_device(ROOT_A, "companion", AUDIO)
    cloud.answers[shape("PCPU:1,MEMORY_MB:1", GPU_RC, AUDIO)] = [
        allocation({ROOT_A: {"PCPU": 1, "MEMORY_MB": 1}, "primary": {GPU_RC: 1}, "companion": {AUDIO: 1}})
    ]
    capabilities = await svc.flavor_automation_policy.capabilities()
    svc.flavor_eligibility.compute_pools.project_pool_snapshot.return_value = active_pool(
        capabilities,
        {"CPU": -1, "MEMORY_MB": -1, GPU_RC: -1},
    )
    snapshot = await svc.options(SimpleNamespace(), "p1", availability_zone=ZONE)
    row = variant(snapshot, "render", 1)
    assert fits(row, 6, 1024) and fits(row, 12, 1024)
    assert not fits(row, 2, 1024) and not fits(row, 8, 1024) and not fits(row, 14, 1024)
    assert row.preview.eligibility.capacity.cpu_resource_class == "PCPU"
    policy["hosts"][0].pop("pcpu")
    snapshot = await svc.options(SimpleNamespace(), "p1", availability_zone=ZONE)
    assert variant(snapshot, "render", 1).status == "insufficient"


async def test_snapshot_retains_non_dominated_supplier_alternatives_on_one_root(cloud, live_options):
    cloud.add_host(ROOT_A, vcpu=(64, 0), ram=(4096, 0))
    cloud.add_device(ROOT_A, "alternate-cpu", "VCPU")
    cloud.add_device(ROOT_A, "alternate-ram", "MEMORY_MB")
    cloud.inventories["alternate-cpu"]["VCPU"].update(total=4, max_unit=4)
    cloud.inventories["alternate-ram"]["MEMORY_MB"].update(total=65536, max_unit=65536)
    cloud.answers[CPU_SHAPE] = [
        allocation({ROOT_A: ONE}),
        allocation({"alternate-cpu": {"VCPU": 1}, "alternate-ram": {"MEMORY_MB": 1}}),
    ]
    row = variant(await svc.options(SimpleNamespace(), "p1", availability_zone=ZONE))
    assert row.status == "available" and len(row.regions) == 2
    assert fits(row, 64, 4096) and fits(row, 4, 65536)
    assert not fits(row, 64, 65536)
    assert row.preview.eligibility.capacity.candidate_hosts == 1
    assert len(cloud.candidate_queries()) == 1


async def test_capacity_timeout_discards_early_and_late_worker_regions(cloud, live_options, monkeypatch):
    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    real_wait_for = asyncio.wait_for

    def slow_projection(demands, *, region_results, **kwargs):
        flavor_id = next(iter(demands))
        region = {"vcpus": {"min": 2, "max": 16, "step": 2}, "ram_mb": {"min": 1024, "max": 65536, "step": 1024}}
        region_results[flavor_id] = [region]
        started.set()
        try:
            assert release.wait(5)
            region_results[flavor_id].append(copy.deepcopy(region))
            return {flavor_id: FlavorCapacityInfo(status="available", checked_at="2026-11-01T00:00:00+00:00")}
        finally:
            finished.set()

    async def expire_after_partial_region(coroutine, *, timeout):
        task = asyncio.create_task(coroutine)
        assert await real_wait_for(asyncio.to_thread(started.wait, 5), timeout=6)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        raise TimeoutError

    monkeypatch.setattr(flavor_capacity, "_project", slow_projection)
    monkeypatch.setattr(flavor_capacity.asyncio, "wait_for", expire_after_partial_region)
    try:
        snapshot = await svc.options(SimpleNamespace(), "p1", availability_zone=ZONE)
        before = snapshot.model_dump()
        assert snapshot.status == variant(snapshot).status == "unavailable"
        assert not variant(snapshot).regions
        assert not variant(snapshot).preview.eligibility.selectable
    finally:
        release.set()
        assert await real_wait_for(asyncio.to_thread(finished.wait, 5), timeout=6)
    assert snapshot.model_dump() == before


@pytest.mark.parametrize("failure", ["state_503", "state_timeout", "evaluation_503"])
async def test_known_catalog_survives_later_authority_failures(cloud, live_options, monkeypatch, failure):
    policy = svc.flavor_automation_policy.load_policy.return_value
    policy["gpu_profiles"] = [profile("render")]
    error = TimeoutError() if failure == "state_timeout" else HTTPException(503, "authority_unavailable")
    if failure.startswith("state"):
        monkeypatch.setattr(managed_flavors, "_load", AsyncMock(side_effect=error))
    else:
        monkeypatch.setattr(svc, "_evaluate", AsyncMock(side_effect=error))
    snapshot = await svc.options(SimpleNamespace(), "p1", availability_zone=ZONE)
    assert snapshot.status == "unavailable"
    assert [row.id for row in snapshot.gpu_profiles] == ["render"]
    assert len(snapshot.variants) == 17
    assert variant(snapshot).status == "unavailable"
    assert all(variant(snapshot, "render", count).status == "unavailable" for count in range(1, 17))
    assert all(not row.regions for row in snapshot.variants)
    assert not cloud.candidate_queries()


async def test_snapshot_omits_gpu_models_allocated_only_to_another_domain(cloud, live_options, monkeypatch):
    policy = svc.flavor_automation_policy.load_policy.return_value
    policy["gpu_profiles"] = [profile("own", "CUSTOM_PCI_OWN"), profile("foreign", "CUSTOM_PCI_FOREIGN")]
    monkeypatch.setattr(
        managed_flavors,
        "_pool_projects",
        AsyncMock(
            return_value={
                "p1": {"domain_id": "d1", "active": True, "limits": {"CUSTOM_PCI_OWN": 1}},
                "p2": {"domain_id": "d2", "active": True, "limits": {"CUSTOM_PCI_FOREIGN": -1}},
            }
        ),
    )
    snapshot = await svc.options(SimpleNamespace(), "p1", availability_zone=ZONE)
    assert [row.id for row in snapshot.gpu_profiles] == ["own"]
    assert all(row.gpu_profile_id != "foreign" for row in snapshot.variants)
    assert all(not variant(snapshot, "own", count).regions for count in range(2, 17))
    managed_flavors._pool_projects.assert_awaited_once()


@pytest.mark.parametrize("target", [None, {"domain_id": "d1", "active": False, "limits": {}}])
async def test_missing_or_disabled_target_never_offers_composable_options(cloud, live_options, monkeypatch, target):
    cloud.add_host(ROOT_A)
    cloud.answers[CPU_SHAPE] = [allocation({ROOT_A: ONE})]
    monkeypatch.setattr(managed_flavors, "_pool_projects", AsyncMock(return_value={"p1": target} if target else {}))
    snapshot = await svc.options(SimpleNamespace(), "p1", availability_zone=ZONE)
    assert snapshot.status != "available"
    assert not snapshot.gpu_profiles
    assert all(not row.regions and row.preview is None for row in snapshot.variants)


async def test_unknown_publication_directory_does_not_leak_approved_gpu_catalog(cloud, live_options, monkeypatch):
    svc.flavor_automation_policy.load_policy.return_value["gpu_profiles"] = [profile("foreign")]
    monkeypatch.setattr(managed_flavors, "_pool_projects", AsyncMock(side_effect=ValueError("incomplete")))
    snapshot = await svc.options(SimpleNamespace(), "p1", availability_zone=ZONE)
    assert snapshot.status == "unavailable"
    assert not snapshot.gpu_profiles and not snapshot.variants


async def test_publication_cpu_ceiling_clips_correlated_regions(cloud, live_options, monkeypatch):
    cloud.add_host(ROOT_A, vcpu=(64, 0), ram=(65536, 0))
    cloud.answers[CPU_SHAPE] = [allocation({ROOT_A: ONE})]
    monkeypatch.setattr(
        managed_flavors,
        "_pool_projects",
        AsyncMock(return_value={"p1": {"domain_id": "d1", "active": True, "limits": {"CPU": 5, "MEMORY_MB": 8192}}}),
    )
    row = variant(await svc.options(SimpleNamespace(), "p1", availability_zone=ZONE))
    assert fits(row, 4, 8192)
    assert not fits(row, 6, 8192) and not fits(row, 4, 9216)


async def test_forged_foreign_domain_gpu_save_fails_fresh_publication_guard(composition_native, monkeypatch):
    env = composition_native
    approved = profile("render")
    env.policy["gpu_profiles"] = [approved]
    monkeypatch.setattr(
        managed_flavors,
        "_pool_projects",
        AsyncMock(
            return_value={
                "p1": {"domain_id": "own", "active": True, "limits": {}},
                "foreign": {"domain_id": "other", "active": True, "limits": {approved["resource_class"]: -1}},
            }
        ),
    )
    with pytest.raises(HTTPException, match="publication_denied") as error:
        await svc.save(env.caller, "p1", env.info, request(gpu_profile_id="render", gpu_count=1))
    assert error.value.status_code == 403
    assert not env.compute.events
    assert not env.state["composition_history"] and not env.state["custom_intents"]


@pytest.mark.parametrize("surface", ["consumer", "admin"])
async def test_save_endpoint_waits_for_graph_owner_then_publishes_once(composition_wait, surface):
    env = composition_wait
    coordinates = request(vcpus=6, ram_mb=5120).model_dump()
    task = resume = None
    async with AsyncClient(transport=ASGITransport(app=env.app), base_url="http://test") as client:
        try:
            async with real_graph_lock(env.graph.conn) as holder:
                task = asyncio.create_task(client.post(composition_url(surface), json=coordinates))
                resume = await env.graph.gate.parked()
                assert not task.done()
                assert await env.graph.redis.get(env.graph.key) == holder.owner
                assert await env.graph.redis.zcard(env.graph.queue) == 1
                assert await holder.waiters_pending()
                assert not env.compute.events and not env.saves
            resume.set_result(None)
            response = await asyncio.wait_for(task, timeout=5)
            assert response.status_code == 200, response.text
            fid = response.json()["id"]
            assert response.json()["composition"] == coordinates
            assert [event for event in env.compute.events if event[0] == "create"] == [("create", fid)]
            assert [event for event in env.compute.events if event[0] == "grant"] == [("grant", fid, "p1")]
            assert env.compute.access[fid] == {"p1"}
            assert env.state["custom_intents"] == {fid: coordinates}
            assert env.state["composition_history"] == {svc._actor(env.info, "p1"): [fid]}
            assert len([state for state in env.saves if state["composition_history"]]) == 1
            assert await env.graph.redis.get(env.graph.key) is None
            assert await env.graph.redis.zcard(env.graph.queue) == 0
        finally:
            await finish_queued_save(task, resume)


@pytest.mark.parametrize("surface", ["consumer", "admin"])
async def test_save_endpoint_graph_wait_timeout_has_no_writes(composition_wait, monkeypatch, surface):
    env = composition_wait
    clock = SimpleNamespace(now=100.0)
    monkeypatch.setattr(svc.identity_roles, "time", SimpleNamespace(monotonic=lambda: clock.now))
    task = resume = None
    async with AsyncClient(transport=ASGITransport(app=env.app), base_url="http://test") as client:
        try:
            async with real_graph_lock(env.graph.conn) as holder:
                task = asyncio.create_task(client.post(composition_url(surface), json=request().model_dump()))
                resume = await env.graph.gate.parked()
                assert await holder.waiters_pending()
                clock.now += svc.identity_roles._GRAPH_WAIT_SECONDS + 1
                resume.set_result(None)
                response = await asyncio.wait_for(task, timeout=5)
                assert response.status_code == 409
                assert response.json()["detail"] == "Another role change is in progress"
                assert await env.graph.redis.get(env.graph.key) == holder.owner
                assert await env.graph.redis.zcard(env.graph.queue) == 0
                assert not env.compute.events and not env.saves
                assert env.state["claims"] == env.state["custom_intents"] == env.state["composition_history"] == {}
            assert await env.graph.redis.get(env.graph.key) is None
        finally:
            await finish_queued_save(task, resume)


@pytest.mark.parametrize(
    "change,status",
    [
        ("session_scope", 401),
        ("session_revoked", 401),
        ("native_reader", 403),
        ("native_revoked", 401),
        ("target_disabled", 403),
        ("automation_disabled", 409),
        ("hardware_removed", 409),
        ("publication_removed", 403),
        ("capacity_unavailable", 503),
    ],
)
async def test_queued_save_rechecks_current_authority_and_admission_before_writing(
    composition_wait, monkeypatch, change, status
):
    env = composition_wait
    task = resume = None
    async with AsyncClient(transport=ASGITransport(app=env.app), base_url="http://test") as client:
        try:
            async with real_graph_lock(env.graph.conn) as holder:
                task = asyncio.create_task(client.post(composition_url("consumer"), json=request().model_dump()))
                resume = await env.graph.gate.parked()
                assert await holder.waiters_pending()
                assert not env.compute.events and not env.saves
                if change == "session_scope":
                    env.session["scope_revision"] += 1
                elif change == "session_revoked":
                    env.session.clear()
                elif change == "native_reader":
                    env.native["roles"] = ["reader"]
                elif change == "native_revoked":
                    env.native_error = svc.Unauthorized("revoked")
                elif change == "target_disabled":
                    env.target["enabled"] = False
                elif change == "automation_disabled":
                    env.state["enabled"] = False
                elif change == "hardware_removed":
                    env.policy["hosts"][0]["removed"] = True
                elif change == "publication_removed":
                    env.projects.clear()
                else:
                    monkeypatch.setattr(svc, "_evaluate", AsyncMock(return_value=[]))
            resume.set_result(None)
            response = await asyncio.wait_for(task, timeout=5)
            assert response.status_code == status, response.text
            assert not env.compute.events and not env.saves
            assert env.state["claims"] == env.state["custom_intents"] == env.state["composition_history"] == {}
            assert await env.graph.redis.get(env.graph.key) is None
            assert await env.graph.redis.zcard(env.graph.queue) == 0
        finally:
            await finish_queued_save(task, resume)


async def test_operation_readback_is_exact_private_and_never_replays(composition_native):
    env = composition_native
    operation_id = "e2306567-dc5b-4e38-ae38-304faabbb0a1"
    saved = await svc.save(env.caller, "p1", env.info, request(vcpus=4, ram_mb=12288), operation_id=operation_id)
    before = [event for event in env.compute.events if event[0] in {"create", "spec_write", "grant", "revoke"}]
    resolved = await svc.resolve(env.caller, "p1", env.info, operation_id)
    assert resolved.id == saved.id
    assert resolved.composition == request(vcpus=4, ram_mb=12288).model_dump()
    assert [event for event in env.compute.events if event[0] in {"create", "spec_write", "grant", "revoke"}] == before
    with pytest.raises(HTTPException, match="operation_exists"):
        await svc.save(env.caller, "p1", env.info, request(vcpus=8), operation_id=operation_id)
    with pytest.raises(HTTPException) as foreign:
        await svc.resolve(env.caller, "p1", {**env.info, "user_id": "other"}, operation_id)
    assert foreign.value.status_code == 403
    with pytest.raises(HTTPException) as surface:
        await svc.resolve(env.caller, "p1", env.info, operation_id, admin=True)
    assert surface.value.status_code == 403
    public = managed_flavors._public(env.state, {"policy_ready": True})
    assert "composition_operations" not in public
    assert await svc.resolve(env.caller, "p1", env.info, "49f49980-f3ea-4b6e-a338-234596417427") is None


async def test_operation_readback_requires_durable_publication_after_native_success(composition_native, monkeypatch):
    env = composition_native
    operation_id = "e2306567-dc5b-4e38-ae38-304faabbb0a2"
    persist = managed_flavors._save

    async def lose_history(state, **kwargs):
        if state["composition_history"]:
            raise RuntimeError("post-publication history response lost")
        await persist(state, **kwargs)

    monkeypatch.setattr(managed_flavors, "_save", lose_history)
    with pytest.raises(HTTPException, match="native_outcome_unknown"):
        await svc.save(env.caller, "p1", env.info, request(vcpus=4, ram_mb=12288), operation_id=operation_id)
    assert not env.state["composition_history"]
    assert len(env.compute.rows) == 1
    before = copy.deepcopy(env.state)
    result = await svc.resolve(env.caller, "p1", env.info, operation_id)
    assert result is None  # A lost final SQL commit is not durable publication proof.
    assert len([event for event in env.compute.events if event[0] == "create"]) == 1
    assert env.state == before  # Readback does not repair history or replay publication.


@pytest.mark.parametrize(
    "change", ["session", "permission", "project", "policy", "capacity", "expired", "shape", "acl"]
)
async def test_operation_readback_rejects_stale_authority_or_native_result(composition_wait, monkeypatch, change):
    env = composition_wait
    operation_id = "e2306567-dc5b-4e38-ae38-304faabbb0a3"
    saved = await svc.save(env.caller, "p1", env.info, request(), operation_id=operation_id)
    if change == "session":
        env.session["scope_revision"] += 1
    elif change == "permission":
        env.native["roles"] = ["reader"]
    elif change == "project":
        env.target["enabled"] = False
    elif change == "policy":
        env.policy["hosts"] = []
    elif change == "capacity":
        monkeypatch.setattr(svc, "_evaluate", AsyncMock(return_value=[]))
    elif change == "expired":
        env.state["composition_operations"][operation_id]["expires_at"] = 0
    elif change == "shape":
        env.compute.rows[saved.id].vcpus += 2
    elif change == "acl":
        env.compute.access[saved.id].clear()
    before = [event for event in env.compute.events if event[0] in {"create", "spec_write", "grant", "revoke"}]
    if change in {"expired", "acl"}:
        assert await svc.resolve(env.caller, "p1", env.info, operation_id) is None
    else:
        with pytest.raises(HTTPException):
            await svc.resolve(env.caller, "p1", env.info, operation_id)
    assert [event for event in env.compute.events if event[0] in {"create", "spec_write", "grant", "revoke"}] == before


async def test_operation_receipt_bound_and_expiry_are_fail_closed(composition_native):
    env = composition_native
    operation_id = "e2306567-dc5b-4e38-ae38-304faabbb0a4"
    await svc.save(env.caller, "p1", env.info, request(), operation_id=operation_id)
    receipt = copy.deepcopy(env.state["composition_operations"][operation_id])
    import uuid

    env.state["composition_operations"] = {
        str(uuid.UUID(int=index + 1)): copy.deepcopy(receipt) for index in range(managed_flavors.MAX_HISTORY_ACTORS)
    }
    with pytest.raises(HTTPException, match="operation_limit"):
        await svc.save(env.caller, "p1", env.info, request(), operation_id=operation_id)
    for value in env.state["composition_operations"].values():
        value["expires_at"] = 0
    result = await svc.save(env.caller, "p1", env.info, request(), operation_id=operation_id)
    assert result.id == receipt["flavor_id"]
    assert len(env.state["composition_operations"]) == 1


@pytest.mark.parametrize("gpu", [False, True])
async def test_operation_readback_accepts_only_reconciler_owned_immutable_names(composition_native, gpu):
    env = composition_native
    if gpu:
        env.policy["gpu_profiles"] = [profile()]
    coordinates = request(gpu_profile_id="3060lhr", gpu_count=1) if gpu else request()
    operation_id = "7c42d34a-b3f8-4f69-a3e9-07eaf4fdc222"
    result = await svc.save(env.caller, "p1", env.info, coordinates, operation_id=operation_id)
    shape = svc._shape(env.policy, coordinates.model_dump())
    for name in managed_flavors._immutable_names(shape):
        env.compute.rows[result.id].name = name
        resolved = await svc.resolve(env.caller, "p1", env.info, operation_id)
        assert resolved.id == result.id
    env.compute.rows[result.id].name = "unowned-name-with-same-hardware"
    with pytest.raises(HTTPException, match="native_conflict"):
        await svc.resolve(env.caller, "p1", env.info, operation_id)
