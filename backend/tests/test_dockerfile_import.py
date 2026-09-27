from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import pytest

from app.services.dockerfile_import import (
    DockerfileImportError,
    DockerfilePlan,
    parse_dockerfile_source,
    parse_github_url,
    prepare_dockerfile_import,
    validate_dockerfile_path,
    validate_layer_name,
)
from tests.test_palimpsest_dockerfile import FakeGlance, glance_conn, glance_image

_SHA = "a" * 40


def _parse_github(dockerfile: str, *, profile_name: str = "demo"):
    return parse_dockerfile_source(
        dockerfile,
        layer_prefix="demo",
        profile_name=profile_name,
        commit_sha=_SHA,
        dockerfile_path="Dockerfile",
        allow_build_context=True,
    )


@contextmanager
def _pinned_github(dockerfile: str):
    """GitHub 네트워크 I/O 대역: 커밋 고정·archive·Dockerfile 본문."""
    with (
        patch("app.services.dockerfile_import.resolve_github_commit", return_value=_SHA),
        patch("app.services.dockerfile_import.fetch_pinned_archive", return_value=b"archive"),
        patch("app.services.dockerfile_import.fetch_pinned_dockerfile", return_value=dockerfile),
    ):
        yield


def _prepare_github(conn) -> DockerfilePlan:
    return prepare_dockerfile_import(
        conn,
        github_url="https://github.com/acme/widgets",
        ref=None,
        dockerfile_path="Dockerfile",
        layer_prefix="demo",
        profile_name=None,
    )


def test_parse_github_url_accepts_only_canonical_public_repo():
    repo = parse_github_url("https://github.com/acme/widgets")

    assert repo.owner == "acme"
    assert repo.repo == "widgets"
    assert repo.canonical_url == "https://github.com/acme/widgets"
    for bad in [
        "http://github.com/acme/widgets",
        "https://evil.com/acme/widgets",
        "https://github.com/acme/widgets?x=1",
        "https://github.com/acme/widgets/tree/main",
        "https://user@github.com/acme/widgets",
    ]:
        with pytest.raises(DockerfileImportError):
            parse_github_url(bad)


def test_validate_names_and_paths_reject_traversal_and_overflow():
    assert validate_layer_name("my-layer.1", field="layer_prefix") == "my-layer.1"
    assert validate_dockerfile_path("docker/Dockerfile") == "docker/Dockerfile"
    for bad in ["../Dockerfile", "/Dockerfile", "docker/../Dockerfile", "Dockerfile;rm"]:
        with pytest.raises(DockerfileImportError):
            validate_dockerfile_path(bad)
    for bad in ["BadUpper", "bad/name", "x" * 65]:
        with pytest.raises(DockerfileImportError):
            validate_layer_name(bad, field="layer_prefix")


def test_parse_dockerfile_supported_subset_plans_layers_deterministically():
    dockerfile = """
    FROM ubuntu:22.04
    ENV APP_HOME=/opt/app PATH=/usr/local/bin
    WORKDIR /opt/app
    COPY src/ ./src/
    ADD config ./config
    RUN echo hello \\
        && touch /opt/app/ready
    """

    parsed = _parse_github(dockerfile, profile_name="demo-profile")
    layers = parsed.planned_layers

    assert parsed.from_ref == "ubuntu:22.04"
    assert [layer["instruction"] for layer in layers] == ["ENV", "WORKDIR", "COPY", "ADD", "RUN"]
    assert [layer["name"] for layer in layers] == [
        "demo-01-env-app-home-opt",
        "demo-02-workdir-opt-app",
        "demo-03-copy-src-src",
        "demo-04-add-config-config",
        "demo-05-run-echo-hello-touch",
    ]
    assert layers[-1]["payload"]["workdir"] == "/opt/app"
    assert layers[-1]["payload"]["env"]["APP_HOME"] == "/opt/app"


def test_parse_dockerfile_env_key_value_form():
    layers = _parse_github("FROM ubuntu:22.04\nENV PATH /usr/local/bin\nRUN echo $PATH").planned_layers

    assert layers[0]["instruction"] == "ENV"
    assert layers[0]["payload"]["env"] == {"PATH": "/usr/local/bin"}
    assert layers[1]["payload"]["env"]["PATH"] == "/usr/local/bin"


@pytest.mark.parametrize(
    "dockerfile, message",
    [
        ("FROM ubuntu:22.04 AS base\nRUN true", "FROM AS"),
        ("FROM ubuntu:22.04\nFROM ubuntu:22.04\nRUN true", "multi-stage"),
        ("FROM ubuntu:22.04\nARG TOKEN", "ARG"),
        ("FROM ubuntu:22.04\nCOPY ../secret /x", "traversal"),
        ("FROM ubuntu:22.04\nADD https://example.com/a /x", "remote URL"),
        ("FROM ubuntu:22.04\nRUN --mount=type=cache echo hi", "RUN"),
    ],
)
def test_parse_dockerfile_rejects_unsafe_or_unsupported_instructions(dockerfile, message):
    with pytest.raises(DockerfileImportError, match=message):
        _parse_github(dockerfile)


def test_prepare_dockerfile_import_resolves_exact_glance_name_and_build_context():
    conn = glance_conn(
        glance_image("img-22", "ubuntu:22.04", release="22.04"),
        glance_image("img-24", "ubuntu:24.04"),
    )

    with _pinned_github("FROM ubuntu:22.04\nCOPY src/ /opt/src/\nRUN make -C /opt/src"):
        plan = _prepare_github(conn)

    assert plan.base_image_snapshot["base_image_id"] == "img-22"
    assert plan.base_image_snapshot["ubuntu_base"] == "ubuntu-22.04"
    assert plan.commit_sha == _SHA
    # GitHub 소스는 커밋 archive 가 빌드 컨텍스트다
    assert [layer["instruction"] for layer in plan.planned_layers] == ["COPY", "RUN"]


def test_prepare_dockerfile_import_resolves_glance_name_tag_from():
    conn = glance_conn(glance_image("img-cuda", "cuda:12.4-runtime", release="22.04"))

    with _pinned_github("FROM cuda:12.4-runtime\nRUN true"):
        plan = _prepare_github(conn)

    assert plan.base_image_snapshot["base_image_id"] == "img-cuda"
    assert plan.base_image_snapshot["ubuntu_base"] == "ubuntu-22.04"


def test_prepare_dockerfile_import_resolves_unique_tag_and_rejects_missing_release():
    conn = glance_conn(glance_image("img-22", "jammy-golden", release="22.04"))

    with _pinned_github("FROM ubuntu:22.04\nRUN true"):
        plan = _prepare_github(conn)

    assert plan.base_image_snapshot["base_image_id"] == "img-22"

    with _pinned_github("FROM ubuntu:20.04\nRUN true"), pytest.raises(ValueError, match="없습니다"):
        _prepare_github(conn)


@pytest.mark.parametrize(
    "dockerfile",
    [
        "FROM cuda:12.4-runtime\nRUN true",
        "FROM palimpsest/py@sha256:" + "a" * 64 + "\nRUN true",
    ],
)
def test_prepare_dockerfile_import_rejects_unusable_from(dockerfile):
    conn = glance_conn(glance_image("img-22", "ubuntu:22.04", release="22.04"))

    with _pinned_github(dockerfile), pytest.raises(ValueError):
        _prepare_github(conn)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "dockerfile",
    [
        "FROM cuda:12.4-runtime\nRUN true",
        "FROM jammy-staging\nRUN true",
        "FROM ubuntu:20.04\nRUN true",
    ],
)
async def test_dockerfile_import_route_rejects_unusable_glance_base_as_400_without_job(
    admin_client, mock_conn, dockerfile
):
    mock_conn.image = FakeGlance(
        glance_image("img-22", "ubuntu:22.04", release="22.04"),
        glance_image("img-staging", "jammy-staging", release="22.04", status="queued"),
    )
    body = {
        "github_url": "https://github.com/acme/widgets",
        "dockerfile_path": "Dockerfile",
        "layer_prefix": "demo",
    }

    with (
        _pinned_github(dockerfile),
        patch("app.services.dockerfile_import.create_import_job", new_callable=AsyncMock) as mock_create,
    ):
        resp = await admin_client.post("/api/v1/admin/libraries/imports/dockerfile", json=body)

    assert resp.status_code == 400
    mock_create.assert_not_awaited()
