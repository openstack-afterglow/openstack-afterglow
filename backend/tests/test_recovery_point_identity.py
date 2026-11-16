"""Creator microversions and exact scheduler classification on real SDK HTTP reads."""

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import httpx
import pytest
from fastapi import FastAPI
from keystoneauth1.session import Session
from keystoneauth1.token_endpoint import Token
from openstack.connection import Connection

from app.api.deps import get_os_conn, get_token_info
from app.api.storage import volume_backups, volume_snapshots
from app.services import auto_backup, cinder

PROJECT = "project-a"
VOLUME = "volume-12345678"
STAMP = "20261116T030000Z"


def point(kind, tier):
    result = {
        "id": "point-a",
        "name": f"afterglow_auto{'_snapshot' if kind == 'snapshot' else ''}_{PROJECT}_{VOLUME}_{tier}_{STAMP}",
        "volume_id": VOLUME,
        "project_id": PROJECT,
        "user_id": "creator-a",
        "size": 10,
        "status": "available",
        "description": "",
        "created_at": "2026-11-16T03:00:00Z",
        "is_incremental": tier == "daily",
        "has_dependent_backups": False,
    }
    if kind == "snapshot":
        result["metadata"] = {
            "afterglow_policy_kind": "auto_snapshot",
            "afterglow_project_id": PROJECT,
            "afterglow_volume_id": VOLUME,
            "afterglow_tier": tier,
            "afterglow_revision": "revision-a",
            "afterglow_slot": f"afterglow:auto_snapshot:slot:{PROJECT}:{VOLUME}:2026-11-16T03:00:00+00:00",
        }
    return result


@pytest.mark.parametrize("kind", ["backup", "snapshot"])
@pytest.mark.parametrize("tier", ["daily", "weekly", "monthly"])
def test_classifier_uses_exact_scheduler_ownership(kind, tier):
    native = point(kind, tier)
    assert auto_backup.classify_recovery_point(native, PROJECT, resource=kind) == tier
    assert auto_backup.classify_recovery_point({**native, "name": "manual"}, PROJECT, resource=kind) is None
    assert auto_backup.classify_recovery_point({**native, "project_id": "foreign"}, PROJECT, resource=kind) is None
    assert auto_backup.classify_recovery_point({"name": native["name"]}, PROJECT, resource=kind) is None
    if kind == "snapshot":
        assert auto_backup.classify_recovery_point({**native, "metadata": {}}, PROJECT, resource=kind) is None
        assert (
            auto_backup.classify_recovery_point(
                {**native, "metadata": {**native["metadata"], "afterglow_slot": "other"}}, PROJECT, resource=kind
            )
            is None
        )


@pytest.fixture(
    params=[("backup", False), ("snapshot", False), ("backup", True), ("snapshot", True)],
    ids=["backup", "snapshot", "backup-owner-hidden", "snapshot-owner-hidden"],
)
def native_reader(request):
    kind, owner_hidden = request.param
    plural = kind + "s"
    calls = []
    record = point(kind, "daily")
    native = {**record}
    native.pop("project_id")
    if not owner_hidden:
        # DMS Lab's Cinder hides the owner attribute from member sessions (`rule:admin_api`).
        native[
            "os-backup-project-attr:project_id" if kind == "backup" else "os-extended-snapshot-attributes:project_id"
        ] = PROJECT

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            path = urlsplit(self.path).path.rstrip("/")
            calls.append((path, self.headers.get("OpenStack-API-Version")))
            if path in ("/v3", f"/v3/{PROJECT}"):
                body = {
                    "version": {
                        "id": "v3.0",
                        "status": "CURRENT",
                        "min_version": "3.0",
                        "version": "3.70",
                        "links": [{"rel": "self", "href": endpoint + "/v3/"}],
                    }
                }
            elif path.endswith("/detail"):
                body = {plural: [native]}
            else:
                body = {kind: native}
            payload = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    endpoint = f"http://127.0.0.1:{server.server_port}"
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    conn = Connection(
        session=Session(auth=Token(endpoint=endpoint, token="synthetic-local-only")),
        block_storage_endpoint_override=f"{endpoint}/v3/{PROJECT}",
        block_storage_api_version="3",
        api_timeout=2,
    )
    conn._afterglow_project_id = PROJECT
    conn._afterglow_authenticated_project_id = PROJECT
    conn.owner_hidden_for_test = owner_hidden
    try:
        yield kind, conn, calls
    finally:
        conn.close()
        server.shutdown()
        worker.join(timeout=5)
        server.server_close()


def test_list_get_explicit_creator_microversion_and_identity(native_reader):
    kind, conn, calls = native_reader
    original = conn.block_storage.default_microversion
    listed = getattr(cinder, f"list_{kind}s")(conn)
    detail = getattr(cinder, f"get_{kind}")(conn, "point-a")
    assert listed == [detail]
    assert detail["user_id"] == "creator-a"
    assert detail["origin"] == "auto"
    assert detail["auto_tier"] == "daily"
    expected = "volume 3.56" if kind == "backup" else "volume 3.41"
    reads = [version for path, version in calls if f"/{kind}s/" in path]
    assert reads == [expected, expected]
    assert conn.block_storage.default_microversion == original


@pytest.mark.asyncio
async def test_endpoint_list_get_preserve_recovery_identity(native_reader, monkeypatch):
    kind, conn, _ = native_reader
    module = volume_backups if kind == "backup" else volume_snapshots

    async def uncached(key, ttl, loader, **kwargs):
        assert "recovery-v2" in key
        return await asyncio.to_thread(loader)

    monkeypatch.setattr(module, "cached_call", uncached)
    app = FastAPI()
    base = "/backups" if kind == "backup" else "/snapshots"
    app.include_router(module.router, prefix=base)
    app.dependency_overrides[get_os_conn] = lambda: conn
    app.dependency_overrides[get_token_info] = lambda: {"project_id": PROJECT, "user_id": "creator-a"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        listed = await client.get(base)
        detail = await client.get(base + "/point-a")
    assert listed.status_code == detail.status_code == 200
    assert listed.json() == [detail.json()]
    assert detail.json()["user_id"] == "creator-a"
    assert detail.json()["origin"] == "auto"
    assert detail.json()["auto_tier"] == "daily"


def test_hidden_owner_is_filled_only_from_the_authenticated_project_of_own_project_reads(native_reader):
    kind, conn, _ = native_reader
    read = getattr(cinder, f"list_{kind}s")
    # Admin-target sessions carry a logical workspace that differs from the project the token is scoped to.
    conn._afterglow_project_id = "logical-workspace"
    own = read(conn)[0]
    assert own["origin"] == "auto" and own["auto_tier"] == "daily"
    assert own["project_id"] == PROJECT  # the token's project, never the logical workspace
    if not conn.owner_hidden_for_test:
        return
    # A cross-project read never trusts the caller's project for an owner Cinder did not show.
    cross = read(conn, all_projects=True)[0]
    assert cross["project_id"] is None and cross["origin"] == "manual" and cross["auto_tier"] is None
    # The logical workspace alone is not proof of ownership.
    del conn._afterglow_authenticated_project_id
    unproven = read(conn)[0]
    assert unproven["project_id"] is None and unproven["origin"] == "manual"


@pytest.mark.parametrize("kind", ["backup", "snapshot"])
def test_visible_foreign_owner_is_never_replaced_by_the_callers_project(kind):
    foreign = {**point(kind, "daily"), "project_id": "foreign-project"}
    assert cinder._recovery_origin(foreign, kind, PROJECT)["origin"] == "manual"
    hidden = {**point(kind, "daily"), "project_id": None}
    assert cinder._recovery_origin(hidden, kind, PROJECT)["origin"] == "auto"
    assert cinder._recovery_origin(hidden, kind, None)["origin"] == "manual"
