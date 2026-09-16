"""라우터 API 단위 테스트."""

from unittest.mock import MagicMock, patch

import pytest

from app.models.storage import RouterDetail, RouterInfo


def make_router(router_id: str = "router-1", name: str = "test-router") -> RouterInfo:
    return RouterInfo(
        id=router_id,
        name=name,
        status="ACTIVE",
        project_id="test-project-123",
        external_gateway_network_id=None,
        connected_subnet_ids=[],
    )


def make_router_detail(router_id: str = "router-1") -> RouterDetail:
    return RouterDetail(
        id=router_id,
        name="test-router",
        status="ACTIVE",
        project_id="test-project-123",
        external_gateway_network_id=None,
        external_gateway_network_name=None,
        interfaces=[],
    )


@pytest.mark.asyncio
async def test_list_routers(client, mock_conn):
    async def mock_cached_call(key, ttl, fn, **kw):
        return fn()

    with (
        patch("app.api.network.routers.neutron.list_routers", return_value=[make_router()]),
        patch("app.api.network.routers.cached_call", new=mock_cached_call),
    ):
        resp = await client.get("/api/v1/routers")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert resp.json()[0]["id"] == "router-1"


@pytest.mark.asyncio
async def test_create_router(client, mock_conn):
    with patch("app.api.network.routers.neutron.create_router", return_value=make_router("router-new")):
        resp = await client.post("/api/v1/routers", json={"name": "test-router"})
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_get_router(client, mock_conn):
    with patch("app.api.network.routers.neutron.get_router_detail", return_value=make_router_detail()):
        resp = await client.get("/api/v1/routers/router-1")
    assert resp.status_code == 200
    assert resp.json()["id"] == "router-1"


@pytest.mark.asyncio
async def test_delete_router(client, mock_conn):
    with patch("app.api.network.routers.neutron.delete_router", return_value=None):
        resp = await client.delete("/api/v1/routers/router-1")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_add_router_interface(client, mock_conn):
    with patch("app.api.network.routers.neutron.add_router_interface", return_value={"subnet_id": "subnet-1"}):
        resp = await client.post("/api/v1/routers/router-1/interfaces", json={"subnet_id": "subnet-1"})
    assert resp.status_code in (200, 201)


@pytest.mark.asyncio
async def test_add_router_interface_rejects_foreign_subnet(client, mock_conn):
    mock_conn.network.get_subnet.return_value = MagicMock(project_id="other-project", tenant_id=None)
    with patch("app.api.network.routers.neutron.add_router_interface") as add:
        resp = await client.post("/api/v1/routers/router-1/interfaces", json={"subnet_id": "foreign-subnet"})

    assert resp.status_code == 404
    add.assert_not_called()


@pytest.mark.asyncio
async def test_remove_router_interface(client, mock_conn):
    with patch("app.api.network.routers.neutron.remove_router_interface", return_value=None):
        resp = await client.delete("/api/v1/routers/router-1/interfaces/subnet-1")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_remove_router_interface_rejects_foreign_subnet(client, mock_conn):
    mock_conn.network.get_subnet.return_value = MagicMock(project_id="other-project", tenant_id=None)
    with patch("app.api.network.routers.neutron.remove_router_interface") as remove:
        resp = await client.delete("/api/v1/routers/router-1/interfaces/foreign-subnet")

    assert resp.status_code == 404
    remove.assert_not_called()


@pytest.mark.asyncio
async def test_set_router_gateway(client, mock_conn):
    with patch("app.api.network.routers.neutron.set_router_gateway", return_value=None):
        resp = await client.post("/api/v1/routers/router-1/gateway", json={"external_network_id": "ext-net-1"})
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_remove_router_gateway(client, mock_conn):
    with patch("app.api.network.routers.neutron.remove_router_gateway", return_value=None):
        resp = await client.delete("/api/v1/routers/router-1/gateway")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_add_router_interface_auto_gateway(client, mock_conn):
    with patch(
        "app.api.network.routers.neutron.add_router_interface",
        return_value={"subnet_id": "subnet-1", "port_id": "port-1"},
    ) as mock_add:
        resp = await client.post(
            "/api/v1/routers/router-1/interfaces",
            json={"subnet_id": "subnet-1", "auto_gateway": True},
        )
    assert resp.status_code in (200, 201)
    mock_add.assert_called_once_with(mock_conn, "router-1", "subnet-1", True)


@pytest.mark.asyncio
async def test_delete_router_rejects_foreign_router(client, mock_conn):
    mock_conn.network.get_router.return_value = MagicMock(project_id="other-project", tenant_id=None)
    with patch("app.api.network.routers.neutron.delete_router") as mock_delete:
        resp = await client.delete("/api/v1/routers/router-foreign")
    assert resp.status_code == 404
    mock_delete.assert_not_called()


@pytest.mark.asyncio
async def test_add_router_interface_rejects_foreign_router(client, mock_conn):
    mock_conn.network.get_router.return_value = MagicMock(project_id="other-project", tenant_id=None)
    with patch("app.api.network.routers.neutron.add_router_interface") as mock_add:
        resp = await client.post("/api/v1/routers/router-foreign/interfaces", json={"subnet_id": "subnet-1"})
    assert resp.status_code == 404
    mock_add.assert_not_called()


@pytest.mark.asyncio
async def test_set_router_gateway_rejects_foreign_router(client, mock_conn):
    mock_conn.network.get_router.return_value = MagicMock(project_id="other-project", tenant_id=None)
    with patch("app.api.network.routers.neutron.set_router_gateway") as mock_gw:
        resp = await client.post("/api/v1/routers/router-foreign/gateway", json={"external_network_id": "ext-1"})
    assert resp.status_code == 404
    mock_gw.assert_not_called()
