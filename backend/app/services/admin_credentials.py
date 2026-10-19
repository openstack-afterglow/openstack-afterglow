"""Caller-connection-only Keystone credential operations.

ApplicationCredential.allow_commit in SDK 3.3 is not an API update contract:
Keystone exposes only list/get/create/delete. Creation is owner/project scoped.
"""

from datetime import UTC, datetime

from fastapi import HTTPException
from keystoneauth1 import exceptions as auth_exc
from openstack import exceptions as sdk_exc

from app.models.admin_credentials import ApplicationCredentialCreate


class ScopeDenied(Exception):
    pass


class RollbackFailed(Exception):
    """A native creation committed but its compensating revocation failed."""


def revoke_created(call):
    try:
        call()
    except (sdk_exc.ResourceNotFound, auth_exc.NotFound):
        # Another native actor already removed it: the revocation goal is met.
        return
    except Exception as exc:
        raise RollbackFailed from exc


def value(resource, key, default=None):
    if isinstance(resource, dict):
        return resource.get(key, default)
    return getattr(resource, key, default)


def application_metadata(resource, user_id, domain_id):
    # Allowlist: even a provider unexpectedly returning a secret cannot leak it.
    return {
        "domain_id": domain_id,
        "id": value(resource, "id"),
        "user_id": user_id,
        "name": value(resource, "name", "") or "",
        "description": value(resource, "description", "") or "",
        "project_id": value(resource, "project_id"),
        "expires_at": value(resource, "expires_at"),
        "unrestricted": bool(value(resource, "unrestricted", False)),
        "roles": [
            {"id": value(role, "id"), "name": value(role, "name", "") or ""}
            for role in (value(resource, "roles", []) or [])
        ],
    }


def user_metadata(resource, domain_id):
    return {"domain_id": domain_id, **{key: value(resource, key) for key in ("id", "user_id", "project_id", "type")}}


def require_domain(conn, domain_id):
    # Exact ID lookup only: names and configured defaults are not boundaries.
    domain = conn.identity.get_domain(domain_id)
    if not domain_id or value(domain, "id") != domain_id:
        raise ScopeDenied


def owner_in_domain(conn, domain_id, user_id, project_id=None, *, project_required=False):
    if not user_id or (project_required and not project_id):
        return False
    for kind, resource_id in (("user", user_id), ("project", project_id)):
        if resource_id is None:
            continue
        if not resource_id:
            return False
        getter = conn.identity.get_user if kind == "user" else conn.identity.get_project
        resource = getter(resource_id)
        matches = value(resource, "id") == resource_id and value(resource, "domain_id") == domain_id
        if not matches:
            return False
    return True


def require_owner(conn, domain_id, user_id, project_id=None, *, project_required=False):
    if not owner_in_domain(conn, domain_id, user_id, project_id, project_required=project_required):
        raise ScopeDenied


def application_in_domain(conn, domain_id, resource, user_id):
    return (
        bool(value(resource, "id"))
        and value(resource, "user_id", user_id) == user_id
        and owner_in_domain(conn, domain_id, user_id, value(resource, "project_id"), project_required=True)
    )


def _domain_ids(conn, domain_id, kind):
    """Native directory filters must prove ownership, never silently degrade."""
    rows = conn.identity.users(domain_id=domain_id) if kind == "user" else conn.identity.projects(domain_id=domain_id)
    ids = set()
    for row in rows:
        resource_id = value(row, "id")
        if not resource_id or value(row, "domain_id") != domain_id:
            raise ScopeDenied
        ids.add(resource_id)
    return ids


def list_applications(conn, domain_id, user_id):
    require_domain(conn, domain_id)
    require_owner(conn, domain_id, user_id)
    projects = _domain_ids(conn, domain_id, "project")
    return {
        "items": [
            application_metadata(resource, user_id, domain_id)
            for resource in conn.identity.application_credentials(user_id)
            if value(resource, "id")
            and value(resource, "user_id", user_id) == user_id
            and value(resource, "project_id") in projects
        ]
    }


def get_application(conn, domain_id, user_id, credential_id):
    require_domain(conn, domain_id)
    require_owner(conn, domain_id, user_id)
    resource = conn.identity.get_application_credential(user_id, credential_id)
    if value(resource, "id") != credential_id or not application_in_domain(conn, domain_id, resource, user_id):
        raise ScopeDenied
    return resource


def delete_application(conn, domain_id, user_id, credential_id):
    get_application(conn, domain_id, user_id, credential_id)
    conn.identity.delete_application_credential(user_id, credential_id, ignore_missing=False)


def list_user_credentials(conn, domain_id, user_id=None):
    require_domain(conn, domain_id)
    if user_id:
        require_owner(conn, domain_id, user_id)
    users, projects = _domain_ids(conn, domain_id, "user"), _domain_ids(conn, domain_id, "project")
    query = {"user_id": user_id} if user_id else {}
    return {
        "items": [
            user_metadata(resource, domain_id)
            for resource in conn.identity.credentials(**query)
            if value(resource, "id")
            and (not user_id or value(resource, "user_id") == user_id)
            and value(resource, "user_id") in users
            and (value(resource, "project_id") is None or value(resource, "project_id") in projects)
        ]
    }


def get_user_credential(conn, domain_id, credential_id):
    require_domain(conn, domain_id)
    resource = conn.identity.get_credential(credential_id)
    if value(resource, "id") != credential_id:
        raise ScopeDenied
    require_owner(conn, domain_id, value(resource, "user_id"), value(resource, "project_id"))
    return resource


def create_user_credential(conn, domain_id, body):
    require_domain(conn, domain_id)
    require_owner(conn, domain_id, body.user_id, body.project_id)
    resource = conn.identity.create_credential(**body.model_dump(exclude_none=True))
    # Compare with the already-proven owner IDs, without fallible post-write
    # directory I/O that could disguise a committed native credential as failure.
    if (
        not value(resource, "id")
        or value(resource, "user_id") != body.user_id
        or value(resource, "project_id") != body.project_id
    ):
        if value(resource, "id"):
            revoke_created(lambda: conn.identity.delete_credential(value(resource, "id"), ignore_missing=False))
        raise ScopeDenied
    return user_metadata(resource, domain_id)


def update_user_credential(conn, domain_id, credential_id, body):
    resource = get_user_credential(conn, domain_id, credential_id)
    attrs = body.model_dump(exclude_unset=True, exclude_none=True)
    if not attrs:
        raise HTTPException(422, "credential_invalid_input")
    user_id = attrs.get("user_id", value(resource, "user_id"))
    project_id = attrs.get("project_id", value(resource, "project_id"))
    require_owner(conn, domain_id, user_id, project_id)
    updated = conn.identity.update_credential(credential_id, **attrs)
    if (
        value(updated, "id") != credential_id
        or value(updated, "user_id") != user_id
        or value(updated, "project_id") != project_id
    ):
        raise ScopeDenied
    return user_metadata(updated, domain_id)


def delete_user_credential(conn, domain_id, credential_id):
    get_user_credential(conn, domain_id, credential_id)
    conn.identity.delete_credential(credential_id, ignore_missing=False)


def creation_context(conn, token_info, domain_id):
    # The logical X-Project-Id may differ from a system administrator's home
    # token. Never grant foreign-project roles using that home connection.
    authenticated = token_info.get("connection_project_id") or token_info.get("project_id")
    if not authenticated or authenticated != token_info.get("project_id"):
        raise ScopeDenied
    access = conn.session.auth.get_access(conn.session)
    if access.project_id != authenticated or access.user_id != token_info.get("user_id"):
        raise ScopeDenied
    require_domain(conn, domain_id)
    require_owner(conn, domain_id, access.user_id, authenticated, project_required=True)
    role_ids = access.role_ids or []
    role_names = access.role_names or []
    if not role_ids:
        raise ScopeDenied
    return {
        "domain_id": domain_id,
        "user_id": access.user_id,
        "project_id": authenticated,
        "roles": [
            {"id": role_id, "name": role_names[index] if index < len(role_names) else ""}
            for index, role_id in enumerate(role_ids)
        ],
    }


def create_application(conn, token_info, body: ApplicationCredentialCreate, domain_id):
    context = creation_context(conn, token_info, domain_id)
    if not set(body.role_ids) <= {role["id"] for role in context["roles"]}:
        raise ScopeDenied
    attrs = {
        "description": body.description,
        "roles": [{"id": role_id} for role_id in dict.fromkeys(body.role_ids)],
        "unrestricted": False,
    }
    if body.expires_at is not None:
        attrs["expires_at"] = body.expires_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
    # Do not send project_id: Keystone derives it from this authenticated token.
    resource = conn.identity.create_application_credential(context["user_id"], body.name, **attrs)
    result = application_metadata(resource, context["user_id"], domain_id)
    returned_roles = {role["id"] for role in result["roles"]}
    expiry_within_scope = True
    if body.expires_at is not None:
        try:
            expiry = result["expires_at"]
            returned_expiry = expiry if isinstance(expiry, datetime) else datetime.fromisoformat(expiry)
            # Keystone's native API also returns UTC timestamps without a suffix.
            if returned_expiry.tzinfo is None:
                returned_expiry = returned_expiry.replace(tzinfo=UTC)
            expiry_within_scope = returned_expiry <= body.expires_at
        except (TypeError, ValueError):
            expiry_within_scope = False
    if (
        result["project_id"] != context["project_id"]
        or value(resource, "user_id", context["user_id"]) != context["user_id"]
        or returned_roles != set(body.role_ids)
        or not expiry_within_scope
        or value(resource, "unrestricted") is not False
        or not result["id"]
        or not isinstance(value(resource, "secret"), str)
        or not value(resource, "secret")
    ):
        # Never publish an over-scoped or incomplete credential. Revoke only
        # the durable native identifier just returned, never a guessed name.
        if result["id"]:
            revoke_created(
                lambda: conn.identity.delete_application_credential(
                    context["user_id"], result["id"], ignore_missing=False
                )
            )
        raise ScopeDenied
    result["secret"] = value(resource, "secret")
    return result
