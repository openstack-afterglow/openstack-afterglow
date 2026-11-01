"""Native owned profiles cannot be manually converted or granted out of pool."""

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from fastapi import HTTPException


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,suffix,body",
    [
        ("delete", "", None),
        ("put", "/frontend-visibility", {"visible": True}),
        ("post", "/extra-specs", {"key": "pci_passthrough:alias", "value": ""}),
        ("delete", "/extra-specs/afterglow:managed_by", None),
        ("post", "/access", {"project_id": "other-domain-project"}),
        ("delete", "/access/project-a", None),
    ],
)
async def test_manual_endpoints_deny_managed_flavor_before_native_write(admin_client, mock_conn, method, suffix, body):
    mock_conn.compute.get_flavor.return_value = SimpleNamespace(
        id="managed", extra_specs={"afterglow:managed_by": "domain-compute-v1"}
    )
    response = await admin_client.request(method, "/api/v1/admin/flavors/managed" + suffix, json=body)
    assert response.status_code == 409
    assert response.json()["detail"] == "managed_flavor_owned_by_automation"
    mock_conn.compute.delete_flavor.assert_not_called()
    mock_conn.compute.create_flavor_extra_specs.assert_not_called()
    mock_conn.compute.delete_flavor_extra_specs_property.assert_not_called()
    mock_conn.session.post.assert_not_called()


@pytest.mark.asyncio
async def test_unknown_flavor_metadata_does_not_allow_access_write(admin_client, mock_conn):
    mock_conn.compute.get_flavor.side_effect = RuntimeError("provider unreadable")
    response = await admin_client.post("/api/v1/admin/flavors/unknown/access", json={"project_id": "project-a"})
    assert response.status_code == 503
    mock_conn.session.post.assert_not_called()


@pytest.mark.asyncio
async def test_private_managed_create_claim_is_locked_before_marker_publication(admin_client, mock_conn):
    mock_conn.compute.get_flavor.return_value = SimpleNamespace(
        id="staged",
        description="afterglow:domain-compute-v1:owned-claim",
        extra_specs={},
    )
    response = await admin_client.post("/api/v1/admin/flavors/staged/access", json={"project_id": "project-a"})
    assert response.status_code == 409
    mock_conn.session.post.assert_not_called()


@pytest.mark.asyncio
async def test_manual_mutation_cannot_enter_active_reconcile_lease(admin_client, mock_conn):
    from app.services.identity_roles import _graph_lock

    mock_conn.compute.get_flavor.return_value = SimpleNamespace(
        id="manual", description="", extra_specs={"os:name": "Linux"}
    )
    async with _graph_lock(mock_conn):
        response = await admin_client.post("/api/v1/admin/flavors/manual/access", json={"project_id": "project-a"})
    assert response.status_code == 409
    mock_conn.session.post.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["ownership_read", "dispatch", "worker_entry"])
@pytest.mark.parametrize(
    ("method", "suffix", "body"),
    [
        ("delete", "", None),
        ("put", "/frontend-visibility", {"visible": True}),
        ("post", "/extra-specs", {"key": "hw:cpu_policy", "value": "shared"}),
        ("delete", "/extra-specs/hw:cpu_policy", None),
        ("post", "/access", {"project_id": "project-a"}),
        ("delete", "/access/project-a", None),
    ],
)
async def test_manual_writes_stop_when_graph_lease_expires(
    admin_client, mock_conn, monkeypatch, stage, method, suffix, body
):
    from app.services import identity_roles

    class Lease:
        lost = False
        calls = 0

        async def assert_owned(self):
            self.calls += 1
            if stage == "dispatch" and self.calls == 2:
                self.lost = True
            if self.lost:
                raise HTTPException(409, "lease lost")
            if stage == "worker_entry" and self.calls == 2:
                self.lost = True

    lease = Lease()

    @asynccontextmanager
    async def graph_lock(_conn):
        yield lease

    def read_flavor(_fid):
        if stage == "ownership_read":
            lease.lost = True
        return SimpleNamespace(id="manual", description="", extra_specs={})

    monkeypatch.setattr(identity_roles, "_graph_lock", graph_lock)
    mock_conn.compute.get_flavor.side_effect = read_flavor
    response = await admin_client.request(method, "/api/v1/admin/flavors/manual" + suffix, json=body)
    assert response.status_code == 409
    mock_conn.compute.delete_flavor.assert_not_called()
    mock_conn.compute.create_flavor_extra_specs.assert_not_called()
    mock_conn.compute.delete_flavor_extra_specs_property.assert_not_called()
    mock_conn.session.post.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["visibility", "grant", "revoke"])
async def test_manual_provider_setup_cannot_dispatch_after_redis_owner_changes(
    admin_client, mock_conn, monkeypatch, mode
):
    from app.services import identity_roles

    class Lease:
        lost = False  # Renewal has not noticed the owner replacement yet.
        owner = "initial"

        async def assert_owned(self):
            if self.owner != "initial":
                raise HTTPException(409, "lease owner changed")

    lease = Lease()
    reads = 0

    @asynccontextmanager
    async def graph_lock(_conn):
        yield lease

    def read_flavor(_fid):
        nonlocal reads
        reads += 1
        if mode == "visibility" and reads == 2:
            lease.owner = "replacement"
        return SimpleNamespace(id="manual", description="", extra_specs={})

    def endpoint():
        lease.owner = "replacement"
        return "https://unreachable.invalid"

    monkeypatch.setattr(identity_roles, "_graph_lock", graph_lock)
    mock_conn.compute.get_flavor.side_effect = read_flavor
    mock_conn.compute.get_endpoint.side_effect = endpoint
    if mode == "visibility":
        response = await admin_client.put("/api/v1/admin/flavors/manual/frontend-visibility", json={"visible": True})
    elif mode == "grant":
        response = await admin_client.post("/api/v1/admin/flavors/manual/access", json={"project_id": "p"})
    else:
        response = await admin_client.delete("/api/v1/admin/flavors/manual/access/p")
    assert response.status_code == 409
    assert lease.lost is False
    mock_conn.compute.create_flavor_extra_specs.assert_not_called()
    mock_conn.session.post.assert_not_called()
