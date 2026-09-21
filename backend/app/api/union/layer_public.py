"""Authenticated public squashfs layer consumption API for VM creation beta."""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import select

from app.api.deps import get_os_conn, get_token_info
from app.config import get_settings
from app.database import get_session_factory
from app.models.db import LayerArtifact, LayerConsume, LayerProfile
from app.services import github_ssh, vm_cloud_init_library
from app.services.cache import invalidate
from app.services.cache import invalidation as cache_invalidation
from app.services.layer_base_images import legacy_snapshot_for_ubuntu_base
from app.services.layer_ubuntu import normalize_ubuntu_base
from app.services.resource_policy_store import get_service_project_connection
from app.utils.ssh_keys import validate_ssh_public_key

_logger = logging.getLogger(__name__)

router = APIRouter()

_LAYER_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9.+\-]*$")
_SERVER_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9\-_.]*$")
_FLAVOR_ID_RE = re.compile(r"^[a-zA-Z0-9\-_.]+$")
_SSH_USERNAME_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")


class PublicLayerConsumeRequest(BaseModel):
    profile_name: str | None = None
    artifact_ids: list[int] | None = None
    server_name: str | None = None
    flavor_id: str
    image_id: str | None = None
    network_id: str | None = None
    key_name: str | None = None
    github_username: str | None = None
    userdata: str | None = Field(default=None, max_length=65_536)
    ssh_public_key: str | None = None
    ssh_username: str | None = None

    @field_validator("profile_name")
    @classmethod
    def validate_profile_name(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if not _LAYER_NAME_RE.match(v):
            raise ValueError(f"유효하지 않은 프로필 이름: {v!r}")
        return v

    @field_validator("artifact_ids")
    @classmethod
    def validate_artifact_ids(cls, v: list[int] | None) -> list[int] | None:
        if v is None:
            return None
        ids = list(dict.fromkeys(int(item) for item in v))
        if not ids:
            raise ValueError("artifact_ids는 최소 1개 이상이어야 합니다")
        if any(item <= 0 for item in ids):
            raise ValueError("artifact_ids는 양수여야 합니다")
        return ids

    @field_validator("server_name")
    @classmethod
    def validate_server_name(cls, v: str | None) -> str | None:
        from app.services.instance_names import normalize_requested_instance_name

        return normalize_requested_instance_name(v)

    @field_validator("flavor_id")
    @classmethod
    def validate_flavor_id(cls, v: str) -> str:
        if not _FLAVOR_ID_RE.match(v):
            raise ValueError(f"유효하지 않은 flavor_id: {v!r}")
        return v

    @field_validator("key_name")
    @classmethod
    def validate_key_name(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if len(v) > 255 or any(ch in v for ch in "\n\r\t"):
            raise ValueError(f"유효하지 않은 key_name: {v!r}")
        return v

    @field_validator("ssh_public_key")
    @classmethod
    def validate_ssh_public_key(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if v == "":
            return None
        validate_ssh_public_key(v)
        return v

    @field_validator("github_username")
    @classmethod
    def validate_github_username(cls, v: str | None) -> str | None:
        from app.services.ssh_access import normalize_github_username

        return normalize_github_username(v)

    @field_validator("ssh_username")
    @classmethod
    def validate_ssh_username(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if not _SSH_USERNAME_RE.match(v):
            raise ValueError(f"유효하지 않은 SSH 사용자명: {v!r}")
        if v == "root":
            raise ValueError("root SSH 사용자는 허용되지 않습니다")
        return v

    @model_validator(mode="after")
    def validate_source(self) -> PublicLayerConsumeRequest:
        if bool(self.profile_name) == bool(self.artifact_ids):
            raise ValueError("profile_name 또는 artifact_ids 중 정확히 하나만 지정해야 합니다")
        if self.github_username and (self.key_name or self.ssh_public_key or self.ssh_username):
            raise ValueError("github_username은 key_name, ssh_public_key, ssh_username과 함께 사용할 수 없습니다")
        if self.ssh_username and not (self.key_name or self.ssh_public_key):
            raise ValueError("ssh_username은 key_name 또는 ssh_public_key와 함께 사용해야 합니다")
        return self


def _iso(value) -> str | None:
    if value is None:
        return None
    return value.isoformat().replace("+00:00", "Z")


def _artifact_base_image_snapshot(row: LayerArtifact) -> dict[str, Any]:
    snapshot = {
        "ubuntu_base": normalize_ubuntu_base(row.ubuntu_base),
        "base_image_id": row.base_image_id,
        "base_image_name": row.base_image_name,
        "base_image_checksum": row.base_image_checksum,
        "base_image_os_hash_algo": row.base_image_os_hash_algo,
        "base_image_os_hash_value": row.base_image_os_hash_value,
        "base_image_min_disk": row.base_image_min_disk,
        "base_image_visibility": row.base_image_visibility,
        "base_image_owner": row.base_image_owner,
    }
    if snapshot.get("base_image_id"):
        return snapshot
    return legacy_snapshot_for_ubuntu_base(get_settings(), snapshot.get("ubuntu_base"))


def _base_image_id(row: LayerArtifact) -> str:
    snapshot = _artifact_base_image_snapshot(row)
    image_id = snapshot.get("base_image_id")
    if not image_id:
        raise ValueError(f"artifact {row.id} base_image_id is unresolved")
    return str(image_id)


def _artifact_public_dict(row: LayerArtifact) -> dict[str, Any]:
    snapshot = _artifact_base_image_snapshot(row)
    return {
        "id": row.id,
        "name": row.name,
        "kind": row.kind,
        "python_version": row.python_version,
        "pip_packages": row.pip_packages if isinstance(row.pip_packages, list) else [],
        "apt_packages": row.apt_packages if isinstance(row.apt_packages, list) else [],
        "ubuntu_base": normalize_ubuntu_base(snapshot.get("ubuntu_base")),
        "base_image_id": snapshot.get("base_image_id"),
        "base_image_name": snapshot.get("base_image_name"),
        "base_image_checksum": snapshot.get("base_image_checksum"),
        "base_image_os_hash_algo": snapshot.get("base_image_os_hash_algo"),
        "base_image_os_hash_value": snapshot.get("base_image_os_hash_value"),
        "base_image_min_disk": snapshot.get("base_image_min_disk"),
        "base_image_visibility": snapshot.get("base_image_visibility"),
        "base_image_owner": snapshot.get("base_image_owner"),
        "parent_id": row.parent_id,
        "created_at": _iso(row.created_at),
    }


def _resolved_artifact_dict(row: LayerArtifact) -> dict[str, Any]:
    data = _artifact_public_dict(row)
    data.update({"share_id": row.share_id, "sqsh_filename": row.sqsh_filename})
    return data


async def _load_published_artifacts(session) -> list[LayerArtifact]:
    return (
        (
            await session.execute(
                select(LayerArtifact)
                .where(LayerArtifact.is_published.is_(True))
                .where(LayerArtifact.is_sealed.is_(True))
                .order_by(LayerArtifact.created_at)
            )
        )
        .scalars()
        .all()
    )


def _single_published_by_name(rows: list[LayerArtifact]) -> dict[str, LayerArtifact]:
    by_name: dict[str, list[LayerArtifact]] = {}
    for row in rows:
        by_name.setdefault(row.name, []).append(row)
    return {name: matches[0] for name, matches in by_name.items() if len(matches) == 1}


def _profile_artifacts(profile: LayerProfile, by_name: dict[str, LayerArtifact]) -> list[LayerArtifact] | None:
    resolved: list[LayerArtifact] = []
    for name in profile.layers:
        row = by_name.get(name)
        if row is None:
            return None
        resolved.append(row)
    return resolved


def _base_image_summary(rows: list[LayerArtifact]) -> dict[str, Any]:
    snapshot = _artifact_base_image_snapshot(rows[0])
    return {
        "ubuntu_base": normalize_ubuntu_base(snapshot.get("ubuntu_base")),
        "base_image_id": snapshot.get("base_image_id"),
        "base_image_name": snapshot.get("base_image_name"),
        "base_image_checksum": snapshot.get("base_image_checksum"),
        "base_image_os_hash_algo": snapshot.get("base_image_os_hash_algo"),
        "base_image_os_hash_value": snapshot.get("base_image_os_hash_value"),
        "base_image_min_disk": snapshot.get("base_image_min_disk"),
    }


def _validate_single_base(rows: list[LayerArtifact]) -> None:
    try:
        base_ids = {_base_image_id(row) for row in rows}
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="선택한 레이어의 base image를 확인할 수 없습니다") from exc
    if len(base_ids) != 1:
        raise HTTPException(status_code=400, detail="선택한 레이어의 base image가 일치하지 않습니다")


async def _resolve_profile_artifact_ids(session, profile_name: str) -> list[LayerArtifact]:
    profile = (
        await session.execute(
            select(LayerProfile).where(LayerProfile.name == profile_name).where(LayerProfile.is_published.is_(True))
        )
    ).scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail=f"공개 프로필을 찾을 수 없습니다: {profile_name!r}")
    published = await _load_published_artifacts(session)
    by_name_all: dict[str, list[LayerArtifact]] = {}
    for row in published:
        by_name_all.setdefault(row.name, []).append(row)
    resolved: list[LayerArtifact] = []
    for name in profile.layers:
        matches = by_name_all.get(name, [])
        if not matches:
            raise HTTPException(status_code=400, detail=f"프로필 레이어가 공개/봉인되어 있지 않습니다: {name!r}")
        if len(matches) > 1:
            raise HTTPException(status_code=409, detail=f"프로필 레이어 이름이 중복되어 모호합니다: {name!r}")
        resolved.append(matches[0])
    _validate_single_base(resolved)
    return resolved


async def _resolve_direct_artifacts(session, artifact_ids: list[int]) -> list[LayerArtifact]:
    requested = list(dict.fromkeys(artifact_ids))
    rows = (
        (
            await session.execute(
                select(LayerArtifact)
                .where(LayerArtifact.id.in_(requested))
                .where(LayerArtifact.is_published.is_(True))
                .where(LayerArtifact.is_sealed.is_(True))
            )
        )
        .scalars()
        .all()
    )
    by_id = {row.id: row for row in rows}
    missing = [artifact_id for artifact_id in requested if artifact_id not in by_id]
    if missing:
        raise HTTPException(status_code=404, detail=f"공개/봉인된 artifact를 찾을 수 없습니다: {missing}")

    all_rows = (await session.execute(select(LayerArtifact))).scalars().all()
    all_by_id = {row.id: row for row in all_rows}
    ordered: list[LayerArtifact] = []
    seen: set[int] = set()

    def add_chain(row: LayerArtifact) -> None:
        chain: list[LayerArtifact] = []
        current: LayerArtifact | None = row
        chain_seen: set[int] = set()
        while current is not None:
            if current.id in chain_seen:
                raise HTTPException(status_code=409, detail="artifact parent chain cycle detected")
            chain_seen.add(current.id)
            if not current.is_published or not current.is_sealed:
                raise HTTPException(
                    status_code=400, detail=f"ancestor artifact가 공개/봉인되어 있지 않습니다: {current.id}"
                )
            chain.append(current)
            current = all_by_id.get(current.parent_id) if current.parent_id is not None else None
        for item in reversed(chain):
            if item.id not in seen:
                seen.add(item.id)
                ordered.append(item)

    for artifact_id in requested:
        add_chain(by_id[artifact_id])

    for index, row in enumerate(ordered):
        expected_parent = None if index == 0 else ordered[index - 1].id
        if row.parent_id != expected_parent:
            raise HTTPException(status_code=400, detail="선택한 artifact lineage가 단일 parent chain이 아닙니다")
    _validate_single_base(ordered)
    return ordered


@router.get("/artifacts")
async def list_public_squashfs_artifacts(_token_info: dict = Depends(get_token_info)) -> list[dict[str, Any]]:
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail="DB 연결이 초기화되지 않았습니다")
    async with factory() as session:
        rows = await _load_published_artifacts(session)
        result: list[dict[str, Any]] = []
        for row in rows:
            try:
                result.append(_artifact_public_dict(row))
            except (RuntimeError, ValueError):
                _logger.warning("[layer_public] skipping artifact with unresolved base image: %s", row.id)
        return result


@router.get("/profiles")
async def list_public_squashfs_profiles(_token_info: dict = Depends(get_token_info)) -> list[dict[str, Any]]:
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail="DB 연결이 초기화되지 않았습니다")
    async with factory() as session:
        profiles = (
            (
                await session.execute(
                    select(LayerProfile).where(LayerProfile.is_published.is_(True)).order_by(LayerProfile.name)
                )
            )
            .scalars()
            .all()
        )
        published = await _load_published_artifacts(session)
        by_name = _single_published_by_name(published)
        result = []
        for profile in profiles:
            artifacts = _profile_artifacts(profile, by_name)
            if not artifacts:
                continue
            try:
                _validate_single_base(artifacts)
            except HTTPException:
                continue
            result.append(
                {
                    "id": profile.id,
                    "name": profile.name,
                    "layers": list(profile.layers),
                    "artifacts": [_artifact_public_dict(row) for row in artifacts],
                    "base_image": _base_image_summary(artifacts),
                    "created_at": _iso(profile.created_at),
                    "updated_at": _iso(profile.updated_at),
                }
            )
        return result


@router.post("/consume")
async def consume_public_squashfs(
    req: PublicLayerConsumeRequest,
    conn=Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
) -> dict[str, Any]:
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail="DB 연결이 초기화되지 않았습니다")

    project_id = token_info.get("project_id") or getattr(conn, "_afterglow_project_id", "")
    if not project_id:
        raise HTTPException(status_code=401, detail="프로젝트 스코프가 필요합니다")
    if req.github_username:
        try:
            await github_ssh.resolve_profile(req.github_username)
        except github_ssh.GitHubSshInvalid as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except github_ssh.GitHubSshUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    async with factory() as session:
        artifacts = (
            await _resolve_profile_artifact_ids(session, req.profile_name)
            if req.profile_name
            else await _resolve_direct_artifacts(session, req.artifact_ids or [])
        )
        _validate_single_base(artifacts)
        resolved = [_resolved_artifact_dict(row) for row in artifacts]
        consume_profile_name = req.profile_name or f"direct-{uuid.uuid4().hex[:8]}"

    ssh_public_key: str | None = req.ssh_public_key or None
    if req.key_name and not ssh_public_key:
        kp = None
        try:
            kp = await asyncio.to_thread(conn.compute.get_keypair, req.key_name)
        except Exception:
            try:
                kp = await asyncio.to_thread(conn.compute.find_keypair, req.key_name)
            except Exception:
                kp = None
        ssh_public_key = getattr(kp, "public_key", None) or ""
        if not ssh_public_key:
            raise HTTPException(
                status_code=400, detail=f"선택한 키페어의 공개키를 조회할 수 없습니다: {req.key_name!r}"
            )

    from app.services.layer_build import resolve_layer_consume_resource_snapshot, run_layer_consume

    try:
        resource_snapshot = await resolve_layer_consume_resource_snapshot(
            conn,
            flavor_ref=req.flavor_id,
            network_id=req.network_id,
        )
        share_conn = await get_service_project_connection()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    async with factory() as session:
        row = LayerConsume(
            profile_name=consume_profile_name,
            project_id=project_id,
            artifact_ids=[row.id for row in artifacts],
            server_name=req.server_name,
            share_id=artifacts[0].share_id,
            resource_snapshot=resource_snapshot,
            status="creating",
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        consume_id = row.id

    try:
        server_id = await run_layer_consume(
            consume_db_id=consume_id,
            profile_name=consume_profile_name,
            server_name=req.server_name,
            flavor_id=req.flavor_id,
            image_id=req.image_id,
            network_id=req.network_id,
            ssh_public_key=ssh_public_key,
            ssh_username=req.ssh_username,
            github_username=req.github_username,
            custom_userdata=req.userdata,
            compute_conn=conn,
            share_conn=share_conn,
            artifact_ids=[row.id for row in artifacts],
            resolved_artifacts=resolved,
            resource_snapshot=resource_snapshot,
        )
        await invalidate(f"afterglow:nova:{project_id}:instances")
        await cache_invalidation.invalidate_mutation_count("nova", project_id)
        try:
            await vm_cloud_init_library.record_history(user_id=token_info["user_id"], content=req.userdata)
        except Exception:
            _logger.warning("cloud-init 실행 이력 저장 실패", extra={"user_id": token_info.get("user_id")})
        return {"consume_id": consume_id, "server_id": server_id, "status": "active"}
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        _logger.exception("[layer_public] public squashfs consume failed")
        raise HTTPException(status_code=500, detail="squashfs consume 생성 실패") from exc
    finally:
        try:
            await asyncio.to_thread(share_conn.close)
        except Exception:
            _logger.warning("[layer_public] service share connection close failed", exc_info=True)
