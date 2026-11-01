"""Exact configured aliases and conservative, read-only Placement PCI discovery."""

import asyncio
import copy
import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from keystoneauth1 import session as native_session
from keystoneauth1 import token_endpoint

from app.api.deps import require_admin
from app.main import app
from app.services import pci_device_inventory as svc

GPU = "CUSTOM_PCI_10DE_2204"
AUDIO = "CUSTOM_PCI_10DE_1AEF"
UNKNOWN = "CUSTOM_PCI_ABCD_0123"


def alias(name="Exact-RTX-3090", vendor="10de", product="2204", **kwargs):
    return {
        "name": name,
        "vendor_id": vendor,
        "product_id": product,
        "resource_class": None,
        "device_type": None,
        "traits": None,
        "numa_policy": None,
        **kwargs,
    }


def controller(host="controller-a", aliases=None, **kwargs):
    return {
        "host": host,
        "state": "ready",
        "observed_at": "2026-10-30T00:00:00+00:00",
        "aliases": [alias()] if aliases is None else aliases,
        **kwargs,
    }


def snapshot(*controllers):
    return {"schema_version": 1, "source": "nova_api_config", "controllers": list(controllers)}


def provider(identity, name, parent=None, root="root"):
    return {"uuid": identity, "name": name, "parent_provider_uuid": parent, "root_provider_uuid": root}


class Response:
    def __init__(self, body, status=200, headers=None):
        self.status_code = status
        self.content = json.dumps(body).encode()
        self.headers = {"Content-Length": str(len(self.content))} if headers is None else headers
        self.closed = False

    def iter_content(self, chunk_size):
        for position in range(0, len(self.content), chunk_size):
            yield self.content[position : position + chunk_size]

    def close(self):
        self.closed = True


class Placement:
    def __init__(self):
        self.calls = []
        self.providers = [
            provider("root", "compute-a"),
            provider("gpu", "compute-a_0000:03:00.0", "root"),
            provider("audio", "compute-a_0000:03:00.1", "root"),
            provider("unknown", "compute-a_0000:04:00.0", "root"),
        ]
        self.inventories = {
            "root": {"VCPU": {"total": 8, "reserved": 0}},
            "gpu": {GPU: {"total": 1, "reserved": 0}},
            "audio": {AUDIO: {"total": 1, "reserved": 0}},
            "unknown": {UNKNOWN: {"total": 4, "reserved": 1}},
        }
        self.usages = {"gpu": {GPU: 1}, "audio": {AUDIO: 1}, "unknown": {UNKNOWN: 0}}
        self.failures = {}
        self.links = []
        self.conn = SimpleNamespace(
            placement=SimpleNamespace(get_endpoint=lambda: "https://placement.invalid"), session=self
        )

    def get(self, url, **kwargs):
        path = url.removeprefix("https://placement.invalid")
        self.calls.append((path, kwargs))
        value = self.failures.get(path)
        if isinstance(value, Exception):
            raise value
        if value is not None:
            return Response({"secret": "native traceback /private/token"}, status=value)
        if path == "/resource_providers":
            body = {"resource_providers": self.providers, "resource_providers_links": self.links}
        else:
            _, _, identity, operation = path.split("/")
            body = {operation: getattr(self, operation)[identity]}
        return Response(body)


@pytest.fixture
def environment(monkeypatch, tmp_path):
    path = tmp_path / "aliases.json"
    path.write_text(json.dumps(snapshot(controller())))
    monkeypatch.setattr(svc, "ALIAS_SNAPSHOT_PATH", path)
    policy = {
        "gpu_profiles": [
            {
                "name": "3090",
                "enabled": False,
                "resource_class": GPU,
                "resource_requirements": {GPU: 1, AUDIO: 1},
                "alias_resource_classes": {"Exact-RTX-3090": GPU, "Exact-Audio": AUDIO},
            }
        ],
    }
    monkeypatch.setattr(svc.flavor_automation_policy, "load_policy", AsyncMock(return_value=policy))
    return SimpleNamespace(path=path, native=Placement(), policy=policy)


@pytest.mark.asyncio
async def test_exact_aliases_and_all_placement_devices_with_allocations_and_mappings(environment):
    env = environment
    env.path.write_text(
        json.dumps(
            snapshot(
                controller(
                    aliases=[
                        alias(),
                        alias("Exact-Audio", product="1aef"),
                        alias("Configured-No-Inventory", product="2684"),
                    ]
                )
            )
        )
    )
    result = await svc.discover(env.native.conn)
    assert result["alias_source"]["state"] == "ready"
    aliases = {row["name"]: row for row in result["aliases"]}
    assert set(aliases) == {"Exact-RTX-3090", "Exact-Audio", "Configured-No-Inventory"}
    assert aliases["Exact-RTX-3090"] == {
        "name": "Exact-RTX-3090",
        "vendor_id": "10DE",
        "product_id": "2204",
        "resource_class": GPU,
        "kind": "gpu",
        "device_name": "RTX 3090",
        "selectable": True,
        "mapped_groups": ["3090"],
    }
    assert aliases["Exact-Audio"]["kind"] == "audio"
    assert aliases["Configured-No-Inventory"]["mapped_groups"] == []
    devices = {row["resource_class"]: row for row in result["inventory"]["devices"]}
    assert result["inventory"]["state"] == "ready" and result["inventory"]["errors"] == []
    assert devices[GPU]["used"] == devices[AUDIO]["used"] == 1
    assert devices[GPU]["mapped_groups"] == devices[AUDIO]["mapped_groups"] == ["3090"]
    assert devices[UNKNOWN]["used"] == 0 and devices[UNKNOWN]["mapped_groups"] == []
    assert devices[UNKNOWN]["kind"] == "unknown" and devices[UNKNOWN]["reserved"] == 1
    assert devices[GPU]["pci_address"] == "0000:03:00.0"
    assert all(row["host"] == "compute-a" for row in devices.values())


@pytest.mark.asyncio
async def test_fresh_catalog_classification_is_consistent_after_remote_updates_and_deletion(environment, monkeypatch):
    from app import database
    from app.services import gpu_catalog, gpu_inventory

    environment.path.write_text(
        json.dumps(snapshot(controller(aliases=[alias("Remote-device", vendor="abcd", product="0123")])))
    )
    monkeypatch.setattr(database, "is_db_configured", lambda: True)
    monkeypatch.setattr(database, "is_db_available", lambda: True)
    monkeypatch.setattr(gpu_inventory, "PCI_DEVICE_MAP", {"ABCD": {"0123": {"name": "old GPU", "is_audio": False}}})
    catalog = AsyncMock(
        return_value=[{"vendor_id": "ABCD", "device_id": "0123", "name": "Current audio", "is_audio": True}]
    )
    monkeypatch.setattr(gpu_catalog, "list_db_devices", catalog)

    result = await svc.discover(environment.native.conn)
    assert result["aliases"][0]["kind"] == "audio" and result["aliases"][0]["device_name"] == "Current audio"
    assert next(row for row in result["inventory"]["devices"] if row["resource_class"] == UNKNOWN)["kind"] == "audio"

    catalog.return_value = []
    result = await svc.discover(environment.native.conn)
    assert result["aliases"][0]["kind"] == "unknown" and result["aliases"][0]["device_name"] is None
    assert next(row for row in result["inventory"]["devices"] if row["resource_class"] == UNKNOWN)["kind"] == "unknown"


@pytest.mark.asyncio
async def test_catalog_read_failure_does_not_reuse_stale_classification(environment, monkeypatch):
    from app import database
    from app.services import gpu_catalog, gpu_inventory

    environment.path.write_text(
        json.dumps(
            snapshot(controller(aliases=[alias("Remote-device", vendor="abcd", product="0123"), alias("Named-audio")]))
        )
    )
    monkeypatch.setattr(database, "is_db_configured", lambda: True)
    monkeypatch.setattr(database, "is_db_available", lambda: True)
    monkeypatch.setattr(gpu_inventory, "PCI_DEVICE_MAP", {"ABCD": {"0123": {"name": "old GPU", "is_audio": False}}})
    monkeypatch.setattr(gpu_catalog, "list_db_devices", AsyncMock(side_effect=RuntimeError("private catalog error")))

    result = await svc.discover(environment.native.conn)
    assert all(row["kind"] == "unknown" and row["device_name"] is None for row in result["aliases"])
    assert next(row for row in result["inventory"]["devices"] if row["resource_class"] == UNKNOWN)["kind"] == "unknown"
    assert "private catalog error" not in json.dumps(result)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [503, RuntimeError("/private/token native traceback")])
async def test_usage_failure_is_unknown_not_zero(environment, failure):
    environment.native.failures["/resource_providers/gpu/usages"] = failure
    result = await svc.discover(environment.native.conn)
    inventory = result["inventory"]
    assert inventory["state"] == "partial"
    gpu = next(row for row in inventory["devices"] if row["resource_class"] == GPU)
    assert gpu["used"] is None and gpu["mapped_groups"] == ["3090"]
    assert inventory["errors"] and "/private" not in json.dumps(result) and "traceback" not in json.dumps(result)


@pytest.mark.asyncio
@pytest.mark.parametrize("usage", [{}, {GPU: None}, {GPU: -1}, {GPU: True}, {GPU: 1.5}, []])
async def test_malformed_or_missing_usage_never_becomes_zero(environment, usage):
    environment.native.usages["gpu"] = usage
    inventory = (await svc.discover(environment.native.conn))["inventory"]
    assert inventory["state"] == "partial"
    assert next(row for row in inventory["devices"] if row["resource_class"] == GPU)["used"] is None


@pytest.mark.asyncio
async def test_provider_directory_failure_does_not_claim_empty_ready_inventory(environment):
    environment.native.failures["/resource_providers"] = 403
    result = await svc.discover(environment.native.conn)
    assert result["inventory"]["state"] == "unavailable"
    assert result["inventory"]["devices"] == [] and result["inventory"]["errors"]
    assert result["alias_source"]["state"] == "ready" and result["aliases"]


@pytest.mark.asyncio
async def test_partial_inventory_retains_unaffected_devices_and_detects_pagination(environment):
    native = environment.native
    native.links = [{"rel": "next", "href": "https://untrusted.invalid/secret"}]
    native.failures["/resource_providers/audio/inventories"] = 500
    result = await svc.discover(native.conn)
    assert result["inventory"]["state"] == "partial"
    assert {row["resource_class"] for row in result["inventory"]["devices"]} == {GPU, UNKNOWN}
    assert "untrusted" not in json.dumps(result)


@pytest.mark.asyncio
@pytest.mark.parametrize("broken", ["orphan", "cycle", "root_mismatch", "duplicate", "missing_parent_field"])
async def test_provider_ownership_joins_fail_closed(environment, broken):
    native = environment.native
    gpu = native.providers[1]
    if broken == "orphan":
        gpu["parent_provider_uuid"] = "absent"
    elif broken == "cycle":
        gpu["parent_provider_uuid"] = "gpu"
    elif broken == "root_mismatch":
        gpu["root_provider_uuid"] = "audio"
    elif broken == "duplicate":
        native.providers.append(copy.deepcopy(gpu))
    else:
        del gpu["parent_provider_uuid"]
    result = await svc.discover(native.conn)
    assert result["inventory"]["state"] == "partial"
    assert GPU not in {row["resource_class"] for row in result["inventory"]["devices"]}
    assert AUDIO in {row["resource_class"] for row in result["inventory"]["devices"]}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name", ["compute-a_0000:03:20.0", "compute-a_0000:03:00.8", "other_0000:03:00.0", "not-a-bdf"]
)
async def test_pci_address_is_only_a_valid_host_matched_provider_suffix(environment, name):
    environment.native.providers[1]["name"] = name
    inventory = (await svc.discover(environment.native.conn))["inventory"]
    row = next(row for row in inventory["devices"] if row["resource_class"] == GPU)
    assert row["pci_address"] is None and row["host"] == "compute-a"


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [{"total": True}, {"total": -1}, {"reserved": 2}, {"reserved": None}])
async def test_invalid_inventory_is_partial_not_zero(environment, change):
    environment.native.inventories["gpu"][GPU].update(change)
    inventory = (await svc.discover(environment.native.conn))["inventory"]
    assert inventory["state"] == "partial"
    assert GPU not in {row["resource_class"] for row in inventory["devices"]}


def test_missing_unreadable_malformed_snapshot_is_unavailable(environment, monkeypatch):
    env = environment
    env.path.unlink()
    assert svc._read_aliases()[0]["state"] == "unavailable"
    for content in ("{invalid", "[]", '{"schema_version":1,"schema_version":1}', json.dumps(snapshot())):
        env.path.write_text(content)
        assert svc._read_aliases() == (
            {
                "state": "unavailable",
                "source": "nova_api_config",
                "observed_at": None,
                "message": "Nova PCI alias snapshot is unavailable.",
            },
            [],
        )
    monkeypatch.setattr(svc.os, "open", lambda *_args: (_ for _ in ()).throw(PermissionError("/secret/path")))
    assert "/secret" not in json.dumps(svc._read_aliases())


def test_snapshot_rejects_symlinks(environment, tmp_path):
    original = tmp_path / "source"
    original.write_text(environment.path.read_text())
    environment.path.unlink()
    environment.path.symlink_to(original)
    assert svc._read_aliases()[0]["state"] == "unavailable"


@pytest.mark.parametrize(
    "other",
    [
        controller("controller-b", aliases=[], state="unavailable"),
        controller("controller-b", aliases=[alias(product="2684")]),
        controller("controller-b", aliases=[]),
        controller("controller-a"),
    ],
)
def test_unavailable_mismatched_or_duplicate_controllers_are_not_selectable(environment, other):
    environment.path.write_text(json.dumps(snapshot(controller(), other)))
    source, aliases = svc._read_aliases()
    assert source["state"] == "partial" and aliases
    assert not any(row["selectable"] for row in aliases)


def test_matching_controllers_deduplicate_identical_observations(environment):
    environment.path.write_text(json.dumps(snapshot(controller(), controller("controller-b"))))
    source, aliases = svc._read_aliases()
    assert source["state"] == "ready" and len(aliases) == 1 and aliases[0]["selectable"]


def test_conflicting_alias_alternatives_are_preserved_and_unknown(environment):
    environment.path.write_text(json.dumps(snapshot(controller(aliases=[alias(), alias(product="2684")]))))
    source, aliases = svc._read_aliases()
    assert source["state"] == "partial" and len(aliases) == 2
    assert {row["product_id"] for row in aliases} == {"2204", "2684"}
    assert all(row["kind"] == "unknown" and not row["selectable"] for row in aliases)


@pytest.mark.parametrize(
    "options",
    [
        {"resource_class": "CUSTOM_OTHER"},
        {"device_type": "type-VF"},
        {"traits": "CUSTOM_SPECIAL"},
        {"numa_policy": "required"},
        {"vendor_id": None},
        {"product_id": None},
    ],
)
def test_unsupported_or_incomplete_alias_is_visible_not_selectable(environment, options):
    environment.path.write_text(json.dumps(snapshot(controller(aliases=[alias(**options)]))))
    _, aliases = svc._read_aliases()
    assert len(aliases) == 1 and not aliases[0]["selectable"]


def test_classification_never_guesses_gpu_from_alias_name_or_catalog_aliases(environment):
    environment.path.write_text(
        json.dumps(
            snapshot(
                controller(
                    aliases=[
                        alias("RTX3090", vendor="abcd", product="0123"),
                        alias("Mystery-Audio", vendor="abcd", product="0124"),
                        alias("Conflicting-audio", product="2204"),
                        alias("Unlabelled", product="1aef"),
                    ]
                )
            )
        )
    )
    _, aliases = svc._read_aliases()
    assert {row["name"]: row["kind"] for row in aliases} == {
        "RTX3090": "unknown",
        "Mystery-Audio": "audio",
        "Conflicting-audio": "unknown",
        "Unlabelled": "audio",
    }
    assert not any(row["device_name"] == "RTX 3090" for row in aliases)


@pytest.mark.asyncio
async def test_mapped_alias_requires_exact_name_and_resource_not_catalog_similarity(environment):
    environment.path.write_text(json.dumps(snapshot(controller(aliases=[alias("RTX3090"), alias(product="2684")]))))
    result = await svc.discover(environment.native.conn)
    assert all(row["mapped_groups"] == [] for row in result["aliases"])
    gpu = next(row for row in result["inventory"]["devices"] if row["resource_class"] == GPU)
    assert gpu["mapped_groups"] == ["3090"]


@pytest.mark.asyncio
async def test_admin_endpoint_is_no_store_and_read_only(admin_client, environment, monkeypatch, mock_conn):
    collect = svc._inventory
    monkeypatch.setattr(svc, "_inventory", lambda conn, device_map=None: collect(environment.native.conn, device_map))
    response = await admin_client.get("/api/v1/admin/flavor-automation/pci-devices")
    assert response.status_code == 200
    assert "no-store" in response.headers["cache-control"] and response.headers["pragma"] == "no-cache"
    assert response.json()["inventory"]["state"] == "ready"
    assert (
        not mock_conn.session.post.called and not mock_conn.session.put.called and not mock_conn.session.delete.called
    )


@pytest.mark.asyncio
async def test_member_cannot_read_admin_pci_inventory(client, environment):
    response = await client.get("/api/v1/admin/flavor-automation/pci-devices")
    assert response.status_code == 403 and "no-store" in response.headers["cache-control"]
    assert not environment.native.calls
    svc.flavor_automation_policy.load_policy.assert_not_awaited()


@pytest.mark.asyncio
async def test_fresh_admin_denial_runs_before_discovery(admin_client, environment, monkeypatch):
    async def revoked():
        raise HTTPException(403, "Current system:all administrator authority is required")

    app.dependency_overrides[require_admin] = revoked
    operation = AsyncMock()
    monkeypatch.setattr(svc, "discover", operation)
    response = await admin_client.get("/api/v1/admin/flavor-automation/pci-devices")
    assert response.status_code == 403 and "no-store" in response.headers["cache-control"]
    operation.assert_not_awaited()


@pytest.mark.asyncio
async def test_blocking_file_and_provider_reads_run_off_event_loop(environment, monkeypatch):
    event_thread = threading.get_ident()
    read = svc._read_aliases
    inventory = svc._inventory
    threads = []

    def aliases(device_map):
        threads.append(threading.get_ident())
        return read(device_map)

    def collect(conn, device_map):
        threads.append(threading.get_ident())
        return inventory(conn, device_map)

    monkeypatch.setattr(svc, "_read_aliases", aliases)
    monkeypatch.setattr(svc, "_inventory", collect)
    await asyncio.wait_for(svc.discover(environment.native.conn), timeout=5)
    assert len(threads) == 2 and all(identity != event_thread for identity in threads)


@pytest.mark.parametrize(
    "value",
    [
        {"name": ["invalid"]},
        {"vendor_id": "nothex"},
        {"device_type": 1},
        {"traits": {}},
        {"numa_policy": True},
        {"unexpected_constraint": "must-not-be-ignored"},
    ],
)
def test_malformed_alias_rows_make_source_partial_and_never_selectable(environment, value):
    malformed = {**alias("Malformed"), **value}
    environment.path.write_text(json.dumps(snapshot(controller(aliases=[alias(), malformed]))))
    source, aliases = svc._read_aliases()
    assert source["state"] == "partial" and not any(row["selectable"] for row in aliases)


def test_successful_empty_configuration_does_not_invent_catalog_aliases(environment):
    environment.path.write_text(json.dumps(snapshot(controller(aliases=[]))))
    source, aliases = svc._read_aliases()
    assert source["state"] == "ready" and aliases == []


def test_snapshot_limits_fail_closed_without_truncating_ready_sets(environment, monkeypatch):
    monkeypatch.setattr(svc, "_MAX_BYTES", 10)
    assert svc._read_aliases()[0]["state"] == "unavailable"
    monkeypatch.setattr(svc, "_MAX_BYTES", 4_194_304)
    monkeypatch.setattr(svc, "_MAX_ALIASES", 1)
    environment.path.write_text(json.dumps(snapshot(controller(aliases=[alias(), alias("other")]))))
    source, aliases = svc._read_aliases()
    assert source["state"] == "unavailable" and aliases == []


@pytest.mark.asyncio
async def test_all_inventory_reads_failing_are_unavailable_not_ready_empty(environment):
    native = environment.native
    for row in native.providers:
        native.failures[f"/resource_providers/{row['uuid']}/inventories"] = 503
    inventory = (await svc.discover(native.conn))["inventory"]
    assert inventory["state"] == "unavailable" and inventory["devices"] == [] and inventory["errors"]


@pytest.mark.asyncio
async def test_provider_limit_and_deadline_are_explicit_incompleteness(environment, monkeypatch):
    monkeypatch.setattr(svc, "_MAX_PROVIDERS", 1)
    inventory = (await svc.discover(environment.native.conn))["inventory"]
    assert inventory["state"] == "partial" and inventory["errors"]
    monkeypatch.setattr(svc, "_MAX_PROVIDERS", 4096)
    monkeypatch.setattr(svc, "_DEADLINE_SECONDS", 0)
    inventory = (await svc.discover(environment.native.conn))["inventory"]
    assert inventory["state"] == "unavailable" and inventory["errors"]


@pytest.mark.asyncio
async def test_nondefault_pci_resources_remain_visible_without_guessed_identity(environment):
    custom = "CUSTOM_PCI_BOARD_CLASS"
    environment.native.inventories["unknown"] = {custom: {"total": 2, "reserved": 0}}
    environment.native.usages["unknown"] = {custom: 1}
    inventory = (await svc.discover(environment.native.conn))["inventory"]
    row = next(row for row in inventory["devices"] if row["resource_class"] == custom)
    assert row["vendor_id"] is row["product_id"] is None
    assert row["kind"] == "unknown" and row["used"] == 1 and row["mapped_groups"] == []


@pytest.mark.asyncio
async def test_custom_resource_on_bdf_provider_is_visible_without_guessing_vendor(environment):
    native = environment.native
    native.inventories["unknown"] = {"CUSTOM_GPU": {"total": 2, "reserved": 0}}
    native.usages["unknown"] = {"CUSTOM_GPU": 1}

    inventory = (await svc.discover(native.conn))["inventory"]

    row = next(item for item in inventory["devices"] if item["resource_class"] == "CUSTOM_GPU")
    assert row["pci_address"] == "0000:04:00.0"
    assert row["vendor_id"] is row["product_id"] is None
    assert row["kind"] == "unknown" and row["used"] == 1 and row["mapped_groups"] == []


def test_controller_pci_ids_are_case_insensitive_but_alias_names_are_exact(environment):
    environment.path.write_text(
        json.dumps(
            snapshot(
                controller(),
                controller("controller-b", aliases=[alias(vendor="10DE", product="2204")]),
            )
        )
    )
    source, aliases = svc._read_aliases()
    assert source["state"] == "ready" and len(aliases) == 1 and aliases[0]["selectable"]
    environment.path.write_text(json.dumps(snapshot(controller(aliases=[alias(), alias("exact-rtx-3090")]))))
    source, aliases = svc._read_aliases()
    assert source["state"] == "ready" and {row["name"] for row in aliases} == {"Exact-RTX-3090", "exact-rtx-3090"}


def test_explicit_nondefault_resource_is_not_reinterpreted_as_default(environment):
    environment.path.write_text(json.dumps(snapshot(controller(aliases=[alias(resource_class="gpu-board")]))))
    source, aliases = svc._read_aliases()
    assert source["state"] == "ready"
    assert aliases[0]["resource_class"] == "gpu-board" and not aliases[0]["selectable"]


@pytest.mark.parametrize("with_length", [True, False])
def test_oversized_streamed_response_is_rejected_and_closed(monkeypatch, with_length):
    response = Response({"resource_providers": ["x" * 256]}, headers=None if with_length else {})
    conn = SimpleNamespace(session=SimpleNamespace(get=lambda *_args, **_kwargs: response))
    monkeypatch.setattr(svc, "_MAX_BYTES", 64)
    with pytest.raises(ValueError, match="exceeds observation limit"):
        svc._get(conn, "https://placement.invalid", "/resource_providers", time.monotonic() + 5)
    assert response.closed


@pytest.mark.parametrize("headers", [{"Content-Encoding": "gzip"}, {"Transfer-Encoding": "chunked"}])
def test_buffering_encodings_are_not_claimed_deadline_bounded(headers):
    response = Response({}, headers=headers)
    conn = SimpleNamespace(session=SimpleNamespace(get=lambda *_args, **_kwargs: response))
    with pytest.raises(ValueError, match="unsupported"):
        svc._get(conn, "https://placement.invalid", "/resource_providers", time.monotonic() + 5)
    assert response.closed


def test_installed_keystoneauth_never_follows_redirect_or_forwards_credentials():
    source_calls, forwarded = [], []

    class Destination(BaseHTTPRequestHandler):
        def do_GET(self):
            forwarded.append(dict(self.headers))
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *_args):
            pass

    destination = ThreadingHTTPServer(("127.0.0.1", 0), Destination)

    class Redirect(BaseHTTPRequestHandler):
        def do_GET(self):
            source_calls.append(dict(self.headers))
            self.send_response(307)
            self.send_header("Location", f"http://127.0.0.1:{destination.server_port}/credential-target")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *_args):
            pass

    source = ThreadingHTTPServer(("127.0.0.1", 0), Redirect)
    servers = (source, destination)
    threads = [threading.Thread(target=server.serve_forever, daemon=True) for server in servers]
    for thread in threads:
        thread.start()
    endpoint = f"http://127.0.0.1:{source.server_port}"
    session = native_session.Session(auth=token_endpoint.Token(endpoint, "synthetic-pci-admin-token"))
    try:
        with pytest.raises(ValueError, match="Placement read failed"):
            svc._get(SimpleNamespace(session=session), endpoint, "/resource_providers", time.monotonic() + 5)
        assert len(source_calls) == 1
        assert source_calls[0]["X-Auth-Token"] == "synthetic-pci-admin-token"
        assert forwarded == []
    finally:
        try:
            session.session.close()
        finally:
            for server in servers:
                server.shutdown()
                server.server_close()
            for thread in threads:
                thread.join(timeout=2)


def test_installed_keystoneauth_dripping_json_body_is_bounded_even_with_debug_logging(caplog):
    stopped = threading.Event()
    calls = []
    caplog.set_level(logging.DEBUG, logger="keystoneauth.session")

    class Drip(BaseHTTPRequestHandler):
        def do_GET(self):
            calls.append(self.path)
            self.send_response(200)
            self.send_header("Content-Length", "1000")
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            try:
                for _ in range(100):
                    if stopped.wait(0.02):
                        return
                    self.wfile.write(b" ")
                    self.wfile.flush()
                self.wfile.write(b" " * 900)
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Drip)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    endpoint = f"http://127.0.0.1:{server.server_port}"
    session = native_session.Session(auth=token_endpoint.Token(endpoint, "synthetic-pci-admin-token"))
    try:
        started = time.monotonic()
        with pytest.raises(ValueError, match="observation deadline"):
            svc._get(SimpleNamespace(session=session), endpoint, "/resource_providers", started + 0.2)
        assert time.monotonic() - started < 1.5
        assert calls == ["/resource_providers"]
    finally:
        stopped.set()
        try:
            session.session.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
