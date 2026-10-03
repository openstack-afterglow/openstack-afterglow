"""Owner-only browser package-key controls; secret is returned once upstream."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from app.api.palimpsest.package_protocol import PackageRoute
from app.api.palimpsest.packages import (
    checked_payload,
    current_namespace,
    package_browser_identity,
    read_query,
)
from app.services.service_proxy import package_member_request

router = APIRouter(route_class=PackageRoute)


async def key_control(request: Request, info: dict, *, key_id: str | None = None) -> Response:
    read_query(request, set())
    namespace, failure = await current_namespace(request, info)
    if failure is not None:
        return failure
    path = f"/v1/projects/{namespace}/keys"
    if key_id is not None:
        try:
            key_id = UUID(key_id).hex
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Invalid key ID") from exc
        path += f"/{key_id}"
    response = await package_member_request(
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
