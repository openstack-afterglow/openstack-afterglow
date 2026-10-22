"""Native project identity stays immutable; only Personal owners edit its label."""

import json
import unicodedata
from urllib.parse import quote

from fastapi import HTTPException
from openstack.identity.v3.project import Project as SdkProject

from app.services import account_spaces, domain_projects, identity_roles, keystone, project_service
from app.services.identity_roles import _field
from app.services.native_operation import NativeOperation

DISPLAY_ATTRIBUTE = "afterglow_display_name"


def validate_name(value):
    if not isinstance(value, str) or any(unicodedata.category(c) in {"Cc", "Cf"} for c in value):
        raise HTTPException(422, "project_display_name_invalid")
    value = value.strip()
    if not 1 <= len(value) <= 64:
        raise HTTPException(422, "project_display_name_invalid")
    return value


def display_name(project, *, operation=None):
    """Project extra fields must not be lost through openstacksdk's schema."""
    pid = _field(project, "id")
    if not isinstance(pid, str) or not pid:
        raise HTTPException(503, "project_display_identity_unavailable")
    if isinstance(project, SdkProject):
        if operation is None:
            with NativeOperation() as directory:
                return display_name(project, operation=directory)
        native = operation.get("projects", pid)
        if _field(native, "domain_id") != _field(project, "domain_id") or _field(native, "name") != _field(
            project, "name"
        ):
            raise HTTPException(503, "project_display_identity_unavailable")
        project = native
    native_name = _field(project, "name")
    if (
        not isinstance(native_name, str)
        or not native_name.strip()
        or any(unicodedata.category(c) in {"Cc", "Cf"} for c in native_name)
    ):
        raise HTTPException(503, "project_display_identity_unavailable")
    label = _field(project, DISPLAY_ATTRIBUTE)
    if label is None:
        return native_name
    try:
        checked = validate_name(label)
    except HTTPException as exc:
        raise HTTPException(503, "project_display_metadata_unavailable") from exc
    if checked != label:
        raise HTTPException(503, "project_display_metadata_unavailable")
    return checked


def _snapshot(project_id, actor, operation):
    """Fresh native membership, identity/home and owner provenance, never JWT roles."""
    uid, did, home = (actor.get(key) for key in ("user_id", "domain_id", "identity_domain_id"))
    if actor.get("project_id") != project_id or not all(
        isinstance(value, str) and value for value in (project_id, uid, did, home)
    ):
        raise HTTPException(403, "project_display_current_membership_required")
    user = operation.get("users", uid)
    if _field(user, "domain_id") != home:
        raise HTTPException(403, "project_display_identity_mismatch")
    if _field(user, "enabled") is not True or _field(operation.get("domains", home), "enabled") is not True:
        raise HTTPException(403, "project_display_identity_disabled")
    project = operation.get("projects", project_id)
    if _field(project, "domain_id") != did:
        raise HTTPException(403, "project_display_domain_mismatch")
    domain_projects.assert_project_membership(uid, project_id, operation=operation)
    can_edit = False
    domain = operation.get("domains", did)
    if account_spaces.domain_kind(domain) == "personal":
        shared = account_spaces.shared_domain("personal", operation=operation)
        if _field(shared, "id") != did or _field(project, "afterglow_personal_user_id") != uid:
            raise HTTPException(403, "personal_project_owner_required")
        if type(_field(project, "afterglow_personal_primary")) is not bool:
            raise HTTPException(503, "personal_project_provenance_unavailable")
        catalog = operation.catalog()
        sources = domain_projects._sources(operation.ks, project, catalog)
        if any(source["role_id"] == account_spaces._personal_member_role(catalog)["id"] for source in sources):
            account_spaces._verify_personal_member(operation.ks, catalog, project, uid)
        else:
            ownership = project_service._ownership_state_sync(operation.ks, catalog, project_id)
            if ownership["status"] != "unique" or ownership["owner_user_id"] != uid:
                raise HTTPException(403, "personal_project_owner_required")
        can_edit = True
    return project, {
        "project_id": project_id,
        "display_name": display_name(project),
        "native_name": _field(project, "name"),
        "can_edit": can_edit,
    }


async def get_display_name(project_id, actor):
    async with NativeOperation() as operation:
        _, result = await identity_roles._to_completion(
            project_service._provider_call(_snapshot, project_id, actor, operation)
        )
        return result


def _native_project(writer, project_id):
    response = writer.identity.get(f"/projects/{quote(project_id, safe='')}", redirect=False)
    response.raise_for_status()
    if not 200 <= response.status_code < 300:
        raise HTTPException(503, "project_display_native_response")
    project = response.json().get("project")
    if not isinstance(project, dict) or project.get("id") != project_id:
        raise HTTPException(503, "project_display_identity_unavailable")
    display_name(project)
    return project


def _same_identity(project, native):
    fields = (
        "id",
        "name",
        "domain_id",
        "enabled",
        "afterglow_personal_user_id",
        "afterglow_personal_primary",
        "afterglow_enrollment_id",
    )
    if any(_field(project, key) != _field(native, key) for key in fields):
        raise HTTPException(503, "project_display_provenance_changed")


def _patch(writer, project_id, label):
    # SDK Project.update silently drops unknown extras. Raw PATCH sends exactly
    # one application-authorized attribute, never a project name or grants.
    response = writer.identity.patch(
        f"/projects/{quote(project_id, safe='')}",
        json={"project": {DISPLAY_ATTRIBUTE: label}},
        redirect=False,
    )
    response.raise_for_status()
    if not 200 <= response.status_code < 300:
        raise HTTPException(503, "project_display_native_response")
    project = response.json().get("project")
    if not isinstance(project, dict) or project.get("id") != project_id or project.get(DISPLAY_ATTRIBUTE) != label:
        raise HTTPException(503, "project_display_write_unconfirmed")


@identity_roles._complete_mutation
async def save_display_name(project_id, actor, label):
    label = validate_name(label)
    # Do not even acquire the delegated writer until exact caller membership
    # and native Personal owner provenance have been established.
    initial = await get_display_name(project_id, actor)
    if not initial["can_edit"]:
        raise HTTPException(403, "personal_project_owner_required")
    writer = await project_service._provider_call(keystone.get_admin_project_connection)
    attempted = False
    try:
        async with identity_roles._graph_lock(writer) as lease, NativeOperation() as operation:
            project, current = await project_service._provider_call(_snapshot, project_id, actor, operation)
            if not current["can_edit"]:
                raise HTTPException(403, "personal_project_owner_required")
            before = await project_service._provider_call(_native_project, writer, project_id)
            _same_identity(project, before)
            if len(json.dumps({**before, DISPLAY_ATTRIBUTE: label}, ensure_ascii=True).encode("ascii")) > 60_000:
                raise HTTPException(422, "project_display_metadata_size")
            attempted = True
            await identity_roles._write(lease, _patch, writer, project_id, label)
            saved = await project_service._provider_call(_native_project, writer, project_id)

            def preserved(row):
                return {key: value for key, value in row.items() if key not in {DISPLAY_ATTRIBUTE, "links"}}

            if saved.get(DISPLAY_ATTRIBUTE) != label or preserved(saved) != preserved(before):
                raise HTTPException(503, "project_display_write_unconfirmed")
            operation.invalidate()
            checked, result = await project_service._provider_call(_snapshot, project_id, actor, operation)
            _same_identity(before, checked)
            if not result["can_edit"] or result["display_name"] != label:
                raise HTTPException(503, "project_display_write_unconfirmed")
            await lease.assert_owned()
            return result
    finally:
        try:
            if attempted:
                await project_service.invalidate_project_lists(actor["user_id"], actor["domain_id"])
        finally:
            await project_service._provider_call(writer.close)
