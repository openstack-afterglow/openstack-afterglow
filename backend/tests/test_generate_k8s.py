"""generate_k8s.py 단위 테스트."""

import sys
from pathlib import Path

import yaml

# generate_k8s.py is at project root, not in backend/
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from generate_k8s import (  # noqa: E402
    _render_toml_for_k8s,
    load_config,
    render_configmap,
    render_grafana_deployment,
    render_secret,
)


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


def test_render_k3s_provisioning_credential_only_in_secret():
    credential = "k3s-provisioning-secret-sentinel-0123456789abcdef"
    cfg = {
        "app": {"secret_key": "application-secret-key-sentinel-0123456789abcdef"},
        "k3s": {"provisioning_token": credential},
    }

    assert credential not in _render_toml_for_k8s(cfg)
    secret = yaml.safe_load(render_secret(cfg))
    assert secret["stringData"]["K3S_PROVISIONING_TOKEN"] == credential


def test_render_toml_includes_login_branding_paths():
    result = _render_toml_for_k8s({"app": {"logo_dark_path": "/brand-dark.png", "logo_light_path": "/brand-light.png"}})

    assert 'logo_dark_path = "/brand-dark.png"' in result
    assert 'logo_light_path = "/brand-light.png"' in result


def test_render_toml_uses_swapped_login_branding_defaults_when_paths_are_omitted():
    result = _render_toml_for_k8s({"app": {}})

    assert 'logo_dark_path = "/logo-white.png"' in result
    assert 'logo_light_path = "/logo-dark.png"' in result


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
        "oidc_client_secret": "worker-runtime-oidc-secret-sentinel",
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
        "gitlab_oidc": {"client_secret": sentinels["oidc_client_secret"]},
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

[gitlab_oidc]
redirect_uri = "https://cloud.dmslab.re.kr/auth/gitlab/callback"
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
    assert 'redirect_uri = "https://test.cloud.dmslab.re.kr/auth/gitlab/callback"' in toml
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
    assert 'redirect_uri = "https://cloud.dmslab.re.kr/auth/gitlab/callback"' in toml
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
    assert keys["GITLAB_OIDC_CLIENT_SECRET"] == ""
    assert keys["K3S_KUBECONFIG_ENCRYPTION_KEY"] == ""
    assert keys["DATABASE_URL"] == ""
    assert keys["K3S_GPU_ADMISSION_TOKEN"] == ""
    assert keys["K3S_PROVISIONING_TOKEN"] == ""
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
