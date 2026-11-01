"""Database authority for discovered OpenStack policies and scalar runtime settings."""

from __future__ import annotations

from contextlib import suppress
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError, OperationalError

from app.database import get_session_factory, is_db_available, mark_db_unhealthy
from app.models.db import LayerArtifact, LayerBuild, LayerImportJob, LibraryBuild, ResourcePolicy, RuntimeSetting
from app.services.resource_policies import (
    PolicySpec,
    ResourcePolicyValidationError,
    get_spec,
    list_specs,
    validate_existing_selection,
    validate_selection,
)


class ResourcePolicyStorageUnavailable(RuntimeError):
    """Database authority is unavailable; callers must fail closed."""


class RuntimeSettingValidationError(ValueError):
    """Runtime-setting value violates its allowlisted contract."""


@dataclass(frozen=True)
class PolicyRowSnapshot:
    """Detached identity, including timestamps, for post-discovery write fencing."""

    policy_key: str
    resource_kind: str
    resource_id: str | None
    resource_name: str | None
    constraints: dict | None
    updated_by_user_id: str | None
    created_at: datetime
    updated_at: datetime


def _row_snapshot(row: ResourcePolicy | None) -> PolicyRowSnapshot | None:
    if row is None:
        return None
    return PolicyRowSnapshot(
        row.policy_key,
        row.resource_kind,
        row.resource_id,
        row.resource_name,
        deepcopy(row.constraints),
        row.updated_by_user_id,
        row.created_at,
        row.updated_at,
    )


@dataclass(frozen=True)
class RuntimeSettingSpec:
    key: str
    title: str
    help_text: str


RUNTIME_SETTING_SPECS = {
    "notion.sync_enabled": RuntimeSettingSpec(
        "notion.sync_enabled", "Enable Notion synchronization", "Global gate for all external Notion synchronization."
    ),
    "compute.managed_flavors": RuntimeSettingSpec(
        "compute.managed_flavors",
        "Managed standard flavors",
        "Owned by the revision-fenced flavor automation API; generic writes are forbidden.",
    ),
    "compute.flavor_automation_policy": RuntimeSettingSpec(
        "compute.flavor_automation_policy",
        "Flavor automation host and GPU policy",
        "Owned by the revision-fenced flavor automation policy API; generic writes are forbidden.",
    ),
}


def _require_db():
    if not is_db_available() or (factory := get_session_factory()) is None:
        raise ResourcePolicyStorageUnavailable("resource policy storage is unavailable")
    return factory


def _public(row: ResourcePolicy | None, spec: PolicySpec) -> dict[str, Any]:
    resource_id = row.resource_id if row else None
    return {
        "key": spec.key,
        "resource_kind": spec.resource_kind,
        "title": spec.title,
        "group": spec.group,
        "help_text": spec.help_text,
        "execution_scope": spec.execution_scope,
        "dependency": spec.dependency,
        "required_when": spec.required_when,
        "external_only": spec.external_only,
        "shared_only": spec.shared_only,
        "resource_id": resource_id,
        "resource_name": row.resource_name if row else None,
        "constraints": row.constraints if row else None,
        "updated_by_user_id": row.updated_by_user_id if row else None,
        "updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
        "state": "missing" if not resource_id else "configured",
    }


def _runtime_public(row: RuntimeSetting | None, spec: RuntimeSettingSpec) -> dict[str, Any]:
    return {
        "key": spec.key,
        "title": spec.title,
        "help_text": spec.help_text,
        "value": row.value_json if row else None,
        "updated_by_user_id": row.updated_by_user_id if row else None,
        "updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
        "state": "missing" if row is None else "configured",
    }


async def list_policies() -> list[dict[str, Any]]:
    factory = _require_db()
    try:
        async with factory() as session:
            rows = (await session.execute(select(ResourcePolicy))).scalars().all()
            by_key = {row.policy_key: row for row in rows}
            return [_public(by_key.get(spec.key), spec) for spec in list_specs()]
    except OperationalError as exc:
        mark_db_unhealthy()
        raise ResourcePolicyStorageUnavailable("resource policy storage failed") from exc


async def inspect_policies(conn) -> list[dict[str, Any]]:
    """Return policy rows annotated with current exact-ID validation state."""
    policies = await list_policies()
    service_conn = None
    try:
        for policy in policies:
            if policy["state"] == "missing":
                continue
            spec = get_spec(policy["key"])
            try:
                if spec.execution_scope == "service":
                    if service_conn is None:
                        service_conn = await get_service_project_connection()
                    execution_conn = service_conn
                else:
                    execution_conn = conn
                selected = await validate_existing_selection(execution_conn, spec.key, policy["resource_id"])
                policy["resolved_name"] = selected["name"]
            except ResourcePolicyValidationError:
                policy["state"] = "stale"
            except Exception:
                policy["state"] = "unavailable"
        return policies
    finally:
        if service_conn is not None:
            with suppress(Exception):
                from app.services.work_dispatcher import close_connection

                await close_connection(service_conn)


async def get_policy_snapshot(keys: tuple[str, ...]) -> dict[str, dict[str, str] | None]:
    """Return stored IDs and display-name snapshots without OpenStack access."""
    specs = {key: get_spec(key) for key in keys}
    factory = _require_db()
    try:
        async with factory() as session:
            rows = (
                (await session.execute(select(ResourcePolicy).where(ResourcePolicy.policy_key.in_(specs))))
                .scalars()
                .all()
            )
    except OperationalError as exc:
        mark_db_unhealthy()
        raise ResourcePolicyStorageUnavailable("resource policy storage failed") from exc
    by_key = {row.policy_key: row for row in rows}
    return {
        key: (
            {"id": row.resource_id, "name": row.resource_name or row.resource_id}
            if (row := by_key.get(key)) and row.resource_id
            else None
        )
        for key in specs
    }


async def reconciliation_snapshot() -> dict[str, PolicyRowSnapshot | None]:
    """Read all local policies once and release the transaction before native I/O."""
    factory = _require_db()
    try:
        async with factory() as session:
            rows = (await session.execute(select(ResourcePolicy))).scalars().all()
            by_key = {row.policy_key: _row_snapshot(row) for row in rows}
            return {spec.key: by_key.get(spec.key) for spec in list_specs()}
    except OperationalError as exc:
        mark_db_unhealthy()
        raise ResourcePolicyStorageUnavailable("resource policy storage failed") from exc


async def apply_reconciled_policy(
    *,
    key: str,
    expected: PolicyRowSnapshot | None,
    resource_id: str,
    resource_name: str,
    service_project: PolicyRowSnapshot | None = None,
) -> bool:
    """Commit a validated observation only while its full database identity matches.

    Only AZ defaults can gain or change an ID. All other writes refresh display
    names for the same ID; administrator clears are never automatic admissions.
    """
    from app.services.work_dispatcher import checkpoint

    spec = get_spec(key)
    if expected is not None and (expected.policy_key != key or expected.resource_id is None):
        return False
    if spec.resource_kind not in {"compute_availability_zone", "volume_availability_zone"} and (
        expected is None or resource_id != expected.resource_id
    ):
        return False
    if expected is not None and (resource_id, resource_name) == (expected.resource_id, expected.resource_name):
        return False
    factory = _require_db()
    await checkpoint()
    try:
        async with factory() as session, session.begin():
            # All service-policy writers acquire the parent before the child.
            if spec.execution_scope == "service":
                scope = await session.get(ResourcePolicy, "openstack.service_project", with_for_update=True)
                if service_project is None or _row_snapshot(scope) != service_project:
                    return False
            # An absent-row INSERT arbitrates directly on the unique key. Do not
            # take an InnoDB gap lock before competing with an administrator.
            row = await session.get(ResourcePolicy, key, with_for_update=True) if expected is not None else None
            if _row_snapshot(row) != expected:
                return False
            if row is None:
                row = ResourcePolicy(
                    policy_key=key,
                    resource_kind=spec.resource_kind,
                    constraints={
                        "external_only": spec.external_only,
                        "shared_only": spec.shared_only,
                        "execution_scope": spec.execution_scope,
                    },
                )
                session.add(row)
            row.resource_id = resource_id
            row.resource_name = resource_name
            _advance_policy_timestamp(row)
            await session.flush()
        return True
    except IntegrityError:
        # An administrator/importer may win an absent-row insert after discovery.
        if expected is not None:
            raise
        async with factory() as session:
            if await session.get(ResourcePolicy, key) is None:
                raise
        return False
    except OperationalError as exc:
        mark_db_unhealthy()
        raise ResourcePolicyStorageUnavailable("resource policy storage failed") from exc


def _advance_policy_timestamp(row: ResourcePolicy) -> None:
    """Fence every write even when auto-created MySQL DATETIME has no fractions.

    Generic model DateTime and migrated DATETIME(6) installations coexist. A
    whole-second successor is distinguishable on both, unlike a microsecond
    increment that storage can discard. Fast repeated writes may lead wall time.
    """
    now = datetime.now(UTC)
    if row.updated_at is not None:
        previous = row.updated_at.replace(tzinfo=UTC)
        now = max(now, previous + timedelta(seconds=1)).replace(microsecond=0)
    row.updated_at = now


async def _ensure_service_project_mutable(session) -> None:
    """Changing service scope cannot strand durable service-owned resources."""
    sealed_artifact = await session.scalar(select(LayerArtifact.id).where(LayerArtifact.is_sealed.is_(True)).limit(1))
    active_layer_build = await session.scalar(
        select(LayerBuild.id).where(LayerBuild.status.not_in(("complete", "error", "cancelled", "timeout"))).limit(1)
    )
    active_library_build = await session.scalar(
        select(LibraryBuild.id).where(LibraryBuild.status.not_in(("complete", "error", "timeout"))).limit(1)
    )
    active_import = await session.scalar(
        select(LayerImportJob.id)
        .where(LayerImportJob.status.not_in(("complete", "error", "cancelled", "timeout")))
        .limit(1)
    )
    if sealed_artifact or active_layer_build or active_library_build or active_import:
        raise ResourcePolicyValidationError("service project cannot change while durable service resources exist")


async def lock_service_project_admission(session, expected_project_id: str) -> None:
    """Serialize immutable build admission against the service-project setter."""
    row = await session.get(ResourcePolicy, "openstack.service_project", with_for_update=True, populate_existing=True)
    if row is None or row.resource_id != expected_project_id:
        raise ResourcePolicyValidationError("service project changed during build admission")


async def set_policy(*, conn, key: str, resource_id: str | None, updated_by_user_id: str) -> dict[str, Any]:
    spec = get_spec(key)
    service_project = None
    if spec.execution_scope == "service" and resource_id and resource_id.strip():
        service_project = (await reconciliation_snapshot())["openstack.service_project"]
        if service_project is None or not service_project.resource_id:
            raise ResourcePolicyValidationError("required resource policy is not configured: openstack.service_project")
        service_conn = await get_service_project_connection(service_project.resource_id)
        try:
            selected = await validate_selection(service_conn, key, resource_id)
        finally:
            from app.services.work_dispatcher import close_connection

            await close_connection(service_conn)
    else:
        selected = await validate_selection(conn, key, resource_id)
    factory = _require_db()
    try:
        async with factory() as session, session.begin():
            if spec.execution_scope == "service":
                scope = await session.get(ResourcePolicy, "openstack.service_project", with_for_update=True)
                if selected is not None and _row_snapshot(scope) != service_project:
                    raise ResourcePolicyValidationError("service project changed during policy validation")
            row = await session.get(ResourcePolicy, spec.key, with_for_update=True)
            current_id = row.resource_id if row else None
            if spec.key == "openstack.service_project" and current_id != (selected["id"] if selected else None):
                await _ensure_service_project_mutable(session)
                await session.execute(
                    delete(ResourcePolicy).where(
                        ResourcePolicy.policy_key != spec.key,
                        ResourcePolicy.policy_key.in_(
                            [candidate.key for candidate in list_specs() if candidate.execution_scope == "service"]
                        ),
                    )
                )
            if row is None:
                row = ResourcePolicy(policy_key=spec.key, resource_kind=spec.resource_kind)
                session.add(row)
            row.resource_id = selected["id"] if selected else None
            row.resource_name = selected["name"] if selected else None
            row.constraints = {
                "external_only": spec.external_only,
                "shared_only": spec.shared_only,
                "execution_scope": spec.execution_scope,
            }
            row.updated_by_user_id = updated_by_user_id
            # A repeated administrator write is still a new decision (ABA fence).
            _advance_policy_timestamp(row)
            await session.flush()
            result = _public(row, spec)
    except OperationalError as exc:
        mark_db_unhealthy()
        raise ResourcePolicyStorageUnavailable("resource policy storage failed") from exc
    return result


async def get_service_project_id() -> str:
    snapshot = await get_policy_snapshot(("openstack.service_project",))
    selected = snapshot["openstack.service_project"]
    if selected is None:
        raise ResourcePolicyValidationError("required resource policy is not configured: openstack.service_project")
    return selected["id"]


async def get_service_project_connection(project_id: str | None = None):
    """Create the service-project connection; admission passes its exact snapshot ID."""
    from app.services.keystone import get_admin_connection_for_project
    from app.services.work_dispatcher import open_connection

    return await open_connection(get_admin_connection_for_project, project_id or await get_service_project_id())


async def resolve_policy_snapshot(*, conn, keys: tuple[str, ...], service_conn=None) -> dict[str, dict[str, str]]:
    """Validate and freeze effective IDs/names in each policy's real execution scope."""
    specs: dict[str, PolicySpec] = {key: get_spec(key) for key in keys}
    stored = await get_policy_snapshot(tuple(specs))
    missing = [key for key, selected in stored.items() if selected is None]
    if missing:
        raise ResourcePolicyValidationError(f"required resource policies are not configured: {', '.join(missing)}")

    owns_service_connection = service_conn is None
    try:
        if any(spec.execution_scope == "service" for spec in specs.values()) and service_conn is None:
            service_conn = await get_service_project_connection()
        resolved: dict[str, dict[str, str]] = {}
        for key, spec in specs.items():
            execution_conn = service_conn if spec.execution_scope == "service" else conn
            selected = await validate_existing_selection(execution_conn, key, stored[key]["id"])
            resolved[key] = {"id": selected["id"], "name": selected["name"]}
        return resolved
    finally:
        if owns_service_connection and service_conn is not None:
            with suppress(Exception):
                from app.services.work_dispatcher import close_connection

                await close_connection(service_conn)


async def resolve_policies(*, conn, keys: tuple[str, ...]) -> dict[str, str]:
    """Compatibility helper returning only immutable validated IDs."""
    snapshot = await resolve_policy_snapshot(conn=conn, keys=keys)
    return {key: value["id"] for key, value in snapshot.items()}


def _runtime_spec(key: str) -> RuntimeSettingSpec:
    try:
        return RUNTIME_SETTING_SPECS[key]
    except KeyError as exc:
        raise RuntimeSettingValidationError("unknown runtime setting") from exc


def _validate_runtime_value(key: str, value: object) -> object:
    if key in {"compute.managed_flavors", "compute.flavor_automation_policy"}:
        raise RuntimeSettingValidationError("managed flavors require the dedicated flavor automation API")
    if key == "notion.sync_enabled":
        if type(value) is not bool:
            raise RuntimeSettingValidationError("notion.sync_enabled must be a boolean")
        return value
    raise RuntimeSettingValidationError("unknown runtime setting")


async def list_runtime_settings() -> list[dict[str, Any]]:
    factory = _require_db()
    try:
        async with factory() as session:
            rows = (await session.execute(select(RuntimeSetting))).scalars().all()
    except OperationalError as exc:
        mark_db_unhealthy()
        raise ResourcePolicyStorageUnavailable("runtime setting storage failed") from exc
    by_key = {row.setting_key: row for row in rows}
    # Automation has a dedicated status API; never expose its private create
    # claims or offer the scalar-setting editor for its revision-fenced state.
    return [
        _runtime_public(by_key.get(key), spec)
        for key, spec in RUNTIME_SETTING_SPECS.items()
        if key not in {"compute.managed_flavors", "compute.flavor_automation_policy"}
    ]


async def get_runtime_setting(key: str) -> object | None:
    _runtime_spec(key)
    factory = _require_db()
    try:
        async with factory() as session:
            row = await session.get(RuntimeSetting, key)
    except OperationalError as exc:
        mark_db_unhealthy()
        raise ResourcePolicyStorageUnavailable("runtime setting storage failed") from exc
    return row.value_json if row is not None else None


async def get_required_runtime_setting(key: str) -> object:
    value = await get_runtime_setting(key)
    if value is None:
        raise RuntimeSettingValidationError(f"required runtime setting is not configured: {key}")
    return _validate_runtime_value(key, value)


async def set_runtime_setting(*, key: str, value: object, updated_by_user_id: str) -> dict[str, Any]:
    spec = _runtime_spec(key)
    normalized = _validate_runtime_value(key, value)
    factory = _require_db()
    try:
        async with factory() as session, session.begin():
            row = await session.get(RuntimeSetting, key, with_for_update=True)
            if row is None:
                row = RuntimeSetting(setting_key=key, value_json=normalized)
                session.add(row)
            else:
                row.value_json = normalized
            row.updated_by_user_id = updated_by_user_id
            await session.flush()
            return _runtime_public(row, spec)
    except OperationalError as exc:
        mark_db_unhealthy()
        raise ResourcePolicyStorageUnavailable("runtime setting storage failed") from exc
