"""Native package error responses without changing legacy JWT Hub errors."""

from uuid import uuid4

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute


def native_error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        {"error": {"code": code, "message": message, "request_id": uuid4().hex}},
        status_code=status,
        headers={"cache-control": "private, no-store"},
    )


class PackageRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def handle(request: Request):
            try:
                return await handler(request)
            except HTTPException as exc:
                native = request.url.path.startswith(
                    (
                        "/api/v1/palimpsest/packages",
                        "/api/v1/palimpsest/package-keys",
                    )
                ) or request.headers.get("authorization", "").lower().startswith("bearer ppk_v1_")
                if not native:
                    raise
                code = {
                    401: "AUTH_REQUIRED",
                    403: "PROJECT_SCOPE_MISMATCH",
                    404: "NOT_FOUND",
                    409: "CONFLICT",
                    422: "INVALID_REQUEST",
                    503: "DEPENDENCY_UNAVAILABLE",
                }.get(exc.status_code, "REQUEST_FAILED")
                # All local details are static; upstream native envelopes are returned unchanged.
                return native_error(exc.status_code, code, str(exc.detail))

        return handle
