"""Helm generation contract: pure rendering, merge order and private artifacts."""

import copy
import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config2helm  # noqa: E402
import generation_config  # noqa: E402
from generate_k8s import render_gpu_toml  # noqa: E402


@pytest.fixture
def cfg():
    return {
        "app": {
            "secret_key": "private-signing-" + "a" * 40,
            "trusted_proxies": "10.24.0.0/16",
            "site_name": 'Quoted "site" \\ name',
        },
        "openstack": {"password": "private-openstack"},
        "database": {"url": "mysql+pymysql://user:private-db@db/afterglow"},
        "k3s": {"kubeconfig_encryption_key": "private-kubeconfig", "gpu_admission_token": "private-gpu-admission"},
        "mcp": {
            "public_url": "https://mcp.example.test/mcp",
            "oauth_consent_url": "https://web.example.test/oauth/mcp/authorize",
            "lumen_service_token": "private-lumen",
        },
        "services": {"mcp": True},
        "auth": {
            "providers": {
                "gitlab": {
                    "name": "DMSLab GitLab",
                    "kind": "oidc",
                    "issuer_url": "https://git.dmslab.re.kr",
                    "client_id": "afterglow",
                    "client_secret": "private-gitlab",
                    "keystone_idp_id": "gitlab",
                    "keystone_protocol_id": "openid",
                },
            },
            "default": {"allow_providers": []},
            "domain": {"dmslab-domain-id": {"allow_providers": ["gitlab"]}},
        },
        "ceph": {
            "rbd_conf_content": "[global]\nmon host = 192.0.2.10\n",
            "rbd_keyring": "[client.afterglow-rbd]\nkey = private-ceph\n",
        },
        "monitoring": {
            "prometheus_password": "private-prometheus",
            "sd_token": "private-sd",
            "infrastructure_topology_observers": [{"password": "private-observer"}],
        },
        "builder": {"ssh_private_key": "-----BEGIN PRIVATE KEY-----\nprivate-builder\n"},
        "notion": {"config_encryption_key": "private-notion"},
        "smtp": {"password": "private-smtp"},
        "traffic_analytics": {"hmac_key": "private-hmac", "frontend_ingest_key": "private-ingest"},
        "gpu": {
            "available_visible": False,
            "password": "private-gpu-section",
            "devices": [
                {
                    "vendor_id": "10DE",
                    "device_id": "1234",
                    "name": "Merged GPU",
                    "aliases": ["merged"],
                    "password": "private-device",
                }
            ],
        },
    }


def test_public_values_exclude_all_private_fields(cfg):
    cfg["logging"] = {"log_level": "WARNING", "password": "private-logging"}
    cfg["smtp"]["invitation"] = {"token_expiry_days": 3, "secret": "private-invitation"}
    cfg["monitoring"]["dashboards"] = {"node_uid": "node", "token": "private-dashboard"}
    cfg["monitoring"]["host_healthcheck_targets"] = [
        {"name": "node", "address": "192.0.2.1", "role": "compute", "token": "private-health"},
    ]
    cfg["monitoring"]["infrastructure_topology_peer_targets"] = [
        {"source_host_id": "one", "target_host_id": "two", "address": "192.0.2.2", "password": "private-peer"},
    ]
    rendered = config2helm.render_values(cfg, include_secrets=False)
    values = yaml.safe_load(rendered)
    assert "private-" not in rendered
    assert "secrets" not in values
    assert values["app"]["trustedProxies"] == "10.24.0.0/16"
    assert values["mcp"]["publicUrl"] == cfg["mcp"]["public_url"]
    assert values["mcp"]["oauthConsentUrl"] == cfg["mcp"]["oauth_consent_url"]
    assert values["logging"] == {"logLevel": "WARNING"}
    assert values["smtp"]["invitation"] == {"tokenExpiryDays": 3}
    assert values["monitoring"]["dashboards"] == {"nodeUid": "node"}
    assert values["monitoring"]["hostHealthcheckTargets"] == [
        {"name": "node", "address": "192.0.2.1", "role": "compute"},
    ]
    assert values["monitoring"]["infrastructureTopologyPeerTargets"] == [
        {"source_host_id": "one", "target_host_id": "two", "address": "192.0.2.2"},
    ]
    assert values["gpu"]["availableVisible"] is False
    assert values["gpu"]["configToml"] == render_gpu_toml(cfg)
    device = tomllib.loads(values["gpu"]["configToml"])["gpu"]["devices"][0]
    assert device == {
        "vendor_id": "10DE",
        "device_id": "1234",
        "name": "Merged GPU",
        "is_audio": False,
        "aliases": ["merged"],
    }


@pytest.mark.parametrize("trailing", ["", "\n", "\n\n"])
def test_normal_renderer_keeps_credentials_only_in_secrets(cfg, trailing):
    cfg["ceph"]["rbd_keyring"] = "[client.afterglow-rbd]\nkey = private-ceph" + trailing
    values = yaml.safe_load(config2helm.render_values(cfg))
    secret_values = values.pop("secrets")
    assert "private-" not in config2helm.render_yaml(values)
    assert secret_values["lumenMcpServiceToken"] == "private-lumen"
    assert secret_values["cephRbdKeyring"] == cfg["ceph"]["rbd_keyring"]
    assert secret_values["k3sGpuAdmissionToken"] == "private-gpu-admission"
    assert secret_values["infrastructureTopologyObservers"] == cfg["monitoring"]["infrastructure_topology_observers"]


def test_renderer_is_pure_and_does_not_read_configuration(cfg, monkeypatch):
    original = copy.deepcopy(cfg)

    def forbidden(*args, **kwargs):
        raise AssertionError("render_values must not read configuration files")

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", forbidden)
        patch.setattr(Path, "read_text", forbidden)
        patch.setattr(Path, "glob", forbidden)
        rendered = config2helm.render_values(cfg, include_secrets=False)
    assert yaml.safe_load(rendered)["app"]["siteName"] == cfg["app"]["site_name"]
    assert cfg == original
    assert config2helm.load_config is generation_config.load_config


@pytest.mark.parametrize("cfg", [{}, {"gpu": {"devices": []}}])
def test_empty_gpu_map_explicitly_overrides_bundled_defaults(cfg):
    assert yaml.safe_load(config2helm.render_values(cfg, False))["gpu"]["configToml"] == ""


def test_merge_order_custom_filename_gpu_and_frontend_exclusion(tmp_path):
    base = tmp_path / "operator.toml"
    base.write_text('[app]\nsite_name="base"\n[logging]\nlog_level="INFO"\n', encoding="utf-8")
    (tmp_path / "operator.a.toml").write_text('[app]\nsite_name="auto-a"\n', encoding="utf-8")
    (tmp_path / "operator.z.toml").write_text('[app]\nsite_name="auto-z"\n', encoding="utf-8")
    (tmp_path / "operator.empty.toml").touch()
    (tmp_path / "afterglow.frontend.conf").write_text("not valid TOML", encoding="utf-8")
    (tmp_path / "config.gpu.toml").write_text('[[gpu.devices]]\nname="merged-device"\n', encoding="utf-8")
    first = tmp_path / "first.conf"
    second = tmp_path / "second.conf"
    first.write_text('[app]\nsite_name="explicit-first"\n', encoding="utf-8")
    second.write_text('[app]\nsite_name="explicit-second"\n', encoding="utf-8")
    auto = config2helm.load_config(base)
    assert auto["app"]["site_name"] == "auto-z"
    merged = config2helm.load_config(base, [second, first])
    assert merged["app"]["site_name"] == "explicit-first"
    assert merged["logging"]["log_level"] == "INFO"
    assert "merged-device" in config2helm.render_values(merged, False)


def test_frontend_projection_is_never_a_backend_override(tmp_path):
    base = tmp_path / "afterglow.conf"
    base.write_text('[app]\nsite_name="backend"\n', encoding="utf-8")
    (tmp_path / "afterglow.frontend.conf").write_text('[app]\nsite_name="frontend"\n', encoding="utf-8")
    assert config2helm.load_config(base)["app"]["site_name"] == "backend"


@pytest.mark.parametrize("namespace,profile", [("afterglow", "prod"), ("afterglow-dev", "dev")])
@pytest.mark.parametrize("explicit_profile", [False, True])
def test_cli_namespace_never_selects_domain_profile_implicitly(
    tmp_path, monkeypatch, capsys, namespace, profile, explicit_profile
):
    monkeypatch.chdir(tmp_path)
    base = tmp_path / "custom.conf"
    base.write_text('[app]\nsite_name="base"\nfrontend_base_url="https://base.test"\n', encoding="utf-8")
    (tmp_path / "custom.auto.conf").write_text('[app]\nfrontend_base_url="https://automatic.test"\n', encoding="utf-8")
    first = tmp_path / "first.toml"
    last = tmp_path / "last.toml"
    first.write_text('[app]\nsite_name="first"\n', encoding="utf-8")
    last.write_text('[app]\nsite_name="last"\n', encoding="utf-8")
    argv = ["config2helm.py", "--config", str(base), "--namespace", namespace]
    expected_url = "https://automatic.test"
    if explicit_profile:
        profile_path = ROOT / "deploy" / f"afterglow-{profile}.conf"
        argv.extend(("--override", str(profile_path)))
        expected_url = tomllib.loads(profile_path.read_text(encoding="utf-8"))["app"]["frontend_base_url"]
    argv.extend(("--override", str(first), "--override", str(last), "--dry-run"))
    monkeypatch.setattr(sys, "argv", argv)
    config2helm.main()
    values = yaml.safe_load(capsys.readouterr().out)
    assert values["app"]["frontendBaseUrl"] == expected_url
    assert values["app"]["siteName"] == "last"
    assert not (tmp_path / "helm").exists()


def test_cli_dry_run_has_no_secret_or_initialization(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["config2helm.py", "--dry-run"])
    config2helm.main()
    values = yaml.safe_load(capsys.readouterr().out)
    assert "secrets" not in values
    assert not (tmp_path / "afterglow.conf").exists()
    assert not (tmp_path / "helm").exists()


def test_cli_dry_run_never_reads_raw_gpu_bytes(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "afterglow.conf").write_text('[app]\nsecret_key="private-existing"\n', encoding="utf-8")
    gpu = tmp_path / "config.gpu.toml"
    gpu.write_text(
        '# private-comment\n[database]\nurl="private-db"\n[[gpu.devices]]\nname="safe-device"\npassword="private-device"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", ["config2helm.py", "--dry-run"])
    config2helm.main()
    output = capsys.readouterr().out
    assert "private-" not in output
    assert "safe-device" in output
    assert "secrets" not in yaml.safe_load(output)


def test_cli_initializes_base_and_values_in_one_private_transaction(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["config2helm.py"])
    writes = []
    real_write_files = generation_config.write_files

    def capture(contents):
        writes.append(set(contents))
        real_write_files(contents)

    monkeypatch.setattr(config2helm, "write_files", capture)
    config2helm.main()
    base = tmp_path / "afterglow.conf"
    output = tmp_path / "helm/afterglow/values-local.yaml"
    assert writes == [{base, output}]
    assert base.stat().st_mode & 0o777 == 0o600
    assert output.stat().st_mode & 0o777 == 0o600
    source = tomllib.loads(base.read_text(encoding="utf-8"))
    values = yaml.safe_load(output.read_text(encoding="utf-8"))
    assert source["app"]["secret_key"] != "change-me-in-production"
    assert values["secrets"]["secretKey"] == source["app"]["secret_key"]


def test_render_failure_does_not_initialize_base_or_publish_values(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["config2helm.py"])

    def fail(*args, **kwargs):
        raise ValueError("private-error-literal")

    monkeypatch.setattr(config2helm, "render_values", fail)
    with pytest.raises(SystemExit, match="1"):
        config2helm.main()
    captured = capsys.readouterr()
    assert "private-error-literal" not in captured.out + captured.err
    assert not (tmp_path / "afterglow.conf").exists()
    assert not (tmp_path / "helm").exists()


def test_cli_no_secrets_preserves_existing_source_and_writes_private_output(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    original = '# preserve bytes\n[app]\nsecret_key="private-source"\n'
    base = tmp_path / "afterglow.conf"
    base.write_text(original, encoding="utf-8")
    output = tmp_path / "values.yaml"
    output.write_text("old content", encoding="utf-8")
    output.chmod(0o666)
    monkeypatch.setattr(sys, "argv", ["config2helm.py", "--no-secrets", "--output", str(output)])
    config2helm.main()
    assert base.read_text(encoding="utf-8") == original
    assert output.stat().st_mode & 0o777 == 0o600
    assert "private-source" not in output.read_text(encoding="utf-8")


@pytest.mark.parametrize("devices", [[], [{"vendor_id": "10DE", "device_id": "1234", "name": "Chart GPU"}]])
def test_canonical_values_render_actual_chart_with_private_boundary(tmp_path, cfg, devices):
    helm = shutil.which("helm")
    if helm is None:
        pytest.skip("Helm is required to render the actual chart")
    cfg["gpu"]["devices"] = devices
    chart = tmp_path / "exported-chart"
    for name, content in config2helm.chart_sources().items():
        destination = chart / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
    override = tmp_path / "values.yaml"
    override.write_text(config2helm.render_values(cfg), encoding="utf-8")
    rendered = subprocess.run(
        [helm, "template", "afterglow", str(chart), "--namespace", "afterglow-dev", "-f", str(override)],
        check=True,
        capture_output=True,
        text=True,
    )
    documents = [doc for doc in yaml.safe_load_all(rendered.stdout) if doc]
    configmap = next(
        doc for doc in documents if doc["kind"] == "ConfigMap" and doc["metadata"]["name"] == "afterglow-config"
    )
    secret = next(
        doc for doc in documents if doc["kind"] == "Secret" and doc["metadata"]["name"] == "afterglow-secrets"
    )
    backend = next(doc for doc in documents if doc["kind"] == "Deployment" and doc["metadata"]["name"] == "backend")
    assert "private-" not in yaml.safe_dump(configmap)
    toml = tomllib.loads(configmap["data"]["afterglow.conf"])
    assert toml["app"]["trusted_proxies"] == cfg["app"]["trusted_proxies"]
    assert toml["mcp"]["public_url"] == cfg["mcp"]["public_url"]
    assert toml["mcp"]["oauth_consent_url"] == cfg["mcp"]["oauth_consent_url"]
    assert toml["cloud_shell"]["image"] == "ghcr.io/openstack-afterglow/openstack-client:slim"
    assert toml["cloud_shell"]["image_pull_policy"] == ""
    assert toml["cloud_shell"]["registry_id"] == ""
    gpu_text = configmap["data"]["config.gpu.toml"]
    assert tomllib.loads(gpu_text or "").get("gpu", {}).get("devices", []) == (
        [{**devices[0], "is_audio": False}] if devices else []
    )
    assert configmap["data"]["ceph.conf"] == cfg["ceph"]["rbd_conf_content"]
    assert secret["stringData"]["LUMEN_MCP_SERVICE_TOKEN"] == "private-lumen"
    assert secret["stringData"]["CEPH_RBD_KEYRING"] == cfg["ceph"]["rbd_keyring"]
    container = backend["spec"]["template"]["spec"]["containers"][0]
    env = {item["name"]: item for item in container["env"]}
    assert env["FORWARDED_ALLOW_IPS"]["value"] == cfg["app"]["trusted_proxies"]
    assert env["LUMEN_MCP_SERVICE_TOKEN"]["valueFrom"]["secretKeyRef"]["key"] == "LUMEN_MCP_SERVICE_TOKEN"
    for probe in ("startupProbe", "livenessProbe", "readinessProbe"):
        assert container[probe]["httpGet"]["path"] == "/api/v1/health"
    deployment_names = {doc["metadata"]["name"] for doc in documents if doc["kind"] == "Deployment"}
    assert "notion-worker" in deployment_names
    assert "drover" not in deployment_names
    assert set(toml["worker_runtime"]["workers"]) == {"notion_worker"}


@pytest.mark.parametrize("default_allowlist", [None, [], ["gitlab"]])
def test_chart_auth_methods_keep_domain_selection_and_secret_environment(tmp_path, cfg, monkeypatch, default_allowlist):
    from app.config import Settings

    helm = shutil.which("helm")
    if helm is None:
        pytest.skip("Helm is required to render the actual chart")
    if default_allowlist is None:
        cfg["auth"].pop("default")
    else:
        cfg["auth"]["default"] = {"allow_providers": default_allowlist}
    override = tmp_path / "auth-values.yaml"
    override.write_text(config2helm.render_values(cfg), encoding="utf-8")
    rendered = subprocess.run(
        [helm, "template", "afterglow", str(ROOT / "helm/afterglow"), "-f", str(override)],
        check=True,
        capture_output=True,
        text=True,
    )
    documents = [doc for doc in yaml.safe_load_all(rendered.stdout) if doc]
    configmap = next(
        doc for doc in documents if doc["kind"] == "ConfigMap" and doc["metadata"]["name"] == "afterglow-config"
    )
    secret = next(
        doc for doc in documents if doc["kind"] == "Secret" and doc["metadata"]["name"] == "afterglow-secrets"
    )
    auth = tomllib.loads(configmap["data"]["afterglow.conf"])["auth"]
    assert "private-" not in yaml.safe_dump(configmap)
    assert auth.get("default") == (None if default_allowlist is None else {"allow_providers": default_allowlist})
    assert auth["domain"] == {"dmslab-domain-id": {"allow_providers": ["gitlab"]}}
    assert auth["providers"]["gitlab"]["issuer_url"] == "https://git.dmslab.re.kr"
    assert "client_secret" not in auth["providers"]["gitlab"]
    variable = "AUTH__PROVIDERS__GITLAB__CLIENT_SECRET"
    assert secret["stringData"][variable] == "private-gitlab"
    for name in ("backend", "notion-worker"):
        deployment = next(doc for doc in documents if doc["kind"] == "Deployment" and doc["metadata"]["name"] == name)
        environment = {entry["name"]: entry for entry in deployment["spec"]["template"]["spec"]["containers"][0]["env"]}
        reference = environment[variable]["valueFrom"]["secretKeyRef"]
        assert (reference["name"], reference["key"]) == ("afterglow-secrets", variable)
    monkeypatch.setenv("AUTH", json.dumps(auth))
    monkeypatch.setenv(variable, secret["stringData"][variable])
    settings = Settings(_env_file=None, secret_key="s" * 64)
    assert settings.auth.providers["gitlab"].client_secret.get_secret_value() == "private-gitlab"
    assert settings.auth.domain["dmslab-domain-id"].allow_providers == ["gitlab"]


def test_chart_sources_export_only_known_canonical_files(tmp_path, monkeypatch):
    expected = config2helm.chart_sources()
    assert {"Chart.yaml", "values.yaml", "templates/worker/notion-deployment.yaml"} <= expected.keys()
    assert "templates/worker/deployment.yaml" not in expected
    assert not any(Path(name).name.startswith(("values-", "secrets-")) for name in expected)
    source = tmp_path / "helm/afterglow"
    for name, content in expected.items():
        target = source / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    for name in (
        "values-local.yaml",
        "values-prod.yaml",
        "secrets-prod.yaml",
        "templates/private.yaml",
        "files/private.conf",
        ".omc/state/private.json",
    ):
        target = source / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("private-export-sentinel", encoding="utf-8")
    monkeypatch.setattr(config2helm, "__file__", str(tmp_path / "config2helm.py"))

    def forbidden(*args, **kwargs):
        raise AssertionError("Canonical chart export must not walk a private checkout")

    monkeypatch.setattr(Path, "rglob", forbidden)
    assert config2helm.chart_sources() == expected


def test_missing_canonical_chart_file_fails_instead_of_exporting_partial_chart(tmp_path, monkeypatch):
    monkeypatch.setattr(config2helm, "__file__", str(tmp_path / "config2helm.py"))
    with pytest.raises(FileNotFoundError):
        config2helm.chart_sources()


@pytest.mark.parametrize(
    "app,cors,expected",
    [
        (
            {"frontend_base_url": "https://web.example.test", "public_api_base": "https://api.example.test:8443"},
            "https://cors.example.test",
            {"host": "web.example.test", "apiHosts": ["api.example.test"]},
        ),
        (
            {"public_api_base": "https://api.example.test"},
            "https://web.example.test, https://other.example.test",
            {"host": "web.example.test", "apiHosts": ["api.example.test"]},
        ),
        ({"frontend_base_url": "https://web.example.test"}, "", {"host": "web.example.test", "apiHosts": []}),
        ({}, "https://web.example.test", {"host": "web.example.test", "apiHosts": []}),
    ],
)
def test_configured_public_origins_select_chart_hosts(app, cors, expected):
    values = config2helm.convert({"app": app, "cors": {"origins": cors}}, False)
    assert values["ingress"] == expected


def test_absent_public_origins_do_not_invent_chart_domain():
    assert "ingress" not in config2helm.convert({}, False)


@pytest.mark.asyncio
@pytest.mark.parametrize("override", [None, 600])
async def test_rendered_session_accepts_until_original_deadline_and_preserves_shorter_override(
    tmp_path, monkeypatch, override
):
    from fastapi import HTTPException

    from app.api import deps

    helm = shutil.which("helm")
    if helm is None:
        pytest.skip("Helm is required to exercise the rendered session policy")
    cfg = {} if override is None else {"session": {"timeout_seconds": override}}
    values_path = tmp_path / "values.yaml"
    values_path.write_text(config2helm.render_values(cfg, False), encoding="utf-8")
    rendered = subprocess.run(
        [
            helm,
            "template",
            "afterglow",
            str(ROOT / "helm/afterglow"),
            "--show-only",
            "templates/configmap.yaml",
            "-f",
            str(values_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    session = tomllib.loads(yaml.safe_load(rendered.stdout)["data"]["afterglow.conf"])["session"]
    monkeypatch.setattr(
        deps, "get_settings", lambda: SimpleNamespace(session_timeout_seconds=session["timeout_seconds"])
    )
    deleted = AsyncMock()
    monkeypatch.setattr("app.services.session_store.delete_session", deleted)
    original_start = 1_000_000.0
    expected_limit = 86400 if override is None else override
    clock = original_start + expected_limit - 1
    monkeypatch.setattr(deps.time, "time", lambda: clock)
    assert (
        await deps._check_session_timeout(
            token_hash="rendered-token",
            session={"started_at": original_start},
            refresh_jti="rendered-session",
            project_id="project",
            issued_at=original_start,
        )
        == original_start
    )
    deleted.assert_not_awaited()
    clock += 1
    with pytest.raises(HTTPException) as error:
        await deps._check_session_timeout(
            token_hash="rendered-token",
            session={"started_at": original_start},
            refresh_jti="rendered-session",
            project_id="project",
            issued_at=original_start,
        )
    assert error.value.status_code == 401
    deleted.assert_awaited_once_with("rendered-session")
