"""Admin-project Swift account HEAD counts preserve unreadable and failed observations."""

import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from keystoneauth1.exceptions.http import Forbidden, Unauthorized
from openstack.exceptions import ResourceNotFound

from app.services import swift


@pytest.fixture
def accounts(monkeypatch):
    conn = MagicMock()
    conn._afterglow_authenticated_project_id = "executor"
    conn.object_store.get_endpoint.return_value = "https://swift.test/swift/v1/AUTH_executor"
    conn.identity.projects.return_value = iter([SimpleNamespace(id="p1"), SimpleNamespace(id="p2")])
    original_timeout = conn.session.timeout
    proxies = {pid: MagicMock() for pid in ("p1", "p2")}
    for proxy in proxies.values():
        proxy.head.return_value = SimpleNamespace(status_code=204, headers={"X-Account-Container-Count": "2"})

    def proxy(**kwargs):
        assert kwargs["session"] is conn.session
        assert kwargs["service_type"] == "object-store"
        return proxies[kwargs["endpoint_override"].rsplit("AUTH_", 1)[1]]

    monkeypatch.setattr(swift, "_get_swift_endpoint", lambda conn: None)
    monkeypatch.setattr("openstack.object_store.v1._proxy.Proxy", proxy)
    yield conn, proxies
    assert conn.session.timeout is original_timeout
    conn.close.assert_not_called()
    conn.object_store.head.assert_not_called()


def test_counts_readable_accounts_with_fixed_admin_project_session(accounts):
    conn, proxies = accounts
    proxies["p2"].head.return_value.headers = {"x-account-container-count": "3"}
    assert swift.count_containers_all_projects(conn, per_request_timeout=1.5) == swift.AccountContainerCount(5, 0)
    for proxy in proxies.values():
        proxy.head.assert_called_once_with("/", connect_retries=0, raise_exc=True, timeout=1.5)


def test_account_not_found_is_zero_not_unreadable(accounts):
    conn, proxies = accounts
    proxies["p2"].head.side_effect = ResourceNotFound("account not initialized")
    assert swift.count_containers_all_projects(conn) == swift.AccountContainerCount(2, 0)


@pytest.mark.parametrize("error", [Unauthorized("unauthorized"), Forbidden("denied")])
def test_auth_denial_is_unreadable_not_empty(accounts, error):
    conn, proxies = accounts
    proxies["p2"].head.side_effect = error
    assert swift.count_containers_all_projects(conn) == swift.AccountContainerCount(2, 1)


def test_all_unreadable_accounts_remain_explicit(accounts):
    conn, proxies = accounts
    for proxy in proxies.values():
        proxy.head.side_effect = Forbidden("may be denied or never created")
    assert swift.count_containers_all_projects(conn) == swift.AccountContainerCount(0, 2)


@pytest.mark.parametrize("error", [RuntimeError("provider unavailable"), TimeoutError("request expired")])
def test_other_account_failures_reject_partial_sum(accounts, error):
    conn, proxies = accounts
    proxies["p2"].head.side_effect = error
    with pytest.raises(type(error)):
        swift.count_containers_all_projects(conn)


@pytest.mark.parametrize("value", [None, "", "-1", "1.5", "unknown", " 2", "٢", 2, True])
def test_invalid_count_headers_reject_partial_sum(accounts, value):
    conn, proxies = accounts
    proxies["p2"].head.return_value.headers = {"X-Account-Container-Count": value}
    with pytest.raises(ValueError, match="Invalid Swift container count"):
        swift.count_containers_all_projects(conn)


def test_unexpected_account_response_is_not_empty(accounts):
    conn, proxies = accounts
    proxies["p2"].head.return_value.status_code = 302
    with pytest.raises(RuntimeError, match="HTTP 302"):
        swift.count_containers_all_projects(conn)


def test_empty_project_inventory_is_zero(accounts):
    conn, _ = accounts
    conn.identity.projects.return_value = iter([])
    assert swift.count_containers_all_projects(conn) == swift.AccountContainerCount(0, 0)


@pytest.mark.parametrize("ids", [[None], [""], [42], ["p1", "p1"]])
def test_invalid_project_inventory_is_not_partial(accounts, ids):
    conn, proxies = accounts
    conn.identity.projects.return_value = iter(SimpleNamespace(id=pid) for pid in ids)
    with pytest.raises(ValueError, match="Invalid project inventory"):
        swift.count_containers_all_projects(conn)
    for proxy in proxies.values():
        proxy.head.assert_not_called()


def test_project_pagination_failure_is_not_partial(accounts):
    conn, proxies = accounts

    def projects():
        yield SimpleNamespace(id="p1")
        raise RuntimeError("later identity page failed")

    conn.identity.projects.return_value = projects()
    with pytest.raises(RuntimeError, match="later identity page failed"):
        swift.count_containers_all_projects(conn)
    for proxy in proxies.values():
        proxy.head.assert_not_called()


def test_account_reads_execute_concurrently(accounts):
    conn, proxies = accounts
    barrier = threading.Barrier(2)

    def head(*args, **kwargs):
        barrier.wait(timeout=1)
        return SimpleNamespace(status_code=204, headers={"X-Account-Container-Count": "1"})

    for proxy in proxies.values():
        proxy.head.side_effect = head
    assert swift.count_containers_all_projects(conn, max_workers=2) == swift.AccountContainerCount(2, 0)


def test_total_budget_timeout_rejects_partial_sum_without_waiting(accounts):
    conn, proxies = accounts
    unblock, finished = threading.Event(), threading.Event()

    def slow_head(*args, **kwargs):
        try:
            unblock.wait(timeout=2)
            return SimpleNamespace(status_code=204, headers={"X-Account-Container-Count": "10"})
        finally:
            finished.set()

    proxies["p2"].head.side_effect = slow_head
    started = time.monotonic()
    try:
        with pytest.raises(TimeoutError, match="inventory incomplete"):
            swift.count_containers_all_projects(conn, total_budget=0.05)
        assert time.monotonic() - started < 0.5
    finally:
        unblock.set()
        assert finished.wait(timeout=1)


def test_unverified_admin_endpoint_fails_before_account_read(accounts):
    conn, proxies = accounts
    conn.object_store.get_endpoint.return_value = "https://swift.test/v1/AUTH_other"
    with pytest.raises(ValueError, match="unverified"):
        swift.count_containers_all_projects(conn)
    for proxy in proxies.values():
        proxy.head.assert_not_called()


def test_count_containers_uses_head_request_and_parses_count(monkeypatch):
    monkeypatch.setattr(swift, "_apply_endpoint_override", lambda conn: None)
    conn = MagicMock()
    conn.object_store.head.return_value.headers = {"X-Account-Container-Count": "42"}
    assert swift.count_containers(conn, timeout=3.5) == 42
    conn.object_store.head.assert_called_once_with("/", connect_retries=0, raise_exc=True, timeout=3.5)
    conn.object_store.head.side_effect = ResourceNotFound("no account")
    assert swift.count_containers(conn) == 0
    conn.object_store.head.side_effect = Unauthorized("unauthorized")
    assert swift.count_containers(conn) == 0
