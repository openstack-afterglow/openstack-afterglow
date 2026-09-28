from __future__ import annotations

import base64
import json
import subprocess
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from app.models.db import LayerArtifact, LayerImportJob
from app.services import dockerfile_import
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


def test_prepare_dockerfile_import_rejects_unusable_glance_from():
    conn = glance_conn(glance_image("img-22", "ubuntu:22.04", release="22.04"))

    with _pinned_github("FROM cuda:12.4-runtime\nRUN true"), pytest.raises(ValueError):
        _prepare_github(conn)


def test_prepare_github_palimpsest_from_defers_base_to_verified_parent():
    digest = "sha256:" + "a" * 64
    with _pinned_github(f"FROM palimpsest/py@{digest}\nRUN true"):
        plan = _prepare_github(glance_conn())

    assert plan.parent_digest == digest
    assert plan.parent_name == "py"
    assert plan.base_image_snapshot == {}
    assert [step["instruction"] for step in plan.planned_layers] == ["RUN"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "dockerfile",
    [
        "FROM cuda:12.4-runtime\nRUN true",
        "FROM jammy-staging\nRUN true",
        "FROM ubuntu:20.04\nRUN true",
        "FROM palimpsest/py@sha256:" + "a" * 64 + "\nRUN true",
    ],
)
async def test_dockerfile_import_route_rejects_unusable_from_as_400_without_job(admin_client, mock_conn, dockerfile):
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
        patch(
            "app.services.dockerfile_import.resolve_parent_layer",
            AsyncMock(side_effect=DockerfileImportError("missing sealed parent")),
        ),
        patch("app.services.dockerfile_import.create_import_job", new_callable=AsyncMock) as mock_create,
    ):
        resp = await admin_client.post("/api/v1/admin/libraries/imports/dockerfile", json=body)

    assert resp.status_code == 400
    mock_create.assert_not_awaited()


@pytest.mark.asyncio
async def test_sealed_root_and_delta_import_launches_consumer_with_child_first_overlay():
    artifacts = [
        LayerArtifact(
            id=1,
            name="root",
            kind="dockerfile-root",
            parent_id=None,
            is_sealed=True,
            share_id="share-root",
            sqsh_filename="root.sqsh",
            ubuntu_base="ubuntu-24.04",
            base_image_id="image-a",
            blob_digest="sha256:" + "a" * 64,
        ),
        LayerArtifact(
            id=2,
            name="step",
            kind="dockerfile",
            parent_id=1,
            is_sealed=True,
            share_id="share-step",
            sqsh_filename="step.sqsh",
            ubuntu_base="ubuntu-24.04",
            base_image_id="image-a",
            blob_digest="sha256:" + "b" * 64,
        ),
    ]
    snapshot = {
        "network": {"id": "network-a"},
        "flavor": {"id": "flavor-a"},
        "openstack.service_project": {"id": "project-a"},
    }
    job = SimpleNamespace(
        consumer_spec={
            "server_name": "vm",
            "flavor_id": "flavor-a",
            "ssh_public_key": "ssh-ed25519 key",
            "ssh_username": "ubuntu",
            "resource_snapshot": snapshot,
        },
        artifact_ids=[1, 2],
        profile_name="profile",
        base_image_id="image-a",
        consume_id=None,
    )
    consumes = []

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            pass

        async def get(self, model, _id):
            return job if model is LayerImportJob else None

        async def execute(self, _statement):
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: artifacts))

        def add(self, row):
            row.id = 7
            consumes.append(row)

        async def flush(self):
            pass

        async def commit(self):
            pass

    conn = MagicMock()
    conn.image.get_image.return_value = SimpleNamespace(id="image-a", name="ubuntu-24.04", status="active")
    conn.compute.create_server.return_value = SimpleNamespace(id="server-a")
    updates = []

    async def update(_id, **values):
        updates.append(values)

    with (
        patch("app.services.dockerfile_import.get_session_factory", return_value=Session),
        patch("app.database.get_session_factory", return_value=Session),
        patch("app.services.keystone.get_admin_connection_for_project", return_value=conn),
        patch("app.services.layer_build._update_consume_db", side_effect=update),
        patch("app.services.layer_build.neutron.create_port", return_value={"id": "port-a", "fixed_ip": "10.0.0.5"}),
        patch("app.services.layer_build.manila.list_access_rules", return_value=[]),
        patch("app.services.layer_build.manila.ensure_nfs_access_rule", return_value={"access_id": "rule-a"}),
        patch(
            "app.services.layer_build.manila.get_export_locations", side_effect=[["10.0.0.1:/root"], ["10.0.0.2:/step"]]
        ),
        patch(
            "app.services.layer_build.cinder.create_empty_volume",
            return_value=SimpleNamespace(id="11111111-2222-3333-4444-555555555555"),
        ),
        patch("app.services.layer_build._wait_for_consume_health", new_callable=AsyncMock),
        patch("app.services.layer_build.layer_consume_ssh.remove_health_key", new_callable=AsyncMock),
        patch.object(dockerfile_import, "_update_job", new_callable=AsyncMock),
    ):
        await dockerfile_import._launch_import_consumer(9)

    assert consumes[0].artifact_ids == [1, 2]
    assert updates[-1]["status"] == "active"
    user_data = yaml.safe_load(base64.b64decode(conn.compute.create_server.call_args.kwargs["user_data"]))
    layer_manifest = next(
        item for item in user_data["write_files"] if item["path"] == "/etc/afterglow/layers/profile.conf"
    )
    assert base64.b64decode(layer_manifest["content"]).decode() == (
        "/mnt/nfs-layers/0|step.sqsh|sha256:" + "b" * 64 + "\n/mnt/nfs-layers/1|root.sqsh|sha256:" + "a" * 64 + "\n"
    )


@pytest.mark.parametrize("reachable", [True, False])
def test_builder_output_mount_tries_alternates_and_fails_closed(tmp_path, capsys, reachable):
    job = SimpleNamespace(source_type=dockerfile_import.SOURCE_INLINE, planned_layers=[])
    script = dockerfile_import._dockerfile_cloud_init_script(
        job, [["10.0.0.1:/missing", "10.0.0.2:/reachable"]], [], None, None, "a" * 32
    )
    snippet = script.split("python3 - <<'PY'\n", 1)[1].split("\nPY\n", 1)[0]
    config = tmp_path / "exports.json"
    config.write_text(json.dumps([["10.0.0.1:/missing", "10.0.0.2:/reachable"]]))
    snippet = snippet.replace("/etc/afterglow/dockerfile-exports.json", str(config))
    snippet = snippet.replace("/mnt/afterglow-import/out", str(tmp_path / "out"))
    attempts = []

    def mount(argv, **kwargs):
        attempts.append(argv[5])
        assert argv[4] == "rw,hard"
        assert kwargs["timeout"] > 0
        assert kwargs["stdout"] is subprocess.DEVNULL
        assert kwargs["stderr"] is subprocess.DEVNULL
        return SimpleNamespace(returncode=0 if reachable and argv[5].endswith("/reachable") else 32)

    with patch.object(subprocess, "run", side_effect=mount), patch("time.sleep", return_value=None):
        if reachable:
            exec(compile(snippet, "<builder output mount>", "exec"), {})
        else:
            with pytest.raises(RuntimeError, match="output share mount failed"):
                exec(compile(snippet, "<builder output mount>", "exec"), {})
    assert attempts[:2] == ["10.0.0.1:/missing", "10.0.0.2:/reachable"]
    assert len(attempts) == (2 if reachable else 24)
    assert (tmp_path / "out/0/images").is_dir() is reachable
    assert capsys.readouterr().err == ""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status, early_failure, expected",
    [
        ("SHUTOFF", True, "status=SHUTOFF, early_failure=True"),
        ("ERROR", False, "status=ERROR, early_failure=False"),
        ("ERROR 10.0.0.1", False, "status=UNKNOWN, early_failure=False"),
    ],
)
async def test_report_failure_identifies_observed_state_without_token(status, early_failure, expected):
    conn = SimpleNamespace(compute=SimpleNamespace(get_server=lambda _: SimpleNamespace(status=status)))
    with patch.object(dockerfile_import.nova, "get_console_output", return_value=""):
        with pytest.raises(DockerfileImportError) as failure:
            await dockerfile_import._read_dockerfile_reports(
                conn,
                "builder",
                "a" * 32,
                [{"name": "root-proof"}],
                [["host:/out"]],
                ["share"],
                {},
                False,
                early_failure,
            )
    assert expected in str(failure.value)
    assert "a" * 32 not in str(failure.value)
