"""Manila NFS 보안 옵션 단위 테스트.

A5: root_squash 강제 + sec_flavor 옵션 (Manila API v2.65 metadata 필드)
"""

from unittest.mock import MagicMock, call, patch

import httpx
import pytest

# _build_nfs_access_metadata
# ---------------------------------------------------------------------------


def test_build_nfs_metadata_defaults():
    """기본값: root_squash=True, sec_flavor="sys"."""
    from app.services.manila import _build_nfs_access_metadata

    meta = _build_nfs_access_metadata()
    assert meta == {"root_squash": "True", "auth_flavor_list": ["sys"]}


def test_build_nfs_metadata_root_squash_false():
    """root_squash=False 시 root_squash 키 제외."""
    from app.services.manila import _build_nfs_access_metadata

    meta = _build_nfs_access_metadata(root_squash=False, sec_flavor="sys")
    assert "root_squash" not in meta
    assert meta["auth_flavor_list"] == ["sys"]


def test_build_nfs_metadata_krb5():
    """sec_flavor="krb5" 시 auth_flavor_list에 krb5 반영."""
    from app.services.manila import _build_nfs_access_metadata

    meta = _build_nfs_access_metadata(root_squash=True, sec_flavor="krb5")
    assert meta["root_squash"] == "True"
    assert meta["auth_flavor_list"] == ["krb5"]


def test_build_nfs_metadata_empty_flavor():
    """sec_flavor="" 시 auth_flavor_list 키 제외."""
    from app.services.manila import _build_nfs_access_metadata

    meta = _build_nfs_access_metadata(root_squash=True, sec_flavor="")
    assert "auth_flavor_list" not in meta


# ---------------------------------------------------------------------------
# create_access_rule — metadata 파라미터
# ---------------------------------------------------------------------------


def _make_manila_client_mock(access_id: str = "rule-id", access_level: str = "rw"):
    client = MagicMock()
    client.post.return_value = {
        "access": {
            "id": access_id,
            "access_type": "ip",
            "access_to": "10.0.0.1",
            "access_level": access_level,
            "state": "new",
        }
    }
    return client


@patch("app.services.manila.get_client")
def test_create_access_rule_ip_with_metadata(mock_get_client):
    """IP access rule 생성 시 metadata가 allow_access에 포함되어야 한다."""
    from app.services.manila import create_access_rule

    client = _make_manila_client_mock()
    mock_get_client.return_value = client

    conn = MagicMock()
    meta = {
        "root_squash": "True",
        "auth_flavor_list": ["sys"],
        "afterglow_instance_id": "11111111-2222-4333-8444-555555555555",
    }
    result = create_access_rule(conn, "share-1", "10.0.0.1", "rw", "ip", metadata=meta)

    posted_body = client.post.call_args[0][1]
    assert posted_body["allow_access"]["metadata"] == meta
    assert result["id"] == "rule-id"
    assert result["state"] == "new"


@patch("app.services.manila.get_client")
def test_create_access_rule_ip_no_metadata_when_none(mock_get_client):
    """metadata=None 시 allow_access에 metadata 키 없음."""
    from app.services.manila import create_access_rule

    client = _make_manila_client_mock()
    mock_get_client.return_value = client

    conn = MagicMock()
    create_access_rule(conn, "share-1", "10.0.0.1", "rw", "ip", metadata=None)

    posted_body = client.post.call_args[0][1]
    assert "metadata" not in posted_body["allow_access"]


@patch("app.services.manila.get_client")
def test_create_access_rule_cephx_preserves_instance_ownership_metadata(mock_get_client):
    """CephX grants must retain the same provider ownership marker as NFS grants."""
    from app.services.manila import create_access_rule

    client = MagicMock()
    client.post.return_value = {
        "access": {
            "id": "cephx-rule-id",
            "access_type": "cephx",
            "access_to": "afterglow-safe-identity",
            "access_level": "rw",
            "state": "new",
        }
    }
    client.get.return_value = {"access_list": [{"id": "cephx-rule-id", "access_key": "AQTEST=="}]}
    mock_get_client.return_value = client

    conn = MagicMock()
    meta = {"afterglow_instance_id": "11111111-2222-4333-8444-555555555555"}
    result = create_access_rule(conn, "share-1", "afterglow-safe-identity", "rw", "cephx", metadata=meta)

    client.post.assert_called_once_with(
        "shares/share-1/action",
        {
            "allow_access": {
                "access_type": "cephx",
                "access_to": "afterglow-safe-identity",
                "access_level": "rw",
                "metadata": meta,
            }
        },
        log_errors=False,
    )
    assert result["id"] == "cephx-rule-id"
    assert result["access_key"] == "AQTEST=="
    assert result["state"] == "new"


@pytest.mark.parametrize("key", [None, "AVAILABLE_NOW=="])
def test_create_ceph_grant_without_wait_preserves_state_and_never_polls_or_revokes(key):
    from app.services.manila import create_access_rule

    client = _make_manila_client_mock()
    client.post.return_value["access"].update(access_type="cephx", access_key=key, state="new")
    with (
        patch("app.services.manila.get_client", return_value=client),
        patch("app.services.manila._get_access_key") as get_key,
        patch("app.services.manila._revoke_access_rule_raw") as revoke,
    ):
        result = create_access_rule(
            MagicMock(),
            "share-1",
            "afterglow-safe-identity",
            "rw",
            "cephx",
            wait_for_key=False,
        )

    assert result["state"] == "new"
    assert result["access_key"] == key
    get_key.assert_not_called()
    revoke.assert_not_called()
    client.get.assert_not_called()
    assert client.post.call_args.kwargs == {"log_errors": False}


@patch("app.services.manila.get_client")
def test_revoke_access_rule_submits_exact_id_without_logging_provider_body(mock_get_client):
    from app.services.manila import revoke_access_rule

    client = MagicMock()
    mock_get_client.return_value = client
    revoke_access_rule(MagicMock(), "share-1", "exact-managed-rule")

    client.post.assert_called_once_with(
        "shares/share-1/action",
        {"deny_access": {"access_id": "exact-managed-rule"}},
        log_errors=False,
    )


# ---------------------------------------------------------------------------
# ensure_nfs_access_rule — 보안 메타데이터 포함 생성
# ---------------------------------------------------------------------------


@patch("app.services.manila.list_access_rules")
@patch("app.services.manila.create_access_rule")
def test_ensure_nfs_access_rule_creates_with_security_metadata(mock_create, mock_list):
    """기존 rule 없을 때 root_squash + sec_flavor 메타데이터와 함께 새 rule 생성."""
    from app.services.manila import ensure_nfs_access_rule

    mock_list.return_value = []
    mock_create.return_value = {
        "access_id": "new-rule",
        "access_key": "",
        "access_to": "10.0.0.5",
        "access_level": "rw",
    }

    conn = MagicMock()
    result = ensure_nfs_access_rule(
        conn,
        "share-1",
        "10.0.0.5",
        "rw",
        root_squash=True,
        sec_flavor="sys",
    )

    assert result["access_id"] == "new-rule"
    # create_access_rule이 metadata와 함께 호출됐는지 검증
    _, kwargs = mock_create.call_args
    passed_meta = (
        kwargs.get("metadata") or mock_create.call_args[0][5]
        if len(mock_create.call_args[0]) > 5
        else kwargs.get("metadata")
    )
    # positional or keyword — 어느 방식으로든 metadata가 전달됐어야 한다
    call_kwargs = mock_create.call_args.kwargs
    call_args = mock_create.call_args.args
    if "metadata" in call_kwargs:
        passed_meta = call_kwargs["metadata"]
    else:
        # positional: conn, file_storage_id, access_to, access_level, access_type, metadata
        passed_meta = call_args[5] if len(call_args) > 5 else None
    assert passed_meta is not None
    assert passed_meta.get("root_squash") == "True"
    assert passed_meta.get("auth_flavor_list") == ["sys"]


@patch("app.services.manila.list_access_rules")
@patch("app.services.manila.create_access_rule")
def test_ensure_nfs_access_rule_returns_existing_without_create(mock_create, mock_list):
    """기존 active rule이 있으면 create_access_rule을 호출하지 않아야 한다."""
    from app.services.manila import ensure_nfs_access_rule

    mock_list.return_value = [
        {
            "id": "existing-rule",
            "access_type": "ip",
            "access_to": "10.0.0.5",
            "access_level": "rw",
            "state": "active",
        }
    ]

    conn = MagicMock()
    result = ensure_nfs_access_rule(conn, "share-1", "10.0.0.5", "rw")

    mock_create.assert_not_called()
    assert result["access_id"] == "existing-rule"


@patch("app.services.manila.list_access_rules")
@patch("app.services.manila.create_access_rule")
def test_ensure_nfs_access_rule_krb5(mock_create, mock_list):
    """sec_flavor=krb5 옵션이 메타데이터에 반영된다."""
    from app.services.manila import ensure_nfs_access_rule

    mock_list.return_value = []
    mock_create.return_value = {
        "access_id": "krb5-rule",
        "access_key": "",
        "access_to": "192.168.1.10",
        "access_level": "rw",
    }

    conn = MagicMock()
    ensure_nfs_access_rule(
        conn,
        "share-2",
        "192.168.1.10",
        "rw",
        root_squash=True,
        sec_flavor="krb5",
    )

    call_kwargs = mock_create.call_args.kwargs
    call_args = mock_create.call_args.args
    if "metadata" in call_kwargs:
        passed_meta = call_kwargs["metadata"]
    else:
        passed_meta = call_args[5] if len(call_args) > 5 else None
    assert passed_meta is not None
    assert passed_meta.get("auth_flavor_list") == ["krb5"]


@patch("app.services.manila.list_access_rules")
@patch("app.services.manila.create_access_rule")
def test_ensure_nfs_access_rule_root_squash_disabled(mock_create, mock_list):
    """root_squash=False 시 메타데이터에 root_squash 키 없음."""
    from app.services.manila import ensure_nfs_access_rule

    mock_list.return_value = []
    mock_create.return_value = {
        "access_id": "nosquash-rule",
        "access_key": "",
        "access_to": "10.0.0.1",
        "access_level": "ro",
    }

    conn = MagicMock()
    ensure_nfs_access_rule(
        conn,
        "share-3",
        "10.0.0.1",
        "ro",
        root_squash=False,
        sec_flavor="sys",
    )

    call_kwargs = mock_create.call_args.kwargs
    call_args = mock_create.call_args.args
    if "metadata" in call_kwargs:
        passed_meta = call_kwargs["metadata"]
    else:
        passed_meta = call_args[5] if len(call_args) > 5 else None
    assert passed_meta is not None
    assert "root_squash" not in passed_meta


# ---------------------------------------------------------------------------
# Settings — 새 config 필드 기본값
# ---------------------------------------------------------------------------


def test_settings_manila_nfs_defaults():
    """Manila NFS 보안 설정 기본값 확인."""
    from app.config import Settings

    s = Settings()
    assert s.manila_nfs_root_squash is True
    assert s.manila_nfs_sec_flavor == "sys"


def test_settings_manila_nfs_env_override(monkeypatch):
    """환경변수로 NFS 보안 옵션을 오버라이드할 수 있다."""
    from app.config import Settings

    monkeypatch.setenv("MANILA_NFS_ROOT_SQUASH", "false")
    monkeypatch.setenv("MANILA_NFS_SEC_FLAVOR", "krb5")
    s = Settings()
    assert s.manila_nfs_root_squash is False
    assert s.manila_nfs_sec_flavor == "krb5"


# ---------------------------------------------------------------------------
# _get_access_key — timeout 기반 재시도 + RuntimeError
# ---------------------------------------------------------------------------


def test_get_access_key_returns_on_first_hit():
    """첫 폴링에 key가 있으면 즉시 반환한다."""
    from app.services.manila import _get_access_key

    client = MagicMock()
    client.get.return_value = {"access_list": [{"id": "rule-1", "access_key": "AQTEST=="}]}
    key = _get_access_key(client, "share-1", "rule-1", timeout_seconds=30)
    assert key == "AQTEST=="
    assert client.get.call_count == 1


def test_get_access_key_retries_until_key_available():
    """처음 몇 회는 빈 key, 이후 채워지면 정상 반환한다."""
    from app.services.manila import _get_access_key

    empty = {"access_list": [{"id": "rule-1", "access_key": ""}]}
    filled = {"access_list": [{"id": "rule-1", "access_key": "AQfilled=="}]}
    client = MagicMock()
    client.get.side_effect = [empty, empty, filled]

    with patch("time.sleep"):
        key = _get_access_key(client, "share-1", "rule-1", timeout_seconds=30)

    assert key == "AQfilled=="
    assert client.get.call_count == 3


def test_get_access_key_raises_on_timeout():
    """timeout 내내 빈 key면 RuntimeError 를 발생시킨다."""
    from app.services.manila import _get_access_key

    client = MagicMock()
    client.get.return_value = {"access_list": [{"id": "rule-1", "access_key": ""}]}

    with patch("time.sleep"):
        try:
            _get_access_key(client, "share-1", "rule-1", timeout_seconds=9)
            assert False, "RuntimeError 미발생"
        except RuntimeError as e:
            assert "access_id=rule-1" in str(e)


def test_get_access_key_respects_timeout_seconds():
    """timeout_seconds=9 → max 3회(9//3) 시도 후 포기."""
    from app.services.manila import _get_access_key

    client = MagicMock()
    client.get.return_value = {"access_list": [{"id": "rule-1", "access_key": ""}]}

    with patch("time.sleep"):
        try:
            _get_access_key(client, "share-1", "rule-1", timeout_seconds=9)
        except RuntimeError:
            pass
    assert client.get.call_count == 3


# ---------------------------------------------------------------------------
# Settings — CephX key timeout 기본값
# ---------------------------------------------------------------------------


def test_settings_manila_cephx_key_timeout_default():
    """manila_cephx_key_timeout_seconds 기본값은 300이다."""
    from app.config import Settings

    s = Settings()
    assert s.manila_cephx_key_timeout_seconds == 300


def test_settings_manila_cephx_key_timeout_env_override(monkeypatch):
    """환경변수로 CephX timeout 을 오버라이드할 수 있다."""
    from app.config import Settings

    monkeypatch.setenv("MANILA_CEPHX_KEY_TIMEOUT_SECONDS", "600")
    s = Settings()
    assert s.manila_cephx_key_timeout_seconds == 600


# ---------------------------------------------------------------------------
# force_delete_file_storage
# ---------------------------------------------------------------------------


@patch("app.services.manila.get_client")
def test_force_delete_file_storage_posts_force_delete_action(mock_get_client):
    from app.services.manila import force_delete_file_storage

    client = MagicMock()
    mock_get_client.return_value = client

    result = force_delete_file_storage(MagicMock(), "share-1")

    assert result == "force_delete_submitted"
    client.post.assert_called_once_with("shares/share-1/action", {"force_delete": None})


@patch("app.services.manila.get_client")
def test_force_delete_file_storage_returns_already_deleted_on_404(mock_get_client):
    from app.services.manila import force_delete_file_storage

    request = httpx.Request("POST", "http://manila.example/v2/project/shares/share-1/action")
    response = httpx.Response(404, request=request)
    client = MagicMock()
    client.post.side_effect = httpx.HTTPStatusError("not found", request=request, response=response)
    mock_get_client.return_value = client

    result = force_delete_file_storage(MagicMock(), "share-1")

    assert result == "already_deleted"


@patch("app.services.manila.get_client")
def test_strict_file_storage_quota_requires_usage_fields(mock_get_client):
    from app.services.manila import get_file_storage_quota

    client = MagicMock()
    client.get.return_value = {"quota_set": {"shares": {"limit": 2}, "gigabytes": {"limit": 20, "in_use": 1}}}
    mock_get_client.return_value = client
    conn = MagicMock()
    conn._afterglow_project_id = "project-a"

    with pytest.raises(ValueError):
        get_file_storage_quota(conn, strict=True)


@patch("app.services.manila.get_client")
def test_strict_file_storage_quota_keeps_unlimited_and_zero(mock_get_client):
    from app.services.manila import get_file_storage_quota

    client = MagicMock()
    client.get.return_value = {
        "quota_set": {
            "shares": {"limit": -1, "in_use": 0},
            "gigabytes": {"limit": 0, "in_use": 0},
        }
    }
    mock_get_client.return_value = client
    conn = MagicMock()
    conn._afterglow_project_id = "project-a"

    assert get_file_storage_quota(conn, strict=True) == {
        "shares": {"limit": -1, "in_use": 0},
        "gigabytes": {"limit": 0, "in_use": 0},
    }
    client.get.assert_has_calls(
        [
            call("quota-sets/project-a/detail", params={"usage": "true"}),
            call("shares/detail"),
        ]
    )


@patch("app.services.manila.get_client")
def test_access_rule_list_trusts_modern_empty_without_legacy_action(mock_get_client):
    from app.services.manila import list_access_rules

    client = MagicMock()
    mock_get_client.return_value = client
    client.get.return_value = {"access_list": []}
    client.post.side_effect = RuntimeError("legacy unsupported")
    assert list_access_rules(MagicMock(), "share-1", strict=True) == []
    assert list_access_rules(MagicMock(), "share-1") == []
    client.post.assert_not_called()


@pytest.mark.parametrize(
    "response", [{}, {"access_list": None}, {"access_list": [{}]}, {"access_rules": [{"id": "rule-1"}]}]
)
@patch("app.services.manila.get_client")
def test_strict_access_rule_list_rejects_incomplete_response(mock_get_client, response):
    from app.services.manila import list_access_rules

    client = MagicMock()
    mock_get_client.return_value = client
    client.get.return_value = response
    with pytest.raises(ValueError):
        list_access_rules(MagicMock(), "share-1", strict=True)
    client.post.assert_not_called()


@pytest.mark.parametrize("status", [401, 403, 409, 500, 503])
@patch("app.services.manila.get_client")
def test_exact_access_rule_get_propagates_non_not_found(mock_get_client, status):
    from app.services.manila import get_access_rule

    client = MagicMock()
    mock_get_client.return_value = client
    response = httpx.Response(status, request=httpx.Request("GET", "https://manila/share-access-rules/rule-1"))
    client.get.side_effect = httpx.HTTPStatusError("provider failure", request=response.request, response=response)
    with pytest.raises(httpx.HTTPStatusError):
        get_access_rule(MagicMock(), "share-1", "rule-1")


@patch("app.services.manila.get_client")
def test_exact_access_rule_get_only_not_found_proves_absence(mock_get_client):
    from app.services.manila import get_access_rule

    client = MagicMock()
    mock_get_client.return_value = client
    response = httpx.Response(404, request=httpx.Request("GET", "https://manila/share-access-rules/rule-1"))
    client.get.side_effect = httpx.HTTPStatusError("not found", request=response.request, response=response)
    assert get_access_rule(MagicMock(), "share-1", "rule-1") is None


@pytest.mark.parametrize("response", [{}, {"access": {}}, {"access": {"id": "rule-1", "share_id": "other"}}])
@patch("app.services.manila.get_client")
def test_exact_access_rule_get_rejects_incomplete_or_foreign(mock_get_client, response):
    from app.services.manila import get_access_rule

    client = MagicMock()
    mock_get_client.return_value = client
    client.get.return_value = response
    with pytest.raises(ValueError):
        get_access_rule(MagicMock(), "share-1", "rule-1")


def test_share_access_rules_read_native_manila_access_list_envelope():
    """Manila 2.45+ GET /share-access-rules returns `access_list`; strict readers must accept it."""
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from app.services import manila

    rule = {
        "id": "rule-1",
        "share_id": "share-1",
        "access_type": "cephx",
        "access_to": "reader",
        "access_level": "ro",
        "state": "active",
        "access_key": "AQnative==",
    }
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            requests.append(("GET", self.path, self.headers["X-OpenStack-Manila-API-Version"]))
            payload = json.dumps({"access_list": [rule]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self):
            requests.append(("POST", self.path, None))
            self.send_response(400)
            self.send_header("Content-Length", "0")
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = manila.ManilaClient(f"http://127.0.0.1:{server.server_port}/v2/project", "synthetic-token", "project")
        with patch.object(manila, "get_client", return_value=client):
            assert manila.list_access_rules(MagicMock(), "share-1", strict=True) == [rule]
            assert manila.list_access_rules(MagicMock(), "share-1") == [rule]
        assert manila._get_access_key(client, "share-1", "rule-1", timeout_seconds=3) == "AQnative=="
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    assert {method for method, _, _ in requests} == {"GET"}
    assert {version for _, _, version in requests} == {"2.65"}
    assert all(path == "/v2/project/share-access-rules?share_id=share-1" for _, path, _ in requests)
