"""Behavior tests against a loopback provider and the real openstacksdk.

The provider is a test fixture, not a production fallback. No cloud credentials,
service identity substitution, monkeypatches, or MagicMock SDK calls are used.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest
import yaml
from fastapi import HTTPException
from keystoneauth1.noauth import NoAuth
from keystoneauth1.session import Session
from openstack.connection import Connection
from starlette.requests import Request

from app.api.union.layer_block_sources import verify_upload
from app.services import glance, layer_block

DATA = b"sealed squashfs fixture bytes"
DIGEST = "sha256:" + hashlib.sha256(DATA).hexdigest()
METADATA = {
    "afterglow_consume_id": "7",
    "afterglow_run_id": "a" * 32,
    "afterglow_project_id": "caller",
    "afterglow_volume_type_id": "type-rbd",
    "afterglow_volume_type_name": "ceph_hdd",
}


def block_entry():
    entry = {
        "id": 12,
        "parent_id": None,
        "chain_id": DIGEST,
        "blob_digest": DIGEST,
        "size_bytes": len(DATA),
        "is_sealed": True,
        "digest_state": "ready",
    }
    entry["block_source"] = {
        **layer_block.artifact_identity(entry),
        "state": "ready",
        "owner_project_id": "service",
        "member_project_ids": ["caller"],
        "upload_id": "e" * 32,
        "image_id": "11111111-1111-1111-1111-111111111111",
        "store_id": "rbd",
    }
    return entry


@pytest.fixture
def block_provider():
    """Importable fixture for parent lifecycle tests; yields conn, state, entry."""
    entry = block_entry()
    source = entry["block_source"]
    state = SimpleNamespace(
        project_id="caller",
        image={
            "id": source["image_id"],
            "owner": "service",
            "status": "active",
            "size": len(DATA),
            "disk_format": "raw",
            "container_format": "bare",
            "protected": True,
            "visibility": "shared",
            "stores": "rbd",
            **layer_block.source_properties(entry, source),
        },
        data=DATA,
        volumes={},
        ports={},
        servers={},
        extra_images={},
        payloads={},
        base_image={"id": "33333333-3333-3333-3333-333333333333", "name": "ubuntu-24.04", "status": "active"},
        server_rejection=None,
        lose_server_response=False,
        guest_failure=False,
        calls=[],
        readonly_denied=False,
        readonly_applied=True,
        stores=[{"id": "rbd", "type": "rbd"}],
        members=[],
        volume_type={"id": "type-rbd", "name": "ceph_hdd", "extra_specs": {"multiattach": "<is> False"}},
        volume_status="available",
        quotas={
            "volumes": {"limit": 20, "in_use": 0, "reserved": 0},
            "gigabytes": {"limit": 256, "in_use": 0, "reserved": 0},
        },
    )

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def send(self, payload, code=200):
            raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
            self.send_response(code)
            self.send_header(
                "Content-Type", "application/octet-stream" if isinstance(payload, bytes) else "application/json"
            )
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            state.calls.append(("GET", self.path))
            path = self.path.split("?")[0].rstrip("/")
            if path in ("/volume", "/image", "/compute", "/network"):
                version = {"/volume": "v3.0", "/image": "v2.0", "/compute": "v2.1", "/network": "v2.0"}[path]
                self.send(
                    {
                        "version": {
                            "id": version,
                            "status": "CURRENT",
                            "min_version": "3.0" if version == "v3.0" else "2.0",
                            "version": "3.71" if version == "v3.0" else "2.0",
                            "links": [{"rel": "self", "href": base + path + "/"}],
                        }
                    }
                )
            elif "/os-quota-sets/" in path:
                self.send({"quota_set": state.quotas})
            elif path.endswith("/types/default"):
                self.send({"volume_type": state.volume_type})
            elif path.endswith("/info/stores/detail"):
                self.send({"stores": state.stores})
            elif path.endswith("/members"):
                self.send({"members": state.members})
            elif path.endswith("/file"):
                self.send(state.payloads.get(path.split("/")[-2], state.data))
            elif "/images/" in path:
                image_id = path.rsplit("/", 1)[-1]
                image = state.extra_images.get(image_id)
                if image_id == state.base_image["id"]:
                    image = state.base_image
                elif state.image is not None and image_id == state.image["id"]:
                    image = state.image
                self.send(image or {}, 200 if image else 404)
            elif path.endswith(("/servers/detail", "/servers")):
                self.send({"servers": list(state.servers.values())})
            elif path.endswith("/ports"):
                self.send({"ports": list(state.ports.values())})
            elif path.endswith("/floatingips"):
                self.send({"floatingips": []})
            elif path.endswith(("/volumes/detail", "/volumes")):
                self.send({"volumes": list(state.volumes.values())})
            elif "/servers/" in path or "/ports/" in path:
                kind = "servers" if "/servers/" in path else "ports"
                resource = getattr(state, kind).get(path.rsplit("/", 1)[-1])
                self.send({kind[:-1]: resource} if resource else {}, 200 if resource else 404)
            elif "/volumes/" in path:
                volume = state.volumes.get(path.rsplit("/", 1)[-1])
                self.send({"volume": volume} if volume else {}, 200 if volume else 404)
            else:
                self.send({}, 404)

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            state.calls.append(("POST", self.path, payload))
            if self.path.rstrip("/").endswith("/volumes"):
                request = payload["volume"]
                volume_id = f"22222222-2222-2222-2222-{len(state.volumes) + 1:012d}"
                source_image = state.extra_images.get(request.get("imageRef"), state.image)
                volume = {
                    **request,
                    "id": volume_id,
                    "status": state.volume_status,
                    "attachments": [],
                    "os-vol-tenant-attr:tenant_id": "caller",
                    "multiattach": False,
                    "snapshot_id": None,
                    "source_volid": None,
                    "volume_type": state.volume_type["name"],
                    "volume_type_id": request["volume_type"],
                    "volume_image_metadata": {**source_image, "image_id": source_image["id"]},
                }
                state.volumes[volume_id] = volume
                self.send({"volume": volume}, 202)
            elif self.path.rstrip("/").endswith("/ports"):
                port_id = "44444444-4444-4444-4444-444444444444"
                port = {
                    **payload["port"],
                    "id": port_id,
                    "project_id": state.project_id,
                    "device_id": "",
                    "fixed_ips": [{"ip_address": "10.0.0.5"}],
                }
                state.ports[port_id] = port
                self.send({"port": port}, 201)
            elif self.path.rstrip("/").endswith("/servers"):
                if state.server_rejection:
                    self.send({"error": {"message": "provider rejected CREATE"}}, state.server_rejection)
                    return
                request = payload["server"]
                server_id = "55555555-5555-5555-5555-555555555555"
                server = {**request, "id": server_id, "tenant_id": state.project_id, "status": "ACTIVE"}
                config = yaml.safe_load(base64.b64decode(request["user_data"]))
                scripts = "\n".join(base64.b64decode(item["content"]).decode() for item in config["write_files"])
                token = re.search(r"::AFTERGLOW::SUCCESS::([0-9a-f]{32})", scripts)[1]
                server["console"] = f"::AFTERGLOW::{'FAILURE' if state.guest_failure else 'SUCCESS'}::{token}"
                state.servers[server_id] = server
                for mapping in request.get("block_device_mapping_v2", []):
                    if mapping["source_type"] == "volume":
                        state.volumes[mapping["uuid"]].update(status="in-use", attachments=[{"server_id": server_id}])
                for network in request["networks"]:
                    state.ports[network["port"]]["device_id"] = server_id
                if state.lose_server_response:
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.connection.close()
                    return
                self.send({"server": server}, 202)
            elif "/servers/" in self.path and self.path.endswith("/action"):
                server = state.servers[self.path.split("/")[-2]]
                self.send({"output": server["console"]})
            elif self.path.rstrip("/").endswith("/images"):
                state.image = {**payload, "owner": "service", "status": "queued", "size": None}
                self.send(state.image, 201)
            elif self.path.endswith("/members"):
                member = {"member_id": payload["member"], "status": "pending"}
                state.members.append(member)
                self.send(member, 200)
            elif self.path.endswith("/action"):
                if state.readonly_denied:
                    self.send({"forbidden": "readonly denied"}, 403)
                    return
                assert payload == {"os-update_readonly_flag": {"readonly": True}}
                volume = state.volumes[self.path.split("/")[-2]]
                if state.readonly_applied:
                    volume["metadata"]["readonly"] = "True"
                self.send({}, 202)
            else:
                self.send({}, 404)

        def do_DELETE(self):
            state.calls.append(("DELETE", self.path))
            kind = next(kind for kind in ("servers", "volumes", "ports") if f"/{kind}/" in self.path)
            resource_id = self.path.rsplit("/", 1)[-1]
            getattr(state, kind).pop(resource_id, None)
            if kind == "servers":
                for volume in state.volumes.values():
                    volume.update(attachments=[], status="available")
                for port in state.ports.values():
                    if port["device_id"] == resource_id:
                        port["device_id"] = ""
            self.send({}, 204)

        def do_PUT(self):
            raw = self.rfile.read(int(self.headers["Content-Length"]))
            state.calls.append(("PUT", self.path, dict(self.headers)))
            assert self.path.endswith("/file")
            state.data = raw
            state.image.update(status="active", size=len(raw), stores=self.headers["X-Image-Meta-Store"])
            self.send({}, 204)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    base = f"http://127.0.0.1:{server.server_port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    class FixtureScope(NoAuth):
        def get_project_id(self, _session):
            return state.project_id

    conn = Connection(
        session=Session(auth=FixtureScope()),
        auth_type="none",
        block_storage_endpoint_override=base + "/volume",
        block_storage_api_version="3",
        image_endpoint_override=base + "/image",
        image_api_version="2",
        compute_endpoint_override=base + "/compute",
        compute_api_version="2",
        network_endpoint_override=base + "/network",
        network_api_version="2",
        api_timeout=3,
    )
    conn._afterglow_project_id = "caller"
    try:
        yield conn, state, entry
    finally:
        conn.close()
        server.shutdown()
        server.server_close()
        thread.join()


def test_allocate_returns_before_prepare_and_readonly_is_get_verified(block_provider):
    conn, state, entry = block_provider
    allocated = conn.block_storage.create_volume(
        **layer_block.layer_volume_create_options(conn, entry, "exclusive-layer", METADATA)
    )
    assert allocated.id in state.volumes
    assert not any(call[1].endswith("/action") for call in state.calls)
    assert state.volumes[allocated.id]["imageRef"] == entry["block_source"]["image_id"]
    ready = layer_block.prepare_layer_volume(conn, allocated.id, entry, METADATA)
    assert ready["metadata"]["readonly"] == "True"
    assert state.calls[-1] == ("GET", "/volume/volumes/" + allocated.id)
    assert state.image["protected"] is True


@pytest.mark.parametrize(
    "field,value",
    [
        ("owner", "foreign"),
        ("afterglow_layer_digest", "sha256:" + "0" * 64),
        ("afterglow_layer_parent_id", "99"),
        ("protected", False),
    ],
)
def test_foreign_or_changed_source_fails_before_allocation(block_provider, field, value):
    conn, state, entry = block_provider
    state.image[field] = value
    with pytest.raises(ValueError):
        conn.block_storage.create_volume(**layer_block.layer_volume_create_options(conn, entry, "bad", METADATA))
    assert state.volumes == {}


def test_wrong_source_bytes_fail_even_with_matching_metadata(block_provider):
    conn, state, entry = block_provider
    state.data = b"x" * len(DATA)
    with pytest.raises(ValueError, match="source bytes differ"):
        layer_block.validate_sources(conn, [entry])
    assert state.volumes == {}


@pytest.mark.parametrize("mode", ["denied", "not-applied"])
def test_readonly_denial_never_returns_success(block_provider, mode):
    conn, state, entry = block_provider
    allocated = conn.block_storage.create_volume(
        **layer_block.layer_volume_create_options(conn, entry, "layer", METADATA)
    )
    state.readonly_denied = mode == "denied"
    state.readonly_applied = mode != "not-applied"
    with pytest.raises(Exception):
        layer_block.prepare_layer_volume(conn, allocated.id, entry, METADATA)
    assert allocated.id in state.volumes  # parent retains durable cleanup identity
    assert state.volumes[allocated.id]["metadata"].get("readonly") is None


@pytest.mark.parametrize("change", ["owner", "source", "attached", "multiattach", "size", "digest"])
def test_volume_lineage_and_exclusivity_fail_closed(block_provider, change):
    conn, state, entry = block_provider
    allocated = conn.block_storage.create_volume(
        **layer_block.layer_volume_create_options(conn, entry, "layer", METADATA)
    )
    volume = state.volumes[allocated.id]
    if change == "owner":
        volume["os-vol-tenant-attr:tenant_id"] = "foreign"
    elif change == "source":
        volume["volume_image_metadata"]["image_id"] = "foreign"
    elif change == "attached":
        volume["attachments"] = [{"server_id": "other"}]
    elif change == "multiattach":
        volume["multiattach"] = True
    elif change == "size":
        volume["size"] = 2
    else:
        volume["volume_image_metadata"]["afterglow_layer_digest"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError):
        layer_block.prepare_layer_volume(conn, allocated.id, entry, METADATA)
    assert not any(call[1].endswith("/action") for call in state.calls)


def test_error_readiness_never_sets_readonly(block_provider):
    conn, state, entry = block_provider
    state.volume_status = "error"
    allocated = conn.block_storage.create_volume(
        **layer_block.layer_volume_create_options(conn, entry, "layer", METADATA)
    )
    with pytest.raises(Exception):
        layer_block.prepare_layer_volume(conn, allocated.id, entry, METADATA)
    assert not any(call[1].endswith("/action") for call in state.calls)


def test_quota_reservations_and_bounds(block_provider):
    conn, state, entry = block_provider
    plan = layer_block.plan_volumes(conn, [entry], True, 8)
    assert plan == {
        "layer_sizes_gb": [1],
        "upper_gb": 8,
        "volume_count": 2,
        "total_gb": 9,
        "disk_count": 4,
        "volume_type_id": "type-rbd",
        "volume_type_name": "ceph_hdd",
    }
    state.quotas["volumes"]["reserved"] = 19
    with pytest.raises(ValueError, match="volumes quota"):
        layer_block.plan_volumes(conn, [entry], True, 8)
    with pytest.raises(ValueError, match="24 total disks"):
        layer_block.plan_volumes(conn, [entry] * 23, False, 0)
    with pytest.raises(ValueError, match="256 GiB"):
        layer_block.plan_volumes(conn, [entry], True, 256)
    entry["size_bytes"] = 65 * layer_block.GIB
    with pytest.raises(ValueError, match="64 GiB"):
        layer_block.plan_volumes(conn, [entry], False, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [b"wrong digest same length!!!!", DATA[:-1], DATA + b"extra"])
async def test_upload_verifies_before_any_provider_allocation(body):
    delivered = False

    async def receive():
        nonlocal delivered
        assert not delivered
        delivered = True
        return {"type": "http.request", "body": body, "more_body": False}

    request = Request({"type": "http", "method": "PUT", "path": "/", "headers": []}, receive)
    with pytest.raises(HTTPException) as error:
        await verify_upload(request, io.BytesIO(), block_entry())
    assert error.value.status_code == 422


@pytest.mark.asyncio
async def test_correct_upload_is_rewound():
    async def receive():
        return {"type": "http.request", "body": DATA, "more_body": False}

    output = io.BytesIO()
    request = Request({"type": "http", "method": "PUT", "path": "/", "headers": []}, receive)
    await verify_upload(request, output, block_entry())
    assert output.read() == DATA


def test_glance_stream_verification_rejects_wrong_length(block_provider):
    conn, state, entry = block_provider
    state.data += b"excess"
    with pytest.raises(ValueError, match="length exceeds"):
        glance.verify_source_bytes(conn, entry["block_source"]["image_id"], DIGEST, len(DATA))


@pytest.mark.parametrize("change", ["missing-parent", "cycle", "duplicate", "forged-chain"])
def test_full_lineage_rejected_before_cloud_reads(block_provider, change):
    conn, state, entry = block_provider
    entries = [entry]
    if change == "missing-parent":
        entry["parent_id"] = 11
    elif change == "cycle":
        entry["parent_id"] = entry["id"]
    elif change == "duplicate":
        entries.append(dict(entry))
    else:
        entry["chain_id"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError):
        layer_block.validate_sources(conn, entries)
    assert state.calls == []


def test_explicit_rbd_store_upload_and_live_store_assertion(block_provider):
    conn, state, entry = block_provider
    source = entry["block_source"]
    glance.validate_rbd_store(conn, source["store_id"])
    glance.allocate_source_image(conn, source["image_id"], "sealed", layer_block.source_properties(entry, source))
    glance.upload_source_image(conn, source["image_id"], io.BytesIO(DATA), len(DATA), source["store_id"])
    layer_block.validate_source_image(entry, source, glance.get_source_image(conn, source["image_id"]))
    upload = next(call for call in state.calls if call[0] == "PUT")
    assert upload[2]["X-Image-Meta-Store"] == "rbd"
    state.image["stores"] = "other"
    with pytest.raises(ValueError, match="selected Glance store"):
        layer_block.validate_sources(conn, [entry])


def test_non_rbd_store_and_multiattach_default_rejected(block_provider):
    conn, state, entry = block_provider
    state.stores[0]["type"] = "cinder"
    with pytest.raises(ValueError, match="RBD store"):
        glance.validate_rbd_store(conn, "rbd")
    state.volume_type["extra_specs"]["multiattach"] = "<is> True"
    with pytest.raises(ValueError, match="exclusive default"):
        layer_block.plan_volumes(conn, [entry], False, 0)


@pytest.mark.parametrize("method", ["PUT", "GET"])
def test_publication_route_rejects_unauthenticated_requests(method):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.union.layer_block_sources import router

    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        response = client.request(method, "/artifacts/12/block-source?store_id=rbd", content=DATA)
    assert response.status_code == 401


@pytest.mark.parametrize("resource", ["volumes", "gigabytes"])
def test_typed_quota_reservations_reject_before_allocate(block_provider, resource):
    conn, state, entry = block_provider
    state.quotas[f"{resource}_ceph_hdd"] = {"limit": 2, "in_use": 0, "reserved": 2}
    with pytest.raises(ValueError, match=f"{resource}_ceph_hdd quota"):
        layer_block.plan_volumes(conn, [entry], False, 0)
    assert state.volumes == {}


@pytest.mark.parametrize("field,value", [("volume_type", "foreign-type"), ("volume_type_id", "foreign-id")])
def test_wrong_pinned_volume_type_fails_before_readonly(block_provider, field, value):
    conn, state, entry = block_provider
    allocated = conn.block_storage.create_volume(
        **layer_block.layer_volume_create_options(conn, entry, "layer", METADATA)
    )
    state.volumes[allocated.id][field] = value
    with pytest.raises(ValueError, match="volume type"):
        layer_block.prepare_layer_volume(conn, allocated.id, entry, METADATA)
    assert not any(call[1].endswith("/action") for call in state.calls)


def test_authenticated_project_needs_no_marker(block_provider):
    conn, state, _ = block_provider
    del conn._afterglow_project_id
    assert layer_block.project_id(conn, expected="caller") == "caller"
    assert state.calls == []


@pytest.mark.parametrize("change", ["marker", "expected", "unscoped"])
def test_foreign_or_unscoped_project_rejected_before_provider_mutation(block_provider, change):
    conn, state, _ = block_provider
    expected = "caller"
    if change == "marker":
        conn._afterglow_project_id = "foreign"
    elif change == "expected":
        expected = "foreign"
    else:
        state.project_id = None
    with pytest.raises(ValueError):
        layer_block.project_id(conn, expected=expected)
    assert state.calls == []
