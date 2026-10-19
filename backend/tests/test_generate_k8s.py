"""generate_k8s.py 단위 테스트."""

import sys
import tomllib
from pathlib import Path

import pytest
import yaml

# generate_k8s.py is at project root, not in backend/
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from generate_k8s import (  # noqa: E402
    _render_toml_for_k8s,
    load_config,
    main,
    render_configmap,
    render_grafana_deployment,
    render_ingress,
    render_secret,
)


@pytest.mark.parametrize("enabled", [False, True])
def test_rendered_analytics_config_loads_with_current_backend_schema(enabled):
    from app.models.traffic_analytics import TrafficAnalyticsSettings

    cfg = {
        "traffic_analytics": {
            "enabled": enabled,
            "geoip_mmdb": "/etc/afterglow/geoip/country.mmdb",
            "cluster_cidrs": ["10.50.0.0/16"],
            "backend_trusted_proxy_cidrs": ["10.51.0.0/24"],
            "frontend_trusted_proxy_cidrs": ["10.52.0.0/24"],
            "site_country": "KR",
        }
    }
    configmap = yaml.safe_load(render_configmap(cfg))
    public_config = tomllib.loads(configmap["data"]["afterglow.conf"])
    settings = TrafficAnalyticsSettings.model_validate(
        {
            **public_config["traffic_analytics"],
            "hmac_key": "synthetic-hmac-fixture-0123456789abcdef",
            "frontend_ingest_key": "synthetic-ingest-fixture-0123456789abcdef",
        }
    )

    assert settings.enabled is enabled
    assert settings.geoip_mmdb == "/etc/afterglow/geoip/country.mmdb"
    assert settings.cluster_cidrs == ["10.50.0.0/16"]
    assert settings.backend_trusted_proxy_cidrs == ["10.51.0.0/24"]
    assert settings.frontend_trusted_proxy_cidrs == ["10.52.0.0/24"]
    assert settings.site_country == "KR"


def test_render_toml_excludes_removed_nova_image_selector():
    result = _render_toml_for_k8s({"nova": {"server_image_id": "legacy-server-image"}})

    assert "[nova]" in result
    assert "server_image_id" not in result


def test_render_toml_derives_public_api_base_for_k8s_runtime_config():
    result = _render_toml_for_k8s(
        {
            "cors": {"origins": "https://afterglow.example.com,http://localhost:3080"},
            "app": {"frontend_base_url": ""},
        }
    )

    assert 'public_api_base = "https://afterglow.example.com"' in result


def test_render_toml_preserves_explicit_public_api_base():
    result = _render_toml_for_k8s(
        {
            "cors": {"origins": "https://afterglow.example.com"},
            "app": {
                "frontend_base_url": "https://frontend.example.com",
                "public_api_base": "https://api.example.com/root/path",
            },
        }
    )

    assert 'public_api_base = "https://api.example.com"' in result


def test_render_toml_strips_credentials_from_public_api_origin():
    result = _render_toml_for_k8s({"app": {"public_api_base": "https://user:pass@api.example.com/root/path"}})

    assert 'public_api_base = "https://api.example.com"' in result


def test_render_toml_falls_back_to_backend_port_without_public_origin():
    result = _render_toml_for_k8s({"app": {"backend_port": 8123}})

    assert 'public_api_base = "http://localhost:8123"' in result


def test_render_toml_includes_public_mcp_urls():
    result = _render_toml_for_k8s(
        {
            "mcp": {
                "public_url": "https://mcp.example.test/control-plane/mcp",
                "oauth_consent_url": "https://app.example.test/oauth/mcp/authorize",
            }
        }
    )

    assert 'public_url = "https://mcp.example.test/control-plane/mcp"' in result
    assert 'oauth_consent_url = "https://app.example.test/oauth/mcp/authorize"' in result


def _generated_service(ingresses, host, request_path):
    matches = []
    for ingress in ingresses:
        priority = ingress["metadata"].get("annotations", {}).get("traefik.ingress.kubernetes.io/router.priority")
        for rule in ingress["spec"]["rules"]:
            if rule["host"] != host:
                continue
            for route in rule["http"]["paths"]:
                path = route["path"]
                exact = route["pathType"] == "Exact"
                if request_path == path if exact else request_path.startswith(path):
                    matcher = "Path" if exact else "PathPrefix"
                    rule_length = len(f"Host(`{host}`) && {matcher}(`{path}`)")
                    matches.append((int(priority) if priority else rule_length, route["backend"]["service"]))
    return max(matches, key=lambda item: item[0])[1] if matches else None


def _assert_generated_service(ingress, host, path, name, port):
    assert _generated_service(ingress, host, path) == {"name": name, "port": {"number": port}}


@pytest.mark.parametrize("namespace", ["afterglow", "afterglow-dev"])
@pytest.mark.parametrize("mcp_host", ["app.example.test", "api.example.test", "mcp.example.test"])
@pytest.mark.parametrize("mcp_path", ["/mcp", "/control-plane/mcp/"])
def test_generated_ingress_routes_configured_resource_and_oauth_without_rewrites(namespace, mcp_host, mcp_path):
    public_url = f"https://{mcp_host}{mcp_path}"
    cfg = {
        "app": {
            "frontend_base_url": "https://app.example.test",
            "public_api_base": "https://api.example.test",
        },
        "services": {"mcp": True},
        "mcp": {"public_url": public_url, "oauth_consent_url": "https://app.example.test/oauth/mcp/authorize"},
    }
    configmap = yaml.safe_load(render_configmap(cfg, namespace))
    config = tomllib.loads(configmap["data"]["afterglow.conf"])
    ingress = list(yaml.safe_load_all(render_ingress(cfg, namespace)))
    assert config["mcp"]["public_url"] == public_url
    assert config["mcp"]["oauth_consent_url"] == cfg["mcp"]["oauth_consent_url"]
    assert all(document["metadata"]["namespace"] == namespace for document in ingress)
    assert set(ingress[0]["spec"]["tls"][0]["hosts"]) == {"app.example.test", "api.example.test", mcp_host}
    profile = "dev" if namespace == "afterglow-dev" else "prod"
    common_annotations = {
        "kubernetes.io/ingress.class": "traefik",
        "traefik.ingress.kubernetes.io/router.entrypoints": "web,websecure",
        "traefik.ingress.kubernetes.io/service.serverstransport": f"{namespace}-backend-long-timeout@kubernetescrd",
    }
    assert ingress[0]["metadata"]["annotations"] == {
        **common_annotations,
        "cert-manager.io/cluster-issuer": f"letsencrypt-{profile}-traefik",
    }
    assert ingress[1]["metadata"]["annotations"] == {
        **common_annotations,
        "traefik.ingress.kubernetes.io/router.priority": "1000",
    }
    resource_path = mcp_path.rstrip("/")
    for path in (
        resource_path,
        resource_path + "/",
        resource_path + "/resource/child",
        *(resource_path + "/oauth/" + endpoint for endpoint in ("register", "authorize", "token", "revoke")),
        "/.well-known/oauth-protected-resource" + resource_path,
        "/.well-known/oauth-authorization-server" + resource_path + "/oauth",
    ):
        _assert_generated_service(ingress, mcp_host, path, "backend", 8000)
    for host in ("app.example.test", "api.example.test"):
        for path in (
            "/",
            "/oauth/mcp/authorize",
            "/mcpevil",
            resource_path + "evil",
            "/.well-knownevil",
            "/unrelated",
        ):
            _assert_generated_service(ingress, host, path, "frontend", 3080)
        _assert_generated_service(ingress, host, "/api/v1/mcp", "backend", 8000)
    _assert_generated_service(ingress, "api.example.test", "/v1/chat/completions", "lumen", 8012)
    _assert_generated_service(ingress, "app.example.test", "/v1/chat/completions", "frontend", 3080)
    if mcp_host == "mcp.example.test":
        for path in (
            "/",
            "/api/v1/mcp",
            "/v1/chat/completions",
            "/oauth/mcp/authorize",
            "/mcpevil",
            resource_path + "evil",
        ):
            assert _generated_service(ingress, mcp_host, path) is None
    assert _generated_service(ingress, "unknown.example.test", resource_path) is None


@pytest.mark.parametrize("root_suffix", ["", "/"])
def test_generated_ingress_exposes_only_root_mcp_routes_on_dedicated_host(root_suffix):
    cfg = {
        "app": {"frontend_base_url": "https://app.example.test", "public_api_base": "https://api.example.test"},
        "services": {"mcp": True},
        "mcp": {"public_url": f"https://mcp.example.test{root_suffix}"},
    }
    config = tomllib.loads(yaml.safe_load(render_configmap(cfg))["data"]["afterglow.conf"])
    assert config["mcp"]["public_url"] == cfg["mcp"]["public_url"]
    ingress = list(yaml.safe_load_all(render_ingress(cfg)))
    paths = next(
        rule["http"]["paths"]
        for document in ingress
        for rule in document["spec"]["rules"]
        if rule["host"] == "mcp.example.test"
    )
    assert {(path["path"], path["pathType"]) for path in paths} == {
        ("/", "Exact"),
        ("/oauth/", "Prefix"),
        ("/.well-known/", "Prefix"),
    }
    for path in (
        "/",
        "/oauth/register",
        "/oauth/authorize",
        "/oauth/token",
        "/oauth/revoke",
        "/.well-known/oauth-protected-resource",
    ):
        _assert_generated_service(ingress, "mcp.example.test", path, "backend", 8000)
    for path in (
        "/api/v1/mcp",
        "/api/v1/auth/login",
        "/v1/models",
        "/anything",
        "/mcpevil",
        "/oauthevil",
        "/.well-knownevil",
    ):
        assert _generated_service(ingress, "mcp.example.test", path) is None
    _assert_generated_service(ingress, "app.example.test", "/oauth/mcp/authorize", "frontend", 3080)


@pytest.mark.parametrize("host", ["app.example.test", "api.example.test", "APP.example.test:443"])
def test_generated_ingress_rejects_shared_root_resource(host):
    cfg = {
        "app": {"frontend_base_url": "https://app.example.test", "public_api_base": "https://api.example.test"},
        "services": {"mcp": True},
        "mcp": {"public_url": f"https://{host}/"},
    }
    with pytest.raises(ValueError, match="requires a dedicated host"):
        render_ingress(cfg)


@pytest.mark.parametrize("services", [{}, {"mcp": False}, {"mcp": True}])
@pytest.mark.parametrize("mcp", [{}, {"public_url": ""}])
def test_generated_ingress_preserves_default_resource_and_frontend_fallback(services, mcp):
    cfg = {"cors": {"origins": "https://app.example.test"}, "services": services, "mcp": mcp}
    ingress = list(yaml.safe_load_all(render_ingress(cfg)))
    config = tomllib.loads(yaml.safe_load(render_configmap(cfg))["data"]["afterglow.conf"])
    assert config.get("mcp", {}).get("public_url", "") == ""
    assert config["app"]["public_api_base"] + "/api/v1/mcp" == "https://app.example.test/api/v1/mcp"
    assert ingress[0]["spec"]["tls"][0]["hosts"] == ["app.example.test"]
    for path in ("/api/v1/mcp", "/api/v1/mcp/oauth/token", "/.well-known/oauth-protected-resource/api/v1/mcp"):
        _assert_generated_service(ingress, "app.example.test", path, "backend", 8000)
    for path in ("/", "/mcp", "/mcpevil", "/oauth/mcp/authorize", "/v1/models", "/unrelated"):
        _assert_generated_service(ingress, "app.example.test", path, "frontend", 3080)


def test_generated_ingress_ignores_explicit_resource_when_mcp_disabled():
    cfg = {
        "app": {"frontend_base_url": "https://app.example.test"},
        "services": {"mcp": False},
        "mcp": {"public_url": "https://mcp.example.test/"},
    }
    ingress = list(yaml.safe_load_all(render_ingress(cfg)))
    assert ingress[0]["spec"]["tls"][0]["hosts"] == ["app.example.test"]
    assert _generated_service(ingress, "mcp.example.test", "/") is None
    _assert_generated_service(ingress, "app.example.test", "/oauth/mcp/authorize", "frontend", 3080)


@pytest.mark.parametrize(
    "namespace,host", [("afterglow", "operator.example.test"), ("afterglow-dev", "dev.operator.example.test")]
)
def test_generator_cli_writes_matching_config_and_ingress(tmp_path, monkeypatch, namespace, host):
    config_path = tmp_path / "afterglow.conf"
    config_path.write_text(
        '[app]\nsecret_key = "0123456789abcdef0123456789abcdef"\n'
        f'frontend_base_url = "https://{host}"\npublic_api_base = "https://{host}"\n'
        "[services]\nmcp = true\n"
        f'[mcp]\npublic_url = "https://{host}/mcp"\n',
        encoding="utf-8",
    )
    output_dir = tmp_path / "generated"
    monkeypatch.setattr(
        sys,
        "argv",
        ["generate_k8s.py", "--config", str(config_path), "--output-dir", str(output_dir), "--namespace", namespace],
    )
    main()
    ingress = list(yaml.safe_load_all((output_dir / "ingress.yaml").read_text(encoding="utf-8")))
    configmap = yaml.safe_load((output_dir / "configmap.yaml").read_text(encoding="utf-8"))
    assert tomllib.loads(configmap["data"]["afterglow.conf"])["mcp"]["public_url"] == f"https://{host}/mcp"
    assert all(
        document["metadata"]["namespace"] == configmap["metadata"]["namespace"] == namespace for document in ingress
    )
    _assert_generated_service(ingress, host, "/mcp", "backend", 8000)
    _assert_generated_service(ingress, host, "/mcp/oauth/token", "backend", 8000)
    _assert_generated_service(ingress, host, "/.well-known/oauth-protected-resource/mcp", "backend", 8000)
    _assert_generated_service(ingress, host, "/oauth/mcp/authorize", "frontend", 3080)
    _assert_generated_service(ingress, host, "/mcpevil", "frontend", 3080)


def test_generator_cli_rejects_shared_root_before_writing_any_manifests(tmp_path, monkeypatch):
    config_path = tmp_path / "afterglow.conf"
    config_path.write_text(
        '[app]\nsecret_key = "0123456789abcdef0123456789abcdef"\n'
        'frontend_base_url = "https://operator.example.test"\n'
        "[services]\nmcp = true\n"
        '[mcp]\npublic_url = "https://operator.example.test/"\n',
        encoding="utf-8",
    )
    output_dir = tmp_path / "generated"
    monkeypatch.setattr(sys, "argv", ["generate_k8s.py", "--config", str(config_path), "--output-dir", str(output_dir)])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    assert not output_dir.exists()


def test_generator_cli_dry_run_includes_ingress_without_writing(tmp_path, monkeypatch, capsys):
    config_path = tmp_path / "afterglow.conf"
    config_path.write_text(
        '[app]\nsecret_key = "0123456789abcdef0123456789abcdef"\n'
        "[services]\nmcp = true\n"
        '[mcp]\npublic_url = "https://mcp.example.test/"\n',
        encoding="utf-8",
    )
    output_dir = tmp_path / "generated"
    monkeypatch.setattr(
        sys,
        "argv",
        ["generate_k8s.py", "--config", str(config_path), "--output-dir", str(output_dir), "--dry-run"],
    )
    main()
    output = capsys.readouterr().out
    # Only public documents are previewed; no Secret or private deployment.
    ingress = [doc for doc in yaml.safe_load_all(output) if doc["kind"] == "Ingress"]
    assert "0123456789abcdef0123456789abcdef" not in output
    _assert_generated_service(ingress, "mcp.example.test", "/", "backend", 8000)
    assert _generated_service(ingress, "mcp.example.test", "/api/v1/auth/login") is None
    assert not output_dir.exists()


def test_render_mcp_lumen_bridge_credential_only_in_secret():
    credential = "lumen-mcp-bridge-secret-sentinel-0123456789abcdef"
    cfg = {
        "app": {"secret_key": "application-secret-key-sentinel-0123456789abcdef"},
        "mcp": {"lumen_service_token": credential},
    }

    assert credential not in _render_toml_for_k8s(cfg)
    secret = yaml.safe_load(render_secret(cfg))
    assert secret["stringData"]["LUMEN_MCP_SERVICE_TOKEN"] == credential


def test_render_k3s_gpu_admission_credential_only_in_secret():
    credential = "k3s-gpu-admission-secret-sentinel-0123456789abcdef"
    cfg = {
        "app": {"secret_key": "application-secret-key-sentinel-0123456789abcdef"},
        "k3s": {"gpu_admission_token": credential},
    }

    assert credential not in _render_toml_for_k8s(cfg)
    secret = yaml.safe_load(render_secret(cfg))
    assert secret["stringData"]["K3S_GPU_ADMISSION_TOKEN"] == credential


def test_render_toml_includes_login_branding_paths():
    result = _render_toml_for_k8s({"app": {"logo_dark_path": "/brand-dark.png", "logo_light_path": "/brand-light.png"}})

    assert 'logo_dark_path = "/brand-dark.png"' in result
    assert 'logo_light_path = "/brand-light.png"' in result


def test_render_toml_includes_worker_runtime_defaults():
    result = _render_toml_for_k8s({})

    assert "[worker_runtime]" in result
    assert 'mode = "static"' in result
    assert "reconcile_interval = 30" in result
    assert "fail_closed = true" in result
    assert "[worker_runtime.workers.notion_worker]" in result
    assert 'module = "app.notion_worker"' in result
    assert "[worker_runtime.docker]" in result
    assert 'config_mount = "/app/afterglow.conf"' in result
    assert "[worker_runtime.kubernetes]" in result
    assert 'namespace = "afterglow"' in result
    assert 'service_account_token_path = "/var/run/secrets/kubernetes.io/serviceaccount/token"' in result
    assert 'service_account_ca_path = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"' in result
    assert "manage_deployments = false" in result


def test_render_toml_includes_logging_config():
    result = _render_toml_for_k8s({"logging": {"log_directory": "/app/logs", "max_bytes": 52428800}})

    assert "[logging]" in result
    assert 'log_directory = "/app/logs"' in result
    assert "max_bytes = 52428800" in result


def test_render_toml_and_configmap_exclude_secret_values():
    sentinels = {
        "openstack_password": "worker-runtime-openstack-secret-sentinel",
        "app_secret_key": "worker-runtime-app-secret-sentinel-0123456789abcdef",
        "database_url": "worker-runtime-db-secret-sentinel",
        "prometheus_password": "worker-runtime-prom-secret-sentinel",
        "monitoring_sd_token": "worker-runtime-monitoring-token-sentinel",
        "notion_encryption_key": "worker-runtime-notion-secret-sentinel",
        "smtp_password": "worker-runtime-smtp-secret-sentinel",
        "builder_ssh_private_key": "worker-runtime-builder-key-sentinel",
        "service_account_token_contents": "worker-runtime-sa-token-secret-sentinel",
        "service_account_ca_contents": "worker-runtime-sa-ca-secret-sentinel",
    }
    cfg = {
        "openstack": {"password": sentinels["openstack_password"]},
        "app": {"secret_key": sentinels["app_secret_key"]},
        "database": {"url": sentinels["database_url"]},
        "monitoring": {
            "prometheus_password": sentinels["prometheus_password"],
            "sd_token": sentinels["monitoring_sd_token"],
        },
        "notion": {"config_encryption_key": sentinels["notion_encryption_key"]},
        "smtp": {
            "host": "smtp.example.com",
            "password": sentinels["smtp_password"],
        },
        "builder": {"ssh_private_key": sentinels["builder_ssh_private_key"]},
        "waygate": {"callback_base_url": "https://legacy-waygate.example"},
        "worker_runtime": {
            "kubernetes": {
                "service_account_token_path": "/var/run/secrets/afterglow/token",
                "service_account_ca_path": "/var/run/secrets/afterglow/ca.crt",
                "service_account_token_contents": sentinels["service_account_token_contents"],
                "service_account_ca_contents": sentinels["service_account_ca_contents"],
            }
        },
    }

    toml_output = _render_toml_for_k8s(cfg)
    configmap_output = render_configmap(cfg)
    configmap_doc = yaml.safe_load(configmap_output)

    assert 'service_account_token_path = "/var/run/secrets/afterglow/token"' in toml_output
    assert 'service_account_ca_path = "/var/run/secrets/afterglow/ca.crt"' in toml_output
    assert 'service_account_token_path = "/var/run/secrets/afterglow/token"' in configmap_doc["data"]["afterglow.conf"]
    assert 'service_account_ca_path = "/var/run/secrets/afterglow/ca.crt"' in configmap_doc["data"]["afterglow.conf"]
    assert "[waygate]" not in toml_output

    for sentinel in sentinels.values():
        assert sentinel not in toml_output
        assert sentinel not in configmap_output


def test_dev_override_renders_dev_urls(tmp_path):
    base_config = tmp_path / "afterglow.conf"
    base_config.write_text(
        """
[app]
frontend_base_url = "https://cloud.dmslab.re.kr"
public_api_base = "https://cloud.dmslab.re.kr"

[instance_health]
callback_base_url = "https://cloud.dmslab.re.kr"

[cors]
origins = "https://cloud.dmslab.re.kr"
""".strip(),
        encoding="utf-8",
    )
    cfg = load_config(
        base_config,
        [ROOT / "deploy" / "afterglow-dev.conf"],
    )
    configmap = yaml.safe_load(render_configmap(cfg, namespace="afterglow-dev"))
    toml = configmap["data"]["afterglow.conf"]

    assert configmap["data"]["APP_ORIGIN"] == "https://test.cloud.dmslab.re.kr"
    assert configmap["data"]["PUBLIC_API_BASE"] == "https://test.cloud.dmslab.re.kr"
    assert 'frontend_base_url = "https://test.cloud.dmslab.re.kr"' in toml
    assert 'public_api_base = "https://test.cloud.dmslab.re.kr"' in toml
    assert 'origins = "https://test.cloud.dmslab.re.kr"' in toml
    assert 'namespace = "afterglow-dev"' in toml


def test_prod_override_renders_prod_urls(tmp_path):
    base_config = tmp_path / "afterglow.conf"
    base_config.write_text('[app]\nsite_name = "base"\n', encoding="utf-8")
    cfg = load_config(
        base_config,
        [ROOT / "deploy" / "afterglow-prod.conf"],
    )
    configmap = yaml.safe_load(render_configmap(cfg, namespace="afterglow"))
    toml = configmap["data"]["afterglow.conf"]

    assert configmap["data"]["APP_ORIGIN"] == "https://cloud.dmslab.re.kr"
    assert configmap["data"]["PUBLIC_API_BASE"] == "https://cloud.dmslab.re.kr"
    assert 'callback_base_url = "https://cloud.dmslab.re.kr"' in toml
    assert 'namespace = "afterglow"' in toml


def test_render_manifests_support_dev_namespace():
    secret = yaml.safe_load(
        render_secret(
            {"app": {"secret_key": "0123456789abcdef0123456789abcdef"}},
            namespace="afterglow-dev",
        )
    )
    configmap = yaml.safe_load(render_configmap({}, namespace="afterglow-dev"))
    grafana = yaml.safe_load(render_grafana_deployment({}, namespace="afterglow-dev"))

    assert secret["metadata"]["namespace"] == "afterglow-dev"
    assert configmap["metadata"]["namespace"] == "afterglow-dev"
    assert grafana["metadata"]["namespace"] == "afterglow-dev"
    assert '\nnamespace = "afterglow-dev"\n' in configmap["data"]["afterglow.conf"]
    assert '\nnamespace = "afterglow"\n' not in configmap["data"]["afterglow.conf"]


def test_render_configmap_falls_back_to_backend_port_without_public_origin():
    result = render_configmap({"app": {"backend_port": 8123}})
    doc = yaml.safe_load(result)

    assert doc["data"]["PUBLIC_API_BASE"] == "http://localhost:8123"
    assert 'public_api_base = "http://localhost:8123"' in doc["data"]["afterglow.conf"]


def test_render_configmap_exposes_frontend_runtime_keys():
    result = render_configmap(
        {
            "cors": {"origins": "https://afterglow.example.com,http://localhost:3080"},
            "openstack": {"s3_endpoint": "https://s3.example.com"},
            "monitoring": {"grafana_base_url": "https://grafana.example.com"},
        }
    )
    doc = yaml.safe_load(result)

    assert doc["data"]["APP_ORIGIN"] == "https://afterglow.example.com"
    assert doc["data"]["PUBLIC_S3_BASE"] == "https://s3.example.com"
    assert doc["data"]["APP_GRAFANA_BASE"] == "https://grafana.example.com"
    assert doc["data"]["PUBLIC_API_BASE"] == "https://afterglow.example.com"
    assert "APP_S3_BASE" not in doc["data"]
    assert 'public_api_base = "https://afterglow.example.com"' in doc["data"]["afterglow.conf"]


def test_render_secret_rejects_default_secret_key():
    try:
        render_secret({"app": {"secret_key": "change-me-in-production"}})
    except ValueError as exc:
        assert "기본 SECRET_KEY" in str(exc)
    else:
        raise AssertionError("render_secret must reject the default SECRET_KEY")


def test_render_secret_accepts_strong_secret_key():
    result = render_secret({"app": {"secret_key": "0123456789abcdef0123456789abcdef"}})

    assert 'SECRET_KEY: "0123456789abcdef0123456789abcdef"' in result


def test_render_secret_always_emits_manifest_required_keys():
    result = render_secret({"app": {"secret_key": "0123456789abcdef0123456789abcdef"}})
    doc = yaml.safe_load(result)

    keys = doc["stringData"]
    assert keys["K3S_KUBECONFIG_ENCRYPTION_KEY"] == ""
    assert keys["DATABASE_URL"] == ""
    assert keys["K3S_GPU_ADMISSION_TOKEN"] == ""
    assert keys["PROMETHEUS_PASSWORD"] == ""
    assert keys["BUILDER_SSH_PRIVATE_KEY"] == ""


class TestRenderGrafanaDeployment:
    def test_default_password_is_admin(self):
        result = render_grafana_deployment({})
        assert '"admin"' in result

    def test_custom_password_from_cfg(self):
        cfg = {"monitoring": {"grafana_admin_password": "s3cret"}}
        result = render_grafana_deployment(cfg)
        assert '"s3cret"' in result
        assert '"admin"' not in result

    def test_volumes_present(self):
        result = render_grafana_deployment({})
        assert "grafana-datasource" in result
        assert "grafana-dashboards-provider" in result
        assert "grafana-dashboards" in result

    def test_volume_mounts_present(self):
        result = render_grafana_deployment({})
        assert "/etc/grafana/provisioning/datasources" in result
        assert "/etc/grafana/provisioning/dashboards" in result
        assert "/var/lib/grafana/dashboards" in result

    def test_anonymous_auth_env_vars_present(self):
        result = render_grafana_deployment({})
        assert "GF_AUTH_ANONYMOUS_ENABLED" in result
        assert "GF_AUTH_ANONYMOUS_ORG_ROLE" in result
        assert "GF_SECURITY_ALLOW_EMBEDDING" in result

    def test_output_is_valid_yaml(self):
        result = render_grafana_deployment({})
        docs = list(yaml.safe_load_all(result))
        assert len(docs) >= 1
        doc = docs[0]
        assert doc["kind"] == "Deployment"
        assert doc["metadata"]["name"] == "grafana"


def _auth_generation_config():
    return {
        "app": {
            "secret_key": "0123456789abcdef0123456789abcdef",
            "frontend_base_url": "https://cloud.example.com",
        },
        "auth": {
            "providers": {
                "sso_common": {
                    "name": "Common GitHub Enterprise",
                    "kind": "github",
                    "enabled": True,
                    "authorization_url": "https://github.example.com/login/oauth/authorize?audience=cloud",
                    "token_url": "https://github.example.com/login/oauth/access_token",
                    "api_url": "https://github.example.com/api/v3",
                    "client_id": "common-client",
                    "client_secret": 'common-secret:"quoted"\nsecond-line',
                    "scopes": ["read:user", "user:email", "read:org"],
                    "keystone_idp_id": "github-enterprise",
                    "keystone_protocol_id": "openid",
                    "federation_token_type": "access_token",
                    "token_endpoint_auth_method": "client_secret_post",
                },
                "gitlab": {
                    "name": "DMSLab GitLab",
                    "kind": "oidc",
                    "enabled": True,
                    "issuer_url": "https://git.dmslab.re.kr",
                    "client_id": "gitlab-client",
                    "client_secret": "gitlab-private-secret",
                    "scopes": ["openid", "email", "profile"],
                    "keystone_idp_id": "gitlab",
                    "keystone_protocol_id": "openid",
                    "federation_token_type": "id_token",
                    "token_endpoint_auth_method": "client_secret_post",
                },
                "paused": {
                    "name": "Disabled GitHub",
                    "kind": "github",
                    "enabled": False,
                    "client_id": "paused-client",
                    "keystone_idp_id": "paused",
                    "keystone_protocol_id": "openid",
                },
            },
            "default": {"allow_providers": ["sso_common", "paused"]},
            "domain": {
                "DmsLab-ID": {"allow_providers": ["gitlab", "sso_common"]},
                "Other-ID": {"allow_providers": []},
            },
        },
    }


@pytest.mark.parametrize("namespace", ["afterglow", "afterglow-dev"])
@pytest.mark.parametrize("default_allowlist", [None, [], ["sso_common", "paused"]])
def test_auth_renderers_reconstruct_runtime_providers_and_selection(
    tmp_path, monkeypatch, namespace, default_allowlist
):
    import copy
    import os
    from unittest.mock import patch

    from generate_k8s import render_artifacts

    from app import config as app_config

    cfg = _auth_generation_config()
    cfg["auth"]["public_signup_enabled"] = True
    cfg["auth"]["signup_email_domains"] = ["gmail.com", "konkuk.ac.kr"]
    cfg["auth"]["domain"]["DmsLab-ID"]["auto_join_email_domains"] = {
        "gitlab": ["gmail.com", "konkuk.ac.kr"],
    }
    cfg["auth"]["domain"]["Other-ID"]["auto_join_email_domains"] = {}
    if default_allowlist is None:
        cfg["auth"].pop("default")
    else:
        cfg["auth"]["default"] = {"allow_providers": default_allowlist}
    cfg["auth"]["domain"]["Inherited-ID"] = {}
    original = copy.deepcopy(cfg)
    artifacts = render_artifacts(cfg, namespace)
    configmap = yaml.safe_load(artifacts["configmap.yaml"])
    secret = yaml.safe_load(artifacts["secret.yaml"])
    assert configmap["metadata"]["namespace"] == namespace
    assert secret["metadata"]["namespace"] == namespace
    public_auth = tomllib.loads(configmap["data"]["afterglow.conf"])["auth"]
    for key, provider in cfg["auth"]["providers"].items():
        assert public_auth["providers"][key] == {
            field: value for field, value in provider.items() if field != "client_secret"
        }
        if provider.get("client_secret"):
            env_key = f"AUTH__PROVIDERS__{key.upper()}__CLIENT_SECRET"
            assert secret["stringData"][env_key] == provider["client_secret"]
            assert provider["client_secret"] not in artifacts["configmap.yaml"]
    assert public_auth.get("default") == cfg["auth"].get("default")
    assert public_auth["domain"] == cfg["auth"]["domain"]
    assert cfg == original

    config_path = tmp_path / "afterglow.conf"
    config_path.write_text(configmap["data"]["afterglow.conf"], encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(app_config, "_config_candidates", lambda: [config_path])
    kustomization = yaml.safe_load(artifacts["kustomization.yaml"])
    patch_paths = {entry["path"] for entry in kustomization["patches"]}
    assert patch_paths == {"auth-backend-env.yaml", "auth-notion-worker-env.yaml"}
    expected = app_config.AuthSettings.model_validate(cfg["auth"])
    for workload in ("backend", "notion-worker"):
        deployment_patch = yaml.safe_load(artifacts[f"auth-{workload}-env.yaml"])
        assert deployment_patch["metadata"]["name"] == workload
        container = deployment_patch["spec"]["template"]["spec"]["containers"][0]
        assert container["name"] == workload
        environment = {"SECRET_KEY": cfg["app"]["secret_key"], "AFTERGLOW_ENV": "development"}
        for entry in container["env"]:
            ref = entry["valueFrom"]["secretKeyRef"]
            assert ref["name"] == secret["metadata"]["name"]
            assert ref["key"] == entry["name"]
            if ref["key"] in secret["stringData"]:
                environment[entry["name"]] = secret["stringData"][ref["key"]]
            else:
                assert ref["optional"] is True
                assert entry["name"] == "AUTH__PROVIDERS__PAUSED__CLIENT_SECRET"
        assert {key for key in environment if key.startswith("AUTH__")} == {
            "AUTH__PROVIDERS__SSO_COMMON__CLIENT_SECRET",
            "AUTH__PROVIDERS__GITLAB__CLIENT_SECRET",
        }
        app_config.load_raw_toml.cache_clear()
        app_config.get_settings.cache_clear()
        try:
            with patch.dict(os.environ, environment, clear=True):
                settings = app_config.get_settings()
                assert settings.auth == expected
                assert settings.auth.providers["gitlab"].client_secret.get_secret_value() == "gitlab-private-secret"
                assert settings.auth.providers["sso_common"].client_secret.get_secret_value() == (
                    'common-secret:"quoted"\nsecond-line'
                )
        finally:
            app_config.load_raw_toml.cache_clear()
            app_config.get_settings.cache_clear()


@pytest.mark.parametrize(
    "auth",
    [
        {"provider": {"client_secret": "private-auth-sentinel"}},
        {"providers": []},
        {"providers": {"GitLab": {"client_secret": "private-auth-sentinel"}}},
        {"providers": {"gitlab_": {"client_secret": "private-auth-sentinel"}}},
        {"providers": {"git__lab": {"client_secret": "private-auth-sentinel"}}},
        {"providers": {"gitlab": {"client_secert": "private-auth-sentinel"}}},
        {"providers": {"gitlab": {"enabled": "false"}}},
        {"providers": {"gitlab": {"scopes": "openid email"}}},
        {"default": {"allow_providers": ["typo"]}},
        {"domain": {"DmsLab-ID": {"allow_providers": ["missing"]}}},
        {"default": {"providers": []}},
        {"domain": {"DmsLab-ID": {"providers": []}}},
        {"default": {"allow_providers": "gitlab"}},
        {"default": {"allow_providers": [1]}},
        {"domain": {"DmsLab-ID": {"password_enabled": False}}},
        {"domain": {"": {"allow_providers": []}}},
    ],
)
def test_auth_projection_rejects_bad_structures_without_leaking_secrets(auth):
    cfg = {"app": {"secret_key": "0123456789abcdef0123456789abcdef"}, "auth": auth}
    for renderer in (render_secret, render_configmap):
        with pytest.raises(ValueError) as exc:
            renderer(cfg)
        assert "private-auth-sentinel" not in str(exc.value)


def test_auth_absent_adds_no_secret_keys_or_workload_patches():
    from generate_k8s import render_artifacts

    cfg = {"app": {"secret_key": "0123456789abcdef0123456789abcdef"}}
    artifacts = render_artifacts(cfg)
    configmap = yaml.safe_load(artifacts["configmap.yaml"])
    secret = yaml.safe_load(artifacts["secret.yaml"])
    assert "auth" not in tomllib.loads(configmap["data"]["afterglow.conf"])
    assert not any(key.startswith("AUTH__") for key in secret["stringData"])
    assert "patches" not in yaml.safe_load(artifacts["kustomization.yaml"])
