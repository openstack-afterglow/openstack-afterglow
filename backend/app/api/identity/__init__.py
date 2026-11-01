"""Identity API routers — lazy import to reduce startup time."""

_ROUTERS = {
    "admin_router": ".admin",
    "auth_router": ".auth",
    "mcp_access_router": ".mcp_access",
    "compute_pools_router": ".compute_pools",
    "managed_flavors_router": ".managed_flavors",
}


def __getattr__(name: str):
    if name in _ROUTERS:
        import importlib

        mod = importlib.import_module(_ROUTERS[name], __package__)
        return mod.router
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = list(_ROUTERS)
