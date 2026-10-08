"""Owner-only browser package-key controls; secret is returned once upstream."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from app.api.palimpsest.package_protocol import PackageRoute
from app.api.palimpsest.packages import (
    checked_payload,
    current_namespace,
    package_browser_identity,
    package_browser_request,
    read_query,
)
from app.services.palimpsest_authorization import authorize_current_package_request

router = APIRouter(route_class=PackageRoute)


async def key_control(request: Request, info: dict, *, key_id: str | None = None) -> Response:
    read_query(request, set())
    # A role-only preflight precedes namespace lookup as well as key mutation.
    suffix = "keys"
    if key_id is not None:
        try:
            key_id = UUID(key_id).hex
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Invalid key ID") from exc
        suffix += f"/{key_id}"
    await authorize_current_package_request(request, f"/v1/projects/{info['project_id']}/{suffix}", info)
    namespace, failure = await current_namespace(request, info)
    if failure is not None:
        return failure
    path = f"/v1/projects/{namespace}/{suffix}"
    response = await package_browser_request(
        request,
        path,
        method=request.method,
        forward_body=request.method == "POST",
    )
    if response.status_code < 400:
        expected = {"GET": 200, "POST": 201, "DELETE": 204}[request.method]
        if response.status_code != expected:
            raise HTTPException(status_code=503, detail="Palimpsest Hub returned an invalid key response")
        if expected != 204:
            checked_payload(response, info, namespace, keys=True)
    return response


@router.get("")
async def list_keys(request: Request, info: dict = Depends(package_browser_identity)) -> Response:
    return await key_control(request, info)


@router.post("")
async def create_key(request: Request, info: dict = Depends(package_browser_identity)) -> Response:
    return await key_control(request, info)


@router.delete("/{key_id}")
async def revoke_key(key_id: str, request: Request, info: dict = Depends(package_browser_identity)) -> Response:
    return await key_control(request, info, key_id=key_id)
