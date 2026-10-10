"""Exercise real ASGI redirects using the deployment's Uvicorn launch settings."""

import importlib.util
import shutil
import subprocess
import time
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
import uvicorn
import yaml
from jinja2 import Environment, StrictUndefined
from starlette.requests import Request
from uvicorn.main import main as uvicorn_cli

from app.main import app

ROOT = Path(__file__).resolve().parents[3]


def _kolla_launch():
    defaults = yaml.safe_load((ROOT / "deploy/kolla/ansible/roles/afterglow/defaults/main.yml").read_text())
    addresses = {"backend": "172.30.0.14", "lb1": "172.30.0.11", "lb2": "172.30.0.12", "lb3": "172.30.0.13"}
    renderer = Environment(undefined=StrictUndefined)
    renderer.filters["kolla_address"] = lambda network, host: addresses[host]
    variables = {
        "inventory_hostname": "backend",
        "groups": {"loadbalancer": ["lb1", "lb2", "lb3"]},
        "afterglow_backend_listen_port": 18020,
    }
    for name in ("afterglow_backend_listen_address", "afterglow_backend_forwarded_allow_ips"):
        if name in defaults:
            variables[name] = renderer.from_string(defaults[name]).render(**variables)
    command = [
        renderer.from_string(argument).render(**variables)
        for argument in defaults["afterglow_services"]["afterglow-backend"]["command"]
    ]
    return command, {}, "172.30.0.12", "172.30.0.99"


def _kubernetes_launch(kind):
    if kind == "helm":
        helm = shutil.which("helm")
        if helm is None:
            pytest.skip("Helm is required to exercise rendered proxy settings")
        result = subprocess.run(
            [helm, "template", "afterglow", "helm/afterglow", "--set-string", "app.trustedProxies=10.50.0.0/24"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        documents = list(yaml.safe_load_all(result.stdout))
        deployment = next(
            document
            for document in documents
            if document["kind"] == "Deployment" and document["metadata"]["name"] == "backend"
        )
        configmap = next(
            document
            for document in documents
            if document["kind"] == "ConfigMap" and document["metadata"]["name"] == "afterglow-config"
        )
    elif kind == "setup-k8s":
        spec = importlib.util.spec_from_file_location("proxy_scheme_setup", ROOT / "setup.py")
        generator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(generator)
        import tomllib

        with (ROOT / "afterglow.conf.example").open("rb") as handle:
            dummy_cfg = tomllib.load(handle)
        dummy_cfg.pop("DEFAULT", None)
        dummy_cfg["manila_ceph"] = {
            "manila_endpoint": "",
            "manila_share_network_id": "",
            "manila_share_type": "cephfs",
            "manila_nfs_share_type": "nfstype",
            "ceph_monitors": "",
        }
        dummy_cfg["gpu_devices"] = []
        dummy_cfg["session"]["warning_before_seconds"] = 300
        dummy_cfg["nova"].update(default_network_id="", default_availability_zone="nova")
        dummy_cfg["openstack"].update(insecure=False, cacert="")
        dummy_cfg["app"]["trusted_proxies"] = "10.50.0.0/24"
        configmap = yaml.safe_load(generator.render_k8s_configmap(dummy_cfg))
        deployment = yaml.safe_load((ROOT / "deploy/k8s-template/base/backend/deployment.yaml").read_text())
    else:
        spec = importlib.util.spec_from_file_location("proxy_scheme_k8s", ROOT / "generate_k8s.py")
        generator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(generator)
        configmap = yaml.safe_load(generator.render_configmap({"app": {"trusted_proxies": "10.50.0.0/24"}}))
        deployment = yaml.safe_load((ROOT / "deploy/k8s-template/base/backend/deployment.yaml").read_text())
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    environment = {}
    for variable in container["env"]:
        if variable["name"] == "FORWARDED_ALLOW_IPS":
            environment[variable["name"]] = variable.get(
                "value", configmap["data"].get(variable.get("valueFrom", {}).get("configMapKeyRef", {}).get("key", ""))
            )
    return container["command"], environment, "10.50.0.42", "10.51.0.42"


@pytest.fixture(params=["kolla", "generated-k8s", "setup-k8s", "helm"])
def launch(request, monkeypatch):
    monkeypatch.delenv("FORWARDED_ALLOW_IPS", raising=False)
    command, environment, trusted, untrusted = (
        _kolla_launch() if request.param == "kolla" else _kubernetes_launch(request.param)
    )
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    with uvicorn_cli.make_context("uvicorn", command[1:]) as context:
        options = context.params
    configuration = uvicorn.Config(
        app,
        proxy_headers=options["proxy_headers"],
        forwarded_allow_ips=options["forwarded_allow_ips"],
        lifespan="off",
    )
    configuration.load()
    return configuration.loaded_app, trusted, untrusted


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/v1/admin/version/"),
        ("POST", "/api/v1/auth/login/"),
    ],
)
async def test_trusted_https_redirect_preserves_scheme_path_and_query(launch, method, path):
    application, trusted, _ = launch
    transport = httpx.ASGITransport(app=application, client=(trusted, 43210))
    async with httpx.AsyncClient(transport=transport, base_url="http://cloud.example.test") as client:
        response = await client.request(
            method, path + "?channel=stable%2Btest&limit=2", headers={"X-Forwarded-Proto": "https"}
        )
    assert response.status_code == 307  # Preserve the method/body on normalization.
    assert (
        response.headers["location"]
        == "https://cloud.example.test" + path.rstrip("/") + "?channel=stable%2Btest&limit=2"
    )


async def test_direct_http_is_not_forced_to_https(launch):
    application, trusted, _ = launch
    transport = httpx.ASGITransport(app=application, client=(trusted, 43210))
    async with httpx.AsyncClient(transport=transport, base_url="http://cloud.example.test") as client:
        response = await client.get("/api/v1/admin/version/")
    assert response.status_code == 307
    assert response.headers["location"] == "http://cloud.example.test/api/v1/admin/version"


async def test_untrusted_peer_cannot_forge_https_or_proxy_identity(launch):
    application, trusted, untrusted = launch
    transport = httpx.ASGITransport(app=application, client=(untrusted, 43210))
    async with httpx.AsyncClient(transport=transport, base_url="http://cloud.example.test") as client:
        response = await client.get(
            "/api/v1/admin/version/",
            headers={"X-Forwarded-Proto": "https", "X-Forwarded-For": trusted},
        )
    assert response.status_code == 307
    assert response.headers["location"] == "http://cloud.example.test/api/v1/admin/version"


async def test_proxy_cutover_requires_reauthentication_without_weakening_binding(launch, monkeypatch):
    from app.config import Settings
    from app.services import jwt_service, session_store
    from app.services.token_binding import get_origin
    from tests.conftest import make_token_info

    application, trusted, untrusted = launch
    settings = Settings.model_construct(
        secret_key="proxy-cutover-regression-key-at-least-32-bytes",
        trusted_proxies="127.0.0.1/32,::1/128",
        token_ip_binding_mode="subnet",
    )
    for target in ("app.config.get_settings", "app.api.deps.get_settings", "app.services.jwt_service.get_settings"):
        monkeypatch.setattr(target, lambda: settings)
    identity = make_token_info()
    monkeypatch.setattr("app.api.deps._cached_validate", AsyncMock(return_value=identity))
    monkeypatch.setattr("app.services.activity.record", AsyncMock())
    public_client = "203.0.113.42"
    headers = {"X-Forwarded-Proto": "https", "X-Forwarded-For": public_client}
    origin_request = Request(
        {
            "type": "http",
            "client": (trusted, 43210),
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        }
    )
    old_ip, fingerprint = get_origin(origin_request)
    assert old_ip == trusted

    async def issue_bound_access(jti, origin_ip):
        await session_store.store_session(
            jti=jti,
            keystone_token=identity["token"],
            project_id=identity["project_id"],
            user_id=identity["user_id"],
            exp=int(time.time()) + 600,
            origin_ip=origin_ip,
            origin_fp=fingerprint,
        )
        token, _, _ = jwt_service.sign_access(
            identity["user_id"], identity["username"], identity["project_id"], identity["project_name"], jti
        )
        return token

    old_access = await issue_bound_access("proxy-cutover-old", old_ip)
    previous = uvicorn.Config(app, forwarded_allow_ips="127.0.0.1", lifespan="off")
    previous.load()
    before = httpx.ASGITransport(app=previous.loaded_app, client=(trusted, 43210))
    async with httpx.AsyncClient(transport=before, base_url="http://cloud.example.test") as client:
        response = await client.get("/api/v1/auth/me", headers={**headers, "Authorization": f"Bearer {old_access}"})
    assert response.status_code == 200

    after = httpx.ASGITransport(app=application, client=(trusted, 43210))
    fresh_access = await issue_bound_access("proxy-cutover-fresh", public_client)
    async with httpx.AsyncClient(transport=after, base_url="http://cloud.example.test") as client:
        rejected = await client.get("/api/v1/auth/me", headers={**headers, "Authorization": f"Bearer {old_access}"})
        accepted = await client.get("/api/v1/auth/me", headers={**headers, "Authorization": f"Bearer {fresh_access}"})
    assert rejected.status_code == 401
    assert accepted.status_code == 200
    assert accepted.json()["user_id"] == identity["user_id"]

    spoofed = httpx.ASGITransport(app=application, client=(untrusted, 43210))
    async with httpx.AsyncClient(transport=spoofed, base_url="http://cloud.example.test") as client:
        rejected_spoof = await client.get(
            "/api/v1/auth/me", headers={**headers, "Authorization": f"Bearer {fresh_access}"}
        )
    assert rejected_spoof.status_code == 401
