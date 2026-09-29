"""Lumen API routers — lazy import to reduce startup time."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import FastAPI

_ROUTERS = {
    "lumen_callback_router": ".callback",
    "lumen_proxy_router": ".proxy",
    "lumen_realtime_router": ".realtime",
}


def register_lumen(app: FastAPI, settings: Any = None) -> bool:
    """Mount Lumen routers on app if service_chat_enabled is True."""
    if settings is None:
        from app.config import get_settings

        settings = get_settings()

    if not getattr(settings, "service_chat_enabled", False):
        return False

    from app.api.lumen.callback import router as lumen_callback_router
    from app.api.lumen.proxy import router as lumen_proxy_router
    from app.api.lumen.realtime import router as lumen_realtime_router

    # Browser callback is state-bound and intentionally has no browser bearer dependency.
    app.include_router(lumen_callback_router, prefix="/api/v1/chat", tags=["chat-callback"])
    app.include_router(lumen_realtime_router, prefix="/api/v1/chat", tags=["chat-realtime"])
    app.include_router(lumen_proxy_router, prefix="/api/v1/chat", tags=["chat"])
    return True


def __getattr__(name: str):
    if name in _ROUTERS:
        import importlib

        mod = importlib.import_module(_ROUTERS[name], __package__)
        return mod.router
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["register_lumen", *_ROUTERS]
