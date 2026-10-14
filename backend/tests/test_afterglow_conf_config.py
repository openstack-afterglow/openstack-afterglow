"""afterglow.conf compatibility tests for runtime and deployment config loading."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from jinja2 import Environment, StrictUndefined

from app import config as app_config

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config2helm  # noqa: E402
import generate_k8s  # noqa: E402


def test_config_to_helm_preserves_public_mcp_configuration():
    converted = config2helm.convert(
        {
            "services": {"mcp": True},
            "mcp": {
                "public_url": "https://mcp.example.test/control-plane/mcp",
                "oauth_consent_url": "https://app.example.test/oauth/mcp/authorize",
            },
        },
        include_secrets=False,
    )

    assert converted["services"]["mcp"] is True
    assert converted["mcp"] == {
        "publicUrl": "https://mcp.example.test/control-plane/mcp",
        "oauthConsentUrl": "https://app.example.test/oauth/mcp/authorize",
    }


@pytest.mark.parametrize(
    ("public_api_base", "expected_resource_path"),
    [
        ("https://mcp.example.test", "/api/v1/mcp"),
        ("https://mcp.example.test/gateway/", "/gateway/api/v1/mcp"),
    ],
)
def test_helm_mcp_ingress_falls_back_to_public_api_base(public_api_base, expected_resource_path):
    helm = shutil.which("helm")
    if helm is None:
        pytest.skip("Helm is required to render the ingress contract")

    rendered = subprocess.run(
        [
            helm,
            "template",
            "afterglow",
            "helm/afterglow",
            "--show-only",
            "templates/ingress.yaml",
            "--set",
            "services.mcp=true",
            "--set",
            f"app.publicApiBase={public_api_base}",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    ingress = next(
        document
        for document in yaml.safe_load_all(rendered.stdout)
        if document["metadata"]["name"] == "afterglow-mcp-ingress"
    )
    mcp_rule = next(rule for rule in ingress["spec"]["rules"] if rule["host"] == "mcp.example.test")
    paths = {entry["path"] for entry in mcp_rule["http"]["paths"]}

    assert "mcp.example.test" in ingress["spec"]["tls"][0]["hosts"]
    assert paths == {expected_resource_path, expected_resource_path + "/", "/.well-known/"}


def _render_helm_ingress(*overrides: str) -> subprocess.CompletedProcess[str]:
    helm = shutil.which("helm")
    if helm is None:
        pytest.skip("Helm is required to render the ingress contract")
    arguments = [helm, "template", "afterglow", "helm/afterglow", "--show-only", "templates/ingress.yaml"]
    for override in ("services.mcp=true", *overrides):
        arguments.extend(("--set", override))
    return subprocess.run(arguments, cwd=ROOT, capture_output=True, text=True)


def test_helm_explicit_origin_mcp_url_publishes_only_mcp_and_oauth_paths_on_the_dedicated_host():
    rendered = _render_helm_ingress("mcp.publicUrl=https://mcp.example.test/")
    assert rendered.returncode == 0, rendered.stderr
    ingress = next(
        document
        for document in yaml.safe_load_all(rendered.stdout)
        if document["metadata"]["name"] == "afterglow-mcp-ingress"
    )
    mcp_rule = next(rule for rule in ingress["spec"]["rules"] if rule["host"] == "mcp.example.test")

    # The exact root resource, OAuth aliases and discovery reach the backend; /api/* does not.
    assert [
        (entry["path"], entry["pathType"], entry["backend"]["service"]["name"]) for entry in mcp_rule["http"]["paths"]
    ] == [("/", "Exact", "backend"), ("/oauth/", "Prefix", "backend"), ("/.well-known/", "Prefix", "backend")]
    assert "mcp.example.test" in ingress["spec"]["tls"][0]["hosts"]


@pytest.mark.parametrize("authority", ["cloud.example.test", "CLOUD.EXAMPLE.TEST:443"])
def test_helm_refuses_an_origin_root_mcp_url_on_the_shared_web_host(authority):
    rendered = _render_helm_ingress("ingress.host=cloud.example.test", f"mcp.publicUrl=https://{authority}")

    assert rendered.returncode != 0
    assert "dedicated host" in rendered.stderr


def _ingress_service(ingresses, host, request_path):
    matches = []
    for ingress in ingresses:
        priority = ingress["metadata"].get("annotations", {}).get("traefik.ingress.kubernetes.io/router.priority")
        for rule in ingress["spec"]["rules"]:
            if rule["host"] != host:
                continue
            for entry in rule["http"]["paths"]:
                path = entry["path"]
                exact = entry["pathType"] == "Exact"
                if request_path == path if exact else request_path.startswith(path):
                    matcher = "Path" if exact else "PathPrefix"
                    rule_length = len(f"Host(`{host}`) && {matcher}(`{path}`)")
                    matches.append((int(priority) if priority else rule_length, entry))
    return max(matches, key=lambda item: item[0])[1]["backend"]["service"]["name"] if matches else None


@pytest.mark.parametrize("host_kind", ["web", "api"])
@pytest.mark.parametrize("resource_path", ["/mcp", "/control-plane/mcp"])
@pytest.mark.parametrize("authority", ["cloud.dmslab.re.kr", "CLOUD.DMSLAB.RE.KR:443"])
def test_helm_explicit_shared_mcp_resource_routes_oauth_discovery_without_hijacking_frontend(
    host_kind,
    resource_path,
    authority,
):
    host = "cloud.dmslab.re.kr"
    host_override = f"ingress.host={host}" if host_kind == "web" else f"ingress.apiHosts[0]={host}"
    rendered = _render_helm_ingress(host_override, f"mcp.publicUrl=https://{authority}{resource_path}///")
    assert rendered.returncode == 0, rendered.stderr
    ingresses = list(yaml.safe_load_all(rendered.stdout))
    ingress = next(document for document in ingresses if document["metadata"]["name"] == "afterglow-mcp-ingress")

    for path in (
        resource_path,
        resource_path + "/",
        resource_path + "/oauth/authorize",
        resource_path + "/oauth/register",
        resource_path + "/oauth/token",
        resource_path + "/oauth/revoke",
        "/.well-known/oauth-protected-resource" + resource_path,
        "/.well-known/oauth-authorization-server" + resource_path + "/oauth",
    ):
        assert _ingress_service(ingresses, host, path) == "backend", path
    for path in (resource_path + "evil", "/mcpevil", "/oauth/mcp/authorize", "/account", "/"):
        assert _ingress_service(ingresses, host, path) == "frontend", path
    annotations = ingress["metadata"]["annotations"]
    assert not any("rewrite" in key or "redirect" in key for key in annotations)
    assert host in ingress["spec"]["tls"][0]["hosts"]


def test_helm_unset_mcp_url_retains_shared_api_fallback():
    rendered = _render_helm_ingress(
        "ingress.host=cloud.dmslab.re.kr",
        "app.publicApiBase=https://cloud.dmslab.re.kr",
    )
    assert rendered.returncode == 0, rendered.stderr
    ingresses = list(yaml.safe_load_all(rendered.stdout))
    host = "cloud.dmslab.re.kr"
    assert _ingress_service(ingresses, host, "/api/v1/mcp") == "backend"
    assert _ingress_service(ingresses, host, "/api/v1/mcp/oauth/token") == "backend"
    assert _ingress_service(ingresses, host, "/.well-known/oauth-protected-resource/api/v1/mcp") == "backend"
    assert _ingress_service(ingresses, host, "/oauth/mcp/authorize") == "frontend"


@pytest.mark.parametrize(
    "public_url",
    ["", "https://cloud.dmslab.re.kr/mcp", "https://mcp.example.test/", "https://mcp.example.test/custom/%E2%9C%93"],
)
def test_kolla_mcp_override_preserves_explicit_urls_and_omits_unset_value(public_url):
    template = (ROOT / "deploy/kolla/ansible/roles/afterglow/templates/afterglow.kolla.conf.j2").read_text()
    start = template.index("{% if afterglow_mcp_public_url %}")
    stop = template.index("{% endif %}", start) + len("{% endif %}")
    environment = Environment(undefined=StrictUndefined)
    environment.filters["to_json"] = json.dumps
    override = tomllib.loads(environment.from_string(template[start:stop]).render(afterglow_mcp_public_url=public_url))
    if public_url:
        assert override == {"mcp": {"public_url": public_url}}
    else:
        # No empty Kolla key erases the operator source or the backend's fallback.
        assert override == {}


@pytest.fixture
def isolated_config_dir(tmp_path, monkeypatch):
    """Run file-discovery config tests in a temp cwd with cold config caches."""
    monkeypatch.chdir(tmp_path)
    app_config.load_raw_toml.cache_clear()
    app_config.get_settings.cache_clear()
    yield tmp_path
    app_config.load_raw_toml.cache_clear()
    app_config.get_settings.cache_clear()


@pytest.fixture
def isolated_debug_config_dir(isolated_config_dir, monkeypatch):
    """Restore all environment values seeded by get_settings after each case."""
    monkeypatch.setattr(app_config, "_config_candidates", lambda: [isolated_config_dir / "afterglow.conf"])
    with patch.dict(
        os.environ,
        {
            "AFTERGLOW_ENV": "development",
            "SECRET_KEY": "6ea4d2fb7c1e9d035a18be4f2740317c9d08ab72f3c46e901bf67ad5041c8ef2",
        },
        clear=True,
    ):
        yield isolated_config_dir


@pytest.mark.parametrize(
    ("config_text", "expected"),
    [
        pytest.param(None, False, id="no-config"),
        pytest.param('[app]\nsite_name = "Debug Test"\n', False, id="no-default-section"),
        pytest.param("[DEFAULT]\n", False, id="absent"),
        pytest.param("[DEFAULT]\ndebug = false\n", False, id="false"),
        pytest.param("[DEFAULT]\ndebug = true\n", True, id="true"),
    ],
)
def test_get_settings_debug_from_afterglow_conf(isolated_debug_config_dir, config_text, expected):
    if config_text is not None:
        (isolated_debug_config_dir / "afterglow.conf").write_text(config_text, encoding="utf-8")

    settings = app_config.get_settings()

    assert settings.debug is expected


@pytest.mark.parametrize(
    ("toml_debug", "env_debug", "expected"),
    [("false", "true", True), ("true", "false", False)],
)
def test_get_settings_debug_env_overrides_toml(isolated_debug_config_dir, toml_debug, env_debug, expected):
    (isolated_debug_config_dir / "afterglow.conf").write_text(f"[DEFAULT]\ndebug = {toml_debug}\n", encoding="utf-8")
    os.environ["DEBUG"] = env_debug

    settings = app_config.get_settings()

    assert settings.debug is expected


@pytest.mark.parametrize(
    ("base_debug", "override_debug", "env_debug", "expected"),
    [
        ("false", "true", None, True),
        ("true", "false", None, False),
        ("false", "true", "false", False),
        ("true", "false", "true", True),
    ],
)
def test_get_settings_debug_from_layered_config(
    isolated_debug_config_dir, base_debug, override_debug, env_debug, expected
):
    (isolated_debug_config_dir / "afterglow.conf").write_text(f"[DEFAULT]\ndebug = {base_debug}\n", encoding="utf-8")
    (isolated_debug_config_dir / "afterglow.local.conf").write_text(
        f"[DEFAULT]\ndebug = {override_debug}\n", encoding="utf-8"
    )
    if env_debug is not None:
        os.environ["DEBUG"] = env_debug

    settings = app_config.get_settings()

    assert settings.debug is expected


@pytest.mark.parametrize("env_debug", [None, "true", "false"])
@pytest.mark.parametrize("malformed_filename", ["afterglow.conf", "afterglow.local.conf"])
def test_get_settings_debug_rejects_malformed_toml(isolated_debug_config_dir, env_debug, malformed_filename):
    (isolated_debug_config_dir / "afterglow.conf").write_text("[DEFAULT]\ndebug = false\n", encoding="utf-8")
    (isolated_debug_config_dir / malformed_filename).write_text("[DEFAULT]\ndebug=True\n", encoding="utf-8")
    if env_debug is not None:
        os.environ["DEBUG"] = env_debug

    with pytest.raises(tomllib.TOMLDecodeError):
        app_config.get_settings()


def test_app_config_loads_afterglow_conf_toml_from_cwd(isolated_config_dir):
    (isolated_config_dir / "afterglow.conf").write_text(
        """
[app]
site_name = "Afterglow From Conf"

[cache]
redis_url = "redis://cache.example:6379/2"
""".strip(),
        encoding="utf-8",
    )

    raw = app_config.load_raw_toml()
    flat = app_config._load_toml()

    assert raw["app"]["site_name"] == "Afterglow From Conf"
    assert raw["cache"]["redis_url"] == "redis://cache.example:6379/2"
    assert flat["site_name"] == "Afterglow From Conf"
    assert flat["redis_url"] == "redis://cache.example:6379/2"


def test_app_config_loads_login_branding_paths_from_afterglow_conf(isolated_config_dir):
    (isolated_config_dir / "afterglow.conf").write_text(
        """
[app]
logo_dark_path = "/brand-dark.png"
logo_light_path = "/brand-light.png"
""".strip(),
        encoding="utf-8",
    )

    flat = app_config._load_toml()
    settings = app_config.Settings(**flat)

    assert flat["logo_dark_path"] == "/brand-dark.png"
    assert flat["logo_light_path"] == "/brand-light.png"
    assert settings.logo_dark_path == "/brand-dark.png"
    assert settings.logo_light_path == "/brand-light.png"


def test_app_config_loads_inbound_mcp_public_urls(isolated_config_dir):
    (isolated_config_dir / "afterglow.conf").write_text(
        """
[mcp]
public_url = "https://mcp.example.test/control-plane/mcp"
oauth_consent_url = "https://app.example.test/oauth/mcp/authorize"
""".strip(),
        encoding="utf-8",
    )

    flat = app_config._load_toml()
    settings = app_config.Settings(**flat)

    assert settings.mcp_public_url == "https://mcp.example.test/control-plane/mcp"
    assert settings.mcp_oauth_consent_url == "https://app.example.test/oauth/mcp/authorize"


def test_app_config_loads_logging_log_directory_from_afterglow_conf(isolated_config_dir):
    (isolated_config_dir / "afterglow.conf").write_text(
        """
[logging]
log_directory = "/var/log/kolla/afterglow_api"
max_bytes = 10485760
""".strip(),
        encoding="utf-8",
    )

    flat = app_config._load_toml()
    settings = app_config.Settings(**flat)

    assert flat["log_directory"] == "/var/log/kolla/afterglow_api"
    assert settings.log_directory == "/var/log/kolla/afterglow_api"
    assert flat["log_max_bytes"] == 10485760
    assert settings.log_max_bytes == 10485760


def test_empty_gitlab_oidc_secret_env_does_not_mask_toml(isolated_config_dir, monkeypatch):
    (isolated_config_dir / "afterglow.conf").write_text(
        """
[app]
secret_key = "0123456789abcdef0123456789abcdef"

[gitlab_oidc]
enabled = true
client_id = "configured-client"
client_secret = "configured-secret"
""".strip(),
        encoding="utf-8",
    )
    for key in (
        "GITLAB_OIDC_ENABLED",
        "GITLAB_OIDC_GITLAB_URL",
        "GITLAB_OIDC_CLIENT_ID",
        "GITLAB_OIDC_CLIENT_SECRET",
        "GITLAB_OIDC_IDP_ID",
        "GITLAB_OIDC_PROTOCOL_ID",
        "GITLAB_OIDC_REDIRECT_URI",
        "GITLAB_OIDC_SCOPES",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("GITLAB_OIDC_CLIENT_SECRET", "")

    settings = app_config.get_settings()

    assert settings.gitlab_oidc_enabled is True
    assert settings.gitlab_oidc_client_id == "configured-client"
    assert settings.gitlab_oidc_client_secret == "configured-secret"
    assert os.environ["GITLAB_OIDC_CLIENT_SECRET"] == "configured-secret"


def test_app_config_loads_openstack_insecure_and_cacert_from_afterglow_conf(isolated_config_dir, monkeypatch):
    (isolated_config_dir / "afterglow.conf").write_text(
        """
[openstack]
insecure = true
cacert = "/etc/ssl/certs/custom-ca.crt"
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.delenv("OS_INSECURE", raising=False)
    monkeypatch.delenv("OS_CACERT", raising=False)

    flat = app_config._load_toml()
    settings = app_config.Settings(**flat)

    assert flat["os_insecure"] is True
    assert flat["os_cacert"] == "/etc/ssl/certs/custom-ca.crt"
    assert settings.os_insecure is True
    assert settings.os_cacert == "/etc/ssl/certs/custom-ca.crt"
    assert settings.ssl_verify is False

    monkeypatch.setenv("OS_INSECURE", "false")
    monkeypatch.setenv("OS_CACERT", "/env/override-ca.crt")
    app_config.get_settings.cache_clear()
    settings_override = app_config.get_settings()
    assert settings_override.os_insecure is False
    assert settings_override.os_cacert == "/env/override-ca.crt"
    assert settings_override.ssl_verify == "/env/override-ca.crt"


def test_app_config_applies_matching_afterglow_conf_overrides(isolated_config_dir):
    (isolated_config_dir / "afterglow.conf").write_text(
        """
[app]
site_name = "Base Site"
logo_path = "/base-logo.png"

[cache]
redis_url = "redis://base-cache:6379/0"
ttl_fast = 11
""".strip(),
        encoding="utf-8",
    )
    (isolated_config_dir / "afterglow.local.conf").write_text(
        """
[app]
site_name = "Override Site"

[cache]
ttl_fast = 3
""".strip(),
        encoding="utf-8",
    )

    raw = app_config.load_raw_toml()
    flat = app_config._load_toml()

    assert raw["app"] == {
        "site_name": "Override Site",
        "logo_path": "/base-logo.png",
    }
    assert raw["cache"] == {
        "redis_url": "redis://base-cache:6379/0",
        "ttl_fast": 3,
    }
    assert flat["site_name"] == "Override Site"
    assert flat["logo_path"] == "/base-logo.png"
    assert flat["cache_ttl_fast"] == 3


def test_app_config_ignores_frontend_public_projection(isolated_config_dir):
    (isolated_config_dir / "afterglow.conf").write_text(
        """
[app]
public_api_base = ""
site_name = "Backend Site"
""".strip(),
        encoding="utf-8",
    )
    (isolated_config_dir / "afterglow.frontend.conf").write_text(
        """
[app]
public_api_base = "http://localhost:8000"
site_name = "Frontend Site"
""".strip(),
        encoding="utf-8",
    )

    raw = app_config.load_raw_toml()
    flat = app_config._load_toml()

    assert raw["app"] == {
        "public_api_base": "",
        "site_name": "Backend Site",
    }
    assert flat["public_api_base"] == ""
    assert flat["site_name"] == "Backend Site"


def test_app_config_ignores_legacy_config_toml_files(isolated_config_dir):
    (isolated_config_dir / "afterglow.conf").write_text(
        """
[app]
site_name = "Primary Site"
logo_path = "/primary-logo.png"

[cache]
redis_url = "redis://primary-cache:6379/0"
ttl_fast = 13
""".strip(),
        encoding="utf-8",
    )
    (isolated_config_dir / "config.toml").write_text(
        """
[app]
site_name = "Ignored Legacy Base"
""".strip(),
        encoding="utf-8",
    )
    (isolated_config_dir / "config.local.toml").write_text(
        """
[app]
site_name = "Ignored Legacy Override"

[cache]
ttl_fast = 4
""".strip(),
        encoding="utf-8",
    )

    raw = app_config.load_raw_toml()
    flat = app_config._load_toml()

    assert raw["app"] == {
        "site_name": "Primary Site",
        "logo_path": "/primary-logo.png",
    }
    assert raw["cache"] == {
        "redis_url": "redis://primary-cache:6379/0",
        "ttl_fast": 13,
    }
    assert flat["site_name"] == "Primary Site"
    assert flat["logo_path"] == "/primary-logo.png"
    assert flat["cache_ttl_fast"] == 13


def test_generate_k8s_main_accepts_explicit_afterglow_conf_path(tmp_path, monkeypatch, capsys):
    config_path = tmp_path / "afterglow.conf"
    config_path.write_text(
        """
[app]
site_name = "Explicit K8s Afterglow Conf"
secret_key = "0123456789abcdef0123456789abcdef"
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_k8s.py",
            "--config",
            str(config_path),
            "--dry-run",
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )

    generate_k8s.main()

    output = capsys.readouterr().out
    assert "afterglow.conf" in output
    assert "afterglow-prod.conf" in output
    assert 'site_name = "Explicit K8s Afterglow Conf"' in output


def test_k8s_python_manifests_use_production_secret_contract():
    """K8s Python services must fail closed and share afterglow-secrets/SECRET_KEY."""
    paths = [
        ROOT / "deploy/k8s-template/base/backend/deployment.yaml",
        ROOT / "deploy/k8s-template/base/worker/deployment.yaml",
        ROOT / "deploy/k8s-template/base/worker/notion-deployment.yaml",
    ]
    for path in paths:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        env = doc["spec"]["template"]["spec"]["containers"][0]["env"]
        by_name = {item["name"]: item for item in env}

        assert by_name["AFTERGLOW_ENV"]["value"] == "production"
        assert by_name["SECRET_KEY"]["valueFrom"]["secretKeyRef"] == {
            "name": "afterglow-secrets",
            "key": "SECRET_KEY",
        }
        assert "AFTERGLOW_ALLOW_INSECURE" not in by_name


def test_helm_python_templates_use_production_secret_contract():
    """Helm Python service templates must reference the production secret contract."""
    paths = [
        ROOT / "helm/afterglow/templates/backend/deployment.yaml",
        ROOT / "helm/afterglow/templates/worker/deployment.yaml",
        ROOT / "helm/afterglow/templates/worker/notion-deployment.yaml",
    ]

    for path in paths:
        text = path.read_text(encoding="utf-8")

        assert '- name: AFTERGLOW_ENV\n              value: "production"' in text
        assert "- name: SECRET_KEY" in text
        assert "name: afterglow-secrets" in text
        assert "key: SECRET_KEY" in text
        assert "AFTERGLOW_ALLOW_INSECURE" not in text


def test_k8s_app_deployments_use_writable_ephemeral_log_mounts():
    """Backend and frontend K8s static deployments must mount pod-local writable emptyDir log volumes."""
    paths = [
        ROOT / "deploy/k8s-template/base/backend/deployment.yaml",
        ROOT / "deploy/k8s-template/base/frontend/deployment.yaml",
    ]
    for path in paths:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        spec = doc["spec"]["template"]["spec"]

        # Security context for non-root fsGroup writable volume access
        assert spec.get("securityContext", {}).get("fsGroup") == 1000

        # Writable emptyDir volume
        volumes = {v["name"]: v for v in spec.get("volumes", [])}
        assert "app-logs" in volumes
        assert volumes["app-logs"] == {"name": "app-logs", "emptyDir": {}}
        assert "hostPath" not in str(volumes["app-logs"])
        assert "persistentVolumeClaim" not in str(volumes["app-logs"])

        # Container volumeMount
        container = spec["containers"][0]
        mounts = {m["name"]: m for m in container.get("volumeMounts", [])}
        assert "app-logs" in mounts
        assert mounts["app-logs"] == {"name": "app-logs", "mountPath": "/app/logs"}


def test_k8s_static_config_uses_portable_log_rotation_settings():
    configmap = (ROOT / "deploy/k8s-template/configmap.yaml").read_text(encoding="utf-8")

    assert 'log_directory = "/app/logs"' in configmap
    assert "max_bytes = 52428800" in configmap
    assert "rotation_type" not in configmap
    assert "rotation_when" not in configmap
    assert "backup_count" not in configmap


def test_ceph_rbd_config_is_disabled_only_when_both_mount_paths_are_empty():
    assert app_config.Settings().ceph_rbd_enabled is False

    with pytest.raises(ValueError, match="함께 설정"):
        app_config.Settings(ceph_rbd_conf_path="/etc/ceph/ceph.conf")
    with pytest.raises(ValueError, match="함께 설정"):
        app_config.Settings(ceph_rbd_keyring_path="/etc/ceph/keyring")


def test_ceph_rbd_config_requires_cluster_pool_and_valid_client_when_enabled():
    base = {
        "ceph_rbd_conf_path": "/etc/ceph/ceph.conf",
        "ceph_rbd_keyring_path": "/etc/ceph/ceph.client.afterglow-rbd.keyring",
        "ceph_rbd_cluster_fsid": "00000000-1111-2222-3333-444444444444",
        "ceph_rbd_volume_pools": {"ceph": "volumes"},
    }

    settings = app_config.Settings(**base)
    assert settings.ceph_rbd_enabled is True

    with pytest.raises(ValueError, match="rbd_cluster_fsid"):
        app_config.Settings(**{**base, "ceph_rbd_cluster_fsid": ""})
    with pytest.raises(ValueError, match="client"):
        app_config.Settings(**{**base, "ceph_rbd_client_name": "bad;client"})
    with pytest.raises(ValueError, match="RBD pool"):
        app_config.Settings(**{**base, "ceph_rbd_volume_pools": {"ceph": "volumes;rm"}})
    with pytest.raises(ValueError, match="양수"):
        app_config.Settings(**{**base, "ceph_rbd_command_timeout_seconds": 0})


def test_app_config_flattens_ceph_rbd_settings(isolated_config_dir):
    (isolated_config_dir / "afterglow.conf").write_text(
        """
[ceph]
rbd_conf_path = "/etc/ceph/ceph.conf"
rbd_keyring_path = "/etc/ceph/ceph.client.afterglow-rbd.keyring"
rbd_client_name = "client.afterglow-rbd"
rbd_cluster_fsid = "00000000-1111-2222-3333-444444444444"
rbd_command_timeout_seconds = 17

[ceph.rbd_volume_pools]
ceph = "volumes"
archive = "archive-volumes"
""".strip(),
        encoding="utf-8",
    )

    settings = app_config.Settings(**app_config._load_toml())

    assert settings.ceph_rbd_enabled is True
    assert settings.ceph_rbd_command_timeout_seconds == 17
    assert settings.ceph_rbd_volume_pools == {
        "ceph": "volumes",
        "archive": "archive-volumes",
    }


def test_k8s_renderer_separates_ceph_conf_and_keyring():
    keyring = "[client.afterglow-rbd]\n  key = secret-sentinel"
    ceph_conf = "[global]\nfsid = 00000000-1111-2222-3333-444444444444"
    cfg = {
        "ceph": {
            "rbd_conf_path": "/etc/ceph/ceph.conf",
            "rbd_keyring_path": "/etc/ceph/ceph.client.afterglow-rbd.keyring",
            "rbd_client_name": "client.afterglow-rbd",
            "rbd_cluster_fsid": "00000000-1111-2222-3333-444444444444",
            "rbd_command_timeout_seconds": 30,
            "rbd_volume_pools": {"ceph": "volumes"},
            "rbd_conf_content": ceph_conf,
            "rbd_keyring": keyring,
        },
        "app": {"secret_key": "0123456789abcdef0123456789abcdef"},
    }

    toml = generate_k8s._render_toml_for_k8s(cfg)
    configmap = yaml.safe_load(generate_k8s.render_configmap(cfg))
    secret = yaml.safe_load(generate_k8s.render_secret(cfg))

    assert '[ceph.rbd_volume_pools]\n"ceph" = "volumes"' in toml
    assert keyring not in toml
    assert configmap["data"]["ceph.conf"].rstrip("\n") == ceph_conf
    assert secret["stringData"]["CEPH_RBD_KEYRING"].rstrip("\n") == keyring


@pytest.fixture
def observation_config():
    return {
        "app": {"secret_key": "fixture-application-secret-" + "s" * 32},
        "openstack": {"password": "fixture-openstack-password"},
        "database": {"url": "mysql+aiomysql://fixture:fixture@127.0.0.1/fixture"},
        "k3s": {"kubeconfig_encryption_key": "ZmZmZmZmZmZmZmZmZmZmZmZmZmZmZmZmZmZmZmZmZmY="},
        "traffic_analytics": {
            "enabled": True,
            "hmac_key": "identity-secret-" + "a" * 32,
            "frontend_ingest_key": "writer-secret-" + "b" * 32,
            "geoip_mmdb": "/etc/afterglow/geoip/country.mmdb",
            "cluster_cidrs": ["10.42.0.0/16", "fd00:42::/48"],
            "backend_trusted_proxy_cidrs": ["10.42.1.8/32"],
            "frontend_trusted_proxy_cidrs": ["10.42.1.9/32"],
            "site_country": "KR",
        },
        "monitoring": {
            "infrastructure_fabric": {
                "revision": 3,
                "poll_interval_seconds": 15,
                "freshness_seconds": 45,
                "targets": [
                    {
                        "id": "switch-a",
                        "name": "Switch A",
                        "chassis_id": "aa:bb:cc:dd:ee:ff",
                        "management_ip": "10.20.0.5",
                        "username": "observer",
                        "auth_key": 'auth-"secret\\value',
                        "priv_key": "privacy-secret-value",
                    }
                ],
            },
        },
    }


def _assert_observation_config(configmap, secret, expected):
    from app.models.infrastructure_fabric import FabricSettings
    from app.models.traffic_analytics import TrafficAnalyticsSettings

    parsed = tomllib.loads(configmap["data"]["afterglow.conf"])
    protected = secret["stringData"]
    traffic = TrafficAnalyticsSettings.model_validate(
        {
            **parsed["traffic_analytics"],
            "hmac_key": protected["TRAFFIC_ANALYTICS__HMAC_KEY"],
            "frontend_ingest_key": protected["TRAFFIC_ANALYTICS__FRONTEND_INGEST_KEY"],
        }
    )
    fabric = FabricSettings.model_validate(
        {
            **parsed["monitoring"]["infrastructure_fabric"],
            "targets": json.loads(protected["MONITORING_INFRASTRUCTURE_FABRIC__TARGETS"]),
        }
    )
    assert traffic == TrafficAnalyticsSettings.model_validate(expected["traffic_analytics"])
    assert fabric == FabricSettings.model_validate(expected["monitoring"]["infrastructure_fabric"])
    public = json.dumps(configmap)
    for value in (
        traffic.hmac_key,
        traffic.frontend_ingest_key,
        fabric.targets[0].auth_key,
        fabric.targets[0].priv_key,
    ):
        assert value.get_secret_value() not in public
        assert value.get_secret_value() not in configmap["data"]["afterglow.conf"]


def test_generated_observation_settings_round_trip_without_public_credentials(observation_config):
    _assert_observation_config(
        yaml.safe_load(generate_k8s.render_configmap(observation_config)),
        yaml.safe_load(generate_k8s.render_secret(observation_config)),
        observation_config,
    )
    public_values = yaml.safe_load(config2helm.render_yaml(config2helm.convert(observation_config, False)))
    assert "secrets" not in public_values
    assert "targets" not in public_values["monitoring"]["infrastructureFabric"]
    for key in ("auth_key", "priv_key", "username", "hmac_key", "frontend_ingest_key"):
        assert key not in json.dumps(public_values)


@pytest.mark.parametrize("claim", ["", "operator-country-data"])
def test_helm_observation_settings_and_optional_readonly_country_volume(tmp_path, observation_config, claim):
    helm = shutil.which("helm")
    if helm is None:
        pytest.skip("Helm is required to render the deployment contract")
    values = config2helm.convert(observation_config, True)
    values["trafficAnalytics"]["geoipExistingClaim"] = claim
    values_path = tmp_path / "observation-values.yaml"
    values_path.write_text(config2helm.render_yaml(values), encoding="utf-8")
    rendered = subprocess.run(
        [helm, "template", "afterglow", str(ROOT / "helm/afterglow"), "-f", str(values_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    documents = list(yaml.safe_load_all(rendered.stdout))
    configmap = next(
        doc for doc in documents if doc["kind"] == "ConfigMap" and doc["metadata"]["name"] == "afterglow-config"
    )
    secret = next(
        doc for doc in documents if doc["kind"] == "Secret" and doc["metadata"]["name"] == "afterglow-secrets"
    )
    _assert_observation_config(configmap, secret, observation_config)
    for document in documents:
        if document["kind"] == "Deployment" and document["metadata"]["name"] in {"backend", "frontend"}:
            app_pod = document["spec"]["template"]["spec"]
            log_volume = next(volume for volume in app_pod["volumes"] if volume["name"] == "app-logs")
            log_mount = next(mount for mount in app_pod["containers"][0]["volumeMounts"] if mount["name"] == "app-logs")
            assert log_volume == {"name": "app-logs", "emptyDir": {}}
            assert log_mount["mountPath"] == "/app/logs" and log_mount.get("readOnly", False) is False
    pod = next(doc for doc in documents if doc["kind"] == "Deployment" and doc["metadata"]["name"] == "backend")[
        "spec"
    ]["template"]["spec"]
    volumes = {volume["name"]: volume for volume in pod["volumes"]}
    mounts = {mount["name"]: mount for mount in pod["containers"][0]["volumeMounts"]}
    if claim:
        assert volumes["traffic-country-mmdb"]["persistentVolumeClaim"] == {"claimName": claim, "readOnly": True}
        assert mounts["traffic-country-mmdb"]["mountPath"] == "/etc/afterglow/geoip"
        assert mounts["traffic-country-mmdb"]["readOnly"] is True
    else:
        assert "traffic-country-mmdb" not in volumes
        assert "traffic-country-mmdb" not in mounts


def test_helm_rejects_country_claim_with_unmounted_database_path():
    helm = shutil.which("helm")
    if helm is None:
        pytest.skip("Helm is required to render the deployment contract")
    rendered = subprocess.run(
        [
            helm,
            "template",
            "afterglow",
            str(ROOT / "helm/afterglow"),
            "--set",
            "trafficAnalytics.geoipExistingClaim=operator-country-data",
            "--set",
            "trafficAnalytics.geoipMmdb=/unmounted/country.mmdb",
        ],
        capture_output=True,
        text=True,
    )
    assert rendered.returncode != 0
    assert "requires geoipMmdb=/etc/afterglow/geoip/country.mmdb" in rendered.stderr


@pytest.mark.parametrize("source", ["", "/operator/country.mmdb"])
def test_kolla_country_mount_configuration_preserves_other_operator_settings(source):
    from jinja2 import meta

    from app.models.traffic_analytics import TrafficAnalyticsSettings

    environment = Environment(undefined=StrictUndefined)
    environment.filters.update(bool=bool, to_json=json.dumps)
    template = environment.parse(
        (ROOT / "deploy/kolla/ansible/roles/afterglow/templates/afterglow.kolla.conf.j2").read_text()
    )
    context = dict.fromkeys(meta.find_undeclared_variables(template), "")
    for key in (
        "backend_port",
        "frontend_port",
        "cloud_shell_home_size_gib",
        "cloud_shell_cpu",
        "cloud_shell_memory_mib",
        "cloud_shell_idle_timeout_seconds",
        "cloud_shell_max_session_seconds",
        "cloud_shell_ticket_ttl_seconds",
        "cloud_shell_reconcile_interval_seconds",
    ):
        context["afterglow_" + key] = 1
    context.update(
        afterglow_traffic_analytics_geoip_mmdb_source=source,
        afterglow_traffic_analytics_geoip_mmdb_path="/etc/afterglow/geoip/country.mmdb",
    )
    override = tomllib.loads(environment.from_string(template).render(context))
    operator = {"geoip_mmdb": "/operator/image-country.mmdb", "cluster_cidrs": ["10.42.0.0/16"]}
    effective = TrafficAnalyticsSettings.model_validate({**operator, **override.get("traffic_analytics", {})})
    assert effective.geoip_mmdb == (
        context["afterglow_traffic_analytics_geoip_mmdb_path"] if source else operator["geoip_mmdb"]
    )
    assert effective.cluster_cidrs == operator["cluster_cidrs"]


def test_kolla_country_startup_fails_closed_and_tracks_source_identity(tmp_path):
    executable = ROOT / "deploy/kolla/operator/.venv/bin/ansible-playbook"
    ansible = str(executable) if executable.is_file() else shutil.which("ansible-playbook")
    if ansible is None:
        pytest.skip("Kolla's Ansible runtime is required for functional startup checks")
    tasks = yaml.safe_load((ROOT / "deploy/kolla/ansible/roles/afterglow/tasks/start.yml").read_text())
    marker = tmp_path / "started-container"
    for task in tasks:
        task["become"] = False
        if "community.docker.docker_container" in task:
            # Sandbox only the Docker side effect; retain the real guards, stat,
            # restart expression, loop and host selection from the startup path.
            container = task.pop("community.docker.docker_container")
            task["ansible.builtin.copy"] = {"content": container["labels"]["config_hash"], "dest": str(marker)}
    playbook = tmp_path / "start.yml"
    playbook.write_text(yaml.safe_dump([{"hosts": "afterglow", "gather_facts": False, "tasks": tasks}]))
    inventory = tmp_path / "inventory"
    inventory.write_text("[afterglow]\nlocalhost ansible_connection=local\n")
    database = tmp_path / "country.mmdb"
    content = b"opaque operator-provisioned database bytes for checksum boundary"
    database.write_bytes(content)
    pin = hashlib.sha256(content).hexdigest()
    variables = {
        "afterglow_runtime_config_dir": str(tmp_path),
        "afterglow_traffic_analytics_geoip_mmdb_source": "/operator/release-a/country.mmdb",
        "afterglow_traffic_analytics_geoip_mmdb_runtime_path": str(database),
        "afterglow_traffic_analytics_geoip_mmdb_path": "/etc/afterglow/geoip/country.mmdb",
        "afterglow_traffic_analytics_geoip_mmdb_sha256": pin,
        "afterglow_services": {"backend": {"enabled": True}},
    }
    for key in (
        "generated_config_name",
        "operator_config_name",
        "operator_frontend_config_name",
        "kolla_config_name",
        "frontend_config_name",
    ):
        variables["afterglow_" + key] = key + ".conf"
        (tmp_path / variables["afterglow_" + key]).write_text("# configuration layer\n")
    environment = {key: value for key, value in os.environ.items() if not key.startswith(("ANSIBLE_", "KOLLA_"))}
    environment.update(ANSIBLE_LOCAL_TEMP=str(tmp_path / "ansible-tmp"), OBJC_DISABLE_INITIALIZE_FORK_SAFETY="YES")

    def start(**overrides):
        marker.unlink(missing_ok=True)
        result = subprocess.run(
            [ansible, "-i", str(inventory), str(playbook), "-e", json.dumps({**variables, **overrides})],
            cwd=tmp_path,
            env=environment,
            capture_output=True,
            text=True,
        )
        return result, marker.read_text() if marker.exists() else None

    result, identity_a = start()
    assert result.returncode == 0, result.stdout + result.stderr
    result, identity_b = start(afterglow_traffic_analytics_geoip_mmdb_source="/operator/release-b/country.mmdb")
    assert result.returncode == 0, result.stdout + result.stderr
    assert identity_a != identity_b
    for overrides in (
        {"afterglow_traffic_analytics_geoip_mmdb_source": ""},
        {"afterglow_traffic_analytics_geoip_mmdb_sha256": ""},
        {"afterglow_traffic_analytics_geoip_mmdb_sha256": "0" * 64},
    ):
        result, identity = start(**overrides)
        assert result.returncode != 0
        assert identity is None
    database.write_bytes(b"replaced data")
    result, identity = start()
    assert result.returncode != 0
    assert identity is None
    database.unlink()
    result, identity = start()
    assert result.returncode != 0
    assert identity is None
    target = tmp_path / "symlink-target.mmdb"
    target.write_bytes(content)
    database.symlink_to(target)
    result, identity = start()
    assert result.returncode != 0
    assert identity is None
