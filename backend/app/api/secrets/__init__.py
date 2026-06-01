"""Barbican Key Manager API routers — lazy import."""

_ROUTERS = {
    "secrets_router": ".secrets",
    "containers_router": ".containers",
    "orders_router": ".orders",
}


def __getattr__(name: str):
    if name in _ROUTERS:
        import importlib

        mod = importlib.import_module(_ROUTERS[name], __package__)
        return mod.router
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = list(_ROUTERS)
