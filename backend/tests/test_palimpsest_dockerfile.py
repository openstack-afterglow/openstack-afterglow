"""Palimpsest inline Dockerfile 빌드 회귀 테스트.

고정하는 계약:
- inline 업로드는 빌드 컨텍스트가 없으므로 COPY/ADD 를 거부한다 (GitHub 경로는 허용)
- FROM 은 Glance 이름/UUID, Ubuntu 태그 또는 palimpsest 부모를 지정한다
- Glance 참조는 active Ubuntu 이미지로 해석하며, 같은 이름은 최신 이미지를 선택한다
- 빌드 캐시 키는 부모 참조 + 정규화된 instruction 의 sha256; 선두 연속 구간만 재사용한다
- lint 는 빌드/잡 없이 전체 진단, FROM 해석 및 레이어 수를 돌려준다
- inline 경로는 관리자 전용이다

외부 I/O 는 Glance(`conn.image`)와 DB 캐시 조회만 대체한다.
"""

from __future__ import annotations

import asyncio
import threading
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openstack.exceptions import NotFoundException

from app.services.dockerfile_import import (
    SOURCE_INLINE,
    DockerfileImportError,
    compute_step_digest,
    parse_dockerfile_source,
    prepare_inline_dockerfile_import,
    split_cached_prefix,
)
from app.services.layer_base_images import resolve_from_reference

_DIGEST_A = "sha256:" + "a" * 64
_DIGEST_B = "sha256:" + "b" * 64
_IMAGE_UUID = "0f6c2a4e-9d1b-4c3a-8e7f-5a6b7c8d9e0f"
_MISSING_UUID = "11111111-2222-4333-8444-555555555555"


def _parse(text: str, *, allow_build_context: bool = False):
    return parse_dockerfile_source(
        text,
        layer_prefix="demo",
        profile_name="demo",
        commit_sha=None,
        dockerfile_path=None,
        allow_build_context=allow_build_context,
    )


# ---------------------------------------------------------------------------
# Glance 대역 — 호출자 범위의 이미지 목록만 흉내 낸다 (openstacksdk image proxy 의 읽기 API)
# ---------------------------------------------------------------------------

_QUERYABLE = {"id", "name", "status", "os_distro", "visibility", "owner"}


def glance_image(
    image_id: str,
    name: str,
    *,
    release: str = "24.04",
    status: str = "active",
    distro: str = "ubuntu",
    created_at: str | None = "2026-09-01T00:00:00Z",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=image_id,
        name=name,
        status=status,
        os_distro=distro,
        os_version=release,
        checksum=f"md5-{image_id}",
        os_hash_algo="sha512",
        os_hash_value=f"hash-{image_id}",
        min_disk=20,
        visibility="private",
        owner="test-project-123",
        created_at=created_at,
    )


class FakeGlance:
    """`conn.image` 의 읽기 전용 대역. SDK 처럼 없는 ID 는 NotFoundException 을 던진다."""

    def __init__(self, *images: SimpleNamespace):
        self._images = list(images)

    def images(self, **query):
        wanted = {key: value for key, value in query.items() if key in _QUERYABLE}
        return iter([img for img in self._images if all(getattr(img, k) == v for k, v in wanted.items())])

    def get_image(self, image_id):
        for img in self._images:
            if img.id == image_id:
                return img
        raise NotFoundException(f"No Image found for {image_id}")


def glance_conn(*images: SimpleNamespace) -> SimpleNamespace:
    # image 외의 속성은 없다 — 해석 경로가 다른 OpenStack 자원을 건드리면 AttributeError 로 드러난다
    return SimpleNamespace(image=FakeGlance(*images))


async def _uncached_build_cache(planned: list[dict], *, root_ref: str | None) -> list[dict]:
    """A new Glance root has no step cache key until its blob digest exists."""
    return [dict(step, step_digest=None, cached=False, reuse_artifact_id=None) for step in planned]


@contextmanager
def _cache_miss():
    with (
        patch("app.services.dockerfile_import.find_cached_root", AsyncMock(return_value=None)),
        patch("app.services.dockerfile_import.apply_build_cache", AsyncMock(side_effect=_uncached_build_cache)),
    ):
        yield


async def _prepare_inline(conn, text: str):
    with _cache_miss():
        return await prepare_inline_dockerfile_import(
            conn,
            dockerfile_text=text,
            layer_prefix="demo",
            profile_name=None,
        )


# ---------------------------------------------------------------------------
# 파서 — 빌드 컨텍스트
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("instruction", ["COPY app /opt/app", "ADD data /opt/data"])
def test_inline_dockerfile_rejects_build_context_instructions(instruction):
    text = f"FROM ubuntu:24.04\n{instruction}\n"

    with pytest.raises(DockerfileImportError, match="빌드 컨텍스트") as exc:
        _parse(text)

    assert exc.value.line == 2


@pytest.mark.parametrize("instruction", ["COPY app /opt/app", "ADD data /opt/data"])
def test_github_source_still_allows_build_context_instructions(instruction):
    # GitHub 경로는 커밋에 고정된 archive 가 컨텍스트다 — 계속 허용해야 한다
    text = f"FROM ubuntu:24.04\n{instruction}\n"

    parsed = _parse(text, allow_build_context=True)

    assert [step["instruction"] for step in parsed.planned_layers] == [instruction.split()[0]]


def test_inline_dockerfile_accepts_run_env_workdir():
    text = "FROM ubuntu:24.04\nENV FOO=bar\nWORKDIR /srv\nRUN apt-get update\n"

    parsed = _parse(text)

    assert parsed.from_ref == "ubuntu:24.04"
    assert [step["instruction"] for step in parsed.planned_layers] == ["ENV", "WORKDIR", "RUN"]
    # ENV/WORKDIR 는 뒤따르는 RUN 의 payload 에 반영된다
    assert parsed.planned_layers[-1]["payload"]["env"] == {"FOO": "bar"}
    assert parsed.planned_layers[-1]["payload"]["workdir"] == "/srv"


# ---------------------------------------------------------------------------
# 파서 — FROM
# ---------------------------------------------------------------------------


def test_from_accepts_palimpsest_layer_reference():
    text = f"FROM palimpsest/python311@{_DIGEST_A}\nRUN pip install torch\n"

    parsed = _parse(text)

    assert parsed.parent_digest == _DIGEST_A
    # 부모에게서 base 를 상속하므로 Glance 참조는 없다
    assert parsed.from_ref is None


@pytest.mark.parametrize(
    "ref",
    [
        "ubuntu:24.04",
        "ubuntu:16.04",
        "alpine:3.20",
        "cuda:12.4-runtime",
        "team-base",
        "registry.local/team/base:1.0",
        _IMAGE_UUID,
    ],
)
def test_from_accepts_glance_image_references(ref):
    parsed = _parse(f"FROM {ref}\nRUN true\n")

    assert parsed.from_ref == ref
    assert parsed.parent_digest is None
    assert len(parsed.planned_layers) == 1


def test_from_line_skips_comments_and_blank_lines():
    parsed = _parse("# syntax comment\n\nFROM ubuntu:24.04\nRUN true\n")

    assert parsed.from_line == 3


def test_from_scratch_is_rejected_with_actionable_message():
    with pytest.raises(DockerfileImportError, match="scratch"):
        _parse("FROM scratch\nRUN true\n")


@pytest.mark.parametrize(
    "from_line",
    [
        f"FROM palimpsest/py@{_DIGEST_A[:-1]}",  # digest 길이 부족
        "FROM palimpsest/py@md5:abc",
        "FROM ubuntu:24.04 AS builder",
        "FROM --platform=linux/amd64 ubuntu:24.04",
        "FROM $BASE_IMAGE",
        "FROM base;reboot",
        "FROM `hostname`",
    ],
)
def test_from_rejects_unsupported_forms(from_line):
    with pytest.raises(DockerfileImportError) as exc:
        _parse(f"# base\n{from_line}\nRUN true\n")

    assert exc.value.line == 2


def test_multi_stage_from_is_rejected():
    text = "FROM ubuntu:24.04\nRUN true\nFROM ubuntu:22.04\nRUN true\n"

    with pytest.raises(DockerfileImportError, match="multi-stage") as exc:
        _parse(text)

    assert exc.value.line == 3


def test_instruction_before_from_is_rejected():
    with pytest.raises(DockerfileImportError, match="첫 instruction"):
        _parse("RUN true\nFROM ubuntu:24.04\n")


def test_relative_paths_follow_workdir():
    parsed = _parse(
        "FROM ubuntu:24.04\nWORKDIR /srv/app\nWORKDIR src\nCOPY config.json .\nRUN pwd\n",
        allow_build_context=True,
    )
    assert parsed.planned_layers[1]["payload"]["workdir"] == "/srv/app/src"
    assert parsed.planned_layers[2]["payload"]["dest"] == "/srv/app/src/"
    assert parsed.planned_layers[3]["payload"]["workdir"] == "/srv/app/src"


# ---------------------------------------------------------------------------
# 파서 — 여러 줄 입력의 오류 위치
# ---------------------------------------------------------------------------


def test_error_after_line_continuation_reports_physical_line():
    text = "FROM ubuntu:24.04\nRUN apt-get update \\\n    && apt-get install -y curl\nARG TOKEN=1\n"

    with pytest.raises(DockerfileImportError, match="ARG") as exc:
        _parse(text)

    # 논리 줄 번호가 아니라 편집기에 보이는 물리 줄 번호여야 한다
    assert exc.value.line == 4


def test_unterminated_continuation_reports_its_start_line():
    text = "FROM ubuntu:24.04\nRUN true\nRUN apt-get update \\\n"

    with pytest.raises(DockerfileImportError) as exc:
        _parse(text)

    assert exc.value.line == 3


# ---------------------------------------------------------------------------
# 인젝션 방어 (기존 계약 유지 확인)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "unsupported",
    ["ARG X=1", "USER root", "EXPOSE 80", "CMD true", "ENTRYPOINT true", "LABEL a=b", 'SHELL ["/bin/sh"]'],
)
def test_unsupported_instructions_are_rejected(unsupported):
    with pytest.raises(DockerfileImportError):
        _parse(f"FROM ubuntu:24.04\n{unsupported}\n")


@pytest.mark.parametrize(
    "run_args",
    ["--mount=type=cache true", "--network=host true", "--security=insecure true"],
)
def test_run_flags_are_rejected(run_args):
    with pytest.raises(DockerfileImportError):
        _parse(f"FROM ubuntu:24.04\nRUN {run_args}\n")


def test_heredoc_is_rejected():
    with pytest.raises(DockerfileImportError, match="heredoc"):
        _parse("FROM ubuntu:24.04\nRUN <<EOF\ntrue\nEOF\n")


# ---------------------------------------------------------------------------
# 빌드 캐시
# ---------------------------------------------------------------------------


def test_step_digest_is_stable_and_parent_sensitive():
    a = compute_step_digest("ubuntu-24.04", "RUN", "apt-get update")
    b = compute_step_digest("ubuntu-24.04", "RUN", "apt-get  update")  # 공백만 다름
    c = compute_step_digest("ubuntu-22.04", "RUN", "apt-get update")  # 부모가 다름
    d = compute_step_digest("ubuntu-24.04", "RUN", "apt-get upgrade")  # 명령이 다름

    assert a == b, "공백 차이는 같은 명령으로 본다"
    assert a != c, "부모가 다르면 다른 스택이다"
    assert a != d


def test_step_digest_normalizes_instruction_case():
    assert compute_step_digest("base", "run", "true") == compute_step_digest("base", "RUN", "true")


def test_executor_format_change_invalidates_old_env_layer_cache():
    import hashlib

    parent = "sha256:" + "a" * 64
    old_key = "sha256:" + hashlib.sha256(f"{parent}\nENV B=b".encode()).hexdigest()
    assert compute_step_digest(parent, "ENV", "B=b") != old_key


def test_split_cached_prefix_takes_only_leading_run():
    annotated = [
        {"name": "a", "cached": True, "reuse_artifact_id": 1},
        {"name": "b", "cached": True, "reuse_artifact_id": 2},
        {"name": "c", "cached": False, "reuse_artifact_id": None},
        {"name": "d", "cached": True, "reuse_artifact_id": 9},
    ]

    cached_ids, remaining = split_cached_prefix(annotated)

    # 중간부터 재사용하면 다른 스택이 된다 — 선두 연속 구간만 취한다
    assert cached_ids == [1, 2]
    assert [step["name"] for step in remaining] == ["c", "d"]


def test_split_cached_prefix_handles_all_cached_and_none_cached():
    all_cached = [{"name": "a", "cached": True, "reuse_artifact_id": 1}]
    none_cached = [{"name": "a", "cached": False, "reuse_artifact_id": None}]

    assert split_cached_prefix(all_cached) == ([1], [])
    assert split_cached_prefix(none_cached)[0] == []


@pytest.mark.asyncio
async def test_cache_never_reuses_a_legacy_delta_without_a_full_root():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.db import LayerArtifact, LayerBuild
    from app.services.dockerfile_import import apply_build_cache, resolve_parent_layer

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(LayerBuild.__table__.create)
            await connection.run_sync(LayerArtifact.__table__.create)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        root_ref = f"glance:{_IMAGE_UUID}"
        step_digest = compute_step_digest(root_ref, "RUN", "touch /opt/marker")
        async with factory() as session:
            session.add(
                LayerArtifact(
                    name="legacy-delta",
                    kind="dockerfile",
                    sqsh_filename="legacy-delta.sqsh",
                    share_id="old-share",
                    ubuntu_base="ubuntu-24.04",
                    base_image_id=_IMAGE_UUID,
                    is_sealed=True,
                    blob_digest=_DIGEST_A,
                    chain_id=_DIGEST_A,
                    digest_state="ready",
                    step_digest=step_digest,
                )
            )
            await session.commit()
        with patch("app.services.dockerfile_import.get_session_factory", return_value=factory):
            result = await apply_build_cache(
                [{"name": "demo-1", "instruction": "RUN", "args": "touch /opt/marker"}], root_ref=root_ref
            )
        assert result[0]["cached"] is False
        assert result[0]["reuse_artifact_id"] is None
        with patch("app.services.dockerfile_import.get_session_factory", return_value=factory):
            with pytest.raises(DockerfileImportError, match="전체 루트 계보"):
                await resolve_parent_layer(_DIGEST_A, name="legacy-delta")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_root_cache_requires_exact_glance_fingerprint_and_complete_lineage():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.db import LayerArtifact, LayerBuild
    from app.services.dockerfile_import import find_cached_root, resolve_parent_layer

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(LayerBuild.__table__.create)
            await connection.run_sync(LayerArtifact.__table__.create)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            older = LayerArtifact(
                name="root-first",
                kind="dockerfile-root",
                sqsh_filename="first.sqsh",
                share_id="share-1",
                ubuntu_base="ubuntu-24.04",
                base_image_id=_IMAGE_UUID,
                base_image_os_hash_algo="sha512",
                base_image_os_hash_value="first",
                is_sealed=True,
                digest_state="ready",
                blob_digest=_DIGEST_A,
                chain_id=_DIGEST_A,
            )
            newer = LayerArtifact(
                name="root-second",
                kind="dockerfile-root",
                sqsh_filename="second.sqsh",
                share_id="share-2",
                ubuntu_base="ubuntu-24.04",
                base_image_id=_IMAGE_UUID,
                base_image_os_hash_algo="sha512",
                base_image_os_hash_value="second",
                is_sealed=True,
                digest_state="ready",
                blob_digest=_DIGEST_B,
                chain_id=_DIGEST_B,
            )
            session.add_all([older, newer])
            await session.commit()
        with patch("app.services.dockerfile_import.get_session_factory", return_value=factory):
            found = await find_cached_root(
                {"base_image_id": _IMAGE_UUID, "base_image_os_hash_algo": "sha512", "base_image_os_hash_value": "first"}
            )
            assert found.id == older.id
            assert (
                await find_cached_root(
                    {
                        "base_image_id": _IMAGE_UUID,
                        "base_image_os_hash_algo": "sha512",
                        "base_image_os_hash_value": "unknown",
                    }
                )
                is None
            )
            assert (await resolve_parent_layer(_DIGEST_A, name="root-first")).id == older.id
            with pytest.raises(DockerfileImportError, match="전체 루트 계보"):
                await resolve_parent_layer(_DIGEST_A, name="root-second")
    finally:
        await engine.dispose()


def test_builder_manifest_requires_every_sealed_artifact_once():
    import base64
    import json

    from app.services.dockerfile_import import _parse_dockerfile_manifest

    token = "a" * 32
    records = [
        {"name": "root-first", "sha256": "a" * 64, "md5": "b" * 32, "size": 4096},
        {"name": "demo-01-run", "sha256": "c" * 64, "md5": "d" * 32, "size": 2048},
    ]

    def output(items):
        encoded = base64.b64encode(json.dumps(items).encode()).decode()
        return f"::AFTERGLOW::MANIFEST::{token}::{encoded}\n"

    reports = _parse_dockerfile_manifest(output(records), token, ["root-first", "demo-01-run"])
    assert reports["root-first"].blob_digest == _DIGEST_A
    for malformed in (
        output(records[:1]),
        output(records) + output(records),
        output(records).replace(token, "b" * 32),
        output([records[0], {**records[1], "sha256": "not-a-digest"}]),
    ):
        with pytest.raises(DockerfileImportError):
            _parse_dockerfile_manifest(malformed, token, ["root-first", "demo-01-run"])


def test_pinned_github_context_rejects_extraction_escape_and_unbounded_expansion():
    import gzip
    import io
    import tarfile

    from app.services.dockerfile_import import validate_archive_bytes

    def archive_blob(member):
        data = io.BytesIO()
        with tarfile.open(fileobj=data, mode="w:gz") as archive:
            archive.addfile(member, io.BytesIO(b"contents") if member.isfile() else None)
        return data.getvalue()

    valid = tarfile.TarInfo("repository/hello.txt")
    valid.size = len(b"contents")
    validate_archive_bytes(archive_blob(valid))

    traversal = tarfile.TarInfo("repository/../../etc/hostname")
    traversal.size = len(b"contents")
    link = tarfile.TarInfo("repository/escape")
    link.type = tarfile.SYMTYPE
    link.linkname = "/etc"
    oversized = tarfile.TarInfo("repository/huge")
    oversized.size = 512 * 1024 * 1024 + 1
    for member in (traversal, link):
        with pytest.raises(DockerfileImportError):
            validate_archive_bytes(archive_blob(member))
    # Header-only expanded-size claims are rejected before extracting or allocating 512 MiB.
    header_only = gzip.compress(oversized.tobuf() + b"\0" * 1024)
    with pytest.raises(DockerfileImportError):
        validate_archive_bytes(header_only)


def _img(image_id: str, name: str, *, release: str = "24.04", created_at: str | None = None) -> dict:
    return {"id": image_id, "name": name, "ubuntu_base": f"ubuntu-{release}", "created_at": created_at}


def test_from_resolution_prefers_exact_name_and_newest_duplicate():
    images = [
        _img("old", "ubuntu:24.04", created_at="2025-01-01T00:00:00Z"),
        _img("new", "ubuntu:24.04", created_at="2026-01-01T00:00:00Z"),
        _img("other", "noble-gpu"),
    ]

    resolved = resolve_from_reference(images, "ubuntu:24.04")

    assert resolved.kind == "glance_name"
    assert resolved.image == images[1]
    assert "최신" in resolved.note
    assert resolved.completions == []


def test_from_resolution_uses_exact_uuid():
    image = _img(_IMAGE_UUID, "noble-golden")

    resolved = resolve_from_reference([image], _IMAGE_UUID)

    assert resolved.kind == "glance_id"
    assert resolved.image == image
    assert resolved.error is None


def test_from_resolution_unique_ubuntu_tag_and_missing_release():
    image = _img("noble", "noble-golden")

    resolved = resolve_from_reference([image], "ubuntu:24.04")
    missing = resolve_from_reference([image], "ubuntu:22.04")
    unsupported = resolve_from_reference([image], "ubuntu:16.04")

    assert resolved.kind == "ubuntu_tag" and resolved.image == image
    assert missing.image is None and "없습니다" in missing.error
    assert missing.completions == []
    assert unsupported.image is None and "지원하는 Ubuntu 버전" in unsupported.error


def test_from_resolution_ambiguous_tag_offers_sorted_copyable_references():
    images = [
        _img("server", "ubuntu:24.04-server"),
        _img("minimal", "ubuntu-24.04-minimal"),
    ]

    resolved = resolve_from_reference(images, "ubuntu:24.04")

    assert resolved.kind == "ubuntu_tag" and resolved.image is None
    assert "지정" in resolved.error
    assert [item["ref"] for item in resolved.completions] == ["ubuntu-24.04-minimal", "ubuntu:24.04-server"]
    assert [item["id"] for item in resolved.completions] == ["minimal", "server"]


def test_from_resolution_unknown_name_suggests_prefix_and_unsafe_name_uses_uuid():
    images = [
        _img("old", "ubuntu:24.04-server", created_at="2025-01-01T00:00:00Z"),
        _img("new", "ubuntu:24.04-server", created_at="2026-01-01T00:00:00Z"),
        _img("space", "ubuntu:24.04 custom"),
    ]

    suggestion = resolve_from_reference(images, "ubuntu:24")
    unknown = resolve_from_reference(images, "debian:12")

    assert suggestion.kind is None and "찾을 수 없습니다" in suggestion.error
    assert [item["ref"] for item in suggestion.completions] == ["space", "ubuntu:24.04-server"]
    assert suggestion.completions[1]["id"] == "new"
    assert unknown.image is None and unknown.completions == []


# ---------------------------------------------------------------------------
# prepare_inline_dockerfile_import — FROM 의 Glance 해석
# ---------------------------------------------------------------------------


def _snapshot(base: str = "ubuntu-24.04") -> dict:
    return {
        "ubuntu_base": base,
        "base_image_id": "img-1",
        "base_image_name": "ubuntu-24.04",
        "base_image_checksum": None,
        "base_image_os_hash_algo": None,
        "base_image_os_hash_value": None,
        "base_image_min_disk": None,
    }


async def test_inline_import_resolves_conventional_tag_by_exact_glance_name():
    conn = glance_conn(
        glance_image("img-24", "ubuntu:24.04"),
        glance_image("img-24-min", "ubuntu:24.04-minimal"),
        glance_image("img-22", "ubuntu:22.04", release="22.04"),
    )

    plan = await _prepare_inline(conn, "FROM ubuntu:24.04\nRUN true\n")

    assert plan.base_image_snapshot["base_image_id"] == "img-24"
    assert plan.base_image_snapshot["base_image_name"] == "ubuntu:24.04"
    assert plan.base_image_snapshot["ubuntu_base"] == "ubuntu-24.04"


async def test_inline_glance_lookup_does_not_block_other_requests():
    started = threading.Event()
    finish = threading.Event()

    def slow_glance_lookup(conn, parsed):
        started.set()
        if not finish.wait(timeout=5):
            raise TimeoutError("Glance lookup prevented the event loop from progressing")
        return _snapshot()

    with patch("app.services.dockerfile_import.resolve_dockerfile_base_image", side_effect=slow_glance_lookup):
        request = asyncio.create_task(_prepare_inline(glance_conn(), "FROM ubuntu:24.04\nRUN true\n"))
        try:
            started_before_timeout = await asyncio.to_thread(started.wait, 2)
        finally:
            finish.set()
        plan = await request
    assert started_before_timeout

    assert plan.base_image_snapshot["base_image_id"] == "img-1"


async def test_inline_import_selects_newest_duplicate_glance_name():
    conn = glance_conn(
        glance_image("older", "team-base", created_at="2025-01-01T00:00:00Z"),
        glance_image("newer", "team-base", created_at="2026-01-01T00:00:00Z"),
    )

    plan = await _prepare_inline(conn, "FROM team-base\nRUN true\n")

    assert plan.base_image_snapshot["base_image_id"] == "newer"


@pytest.mark.parametrize(
    "tag,expected_id",
    [("ubuntu:24.04", "img-noble"), ("ubuntu:22.04", "img-jammy")],
)
async def test_inline_import_falls_back_to_unique_active_image_of_tag_release(tag, expected_id):
    # 정확히 같은 이름이 없으면 같은 Ubuntu 버전의 active 이미지가 하나뿐일 때만 그것을 쓴다
    conn = glance_conn(
        glance_image("img-noble", "ubuntu-24.04"),
        glance_image("img-noble-staging", "ubuntu-24.04-staging", status="queued"),
        glance_image("img-jammy", "jammy-golden", release="22.04"),
        glance_image("img-deb", "debian-12", release="12", distro="debian"),
    )

    plan = await _prepare_inline(conn, f"FROM {tag}\nRUN true\n")

    assert plan.base_image_snapshot["base_image_id"] == expected_id
    assert plan.base_image_snapshot["ubuntu_base"] == f"ubuntu-{tag.split(':')[1]}"


async def test_inline_import_requires_unambiguous_from_tag():
    conn = glance_conn(
        glance_image("img-noble-a", "ubuntu-24.04"),
        glance_image("img-noble-b", "noble-gpu"),
    )

    with pytest.raises(DockerfileImportError, match="noble-gpu"):
        await _prepare_inline(conn, "# base\nFROM ubuntu:24.04\nRUN true\n")

    # FROM, rather than a separate image selector, disambiguates the build.
    plan = await _prepare_inline(conn, "FROM noble-gpu\nRUN true\n")
    assert plan.base_image_snapshot["base_image_id"] == "img-noble-b"


@pytest.mark.parametrize(
    "ref,expected_id,expected_base",
    [
        ("cuda:12.4-runtime", "img-cuda", "ubuntu-22.04"),
        ("ubuntu:22.04-server", "img-server", "ubuntu-22.04"),
        (_IMAGE_UUID, _IMAGE_UUID, "ubuntu-20.04"),
    ],
)
async def test_inline_import_resolves_glance_name_tag_or_id(ref, expected_id, expected_base):
    conn = glance_conn(
        glance_image("img-cuda", "cuda:12.4-runtime", release="22.04"),
        glance_image("img-cuda-old", "cuda:12.2-runtime", release="22.04"),
        glance_image("img-server", "ubuntu:22.04-server", release="22.04"),
        glance_image(_IMAGE_UUID, "focal-golden", release="20.04"),
    )

    plan = await _prepare_inline(conn, f"FROM {ref}\nRUN true\n")

    # Builder VM 이 부팅할 이미지 ID 는 Dockerfile 텍스트가 아니라 Glance 에서 확인한 값이다
    assert plan.base_image_snapshot["base_image_id"] == expected_id
    assert plan.base_image_snapshot["ubuntu_base"] == expected_base
    assert plan.parent_digest is None


@pytest.mark.parametrize(
    "from_ref,images",
    [
        pytest.param("cuda:12.4-runtime", [], id="missing-name"),
        pytest.param(_MISSING_UUID, [glance_image("img-24", "ubuntu:24.04")], id="missing-id"),
        pytest.param(
            "cuda:12.4-runtime",
            [glance_image("img-q", "cuda:12.4-runtime", release="22.04", status="queued")],
            id="inactive",
        ),
        pytest.param(
            "debian:12",
            [glance_image("img-deb", "debian:12", release="12", distro="debian")],
            id="not-ubuntu",
        ),
        pytest.param(
            "ubuntu:16.04",
            [glance_image("img-16", "ubuntu:16.04", release="16.04")],
            id="unsupported-release",
        ),
    ],
)
async def test_inline_import_rejects_unresolvable_from(from_ref, images):
    with pytest.raises(DockerfileImportError, match="찾을 수 없습니다|지원하는 Ubuntu 버전"):
        await _prepare_inline(glance_conn(*images), f"# base image\nFROM {from_ref}\nRUN true\n")


async def test_inline_import_records_digest_and_source_type():
    conn = glance_conn(glance_image("img-24", "ubuntu:24.04"))

    plan = await _prepare_inline(conn, "FROM ubuntu:24.04\nRUN true\n")

    assert plan.source_type == SOURCE_INLINE
    assert plan.dockerfile_digest.startswith("sha256:")
    assert plan.dockerfile_text == "FROM ubuntu:24.04\nRUN true\n"
    # GitHub 전용 필드는 비어 있어야 한다
    assert plan.github_url is None and plan.commit_sha is None
    assert plan.planned_layers[0]["source_metadata"]["source_type"] == SOURCE_INLINE


@pytest.mark.parametrize("from_ref", ["ubuntu:24.04", f"palimpsest/py@{_DIGEST_A}"])
async def test_from_only_import_rejects_empty_layer_plan(from_ref):
    with pytest.raises(DockerfileImportError, match="instruction이 필요"):
        await _prepare_inline(glance_conn(glance_image("img-24", "ubuntu:24.04")), f"FROM {from_ref}\n")


async def test_inline_import_inherits_base_from_palimpsest_parent():
    parent = MagicMock(id=7, chain_id=_DIGEST_A, **_snapshot("ubuntu-22.04"))
    annotated = [
        {
            "name": "demo-01-run",
            "instruction": "RUN",
            "args": "true",
            "payload": {},
            "source_metadata": {},
            "step_digest": _DIGEST_B,
            "cached": False,
            "reuse_artifact_id": None,
        }
    ]
    with (
        patch("app.services.dockerfile_import.resolve_parent_layer", AsyncMock(return_value=parent)),
        patch("app.services.dockerfile_import.apply_build_cache", AsyncMock(return_value=annotated)) as cache,
    ):
        plan = await prepare_inline_dockerfile_import(
            # Glance 가 없는 연결 — 부모 상속 경로는 Glance 를 조회하지 않는다
            SimpleNamespace(),
            dockerfile_text=f"FROM palimpsest/py@{_DIGEST_A}\nRUN true\n",
            layer_prefix="demo",
            profile_name=None,
        )

    # 부모의 ubuntu base 를 그대로 물려받는다 (다른 base 위에 쌓으면 ABI 가 어긋난다)
    assert plan.base_image_snapshot["ubuntu_base"] == "ubuntu-22.04"
    assert plan.parent_digest == _DIGEST_A
    # 부모가 재사용 접두부의 첫 항목이 된다
    assert plan.cached_artifact_ids == [7]
    # 캐시 조회는 부모의 chain_id 에서 시작한다
    assert cache.await_args.kwargs["root_ref"] == _DIGEST_A


# ---------------------------------------------------------------------------
# API 계약 — 빌드/계획
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path,payload",
    [
        (
            "/api/v1/palimpsest/builds/dockerfile",
            {"dockerfile": "FROM ubuntu:24.04\nRUN true\n", "layer_prefix": "demo"},
        ),
        (
            "/api/v1/palimpsest/builds/dockerfile/plan",
            {"dockerfile": "FROM ubuntu:24.04\nRUN true\n", "layer_prefix": "demo"},
        ),
        ("/api/v1/palimpsest/builds/dockerfile/lint", {"dockerfile": "FROM ubuntu:24.04\nRUN true\n"}),
        ("/api/v1/palimpsest/builds/dockerfile/fetch-url", {"url": "https://example.com/Dockerfile"}),
    ],
)
async def test_inline_build_is_admin_only(non_admin_client, path, payload):
    # 🔴 관리자 전용 표면이다 — 일반 사용자에게 열려 있으면 안 된다
    resp = await non_admin_client.post(path, json=payload)
    assert resp.status_code == 403


async def test_inline_build_rejects_empty_dockerfile(admin_client):
    resp = await admin_client.post(
        "/api/v1/palimpsest/builds/dockerfile", json={"dockerfile": "   ", "layer_prefix": "demo"}
    )

    assert resp.status_code == 422


async def test_inline_build_surfaces_parse_error_as_422(admin_client):
    resp = await admin_client.post(
        "/api/v1/palimpsest/builds/dockerfile",
        json={"dockerfile": "FROM ubuntu:24.04\nCOPY a /b\n", "layer_prefix": "demo"},
    )

    assert resp.status_code == 422
    assert "COPY" in resp.json()["detail"]


async def test_inline_build_rejects_missing_or_unsafe_consumer_ssh_identity_before_queueing(admin_client, mock_conn):
    mock_conn.image = FakeGlance(glance_image("img-24", "ubuntu:24.04"))
    body = {"dockerfile": "FROM ubuntu:24.04\nRUN true\n", "layer_prefix": "demo"}
    with (
        _cache_miss(),
        patch("app.services.dockerfile_import.find_cached_root", AsyncMock(return_value=None)),
        patch("app.api.palimpsest.builds.create_import_job", new_callable=AsyncMock) as create_job,
    ):
        no_key = await admin_client.post(
            "/api/v1/palimpsest/builds/dockerfile", json={**body, "consumer": {"flavor_id": "m1.small"}}
        )
        root_user = await admin_client.post(
            "/api/v1/palimpsest/builds/dockerfile",
            json={
                **body,
                "consumer": {"flavor_id": "m1.small", "ssh_public_key": "ssh-ed25519 AAAA", "ssh_username": "root"},
            },
        )
    assert no_key.status_code == 422
    assert "SSH" in no_key.json()["detail"]
    assert root_user.status_code == 422
    create_job.assert_not_awaited()


async def test_plan_endpoint_resolves_glance_from_without_base_image_id(admin_client, mock_conn):
    mock_conn.image = FakeGlance(glance_image("img-noble", "noble-golden"))

    with _cache_miss():
        resp = await admin_client.post(
            "/api/v1/palimpsest/builds/dockerfile/plan",
            json={"dockerfile": "FROM ubuntu:24.04\nRUN true\n", "layer_prefix": "demo"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["ubuntu_base"] == "ubuntu-24.04"
    assert [step["instruction"] for step in data["steps"]] == ["RUN"]


async def test_build_endpoint_rejects_unresolved_from_without_creating_job(admin_client, mock_conn):
    mock_conn.image = FakeGlance(glance_image("img-24", "ubuntu:24.04"))

    with (
        _cache_miss(),
        patch("app.services.dockerfile_import.create_import_job", new_callable=AsyncMock) as create_job,
        patch("app.api.palimpsest.builds.create_import_job", create_job),
    ):
        resp = await admin_client.post(
            "/api/v1/palimpsest/builds/dockerfile",
            json={"dockerfile": "FROM cuda:12.4-runtime\nRUN true\n", "layer_prefix": "demo"},
        )

    assert resp.status_code == 422
    create_job.assert_not_awaited()


@pytest.mark.parametrize("path", ["/api/v1/palimpsest/builds/dockerfile", "/api/v1/palimpsest/builds/dockerfile/plan"])
async def test_inline_glance_failure_returns_safe_error_without_starting_job(admin_client, mock_conn, path):
    mock_conn.image.images.side_effect = RuntimeError("private provider credential")
    with patch("app.api.palimpsest.builds.create_import_job", new_callable=AsyncMock) as create_job:
        resp = await admin_client.post(
            path,
            json={"dockerfile": "FROM ubuntu:24.04\nRUN true\n", "layer_prefix": "demo"},
        )

    assert resp.status_code == 422
    assert "Glance 이미지 목록을 조회하지 못했습니다" in resp.json()["detail"]
    assert "private provider credential" not in resp.text
    create_job.assert_not_awaited()


# ---------------------------------------------------------------------------
# API 계약 — lint (읽기 전용 진단)
# ---------------------------------------------------------------------------

_LINT = "/api/v1/palimpsest/builds/dockerfile/lint"


async def _lint(admin_client, dockerfile: str, **extra):
    with patch("app.api.palimpsest.builds.create_import_job", new_callable=AsyncMock) as create_job:
        resp = await admin_client.post(_LINT, json={"dockerfile": dockerfile, **extra})

    assert resp.status_code == 200
    create_job.assert_not_awaited()
    return resp.json()


async def test_lint_valid_dockerfile_resolves_ubuntu_tag_and_counts_layers(admin_client, mock_conn):
    mock_conn.image = FakeGlance(glance_image("img-24", "noble-golden"))

    data = await _lint(admin_client, "FROM ubuntu:24.04\nENV A=1\nRUN true\n")

    assert set(data) == {"valid", "diagnostics", "warnings", "from", "layers"}
    assert set(data["from"]) == {
        "line",
        "ref",
        "kind",
        "image",
        "parent",
        "completions",
        "error",
        "note",
    }
    assert data["valid"] is True
    assert data["diagnostics"] == []
    assert data["warnings"] == []
    assert data["from"]["line"] == 1
    assert data["from"]["ref"] == "ubuntu:24.04"
    assert data["from"]["kind"] == "ubuntu_tag"
    assert data["from"]["image"]["id"] == "img-24"
    assert data["from"]["image"]["name"] == "noble-golden"
    assert data["from"]["image"]["ubuntu_base"] == "ubuntu-24.04"
    assert data["from"]["image"]["min_disk"] == 20
    assert data["from"]["parent"] is None
    assert data["from"]["completions"] == []
    assert data["from"]["error"] is None
    assert data["layers"] == {
        "new": 2,
        "inherited": 0,
        "total": 2,
        "limit": 25,
        "by_instruction": {"ENV": 1, "RUN": 1},
    }


async def test_lint_from_only_reports_no_buildable_instructions(admin_client, mock_conn):
    mock_conn.image = FakeGlance(glance_image("img-24", "ubuntu:24.04"))

    data = await _lint(admin_client, "FROM ubuntu:24.04\n")

    assert data["valid"] is False
    assert any("instruction이 필요" in item["message"] for item in data["diagnostics"])
    assert data["from"]["image"]["id"] == "img-24"
    assert data["layers"]["new"] == 0


async def test_lint_whitespace_only_editor_returns_diagnostic(admin_client):
    data = await _lint(admin_client, "   ")

    assert data["valid"] is False
    assert any(diagnostic["line"] is None and "비어" in diagnostic["message"] for diagnostic in data["diagnostics"])
    assert data["layers"]["new"] == 0


async def test_lint_exact_name_selects_newest_duplicate_with_note(admin_client, mock_conn):
    mock_conn.image = FakeGlance(
        glance_image("older", "team-base", created_at="2025-01-01T00:00:00Z"),
        glance_image("newer", "team-base", created_at="2026-01-01T00:00:00Z"),
    )

    data = await _lint(admin_client, "FROM team-base\nRUN true\n")

    assert data["valid"] is True
    assert data["from"]["kind"] == "glance_name"
    assert data["from"]["image"]["id"] == "newer"
    assert "최신" in data["from"]["note"]


async def test_lint_unsupported_ubuntu_release_is_from_error(admin_client, mock_conn):
    mock_conn.image = FakeGlance(glance_image("img-24", "noble"))

    data = await _lint(admin_client, "FROM ubuntu:16.04\nRUN true\n")

    assert data["valid"] is False
    assert data["diagnostics"] == []
    assert data["from"]["kind"] == "ubuntu_tag"
    assert "지원하는 Ubuntu 버전" in data["from"]["error"]
    assert data["from"]["completions"] == []


async def test_lint_collects_all_syntax_errors_and_preserves_valid_steps(admin_client, mock_conn):
    mock_conn.image = FakeGlance(glance_image("img-24", "noble"))

    data = await _lint(admin_client, "FROM ubuntu:24.04\nARG X=1\nRUN true\nCOPY a /b\n")

    assert data["valid"] is False
    assert [diagnostic["line"] for diagnostic in data["diagnostics"]] == [2, 4]
    assert "ARG" in data["diagnostics"][0]["message"]
    assert "COPY" in data["diagnostics"][1]["message"]
    assert data["from"]["kind"] == "ubuntu_tag"
    assert data["layers"] == {"new": 1, "inherited": 0, "total": 1, "limit": 25, "by_instruction": {"RUN": 1}}


async def test_lint_invalid_from_does_not_hide_following_valid_layers(admin_client):
    data = await _lint(admin_client, "FROM scratch\nRUN true\nENV A=1\n")

    assert data["valid"] is False
    assert [diagnostic["line"] for diagnostic in data["diagnostics"]] == [1]
    assert "scratch" in data["diagnostics"][0]["message"]
    assert data["layers"]["new"] == 2
    assert data["layers"]["by_instruction"] == {"RUN": 1, "ENV": 1}


@pytest.mark.parametrize(
    "dockerfile,line,token",
    [
        pytest.param(
            "FROM ubuntu:24.04\nRUN true \\\n    && echo done\nARG TOKEN=1\n", 4, "ARG", id="after-continuation"
        ),
        pytest.param("FROM ubuntu:24.04\nRUN <<EOF\ntrue\nEOF\n", 2, "heredoc", id="heredoc"),
        pytest.param("RUN true\nFROM ubuntu:24.04\n", 1, "FROM", id="instruction-before-from"),
    ],
)
async def test_lint_reports_physical_editor_lines(admin_client, mock_conn, dockerfile, line, token):
    mock_conn.image = FakeGlance(glance_image("img-24", "noble"))

    data = await _lint(admin_client, dockerfile)

    assert data["valid"] is False
    assert data["diagnostics"][0]["line"] == line
    assert token in data["diagnostics"][0]["message"]


async def test_lint_reports_ambiguous_tag_with_copyable_candidates(admin_client, mock_conn):
    mock_conn.image = FakeGlance(
        glance_image("server", "ubuntu:24.04-server"),
        glance_image("minimal", "ubuntu-24.04-minimal"),
    )

    data = await _lint(admin_client, "# base\nFROM ubuntu:24.04\nRUN true\n")

    assert data["valid"] is False
    assert data["diagnostics"] == []
    assert data["from"]["line"] == 2
    assert data["from"]["kind"] == "ubuntu_tag"
    assert data["from"]["image"] is None
    assert "지정" in data["from"]["error"]
    assert [item["ref"] for item in data["from"]["completions"]] == ["ubuntu-24.04-minimal", "ubuntu:24.04-server"]
    assert data["layers"] == {"new": 1, "inherited": 0, "total": 1, "limit": 25, "by_instruction": {"RUN": 1}}


async def test_lint_suggests_unknown_from_prefix(admin_client, mock_conn):
    mock_conn.image = FakeGlance(glance_image("server", "ubuntu:24.04-server"))

    data = await _lint(admin_client, "FROM ubuntu:24\nRUN true\n")

    assert data["valid"] is False
    assert data["from"]["ref"] == "ubuntu:24"
    assert "찾을 수 없습니다" in data["from"]["error"]
    assert [item["ref"] for item in data["from"]["completions"]] == ["ubuntu:24.04-server"]


async def test_lint_bad_prefix_is_diagnostic_without_stopping_parse(admin_client, mock_conn):
    mock_conn.image = FakeGlance(glance_image("noble", "noble"))

    data = await _lint(admin_client, "FROM ubuntu:24.04\nRUN true\n", layer_prefix="Bad Prefix")

    assert data["valid"] is False
    assert len(data["diagnostics"]) == 1
    assert data["diagnostics"][0]["line"] is None
    assert "layer_prefix" in data["diagnostics"][0]["message"]
    assert data["from"]["image"]["id"] == "noble"
    assert data["layers"]["new"] == 1


async def test_lint_reports_glance_list_failure_as_from_error(admin_client, mock_conn):
    mock_conn.image.images.side_effect = RuntimeError("glance down")

    data = await _lint(admin_client, "FROM ubuntu:24.04\nRUN true\n")

    assert data["valid"] is False
    assert data["diagnostics"] == []
    assert data["from"]["error"] == "Glance 이미지 목록을 조회하지 못했습니다"
    assert data["layers"]["new"] == 1


async def test_lint_parent_chain_counts_inherited_layers_and_kvm_warning(admin_client):
    parent = SimpleNamespace(
        id=7,
        name="py",
        blob_digest=_DIGEST_A,
        **{**_snapshot("ubuntu-22.04"), "base_image_name": "ubuntu-22.04"},
    )
    with (
        patch("app.services.dockerfile_import.resolve_parent_layer", AsyncMock(return_value=parent)),
        patch("app.services.dockerfile_import.parent_chain_depth", AsyncMock(return_value=24)),
    ):
        data = await _lint(admin_client, f"FROM palimpsest/py@{_DIGEST_A}\nRUN true\nRUN echo done\n")

    assert data["valid"] is True
    assert data["diagnostics"] == []
    assert data["from"] == {
        "line": 1,
        "ref": _DIGEST_A,
        "kind": "palimpsest",
        "image": None,
        "parent": {
            "id": 7,
            "name": "py",
            "blob_digest": _DIGEST_A,
            "ubuntu_base": "ubuntu-22.04",
            "base_image_name": "ubuntu-22.04",
            "chain_depth": 24,
        },
        "completions": [],
        "error": None,
        "note": None,
    }
    assert data["layers"] == {
        "new": 2,
        "inherited": 24,
        "total": 26,
        "limit": 25,
        "by_instruction": {"RUN": 2},
    }
    assert len(data["warnings"]) == 1
    assert data["warnings"][0]["line"] is None
    assert "상한 25" in data["warnings"][0]["message"]


async def test_lint_reports_missing_palimpsest_parent_without_discarding_estimate(admin_client):
    missing = AsyncMock(side_effect=DockerfileImportError("FROM 이 가리키는 레이어를 찾을 수 없습니다"))

    with patch("app.services.dockerfile_import.resolve_parent_layer", missing):
        data = await _lint(admin_client, f"# parent\nFROM palimpsest/py@{_DIGEST_A}\nRUN true\n")

    assert data["valid"] is False
    assert data["diagnostics"] == []
    assert data["from"]["line"] == 2
    assert data["from"]["parent"] is None
    assert "찾을 수 없습니다" in data["from"]["error"]
    assert data["layers"]["new"] == 1


async def test_lint_rejects_parent_missing_glance_base_image_id(admin_client):
    parent = SimpleNamespace(
        id=7,
        name="py",
        blob_digest=_DIGEST_A,
        **{**_snapshot("ubuntu-22.04"), "base_image_id": None},
    )
    with (
        patch("app.services.dockerfile_import.resolve_parent_layer", AsyncMock(return_value=parent)),
        patch("app.services.dockerfile_import.parent_chain_depth", AsyncMock(return_value=1)),
    ):
        data = await _lint(admin_client, f"FROM palimpsest/py@{_DIGEST_A}\nRUN true\n")

    assert data["valid"] is False
    assert "snapshot 백필" in data["from"]["error"]
    assert data["layers"]["new"] == 1


# ---------------------------------------------------------------------------
# fetch-url
# ---------------------------------------------------------------------------


async def test_fetch_dockerfile_url_happy_path(admin_client):
    sample_dockerfile = b"FROM ubuntu:24.04\nRUN apt-get update\n"
    response = MagicMock(status=200)
    response.read.return_value = sample_dockerfile
    connection = MagicMock()
    connection.getresponse.return_value = response

    with (
        patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]),
        patch("http.client.HTTPSConnection", return_value=connection),
    ):
        resp = await admin_client.post(
            "/api/v1/palimpsest/builds/dockerfile/fetch-url",
            json={"url": "https://raw.githubusercontent.com/org/repo/main/Dockerfile"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["dockerfile"] == "FROM ubuntu:24.04\nRUN apt-get update\n"
    assert data["filename"] == "Dockerfile"
    assert data["size_bytes"] == len(sample_dockerfile)


async def test_fetch_dockerfile_url_normalizes_github_blob(admin_client):
    sample_dockerfile = b"FROM ubuntu:24.04\nENV FOO=bar\n"
    response = MagicMock(status=200)
    response.read.return_value = sample_dockerfile
    connection = MagicMock()
    connection.getresponse.return_value = response
    connection.request.side_effect = lambda *_args, **_kwargs: connection._create_connection(
        ("raw.githubusercontent.com", 443),
        10,
    )

    with (
        patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]) as dns,
        patch("http.client.HTTPSConnection", return_value=connection) as https_conn,
        patch("socket.create_connection") as create_socket,
    ):
        resp = await admin_client.post(
            "/api/v1/palimpsest/builds/dockerfile/fetch-url",
            json={"url": "https://github.com/myorg/myrepo/blob/v1.0.0/deploy/Dockerfile"},
        )

    assert resp.status_code == 200
    assert https_conn.call_args.args[:2] == ("raw.githubusercontent.com", 443)
    assert connection.request.call_args.args[:2] == ("GET", "/myorg/myrepo/v1.0.0/deploy/Dockerfile")
    dns.assert_called_once()
    create_socket.assert_called_once_with(("93.184.216.34", 443), 10, None)


@pytest.mark.parametrize(
    "invalid_url,match_msg",
    [
        ("http://127.0.0.1/Dockerfile", "로컬/사설 네트워크"),
        ("http://localhost:8080/Dockerfile", "로컬/사설 네트워크"),
        ("ftp://example.com/Dockerfile", "http 또는 https"),
        ("http://169.254.169.254/latest/meta-data", "로컬/사설 네트워크"),
        ("http://10.0.0.1/Dockerfile", "로컬/사설 네트워크"),
    ],
)
async def test_fetch_dockerfile_url_rejects_ssrf_and_invalid_schemes(admin_client, invalid_url, match_msg):
    resp = await admin_client.post(
        "/api/v1/palimpsest/builds/dockerfile/fetch-url",
        json={"url": invalid_url},
    )
    assert resp.status_code == 422
    assert match_msg in resp.json()["detail"]


async def test_fetch_dockerfile_url_rejects_redirect_to_private_host_before_connecting(admin_client):
    redirect = MagicMock(status=302)
    redirect.getheader.return_value = "http://private.example/latest/meta-data"
    connection = MagicMock()
    connection.getresponse.return_value = redirect
    with (
        patch(
            "socket.getaddrinfo",
            side_effect=[
                [(2, 1, 6, "", ("93.184.216.34", 443))],
                [(2, 1, 6, "", ("169.254.169.254", 80))],
            ],
        ),
        patch("http.client.HTTPSConnection", return_value=connection) as https_conn,
        patch("http.client.HTTPConnection") as http_conn,
    ):
        resp = await admin_client.post(
            "/api/v1/palimpsest/builds/dockerfile/fetch-url",
            json={"url": "https://example.com/Dockerfile"},
        )
    assert resp.status_code == 422
    assert "로컬/사설 네트워크" in resp.json()["detail"]
    https_conn.assert_called_once()
    http_conn.assert_not_called()


async def test_fetch_dockerfile_url_pins_the_validated_ip_through_connection(admin_client):
    response = MagicMock(status=200)
    response.read.return_value = b"FROM ubuntu:24.04\n"
    connection = MagicMock()
    connection.getresponse.return_value = response
    connection.request.side_effect = lambda *_args, **_kwargs: connection._create_connection(("example.com", 80), 10)
    with (
        patch(
            "socket.getaddrinfo",
            side_effect=[
                [(2, 1, 6, "", ("93.184.216.34", 80))],
                [(2, 1, 6, "", ("127.0.0.1", 80))],
            ],
        ) as dns,
        patch("http.client.HTTPConnection", return_value=connection),
        patch("socket.create_connection") as create_socket,
    ):
        resp = await admin_client.post(
            "/api/v1/palimpsest/builds/dockerfile/fetch-url",
            json={"url": "http://example.com/Dockerfile"},
        )
    assert resp.status_code == 200
    dns.assert_called_once()
    create_socket.assert_called_once_with(("93.184.216.34", 80), 10, None)


async def test_fetch_dockerfile_url_rejects_mixed_dns_answers_before_connect(admin_client):
    with (
        patch(
            "socket.getaddrinfo",
            return_value=[
                (2, 1, 6, "", ("93.184.216.34", 443)),
                (2, 1, 6, "", ("127.0.0.1", 443)),
            ],
        ),
        patch("http.client.HTTPSConnection") as connect,
    ):
        resp = await admin_client.post(
            "/api/v1/palimpsest/builds/dockerfile/fetch-url",
            json={"url": "https://example.com/Dockerfile"},
        )
    assert resp.status_code == 422
    connect.assert_not_called()


@pytest.mark.asyncio
async def test_parent_env_and_workdir_inherit_into_child_plan_and_cached_lineage():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.db import LayerArtifact, LayerBuild

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    digest_c = "sha256:" + "c" * 64
    try:
        async with engine.begin() as connection:
            await connection.run_sync(LayerBuild.__table__.create)
            await connection.run_sync(LayerArtifact.__table__.create)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            root = LayerArtifact(
                id=1,
                name="root-1",
                kind="dockerfile-root",
                parent_id=None,
                sqsh_filename="root-1.sqsh",
                share_id="share-1",
                ubuntu_base="ubuntu-24.04",
                base_image_id=_IMAGE_UUID,
                base_image_name="ubuntu-24.04",
                is_sealed=True,
                digest_state="ready",
                blob_digest=_DIGEST_A,
                chain_id=_DIGEST_A,
                source_metadata={"source_type": "glance-root", "dockerfile_env": {}, "dockerfile_workdir": "/"},
            )
            env_step = LayerArtifact(
                id=2,
                name="parent-01-env-a",
                kind="dockerfile",
                parent_id=1,
                sqsh_filename="parent-01-env-a.sqsh",
                share_id="share-2",
                ubuntu_base="ubuntu-24.04",
                base_image_id=_IMAGE_UUID,
                base_image_name="ubuntu-24.04",
                is_sealed=True,
                digest_state="ready",
                blob_digest=_DIGEST_B,
                chain_id=_DIGEST_B,
                source_metadata={
                    "dockerfile_instruction": "ENV",
                    "dockerfile_args": "A=a",
                    "dockerfile_env": {"A": "a"},
                    "dockerfile_workdir": "/",
                },
            )
            workdir_step = LayerArtifact(
                id=3,
                name="parent-02-workdir-app",
                kind="dockerfile",
                parent_id=2,
                sqsh_filename="parent-02-workdir-app.sqsh",
                share_id="share-3",
                ubuntu_base="ubuntu-24.04",
                base_image_id=_IMAGE_UUID,
                base_image_name="ubuntu-24.04",
                is_sealed=True,
                digest_state="ready",
                blob_digest=digest_c,
                chain_id=digest_c,
                source_metadata={
                    "dockerfile_instruction": "WORKDIR",
                    "dockerfile_args": "/app",
                    "dockerfile_env": {"A": "a"},
                    "dockerfile_workdir": "/app",
                },
            )
            session.add_all([root, env_step, workdir_step])
            await session.commit()

        with patch("app.services.dockerfile_import.get_session_factory", return_value=factory):
            plan = await prepare_inline_dockerfile_import(
                SimpleNamespace(),
                dockerfile_text=(
                    f"FROM palimpsest/parent-02-workdir-app@{digest_c}\n"
                    "ENV B=b\n"
                    "WORKDIR sub\n"
                    'RUN test "$A" = a && test "$B" = b && test "$PWD" = /app/sub\n'
                ),
                layer_prefix="child",
                profile_name="child",
            )
        assert plan.cached_artifact_ids == [1, 2, 3]
        assert [step["instruction"] for step in plan.planned_layers] == ["ENV", "WORKDIR", "RUN"]
        assert plan.planned_layers[0]["payload"]["full_env"] == {"A": "a", "B": "b"}
        assert plan.planned_layers[0]["payload"]["workdir"] == "/app"
        assert plan.planned_layers[1]["payload"]["workdir"] == "/app/sub"
        assert plan.planned_layers[2]["payload"]["env"] == {"A": "a", "B": "b"}
        assert plan.planned_layers[2]["payload"]["workdir"] == "/app/sub"
        assert plan.planned_layers[2]["source_metadata"]["dockerfile_env"] == {"A": "a", "B": "b"}
        assert plan.planned_layers[2]["source_metadata"]["dockerfile_workdir"] == "/app/sub"
    finally:
        await engine.dispose()


def test_guest_executor_preserves_inherited_env_and_workdir_across_layers(tmp_path):
    from app.services import dockerfile_guest

    root_lower = tmp_path / "root"
    parent_env_lower = tmp_path / "parent-env"
    parent_wd_lower = tmp_path / "parent-wd"
    for directory in (root_lower, parent_env_lower, parent_wd_lower):
        directory.mkdir(parents=True)

    dockerfile_guest.write_env_files(parent_env_lower, {"A": "a"})
    dockerfile_guest.write_workdir_files(parent_wd_lower, "/app")
    lowers = [str(parent_wd_lower), str(parent_env_lower), str(root_lower)]
    inherited_env, inherited_workdir = dockerfile_guest.load_inherited_state(lowers)
    assert inherited_env == {"A": "a"}
    assert inherited_workdir == "/app"

    recorded_chroot: list[tuple[list[str], dict[str, str]]] = []

    def fake_call(*args: str) -> None:
        if args and args[0] == "mksquashfs":
            from pathlib import Path

            Path(args[2]).parent.mkdir(parents=True, exist_ok=True)
            Path(args[2]).write_bytes(b"sqsh")

    def fake_run(argv, *, env=None, check=False):
        recorded_chroot.append((list(argv), dict(env or {})))

    with (
        patch.object(dockerfile_guest, "STATE", tmp_path / "state"),
        patch.object(dockerfile_guest, "OUTPUTS", tmp_path / "out"),
        patch.object(dockerfile_guest, "call", side_effect=fake_call),
        patch("app.services.dockerfile_guest.subprocess.run", side_effect=fake_run),
    ):
        dockerfile_guest.run_step(
            {
                "name": "child-01-env-b",
                "instruction": "ENV",
                "args": "B=b",
                "payload": {"env": {"B": "b"}, "full_env": {"B": "b"}},
            },
            0,
            0,
            lowers,
            None,
        )
        child_env_upper = tmp_path / "state/upper-0"
        profile_env = (child_env_upper / "etc/profile.d/afterglow-docker-env.sh").read_text(encoding="utf-8")
        sshd_env = (child_env_upper / "etc/ssh/sshd_config.d/90-afterglow-docker-env.conf").read_text(encoding="utf-8")
        systemd_env = (child_env_upper / "etc/systemd/system.conf.d/90-afterglow-docker-env.conf").read_text(
            encoding="utf-8"
        )
        assert "export A=a\n" in profile_env and "export B=b\n" in profile_env
        assert sshd_env == 'SetEnv A="a" B="b"\n'
        assert 'DefaultEnvironment="A=a" "B=b"\n' in systemd_env

        lowers_with_child_env = [str(child_env_upper), *lowers]
        dockerfile_guest.run_step(
            {
                "name": "child-02-run",
                "instruction": "RUN",
                "args": 'test "$A" = a && test "$B" = b && test "$PWD" = /app',
                "payload": {
                    "command": 'test "$A" = a && test "$B" = b && test "$PWD" = /app',
                    "env": {},
                    "workdir": "/",
                },
            },
            1,
            1,
            lowers_with_child_env,
            None,
        )

    assert len(recorded_chroot) == 1
    chroot_argv, chroot_env = recorded_chroot[0]
    assert chroot_argv[-1].startswith("cd /app && ")
    assert chroot_env["A"] == "a" and chroot_env["B"] == "b"
