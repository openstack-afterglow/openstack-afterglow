"""Launcher factory preserving the socket peer before Uvicorn's existing rewrite.

Launch with --factory --no-proxy-headers; only this outer wrapper may stamp the
private ASGI extension. Without it analytics treats the rewritten peer as unknown.
Authentication still sees the same Uvicorn trusted-proxies rewrite as before.
"""

import os


class OriginalPeerMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            scope = dict(scope)
            scope["extensions"] = dict(scope.get("extensions", {}))
            scope["extensions"]["afterglow.analytics.original_peer"] = scope.get("client")
        await self.app(scope, receive, send)


def create_app():
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

    from app.main import app

    # Match Uvicorn Config's existing environment/default contract exactly.
    # Analytics proxy CIDRs intentionally do not govern authentication addresses.
    return OriginalPeerMiddleware(
        ProxyHeadersMiddleware(app, trusted_hosts=os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1"))
    )
