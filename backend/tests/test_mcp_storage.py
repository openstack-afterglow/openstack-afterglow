from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.mcp_control_plane import sdk, storage
from app.services.mcp_control_plane.storage import (
    McpStorageError,
    get_project_backup,
    get_project_snapshot,
    get_project_volume,
    list_project_backups,
    list_project_server_volumes,
    list_project_snapshots,
    list_project_volumes,
    preview_project_backup_delete,
    preview_project_snapshot_delete,
    preview_project_volume_create,
    preview_project_volume_delete,
    request_project_backup_delete,
    request_project_snapshot_delete,
    request_project_volume_create,
    request_project_volume_delete,
)


@pytest.mark.asyncio
async def test_volume_list_uses_project_filter_and_returns_only_safe_owned_fields():
    calls: list[dict[str, object]] = []

    class BlockStorage:
        def volumes(self, **kwargs):
            calls.append(kwargs)
            return [
                SimpleNamespace(
                    id="volume-a",
                    name="data-a",
                    status="available",
                    size=20,
                    project_id="project-a",
                    created_at="2026-07-27T00:00:00Z",
                    encryption_key_id="secret",
                    volume_image_metadata={"credential": "secret"},
                )
            ]

    result = await list_project_volumes(SimpleNamespace(block_storage=BlockStorage()), project_id="project-a", limit=50)

    assert calls == [{"details": True, "project_id": "project-a"}]
    assert result == [
        {
            "id": "volume-a",
            "name": "data-a",
            "status": "available",
            "size_gb": 20,
            "created_at": "2026-07-27T00:00:00Z",
        }
    ]


@pytest.mark.asyncio
async def test_volume_get_requires_ownership_proof():
    class BlockStorage:
        def get_volume(self, _volume_id):
            return SimpleNamespace(id="volume-a", name=None, status="available", size=20, project_id="project-b")

    with pytest.raises(McpStorageError, match="ownership"):
        await get_project_volume(
            SimpleNamespace(block_storage=BlockStorage()), project_id="project-a", volume_id="volume-a"
        )


@pytest.mark.asyncio
async def test_snapshot_list_proves_snapshot_and_parent_volume_ownership_and_redacts_metadata():
    calls: list[tuple[str, object]] = []

    class BlockStorage:
        def snapshots(self, **kwargs):
            calls.append(("snapshots", kwargs))
            return [
                SimpleNamespace(
                    id="snapshot-a",
                    name="backup-a",
                    status="available",
                    size=20,
                    volume_id="volume-a",
                    project_id="project-a",
                    created_at="2026-07-27T00:00:00Z",
                    encryption_key_id="secret",
                    metadata={"credential": "secret"},
                )
            ]

        def get_volume(self, volume_id):
            calls.append(("get_volume", volume_id))
            return SimpleNamespace(
                id=volume_id,
                name="data-a",
                status="available",
                size=20,
                project_id="project-a",
            )

    result = await list_project_snapshots(
        SimpleNamespace(block_storage=BlockStorage()), project_id="project-a", limit=50
    )

    assert calls == [
        ("snapshots", {"details": True, "project_id": "project-a"}),
        ("get_volume", "volume-a"),
    ]
    assert result == [
        {
            "id": "snapshot-a",
            "name": "backup-a",
            "status": "available",
            "source_volume_id": "volume-a",
            "size_gb": 20,
            "created_at": "2026-07-27T00:00:00Z",
        }
    ]


@pytest.mark.asyncio
async def test_snapshot_get_rejects_foreign_parent_volume():
    class BlockStorage:
        def get_snapshot(self, _snapshot_id):
            return SimpleNamespace(
                id="snapshot-a",
                name="backup-a",
                status="available",
                size=20,
                volume_id="volume-a",
                project_id="project-a",
            )

        def get_volume(self, volume_id):
            return SimpleNamespace(
                id=volume_id,
                name="data-a",
                status="available",
                size=20,
                project_id="project-b",
            )

    with pytest.raises(McpStorageError, match="ownership"):
        await get_project_snapshot(
            SimpleNamespace(block_storage=BlockStorage()),
            project_id="project-a",
            snapshot_id="snapshot-a",
        )


@pytest.mark.asyncio
async def test_backup_list_proves_parent_ownership_and_redacts_metadata():
    calls: list[tuple[str, object]] = []

    class BlockStorage:
        def backups(self, **kwargs):
            calls.append(("backups", kwargs))
            return [
                SimpleNamespace(
                    id="backup-a",
                    name="daily-a",
                    status="available",
                    size=20,
                    volume_id="volume-a",
                    project_id="project-a",
                    created_at="2026-07-27T00:00:00Z",
                    service_metadata={"credential": "secret"},
                )
            ]

        def get_volume(self, volume_id):
            calls.append(("get_volume", volume_id))
            return SimpleNamespace(
                id=volume_id,
                name="data-a",
                status="available",
                size=20,
                project_id="project-a",
            )

    result = await list_project_backups(SimpleNamespace(block_storage=BlockStorage()), project_id="project-a", limit=50)

    assert calls == [
        ("backups", {"details": True, "project_id": "project-a"}),
        ("get_volume", "volume-a"),
    ]
    assert result == [
        {
            "id": "backup-a",
            "name": "daily-a",
            "status": "available",
            "source_volume_id": "volume-a",
            "size_gb": 20,
            "created_at": "2026-07-27T00:00:00Z",
        }
    ]


@pytest.mark.asyncio
async def test_backup_get_rejects_foreign_backup_record():
    class BlockStorage:
        def get_backup(self, _backup_id):
            return SimpleNamespace(
                id="backup-a",
                name="daily-a",
                status="available",
                size=20,
                volume_id="volume-a",
                project_id="project-b",
            )

    with pytest.raises(McpStorageError, match="ownership"):
        await get_project_backup(
            SimpleNamespace(block_storage=BlockStorage()),
            project_id="project-a",
            backup_id="backup-a",
        )


@pytest.mark.asyncio
async def test_volume_delete_revalidates_available_owner_without_force():
    calls: list[tuple[str, object]] = []

    class BlockStorage:
        def get_volume(self, volume_id):
            calls.append(("get_volume", volume_id))
            return SimpleNamespace(
                id=volume_id,
                name="data-a",
                status="available",
                size=20,
                project_id="project-a",
            )

        def delete_volume(self, volume_id, **kwargs):
            calls.append(("delete_volume", (volume_id, kwargs)))

    conn = SimpleNamespace(block_storage=BlockStorage())
    preview = await preview_project_volume_delete(conn, project_id="project-a", volume_id="volume-a")
    result = await request_project_volume_delete(conn, project_id="project-a", volume_id="volume-a")

    assert preview["requested_action"] == "delete"
    assert result["requested_action"] == "delete"
    assert calls == [
        ("get_volume", "volume-a"),
        ("get_volume", "volume-a"),
        ("delete_volume", ("volume-a", {"ignore_missing": False, "force": False})),
    ]


@pytest.mark.asyncio
async def test_volume_delete_rejects_in_use_state_before_provider_call():
    calls: list[str] = []

    class BlockStorage:
        def get_volume(self, volume_id):
            return SimpleNamespace(
                id=volume_id,
                name="data-a",
                status="in-use",
                size=20,
                project_id="project-a",
            )

        def delete_volume(self, volume_id, **_kwargs):
            calls.append(volume_id)

    with pytest.raises(McpStorageError, match="state"):
        await request_project_volume_delete(
            SimpleNamespace(block_storage=BlockStorage()),
            project_id="project-a",
            volume_id="volume-a",
        )

    assert calls == []


@pytest.mark.asyncio
async def test_vm_volume_list_proves_owned_parent_attachment_and_child_volume():
    calls: list[tuple[str, object]] = []

    class Compute:
        def get_server(self, server_id):
            calls.append(("get_server", server_id))
            return SimpleNamespace(id=server_id, name="web-a", status="ACTIVE", project_id="project-a")

        def volume_attachments(self, server_id):
            calls.append(("volume_attachments", server_id))
            return [SimpleNamespace(volume_id="volume-a", device="/dev/vdb")]

    class BlockStorage:
        def get_volume(self, volume_id):
            calls.append(("get_volume", volume_id))
            return SimpleNamespace(
                id=volume_id,
                name="data-a",
                status="in-use",
                size=20,
                project_id="project-a",
                encryption_key_id="secret",
            )

    result = await list_project_server_volumes(
        SimpleNamespace(compute=Compute(), block_storage=BlockStorage()),
        project_id="project-a",
        server_id="server-a",
        limit=50,
    )

    assert result == [
        {
            "id": "volume-a",
            "name": "data-a",
            "status": "in-use",
            "size_gb": 20,
            "created_at": None,
        }
    ]
    assert calls == [
        ("get_server", "server-a"),
        ("volume_attachments", "server-a"),
        ("get_volume", "volume-a"),
    ]


@pytest.mark.asyncio
async def test_vm_volume_list_rejects_foreign_child_volume():
    class Compute:
        def get_server(self, server_id):
            return SimpleNamespace(id=server_id, name="web-a", status="ACTIVE", project_id="project-a")

        def volume_attachments(self, _server_id):
            return [SimpleNamespace(volume_id="volume-a")]

    class BlockStorage:
        def get_volume(self, volume_id):
            return SimpleNamespace(
                id=volume_id,
                name="data-a",
                status="in-use",
                size=20,
                project_id="project-b",
            )

    with pytest.raises(McpStorageError, match="ownership"):
        await list_project_server_volumes(
            SimpleNamespace(compute=Compute(), block_storage=BlockStorage()),
            project_id="project-a",
            server_id="server-a",
            limit=50,
        )


@pytest.mark.asyncio
async def test_snapshot_and_backup_delete_revalidate_owned_parent_without_force():
    calls: list[tuple[str, object]] = []

    class BlockStorage:
        def get_snapshot(self, snapshot_id):
            calls.append(("get_snapshot", snapshot_id))
            return SimpleNamespace(
                id=snapshot_id,
                name="snapshot-a",
                status="available",
                size=20,
                volume_id="volume-a",
                project_id="project-a",
            )

        def get_backup(self, backup_id):
            calls.append(("get_backup", backup_id))
            return SimpleNamespace(
                id=backup_id,
                name="backup-a",
                status="available",
                size=20,
                volume_id="volume-a",
                project_id="project-a",
            )

        def get_volume(self, volume_id):
            calls.append(("get_volume", volume_id))
            return SimpleNamespace(
                id=volume_id,
                name="data-a",
                status="available",
                size=20,
                project_id="project-a",
            )

        def delete_snapshot(self, snapshot_id, **kwargs):
            calls.append(("delete_snapshot", (snapshot_id, kwargs)))

        def delete_backup(self, backup_id, **kwargs):
            calls.append(("delete_backup", (backup_id, kwargs)))

    conn = SimpleNamespace(block_storage=BlockStorage())
    snapshot_preview = await preview_project_snapshot_delete(
        conn,
        project_id="project-a",
        snapshot_id="snapshot-a",
    )
    snapshot_result = await request_project_snapshot_delete(
        conn,
        project_id="project-a",
        snapshot_id="snapshot-a",
    )
    backup_preview = await preview_project_backup_delete(
        conn,
        project_id="project-a",
        backup_id="backup-a",
    )
    backup_result = await request_project_backup_delete(
        conn,
        project_id="project-a",
        backup_id="backup-a",
    )

    assert snapshot_preview["requested_action"] == "delete"
    assert snapshot_result["requested_action"] == "delete"
    assert backup_preview["requested_action"] == "delete"
    assert backup_result["requested_action"] == "delete"
    assert calls == [
        ("get_snapshot", "snapshot-a"),
        ("get_volume", "volume-a"),
        ("get_snapshot", "snapshot-a"),
        ("get_volume", "volume-a"),
        ("delete_snapshot", ("snapshot-a", {"ignore_missing": False, "force": False})),
        ("get_backup", "backup-a"),
        ("get_volume", "volume-a"),
        ("get_backup", "backup-a"),
        ("get_volume", "volume-a"),
        ("delete_backup", ("backup-a", {"ignore_missing": False, "force": False})),
    ]


class _VolumeCreateStore:
    """A principal-owned store with asynchronous creation and native tenant omission."""

    def __init__(self, *, include_owner=False):
        self.project_id = "project-a"
        self.include_owner = include_owner
        self.records = {}
        self.calls = []

    def create_volume(self, *, name, size, **attributes):
        self.calls.append(("create", attributes))
        volume_id = f"volume-{len(self.records) + 1}"
        record = {
            "id": volume_id,
            "name": name,
            "size": size,
            "status": "creating",
            "project_id": self.project_id,
            "created_at": "2026-10-11T00:00:00Z",
            "availability_zone": attributes.get("availability_zone", "native-default"),
            "encryption_key_id": "secret-key",
            "volume_image_metadata": {"password": "secret-password"},
            "metadata": {"token": "secret-token"},
        }
        self.records[volume_id] = record
        response = dict(record)
        if not self.include_owner:
            response.pop("project_id")
        return response

    def get_volume(self, volume_id):
        self.calls.append(("get", volume_id))
        return self.records.get(volume_id)

    def wait_for_status(self, *_args, **_kwargs):
        self.calls.append(("wait", None))
        raise AssertionError("creation must not wait for readiness")

    def delete_volume(self, *_args, **_kwargs):
        self.calls.append(("delete", None))
        raise AssertionError("creation must not roll back an uncertain result")


@pytest.mark.asyncio
@pytest.mark.parametrize("size_gb", [1, 16384])
async def test_volume_create_preview_validates_without_provider_access(size_gb):
    class NoProviderAccess:
        def __getattr__(self, _name):
            raise AssertionError("preview must not access a provider")

    result = await preview_project_volume_create(
        NoProviderAccess(),
        project_id="project-a",
        name="x" * 255,
        size_gb=size_gb,
        availability_zone="z" * 255,
    )

    assert result == {"name": "x" * 255, "size_gb": size_gb, "availability_zone": "z" * 255}


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", [preview_project_volume_create, request_project_volume_create])
@pytest.mark.parametrize(
    "invalid",
    [
        {"name": ""},
        {"name": " \t\n"},
        {"name": "x" * 256},
        {"name": None},
        {"name": 1},
        {"size_gb": 0},
        {"size_gb": -1},
        {"size_gb": 16385},
        {"size_gb": True},
        {"size_gb": False},
        {"size_gb": "20"},
        {"size_gb": 20.0},
        {"size_gb": None},
        {"availability_zone": ""},
        {"availability_zone": " \t\n"},
        {"availability_zone": "z" * 256},
        {"availability_zone": True},
        {"availability_zone": 1},
    ],
)
async def test_volume_create_invalid_inputs_never_touch_provider(operation, invalid):
    store = _VolumeCreateStore()
    arguments = {"name": "data-a", "size_gb": 20, "availability_zone": None, **invalid}

    with pytest.raises(McpStorageError):
        await operation(SimpleNamespace(block_storage=store), project_id="project-a", **arguments)

    assert store.records == {}
    assert store.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("include_owner", [False, True])
@pytest.mark.parametrize("availability_zone", [None, "zone-a"])
@pytest.mark.parametrize("size_gb", [1, 16384])
async def test_volume_create_accepts_one_owned_async_resource_without_waiting(
    include_owner, availability_zone, size_gb
):
    store = _VolumeCreateStore(include_owner=include_owner)
    conn = SimpleNamespace(block_storage=store)
    arguments = {"project_id": "project-a", "name": "data-a", "size_gb": size_gb}
    if availability_zone is not None:
        arguments["availability_zone"] = availability_zone

    preview = await preview_project_volume_create(conn, **arguments)
    assert store.calls == []
    assert preview == {"name": "data-a", "size_gb": size_gb, "availability_zone": availability_zone}
    result = await request_project_volume_create(conn, **arguments)

    assert result == {
        "id": "volume-1",
        "name": "data-a",
        "status": "creating",
        "size_gb": size_gb,
        "created_at": "2026-10-11T00:00:00Z",
        "requested_action": "create",
    }
    assert len(store.records) == 1
    created = store.records["volume-1"]
    assert created["project_id"] == "project-a"
    assert created["size"] == size_gb
    assert created["status"] == "creating"
    assert created["availability_zone"] == (availability_zone or "native-default")
    assert store.calls == [
        ("create", {} if availability_zone is None else {"availability_zone": availability_zone}),
        *([] if include_owner else [("get", "volume-1")]),
    ]
    assert "secret" not in repr(result)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fields",
    [
        {"project_id": "project-b"},
        {"project_id": ""},
        {"project_id": True},
        {"project_id": "project-a", "os-vol-tenant-attr:tenant_id": "project-b"},
        {"id": None},
        {"id": ""},
        {"id": "  "},
        {"status": None},
        {"status": 202},
        {"size": True},
        {"size": "20"},
        {"size": -1},
        {"name": {"password": "secret-password"}},
        {"created_at": {"password": "secret-password"}},
    ],
)
async def test_volume_create_rejects_unproven_or_malformed_response_without_deleting(fields):
    class Store(_VolumeCreateStore):
        def create_volume(self, **attributes):
            return {**super().create_volume(**attributes), **fields}

    store = Store(include_owner=True)
    with pytest.raises(McpStorageError) as failure:
        await request_project_volume_create(
            SimpleNamespace(block_storage=store), project_id="project-a", name="data-a", size_gb=20
        )

    assert "secret" not in str(failure.value)
    assert len(store.records) == 1
    assert store.calls == [("create", {})]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fields",
    [
        {"project_id": None},
        {"project_id": "project-b"},
        {"os-vol-tenant-attr:tenant_id": "project-b"},
        {"id": "unrelated-volume"},
        {"status": None},
        {"size": False},
    ],
)
async def test_volume_create_owner_lookup_cannot_invent_or_replace_created_record(fields):
    class Store(_VolumeCreateStore):
        def get_volume(self, volume_id):
            return {**super().get_volume(volume_id), **fields}

    store = Store()
    with pytest.raises(McpStorageError):
        await request_project_volume_create(
            SimpleNamespace(block_storage=store), project_id="project-a", name="data-a", size_gb=20
        )

    assert len(store.records) == 1
    assert store.calls == [("create", {}), ("get", "volume-1")]


@pytest.mark.asyncio
async def test_volume_create_missing_lookup_leaves_created_volume_untouched():
    class Store(_VolumeCreateStore):
        def get_volume(self, volume_id):
            super().get_volume(volume_id)
            return None

    store = Store()
    with pytest.raises(McpStorageError, match="not found"):
        await request_project_volume_create(
            SimpleNamespace(block_storage=store), project_id="project-a", name="data-a", size_gb=20
        )

    assert len(store.records) == 1
    assert store.calls == [("create", {}), ("get", "volume-1")]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_stage", ["create", "get"])
async def test_volume_create_sanitizes_upstream_failures_without_retry_or_rollback(failure_stage):
    class Store(_VolumeCreateStore):
        def create_volume(self, **attributes):
            response = super().create_volume(**attributes)
            if failure_stage == "create":
                raise RuntimeError("secret-password at https://user:secret-token@provider.invalid")
            return response

        def get_volume(self, volume_id):
            super().get_volume(volume_id)
            raise RuntimeError("secret-password at https://user:secret-token@provider.invalid")

    store = Store()
    with pytest.raises(McpStorageError, match="Cinder volume creation is unavailable") as failure:
        await request_project_volume_create(
            SimpleNamespace(block_storage=store), project_id="project-a", name="data-a", size_gb=20
        )

    assert "secret" not in str(failure.value)
    assert "provider.invalid" not in str(failure.value)
    assert len(store.records) == 1
    assert store.calls == [("create", {}), *([] if failure_stage == "create" else [("get", "volume-1")])]


@pytest.mark.asyncio
async def test_volume_create_fences_deadline_after_final_worker_validation(monkeypatch):
    store = _VolumeCreateStore()
    prepare = storage._prepare_volume_create
    validations = []

    def expire_after_validation(**arguments):
        result = prepare(**arguments)
        validations.append(result)
        call = sdk._current_call.get()
        assert call is not None
        call.deadline = 0
        return result

    monkeypatch.setattr(storage, "_prepare_volume_create", expire_after_validation)
    with sdk.sdk_deadline(60):
        with pytest.raises(McpStorageError, match="creation is unavailable"):
            await request_project_volume_create(
                SimpleNamespace(block_storage=store), project_id="project-a", name="data-a", size_gb=20
            )

    assert validations == [{"name": "data-a", "size_gb": 20, "availability_zone": None}]
    assert store.records == {}
    assert store.calls == []
