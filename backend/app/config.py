"""Afterglow 설정 모듈.

우선순위: 환경변수 > afterglow.conf (프로젝트 루트) > 기본값
"""

import json
import os
import re
import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings

_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_EMPTY_ENV_TOML_FALLBACK_KEYS = frozenset(
    {"GITLAB_OIDC_CLIENT_SECRET", "K3S_GPU_ADMISSION_TOKEN", "K3S_PROVISIONING_TOKEN"}
)


def is_development_loopback_http_url(value: str) -> bool:
    """Return whether a URL is a valid development-only HTTP loopback endpoint."""
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError:
        return False
    return (
        os.environ.get("AFTERGLOW_ENV", "development").strip().lower() == "development"
        and parsed.scheme.lower() == "http"
        and bool(parsed.netloc)
        and (parsed.hostname or "").lower() in _LOOPBACK_HOSTS
        and not parsed.username
        and not parsed.password
        and not parsed.query
        and not parsed.fragment
    )


def _config_candidates() -> list[Path]:
    """지원하는 기본 설정 파일 경로 목록."""
    return [
        Path.cwd() / "afterglow.conf",
        Path.cwd().parent / "afterglow.conf",
        Path("/app/afterglow.conf"),
    ]


def _deep_merge(base: dict, override: dict) -> dict:
    """base 위에 override를 재귀적으로 딥 머지한 새 dict를 반환.

    dict 값은 재귀 병합, 그 외(스칼라·리스트)는 override가 덮어쓴다.
    """
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _config_override_paths(base_path: Path) -> list[Path]:
    """같은 디렉터리의 afterglow.*.conf와 GPU 맵 오버라이드를 반환한다."""
    patterns = [f"{base_path.stem}.*{base_path.suffix}"]
    if base_path.name == "afterglow.conf":
        patterns.append("config.gpu.toml")

    overrides: dict[Path, Path] = {}
    for pattern in patterns:
        for p in base_path.parent.glob(pattern):
            if p.name == base_path.name:
                continue
            if not p.is_file() or p.stat().st_size == 0 or p.name == "afterglow.frontend.conf":
                continue
            overrides[p.resolve()] = p
    return [overrides[key] for key in sorted(overrides)]


def _load_toml() -> dict:
    """afterglow.conf(+ 오버라이드)을 읽어 평탄화된 dict를 반환."""
    data = load_raw_toml()
    if not data:
        return {}

    flat: dict = {}
    ost = data.get("openstack", {})
    flat["os_auth_url"] = ost.get("auth_url", "")
    flat["os_username"] = ost.get("username", "")
    flat["os_password"] = ost.get("password", "")
    flat["os_project_name"] = ost.get("project_name", "admin")
    flat["os_project_domain_name"] = ost.get("project_domain_name", "Default")
    flat["os_user_domain_name"] = ost.get("user_domain_name", "Default")
    flat["os_region_name"] = ost.get("region_name", "RegionOne")
    flat["os_interface"] = ost.get("interface", "internal")
    flat["os_insecure"] = ost.get("insecure", False)
    flat["os_cacert"] = ost.get("cacert", "")
    flat["os_manila_endpoint"] = ost.get("manila_endpoint", "")
    flat["os_swift_endpoint"] = ost.get("swift_endpoint", "")
    flat["os_swift_upload_timeout"] = ost.get("swift_upload_timeout", 1800)
    flat["os_trash_retention_days"] = ost.get("trash_retention_days", 30)
    flat["os_manila_share_network_id"] = ost.get("manila_share_network_id", "")
    flat["os_manila_share_type"] = ost.get("manila_share_type", "cephfs")
    flat["os_manila_nfs_share_type"] = ost.get("manila_nfs_share_type", "nfstype")
    flat["manila_nfs_root_squash"] = ost.get("manila_nfs_root_squash", True)
    flat["manila_nfs_sec_flavor"] = ost.get("manila_nfs_sec_flavor", "sys")
    flat["manila_cephx_key_timeout_seconds"] = ost.get("manila_cephx_key_timeout_seconds", 300)
    flat["ceph_monitors"] = ost.get("ceph_monitors", "")

    ceph = data.get("ceph", {})
    flat["ceph_rbd_conf_path"] = ceph.get("rbd_conf_path", "")
    flat["ceph_rbd_keyring_path"] = ceph.get("rbd_keyring_path", "")
    flat["ceph_rbd_client_name"] = ceph.get("rbd_client_name", "client.afterglow-rbd")
    flat["ceph_rbd_cluster_fsid"] = ceph.get("rbd_cluster_fsid", "")
    flat["ceph_rbd_command_timeout_seconds"] = ceph.get("rbd_command_timeout_seconds", 30)
    flat["ceph_rbd_volume_pools"] = dict(ceph.get("rbd_volume_pools", {}) or {})
    flat["os_service_project_id"] = ost.get("service_project_id", "")

    app = data.get("app", {})
    flat["backend_port"] = app.get("backend_port", 8000)
    flat["frontend_port"] = app.get("frontend_port", 3080)
    flat["secret_key"] = app.get("secret_key", "change-me-in-production")
    flat["refresh_interval_ms"] = app.get("refresh_interval_ms", 5000)
    flat["site_name"] = app.get("site_name", "Afterglow")
    flat["site_description"] = app.get("site_description", "OpenStack VM + OverlayFS 배포 플랫폼")
    flat["logo_path"] = app.get("logo_path", "/logo.png")
    flat["logo_dark_path"] = app.get("logo_dark_path", "/logo-white.png")
    flat["logo_light_path"] = app.get("logo_light_path", "/logo-dark.png")
    flat["favicon_path"] = app.get("favicon_path", "/favicon.ico")
    flat["frontend_base_url"] = app.get("frontend_base_url", "")
    flat["public_api_base"] = app.get("public_api_base", "")

    cache = data.get("cache", {})
    flat["redis_url"] = cache.get("redis_url", "redis://localhost:6379/0")
    flat["cache_ttl_seconds"] = cache.get("default_ttl_seconds", 30)
    flat["cache_ttl_fast"] = cache.get("ttl_fast", 15)
    flat["cache_ttl_normal"] = cache.get("ttl_normal", cache.get("default_ttl_seconds", 30))
    flat["cache_ttl_slow"] = cache.get("ttl_slow", 60)
    flat["cache_ttl_static"] = cache.get("ttl_static", 300)
    flat["cache_backend"] = cache.get("backend", "redis")
    flat["sentinel_enabled"] = cache.get("sentinel_enabled", False)
    flat["sentinel_master_name"] = cache.get("sentinel_master_name", "mymaster")
    flat["sentinel_hosts"] = cache.get("sentinel_hosts", "")
    flat["cache_dynamic_threshold_low"] = cache.get("dynamic_threshold_low", 5)
    flat["cache_dynamic_threshold_high"] = cache.get("dynamic_threshold_high", 20)
    flat["cache_ttl_identity_stable"] = cache.get("ttl_identity_stable", 86400)
    flat["cache_ttl_catalog_slow"] = cache.get("ttl_catalog_slow", 900)
    flat["cache_ttl_project_meta"] = cache.get("ttl_project_meta", 300)
    flat["cache_ttl_operational_live"] = cache.get("ttl_operational_live", 30)
    flat["cache_ttl_admin_overview"] = cache.get("ttl_admin_overview", 60)
    flat["cache_ttl_auth_token"] = cache.get("ttl_auth_token", 60)

    svc = data.get("services", {})
    flat["service_magnum_enabled"] = svc.get("magnum", False)
    flat["service_manila_enabled"] = svc.get("manila", False)
    flat["service_zun_enabled"] = svc.get("zun", False)
    flat["service_cloud_shell_enabled"] = svc.get("cloud_shell", False)
    flat["service_k3s_enabled"] = svc.get("k3s", False)
    flat["service_trove_enabled"] = svc.get("trove", False)
    flat["service_swift_enabled"] = svc.get("swift", False)
    flat["service_barbican_enabled"] = svc.get("barbican", False)
    flat["service_waygate_enabled"] = svc.get("waygate", False)
    flat["service_palimpsest_enabled"] = svc.get("palimpsest", False)
    flat["service_chat_enabled"] = svc.get("chat", False)
    flat["service_mcp_enabled"] = svc.get("mcp", False)
    flat["service_waygate_internal_url"] = svc.get("waygate_internal_url", "")
    flat["service_drover_internal_url"] = svc.get("drover_internal_url", "")
    flat["service_lumen_internal_url"] = svc.get("lumen_internal_url", "")
    flat["service_palimpsest_internal_url"] = svc.get("palimpsest_internal_url", "")

    cloud_shell = data.get("cloud_shell", {})
    flat["cloud_shell_service_project_id"] = cloud_shell.get("service_project_id", "")
    flat["cloud_shell_image"] = cloud_shell.get("image", "")
    flat["cloud_shell_network_id"] = cloud_shell.get("network_id", "")
    flat["cloud_shell_security_group"] = cloud_shell.get("security_group", "")
    flat["cloud_shell_auth_url"] = cloud_shell.get("auth_url", "")
    flat["cloud_shell_interface"] = cloud_shell.get("interface", "internal")
    flat["cloud_shell_volume_type"] = cloud_shell.get("volume_type", "")
    flat["cloud_shell_home_size_gib"] = cloud_shell.get("home_size_gib", 5)
    flat["cloud_shell_cpu"] = cloud_shell.get("cpu", 1.0)
    flat["cloud_shell_memory_mib"] = cloud_shell.get("memory_mib", 1024)
    flat["cloud_shell_idle_timeout_seconds"] = cloud_shell.get("idle_timeout_seconds", 1200)
    flat["cloud_shell_max_session_seconds"] = cloud_shell.get("max_session_seconds", 3600)
    flat["cloud_shell_ticket_ttl_seconds"] = cloud_shell.get("ticket_ttl_seconds", 60)
    flat["cloud_shell_reconcile_interval_seconds"] = cloud_shell.get("reconcile_interval_seconds", 60)
    flat["cloud_shell_zun_websocket_origin"] = cloud_shell.get("zun_websocket_origin", "")
    mcp = data.get("mcp", {})
    flat["mcp_public_url"] = mcp.get("public_url", "")
    flat["mcp_oauth_consent_url"] = mcp.get("oauth_consent_url", "")
    flat["mcp_authorization_ticket_ttl_seconds"] = mcp.get("authorization_ticket_ttl_seconds", 600)
    flat["mcp_access_token_ttl_seconds"] = mcp.get("access_token_ttl_seconds", 900)
    flat["mcp_default_grant_ttl_days"] = mcp.get("default_grant_ttl_days", 30)
    flat["mcp_max_grant_ttl_days"] = mcp.get("max_grant_ttl_days", 90)
    flat["mcp_max_personal_tokens"] = mcp.get("max_personal_tokens", 10)
    flat["mcp_max_delegated_grants"] = mcp.get("max_delegated_grants", 20)
    flat["mcp_request_max_bytes"] = mcp.get("request_max_bytes", 1048576)
    flat["mcp_read_result_max_bytes"] = mcp.get("read_result_max_bytes", 524288)
    flat["mcp_mutation_result_max_bytes"] = mcp.get("mutation_result_max_bytes", 65536)
    flat["mcp_default_page_size"] = mcp.get("default_page_size", 50)
    flat["mcp_max_page_size"] = mcp.get("max_page_size", 100)
    flat["mcp_concurrent_calls_per_grant"] = mcp.get("concurrent_calls_per_grant", 4)
    flat["mcp_read_rate_per_minute"] = mcp.get("read_rate_per_minute", 120)
    flat["mcp_mutation_rate_per_minute"] = mcp.get("mutation_rate_per_minute", 20)
    flat["lumen_mcp_service_token"] = mcp.get("lumen_service_token", "")

    instance_health = data.get("instance_health", {})
    flat["instance_health_callback_base_url"] = instance_health.get("callback_base_url", "")

    # Retained temporarily as the shared master key for existing ciphertext domains.
    k3s = data.get("k3s", {})
    flat["k3s_kubeconfig_encryption_key"] = k3s.get("kubeconfig_encryption_key", "")
    flat["k3s_gpu_admission_token"] = k3s.get("gpu_admission_token", "")
    flat["k3s_provisioning_token"] = k3s.get("provisioning_token", "")

    wr = data.get("worker_runtime", {})
    wr_workers = wr.get("workers", {})
    wr_notion = wr_workers.get("notion_worker", {})
    wr_docker = wr.get("docker", {})
    wr_k8s = wr.get("kubernetes", {})
    flat["worker_runtime_mode"] = wr.get("mode", "static")
    flat["worker_runtime_reconcile_interval"] = wr.get("reconcile_interval", 30)
    flat["worker_runtime_fail_closed"] = wr.get("fail_closed", True)
    flat["worker_runtime_notion_worker_enabled"] = wr_notion.get("enabled", True)
    flat["worker_runtime_notion_worker_desired_replicas"] = wr_notion.get("desired_replicas", 1)
    flat["worker_runtime_notion_worker_max_replicas"] = wr_notion.get("max_replicas", 1)
    flat["worker_runtime_notion_worker_module"] = wr_notion.get("module", "app.notion_worker")
    flat["worker_runtime_docker_socket_path"] = wr_docker.get("socket_path", "")
    flat["worker_runtime_docker_image"] = wr_docker.get("image", "")
    flat["worker_runtime_docker_network"] = wr_docker.get("network", "")
    flat["worker_runtime_docker_config_mount"] = wr_docker.get("config_mount", "/app/afterglow.conf")
    flat["worker_runtime_docker_config_host_path"] = wr_docker.get("config_host_path", "")
    flat["worker_runtime_docker_gpu_config_mount"] = wr_docker.get("gpu_config_mount", "/app/config.gpu.toml")
    flat["worker_runtime_docker_gpu_config_host_path"] = wr_docker.get("gpu_config_host_path", "")
    flat["worker_runtime_docker_logs_mount"] = wr_docker.get("logs_mount", "/app/logs")
    flat["worker_runtime_docker_logs_host_path"] = wr_docker.get("logs_host_path", "")
    flat["worker_runtime_docker_env_allowlist"] = wr_docker.get(
        "env_allowlist",
        (
            "AFTERGLOW_ENV,AFTERGLOW_ALLOW_INSECURE,SECRET_KEY,OS_PASSWORD,DATABASE_URL,"
            "K3S_KUBECONFIG_ENCRYPTION_KEY,K3S_GPU_ADMISSION_TOKEN,K3S_PROVISIONING_TOKEN,PROMETHEUS_PASSWORD,"
            "GITLAB_OIDC_CLIENT_SECRET,NOTION_CONFIG_ENCRYPTION_KEY"
        ),
    )
    flat["worker_runtime_kubernetes_namespace"] = wr_k8s.get("namespace", "afterglow")
    flat["worker_runtime_kubernetes_service_account_token_path"] = wr_k8s.get(
        "service_account_token_path", "/var/run/secrets/kubernetes.io/serviceaccount/token"
    )
    flat["worker_runtime_kubernetes_service_account_ca_path"] = wr_k8s.get(
        "service_account_ca_path", "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
    )
    flat["worker_runtime_kubernetes_manage_deployments"] = wr_k8s.get("manage_deployments", False)

    gpu = data.get("gpu", {})
    flat["gpu_available_visible"] = gpu.get("available_visible", False)

    sess = data.get("session", {})
    flat["session_timeout_seconds"] = sess.get("timeout_seconds", 3600)
    flat["jwt_access_ttl"] = sess.get("jwt_access_ttl", 900)
    flat["jwt_refresh_ttl"] = sess.get("jwt_refresh_ttl", 604800)
    flat["token_ip_binding_mode"] = sess.get("token_ip_binding_mode", "subnet")

    nv = data.get("nova", {})
    flat["boot_volume_size_gb"] = nv.get("boot_volume_size_gb", 20)
    flat["upper_volume_size_gb"] = nv.get("upper_volume_size_gb", 50)

    builder = data.get("builder", {})
    flat["builder_ssh_user"] = builder.get("ssh_user", "ubuntu")
    flat["builder_ssh_key_path"] = builder.get("ssh_key_path", "/etc/afterglow/ssh/builder.key")
    flat["builder_build_timeout"] = builder.get("build_timeout", 3600)
    flat["builder_layer_share_size_gb"] = builder.get("layer_share_size_gb", 20)

    palimpsest = data.get("palimpsest", {})
    flat["palimpsest_kvm_uri"] = palimpsest.get("kvm_uri", "")
    flat["palimpsest_kvm_layer_root"] = palimpsest.get("kvm_layer_root", "/var/lib/palimpsest/layers")
    flat["palimpsest_kvm_state_dir"] = palimpsest.get("kvm_state_dir", "/var/lib/palimpsest/domains")

    mon = data.get("monitoring", {})
    flat["prometheus_base_url"] = mon.get("prometheus_base_url", "http://prometheus:9090")
    flat["prometheus_username"] = mon.get("prometheus_username", "")
    flat["prometheus_password"] = mon.get("prometheus_password", "")
    flat["monitoring_sd_token"] = mon.get("sd_token", "")
    flat["monitoring_scrape_cidr"] = mon.get("scrape_cidr", "")
    flat["monitoring_auto_sg_enabled"] = mon.get("auto_sg_enabled", True)
    flat["node_exporter_sg_name"] = mon.get("node_exporter_sg_name", "node_exporter")
    flat["dcgm_exporter_sg_name"] = mon.get("dcgm_exporter_sg_name", "dcgm_exporter")
    flat["node_exporter_port"] = mon.get("node_exporter_port", 9100)
    flat["dcgm_exporter_port"] = mon.get("dcgm_exporter_port", 9400)
    flat["libvirt_exporter_port"] = mon.get("libvirt_exporter_port", 9177)
    flat["gpu_flavor_prefix"] = mon.get("gpu_flavor_prefix", "gpu.")
    flat["grafana_base_url"] = mon.get("grafana_base_url", "")
    dashboards = mon.get("dashboards", {})
    flat["grafana_dashboard_node_uid"] = dashboards.get("node_uid", "afterglow-node")
    flat["grafana_dashboard_rabbitmq_uid"] = dashboards.get("rabbitmq_uid", "afterglow-rabbitmq")
    flat["grafana_dashboard_mysqld_uid"] = dashboards.get("mysqld_uid", "afterglow-mysqld")
    flat["grafana_dashboard_memcached_uid"] = dashboards.get("memcached_uid", "afterglow-memcached")
    flat["grafana_dashboard_etcd_uid"] = dashboards.get("etcd_uid", "afterglow-etcd")
    flat["grafana_dashboard_haproxy_uid"] = dashboards.get("haproxy_uid", "afterglow-haproxy")
    flat["grafana_dashboard_libvirt_uid"] = dashboards.get("libvirt_uid", "afterglow-libvirt")
    flat["grafana_dashboard_openstack_uid"] = dashboards.get("openstack_uid", "afterglow-openstack")
    flat["grafana_dashboard_ceph_uid"] = dashboards.get("ceph_uid", "afterglow-ceph")
    flat["grafana_dashboard_instance_cpu_uid"] = dashboards.get("instance_cpu_uid", "afterglow-instance-cpu")
    flat["grafana_dashboard_instance_gpu_uid"] = dashboards.get("instance_gpu_uid", "afterglow-instance-gpu")

    notion = data.get("notion", {})
    flat["notion_config_encryption_key"] = notion.get("config_encryption_key", "")

    security = data.get("security", {})
    flat["admin_legacy_project_policy"] = security.get("admin_legacy_project_policy", False)
    flat["login_max_attempts"] = security.get("login_max_attempts", 10)
    flat["login_lockout_seconds"] = security.get("login_lockout_seconds", 300)
    flat["login_backoff_base"] = security.get("login_backoff_base", 2)

    gl = data.get("gitlab_oidc", {})
    flat["gitlab_oidc_enabled"] = gl.get("enabled", False)
    flat["gitlab_oidc_gitlab_url"] = gl.get("gitlab_url", "")
    flat["gitlab_oidc_client_id"] = gl.get("client_id", "")
    flat["gitlab_oidc_client_secret"] = gl.get("client_secret", "")
    flat["gitlab_oidc_idp_id"] = gl.get("idp_id", "gitlab")
    flat["gitlab_oidc_protocol_id"] = gl.get("protocol_id", "openid")
    flat["gitlab_oidc_redirect_uri"] = gl.get("redirect_uri", "")
    flat["gitlab_oidc_scopes"] = gl.get("scopes", "openid email profile read_user")

    db = data.get("database", {})
    flat["database_url"] = db.get("url", "")
    flat["database_pool_size"] = db.get("pool_size", 5)
    flat["database_max_overflow"] = db.get("max_overflow", 10)
    flat["database_auto_create_tables"] = db.get("auto_create_tables", True)
    flat["database_connect_timeout"] = db.get("connect_timeout", 10)
    flat["database_pool_timeout"] = db.get("pool_timeout", 10)
    flat["database_unhealthy_seconds"] = db.get("unhealthy_seconds", 15)
    flat["database_db_auto_backup_cron"] = db.get("db_auto_backup_cron", "0 3 * * *")

    smtp = data.get("smtp", {})
    flat["smtp_enabled"] = smtp.get("enabled", False)
    flat["smtp_host"] = smtp.get("host", "")
    flat["smtp_port"] = smtp.get("port", 587)
    flat["smtp_username"] = smtp.get("username", "")
    flat["smtp_password"] = smtp.get("password", "")
    flat["smtp_from_address"] = smtp.get("from_address", "noreply@afterglow.example.com")
    flat["smtp_from_name"] = smtp.get("from_name", "Afterglow")
    flat["smtp_use_tls"] = smtp.get("use_tls", True)
    flat["smtp_timeout_seconds"] = smtp.get("timeout_seconds", 10)
    smtp_inv = smtp.get("invitation", {})
    flat["smtp_invitation_token_expiry_days"] = smtp_inv.get("token_expiry_days", 7)

    cors = data.get("cors", {})
    flat["cors_origins"] = cors.get("origins", "http://localhost:3080,http://localhost")

    log = data.get("logging", {})
    flat["log_directory"] = log.get("log_directory", "logs")
    flat["log_level"] = log.get("log_level", "INFO")
    flat["log_max_bytes"] = log.get("max_bytes", 52428800)

    return flat


class Settings(BaseSettings):
    # OpenStack 인증
    os_auth_url: str = ""
    os_username: str = ""
    os_password: str = ""
    os_project_name: str = "admin"
    os_project_domain_name: str = "Default"
    os_user_domain_name: str = "Default"
    os_region_name: str = "RegionOne"
    os_interface: str = "internal"
    os_insecure: bool = False
    os_cacert: str = ""

    # Manila 설정
    os_service_project_id: str = (
        ""  # Union Mount 빌더/share 전용 service 프로젝트 UUID. 미설정 시 prebuilt 경로 fail-fast.
    )
    os_manila_endpoint: str = ""
    # Swift 설정
    os_swift_endpoint: str = ""
    os_swift_upload_timeout: int = 1800  # 대용량 업로드용 타임아웃 (초)
    os_trash_retention_days: int = 30  # 휴지통 보관 기간 (일). 만료 후 자동 영구 삭제.
    # S3 Direct Upload 설정 (Ceph RGW S3 endpoint 대상)
    os_s3_endpoint: str = "https://s3.dmslab.re.kr"
    upload_part_size_mb: int = 50
    upload_url_expires_sec: int = 3600
    upload_tx_ttl_sec: int = 86400
    os_manila_share_network_id: str = ""
    os_manila_share_type: str = "cephfs"
    os_manila_nfs_share_type: str = "nfstype"
    manila_nfs_root_squash: bool = True  # NFS access rule root_squash 강제 (보안 기본값)
    manila_nfs_sec_flavor: str = "sys"  # NFS 인증 flavor: "sys"(기본) | "krb5"(Kerberos)
    manila_cephx_key_timeout_seconds: int = 300  # CephX key 발급 폴링 최대 대기 (초)

    # Ceph 모니터 (cloud-init CephFS 마운트용)
    ceph_monitors: str = ""

    # 관리자 볼륨 삭제 복구용 Ceph RBD 검사/매핑 복원 (두 경로가 모두 설정될 때만 활성)
    ceph_rbd_conf_path: str = ""
    ceph_rbd_keyring_path: str = ""
    ceph_rbd_client_name: str = "client.afterglow-rbd"
    ceph_rbd_cluster_fsid: str = ""
    ceph_rbd_command_timeout_seconds: int = 30
    ceph_rbd_volume_pools: dict[str, str] = Field(default_factory=dict)

    # 앱 설정
    backend_port: int = 8000
    frontend_port: int = 3080
    secret_key: str = "change-me-in-production"
    # object-storage 업로드 단일 파일 최대 크기 (GiB). 0 또는 음수 = 사실상 무제한(기존 100GiB cap).
    app_max_upload_gb: int = 10
    # rate-limit / 클라이언트 IP 추출 시 신뢰할 reverse proxy CIDR (쉼표 구분).
    # 비어 있으면 X-Forwarded-For / X-Real-IP 헤더를 모두 무시 → 직접 연결 IP 사용.
    # 운영(K8s/HAProxy) 에서는 ingress/HAProxy 의 pod CIDR 을 명시적으로 추가해야 한다.
    trusted_proxies: str = "127.0.0.1/32,::1/128"

    # CORS 허용 origin (쉼표 구분)
    cors_origins: str = "http://localhost:3080,http://localhost"
    refresh_interval_ms: int = 5000
    site_name: str = "Afterglow"
    site_description: str = "OpenStack VM + OverlayFS 배포 플랫폼"
    logo_path: str = "/logo.png"
    logo_dark_path: str = "/logo-white.png"
    logo_light_path: str = "/logo-dark.png"
    favicon_path: str = "/favicon.ico"

    # Redis 캐시
    redis_url: str = "redis://localhost:6379/0"
    cache_ttl_seconds: int = 30
    cache_ttl_fast: int = 15
    cache_ttl_normal: int = 30
    cache_ttl_slow: int = 60
    cache_ttl_static: int = 300
    # 캐시 백엔드: "redis" | "valkey" (v1 동일 클라이언트, v2 에서 Memcached 추가 시 확장)
    cache_backend: Literal["redis", "valkey"] = "redis"
    # Redis Sentinel HA
    sentinel_enabled: bool = False
    sentinel_master_name: str = "mymaster"
    sentinel_hosts: str = ""  # 콤마 구분 "host:port" 목록 (예: sentinel-a:26379,sentinel-b:26379)
    # Dynamic TTL 조정 임계치 (시간당 mutation 횟수)
    cache_dynamic_threshold_low: int = 5
    cache_dynamic_threshold_high: int = 20
    # 3-tier TTL 카테고리 (Phase B)
    cache_ttl_identity_stable: int = 86400  # 개인 프로필, role/group 멤버십
    cache_ttl_catalog_slow: int = 900  # flavors, image 메타, 데이터스토어
    cache_ttl_project_meta: int = 300  # keypair, SG 정의, 네트워크 메타
    mcp_authorization_ticket_ttl_seconds: int = 600
    # Public resource URL and browser consent page for the inbound MCP OAuth server.
    # Client callback URLs remain client-owned DCR inputs and are never configured here.
    mcp_public_url: str = ""
    mcp_oauth_consent_url: str = ""
    mcp_access_token_ttl_seconds: int = 900
    mcp_default_grant_ttl_days: int = 30
    mcp_max_grant_ttl_days: int = 90
    mcp_max_personal_tokens: int = 10
    mcp_max_delegated_grants: int = 20
    mcp_request_max_bytes: int = 1048576
    mcp_read_result_max_bytes: int = 524288
    mcp_mutation_result_max_bytes: int = 65536
    mcp_default_page_size: int = 50
    mcp_max_page_size: int = 100
    mcp_concurrent_calls_per_grant: int = 4
    mcp_read_rate_per_minute: int = 120
    mcp_mutation_rate_per_minute: int = 20
    # Shared only with Lumen's workload identity; it authorizes opaque delegated
    # MCP snapshots, never browser credentials or personal MCP tokens.
    lumen_mcp_service_token: str = ""
    cache_ttl_operational_live: int = 30  # instances/volumes/FIP/컨테이너 상태
    cache_ttl_admin_overview: int = 60  # admin 토폴로지, 하이퍼바이저
    cache_ttl_auth_token: int = 60  # Keystone 토큰 검증 결과
    # 프로젝트별 기본 네트워크 자동 생성은 배포 운영 정책이다.
    default_network_enabled: bool = True
    default_network_cidr: str = "192.168.0.0/24"

    # 선택적 서비스
    service_magnum_enabled: bool = False
    service_manila_enabled: bool = False
    service_zun_enabled: bool = False
    service_cloud_shell_enabled: bool = False
    service_k3s_enabled: bool = False
    service_trove_enabled: bool = False
    service_swift_enabled: bool = False
    service_barbican_enabled: bool = False
    service_waygate_enabled: bool = False  # Waygate service proxy mount
    service_palimpsest_enabled: bool = False  # Palimpsest Hub service proxy mount
    service_chat_enabled: bool = False  # AI 채팅 (Lumen AI API 프록시 마운트)
    service_mcp_enabled: bool = False  # inbound consumer MCP control plane (Stage 2 rollout gate)
    # Trusted deployment overrides for extracted-service discovery. Empty values
    # retain the caller-scoped Keystone catalog as the canonical default.
    service_waygate_internal_url: str = ""
    service_drover_internal_url: str = ""
    service_lumen_internal_url: str = ""
    service_palimpsest_internal_url: str = ""

    # Global Cloud Shell resources live only in a dedicated service project.
    # User tokens are separately re-scoped to the selected logical project and
    # are never used for Zun/Cinder lifecycle operations.
    cloud_shell_service_project_id: str = ""
    cloud_shell_image: str = ""
    cloud_shell_network_id: str = ""
    cloud_shell_security_group: str = ""
    cloud_shell_auth_url: str = ""
    cloud_shell_interface: Literal["public", "internal", "admin"] = "internal"
    cloud_shell_volume_type: str = ""
    cloud_shell_home_size_gib: int = 5
    cloud_shell_cpu: float = 1.0
    cloud_shell_memory_mib: int = 1024
    cloud_shell_idle_timeout_seconds: int = 1200
    cloud_shell_max_session_seconds: int = 3600
    cloud_shell_ticket_ttl_seconds: int = 60
    cloud_shell_reconcile_interval_seconds: int = 60
    cloud_shell_zun_websocket_origin: str = ""
    # Generic instance health-report callback.
    instance_health_callback_base_url: str = ""

    # Shared legacy master key. Existing ciphertext domains still depend on it.
    k3s_kubeconfig_encryption_key: str = ""
    k3s_gpu_admission_token: str = ""
    k3s_provisioning_token: str = ""

    # Background worker runtime manager
    worker_runtime_mode: Literal["static", "docker", "kubernetes"] = "static"
    worker_runtime_reconcile_interval: int = 30
    worker_runtime_fail_closed: bool = True
    worker_runtime_notion_worker_enabled: bool = True
    worker_runtime_notion_worker_desired_replicas: int = 1
    worker_runtime_notion_worker_max_replicas: int = 1
    worker_runtime_notion_worker_module: str = "app.notion_worker"
    worker_runtime_docker_socket_path: str = ""
    worker_runtime_docker_image: str = ""
    worker_runtime_docker_network: str = ""
    worker_runtime_docker_config_mount: str = "/app/afterglow.conf"
    worker_runtime_docker_config_host_path: str = ""
    worker_runtime_docker_gpu_config_mount: str = "/app/config.gpu.toml"
    worker_runtime_docker_gpu_config_host_path: str = ""
    worker_runtime_docker_logs_mount: str = "/app/logs"
    worker_runtime_docker_logs_host_path: str = ""
    worker_runtime_docker_env_allowlist: str = (
        "AFTERGLOW_ENV,AFTERGLOW_ALLOW_INSECURE,SECRET_KEY,OS_PASSWORD,DATABASE_URL,"
        "K3S_KUBECONFIG_ENCRYPTION_KEY,K3S_GPU_ADMISSION_TOKEN,K3S_PROVISIONING_TOKEN,PROMETHEUS_PASSWORD,"
        "GITLAB_OIDC_CLIENT_SECRET,NOTION_CONFIG_ENCRYPTION_KEY"
    )
    worker_runtime_kubernetes_namespace: str = "afterglow"
    worker_runtime_kubernetes_service_account_token_path: str = "/var/run/secrets/kubernetes.io/serviceaccount/token"
    worker_runtime_kubernetes_service_account_ca_path: str = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
    worker_runtime_kubernetes_manage_deployments: bool = False

    @field_validator(
        "worker_runtime_reconcile_interval",
        "worker_runtime_notion_worker_desired_replicas",
        "worker_runtime_notion_worker_max_replicas",
    )
    @classmethod
    def validate_worker_runtime_counts(cls, v: int) -> int:
        if v < 0:
            raise ValueError("worker runtime replica counts and intervals must be non-negative")
        return v

    # --- Palimpsest 로컬 KVM 런타임 (선택) ---
    # 비어 있으면 기능 비활성(503). `qemu:///system` 또는 `qemu+ssh://user@host/system`.
    # libvirt-python 은 별도 extra 다: `uv sync --extra kvm`
    palimpsest_kvm_uri: str = ""
    # 레이어 blob 이 놓인 호스트 경로. 허브 OCI 번들을 펼치면 이 배치가 된다:
    #   <kvm_layer_root>/blobs/sha256/<hex>
    palimpsest_kvm_layer_root: str = "/var/lib/palimpsest/layers"
    # 도메인별 루트 오버레이(qcow2)와 seed ISO 를 두는 경로
    palimpsest_kvm_state_dir: str = "/var/lib/palimpsest/domains"
    union_cephx_rotate_hours: int = 24  # CephX 키 자동 회전 주기 (0이면 비활성)
    union_auto_egress_sg_enabled: bool = True  # Union VM에 egress SG 자동 attach
    union_egress_sg_name: str = "union-egress-default"  # 자동 생성/재사용할 SG 이름

    # 모니터링 (Prometheus + Grafana — Option A, label-based 프로젝트 격리)
    monitoring_auto_sg_enabled: bool = True  # 프로젝트/인스턴스 생성 시 monitoring SG 자동 attach
    node_exporter_sg_name: str = "node_exporter"  # node_exporter ingress SG 이름 (tcp/9100)
    dcgm_exporter_sg_name: str = "dcgm_exporter"  # dcgm_exporter ingress SG 이름 (tcp/9400, GPU 전용)
    node_exporter_port: int = 9100  # VM에 설치된 node_exporter 포트
    dcgm_exporter_port: int = 9400  # GPU VM의 dcgm_exporter 포트
    libvirt_exporter_port: int = 9177  # compute 노드 libvirt_exporter 포트 (kolla enable_prometheus_libvirt_exporter)
    gpu_flavor_prefix: str = "gpu."  # GPU 노드로 판별할 flavor 이름 prefix
    monitoring_scrape_cidr: str = ""  # Prometheus scrape CIDR (예: 10.0.0.0/8). 미설정 시 ValueError
    monitoring_sd_token: str = ""  # /api/sd/prometheus/targets 인증 토큰
    grafana_base_url: str = ""  # Grafana 외부 URL (예: https://grafana.example.com)
    grafana_dashboard_node_uid: str = "afterglow-node"
    grafana_dashboard_rabbitmq_uid: str = "afterglow-rabbitmq"
    grafana_dashboard_mysqld_uid: str = "afterglow-mysqld"
    grafana_dashboard_memcached_uid: str = "afterglow-memcached"
    grafana_dashboard_etcd_uid: str = "afterglow-etcd"
    grafana_dashboard_haproxy_uid: str = "afterglow-haproxy"
    grafana_dashboard_libvirt_uid: str = "afterglow-libvirt"
    grafana_dashboard_openstack_uid: str = "afterglow-openstack"
    grafana_dashboard_ceph_uid: str = "afterglow-ceph"
    grafana_dashboard_instance_cpu_uid: str = "afterglow-instance-cpu"
    grafana_dashboard_instance_gpu_uid: str = "afterglow-instance-gpu"
    # Prometheus 서버 주소. 우선순위: 환경변수 PROMETHEUS_BASE_URL > afterglow.conf [monitoring].prometheus_base_url > 기본값
    prometheus_base_url: str = "http://prometheus:9090"
    prometheus_username: str = ""  # basic auth 미사용 시 빈 문자열
    prometheus_password: str = ""

    # Notion 연동
    notion_config_encryption_key: str = ""  # 미설정 시 k3s_kubeconfig_encryption_key 재사용

    # GPU
    gpu_available_visible: bool = False  # true 시 사용자에게 GPU 가용량 API 노출

    # 세션 관리
    session_timeout_seconds: int = 3600
    jwt_access_ttl: int = 900  # access JWT 수명 (초), 기본 15분
    jwt_refresh_ttl: int = 604800  # refresh JWT 수명 (초), 기본 7일
    token_ip_binding_mode: str = "subnet"  # off | log | subnet | strict

    @field_validator("token_ip_binding_mode")
    @classmethod
    def validate_binding_mode(cls, v: str) -> str:
        _VALID_MODES = {"off", "log", "subnet", "strict"}
        if v not in _VALID_MODES:
            raise ValueError(f"token_ip_binding_mode={v!r} 은 유효하지 않습니다. 허용값: {sorted(_VALID_MODES)}")
        return v

    # 보안 정책
    # True: system:all role OR admin project+role 모두 system admin 인정 (마이그레이션 호환 모드)
    # False: system:all role만 system admin으로 인정 (자기복제 권한 상승 완전 차단)
    admin_legacy_project_policy: bool = False

    # 로그인 브루트포스 방어
    login_max_attempts: int = 10  # 잠금 임계값 (실패 횟수)
    login_lockout_seconds: int = 300  # 기본 잠금 시간 (초, 5분)
    login_backoff_base: int = 2  # 지수 백오프 밑수

    # Nova 기본값
    boot_volume_size_gb: int = 20
    upper_volume_size_gb: int = 50
    builder_build_timeout: int = 3600  # 빌드 SSH 명령 최대 대기 시간 (초)
    builder_layer_share_size_gb: int = 20  # 레이어별 동적 Manila NFS share 용량 (GB)
    builder_ssh_user: str = "ubuntu"
    builder_ssh_key_path: str = "/etc/afterglow/ssh/builder.key"

    # 데이터베이스 (MariaDB/MySQL, 선택적)
    database_url: str = ""
    database_pool_size: int = 5
    database_max_overflow: int = 10
    database_auto_create_tables: bool = True
    database_connect_timeout: int = 10
    database_pool_timeout: int = 10
    database_unhealthy_seconds: int = 15
    database_db_auto_backup_cron: str = "0 3 * * *"

    # GitLab OIDC
    gitlab_oidc_enabled: bool = False
    gitlab_oidc_gitlab_url: str = ""
    gitlab_oidc_client_id: str = ""
    gitlab_oidc_client_secret: str = ""
    gitlab_oidc_idp_id: str = "gitlab"
    gitlab_oidc_protocol_id: str = "openid"
    gitlab_oidc_redirect_uri: str = ""
    gitlab_oidc_scopes: str = "openid email profile read_user"

    # SMTP 이메일 전송
    smtp_enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_address: str = "noreply@afterglow.example.com"
    smtp_from_name: str = "Afterglow"
    smtp_use_tls: bool = True
    smtp_timeout_seconds: int = 10
    smtp_invitation_token_expiry_days: int = 7

    # 프론트엔드 기본 URL (초대 이메일 링크 생성에 사용)
    frontend_base_url: str = ""
    # 브라우저 런타임 API Origin (비워두면 프론트엔드가 현재 호스트의 backend_port 사용)
    public_api_base: str = ""

    # 로깅 설정
    log_directory: str = "logs"
    log_level: str = "INFO"
    log_max_bytes: int = 52428800  # 50MB

    @field_validator("os_auth_url", mode="after")
    @classmethod
    def _norm_auth_url(cls, v: str) -> str:
        from app.services._endpoint import normalize_keystone_url

        return normalize_keystone_url(v)

    @field_validator(
        "os_manila_endpoint",
        "os_swift_endpoint",
        "service_waygate_internal_url",
        "service_drover_internal_url",
        "service_lumen_internal_url",
        "service_palimpsest_internal_url",
    )
    @classmethod
    def _norm_service_endpoint(cls, v: str) -> str:
        from app.services._endpoint import normalize_endpoint

        return normalize_endpoint(v)

    @property
    def ssl_verify(self) -> bool | str:
        """OpenStack API SSL 검증 설정. cacert 경로가 있으면 해당 경로, insecure면 False, 아니면 True."""
        if self.os_insecure:
            return False
        if self.os_cacert:
            return self.os_cacert
        return True

    @property
    def ceph_monitor_list(self) -> list[str]:
        return [m.strip() for m in self.ceph_monitors.split(",") if m.strip()]

    @property
    def ceph_rbd_enabled(self) -> bool:
        return bool(self.ceph_rbd_conf_path.strip() and self.ceph_rbd_keyring_path.strip())

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @model_validator(mode="after")
    def warn_insecure_defaults(self) -> "Settings":
        import logging
        import os

        logger = logging.getLogger(__name__)
        env = os.environ.get("AFTERGLOW_ENV", "development").strip().lower()
        is_production = env == "production"
        insecure_flag = os.environ.get("AFTERGLOW_ALLOW_INSECURE", "").strip() == "1"

        ceph_paths = (
            bool(self.ceph_rbd_conf_path.strip()),
            bool(self.ceph_rbd_keyring_path.strip()),
        )
        if any(ceph_paths) and not all(ceph_paths):
            raise ValueError("[ceph] rbd_conf_path와 rbd_keyring_path는 함께 설정하거나 모두 비워야 합니다")

        if self.ceph_rbd_enabled:
            if not self.ceph_rbd_cluster_fsid.strip() or not self.ceph_rbd_volume_pools:
                raise ValueError(
                    "[ceph] rbd_cluster_fsid와 rbd_volume_pools는 rbd_conf_path/rbd_keyring_path 설정 시 필수"
                )
            if re.fullmatch(r"client\.[A-Za-z0-9._-]{1,64}", self.ceph_rbd_client_name) is None:
                raise ValueError(f"[ceph] 유효하지 않은 Ceph client 이름: {self.ceph_rbd_client_name!r}")
            if self.ceph_rbd_command_timeout_seconds <= 0:
                raise ValueError("[ceph] rbd_command_timeout_seconds는 양수여야 합니다")
            for backend, pool in self.ceph_rbd_volume_pools.items():
                if re.fullmatch(r"[A-Za-z0-9._@-]{1,64}", backend) is None:
                    raise ValueError(f"[ceph] 유효하지 않은 Cinder backend 이름: {backend!r}")
                if re.fullmatch(r"[A-Za-z0-9._-]{1,64}", pool) is None:
                    raise ValueError(f"[ceph] 유효하지 않은 RBD pool 이름: {pool!r}")
        cloud_shell_bounds = (
            ("home_size_gib", self.cloud_shell_home_size_gib, 1, 100),
            ("cpu", self.cloud_shell_cpu, 0.1, 8.0),
            ("memory_mib", self.cloud_shell_memory_mib, 256, 32768),
            ("idle_timeout_seconds", self.cloud_shell_idle_timeout_seconds, 60, 3600),
            ("max_session_seconds", self.cloud_shell_max_session_seconds, 300, 14400),
            ("ticket_ttl_seconds", self.cloud_shell_ticket_ttl_seconds, 10, 120),
            ("reconcile_interval_seconds", self.cloud_shell_reconcile_interval_seconds, 15, 600),
        )
        for field, value, lower, upper in cloud_shell_bounds:
            if not lower <= value <= upper:
                raise ValueError(f"cloud_shell.{field} must be between {lower} and {upper}")
        if self.cloud_shell_max_session_seconds < self.cloud_shell_idle_timeout_seconds:
            raise ValueError("cloud_shell.max_session_seconds may not be shorter than idle_timeout_seconds")
        if self.service_cloud_shell_enabled:
            required = {
                "service_project_id": self.cloud_shell_service_project_id,
                "image": self.cloud_shell_image,
                "network_id": self.cloud_shell_network_id,
                "security_group": self.cloud_shell_security_group,
                "auth_url": self.cloud_shell_auth_url,
                "zun_websocket_origin": self.cloud_shell_zun_websocket_origin,
            }
            missing = [field for field, value in required.items() if not value.strip()]
            if missing:
                raise ValueError(f"enabled Cloud Shell requires: {', '.join(missing)}")
            if not self.service_zun_enabled:
                raise ValueError("services.cloud_shell=true requires services.zun=true")
            try:
                UUID(self.cloud_shell_service_project_id)
            except ValueError as exc:
                raise ValueError("cloud_shell.service_project_id must be a UUID") from exc
            if self.cloud_shell_service_project_id == self.os_service_project_id:
                raise ValueError("Cloud Shell requires a dedicated service project")

            auth_url = urlsplit(self.cloud_shell_auth_url)
            auth_is_trusted = (
                auth_url.scheme == "https"
                and bool(auth_url.netloc)
                and not auth_url.username
                and not auth_url.password
                and not auth_url.query
                and not auth_url.fragment
                and auth_url.path.rstrip("/").endswith("/v3")
            ) or (
                is_development_loopback_http_url(self.cloud_shell_auth_url)
                and auth_url.path.rstrip("/").endswith("/v3")
            )
            if not auth_is_trusted:
                raise ValueError("cloud_shell.auth_url must be trusted HTTPS /v3 or development loopback HTTP")

            ws_origin = urlsplit(self.cloud_shell_zun_websocket_origin)
            ws_is_loopback = (
                env == "development"
                and ws_origin.scheme == "ws"
                and (ws_origin.hostname or "").lower() in _LOOPBACK_HOSTS
            )
            if (
                ws_origin.scheme not in {"wss", "ws"}
                or not ws_origin.netloc
                or ws_origin.username
                or ws_origin.password
                or ws_origin.path not in {"", "/"}
                or ws_origin.query
                or ws_origin.fragment
                or (ws_origin.scheme == "ws" and not ws_is_loopback)
            ):
                raise ValueError("cloud_shell.zun_websocket_origin must be WSS or development loopback WS")
            if is_production and re.search(r"@sha256:[0-9a-f]{64}$", self.cloud_shell_image) is None:
                raise ValueError("production Cloud Shell image must use an immutable sha256 digest")
        # production 환경에서는 INSECURE 우회 자체를 금지 — 운영 부팅 실수 차단.
        if is_production and insecure_flag:
            raise ValueError(
                "AFTERGLOW_ALLOW_INSECURE=1 must NOT be set when AFTERGLOW_ENV=production. "
                "Provide a real SECRET_KEY (and other secrets) instead of bypassing the check."
            )

        # docker 모드는 백엔드 컨테이너에 /var/run/docker.sock(호스트 root 등가)을 마운트해야
        # 동작한다. 멀티테넌트 프로덕션에서 백엔드 침해 시 호스트 전체 탈취로 이어지므로,
        # 운영 부팅 시점에 fail-closed 로 거부한다. 프로덕션에서는 mode='kubernetes' 를 쓴다.
        if is_production and self.worker_runtime_mode == "docker":
            raise ValueError(
                "worker_runtime.mode='docker' mounts the host Docker socket "
                "(root-equivalent) and must NOT be used when AFTERGLOW_ENV=production. "
                "Use mode='kubernetes' for production worker management."
            )

        for field_name, endpoint in (
            ("services.waygate_internal_url", self.service_waygate_internal_url),
            ("services.drover_internal_url", self.service_drover_internal_url),
            ("services.lumen_internal_url", self.service_lumen_internal_url),
            ("services.palimpsest_internal_url", self.service_palimpsest_internal_url),
        ):
            if not endpoint:
                continue
            try:
                parsed = urlsplit(endpoint)
                _ = parsed.port
            except ValueError as exc:
                raise ValueError(f"{field_name} must use a valid absolute URL") from exc
            if (
                parsed.scheme not in {"http", "https"}
                or (is_production and parsed.scheme != "https")
                or not parsed.netloc
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
            ):
                scheme_requirement = "HTTPS" if is_production else "HTTP or HTTPS"
                raise ValueError(
                    f"{field_name} requires an absolute {scheme_requirement} URL "
                    "without credentials, query, or fragment"
                )

        if self.service_mcp_enabled:

            def valid_mcp_url(value: str, *, name: str) -> None:
                parsed = urlsplit(value)
                if (
                    parsed.scheme not in {"http", "https"}
                    or (is_production and parsed.scheme != "https")
                    or not parsed.netloc
                    or parsed.username
                    or parsed.password
                    or parsed.query
                    or parsed.fragment
                ):
                    scheme_requirement = "HTTPS" if is_production else "HTTP or HTTPS"
                    raise ValueError(
                        f"{name} requires an absolute {scheme_requirement} URL without credentials, query, or fragment"
                    )

            public_mcp_url = self.mcp_public_url or f"{self.public_api_base.rstrip('/')}/api/v1/mcp"
            consent_url = self.mcp_oauth_consent_url or f"{self.frontend_base_url.rstrip('/')}/oauth/mcp/authorize"
            valid_mcp_url(public_mcp_url, name="services.mcp")
            valid_mcp_url(consent_url, name="services.mcp OAuth consent")

        if self.secret_key == "change-me-in-production":
            if is_production:
                raise ValueError(
                    "SECRET_KEY is set to the default value 'change-me-in-production' "
                    "while AFTERGLOW_ENV=production. Refusing to start with an insecure key."
                )
            if insecure_flag:
                logger.warning(
                    "SECRET_KEY is set to the default insecure value. "
                    "AFTERGLOW_ALLOW_INSECURE=1 is set — this must NOT be used in production."
                )
            else:
                raise ValueError(
                    "SECRET_KEY is set to the default value 'change-me-in-production'. "
                    "Set a strong random value in afterglow.conf [app] secret_key or SECRET_KEY env var. "
                    "To override this check in development, set AFTERGLOW_ALLOW_INSECURE=1."
                )
        elif len(self.secret_key) < 32:
            # 비기본이어도 약한(짧은) 키는 production 부팅을 거부 — 엔트로피 게이트.
            # dev 는 기존 워크플로 비파괴를 위해 경고만.
            if is_production:
                raise ValueError(
                    f"SECRET_KEY is too short for AFTERGLOW_ENV=production "
                    f"(got {len(self.secret_key)} chars, require >= 32). "
                    "Generate a strong random value, e.g. `openssl rand -hex 32`."
                )
            logger.warning(
                "SECRET_KEY is shorter than 32 characters (%d). Use a strong random value "
                "(e.g. `openssl rand -hex 32`) before deploying to production.",
                len(self.secret_key),
            )
        mcp_positive = (
            self.mcp_authorization_ticket_ttl_seconds,
            self.mcp_access_token_ttl_seconds,
            self.mcp_default_grant_ttl_days,
            self.mcp_max_grant_ttl_days,
            self.mcp_max_personal_tokens,
            self.mcp_max_delegated_grants,
            self.mcp_request_max_bytes,
            self.mcp_read_result_max_bytes,
            self.mcp_mutation_result_max_bytes,
            self.mcp_default_page_size,
            self.mcp_max_page_size,
            self.mcp_concurrent_calls_per_grant,
            self.mcp_read_rate_per_minute,
            self.mcp_mutation_rate_per_minute,
        )
        if any(value <= 0 for value in mcp_positive):
            raise ValueError("all [mcp] limits and TTLs must be positive")
        if self.mcp_default_grant_ttl_days > self.mcp_max_grant_ttl_days:
            raise ValueError("mcp.default_grant_ttl_days may not exceed mcp.max_grant_ttl_days")
        if self.mcp_default_page_size > self.mcp_max_page_size:
            raise ValueError("mcp.default_page_size may not exceed mcp.max_page_size")
        return self

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# 부팅 시 실제로 읽어들인 설정 파일 목록(진단용). load_raw_toml() 첫 호출 시 채워진다.
_LOADED_CONFIG_SOURCES: list[dict] = []


def _record_source(path: Path, role: str) -> None:
    try:
        st = path.stat()
        _LOADED_CONFIG_SOURCES.append({"path": str(path), "role": role, "size": st.st_size, "mtime": st.st_mtime})
    except OSError:
        _LOADED_CONFIG_SOURCES.append({"path": str(path), "role": role, "size": None, "mtime": None})


@lru_cache
def load_raw_toml() -> dict:
    """afterglow.conf 원본(+ 같은 디렉터리 오버라이드)을 중첩 구조 그대로 반환.

    머지 규칙: dict는 재귀 병합, 그 외는 오버라이드가 덮어쓴다. 오버라이드 파일은 알파벳순으로
    적용되어 뒤에 오는 파일이 앞의 값을 이긴다.
    """
    _LOADED_CONFIG_SOURCES.clear()
    for path in _config_candidates():
        if path.exists() and path.stat().st_size > 0:
            _record_source(path, "base")
            with open(path, "rb") as f:
                merged = tomllib.load(f)
            for override in _config_override_paths(path):
                _record_source(override, "override")
                with open(override, "rb") as f:
                    merged = _deep_merge(merged, tomllib.load(f))
            return merged
    return {}


@lru_cache
def get_settings() -> Settings:
    # K8s 서비스 디스커버리 환경변수 충돌 방지
    # K8s는 서비스명 기반으로 {SVC}_PORT=tcp://IP:PORT 등을 자동 주입하는데,
    # 이것이 우리 설정 필드(backend_port, frontend_port 등)와 충돌할 수 있음.
    _k8s_collision_keys = ("BACKEND_PORT", "FRONTEND_PORT")
    for key in _k8s_collision_keys:
        val = os.environ.get(key, "")
        if val.startswith("tcp://") or val.startswith("udp://"):
            del os.environ[key]

    # TOML values seed missing environment settings. Secret mounts commonly
    # materialize optional values as an empty string; that must not erase a
    # configured GitLab client secret from a protected TOML layer.
    toml_data = _load_toml()
    for key, value in toml_data.items():
        env_key = key.upper()
        if env_key not in os.environ or (
            env_key in _EMPTY_ENV_TOML_FALLBACK_KEYS and os.environ[env_key] == "" and value != ""
        ):
            os.environ[env_key] = json.dumps(value) if isinstance(value, dict) else str(value)
    return Settings()
