"""Domain UUIDs are identity; display labels are deliberately nonunique."""

from uuid import uuid4

from fastapi import HTTPException
from openstack.identity.v3.domain import Domain as SdkDomain

from app.services.identity_roles import _field

DISPLAY_ATTRIBUTE = "afterglow_display_name"


def display_name(domain):
    if isinstance(domain, SdkDomain):
        # openstacksdk's Domain deliberately drops unknown extra attributes.
        # Resolve through Keystone's extensible native resource, not a fallback
        # to the opaque internal name after that lossy SDK conversion.
        from app.services import keystone

        did = _field(domain, "id")
        try:
            native = keystone._get_admin_ks_client().domains.get(did)
        except Exception as exc:
            raise HTTPException(503, "Domain display directory is unavailable") from exc
        if not isinstance(did, str) or not did or _field(native, "id") != did:
            raise HTTPException(503, "Domain display identity is unavailable")
        domain = native
    value = _field(domain, DISPLAY_ATTRIBUTE)
    if value is None:
        value = _field(domain, "name")
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(503, "Domain display metadata is unavailable")
    return value


def validate_name(value):
    if not isinstance(value, str) or not value.strip() or value != value.strip() or len(value) > 64:
        raise HTTPException(422, "A personal domain display name of 1–64 characters is required")
    return value


def native_name():
    return "afterglow-" + uuid4().hex
