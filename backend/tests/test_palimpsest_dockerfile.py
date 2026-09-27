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


async def _uncached_build_cache(planned: list[dict], *, root_ref: str) -> list[dict]:
    """DB 없는 캐시 조회 대역: 전부 캐시 미스이고 digest 는 root_ref 에서 이어진다."""
    annotated = []
    parent_ref = root_ref
    for step in planned:
        digest = compute_step_digest(parent_ref, step["instruction"], step["args"])
        annotated.append(dict(step, step_digest=digest, cached=False, reuse_artifact_id=None))
        parent_ref = digest
    return annotated


def _cache_miss():
    return patch(
        "app.services.dockerfile_import.apply_build_cache",
        AsyncMock(side_effect=_uncached_build_cache),
    )


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


async def test_inline_build_cache_never_crosses_glance_images_of_same_release():
    conn = glance_conn(
        glance_image("img-a", "noble-a"),
        glance_image("img-b", "noble-b"),
    )
    body = "RUN apt-get update\n"

    on_a = await _prepare_inline(conn, f"FROM noble-a\n{body}")
    on_a_again = await _prepare_inline(conn, f"FROM noble-a\n{body}")
    on_b = await _prepare_inline(conn, f"FROM noble-b\n{body}")

    # 같은 Ubuntu 버전이라도 다른 이미지 위의 레이어를 재사용하면 다른 root filesystem 이 된다
    assert on_a.planned_layers[0]["step_digest"] == on_a_again.planned_layers[0]["step_digest"]
    assert on_a.planned_layers[0]["step_digest"] != on_b.planned_layers[0]["step_digest"]


async def test_inline_import_records_digest_and_source_type():
    conn = glance_conn(glance_image("img-24", "ubuntu:24.04"))

    plan = await _prepare_inline(conn, "FROM ubuntu:24.04\nRUN true\n")

    assert plan.source_type == SOURCE_INLINE
    assert plan.dockerfile_digest.startswith("sha256:")
    assert plan.dockerfile_text == "FROM ubuntu:24.04\nRUN true\n"
    # GitHub 전용 필드는 비어 있어야 한다
    assert plan.github_url is None and plan.commit_sha is None
    assert plan.planned_layers[0]["source_metadata"]["source_type"] == SOURCE_INLINE


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


async def test_inline_import_rejects_fully_cached_plan():
    annotated = [{"name": "a", "instruction": "RUN", "args": "true", "cached": True, "reuse_artifact_id": 3}]
    with patch("app.services.dockerfile_import.apply_build_cache", AsyncMock(return_value=annotated)):
        with pytest.raises(DockerfileImportError, match="모든 단계가 이미 빌드"):
            await prepare_inline_dockerfile_import(
                glance_conn(glance_image("img-24", "ubuntu:24.04")),
                dockerfile_text="FROM ubuntu:24.04\nRUN true\n",
                layer_prefix="demo",
                profile_name=None,
            )


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


async def test_inline_build_reports_fully_cached_plan_as_409(admin_client):
    with patch(
        "app.api.palimpsest.builds.prepare_inline_dockerfile_import",
        AsyncMock(side_effect=DockerfileImportError("모든 단계가 이미 빌드되어 있습니다")),
    ):
        resp = await admin_client.post(
            "/api/v1/palimpsest/builds/dockerfile",
            json={"dockerfile": "FROM ubuntu:24.04\nRUN true\n", "layer_prefix": "demo"},
        )

    assert resp.status_code == 409


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
    mock_resp = MagicMock()
    mock_resp.geturl.return_value = "https://raw.githubusercontent.com/org/repo/main/Dockerfile"
    mock_resp.read.return_value = sample_dockerfile
    mock_resp.__enter__.return_value = mock_resp

    with (
        patch("urllib.request.urlopen", return_value=mock_resp),
        patch("app.api.palimpsest.builds._validate_safe_url"),
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
    mock_resp = MagicMock()
    mock_resp.geturl.return_value = "https://raw.githubusercontent.com/myorg/myrepo/v1.0.0/deploy/Dockerfile"
    mock_resp.read.return_value = sample_dockerfile
    mock_resp.__enter__.return_value = mock_resp

    with (
        patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen,
        patch("app.api.palimpsest.builds._validate_safe_url"),
    ):
        resp = await admin_client.post(
            "/api/v1/palimpsest/builds/dockerfile/fetch-url",
            json={"url": "https://github.com/myorg/myrepo/blob/v1.0.0/deploy/Dockerfile"},
        )

    assert resp.status_code == 200
    # urllib 에 전달된 Request 객체의 full_url 이 raw URL 로 변환되었는지 검증
    req_arg = mock_urlopen.call_args[0][0]
    assert req_arg.full_url == "https://raw.githubusercontent.com/myorg/myrepo/v1.0.0/deploy/Dockerfile"


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
