#!/usr/bin/env python3
"""afterglow.conf → Helm values.yaml 변환기.

afterglow.conf(및 afterglow.*.conf 오버라이드)을 읽어
helm/afterglow/values-override.yaml (또는 지정 경로)을 생성합니다.

afterglow.conf 옆에 config.gpu.toml(GPU 디바이스 맵 오버라이드)이 있으면
원본 텍스트가 gpu.configToml 값으로 포함되어, 차트 기본값
(helm/afterglow/files/config.gpu.toml) 대신 configmap에 렌더링됩니다.

생성된 파일은 values.yaml 위에 덮어쓰는 오버라이드로 사용합니다:
    helm upgrade --install afterglow helm/afterglow \
        -f helm/afterglow/values-prod.yaml \
        -f <output>

사용법:
    python3 config2helm.py
    python3 config2helm.py --config /path/to/afterglow.conf
    python3 config2helm.py --output helm/afterglow/values-local.yaml
    python3 config2helm.py --no-secrets   # 시크릿 제외 (git 안전)
    python3 config2helm.py --dry-run      # 파일 쓰지 않고 stdout 출력
"""

import argparse
import os
import sys
import tempfile
import tomllib
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()

_USE_COLOR = os.name != "nt" or os.environ.get("FORCE_COLOR")


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _USE_COLOR else text


def green(t: str) -> str:  return _c("32", t)
def yellow(t: str) -> str: return _c("33", t)
def red(t: str) -> str:    return _c("31", t)
def dim(t: str) -> str:    return _c("2",  t)


# ─────────────────────────────────────────────────────────────────────────────
# 설정 로드 (generate_k8s.py 와 동일 로직)
# ─────────────────────────────────────────────────────────────────────────────

def _deep_merge(base: dict, override: dict) -> None:
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


def load_config(config_path: Path) -> dict:
    with open(config_path, "rb") as f:
        cfg = tomllib.load(f)
    for override_path in sorted(config_path.parent.glob(f"{config_path.stem}.*{config_path.suffix}")):
        if override_path.resolve() == config_path.resolve():
            continue
        with open(override_path, "rb") as f:
            _deep_merge(cfg, tomllib.load(f))
        print(f"  {dim(f'오버라이드 로드: {override_path.name}')}")
    return cfg


# ─────────────────────────────────────────────────────────────────────────────
# YAML 렌더링 헬퍼
# ─────────────────────────────────────────────────────────────────────────────

def _yaml_str(v: str, indent: int = 0) -> str:
    """YAML 문자열 값 렌더링. 멀티라인은 block scalar로."""
    prefix = " " * indent
    if "\n" in v:
        lines = v.splitlines()
        body = "\n".join(prefix + "  " + line for line in lines)
        return "|\n" + body
    # 특수문자가 포함된 경우 큰따옴표
    if any(c in v for c in ('"', "'", ":", "#", "{", "}", "[", "]", ",")):
        escaped = v.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return f'"{v}"'


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
    k3s     = cfg.get("k3s", {})
    db      = cfg.get("database", {})
    cors    = cfg.get("cors", {})
    oidc    = cfg.get("gitlab_oidc", {})
    logging_cfg = cfg.get("logging", {})
    mon     = cfg.get("monitoring", {})
    notion  = cfg.get("notion", {})
    smtp    = cfg.get("smtp", {})
    sec     = cfg.get("security", {})

    # ── secrets ────────────────────────────────────────────────────────────
    secrets: dict = {}
    if include_secrets:
        def _sec(val: str, key: str) -> None:
            if val:
                secrets[key] = val

        _sec(os_cfg.get("password", ""),             "osPassword")
        _sec(app.get("secret_key", ""),              "secretKey")
        _sec(oidc.get("client_secret", ""),          "gitlabOidcClientSecret")
        _sec(k3s.get("kubeconfig_encryption_key", ""), "k3sKubeconfigEncryptionKey")
        _sec(db.get("url", ""),                      "databaseUrl")
        _sec(mon.get("prometheus_password", ""),     "prometheusPassword")
        _sec(mon.get("sd_token", ""),                "monitoringSDToken")
        _sec(notion.get("config_encryption_key", ""), "notionConfigEncryptionKey")
        _sec(smtp.get("password", ""),               "smtpPassword")
        _sec(builder.get("ssh_private_key", ""),     "builderSshPrivateKey")
    if secrets:
        out["secrets"] = secrets

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

    # ── gpu ────────────────────────────────────────────────────────────────
    gpu_out: dict = {}
    if "available_visible" in gpu:
        gpu_out["availableVisible"] = gpu["available_visible"]
    if gpu_out:
        out["gpu"] = gpu_out

    # ── services ───────────────────────────────────────────────────────────
    svc_out: dict = {}
    for k in ("magnum", "manila", "zun", "k3s", "swift", "trove", "barbican", "mcp"):
        if k in svc:
            svc_out[k] = svc[k]
    if svc_out:
        out["services"] = svc_out

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

    # ── gitlab_oidc ────────────────────────────────────────────────────────
    oidc_out: dict = {}
    for k in ("enabled", "gitlab_url", "client_id", "idp_id",
              "protocol_id", "redirect_uri", "scopes"):
        if k in oidc:
            oidc_out[_s(k)] = oidc[k]
    # client_secret은 secret으로 이동됨 — 제외
    if oidc_out:
        out["gitlabOidc"] = oidc_out

    # ── smtp ───────────────────────────────────────────────────────────────
    smtp_out: dict = {}
    for k in ("enabled", "host", "port", "username",
              "from_address", "from_name", "use_tls", "timeout_seconds"):
        if k in smtp:
            smtp_out[_s(k)] = smtp[k]
    # password는 secret으로 이동됨 — 제외
    inv = smtp.get("invitation", {})
    if inv:
        smtp_out["invitation"] = {_s(k): v for k, v in inv.items()}
    if smtp_out:
        out["smtp"] = smtp_out

    # ── monitoring ─────────────────────────────────────────────────────────
    mon_out: dict = {}
    for k in ("prometheus_base_url", "prometheus_username",
              "scrape_cidr", "auto_sg_enabled",
              "node_exporter_sg_name", "dcgm_exporter_sg_name",
              "node_exporter_port", "dcgm_exporter_port",
              "libvirt_exporter_port", "gpu_flavor_prefix", "grafana_base_url"):
        if k in mon:
            mon_out[_s(k)] = mon[k]
    # prometheus_password, sd_token은 secret으로 이동됨 — 제외
    dashboards = mon.get("dashboards", {})
    if dashboards:
        mon_out["dashboards"] = {_s(k): v for k, v in dashboards.items()}
    if mon_out:
        out["monitoring"] = mon_out

    # ── notion ─────────────────────────────────────────────────────────────
    if notion:
        out["notion"] = {"enabled": bool(notion.get("config_encryption_key"))}

    # ── logging ────────────────────────────────────────────────────────────
    if logging_cfg:
        out["logging"] = {_s(k): v for k, v in logging_cfg.items()}

    # ── security ───────────────────────────────────────────────────────────
    sec_out: dict = {}
    for k in ("admin_legacy_project_policy", "login_max_attempts",
              "login_lockout_seconds", "login_backoff_base"):
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
            lines.append(f"{prefix}{key}:")
            lines.extend(_render_yaml(value, indent + 1))
        elif isinstance(value, list):
            if not value:
                lines.append(f"{prefix}{key}: []")
            else:
                lines.append(f"{prefix}{key}:")
                for item in value:
                    lines.append(f"{prefix}  - {_yaml_val(item, (indent + 1) * 2)}")
        elif isinstance(value, str) and "\n" in value:
            lines.append(f"{prefix}{key}: |")
            for ln in value.splitlines():
                lines.append(f"{prefix}  {ln}")
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


# ─────────────────────────────────────────────────────────────────────────────
# 진입점
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="afterglow.conf → Helm values.yaml 변환기"
    )
    parser.add_argument(
        "--config", type=Path,
        default=SCRIPT_DIR / "afterglow.conf",
        help="afterglow.conf 경로 (기본값: ./afterglow.conf)",
    )
    parser.add_argument(
        "--output", type=Path,
        default=SCRIPT_DIR / "helm" / "afterglow" / "values-local.yaml",
        help="출력 파일 경로 (기본값: helm/afterglow/values-local.yaml)",
    )
    parser.add_argument(
        "--no-secrets", action="store_true",
        help="시크릿 값 제외 (git 커밋 안전 버전)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="파일을 쓰지 않고 stdout 출력",
    )
    args = parser.parse_args()

    config_path = args.config.resolve()
    if config_path.name != "afterglow.conf" or not config_path.is_file():
        print(f"{red('오류')}: afterglow.conf을(를) 찾을 수 없습니다: {config_path}",
              file=sys.stderr)
        sys.exit(1)

    print(f"  설정 로드: {dim(str(config_path))}")
    cfg = load_config(config_path)
    print(f"  {green('✓')} 설정 로드 완료")

    include_secrets = not args.no_secrets
    values = convert(cfg, include_secrets=include_secrets)

    # config.gpu.toml(GPU 디바이스 맵 오버라이드)이 있으면 원본 텍스트를
    # gpu.configToml로 주입 — 차트가 기본값(files/config.gpu.toml) 대신 사용한다.
    gpu_toml_path = config_path.parent / "config.gpu.toml"
    if gpu_toml_path.exists():
        values.setdefault("gpu", {})["configToml"] = gpu_toml_path.read_text(
            encoding="utf-8"
        )
        print(f"  {green('✓')} GPU 디바이스 맵 포함: {dim(str(gpu_toml_path))}")

    header_lines = [
        "afterglow.conf → Helm values 자동 변환 파일",
        "생성: python3 config2helm.py",
        "",
        "사용법:",
        "  helm upgrade --install afterglow helm/afterglow \\",
        "    -f helm/afterglow/values-prod.yaml \\",
        f"    -f {args.output.name}",
    ]
    if not include_secrets:
        header_lines += ["", "⚠ --no-secrets 옵션: 시크릿 값이 제외되었습니다."]
    else:
        header_lines += ["", "⚠ 시크릿 값 포함 — git에 커밋하지 마세요!"]

    content = render_yaml(values, comment_header="\n".join(header_lines))

    if args.dry_run:
        print(content)
        return

    output_path = args.output.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp = tempfile.mkstemp(dir=output_path.parent, prefix=".config2helm_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, output_path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

    print(f"  {green('✓')} 생성 완료: {output_path}")
    print()
    if include_secrets:
        print(f"  {yellow('주의')}: 시크릿 값이 평문으로 포함되어 있습니다.")
        print(f"        git에 커밋하지 마세요. (.gitignore에 추가 권장)")
    print()
    print("  적용 방법:")
    print(f"    helm upgrade --install afterglow helm/afterglow \\")
    print(f"        -f helm/afterglow/values-prod.yaml \\")
    print(f"        -f {output_path}")


if __name__ == "__main__":
    main()
