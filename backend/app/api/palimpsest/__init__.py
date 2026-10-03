"""Palimpsest (레이어드 VM) API.

도메인 정의와 digest 규칙은 `docs/palimpsest.md` 참조.
"""

from app.api.palimpsest.admin import router as palimpsest_admin_router
from app.api.palimpsest.builds import router as palimpsest_builds_router
from app.api.palimpsest.hub import router as palimpsest_hub_router
from app.api.palimpsest.layers import router as palimpsest_layers_router
from app.api.palimpsest.package_keys import router as palimpsest_package_keys_router
from app.api.palimpsest.packages import router as palimpsest_packages_router

__all__ = [
    "palimpsest_admin_router",
    "palimpsest_builds_router",
    "palimpsest_hub_router",
    "palimpsest_layers_router",
    "palimpsest_package_keys_router",
    "palimpsest_packages_router",
]
