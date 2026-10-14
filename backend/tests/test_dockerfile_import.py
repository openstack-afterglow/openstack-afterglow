from __future__ import annotations

import asyncio
import base64
import json
import subprocess
import threading
from contextlib import asynccontextmanager, contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from app.models.db import LayerArtifact, LayerBuild, LayerConsume, LayerImportJob
from app.services import build_work, dockerfile_import
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


class _ImportRows:
    """SQL-authority double; provider work still uses real bind/journal/drain."""

    def __init__(self, *rows):
        self.rows = {(type(row), row.id): row for row in rows}
        self.commits = 0

    def __call__(self):
        store = self

        class Session:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                pass

            async def get(self, model, identity, **_kwargs):
                return store.rows.get((model, identity))

            async def execute(self, statement):
                model = statement.column_descriptions[0]["entity"]
                rows = [row for (kind, _), row in store.rows.items() if kind is model]
                return SimpleNamespace(
                    scalar_one_or_none=lambda: rows[0] if rows else None,
                    scalars=lambda: SimpleNamespace(all=lambda: rows),
                )

            def add(self, row):
                if row.id is None:
                    row.id = 1 + max((identity for kind, identity in store.rows if kind is type(row)), default=0)
                store.rows[type(row), row.id] = row

            async def flush(self):
                pass

            async def commit(self):
                store.commits += 1

            async def refresh(self, _row):
                pass

        return Session()


@asynccontextmanager
async def _owned_import(store, redis, *, job_id=9, owner="owner-a"):
    """Exercise real SQL guards and nonexpiring Redis submission journals."""
    key = f"test:imports:lease:import:{job_id}"

    class Lease:
        def __init__(self):
            self.key, self.owner = key, owner

        async def check(self):
            if await redis.get(self.key) != self.owner:
                raise build_work.DispatcherUnavailable("import ownership lost")

    await redis.set(key, owner)
    with (
        patch.object(dockerfile_import, "get_session_factory", return_value=store),
        patch("app.database.get_session_factory", return_value=store),
    ):
        try:
            async with build_work.bind(redis, f"import:{job_id}", Lease()) as binding:
                yield binding
        finally:
            if await redis.get(key) == owner:
                await redis.delete(key)


def _import_job(*, cached=False, consumer=False):
    snapshot = {
        "openstack.service_project": {"id": "project-a"},
        "builder.flavor": {"id": "flavor-a"},
        "builder.network": {"id": "network-a"},
        "base_image": {"id": "image-a"},
        "build_token": "a" * 32,
        "manila": {"share_network_id": "share-network", "share_type": "nfs", "share_size_gb": 1},
    }
    return LayerImportJob(
        id=9,
        profile_name="profile",
        source_type=dockerfile_import.SOURCE_INLINE,
        layer_prefix="demo",
        planned_layers=[],
        artifact_ids=[1] if cached else [],
        build_ids=[],
        status="queued",
        base_image_id="image-a",
        base_image_name="ubuntu",
        ubuntu_base="ubuntu-24.04",
        resource_snapshot=snapshot,
        consumer_spec={
            "transport": "nfs",
            "server_name": "vm",
            "flavor_id": "flavor-a",
            "ssh_username": "ubuntu",
            "ssh_public_key": "ssh-ed25519 key",
            "resource_snapshot": {"openstack.service_project": {"id": "project-a"}, "network": {"id": "network-a"}},
        }
        if consumer
        else None,
    )


def _sealed_import_root():
    return LayerArtifact(
        id=1,
        name="root",
        kind="dockerfile-root",
        parent_id=None,
        is_sealed=True,
        digest_state="ready",
        share_id="share-root",
        sqsh_filename="root.sqsh",
        base_image_id="image-a",
        ubuntu_base="ubuntu-24.04",
        blob_digest="sha256:" + "a" * 64,
        chain_id="sha256:" + "a" * 64,
        size_bytes=8,
    )


@contextmanager
def _import_provider(conn):
    from app.services.palimpsest_digest import DigestReport

    conn.network.create_port.return_value = SimpleNamespace(id="port-a", fixed_ips=[{"ip_address": "10.0.0.5"}])
    conn.network.get_port.return_value = conn.network.create_port.return_value
    conn.image.get_image.return_value = SimpleNamespace(id="image-a", status="active")
    conn.block_storage.create_volume.return_value = SimpleNamespace(id="base-volume")
    conn.block_storage.get_volume.return_value = SimpleNamespace(id="base-volume")
    conn.compute.create_server.return_value = SimpleNamespace(id="server-a")
    conn.compute.get_server.return_value = SimpleNamespace(id="server-a", status="SHUTOFF")
    conn.compute.volume_attachments.return_value = []
    client = MagicMock()
    client.post.return_value = {"share": {"id": "share-root"}}
    client.get.return_value = {"share": {"id": "share-root", "status": "available"}}

    async def reports(_conn, _server, _token, outputs, *_args):
        return {
            step["name"]: DigestReport(
                layer_name=step["name"], blob_digest="sha256:" + "a" * 64, blob_md5="b" * 32, size_bytes=8
            )
            for step in outputs
        }

    with (
        patch("app.services.keystone.get_admin_connection_for_project", return_value=conn),
        patch.object(dockerfile_import.manila, "get_client", return_value=client),
        patch.object(
            dockerfile_import.manila,
            "list_share_types",
            return_value=[{"name": "nfs", "extra_specs": {"driver_handles_share_servers": "true"}}],
        ),
        patch.object(dockerfile_import.manila, "ensure_nfs_access_rule", return_value={"access_id": "rule-a"}),
        patch.object(dockerfile_import.manila, "get_export_locations", return_value=["10.0.0.1:/root"]),
        patch.object(dockerfile_import.manila, "list_access_rules", return_value=[{"id": "rule-a"}]),
        patch.object(dockerfile_import.manila, "revoke_access_rule") as revoke,
        patch.object(dockerfile_import.manila, "delete_file_storage") as delete_share,
        patch.object(dockerfile_import, "_dockerfile_cloud_config", return_value="cloud-config"),
        patch.object(dockerfile_import, "_wait_for_import_shutdown", AsyncMock(return_value=(True, False))) as wait,
        patch.object(dockerfile_import, "_read_dockerfile_reports", side_effect=reports),
        patch.object(
            dockerfile_import,
            "resolve_digest_fields",
            AsyncMock(
                return_value={
                    "blob_digest": "sha256:" + "a" * 64,
                    "chain_id": "sha256:" + "a" * 64,
                    "digest_state": "ready",
                }
            ),
        ),
        patch("app.services.cache.invalidate", AsyncMock()),
    ):
        yield SimpleNamespace(wait=wait, client=client, revoke=revoke, delete_share=delete_share, reports=reports)


@pytest.mark.asyncio
async def test_import_consumer_binding_preserves_root_first_ids_and_is_reused(_fake_redis_global):
    job = _import_job(cached=True, consumer=True)
    job.artifact_ids = [1, 2]
    store = _ImportRows(job, _sealed_import_root())

    async def launch(**values):
        row = store.rows[LayerConsume, values["consume_db_id"]]
        row.status = "active"

    with patch("app.services.layer_build.run_layer_consume", AsyncMock(side_effect=launch)) as consume:
        async with _owned_import(store, _fake_redis_global):
            await dockerfile_import._launch_import_consumer(9)
            await dockerfile_import._launch_import_consumer(9)
            assert (await build_work.journal_get())["consume_id"] == job.consume_id
    rows = [row for (kind, _), row in store.rows.items() if kind is LayerConsume]
    assert len(rows) == 1
    assert rows[0].artifact_ids == [1, 2]
    assert rows[0].transport == "nfs" and rows[0].project_id == "project-a" and rows[0].share_id == ""
    consume.assert_awaited_once()
    assert consume.call_args.kwargs["artifact_ids"] == [1, 2]
    assert consume.call_args.kwargs["resource_snapshot"] == job.consumer_spec["resource_snapshot"]
    assert consume.call_args.kwargs["image_id"] == job.base_image_id


@pytest.mark.asyncio
async def test_import_consumer_handoff_reuses_pending_binding(_fake_redis_global):
    job = _import_job(cached=True, consumer=True)
    row = LayerConsume(
        id=7,
        profile_name=job.profile_name,
        server_name="vm",
        status="creating",
        share_id="",
        project_id="project-a",
        artifact_ids=[1],
        resource_snapshot={},
    )
    job.consume_id = row.id
    store = _ImportRows(job, _sealed_import_root(), row)
    with patch("app.services.layer_build.run_layer_consume", AsyncMock()) as consume:
        async with _owned_import(store, _fake_redis_global, owner="replacement"):
            with pytest.raises(build_work.SubmissionUnknown, match="consumer"):
                await dockerfile_import._launch_import_consumer(9)
    assert len([kind for kind, _ in store.rows if kind is LayerConsume]) == 1
    assert consume.call_args.kwargs["consume_db_id"] == 7


@pytest.mark.asyncio
async def test_failed_consumer_completes_sealed_import_only_after_terminal_disposal(caplog, _fake_redis_global):
    job = _import_job(cached=True, consumer=True)
    store = _ImportRows(job, _sealed_import_root())
    # First owner's disposal fails (row stays creating); the successor finishes it.
    outcomes = iter(["creating", "error"])

    async def consume(**values):
        store.rows[LayerConsume, values["consume_db_id"]].status = next(outcomes)
        raise RuntimeError("private provider token")

    with (
        _import_provider(MagicMock()) as provider,
        patch("app.services.layer_build.run_layer_consume", AsyncMock(side_effect=consume)) as launch,
    ):
        async with _owned_import(store, _fake_redis_global):
            await dockerfile_import.run_dockerfile_import_job(9)
        assert job.status == "running" and job.completed_at is None and job.error_message is None
        async with _owned_import(store, _fake_redis_global, owner="replacement"):
            await dockerfile_import.run_dockerfile_import_job(9)
            journal = await build_work.journal_get()
    assert launch.await_count == 2
    assert {call.kwargs["consume_db_id"] for call in launch.await_args_list} == {job.consume_id}
    assert journal["consumer_done"] is True and journal["consumer_status"] == "error"
    assert job.status == "complete" and job.error_message.startswith("Optional consumer launch failed")
    assert dockerfile_import._job_to_dict(job)["consumer_status"] == "error"
    assert store.rows[LayerArtifact, 1].is_sealed
    provider.delete_share.assert_not_called()
    assert "private provider token" not in caplog.text


def test_root_consumer_renderer_keeps_child_first_manifest():
    from app.services.layer_build import render_layer_consume_user_data

    user_data = yaml.safe_load(
        render_layer_consume_user_data(
            "profile",
            [("10.0.0.2:/step", "step.sqsh"), ("10.0.0.1:/root", "root.sqsh")],
            ssh_public_key="ssh-ed25519 key",
            ssh_username="ubuntu",
            root_mode=True,
            digests=["sha256:" + "b" * 64, "sha256:" + "a" * 64],
            root_upper_volume_id="11111111-2222-3333-4444-555555555555",
            root_export_candidates=[["10.0.0.2:/step"], ["10.0.0.1:/root"]],
        )
    )
    manifest = next(item for item in user_data["write_files"] if item["path"] == "/etc/afterglow/layers/profile.conf")
    assert base64.b64decode(manifest["content"]).decode() == (
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
async def test_report_failure_identifies_observed_state_without_token(
    status, early_failure, expected, _fake_redis_global
):
    conn = SimpleNamespace(compute=SimpleNamespace(get_server=lambda _: SimpleNamespace(status=status)))
    async with _owned_import(_ImportRows(_import_job()), _fake_redis_global):
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


@pytest.mark.asyncio
async def test_immediate_block_job_rejected_before_policy_or_provider_resolution():
    with (
        patch.object(dockerfile_import, "finalize_dockerfile_plan", AsyncMock()) as finalize,
        patch("app.services.resource_policy_store.get_service_project_connection", AsyncMock()) as connect,
        patch.object(dockerfile_import, "get_session_factory") as factory,
    ):
        with pytest.raises(DockerfileImportError, match="exact import_id"):
            await dockerfile_import.create_import_job(SimpleNamespace(), consumer_spec={"transport": "block"})
    finalize.assert_not_awaited()
    connect.assert_not_awaited()
    factory.assert_not_called()


@pytest.mark.asyncio
async def test_github_block_consumer_rejected_before_provider_mutation(admin_client, mock_conn):
    with (
        patch.object(
            dockerfile_import, "prepare_dockerfile_import", side_effect=AssertionError("planner invoked")
        ) as plan,
        patch.object(dockerfile_import, "finalize_dockerfile_plan", AsyncMock()) as finalize,
        patch("app.services.layer_build.resolve_layer_consume_resource_snapshot", AsyncMock()) as resolve,
        patch.object(dockerfile_import, "create_import_job", AsyncMock()) as create,
    ):
        response = await admin_client.post(
            "/api/v1/admin/libraries/imports/dockerfile",
            json={
                "github_url": "https://github.com/acme/widgets",
                "layer_prefix": "demo",
                "consumer": {"flavor_id": "m1.small", "transport": "block", "key_name": "private-key"},
            },
        )
    assert response.status_code == 422
    assert "import_id" in str(response.json()["detail"])
    plan.assert_not_called()
    finalize.assert_not_awaited()
    resolve.assert_not_awaited()
    create.assert_not_awaited()
    mock_conn.compute.get_keypair.assert_not_called()
    mock_conn.compute.create_server.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("cached", [False, True])
async def test_sealed_import_remains_consumable_when_optional_consumer_fails(cached, caplog, _fake_redis_global):
    from app.services.layer_build import resolve_import_consume_artifacts

    job = _import_job(cached=cached, consumer=True)
    store = _ImportRows(job, *([_sealed_import_root()] if cached else []))
    conn = MagicMock()
    with (
        _import_provider(conn) as provider,
        patch.object(
            dockerfile_import, "_launch_import_consumer", AsyncMock(side_effect=RuntimeError("private provider token"))
        ),
    ):
        async with _owned_import(store, _fake_redis_global):
            await dockerfile_import.run_dockerfile_import_job(9)
            assert job.status == "complete" and job.completed_at is not None and job.progress_pct == 100
            assert job.artifact_ids == [1] and store.rows[LayerArtifact, 1].is_sealed
            assert dockerfile_import._job_to_dict(job)["consumer_status"] == "error"
            profile, artifacts = await resolve_import_consume_artifacts(9)
            assert profile == "profile" and [item["id"] for item in artifacts] == [1]
    provider.delete_share.assert_not_called()
    assert "private provider token" not in caplog.text
    assert "private provider token" not in (job.error_message or "")


@pytest.mark.asyncio
@pytest.mark.parametrize("cached", [False, True])
async def test_cancel_after_sealing_keeps_import_runnable_for_consumer_handoff(cached, _fake_redis_global):
    job = _import_job(cached=cached, consumer=True)
    store = _ImportRows(job, *([_sealed_import_root()] if cached else []))
    conn = MagicMock()
    with (
        _import_provider(conn) as provider,
        patch.object(dockerfile_import, "_launch_import_consumer", AsyncMock(side_effect=asyncio.CancelledError)),
    ):
        async with _owned_import(store, _fake_redis_global):
            with pytest.raises(asyncio.CancelledError):
                await dockerfile_import.run_dockerfile_import_job(9)
        assert job.status == "running" and job.error_message is None
        assert store.rows[LayerArtifact, 1].is_sealed and job.artifact_ids == [1]
        with patch.object(dockerfile_import, "_launch_import_consumer", AsyncMock()) as launch:
            async with _owned_import(store, _fake_redis_global, owner="replacement"):
                await dockerfile_import.run_dockerfile_import_job(9)
            launch.assert_awaited_once_with(9)
        assert job.status == "complete"
        assert conn.compute.create_server.call_count == (0 if cached else 1)
        assert len([kind for kind, _ in store.rows if kind is LayerArtifact]) == 1
        provider.delete_share.assert_not_called()


@pytest.mark.asyncio
async def test_cancelled_create_drains_acceptance_and_handoff_finalizes_same_server(_fake_redis_global):
    job, conn = _import_job(), MagicMock()
    store = _ImportRows(job)
    started, release = threading.Event(), threading.Event()
    guest = {"elapsed": 0, "source_ready_at_boot": False}

    def create(**kwargs):
        guest["source_ready_at_boot"] = any(
            entry.get("uuid") == "base-volume"
            and entry.get("boot_index") == -1
            and entry.get("source_type") == entry.get("destination_type") == "volume"
            and entry.get("delete_on_termination") is False
            for entry in kwargs.get("block_device_mapping_v2", [])
        )
        started.set()
        if not release.wait(5):
            raise TimeoutError("test SDK barrier was not released")
        return SimpleNamespace(id="server-a")

    with _import_provider(conn) as provider:
        conn.compute.create_server.side_effect = create
        async with _owned_import(store, _fake_redis_global):
            task = asyncio.create_task(dockerfile_import.run_dockerfile_import_job(9))
            try:
                assert await asyncio.wait_for(asyncio.to_thread(started.wait, 5), 6)
                task.cancel()
                await asyncio.sleep(0)
                assert not task.done()
                conn.close.assert_not_called()
            finally:
                release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
            submission = await build_work.submission_get("server")
            assert submission == {"state": "accepted", "result": {"id": "server-a"}}
            assert await _fake_redis_global.ttl("afterglow:builds:journal:import:9:submit:server") == -1
        assert job.status == "running"
        conn.compute.delete_server.assert_not_called()
        provider.revoke.assert_not_called()
        provider.delete_share.assert_not_called()
        conn.close.assert_called_once()
        guest["elapsed"] = 300

        async def reports(*args):
            if not guest["source_ready_at_boot"] and guest["elapsed"] > 180:
                raise DockerfileImportError("root source disk missed the guest mount deadline")
            return await provider.reports(*args)

        with patch.object(dockerfile_import, "_read_dockerfile_reports", side_effect=reports):
            async with _owned_import(store, _fake_redis_global, owner="replacement"):
                await dockerfile_import.run_dockerfile_import_job(9)
        assert guest["source_ready_at_boot"]
        conn.compute.create_volume_attachment.assert_not_called()
        assert job.status == "complete" and job.artifact_ids == [1]
        assert conn.compute.create_server.call_count == 1
        assert conn.network.create_port.call_count == 1
        assert conn.block_storage.create_volume.call_count == 1
        assert provider.client.post.call_count == 1
        assert conn.close.call_count == 2
        assert len([kind for kind, _ in store.rows if kind is LayerBuild]) == 1


@pytest.mark.asyncio
async def test_lost_server_reply_is_observed_by_exact_scope_without_recreate(_fake_redis_global):
    job, conn = _import_job(), MagicMock()
    store = _ImportRows(job)
    with _import_provider(conn):
        conn.compute.create_server.side_effect = OSError("accepted reply lost")
        async with _owned_import(store, _fake_redis_global):
            await dockerfile_import.run_dockerfile_import_job(9)
            assert (await build_work.submission_get("server"))["state"] == "unknown"
        assert job.status == "running" and job.error_message is None
        conn.compute.servers.return_value = [
            SimpleNamespace(
                id="server-a",
                name="afterglow-layer-import-demo-aaaaaaaa",
                project_id="project-a",
                metadata={"import_id": "9", "build_token": "a" * 32},
            )
        ]
        async with _owned_import(store, _fake_redis_global, owner="replacement"):
            await dockerfile_import.run_dockerfile_import_job(9)
        assert job.status == "complete"
        assert conn.compute.create_server.call_count == 1
        conn.compute.servers.assert_called_once_with(name="afterglow-layer-import-demo-aaaaaaaa")


@pytest.mark.asyncio
@pytest.mark.parametrize("loss", ["assignment", "terminal_sql"])
async def test_lost_authority_preserves_builder_and_cannot_overwrite_terminal(loss, _fake_redis_global):
    job, conn = _import_job(), MagicMock()
    store = _ImportRows(job)

    async def lose(*_args):
        if loss == "assignment":
            await _fake_redis_global.set("test:imports:lease:import:9", "new-owner")
        else:
            job.status, job.error_message = "cancelled", "operator cancellation"
        return True, False

    with _import_provider(conn) as provider:
        provider.wait.side_effect = lose
        async with _owned_import(store, _fake_redis_global):
            with pytest.raises(build_work.DispatcherUnavailable):
                await dockerfile_import.run_dockerfile_import_job(9)
        assert job.status == ("running" if loss == "assignment" else "cancelled")
        conn.compute.delete_server.assert_not_called()
        conn.network.delete_port.assert_not_called()
        conn.block_storage.delete_volume.assert_not_called()
        provider.revoke.assert_not_called()
        provider.delete_share.assert_not_called()
        conn.close.assert_called_once()


@pytest.mark.asyncio
async def test_import_worker_requires_owned_durable_target():
    with patch.object(dockerfile_import, "get_session_factory") as factory:
        with pytest.raises(build_work.DispatcherUnavailable):
            await dockerfile_import.run_dockerfile_import_job(9)
    factory.assert_not_called()


@pytest.mark.asyncio
async def test_admission_persists_only_sql_job_and_token_without_starting_task():
    store = _ImportRows()
    plan = DockerfilePlan(
        github_url=None,
        repo_owner=None,
        repo_name=None,
        commit_sha=None,
        dockerfile_path=None,
        layer_prefix="demo",
        profile_name="profile",
        source_type=dockerfile_import.SOURCE_INLINE,
        planned_layers=[],
        cached_artifact_ids=[1],
        base_image_snapshot={
            "base_image_id": "image-a",
            "ubuntu_base": "ubuntu-24.04",
            "base_image_checksum": "immutable-checksum",
        },
    )
    with (
        patch.object(dockerfile_import, "get_session_factory", return_value=store),
        patch.object(dockerfile_import.asyncio, "create_task") as create_task,
    ):
        result = await dockerfile_import.create_import_job(plan)
    row = store.rows[LayerImportJob, result["id"]]
    assert row.status == "queued" and row.build_ids == [] and row.artifact_ids == [1]
    assert row.base_image_checksum == "immutable-checksum"
    assert len(row.resource_snapshot["build_token"]) == 32
    assert "build_token" not in result["resource_snapshot"]
    create_task.assert_not_called()


@pytest.mark.asyncio
async def test_existing_sql_builder_and_shares_recover_without_rebinding_or_create(_fake_redis_global):
    job, conn = _import_job(), MagicMock()
    store = _ImportRows(job)
    with _import_provider(conn) as provider:
        provider.wait.side_effect = asyncio.CancelledError
        async with _owned_import(store, _fake_redis_global):
            with pytest.raises(asyncio.CancelledError):
                await dockerfile_import.run_dockerfile_import_job(9)
        bound_ids = list(job.build_ids)
        assert store.rows[LayerBuild, bound_ids[0]].server_id == "server-a"
        assert store.rows[LayerBuild, bound_ids[0]].share_id == "share-root"
        # Drop only the merged context acknowledgment. The SQL bindings and
        # accepted CREATE journals still identify the in-flight provider work.
        await _fake_redis_global.delete("afterglow:builds:journal:import:9")
        provider.wait.side_effect = None
        conn.compute.volume_attachments.return_value = [SimpleNamespace(volume_id="base-volume")]
        with patch.object(dockerfile_import.manila, "list_access_rules", return_value=[{"id": "rule-a"}]):
            async with _owned_import(store, _fake_redis_global, owner="replacement"):
                await dockerfile_import.run_dockerfile_import_job(9)
        assert job.status == "complete" and job.build_ids == bound_ids and job.artifact_ids == [1]
        assert conn.compute.create_server.call_count == 1
        assert conn.network.create_port.call_count == 1
        assert conn.block_storage.create_volume.call_count == 1
        conn.compute.create_volume_attachment.assert_not_called()
        assert provider.client.post.call_count == 1
        assert conn.close.call_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("mismatch", ["project", "token", "ambiguous"])
async def test_unknown_create_scope_mismatch_stays_nonterminal_without_replay(mismatch, _fake_redis_global):
    job, conn = _import_job(), MagicMock()
    store = _ImportRows(job)
    with _import_provider(conn) as provider:
        conn.compute.create_server.side_effect = OSError("accepted reply lost")
        async with _owned_import(store, _fake_redis_global):
            await dockerfile_import.run_dockerfile_import_job(9)
        resource = SimpleNamespace(
            id="server-a",
            name="afterglow-layer-import-demo-aaaaaaaa",
            project_id="foreign" if mismatch == "project" else "project-a",
            metadata={"import_id": "9", "build_token": "b" * 32 if mismatch == "token" else "a" * 32},
        )
        conn.compute.servers.return_value = [resource, resource] if mismatch == "ambiguous" else [resource]
        async with _owned_import(store, _fake_redis_global, owner="replacement"):
            await dockerfile_import.run_dockerfile_import_job(9)
        assert job.status == "running" and job.error_message is None
        assert conn.compute.create_server.call_count == 1
        assert job.artifact_ids == []
        conn.compute.delete_server.assert_not_called()
        provider.delete_share.assert_not_called()
        assert conn.close.call_count == 2


@pytest.mark.asyncio
async def test_import_shutdown_failure_observation_is_durable_across_handoff(_fake_redis_global):
    job = _import_job()
    build = LayerBuild(id=1, layer_name="root", kind="dockerfile-root", status="building", share_id="share-root")
    store = _ImportRows(job, build)
    conn = MagicMock()
    conn.compute.get_server.side_effect = [SimpleNamespace(status="ACTIVE")] * 6 + [SimpleNamespace(status="SHUTOFF")]
    with (
        patch.object(dockerfile_import.nova, "get_console_output", return_value=f"::AFTERGLOW::FAILURE::{'a' * 32}"),
        patch.object(dockerfile_import.asyncio, "sleep", AsyncMock()),
    ):
        async with _owned_import(store, _fake_redis_global):
            assert await dockerfile_import._wait_for_import_shutdown(conn, "server-a", 1, "a" * 32) == (False, True)
            assert (await build_work.journal_get())["early_failure"] is True
        conn.compute.get_server.side_effect = None
        conn.compute.get_server.return_value = SimpleNamespace(status="SHUTOFF")
        async with _owned_import(store, _fake_redis_global, owner="replacement"):
            assert await dockerfile_import._wait_for_import_shutdown(conn, "server-a", 1, "a" * 32) == (False, True)
    conn.compute.create_server.assert_not_called()


@pytest.mark.asyncio
async def test_definitive_failure_disposes_resources_before_terminalizing_import_and_children(_fake_redis_global):
    job, conn = _import_job(), MagicMock()
    store = _ImportRows(job)
    observed_statuses = []
    with _import_provider(conn) as provider:

        def delete(*_args, **_kwargs):
            observed_statuses.append(job.status)

        conn.compute.delete_server.side_effect = delete
        with patch.object(
            dockerfile_import, "_read_dockerfile_reports", AsyncMock(side_effect=RuntimeError("bad output"))
        ):
            async with _owned_import(store, _fake_redis_global):
                await dockerfile_import.run_dockerfile_import_job(9)
        assert observed_statuses == ["running"]
        assert job.status == "error" and job.error_message == "Dockerfile import failed before sealing"
        assert all(store.rows[LayerBuild, identity].status == "error" for identity in job.build_ids)
        provider.delete_share.assert_called_once_with(conn, "share-root")
        conn.network.delete_port.assert_called_once_with("port-a", ignore_missing=True)
        conn.block_storage.delete_volume.assert_called_once_with("base-volume", ignore_missing=True)
        conn.close.assert_called_once()


@pytest.mark.asyncio
async def test_failed_disposal_handoff_skips_provisioning_and_terminalizes_only_after_cleanup(_fake_redis_global):
    job, conn = _import_job(), MagicMock()
    store = _ImportRows(job)
    loop = asyncio.get_running_loop()
    with _import_provider(conn) as provider:

        def lose_during_delete(*_args, **_kwargs):
            assert job.status == "running"
            asyncio.run_coroutine_threadsafe(
                _fake_redis_global.set("test:imports:lease:import:9", "replacement"),
                loop,
            ).result(timeout=5)

        conn.compute.delete_server.side_effect = lose_during_delete
        with patch.object(
            dockerfile_import, "_read_dockerfile_reports", AsyncMock(side_effect=RuntimeError("bad output"))
        ):
            async with _owned_import(store, _fake_redis_global):
                with pytest.raises(build_work.DispatcherUnavailable):
                    await dockerfile_import.run_dockerfile_import_job(9)
        assert job.status == "running"
        state = json.loads(await _fake_redis_global.get("afterglow:builds:journal:import:9"))
        assert state["pending_failure"] == "Dockerfile import failed before sealing"
        provider.delete_share.assert_not_called()
        conn.compute.delete_server.side_effect = None
        async with _owned_import(store, _fake_redis_global, owner="replacement"):
            await dockerfile_import.run_dockerfile_import_job(9)
        assert job.status == "error"
        assert all(store.rows[LayerBuild, identity].status == "error" for identity in job.build_ids)
        assert conn.compute.create_server.call_count == 1
        assert conn.network.create_port.call_count == 1
        assert conn.block_storage.create_volume.call_count == 1
        assert provider.client.post.call_count == 1
        assert provider.wait.call_count == 1
        provider.delete_share.assert_called_once_with(conn, "share-root")
        assert conn.close.call_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("step", ["port", "base-volume", "server"])
async def test_definitive_create_rejection_disposes_only_accepted_resources_without_replay(step, _fake_redis_global):
    class RejectedCreate(RuntimeError):
        status_code = 400

    job, conn = _import_job(), MagicMock()
    store = _ImportRows(job)
    with _import_provider(conn) as provider:
        create = {
            "port": conn.network.create_port,
            "base-volume": conn.block_storage.create_volume,
            "server": conn.compute.create_server,
        }[step]
        create.side_effect = RejectedCreate("provider rejected CREATE")
        async with _owned_import(store, _fake_redis_global):
            await dockerfile_import.run_dockerfile_import_job(9)
            assert (await build_work.submission_get(step))["state"] == "rejected"
        assert job.status == "error"
        assert all(store.rows[LayerBuild, identity].status == "error" for identity in job.build_ids)
        assert create.call_count == 1
        conn.compute.delete_server.assert_not_called()
        if step == "port":
            provider.delete_share.assert_not_called()
            conn.network.delete_port.assert_not_called()
        else:
            provider.delete_share.assert_called_once_with(conn, "share-root")
            conn.network.delete_port.assert_called_once_with("port-a", ignore_missing=True)
        if step == "server":
            conn.block_storage.delete_volume.assert_called_once_with("base-volume", ignore_missing=True)
        else:
            conn.block_storage.delete_volume.assert_not_called()
        conn.close.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("observed", ["gone", "deleting"])
async def test_sealed_import_recovers_base_delete_before_journal_ack_and_finishes_consumer(
    observed, _fake_redis_global
):
    from openstack.exceptions import ResourceNotFound

    job, conn = _import_job(consumer=True), MagicMock()
    job.status, job.artifact_ids, job.build_ids = "running", [1], [10]
    root = _sealed_import_root()
    root.build_id = 10
    build = LayerBuild(
        id=10,
        layer_name="root",
        kind="dockerfile-root",
        status="complete",
        share_id="share-root",
        server_id="server-a",
        port_id="port-a",
        build_token="a" * 32,
    )
    store = _ImportRows(job, root, build)
    with _import_provider(conn), patch.object(dockerfile_import, "_launch_import_consumer", AsyncMock()) as launch:
        if observed == "gone":
            conn.block_storage.get_volume.side_effect = ResourceNotFound("base clone was already deleted")
        else:
            conn.block_storage.get_volume.return_value = SimpleNamespace(id="base-volume", status="deleting")
        async with _owned_import(store, _fake_redis_global):
            await build_work.journal_update(
                outputs=[{"name": "root", "instruction": "ROOT", "args": ""}],
                root_name="root",
                token="a" * 32,
                cached_ids=[],
                shares=[{"id": "share-root"}],
                server_id="server-a",
                server_deleted=True,
                port_id="port-a",
                base_volume_id="base-volume",
            )
            await dockerfile_import.run_dockerfile_import_job(9)
        conn.block_storage.wait_for_status.assert_not_called()
        conn.block_storage.delete_volume.assert_not_called()
        if observed == "deleting":
            assert job.status == "running" and job.error_message is None
            conn.network.delete_port.assert_not_called()
            launch.assert_not_awaited()
            conn.block_storage.get_volume.side_effect = ResourceNotFound("base clone finished deletion")
            async with _owned_import(store, _fake_redis_global, owner="replacement"):
                await dockerfile_import.run_dockerfile_import_job(9)
        assert job.status == "complete" and job.artifact_ids == [1] and job.build_ids == [10]
        launch.assert_awaited_once_with(9)
        conn.network.delete_port.assert_called_once_with("port-a", ignore_missing=True)
        conn.compute.create_server.assert_not_called()
        conn.compute.delete_server.assert_not_called()
        assert conn.close.call_count == (1 if observed == "gone" else 2)


@pytest.mark.asyncio
async def test_failed_source_clone_is_deleted_without_waiting_for_impossible_available_state(_fake_redis_global):
    job, conn = _import_job(), MagicMock()
    store = _ImportRows(job)
    with _import_provider(conn) as provider:
        conn.block_storage.get_volume.return_value = SimpleNamespace(id="base-volume", status="error")
        conn.block_storage.wait_for_status.side_effect = RuntimeError("source clone provisioning failed")
        async with _owned_import(store, _fake_redis_global):
            await dockerfile_import.run_dockerfile_import_job(9)
        assert job.status == "error"
        assert conn.block_storage.wait_for_status.call_count == 1
        conn.block_storage.delete_volume.assert_called_once_with("base-volume", ignore_missing=True)
        conn.compute.create_server.assert_not_called()
        assert all(store.rows[LayerBuild, identity].status == "error" for identity in job.build_ids)
        provider.delete_share.assert_called_once_with(conn, "share-root")
        conn.close.assert_called_once()
