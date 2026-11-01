"""Revisioned administrator approval and explicit stock Nova host lifecycle."""

import copy
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import RuntimeSetting
from app.models.flavor_automation import GpuProfile, PolicyUpdate
from app.services import flavor_automation_policy as svc
from app.services import managed_flavors

GPU = "CUSTOM_PCI_10DE_2208"
AUDIO = "CUSTOM_PCI_10DE_1AEB"


def host():
    return {
        "id": "root",
        "name": "compute-a",
        "removed": False,
        "observed_at": "2026-10-30T00:00:00+00:00",
        "state": "up",
        "status": "enabled",
        "cpu": {"capacity": 8, "min": 1, "step": 1},
        "ram": {"capacity": 65536, "min": 1, "step": 1},
        "gpu": {GPU: 4, AUDIO: 4},
    }


def profile():
    return {
        "name": "3060lhr",
        "display_name": "GeForce 3060 LHR",
        "enabled": True,
        "resource_class": GPU,
        "resource_requirements": {GPU: 1, AUDIO: 1},
        "extra_specs": {"pci_passthrough:alias": "exact-gpu:1,exact-audio:1", "hw:cpu_policy": "shared"},
        "alias_resource_classes": {"exact-gpu": GPU, "exact-audio": AUDIO},
    }


@pytest.fixture
async def environment(monkeypatch, tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'flavor-policy.sqlite'}")
    async with engine.begin() as connection:
        await connection.run_sync(RuntimeSetting.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(svc, "get_session_factory", lambda: factory)
    monkeypatch.setattr(svc, "is_db_available", lambda: True)
    lease = SimpleNamespace(assert_owned=AsyncMock())

    @asynccontextmanager
    async def lock(conn):
        yield lease

    async def call(function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(svc.identity_roles, "_graph_lock", lock)
    monkeypatch.setattr(svc, "run_sync", call)
    monkeypatch.setattr(svc, "_authorize", AsyncMock())
    inventory = {"hosts": [host()], "complete": True, "error": None}
    services = [{"id": "native-service", "host": "compute-a", "binary": "nova-compute", "status": "enabled"}]
    writes = []

    def observe(conn):
        if inventory["error"]:
            raise inventory["error"]
        return copy.deepcopy(inventory["hosts"]), inventory["complete"]

    def disable(conn, service_id):
        writes.append(service_id)
        assert service_id == "native-service"
        services[0]["status"] = "disabled"

    native_services = svc._services
    monkeypatch.setattr(managed_flavors, "supported_hosts", observe)
    monkeypatch.setattr(svc, "_services", lambda conn: copy.deepcopy(services))
    monkeypatch.setattr(svc, "_disable", disable)
    try:
        yield SimpleNamespace(
            factory=factory,
            lease=lease,
            inventory=inventory,
            services=services,
            writes=writes,
            native_services=native_services,
        )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_get_policy_is_side_effect_free_and_never_discovers(admin_client, environment, monkeypatch):
    monkeypatch.setattr(managed_flavors, "supported_hosts", Mock(side_effect=AssertionError("GET cannot discover")))
    for _ in range(2):
        response = await admin_client.get("/api/v1/admin/flavor-automation/policy")
        assert response.status_code == 200 and response.json() == {"revision": 0, "hosts": [], "gpu_profiles": []}
    async with environment.factory() as session:
        assert (await session.scalars(select(RuntimeSetting))).all() == []


@pytest.mark.asyncio
async def test_put_profiles_preserves_hosts_and_rejects_stale_revision(admin_client, environment):
    discovered = await admin_client.post("/api/v1/admin/flavor-automation/discover")
    assert discovered.status_code == 200 and discovered.json()["revision"] == 1
    response = await admin_client.put(
        "/api/v1/admin/flavor-automation/policy", json={"revision": 1, "gpu_profiles": [profile()]}
    )
    assert response.status_code == 200
    result = response.json()
    assert result["revision"] == 2 and result["hosts"] == discovered.json()["hosts"]
    assert result["gpu_profiles"] == [profile()]
    stale = await admin_client.put("/api/v1/admin/flavor-automation/policy", json={"revision": 1, "gpu_profiles": []})
    assert stale.status_code == 409
    assert await svc.load_policy() == result


@pytest.mark.asyncio
async def test_discover_retains_down_missing_failed_and_shrunk_host_inventory(admin_client, environment):
    env = environment
    first = (await admin_client.post("/api/v1/admin/flavor-automation/discover")).json()
    baseline = first["hosts"][0]
    env.inventory["hosts"][0].update(state="down", gpu={})
    down = (await admin_client.post("/api/v1/admin/flavor-automation/discover")).json()
    assert down["hosts"][0]["state"] == "down"
    assert down["hosts"][0]["gpu"] == baseline["gpu"]
    env.inventory["hosts"] = []
    missing = (await admin_client.post("/api/v1/admin/flavor-automation/discover")).json()
    assert missing["hosts"][0]["state"] == "missing" and missing["hosts"][0]["gpu"] == baseline["gpu"]
    env.inventory["error"] = RuntimeError("Placement unavailable")
    failed = (await admin_client.post("/api/v1/admin/flavor-automation/discover")).json()
    assert failed["hosts"][0]["state"] == "unknown" and failed["hosts"][0]["cpu"] == baseline["cpu"]
    env.inventory["error"] = None
    env.inventory["hosts"] = [{**host(), "cpu": {"capacity": 1, "min": 1, "step": 1}}]
    shrunk = (await admin_client.post("/api/v1/admin/flavor-automation/discover")).json()
    assert shrunk["hosts"][0]["cpu"] == baseline["cpu"]
    assert not env.writes


@pytest.mark.asyncio
async def test_explicit_retirement_disables_then_readbacks_and_rediscovery_keeps_tombstone(admin_client, environment):
    first = (await admin_client.post("/api/v1/admin/flavor-automation/discover")).json()
    response = await admin_client.put(
        "/api/v1/admin/flavor-automation/hosts/root", json={"revision": first["revision"], "removed": True}
    )
    assert response.status_code == 200 and response.json()["hosts"][0]["removed"] is True
    assert environment.writes == ["native-service"] and environment.services[0]["status"] == "disabled"
    rediscovered = (await admin_client.post("/api/v1/admin/flavor-automation/discover")).json()
    assert rediscovered["hosts"][0]["removed"] is True
    restored = await admin_client.put(
        "/api/v1/admin/flavor-automation/hosts/root", json={"revision": rediscovered["revision"], "removed": False}
    )
    assert restored.status_code == 200 and restored.json()["hosts"][0]["removed"] is False
    assert environment.services[0]["status"] == "disabled" and environment.writes == ["native-service"]


@pytest.mark.asyncio
async def test_verified_service_absence_allows_retirement_without_native_write(admin_client, environment):
    first = (await admin_client.post("/api/v1/admin/flavor-automation/discover")).json()
    environment.services.clear()
    response = await admin_client.put(
        "/api/v1/admin/flavor-automation/hosts/root", json={"revision": first["revision"], "removed": True}
    )
    assert response.status_code == 200 and response.json()["hosts"][0]["removed"] is True
    assert environment.writes == []


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["directory", "write", "readback"])
async def test_unknown_retirement_preserves_policy_without_replay(admin_client, environment, monkeypatch, failure):
    first = (await admin_client.post("/api/v1/admin/flavor-automation/discover")).json()
    if failure == "directory":
        monkeypatch.setattr(svc, "_services", Mock(side_effect=ValueError("partial directory")))
    elif failure == "write":
        monkeypatch.setattr(svc, "_disable", Mock(side_effect=TimeoutError("unknown native outcome")))
    else:
        monkeypatch.setattr(svc, "_disable", Mock())
    response = await admin_client.put(
        "/api/v1/admin/flavor-automation/hosts/root", json={"revision": first["revision"], "removed": True}
    )
    assert response.status_code == 503
    assert await svc.load_policy() == first
    if failure != "directory":
        svc._disable.assert_called_once()


@pytest.mark.asyncio
async def test_host_unknown_and_stale_revision_never_disable(admin_client, environment):
    await admin_client.post("/api/v1/admin/flavor-automation/discover")
    response = await admin_client.put(
        "/api/v1/admin/flavor-automation/hosts/root", json={"revision": 0, "removed": True}
    )
    assert response.status_code == 409 and not environment.writes
    response = await admin_client.put(
        "/api/v1/admin/flavor-automation/hosts/missing", json={"revision": 1, "removed": True}
    )
    assert response.status_code == 404 and not environment.writes


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,path,body",
    [
        ("get", "/api/v1/admin/flavor-automation/policy", None),
        ("put", "/api/v1/admin/flavor-automation/policy", {"revision": 0, "gpu_profiles": []}),
        ("post", "/api/v1/admin/flavor-automation/discover", None),
        ("put", "/api/v1/admin/flavor-automation/hosts/root", {"revision": 0, "removed": True}),
    ],
)
async def test_policy_routes_require_fresh_system_authority(non_admin_client, method, path, body):
    response = await non_admin_client.request(method, path, **({"json": body} if body else {}))
    assert response.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {"revision": True, "gpu_profiles": []},
        {"revision": -1, "gpu_profiles": []},
        {"revision": 0, "gpu_profiles": [], "hosts": []},
        {"revision": 0, "gpu_profiles": [{**profile(), "extra_specs": {"afterglow:managed_by": "attacker"}}]},
        {"revision": 0, "gpu_profiles": [profile(), profile()]},
        {"revision": 0, "gpu_profiles": [{**profile(), "alias_resource_classes": {}}]},
    ],
)
async def test_policy_endpoint_rejects_malformed_and_ambiguous_approval(admin_client, environment, body):
    assert (await admin_client.put("/api/v1/admin/flavor-automation/policy", json=body)).status_code == 422
    assert await svc.load_policy() == svc._default()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {"revision": True, "removed": True},
        {"revision": 0, "removed": "true"},
        {"revision": 0, "removed": True, "force_down": True},
    ],
)
async def test_host_endpoint_rejects_coercion_or_force_flags(admin_client, environment, body):
    assert (await admin_client.put("/api/v1/admin/flavor-automation/hosts/root", json=body)).status_code == 422
    assert not environment.writes


@pytest.mark.asyncio
async def test_revoked_authority_or_lost_lease_prevents_policy_mutation(environment, monkeypatch):
    before = await svc.load_policy()
    monkeypatch.setattr(svc, "_authorize", AsyncMock(side_effect=[None, HTTPException(403, "revoked")]))
    with pytest.raises(HTTPException) as error:
        await svc.update_profiles(object(), revision=0, gpu_profiles=[profile()], token_info={"user_id": "admin"})
    assert error.value.status_code == 403 and await svc.load_policy() == before
    monkeypatch.setattr(svc, "_authorize", AsyncMock())
    environment.lease.assert_owned.side_effect = HTTPException(409, "lease lost")
    with pytest.raises(HTTPException):
        await svc.discover(object(), token_info={"user_id": "admin"})
    assert await svc.load_policy() == before


@pytest.mark.asyncio
async def test_capabilities_only_project_enabled_explicit_aliases(environment):
    await svc._save({"revision": 1, "hosts": [], "gpu_profiles": [profile()]}, expected_revision=0)
    result = await svc.capabilities()
    assert result["control_scope"] == "afterglow" and result["policy_ready"] is True
    assert "enforcement" not in result
    assert {row["name"]: row["resource_class"] for row in result["pci_aliases"]} == {
        "exact-gpu": GPU,
        "exact-audio": AUDIO,
    }
    assert result["resource_kinds"] == {GPU: "gpu", AUDIO: "companion"}
    disabled = {**profile(), "enabled": False}
    await svc._save({"revision": 2, "hosts": [], "gpu_profiles": [disabled]}, expected_revision=1)
    result = await svc.capabilities()
    assert result["aliases"] == result["pci_aliases"] == result["gpu_profiles"] == []


@pytest.mark.asyncio
async def test_unknown_companion_is_not_reported_as_audio_and_still_accounts_as_companion(environment):
    from app.services import compute_pools

    candidate = profile()
    candidate["extra_specs"]["pci_passthrough:alias"] = "exact-gpu:1,display-controller:1"
    candidate["alias_resource_classes"] = {"exact-gpu": GPU, "display-controller": AUDIO}
    await svc._save({"revision": 1, "hosts": [], "gpu_profiles": [candidate]}, expected_revision=0)

    capabilities = await svc.capabilities()
    companion = next(item for item in capabilities["pci_aliases"] if item["name"] == "display-controller")
    assert companion["is_companion"] is True
    assert companion["is_audio"] is False
    assert compute_pools._resource_kinds(capabilities) == {GPU: "gpu", AUDIO: "companion"}
    demand = await compute_pools.approved_gpu_requirements(candidate["extra_specs"], capabilities)
    assert demand == {GPU: 1}


@pytest.mark.asyncio
async def test_storage_rejects_stale_revision_and_malformed_stored_policy(environment):
    await svc._save({"revision": 1, "hosts": [], "gpu_profiles": []}, expected_revision=0)
    with pytest.raises(HTTPException) as error:
        await svc._save({"revision": 1, "hosts": [host()], "gpu_profiles": []}, expected_revision=0)
    assert error.value.status_code == 409
    async with environment.factory() as session, session.begin():
        from sqlalchemy import update

        await session.execute(
            update(RuntimeSetting)
            .where(RuntimeSetting.setting_key == svc.KEY)
            .values(value_json={"revision": True, "hosts": [], "gpu_profiles": []})
        )
    with pytest.raises(HTTPException) as error:
        await svc.load_policy()
    assert error.value.status_code == 503


@pytest.mark.parametrize(
    "changes",
    [
        {"name": "3060LHR"},
        {"resource_requirements": {GPU: 2}},
        {"resource_requirements": {GPU: True}},
        {"extra_specs": {"pci_passthrough:alias": "exact-gpu:0"}},
        {"extra_specs": {"pci_passthrough:alias": "exact-gpu:1,exact-gpu:1"}},
        {"extra_specs": {"resources1:" + GPU: "2"}},
        {"extra_specs": {"afterglow:frontend_visible": "true"}},
        {"extra_specs": {"pci_passthrough:alias": "exact-gpu:1,exact-audio:2"}},
        {"alias_resource_classes": {"exact-gpu": AUDIO, "exact-audio": GPU, "extra": GPU}},
    ],
)
def test_strict_profile_rejects_ambiguous_counts_and_protected_keys(changes):
    with pytest.raises(ValidationError):
        GpuProfile.model_validate({**profile(), **changes})


def test_single_alias_single_resource_mapping_is_unique_not_name_inference():
    value = {
        **profile(),
        "resource_requirements": {GPU: 1},
        "extra_specs": {"pci_passthrough:alias": "unrelated-exact-native-name:1"},
        "alias_resource_classes": {},
    }
    approved = GpuProfile.model_validate(value).model_dump()
    assert approved["alias_resource_classes"] == {"unrelated-exact-native-name": GPU}


def test_conflicting_primary_and_companion_identities_are_rejected():
    other = {
        **profile(),
        "name": "audio-as-gpu",
        "resource_class": AUDIO,
        "resource_requirements": {AUDIO: 1},
        "extra_specs": {"pci_passthrough:alias": "audio-as-gpu:1"},
        "alias_resource_classes": {"audio-as-gpu": AUDIO},
    }
    with pytest.raises(ValidationError):
        PolicyUpdate.model_validate({"revision": 0, "gpu_profiles": [profile(), other]})


def test_stock_disable_uses_bounded_nonreplaying_update_transport():
    calls = []

    def request(url, method, **kwargs):
        calls.append((url, method, kwargs))
        return SimpleNamespace(status_code=200)

    conn = SimpleNamespace(
        compute=SimpleNamespace(get_endpoint=lambda: "https://nova.invalid/v2.1"),
        session=SimpleNamespace(request=request),
    )
    svc._disable(conn, "service-id")
    assert len(calls) == 1
    url, method, kwargs = calls[0]
    assert url == "https://nova.invalid/v2.1/os-services/service-id" and method == "PUT"
    assert kwargs["json"] == {"status": "disabled"}
    assert kwargs["allow_reauth"] is kwargs["redirect"] is False
    assert kwargs["connect_retries"] == kwargs["status_code_retries"] == 0
    assert kwargs["headers"]["OpenStack-API-Version"] == "compute 2.53"


@pytest.mark.parametrize("invalid", ["pagination", "duplicate", "binary", "unknown-status", "partial-cell"])
def test_service_absence_requires_complete_unambiguous_native_directory(invalid):

    service = {"id": "native-service", "host": "compute-a", "binary": "nova-compute", "status": "enabled"}
    body = {"services": [service]}
    if invalid == "pagination":
        body["links"] = {"next": "more-services"}
    elif invalid == "duplicate":
        body["services"].append(dict(service))
    elif invalid == "binary":
        service["binary"] = "nova-scheduler"
    elif invalid == "partial-cell":
        body["services"] = [{"binary": "nova-compute", "host": "compute-a", "status": "UNKNOWN"}]
    else:
        service["status"] = "unknown"

    def request(url, method, **kwargs):
        assert method == "GET" and kwargs["headers"]["OpenStack-API-Version"] == "compute 2.69"
        return SimpleNamespace(status_code=200, json=lambda: body)

    conn = SimpleNamespace(
        compute=SimpleNamespace(get_endpoint=lambda: "https://nova.invalid/v2.1"),
        session=SimpleNamespace(request=request),
    )
    with pytest.raises(ValueError):
        svc._services(conn)


@pytest.mark.asyncio
async def test_storage_readback_mismatch_is_not_acknowledged(environment, monkeypatch):
    original = svc.load_policy
    calls = 0

    async def stale_readback():
        nonlocal calls
        calls += 1
        return svc._default()

    monkeypatch.setattr(svc, "load_policy", stale_readback)
    with pytest.raises(HTTPException) as error:
        await svc._save({"revision": 1, "hosts": [], "gpu_profiles": []}, expected_revision=0)
    assert error.value.status_code == 503 and calls == 1
    monkeypatch.setattr(svc, "load_policy", original)
    assert (await svc.load_policy())["revision"] == 1


def test_duplicate_aliases_cannot_map_different_physical_resources():
    other = {
        **profile(),
        "name": "4090",
        "resource_class": "CUSTOM_PCI_10DE_2684",
        "resource_requirements": {"CUSTOM_PCI_10DE_2684": 1, AUDIO: 1},
        "alias_resource_classes": {"exact-gpu": "CUSTOM_PCI_10DE_2684", "exact-audio": AUDIO},
    }
    with pytest.raises(ValidationError):
        PolicyUpdate.model_validate({"revision": 0, "gpu_profiles": [profile(), other]})


def test_shared_companion_alias_requires_identical_explicit_resource_identity():
    first = profile()
    other = {
        **profile(),
        "name": "4090",
        "resource_class": "CUSTOM_PCI_10DE_2684",
        "resource_requirements": {"CUSTOM_PCI_10DE_2684": 1, AUDIO: 1},
        "extra_specs": {"pci_passthrough:alias": "4090:1,exact-audio:1"},
        "alias_resource_classes": {"4090": "CUSTOM_PCI_10DE_2684", "exact-audio": AUDIO},
    }
    result = PolicyUpdate.model_validate({"revision": 0, "gpu_profiles": [first, other]})
    assert len(result.gpu_profiles) == 2


@pytest.mark.asyncio
async def test_first_discovery_failure_does_not_publish_empty_success(admin_client, environment):
    environment.inventory["error"] = RuntimeError("Nova directory unavailable")
    response = await admin_client.post("/api/v1/admin/flavor-automation/discover")
    assert response.status_code == 503 and await svc.load_policy() == svc._default()


@pytest.mark.asyncio
async def test_timestamp_only_observations_do_not_write_or_advance_editor_revision(
    admin_client, environment, monkeypatch
):
    first = (await admin_client.post("/api/v1/admin/flavor-automation/discover")).json()
    original_save = svc._save
    saved = AsyncMock(wraps=original_save)
    monkeypatch.setattr(svc, "_save", saved)
    environment.inventory["hosts"][0]["observed_at"] = "2026-10-30T00:01:00+00:00"
    second = (await admin_client.post("/api/v1/admin/flavor-automation/discover")).json()
    assert second == first
    assert second["revision"] == 1
    saved.assert_not_awaited()


@pytest.mark.asyncio
async def test_partial_down_cell_directory_cannot_retire_missing_host(
    admin_client, environment, monkeypatch, mock_conn
):
    first = (await admin_client.post("/api/v1/admin/flavor-automation/discover")).json()
    monkeypatch.setattr(svc, "_services", environment.native_services)
    mock_conn.compute.get_endpoint.return_value = "https://nova.invalid/v2.1"
    mock_conn.session.request.return_value = SimpleNamespace(
        status_code=200,
        json=lambda: {"services": [{"binary": "nova-compute", "host": "compute-a", "status": "UNKNOWN"}]},
    )
    response = await admin_client.put(
        "/api/v1/admin/flavor-automation/hosts/root", json={"revision": first["revision"], "removed": True}
    )
    assert response.status_code == 503 and await svc.load_policy() == first


def test_alias_and_explicit_native_resources_cannot_double_request_same_gpu():
    value = profile()
    value["extra_specs"].update({"resources:" + GPU: "1", "resources:" + AUDIO: "1"})
    with pytest.raises(ValidationError, match="overlap"):
        GpuProfile.model_validate(value)


def test_explicit_only_companion_request_does_not_authorize_missing_native_attachment():
    value = profile()
    value["extra_specs"] = {"pci_passthrough:alias": "exact-gpu:1", "resources:" + AUDIO: "1"}
    value["alias_resource_classes"] = {"exact-gpu": GPU}
    with pytest.raises(ValidationError, match="attachment alias"):
        GpuProfile.model_validate(value)


@pytest.mark.parametrize("missing", ["primary", "companion", "both"])
def test_all_physical_resources_require_alias_attachment_not_only_placement_reservation(missing):
    value = profile()
    if missing == "both":
        value["extra_specs"] = {"resources:" + GPU: "1", "resources:" + AUDIO: "1"}
        value["alias_resource_classes"] = {}
    elif missing == "primary":
        value["extra_specs"] = {"resources:" + GPU: "1", "pci_passthrough:alias": "exact-audio:1"}
        value["alias_resource_classes"] = {"exact-audio": AUDIO}
    else:
        value["extra_specs"] = {"pci_passthrough:alias": "exact-gpu:1"}
        value["alias_resource_classes"] = {"exact-gpu": GPU}
    with pytest.raises(ValidationError, match="attachment alias"):
        GpuProfile.model_validate(value)


@pytest.mark.asyncio
async def test_pcpu_inventory_is_retained_across_disappearance_and_physical_shrink(environment, admin_client):
    environment.inventory["hosts"][0]["pcpu"] = {"capacity": 8, "min": 1, "step": 1}
    first = (await admin_client.post("/api/v1/admin/flavor-automation/discover")).json()
    environment.inventory["hosts"][0]["pcpu"]["capacity"] = 1
    shrunk = (await admin_client.post("/api/v1/admin/flavor-automation/discover")).json()
    assert shrunk["hosts"][0]["pcpu"] == first["hosts"][0]["pcpu"]
    environment.inventory["hosts"][0].pop("pcpu")
    missing = (await admin_client.post("/api/v1/admin/flavor-automation/discover")).json()
    assert missing["hosts"][0]["pcpu"] == first["hosts"][0]["pcpu"]


def test_optional_pcpu_is_validated_and_never_inferred_from_virtual_inventory():
    policy = {"revision": 0, "hosts": [host()], "gpu_profiles": []}
    assert "pcpu" not in svc._validated(policy)["hosts"][0]
    policy["hosts"][0]["pcpu"] = {"capacity": True, "min": 1, "step": 1}
    with pytest.raises(HTTPException) as error:
        svc._validated(policy)
    assert error.value.status_code == 503
