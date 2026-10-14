"""GitHub Dockerfile → squashfs layer import workflow."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import logging
import posixpath
import re
import shlex
import tarfile
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any

from openstack.exceptions import ResourceNotFound
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.database import get_session_factory
from app.models.db import LayerArtifact, LayerBuild, LayerImportJob, LayerProfile
from app.services import build_work, manila, neutron, nova
from app.services.layer_base_images import (
    FROM_REF_RE,
    list_base_images,
    resolve_from_reference,
    resolve_glance_base_snapshot,
)
from app.services.layer_build import _SHUTOFF_MAX_WAIT, _SHUTOFF_POLL_INTERVAL, LAYER_BUILD_IMAGE_PACKAGES
from app.services.palimpsest_kvm import MAX_LAYER_DISKS
from app.services.palimpsest_layers import load_lineage, resolve_digest_fields
from app.services.recipe_blocks import _NFS_EXPORT_RE

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
    parent_name: str | None = None


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
    parent_name: str | None = None

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
    try:
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r|gz") as archive:
            unpacked_bytes = 0
            for index, member in enumerate(archive, start=1):
                if index > _MAX_ARCHIVE_FILES:
                    raise DockerfileImportError("GitHub archive 파일 수는 5000개 이하여야 합니다")
                parts = PurePosixPath(member.name).parts
                if ".." in parts or member.name.startswith("/"):
                    raise DockerfileImportError("archive에 안전하지 않은 경로가 있습니다")
                if not (member.isfile() or member.isdir()):
                    raise DockerfileImportError("archive에는 일반 파일과 디렉터리만 허용됩니다")
                if member.isfile():
                    unpacked_bytes += member.size
                    if unpacked_bytes > 512 * 1024 * 1024:
                        raise DockerfileImportError("압축 해제된 GitHub archive는 512MiB 이하여야 합니다")
    except (tarfile.TarError, EOFError, OSError) as exc:
        raise DockerfileImportError("GitHub archive 형식이 손상되었거나 유효하지 않습니다") from exc


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


def _parse_copy_add(instruction: str, args: str, line: int, workdir: str = "/") -> dict:
    try:
        parts = shlex.split(args)
    except ValueError as exc:
        raise _line_error(line, f"{instruction} 구문을 파싱할 수 없습니다") from exc
    if len(parts) < 2:
        raise _line_error(line, f"{instruction}에는 source와 destination이 필요합니다")
    if any(part.startswith("--") for part in parts):
        raise _line_error(line, f"{instruction} flags는 지원하지 않습니다")
    sources = parts[:-1]
    raw_dest = _validate_container_path(parts[-1], line, dest=True)
    dest = posixpath.normpath(posixpath.join(workdir, raw_dest))
    if raw_dest.endswith("/") or raw_dest in {".", "./"}:
        dest += "/"
    for src in sources:
        if src.startswith(("http://", "https://")):
            raise _line_error(line, f"{instruction} remote URL은 지원하지 않습니다")
        if instruction == "ADD" and src.lower().endswith(_ARCHIVE_EXTENSIONS):
            raise _line_error(line, "ADD archive 자동 추출은 지원하지 않습니다")
        _validate_container_path(src, line)
    return {"sources": sources, "dest": dest, "raw_dest": raw_dest}


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
    initial_env: dict[str, str] | None = None,
    initial_workdir: str = "/",
) -> tuple[ParsedDockerfile | None, list[DockerfileImportError]]:
    """Parse once for lint and build; recover after independent instruction errors."""
    prefix = validate_layer_name(layer_prefix, field="layer_prefix")
    validate_layer_name(profile_name or layer_prefix, field="profile_name")
    from_ref: str | None = None
    parent_digest: str | None = None
    parent_name: str | None = None
    from_line: int | None = None
    seen_from = False
    planned: list[dict] = []
    diagnostics: list[DockerfileImportError] = []
    env: dict[str, str] = dict(initial_env or {})
    workdir = posixpath.normpath(initial_workdir) if initial_workdir and initial_workdir.startswith("/") else "/"
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
                    parent_name = palimpsest_match.group(1)
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
                payload = _parse_copy_add(instruction, args, line, workdir)
            elif instruction == "ENV":
                updates = _parse_env(args, line)
                env.update(updates)
                payload = {"env": updates, "full_env": dict(env), "workdir": workdir}
            elif instruction == "WORKDIR":
                raw_workdir = _validate_container_path(args, line, dest=True)
                workdir = posixpath.normpath(posixpath.join(workdir, raw_workdir))
                payload = {"workdir": workdir, "raw_workdir": raw_workdir, "full_env": dict(env)}
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
                        "dockerfile_args": args,
                        "dockerfile_env": dict(env),
                        "dockerfile_workdir": workdir,
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
        from_ref=from_ref,
        parent_digest=parent_digest,
        from_line=from_line,
        planned_layers=planned,
        parent_name=parent_name,
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
    initial_env: dict[str, str] | None = None,
    initial_workdir: str = "/",
) -> ParsedDockerfile:
    """Parse a build using the same syntax diagnostics as the editor lint."""
    parsed, errors = _parse_dockerfile_with_diagnostics(
        text,
        layer_prefix=layer_prefix,
        profile_name=profile_name,
        commit_sha=commit_sha,
        dockerfile_path=dockerfile_path,
        allow_build_context=allow_build_context,
        initial_env=initial_env,
        initial_workdir=initial_workdir,
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
    """Bind a normalized instruction to its actual parent chain and executor format.

    The executor format changes when emitted guest bytes change: older sealed
    artifacts remain valid but cannot be mistaken for new cache results.
    """
    normalized = f"{instruction.upper()} {' '.join(args.split())}"
    payload = f"dockerfile-full-root-v2\n{parent_ref}\n{normalized}".encode()
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
            parent = await resolve_parent_layer(parsed.parent_digest, name=parsed.parent_name)
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
    base_snapshot = {} if parsed.parent_digest else resolve_dockerfile_base_image(conn, parsed)
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
        parent_digest=parsed.parent_digest,
        parent_name=parsed.parent_name,
        dockerfile_digest="sha256:" + hashlib.sha256(dockerfile.encode("utf-8")).hexdigest(),
    )


async def _recover_lineage_state(root: Any) -> tuple[dict[str, str], str, list[int]]:
    """Recover cumulative ENV and WORKDIR across a sealed parent lineage (root-first)."""
    if root is None:
        return {}, "/", []
    lineage = [root]
    if isinstance(getattr(root, "parent_id", None), int) and (factory := get_session_factory()) is not None:
        async with factory() as session:
            lineage = await load_lineage(session, root)
    env: dict[str, str] = {}
    workdir = "/"
    lineage_ids: list[int] = []
    for row in reversed(lineage):
        row_id = getattr(row, "id", None)
        if isinstance(row_id, int):
            lineage_ids.append(row_id)
        meta = getattr(row, "source_metadata", None)
        if not isinstance(meta, dict):
            meta = {}
        if isinstance(meta.get("dockerfile_env"), dict):
            env.update({str(k): str(v) for k, v in meta["dockerfile_env"].items()})
        elif isinstance(meta.get("full_env"), dict):
            env.update({str(k): str(v) for k, v in meta["full_env"].items()})
        elif isinstance(meta.get("env"), dict):
            env.update({str(k): str(v) for k, v in meta["env"].items()})
        elif meta.get("dockerfile_instruction") == "ENV" and isinstance(meta.get("dockerfile_args"), str):
            env.update(_parse_env(meta["dockerfile_args"], int(meta.get("dockerfile_line") or 1)))
        if isinstance(meta.get("dockerfile_workdir"), str) and meta["dockerfile_workdir"].strip():
            workdir = posixpath.normpath(meta["dockerfile_workdir"].strip())
        elif isinstance(meta.get("workdir"), str) and meta["workdir"].strip():
            workdir = posixpath.normpath(meta["workdir"].strip())
        elif meta.get("dockerfile_instruction") == "WORKDIR" and isinstance(meta.get("dockerfile_args"), str):
            workdir = posixpath.normpath(posixpath.join(workdir, meta["dockerfile_args"].strip()))
    if not lineage_ids and getattr(root, "id", None) is not None:
        lineage_ids = [root.id]
    return env, workdir, lineage_ids


def _apply_inherited_state(
    planned_layers: list[dict], *, initial_env: dict[str, str], initial_workdir: str
) -> list[dict]:
    env = dict(initial_env)
    workdir = posixpath.normpath(initial_workdir) if initial_workdir and initial_workdir.startswith("/") else "/"
    resolved: list[dict] = []
    for raw_step in planned_layers:
        step = dict(raw_step)
        instr = step["instruction"]
        payload = dict(step.get("payload") or {})
        if instr == "ENV":
            updates = dict(payload.get("env") or _parse_env(step["args"], int(step.get("line") or 1)))
            env.update(updates)
            payload = {"env": updates, "full_env": dict(env), "workdir": workdir}
        elif instr == "WORKDIR":
            raw_wd = payload.get("raw_workdir") or step["args"].strip()
            workdir = posixpath.normpath(posixpath.join(workdir, raw_wd))
            payload = {"workdir": workdir, "raw_workdir": raw_wd, "full_env": dict(env)}
        elif instr == "RUN":
            payload = {"command": payload.get("command", step["args"]), "env": dict(env), "workdir": workdir}
        elif instr in {"COPY", "ADD"}:
            raw_dest = payload.get("raw_dest")
            if raw_dest:
                dest = posixpath.normpath(posixpath.join(workdir, raw_dest))
                if raw_dest.endswith("/") or raw_dest in {".", "./"}:
                    dest += "/"
                payload["dest"] = dest
            payload["workdir"] = workdir
            payload["full_env"] = dict(env)
        step["payload"] = payload
        step["source_metadata"] = {
            **(step.get("source_metadata") or {}),
            "dockerfile_args": step["args"],
            "dockerfile_env": dict(env),
            "dockerfile_workdir": workdir,
        }
        resolved.append(step)
    return resolved


async def finalize_dockerfile_plan(plan: DockerfilePlan, *, parent: LayerArtifact | None = None) -> DockerfilePlan:
    """Both source types share the same sealed-root lineage and cache lookup."""
    if parent is None and plan.parent_digest:
        parent = await resolve_parent_layer(plan.parent_digest, name=plan.parent_name)
    root = parent or await find_cached_root(plan.base_image_snapshot)
    inherited_env, inherited_workdir, root_lineage_ids = await _recover_lineage_state(root)
    resolved_layers = _apply_inherited_state(
        plan.planned_layers, initial_env=inherited_env, initial_workdir=inherited_workdir
    )
    resolved_by_name = {step["name"]: step for step in resolved_layers}
    annotated = await apply_build_cache(resolved_layers, root_ref=root.chain_id if root else None)
    cached_ids, planned = split_cached_prefix(annotated)
    if root_lineage_ids:
        cached_ids = root_lineage_ids + cached_ids
    for step in planned:
        fallback = resolved_by_name.get(step.get("name"), {})
        if not step.get("payload") and fallback.get("payload"):
            step["payload"] = dict(fallback["payload"])
        step["source_metadata"] = {
            **(fallback.get("source_metadata") or {}),
            **(step.get("source_metadata") or {}),
            "dockerfile_digest": plan.dockerfile_digest,
            "source_type": plan.source_type,
        }
    return replace(plan, planned_layers=planned, cached_artifact_ids=cached_ids)


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
        parent = await resolve_parent_layer(parsed.parent_digest, name=parsed.parent_name)
        base_snapshot = _snapshot_from_artifact(parent)
    else:
        base_snapshot = await asyncio.to_thread(resolve_dockerfile_base_image, conn, parsed)
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    return await finalize_dockerfile_plan(
        DockerfilePlan(
            github_url=None,
            repo_owner=None,
            repo_name=None,
            commit_sha=None,
            dockerfile_path=None,
            layer_prefix=prefix,
            profile_name=profile,
            base_image_snapshot=base_snapshot,
            planned_layers=parsed.planned_layers,
            dockerfile_text=dockerfile_text,
            dockerfile_digest=digest,
            parent_digest=parsed.parent_digest,
            parent_name=parsed.parent_name,
            source_type=SOURCE_INLINE,
        ),
        parent=parent,
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


async def _rooted_lineage(session, artifact: LayerArtifact, base_image_id: str | None = None) -> list[LayerArtifact]:
    """Only sealed and digested full-root chains are safe Dockerfile cache inputs."""
    lineage = await load_lineage(session, artifact)
    if not lineage or lineage[-1].kind != "dockerfile-root" or lineage[-1].parent_id is not None:
        return []
    image_id = base_image_id or artifact.base_image_id
    if not image_id or any(
        row.base_image_id != image_id
        or not row.is_sealed
        or row.digest_state != "ready"
        or not row.blob_digest
        or not row.chain_id
        or not row.share_id
        or not row.sqsh_filename
        for row in lineage
    ):
        return []
    if any(row.kind != "dockerfile" for row in lineage[:-1]):
        return []
    return lineage


async def find_cached_root(base_snapshot: dict) -> LayerArtifact | None:
    from sqlalchemy import select

    factory = get_session_factory()
    if factory is None:
        raise DockerfileImportError("DB가 초기화되지 않았습니다")
    async with factory() as session:
        candidates = (
            await session.execute(
                select(LayerArtifact)
                .where(LayerArtifact.kind == "dockerfile-root")
                .where(LayerArtifact.base_image_id == base_snapshot["base_image_id"])
                .where(LayerArtifact.is_sealed.is_(True))
                .order_by(LayerArtifact.id.desc())
                .limit(10)
            )
        ).scalars()
        for row in candidates:
            if (
                row.base_image_checksum == base_snapshot.get("base_image_checksum")
                and row.base_image_os_hash_algo == base_snapshot.get("base_image_os_hash_algo")
                and row.base_image_os_hash_value == base_snapshot.get("base_image_os_hash_value")
                and await _rooted_lineage(session, row, base_snapshot["base_image_id"])
            ):
                return row
    return None


async def resolve_parent_layer(parent_digest: str, *, name: str | None = None) -> LayerArtifact:
    """Resolve an exact named, sealed parent with a complete full-root lineage."""
    from sqlalchemy import select

    factory = get_session_factory()
    if factory is None:
        raise DockerfileImportError("DB가 초기화되지 않았습니다")
    async with factory() as session:
        query = select(LayerArtifact).where(LayerArtifact.blob_digest == parent_digest)
        if name is not None:
            query = query.where(LayerArtifact.name == name)
        candidates = (await session.execute(query.order_by(LayerArtifact.id.desc()))).scalars()
        for row in candidates:
            if await _rooted_lineage(session, row):
                return row
    raise DockerfileImportError(f"FROM 레이어 {name or ''}@{parent_digest}의 봉인된 전체 루트 계보를 찾을 수 없습니다")


async def apply_build_cache(planned: list[dict], *, root_ref: str | None) -> list[dict]:
    """Reuse only a contiguous prefix in a verified full-root chain."""
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
            args_for_key = step["args"]
            if step["instruction"] in {"COPY", "ADD"}:
                args_for_key += "\ncommit:" + (step.get("source_metadata") or {}).get("commit_sha", "")
            step_digest = compute_step_digest(parent_ref, step["instruction"], args_for_key) if parent_ref else None
            entry = dict(step, step_digest=step_digest, cached=False, reuse_artifact_id=None)
            if cache_live and step_digest:
                hit = (
                    await session.execute(
                        select(LayerArtifact)
                        .where(LayerArtifact.step_digest == step_digest)
                        .where(LayerArtifact.is_sealed.is_(True))
                        .order_by(LayerArtifact.id.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                expected_base_id = None
                if hit is not None and await _rooted_lineage(session, hit, expected_base_id):
                    entry["cached"] = True
                    entry["reuse_artifact_id"] = hit.id
                    parent_ref = hit.chain_id
                    annotated.append(entry)
                    continue
                cache_live = False
            # Until the new parent's content digest exists the next cache key is unknown.
            parent_ref = None
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


IMMEDIATE_BLOCK_IMPORT_GUIDANCE = (
    "Immediate block import is unsupported. Seal the Dockerfile import first, publish the exact sealed "
    "SquashFS bytes for every artifact, then consume with transport=block using that exact import_id. "
    "Provider image/volume IDs are not consume inputs; no fallback is available."
)


def _job_to_dict(job: LayerImportJob, consumer_status: str | None = None) -> dict:
    return {
        "id": job.id,
        "source_type": job.source_type,
        "dockerfile_digest": job.dockerfile_digest,
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
        "resource_snapshot": (
            {key: value for key, value in job.resource_snapshot.items() if key != "build_token"}
            if job.resource_snapshot is not None
            else None
        ),
        "artifact_ids": job.artifact_ids or [],
        "build_ids": job.build_ids or [],
        "consumer_requested": job.consumer_spec is not None,
        "consumer_spec": (
            {
                "server_name": job.consumer_spec["server_name"],
                "flavor_id": job.consumer_spec["flavor_id"],
                "network_id": job.consumer_spec["resource_snapshot"]["network"]["id"],
                "ssh_username": job.consumer_spec["ssh_username"],
            }
            if job.consumer_spec
            else None
        ),
        "consume_id": job.consume_id,
        "consumer_status": consumer_status
        or (
            "error"
            if job.consumer_spec and job.error_message
            else "creating"
            if job.consumer_spec and job.consume_id
            else "queued"
            if job.consumer_spec
            else None
        ),
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


async def create_import_job(plan: DockerfilePlan, *, consumer_spec: dict | None = None) -> dict:
    if consumer_spec and consumer_spec.get("transport") == "block":
        raise DockerfileImportError(IMMEDIATE_BLOCK_IMPORT_GUIDANCE)
    if plan.source_type == SOURCE_GITHUB:
        if plan.parent_digest:
            parent = await resolve_parent_layer(plan.parent_digest, name=plan.parent_name)
            plan = replace(plan, base_image_snapshot=_snapshot_from_artifact(parent))
            plan = await finalize_dockerfile_plan(plan, parent=parent)
        else:
            plan = await finalize_dockerfile_plan(plan)
    factory = get_session_factory()
    if factory is None:
        raise DockerfileImportError("DB가 초기화되지 않았습니다")
    from app.services.resource_policy_store import (
        get_policy_snapshot,
        get_service_project_connection,
        lock_service_project_admission,
        resolve_policy_snapshot,
    )

    if not plan.planned_layers and plan.cached_artifact_ids:
        resource_snapshot = {"base_image": {"id": plan.base_image_snapshot["base_image_id"]}}
    else:
        service_project = (await get_policy_snapshot(("openstack.service_project",)))["openstack.service_project"]
        if service_project is None:
            raise DockerfileImportError("service project policy is not configured")
        service_conn = await get_service_project_connection(service_project["id"])
        try:
            policies = await resolve_policy_snapshot(
                conn=service_conn,
                service_conn=service_conn,
                keys=("builder.flavor", "builder.network", "manila.share_network", "manila.nfs_share_type"),
            )
        finally:
            await build_work.cleanup_sync(service_conn.close)
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
    resource_snapshot["build_token"] = uuid.uuid4().hex
    async with factory() as session:
        if "openstack.service_project" in resource_snapshot:
            await lock_service_project_admission(session, resource_snapshot["openstack.service_project"]["id"])
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
            **_base_fields(plan.base_image_snapshot),
            profile_name=plan.profile_name,
            planned_layers=plan.planned_layers,
            # 캐시 재사용분을 미리 채워 둔다 — 빌드 루프가 여기서 이어 쌓는다.
            artifact_ids=list(plan.cached_artifact_ids),
            build_ids=[],
            resource_snapshot=resource_snapshot,
            consumer_spec=consumer_spec,
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        data = _job_to_dict(job)
    return data


async def list_import_jobs(limit: int = 50) -> list[dict]:
    from sqlalchemy import desc, select

    from app.models.db import LayerConsume

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
        consume_ids = [row.consume_id for row in rows if row.consume_id]
        statuses = {}
        if consume_ids:
            consumes = (await session.execute(select(LayerConsume).where(LayerConsume.id.in_(consume_ids)))).scalars()
            statuses = {row.id: row.status for row in consumes}
        return [_job_to_dict(row, statuses.get(row.consume_id)) for row in rows]


async def get_import_job(import_id: int) -> dict | None:
    from app.models.db import LayerConsume

    factory = get_session_factory()
    if factory is None:
        raise DockerfileImportError("DB가 초기화되지 않았습니다")
    async with factory() as session:
        row = await session.get(LayerImportJob, import_id)
        if row is None:
            return None
        consumer = await session.get(LayerConsume, row.consume_id) if row.consume_id else None
        return _job_to_dict(row, consumer.status if consumer else None)


async def _update_job(job_id: int, **fields) -> None:
    factory = get_session_factory()
    if factory is None:
        return
    async with factory() as session:
        job = await _locked_import(session, job_id)
        if job.status in build_work.TERMINAL:
            raise build_work.DispatcherUnavailable("terminal import cannot be overwritten")
        for key, value in fields.items():
            setattr(job, key, value)
        job.updated_at = _now()
        if fields.get("status") in {"complete", "error", "cancelled"} and job.completed_at is None:
            job.completed_at = _now()
        # The current status is locked above; only execution authority can
        # change while the terminal transition itself remains uncommitted.
        await build_work.current_binding().lease.check()
        await session.commit()


def _dockerfile_cloud_init_script(
    job: LayerImportJob,
    exports: list[list[str]],
    ancestors: list[dict],
    root_name: str | None,
    base_volume_id: str | None,
    token: str,
) -> str:
    """Execute identical plans from inline text or a commit-pinned GitHub context."""
    plan_json = shlex.quote(json.dumps(job.planned_layers or [], ensure_ascii=False))
    config_json = shlex.quote(
        json.dumps(
            {
                "ancestors": ancestors,
                "root_name": root_name,
                "base_volume_id": base_volume_id,
                "context": "/tmp/afterglow-context" if job.source_type == SOURCE_GITHUB else None,
            },
            ensure_ascii=False,
        )
    )
    exports_json = shlex.quote(json.dumps(exports, ensure_ascii=False))
    acquire = ""
    if job.source_type == SOURCE_GITHUB:
        if not all((job.repo_owner, job.repo_name, job.commit_sha, job.dockerfile_path)):
            raise DockerfileImportError("GitHub import source snapshot is incomplete")
        repo = parse_github_url(job.github_url)
        if repo.owner != job.repo_owner or repo.repo != job.repo_name or not _SHA_RE.fullmatch(job.commit_sha):
            raise DockerfileImportError("GitHub import source snapshot is inconsistent")
        archive = shlex.quote(f"https://codeload.github.com/{repo.owner}/{repo.repo}/tar.gz/{job.commit_sha}")
        path = shlex.quote(validate_dockerfile_path(job.dockerfile_path))
        acquire = (
            f"curl -fsSL --proto '=https' --tlsv1.2 {archive} -o /tmp/afterglow-repo.tar.gz\n"
            "mkdir -p /tmp/afterglow-context\n"
            "tar -xzf /tmp/afterglow-repo.tar.gz --no-same-owner -C /tmp/afterglow-context --strip-components=1\n"
            f"test -f /tmp/afterglow-context/{path}\n"
        )
    elif job.source_type != SOURCE_INLINE:
        raise DockerfileImportError("unsupported Dockerfile source")

    return (
        "set -euo pipefail\n"
        'trap \'rc=$?; echo "::AFTERGLOW::FAILURE::${AFTERGLOW_BUILD_TOKEN}::rc=$rc"; { echo "::AFTERGLOW::FAILURE::${AFTERGLOW_BUILD_TOKEN}::rc=$rc" > /dev/console; } 2>/dev/null || :; umount -l /mnt/afterglow-import/out/* /mnt/afterglow-import/in/* 2>/dev/null || :; shutdown -h now\' ERR\n'
        f"export AFTERGLOW_BUILD_TOKEN={shlex.quote(token)}\n"
        "install -d /etc/afterglow /mnt/afterglow-import/out /var/lib/afterglow-dockerfile\n"
        f"printf '%s' {plan_json} > /etc/afterglow/dockerfile-plan.json\n"
        f"printf '%s' {config_json} > /etc/afterglow/dockerfile-config.json\n"
        f"printf '%s' {exports_json} > /etc/afterglow/dockerfile-exports.json\n"
        "python3 - <<'PY'\n"
        "import json, pathlib, subprocess, time\n"
        "exports = json.loads(pathlib.Path('/etc/afterglow/dockerfile-exports.json').read_text())\n"
        "for idx, candidates in enumerate(exports):\n"
        "    mount = pathlib.Path('/mnt/afterglow-import/out') / str(idx)\n"
        "    mount.mkdir(parents=True, exist_ok=True)\n"
        "    deadline = time.monotonic() + 180\n"
        "    mounted = False\n"
        "    for attempt in range(12):\n"
        "        for export in candidates:\n"
        "            remaining = deadline - time.monotonic()\n"
        "            if remaining <= 0:\n"
        "                break\n"
        "            try:\n"
        "                result = subprocess.run(['mount', '-t', 'nfs4', '-o', 'rw,hard', export, str(mount)], timeout=min(15, remaining), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
        "            except (OSError, subprocess.TimeoutExpired):\n"
        "                continue\n"
        "            if result.returncode == 0:\n"
        "                mounted = True\n"
        "                break\n"
        "        if mounted or time.monotonic() >= deadline:\n"
        "            break\n"
        "        if attempt < 11:\n"
        "            time.sleep(min(5, max(0, deadline - time.monotonic())))\n"
        "    if not mounted:\n"
        "        raise RuntimeError('output share mount failed')\n"
        "    (mount / 'images').mkdir(parents=True, exist_ok=True)\n"
        "PY\n"
        + acquire
        + "python3 /usr/local/bin/afterglow-dockerfile-step.py\n"
        + 'echo "::AFTERGLOW::SUCCESS::${AFTERGLOW_BUILD_TOKEN}"; { echo "::AFTERGLOW::SUCCESS::${AFTERGLOW_BUILD_TOKEN}" > /dev/console; } 2>/dev/null || :\n'
        + "shutdown -h now\n"
    )


def _dockerfile_cloud_config(
    job: LayerImportJob,
    exports: list[list[str]],
    ancestors: list[dict],
    root_name: str | None,
    base_volume_id: str | None,
    token: str,
) -> str:
    from pathlib import Path

    script = _dockerfile_cloud_init_script(job, exports, ancestors, root_name, base_volume_id, token)
    packages = "\n".join(f"  - {pkg}" for pkg in LAYER_BUILD_IMAGE_PACKAGES)
    encoded = base64.b64encode(script.encode()).decode()
    guest_executor = base64.b64encode(Path(__file__).with_name("dockerfile_guest.py").read_bytes()).decode()
    return f"""#cloud-config
package_update: true
packages:
{packages}
write_files:
  - path: /usr/local/bin/afterglow-dockerfile-import.sh
    permissions: '0755'
    encoding: b64
    content: {encoded}
  - path: /usr/local/bin/afterglow-dockerfile-step.py
    permissions: '0755'
    encoding: b64
    content: {guest_executor}
runcmd:
  - [ bash, /usr/local/bin/afterglow-dockerfile-import.sh ]
"""


def _parse_dockerfile_manifest(console: str, token: str, names: list[str]) -> dict[str, Any]:
    """A truncated or ambiguous Nova console must never seal partial output."""
    import hmac

    from app.services.palimpsest_digest import DigestReport

    matches = re.findall(r"::AFTERGLOW::MANIFEST::([0-9a-f]{32})::([A-Za-z0-9+/=]+)", console)
    if len(matches) != 1 or not hmac.compare_digest(matches[0][0], token):
        raise DockerfileImportError("builder did not report exactly one authenticated digest manifest")
    try:
        payload = base64.b64decode(matches[0][1], validate=True)
        if len(payload) > 1024 * 1024:
            raise ValueError("manifest exceeds 1MiB")
        records = json.loads(payload)
    except (ValueError, UnicodeError) as exc:
        raise DockerfileImportError("builder digest manifest is malformed") from exc
    if (
        not isinstance(records, list)
        or [row.get("name") if isinstance(row, dict) else None for row in records] != names
    ):
        raise DockerfileImportError("builder digest manifest does not match the complete build plan")
    reports = {}
    for row in records:
        sha256, md5, size = row.get("sha256"), row.get("md5"), row.get("size")
        if (
            not isinstance(sha256, str)
            or not re.fullmatch(r"[0-9a-f]{64}", sha256)
            or not isinstance(md5, str)
            or not re.fullmatch(r"[0-9a-f]{32}", md5)
            or type(size) is not int
            or size <= 0
        ):
            raise DockerfileImportError("builder reported an invalid artifact digest or size")
        reports[row["name"]] = DigestReport(
            layer_name=row["name"], blob_digest="sha256:" + sha256, blob_md5=md5, size_bytes=size
        )
    return reports


async def _wait_for_import_shutdown(conn, server_id: str, build_id: int, token: str) -> tuple[bool, bool]:
    """Observe the existing builder under the import target, not a layer target."""
    state = await build_work.journal_get()
    early_success, early_failure = bool(state.get("early_success")), bool(state.get("early_failure"))
    for waited in range(0, _SHUTOFF_MAX_WAIT, _SHUTOFF_POLL_INTERVAL):
        server = await build_work.run_sync(conn.compute.get_server, server_id)
        if server is None:
            raise DockerfileImportError("import builder is unavailable")
        status = (server.status or "").upper()
        if status in {"SHUTOFF", "ERROR"}:
            return early_success, early_failure
        if status == "ACTIVE" and waited > 60:
            try:
                console = await build_work.run_sync(nova.get_console_output, conn, server_id, 12000)
            except build_work.DispatcherUnavailable:
                raise
            except Exception:
                console = ""
            early_success |= f"::AFTERGLOW::SUCCESS::{token}" in console
            early_failure |= f"::AFTERGLOW::FAILURE::{token}" in console
            await build_work.journal_update(early_success=early_success, early_failure=early_failure)
        async with get_session_factory()() as session:
            import_id = int(build_work.current_binding().member.split(":", 1)[1])
            await _locked_import(session, import_id)
            build = await session.get(LayerBuild, build_id)
            if build is None or build.status in build_work.TERMINAL:
                raise build_work.DispatcherUnavailable("bound import build is terminal")
            build.cloud_init_status = "booting" if waited < 120 else "installing"
            await build_work.checkpoint()
            await session.commit()
        await asyncio.sleep(_SHUTOFF_POLL_INTERVAL)
    raise TimeoutError("Dockerfile builder did not shut down within the build deadline")


async def _read_dockerfile_reports(
    conn,
    server_id: str,
    token: str,
    outputs: list[dict],
    exports: list[list[str]],
    share_ids: list[str],
    snapshot: dict,
    _early_success: bool,
    early_failure: bool,
) -> dict[str, Any]:
    try:
        console = await build_work.run_sync(nova.get_console_output, conn, server_id, None)
    except build_work.DispatcherUnavailable:
        raise
    except Exception:
        _logger.warning("[dockerfile_import] Nova console unavailable; verifying output shares")
        console = ""
    status = await build_work.run_sync(conn.compute.get_server, server_id)
    observed_status = getattr(status, "status", "")
    safe_status = observed_status.upper() if isinstance(observed_status, str) else "UNKNOWN"
    if safe_status not in {"ACTIVE", "BUILD", "ERROR", "HARD_REBOOT", "REBOOT", "SHUTOFF", "SUSPENDED"}:
        safe_status = "UNKNOWN"
    console_failure = f"::AFTERGLOW::FAILURE::{token}" in console
    if safe_status != "SHUTOFF" or early_failure or console_failure:
        raise DockerfileImportError(
            "Dockerfile builder did not shut down successfully "
            f"(status={safe_status}, early_failure={early_failure}, console_failure={console_failure})"
        )
    # A console digest alone cannot prove that the persisted share still holds those bytes.

    from app.services.dockerfile_verify import verify_builder_outputs

    return await verify_builder_outputs(
        conn, token=token, outputs=outputs, exports=exports, share_ids=share_ids, snapshot=snapshot
    )


async def _save_import_profile(session, job: LayerImportJob, artifact_ids: list[int]) -> None:
    from sqlalchemy import select

    if not artifact_ids:
        raise DockerfileImportError("a Dockerfile import needs a sealed full-root artifact")
    final = await session.get(LayerArtifact, artifact_ids[-1])
    lineage = await _rooted_lineage(session, final, job.base_image_id)
    if not lineage:
        raise DockerfileImportError("Dockerfile import produced an incomplete full-root lineage")
    names = [artifact.name for artifact in lineage]
    profile = (
        await session.execute(select(LayerProfile).where(LayerProfile.name == job.profile_name))
    ).scalar_one_or_none()
    if profile is None:
        session.add(LayerProfile(name=job.profile_name, layers=names))
    else:
        profile.layers = names
    job.artifact_ids = [artifact.id for artifact in reversed(lineage)]


async def prepare_import_consumer(conn, request, *, profile_name: str) -> dict:
    """Freeze public SSH key and placement while the authenticated admin request is alive."""
    from app.api.union.layer_ops import LayerConsumeRequest
    from app.services.layer_build import resolve_layer_consume_resource_snapshot

    validated = LayerConsumeRequest(profile_name=profile_name, **request.model_dump(exclude_none=True))
    if validated.transport == "block":
        raise DockerfileImportError(IMMEDIATE_BLOCK_IMPORT_GUIDANCE)
    ssh_public_key = validated.ssh_public_key
    if validated.key_name and not ssh_public_key:
        try:
            keypair = await asyncio.to_thread(conn.compute.get_keypair, validated.key_name)
        except Exception as exc:
            raise DockerfileImportError("selected SSH keypair could not be resolved") from exc
        ssh_public_key = getattr(keypair, "public_key", None)
    if not ssh_public_key:
        raise DockerfileImportError("SSH public key or existing keypair is required to launch a consumer VM")
    snapshot = await resolve_layer_consume_resource_snapshot(
        conn, flavor_ref=validated.flavor_id, network_id=validated.network_id
    )
    return {
        "server_name": validated.server_name,
        "flavor_id": validated.flavor_id,
        "transport": validated.transport,
        "ssh_public_key": ssh_public_key,
        "ssh_username": validated.ssh_username,
        "resource_snapshot": snapshot,
    }


async def _locked_import(session, import_id: int):
    """Read current SQL authority under a row lock, never a detached status snapshot."""
    from sqlalchemy import select

    await build_work.checkpoint()
    job = (
        await session.execute(
            select(LayerImportJob)
            .where(LayerImportJob.id == import_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    binding = build_work.current_binding()
    if binding.member != f"import:{import_id}":
        raise build_work.DispatcherUnavailable("import does not match the owned target")
    if job is None or (job.status in build_work.TERMINAL and not (binding.allow_complete and job.status == "complete")):
        raise build_work.DispatcherUnavailable("import is no longer runnable")
    return job


async def _launch_import_consumer(import_id: int) -> None:
    from app.models.db import LayerConsume
    from app.services.layer_build import run_layer_consume

    factory = get_session_factory()
    async with factory() as session:
        job = await _locked_import(session, import_id)
        spec = job.consumer_spec
        if not spec:
            return
        if not job.artifact_ids:
            raise DockerfileImportError("cannot create a VM before sealing its full-root artifact")
        # Parent row lock serializes consumer admission; handoff reuses its
        # existing allocation ledger, never a second consume row or CREATE.
        row = await session.get(LayerConsume, job.consume_id) if job.consume_id else None
        if job.consume_id and row is None:
            raise DockerfileImportError("import consumer binding is missing")
        if row is None:
            row = LayerConsume(
                profile_name=job.profile_name,
                server_name=spec["server_name"],
                transport=spec.get("transport", "nfs"),
                project_id=spec["resource_snapshot"]["openstack.service_project"]["id"],
                artifact_ids=list(job.artifact_ids),
                resource_snapshot=spec["resource_snapshot"],
                status="creating",
                share_id="",
            )
            session.add(row)
            await build_work.checkpoint()
            await session.flush()
            job.consume_id = row.id
        consume_id = row.id
        profile_name, base_image_id = job.profile_name, job.base_image_id
        artifact_ids = list(job.artifact_ids)
        consumer_status = row.status
        terminal = consumer_status in {"active", "error", "deleted", "cancelled"}
        job.progress_step = "전체 루트 SSH VM 활성화 중"
        await build_work.checkpoint()
        await session.commit()
    await build_work.journal_update(consume_id=consume_id)
    if not terminal:
        await build_work.checkpoint()
        try:
            await run_layer_consume(
                consume_db_id=consume_id,
                profile_name=profile_name,
                server_name=spec["server_name"],
                flavor_id=spec["flavor_id"],
                transport=spec.get("transport", "nfs"),
                image_id=base_image_id,
                ssh_public_key=spec["ssh_public_key"],
                ssh_username=spec["ssh_username"],
                resource_snapshot=spec["resource_snapshot"],
                artifact_ids=artifact_ids,
            )
        except (build_work.DispatcherUnavailable, build_work.SubmissionUnknown, SQLAlchemyError):
            raise
        except Exception as exc:
            # Sealed output survives a definite consumer failure, but only the
            # re-read SQL row may finish the import: a row left nonterminal
            # (for example, failed disposal) stays runnable for the next owner.
            _logger.warning("[dockerfile_import] import %s optional consumer failed: %s", import_id, type(exc).__name__)
        async with factory() as session:
            await _locked_import(session, import_id)
            row = await session.get(LayerConsume, consume_id, populate_existing=True)
            consumer_status = row.status if row is not None else None
    if consumer_status not in {"active", "error", "deleted", "cancelled"}:
        raise build_work.SubmissionUnknown("import consumer awaits reconciliation")
    await build_work.journal_update(consumer_done=True, consumer_status=consumer_status)
    if consumer_status != "active":
        await _update_job(
            import_id, error_message="Optional consumer launch failed; sealed artifacts remain consumable by import_id"
        )


async def _accepted_id(step: str, existing: str | None = None, *, observe=None, allow_rejected=False) -> str | None:
    """SQL resource IDs outrank a journal; ambiguous CREATE is never replayed."""
    submission = await build_work.submission_get(step)
    if existing:
        return existing
    if submission is None:
        return None
    if submission["state"] == "rejected":
        if allow_rejected:
            return None
        raise DockerfileImportError(f"{step} was definitively rejected")
    if submission["state"] != "accepted":
        if observe is not None:
            identity = await build_work.run_sync(observe)
            if identity:
                return identity
        raise build_work.SubmissionUnknown(f"{step} awaits provider reconciliation")
    result = submission.get("result")
    identity = result.get("id") if isinstance(result, dict) else result
    if not identity:
        raise build_work.SubmissionUnknown(f"{step} has no accepted resource identity")
    return identity


def _resource_field(resource, field, default=None):
    return resource.get(field, default) if isinstance(resource, dict) else getattr(resource, field, default)


def _discover_import_resource(conn, kind, name, project_id, token, import_id, network_id=None):
    """Recover only one exact tenant/token-bound resource after a lost reply."""
    if kind == "port":
        resources = list(conn.network.ports(name=name))
    elif kind == "share":
        resources = manila.get_client(conn).get("shares/detail", params={"name": name})["shares"]
    elif kind == "volume":
        resources = list(conn.block_storage.volumes(name=name))
    else:
        resources = list(conn.compute.servers(name=name))
    matches = []
    for resource in resources:
        owner = _resource_field(resource, "project_id") or _resource_field(resource, "tenant_id")
        if owner != project_id or _resource_field(resource, "name") != name:
            continue
        if kind == "port":
            exact = (
                _resource_field(resource, "network_id") == network_id
                and _resource_field(resource, "description") == f"afterglow-import:{import_id}:{token}"
            )
        else:
            metadata = _resource_field(resource, "metadata", {}) or {}
            exact = metadata.get("import_id") == str(import_id) and metadata.get("build_token") == token
        if exact:
            matches.append(_resource_field(resource, "id"))
    if len(matches) != 1 or not matches[0]:
        raise build_work.SubmissionUnknown("import submission has no unique owned provider identity")
    return matches[0]


def _get_import_share(conn, share_id):
    return manila.get_client(conn).get(f"shares/{share_id}")["share"]


async def _import_exports(conn, share_id: str) -> list[str]:
    for _ in range(60):
        share = await build_work.run_sync(_get_import_share, conn, share_id)
        if share["status"] == "available":
            break
        if share["status"].startswith("error"):
            raise DockerfileImportError("import share failed provisioning")
        await asyncio.sleep(5)
    else:
        raise TimeoutError("import share did not become available")
    locations = await build_work.run_sync(manila.get_export_locations, conn, share_id)
    candidates = [
        path
        for path in locations
        if isinstance(path, str) and _NFS_EXPORT_RE.fullmatch(path) and path.rpartition(":/")[0]
    ]
    if not candidates:
        raise DockerfileImportError("import share export location is unavailable")
    return candidates


async def _import_rule(conn, step: str, share_id: str, fixed_ip: str, mode: str) -> str:
    submission = await build_work.submission_get(step)
    if submission is not None:
        rules = await build_work.run_sync(manila.list_access_rules, conn, share_id)
        if submission["state"] == "accepted":
            access_id = submission["result"]["access_id"]
            if not any(rule.get("id") == access_id for rule in rules):
                raise DockerfileImportError("import access rule disappeared")
            return access_id
        matches = [
            rule
            for rule in rules
            if rule.get("access_to") == fixed_ip
            and rule.get("access_type") == "ip"
            and rule.get("access_level") == mode
            and rule.get("state") == "active"
        ]
        if len(matches) != 1:
            raise build_work.SubmissionUnknown(f"{step} awaits access reconciliation")
        return matches[0]["id"]
    rule = await build_work.submit(
        step,
        manila.ensure_nfs_access_rule,
        conn,
        share_id,
        fixed_ip,
        mode,
        root_squash=False,
        sec_flavor="sys",
    )
    return rule["access_id"]


async def _open_import_connection(project_id: str):
    from app.services.keystone import get_admin_connection_for_project

    holder = []
    connection = None

    def connect():
        value = get_admin_connection_for_project(project_id)
        holder.append(value)
        return value

    try:
        connection = await build_work.run_sync(connect)
        return connection
    finally:
        if connection is None and holder:
            await build_work.cleanup_sync(holder[0].close)


async def _dispose_import_resources(conn, state: dict, *, drop_outputs=False, protected_shares=()):
    from app.services import cinder

    if drop_outputs and state.get("verifier"):
        from app.services.dockerfile_verify import _cleanup_verifier

        await _cleanup_verifier(conn, state["verifier"])
    for entry in state.get("shares", []) + state.get("ancestors", []):
        if entry.get("access_id") and not entry.get("revoked"):
            share_id = entry.get("id", entry.get("share_id"))
            rules = await build_work.run_sync(manila.list_access_rules, conn, share_id)
            if any(rule.get("id") == entry["access_id"] for rule in rules):
                await build_work.run_sync(manila.revoke_access_rule, conn, share_id, entry["access_id"])
            entry["revoked"] = True
            await build_work.journal_update(shares=state.get("shares", []), ancestors=state.get("ancestors", []))
    if state.get("server_id") and not state.get("server_deleted"):
        await build_work.run_sync(conn.compute.delete_server, state["server_id"], ignore_missing=True)
        state["server_deleted"] = True
        await build_work.journal_update(server_deleted=True)
    if state.get("base_volume_id") and not state.get("base_deleted"):
        try:
            volume = await build_work.run_sync(conn.block_storage.get_volume, state["base_volume_id"])
        except ResourceNotFound:
            # DELETE may have succeeded before its journal acknowledgment.
            volume = None
        if volume is not None and _resource_field(volume, "status") == "deleting":
            # A successor observes disappearance on its next owned attempt;
            # this clone will never become available again and needs no DELETE.
            raise build_work.SubmissionUnknown("base volume deletion awaits disappearance")
        if volume is not None:
            # A clone that failed provisioning cannot become available. Normal
            # Cinder DELETE accepts the error state without any force override.
            if _resource_field(volume, "status") != "error":
                await build_work.run_sync(conn.block_storage.wait_for_status, volume, status="available", wait=180)
            await build_work.run_sync(cinder.delete_volume, conn, state["base_volume_id"])
        state["base_deleted"] = True
        await build_work.journal_update(base_deleted=True)
    if state.get("port_id") and not state.get("port_deleted"):
        await build_work.run_sync(neutron.delete_port, conn, state["port_id"])
        state["port_deleted"] = True
        await build_work.journal_update(port_deleted=True)
    if drop_outputs:
        for entry in state.get("shares", []):
            if not entry.get("id") or entry.get("deleted") or entry["id"] in protected_shares:
                continue
            try:
                share = await build_work.run_sync(_get_import_share, conn, entry["id"])
            except build_work.DispatcherUnavailable:
                raise
            except Exception as exc:
                if getattr(getattr(exc, "response", None), "status_code", None) != 404:
                    raise
                share = None
            if share is not None and share.get("status") != "deleting":
                await build_work.run_sync(manila.delete_file_storage, conn, entry["id"])
            entry["deleted"] = True
            await build_work.journal_update(shares=state.get("shares", []))


async def _finish_failed_import(import_id: int, conn=None) -> None:
    """Remain discoverable during disposal; terminalize SQL only at its end."""
    factory = get_session_factory()
    owned_connection = False
    try:
        state = await build_work.journal_get()
        async with factory() as session:
            job = await _locked_import(session, import_id)
            snapshot = job.resource_snapshot or {}
            builds = [await session.get(LayerBuild, identity) for identity in (job.build_ids or [])]
            builds = [build for build in builds if build is not None]
            protected = {build.share_id for build in builds if build.status == "complete"}
        state["server_id"] = await _accepted_id(
            "server",
            state.get("server_id") or next((build.server_id for build in builds if build.server_id), None),
            allow_rejected=True,
        )
        state["port_id"] = await _accepted_id(
            "port",
            state.get("port_id") or next((build.port_id for build in builds if build.port_id), None),
            allow_rejected=True,
        )
        state["base_volume_id"] = await _accepted_id("base-volume", state.get("base_volume_id"), allow_rejected=True)
        shares = state.setdefault("shares", [{} for _ in builds])
        for index, build in enumerate(builds):
            while len(shares) <= index:
                shares.append({})
            shares[index]["id"] = await _accepted_id(
                f"share:{index}", build.share_id or shares[index].get("id"), allow_rejected=True
            )
        await build_work.journal_update(
            server_id=state["server_id"],
            port_id=state["port_id"],
            base_volume_id=state["base_volume_id"],
            shares=shares,
        )
        has_resources = (
            state["server_id"]
            or state["port_id"]
            or state["base_volume_id"]
            or any(entry.get("id") for entry in shares)
            or state.get("verifier")
        )
        if has_resources:
            if conn is None:
                project_id = snapshot.get("openstack.service_project", {}).get("id")
                if not project_id:
                    raise build_work.DispatcherUnavailable("failed import cleanup project is unavailable")
                conn = await _open_import_connection(project_id)
                owned_connection = True
            await _dispose_import_resources(conn, state, drop_outputs=True, protected_shares=protected)
        async with factory() as session:
            job = await _locked_import(session, import_id)
            message = state["pending_failure"]
            for identity in job.build_ids or []:
                build = await session.get(LayerBuild, identity, with_for_update=True, populate_existing=True)
                if build is not None and build.status not in build_work.TERMINAL:
                    build.status, build.cloud_init_status = "error", "failure"
                    build.progress_step, build.error_message = "Dockerfile import 실패", message
                    build.completed_at = _now()
            job.status, job.progress_step, job.error_message = "error", "실패", message
            job.completed_at, job.updated_at = _now(), _now()
            await build_work.current_binding().lease.check()
            await session.commit()
    except SQLAlchemyError as exc:
        raise build_work.DispatcherUnavailable("import SQL authority is unavailable") from exc
    except (asyncio.CancelledError, build_work.DispatcherUnavailable, build_work.SubmissionUnknown):
        raise
    except Exception as exc:
        raise build_work.SubmissionUnknown("failed import disposal awaits handoff") from exc
    finally:
        if owned_connection:
            await build_work.cleanup_sync(conn.close)


async def run_dockerfile_import_job(import_id: int) -> None:
    """Execute the admitted SQL job under its worker lease; resume, never resubmit."""
    from app.services.palimpsest_digest import DigestReport

    await build_work.checkpoint()
    factory = get_session_factory()
    conn = None
    artifacts_committed = False
    consumer_started = False
    try:
        state = await build_work.journal_get()
        if state.get("pending_failure"):
            await _finish_failed_import(import_id)
            return
        async with factory() as session:
            job = await _locked_import(session, import_id)
            cached_ids = list(state.get("cached_ids", job.artifact_ids or []))
            planned = list(job.planned_layers or [])
            snapshot = job.resource_snapshot or {}
            existing_builds = [await session.get(LayerBuild, identity) for identity in (job.build_ids or [])]
            if any(build is None for build in existing_builds):
                raise DockerfileImportError("import build binding is missing")
            if "outputs" not in state:
                root_name = None
                recovered_token = next((build.build_token for build in existing_builds if build.build_token), None)
                if existing_builds:
                    if not recovered_token and any(build.server_id for build in existing_builds):
                        raise build_work.SubmissionUnknown("existing builder token awaits reconciliation")
                    cached_ids = [
                        identity
                        for identity in cached_ids
                        if (await session.get(LayerArtifact, identity)).build_id not in job.build_ids
                    ]
                    if existing_builds[0].kind == "dockerfile-root":
                        root_name = existing_builds[0].layer_name
                elif not cached_ids:
                    identity = f"{job.base_image_id}:{job.base_image_os_hash_value or job.base_image_checksum or ''}"
                    root_name = "root-" + hashlib.sha256(identity.encode()).hexdigest()[:20]
                outputs = (
                    [
                        {
                            "name": root_name,
                            "instruction": "ROOT",
                            "args": "",
                            "source_metadata": {
                                "source_type": "glance-root",
                                "base_image_id": job.base_image_id,
                                "dockerfile_env": {},
                                "dockerfile_workdir": "/",
                            },
                        }
                    ]
                    if root_name
                    else []
                ) + planned
                # Freeze context and token BEFORE build flush/any provider call.
                await build_work.journal_update(
                    outputs=outputs,
                    cached_ids=cached_ids,
                    root_name=root_name,
                    token=recovered_token or snapshot.get("build_token") or uuid.uuid4().hex,
                    snapshot=snapshot,
                    adopted_sql=bool(existing_builds),
                    shares=[{"id": build.share_id} for build in existing_builds]
                    if existing_builds
                    else [{} for _ in outputs],
                    server_id=next((build.server_id for build in existing_builds if build.server_id), None),
                    port_id=next((build.port_id for build in existing_builds if build.port_id), None),
                )
                state = await build_work.journal_get()
            outputs = state.get("outputs")
            if outputs is None:
                raise DockerfileImportError("import execution context is missing")
            root_name, token = state["root_name"], state["token"]
            build_ids = list(job.build_ids or [])
            if outputs:
                required = (
                    snapshot.get("openstack.service_project", {}).get("id"),
                    snapshot.get("builder.flavor", {}).get("id"),
                    snapshot.get("builder.network", {}).get("id"),
                    snapshot.get("manila", {}).get("share_network_id"),
                    snapshot.get("manila", {}).get("share_type"),
                    snapshot.get("manila", {}).get("share_size_gb"),
                )
                if not all(required):
                    raise DockerfileImportError("import resource snapshot is incomplete")
                if not build_ids:
                    for step in outputs:
                        build = LayerBuild(
                            layer_name=step["name"],
                            kind="dockerfile-root" if step["instruction"] == "ROOT" else "dockerfile",
                            python_version=None,
                            pip_packages=[],
                            apt_packages=[],
                            parent_artifact_id=cached_ids[-1] if cached_ids and not build_ids else None,
                            share_id="",
                            builder_flavor_id=snapshot["builder.flavor"]["id"],
                            builder_network_id=snapshot["builder.network"]["id"],
                            resource_snapshot=snapshot,
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
                        await build_work.checkpoint()
                        await session.flush()
                        build_ids.append(build.id)
                    job.build_ids = build_ids
                if len(build_ids) != len(outputs):
                    raise DockerfileImportError("import build binding does not match frozen outputs")
            builds = [await session.get(LayerBuild, identity) for identity in build_ids]
            if any(build is None for build in builds):
                raise DockerfileImportError("import build binding is missing")
            if cached_ids:
                final = await session.get(LayerArtifact, cached_ids[-1])
                if final is None or not await _rooted_lineage(session, final, job.base_image_id):
                    raise DockerfileImportError("cached import lineage is no longer sealed and complete")
            # SQL build/artifact completion outranks a missing journal ack.
            artifacts_committed = bool(builds) and all(build.status == "complete" for build in builds)
            if any(build.status in build_work.TERMINAL and build.status != "complete" for build in builds):
                raise build_work.DispatcherUnavailable("bound import build is terminal")
            if artifacts_committed:
                await _save_import_profile(session, job, list(job.artifact_ids or []))
            if not outputs:
                await _save_import_profile(session, job, cached_ids)
                artifacts_committed = True
            if job.status != "complete":
                job.status = "running"
            await build_work.checkpoint()
            await session.commit()
        await build_work.journal_update(build_ids=build_ids)

        if outputs:
            conn = await _open_import_connection(snapshot["openstack.service_project"]["id"])
            state = await build_work.journal_get()
            if not artifacts_committed:
                port_id = await _accepted_id(
                    "port",
                    next((b.port_id for b in builds if b.port_id), state.get("port_id")),
                    observe=lambda: _discover_import_resource(
                        conn,
                        "port",
                        f"afterglow-layer-import-{token[:8]}",
                        snapshot["openstack.service_project"]["id"],
                        token,
                        import_id,
                        snapshot["builder.network"]["id"],
                    ),
                )
                if port_id:
                    port = await build_work.run_sync(conn.network.get_port, port_id)
                    if port is None or not port.fixed_ips:
                        raise DockerfileImportError("import port is unavailable")
                    fixed_ip = port.fixed_ips[0]["ip_address"]
                else:
                    if state.get("adopted_sql"):
                        raise build_work.SubmissionUnknown("existing import port awaits reconciliation")
                    port = await build_work.submit(
                        "port",
                        conn.network.create_port,
                        network_id=snapshot["builder.network"]["id"],
                        name=f"afterglow-layer-import-{token[:8]}",
                        description=f"afterglow-import:{import_id}:{token}",
                    )
                    port_id, fixed_ip = port.id, port.fixed_ips[0]["ip_address"]
                await build_work.journal_update(port_id=port_id, fixed_ip=fixed_ip)
                shares = list(state.get("shares", [{} for _ in outputs]))
                for index, step in enumerate(outputs):
                    entry = shares[index]
                    share_id = await _accepted_id(
                        f"share:{index}",
                        builds[index].share_id or entry.get("id"),
                        observe=lambda step=step: _discover_import_resource(
                            conn,
                            "share",
                            f"afterglow-layer-{step['name']}-{token[:8]}",
                            snapshot["openstack.service_project"]["id"],
                            token,
                            import_id,
                        ),
                    )
                    if not share_id:
                        if state.get("adopted_sql"):
                            raise build_work.SubmissionUnknown("existing import share awaits reconciliation")
                        policy = snapshot["manila"]
                        share = await build_work.submit(
                            f"share:{index}",
                            manila.submit_file_storage,
                            conn,
                            f"afterglow-layer-{step['name']}-{token[:8]}",
                            policy["share_size_gb"],
                            policy["share_network_id"],
                            policy["share_type"],
                            "NFS",
                            {
                                "afterglow_role": "dockerfile-layer",
                                "afterglow_layer_name": step["name"],
                                "import_id": str(import_id),
                                "build_token": token,
                            },
                        )
                        share_id = share["id"]
                    entry["id"] = share_id
                    await build_work.journal_update(shares=shares)
                    async with factory() as session:
                        await _locked_import(session, import_id)
                        build = await session.get(LayerBuild, build_ids[index])
                        build.share_id = share_id
                        await build_work.checkpoint()
                        await session.commit()
                    if not entry.get("exports"):
                        entry["exports"] = await _import_exports(conn, share_id)
                        await build_work.journal_update(shares=shares)
                    if not entry.get("access_id"):
                        entry["access_id"] = await _import_rule(conn, f"rw:{index}", share_id, fixed_ip, "rw")
                        await build_work.journal_update(shares=shares)
                ancestors = state.get("ancestors")
                if ancestors is None:
                    ancestors = []
                    if cached_ids:
                        async with factory() as session:
                            await _locked_import(session, import_id)
                            final = await session.get(LayerArtifact, cached_ids[-1])
                            lineage = await _rooted_lineage(session, final, job.base_image_id)
                            if not lineage:
                                raise DockerfileImportError("cached lineage changed during import")
                            ancestors = [
                                {
                                    "share_id": artifact.share_id,
                                    "filename": artifact.sqsh_filename,
                                    "blob_digest": artifact.blob_digest,
                                }
                                for artifact in lineage
                            ]
                    await build_work.journal_update(ancestors=ancestors)
                for index, ancestor in enumerate(ancestors):
                    if not ancestor.get("exports"):
                        ancestor["exports"] = await _import_exports(conn, ancestor["share_id"])
                        await build_work.journal_update(ancestors=ancestors)
                    if not ancestor.get("access_id"):
                        ancestor["access_id"] = await _import_rule(
                            conn, f"ro:{index}", ancestor["share_id"], fixed_ip, "ro"
                        )
                        await build_work.journal_update(ancestors=ancestors)
                base_volume_id = await _accepted_id(
                    "base-volume",
                    state.get("base_volume_id"),
                    observe=lambda: _discover_import_resource(
                        conn,
                        "volume",
                        f"afterglow-root-source-{token[:8]}",
                        snapshot["openstack.service_project"]["id"],
                        token,
                        import_id,
                    ),
                )
                if root_name and not base_volume_id and state.get("adopted_sql"):
                    existing_server = next((build.server_id for build in builds if build.server_id), None)
                    if existing_server:
                        attachments = await build_work.run_sync(
                            lambda: list(conn.compute.volume_attachments(existing_server))
                        )
                        candidates = []
                        for attachment in attachments:
                            identity = _resource_field(attachment, "volume_id")
                            volume = await build_work.run_sync(conn.block_storage.get_volume, identity)
                            if (
                                volume is not None
                                and volume.name == f"afterglow-root-source-{token[:8]}"
                                and _resource_field(volume, "project_id") == snapshot["openstack.service_project"]["id"]
                            ):
                                candidates.append(identity)
                        if len(candidates) == 1:
                            base_volume_id = candidates[0]
                            await build_work.journal_update(base_volume_id=base_volume_id)
                    if not base_volume_id:
                        raise build_work.SubmissionUnknown("existing root source volume awaits reconciliation")
                if root_name:
                    if not base_volume_id:
                        image = await build_work.run_sync(conn.image.get_image, job.base_image_id)
                        if image is None or getattr(image, "status", None) != "active":
                            raise DockerfileImportError("Glance base image is no longer active")
                        for field, expected in (
                            ("checksum", job.base_image_checksum),
                            ("hash_algo", job.base_image_os_hash_algo),
                            ("hash_value", job.base_image_os_hash_value),
                        ):
                            if expected and getattr(image, field, None) != expected:
                                raise DockerfileImportError("Glance base image fingerprint changed before snapshot")
                        volume = await build_work.submit(
                            "base-volume",
                            conn.block_storage.create_volume,
                            name=f"afterglow-root-source-{token[:8]}",
                            imageRef=job.base_image_id,
                            size=max(job.base_image_min_disk or 0, get_settings().boot_volume_size_gb, 1),
                            metadata={"import_id": str(import_id), "build_token": token},
                        )
                        base_volume_id = volume.id
                    await build_work.journal_update(base_volume_id=base_volume_id)
                exports = [entry["exports"] for entry in shares]
                share_ids = [entry["id"] for entry in shares]
                server_id = await _accepted_id(
                    "server",
                    next((b.server_id for b in builds if b.server_id), state.get("server_id")),
                    observe=lambda: _discover_import_resource(
                        conn,
                        "server",
                        f"afterglow-layer-import-{job.layer_prefix}-{token[:8]}",
                        snapshot["openstack.service_project"]["id"],
                        token,
                        import_id,
                    ),
                )
                if server_id:
                    server = await build_work.run_sync(conn.compute.get_server, server_id)
                    if server is None:
                        raise DockerfileImportError("import builder is unavailable")
                else:
                    if state.get("adopted_sql"):
                        raise build_work.SubmissionUnknown("existing import builder awaits reconciliation")
                    if base_volume_id:
                        volume = await build_work.run_sync(conn.block_storage.get_volume, base_volume_id)
                        await build_work.run_sync(
                            conn.block_storage.wait_for_status, volume, status="available", wait=300
                        )
                    user_data = _dockerfile_cloud_config(job, exports, ancestors, root_name, base_volume_id, token)
                    block_mapping = []
                    if base_volume_id:
                        block_mapping = [
                            {
                                "boot_index": 0,
                                "uuid": job.base_image_id,
                                "source_type": "image",
                                "destination_type": "local",
                            },
                            {
                                "boot_index": -1,
                                "uuid": base_volume_id,
                                "source_type": "volume",
                                "destination_type": "volume",
                                "delete_on_termination": False,
                                "disk_bus": "virtio",
                                "device_type": "disk",
                            },
                        ]
                    await build_work.journal_update(user_data=user_data, block_mapping=block_mapping)
                    server = await build_work.submit(
                        "server",
                        conn.compute.create_server,
                        name=f"afterglow-layer-import-{job.layer_prefix}-{token[:8]}",
                        image_id=job.base_image_id,
                        flavor_id=snapshot["builder.flavor"]["id"],
                        networks=[{"port": port_id}],
                        user_data=base64.b64encode(user_data.encode()).decode(),
                        **({"block_device_mapping_v2": block_mapping} if block_mapping else {}),
                        metadata={
                            "union_type": "dockerfile-layer-import",
                            "afterglow_managed": "true",
                            "import_id": str(import_id),
                            "build_token": token,
                        },
                    )
                    server_id = server.id
                await build_work.journal_update(server_id=server_id)
                async with factory() as session:
                    await _locked_import(session, import_id)
                    for index, identity in enumerate(build_ids):
                        build = await session.get(LayerBuild, identity)
                        if build.status not in build_work.TERMINAL:
                            build.server_id, build.port_id = server_id, port_id
                            build.build_token = token if index == 0 else None
                            build.status, build.cloud_init_status = "building", "booting"
                            build.progress_step, build.progress_pct = "Dockerfile import 실행 중", 35
                    await build_work.checkpoint()
                    await session.commit()
                frozen_reports = state.get("reports")
                if frozen_reports:
                    reports = {name: DigestReport(**value) for name, value in frozen_reports.items()}
                else:
                    await build_work.checkpoint()
                    early_success, early_failure = await _wait_for_import_shutdown(conn, server_id, build_ids[0], token)
                    await build_work.checkpoint()
                    reports = await _read_dockerfile_reports(
                        conn, server_id, token, outputs, exports, share_ids, snapshot, early_success, early_failure
                    )
                    await build_work.journal_update(
                        reports={
                            name: {
                                "layer_name": report.layer_name,
                                "blob_digest": report.blob_digest,
                                "blob_md5": report.blob_md5,
                                "size_bytes": report.size_bytes,
                            }
                            for name, report in reports.items()
                        }
                    )
                async with factory() as session:
                    job = await _locked_import(session, import_id)
                    parent_id = cached_ids[-1] if cached_ids else None
                    completed_ids = list(cached_ids)
                    for index, step in enumerate(outputs):
                        report = reports[step["name"]]
                        root = step["instruction"] == "ROOT"
                        kind = "dockerfile-root" if root else "dockerfile"
                        fields = await resolve_digest_fields(
                            session,
                            report=report,
                            parent_artifact_id=parent_id,
                            name=step["name"],
                            kind=kind,
                            ubuntu_base=job.ubuntu_base,
                            python_version=None,
                            pip_packages=[],
                            apt_packages=[],
                        )
                        if not fields["chain_id"]:
                            raise DockerfileImportError("Dockerfile artifact has no verifiable parent digest")
                        step_digest = None
                        if not root:
                            parent = await session.get(LayerArtifact, parent_id)
                            args = step["args"]
                            if step["instruction"] in {"COPY", "ADD"}:
                                args += "\ncommit:" + (step.get("source_metadata") or {}).get("commit_sha", "")
                            step_digest = compute_step_digest(parent.chain_id, step["instruction"], args)
                        artifact = LayerArtifact(
                            name=step["name"],
                            kind=kind,
                            python_version=None,
                            pip_packages=[],
                            apt_packages=[],
                            ubuntu_base=job.ubuntu_base,
                            sqsh_filename=f"{step['name']}-latest.sqsh",
                            share_id=share_ids[index],
                            build_id=build_ids[index],
                            parent_id=parent_id,
                            is_sealed=True,
                            size_bytes=report.size_bytes,
                            step_digest=step_digest,
                            **fields,
                            base_image_id=job.base_image_id,
                            base_image_name=job.base_image_name,
                            base_image_checksum=job.base_image_checksum,
                            base_image_os_hash_algo=job.base_image_os_hash_algo,
                            base_image_os_hash_value=job.base_image_os_hash_value,
                            base_image_min_disk=job.base_image_min_disk,
                            source_metadata=step.get("source_metadata"),
                        )
                        session.add(artifact)
                        await build_work.checkpoint()
                        await session.flush()
                        completed_ids.append(artifact.id)
                        parent_id = artifact.id
                        build = await session.get(LayerBuild, build_ids[index])
                        build.status, build.cloud_init_status = "complete", "success"
                        build.progress_step, build.progress_pct, build.completed_at = "빌드 완료", 100, _now()
                    await _save_import_profile(session, job, completed_ids)
                    await build_work.checkpoint()
                    await session.commit()
                    artifacts_committed = True
            # Only sealed output may advance to disposable cleanup. Cancellation
            # or loss before here never deletes the ongoing builder or output.
            await _dispose_import_resources(conn, await build_work.journal_get())
        if job.consumer_spec:
            consumer_started = True
            await _launch_import_consumer(import_id)
        await _update_job(import_id, status="complete", progress_step="레이어 봉인 완료", progress_pct=100)
        try:
            from app.services.cache import invalidate

            await invalidate("afterglow:union_layer:*")
        except Exception:
            _logger.warning("[dockerfile_import] layer cache invalidation failed")
    except (asyncio.CancelledError, build_work.DispatcherUnavailable):
        # Handoff is not failure: the next owner observes durable resource IDs.
        raise
    except SQLAlchemyError as exc:
        raise build_work.DispatcherUnavailable("import SQL authority is unavailable") from exc
    except build_work.SubmissionUnknown:
        _logger.warning("[dockerfile_import] import %s awaits submission reconciliation", import_id)
    except Exception:
        _logger.warning("[dockerfile_import] import %s failed", import_id)
        if artifacts_committed:
            if consumer_started:
                await _update_job(
                    import_id,
                    status="complete",
                    progress_pct=100,
                    progress_step="레이어 봉인 완료; VM 시작 실패",
                    error_message="Optional consumer launch failed; sealed artifacts remain consumable by import_id",
                )
            # Otherwise disposable cleanup remains pending. Keep sealed work
            # runnable so a successor finishes disposal and the requested VM.
        else:
            await build_work.journal_update(pending_failure="Dockerfile import failed before sealing")
            try:
                await _finish_failed_import(import_id, conn)
            except build_work.SubmissionUnknown:
                _logger.warning("[dockerfile_import] import %s awaits failure disposal", import_id)
    finally:
        if conn is not None:
            await build_work.cleanup_sync(conn.close)
