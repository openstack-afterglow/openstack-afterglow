"""Admin credential API. Mount router under /api/v1/admin."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from keystoneauth1 import exceptions as auth_exc
from openstack import exceptions as sdk_exc

from app.api.common.errors import public_service_error
from app.api.deps import get_os_conn, get_token_info, require_admin
from app.models.admin_credentials import (
    ApplicationCredentialCreate,
    Identifier,
    UserCredentialCreate,
    UserCredentialUpdate,
)
from app.services import admin_credentials as svc

NO_STORE = {"Cache-Control": "no-store, private", "Pragma": "no-cache"}
# A bare ``= Query(...)`` default discards the Annotated identifier constraints, so
# an empty or malformed ``?domain_id=`` would otherwise reach native lookups.
QueryIdentifier = Annotated[Identifier, Query()]
OptionalQueryIdentifier = Annotated[Identifier | None, Query()]


class CredentialRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def guarded(request):
            try:
                response = await handler(request)
            except RequestValidationError:
                # Pydantic input/ctx may contain a complete credential blob.
                response = JSONResponse({"detail": "credential_invalid_input"}, status_code=422)
            except HTTPException as exc:
                response = JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)
            response.headers.update(NO_STORE)
            return response

        return guarded


router = APIRouter(route_class=CredentialRoute, dependencies=[Depends(require_admin)])


async def native(call):
    try:
        return await asyncio.to_thread(call)
    except HTTPException:
        raise
    except svc.ScopeDenied:
        raise HTTPException(403, "credential_scope_denied") from None
    except svc.RollbackFailed:
        # Issuance committed and revocation failed; never label this a normal
        # denial/not-found that implies no live credential was created.
        raise public_service_error(502, "credential_rollback_failed") from None
    except Exception as exc:
        status = getattr(exc, "status_code", None) or getattr(exc, "http_status", None)
        if isinstance(exc, (sdk_exc.ForbiddenException, auth_exc.Forbidden)) or status in (401, 403):
            code, detail = 403, "credential_native_denied"
        elif isinstance(exc, (sdk_exc.ResourceNotFound, auth_exc.NotFound)) or status == 404:
            code, detail = 404, "credential_not_found"
        elif status == 409:
            code, detail = 409, "credential_conflict"
        elif status in (400, 422):
            code, detail = status, "credential_native_invalid"
        else:
            code, detail = 503, "credential_unavailable"
        raise HTTPException(code, detail) from None


@router.get("/application-credentials/context")
async def application_context(
    domain_id: QueryIdentifier, conn=Depends(get_os_conn), token_info=Depends(get_token_info)
):
    return await native(lambda: svc.creation_context(conn, token_info, domain_id))


@router.get("/application-credentials")
async def list_applications(
    domain_id: QueryIdentifier,
    user_id: OptionalQueryIdentifier = None,
    conn=Depends(get_os_conn),
    token_info=Depends(get_token_info),
):
    user_id = user_id or token_info["user_id"]
    return await native(lambda: svc.list_applications(conn, domain_id, user_id))


@router.get("/application-credentials/{credential_id}")
async def get_application(
    credential_id: Identifier,
    domain_id: QueryIdentifier,
    user_id: OptionalQueryIdentifier = None,
    conn=Depends(get_os_conn),
    token_info=Depends(get_token_info),
):
    user_id = user_id or token_info["user_id"]
    return await native(
        lambda: svc.application_metadata(
            svc.get_application(conn, domain_id, user_id, credential_id), user_id, domain_id
        )
    )


@router.post("/application-credentials", status_code=201)
async def create_application(
    body: ApplicationCredentialCreate,
    domain_id: QueryIdentifier,
    conn=Depends(get_os_conn),
    token_info=Depends(get_token_info),
):
    return await native(lambda: svc.create_application(conn, token_info, body, domain_id))


@router.delete("/application-credentials/{credential_id}", status_code=204)
async def delete_application(
    credential_id: Identifier,
    domain_id: QueryIdentifier,
    user_id: OptionalQueryIdentifier = None,
    conn=Depends(get_os_conn),
    token_info=Depends(get_token_info),
):
    user_id = user_id or token_info["user_id"]
    await native(lambda: svc.delete_application(conn, domain_id, user_id, credential_id))
    return Response(status_code=204, headers=NO_STORE)


@router.get("/user-credentials")
async def list_user_credentials(
    domain_id: QueryIdentifier, user_id: OptionalQueryIdentifier = None, conn=Depends(get_os_conn)
):
    return await native(lambda: svc.list_user_credentials(conn, domain_id, user_id))


@router.get("/user-credentials/{credential_id}")
async def get_user_credential(
    credential_id: Identifier,
    domain_id: QueryIdentifier,
    sensitive: bool = Query(False),
    conn=Depends(get_os_conn),
):
    def fetch():
        resource = svc.get_user_credential(conn, domain_id, credential_id)
        result = svc.user_metadata(resource, domain_id)
        if sensitive:
            result["blob"] = svc.value(resource, "blob")
        return result

    return await native(fetch)


@router.post("/user-credentials", status_code=201)
async def create_user_credential(body: UserCredentialCreate, domain_id: QueryIdentifier, conn=Depends(get_os_conn)):
    return await native(lambda: svc.create_user_credential(conn, domain_id, body))


@router.patch("/user-credentials/{credential_id}")
async def update_user_credential(
    credential_id: Identifier, body: UserCredentialUpdate, domain_id: QueryIdentifier, conn=Depends(get_os_conn)
):
    return await native(lambda: svc.update_user_credential(conn, domain_id, credential_id, body))


@router.delete("/user-credentials/{credential_id}", status_code=204)
async def delete_user_credential(credential_id: Identifier, domain_id: QueryIdentifier, conn=Depends(get_os_conn)):
    await native(lambda: svc.delete_user_credential(conn, domain_id, credential_id))
    return Response(status_code=204, headers=NO_STORE)
