#!/usr/bin/env python3
"""afterglow.conf → Helm values.yaml 변환기.

afterglow.conf(및 afterglow.*.conf 오버라이드)을 읽어
helm/afterglow/values-local.yaml (또는 지정 경로)을 생성합니다.

GPU 디바이스 맵은 병합된 설정에서 공개 필드만 gpu.configToml로 렌더링합니다.
렌더러는 설정 디렉터리나 GPU 원본 파일을 읽지 않습니다.

생성된 파일은 values.yaml 위에 덮어쓰는 오버라이드로 사용합니다:
    helm upgrade --install afterglow helm/afterglow \
        -f <output>

사용법:
    python3 config2helm.py
    python3 config2helm.py --config /path/to/afterglow.conf
    python3 config2helm.py --output helm/afterglow/values-local.yaml
    python3 config2helm.py --no-secrets   # 시크릿 제외 (git 안전)
    python3 config2helm.py --dry-run      # 시크릿 없이 stdout 출력, 파일 쓰기 없음
"""

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

from generation_config import (
    load_config as load_config,
    merge_config,
    prepare_config,
    write_files,
)
from generate_k8s import auth_secret_env, render_auth_toml, render_gpu_toml

_USE_COLOR = os.name != "nt" or os.environ.get("FORCE_COLOR")


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _USE_COLOR else text


def green(t: str) -> str:  return _c("32", t)
def yellow(t: str) -> str: return _c("33", t)


# ─────────────────────────────────────────────────────────────────────────────
# YAML 렌더링 헬퍼
# ─────────────────────────────────────────────────────────────────────────────

def _yaml_str(v: str, indent: int = 0) -> str:
    """JSON-quoted scalars are also YAML strings, including control characters."""
    return json.dumps(v, ensure_ascii=False)


def _yaml_val(v, indent: int = 0) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return _yaml_str(v, indent)
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        # 문자열 리스트만 지원
        items = ", ".join(f'"{i}"' for i in v)
        return f"[{items}]"
    return f'"{v}"'


# ─────────────────────────────────────────────────────────────────────────────
# 변환 로직
# ─────────────────────────────────────────────────────────────────────────────

def _s(key: str) -> str:
    """snake_case → camelCase."""
    parts = key.split("_")
    return parts[0] + "".join(p.title() for p in parts[1:])


def convert(cfg: dict, include_secrets: bool) -> dict:
    """afterglow.conf dict → Helm values dict."""
    out: dict = {}
    out["debug"] = cfg.get("DEFAULT", {}).get("debug", False)

    os_cfg  = cfg.get("openstack", {})
    app     = cfg.get("app", {})
    cache   = cfg.get("cache", {})
    sess    = cfg.get("session", {})
    nova    = cfg.get("nova", {})
    builder = cfg.get("builder", {})
    union   = cfg.get("union", {})
    gpu     = cfg.get("gpu", {})
    svc     = cfg.get("services", {})
    mcp     = cfg.get("mcp", {})
    cloud_shell = cfg.get("cloud_shell", {})
    k3s     = cfg.get("k3s", {})
    db      = cfg.get("database", {})
    cors    = cfg.get("cors", {})
    logging_cfg = cfg.get("logging", {})
    mon     = cfg.get("monitoring", {})
    notion  = cfg.get("notion", {})
    smtp    = cfg.get("smtp", {})
    sec     = cfg.get("security", {})
    traffic = cfg.get("traffic_analytics", {})
    ceph = cfg.get("ceph", {})

    # Namespace selects no domain. Route only the operator's configured origins,
    # using the same frontend/CORS/API precedence as generated Kubernetes.
    cors_origin = cors.get("origins", "").split(",", 1)[0].strip()
    public_origin = app.get("public_api_base") or app.get("frontend_base_url") or cors_origin
    frontend_origin = app.get("frontend_base_url") or cors_origin or public_origin
    frontend_host = urlsplit(frontend_origin).hostname
    api_host = urlsplit(public_origin).hostname
    if frontend_host:
        out["ingress"] = {
            "host": frontend_host,
            "apiHosts": [api_host] if api_host and api_host != frontend_host else [],
        }

    # ── secrets ────────────────────────────────────────────────────────────
    secrets: dict = {}
    if include_secrets:
        def _sec(val: str, key: str) -> None:
            if val:
                secrets[key] = val

        _sec(os_cfg.get("password", ""),             "osPassword")
        _sec(app.get("secret_key", ""),              "secretKey")
        _sec(k3s.get("kubeconfig_encryption_key", ""), "k3sKubeconfigEncryptionKey")
        _sec(k3s.get("gpu_admission_token", ""), "k3sGpuAdmissionToken")
        _sec(mcp.get("lumen_service_token", ""), "lumenMcpServiceToken")
        _sec(ceph.get("rbd_keyring", ""), "cephRbdKeyring")
        _sec(db.get("url", ""),                      "databaseUrl")
        _sec(mon.get("prometheus_password", ""),     "prometheusPassword")
        _sec(mon.get("sd_token", ""),                "monitoringSDToken")
        _sec(notion.get("config_encryption_key", ""), "notionConfigEncryptionKey")
        _sec(smtp.get("password", ""),               "smtpPassword")
        _sec(builder.get("ssh_private_key", ""),     "builderSshPrivateKey")
        _sec(traffic.get("hmac_key", ""), "trafficAnalyticsHmacKey")
        _sec(traffic.get("frontend_ingest_key", ""), "trafficAnalyticsFrontendIngestKey")
        if mon.get("infrastructure_topology_observers"):
            secrets["infrastructureTopologyObservers"] = mon["infrastructure_topology_observers"]
        fabric_targets = mon.get("infrastructure_fabric", {}).get("targets", [])
        if fabric_targets:
            secrets["infrastructureFabricTargets"] = fabric_targets
        if provider_secrets := auth_secret_env(cfg):
            secrets["authProviders"] = provider_secrets
    if secrets:
        out["secrets"] = secrets

    ceph_out = {
        _s(k): ceph[k] for k in (
            "rbd_conf_content", "rbd_conf_path", "rbd_keyring_path",
            "rbd_client_name", "rbd_cluster_fsid", "rbd_command_timeout_seconds",
            "rbd_volume_pools",
        ) if k in ceph
    }
    if ceph_out:
        out["ceph"] = ceph_out

    # ── openstack ──────────────────────────────────────────────────────────
    os_out: dict = {}
    for k in ("auth_url", "project_name", "project_domain_name", "user_domain_name",
              "region_name", "username", "interface", "cacert",
              "manila_endpoint", "manila_share_network_id", "manila_share_type",
              "manila_nfs_share_type", "manila_nfs_root_squash", "manila_nfs_sec_flavor",
              "manila_cephx_key_timeout_seconds", "ceph_monitors", "service_project_id",
              "swift_endpoint", "swift_upload_timeout", "trash_retention_days",
              "s3_endpoint"):
        if k in os_cfg:
            os_out[_s(k)] = os_cfg[k]
    if os_cfg.get("insecure"):
        os_out["insecure"] = True
    if os_out:
        out["openstack"] = os_out

    # ── app ────────────────────────────────────────────────────────────────
    app_out: dict = {}
    for k in ("backend_port", "frontend_port", "site_name", "site_description",
              "logo_path", "favicon_path", "refresh_interval_ms",
              "frontend_base_url", "public_api_base", "trusted_proxies"):
        if k in app:
            app_out[_s(k)] = app[k]
    if app_out:
        out["app"] = app_out

    # ── cache (sentinel 관련 K8s 고정값 제외) ──────────────────────────────
    cache_out: dict = {}
    for k in ("ttl_fast", "ttl_normal", "ttl_slow", "ttl_static",
              "default_ttl_seconds", "backend",
              "dynamic_threshold_low", "dynamic_threshold_high",
              "ttl_identity_stable", "ttl_catalog_slow", "ttl_project_meta",
              "ttl_operational_live", "ttl_admin_overview", "ttl_auth_token"):
        if k in cache:
            cache_out[_s(k)] = cache[k]
    if cache_out:
        out["cache"] = cache_out

    # ── session ────────────────────────────────────────────────────────────
    sess_out: dict = {}
    for k in ("timeout_seconds", "warning_before_seconds", "absolute_timeout",
              "jwt_access_ttl", "jwt_refresh_ttl", "token_ip_binding_mode"):
        if k in sess:
            sess_out[_s(k)] = sess[k]
    if sess_out:
        out["session"] = sess_out

    # ── nova ───────────────────────────────────────────────────────────────
    nova_out: dict = {}
    for k in ("default_network_id", "default_availability_zone",
              "boot_volume_size_gb", "upper_volume_size_gb",
              "default_network_enabled", "default_network_cidr",
              "default_network_external_id"):
        if k in nova:
            nova_out[_s(k)] = nova[k]
    if nova_out:
        out["nova"] = nova_out

    # ── builder ────────────────────────────────────────────────────────────
    builder_out: dict = {}
    for k in ("image_id", "flavor_id", "network_id", "persistent_server_id",
              "ssh_user", "ssh_key_path", "ssh_host", "floating_network_id",
              "build_timeout"):
        if k in builder:
            builder_out[_s(k)] = builder[k]
    # ssh_private_key는 secret으로 이동됨 — 제외
    if builder_out:
        out["builder"] = builder_out

    # ── union ──────────────────────────────────────────────────────────────
    union_out: dict = {}
    for k in ("layer_store_rw_share_id", "layer_store_ro_share_id",
              "manifest_store_share_id"):
        if k in union:
            union_out[_s(k)] = union[k]
    if union_out:
        out["union"] = union_out

    # ── gpu: same closed public projection as generated Kubernetes ──────────
    out["gpu"] = {"configToml": render_gpu_toml(cfg)}
    if "available_visible" in gpu:
        out["gpu"]["availableVisible"] = gpu["available_visible"]

    if "auth" in cfg:
        out["auth"] = {
            "configToml": render_auth_toml(cfg),
            "providerKeys": list(cfg["auth"].get("providers", {})),
        }

    # ── services ───────────────────────────────────────────────────────────
    svc_out: dict = {}
    for k in ("magnum", "manila", "zun", "cloud_shell", "k3s", "swift", "trove", "barbican", "mcp"):
        if k in svc:
            svc_out[k] = svc[k]
    if svc_out:
        out["services"] = svc_out

    # ── Cloud Shell ────────────────────────────────────────────────────────
    cloud_shell_out: dict = {}
    for k in ("service_project_id", "image", "image_pull_policy", "registry_id",
              "network_id", "security_group", "auth_url", "interface", "volume_type",
              "home_size_gib", "cpu", "memory_mib", "idle_timeout_seconds",
              "max_session_seconds", "ticket_ttl_seconds", "reconcile_interval_seconds",
              "zun_websocket_origin"):
        if k in cloud_shell:
            cloud_shell_out[_s(k)] = cloud_shell[k]
    if cloud_shell_out:
        out["cloudShell"] = cloud_shell_out

    # ── MCP ────────────────────────────────────────────────────────────────
    mcp_out: dict = {}
    for k in ("public_url", "oauth_consent_url"):
        if k in mcp:
            mcp_out[_s(k)] = mcp[k]
    if mcp_out:
        out["mcp"] = mcp_out

    # ── k3s ────────────────────────────────────────────────────────────────
    k3s_out: dict = {}
    for k in ("version", "server_flavor_id", "default_agent_flavor_id",
              "server_image_id", "fcos_image_id", "callback_base_url",
              "boot_volume_size_gb", "cert_rotation_node_timeout_sec",
              "occm_enabled", "occm_image", "occm_floating_network_id",
              "occm_public_network_name",
              "cinder_csi_enabled", "cinder_csi_image", "cinder_csi_default_az",
              "manila_csi_enabled", "manila_csi_image", "manila_csi_nfs_image",
              "manila_csi_share_protocol",
              "keystone_auth_enabled", "keystone_auth_image", "keystone_auth_policy",
              "octavia_ingress_enabled", "octavia_ingress_image",
              "octavia_ingress_subnet_id", "octavia_ingress_floating_network_id",
              "barbican_kms_enabled", "barbican_kms_image", "barbican_kms_kek_id",
              "api_lb_enabled", "api_lb_vip_network_id", "api_lb_floating_network_id",
              "lb_subnet_id", "cert_rotation_job_image",
              "stampede_enabled", "stampede_project_id", "stampede_interval",
              "stampede_scale_down_window", "stampede_scale_up_cooldown",
              "stampede_scale_down_cooldown", "stampede_scale_down_threshold",
              "stampede_resource_headroom_factor"):
        if k in k3s:
            k3s_out[_s(k)] = k3s[k]
    # kubeconfig_encryption_key는 secret으로 이동됨 — 제외
    if k3s_out:
        out["k3s"] = k3s_out

    # ── database ───────────────────────────────────────────────────────────
    db_out: dict = {}
    for k in ("pool_size", "max_overflow", "auto_create_tables",
              "connect_timeout", "pool_timeout", "unhealthy_seconds",
              "db_auto_backup_cron"):
        if k in db:
            db_out[_s(k)] = db[k]
    # url은 secret으로 이동됨 — 제외
    if db_out:
        out["database"] = db_out

    # ── cors ───────────────────────────────────────────────────────────────
    if cors:
        out["cors"] = {"origins": cors.get("origins", "")}

    # ── smtp ───────────────────────────────────────────────────────────────
    smtp_out: dict = {}
    for k in ("enabled", "host", "port", "username",
              "from_address", "from_name", "use_tls", "timeout_seconds"):
        if k in smtp:
            smtp_out[_s(k)] = smtp[k]
    # password는 secret으로 이동됨 — 제외
    inv = smtp.get("invitation", {})
    if inv:
        smtp_out["invitation"] = {
            "tokenExpiryDays": inv["token_expiry_days"]
        } if "token_expiry_days" in inv else {}
    if smtp_out:
        out["smtp"] = smtp_out

    # ── monitoring ─────────────────────────────────────────────────────────
    mon_out: dict = {}
    for k in ("host_healthcheck_enabled",
              "infrastructure_topology_enabled", "infrastructure_topology_trace_targets",
              "infrastructure_topology_retention_seconds", "prometheus_base_url", "prometheus_username",
              "scrape_cidr", "auto_sg_enabled",
              "node_exporter_sg_name", "dcgm_exporter_sg_name",
              "node_exporter_port", "dcgm_exporter_port",
              "libvirt_exporter_port", "gpu_flavor_prefix", "grafana_base_url"):
        if k in mon:
            mon_out[_s(k)] = mon[k]
    for key, fields in (
        ("host_healthcheck_targets", ("name", "address", "role", "port")),
        ("infrastructure_topology_peer_targets", ("source_host_id", "target_host_id", "address", "port")),
    ):
        if key in mon:
            mon_out[_s(key)] = [
                {field: target[field] for field in fields if field in target}
                for target in mon[key]
            ]
    # prometheus_password, sd_token은 secret으로 이동됨 — 제외
    dashboards = mon.get("dashboards", {})
    if dashboards:
        mon_out["dashboards"] = {
            _s(k): dashboards[k] for k in (
                "node_uid", "rabbitmq_uid", "mysqld_uid", "proxysql_uid",
                "memcached_uid", "etcd_uid", "haproxy_uid", "libvirt_uid",
                "openstack_uid", "ceph_uid", "instance_cpu_uid", "instance_gpu_uid",
            ) if k in dashboards
        }
    fabric = mon.get("infrastructure_fabric", {})
    if fabric:
        mon_out["infrastructureFabric"] = {_s(k): v for k, v in fabric.items() if k != "targets"}
    if mon_out:
        out["monitoring"] = mon_out
    traffic_out = {_s(k): traffic[k] for k in ("enabled", "retention_days", "geoip_mmdb", "site_country", "cluster_cidrs", "backend_trusted_proxy_cidrs", "frontend_trusted_proxy_cidrs") if k in traffic}
    if traffic_out:
        out["trafficAnalytics"] = traffic_out

    # ── notion ─────────────────────────────────────────────────────────────
    if notion:
        out["notion"] = {"enabled": bool(notion.get("config_encryption_key"))}

    # ── logging ────────────────────────────────────────────────────────────
    if logging_cfg:
        out["logging"] = {
            _s(k): logging_cfg[k] for k in ("log_directory", "log_level", "max_bytes")
            if k in logging_cfg
        }

    # ── security ───────────────────────────────────────────────────────────
    sec_out: dict = {}
    for k in ("login_max_attempts", "login_lockout_seconds", "login_backoff_base"):
        if k in sec:
            sec_out[_s(k)] = sec[k]
    if sec_out:
        out["security"] = sec_out

    return out


# ─────────────────────────────────────────────────────────────────────────────
# YAML 직렬화 (PyYAML 없이 표준 라이브러리만 사용)
# ─────────────────────────────────────────────────────────────────────────────

def _render_yaml(data: dict, indent: int = 0) -> list[str]:
    lines: list[str] = []
    prefix = "  " * indent
    for key, value in data.items():
        if isinstance(value, dict):
            if value:
                lines.append(f"{prefix}{key}:")
                lines.extend(_render_yaml(value, indent + 1))
            else:
                lines.append(f"{prefix}{key}: {{}}")
        elif isinstance(value, list):
            if not value:
                lines.append(f"{prefix}{key}: []")
            else:
                lines.append(f"{prefix}{key}:")
                for item in value:
                    rendered = json.dumps(item, ensure_ascii=False) if isinstance(item, dict) else _yaml_val(item, (indent + 1) * 2)
                    lines.append(f"{prefix}  - {rendered}")
        elif isinstance(value, str) and "\n" in value:
            lines.append(f"{prefix}{key}: {json.dumps(value, ensure_ascii=False)}")
        else:
            lines.append(f"{prefix}{key}: {_yaml_val(value, indent * 2)}")
    return lines


def render_yaml(data: dict, comment_header: str = "") -> str:
    lines: list[str] = []
    if comment_header:
        for ln in comment_header.splitlines():
            lines.append(f"# {ln}" if ln.strip() else "#")
        lines.append("")
    lines.extend(_render_yaml(data))
    lines.append("")
    return "\n".join(lines)


def render_values(cfg: dict, include_secrets: bool = True) -> str:
    """Render merged configuration as a Helm override without filesystem reads.

    Public values are a closed projection; only ``secrets`` contains credentials.
    An explicitly empty GPU map overrides the chart's bundled device defaults.
    """
    boundary = ("Contains secrets; do not commit." if include_secrets
                else "Public values only; secrets excluded.")
    return render_yaml(
        convert(cfg, include_secrets=include_secrets),
        comment_header=f"Generated by config2helm.py.\n{boundary}",
    )


def chart_sources() -> dict[str, str]:
    """Read only canonical chart sources, never local/private deployment files.

    Paths are relative to the chart root, suitable for the setup write transaction.
    Keep this closed list in sync when canonical templates or assets change; do
    not discover files recursively from an operator's potentially private tree.
    """
    chart = Path(__file__).resolve().parent / "helm" / "afterglow"
    names = (
        "Chart.yaml",
        "values.yaml",
        "templates/_helpers.tpl",
        "templates/configmap.yaml",
        "templates/secret.yaml",
        "templates/ingress.yaml",
        "templates/middleware.yaml",
        "templates/namespace.yaml",
        "templates/backend/deployment.yaml",
        "templates/backend/service.yaml",
        "templates/backend/worker-runtime-rbac.yaml",
        "templates/frontend/deployment.yaml",
        "templates/frontend/service.yaml",
        "templates/worker/notion-deployment.yaml",
        "templates/redis/configmap.yaml",
        "templates/redis/headless-service.yaml",
        "templates/redis/sentinel-deployment.yaml",
        "templates/redis/sentinel-service.yaml",
        "templates/redis/service.yaml",
        "templates/redis/statefulset.yaml",
        "templates/monitoring/grafana/configmap-dashboards-provider.yaml",
        "templates/monitoring/grafana/configmap-dashboards.yaml",
        "templates/monitoring/grafana/configmap-datasource.yaml",
        "templates/monitoring/grafana/deployment.yaml",
        "templates/monitoring/grafana/service.yaml",
        "templates/monitoring/prometheus/configmap.yaml",
        "templates/monitoring/prometheus/deployment.yaml",
        "templates/monitoring/prometheus/secret.yaml",
        "templates/monitoring/prometheus/service.yaml",
        "templates/monitoring/opensearch/service.yaml",
        "templates/monitoring/opensearch/statefulset.yaml",
        "files/config.gpu.toml",
        "files/dashboards/ceph.json",
        "files/dashboards/etcd.json",
        "files/dashboards/haproxy.json",
        "files/dashboards/libvirt.json",
        "files/dashboards/memcached.json",
        "files/dashboards/mysqld.json",
        "files/dashboards/node.json",
        "files/dashboards/openstack.json",
        "files/dashboards/rabbitmq.json",
    )
    return {name: (chart / name).read_text(encoding="utf-8") for name in names}


# ─────────────────────────────────────────────────────────────────────────────
# 진입점
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="afterglow.conf → Helm values.yaml 변환기"
    )
    parser.add_argument(
        "--config", type=Path, default=Path.cwd() / "afterglow.conf",
        help="설정 경로 (기본값: ./afterglow.conf)",
    )
    parser.add_argument(
        "--override", dest="override_paths", action="append", type=Path,
        default=[], metavar="PATH", help="명시적 오버라이드 (반복 지정 가능)",
    )
    parser.add_argument(
        "--namespace", choices=("afterglow", "afterglow-dev"),
        default="afterglow", help="대상 네임스페이스 (도메인 프로필은 --override로 명시)",
    )
    parser.add_argument(
        "--output", type=Path,
        default=Path.cwd() / "helm" / "afterglow" / "values-local.yaml",
        help="출력 파일 경로 (기본값: ./helm/afterglow/values-local.yaml)",
    )
    parser.add_argument(
        "--no-secrets", action="store_true", help="시크릿 값 제외",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="시크릿 없이 stdout 출력, 설정 초기화 및 파일 쓰기 없음",
    )
    args = parser.parse_args()
    config_path = args.config.resolve()
    output_path = args.output.resolve()
    include_secrets = not (args.no_secrets or args.dry_run)
    try:
        text = prepare_config(config_path)
        cfg = merge_config(config_path, text, args.override_paths)
        content = render_values(cfg, include_secrets=include_secrets)
        if args.dry_run:
            print(content, end="")
            return
        if output_path == config_path:
            raise ValueError("Configuration and values paths must be distinct")
        contents = {output_path: content}
        if not config_path.exists():
            contents[config_path] = text
        write_files(contents)
    except (OSError, ValueError):
        # Parser exceptions can contain input literals; never echo credentials.
        print("Generation failed; check configuration and output permissions. No secrets displayed.", file=sys.stderr)
        sys.exit(1)

    print(f"  {green('✓')} 생성 완료: {output_path}")
    if include_secrets:
        print(f"  {yellow('주의')}: 시크릿 포함 — git에 커밋하지 마세요.")
    print("  적용 방법:")
    print(f"    helm upgrade --install afterglow helm/afterglow --namespace {args.namespace} --create-namespace \\")
    print(f"        -f {output_path}")


if __name__ == "__main__":
    main()
