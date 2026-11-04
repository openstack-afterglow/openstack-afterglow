"""Trove 유저 관리 함수 단위 테스트.

create_user 가 raw REST(POST /instances/{id}/users) 로 동작하고
host 필드를 포함하는지, list_users 가 host 를 응답에 포함하는지 검증.
"""

from unittest.mock import MagicMock

import pytest

from app.services import trove


def _make_conn() -> MagicMock:
    conn = MagicMock()
    resp = MagicMock()
    resp.status_code = 202
    resp.text = ""
    resp.json.return_value = {}
    conn.database.post.return_value = resp
    return conn


# ---------------------------------------------------------------------------
# create_user — raw REST 페이로드 구조 검증
# ---------------------------------------------------------------------------


def test_create_user_uses_raw_rest_post():
    """conn.database.post 가 /instances/{id}/users 경로로 호출되어야 한다."""
    conn = _make_conn()
    trove.create_user(conn, "inst-001", name="alice", password="pw123")

    call_args = conn.database.post.call_args
    path = call_args.args[0] if call_args.args else call_args.kwargs.get("url")
    assert path == "/instances/inst-001/users"


def test_create_user_payload_wraps_in_users_array():
    """페이로드는 {"users":[{...}]} 배열 형식이어야 한다 (Trove API 스펙)."""
    conn = _make_conn()
    trove.create_user(conn, "inst-001", name="alice", password="pw123", host="10.0.0.%")

    payload = conn.database.post.call_args.kwargs["json"]
    assert "users" in payload
    assert isinstance(payload["users"], list)
    assert len(payload["users"]) == 1
    user = payload["users"][0]
    assert user["name"] == "alice"
    assert user["password"] == "pw123"
    assert user["host"] == "10.0.0.%"


def test_create_user_default_host_is_wildcard():
    """host 미지정 시 기본값 '%' 가 페이로드에 포함되어야 한다."""
    conn = _make_conn()
    trove.create_user(conn, "inst-001", name="bob", password="pw")

    user = conn.database.post.call_args.kwargs["json"]["users"][0]
    assert user["host"] == "%"


def test_create_user_databases_formatted_as_dict_list():
    """databases 는 [{"name": ...}, ...] 형식으로 변환되어야 한다."""
    conn = _make_conn()
    trove.create_user(conn, "inst-001", name="alice", password="pw", databases=["db1", "db2"])

    user = conn.database.post.call_args.kwargs["json"]["users"][0]
    assert user["databases"] == [{"name": "db1"}, {"name": "db2"}]


def test_create_user_omits_databases_when_empty():
    """databases 가 None/빈 리스트면 페이로드 키에서 제외."""
    conn = _make_conn()
    trove.create_user(conn, "inst-001", name="alice", password="pw", databases=None)

    user = conn.database.post.call_args.kwargs["json"]["users"][0]
    assert "databases" not in user


# ---------------------------------------------------------------------------
# delete_user — host 식별 검증
# ---------------------------------------------------------------------------


def test_delete_user_passes_host_in_url():
    """삭제 URL 은 /instances/{id}/users/{name}@{host} 형식이어야 한다."""
    conn = MagicMock()
    trove.delete_user(conn, "inst-001", "alice", host="10.0.0.%")

    call_args = conn.database.delete.call_args
    path = call_args.args[0] if call_args.args else call_args.kwargs.get("url")
    # URL-encoded: alice%4010.0.0.%25
    assert path.startswith("/instances/inst-001/users/")
    assert "alice" in path
    # @ → %40, % → %25
    assert "%40" in path
    assert "%25" in path


def test_delete_user_default_host_is_wildcard():
    """host 미지정 시 기본 '%' 로 삭제 호출."""
    conn = MagicMock()
    trove.delete_user(conn, "inst-001", "alice")

    path = conn.database.delete.call_args.args[0]
    # alice@% → alice%40%25
    assert path == "/instances/inst-001/users/alice%40%25"


# ---------------------------------------------------------------------------
# list_users — host 필드 포함 검증
# ---------------------------------------------------------------------------


def test_list_users_includes_host():
    """raw REST 응답의 host 필드가 dict 에 포함되어야 한다."""
    conn = MagicMock()
    resp = MagicMock()
    resp.json.return_value = {"users": [{"name": "alice", "host": "10.0.0.%", "databases": [{"name": "db1"}]}]}
    conn.database.get.return_value = resp

    result = trove.list_users(conn, "inst-001")
    assert len(result) == 1
    assert result[0]["name"] == "alice"
    assert result[0]["host"] == "10.0.0.%"
    assert result[0]["databases"] == [{"name": "db1"}]


def test_list_users_defaults_host_to_wildcard():
    """user.host 누락 시 응답에 '%' 가 채워져야 한다."""
    conn = MagicMock()
    resp = MagicMock()
    resp.json.return_value = {"users": [{"name": "bob", "databases": []}]}
    conn.database.get.return_value = resp

    result = trove.list_users(conn, "inst-001")
    assert result[0]["host"] == "%"


def test_list_users_dedupes_duplicate_name_host():
    """Trove 가 동일 (name, host) entry 를 중복 반환해도 1개로 합쳐야 한다."""
    conn = MagicMock()
    resp = MagicMock()
    resp.json.return_value = {
        "users": [
            {"name": "healthcheck", "host": "%", "databases": []},
            {"name": "healthcheck", "host": "%", "databases": []},
            {"name": "alice", "host": "%", "databases": []},
        ]
    }
    conn.database.get.return_value = resp

    result = trove.list_users(conn, "inst-001")
    keys = {(u["name"], u["host"]) for u in result}
    assert len(result) == 2
    assert ("healthcheck", "%") in keys
    assert ("alice", "%") in keys


def test_list_users_failed_read_never_degrades_to_empty():
    """raw 상태 실패와 SDK fallback 실패는 호출자 예외이며 빈 유저 목록(정상)이 아니다."""
    from httpx import Request, Response
    from openstack.exceptions import HttpException

    conn = MagicMock()
    conn.database.get.return_value = Response(
        503, text="PRIVATE_NATIVE_USERS_CANARY", request=Request("GET", "http://native.invalid/users")
    )
    conn.database.users.side_effect = HttpException("PRIVATE_NATIVE_USERS_CANARY", http_status=503)

    with pytest.raises(HttpException):
        trove.list_users(conn, "inst-001")


def test_list_users_valid_empty_inventory_is_not_retried():
    """정상 빈 응답은 빈 목록이며 SDK로 같은 조회를 반복하지 않는다."""
    from httpx import Request, Response

    conn = MagicMock()
    conn.database.get.return_value = Response(
        200, json={"users": []}, request=Request("GET", "http://native.invalid/users")
    )

    assert trove.list_users(conn, "inst-001") == []
    conn.database.users.assert_not_called()


# ---------------------------------------------------------------------------
# _instance_to_dict — address_map 검증
# ---------------------------------------------------------------------------


def test_instance_to_dict_builds_address_map_from_addresses():
    """addresses dict 가 있으면 network_name → [ip] 매핑이 채워져야 한다."""
    inst = MagicMock()
    inst.id = "inst-001"
    inst.name = "db1"
    inst.status = "ACTIVE"
    inst.flavor = {"id": "5", "ram": 8192, "vcpus": 4}
    inst.volume = {"size": 10}
    inst.datastore = {"type": "mariadb"}
    inst.created_at = ""
    inst.updated_at = ""
    inst.hostname = "db1.local"
    inst.ip = None
    inst.addresses = {
        "private": [{"addr": "192.168.0.10"}, {"addr": "192.168.0.11"}],
        "public": [{"addr": "10.0.0.5"}],
    }
    inst.links = []

    result = trove._instance_to_dict(inst)
    assert result["address_map"] == {
        "private": ["192.168.0.10", "192.168.0.11"],
        "public": ["10.0.0.5"],
    }
    # ips 평탄화 fallback 도 동작
    assert "192.168.0.10" in result["ips"]
    assert "10.0.0.5" in result["ips"]


def test_instance_to_dict_address_map_empty_when_no_addresses():
    """addresses 가 비어있으면 address_map 은 빈 dict, ips 도 비어야 한다."""
    inst = MagicMock()
    inst.id = "inst-001"
    inst.name = "db1"
    inst.status = "ACTIVE"
    inst.flavor = {}
    inst.volume = {}
    inst.datastore = {}
    inst.created_at = ""
    inst.updated_at = ""
    inst.hostname = ""
    inst.ip = None
    inst.addresses = {}
    inst.links = []

    result = trove._instance_to_dict(inst)
    assert result["address_map"] == {}
    assert result["ips"] == []
    assert result["ip"] == ""


def test_instance_to_dict_prefers_ip_list_over_addresses():
    """i.ip 리스트가 있으면 우선 사용 (Trove 1차 응답 형식)."""
    inst = MagicMock()
    inst.id = "inst-001"
    inst.name = "db1"
    inst.status = "ACTIVE"
    inst.flavor = {}
    inst.volume = {}
    inst.datastore = {}
    inst.created_at = ""
    inst.updated_at = ""
    inst.hostname = ""
    inst.ip = ["192.168.1.1"]
    inst.addresses = {"private": [{"addr": "10.0.0.1"}]}
    inst.links = []

    result = trove._instance_to_dict(inst)
    assert result["ips"] == ["192.168.1.1"]
    # address_map 은 별도로 채워짐 (network 라벨 보존용)
    assert result["address_map"] == {"private": ["10.0.0.1"]}


# ---------------------------------------------------------------------------
# get_instance / list_instances — raw REST 호출 + addresses list 형식 검증
# ---------------------------------------------------------------------------


def test_get_instance_uses_raw_rest_and_extracts_ip():
    """get_instance 가 conn.database.get 으로 호출되고 ip 가 잘 추출되어야 한다."""
    conn = MagicMock()
    resp = MagicMock()
    resp.json.return_value = {
        "instance": {
            "id": "inst-001",
            "name": "db1",
            "status": "ACTIVE",
            "ip": ["192.168.0.38"],
            "flavor": {"id": "5", "ram": 8192, "vcpus": 4},
            "volume": {"size": 50, "used": 0.07},
            "datastore": {"type": "mariadb", "version": "10.11"},
            "created": "2026-05-10T17:08:00",
            "hostname": "",
            "addresses": {},
            "links": [],
        }
    }
    conn.database.get.return_value = resp

    result = trove.get_instance(conn, "inst-001")
    conn.database.get.assert_called_with("/instances/inst-001")
    assert result["ip"] == "192.168.0.38"
    assert result["ips"] == ["192.168.0.38"]
    assert result["flavor_id"] == "5"
    assert result["flavor_vcpus"] == 4
    assert result["volume_used"] == 0.07


def test_dict_from_raw_handles_addresses_list_format():
    """Trove >= Yoga 의 addresses list 형식 ({address, type}) 도 매핑되어야 한다."""
    raw = {
        "id": "inst-001",
        "name": "db1",
        "status": "ACTIVE",
        "addresses": [
            {"address": "192.168.0.38", "type": "private"},
            {"address": "10.0.0.5", "type": "public"},
        ],
    }
    result = trove._dict_from_raw(raw)
    assert result["address_map"] == {"private": ["192.168.0.38"], "public": ["10.0.0.5"]}
    assert "192.168.0.38" in result["ips"]


def test_list_instances_uses_raw_rest():
    """list_instances 가 conn.database.get('/instances') 로 호출되어야 한다."""
    conn = MagicMock()
    resp = MagicMock()
    resp.json.return_value = {
        "instances": [
            {"id": "i1", "name": "db1", "status": "ACTIVE", "ip": ["1.1.1.1"]},
            {"id": "i2", "name": "db2", "status": "BUILD"},
        ]
    }
    conn.database.get.return_value = resp

    result = trove.list_instances(conn)
    conn.database.get.assert_called_with("/instances")
    assert len(result) == 2
    assert result[0]["ips"] == ["1.1.1.1"]
    assert result[1]["status"] == "BUILD"
