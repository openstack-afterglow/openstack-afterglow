"""Image property saves must persist and surface provider errors with the real SDK."""

import copy
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from keystoneauth1 import session
from keystoneauth1.token_endpoint import Token
from openstack.connection import Connection

from app.services import image_verification

PRESET = {
    "os_type": "windows",
    "os_distro": "windows",
    "os_admin_user": "CloudAdmin",
    "windows_initial_password_method": "nova-adminpass-configdrive",
    "img_config_drive": "mandatory",
    "hw_firmware_type": "uefi",
    "hw_machine_type": "q35",
    "hw_tpm_version": "2.0",
    "hw_tpm_model": "tpm-crb",
    "os_secure_boot": "required",
    "hw_qemu_guest_agent": "yes",
}


@pytest.fixture
def native_glance(mock_conn, monkeypatch):
    state = {
        "document": {
            "id": "img-native",
            "name": "windows:service",
            "status": "active",
            "owner": mock_conn._afterglow_project_id,
            "visibility": "private",
            "min_disk": 80,
            "min_ram": 8192,
            "disk_format": "raw",
            "container_format": "bare",
            "os_type": "windows",
            "os_admin_user": "Admin",
            "windows_initial_password_method": "cloudbase-user-data",
            "custom_keep": "original",
            "production_ready": "false",
            "os_hash_algo": "sha512",
            "os_hash_value": "a" * 128,
        },
        "patches": [],
        "reject": False,
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def respond(self, value, status=200):
            body = json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path.rstrip("/") == "/v2":
                return self.respond(
                    {
                        "versions": [
                            {"id": "v2.0", "status": "CURRENT", "links": [{"rel": "self", "href": endpoint + "/v2/"}]}
                        ]
                    }
                )
            if self.path == "/v2/images/img-native":
                return self.respond(state["document"])
            return self.respond({"error": "unknown endpoint"}, 404)

        def do_PATCH(self):
            if self.path != "/v2/images/img-native":
                return self.respond({"error": "unknown endpoint"}, 404)
            if self.headers.get("Content-Type") != "application/openstack-images-v2.1-json-patch":
                return self.respond({"error": "invalid patch type"}, 415)
            if state["reject"]:
                return self.respond({"error": "image modification refused"}, 409)
            operations = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            updated = copy.deepcopy(state["document"])
            for operation in operations:
                if operation["op"] not in ("add", "replace"):
                    return self.respond({"error": "unexpected operation"}, 400)
                key = operation["path"][1:]
                if operation["op"] == "replace" and key not in updated:
                    return self.respond({"error": "missing replacement"}, 400)
                updated[key] = operation["value"]
            state["document"] = updated
            state["patches"].append(operations)
            return self.respond(updated)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    endpoint = f"http://127.0.0.1:{server.server_address[1]}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    conn = Connection(
        session=session.Session(auth=Token(endpoint, "synthetic-native-glance")),
        image_endpoint_override=endpoint + "/v2",
        image_api_version="2",
        connect_retries=0,
    )
    mock_conn.image = conn.image

    def unavailable_factory():
        raise image_verification.VerificationUnavailable("Isolated verification store")

    monkeypatch.setattr(image_verification, "_factory", unavailable_factory)
    try:
        yield state
    finally:
        conn.close()
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.asyncio
async def test_native_properties_save_persists_all_flags_and_full_projection(admin_client, native_glance):
    before = copy.deepcopy(native_glance["document"])
    response = await admin_client.patch("/api/v1/images/img-native/properties", json={"set": PRESET, "remove": []})
    assert response.status_code == 200
    saved = response.json()
    assert {key: saved["properties"][key] for key in PRESET} == PRESET
    assert saved["os_admin_user"] == "CloudAdmin"
    assert saved["windows_initial_password_method"] == "nova-adminpass-configdrive"
    assert len(native_glance["patches"]) == 1
    for key in [
        "owner",
        "visibility",
        "min_disk",
        "min_ram",
        "os_hash_algo",
        "os_hash_value",
        "custom_keep",
        "production_ready",
    ]:
        assert native_glance["document"][key] == before[key]
    reread = await admin_client.get("/api/v1/images/img-native")
    assert reread.status_code == 200
    assert {key: reread.json()["properties"][key] for key in PRESET} == PRESET
    assert reread.json()["verification_status"] == "unavailable"


@pytest.mark.asyncio
async def test_native_provider_rejection_is_not_a_successful_unchanged_save(admin_client, native_glance):
    before = copy.deepcopy(native_glance["document"])
    native_glance["reject"] = True
    response = await admin_client.patch("/api/v1/images/img-native/properties", json={"set": PRESET, "remove": []})
    assert response.status_code == 400
    assert native_glance["document"] == before
    assert native_glance["patches"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("prefix", ["/api/v1/images", "/api/v1/admin/images"])
async def test_native_typed_gpu_metadata_persists_and_replaces_existing_values(admin_client, native_glance, prefix):
    before = copy.deepcopy(native_glance["document"])
    for driver in ["nvidia", "nvidia-grid"]:
        response = await admin_client.patch(
            f"{prefix}/img-native",
            json={"name": "gpu:latest", "gpu_vendor": "nvidia", "gpu_driver": driver},
        )
        assert response.status_code == 200
        assert response.json()["gpu_vendor"] == "nvidia"
        assert response.json()["gpu_driver"] == driver
        assert native_glance["document"]["gpu_driver"] == driver
        reread = await admin_client.get(f"{prefix}/img-native")
        assert reread.status_code == 200
        assert reread.json()["properties"]["gpu_driver"] == driver
    assert len(native_glance["patches"]) == 2
    assert native_glance["document"]["name"] == "gpu:latest"
    for key, value in before.items():
        if key != "name":
            assert native_glance["document"][key] == value


@pytest.mark.asyncio
@pytest.mark.parametrize("prefix, status", [("/api/v1/images", 500), ("/api/v1/admin/images", 400)])
async def test_native_typed_gpu_metadata_rejection_never_reports_success(admin_client, native_glance, prefix, status):
    before = copy.deepcopy(native_glance["document"])
    native_glance["reject"] = True
    response = await admin_client.patch(
        f"{prefix}/img-native",
        json={"gpu_vendor": "nvidia", "gpu_driver": "nvidia"},
    )
    assert response.status_code == status
    assert native_glance["document"] == before
    assert native_glance["patches"] == []
