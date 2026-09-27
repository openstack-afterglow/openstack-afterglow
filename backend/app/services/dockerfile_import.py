"""GitHub Dockerfile → squashfs layer import workflow."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import logging
import re
import shlex
import tarfile
import textwrap
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any

from app.config import get_settings
from app.database import get_session_factory
from app.models.db import LayerArtifact, LayerBuild, LayerImportJob, LayerProfile
from app.services import manila, neutron, nova
from app.services.layer_base_images import (
    FROM_REF_RE,
    list_base_images,
    resolve_from_reference,
    resolve_glance_base_snapshot,
)
from app.services.layer_build import LAYER_BUILD_IMAGE_PACKAGES, _wait_for_shutoff
from app.services.palimpsest_digest import parse_digest_sentinels
from app.services.palimpsest_kvm import MAX_LAYER_DISKS
from app.services.palimpsest_layers import load_lineage, resolve_digest_fields

_logger = logging.getLogger(__name__)

_GITHUB_RE = re.compile(
    r"^https://github\.com/([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}[A-Za-z0-9])?)/([A-Za-z0-9._-]{1,100})/?$"
)
_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/\-]{0,127}$")
_PATH_RE = re.compile(r"^[A-Za-z0-9._/\-]{1,255}$")
_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_LAYER_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9.+\-]*$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_UNSUPPORTED = {
    "ARG",
    "USER",
    "EXPOSE",
    "ENTRYPOINT",
    "CMD",
    "VOLUME",
    "HEALTHCHECK",
    "SHELL",
    "ONBUILD",
    "STOPSIGNAL",
    "LABEL",
}
_MAX_DOCKERFILE_BYTES = 1024 * 1024
_MAX_ARCHIVE_BYTES = 50 * 1024 * 1024
_MAX_ARCHIVE_FILES = 5000
_ARCHIVE_EXTENSIONS = (".tar", ".tar.gz", ".tgz", ".zip", ".whl")


@dataclass(frozen=True)
class GitHubRepo:
    owner: str
    repo: str
    canonical_url: str


SOURCE_GITHUB = "github_dockerfile"
SOURCE_INLINE = "inline_dockerfile"

# FROM 이 기존 Palimpsest 레이어를 가리키는 형태: `FROM palimpsest/<name>@sha256:<64hex>`
_PALIMPSEST_FROM_RE = re.compile(r"^palimpsest/([a-z0-9][a-z0-9.+\-]{0,63})@(sha256:[0-9a-f]{64})$")


@dataclass(frozen=True)
class ParsedDockerfile:
    """One FROM target plus the steps to build on it."""

    from_ref: str | None
    parent_digest: str | None
    from_line: int | None
    planned_layers: list[dict]


@dataclass(frozen=True)
class DockerfilePlan:
    # github_* / commit_sha / dockerfile_path 는 source_type == SOURCE_GITHUB 일 때만 채워진다.
    github_url: str | None
    repo_owner: str | None
    repo_name: str | None
    commit_sha: str | None
    dockerfile_path: str | None
    layer_prefix: str
    profile_name: str
    base_image_snapshot: dict
    planned_layers: list[dict]
    source_type: str = SOURCE_GITHUB
    dockerfile_text: str | None = None
    dockerfile_digest: str | None = None
    parent_digest: str | None = None
    # 빌드 캐시로 재사용하는 접두부 artifact id (루트→리프 순).
    # 이 단계들은 `planned_layers` 에서 빠져 있어 빌더 VM 이 다시 만들지 않는다.
    cached_artifact_ids: list[int] = field(default_factory=list)


class DockerfileImportError(ValueError):
    def __init__(self, message: str, *, line: int | None = None, detail: str | None = None):
        super().__init__(message)
        self.line = line
        self.detail = detail if detail is not None else message


def _now() -> datetime:
    return datetime.now(UTC)


def _line_error(line: int, message: str) -> DockerfileImportError:
    return DockerfileImportError(f"Dockerfile line {line}: {message}", line=line, detail=message)


def validate_layer_name(value: str, *, field: str) -> str:
    name = str(value or "").strip()
    if not _LAYER_NAME_RE.match(name) or len(name) > 64:
        raise DockerfileImportError(f"{field}은 소문자/숫자/점/하이픈만 허용하며 64자 이하여야 합니다")
    return name


def parse_github_url(url: str) -> GitHubRepo:
    raw = str(url or "").strip()
    parsed = urllib.parse.urlsplit(raw)
    if parsed.scheme != "https" or parsed.netloc != "github.com" or parsed.username or parsed.password:
        raise DockerfileImportError("GitHub URL은 canonical https://github.com/{owner}/{repo} 형식이어야 합니다")
    if parsed.query or parsed.fragment:
        raise DockerfileImportError("GitHub URL에는 query/fragment를 사용할 수 없습니다")
    if any(ch in raw for ch in "\r\n\t '\"`$\\;|<>"):
        raise DockerfileImportError("GitHub URL에 허용되지 않는 문자가 있습니다")
    match = _GITHUB_RE.match(raw)
    if not match:
        raise DockerfileImportError("GitHub URL은 canonical https://github.com/{owner}/{repo} 형식이어야 합니다")
    owner, repo = match.groups()
    return GitHubRepo(owner=owner, repo=repo, canonical_url=f"https://github.com/{owner}/{repo}")


def validate_ref(ref: str | None) -> str | None:
    if ref is None or ref == "":
        return None
    value = str(ref).strip()
    if not _REF_RE.match(value) or ".." in value or value.startswith("/") or value.endswith("/"):
        raise DockerfileImportError("ref 형식이 유효하지 않습니다")
    if any(ch in value for ch in "\r\n\t '\"`$\\;|<>"):
        raise DockerfileImportError("ref에 허용되지 않는 문자가 있습니다")
    return value


def validate_dockerfile_path(path: str) -> str:
    value = str(path or "Dockerfile").strip() or "Dockerfile"
    if not _PATH_RE.match(value) or value.startswith("/") or ".." in PurePosixPath(value).parts:
        raise DockerfileImportError("dockerfile_path는 repo 내부 상대 경로여야 합니다")
    if any(ch in value for ch in "\r\n\t '\"`$\\;|<>"):
        raise DockerfileImportError("dockerfile_path에 허용되지 않는 문자가 있습니다")
    return value


def _http_json(url: str, *, timeout: float = 10.0) -> dict:
    req = urllib.request.Request(
        url, headers={"Accept": "application/vnd.github+json", "User-Agent": "afterglow-layer-import"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        final_host = urllib.parse.urlsplit(resp.geturl()).netloc.lower()
        if final_host not in {"api.github.com"}:
            raise DockerfileImportError("GitHub API redirect 대상이 허용되지 않습니다")
        return json.loads(resp.read(1024 * 1024).decode())


def resolve_github_commit(repo: GitHubRepo, ref: str | None) -> str:
    safe_ref = validate_ref(ref) or "HEAD"
    if _SHA_RE.match(safe_ref):
        return safe_ref
    quoted = urllib.parse.quote(safe_ref, safe="")
    data = _http_json(f"https://api.github.com/repos/{repo.owner}/{repo.repo}/commits/{quoted}")
    sha = str(data.get("sha") or "").lower()
    if not _SHA_RE.match(sha):
        raise DockerfileImportError("GitHub commit SHA를 확인할 수 없습니다")
    return sha


def fetch_pinned_dockerfile(repo: GitHubRepo, commit_sha: str, dockerfile_path: str) -> str:
    if not _SHA_RE.match(commit_sha):
        raise DockerfileImportError("commit_sha 형식이 유효하지 않습니다")
    path = validate_dockerfile_path(dockerfile_path)
    url = f"https://raw.githubusercontent.com/{repo.owner}/{repo.repo}/{commit_sha}/{urllib.parse.quote(path)}"
    req = urllib.request.Request(url, headers={"User-Agent": "afterglow-layer-import"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            final_host = urllib.parse.urlsplit(resp.geturl()).netloc.lower()
            if final_host not in {"raw.githubusercontent.com", "github.com"}:
                raise DockerfileImportError("GitHub raw redirect 대상이 허용되지 않습니다")
            content = resp.read(_MAX_DOCKERFILE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise DockerfileImportError(f"Dockerfile을 가져올 수 없습니다: HTTP {exc.code}") from exc
    if len(content) > _MAX_DOCKERFILE_BYTES:
        raise DockerfileImportError("Dockerfile 크기는 1MiB 이하여야 합니다")
    return content.decode("utf-8")


def validate_archive_bytes(blob: bytes) -> None:
    if len(blob) > _MAX_ARCHIVE_BYTES:
        raise DockerfileImportError("GitHub archive 크기는 50MiB 이하여야 합니다")
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as archive:
        members = archive.getmembers()
        if len(members) > _MAX_ARCHIVE_FILES:
            raise DockerfileImportError("GitHub archive 파일 수는 5000개 이하여야 합니다")
        for member in members:
            parts = PurePosixPath(member.name).parts
            if ".." in parts or member.name.startswith("/"):
                raise DockerfileImportError("archive에 안전하지 않은 경로가 있습니다")


def fetch_pinned_archive(repo: GitHubRepo, commit_sha: str) -> bytes:
    if not _SHA_RE.match(commit_sha):
        raise DockerfileImportError("commit_sha 형식이 유효하지 않습니다")
    url = f"https://codeload.github.com/{repo.owner}/{repo.repo}/tar.gz/{commit_sha}"
    req = urllib.request.Request(url, headers={"User-Agent": "afterglow-layer-import"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        final_host = urllib.parse.urlsplit(resp.geturl()).netloc.lower()
        if final_host not in {"codeload.github.com", "github.com"}:
            raise DockerfileImportError("GitHub archive redirect 대상이 허용되지 않습니다")
        blob = resp.read(_MAX_ARCHIVE_BYTES + 1)
    validate_archive_bytes(blob)
    return blob


def _logical_lines(text: str) -> list[tuple[int, str]]:
    result: list[tuple[int, str]] = []
    pending = ""
    start_line = 0
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.rstrip()
        stripped = line.strip()
        if not pending and (not stripped or stripped.startswith("#")):
            continue
        if "<<" in stripped:
            raise _line_error(lineno, "heredoc은 지원하지 않습니다")
        if not pending:
            start_line = lineno
        continued = stripped.endswith("\\")
        chunk = stripped[:-1].rstrip() if continued else stripped
        pending = f"{pending} {chunk}".strip() if pending else chunk
        if not continued:
            result.append((start_line, pending))
            pending = ""
    if pending:
        raise _line_error(start_line, "line continuation이 종료되지 않았습니다")
    return result


def _slug(text: str) -> str:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return "-".join(words[:4]) or "step"


def _validate_container_path(path: str, line: int, *, dest: bool = False) -> str:
    value = str(path or "").strip()
    if not value or "\x00" in value or ".." in PurePosixPath(value).parts:
        raise _line_error(line, "경로 traversal은 허용되지 않습니다")
    if not dest and value.startswith("/"):
        raise _line_error(line, "COPY/ADD source는 상대 경로여야 합니다")
    return value


def _parse_copy_add(instruction: str, args: str, line: int) -> dict:
    try:
        parts = shlex.split(args)
    except ValueError as exc:
        raise _line_error(line, f"{instruction} 구문을 파싱할 수 없습니다") from exc
    if len(parts) < 2:
        raise _line_error(line, f"{instruction}에는 source와 destination이 필요합니다")
    if any(part.startswith("--") for part in parts):
        raise _line_error(line, f"{instruction} flags는 지원하지 않습니다")
    sources = parts[:-1]
    dest = _validate_container_path(parts[-1], line, dest=True)
    for src in sources:
        if src.startswith(("http://", "https://")):
            raise _line_error(line, f"{instruction} remote URL은 지원하지 않습니다")
        if instruction == "ADD" and src.lower().endswith(_ARCHIVE_EXTENSIONS):
            raise _line_error(line, "ADD archive 자동 추출은 지원하지 않습니다")
        _validate_container_path(src, line)
    return {"sources": sources, "dest": dest}


def _parse_env(args: str, line: int) -> dict:
    if not args.strip():
        raise _line_error(line, "ENV 값이 비어 있습니다")
    env: dict[str, str] = {}
    if "=" in args.split()[0]:
        try:
            parts = shlex.split(args)
        except ValueError as exc:
            raise _line_error(line, "ENV 구문을 파싱할 수 없습니다") from exc
        for part in parts:
            if "=" not in part:
                raise _line_error(line, "ENV key=value 형식이 필요합니다")
            key, value = part.split("=", 1)
            if not _ENV_KEY_RE.match(key):
                raise _line_error(line, f"유효하지 않은 ENV key: {key!r}")
            if any(ch in value for ch in "\r\n\x00"):
                raise _line_error(line, "ENV value에 control 문자를 사용할 수 없습니다")
            env[key] = value
        return env
    try:
        parts = shlex.split(args)
    except ValueError as exc:
        raise _line_error(line, "ENV key value 형식이 필요합니다") from exc
    if len(parts) < 2:
        raise _line_error(line, "ENV key value 형식이 필요합니다")
    key = parts[0]
    value = " ".join(parts[1:])
    if not _ENV_KEY_RE.match(key):
        raise _line_error(line, f"유효하지 않은 ENV key: {key!r}")
    if any(ch in value for ch in "\r\n\x00"):
        raise _line_error(line, "ENV value에 control 문자를 사용할 수 없습니다")
    return {key: value}


def _parse_dockerfile_with_diagnostics(
    text: str,
    *,
    layer_prefix: str,
    profile_name: str,
    commit_sha: str | None,
    dockerfile_path: str | None,
    allow_build_context: bool,
) -> tuple[ParsedDockerfile | None, list[DockerfileImportError]]:
    """Parse once for lint and build; recover after independent instruction errors."""
    prefix = validate_layer_name(layer_prefix, field="layer_prefix")
    validate_layer_name(profile_name or layer_prefix, field="profile_name")
    from_ref: str | None = None
    parent_digest: str | None = None
    from_line: int | None = None
    seen_from = False
    planned: list[dict] = []
    diagnostics: list[DockerfileImportError] = []
    env: dict[str, str] = {}
    workdir = "/"
    try:
        lines = _logical_lines(text)
    except DockerfileImportError as exc:
        return None, [exc]
    for line, logical in lines:
        try:
            match = re.match(r"^([A-Za-z]+)\s+(.*)$", logical)
            if not match:
                raise _line_error(line, "Dockerfile instruction 형식이 아닙니다")
            instruction = match.group(1).upper()
            args = match.group(2).strip()
            if instruction == "FROM":
                if seen_from:
                    raise _line_error(line, "multi-stage FROM은 지원하지 않습니다")
                from_line = line
                seen_from = True
                if " AS " in f" {args.upper()} " or args.startswith("--"):
                    raise _line_error(line, "FROM AS/flags는 지원하지 않습니다")
                if args == "scratch":
                    raise _line_error(
                        line, "FROM scratch는 지원하지 않습니다 — Ubuntu Glance 이미지 또는 기존 레이어를 사용하세요"
                    )
                palimpsest_match = _PALIMPSEST_FROM_RE.match(args)
                if palimpsest_match:
                    parent_digest = palimpsest_match.group(2)
                elif args.startswith("palimpsest/"):
                    raise _line_error(line, "FROM palimpsest 레이어 참조 형식이 유효하지 않습니다")
                elif FROM_REF_RE.fullmatch(args):
                    from_ref = args
                else:
                    raise _line_error(
                        line,
                        "FROM은 Ubuntu tag, Glance 이미지 이름/UUID 또는 palimpsest/<name>@sha256:<64hex>여야 합니다",
                    )
                continue
            if not seen_from:
                raise _line_error(line, "첫 instruction은 FROM이어야 합니다")
            payload: dict[str, Any]
            if instruction == "RUN":
                if (
                    not args
                    or args.startswith("--")
                    or "--mount" in args
                    or "--network" in args
                    or "--security" in args
                ):
                    raise _line_error(line, "지원하지 않는 RUN 옵션입니다")
                payload = {"command": args, "env": dict(env), "workdir": workdir}
            elif instruction in {"COPY", "ADD"}:
                if not allow_build_context:
                    raise _line_error(
                        line,
                        f"{instruction}은 업로드한 Dockerfile에서 지원하지 않습니다 — 빌드 컨텍스트가 없습니다. GitHub 소스를 사용하세요",
                    )
                payload = _parse_copy_add(instruction, args, line)
            elif instruction == "ENV":
                updates = _parse_env(args, line)
                env.update(updates)
                payload = {"env": updates, "full_env": dict(env)}
            elif instruction == "WORKDIR":
                workdir = _validate_container_path(args, line, dest=True)
                payload = {"workdir": workdir}
            elif instruction in _UNSUPPORTED:
                raise _line_error(line, f"{instruction}은 v1 Dockerfile import에서 지원하지 않습니다")
            else:
                raise _line_error(line, f"알 수 없는 instruction: {instruction}")
            name = f"{prefix}-{len(planned) + 1:02d}-{_slug(instruction + ' ' + args)}"
            if len(name) > 64:
                raise _line_error(
                    line, f"생성될 layer name이 64자를 초과합니다: {name!r}; 더 짧은 layer_prefix를 사용하세요"
                )
            planned.append(
                {
                    "name": name,
                    "line": line,
                    "instruction": instruction,
                    "args": args,
                    "payload": payload,
                    "source_metadata": {
                        "dockerfile_line": line,
                        "dockerfile_instruction": instruction,
                        "commit_sha": commit_sha,
                        "dockerfile_path": dockerfile_path,
                    },
                }
            )
        except DockerfileImportError as exc:
            diagnostics.append(exc)
    if not seen_from:
        diagnostics.append(
            DockerfileImportError(
                "Dockerfile에는 FROM <ubuntu:<version> | Glance 이미지 이름/UUID | palimpsest/<name>@sha256:<64hex>> 가 필요합니다"
            )
        )
    elif not planned and not diagnostics:
        diagnostics.append(
            DockerfileImportError("Dockerfile에는 layer로 변환할 RUN/COPY/ADD/ENV/WORKDIR instruction이 필요합니다")
        )
    parsed = ParsedDockerfile(
        from_ref=from_ref, parent_digest=parent_digest, from_line=from_line, planned_layers=planned
    )
    return parsed, diagnostics


def parse_dockerfile_source(
    text: str,
    *,
    layer_prefix: str,
    profile_name: str,
    commit_sha: str | None,
    dockerfile_path: str | None,
    allow_build_context: bool = True,
    diagnostics: list[dict] | None = None,
) -> ParsedDockerfile:
    """Parse a build using the same syntax diagnostics as the editor lint."""
    parsed, errors = _parse_dockerfile_with_diagnostics(
        text,
        layer_prefix=layer_prefix,
        profile_name=profile_name,
        commit_sha=commit_sha,
        dockerfile_path=dockerfile_path,
        allow_build_context=allow_build_context,
    )
    if diagnostics is not None:
        diagnostics.extend({"line": exc.line, "message": exc.detail} for exc in errors)
        return parsed if parsed is not None else ParsedDockerfile(None, None, None, [])
    if errors:
        raise errors[0]
    assert parsed is not None
    return parsed


def resolve_dockerfile_base_image(conn: Any, parsed: ParsedDockerfile) -> dict:
    """Resolve the sole root image selection from FROM; fail on ambiguity."""
    if parsed.parent_digest or not parsed.from_ref:
        raise ValueError("root FROM must identify a Glance image")
    try:
        return resolve_glance_base_snapshot(conn, parsed.from_ref)
    except ValueError as exc:
        raise _line_error(parsed.from_line, str(exc)) from exc
    except Exception:
        _logger.warning("[dockerfile] Glance base image 조회 실패")
        raise DockerfileImportError("Glance 이미지 목록을 조회하지 못했습니다") from None


def compute_step_digest(parent_ref: str, instruction: str, args: str) -> str:
    """빌드 캐시 키 — 같은 부모 위의 같은 명령이면 같은 값.

    `parent_ref` 는 부모 레이어의 `chain_id` 또는 루트 Glance image ID다.
    Docker 의 레이어 캐시와 같은 개념이고, Palimpsest 의 chain_id 가 "여기까지의 스택"을
    한 값으로 대표해 주기 때문에 성립한다.

    instruction/args 는 공백만 정규화한다 — 셸 명령의 의미를 바꾸지 않기 위해 그 이상은 손대지 않는다.
    """
    normalized = f"{instruction.upper()} {' '.join(args.split())}"
    payload = f"{parent_ref}\n{normalized}".encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


async def parent_chain_depth(artifact: Any) -> int:
    """Count the sealed parent and its ancestors without consulting the build cache."""
    factory = get_session_factory()
    if factory is None:
        raise DockerfileImportError("DB가 초기화되지 않았습니다")
    async with factory() as session:
        return len(await load_lineage(session, artifact))


async def lint_dockerfile(conn: Any, *, dockerfile_text: str, layer_prefix: str | None) -> dict:
    """Return syntax, Glance resolution and local-KVM estimates without build side effects."""
    diagnostics: list[dict] = []
    prefix = "layer"
    if layer_prefix:
        try:
            prefix = validate_layer_name(layer_prefix, field="layer_prefix")
        except DockerfileImportError as exc:
            diagnostics.append({"line": None, "message": exc.detail})
    if len(dockerfile_text.encode("utf-8")) > _MAX_DOCKERFILE_BYTES:
        diagnostics.append({"line": None, "message": "Dockerfile 크기는 1MiB 이하여야 합니다"})
        parsed = ParsedDockerfile(None, None, None, [])
    elif not dockerfile_text.strip():
        diagnostics.append({"line": None, "message": "Dockerfile 본문이 비어 있습니다"})
        parsed = ParsedDockerfile(None, None, None, [])
    else:
        parsed = parse_dockerfile_source(
            dockerfile_text,
            layer_prefix=prefix,
            profile_name=prefix,
            commit_sha=None,
            dockerfile_path=None,
            allow_build_context=False,
            diagnostics=diagnostics,
        )

    from_info: dict = {
        "line": parsed.from_line,
        "ref": parsed.from_ref or parsed.parent_digest,
        "kind": None,
        "image": None,
        "parent": None,
        "completions": [],
        "error": None,
        "note": None,
    }
    inherited = 0
    if parsed.parent_digest:
        from_info["kind"] = "palimpsest"
        try:
            parent = await resolve_parent_layer(parsed.parent_digest)
            _snapshot_from_artifact(parent)
            inherited = await parent_chain_depth(parent)
            from_info["parent"] = {
                "id": parent.id,
                "name": parent.name,
                "blob_digest": parent.blob_digest,
                "ubuntu_base": parent.ubuntu_base,
                "base_image_name": parent.base_image_name,
                "chain_depth": inherited,
            }
        except DockerfileImportError as exc:
            from_info["error"] = str(exc)
    elif parsed.from_ref:
        try:
            images = await asyncio.to_thread(list_base_images, conn)
        except Exception:
            _logger.warning("[dockerfile_lint] Glance base image 목록 조회 실패", exc_info=True)
            from_info["error"] = "Glance 이미지 목록을 조회하지 못했습니다"
        else:
            resolution = resolve_from_reference(images, parsed.from_ref)
            from_info.update(
                kind=resolution.kind,
                image=resolution.image,
                error=resolution.error,
                note=resolution.note,
                completions=resolution.completions,
            )

    new = len(parsed.planned_layers)
    total = inherited + new
    warnings: list[dict] = []
    if total > MAX_LAYER_DISKS:
        warnings.append(
            {
                "line": None,
                "message": f"예상 체인 길이 {total}개가 로컬 KVM 레이어 상한 {MAX_LAYER_DISKS}개를 넘습니다 — RUN을 합치거나 부모 체인을 줄이세요",
            }
        )
    return {
        "valid": not diagnostics and from_info["error"] is None,
        "diagnostics": diagnostics,
        "warnings": warnings,
        "from": from_info,
        "layers": {
            "new": new,
            "inherited": inherited,
            "total": total,
            "limit": MAX_LAYER_DISKS,
            "by_instruction": dict(Counter(step["instruction"] for step in parsed.planned_layers)),
        },
    }


def prepare_dockerfile_import(
    conn,
    *,
    github_url: str,
    ref: str | None,
    dockerfile_path: str,
    layer_prefix: str,
    profile_name: str | None,
) -> DockerfilePlan:
    repo = parse_github_url(github_url)
    path = validate_dockerfile_path(dockerfile_path)
    prefix = validate_layer_name(layer_prefix, field="layer_prefix")
    profile = validate_layer_name(profile_name or prefix, field="profile_name")
    sha = resolve_github_commit(repo, ref)
    fetch_pinned_archive(repo, sha)
    dockerfile = fetch_pinned_dockerfile(repo, sha, path)
    parsed = parse_dockerfile_source(
        dockerfile,
        layer_prefix=prefix,
        profile_name=profile,
        commit_sha=sha,
        dockerfile_path=path,
    )
    if parsed.parent_digest:
        raise _line_error(parsed.from_line, "GitHub import에서는 Palimpsest 부모 FROM을 지원하지 않습니다")
    base_snapshot = resolve_dockerfile_base_image(conn, parsed)
    return DockerfilePlan(
        github_url=repo.canonical_url,
        repo_owner=repo.owner,
        repo_name=repo.repo,
        commit_sha=sha,
        dockerfile_path=path,
        layer_prefix=prefix,
        profile_name=profile,
        base_image_snapshot=base_snapshot,
        planned_layers=parsed.planned_layers,
    )


async def prepare_inline_dockerfile_import(
    conn,
    *,
    dockerfile_text: str,
    layer_prefix: str,
    profile_name: str | None,
) -> DockerfilePlan:
    """사용자가 올린 Dockerfile 본문을 레이어 계획으로 만든다.

    `FROM palimpsest/<name>@sha256:…` 는 부모 이미지를 상속한다.
    루트 FROM 은 Glance 에서 active Ubuntu 이미지를 선택한다.
    """
    if not dockerfile_text or not dockerfile_text.strip():
        raise DockerfileImportError("Dockerfile 본문이 비어 있습니다")
    raw = dockerfile_text.encode("utf-8")
    if len(raw) > _MAX_DOCKERFILE_BYTES:
        raise DockerfileImportError("Dockerfile 크기는 1MiB 이하여야 합니다")

    prefix = validate_layer_name(layer_prefix, field="layer_prefix")
    profile = validate_layer_name(profile_name or prefix, field="profile_name")
    parsed = parse_dockerfile_source(
        dockerfile_text,
        layer_prefix=prefix,
        profile_name=profile,
        commit_sha=None,
        dockerfile_path=None,
        allow_build_context=False,
    )

    parent = None
    if parsed.parent_digest:
        parent = await resolve_parent_layer(parsed.parent_digest)
        base_snapshot = _snapshot_from_artifact(parent)
        root_ref = parent.chain_id or parsed.parent_digest
    else:
        base_snapshot = await asyncio.to_thread(resolve_dockerfile_base_image, conn, parsed)
        root_ref = f"glance:{base_snapshot['base_image_id']}"

    annotated = await apply_build_cache(parsed.planned_layers, root_ref=root_ref)
    cached_ids, planned = split_cached_prefix(annotated)

    # `FROM palimpsest/…` 의 부모도 재사용 접두부의 일부다 — 빌드 루프가 여기서 이어 쌓는다.
    if parent:
        cached_ids = [parent.id, *cached_ids]
    if not planned:
        raise DockerfileImportError(
            "모든 단계가 이미 빌드되어 있습니다 — 새로 만들 레이어가 없습니다. 기존 프로파일을 그대로 사용하세요"
        )

    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    for step in planned:
        step["source_metadata"] = {
            **(step.get("source_metadata") or {}),
            "dockerfile_digest": digest,
            "source_type": SOURCE_INLINE,
        }

    return DockerfilePlan(
        github_url=None,
        repo_owner=None,
        repo_name=None,
        commit_sha=None,
        dockerfile_path=None,
        layer_prefix=prefix,
        profile_name=profile,
        base_image_snapshot=base_snapshot,
        planned_layers=planned,
        source_type=SOURCE_INLINE,
        dockerfile_text=dockerfile_text,
        dockerfile_digest=digest,
        parent_digest=parsed.parent_digest,
        cached_artifact_ids=cached_ids,
    )


def split_cached_prefix(annotated: list[dict]) -> tuple[list[int], list[dict]]:
    """캐시에 맞은 **선두 연속 구간**과 새로 빌드할 나머지로 나눈다.

    중간부터 재사용하는 건 불가능하다 — 레이어는 부모 위에 쌓이므로 앞을 건너뛰면 다른 스택이 된다.
    `apply_build_cache` 도 첫 미스 이후로는 캐시를 끄므로 여기서는 선두만 보면 된다.
    """
    cached_ids: list[int] = []
    for index, step in enumerate(annotated):
        if step.get("cached") and step.get("reuse_artifact_id"):
            cached_ids.append(int(step["reuse_artifact_id"]))
            continue
        return cached_ids, [dict(item) for item in annotated[index:]]
    return cached_ids, []


def _snapshot_from_artifact(artifact) -> dict:
    """부모 artifact 가 들고 있는 base image 지문을 그대로 물려받는다.

    `FROM palimpsest/...` 는 부모와 같은 Ubuntu base 위에서만 성립한다 — 다른 base 로
    쌓으면 ABI 가 어긋난다(union.md §4.2 의 다중 상속 위험과 같은 이유).
    """
    if not artifact.base_image_id:
        raise DockerfileImportError("부모 레이어에 Glance base image ID가 없습니다 — snapshot 백필이 필요합니다")
    return {
        "ubuntu_base": artifact.ubuntu_base,
        "base_image_id": artifact.base_image_id,
        "base_image_name": artifact.base_image_name,
        "base_image_checksum": artifact.base_image_checksum,
        "base_image_os_hash_algo": artifact.base_image_os_hash_algo,
        "base_image_os_hash_value": artifact.base_image_os_hash_value,
        "base_image_min_disk": artifact.base_image_min_disk,
    }


async def resolve_parent_layer(parent_digest: str) -> Any:
    """`FROM palimpsest/<name>@sha256:…` 이 가리키는 sealed artifact 를 찾는다."""
    from sqlalchemy import select

    from app.models.db import LayerArtifact

    factory = get_session_factory()
    if factory is None:
        raise DockerfileImportError("DB가 초기화되지 않았습니다")
    async with factory() as session:
        row = (
            await session.execute(
                select(LayerArtifact)
                .where(LayerArtifact.blob_digest == parent_digest)
                .where(LayerArtifact.is_sealed.is_(True))
                .order_by(LayerArtifact.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
    if row is None:
        raise DockerfileImportError(
            f"FROM 이 가리키는 레이어를 찾을 수 없습니다: {parent_digest} "
            "(digest 백필이 끝나지 않았거나 봉인되지 않은 레이어일 수 있습니다)"
        )
    return row


async def apply_build_cache(planned: list[dict], *, root_ref: str) -> list[dict]:
    """각 단계에 `step_digest` 를 붙이고, 이미 있는 sealed artifact 는 재사용으로 표시한다.

    `root_ref` 는 체인의 시작점 — ubuntu base 키(루트 빌드) 또는 부모 레이어의 chain_id 다.
    한 단계가 캐시에 맞으면 그 artifact 의 chain_id 가 다음 단계의 부모 참조가 된다.
    **캐시가 끊기면 그 뒤는 전부 새로 빌드한다** — 중간을 건너뛰면 스택이 달라지기 때문이다.
    """
    from sqlalchemy import select

    from app.models.db import LayerArtifact

    factory = get_session_factory()
    if factory is None:
        raise DockerfileImportError("DB가 초기화되지 않았습니다")

    annotated: list[dict] = []
    parent_ref = root_ref
    cache_live = True
    async with factory() as session:
        for step in planned:
            step_digest = compute_step_digest(parent_ref, step["instruction"], step["args"])
            entry = dict(step, step_digest=step_digest, cached=False, reuse_artifact_id=None)
            if cache_live:
                hit = (
                    await session.execute(
                        select(LayerArtifact)
                        .where(LayerArtifact.step_digest == step_digest)
                        .where(LayerArtifact.is_sealed.is_(True))
                        .order_by(LayerArtifact.id.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if hit is not None and hit.chain_id:
                    entry["cached"] = True
                    entry["reuse_artifact_id"] = hit.id
                    parent_ref = hit.chain_id
                    annotated.append(entry)
                    continue
                cache_live = False
            # 캐시 미스 이후로는 부모 참조를 알 수 없다(아직 빌드 전) — step_digest 만 기록해 두고
            # 실제 값은 빌드 후 artifact 에 저장된다.
            parent_ref = step_digest
            annotated.append(entry)
    return annotated


def _base_fields(snapshot: dict) -> dict:
    return {
        "ubuntu_base": snapshot["ubuntu_base"],
        "base_image_id": snapshot["base_image_id"],
        "base_image_name": snapshot.get("base_image_name"),
        "base_image_checksum": snapshot.get("base_image_checksum"),
        "base_image_os_hash_algo": snapshot.get("base_image_os_hash_algo"),
        "base_image_os_hash_value": snapshot.get("base_image_os_hash_value"),
        "base_image_min_disk": snapshot.get("base_image_min_disk"),
    }


def _job_to_dict(job: LayerImportJob) -> dict:
    return {
        "id": job.id,
        "source_type": job.source_type,
        "status": job.status,
        "progress_step": job.progress_step,
        "progress_pct": job.progress_pct,
        "error_message": job.error_message,
        "github_url": job.github_url,
        "repo_owner": job.repo_owner,
        "repo_name": job.repo_name,
        "commit_sha": job.commit_sha,
        "dockerfile_path": job.dockerfile_path,
        "layer_prefix": job.layer_prefix,
        "profile_name": job.profile_name,
        "ubuntu_base": job.ubuntu_base,
        "base_image_id": job.base_image_id,
        "base_image_name": job.base_image_name,
        "base_image_checksum": job.base_image_checksum,
        "base_image_os_hash_algo": job.base_image_os_hash_algo,
        "base_image_os_hash_value": job.base_image_os_hash_value,
        "base_image_min_disk": job.base_image_min_disk,
        "resource_snapshot": job.resource_snapshot,
        "artifact_ids": job.artifact_ids or [],
        "build_ids": job.build_ids or [],
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


async def create_import_job(plan: DockerfilePlan) -> dict:
    factory = get_session_factory()
    if factory is None:
        raise DockerfileImportError("DB가 초기화되지 않았습니다")
    from app.services.resource_policy_store import (
        get_policy_snapshot,
        get_service_project_connection,
        resolve_policy_snapshot,
    )

    service_conn = await get_service_project_connection()
    try:
        policies = await resolve_policy_snapshot(
            conn=service_conn,
            keys=("builder.flavor", "builder.network", "manila.share_network", "manila.nfs_share_type"),
        )
        service_project = (await get_policy_snapshot(("openstack.service_project",)))["openstack.service_project"]
        if service_project is None:
            raise DockerfileImportError("service project policy is not configured")
    finally:
        await asyncio.to_thread(service_conn.close)
    resource_snapshot = {
        "openstack.service_project": service_project,
        "base_image": {
            "id": plan.base_image_snapshot["base_image_id"],
            "name": plan.base_image_snapshot["base_image_name"],
        },
        **policies,
        "manila": {
            "share_network_id": policies["manila.share_network"]["id"],
            "share_type": policies["manila.nfs_share_type"]["name"],
            "share_proto": "NFS",
            "share_size_gb": get_settings().builder_layer_share_size_gb,
        },
    }
    async with factory() as session:
        job = LayerImportJob(
            source_type=plan.source_type,
            status="queued",
            progress_step="검증 완료",
            progress_pct=0,
            github_url=plan.github_url,
            repo_owner=plan.repo_owner,
            repo_name=plan.repo_name,
            commit_sha=plan.commit_sha,
            dockerfile_path=plan.dockerfile_path,
            dockerfile_text=plan.dockerfile_text,
            dockerfile_digest=plan.dockerfile_digest,
            parent_digest=plan.parent_digest,
            layer_prefix=plan.layer_prefix,
            profile_name=plan.profile_name,
            planned_layers=plan.planned_layers,
            # 캐시 재사용분을 미리 채워 둔다 — 빌드 루프가 여기서 이어 쌓는다.
            artifact_ids=list(plan.cached_artifact_ids),
            build_ids=[],
            resource_snapshot=resource_snapshot,
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        data = _job_to_dict(job)
    asyncio.create_task(run_dockerfile_import_job(data["id"]))
    return data


async def list_import_jobs(limit: int = 50) -> list[dict]:
    from sqlalchemy import desc, select

    factory = get_session_factory()
    if factory is None:
        raise DockerfileImportError("DB가 초기화되지 않았습니다")
    async with factory() as session:
        rows = (
            (
                await session.execute(
                    select(LayerImportJob).order_by(desc(LayerImportJob.created_at)).limit(min(limit, 100))
                )
            )
            .scalars()
            .all()
        )
        return [_job_to_dict(row) for row in rows]


async def get_import_job(import_id: int) -> dict | None:
    factory = get_session_factory()
    if factory is None:
        raise DockerfileImportError("DB가 초기화되지 않았습니다")
    async with factory() as session:
        row = await session.get(LayerImportJob, import_id)
        return _job_to_dict(row) if row else None


async def _update_job(job_id: int, **fields) -> None:
    factory = get_session_factory()
    if factory is None:
        return
    async with factory() as session:
        job = await session.get(LayerImportJob, job_id)
        if job is None:
            return
        for key, value in fields.items():
            setattr(job, key, value)
        job.updated_at = _now()
        if fields.get("status") in {"complete", "error", "cancelled"} and job.completed_at is None:
            job.completed_at = _now()
        await session.commit()


def _shell_export_env(env: dict[str, str]) -> str:
    return " ".join(f"{key}={shlex.quote(str(value))}" for key, value in sorted(env.items()))


def _dockerfile_cloud_init_script(job: LayerImportJob, exports: list[str], token: str) -> str:
    """Render the one-VM sequential OverlayFS Dockerfile executor.

    The builder downloads the pinned GitHub archive, extracts the context, mounts
    every per-step output share, executes each supported instruction against an
    overlay workspace, squashes only the upper delta to that step's share, then
    mounts the new squashfs as the top lowerdir for subsequent steps.
    """
    archive_url = f"https://codeload.github.com/{job.repo_owner}/{job.repo_name}/tar.gz/{job.commit_sha}"
    plan_json = shlex.quote(json.dumps(job.planned_layers or [], ensure_ascii=False))
    exports_json = shlex.quote(json.dumps(exports, ensure_ascii=False))
    archive_url_q = shlex.quote(archive_url)
    dockerfile_path_q = shlex.quote(job.dockerfile_path)
    return textwrap.dedent(
        f"""
        set -euo pipefail
        export AFTERGLOW_BUILD_TOKEN={shlex.quote(token)}
        install -d /etc/afterglow /etc/profile.d /mnt/afterglow-import /run/afterglow-dockerfile
        printf '%s' {plan_json} > /etc/afterglow/dockerfile-plan.json
        printf '%s' {exports_json} > /etc/afterglow/dockerfile-exports.json
        curl -fsSL --proto '=https' --tlsv1.2 {archive_url_q} -o /tmp/afterglow-repo.tar.gz
        mkdir -p /tmp/afterglow-context
        tar -xzf /tmp/afterglow-repo.tar.gz -C /tmp/afterglow-context --strip-components=1
        test -f /tmp/afterglow-context/{dockerfile_path_q}
        python3 - <<'PY'
        import json, os
        exports = json.load(open('/etc/afterglow/dockerfile-exports.json'))
        for idx, export in enumerate(exports):
            mount = f'/mnt/afterglow-import/out/{{idx}}'
            os.makedirs(mount, exist_ok=True)
            with open('/etc/fstab', 'a') as fh:
                fh.write(f'{{export}} {{mount}} nfs4 rw,nofail,_netdev,x-systemd.automount 0 0\\n')
        PY
        python3 - <<'PY'
        import json, subprocess
        exports = json.load(open('/etc/afterglow/dockerfile-exports.json'))
        for idx, _ in enumerate(exports):
            mount = f'/mnt/afterglow-import/out/{{idx}}'
            subprocess.check_call(['mount', mount])
            subprocess.check_call(['mkdir', '-p', f'{{mount}}/images'])
        PY
        cat > /usr/local/bin/afterglow-dockerfile-step.py <<'PY'
        import json, os, shlex, shutil, subprocess, sys
        from pathlib import Path

        plan = json.load(open('/etc/afterglow/dockerfile-plan.json'))
        env = {{}}
        workdir = '/'
        lowers = ['/']
        context = Path('/tmp/afterglow-context').resolve()

        def safe_context(src):
            p = (context / src).resolve()
            if not str(p).startswith(str(context) + os.sep) and p != context:
                raise SystemExit(f'unsafe COPY/ADD source: {{src}}')
            if not p.exists():
                raise SystemExit(f'missing COPY/ADD source: {{src}}')
            return p

        def mount_overlay(upper, work, merged):
            os.makedirs(upper, exist_ok=True)
            os.makedirs(work, exist_ok=True)
            os.makedirs(merged, exist_ok=True)
            lowerdir = ':'.join(lowers)
            subprocess.check_call(['mount', '-t', 'overlay', 'overlay', '-o', f'lowerdir={{lowerdir}},upperdir={{upper}},workdir={{work}}', merged])

        def unmount(path):
            subprocess.call(['umount', path])

        def copy_into(src, dest_root):
            if src.is_dir():
                target = dest_root
                target.mkdir(parents=True, exist_ok=True)
                for child in src.iterdir():
                    dst = target / child.name
                    if child.is_dir():
                        shutil.copytree(child, dst, symlinks=True, dirs_exist_ok=True)
                    else:
                        if child.is_symlink():
                            if dst.exists() or dst.is_symlink():
                                dst.unlink()
                            os.symlink(os.readlink(child), dst)
                        else:
                            shutil.copy2(child, dst)
            else:
                dest_root.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest_root)

        for idx, step in enumerate(plan):
            name = step['name']
            payload = step.get('payload') or {{}}
            upper = f'/run/afterglow-dockerfile/upper-{{idx}}'
            work = f'/run/afterglow-dockerfile/work-{{idx}}'
            merged = f'/run/afterglow-dockerfile/merged-{{idx}}'
            instr = step['instruction']
            if instr == 'ENV':
                env.update(payload.get('env') or {{}})
                os.makedirs(os.path.join(upper, 'etc/afterglow'), exist_ok=True)
                os.makedirs(os.path.join(upper, 'etc/profile.d'), exist_ok=True)
                Path(os.path.join(upper, 'etc/afterglow/dockerfile-env.json')).write_text(json.dumps(env, ensure_ascii=False, sort_keys=True))
                with open(os.path.join(upper, 'etc/profile.d/afterglow-docker-env.sh'), 'w') as fh:
                    for key, value in sorted(env.items()):
                        fh.write(f'export {{key}}={{shlex.quote(str(value))}}\\n')
            elif instr == 'WORKDIR':
                workdir = payload['workdir']
                target = os.path.join(upper, workdir.lstrip('/'))
                os.makedirs(target, exist_ok=True)
                os.makedirs(os.path.join(upper, 'etc/afterglow'), exist_ok=True)
                Path(os.path.join(upper, 'etc/afterglow/dockerfile-workdir')).write_text(workdir + '\\n')
            elif instr == 'RUN':
                mount_overlay(upper, work, merged)
                try:
                    wd = os.path.join(merged, workdir.lstrip('/'))
                    os.makedirs(wd, exist_ok=True)
                    cmd = payload['command']
                    env_prefix = ' '.join(f"{{k}}={{shlex.quote(str(v))}}" for k, v in sorted(env.items()))
                    subprocess.check_call(['chroot', merged, '/bin/bash', '-lc', f'cd {{shlex.quote(workdir)}} && {{env_prefix}} {{cmd}}'])
                finally:
                    unmount(merged)
            elif instr in ('COPY', 'ADD'):
                mount_overlay(upper, work, merged)
                try:
                    dest = payload['dest']
                    sources = payload['sources']
                    dest_path = Path(merged) / dest.lstrip('/')
                    multi = len(sources) > 1 or str(dest).endswith('/')
                    for src in sources:
                        src_path = safe_context(src)
                        target = dest_path / src_path.name if multi else dest_path
                        copy_into(src_path, target)
                finally:
                    unmount(merged)
            else:
                raise SystemExit(f'unsupported instruction reached executor: {{instr}}')
            out_dir = f'/mnt/afterglow-import/out/{{idx}}/images'
            os.makedirs(out_dir, exist_ok=True)
            subprocess.check_call(['mksquashfs', upper, f'{{out_dir}}/{{name}}-latest.sqsh', '-noappend'])
            sqsh_mount = f'/run/afterglow-dockerfile/lower-{{idx}}'
            os.makedirs(sqsh_mount, exist_ok=True)
            subprocess.check_call(['mount', '-o', 'loop,ro', f'{{out_dir}}/{{name}}-latest.sqsh', sqsh_mount])
            lowers.insert(0, sqsh_mount)
        PY
        python3 /usr/local/bin/afterglow-dockerfile-step.py
        echo "::AFTERGLOW::SUCCESS::${{AFTERGLOW_BUILD_TOKEN}}"
        shutdown -h now
        """
    ).strip()


def _dockerfile_cloud_config(job: LayerImportJob, exports: list[str], token: str) -> str:
    script = _dockerfile_cloud_init_script(job, exports, token)
    packages = "\n".join(f"  - {pkg}" for pkg in LAYER_BUILD_IMAGE_PACKAGES)
    encoded = base64.b64encode(script.encode()).decode()
    return f"""#cloud-config
package_update: true
packages:
{packages}
write_files:
  - path: /usr/local/bin/afterglow-dockerfile-import.sh
    permissions: '0755'
    encoding: b64
    content: {encoded}
runcmd:
  - [ bash, /usr/local/bin/afterglow-dockerfile-import.sh ]
"""


async def run_dockerfile_import_job(import_id: int) -> None:
    """Run a Dockerfile import job with one builder VM and normal layer artifact rows."""
    factory = get_session_factory()
    if factory is None:
        return
    conn = None
    port_id: str | None = None
    server_id: str | None = None
    share_ids: list[str] = []
    rw_access_rules: list[tuple[str, str]] = []
    build_ids: list[int] = []
    artifact_ids: list[int] = []
    try:
        async with factory() as session:
            job = await session.get(LayerImportJob, import_id)
            if job is None:
                return
            resource_snapshot = job.resource_snapshot or {}
            service_project = resource_snapshot.get("openstack.service_project") or {}
            builder_flavor = resource_snapshot.get("builder.flavor") or {}
            builder_network = resource_snapshot.get("builder.network") or {}
            manila_snapshot = resource_snapshot.get("manila") or {}
            if not all(
                (
                    service_project.get("id"),
                    builder_flavor.get("id"),
                    builder_network.get("id"),
                    manila_snapshot.get("share_network_id"),
                    manila_snapshot.get("share_type"),
                    manila_snapshot.get("share_size_gb"),
                )
            ):
                raise DockerfileImportError("import resource snapshot is incomplete")
            await _update_job(import_id, status="validating", progress_step="빌드 레코드 생성", progress_pct=5)
            parent_id = None
            for step in job.planned_layers or []:
                build = LayerBuild(
                    layer_name=step["name"],
                    kind="dockerfile",
                    python_version=None,
                    pip_packages=[],
                    apt_packages=[],
                    parent_artifact_id=parent_id,
                    share_id="",
                    builder_flavor_id=builder_flavor["id"],
                    builder_network_id=builder_network["id"],
                    resource_snapshot=resource_snapshot,
                    status="queued",
                    cloud_init_status="queued",
                    progress_step="Dockerfile import 대기",
                    progress_pct=0,
                    ubuntu_base=job.ubuntu_base,
                    base_image_id=job.base_image_id,
                    base_image_name=job.base_image_name,
                    base_image_checksum=job.base_image_checksum,
                    base_image_os_hash_algo=job.base_image_os_hash_algo,
                    base_image_os_hash_value=job.base_image_os_hash_value,
                    base_image_min_disk=job.base_image_min_disk,
                    source_metadata=step.get("source_metadata"),
                )
                session.add(build)
                await session.flush()
                build_ids.append(build.id)
                parent_id = None
            job.build_ids = build_ids
            await session.commit()
        from app.services.keystone import get_admin_connection_for_project

        conn = await asyncio.to_thread(get_admin_connection_for_project, service_project["id"])
        flavor_id = builder_flavor["id"]
        network_id = builder_network["id"]
        token = uuid.uuid4().hex
        port = await asyncio.to_thread(neutron.create_port, conn, network_id, f"afterglow-layer-import-{token[:8]}")
        port_id = port["id"]
        fixed_ip = port["fixed_ip"]
        await _update_job(import_id, status="creating_vm", progress_step="share/VM 생성", progress_pct=15)
        async with factory() as session:
            job = await session.get(LayerImportJob, import_id)
            if job is None:
                return
            for index, step in enumerate(job.planned_layers or []):
                share_name = f"afterglow-layer-{step['name']}-{token[:8]}"
                share = await asyncio.to_thread(
                    manila.create_file_storage,
                    conn,
                    share_name,
                    manila_snapshot["share_size_gb"],
                    manila_snapshot["share_network_id"],
                    manila_snapshot["share_type"],
                    "NFS",
                    {"afterglow_role": "dockerfile-layer", "afterglow_layer_name": step["name"]},
                )
                share_ids.append(share.id)
                rule = await asyncio.to_thread(
                    manila.ensure_nfs_access_rule, conn, share.id, fixed_ip, "rw", root_squash=False, sec_flavor="sys"
                )
                rw_access_rules.append((share.id, rule["access_id"]))
                build = await session.get(LayerBuild, build_ids[index])
                if build is not None:
                    build.share_id = share.id
                    build.status = "creating_vm"
                    build.progress_pct = 15
            await session.commit()
        export_lists = [await asyncio.to_thread(manila.get_export_locations, conn, share_id) for share_id in share_ids]
        exports = [items[0] for items in export_lists if items]
        if len(exports) != len(share_ids):
            raise DockerfileImportError("import share export location을 찾을 수 없습니다")
        user_data = _dockerfile_cloud_config(job, exports, token)
        server = await asyncio.to_thread(
            conn.compute.create_server,
            name=f"afterglow-layer-import-{job.layer_prefix}-{token[:8]}",
            image_id=job.base_image_id,
            flavor_id=flavor_id,
            networks=[{"port": port_id}],
            user_data=base64.b64encode(user_data.encode()).decode(),
            metadata={
                "union_type": "dockerfile-layer-import",
                "afterglow_managed": "true",
                "import_id": str(import_id),
            },
        )
        server_id = server.id
        await _update_job(import_id, status="running", progress_step="Dockerfile import 실행 중", progress_pct=35)
        for build_id in build_ids:
            await _set_build_running(build_id, server_id, port_id, token)
        early_success, early_failure = await _wait_for_shutoff(conn, server_id, None, token)
        console = await asyncio.to_thread(nova.get_console_output, conn, server_id, 500)
        if early_failure or f"::AFTERGLOW::FAILURE::{token}" in console:
            raise DockerfileImportError("Dockerfile import cloud-init 실패")
        if not (early_success or f"::AFTERGLOW::SUCCESS::{token}" in console):
            raise DockerfileImportError("Dockerfile import success sentinel을 찾을 수 없습니다")
        for share_id, access_id in rw_access_rules:
            await asyncio.to_thread(manila.revoke_access_rule, conn, share_id, access_id)
        rw_access_rules.clear()

        async with factory() as session:
            job = await session.get(LayerImportJob, import_id)
            if job is None:
                return
            # 캐시로 재사용한 접두부(또는 `FROM palimpsest/…` 의 부모)에서 이어 쌓는다.
            # 재사용분은 plan 단계에서 planned_layers 에서 제거됐고 job.artifact_ids 에 들어 있다.
            reused_ids = list(job.artifact_ids or [])
            parent_artifact_id: int | None = reused_ids[-1] if reused_ids else None
            layer_names: list[str] = []
            for reused_id in reused_ids:
                reused = await session.get(LayerArtifact, reused_id)
                if reused is not None:
                    layer_names.append(reused.name)
            artifact_ids = list(reused_ids)
            # 한 번의 VM 실행이 여러 레이어를 만든다 — sentinel 은 레이어 이름으로 매핑한다
            # (콘솔이 잘리면 위치 기반 매핑은 조용히 어긋난다). docs/palimpsest.md §3.
            digest_reports = parse_digest_sentinels(console)
            for index, step in enumerate(job.planned_layers or []):
                digest_report = digest_reports.get(step["name"])
                digest_fields = await resolve_digest_fields(
                    session,
                    report=digest_report,
                    parent_artifact_id=parent_artifact_id,
                    name=step["name"],
                    kind="dockerfile",
                    ubuntu_base=job.ubuntu_base,
                    python_version=None,
                    pip_packages=[],
                    apt_packages=[],
                )
                artifact = LayerArtifact(
                    name=step["name"],
                    kind="dockerfile",
                    python_version=None,
                    pip_packages=[],
                    apt_packages=[],
                    ubuntu_base=job.ubuntu_base,
                    sqsh_filename=f"{step['name']}-latest.sqsh",
                    share_id=share_ids[index],
                    build_id=build_ids[index],
                    parent_id=parent_artifact_id,
                    is_sealed=True,
                    size_bytes=digest_report.size_bytes if digest_report else None,
                    # 빌드 캐시 키 — 다음 요청이 같은 부모 위에 같은 명령을 주면 재사용된다
                    step_digest=step.get("step_digest"),
                    **digest_fields,
                    base_image_id=job.base_image_id,
                    base_image_name=job.base_image_name,
                    base_image_checksum=job.base_image_checksum,
                    base_image_os_hash_algo=job.base_image_os_hash_algo,
                    base_image_os_hash_value=job.base_image_os_hash_value,
                    base_image_min_disk=job.base_image_min_disk,
                    source_metadata=step.get("source_metadata"),
                )
                session.add(artifact)
                await session.flush()
                artifact_ids.append(artifact.id)
                parent_artifact_id = artifact.id
                layer_names.append(step["name"])
                build = await session.get(LayerBuild, build_ids[index])
                if build is not None:
                    build.status = "complete"
                    build.cloud_init_status = "success"
                    build.progress_step = "빌드 완료"
                    build.progress_pct = 100
                    build.completed_at = _now()
            profile = (
                await session.execute(
                    __import__("sqlalchemy").select(LayerProfile).where(LayerProfile.name == job.profile_name)
                )
            ).scalar_one_or_none()
            if profile is None:
                profile = LayerProfile(name=job.profile_name, layers=layer_names)
                session.add(profile)
            else:
                profile.layers = layer_names
            job.status = "complete"
            job.progress_step = "완료"
            job.progress_pct = 100
            job.artifact_ids = artifact_ids
            job.completed_at = _now()
            await session.commit()
        # artifact/profile 이 실제로 생긴 지점에서 레이어 캐시를 무효화한다.
        # 요청 핸들러가 아니라 여기가 맞다 — 핸들러는 잡만 만들고 산출물은 여기서 나온다.
        try:
            from app.services.cache import invalidate

            await invalidate("afterglow:union_layer:*")
        except Exception:
            _logger.warning("[dockerfile_import] 레이어 캐시 무효화 실패 (빌드는 성공)", exc_info=True)
    except Exception as exc:
        await _update_job(import_id, status="error", progress_step="실패", error_message=str(exc)[:1000])
        for build_id in build_ids:
            await _set_build_error(build_id, str(exc))
        if conn is not None:
            for share_id, access_id in rw_access_rules:
                try:
                    await asyncio.to_thread(manila.revoke_access_rule, conn, share_id, access_id)
                except Exception:
                    pass
            for share_id in share_ids:
                try:
                    await asyncio.to_thread(manila.delete_file_storage, conn, share_id)
                except Exception:
                    pass
            if server_id:
                try:
                    await asyncio.to_thread(conn.compute.delete_server, server_id)
                except Exception:
                    pass
            if port_id:
                try:
                    await asyncio.to_thread(neutron.delete_port, conn, port_id)
                except Exception:
                    pass
    finally:
        if conn is not None:
            try:
                await asyncio.to_thread(conn.close)
            except Exception:
                _logger.warning("[dockerfile_import] service connection close failed", exc_info=True)


async def _set_build_running(build_id: int, server_id: str, port_id: str, token: str) -> None:
    factory = get_session_factory()
    if factory is None:
        return
    async with factory() as session:
        build = await session.get(LayerBuild, build_id)
        if build is not None:
            build.server_id = server_id
            build.port_id = port_id
            build.build_token = token
            build.status = "building"
            build.cloud_init_status = "booting"
            build.progress_step = "Dockerfile import 실행 중"
            build.progress_pct = 35
        await session.commit()


async def _set_build_error(build_id: int, message: str) -> None:
    factory = get_session_factory()
    if factory is None:
        return
    async with factory() as session:
        build = await session.get(LayerBuild, build_id)
        if build is not None:
            build.status = "error"
            build.cloud_init_status = "failure"
            build.progress_step = "Dockerfile import 실패"
            build.error_message = message[:1000]
            build.completed_at = _now()
        await session.commit()
