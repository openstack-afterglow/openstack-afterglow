"""Actual installed Nova/Cinder SDK over loopback HTTP, never a real cloud."""

import json
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from keystoneauth1.session import Session
from keystoneauth1.token_endpoint import Token
from openstack.connection import Connection

from app.models.instance_usage import UsageScheduleRequest
from app.services import instance_usage as usage
from app.services import instance_usage_scheduler as scheduler

PROJECT, SERVER, VOLUME = "usage-project", "usage-server", "usage-boot"
NOW = datetime(2026, 10, 29, tzinfo=UTC)


class Redis:
    def __init__(self):
        self.items = {}

    async def set(self, key, owner, **_):
        if key in self.items:
            return False
        self.items[key] = owner
        return True

    async def eval(self, script, _, key, owner, *args):
        if self.items.get(key) != owner:
            return 0
        if "redis.call('del'" in script:
            self.items.pop(key)
        return 1


@pytest.fixture
def native_usage():
    state = dict(
        metadata={},
        status="ACTIVE",
        flag=True,
        owner=PROJECT,
        links=[{"server_id": SERVER}],
        action_posts=[],
        metadata_posts=[],
        flag_puts=[],
        deletes=[],
        sink=[],
        invalidations=0,
        failure=None,
        fail_kind="action",
        deleted=False,
        multiattach=False,
        connections=[],
        gets=[],
        extra_servers=[],
        inline_specs=False,
    )
    state["flavor"] = {"original_name": "cpu.large", "vcpus": 12, "ram": 8192, "disk": 0, "extra_specs": {}}
    state["legacy_flavor_id"] = "large"
    state["catalog"] = [
        {
            "id": "large",
            "name": "cpu.large",
            "vcpus": 12,
            "ram": 8192,
            "disk": 0,
            "extra_specs": {},
            "os-flavor-access:is_public": True,
        }
    ]

    class Auth(Token):
        def get_access(self, session):
            return SimpleNamespace(project_id=PROJECT, project_scoped=True, system_scoped=False)

        def invalidate(self):
            # An unsafe KSA request can reauthenticate/replay after 401. The
            # scheduler must suppress this even on adapters configured to retry.
            state["invalidations"] += 1
            return True

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, status, value=None, location=None):
            body = json.dumps(value if value is not None else {}).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            if location:
                self.send_header("Location", location)
            self.end_headers()
            self.wfile.write(body)

        def read_body(self):
            return json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")

        def failing(self, kind):
            if kind != state["fail_kind"] or not state["failure"]:
                return False
            code = state["failure"]
            self.reply(
                code, {"error": {"message": "synthetic uncertain write"}}, sink_url if code in {307, 308} else None
            )
            return True

        def native_server(self):
            version = (
                self.headers.get("OpenStack-API-Version") or self.headers.get("X-OpenStack-Nova-API-Version") or ""
            )
            flavor = {"id": state["legacy_flavor_id"]} if "2.46" in version else state["flavor"]
            return {
                "id": SERVER,
                "tenant_id": PROJECT,
                "name": "usage fixture",
                "status": state["status"],
                "metadata": state["metadata"],
                "flavor": flavor,
                "OS-EXT-STS:task_state": None,
                "os-extended-volumes:volumes_attached": [{"id": VOLUME}],
            }

        def do_GET(self):
            path = urlsplit(self.path).path.rstrip("/")
            state["gets"].append(
                (path, self.headers.get("OpenStack-API-Version") or self.headers.get("X-OpenStack-Nova-API-Version"))
            )
            if path.endswith(f"/servers/{SERVER}"):
                if state["deleted"]:
                    return self.reply(404, {"itemNotFound": {"message": "gone"}})
                return self.reply(200, {"server": self.native_server()})
            if path.endswith("/servers/detail"):
                servers = [] if state["deleted"] else [self.native_server()]
                version = (
                    self.headers.get("OpenStack-API-Version") or self.headers.get("X-OpenStack-Nova-API-Version") or ""
                )
                for extra in state["extra_servers"]:
                    server = dict(extra)
                    if "2.46" in version:
                        server["flavor"] = {"id": "unrelated-native-uuid"}
                    servers.append(server)
                return self.reply(200, {"servers": servers})
            if path.endswith("/flavors/detail"):
                return self.reply(
                    200,
                    {
                        "flavors": [
                            {
                                key: value
                                for key, value in entry.items()
                                if state["inline_specs"] or key != "extra_specs"
                            }
                            for entry in state["catalog"]
                        ]
                    },
                )
            if "/flavors/" in path and path.endswith("/os-extra_specs"):
                identifier = path.split("/flavors/", 1)[1].split("/", 1)[0]
                match = next((entry for entry in state["catalog"] if entry["id"] == identifier), None)
                return self.reply(200, {"extra_specs": match["extra_specs"]}) if match else self.reply(404)
            if path.endswith(f"/servers/{SERVER}/os-volume_attachments"):
                return self.reply(
                    200,
                    {
                        "volumeAttachments": [
                            {
                                "id": VOLUME,
                                "volumeId": VOLUME,
                                "serverId": SERVER,
                                "delete_on_termination": state["flag"],
                            }
                        ]
                    },
                )
            if path.endswith(f"/volumes/{VOLUME}"):
                return self.reply(
                    200,
                    {
                        "volume": {
                            "id": VOLUME,
                            "status": "in-use",
                            "size": 8,
                            "os-vol-tenant-attr:tenant_id": state["owner"],
                            "attachments": state["links"],
                            "multiattach": state["multiattach"],
                        }
                    },
                )
            if "/compute" in path or path in {"", "/v2.1"}:
                version = {
                    "id": "v2.1",
                    "status": "CURRENT",
                    "min_version": "2.1",
                    "version": "2.96",
                    "links": [{"rel": "self", "href": endpoint + "/compute/v2.1/"}],
                }
            elif "/cinder" in path:
                version = {
                    "id": "v3.0",
                    "status": "CURRENT",
                    "min_version": "3.0",
                    "version": "3.70",
                    "links": [{"rel": "self", "href": endpoint + "/cinder/v3/"}],
                }
            else:
                version = {
                    "id": "v3.14",
                    "status": "CURRENT",
                    "links": [{"rel": "self", "href": endpoint + "/identity/v3/"}],
                }
            return self.reply(200, {"version": version})

        def do_POST(self):
            body = self.read_body()
            path = urlsplit(self.path).path
            if path.endswith("/metadata"):
                state["metadata_posts"].append(body)
                if self.failing("metadata"):
                    return
                state["metadata"].update(body["metadata"])
                return self.reply(200, {"metadata": state["metadata"]})
            if path.endswith("/action"):
                state["action_posts"].append(body)
                if self.failing("action"):
                    return
                if "shelve" in body:
                    state["status"] = "SHELVED"
                elif "shelveOffload" in body:
                    state["status"] = "SHELVED_OFFLOADED"
                elif "os-stop" in body:
                    state["status"] = "SHUTOFF"
                return self.reply(202)
            self.reply(404)

        def do_PUT(self):
            body = self.read_body()
            state["flag_puts"].append(
                {
                    "body": body,
                    "version": self.headers.get("OpenStack-API-Version")
                    or self.headers.get("X-OpenStack-Nova-API-Version"),
                }
            )
            if self.failing("flag"):
                return
            state["flag"] = body["volumeAttachment"]["delete_on_termination"]
            return self.reply(
                200,
                {
                    "volumeAttachment": {
                        "id": VOLUME,
                        "volumeId": VOLUME,
                        "serverId": SERVER,
                        "delete_on_termination": state["flag"],
                    }
                },
            )

        def do_DELETE(self):
            state["deletes"].append(urlsplit(self.path).path)
            if self.failing("delete"):
                return
            state["deleted"] = True
            self.reply(204)

    class Sink(Handler):
        def capture(self):
            state["sink"].append(
                {"method": self.command, "token": self.headers.get("X-Auth-Token"), "body": self.read_body()}
            )
            self.reply(202)

        do_POST = capture
        do_PUT = capture
        do_DELETE = capture
        do_GET = capture

    sink = ThreadingHTTPServer(("127.0.0.1", 0), Sink)
    sink_url = f"http://127.0.0.1:{sink.server_port}/do-not-forward"
    sink_thread = threading.Thread(target=sink.serve_forever, daemon=True)
    sink_thread.start()
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    endpoint = f"http://127.0.0.1:{server.server_port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def factory():
        conn = Connection(
            session=Session(auth=Auth(endpoint, "synthetic-usage-token"), connect_retries=2),
            compute_endpoint_override=f"{endpoint}/compute/v2.1/{PROJECT}",
            compute_api_version="2",
            identity_endpoint_override=endpoint + "/identity/v3",
            block_storage_endpoint_override=f"{endpoint}/cinder/v3/{PROJECT}",
            block_storage_api_version="3",
            compute_status_code_retries=2,
            compute_connect_retries=2,
            api_timeout=2,
        )
        state["connections"].append(conn)
        return conn

    def configure(*, action="shelve", delete_volumes=False, status="ACTIVE"):
        state["metadata"] = usage.creation_metadata(
            {"vcpus": 12},
            UsageScheduleRequest(expiry_action=action, delete_volumes=delete_volumes),
            now=NOW - timedelta(days=40),
        )
        state["metadata"]["unrelated"] = "preserve"
        state["status"] = status
        return factory()

    try:
        yield SimpleNamespace(state=state, configure=configure)
    finally:
        for conn in state["connections"]:
            conn.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        sink.shutdown()
        sink.server_close()
        sink_thread.join(timeout=5)


async def tick(conn):
    await scheduler._cycle(conn, PROJECT, SERVER, NOW, Redis())


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 307, 308, 503])
async def test_native_action_never_replays_or_redirects_token(native_usage, status):
    native = native_usage
    conn = native.configure()
    native.state["failure"] = status
    with pytest.raises(Exception):
        await tick(conn)
    assert len(native.state["action_posts"]) == 1
    assert native.state["invalidations"] == 0
    assert native.state["sink"] == []
    assert native.state["metadata"][usage.METADATA_PREFIX + "state"] == "shelve_requested"
    await tick(conn)
    assert len(native.state["action_posts"]) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["metadata", "flag", "delete"])
@pytest.mark.parametrize("status", [401, 307, 308])
async def test_every_mutation_disables_native_reauth_and_redirect(native_usage, kind, status):
    native = native_usage
    conn = native.configure(action="delete", status="SHUTOFF")
    native.state.update(failure=status, fail_kind=kind)
    with pytest.raises(Exception):
        await tick(conn)
    key = {"metadata": "metadata_posts", "flag": "flag_puts", "delete": "deletes"}[kind]
    assert len(native.state[key]) == 1
    assert native.state["invalidations"] == 0 and native.state["sink"] == []
    if kind != "metadata":
        assert native.state["metadata"][usage.METADATA_PREFIX + "state"] == (
            "volume_flags_requested" if kind == "flag" else "delete_requested"
        )
        if kind == "delete":
            await tick(conn)
        assert len(native.state[key]) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("delete_volumes", [False, True])
async def test_native_sdk_delete_preserves_or_explicitly_selects_all_volume_flags(native_usage, delete_volumes):
    native = native_usage
    conn = native.configure(action="delete", delete_volumes=delete_volumes)
    native.state["flag"] = not delete_volumes
    await tick(conn)
    assert native.state["action_posts"] == [{"os-stop": None}]
    await tick(conn)
    assert native.state["flag"] is delete_volumes
    assert len(native.state["flag_puts"]) == len(native.state["deletes"]) == 1
    assert "2.85" in native.state["flag_puts"][0]["version"]
    attachment_versions = [version for path, version in native.state["gets"] if path.endswith("/os-volume_attachments")]
    assert attachment_versions and all("2.85" in version for version in attachment_versions)
    server_versions = [version for path, version in native.state["gets"] if path.endswith(f"/servers/{SERVER}")]
    assert any(version and "2.96" in version for version in server_versions)
    assert native.state["flag_puts"][0]["body"]["volumeAttachment"]["volumeId"] == VOLUME
    assert native.state["metadata"]["unrelated"] == "preserve"
    await tick(conn)
    assert len(native.state["deletes"]) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", ["foreign", "multiattach", "wrong_server"])
async def test_native_cinder_proof_blocks_volume_flag_and_server_delete(native_usage, defect):
    native = native_usage
    conn = native.configure(action="delete", delete_volumes=True, status="SHUTOFF")
    if defect == "foreign":
        native.state["owner"] = "foreign-project"
    elif defect == "multiattach":
        native.state["multiattach"] = True
    else:
        native.state["links"] = [{"server_id": "foreign-server"}]
    with pytest.raises(RuntimeError):
        await tick(conn)
    assert native.state["flag_puts"] == native.state["deletes"] == []
    assert native.state["metadata"][usage.METADATA_PREFIX + "state"] == "blocked"


@pytest.mark.asyncio
async def test_native_shelve_requires_offloaded_readback_for_completion(native_usage):
    native = native_usage
    conn = native.configure()
    await tick(conn)
    assert native.state["status"] == "SHELVED"
    assert native.state["metadata"][usage.METADATA_PREFIX + "state"] == "shelve_requested"
    await tick(conn)
    assert native.state["status"] == "SHELVED_OFFLOADED"
    assert native.state["metadata"][usage.METADATA_PREFIX + "state"] == "offload_requested"
    await tick(conn)
    assert native.state["metadata"][usage.METADATA_PREFIX + "state"] == "complete"
    assert native.state["action_posts"] == [{"shelve": None}, {"shelveOffload": None}]
    assert native.state["flag_puts"] == native.state["deletes"] == []


@pytest.mark.asyncio
async def test_native_uncertain_flag_write_blocks_delete_without_put_replay(native_usage):
    native = native_usage
    conn = native.configure(action="delete", status="SHUTOFF")
    native.state.update(failure=503, fail_kind="flag")
    with pytest.raises(Exception):
        await tick(conn)
    native.state["failure"] = None
    with pytest.raises(RuntimeError):
        await tick(conn)
    assert len(native.state["flag_puts"]) == 1
    assert native.state["deletes"] == []
    assert native.state["metadata"][usage.METADATA_PREFIX + "state"] == "volume_flags_requested"


@pytest.mark.asyncio
@pytest.mark.parametrize("designated", [False, True])
async def test_native_embedded_flavor_synthetic_id_cannot_match_reused_catalog_name(native_usage, designated):
    native = native_usage
    conn = native.configure()
    native.state["metadata"] = {}
    native.state["flavor"] = {"original_name": "cpu.reused", "vcpus": 2, "ram": 8192, "disk": 0, "extra_specs": {}}
    native.state["legacy_flavor_id"] = "old-deleted-uuid"
    native.state["catalog"] = [
        {
            "id": "cpu.reused",
            "name": "cpu.reused",
            "vcpus": 12,
            "ram": 8192,
            "disk": 0,
            "extra_specs": {"afterglow:usage_schedule_required": "true"} if designated else {},
            "os-flavor-access:is_public": True,
        }
    ]
    # Installed SDK synthesizes Flavor.id from original_name. The scheduler
    # must not mistake that convenience alias for Nova's original flavor UUID.
    observed = await usage.sdk_call(conn.compute.get_server, SERVER)
    assert observed.flavor.id == "cpu.reused"
    assert scheduler._native_flavor(observed).get("id") is None
    assert await usage.sdk_call(scheduler._census, conn, NOW) == []
    await tick(conn)
    assert native.state["metadata_posts"] == native.state["action_posts"] == []
    assert not any(version and "2.46" in version for _, version in native.state["gets"])


@pytest.mark.asyncio
async def test_native_modern_additive_schedule_recovers_real_uuid_via_246(native_usage):
    native = native_usage
    conn = native.configure()
    native.state["metadata"] = {}
    native.state["flavor"] = {"original_name": "old-name", "vcpus": 2, "ram": 8192, "disk": 0, "extra_specs": {}}
    native.state["legacy_flavor_id"] = "real-native-uuid"
    native.state["catalog"] = [
        {
            "id": "real-native-uuid",
            "name": "renamed-current-name",
            "vcpus": 2,
            "ram": 8192,
            "disk": 0,
            "extra_specs": {"afterglow:usage_schedule_required": "true"},
            "os-flavor-access:is_public": True,
        }
    ]
    assert await usage.sdk_call(scheduler._census, conn, NOW) == [f"{PROJECT}:{SERVER}"]
    await tick(conn)
    info = usage.parse_schedule({"id": SERVER, "metadata": native.state["metadata"]})
    assert info.source == "adopted" and datetime.fromisoformat(info.starts_at) == NOW
    assert len(native.state["metadata_posts"]) == 1 and native.state["action_posts"] == []
    assert any(
        path.endswith(f"/servers/{SERVER}") and version and "2.46" in version for path, version in native.state["gets"]
    )


@pytest.mark.asyncio
async def test_native_census_batches_legacy_identity_for_many_small_servers(native_usage):
    native = native_usage
    conn = native.configure()
    native.state["metadata"] = {}
    native.state["flavor"] = {"original_name": "cpu.small", "vcpus": 2, "ram": 8192, "disk": 0, "extra_specs": {}}
    native.state["legacy_flavor_id"] = "designated-native-uuid"
    native.state["catalog"] = [
        {
            "id": "designated-native-uuid",
            "name": "cpu.small",
            "vcpus": 2,
            "ram": 8192,
            "disk": 0,
            "extra_specs": {"afterglow:usage_schedule_required": "true"},
            "os-flavor-access:is_public": True,
        }
    ]
    native.state["extra_servers"] = [
        {
            "id": f"fleet-{index}",
            "tenant_id": PROJECT,
            "status": "ACTIVE",
            "metadata": {},
            "flavor": {"original_name": "other.small", "vcpus": 2, "ram": 8192, "disk": 0, "extra_specs": {}},
        }
        for index in range(500)
    ]
    assert await usage.sdk_call(scheduler._census, conn, NOW) == [f"{PROJECT}:{SERVER}"]
    detail_versions = [version for path, version in native.state["gets"] if path.endswith("/servers/detail")]
    assert len(detail_versions) == 2
    assert sum(bool(version and "2.46" in version) for version in detail_versions) == 1
    assert not any(path.endswith(f"/servers/{SERVER}") for path, _ in native.state["gets"])
    assert native.state["metadata_posts"] == native.state["action_posts"] == []


@pytest.mark.asyncio
async def test_native_catalog_inline_empty_specs_avoid_per_flavor_gets(native_usage):
    native = native_usage
    conn = native.configure()
    native.state["metadata"] = {}
    native.state["inline_specs"] = True
    native.state["flavor"] = {"original_name": "cpu.small", "vcpus": 2, "ram": 8192, "disk": 0, "extra_specs": {}}
    native.state["catalog"] = [
        {
            "id": f"small-{index}",
            "name": f"small-{index}",
            "vcpus": 2,
            "ram": 8192,
            "disk": 0,
            "extra_specs": {},
            "os-flavor-access:is_public": True,
        }
        for index in range(100)
    ]
    assert await usage.sdk_call(scheduler._census, conn, NOW) == []
    assert not any(path.endswith("/os-extra_specs") for path, _ in native.state["gets"])
    assert len([path for path, _ in native.state["gets"] if path.endswith("/flavors/detail")]) == 1
    assert len([path for path, _ in native.state["gets"] if path.endswith("/servers/detail")]) == 1
