"""network/loadbalancers.py 엔드포인트 단위 테스트 (17개)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.octavia import _lb_to_dict


@pytest.mark.asyncio
async def test_list_lbs_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/loadbalancers")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_lbs_success(client):
    with patch("app.api.network.loadbalancers.cached_call", new=AsyncMock(return_value=[])):
        resp = await client.get("/api/v1/loadbalancers")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_create_lb_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/loadbalancers", json={"name": "lb1", "vip_subnet_id": "s1"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_lb_success(client, mock_conn):
    with (
        patch("app.api.network.loadbalancers.octavia") as mock_oct,
        patch("app.api.network.loadbalancers.invalidate", new=AsyncMock()),
    ):
        mock_oct.create_load_balancer.return_value = {"id": "lb-1", "name": "lb1"}
        resp = await client.post("/api/v1/loadbalancers", json={"name": "lb1", "vip_subnet_id": "sub-1"})
    assert resp.status_code == 201
    mock_oct.create_load_balancer.assert_called_once_with(mock_conn, "lb1", "sub-1", "")


@pytest.mark.asyncio
async def test_get_lb_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/loadbalancers/lb-1")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_lb_success(client, mock_conn):
    with patch("app.api.network.loadbalancers.octavia") as mock_oct:
        mock_oct.get_load_balancer.return_value = {"id": "lb-1"}
        resp = await client.get("/api/v1/loadbalancers/lb-1")
    assert resp.status_code == 200
    mock_oct.get_load_balancer.assert_called_once_with(mock_conn, "lb-1")


@pytest.mark.asyncio
async def test_get_lb_status_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/loadbalancers/lb-1/status")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_lb_status_success(client, mock_conn):
    with patch("app.api.network.loadbalancers.octavia") as mock_oct:
        mock_oct.get_lb_status_tree.return_value = {"id": "lb-1", "statuses": {}}
        resp = await client.get("/api/v1/loadbalancers/lb-1/status")
    assert resp.status_code == 200
    mock_oct.get_lb_status_tree.assert_called_once_with(mock_conn, "lb-1")


@pytest.mark.asyncio
async def test_delete_lb_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.delete("/api/v1/loadbalancers/lb-1")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_delete_lb_success(client, mock_conn):
    with (
        patch("app.api.network.loadbalancers.octavia") as mock_oct,
        patch("app.api.network.loadbalancers.invalidate", new=AsyncMock()),
    ):
        mock_oct.delete_load_balancer.return_value = None
        resp = await client.delete("/api/v1/loadbalancers/lb-1")
    assert resp.status_code == 204
    mock_oct.delete_load_balancer.assert_called_once_with(mock_conn, "lb-1")


@pytest.mark.asyncio
async def test_list_listeners_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/loadbalancers/lb-1/listeners")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_listeners_success(client, mock_conn):
    with patch("app.api.network.loadbalancers.octavia") as mock_oct:
        mock_oct.list_listeners.return_value = []
        resp = await client.get("/api/v1/loadbalancers/lb-1/listeners")
    assert resp.status_code == 200
    mock_oct.list_listeners.assert_called_once_with(mock_conn, lb_id="lb-1")


@pytest.mark.asyncio
async def test_create_listener_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/loadbalancers/lb-1/listeners", json={"protocol": "HTTP", "protocol_port": 80})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_listener_success(client, mock_conn):
    with patch("app.api.network.loadbalancers.octavia") as mock_oct:
        mock_oct.create_listener.return_value = {"id": "lis-1"}
        resp = await client.post("/api/v1/loadbalancers/lb-1/listeners", json={"protocol": "HTTP", "protocol_port": 80})
    assert resp.status_code == 201
    mock_oct.create_listener.assert_called_once_with(mock_conn, "lb-1", "HTTP", 80, "", None)


@pytest.mark.asyncio
async def test_delete_listener_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.delete("/api/v1/loadbalancers/lb-1/listeners/lis-1")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_delete_listener_success(client, mock_conn):
    with patch("app.api.network.loadbalancers.octavia") as mock_oct:
        mock_oct.delete_listener.return_value = None
        resp = await client.delete("/api/v1/loadbalancers/lb-1/listeners/lis-1")
    assert resp.status_code == 204
    mock_oct.delete_listener.assert_called_once_with(mock_conn, "lis-1")


@pytest.mark.asyncio
async def test_list_pools_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/loadbalancers/lb-1/pools")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_pools_success(client, mock_conn):
    with patch("app.api.network.loadbalancers.octavia") as mock_oct:
        mock_oct.list_pools.return_value = []
        resp = await client.get("/api/v1/loadbalancers/lb-1/pools")
    assert resp.status_code == 200
    mock_oct.list_pools.assert_called_once_with(mock_conn, lb_id="lb-1")


@pytest.mark.asyncio
async def test_create_pool_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/loadbalancers/lb-1/pools", json={"protocol": "HTTP"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_pool_success(client, mock_conn):
    with patch("app.api.network.loadbalancers.octavia") as mock_oct:
        mock_oct.create_pool.return_value = {"id": "pool-1"}
        resp = await client.post("/api/v1/loadbalancers/lb-1/pools", json={"protocol": "HTTP"})
    assert resp.status_code == 201
    mock_oct.create_pool.assert_called_once_with(mock_conn, "lb-1", "HTTP", "ROUND_ROBIN", "", None)


@pytest.mark.asyncio
async def test_delete_pool_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.delete("/api/v1/loadbalancers/lb-1/pools/pool-1")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_delete_pool_success(client, mock_conn):
    with patch("app.api.network.loadbalancers.octavia") as mock_oct:
        mock_oct.delete_pool.return_value = None
        resp = await client.delete("/api/v1/loadbalancers/lb-1/pools/pool-1")
    assert resp.status_code == 204
    mock_oct.delete_pool.assert_called_once_with(mock_conn, "pool-1")


@pytest.mark.asyncio
async def test_list_members_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/loadbalancers/lb-1/pools/pool-1/members")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_members_success(client, mock_conn):
    with patch("app.api.network.loadbalancers.octavia") as mock_oct:
        mock_oct.list_members.return_value = []
        resp = await client.get("/api/v1/loadbalancers/lb-1/pools/pool-1/members")
    assert resp.status_code == 200
    mock_oct.list_members.assert_called_once_with(mock_conn, "pool-1")


@pytest.mark.asyncio
async def test_add_member_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/loadbalancers/lb-1/pools/pool-1/members", json={"address": "10.0.0.1", "protocol_port": 80}
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_add_member_success(client, mock_conn):
    with patch("app.api.network.loadbalancers.octavia") as mock_oct:
        mock_oct.add_member.return_value = {"id": "mem-1"}
        resp = await client.post(
            "/api/v1/loadbalancers/lb-1/pools/pool-1/members", json={"address": "10.0.0.1", "protocol_port": 80}
        )
    assert resp.status_code == 201
    mock_oct.add_member.assert_called_once_with(mock_conn, "pool-1", "10.0.0.1", 80, None, "", 1)


@pytest.mark.asyncio
async def test_remove_member_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.delete("/api/v1/loadbalancers/lb-1/pools/pool-1/members/mem-1")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_remove_member_success(client, mock_conn):
    with patch("app.api.network.loadbalancers.octavia") as mock_oct:
        mock_oct.remove_member.return_value = None
        resp = await client.delete("/api/v1/loadbalancers/lb-1/pools/pool-1/members/mem-1")
    assert resp.status_code == 204
    mock_oct.remove_member.assert_called_once_with(mock_conn, "pool-1", "mem-1")


@pytest.mark.asyncio
async def test_list_health_monitors_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/loadbalancers/lb-1/pools/pool-1/health-monitor")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_health_monitors_success(client, mock_conn):
    with patch("app.api.network.loadbalancers.octavia") as mock_oct:
        mock_oct.list_health_monitors.return_value = []
        resp = await client.get("/api/v1/loadbalancers/lb-1/pools/pool-1/health-monitor")
    assert resp.status_code == 200
    mock_oct.list_health_monitors.assert_called_once_with(mock_conn, pool_id="pool-1")


@pytest.mark.asyncio
async def test_create_health_monitor_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/loadbalancers/lb-1/pools/pool-1/health-monitor", json={})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_health_monitor_success(client, mock_conn):
    with patch("app.api.network.loadbalancers.octavia") as mock_oct:
        mock_oct.create_health_monitor.return_value = {"id": "hm-1"}
        resp = await client.post("/api/v1/loadbalancers/lb-1/pools/pool-1/health-monitor", json={})
    assert resp.status_code == 201
    mock_oct.create_health_monitor.assert_called_once_with(mock_conn, "pool-1", "HTTP", 5, 5, 3, "")


@pytest.mark.asyncio
async def test_delete_health_monitor_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.delete("/api/v1/loadbalancers/lb-1/pools/pool-1/health-monitor/hm-1")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_delete_health_monitor_success(client, mock_conn):
    with patch("app.api.network.loadbalancers.octavia") as mock_oct:
        mock_oct.delete_health_monitor.return_value = None
        resp = await client.delete("/api/v1/loadbalancers/lb-1/pools/pool-1/health-monitor/hm-1")
    assert resp.status_code == 204
    mock_oct.delete_health_monitor.assert_called_once_with(mock_conn, "hm-1")


def test_lb_to_dict_preserves_tags():
    lb = MagicMock()
    lb.id = "lb-tags-1"
    lb.name = "k3s-lb"
    lb.description = "Drover LB"
    lb.provisioning_status = "ACTIVE"
    lb.operating_status = "ONLINE"
    lb.vip_address = "192.0.2.50"
    lb.vip_subnet_id = "sub-1"
    lb.vip_network_id = None
    lb.vip_port_id = None
    lb.project_id = "proj-1"
    lb.tags = ["drover.managed=true", "drover.resource_type=load_balancer"]

    result = _lb_to_dict(lb)
    assert result["tags"] == ["drover.managed=true", "drover.resource_type=load_balancer"]
    assert result["project_id"] == "proj-1"


def test_lb_to_dict_default_empty_tags():
    lb = MagicMock()
    lb.id = "lb-tags-2"
    lb.name = "user-lb"
    lb.description = ""
    lb.provisioning_status = "ACTIVE"
    lb.operating_status = "ONLINE"
    lb.vip_address = "192.0.2.51"
    lb.vip_subnet_id = "sub-1"
    lb.vip_network_id = None
    lb.vip_port_id = None
    lb.project_id = "proj-1"
    lb.tags = None

    result = _lb_to_dict(lb)
    assert result["tags"] == []
