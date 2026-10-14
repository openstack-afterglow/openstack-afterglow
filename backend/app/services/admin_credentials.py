"""Caller-connection-only Keystone credential operations.

ApplicationCredential.allow_commit in SDK 3.3 is not an API update contract:
Keystone exposes only list/get/create/delete. Creation is owner/project scoped.
"""

from datetime import UTC, datetime

from app.models.admin_credentials import ApplicationCredentialCreate


class ScopeDenied(Exception):
    pass


def value(resource, key, default=None):
    if isinstance(resource, dict):
        return resource.get(key, default)
    return getattr(resource, key, default)


def application_metadata(resource, user_id):
    # Allowlist: even a provider unexpectedly returning a secret cannot leak it.
    return {
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


def user_metadata(resource):
    return {key: value(resource, key) for key in ("id", "user_id", "project_id", "type")}


def creation_context(conn, token_info):
    # The logical X-Project-Id may differ from a system administrator's home
    # token. Never grant foreign-project roles using that home connection.
    authenticated = token_info.get("connection_project_id") or token_info.get("project_id")
    if not authenticated or authenticated != token_info.get("project_id"):
        raise ScopeDenied
    access = conn.session.auth.get_access(conn.session)
    if access.project_id != authenticated or access.user_id != token_info.get("user_id"):
        raise ScopeDenied
    role_ids = access.role_ids or []
    role_names = access.role_names or []
    if not role_ids:
        raise ScopeDenied
    return {
        "user_id": access.user_id,
        "project_id": authenticated,
        "roles": [
            {"id": role_id, "name": role_names[index] if index < len(role_names) else ""}
            for index, role_id in enumerate(role_ids)
        ],
    }


def create_application(conn, token_info, body: ApplicationCredentialCreate):
    context = creation_context(conn, token_info)
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
    result = application_metadata(resource, context["user_id"])
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
            conn.identity.delete_application_credential(context["user_id"], result["id"], ignore_missing=False)
        raise ScopeDenied
    result["secret"] = value(resource, "secret")
    return result
