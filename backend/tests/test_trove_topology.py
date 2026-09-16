"""Trove 토폴로지 IP 헬퍼 단위 테스트 (`trove.topology_database_ips`)."""

from unittest.mock import MagicMock, patch

from app.services import trove


def _inst(*ips: str) -> dict:
    return {"id": "db-1", "ips": list(ips)}


def test_topology_database_ips_unions_ips_across_instances():
    """여러 Trove 인스턴스의 ips 를 합집합으로 모은다."""
    conn = MagicMock()
    instances = [
        {"id": "db-1", "ips": ["10.0.0.11", "203.0.113.11"]},
        {"id": "db-2", "ips": ["10.0.0.12"]},
    ]
    with patch.object(trove, "list_instances", return_value=instances) as lst:
        result = trove.topology_database_ips(conn)

    assert result == {"10.0.0.11", "203.0.113.11", "10.0.0.12"}
    lst.assert_called_once_with(conn)


def test_topology_database_ips_skips_empty_and_missing_ips():
    """ips 가 없거나 빈 문자열인 항목은 집합에서 제외한다 (빈 addr 오탐 방지)."""
    conn = MagicMock()
    instances = [
        {"id": "db-1", "ips": ["10.0.0.11", ""]},
        {"id": "db-2"},  # ips 키 자체가 없음
        {"id": "db-3", "ips": None},
    ]
    with patch.object(trove, "list_instances", return_value=instances):
        assert trove.topology_database_ips(conn) == {"10.0.0.11"}


def test_topology_database_ips_extracts_addr_from_dict_entries():
    """`ips` 항목이 dict 인 Trove 응답도 address/addr 키에서 IP 문자열을 꺼낸다."""
    conn = MagicMock()
    instances = [
        {"id": "db-1", "ips": [{"address": "10.0.0.11"}, {"addr": "10.0.0.12"}]},
        {"id": "db-2", "ips": [{"type": "private"}, 12345]},  # IP 없는 dict / 문자열 아님 → 제외
    ]
    with patch.object(trove, "list_instances", return_value=instances):
        assert trove.topology_database_ips(conn) == {"10.0.0.11", "10.0.0.12"}


def test_topology_database_ips_returns_empty_set_when_trove_absent():
    """Trove 가 없어 목록이 빈 리스트면 빈 집합을 반환한다 (정상 상황)."""
    conn = MagicMock()
    with patch.object(trove, "list_instances", return_value=[]):
        assert trove.topology_database_ips(conn) == set()


def test_topology_database_ips_swallows_listing_exception():
    """목록 조회가 예외를 던져도 예외를 전파하지 않고 빈 집합을 반환한다."""
    conn = MagicMock()
    with patch.object(trove, "list_instances", side_effect=RuntimeError("Trove 없음")):
        assert trove.topology_database_ips(conn) == set()


def test_topology_database_ips_all_projects_uses_admin_listing():
    """all_projects=True 는 admin mgmt 목록을 사용하고 프로젝트 목록은 호출하지 않는다."""
    conn = MagicMock()
    with (
        patch.object(
            trove,
            "list_instances_admin_all_projects",
            return_value=[_inst("10.0.0.21"), _inst("10.0.0.22")],
        ) as admin_lst,
        patch.object(trove, "list_instances") as project_lst,
    ):
        result = trove.topology_database_ips(conn, all_projects=True)

    assert result == {"10.0.0.21", "10.0.0.22"}
    admin_lst.assert_called_once_with(conn)
    project_lst.assert_not_called()


def test_topology_database_ips_all_projects_swallows_exception():
    """all_projects 경로의 예외도 빈 집합으로 흡수한다."""
    conn = MagicMock()
    with patch.object(trove, "list_instances_admin_all_projects", side_effect=RuntimeError("mgmt 미지원")):
        assert trove.topology_database_ips(conn, all_projects=True) == set()
