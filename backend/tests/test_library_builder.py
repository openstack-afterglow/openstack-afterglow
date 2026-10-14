"""Persisted admissions and leader-only durable build discovery."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import library_builder


@pytest.mark.asyncio
async def test_admission_fails_closed_before_reading_provider_when_db_unavailable():
    with (
        patch("app.database.get_session_factory", return_value=None),
        patch("app.services.library_recipes.get_recipe", AsyncMock()) as recipe,
        patch("app.services.resource_policy_store.get_service_project_connection", AsyncMock()) as connect,
    ):
        with pytest.raises(RuntimeError, match="DB"):
            await library_builder.queue_build("python311")
    recipe.assert_not_awaited()
    connect.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("commit_failure", [False, True])
async def test_admission_commit_or_failure_never_starts_provider(commit_failure):
    recipe = SimpleNamespace(
        id=3,
        library_id="python311",
        version=4,
        commands=[{"script": "old recipe"}],
        apt_packages=[],
        pip_packages=["package==1"],
        base_image_id="image",
        share_size_gb=5,
        share_proto="NFS",
        cloud_init_template_version=1,
    )
    session = AsyncMock()
    session.__aenter__.return_value = session
    anchor, existing, queued = MagicMock(), MagicMock(), MagicMock()
    anchor.scalar_one_or_none.return_value = recipe
    existing.scalars.return_value.first.return_value = None
    queued.scalars.return_value.all.return_value = [8]
    session.execute.side_effect = [anchor, existing, queued]
    # Admission locks the exact service project it resolved policies against.
    session.get.return_value = SimpleNamespace(resource_id="project")
    session.add = MagicMock()
    if commit_failure:
        session.commit.side_effect = RuntimeError("database connection lost on commit")
    connection = MagicMock()
    connection.image.get_image.return_value = SimpleNamespace(name="image-name")
    policies = {
        "builder.flavor": {"id": "flavor"},
        "builder.network": {"id": "network"},
        "manila.nfs_share_type": {"name": "nfs"},
        "manila.share_network": {"id": "share-network"},
    }
    with (
        patch("app.database.get_session_factory", return_value=MagicMock(return_value=session)),
        patch.object(library_builder.lib_svc, "get_by_id", return_value=SimpleNamespace(version="3.11")),
        patch("app.services.library_recipes.get_recipe", AsyncMock(return_value=recipe)),
        patch("app.services.resource_policy_store.get_service_project_connection", AsyncMock(return_value=connection)),
        patch("app.services.resource_policy_store.resolve_policy_snapshot", AsyncMock(return_value=policies)),
        patch(
            "app.services.resource_policy_store.get_policy_snapshot",
            AsyncMock(return_value={"openstack.service_project": {"id": "project"}}),
        ),
        patch("app.services.ephemeral_build.run_ephemeral_build", AsyncMock()) as execute,
    ):
        if commit_failure:
            with pytest.raises(RuntimeError, match="commit"):
                await library_builder.queue_build("python311", existing_share_id="existing-share")
        else:
            result = await library_builder.queue_build("python311", existing_share_id="existing-share")
    row = session.add.call_args.args[0]
    recipe.commands[0]["script"] = "edited later"
    assert row.resource_snapshot["recipe"]["commands"] == [{"script": "old recipe"}]
    assert row.resource_snapshot["library_version"] == "3.11"
    assert row.build_token and row.file_storage_id == "existing-share" and row.status == "queued"
    if not commit_failure:
        assert result == {"status": "queued", "library_id": "python311", "queue_position": 1}
    session.commit.assert_awaited_once()
    execute.assert_not_awaited()
    connection.close.assert_called_once()


@pytest.mark.asyncio
async def test_nonleader_never_discovers_or_reconciles_other_process_work():
    dispatcher = SimpleNamespace(is_leader=AsyncMock(return_value=False), publish=AsyncMock())
    with patch("app.database.get_session_factory") as factory:
        await library_builder._discover_work(dispatcher)
    factory.assert_not_called()
    dispatcher.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_leader_publishes_queued_and_active_sql_identities_without_mutating_rows():
    session = AsyncMock()
    session.__aenter__.return_value = session
    libraries, imports, layers = MagicMock(), MagicMock(), MagicMock()
    libraries.scalars.return_value.all.return_value = [1, 2]
    imports.scalars.return_value.all.return_value = [7]
    layers.scalars.return_value.all.return_value = [11]
    session.execute.side_effect = [libraries, imports, layers]
    dispatcher = SimpleNamespace(is_leader=AsyncMock(return_value=True), publish=AsyncMock())
    with patch("app.database.get_session_factory", return_value=MagicMock(return_value=session)):
        await library_builder._discover_work(dispatcher)
    dispatcher.publish.assert_awaited_once_with(["library:1", "library:2", "import:7", "layer:11"])
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_leader_database_loss_does_not_publish_empty_or_cleanup_active_work():
    dispatcher = SimpleNamespace(is_leader=AsyncMock(return_value=True), publish=AsyncMock())
    with patch("app.database.get_session_factory", return_value=None):
        with pytest.raises(RuntimeError, match="database"):
            await library_builder._discover_work(dispatcher)
    dispatcher.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_api_admission_and_status_fail_closed_without_sql(admin_client):
    with (
        patch("app.database.get_session_factory", return_value=None),
        patch("app.api.identity.admin.manila.list_file_storages", return_value=[]),
        patch.object(library_builder.lib_svc, "get_by_id", return_value=SimpleNamespace(version="3.11")),
        patch("app.services.ephemeral_build.run_ephemeral_build", AsyncMock()) as execute,
    ):
        admission = await admin_client.post(
            "/api/v1/admin/file-storage/build",
            params={
                "library_id": "python311",
                "auto_install": "true",
            },
        )
        status = await admin_client.get("/api/v1/admin/file-storage/builds")
    assert admission.status_code == 503
    assert status.status_code == 503
    execute.assert_not_awaited()
