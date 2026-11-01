"""Import legacy deployment selectors into runtime infrastructure tables.

Run from ``backend`` after migration 062:

    uv run python scripts/import_runtime_infrastructure_settings.py --config ../afterglow.conf --dry-run
    uv run python scripts/import_runtime_infrastructure_settings.py --config ../afterglow.conf --apply

The importer is intentionally the only compatibility bridge. It never logs raw
configuration values, never overwrites an existing selection, validates every
candidate before opening its write transaction, and performs all writes atomically.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# Running a script by path puts ``backend/scripts`` on sys.path, not ``backend``.
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


_POLICY_SOURCES: dict[str, tuple[str, str, str]] = {
    "openstack.service_project": ("openstack", "service_project_id", "OS_SERVICE_PROJECT_ID"),
    "nova.default_network": ("nova", "default_network_id", "DEFAULT_NETWORK_ID"),
    "nova.default_external_network": ("nova", "default_network_external_id", "DEFAULT_NETWORK_EXTERNAL_ID"),
    "nova.default_compute_availability_zone": ("nova", "default_availability_zone", "DEFAULT_AVAILABILITY_ZONE"),
    "cinder.default_volume_availability_zone": ("nova", "default_availability_zone", "DEFAULT_AVAILABILITY_ZONE"),
    "builder.flavor": ("builder", "flavor_id", "BUILDER_FLAVOR_ID"),
    "builder.network": ("builder", "network_id", "BUILDER_NETWORK_ID"),
    "builder.floating_network": ("builder", "floating_network_id", "BUILDER_FLOATING_NETWORK_ID"),
}

_LEGACY_NAME_SELECTOR_KEYS = {
    "manila.cephfs_share_type",
    "manila.nfs_share_type",
}


def _legacy_value(config: Mapping[str, Any], section: str, key: str, env_key: str) -> str | None:
    value = os.environ.get(env_key)
    if value is None:
        value = (config.get(section) or {}).get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _legacy_bool(config: Mapping[str, Any], section: str, key: str, env_key: str) -> bool | None:
    raw = os.environ.get(env_key)
    if raw is None:
        raw = (config.get(section) or {}).get(key)
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str) and raw.strip().lower() in {"true", "1", "yes", "on"}:
        return True
    if isinstance(raw, str) and raw.strip().lower() in {"false", "0", "no", "off"}:
        return False
    return None


def _parse_legacy_base_images(values: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        release, delimiter, image_id = value.partition("=")
        if not delimiter or not release.strip() or not image_id.strip():
            raise ValueError("--legacy-base-image must be RELEASE=IMAGE_ID")
        if release.strip() in result:
            raise ValueError(f"duplicate legacy base-image release: {release.strip()}")
        result[release.strip()] = image_id.strip()
    return result


def _database_url(config: Mapping[str, Any]) -> str:
    return os.environ.get("DATABASE_URL") or str((config.get("database") or {}).get("url") or "")


async def _existing_service_project(database_url: str) -> dict[str, str] | None:
    """Read the authoritative service-project selection before validating dependents."""
    from app.models.db import ResourcePolicy

    engine = create_async_engine(database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            row = await session.get(ResourcePolicy, "openstack.service_project")
            if row is None or not row.resource_id:
                return None
            return {"id": row.resource_id, "name": row.resource_name or row.resource_id}
    finally:
        await engine.dispose()


async def _resolve_legacy_selection(conn: Any, policy_key: str, value: str) -> dict[str, str]:
    """Validate a legacy selector without exposing its potentially sensitive value."""
    from app.services.resource_policies import ResourcePolicyValidationError, validate_legacy_selection

    try:
        resolved = await validate_legacy_selection(
            conn, policy_key, value, allow_exact_name=policy_key in _LEGACY_NAME_SELECTOR_KEYS
        )
    except ResourcePolicyValidationError as exc:
        raise ValueError(f"legacy selection is unavailable or invalid for {policy_key}") from exc
    if resolved is None:
        raise ValueError(f"legacy selection is unavailable or invalid for {policy_key}")
    return {"id": resolved["id"], "name": resolved["name"]}


async def _collect(
    config: Mapping[str, Any],
    legacy_base_images: dict[str, str],
    persisted_service_project: dict[str, str] | None,
) -> tuple[dict[str, dict[str, str]], dict[str, object], dict[str, dict[str, object]]]:
    from app.services.keystone import get_admin_connection_for_project, get_admin_project_connection
    from app.services.resource_policies import get_spec

    admin_conn = await asyncio.to_thread(get_admin_project_connection)
    service_conn = None
    try:
        selected: dict[str, dict[str, str]] = {}
        service_source = _POLICY_SOURCES["openstack.service_project"]
        legacy_service_value = _legacy_value(config, *service_source)
        service_value = (persisted_service_project or {}).get("id") or legacy_service_value
        if service_value:
            selected["openstack.service_project"] = await _resolve_legacy_selection(
                admin_conn, "openstack.service_project", service_value
            )
            service_conn = await asyncio.to_thread(
                get_admin_connection_for_project, selected["openstack.service_project"]["id"]
            )

        for policy_key, source in _POLICY_SOURCES.items():
            if policy_key == "openstack.service_project":
                continue
            value = _legacy_value(config, *source)
            if value is None:
                continue
            spec = get_spec(policy_key)
            if spec.execution_scope == "service":
                if service_conn is None:
                    raise ValueError(f"{policy_key} requires legacy openstack.service_project_id")
                conn = service_conn
            else:
                conn = admin_conn
            selected[policy_key] = await _resolve_legacy_selection(conn, policy_key, value)

        base_images: dict[str, dict[str, object]] = {}
        for release, image_id in legacy_base_images.items():
            image = await asyncio.to_thread(admin_conn.image.get_image, image_id)
            if image is None:
                raise ValueError(f"legacy base image is unavailable: {release}")
            base_images[release] = {
                "base_image_id": str(image.id),
                "base_image_name": str(getattr(image, "name", image.id)),
                "base_image_checksum": getattr(image, "checksum", None),
                "base_image_os_hash_algo": getattr(image, "os_hash_algo", None),
                "base_image_os_hash_value": getattr(image, "os_hash_value", None),
                "base_image_min_disk": getattr(image, "min_disk", None),
                "base_image_visibility": getattr(image, "visibility", None),
                "base_image_owner": getattr(image, "owner_id", None),
                "ubuntu_base": release,
            }

        runtime = {
            "notion.sync_enabled": _legacy_bool(config, "notion", "enabled", "NOTION_ENABLED"),
        }
        return selected, runtime, base_images
    finally:
        if service_conn is not None:
            await asyncio.to_thread(service_conn.close)
        await asyncio.to_thread(admin_conn.close)


async def _inflight_snapshot_blockers(session: Any) -> list[str]:
    """Report non-terminal Afterglow rows without immutable resource snapshots."""
    from app.models.db import LayerBuild, LayerConsume, LayerImportJob, LibraryBuild

    blockers: list[str] = []

    model_states = (
        (LibraryBuild, {"complete", "error", "timeout", "cancelled"}, "library_build"),
        (LayerBuild, {"complete", "error", "failure", "timeout", "cancelled"}, "layer_build"),
        (LayerImportJob, {"complete", "error", "cancelled"}, "layer_import_job"),
        (LayerConsume, {"active", "error", "deleted"}, "layer_consume"),
    )
    for model, terminal_states, label in model_states:
        rows = (
            (
                await session.execute(
                    select(model).where(model.status.notin_(terminal_states), model.resource_snapshot.is_(None))
                )
            )
            .scalars()
            .all()
        )
        blockers.extend(f"{label}:{row.id}" for row in rows)
    return blockers


async def _database_snapshot_blockers(database_url: str) -> list[str]:
    engine = create_async_engine(database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            return await _inflight_snapshot_blockers(session)
    finally:
        await engine.dispose()


async def _insert_policy_if_absent(session: Any, key: str, resource: dict[str, str]) -> bool:
    """Keep a concurrent administrator/reconciler winner without aborting seeding."""
    from app.models.db import ResourcePolicy
    from app.services.resource_policies import get_spec

    spec = get_spec(key)
    try:
        async with session.begin_nested():
            session.add(
                ResourcePolicy(
                    policy_key=key,
                    resource_kind=spec.resource_kind,
                    resource_id=resource["id"],
                    resource_name=resource["name"],
                )
            )
            await session.flush()
        return True
    except IntegrityError as exc:
        # Only duplicate-key errors can represent an absent-snapshot race.
        # Other integrity failures must still roll back the entire import.
        original = exc.orig
        code = getattr(original, "sqlite_errorcode", None)
        if code is None and original.args:
            code = original.args[0]
        if code not in (1062, 1555, 2067) and getattr(original, "sqlstate", None) != "23505":
            raise
        # In MariaDB REPEATABLE READ another plain SELECT can retain the old
        # absent snapshot. A locking read observes the committed unique-key winner.
        winner = await session.scalar(
            select(ResourcePolicy.policy_key).where(ResourcePolicy.policy_key == key).with_for_update()
        )
        if winner is None:
            raise
        return False


async def _apply(
    database_url: str,
    selected: dict[str, dict[str, str]],
    runtime: dict[str, object],
    base_images: dict[str, dict[str, object]],
) -> tuple[int, int, int]:
    from app.models.db import LayerArtifact, ResourcePolicy, RuntimeSetting

    engine = create_async_engine(database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    policy_count = 0
    runtime_count = 0
    artifact_count = 0
    try:
        async with factory() as session, session.begin():
            existing_policy_keys = set((await session.execute(select(ResourcePolicy.policy_key))).scalars())
            existing_runtime_keys = set((await session.execute(select(RuntimeSetting.setting_key))).scalars())
            for key, resource in selected.items():
                if key in existing_policy_keys:
                    continue
                policy_count += await _insert_policy_if_absent(session, key, resource)
            blockers = await _inflight_snapshot_blockers(session)
            if blockers:
                raise ValueError(f"unresolved in-flight resource snapshots: {', '.join(blockers)}")

            for key, value in runtime.items():
                if value is None or key in existing_runtime_keys:
                    continue
                session.add(RuntimeSetting(setting_key=key, value_json=value))
                runtime_count += 1

            if base_images:
                artifacts = (
                    (await session.execute(select(LayerArtifact).where(LayerArtifact.base_image_id.is_(None))))
                    .scalars()
                    .all()
                )
                for artifact in artifacts:
                    snapshot = base_images.get(str(artifact.ubuntu_base))
                    if snapshot is None:
                        continue
                    for field, value in snapshot.items():
                        if field != "ubuntu_base":
                            setattr(artifact, field, value)
                    artifact_count += 1
        return policy_count, runtime_count, artifact_count
    finally:
        await engine.dispose()


async def _main(args: argparse.Namespace) -> int:
    if args.apply == args.dry_run:
        raise ValueError("choose exactly one of --dry-run or --apply")
    config_path = Path(args.config)
    if config_path.name == "config.toml":
        raise ValueError("config.toml is unsupported; migrate the configuration to afterglow.conf")
    with config_path.open("rb") as fh:
        config = tomllib.load(fh)
    database_url = _database_url(config)
    if not database_url:
        raise ValueError("DATABASE_URL or [database] url is required")
    persisted_service_project = await _existing_service_project(database_url)
    selected, runtime, base_images = await _collect(
        config, _parse_legacy_base_images(args.legacy_base_image), persisted_service_project
    )
    blockers = await _database_snapshot_blockers(database_url)
    if blockers:
        print(f"unresolved in-flight resource snapshots: {', '.join(blockers)}", file=sys.stderr)
        return 2
    if args.dry_run:
        print(
            "validated "
            f"policies={len(selected)} "
            f"runtime_settings={sum(value is not None for value in runtime.values())} "
            f"legacy_base_images={len(base_images)}; no writes"
        )
        return 0
    policies, runtime_settings, artifacts = await _apply(database_url, selected, runtime, base_images)
    print(
        f"seeded policies={policies} runtime_settings={runtime_settings} artifacts={artifacts}; existing rows unchanged"
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="afterglow.conf path")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--legacy-base-image", action="append", default=[], metavar="RELEASE=IMAGE_ID")
    args = parser.parse_args()
    try:
        raise SystemExit(asyncio.run(_main(args)))
    except Exception as exc:
        print(f"import failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
