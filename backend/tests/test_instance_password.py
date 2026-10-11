"""인스턴스 관리자 패스워드 재설정 API 단위 테스트."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openstack.block_storage.v3.volume import Volume
from openstack.exceptions import HttpException

from app.services import nova


def _make_server(
    status: str = "ACTIVE",
    image_id: str = "img-1",
    user_id: str | None = "u1",
    project_id: str | None = "test-project-123",
) -> MagicMock:
    s = MagicMock()
    s.id = "server-1"
    s.name = "test-server"
    s.status = status
    s.image = {"id": image_id} if image_id else {}
    s.addresses = {}
    s.metadata = {}
    s.flavor = {"id": "flv-1"}
    s.created_at = None
    s.key_name = None
    s.user_id = user_id
    s.project_id = project_id
    s.tenant_id = project_id
    s.fault = None
    return s


def _qga_meta(enabled: bool = True, admin_user: str = "ubuntu") -> dict:
    return {
        "qga_enabled": enabled,
        "os_admin_user": admin_user if enabled else None,
        "image_id": "img-1",
        "image_name": "Ubuntu 22.04",
    }


@pytest.mark.asyncio
async def test_precheck_returns_supported_when_active_and_qga(admin_client, mock_conn):
    """ACTIVE + QGA 지원 시 supported=True를 반환한다."""
    mock_conn.compute.get_server.return_value = _make_server()
    with patch("app.api.compute.instances.nova.get_server_image_meta", return_value=_qga_meta(True)):
        resp = await admin_client.get("/api/v1/instances/server-1/admin-password/precheck")
    assert resp.status_code == 200
    data = resp.json()
    assert data["supported"] is True
    assert data["os_admin_user"] == "ubuntu"
    assert data["server_status"] == "ACTIVE"


@pytest.mark.asyncio
async def test_precheck_returns_unsupported_when_not_active(admin_client, mock_conn):
    """ACTIVE가 아닌 인스턴스는 supported=False를 반환한다."""
    mock_conn.compute.get_server.return_value = _make_server(status="SHELVED")
    with patch("app.api.compute.instances.nova.get_server_image_meta", return_value=_qga_meta(True)):
        resp = await admin_client.get("/api/v1/instances/server-1/admin-password/precheck")
    assert resp.status_code == 200
    data = resp.json()
    assert data["supported"] is False
    assert data["server_status"] == "SHELVED"


@pytest.mark.asyncio
async def test_precheck_returns_unsupported_when_no_qga(admin_client, mock_conn):
    """QGA 미지원 이미지는 supported=False를 반환한다."""
    mock_conn.compute.get_server.return_value = _make_server()
    with patch("app.api.compute.instances.nova.get_server_image_meta", return_value=_qga_meta(False)):
        resp = await admin_client.get("/api/v1/instances/server-1/admin-password/precheck")
    assert resp.status_code == 200
    data = resp.json()
    assert data["supported"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize("creator_id", ["test-user-123", "other-user", None])
@pytest.mark.parametrize("project_id", ["test-project-123", "other-project", None])
async def test_password_access_requires_native_creator_and_current_project(
    non_admin_client, mock_conn, method, creator_id, project_id
):
    mock_conn.compute.get_server.return_value = _make_server(user_id=creator_id, project_id=project_id)
    path = "/api/v1/instances/server-1/admin-password" + ("/precheck" if method == "GET" else "")
    kwargs = {"json": {"new_password": "Secure1234!"}} if method == "POST" else {}
    with patch("app.api.compute.instances.nova.get_server_image_meta", return_value=_qga_meta(True)) as metadata:
        response = await non_admin_client.request(method, path, **kwargs)
    expected = (
        404
        if project_id != "test-project-123"
        else (403 if creator_id != "test-user-123" else (200 if method == "GET" else 204))
    )
    assert response.status_code == expected
    if expected in (403, 404):
        metadata.assert_not_called()
        mock_conn.compute.change_server_password.assert_not_called()
    elif method == "GET":
        assert response.json()["supported"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["GET", "POST"])
async def test_system_admin_can_access_another_creators_project(admin_client, mock_conn, method):
    mock_conn.compute.get_server.return_value = _make_server(user_id="other-user", project_id="other-project")
    path = "/api/v1/instances/server-1/admin-password" + ("/precheck" if method == "GET" else "")
    kwargs = {"json": {"new_password": "Secure1234!"}} if method == "POST" else {}
    with patch("app.api.compute.instances.nova.get_server_image_meta", return_value=_qga_meta(True)):
        response = await admin_client.request(method, path, **kwargs)
    assert response.status_code == (200 if method == "GET" else 204)


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["GET", "POST"])
async def test_editable_metadata_cannot_forge_instance_creator(non_admin_client, mock_conn, method):
    server = _make_server(user_id="other-user")
    server.metadata = {"user_id": "test-user-123", "creator_id": "test-user-123"}
    mock_conn.compute.get_server.return_value = server
    path = "/api/v1/instances/server-1/admin-password" + ("/precheck" if method == "GET" else "")
    kwargs = {"json": {"new_password": "Secure1234!"}} if method == "POST" else {}
    response = await non_admin_client.request(method, path, **kwargs)
    assert response.status_code == 403
    mock_conn.compute.change_server_password.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("roles,user_id", [(["admin"], "test-user-123"), (["member"], None)])
async def test_project_admin_or_missing_caller_identity_cannot_change_another_instances_password(
    non_admin_client, mock_conn, roles, user_id
):
    from app.api.deps import get_token_info
    from app.main import app
    from tests.conftest import make_token_info

    async def caller():
        return {**make_token_info(roles=roles), "user_id": user_id}

    app.dependency_overrides[get_token_info] = caller
    mock_conn.compute.get_server.return_value = _make_server(user_id="other-user")
    response = await non_admin_client.post(
        "/api/v1/instances/server-1/admin-password", json={"new_password": "Secure1234!"}
    )
    assert response.status_code == 403
    mock_conn.compute.change_server_password.assert_not_called()


@pytest.mark.asyncio
async def test_reader_creator_cannot_bypass_project_write_permission(non_admin_client, mock_conn):
    from app.api.deps import get_token_info
    from app.main import app
    from tests.conftest import make_token_info

    async def caller():
        return make_token_info(roles=["reader"])

    app.dependency_overrides[get_token_info] = caller
    mock_conn.compute.get_server.return_value = _make_server(user_id="test-user-123")
    response = await non_admin_client.post(
        "/api/v1/instances/server-1/admin-password", json={"new_password": "Secure1234!"}
    )
    assert response.status_code == 403
    mock_conn.compute.change_server_password.assert_not_called()


@pytest.mark.asyncio
async def test_set_password_rejects_non_active(admin_client, mock_conn):
    """ACTIVE가 아닌 인스턴스에 패스워드 변경 시도 시 409를 반환한다."""
    mock_conn.compute.get_server.return_value = _make_server(status="SHUTOFF")
    resp = await admin_client.post(
        "/api/v1/instances/server-1/admin-password",
        json={"new_password": "Secure1234!"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_set_password_rejects_no_qga(admin_client, mock_conn):
    """QGA 미지원 이미지에 패스워드 변경 시도 시 409를 반환한다."""
    mock_conn.compute.get_server.return_value = _make_server()
    with patch("app.api.compute.instances.nova.get_server_image_meta", return_value=_qga_meta(False)):
        resp = await admin_client.post(
            "/api/v1/instances/server-1/admin-password",
            json={"new_password": "Secure1234!"},
        )
    assert resp.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize("password", ["Bad7!", "Q" * 129])
async def test_invalid_password_length_is_rejected_without_echoing_secret(admin_client, password):
    response = await admin_client.post("/api/v1/instances/server-1/admin-password", json={"new_password": password})
    assert response.status_code == 422
    assert password not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_status", [400, 401, 403, 409, 501, 503, 500])
async def test_nova_rejection_is_not_success_and_never_exposes_password(
    admin_client, mock_conn, caplog, provider_status
):
    password = "NeverExpose-123!"
    mock_conn.compute.get_server.return_value = _make_server()
    mock_conn.compute.change_server_password.side_effect = HttpException(
        message=f"upstream rejected adminPass={password}", http_status=provider_status
    )
    with (
        patch("app.api.compute.instances.nova.get_server_image_meta", return_value=_qga_meta(True)),
        patch("app.api.compute.instances.rec", new_callable=AsyncMock) as record,
    ):
        response = await admin_client.post("/api/v1/instances/server-1/admin-password", json={"new_password": password})
    assert response.status_code == (502 if provider_status == 500 else provider_status)
    assert password not in response.text
    assert password not in caplog.text
    assert record.await_args.kwargs["status"] == "failed"
    assert password not in record.await_args.kwargs["error_message"]


@pytest.mark.asyncio
async def test_unexpected_provider_failure_never_persists_secret(admin_client, mock_conn, caplog):
    password = "NeverExpose-123!"
    mock_conn.compute.get_server.return_value = _make_server()
    mock_conn.compute.change_server_password.side_effect = RuntimeError(password)
    with (
        patch("app.api.compute.instances.nova.get_server_image_meta", return_value=_qga_meta(True)),
        patch("app.api.compute.instances.rec", new_callable=AsyncMock) as record,
    ):
        response = await admin_client.post("/api/v1/instances/server-1/admin-password", json={"new_password": password})
    assert response.status_code == 502
    assert password not in response.text + caplog.text
    assert record.await_args.kwargs["status"] == "failed"
    assert password not in record.await_args.kwargs["error_message"]


@pytest.mark.parametrize(
    ("root_device", "data_bootable", "supported", "admin_user"),
    [
        ("/dev/sda", True, True, "Administrator"),
        (None, False, True, "Administrator"),
        (None, True, False, None),
        ("/dev/sdz", False, False, None),
    ],
)
def test_boot_volume_password_metadata_uses_native_root_or_unique_bootable_volume(
    mock_conn, root_device, data_bootable, supported, admin_user
):
    server = _make_server(image_id="")
    server.root_device_name = root_device
    mock_conn.compute.get_server.return_value = server
    mock_conn.compute.volume_attachments.return_value = [
        SimpleNamespace(device="/dev/vda", volume_id="data"),
        SimpleNamespace(device="/dev/sda", volume_id="boot"),
    ]
    volumes = {
        "data": Volume(
            id="data",
            bootable="true" if data_bootable else "false",
            volume_image_metadata={"hw_qemu_guest_agent": "no", "os_admin_user": "wrong-data-account"},
        ),
        "boot": Volume(
            id="boot",
            bootable="true",
            volume_image_metadata={"hw_qemu_guest_agent": "yes", "os_admin_user": "Administrator"},
        ),
    }
    mock_conn.block_storage.get_volume.side_effect = volumes.__getitem__

    result = nova.get_server_image_meta(mock_conn, "server-1")

    assert result["qga_enabled"] is supported
    assert result["os_admin_user"] == admin_user
