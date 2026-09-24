"""Palimpsest inline Dockerfile 빌드 회귀 테스트.

고정하는 계약:
- inline 업로드는 **빌드 컨텍스트가 없으므로 COPY/ADD 를 거부**한다 (GitHub 경로는 계속 허용)
- `FROM` 은 ubuntu 4종 또는 `palimpsest/<name>@sha256:<64hex>` 만. `scratch` 는 거부
- 빌드 캐시 키는 부모 참조 + 정규화된 instruction 의 sha256. **선두 연속 구간만** 재사용한다
- inline 경로는 관리자 전용 — 임의 셸 실행 표면이기 때문
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.dockerfile_import import (
    SOURCE_GITHUB,
    SOURCE_INLINE,
    DockerfileImportError,
    compute_step_digest,
    parse_dockerfile_plan,
    parse_dockerfile_source,
    prepare_inline_dockerfile_import,
    split_cached_prefix,
)

_DIGEST_A = "sha256:" + "a" * 64
_DIGEST_B = "sha256:" + "b" * 64


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
# 파서 — 빌드 컨텍스트
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("instruction", ["COPY app /opt/app", "ADD data /opt/data"])
def test_inline_dockerfile_rejects_build_context_instructions(instruction):
    text = f"FROM ubuntu:24.04\n{instruction}\n"

    with pytest.raises(DockerfileImportError, match="빌드 컨텍스트"):
        _parse(text)


@pytest.mark.parametrize("instruction", ["COPY app /opt/app", "ADD data /opt/data"])
def test_github_source_still_allows_build_context_instructions(instruction):
    # GitHub 경로는 커밋에 고정된 archive 가 컨텍스트다 — 계속 허용해야 한다
    text = f"FROM ubuntu:24.04\n{instruction}\n"

    parsed = _parse(text, allow_build_context=True)

    assert [step["instruction"] for step in parsed.planned_layers] == [instruction.split()[0]]


def test_inline_dockerfile_accepts_run_env_workdir():
    text = "FROM ubuntu:24.04\nENV FOO=bar\nWORKDIR /srv\nRUN apt-get update\n"

    parsed = _parse(text)

    assert parsed.ubuntu_base == "ubuntu-24.04"
    assert parsed.parent_digest is None
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
    # 부모에게서 base 를 상속하므로 여기서는 정하지 않는다
    assert parsed.ubuntu_base is None


def test_from_scratch_is_rejected_with_actionable_message():
    with pytest.raises(DockerfileImportError, match="scratch"):
        _parse("FROM scratch\nRUN true\n")


@pytest.mark.parametrize(
    "from_line",
    [
        "FROM alpine:3.20",
        "FROM ubuntu:16.04",
        f"FROM palimpsest/py@{_DIGEST_A[:-1]}",  # digest 길이 부족
        "FROM palimpsest/py@md5:abc",
        "FROM ubuntu:24.04 AS builder",
        "FROM --platform=linux/amd64 ubuntu:24.04",
    ],
)
def test_from_rejects_unsupported_forms(from_line):
    with pytest.raises(DockerfileImportError):
        _parse(f"{from_line}\nRUN true\n")


def test_multi_stage_from_is_rejected():
    text = "FROM ubuntu:24.04\nRUN true\nFROM ubuntu:22.04\nRUN true\n"

    with pytest.raises(DockerfileImportError, match="multi-stage"):
        _parse(text)


def test_instruction_before_from_is_rejected():
    with pytest.raises(DockerfileImportError, match="첫 instruction"):
        _parse("RUN true\nFROM ubuntu:24.04\n")


def test_parse_dockerfile_plan_wrapper_stays_backward_compatible():
    ubuntu_base, planned = parse_dockerfile_plan(
        "FROM ubuntu:22.04\nRUN true\n",
        layer_prefix="demo",
        profile_name="demo",
        commit_sha="a" * 40,
        dockerfile_path="Dockerfile",
    )

    assert ubuntu_base == "ubuntu-22.04"
    assert len(planned) == 1


def test_parse_dockerfile_plan_wrapper_rejects_palimpsest_from():
    # 이 래퍼는 (ubuntu_base, planned) 2-튜플이라 부모 레이어 참조를 표현할 수 없다
    with pytest.raises(DockerfileImportError, match="inline"):
        parse_dockerfile_plan(
            f"FROM palimpsest/py@{_DIGEST_A}\nRUN true\n",
            layer_prefix="demo",
            profile_name="demo",
            commit_sha="a" * 40,
            dockerfile_path="Dockerfile",
        )


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


# ---------------------------------------------------------------------------
# prepare_inline_dockerfile_import
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


async def test_inline_import_requires_base_image_for_ubuntu_from():
    with pytest.raises(DockerfileImportError, match="base_image_id"):
        await prepare_inline_dockerfile_import(
            MagicMock(),
            dockerfile_text="FROM ubuntu:24.04\nRUN true\n",
            layer_prefix="demo",
            profile_name=None,
            base_image_id=None,
        )


async def test_inline_import_rejects_base_mismatch():
    with (
        patch("app.services.dockerfile_import.resolve_base_image_snapshot", return_value=_snapshot("ubuntu-22.04")),
        patch("app.services.dockerfile_import.apply_build_cache", AsyncMock(return_value=[])),
    ):
        with pytest.raises(DockerfileImportError, match="일치하지 않습니다"):
            await prepare_inline_dockerfile_import(
                MagicMock(),
                dockerfile_text="FROM ubuntu:24.04\nRUN true\n",
                layer_prefix="demo",
                profile_name=None,
                base_image_id="img-1",
            )


async def test_inline_import_records_digest_and_source_type():
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
        patch("app.services.dockerfile_import.resolve_base_image_snapshot", return_value=_snapshot()),
        patch("app.services.dockerfile_import.apply_build_cache", AsyncMock(return_value=annotated)),
    ):
        plan = await prepare_inline_dockerfile_import(
            MagicMock(),
            dockerfile_text="FROM ubuntu:24.04\nRUN true\n",
            layer_prefix="demo",
            profile_name=None,
            base_image_id="img-1",
        )

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
            MagicMock(),
            dockerfile_text=f"FROM palimpsest/py@{_DIGEST_A}\nRUN true\n",
            layer_prefix="demo",
            profile_name=None,
            base_image_id=None,
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
    with (
        patch("app.services.dockerfile_import.resolve_base_image_snapshot", return_value=_snapshot()),
        patch("app.services.dockerfile_import.apply_build_cache", AsyncMock(return_value=annotated)),
    ):
        with pytest.raises(DockerfileImportError, match="모든 단계가 이미 빌드"):
            await prepare_inline_dockerfile_import(
                MagicMock(),
                dockerfile_text="FROM ubuntu:24.04\nRUN true\n",
                layer_prefix="demo",
                profile_name=None,
                base_image_id="img-1",
            )


# ---------------------------------------------------------------------------
# API 계약
# ---------------------------------------------------------------------------


async def test_build_routes_are_mounted_under_v1():
    from app.main import app

    paths = {route.path for route in app.routes if "/palimpsest/builds" in route.path}

    assert paths == {
        "/api/v1/palimpsest/builds/dockerfile",
        "/api/v1/palimpsest/builds/dockerfile/fetch-url",
        "/api/v1/palimpsest/builds/dockerfile/plan",
    }


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


def test_source_type_constants_are_distinct():
    assert SOURCE_GITHUB != SOURCE_INLINE
