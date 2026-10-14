"""Durable squashfs build admission; assigned workers consume SQL identities."""

from __future__ import annotations

import logging
import uuid
from copy import deepcopy

from app.config import get_settings
from app.services.layer_ubuntu import normalize_ubuntu_base


def _base_image_fields(snapshot: dict | None) -> dict:
    if not isinstance(snapshot, dict):
        return {}
    return {
        name: snapshot.get(name)
        for name in (
            "base_image_id",
            "base_image_name",
            "base_image_checksum",
            "base_image_os_hash_algo",
            "base_image_os_hash_value",
            "base_image_min_disk",
            "base_image_visibility",
            "base_image_owner",
            "source_metadata",
        )
        if snapshot.get(name) is not None
    }


_logger = logging.getLogger(__name__)


class LayerBuildUnavailable(RuntimeError):
    """A build cannot be admitted or consumed without durable SQL authority."""


async def start_layer_build(
    layer_name: str,
    kind: str,
    python_version: str | None,
    pip_packages: list[str],
    apt_packages: list[str] | None = None,
    pip_index_url: str | None = None,
    pip_extra_index_urls: list[str] | None = None,
    pip_find_links: list[str] | None = None,
    parent_artifact_id: int | None = None,
    nvidia_driver_branch: str | None = None,
    ubuntu_base: str | None = None,
    base_image_snapshot: dict | None = None,
    source_metadata: dict | None = None,
) -> dict:
    """Commit the immutable recipe/resource snapshot before any worker allocation."""
    from app.database import get_session_factory
    from app.models.db import LayerBuild

    factory = get_session_factory()
    if factory is None:
        raise LayerBuildUnavailable("layer build database unavailable")

    if base_image_snapshot and base_image_snapshot.get("ubuntu_base"):
        effective_ubuntu_base = normalize_ubuntu_base(base_image_snapshot.get("ubuntu_base"))
    else:
        effective_ubuntu_base = normalize_ubuntu_base(ubuntu_base)
    if source_metadata is not None:
        base_image_snapshot = {**(base_image_snapshot or {}), "source_metadata": source_metadata}

    if not base_image_snapshot or not base_image_snapshot.get("base_image_id"):
        raise ValueError("root and imported layer builds require an explicit base image")
    from app.services.resource_policy_store import (
        get_policy_snapshot,
        get_service_project_connection,
        lock_service_project_admission,
        resolve_policy_snapshot,
    )
    from app.services.work_dispatcher import close_connection

    service_project = (await get_policy_snapshot(("openstack.service_project",)))["openstack.service_project"]
    if service_project is None:
        raise ValueError("service project policy is not configured")

    service_conn = await get_service_project_connection(service_project["id"])
    try:
        policies = await resolve_policy_snapshot(
            conn=service_conn,
            service_conn=service_conn,
            keys=(
                "builder.flavor",
                "builder.network",
                "manila.share_network",
                "manila.nfs_share_type",
            ),
        )
    finally:
        await close_connection(service_conn)
    resource_snapshot = {
        "base_image": {
            "id": base_image_snapshot["base_image_id"],
            "name": base_image_snapshot.get("base_image_name") or base_image_snapshot["base_image_id"],
        },
        "openstack.service_project": service_project,
        "builder.flavor": deepcopy(policies["builder.flavor"]),
        "builder.network": deepcopy(policies["builder.network"]),
        "manila": {
            "share_network_id": policies["manila.share_network"]["id"],
            "share_type": policies["manila.nfs_share_type"]["name"],
            "share_proto": "NFS",
            "share_size_gb": get_settings().builder_layer_share_size_gb,
        },
        "build_input": {
            "layer_name": layer_name,
            "kind": kind,
            "python_version": python_version,
            "pip_packages": list(pip_packages or []),
            "apt_packages": [] if kind == "nvidia" else list(apt_packages or []),
            "pip_index_url": pip_index_url,
            "pip_extra_index_urls": list(pip_extra_index_urls or []),
            "pip_find_links": list(pip_find_links or []),
            "parent_artifact_id": parent_artifact_id,
            "nvidia_driver_branch": nvidia_driver_branch,
            "ubuntu_base": effective_ubuntu_base,
            "base_image_snapshot": deepcopy(base_image_snapshot),
            "source_metadata": deepcopy(source_metadata),
        },
    }
    from sqlalchemy.exc import SQLAlchemyError

    try:
        async with factory() as session:
            await lock_service_project_admission(session, service_project["id"])
            row = LayerBuild(
                layer_name=layer_name,
                kind=kind,
                python_version=python_version,
                pip_packages=list(pip_packages or []),
                apt_packages=list(apt_packages or []),
                ubuntu_base=effective_ubuntu_base,
                parent_artifact_id=parent_artifact_id,
                share_id="",
                builder_flavor_id=policies["builder.flavor"]["id"],
                builder_network_id=policies["builder.network"]["id"],
                resource_snapshot=resource_snapshot,
                build_token=uuid.uuid4().hex,
                status="queued",
                cloud_init_status="queued",
                progress_step="빌드 대기",
                progress_pct=0,
                **_base_image_fields(base_image_snapshot),
            )
            session.add(row)
            await session.commit()
            build_db_id = row.id
    except SQLAlchemyError as exc:
        raise LayerBuildUnavailable("layer build admission could not be committed") from exc

    return {
        "build_id": build_db_id,
        "layer_name": layer_name,
        "parent_artifact_id": parent_artifact_id,
        "status": "queued",
        "ubuntu_base": effective_ubuntu_base,
        "base_image_id": (base_image_snapshot or {}).get("base_image_id"),
        "base_image_name": (base_image_snapshot or {}).get("base_image_name"),
    }


async def execute_layer_build(build_id: int) -> None:
    """The unified worker binds ownership; the pipeline reloads its SQL identity."""
    from app.services.layer_build import run_layer_build

    await run_layer_build(build_id)


async def cancel_layer_build(build_db_id: int) -> dict:
    """진행 중인 레이어 빌드를 취소한다."""
    from sqlalchemy import select

    from app.database import get_session_factory
    from app.models.db import LayerBuild

    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("DB가 초기화되지 않았습니다")

    async with factory() as session:
        row = (
            await session.execute(select(LayerBuild).where(LayerBuild.id == build_db_id).with_for_update())
        ).scalar_one_or_none()
        if row is None:
            raise KeyError(f"빌드 {build_db_id}를 찾을 수 없습니다")

        terminal = {"complete", "error", "timeout", "cancelled"}
        if row.status in terminal:
            raise ValueError(f"이미 종료된 빌드입니다 (상태: {row.status})")

        layer_name = row.layer_name
        snapshot = deepcopy(row.resource_snapshot or {})
        snapshot["cancel_cleanup"] = "pending"
        row.resource_snapshot = snapshot

        row.status = "cancelled"
        row.cloud_init_status = "failure"
        row.progress_step = "사용자 취소"
        row.error_message = "관리자에 의해 취소됨"
        await session.commit()

    # The assigned cleanup owner waits for in-flight SDK effects and observes
    # late accepted identities; the request cannot safely use its earlier IDs.
    return {"cancelled": True, "layer_name": layer_name}
