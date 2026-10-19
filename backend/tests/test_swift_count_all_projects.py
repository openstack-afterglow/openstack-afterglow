"""swift.count_containers_all_projects — admin fan-out 컨테이너 합산 단위 테스트."""

import threading
import time
from unittest.mock import MagicMock, patch

from keystoneauth1.exceptions.http import Unauthorized
from openstack.exceptions import ResourceNotFound

from app.services import swift


def _conn_with_containers(*names: str) -> MagicMock:
    conn = MagicMock()
    resp = MagicMock()
    resp.headers = {"X-Account-Container-Count": str(len(names))}
    conn.object_store.head = MagicMock(return_value=resp)
    conn.object_store.get_endpoint = MagicMock(return_value="http://swift")
    conn._afterglow_project_id = "p"
    conn.close = MagicMock()
    return conn


def test_count_all_projects_sums_containers_across_projects():
    """여러 프로젝트의 컨테이너 수가 합산되고 connection이 닫힌다."""
    projects = [{"id": "p1", "name": "A"}, {"id": "p2", "name": "B"}]
    conn_p1 = _conn_with_containers("a", "b")  # 2
    conn_p2 = _conn_with_containers("c", "d", "e")  # 3

    with (
        patch("app.services.keystone.list_system_projects", return_value=projects),
        patch(
            "app.services.keystone.get_admin_connection_for_project",
            side_effect=[conn_p1, conn_p2],
        ),
    ):
        total = swift.count_containers_all_projects("admin-token")

    assert total == 5
    conn_p1.close.assert_called_once()
    conn_p2.close.assert_called_once()


def test_count_all_projects_skips_unauthorized_project():
    """한 프로젝트 connection 이 401이면 그 프로젝트만 0 처리하고 나머지는 합산."""
    projects = [{"id": "p1", "name": "A"}, {"id": "p2", "name": "B"}]
    conn_p2 = _conn_with_containers("c")  # 1

    def _get_conn(pid: str):
        if pid == "p1":
            raise Unauthorized("no admin role")
        return conn_p2

    with (
        patch("app.services.keystone.list_system_projects", return_value=projects),
        patch("app.services.keystone.get_admin_connection_for_project", side_effect=_get_conn),
    ):
        total = swift.count_containers_all_projects("admin-token")

    assert total == 1
    conn_p2.close.assert_called_once()


def test_count_all_projects_returns_zero_when_keystone_fails():
    """Keystone 프로젝트 목록 조회 실패 시 0 (silent fail)."""
    with patch("app.services.keystone.list_system_projects", side_effect=Exception("keystone down")):
        assert swift.count_containers_all_projects("admin-token") == 0


def test_count_all_projects_skips_project_without_id():
    """id 없는 프로젝트 항목은 skip 한다."""
    projects = [{"name": "no-id"}, None, {}, {"id": "p2", "name": "B"}]
    conn_p2 = _conn_with_containers("c", "d")  # 2

    with (
        patch("app.services.keystone.list_system_projects", return_value=projects),
        patch(
            "app.services.keystone.get_admin_connection_for_project",
            return_value=conn_p2,
        ),
    ):
        total = swift.count_containers_all_projects("admin-token")

    assert total == 2
    conn_p2.close.assert_called_once()


def test_count_containers_uses_head_request_and_parses_count():
    """count_containers가 Swift HEAD 요청을 보내고 X-Account-Container-Count를 파싱한다."""
    conn = MagicMock()
    resp = MagicMock()
    resp.headers = {"X-Account-Container-Count": "42"}
    conn.object_store.head.return_value = resp

    count = swift.count_containers(conn, timeout=3.5)

    assert count == 42
    conn.object_store.head.assert_called_once_with("/", connect_retries=0, raise_exc=True, timeout=3.5)

    # 404 account not found -> returns 0
    conn_404 = MagicMock()
    conn_404.object_store.head.side_effect = ResourceNotFound("no account")
    assert swift.count_containers(conn_404) == 0

    # 401 unauthorized -> returns 0
    conn_401 = MagicMock()
    conn_401.object_store.head.side_effect = Unauthorized("unauthorized")
    assert swift.count_containers(conn_401) == 0


def test_count_all_projects_sets_timeouts_and_passes_arguments():
    """session timeout 및 request timeout 매개변수를 올바르게 전달한다."""
    projects = [{"id": "p1"}]
    conn_p1 = _conn_with_containers("a", "b")

    with (
        patch("app.services.keystone.list_system_projects", return_value=projects),
        patch("app.services.keystone.get_admin_connection_for_project", return_value=conn_p1),
    ):
        total = swift.count_containers_all_projects("admin-token", per_request_timeout=1.5)

    assert total == 2
    assert conn_p1.session.timeout == 1.5
    conn_p1.object_store.head.assert_called_once_with("/", connect_retries=0, raise_exc=True, timeout=1.5)


def test_count_all_projects_executes_concurrently():
    """여러 프로젝트 조회가 ThreadPoolExecutor를 통해 동시 실행된다."""
    projects = [{"id": "p1"}, {"id": "p2"}]
    barrier = threading.Barrier(2)

    def _sync_conn(pid: str):
        conn = MagicMock()

        def _head(*args, **kwargs):
            barrier.wait(timeout=1.0)
            r = MagicMock()
            r.headers = {"X-Account-Container-Count": "1"}
            return r

        conn.object_store.head.side_effect = _head
        conn.close = MagicMock()
        return conn

    with (
        patch("app.services.keystone.list_system_projects", return_value=projects),
        patch("app.services.keystone.get_admin_connection_for_project", side_effect=_sync_conn),
    ):
        total = swift.count_containers_all_projects("admin-token", max_workers=2)

    assert total == 2


def test_count_all_projects_returns_zero_on_total_budget_timeout():
    """총 예산 안에 0을 반환하고 실행 중인 connection도 종료 후 닫는다."""
    projects = [{"id": "p1"}, {"id": "p2"}]
    conn_p1 = _conn_with_containers("a", "b", "c")
    unblock_event = threading.Event()
    closed_event = threading.Event()

    def _slow_head(*args, **kwargs):
        unblock_event.wait(timeout=2.0)
        r = MagicMock()
        r.headers = {"X-Account-Container-Count": "10"}
        return r

    conn_p2 = MagicMock()
    conn_p2.object_store.head.side_effect = _slow_head
    conn_p2.close = MagicMock(side_effect=closed_event.set)

    started = time.monotonic()
    try:
        with (
            patch("app.services.keystone.list_system_projects", return_value=projects),
            patch(
                "app.services.keystone.get_admin_connection_for_project",
                side_effect=[conn_p1, conn_p2],
            ),
        ):
            total = swift.count_containers_all_projects("admin-token", total_budget=0.05)
        elapsed = time.monotonic() - started

        assert total == 0
        assert elapsed < 0.5
    finally:
        unblock_event.set()

    assert closed_event.wait(timeout=1.0)
    conn_p1.close.assert_called_once()
    conn_p2.close.assert_called_once()


def test_count_all_projects_closes_all_connections():
    """예외 발생 여부와 상관없이 모든 생성된 connection이 finally에서 닫힌다."""
    projects = [{"id": "p1"}, {"id": "p2"}, {"id": "p3"}]
    conn_p1 = _conn_with_containers("a")
    conn_p2 = MagicMock()
    conn_p2.object_store.head.side_effect = Exception("swift error")
    conn_p2.close = MagicMock()

    def _get_conn(pid: str):
        if pid == "p1":
            return conn_p1
        elif pid == "p2":
            return conn_p2
        else:
            raise Unauthorized("connection failed")

    with (
        patch("app.services.keystone.list_system_projects", return_value=projects),
        patch("app.services.keystone.get_admin_connection_for_project", side_effect=_get_conn),
    ):
        total = swift.count_containers_all_projects("admin-token")

    assert total == 1
    conn_p1.close.assert_called_once()
    conn_p2.close.assert_called_once()
