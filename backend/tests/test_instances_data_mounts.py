"""인스턴스 데이터 마운트(storage-attachments) 단위 테스트."""

from unittest.mock import MagicMock, patch

import pytest

from app.models.compute import DataMountSpec, StorageAttachRequest

# ────── 모델 검증 ──────


@pytest.mark.parametrize(
    "path",
    [
        "/mnt/mydata",
        "/mnt/data-set_1.2",
        "/data/work",
        "/srv/files",
        "/home/userdir",
        "/mnt",
        "/data",
    ],
)
def test_data_mount_spec_valid_paths(path):
    spec = DataMountSpec(file_storage_id="share-1", mount_point=path, read_only=False)
    assert spec.mount_point == path


@pytest.mark.parametrize(
    "path",
    [
        "mnt/data",  # 상대 경로
        "/tmp/data",  # 허용 외 prefix
        "/opt/layers/merged",  # 차단 prefix
        "/etc/myconf",  # 차단 prefix
        "/usr/local/bin",  # 차단 prefix
        "/opt/layers",  # 차단 prefix 정확 일치
        "/mnt/a/b c",  # 공백 포함
        "/mnt/../etc/passwd",  # path traversal
    ],
)
def test_data_mount_spec_invalid_paths(path):
    with pytest.raises(Exception):
        DataMountSpec(file_storage_id="share-1", mount_point=path, read_only=False)


@pytest.mark.parametrize(
    "payload",
    [
        {"file_storage_id": "s1", "mount_point": "/mnt/x$y"},  # 쉘 메타문자 $
        {"file_storage_id": "s1", "mount_point": "/mnt/x`y"},  # 백틱
        {"file_storage_id": "s1", "mount_point": "/mnt/x;y"},  # 세미콜론
        {"file_storage_id": "s1", "mount_point": "/mnt/x\ny"},  # 개행
    ],
)
def test_data_mount_spec_injection_chars_rejected(payload):
    with pytest.raises(Exception):
        DataMountSpec(**payload)


def test_storage_attach_request_valid():
    req = StorageAttachRequest(file_storage_id="share-1", mount_point="/mnt/mydata", read_only=True)
    assert req.read_only is True


def test_storage_attach_request_invalid_path():
    with pytest.raises(Exception):
        StorageAttachRequest(file_storage_id="share-1", mount_point="/proc/data", read_only=False)


# ────── POST /storage-attachments ──────


def _make_server(project_id="test-project-123", name="vm-1", fixed_ip="10.0.0.5"):
    server = MagicMock()
    server.id = "inst-1"
    server.name = name
    server.project_id = project_id
    server.metadata = {}
    ip = MagicMock()
    ip.type = "fixed"
    ip.addr = fixed_ip
    server.ip_addresses = [ip]
    return server


def _make_share(share_id="share-1", proto="NFS", project_id="test-project-123", status="available"):
    share = MagicMock()
    share.id = share_id
    share.name = "test-share"
    share.share_proto = proto
    share.project_id = project_id
    share.is_public = False
    share.status = status
    share.nfs_export_location = "192.168.1.10:/volumes/share-1"
    return share


@pytest.mark.asyncio
async def test_attach_nfs_storage_success(client, mock_conn):
    server = _make_server()
    share = _make_share()
    mock_conn.compute.set_server_metadata = MagicMock()

    with (
        patch("app.api.compute.instances.nova.get_server", return_value=server),
        patch("app.api.compute.instances.manila.get_file_storage", return_value=share),
        patch("app.api.compute.instances.manila.ensure_nfs_access_rule", return_value={"access_id": "rule-1"}),
    ):
        resp = await client.post(
            "/api/v1/instances/inst-1/storage-attachments",
            json={"file_storage_id": "share-1", "mount_point": "/mnt/mydata", "read_only": False},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["share_proto"] == "NFS"
    assert "/mnt/mydata" in data["mount_command"]
    assert data["keyring_file"] is None
    mock_conn.compute.set_server_metadata.assert_called_once_with("inst-1", {"afterglow_data_share_ids": "share-1"})


@pytest.mark.asyncio
async def test_attach_cephfs_storage_success(client, mock_conn):
    server = _make_server()
    share = _make_share(proto="CEPHFS")
    share.nfs_export_location = None
    mock_conn.compute.set_server_metadata = MagicMock()

    with (
        patch("app.api.compute.instances.nova.get_server", return_value=server),
        patch("app.api.compute.instances.manila.get_file_storage", return_value=share),
        patch(
            "app.api.compute.instances.manila.create_access_rule",
            return_value={"access_id": "rule-2", "access_key": "AAAABBBBCCCC=="},
        ),
        patch(
            "app.api.compute.instances.manila.get_export_locations",
            return_value=["mon1:6789,mon2:6789:/volumes/share-1"],
        ),
    ):
        resp = await client.post(
            "/api/v1/instances/inst-1/storage-attachments",
            json={"file_storage_id": "share-1", "mount_point": "/data/ceph", "read_only": False},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["share_proto"] == "CEPHFS"
    assert "/data/ceph" in data["mount_command"]
    assert data["keyring_file"] is not None


@pytest.mark.asyncio
async def test_attach_storage_read_only_flag(client, mock_conn):
    server = _make_server()
    share = _make_share()
    mock_conn.compute.set_server_metadata = MagicMock()

    with (
        patch("app.api.compute.instances.nova.get_server", return_value=server),
        patch("app.api.compute.instances.manila.get_file_storage", return_value=share),
        patch("app.api.compute.instances.manila.ensure_nfs_access_rule", return_value={"access_id": "rule-ro"}),
    ):
        resp = await client.post(
            "/api/v1/instances/inst-1/storage-attachments",
            json={"file_storage_id": "share-1", "mount_point": "/mnt/ro", "read_only": True},
        )

    assert resp.status_code == 200
    assert "ro," in resp.json()["mount_command"]


@pytest.mark.asyncio
async def test_attach_storage_foreign_share_returns_403(client, mock_conn):
    """다른 프로젝트 소유 non-public share → 403."""
    server = _make_server()
    share = _make_share(project_id="other-project-999")

    with (
        patch("app.api.compute.instances.nova.get_server", return_value=server),
        patch("app.api.compute.instances.manila.get_file_storage", return_value=share),
    ):
        resp = await client.post(
            "/api/v1/instances/inst-1/storage-attachments",
            json={"file_storage_id": "share-1", "mount_point": "/mnt/x", "read_only": False},
        )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_attach_storage_unavailable_share_returns_409(client, mock_conn):
    """available 아닌 share → 409."""
    server = _make_server()
    share = _make_share(status="creating")

    with (
        patch("app.api.compute.instances.nova.get_server", return_value=server),
        patch("app.api.compute.instances.manila.get_file_storage", return_value=share),
    ):
        resp = await client.post(
            "/api/v1/instances/inst-1/storage-attachments",
            json={"file_storage_id": "share-1", "mount_point": "/mnt/x", "read_only": False},
        )

    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_attach_storage_invalid_mount_point_returns_422(client, mock_conn):
    """잘못된 mount_point → 422 (Pydantic 검증)."""
    resp = await client.post(
        "/api/v1/instances/inst-1/storage-attachments",
        json={"file_storage_id": "share-1", "mount_point": "/etc/passwd", "read_only": False},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_attach_storage_injection_mount_point_rejected(client, mock_conn):
    """쉘 메타문자 포함 mount_point → 422."""
    resp = await client.post(
        "/api/v1/instances/inst-1/storage-attachments",
        json={"file_storage_id": "s1", "mount_point": "/mnt/$(rm -rf /)", "read_only": False},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_attach_storage_foreign_instance_returns_404(client, mock_conn):
    """다른 프로젝트 인스턴스 → 404 (소유권 검증)."""
    server = _make_server(project_id="other-project-999")

    with patch("app.api.compute.instances.nova.get_server", return_value=server):
        resp = await client.post(
            "/api/v1/instances/inst-1/storage-attachments",
            json={"file_storage_id": "s1", "mount_point": "/mnt/x", "read_only": False},
        )

    assert resp.status_code == 404


# ────── GET /storage-attachments ──────


@pytest.mark.asyncio
async def test_list_storage_attachments_empty(client, mock_conn):
    server = _make_server()
    server.metadata = {}

    with patch("app.api.compute.instances.nova.get_server", return_value=server):
        resp = await client.get("/api/v1/instances/inst-1/storage-attachments")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_storage_attachments_with_shares(client, mock_conn):
    server = _make_server()
    server.metadata = {"union_data_share_ids": "share-1,share-2"}
    share1 = _make_share("share-1")
    share2 = _make_share("share-2", proto="CEPHFS")

    def mock_get_share(conn, fsi):
        return share1 if fsi == "share-1" else share2

    with (
        patch("app.api.compute.instances.nova.get_server", return_value=server),
        patch("app.api.compute.instances.manila.get_file_storage", side_effect=mock_get_share),
    ):
        resp = await client.get("/api/v1/instances/inst-1/storage-attachments")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    ids = {d["file_storage_id"] for d in data}
    assert ids == {"share-1", "share-2"}


# ────── DELETE /storage-attachments/{file_storage_id} ──────


@pytest.mark.asyncio
async def test_detach_nfs_storage_success(client, mock_conn):
    server = _make_server()
    server.metadata = {"union_data_share_ids": "share-1"}
    share = _make_share()
    mock_conn.compute.set_server_metadata = MagicMock()

    ip_rule = {"access_type": "ip", "access_to": "10.0.0.5", "id": "rule-nfs-1"}

    with (
        patch("app.api.compute.instances.nova.get_server", return_value=server),
        patch("app.api.compute.instances.manila.get_file_storage", return_value=share),
        patch("app.api.compute.instances.manila.list_access_rules", return_value=[ip_rule]),
        patch("app.api.compute.instances.manila.revoke_access_rule") as mock_revoke,
    ):
        resp = await client.delete("/api/v1/instances/inst-1/storage-attachments/share-1")

    assert resp.status_code == 204
    mock_revoke.assert_called_once()


@pytest.mark.asyncio
async def test_detach_cephfs_storage_success(client, mock_conn):
    server = _make_server()
    server.metadata = {"union_data_share_ids": "share-c"}
    share = _make_share("share-c", proto="CEPHFS")
    mock_conn.compute.set_server_metadata = MagicMock()

    cephx_rule = {"access_type": "cephx", "access_to": f"data-rw-{server.name}-share-cc", "id": "rule-ceph-1"}

    with (
        patch("app.api.compute.instances.nova.get_server", return_value=server),
        patch("app.api.compute.instances.manila.get_file_storage", return_value=share),
        patch("app.api.compute.instances.manila.list_access_rules", return_value=[cephx_rule]),
        patch("app.api.compute.instances.manila.revoke_access_rule"),
    ):
        resp = await client.delete("/api/v1/instances/inst-1/storage-attachments/share-c")

    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_detach_storage_foreign_instance_returns_404(client, mock_conn):
    """다른 프로젝트 인스턴스 연결 해제 시도 → 404."""
    server = _make_server(project_id="other-project-999")

    with patch("app.api.compute.instances.nova.get_server", return_value=server):
        resp = await client.delete("/api/v1/instances/inst-1/storage-attachments/share-1")

    assert resp.status_code == 404


# ────── mount_command 인젝션 방어 ──────


@pytest.mark.asyncio
async def test_nfs_export_path_is_quoted_in_mount_command(client, mock_conn):
    """NFS export_location에 공백이나 특수문자가 있어도 마운트 명령에 shlex.quote가 적용된다."""
    server = _make_server()
    share = _make_share()
    share.nfs_export_location = "192.168.1.10:/volumes/share with spaces"
    mock_conn.compute.set_server_metadata = MagicMock()

    with (
        patch("app.api.compute.instances.nova.get_server", return_value=server),
        patch("app.api.compute.instances.manila.get_file_storage", return_value=share),
        patch("app.api.compute.instances.manila.ensure_nfs_access_rule", return_value={"access_id": "rule-q"}),
    ):
        resp = await client.post(
            "/api/v1/instances/inst-1/storage-attachments",
            json={"file_storage_id": "share-1", "mount_point": "/mnt/q", "read_only": False},
        )

    assert resp.status_code == 200
    cmd = resp.json()["mount_command"]
    # 공백이 raw 형태로 노출되지 않고 따옴표로 감싸져야 한다
    assert "share with spaces" not in cmd or "'192.168.1.10:/volumes/share with spaces'" in cmd
