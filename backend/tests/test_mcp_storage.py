from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from keystoneauth1.session import Session
from keystoneauth1.token_endpoint import Token
from openstack.connection import Connection
from openstack.exceptions import BadRequestException

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


@pytest.fixture(params=["volume", "snapshot", pytest.param("backup", id="backup-owner-policy-override")])
def cinder_list_http(request):
    """Non-admin HTTP; backup ownership is visible only via explicit policy override."""
    kind = request.param
    plural = kind + "s"
    owner_key = {
        "volume": "os-vol-tenant-attr:tenant_id",
        "snapshot": "os-extended-snapshot-attributes:project_id",
        "backup": "os-backup-project-attr:project_id",
    }[kind]
    record = {
        "id": f"{kind}-a",
        "name": "data-a",
        "status": "available",
        "size": 20,
        "created_at": "2026-07-27T00:00:00Z",
        owner_key: "project-a",
        "metadata": {"credential": "secret"},
        "encryption_key_id": "secret",
        "service_metadata": "secret",
        "volume_image_metadata": {"credential": "secret"},
    }
    if kind != "volume":
        record["volume_id"] = "volume-a"
    state = SimpleNamespace(
        kind=kind,
        plural=plural,
        owner_key=owner_key,
        records=[record],
        parent={
            "id": "volume-a",
            "name": "parent",
            "status": "available",
            "size": 20,
            "os-vol-tenant-attr:tenant_id": "project-a",
        },
        requests=[],
        next_page=False,
        expose_backup_owner=True,
        is_admin=False,
    )
    root = "/v3"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def reply(self, status, body):
            payload = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            parsed = urlsplit(self.path)
            path = parsed.path.rstrip("/")
            if path in ("/v3", root):
                self.reply(
                    200,
                    {
                        "version": {
                            "id": "v3.0",
                            "status": "CURRENT",
                            "min_version": "3.0",
                            "version": "3.70",
                            "links": [{"rel": "self", "href": endpoint + "/v3/"}],
                        }
                    },
                )
                return
            query = parse_qs(parsed.query)
            microversion = self.headers.get("OpenStack-API-Version")
            state.requests.append((path, query, microversion))
            version = tuple(map(int, microversion.split()[-1].split("."))) if microversion else (3, 0)
            if self.headers.get("X-Auth-Token") != "synthetic-cinder-project-a":
                self.reply(401, {"unauthorized": {}})
            elif path == f"{root}/{plural}/detail":
                # Cinder RESOURCE_FILTER is 3.31; admins bypass its allowlist.
                # SDK wire version + query, not adapter kwargs, select failure.
                if "project_id" in query and not state.is_admin and version >= (3, 31):
                    self.reply(
                        400,
                        {
                            "badRequest": {
                                "code": 400,
                                "message": "Invalid filters project_id are found in query options.",
                            }
                        },
                    )
                    return
                records = state.records
                if kind == "backup" and not state.expose_backup_owner and not state.is_admin:
                    records = [{key: value for key, value in record.items() if key != owner_key} for record in records]
                body = {plural: records}
                if state.next_page:
                    body[plural + "_links"] = [{"rel": "next", "href": endpoint + path + "?marker=next-page"}]
                self.reply(200, body)
            elif path == f"{root}/volumes/volume-a":
                if state.parent is None:
                    self.reply(404, {"itemNotFound": {"message": "Volume not found"}})
                else:
                    self.reply(200, {"volume": state.parent})
            elif kind == "backup" and path == f"{root}/backups/backup-a":
                record = dict(state.records[0])
                if not state.expose_backup_owner and not state.is_admin:
                    record.pop(owner_key, None)
                self.reply(200, {"backup": record})
            else:
                self.reply(404, {"itemNotFound": {}})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    endpoint = f"http://127.0.0.1:{server.server_port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    conn = Connection(
        session=Session(auth=Token(endpoint=endpoint, token="synthetic-cinder-project-a")),
        block_storage_endpoint_override=endpoint + root,
        block_storage_api_version="3",
        connect_retries=0,
        api_timeout=2,
    )
    state.operation = {
        "volume": list_project_volumes,
        "snapshot": list_project_snapshots,
        "backup": list_project_backups,
    }[kind]
    try:
        yield conn, state
    finally:
        conn.close()
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


@pytest.mark.asyncio
async def test_cinder_lists_use_credential_scope_and_redact_native_details(cinder_list_http):
    conn, state = cinder_list_http
    result = await state.operation(conn, project_id="project-a", limit=50)

    expected = {
        "id": f"{state.kind}-a",
        "name": "data-a",
        "status": "available",
        "size_gb": 20,
        "created_at": "2026-07-27T00:00:00Z",
    }
    if state.kind != "volume":
        expected["source_volume_id"] = "volume-a"
    assert result == [expected]
    expected_requests = [(f"/v3/{state.plural}/detail", {})]
    if state.kind != "volume":
        expected_requests.append(("/v3/volumes/volume-a", {}))
    assert [(path, query) for path, query, _version in state.requests] == expected_requests
    if state.kind == "backup":
        assert tuple(map(int, state.requests[0][2].split()[-1].split("."))) >= (3, 18)


def test_cinder_sdk_project_filter_is_query_not_credential_scope(cinder_list_http):
    conn, state = cinder_list_http
    with pytest.raises(BadRequestException, match="Invalid filters project_id"):
        list(getattr(conn.block_storage, state.plural)(details=True, project_id="project-a"))

    assert [(path, query) for path, query, _version in state.requests] == [
        (f"/v3/{state.plural}/detail", {"project_id": ["project-a"]})
    ]
    assert tuple(map(int, state.requests[0][2].split()[-1].split("."))) >= (3, 31)


@pytest.mark.asyncio
@pytest.mark.parametrize("owner", [None, "project-b"], ids=["missing-owner", "foreign-owner"])
async def test_cinder_lists_reject_unproven_record_without_partial_result(cinder_list_http, owner):
    conn, state = cinder_list_http
    invalid_record = {**state.records[0], "id": f"{state.kind}-b"}
    if owner is None:
        invalid_record.pop(state.owner_key)
    else:
        invalid_record[state.owner_key] = owner
    state.records.append(invalid_record)

    with pytest.raises(McpStorageError, match=f"Cinder {state.kind} ownership cannot be proven"):
        await state.operation(conn, project_id="project-a", limit=50)

    assert sum(path.endswith("/detail") for path, _query, _version in state.requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("cinder_list_http", ["snapshot", "backup"], indirect=True)
@pytest.mark.parametrize("owner", [None, "project-b"], ids=["missing-owner", "foreign-owner"])
async def test_cinder_recovery_lists_require_parent_volume_ownership(cinder_list_http, owner):
    conn, state = cinder_list_http
    if owner is None:
        state.parent.pop("os-vol-tenant-attr:tenant_id")
    else:
        state.parent["os-vol-tenant-attr:tenant_id"] = owner

    with pytest.raises(McpStorageError, match="Cinder volume ownership cannot be proven"):
        await state.operation(conn, project_id="project-a", limit=50)

    assert [(path, query) for path, query, _version in state.requests] == [
        (f"/v3/{state.plural}/detail", {}),
        ("/v3/volumes/volume-a", {}),
    ]


@pytest.mark.asyncio
async def test_cinder_lists_keep_result_cap_without_fetching_next_page(cinder_list_http):
    conn, state = cinder_list_http
    state.records.append({**state.records[0], state.owner_key: "project-b"})
    state.next_page = True

    result = await state.operation(conn, project_id="project-a", limit=1)

    assert [record["id"] for record in result] == [f"{state.kind}-a"]
    assert len(state.requests) == (1 if state.kind == "volume" else 2)
    assert all(query == {} for _path, query, _version in state.requests)


@pytest.mark.asyncio
async def test_cinder_lists_return_empty_provider_result(cinder_list_http):
    conn, state = cinder_list_http
    state.records.clear()

    assert await state.operation(conn, project_id="project-a", limit=50) == []
    assert [(path, query) for path, query, _version in state.requests] == [(f"/v3/{state.plural}/detail", {})]


@pytest.mark.asyncio
@pytest.mark.parametrize("cinder_list_http", ["backup"], indirect=True)
@pytest.mark.parametrize("operation", ["list", "get"])
async def test_cinder_default_backup_policy_keeps_missing_owner_fail_closed(cinder_list_http, operation):
    conn, state = cinder_list_http
    state.expose_backup_owner = False

    with pytest.raises(McpStorageError, match="Cinder backup ownership cannot be proven"):
        if operation == "list":
            await list_project_backups(conn, project_id="project-a", limit=50)
        else:
            await get_project_backup(conn, project_id="project-a", backup_id="backup-a")

    path = "/v3/backups/detail" if operation == "list" else "/v3/backups/backup-a"
    assert [(request_path, query) for request_path, query, _version in state.requests] == [(path, {})]
    assert tuple(map(int, state.requests[0][2].split()[-1].split("."))) >= (3, 18)


@pytest.mark.asyncio
async def test_cinder_lists_do_not_dispatch_after_deadline(cinder_list_http):
    conn, state = cinder_list_http
    with sdk.sdk_deadline(0):
        with pytest.raises(McpStorageError, match="list is unavailable"):
            await state.operation(conn, project_id="project-a", limit=50)

    assert state.requests == []


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
