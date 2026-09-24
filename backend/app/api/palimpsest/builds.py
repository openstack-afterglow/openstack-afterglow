"""Palimpsest 빌드 API — 사용자가 올린 Dockerfile 로 레이어 체인을 만든다.

기존 `/api/v1/admin/libraries/imports/dockerfile` 은 canonical public GitHub repo 의
commit 을 고정해 받아오는 경로다. 여기는 **본문을 직접 올리는** 경로다.

🔴 **보안**: inline Dockerfile 의 `RUN` 은 임의 셸 명령이다. 실행은 격리된 임시 Builder VM
안에서만 일어나고 모든 보간이 `shlex.quote` 되지만, 그럼에도 **관리자 전용**으로 유지한다.
일반 사용자 개방은 격리 강도·쿼터·네트워크 정책이 선행되어야 하는 별도 결정이다.

빌드 컨텍스트가 없으므로 `COPY`/`ADD` 는 거부한다(파서가 `allow_build_context=False`).
"""

import ipaddress
import logging
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from pathlib import PurePosixPath
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.api.deps import get_os_conn, require_admin
from app.services.dockerfile_import import (
    DockerfileImportError,
    compute_step_digest,
    create_import_job,
    prepare_inline_dockerfile_import,
)

_logger = logging.getLogger(__name__)

router = APIRouter()

_MAX_DOCKERFILE_CHARS = 1024 * 1024


class InlineDockerfileBuildRequest(BaseModel):
    """업로드한 Dockerfile 로 레이어 체인을 빌드한다."""

    dockerfile: str = Field(..., min_length=1, max_length=_MAX_DOCKERFILE_CHARS)
    layer_prefix: str
    profile_name: str | None = None
    # `FROM ubuntu:<ver>` 일 때 필수. `FROM palimpsest/<name>@sha256:…` 이면 부모에게서 상속한다.
    base_image_id: str | None = None

    @field_validator("dockerfile")
    @classmethod
    def _check_dockerfile(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Dockerfile 본문이 비어 있습니다")
        return value


class FetchDockerfileUrlRequest(BaseModel):
    """원격 URL에서 Dockerfile 본문을 안전하게 가져온다."""

    url: str = Field(..., min_length=1, max_length=2048, description="Dockerfile을 호스팅하는 HTTP/HTTPS URL")

    @field_validator("url")
    @classmethod
    def _check_url(cls, value: str) -> str:
        v = value.strip()
        if not v:
            raise ValueError("URL이 비어 있습니다")
        return v


_GITHUB_BLOB_RE = re.compile(r"^https://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.*)$")


def _normalize_dockerfile_url(raw_url: str) -> str:
    """GitHub blob URL을 raw URL로 정규화한다."""
    match = _GITHUB_BLOB_RE.match(raw_url)
    if match:
        owner, repo, ref, path = match.groups()
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}"
    return raw_url


def _validate_safe_url(url: str) -> urllib.parse.SplitResult:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise HTTPException(status_code=422, detail="http 또는 https URL만 지원됩니다")
    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(status_code=422, detail="유효한 호스트가 포함된 URL이어야 합니다")

    # SSRF 차단: IP 직접 입력 및 DNS 해석 결과 검증
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise HTTPException(status_code=422, detail="로컬/사설 네트워크 주소는 접근할 수 없습니다")
    except ValueError:
        if hostname.lower() in {"localhost", "metadata", "metadata.google.internal"} or hostname.lower().endswith(
            ".local"
        ):
            raise HTTPException(status_code=422, detail="로컬/사설 네트워크 주소는 접근할 수 없습니다")
        try:
            addr_info = socket.getaddrinfo(hostname, None)
            for item in addr_info:
                sockaddr = item[4]
                ip = ipaddress.ip_address(sockaddr[0])
                if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                    raise HTTPException(status_code=422, detail="로컬/사설 네트워크 주소는 접근할 수 없습니다")
        except socket.gaierror as exc:
            raise HTTPException(status_code=422, detail=f"호스트를 확인할 수 없습니다: {hostname}") from exc

    return parsed


@router.post("/dockerfile", dependencies=[Depends(require_admin)])
async def build_from_inline_dockerfile(
    req: InlineDockerfileBuildRequest,
    conn=Depends(get_os_conn),
) -> dict[str, Any]:
    """Dockerfile 을 해석해 빌드 잡을 만든다.

    같은 부모 위에 같은 명령이 이미 빌드돼 있으면 그 접두부는 **재사용**하고 나머지만 빌드한다
    (`step_digest` 기반 캐시). 전부 캐시에 맞으면 만들 게 없다는 뜻이므로 409 를 준다.
    """
    try:
        plan = await prepare_inline_dockerfile_import(
            conn,
            dockerfile_text=req.dockerfile,
            layer_prefix=req.layer_prefix,
            profile_name=req.profile_name,
            base_image_id=req.base_image_id,
        )
    except DockerfileImportError as exc:
        message = str(exc)
        # "전부 캐시" 는 잘못된 요청이 아니라 상태 충돌이다
        status = 409 if "모든 단계가 이미 빌드" in message else 422
        raise HTTPException(status_code=status, detail=message) from exc

    try:
        job = await create_import_job(plan)
    except DockerfileImportError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        **job,
        "source_type": plan.source_type,
        "dockerfile_digest": plan.dockerfile_digest,
        "parent_digest": plan.parent_digest,
        "cached_artifact_ids": plan.cached_artifact_ids,
        "planned_step_count": len(plan.planned_layers),
    }


@router.post("/dockerfile/plan", dependencies=[Depends(require_admin)])
async def preview_inline_dockerfile_plan(
    req: InlineDockerfileBuildRequest,
    conn=Depends(get_os_conn),
) -> dict[str, Any]:
    """빌드하지 않고 계획만 본다 — 어떤 단계가 캐시에 맞는지 확인하는 용도."""
    try:
        plan = await prepare_inline_dockerfile_import(
            conn,
            dockerfile_text=req.dockerfile,
            layer_prefix=req.layer_prefix,
            profile_name=req.profile_name,
            base_image_id=req.base_image_id,
        )
    except DockerfileImportError as exc:
        message = str(exc)
        status = 409 if "모든 단계가 이미 빌드" in message else 422
        raise HTTPException(status_code=status, detail=message) from exc

    return {
        "source_type": plan.source_type,
        "dockerfile_digest": plan.dockerfile_digest,
        "parent_digest": plan.parent_digest,
        "ubuntu_base": plan.base_image_snapshot.get("ubuntu_base"),
        "cached_artifact_ids": plan.cached_artifact_ids,
        "steps": [
            {
                "name": step["name"],
                "instruction": step["instruction"],
                "args": step["args"],
                "step_digest": step.get("step_digest"),
            }
            for step in plan.planned_layers
        ],
    }


@router.post("/dockerfile/fetch-url", dependencies=[Depends(require_admin)])
async def fetch_dockerfile_from_url(req: FetchDockerfileUrlRequest) -> dict[str, Any]:
    """원격 URL(GitHub raw, GitLab, 일반 HTTP/S)에서 Dockerfile 텍스트를 가져온다."""
    normalized_url = _normalize_dockerfile_url(req.url)
    _validate_safe_url(normalized_url)

    request = urllib.request.Request(
        normalized_url,
        headers={
            "User-Agent": "afterglow-palimpsest-import/1.0",
            "Accept": "text/plain, text/x-dockerfile, text/plain;charset=utf-8, */*",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as resp:
            final_url = resp.geturl()
            _validate_safe_url(final_url)
            raw = resp.read(_MAX_DOCKERFILE_CHARS + 1)
    except urllib.error.HTTPError as exc:
        raise HTTPException(
            status_code=exc.code if exc.code in {400, 403, 404} else 502,
            detail=f"원격 서버 오류: HTTP {exc.code}",
        ) from exc
    except urllib.error.URLError as exc:
        raise HTTPException(status_code=502, detail=f"원격 URL에 연결할 수 없습니다: {exc.reason}") from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="원격 URL 요청 시간이 초과되었습니다") from exc

    if len(raw) > _MAX_DOCKERFILE_CHARS:
        raise HTTPException(status_code=422, detail="Dockerfile 크기는 1MiB 이하여야 합니다")

    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="Dockerfile은 UTF-8 인코딩 텍스트여야 합니다") from exc

    if not content.strip():
        raise HTTPException(status_code=422, detail="가져온 Dockerfile 본문이 비어 있습니다")

    filename = PurePosixPath(urllib.parse.urlsplit(normalized_url).path).name or "Dockerfile"

    return {
        "dockerfile": content,
        "url": normalized_url,
        "filename": filename,
        "size_bytes": len(raw),
    }


__all__ = ["compute_step_digest", "router"]
