"""Deterministic administrator gate for isolated endpoint tests.

Production ``require_admin`` re-validates the caller's native token, domain and exact
system:all grant on every request; its fail-closed behavior has dedicated regressions in
``test_auth_domain_boundaries.py``. Endpoint tests that already substitute
``get_token_info`` with a synthetic identity use this gate instead of a live Keystone.
"""

from fastapi import Depends, HTTPException

from app.api.deps import get_token_info


async def synthetic_verified_admin(token_info: dict = Depends(get_token_info)) -> dict:
    if token_info.get("is_system_admin") is not True:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "system_admin_required",
                "message": "Current system:all administrator authority is required",
            },
        )
    token_info["_live_system_admin"] = True
    return token_info
