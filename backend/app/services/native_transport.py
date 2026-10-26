"""Process-owned sockets; operation-owned credentials, cookies and discovery.

Never share a requests/Keystoneauth Session or SDK Connection between callers.
Only the thread-safe urllib3 pools beneath their adapter survive client closure.
"""

from __future__ import annotations

import atexit
import threading
from typing import TYPE_CHECKING

import requests
from keystoneauth1 import session as ks_session

if TYPE_CHECKING:
    import openstack


class _SharedAdapter(ks_session.TCPKeepAliveAdapter):
    def __init__(self):
        self._proxy_lock = threading.Lock()
        super().__init__()

    def proxy_manager_for(self, proxy, **proxy_kwargs):
        # Requests' lazy proxy-manager dictionary is not synchronized. Network
        # calls still run concurrently through urllib3's own pool locks.
        with self._proxy_lock:
            return super().proxy_manager_for(proxy, **proxy_kwargs)

    def close(self):
        """Borrowing sessions do not own these sockets; close_pools does."""

    def dispose(self):
        with self._proxy_lock:
            for manager in (self.poolmanager, *self.proxy_manager.values()):
                # urllib3.clear() drops references without closing a pool held
                # by a consumed Response. Drain first, then close sockets even
                # when callers retain those responses for diagnostics.
                with manager.pools.lock:
                    for key in manager.pools.keys():  # noqa: SIM118 — urllib3 forbids direct iteration.
                        manager.pools[key].close()
                    manager.clear()
            self.proxy_manager.clear()


_lock = threading.Lock()
_adapter: _SharedAdapter | None = None


def _mount_pools(http: requests.Session) -> None:
    global _adapter
    with _lock:
        if _adapter is None:
            _adapter = _SharedAdapter()
        adapter = _adapter
    for scheme in ("http://", "https://"):
        previous = http.adapters.get(scheme)
        if previous is not adapter:
            if previous is not None:
                previous.close()
            http.mount(scheme, adapter)


def create_session(**kwargs) -> ks_session.Session:
    """Create independent auth/session state backed by process-owned sockets."""
    http = requests.Session()
    _mount_pools(http)
    try:
        return ks_session.Session(session=http, **kwargs)
    except BaseException:
        http.close()
        raise


def connect(**kwargs) -> openstack.connection.Connection:
    """Preserve SDK auth/config loading while replacing only its HTTP pools."""
    import openstack

    conn = openstack.connect(**kwargs)
    try:
        conn.config.set_session_constructor(create_session)
        # A vendor hook or CloudRegion name may already have initialized it.
        # This accessor constructs transport, not a token exchange.
        _mount_pools(conn.session.session)
    except BaseException:
        conn.close()
        raise
    return conn


def close_pools() -> None:
    """Release idle sockets after API/worker work has drained (also at exit)."""
    global _adapter
    with _lock:
        adapter, _adapter = _adapter, None
    if adapter is not None:
        adapter.dispose()


atexit.register(close_pools)
