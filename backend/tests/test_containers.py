"""container/containers.py 엔드포인트 단위 테스트 (8 HTTP 엔드포인트, Zun 서비스 필요)."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.containers import ZunContainerInfo
from app.services.ws_ticket import consume_ticket


def _make_container():
    return ZunContainerInfo(
        uuid="c-1",
        name="mycontainer",
        status="Running",
        image="nginx",
        cpu=0.5,
        memory="128",
        command=None,
        created_at=None,
    )


@pytest.mark.asyncio
async def test_list_containers_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/containers")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_containers_success(client):
    with patch("app.api.container.containers.asyncio") as mock_asyncio:
        mock_asyncio.to_thread = AsyncMock(return_value=[])
        resp = await client.get("/api/v1/containers")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_get_container_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/containers/c-1")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_container_success(client):
    with patch("app.api.container.containers.zun.get_container", return_value=_make_container()):
        resp = await client.get("/api/v1/containers/c-1")
    assert resp.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 422, 429, 500, 502, 503, 504])
async def test_get_container_native_read_status_preserves_denial_without_inventing_absence(client, mock_conn, status):
    from openstack.exceptions import HttpException

    with patch(
        "app.api.container.containers.zun.get_container",
        side_effect=HttpException("PRIVATE_NATIVE_CONTAINER_BODY", http_status=status),
    ) as lookup:
        response = await client.get("/api/v1/containers/c-1")

    lookup.assert_called_once_with(mock_conn, "c-1")
    expected = 404 if status in (401, 403, 404) else 503
    assert response.status_code == expected
    assert response.json() == {
        "detail": "컨테이너를 찾을 수 없습니다" if expected == 404 else "컨테이너 서비스에 연결할 수 없습니다"
    }
    assert "PRIVATE_NATIVE_CONTAINER_BODY" not in response.text
    assert "PRIVATE_NATIVE_CONTAINER_BODY" not in str(response.headers)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_kind", ["connection", "timeout", "unexpected"])
async def test_get_container_transport_and_unexpected_read_failures_are_sanitized_unavailable(client, failure_kind):
    from requests.exceptions import ConnectionError, Timeout

    error_type = {"connection": ConnectionError, "timeout": Timeout, "unexpected": RuntimeError}[failure_kind]
    with patch(
        "app.api.container.containers.zun.get_container", side_effect=error_type("PRIVATE_NATIVE_CONTAINER_BODY")
    ):
        response = await client.get("/api/v1/containers/c-1")

    assert response.status_code == 503
    assert response.json() == {"detail": "컨테이너 서비스에 연결할 수 없습니다"}
    assert "PRIVATE_NATIVE_CONTAINER_BODY" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403, 404])
async def test_get_container_keeps_local_lookup_denial_opaque_without_forwarding_provider_headers(client, status):
    from fastapi import HTTPException

    with patch(
        "app.api.container.containers.zun.get_container",
        side_effect=HTTPException(
            status, "PRIVATE_NATIVE_CONTAINER_BODY", headers={"X-Native-Private": "PRIVATE_HEADER"}
        ),
    ):
        response = await client.get("/api/v1/containers/c-1")

    assert response.status_code == 404
    assert response.json() == {"detail": "컨테이너를 찾을 수 없습니다"}
    assert "X-Native-Private" not in response.headers
    assert "PRIVATE_HEADER" not in str(response.headers)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 422, 429, 500, 502, 503, 504])
async def test_admin_container_read_outage_is_not_reported_as_absent(admin_client, status):
    from openstack.exceptions import HttpException

    with patch(
        "app.services.zun.get_container",
        side_effect=HttpException("PRIVATE_ADMIN_CONTAINER_BODY", http_status=status),
    ):
        response = await admin_client.get("/api/v1/admin/containers/c-1")

    expected = 404 if status in (401, 403, 404) else 503
    assert response.status_code == expected
    assert response.json() == {
        "detail": "컨테이너를 찾을 수 없습니다" if expected == 404 else "컨테이너 서비스에 연결할 수 없습니다"
    }
    assert "PRIVATE_ADMIN_CONTAINER_BODY" not in response.text
    assert "PRIVATE_ADMIN_CONTAINER_BODY" not in str(response.headers)


@pytest.mark.asyncio
async def test_create_container_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/containers", json={"name": "test", "image": "nginx"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_container_success(client):
    with patch("app.api.container.containers.asyncio") as mock_asyncio:
        mock_asyncio.to_thread = AsyncMock(return_value=_make_container())
        resp = await client.post("/api/v1/containers", json={"name": "test", "image": "nginx"})
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_delete_container_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.delete("/api/v1/containers/c-1")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_delete_container_success(client):
    with patch("app.api.container.containers.asyncio") as mock_asyncio:
        mock_asyncio.to_thread = AsyncMock(return_value=None)
        resp = await client.delete("/api/v1/containers/c-1")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_start_container_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/containers/c-1/start")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_start_container_success(client):
    with patch("app.api.container.containers.asyncio") as mock_asyncio:
        mock_asyncio.to_thread = AsyncMock(return_value=None)
        resp = await client.post("/api/v1/containers/c-1/start")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_stop_container_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/containers/c-1/stop")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_stop_container_success(client):
    with patch("app.api.container.containers.asyncio") as mock_asyncio:
        mock_asyncio.to_thread = AsyncMock(return_value=None)
        resp = await client.post("/api/v1/containers/c-1/stop")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_get_container_logs_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/containers/c-1/logs")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_container_logs_success(client):
    with patch("app.api.container.containers.asyncio") as mock_asyncio:
        mock_asyncio.to_thread = AsyncMock(return_value="log line 1\n")
        resp = await client.get("/api/v1/containers/c-1/logs")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_create_exec_ticket_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/containers/c-1/exec-ticket")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_exec_ticket_is_single_use(client):
    response = await client.post("/api/v1/containers/c-1/exec-ticket")
    assert response.status_code == 201
    ticket = response.json()["ticket"]

    payload = await consume_ticket(ticket, expected_kind="container-exec")
    assert payload is not None
    assert payload["container_id"] == "c-1"
    assert await consume_ticket(ticket, expected_kind="container-exec") is None
