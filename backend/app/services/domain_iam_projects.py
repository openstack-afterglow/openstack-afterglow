"""Domain-manager edits of a native project's name and description.

Only the label fields change; enabled state, domain and parent stay with the
system-administrator and ownership workflows.
"""

from __future__ import annotations

import asyncio

from fastapi import HTTPException

from app.api.common.errors import public_service_error
from app.services import (
    activity,
    cache,
    domain_iam,
    domain_projects,
    domain_scope,
    identity_roles,
    keystone,
    project_ownership_journal,
)
from app.services.cache import keys
from app.services.project_service import _provider_call

_field = identity_roles._field


def _native_error(exc: Exception) -> HTTPException:
    if isinstance(exc, HTTPException):
        status = exc.status_code
    else:
        status = getattr(exc, "http_status", None) or getattr(exc, "status_code", None)
        if status is None:
            status = getattr(getattr(exc, "response", None), "status_code", None)
    if status == 409:
        return HTTPException(409, "project_name_conflict")
    if status in (400, 422):
        return HTTPException(422, "project_update_invalid")
    if status in (401, 403):
        return HTTPException(403, "project_update_denied")
    if status == 404:
        return HTTPException(404, "project_not_found")
    return public_service_error(503, "project_update_unavailable")


def _project(ks, project_id):
    try:
        project = ks.projects.get(project_id)
    except Exception as exc:
        raise _native_error(exc) from exc
    if _field(project, "id") != project_id:
        raise public_service_error(503, "project_identity_unverified")
    return project


def _update(ks, project_id, attrs):
    try:
        return ks.projects.update(project_id, **attrs)
    except Exception as exc:
        raise _native_error(exc) from exc


@identity_roles._complete_mutation
async def update_project(project_id, attrs, token_info):
    await domain_iam.context(token_info)
    conn = await _provider_call(keystone.get_admin_project_connection)
    try:
        # One graph lease with role/ownership mutations: the Default authority
        # project and an in-flight ownership transfer cannot change underneath.
        async with identity_roles._graph_lock(conn) as lease:
            domain_id = (await domain_iam.context(token_info))["domain_id"]
            ks = await _provider_call(keystone._get_admin_ks_client)
            project = await asyncio.to_thread(_project, ks, project_id)
            domain_scope.assert_domain_resource(domain_id, _field(project, "domain_id"))
            domain_projects.assert_default_immutable(project_id, attrs=attrs, project=project)
            await project_ownership_journal.assert_resolved(project_id)
            succeeded = False
            try:
                updated = await identity_roles._write(lease, _update, ks, project_id, attrs)
                if (
                    _field(updated, "id") != project_id
                    or _field(updated, "domain_id") != domain_id
                    or any(_field(updated, key, "") != value for key, value in attrs.items())
                ):
                    raise public_service_error(503, "project_update_unverified")
                succeeded = True
            finally:
                try:
                    await domain_scope.invalidate_authority()
                    await cache.invalidate(keys.user_key("*", f"domain:{domain_id}:projects"))
                    await cache.invalidate("afterglow:admin:projects:*")
                    await cache.invalidate("afterglow:admin:project_names:*")
                finally:
                    await activity.record(
                        project_id=token_info.get("project_id") or "",
                        user_id=token_info["user_id"],
                        username=token_info.get("username", ""),
                        resource_type="project",
                        action="project.update",
                        status="success" if succeeded else "failed",
                        resource_id=project_id,
                        extra={"fields": sorted(attrs)},
                    )
            return {
                "id": project_id,
                "name": _field(updated, "name", "") or "",
                "description": _field(updated, "description", "") or "",
                "enabled": _field(updated, "enabled") is True,
            }
    finally:
        await asyncio.to_thread(conn.close)
