"""Palimpsest 레이어 조회 — digest 기반 검색과 부모 체인.

사용자 JWT 로 접근하며 **공개(`is_published`) + 봉인(`is_sealed`)된 레이어만** 노출한다.
전체 목록은 관리자 `/api/v1/admin/palimpsest/artifacts` 가 담당한다.
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from app.api.deps import get_token_info
from app.database import get_session_factory
from app.models.db import LayerArtifact
from app.services.palimpsest_digest import is_digest_prefix, normalize_digest, normalize_md5
from app.services.palimpsest_layers import load_ancestor_chain

router = APIRouter()

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9.+\-]{0,63}$")
_KIND_RE = re.compile(r"^[a-z][a-z0-9_-]{0,15}$")
_MAX_LIMIT = 200


def _layer_dict(row: LayerArtifact) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "kind": row.kind,
        "ubuntu_base": row.ubuntu_base,
        "python_version": row.python_version,
        "parent_id": row.parent_id,
        "size_bytes": row.size_bytes,
        "blob_digest": row.blob_digest,
        "blob_md5": row.blob_md5,
        "config_digest": row.config_digest,
        "chain_id": row.chain_id,
        "digest_state": row.digest_state,
        "is_sealed": row.is_sealed,
        "is_published": row.is_published,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _visible(stmt):
    """사용자에게 보이는 레이어만."""
    return stmt.where(LayerArtifact.is_published.is_(True)).where(LayerArtifact.is_sealed.is_(True))


@router.get("/layers")
async def search_layers(
    digest: str | None = Query(None, description="정확한 blob digest (sha256:<64hex> 또는 64hex)"),
    digest_prefix: str | None = Query(None, description="blob digest 접두사 (hex 4자 이상)"),
    md5: str | None = Query(None, description="보조 검색 키. 무결성 권위는 sha256 이다"),
    chain_id: str | None = Query(None, description="스택 전체 정체성"),
    name: str | None = Query(None),
    kind: str | None = Query(None),
    limit: int = Query(50, ge=1, le=_MAX_LIMIT),
    _token_info: dict = Depends(get_token_info),
) -> list[dict[str, Any]]:
    # 입력 검증이 DB 가용성 체크보다 먼저다 — 잘못된 요청은 DB 상태와 무관하게 422 여야 한다.
    stmt = _visible(select(LayerArtifact))

    if digest is not None:
        normalized = normalize_digest(digest)
        if normalized is None:
            raise HTTPException(status_code=422, detail="digest 는 sha256:<64hex> 형식이어야 합니다")
        stmt = stmt.where(LayerArtifact.blob_digest == normalized)

    if digest_prefix is not None:
        if not is_digest_prefix(digest_prefix):
            raise HTTPException(status_code=422, detail="digest_prefix 는 hex 4~64자여야 합니다")
        bare = digest_prefix.strip().lower().removeprefix("sha256:")
        stmt = stmt.where(LayerArtifact.blob_digest.startswith(f"sha256:{bare}"))

    if md5 is not None:
        normalized_md5 = normalize_md5(md5)
        if normalized_md5 is None:
            raise HTTPException(status_code=422, detail="md5 는 32자리 hex 여야 합니다")
        stmt = stmt.where(LayerArtifact.blob_md5 == normalized_md5)

    if chain_id is not None:
        normalized_chain = normalize_digest(chain_id)
        if normalized_chain is None:
            raise HTTPException(status_code=422, detail="chain_id 는 sha256:<64hex> 형식이어야 합니다")
        stmt = stmt.where(LayerArtifact.chain_id == normalized_chain)

    if name is not None:
        if not _NAME_RE.match(name):
            raise HTTPException(status_code=422, detail="name 형식이 유효하지 않습니다")
        stmt = stmt.where(LayerArtifact.name == name)

    if kind is not None:
        if not _KIND_RE.match(kind):
            raise HTTPException(status_code=422, detail="kind 형식이 유효하지 않습니다")
        stmt = stmt.where(LayerArtifact.kind == kind)

    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail="DB 연결이 초기화되지 않았습니다")

    async with factory() as session:
        rows = (await session.execute(stmt.order_by(LayerArtifact.id).limit(limit))).scalars().all()
        return [_layer_dict(row) for row in rows]


@router.get("/layers/{artifact_id}/ancestors")
async def get_layer_ancestors(
    artifact_id: int,
    _token_info: dict = Depends(get_token_info),
) -> list[dict[str, Any]]:
    """루트 → 자기 자신 순서의 부모 체인.

    허브 번들의 `layers[]` 와 같은 순서다. OverlayFS `lowerdir` 는 왼쪽이 최상위이므로
    마운트 시에는 뒤집어 써야 한다(`docs/palimpsest.md` §5).
    """
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail="DB 연결이 초기화되지 않았습니다")

    async with factory() as session:
        row = await session.get(LayerArtifact, artifact_id)
        # 비공개 레이어의 존재 여부를 흘리지 않도록 미공개도 404 로 통일한다.
        if row is None or not (row.is_published and row.is_sealed):
            raise HTTPException(status_code=404, detail="레이어를 찾을 수 없습니다")
        chain = await load_ancestor_chain(session, row)
        return [_layer_dict(item) for item in chain]
