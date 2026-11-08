"""Per-domain VPN reserved ranges: validation, overlap, persistence, authorization and enforcement."""

from __future__ import annotations

import ipaddress
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app import database
from app.api.deps import get_token_info
from app.main import app
from app.models.domain_network_policy import DomainNetworkPolicy
from app.services import vpn_reserved_ranges as svc
from app.services.vpn_reserved_ranges import VPN_RESERVED_CIDR, VpnReservedCidrError
from tests.conftest import make_token_info

# Captured at import, before the autouse in-memory store replaces the readers.
_DB_STORED_ROW = svc._stored_row
_DB_STORED_RANGE_LISTS = svc._stored_range_lists


def _nets(*values: str):
    return [ipaddress.ip_network(value) for value in values]


# ── validation matrix ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ([], []),
        (["10.8.0.0/24"], ["10.8.0.0/24"]),
        (["10.8.0.1/24"], ["10.8.0.0/24"]),  # host bits are canonicalized
        ([" 10.9.0.0/16 "], ["10.9.0.0/16"]),
        (["10.8.0.0/24", "10.8.0.5/24", "10.8.0.0/24"], ["10.8.0.0/24"]),  # deduplicated, order kept
        (["2001:DB8::/48"], ["2001:db8::/48"]),
        (["10.0.0.0/8", "2001:db8::/32"], ["10.0.0.0/8", "2001:db8::/32"]),
        (["192.0.2.7/32", "2001:db8::1/128"], ["192.0.2.7/32", "2001:db8::1/128"]),
        ([f"10.{index}.0.0/16" for index in range(16)], [f"10.{index}.0.0/16" for index in range(16)]),
    ],
)
def test_normalize_accepts_and_canonicalizes(values, expected):
    assert svc.normalize_ranges(values) == expected


@pytest.mark.parametrize(
    "values",
    [
        "10.8.0.0/24",
        None,
        [f"10.{index}.0.0/16" for index in range(17)],
        ["0.0.0.0/0"],
        ["::/0"],
        ["10.0.0.0/7"],
        ["2001:db8::/31"],
        ["10.8.0.1"],  # a bare address is not a range
        ["not-a-cidr/24"],
        ["10.8.0.0/33"],
        [24],
        ["1" * 70 + "/24"],
    ],
)
def test_normalize_rejects_with_stable_code(values):
    with pytest.raises(HTTPException) as raised:
        svc.normalize_ranges(values)
    assert raised.value.status_code == 422
    assert raised.value.detail["code"] == "vpn_reserved_ranges_invalid"


# ── overlap matrix ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("reserved", "cidr"),
    [
        (["10.8.0.0/24"], "10.8.0.0/24"),  # exact
        (["10.8.0.0/24"], "10.8.0.128/25"),  # contained
        (["10.8.0.0/24"], "10.8.0.0/16"),  # containing
        (["10.8.0.0/24"], "10.0.0.0/8"),  # containing (wide)
        (["10.8.0.0/24", "172.31.0.0/16"], "172.31.4.0/24"),  # second range
        (["10.8.0.0/24"], "10.8.0.7/24"),  # non-canonical request is still checked
        (["2001:db8:8::/48"], "2001:db8:8::/64"),  # IPv6 contained
        (["2001:db8:8::/48"], "2001:db8::/32"),  # IPv6 containing
    ],
)
def test_overlapping_cidr_is_refused(reserved, cidr):
    with pytest.raises(VpnReservedCidrError) as raised:
        svc.assert_outside(_nets(*reserved), cidr=cidr)
    assert str(raised.value).startswith(f"{VPN_RESERVED_CIDR}: ")


@pytest.mark.parametrize(
    ("reserved", "cidr"),
    [
        (["10.8.0.0/24"], "10.8.1.0/24"),  # adjacent above
        (["10.8.0.0/24"], "10.7.255.0/24"),  # adjacent below
        (["10.8.0.0/24"], "192.168.0.0/24"),
        (["2001:db8:8::/48"], "2001:db8:9::/48"),  # IPv6 adjacent
        (["10.8.0.0/24"], "::ffff:0:0/96"),  # other family never collides
        ([], "10.8.0.0/24"),  # domain opted out
    ],
)
def test_non_overlapping_cidr_is_allowed(reserved, cidr):
    svc.assert_outside(_nets(*reserved), cidr=cidr)


def test_gateway_inside_reserved_range_is_refused_and_outside_allowed():
    reserved = _nets("10.8.0.0/24", "2001:db8:8::/48")
    for gateway in ("10.8.0.1", "10.8.0.255", "2001:db8:8::1"):
        with pytest.raises(VpnReservedCidrError):
            svc.assert_outside(reserved, gateway_ip=gateway)
    for gateway in ("10.8.1.1", "10.7.255.255", "2001:db8:9::1"):
        svc.assert_outside(reserved, gateway_ip=gateway)


@pytest.mark.parametrize(
    ("kwargs", "code"), [({"cidr": "bad"}, "subnet_cidr_invalid"), ({"gateway_ip": "x"}, "subnet_gateway_invalid")]
)
async def test_malformed_request_fails_closed(kwargs, code):
    with pytest.raises(HTTPException) as raised:
        await svc.require_domain_subnet_allowed("default", **kwargs)
    assert raised.value.status_code == 422 and raised.value.detail["code"] == code


# ── persistence (real SQLite schema) ────────────────────────────────────────


@pytest.fixture
async def db(monkeypatch, tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'vpn-reserved.sqlite'}")
    async with engine.begin() as connection:
        await connection.run_sync(DomainNetworkPolicy.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, "is_db_available", lambda: True)
    monkeypatch.setattr(database, "get_session_factory", lambda: factory)
    monkeypatch.setattr(svc, "_stored_row", _DB_STORED_ROW)
    monkeypatch.setattr(svc, "_stored_range_lists", _DB_STORED_RANGE_LISTS)
    try:
        yield factory
    finally:
        await engine.dispose()


async def test_absent_policy_reports_documented_default(db):
    view = await svc.policy_view("domain-a")
    assert view == {
        "domain_id": "domain-a",
        "vpn_reserved_cidrs": ["10.8.0.0/24"],
        "default_vpn_reserved_cidrs": ["10.8.0.0/24"],
        "revision": 0,
        "configured": False,
        "max_ranges": 16,
    }
    assert await svc.domain_reserved_networks("domain-a") == _nets("10.8.0.0/24")


async def test_update_persists_canonical_list_with_revision_fence(db):
    saved = await svc.update_policy(
        "domain-a",
        actor_user_id="manager",
        cidrs=["10.20.0.1/16", "10.20.0.0/16", "2001:db8::/48"],
        expected_revision=0,
    )
    assert saved["vpn_reserved_cidrs"] == ["10.20.0.0/16", "2001:db8::/48"]
    assert saved["revision"] == 1 and saved["configured"] is True
    async with db() as session:
        row = await session.get(DomainNetworkPolicy, "domain-a")
        assert row.vpn_reserved_cidrs == ["10.20.0.0/16", "2001:db8::/48"] and row.updated_by_user_id == "manager"
    with pytest.raises(HTTPException) as raised:
        await svc.update_policy("domain-a", actor_user_id="manager", cidrs=[], expected_revision=0)
    assert raised.value.status_code == 409 and raised.value.detail["code"] == "revision_conflict"
    emptied = await svc.update_policy("domain-a", actor_user_id="admin", cidrs=[], expected_revision=1)
    assert emptied["vpn_reserved_cidrs"] == [] and emptied["revision"] == 2
    assert await svc.domain_reserved_networks("domain-a") == []


async def test_domain_isolation_and_platform_union(db):
    await svc.update_policy("domain-a", actor_user_id="m", cidrs=["172.31.0.0/16"], expected_revision=0)
    assert await svc.domain_reserved_networks("domain-a") == _nets("172.31.0.0/16")
    assert await svc.domain_reserved_networks("domain-b") == _nets("10.8.0.0/24")
    assert (await svc.policy_view("domain-b"))["configured"] is False
    assert set(await svc.platform_reserved_networks()) == set(_nets("10.8.0.0/24", "172.31.0.0/16"))


async def test_storage_failure_fails_closed(monkeypatch):
    monkeypatch.setattr(svc, "_stored_row", _DB_STORED_ROW)
    monkeypatch.setattr(database, "is_db_available", lambda: False)
    with pytest.raises(HTTPException) as raised:
        await svc.require_domain_subnet_allowed("domain-a", cidr="192.168.0.0/24")
    assert raised.value.status_code == 503 and raised.value.detail["code"] == "vpn_reserved_ranges_unavailable"


async def test_unknown_project_domain_fails_closed():
    with pytest.raises(HTTPException) as raised:
        await svc.require_domain_subnet_allowed("", cidr="192.168.0.0/24")
    assert raised.value.status_code == 503


async def test_corrupt_stored_policy_fails_closed(_vpn_reserved_ranges_store):
    _vpn_reserved_ranges_store["domain-a"] = {"vpn_reserved_cidrs": ["0.0.0.0/0"], "revision": 1}
    with pytest.raises(HTTPException) as raised:
        await svc.require_domain_subnet_allowed("domain-a", cidr="192.168.0.0/24")
    assert raised.value.status_code == 503


# ── API authorization ───────────────────────────────────────────────────────


@asynccontextmanager
async def _identity(monkeypatch, *, domain_id="domain-a", manager=True, admin=False):
    from app.services import domain_scope

    monkeypatch.setattr(
        domain_scope,
        "domain_context",
        lambda user_id, domain, **_: {"domain_id": domain, "is_domain_manager": manager, "is_system_admin": admin},
    )
    previous = app.dependency_overrides.copy()
    token = make_token_info(domain_id=domain_id, is_system_admin=admin, roles=["admin"] if admin else ["member"])
    app.dependency_overrides[get_token_info] = lambda: token
    try:
        yield
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


async def test_domain_manager_reads_and_updates_only_own_domain(client, db, monkeypatch):
    async with _identity(monkeypatch, domain_id="domain-a"):
        view = await client.get("/api/v1/iam/vpn-reserved-ranges")
        assert view.status_code == 200, view.text
        assert view.json()["domain_id"] == "domain-a" and view.json()["vpn_reserved_cidrs"] == ["10.8.0.0/24"]
        assert view.headers["cache-control"].startswith("no-store")
        saved = await client.put(
            "/api/v1/iam/vpn-reserved-ranges", json={"vpn_reserved_cidrs": ["10.30.0.0/16"], "revision": 0}
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["vpn_reserved_cidrs"] == ["10.30.0.0/16"] and saved.json()["revision"] == 1
        # The body cannot name another domain.
        smuggled = await client.put(
            "/api/v1/iam/vpn-reserved-ranges",
            json={"vpn_reserved_cidrs": [], "revision": 1, "domain_id": "domain-b"},
        )
        assert smuggled.status_code == 422
        invalid = await client.put(
            "/api/v1/iam/vpn-reserved-ranges", json={"vpn_reserved_cidrs": ["0.0.0.0/0"], "revision": 1}
        )
        assert invalid.status_code == 422 and invalid.json()["detail"]["code"] == "vpn_reserved_ranges_invalid"
        stale = await client.put("/api/v1/iam/vpn-reserved-ranges", json={"vpn_reserved_cidrs": [], "revision": 0})
        assert stale.status_code == 409 and stale.json()["detail"]["code"] == "revision_conflict"
    async with _identity(monkeypatch, domain_id="domain-b"):
        other = await client.get("/api/v1/iam/vpn-reserved-ranges")
        assert other.json()["domain_id"] == "domain-b" and other.json()["vpn_reserved_cidrs"] == ["10.8.0.0/24"]
    assert await svc.domain_reserved_networks("domain-a") == _nets("10.30.0.0/16")


async def test_non_manager_cannot_read_or_update(client, db, monkeypatch):
    async with _identity(monkeypatch, manager=False):
        assert (await client.get("/api/v1/iam/vpn-reserved-ranges")).status_code == 403
        denied = await client.put("/api/v1/iam/vpn-reserved-ranges", json={"vpn_reserved_cidrs": [], "revision": 0})
        assert denied.status_code == 403
    assert (await svc.policy_view("domain-a"))["configured"] is False


async def test_admin_domain_routes_require_system_admin(client, db):
    assert (await client.get("/api/v1/admin/domains/domain-a/vpn-reserved-ranges")).status_code == 403
    denied = await client.put(
        "/api/v1/admin/domains/domain-a/vpn-reserved-ranges", json={"vpn_reserved_cidrs": [], "revision": 0}
    )
    assert denied.status_code == 403
    assert (await svc.policy_view("domain-a"))["configured"] is False


async def test_system_admin_edits_any_existing_domain(admin_client, mock_conn, db):
    mock_conn.identity.get_domain.side_effect = lambda domain_id: (
        SimpleNamespace(id=domain_id) if domain_id == "domain-b" else None
    )
    saved = await admin_client.put(
        "/api/v1/admin/domains/domain-b/vpn-reserved-ranges",
        json={"vpn_reserved_cidrs": ["10.8.0.0/24", "10.9.0.0/24"], "revision": 0},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["domain_id"] == "domain-b" and saved.json()["revision"] == 1
    view = await admin_client.get("/api/v1/admin/domains/domain-b/vpn-reserved-ranges")
    assert view.json()["vpn_reserved_cidrs"] == ["10.8.0.0/24", "10.9.0.0/24"]
    missing = await admin_client.put(
        "/api/v1/admin/domains/missing/vpn-reserved-ranges", json={"vpn_reserved_cidrs": [], "revision": 0}
    )
    assert missing.status_code == 404
    assert (await svc.policy_view("missing"))["configured"] is False


# ── enforcement: tenant REST ────────────────────────────────────────────────


def _subnet(**overrides):
    values = {
        "id": "subnet-1",
        "name": "s",
        "cidr": "192.168.10.0/24",
        "gateway_ip": None,
        "ip_version": 4,
        "is_dhcp_enabled": True,
        "project_id": "test-project-123",
    }
    return SimpleNamespace(**{**values, **overrides})


def _assert_refused(response, reserved="10.8.0.0/24"):
    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["code"] == VPN_RESERVED_CIDR and detail["reserved_cidr"] == reserved


@pytest.mark.parametrize("cidr", ["10.8.0.0/24", "10.8.0.64/26", "10.8.0.0/16"])
async def test_tenant_network_with_reserved_subnet_creates_nothing(client, mock_conn, cidr):
    response = await client.post("/api/v1/networks", json={"name": "n", "subnet": {"cidr": cidr}})
    _assert_refused(response)
    mock_conn.network.create_network.assert_not_called()
    mock_conn.network.create_subnet.assert_not_called()


async def test_tenant_subnet_create_refuses_reserved_and_allows_adjacent(client, mock_conn):
    refused = await client.post("/api/v1/networks/net-1/subnets", json={"name": "s", "cidr": "10.8.0.0/25"})
    _assert_refused(refused)
    mock_conn.network.create_subnet.assert_not_called()
    mock_conn.network.create_subnet.return_value = _subnet(cidr="10.8.1.0/24")
    allowed = await client.post("/api/v1/networks/net-1/subnets", json={"name": "s", "cidr": "10.8.1.0/24"})
    assert allowed.status_code == 201, allowed.text
    mock_conn.network.create_subnet.assert_called_once()


async def test_tenant_subnet_create_refuses_malformed_cidr_before_native(client, mock_conn):
    response = await client.post("/api/v1/networks/net-1/subnets", json={"name": "s", "cidr": "10.8/16"})
    assert response.status_code == 422 and response.json()["detail"]["code"] == "subnet_cidr_invalid"
    mock_conn.network.create_subnet.assert_not_called()


async def test_tenant_enforcement_uses_only_the_project_domain(client, mock_conn, _vpn_reserved_ranges_store):
    mock_conn.network.create_subnet.return_value = _subnet()
    _vpn_reserved_ranges_store["other-domain"] = {"vpn_reserved_cidrs": ["192.168.10.0/24"], "revision": 1}
    allowed = await client.post("/api/v1/networks/net-1/subnets", json={"name": "s", "cidr": "192.168.10.0/24"})
    assert allowed.status_code == 201, allowed.text
    _vpn_reserved_ranges_store["default"] = {"vpn_reserved_cidrs": ["192.168.10.0/24"], "revision": 1}
    refused = await client.post("/api/v1/networks/net-1/subnets", json={"name": "s", "cidr": "192.168.10.0/24"})
    _assert_refused(refused, "192.168.10.0/24")
    # The domain replaced the default list, so the Waygate default range is usable again.
    mock_conn.network.create_subnet.return_value = _subnet(cidr="10.8.0.0/24")
    reopened = await client.post("/api/v1/networks/net-1/subnets", json={"name": "s", "cidr": "10.8.0.0/24"})
    assert reopened.status_code == 201
    assert mock_conn.network.create_subnet.call_count == 2


async def test_tenant_subnet_update_gateway_change_is_checked_but_other_edits_allowed(client, mock_conn):
    # A pre-existing overlapping subnet stays usable; it is never modified by the policy.
    mock_conn.network.get_subnet.return_value = _subnet(cidr="10.8.0.0/24", gateway_ip="10.8.0.1")
    mock_conn.network.update_subnet.return_value = _subnet(cidr="10.8.0.0/24", gateway_ip="10.8.0.1", name="renamed")
    refused = await client.put("/api/v1/networks/subnets/subnet-1", json={"gateway_ip": "10.8.0.254"})
    _assert_refused(refused)
    mock_conn.network.update_subnet.assert_not_called()
    renamed = await client.put(
        "/api/v1/networks/subnets/subnet-1", json={"name": "renamed", "enable_dhcp": False, "gateway_ip": "10.8.0.1"}
    )
    assert renamed.status_code == 200, renamed.text
    mock_conn.network.update_subnet.assert_called_once()


# ── enforcement: admin REST (provider networks) ─────────────────────────────


async def test_admin_provider_network_refuses_any_domain_reserved_range(
    admin_client, mock_conn, _vpn_reserved_ranges_store
):
    _vpn_reserved_ranges_store["domain-b"] = {"vpn_reserved_cidrs": ["172.31.0.0/16"], "revision": 1}
    for cidr, reserved in (("10.8.0.0/24", "10.8.0.0/24"), ("172.31.5.0/24", "172.31.0.0/16")):
        response = await admin_client.post(
            "/api/v1/admin/networks", json={"name": "provider", "is_external": True, "is_shared": True, "cidr": cidr}
        )
        _assert_refused(response, reserved)
    mock_conn.network.create_network.assert_not_called()
    mock_conn.network.create_subnet.assert_not_called()
    mock_conn.network.create_network.return_value = SimpleNamespace(
        id="net-p", name="provider", status="ACTIVE", is_router_external=True, is_shared=True, subnet_ids=[]
    )
    allowed = await admin_client.post(
        "/api/v1/admin/networks", json={"name": "provider", "is_external": True, "cidr": "203.0.113.0/24"}
    )
    assert allowed.status_code == 201, allowed.text
    mock_conn.network.create_subnet.assert_called_once()


async def test_admin_network_update_without_cidr_is_unaffected(admin_client, mock_conn):
    mock_conn.network.update_network.return_value = SimpleNamespace(
        id="net-p", name="renamed", status="ACTIVE", is_router_external=True, is_shared=True
    )
    response = await admin_client.put("/api/v1/admin/networks/net-p", json={"name": "renamed"})
    assert response.status_code == 200, response.text


# ── enforcement: MCP control plane ──────────────────────────────────────────


def _mcp_conn():
    from tests.test_mcp_network_management import Neutron

    return SimpleNamespace(network=Neutron(), _afterglow_domain_id="domain-a")


async def test_mcp_subnet_create_refuses_reserved_cidr_with_stable_code():
    from app.services.mcp_control_plane import network_management as management
    from tests.test_mcp_network_management import NETWORK, PROJECT

    conn = _mcp_conn()
    for cidr in ("10.8.0.0/24", "10.8.0.0/16", "10.8.0.128/25"):
        attrs = {"network_id": NETWORK, "name": "s", "cidr": cidr}
        for operation in (management.preview_project_subnet_create, management.request_project_subnet_create):
            with pytest.raises(VpnReservedCidrError, match=VPN_RESERVED_CIDR):
                await operation(conn, project_id=PROJECT, attributes=attrs)
    assert conn.network.writes == []
    await management.request_project_subnet_create(
        conn,
        project_id=PROJECT,
        attributes={"network_id": NETWORK, "name": "s", "cidr": "10.8.1.0/24", "gateway_ip": None},
    )
    assert len(conn.network.writes) == 1


async def test_mcp_subnet_update_checks_only_gateway_changes():
    from app.services.mcp_control_plane import network_management as management
    from tests.test_mcp_network_management import PROJECT, SUBNET

    conn = _mcp_conn()
    record = conn.network.records["subnets"][SUBNET]
    record.update(cidr="10.8.0.0/24", gateway_ip="10.8.0.1", dns_nameservers=[])
    for operation in (management.preview_project_subnet_update, management.request_project_subnet_update):
        with pytest.raises(VpnReservedCidrError):
            await operation(conn, project_id=PROJECT, subnet_id=SUBNET, attributes={"gateway_ip": "10.8.0.254"})
    assert conn.network.writes == []
    await management.request_project_subnet_update(
        conn, project_id=PROJECT, subnet_id=SUBNET, attributes={"name": "renamed", "gateway_ip": "10.8.0.1"}
    )
    await management.request_project_subnet_update(
        conn, project_id=PROJECT, subnet_id=SUBNET, attributes={"gateway_ip": None}
    )
    assert len(conn.network.writes) == 2


async def test_mcp_policy_unavailable_or_unknown_domain_fails_closed(monkeypatch):
    from app.services.mcp_control_plane import network_management as management
    from app.services.mcp_control_plane.network import McpNetworkError
    from tests.test_mcp_network_management import NETWORK, PROJECT

    attrs = {"network_id": NETWORK, "name": "s", "cidr": "192.168.50.0/24"}
    conn = _mcp_conn()
    conn._afterglow_domain_id = None
    with pytest.raises(McpNetworkError, match="VPN reserved range policy is unavailable"):
        await management.request_project_subnet_create(conn, project_id=PROJECT, attributes=attrs)

    async def unavailable(domain_id):
        raise svc.VpnReservedRangesUnavailable("down")

    monkeypatch.setattr(svc, "_stored_row", unavailable)
    conn = _mcp_conn()
    with pytest.raises(McpNetworkError, match="VPN reserved range policy is unavailable"):
        await management.request_project_subnet_create(conn, project_id=PROJECT, attributes=attrs)
    assert conn.network.writes == []


async def test_mcp_registry_handlers_surface_code_not_generic_unavailable():
    from app.services.mcp_control_plane import registry
    from tests.test_mcp_network_management import NETWORK, PROJECT

    conn = _mcp_conn()

    @asynccontextmanager
    async def connection():
        yield conn

    context = SimpleNamespace(project_id=PROJECT, openstack_connection=connection)
    arguments = registry.SubnetCreateArguments.model_validate(
        {"network_id": NETWORK, "name": "s", "cidr": "10.8.0.0/24"}
    )
    for handler in (registry._subnet_create_preview, registry._subnet_create):
        with pytest.raises(VpnReservedCidrError) as raised:
            await handler(context, arguments)
        assert str(raised.value).startswith(f"{VPN_RESERVED_CIDR}: ")
    assert conn.network.writes == []


async def test_mcp_enforcement_is_domain_isolated(_vpn_reserved_ranges_store):
    from app.services.mcp_control_plane import network_management as management
    from tests.test_mcp_network_management import NETWORK, PROJECT

    _vpn_reserved_ranges_store["domain-b"] = {"vpn_reserved_cidrs": ["192.168.50.0/24"], "revision": 1}
    conn = _mcp_conn()
    attrs = {"network_id": NETWORK, "name": "s", "cidr": "192.168.50.0/24", "gateway_ip": None}
    await management.request_project_subnet_create(conn, project_id=PROJECT, attributes=attrs)
    _vpn_reserved_ranges_store["domain-a"] = {"vpn_reserved_cidrs": ["192.168.50.0/24"], "revision": 1}
    with pytest.raises(VpnReservedCidrError):
        await management.request_project_subnet_create(conn, project_id=PROJECT, attributes=attrs)
    assert len(conn.network.writes) == 1
