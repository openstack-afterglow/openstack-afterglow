"""Native HTTP boundaries for conditional Neutron and Nova/Cinder data disks.

Identity/policy/resources are synthetic; HTTP and installed SDK serialization are real.
"""

from __future__ import annotations

import copy
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

import pytest
from keystoneauth1.session import Session
from keystoneauth1.token_endpoint import Token
from openstack.connection import Connection

from tests.test_mcp_project_runtime import runtime as _runtime

runtime = _runtime

PROJECT = str(UUID(int=101))
NETWORK = str(UUID(int=201))
SUBNET = str(UUID(int=301))
PORT = str(UUID(int=401))
SERVER = str(UUID(int=501))
GROUP = str(UUID(int=601))
VOLUME = str(UUID(int=701))
ROOT = str(UUID(int=702))
ATTACHMENT = str(UUID(int=801))


@contextmanager
def native_management():
    state = {
        "requests": [],
        "writes": [],
        "stale_revision": False,
        "disconnect_after_write": False,
        "redirect_write": False,
        "networks": {
            NETWORK: {
                "id": NETWORK,
                "project_id": PROJECT,
                "tenant_id": PROJECT,
                "name": "tenant-net",
                "description": "",
                "status": "ACTIVE",
                "shared": False,
                "router:external": False,
                "admin_state_up": True,
                "revision_number": 1,
            }
        },
        "subnets": {
            SUBNET: {
                "id": SUBNET,
                "project_id": PROJECT,
                "tenant_id": PROJECT,
                "name": "tenant-subnet",
                "description": "",
                "network_id": NETWORK,
                "cidr": "10.80.0.0/24",
                "ip_version": 4,
                "gateway_ip": "10.80.0.1",
                "enable_dhcp": True,
                "dns_nameservers": [],
                "revision_number": 1,
            }
        },
        "ports": {
            PORT: {
                "id": PORT,
                "project_id": PROJECT,
                "tenant_id": PROJECT,
                "name": "tenant-port",
                "description": "",
                "network_id": NETWORK,
                "status": "DOWN",
                "admin_state_up": True,
                "mac_address": "fa:16:3e:01:02:03",
                "device_id": "",
                "device_owner": "",
                "binding:host_id": "",
                "binding:vif_type": "unbound",
                "binding:profile": {},
                "provider_secret": "never-return-provider-binding",
                "fixed_ips": [{"subnet_id": SUBNET, "ip_address": "10.80.0.10"}],
                "security_groups": [GROUP],
                "port_security_enabled": True,
                "revision_number": 1,
            }
        },
        "security-groups": {
            GROUP: {
                "id": GROUP,
                "project_id": PROJECT,
                "tenant_id": PROJECT,
                "name": "tenant-group",
                "description": "group for synthetic TCP fixture",
                "security_group_rules": [],
            }
        },
        "interfaces": {},
        "attachments": {},
        "server": {
            "id": SERVER,
            "name": "owned-vm",
            "status": "ACTIVE",
            "tenant_id": PROJECT,
            "OS-EXT-SRV-ATTR:root_device_name": "/dev/sda",
            "OS-EXT-AZ:availability_zone": "nova",
            "OS-EXT-STS:task_state": None,
            "os-extended-volumes:volumes_attached": [{"id": ROOT}],
        },
        "volumes": {},
    }
    for volume_id, root in ((VOLUME, False), (ROOT, True)):
        state["volumes"][volume_id] = {
            "id": volume_id,
            "name": "root" if root else "data",
            "description": "",
            "status": "in-use" if root else "available",
            "size": 8,
            "created_at": "2026-11-03T00:00:00",
            "os-vol-tenant-attr:tenant_id": PROJECT,
            "project_id": PROJECT,
            "multiattach": False,
            "bootable": "true" if root else "false",
            "availability_zone": "nova",
            "attachments": (
                [{"attachment_id": str(UUID(int=802)), "volume_id": ROOT, "server_id": SERVER, "device": "/dev/sda"}]
                if root
                else []
            ),
        }
    state["attachments"][ROOT] = {
        "id": ROOT,
        "volumeId": ROOT,
        "serverId": SERVER,
        "device": "/dev/sda",
        "attachment_id": str(UUID(int=802)),
    }

    class Native(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, payload=None, status=200):
            data = b"" if payload is None else json.dumps(copy.deepcopy(payload)).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            if 300 <= status < 400:
                self.send_header("Location", self.base() + "/must-not-follow")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self.handle_request("GET")

        def do_POST(self):
            self.handle_request("POST")

        def do_PUT(self):
            self.handle_request("PUT")

        def do_DELETE(self):
            self.handle_request("DELETE")

        def handle_request(self, method):
            parsed = urlsplit(self.path)
            path, query = parsed.path.rstrip("/"), parse_qs(parsed.query)
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length)) if length else None
            record = {
                "method": method,
                "path": path,
                "query": query,
                "body": body,
                "if_match": self.headers.get("If-Match"),
                "microversion": self.headers.get("OpenStack-API-Version")
                or self.headers.get("X-OpenStack-Nova-API-Version"),
            }
            state["requests"].append(record)
            if method != "GET":
                state["writes"].append(record)
            if method == "POST" and path.endswith("/action") and state["redirect_write"]:
                self.reply(status=307)
                return
            if method == "POST" and path == "/v2.0/networks" and state["disconnect_after_write"]:
                # The create reached native, but its reply was lost.
                resource_id = str(UUID(int=1000 + len(state["writes"])))
                state["networks"][resource_id] = {
                    **copy.deepcopy(state["networks"][NETWORK]),
                    **body["network"],
                    "id": resource_id,
                }
                self.close_connection = True
                self.connection.shutdown(2)
                self.connection.close()
                return
            if method == "GET" and path == "/v2.0":
                self.reply(
                    {
                        "version": {
                            "id": "v2.0",
                            "status": "CURRENT",
                            "links": [{"rel": "self", "href": self.base() + "/v2.0/"}],
                        }
                    }
                )
                return
            if method == "GET" and path in {"/v3", "/v3/" + PROJECT}:
                self.reply(
                    {
                        "version": {
                            "id": "v3.0",
                            "status": "CURRENT",
                            "min_version": "3.0",
                            "version": "3.71",
                            "links": [{"rel": "self", "href": self.base() + "/v3/"}],
                        }
                    }
                )
                return
            if path == "/v2.1":
                self.reply(
                    {
                        "version": {
                            "id": "v2.1",
                            "status": "CURRENT",
                            "min_version": "2.1",
                            "version": "2.95",
                            "links": [{"rel": "self", "href": self.base() + "/v2.1/"}],
                        }
                    }
                )
                return
            if path == "/v2.0/extensions":
                self.reply({"extensions": [{"alias": "revision-if-match", "name": "Revision constraints"}]})
                return
            if path == "/v2.0/extensions/revision-if-match":
                self.reply({"extension": {"alias": "revision-if-match", "name": "Revision constraints"}})
                return
            if path.startswith("/v2.0/"):
                parts = path[len("/v2.0/") :].split("/")
                collection = parts[0]
                if collection not in {"networks", "subnets", "ports", "security-groups"}:
                    self.reply({"error": "unknown network collection"}, 404)
                    return
                rows = state[collection]
                key = {
                    "networks": "network",
                    "subnets": "subnet",
                    "ports": "port",
                    "security-groups": "security_group",
                }[collection]
                if method == "GET":
                    if len(parts) == 2:
                        if parts[1] not in rows:
                            self.reply({"error": "missing native resource"}, 404)
                        else:
                            self.reply({key: rows[parts[1]]})
                    else:
                        selected = list(rows.values())
                        for field in ("project_id", "network_id", "device_id", "id"):
                            if field in query:
                                selected = [row for row in selected if row.get(field) == query[field][0]]
                        if "marker" in query:
                            marker = query["marker"][0]
                            ids = [row["id"] for row in selected]
                            selected = selected[ids.index(marker) + 1 :] if marker in ids else []
                        self.reply({collection.replace("-", "_"): selected[: int(query.get("limit", [100])[0])]})
                    return
                if method == "POST":
                    attrs = body[key]
                    resource_id = str(UUID(int=1000 + len(state["writes"])))
                    if collection == "networks":
                        row = {**copy.deepcopy(state["networks"][NETWORK]), **attrs, "id": resource_id}
                    elif collection == "subnets":
                        row = {**copy.deepcopy(state["subnets"][SUBNET]), **attrs, "id": resource_id}
                        if "gateway_ip" not in attrs:
                            from ipaddress import ip_network

                            row["gateway_ip"] = str(ip_network(row["cidr"]).network_address + 1)
                    else:
                        row = {**copy.deepcopy(state["ports"][PORT]), **attrs, "id": resource_id}
                    rows[resource_id] = row
                    self.reply({key: row}, 201)
                    return
                if len(parts) != 2 or parts[1] not in rows:
                    self.reply({"error": "missing native resource"}, 404)
                    return
                row = rows[parts[1]]
                if record["if_match"] != "revision_number=" + str(row["revision_number"]) or state["stale_revision"]:
                    self.reply(
                        {
                            "NeutronError": {
                                "message": "stale native revision",
                                "type": "RevisionNumberConstraintFailed",
                            }
                        },
                        412,
                    )
                    return
                if method == "PUT":
                    row.update(body[key])
                    row["revision_number"] += 1
                    self.reply({key: row})
                    return
                if method == "DELETE":
                    del rows[parts[1]]
                    self.reply(status=204)
                    return
            if path == "/v2.1/servers/" + SERVER:
                record_server = copy.deepcopy(state["server"])
                version = (record["microversion"] or "2.1").split()[-1]
                if tuple(map(int, version.split("."))) < (2, 3):
                    record_server.pop("OS-EXT-SRV-ATTR:root_device_name", None)
                self.reply({"server": record_server})
                return
            interface_base = "/v2.1/servers/" + SERVER + "/os-interface"
            if path.startswith(interface_base):
                port_id = path[len(interface_base) :].strip("/")
                if method == "GET":
                    if port_id:
                        item = state["interfaces"].get(port_id)
                        self.reply({"interfaceAttachment": item}, 200 if item else 404)
                    else:
                        self.reply({"interfaceAttachments": list(state["interfaces"].values())})
                    return
                if method == "POST":
                    attrs = body["interfaceAttachment"]
                    port_id = attrs["port_id"]
                    port = state["ports"][port_id]
                    port.update(
                        {
                            "device_id": SERVER,
                            "device_owner": "compute:nova",
                            "status": "ACTIVE",
                            "binding:host_id": "synthetic-host",
                            "binding:vif_type": "ovs",
                        }
                    )
                    port["revision_number"] += 1
                    item = {
                        "port_id": port_id,
                        "net_id": port["network_id"],
                        "mac_addr": port["mac_address"],
                        "fixed_ips": port["fixed_ips"],
                        "port_state": "ACTIVE",
                    }
                    state["interfaces"][port_id] = item
                    self.reply({"interfaceAttachment": item}, 200)
                    return
                if method == "DELETE":
                    del state["interfaces"][port_id]
                    state["ports"][port_id].update(
                        {
                            "device_id": "",
                            "device_owner": "",
                            "status": "DOWN",
                            "binding:host_id": "",
                            "binding:vif_type": "unbound",
                        }
                    )
                    self.reply(status=202)
                    return
            attachment_base = "/v2.1/servers/" + SERVER + "/os-volume_attachments"
            if path.startswith(attachment_base):
                volume_id = path[len(attachment_base) :].strip("/")
                if method == "GET":
                    if volume_id:
                        item = state["attachments"].get(volume_id)
                        self.reply({"volumeAttachment": item}, 200 if item else 404)
                    else:
                        self.reply({"volumeAttachments": list(state["attachments"].values())})
                    return
                if method == "POST":
                    volume_id = body["volumeAttachment"]["volumeId"]
                    item = {
                        "id": volume_id,
                        "volumeId": volume_id,
                        "serverId": SERVER,
                        "device": "/dev/sdb",
                        "attachment_id": ATTACHMENT,
                    }
                    state["attachments"][volume_id] = item
                    state["server"]["os-extended-volumes:volumes_attached"].append({"id": volume_id})
                    state["volumes"][volume_id].update(
                        {
                            "status": "in-use",
                            "attachments": [
                                {
                                    "attachment_id": state.get("reported_cinder_attachment_id", ATTACHMENT),
                                    "volume_id": volume_id,
                                    "server_id": SERVER,
                                    "device": "/dev/sdb",
                                }
                            ],
                        }
                    )
                    # Nova POST retains the legacy volume id, while 2.89 GET
                    # separately exposes the actual Cinder attachment_id.
                    self.reply(
                        {"volumeAttachment": {key: value for key, value in item.items() if key != "attachment_id"}}
                    )
                    return
                if method == "DELETE":
                    del state["attachments"][volume_id]
                    state["volumes"][volume_id].update({"status": "available", "attachments": []})
                    state["server"]["os-extended-volumes:volumes_attached"] = [
                        row for row in state["server"]["os-extended-volumes:volumes_attached"] if row["id"] != volume_id
                    ]
                    self.reply(status=202)
                    return
            volume_base = "/v3/" + PROJECT + "/volumes/"
            if path.startswith(volume_base):
                parts = path[len(volume_base) :].split("/")
                volume_id = parts[0]
                if volume_id not in state["volumes"]:
                    self.reply({"error": "missing volume"}, 404)
                    return
                if method == "GET":
                    self.reply({"volume": state["volumes"][volume_id]})
                    return
                if method == "PUT":
                    state["volumes"][volume_id].update(body["volume"])
                    self.reply({"volume": state["volumes"][volume_id]})
                    return
                if method == "POST" and parts[1:] == ["action"]:
                    state["volumes"][volume_id]["size"] = body["os-extend"]["new_size"]
                    self.reply(status=202)
                    return
            self.reply({"error": "unimplemented native fixture path", "path": path}, 404)

        def base(self):
            return f"http://127.0.0.1:{self.server.server_port}"

    server = ThreadingHTTPServer(("127.0.0.1", 0), Native)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    endpoint = f"http://127.0.0.1:{server.server_port}"
    conn = Connection(
        session=Session(auth=Token(endpoint, "synthetic-native-token")),
        compute_endpoint_override=endpoint + "/v2.1",
        compute_api_version="2",
        network_endpoint_override=endpoint + "/v2.0",
        network_api_version="2",
        block_storage_endpoint_override=endpoint + "/v3/" + PROJECT,
        block_storage_api_version="3",
        block_storage_default_microversion="3.0",
        connect_retries=0,
        status_code_retries=0,
    )
    conn._afterglow_project_id = PROJECT
    conn._afterglow_domain_id = "domain-a"
    try:
        yield conn, state
    finally:
        conn.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.asyncio
async def test_native_conditional_update_preserves_omitted_gateway_and_stale_revision_never_retries():
    from app.services.mcp_control_plane.network import McpNetworkError
    from app.services.mcp_control_plane.network_management import request_project_subnet_update

    with native_management() as (conn, native):
        await request_project_subnet_update(conn, project_id=PROJECT, subnet_id=SUBNET, attributes={"name": "renamed"})
        assert native["subnets"][SUBNET]["gateway_ip"] == "10.80.0.1"
        await request_project_subnet_update(conn, project_id=PROJECT, subnet_id=SUBNET, attributes={"gateway_ip": None})
        assert native["subnets"][SUBNET]["gateway_ip"] is None
        native["stale_revision"] = True
        with pytest.raises(McpNetworkError):
            await request_project_subnet_update(
                conn, project_id=PROJECT, subnet_id=SUBNET, attributes={"name": "stale"}
            )
        assert native["subnets"][SUBNET]["name"] == "renamed"
        assert [row["if_match"] for row in native["writes"]] == [
            "revision_number=1",
            "revision_number=2",
            "revision_number=3",
        ]


@pytest.mark.asyncio
async def test_native_data_disk_detach_uses_actual_scsi_root_and_cannot_detach_root():
    from app.services.mcp_control_plane.storage import (
        McpStorageError,
        request_project_server_volume_attach,
        request_project_server_volume_detach,
    )

    with native_management() as (conn, native):
        attached = await request_project_server_volume_attach(
            conn, project_id=PROJECT, server_id=SERVER, volume_id=VOLUME
        )
        assert attached["volume_id"] == VOLUME
        detached = await request_project_server_volume_detach(
            conn, project_id=PROJECT, server_id=SERVER, volume_id=VOLUME
        )
        assert detached["device"] == "/dev/sdb"
        writes_before = copy.deepcopy(native["writes"])
        with pytest.raises(McpStorageError):
            await request_project_server_volume_detach(conn, project_id=PROJECT, server_id=SERVER, volume_id=ROOT)
        assert native["writes"] == writes_before
        assert native["volumes"][ROOT]["status"] == "in-use"
        assert ROOT in native["attachments"]
        assert VOLUME not in native["attachments"]


def test_native_accepted_write_with_lost_reply_is_never_retransmitted():
    from app.services.mcp_control_plane.connection import _prevent_write_replay

    with native_management() as (conn, native):
        _prevent_write_replay(conn.session)
        native["disconnect_after_write"] = True
        with pytest.raises(Exception):
            conn.network.create_network(name="one-create-only", project_id=PROJECT)
        assert [(row["method"], row["path"]) for row in native["writes"]] == [("POST", "/v2.0/networks")]
        assert [row["name"] for row in native["networks"].values()].count("one-create-only") == 1


@pytest.mark.asyncio
async def test_native_attachment_contradictory_server_is_denied_before_detach():
    from app.services.mcp_control_plane.storage import McpStorageError, request_project_server_volume_detach

    with native_management() as (conn, native):
        conn.compute.default_microversion = "2.89"
        native["attachments"][VOLUME] = {
            "volumeId": VOLUME,
            "serverId": str(UUID(int=999)),
            "attachment_id": ATTACHMENT,
            "device": "/dev/sdb",
        }
        native["volumes"][VOLUME].update(
            status="in-use",
            attachments=[{"volume_id": VOLUME, "server_id": SERVER, "attachment_id": ATTACHMENT, "device": "/dev/sdb"}],
        )
        native["server"]["os-extended-volumes:volumes_attached"].append({"id": VOLUME})
        with pytest.raises(McpStorageError):
            await request_project_server_volume_detach(conn, project_id=PROJECT, server_id=SERVER, volume_id=VOLUME)
        assert native["writes"] == []
        assert VOLUME in native["attachments"]


@pytest.mark.asyncio
async def test_native_redirected_volume_write_is_unknown_not_success_and_not_followed():
    from app.services.mcp_control_plane.connection import _prevent_write_replay
    from app.services.mcp_control_plane.storage import McpStorageError, request_project_volume_extend

    with native_management() as (conn, native):
        _prevent_write_replay(conn.session)
        native["redirect_write"] = True
        with pytest.raises(McpStorageError):
            await request_project_volume_extend(conn, project_id=PROJECT, volume_id=VOLUME, size_gb=16)
        assert native["volumes"][VOLUME]["size"] == 8
        assert len(native["writes"]) == 1
        assert not any(row["path"] == "/must-not-follow" for row in native["requests"])


@pytest.mark.asyncio
async def test_native_port_and_group_pages_request_provider_limit():
    from app.services.mcp_control_plane.instance_management import list_project_security_groups
    from app.services.mcp_control_plane.network_management import list_project_ports

    with native_management() as (conn, native):
        await list_project_ports(conn, project_id=PROJECT, limit=1)
        await list_project_security_groups(conn, project_id=PROJECT, limit=1)
        queries = {
            row["path"]: row["query"]
            for row in native["requests"]
            if row["path"] in {"/v2.0/ports", "/v2.0/security-groups"}
        }
        assert queries["/v2.0/ports"]["limit"] == ["1"]
        assert queries["/v2.0/security-groups"]["limit"] == ["1"]


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["mcp", "lumen"])
async def test_native_corroborated_attachment_id_mismatch_stays_unknown_without_replay(runtime, monkeypatch, surface):
    import sys
    from contextlib import asynccontextmanager

    from app.services.mcp_control_plane import registry
    from tests.test_mcp_project_runtime import invoke_provisioning

    monkeypatch.setattr(sys.modules[__name__], "PROJECT", "b")
    with native_management() as (conn, native):
        native["reported_cinder_attachment_id"] = str(UUID(int=999))

        @asynccontextmanager
        async def cloud(context):
            assert context.project_id == "b"
            yield conn

        monkeypatch.setattr(registry.ConsumerCloudContext, "openstack_connection", cloud)
        args = {"project_id": "b", "server_id": SERVER, "volume_id": VOLUME}
        for key in ("corroboration-0001", "corroboration-0001", "corroboration-0002"):
            with pytest.raises(Exception):
                await invoke_provisioning(runtime, surface, "afterglow_vm_volume_attach", args, key)
        assert len(runtime.invocations) == 1
        assert runtime.invocations[0].status == "unknown"
        assert [(row["method"], row["path"]) for row in native["writes"]] == [
            ("POST", f"/v2.1/servers/{SERVER}/os-volume_attachments")
        ]
        assert native["attachments"][VOLUME]["attachment_id"] == ATTACHMENT
        assert native["volumes"][VOLUME]["attachments"][0]["attachment_id"] != ATTACHMENT
