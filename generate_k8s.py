#!/usr/bin/env python3
"""afterglow.conf → K8s configmap/secret/ingress/grafana 매니페스트 변환기.

afterglow.conf(및 오버라이드)을 읽어
deploy/k8s/{secret.yaml, configmap.yaml, ingress.yaml, grafana-deployment.yaml}을 자동 생성합니다.
`--namespace`는 namespace만 선택합니다. 환경별 domain 프로필은
`--override deploy/afterglow-prod.conf` 또는 dev.conf로 명시적으로 선택합니다.

grafana-deployment.yaml 은 anonymous 인증으로 동작하는 Grafana Deployment 매니페스트로,
iframe 임베드를 위해 GF_SECURITY_ALLOW_EMBEDDING 이 활성화되어 있습니다.
Afterglow 앱 인증이 실질적인 접근 게이트 역할을 합니다.

ingress.yaml 은 frontend/public API origin의 기존 /api, /.well-known, frontend fallback과
별도 API host의 /v1(Lumen)을 보존합니다. services.mcp=true이면 mcp.public_url의 host에
정확한 resource 경로 및 OAuth descendants와 /.well-known을 backend로 전달합니다.
미설정 resource는 public_api_base + /api/v1/mcp이며 rewrite/redirect는 사용하지 않습니다.
루트 resource는 전용 host에서 Exact /, Prefix /oauth, Prefix /.well-known만 노출합니다.
web/API host와 공유하는 루트 resource는 생성 전에 거부합니다. 정적 overlay 대신 생성한
ingress.yaml을 적용해야 설정된 MCP 경로가 반영됩니다.

사용법:
    python3 generate_k8s.py --config /path/to/afterglow.conf
    python3 generate_k8s.py --output-dir /path/to/deploy/k8s
    python3 generate_k8s.py --config afterglow.conf \
        --override deploy/afterglow-dev.conf \
        --namespace afterglow-dev

Python 3.11+ 표준 라이브러리만 사용합니다.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID

from generation_config import config_override_paths, load_config, merge_config, prepare_config, write_files

# ─────────────────────────────────────────────────────────────────────────────
# 상수
# ─────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent.resolve()
# 네임스페이스 상대 이름 사용 — 동일 네임스페이스 내 서비스이므로
# prod(afterglow)·dev(afterglow-dev) 양쪽에서 자동 해석됨
REDIS_K8S = "redis://redis:6379/0"
REDIS_SENTINEL_K8S = "redis-sentinel:26379"
REDIS_SENTINEL_MASTER = "mymaster"

# ANSI 색상 (Windows에서는 비활성화)
_USE_COLOR = os.name != "nt" or os.environ.get("FORCE_COLOR")


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _USE_COLOR else text


def green(t: str) -> str:
    return _c("32", t)


def yellow(t: str) -> str:
    return _c("33", t)


def red(t: str) -> str:
    return _c("31", t)


def dim(t: str) -> str:
    return _c("2", t)


# ─────────────────────────────────────────────────────────────────────────────
# 설정 로드
# ─────────────────────────────────────────────────────────────────────────────




def default_config_path() -> Path:
    """기본 설정 파일 경로."""
    return Path.cwd() / "afterglow.conf"


# ─────────────────────────────────────────────────────────────────────────────
# YAML 헬퍼
# ─────────────────────────────────────────────────────────────────────────────


def _yaml_str(v: str) -> str:
    """Quote a scalar, including controls and multiline values, as valid YAML."""
    return json.dumps(v, ensure_ascii=False)


def _yaml_block_scalar(v: str) -> str:
    """멀티라인 YAML block scalar (|) 렌더링 — SSH 개인키 등에 사용.

    단일 라인이면 _yaml_str로 위임. 빈 값이면 빈 문자열 반환.
    """
    if not v:
        return '""'
    if "\n" not in v:
        return _yaml_str(v)
    lines = v.splitlines()
    body = "\n".join("    " + line for line in lines)
    return "|\n" + body


# ─────────────────────────────────────────────────────────────────────────────
# TOML 헬퍼 (렌더링용)
# ─────────────────────────────────────────────────────────────────────────────


def _toml_str(v: str) -> str:
    """TOML 문자열 값 이스케이프."""
    return json.dumps(v, ensure_ascii=False)


def _toml_bool(v: bool) -> str:
    return "true" if v else "false"


def _toml_list_str(items: list[str]) -> str:
    return "[" + ", ".join(_toml_str(i) for i in items) + "]"


def _toml_val(v) -> str:
    """Python 값을 TOML 값 문자열로 변환."""
    if isinstance(v, bool):
        return _toml_bool(v)
    if isinstance(v, str):
        return _toml_str(v)
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        if all(isinstance(i, str) for i in v):
            return _toml_list_str(v)
        return str(v)
    return _toml_str(str(v))


_AUTH_PROVIDER_FIELDS = frozenset({
    "name", "kind", "enabled", "issuer_url", "authorization_url", "token_url", "api_url",
    "client_id", "client_secret", "scopes", "keystone_idp_id", "keystone_protocol_id",
    "federation_token_type", "token_endpoint_auth_method", "organization",
})


def _auth_config(cfg: dict) -> dict:
    """Reject unknown structures before projecting secrets; runtime validates semantics."""
    invalid = ValueError("Invalid auth configuration; check registry fields and selection references")
    auth = cfg.get("auth", {})
    if not isinstance(auth, dict) or set(auth) - {
        "providers", "default", "domain", "public_signup_enabled", "signup_email_domains",
        "organization_creation_enabled", "max_organizations_per_user",
    }:
        raise invalid
    if "public_signup_enabled" in auth and not isinstance(auth["public_signup_enabled"], bool):
        raise invalid
    if "organization_creation_enabled" in auth and not isinstance(auth["organization_creation_enabled"], bool):
        raise invalid
    maximum = auth.get("max_organizations_per_user", 10)
    if type(maximum) is not int or maximum < 0:
        raise invalid
    signup_domains = auth.get("signup_email_domains", [])
    if not isinstance(signup_domains, list) or any(not isinstance(host, str) for host in signup_domains):
        raise invalid
    providers = auth.get("providers", {})
    domains = auth.get("domain", {})
    if not isinstance(providers, dict) or not isinstance(domains, dict):
        raise invalid
    for key, provider in providers.items():
        if (
            not isinstance(key, str) or len(key) > 32 or re.fullmatch(r"[a-z](?:[a-z0-9]|_[a-z0-9])*", key) is None
            or not isinstance(provider, dict) or set(provider) - _AUTH_PROVIDER_FIELDS
        ):
            raise invalid
        for field, value in provider.items():
            if field == "enabled":
                valid = isinstance(value, bool)
            elif field == "scopes":
                valid = isinstance(value, list) and all(isinstance(item, str) for item in value)
            elif field == "organization":
                valid = (
                    provider.get("kind") == "oidc" and isinstance(value, dict)
                    and set(value) == {"id", "name", "manager_subjects"}
                    and all(isinstance(value.get(key), str) and value[key].strip() for key in ("id", "name"))
                    and isinstance(value.get("manager_subjects"), list) and bool(value["manager_subjects"])
                    and all(isinstance(subject, str) and subject.strip() for subject in value["manager_subjects"])
                )
            else:
                valid = isinstance(value, str)
            if not valid:
                raise invalid
    for domain_id in domains:
        if (
            not isinstance(domain_id, str) or not 1 <= len(domain_id) <= 64
            or any(char.isspace() or ord(char) < 32 for char in domain_id)
        ):
            raise invalid
    for methods in (auth.get("default", {}), *domains.values()):
        if not isinstance(methods, dict) or set(methods) - {"allow_providers", "auto_join_email_domains"}:
            raise invalid
        selected = methods.get("allow_providers", [])
        auto_join = methods.get("auto_join_email_domains", {})
        if not isinstance(selected, list) or not isinstance(auto_join, dict):
            raise invalid
        if any(
            not isinstance(hosts, list) or any(not isinstance(host, str) for host in hosts)
            for hosts in auto_join.values()
        ):
            raise invalid
        for selectors in (selected, auto_join):
            for key in selectors:
                if not isinstance(key, str):
                    raise invalid
                if key in providers:
                    continue
                try:
                    if str(UUID(key)) == key:
                        continue
                except ValueError:
                    pass
                raise invalid
    return auth


def auth_secret_env(cfg: dict) -> dict[str, str]:
    """Return raw provider credentials only as nested Settings environment entries."""
    return {
        f"AUTH__PROVIDERS__{key.upper()}__CLIENT_SECRET": provider["client_secret"]
        for key, provider in _auth_config(cfg).get("providers", {}).items()
        if provider.get("client_secret")
    }


def render_auth_toml(cfg: dict) -> str:
    """Render standalone auth TOML preserving every configured nonsecret field."""
    auth = _auth_config(cfg)
    if not auth:
        return ""
    lines = ["[auth]"]
    for field in (
        "public_signup_enabled", "signup_email_domains", "organization_creation_enabled", "max_organizations_per_user",
    ):
        if field in auth:
            lines.append(f"{field} = {_toml_val(auth[field])}")
    for key, provider in auth.get("providers", {}).items():
        lines.extend(("", f"[auth.providers.{_toml_str(key)}]"))
        for field, value in provider.items():
            if field not in {"client_secret", "organization"}:
                lines.append(f"{field} = {_toml_val(value)}")
        if "organization" in provider:
            lines.extend(("", f"[auth.providers.{_toml_str(key)}.organization]"))
            for field, value in provider["organization"].items():
                lines.append(f"{field} = {_toml_val(value)}")
    if "default" in auth:
        lines.extend(("", "[auth.default]"))
        if "allow_providers" in auth["default"]:
            lines.append(f"allow_providers = {_toml_list_str(auth['default']['allow_providers'])}")
        if "auto_join_email_domains" in auth["default"]:
            entries = ", ".join(
                f"{_toml_str(key)} = {_toml_list_str(hosts)}"
                for key, hosts in auth["default"]["auto_join_email_domains"].items()
            )
            lines.append(f"auto_join_email_domains = {{{entries}}}")
    for domain_id, methods in auth.get("domain", {}).items():
        lines.extend(("", f"[auth.domain.{_toml_str(domain_id)}]"))
        if "allow_providers" in methods:
            lines.append(f"allow_providers = {_toml_list_str(methods['allow_providers'])}")
        if "auto_join_email_domains" in methods:
            entries = ", ".join(
                f"{_toml_str(key)} = {_toml_list_str(hosts)}"
                for key, hosts in methods["auto_join_email_domains"].items()
            )
            lines.append(f"auto_join_email_domains = {{{entries}}}")
    return "\n".join(lines) + "\n"


def _origin_of(value: object) -> str:
    """Return normalized URL origin, or empty string for invalid/missing values."""
    if not isinstance(value, str):
        return ""
    raw = value.strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return ""
    try:
        port = parsed.port
    except ValueError:
        return ""
    host = parsed.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    port_part = f":{port}" if port is not None else ""
    return f"{parsed.scheme}://{host}{port_part}"


def _first_cors_origin(cors: dict) -> str:
    origins_raw = cors.get("origins", "http://localhost:3080")
    if not isinstance(origins_raw, str):
        return "http://localhost:3080"
    first = origins_raw.split(",", 1)[0].strip()
    return first or "http://localhost:3080"


def _configured_cors_origin(cors: dict) -> str:
    if "origins" not in cors:
        return ""
    origins_raw = cors.get("origins")
    if not isinstance(origins_raw, str):
        return ""
    return _origin_of(origins_raw.split(",", 1)[0])


def _port_from(value: object, fallback: int) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError):
        return fallback
    return port if port > 0 else fallback


def _derive_public_api_base_for_k8s(cfg: dict) -> str:
    """Derive browser-reachable API origin for K8s env and inline afterglow.conf."""
    app = cfg.get("app", {})
    cors = cfg.get("cors", {})
    public_api_origin = _origin_of(app.get("public_api_base"))
    if public_api_origin:
        return public_api_origin
    frontend_origin = _origin_of(app.get("frontend_base_url"))
    if frontend_origin:
        return frontend_origin
    cors_origin = _configured_cors_origin(cors)
    if cors_origin:
        return cors_origin
    return f"http://localhost:{_port_from(app.get('backend_port'), 8000)}"


# ─────────────────────────────────────────────────────────────────────────────
# secret.yaml 렌더링
# ─────────────────────────────────────────────────────────────────────────────


def _validate_k8s_secret_key(secret_key: str) -> None:
    """K8s 배포용 SECRET_KEY가 운영 fail-closed 조건을 만족하는지 확인."""
    if not secret_key:
        raise ValueError("K8s secret.yaml 생성을 위해 [app].secret_key 또는 SECRET_KEY 값을 설정해야 합니다.")
    if secret_key == "change-me-in-production":
        raise ValueError("K8s secret.yaml에는 기본 SECRET_KEY(change-me-in-production)를 사용할 수 없습니다.")
    if len(secret_key) < 32:
        raise ValueError("K8s secret.yaml의 SECRET_KEY는 32자 이상이어야 합니다.")


def render_secret(cfg: dict, namespace: str = "afterglow") -> str:
    """secret.yaml 생성: 비밀 값만 추출."""
    os_cfg = cfg.get("openstack", {})
    app = cfg.get("app", {})
    k3s = cfg.get("k3s", {})
    ceph = cfg.get("ceph", {})
    db = cfg.get("database", {})
    mon = cfg.get("monitoring", {})
    notion = cfg.get("notion", {})
    builder = cfg.get("builder", {})
    mcp = cfg.get("mcp", {})

    secret_key = app.get("secret_key", "")
    _validate_k8s_secret_key(secret_key)

    lines = [
        "apiVersion: v1",
        "kind: Secret",
        "metadata:",
        "  name: afterglow-secrets",
        f"  namespace: {namespace}",
        "type: Opaque",
        "stringData:",
        "  # OpenStack 관리자 계정 비밀번호",
        f"  OS_PASSWORD: {_yaml_str(os_cfg.get('password', ''))}",
        "",
        "  # FastAPI 세션/JWT 서명용 시크릿 키",
        '  # 생성: python3 -c "import secrets; print(secrets.token_hex(32))"',
        f"  SECRET_KEY: {_yaml_str(secret_key)}",
    ]

    enc_key = k3s.get("kubeconfig_encryption_key", "")
    token = k3s.get("gpu_admission_token", "")
    lines.extend(
        [
            "",
            "  # k3s kubeconfig 암호화 키 및 GPU admission 인증 토큰",
            '  # 생성: python3 -c "import secrets; print(secrets.token_hex(32))"',
            f"  K3S_KUBECONFIG_ENCRYPTION_KEY: {_yaml_str(enc_key)}",
            f"  K3S_GPU_ADMISSION_TOKEN: {_yaml_str(token)}",
        ]
    )

    db_url = db.get("url", "")
    lines.extend(
        [
            "",
            "  # 애플리케이션 데이터베이스 연결 URL",
            f"  DATABASE_URL: {_yaml_str(db_url)}",
        ]
    )

    prometheus_password = mon.get("prometheus_password", "")
    lines.extend(
        [
            "",
            "  # Prometheus basic auth 비밀번호 (미사용 시 빈 문자열)",
            f"  PROMETHEUS_PASSWORD: {_yaml_str(prometheus_password)}",
        ]
    )

    lines.extend(
        [
            "",
            "  # Lumen 내부 MCP bridge workload credential",
            f"  LUMEN_MCP_SERVICE_TOKEN: {_yaml_str(mcp.get('lumen_service_token', ''))}",
        ]
    )

    sd_token = mon.get("sd_token", "")
    if sd_token:
        lines.extend(
            [
                "",
                "  # Prometheus SD 엔드포인트 인증 토큰",
                f"  MONITORING_SD_TOKEN: {_yaml_str(sd_token)}",
            ]
        )

    traffic = cfg.get("traffic_analytics", {})
    lines.extend([
        f"  MONITORING_INFRASTRUCTURE_TOPOLOGY_OBSERVERS: {_yaml_str(json.dumps(mon.get('infrastructure_topology_observers', [])))}",
        f"  MONITORING_INFRASTRUCTURE_FABRIC__TARGETS: {_yaml_str(json.dumps(mon.get('infrastructure_fabric', {}).get('targets', [])))}",
        f"  TRAFFIC_ANALYTICS__HMAC_KEY: {_yaml_str(traffic.get('hmac_key', ''))}",
        f"  TRAFFIC_ANALYTICS__FRONTEND_INGEST_KEY: {_yaml_str(traffic.get('frontend_ingest_key', ''))}",
        f"  TRAFFIC_ANALYTICS_INGEST_KEY: {_yaml_str(traffic.get('frontend_ingest_key', ''))}",
    ])

    notion_enc_key = notion.get("config_encryption_key", "")
    if notion_enc_key:
        lines.extend(
            [
                "",
                "  # Notion 설정 암호화 키",
                f"  NOTION_CONFIG_ENCRYPTION_KEY: {_yaml_str(notion_enc_key)}",
            ]
        )

    smtp = cfg.get("smtp", {})
    smtp_password = smtp.get("password", "")
    if smtp_password:
        lines.extend(
            [
                "",
                "  # SMTP 이메일 서버 인증 비밀번호",
                f"  SMTP_PASSWORD: {_yaml_str(smtp_password)}",
            ]
        )

    ssh_private_key = builder.get("ssh_private_key", "")
    builder_key_value = _yaml_block_scalar(ssh_private_key) if ssh_private_key else _yaml_str("")
    lines.extend(
        [
            "",
            "  # Builder VM SSH 개인키 — /etc/afterglow/ssh/builder.key 로 볼륨 마운트됨",
            f"  BUILDER_SSH_PRIVATE_KEY: {builder_key_value}",
        ]
    )
    rbd_keyring = ceph.get("rbd_keyring", "")
    lines.extend(
        [
            "",
            "  # 관리자 볼륨 삭제 복구용 Ceph RBD 제한 keyring",
            f"  CEPH_RBD_KEYRING: {_yaml_block_scalar(rbd_keyring)}",
        ]
    )
    for key, value in auth_secret_env(cfg).items():
        lines.append(f"  {key}: {_yaml_str(value)}")

    lines.append("")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# afterglow.conf 인라인 렌더링 (비밀 제외)
# ─────────────────────────────────────────────────────────────────────────────


def _render_toml_for_k8s(cfg: dict, namespace: str | None = None) -> str:
    """afterglow.conf 전체를 렌더링하되 비밀 값은 주석으로 대체."""
    os_cfg = cfg.get("openstack", {})
    ceph = cfg.get("ceph", {})
    app = cfg.get("app", {})
    cache = cfg.get("cache", {})
    sess = cfg.get("session", {})
    nova = cfg.get("nova", {})
    gpu = cfg.get("gpu", {})
    svc = cfg.get("services", {})
    cloud_shell = cfg.get("cloud_shell", {})
    instance_health = cfg.get("instance_health", {})
    builder = cfg.get("builder", {})
    palimpsest = cfg.get("palimpsest", {})
    mcp = cfg.get("mcp", {})
    db = cfg.get("database", {})
    cors = cfg.get("cors", {})
    public_api_base = _derive_public_api_base_for_k8s(cfg)
    logging_cfg = cfg.get("logging", {})
    mon = cfg.get("monitoring", {})
    notion = cfg.get("notion", {})
    smtp = cfg.get("smtp", {})
    worker_runtime = cfg.get("worker_runtime", {})

    lines = [
        "# Afterglow 통합 설정 파일",
        "# 비밀 값은 secret.yaml의 환경변수로 주입됩니다.",
        "",
    ]

    # [DEFAULT]
    lines.append("[DEFAULT]")
    lines.append(f"debug = {_toml_bool(cfg.get('DEFAULT', {}).get('debug', False))}")
    lines.append("")

    # [openstack]
    lines.append("[openstack]")
    lines.append(f"auth_url = {_toml_str(os_cfg.get('auth_url', ''))}")
    lines.append(f"project_name = {_toml_str(os_cfg.get('project_name', 'admin'))}")
    lines.append(f"project_domain_name = {_toml_str(os_cfg.get('project_domain_name', 'Default'))}")
    lines.append(f"user_domain_name = {_toml_str(os_cfg.get('user_domain_name', 'Default'))}")
    lines.append(f"region_name = {_toml_str(os_cfg.get('region_name', 'RegionOne'))}")
    lines.append(f"username = {_toml_str(os_cfg.get('username', 'admin'))}")
    lines.append("# password는 secret.yaml의 OS_PASSWORD 환경변수로 주입됩니다")
    if os_cfg.get("insecure"):
        lines.append("insecure = true")
    if os_cfg.get("cacert"):
        lines.append(f"cacert = {_toml_str(os_cfg['cacert'])}")
    lines.append("")
    lines.append("")
    lines.append("# Ceph 모니터 (cloud-init CephFS 마운트용, 콤마 구분)")
    lines.append(f"ceph_monitors = {_toml_str(os_cfg.get('ceph_monitors', ''))}")
    lines.append("")
    lines.append("")
    lines.append("# Swift 설정")
    lines.append(f"swift_endpoint = {_toml_str(os_cfg.get('swift_endpoint', ''))}")
    lines.append(f"swift_upload_timeout = {os_cfg.get('swift_upload_timeout', 600)}")
    lines.append(f"trash_retention_days = {os_cfg.get('trash_retention_days', 30)}")
    lines.append("")
    lines.append("# Manila NFS 설정")
    lines.append(f"manila_nfs_root_squash = {_toml_bool(os_cfg.get('manila_nfs_root_squash', True))}")
    lines.append(f"manila_nfs_sec_flavor = {_toml_str(os_cfg.get('manila_nfs_sec_flavor', 'sys'))}")
    lines.append(f"manila_cephx_key_timeout_seconds = {os_cfg.get('manila_cephx_key_timeout_seconds', 300)}")
    lines.append(f"interface = {_toml_str(os_cfg.get('interface', 'internal'))}")
    lines.append("")
    # [ceph]
    lines.append("[ceph]")
    lines.append(f"rbd_conf_path = {_toml_str(ceph.get('rbd_conf_path', ''))}")
    lines.append(f"rbd_keyring_path = {_toml_str(ceph.get('rbd_keyring_path', ''))}")
    lines.append(f"rbd_client_name = {_toml_str(ceph.get('rbd_client_name', 'client.afterglow-rbd'))}")
    lines.append(f"rbd_cluster_fsid = {_toml_str(ceph.get('rbd_cluster_fsid', ''))}")
    lines.append(f"rbd_command_timeout_seconds = {ceph.get('rbd_command_timeout_seconds', 30)}")
    lines.append("[ceph.rbd_volume_pools]")
    for backend, pool in sorted((ceph.get("rbd_volume_pools", {}) or {}).items()):
        lines.append(f"{_toml_str(str(backend))} = {_toml_str(str(pool))}")
    lines.append("")

    # [app]
    lines.append("[app]")
    lines.append(f"backend_port = {app.get('backend_port', 8000)}")
    lines.append(f"frontend_port = {app.get('frontend_port', 3080)}")
    lines.append("# secret_key는 secret.yaml의 SECRET_KEY 환경변수로 주입됩니다")
    lines.append("")
    lines.append("# 사이트 표시 이름 및 설명")
    lines.append(f"site_name = {_toml_str(app.get('site_name', 'afterglow'))}")
    lines.append(f"site_description = {_toml_str(app.get('site_description', ''))}")
    lines.append("")
    lines.append("# 로고 및 파비콘 경로 (frontend/static/ 기준)")
    lines.append(f"logo_path = {_toml_str(app.get('logo_path', '/afterglow-logo.svg'))}")
    lines.append(f"logo_dark_path = {_toml_str(app.get('logo_dark_path', '/afterglow-logo.svg'))}")
    lines.append(f"logo_light_path = {_toml_str(app.get('logo_light_path', '/afterglow-logo.svg'))}")
    lines.append(f"favicon_path = {_toml_str(app.get('favicon_path', '/favicon.svg'))}")
    lines.append("")
    lines.append("# 프론트엔드 대시보드 자동 새로고침 간격 (밀리초)")
    lines.append(f"refresh_interval_ms = {app.get('refresh_interval_ms', 5000)}")
    lines.append("")
    lines.append("# 초대 이메일 링크 생성에 사용하는 프론트엔드 베이스 URL")
    lines.append(f"frontend_base_url = {_toml_str(app.get('frontend_base_url', ''))}")
    lines.append(f"public_api_base = {_toml_str(public_api_base)}")
    lines.append("")
    lines.append("# 리버스 프록시 신뢰 CIDR — X-Forwarded-For / X-Real-IP 를 신뢰할 주소 범위")
    lines.append(f"trusted_proxies = {_toml_str(app.get('trusted_proxies', '127.0.0.1/32,::1/128'))}")
    lines.append("")

    # [logging] (선택)
    if logging_cfg:
        lines.append("[logging]")
        for k, v in logging_cfg.items():
            lines.append(f"{k} = {_toml_val(v)}")
        lines.append("")

    # [cache]
    lines.append("[cache]")
    lines.append(f"redis_url = {_toml_str(REDIS_K8S)}")
    lines.append("")
    lines.append("# Redis Sentinel HA — K8s 배포 시 자동 활성화")
    lines.append("sentinel_enabled = true")
    lines.append(f"sentinel_master_name = {_toml_str(REDIS_SENTINEL_MASTER)}")
    lines.append(f"sentinel_hosts = {_toml_str(REDIS_SENTINEL_K8S)}")
    lines.append("# TTL 티어 (초)")
    lines.append(f"ttl_fast = {cache.get('ttl_fast', 15)}      # 인스턴스, 볼륨, 플로팅IP")
    lines.append(f"ttl_normal = {cache.get('ttl_normal', 30)}    # 네트워크, 라우터, 대시보드")
    lines.append(f"ttl_slow = {cache.get('ttl_slow', 60)}      # 키페어, 보안그룹")
    lines.append(f"ttl_static = {cache.get('ttl_static', 300)}   # 이미지, 플레이버, 토큰 검증")
    lines.append(f"default_ttl_seconds = {cache.get('default_ttl_seconds', 30)}")
    lines.append(f"backend = {_toml_str(cache.get('backend', 'redis'))}")
    lines.append(f"dynamic_threshold_low = {cache.get('dynamic_threshold_low', 5)}")
    lines.append(f"dynamic_threshold_high = {cache.get('dynamic_threshold_high', 20)}")
    lines.append(f"ttl_identity_stable = {cache.get('ttl_identity_stable', 86400)}")
    lines.append(f"ttl_catalog_slow = {cache.get('ttl_catalog_slow', 900)}")
    lines.append(f"ttl_project_meta = {cache.get('ttl_project_meta', 300)}")
    lines.append(f"ttl_operational_live = {cache.get('ttl_operational_live', 30)}")
    lines.append(f"ttl_admin_overview = {cache.get('ttl_admin_overview', 60)}")
    lines.append(f"ttl_auth_token = {cache.get('ttl_auth_token', 60)}")
    lines.append("")

    # [session]
    lines.append("[session]")
    lines.append(f"timeout_seconds = {sess.get('timeout_seconds', 3600)}")
    lines.append(f"jwt_access_ttl = {sess.get('jwt_access_ttl', 900)}")
    lines.append(f"jwt_refresh_ttl = {sess.get('jwt_refresh_ttl', 604800)}")
    lines.append(f"token_ip_binding_mode = {_toml_str(sess.get('token_ip_binding_mode', 'subnet'))}")
    lines.append("")

    # [nova]
    lines.append("[nova]")
    lines.append(f"boot_volume_size_gb = {nova.get('boot_volume_size_gb', 20)}")
    lines.append(f"upper_volume_size_gb = {nova.get('upper_volume_size_gb', 50)}")
    lines.append("")

    # [builder] (선택)
    if builder:
        lines.append("[builder]")
        if "ssh_user" in builder:
            lines.append(f"ssh_user = {_toml_str(builder['ssh_user'])}")
        if "ssh_key_path" in builder:
            lines.append(f"ssh_key_path = {_toml_str(builder['ssh_key_path'])}")
        if "ssh_host" in builder:
            lines.append(f"ssh_host = {_toml_str(builder['ssh_host'])}")
        if "build_timeout" in builder:
            lines.append(f"build_timeout = {builder['build_timeout']}")
        if "layer_share_size_gb" in builder:
            lines.append(f"layer_share_size_gb = {builder['layer_share_size_gb']}")
        lines.append("")

    # [palimpsest] (선택) — 로컬 KVM 런타임. Hub 저장소는 별도 서비스가 소유한다.
    if palimpsest:
        lines.append("[palimpsest]")
        for key in ("kvm_uri", "kvm_layer_root", "kvm_state_dir"):
            if key in palimpsest:
                lines.append(f"{key} = {_toml_str(palimpsest[key])}")
        lines.append("")

    # [gpu] (디바이스 맵은 config.gpu.toml로 분리)
    lines.append("[gpu]")
    if "available_visible" in gpu:
        lines.append(f"available_visible = {_toml_bool(gpu['available_visible'])}")
    lines.append("# GPU 디바이스 맵은 config.gpu.toml에서 관리됩니다")
    lines.append("")

    # [services]
    lines.append("[services]")
    for svc_name in (
        "magnum",
        "manila",
        "zun",
        "k3s",
        "swift",
        "trove",
        "barbican",
        "waygate",
        "palimpsest",
        "chat",
        "mcp",
        "cloud_shell",
    ):
        if svc_name in svc:
            lines.append(f"{svc_name} = {_toml_bool(svc[svc_name])}")
    for endpoint_name in (
        "waygate_internal_url",
        "drover_internal_url",
        "lumen_internal_url",
        "palimpsest_internal_url",
    ):
        if endpoint_name in svc:
            lines.append(f"{endpoint_name} = {_toml_str(svc[endpoint_name])}")
    lines.append("")
    lines.append("[cloud_shell]")
    for key, default in (
        ("service_project_id", ""),
        ("image", "ghcr.io/openstack-afterglow/openstack-client:slim"),
        ("image_pull_policy", ""),
        ("registry_id", ""),
        ("network_id", ""),
        ("security_group", "default"),
        ("auth_url", ""),
        ("interface", "public"),
        ("volume_type", ""),
        ("home_size_gib", 5),
        ("cpu", 1.0),
        ("memory_mib", 1024),
        ("idle_timeout_seconds", 1200),
        ("max_session_seconds", 3600),
        ("ticket_ttl_seconds", 60),
        ("reconcile_interval_seconds", 60),
        ("zun_websocket_origin", ""),
    ):
        lines.append(f"{key} = {_toml_val(cloud_shell.get(key, default))}")
    lines.append("")
    if mcp:
        lines.append("[mcp]")
        for key in ("public_url", "oauth_consent_url"):
            if key in mcp:
                lines.append(f"{key} = {_toml_str(mcp[key])}")
        if "lumen_service_token" in mcp:
            lines.append("# lumen_service_token is injected as LUMEN_MCP_SERVICE_TOKEN from secret.yaml")
        for key in (
            "authorization_ticket_ttl_seconds",
            "access_token_ttl_seconds",
            "default_grant_ttl_days",
            "max_grant_ttl_days",
            "max_personal_tokens",
            "max_delegated_grants",
            "request_max_bytes",
            "read_result_max_bytes",
            "mutation_result_max_bytes",
            "default_page_size",
            "max_page_size",
            "concurrent_calls_per_grant",
            "read_rate_per_minute",
            "mutation_rate_per_minute",
        ):
            if key in mcp:
                lines.append(f"{key} = {int(mcp[key])}")
        lines.append("")

    # [instance_health]
    lines.append("[instance_health]")
    lines.append(f"callback_base_url = {_toml_str(instance_health.get('callback_base_url', ''))}")
    lines.append("")
    # [k3s]
    lines.append("[k3s]")
    lines.append("# kubeconfig_encryption_key is injected as K3S_KUBECONFIG_ENCRYPTION_KEY from secret.yaml")
    lines.append("# gpu_admission_token is injected as K3S_GPU_ADMISSION_TOKEN from secret.yaml")
    lines.append("")
    # [worker_runtime] (non-secret runtime manager config)
    wr_workers = worker_runtime.get("workers", {})
    wr_notion = wr_workers.get("notion_worker", {})
    wr_docker = worker_runtime.get("docker", {})
    wr_k8s = worker_runtime.get("kubernetes", {})
    lines.append("[worker_runtime]")
    lines.append(f"mode = {_toml_str(worker_runtime.get('mode', 'static'))}")
    lines.append(f"reconcile_interval = {worker_runtime.get('reconcile_interval', 30)}")
    lines.append(f"fail_closed = {_toml_bool(worker_runtime.get('fail_closed', True))}")
    lines.append("")
    lines.append("[worker_runtime.workers.notion_worker]")
    lines.append(f"enabled = {_toml_bool(wr_notion.get('enabled', True))}")
    lines.append(f"desired_replicas = {wr_notion.get('desired_replicas', 1)}")
    lines.append(f"max_replicas = {wr_notion.get('max_replicas', 1)}")
    lines.append(f"module = {_toml_str(wr_notion.get('module', 'app.notion_worker'))}")
    lines.append("")
    lines.append("[worker_runtime.docker]")
    lines.append(f"socket_path = {_toml_str(wr_docker.get('socket_path', ''))}")
    lines.append(f"image = {_toml_str(wr_docker.get('image', ''))}")
    lines.append(f"network = {_toml_str(wr_docker.get('network', ''))}")
    lines.append(f"config_mount = {_toml_str(wr_docker.get('config_mount', '/app/afterglow.conf'))}")
    lines.append(f"config_host_path = {_toml_str(wr_docker.get('config_host_path', ''))}")
    lines.append(f"gpu_config_mount = {_toml_str(wr_docker.get('gpu_config_mount', '/app/config.gpu.toml'))}")
    lines.append(f"gpu_config_host_path = {_toml_str(wr_docker.get('gpu_config_host_path', ''))}")
    lines.append(f"logs_mount = {_toml_str(wr_docker.get('logs_mount', '/app/logs'))}")
    lines.append(f"logs_host_path = {_toml_str(wr_docker.get('logs_host_path', ''))}")
    lines.append(
        f"env_allowlist = {_toml_str(wr_docker.get('env_allowlist', 'AFTERGLOW_ENV,AFTERGLOW_ALLOW_INSECURE,SECRET_KEY,OS_PASSWORD,DATABASE_URL,K3S_KUBECONFIG_ENCRYPTION_KEY,K3S_GPU_ADMISSION_TOKEN,PROMETHEUS_PASSWORD,NOTION_CONFIG_ENCRYPTION_KEY'))}"
    )
    lines.append("")
    lines.append("[worker_runtime.kubernetes]")
    lines.append(f"namespace = {_toml_str(namespace or wr_k8s.get('namespace', 'afterglow'))}")
    lines.append(
        f"service_account_token_path = {_toml_str(wr_k8s.get('service_account_token_path', '/var/run/secrets/kubernetes.io/serviceaccount/token'))}"
    )
    lines.append(
        f"service_account_ca_path = {_toml_str(wr_k8s.get('service_account_ca_path', '/var/run/secrets/kubernetes.io/serviceaccount/ca.crt'))}"
    )
    lines.append(f"manage_deployments = {_toml_bool(wr_k8s.get('manage_deployments', False))}")
    lines.append("")

    # [database] (url은 비밀, 나머지는 포함)
    if db:
        lines.append("[database]")
        lines.append("# url은 secret.yaml의 DATABASE_URL 환경변수로 주입됩니다")
        if "pool_size" in db:
            lines.append(f"pool_size = {db['pool_size']}")
        if "max_overflow" in db:
            lines.append(f"max_overflow = {db['max_overflow']}")
        if "auto_create_tables" in db:
            lines.append(f"auto_create_tables = {_toml_bool(db['auto_create_tables'])}")
        if "connect_timeout" in db:
            lines.append(f"connect_timeout = {db['connect_timeout']}")
        if "pool_timeout" in db:
            lines.append(f"pool_timeout = {db['pool_timeout']}")
        if "unhealthy_seconds" in db:
            lines.append(f"unhealthy_seconds = {db['unhealthy_seconds']}")
        if "db_auto_backup_cron" in db:
            lines.append(f"db_auto_backup_cron = {_toml_str(db['db_auto_backup_cron'])}")
        lines.append("")

    # [cors]
    lines.append("[cors]")
    lines.append(f"origins = {_toml_str(cors.get('origins', 'http://localhost:3080'))}")
    lines.append("")

    # [smtp]
    if smtp.get("host") or smtp.get("enabled"):
        lines.append("[smtp]")
        lines.append(f"enabled = {_toml_bool(smtp.get('enabled', False))}")
        lines.append(f"host = {_toml_str(smtp.get('host', ''))}")
        lines.append(f"port = {smtp.get('port', 587)}")
        lines.append(f"username = {_toml_str(smtp.get('username', ''))}")
        lines.append("# password는 secret.yaml의 SMTP_PASSWORD 환경변수로 주입됩니다")
        lines.append(f"from_address = {_toml_str(smtp.get('from_address', 'noreply@afterglow.example.com'))}")
        lines.append(f"from_name = {_toml_str(smtp.get('from_name', 'Afterglow'))}")
        lines.append(f"use_tls = {_toml_bool(smtp.get('use_tls', True))}")
        lines.append(f"timeout_seconds = {smtp.get('timeout_seconds', 10)}")
        smtp_inv = smtp.get("invitation", {})
        lines.append("")
        lines.append("[smtp.invitation]")
        lines.append(f"token_expiry_days = {smtp_inv.get('token_expiry_days', 7)}")
        lines.append("")

    # [monitoring]
    lines.append("[monitoring]")
    lines.append(f"host_healthcheck_enabled = {_toml_bool(mon.get('host_healthcheck_enabled', True))}")
    targets = mon.get("host_healthcheck_targets", [])
    # Inline tables keep the targets inside [monitoring], before its child tables.
    rendered_targets = []
    for target in targets:
        fields = [f"{key} = {_toml_str(target[key])}" for key in ("name", "address", "role")]
        fields.append(f"port = {target.get('port', 9100)}")
        rendered_targets.append("{ " + ", ".join(fields) + " }")
    lines.append("host_healthcheck_targets = [" + ", ".join(rendered_targets) + "]")
    lines.append(f"infrastructure_topology_enabled = {_toml_bool(mon.get('infrastructure_topology_enabled', False))}")
    lines.append(f"infrastructure_topology_retention_seconds = {mon.get('infrastructure_topology_retention_seconds', 3600)}")
    lines.append("infrastructure_topology_trace_targets = [" + ", ".join(_toml_str(target) for target in mon.get("infrastructure_topology_trace_targets", [])) + "]")
    rendered_peers = []
    for target in mon.get("infrastructure_topology_peer_targets", []):
        fields = [f"{key} = {_toml_str(target[key])}" for key in ("source_host_id", "target_host_id", "address")]
        fields.append(f"port = {target.get('port', 9100)}")
        rendered_peers.append("{ " + ", ".join(fields) + " }")
    lines.append("infrastructure_topology_peer_targets = [" + ", ".join(rendered_peers) + "]")
    lines.append("# infrastructure_topology_observers is injected from MONITORING_INFRASTRUCTURE_TOPOLOGY_OBSERVERS in Secret")
    lines.append(f"prometheus_base_url = {_toml_str(mon.get('prometheus_base_url', 'http://prometheus:9090'))}")
    lines.append(f"prometheus_username = {_toml_str(mon.get('prometheus_username', ''))}")
    lines.append("# prometheus_password는 secret.yaml의 PROMETHEUS_PASSWORD 환경변수로 주입됩니다")
    lines.append(f"scrape_cidr = {_toml_str(mon.get('scrape_cidr', ''))}")
    lines.append(f"auto_sg_enabled = {_toml_bool(mon.get('auto_sg_enabled', True))}")
    lines.append(f"node_exporter_sg_name = {_toml_str(mon.get('node_exporter_sg_name', 'node_exporter'))}")
    lines.append(f"dcgm_exporter_sg_name = {_toml_str(mon.get('dcgm_exporter_sg_name', 'dcgm_exporter'))}")
    lines.append(f"node_exporter_port = {mon.get('node_exporter_port', 9100)}")
    lines.append(f"dcgm_exporter_port = {mon.get('dcgm_exporter_port', 9400)}")
    lines.append(f"libvirt_exporter_port = {mon.get('libvirt_exporter_port', 9177)}")
    lines.append(f"gpu_flavor_prefix = {_toml_str(mon.get('gpu_flavor_prefix', 'gpu.'))}")
    lines.append(f"grafana_base_url = {_toml_str(mon.get('grafana_base_url', ''))}")
    lines.append("# sd_token은 secret.yaml의 MONITORING_SD_TOKEN 환경변수로 주입됩니다")
    dashboards = mon.get("dashboards", {})
    lines.append("")
    lines.append("[monitoring.dashboards]")
    lines.append(f"node_uid = {_toml_str(dashboards.get('node_uid', 'afterglow-node'))}")
    lines.append(f"rabbitmq_uid = {_toml_str(dashboards.get('rabbitmq_uid', 'afterglow-rabbitmq'))}")
    lines.append(f"mysqld_uid = {_toml_str(dashboards.get('mysqld_uid', 'afterglow-mysqld'))}")
    lines.append(f"proxysql_uid = {_toml_str(dashboards.get('proxysql_uid', 'afterglow-proxysql'))}")
    lines.append(f"memcached_uid = {_toml_str(dashboards.get('memcached_uid', 'afterglow-memcached'))}")
    lines.append(f"etcd_uid = {_toml_str(dashboards.get('etcd_uid', 'afterglow-etcd'))}")
    lines.append(f"haproxy_uid = {_toml_str(dashboards.get('haproxy_uid', 'afterglow-haproxy'))}")
    lines.append(f"libvirt_uid = {_toml_str(dashboards.get('libvirt_uid', 'afterglow-libvirt'))}")
    lines.append(f"openstack_uid = {_toml_str(dashboards.get('openstack_uid', 'afterglow-openstack'))}")
    lines.append(f"ceph_uid = {_toml_str(dashboards.get('ceph_uid', 'afterglow-ceph'))}")
    lines.append(f"instance_cpu_uid = {_toml_str(dashboards.get('instance_cpu_uid', 'afterglow-instance-cpu'))}")
    lines.append(f"instance_gpu_uid = {_toml_str(dashboards.get('instance_gpu_uid', 'afterglow-instance-gpu'))}")
    lines.append("")
    fabric = mon.get("infrastructure_fabric", {})
    lines.append("[monitoring.infrastructure_fabric]")
    for key, default in (
        ("revision", 0), ("poll_interval_seconds", 10), ("freshness_seconds", 30),
        ("timeout_seconds", 2), ("retries", 1), ("concurrency", 4), ("poll_budget_seconds", 30),
        ("max_ports", 256), ("max_neighbors", 256), ("max_varbinds", 16384), ("retention_seconds", 3600),
    ):
        lines.append(f"{key} = {fabric.get(key, default)}")
    lines.append("# AuthPriv target credentials are injected through MONITORING_INFRASTRUCTURE_FABRIC__TARGETS Secret")
    lines.append("")

    traffic = cfg.get("traffic_analytics", {})
    lines.append("[traffic_analytics]")
    lines.append(f"enabled = {_toml_bool(traffic.get('enabled', False))}")
    lines.append(f"retention_days = {traffic.get('retention_days', 30)}")
    lines.append(f"geoip_mmdb = {_toml_str(traffic.get('geoip_mmdb', ''))}")
    for key in ("cluster_cidrs", "backend_trusted_proxy_cidrs", "frontend_trusted_proxy_cidrs"):
        lines.append(f"{key} = [" + ", ".join(_toml_str(value) for value in traffic.get(key, [])) + "]")
    lines.append(f"site_country = {_toml_str(traffic.get('site_country', ''))}")
    lines.append("# hmac_key and frontend_ingest_key are injected through TRAFFIC_ANALYTICS__* Secret environment keys")
    lines.append("")


    # [notion]
    if notion.get("config_encryption_key"):
        lines.append("[notion]")
        lines.append("# config_encryption_key는 secret.yaml의 NOTION_CONFIG_ENCRYPTION_KEY 환경변수로 주입됩니다")
        lines.append("")

    # [security]
    security = cfg.get("security", {})
    lines.append("[security]")
    lines.append(f"login_max_attempts = {security.get('login_max_attempts', 10)}")
    lines.append(f"login_lockout_seconds = {security.get('login_lockout_seconds', 300)}")
    lines.append(f"login_backoff_base = {security.get('login_backoff_base', 2)}")
    lines.append("")
    lines.append(render_auth_toml(cfg))

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# config.gpu.toml 렌더링
# ─────────────────────────────────────────────────────────────────────────────


def render_gpu_toml(cfg: dict) -> str:
    """config.gpu.toml 렌더링: GPU 디바이스 맵."""
    gpu = cfg.get("gpu", {})
    devices = gpu.get("devices", [])
    if not devices:
        return ""

    lines = [
        "# Afterglow GPU 디바이스 맵",
        "# afterglow.conf와 함께 로드되어 딥 머지됩니다.",
        "",
    ]
    for dev in devices:
        lines.append("[[gpu.devices]]")
        lines.append(f"vendor_id = {_toml_str(dev.get('vendor_id', ''))}")
        lines.append(f"device_id = {_toml_str(dev.get('device_id', ''))}")
        lines.append(f"name = {_toml_str(dev.get('name', ''))}")
        lines.append(f"is_audio = {_toml_bool(dev.get('is_audio', False))}")
        aliases = dev.get("aliases", [])
        if aliases:
            lines.append(f"aliases = {_toml_list_str(aliases)}")
        lines.append("")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# configmap.yaml 렌더링
# ─────────────────────────────────────────────────────────────────────────────


def render_configmap(cfg: dict, namespace: str = "afterglow") -> str:
    """configmap.yaml 생성: Redis URL, Origin, S3 base, afterglow.conf와 GPU 맵을 포함한다."""
    cors = cfg.get("cors", {})
    ost = cfg.get("openstack", {})

    # APP_ORIGIN: cors.origins 의 첫 번째 항목 (프로덕션 도메인)
    app_origin = _first_cors_origin(cors)
    public_api_base = _derive_public_api_base_for_k8s(cfg)

    # PUBLIC_S3_BASE: openstack.s3_endpoint (미설정 시 기본값)
    public_s3_base = ost.get("s3_endpoint", "https://s3.dmslab.re.kr")

    # APP_GRAFANA_BASE: monitoring.grafana_base_url (CSP frame-src 및 frontend 임베드용)
    app_grafana_base = cfg.get("monitoring", {}).get("grafana_base_url", "")

    # afterglow.conf 인라인 (4칸 들여쓰기).
    toml_content = _render_toml_for_k8s(cfg, namespace)
    indented_toml = "\n".join("    " + line for line in toml_content.splitlines())

    lines = [
        "apiVersion: v1",
        "kind: ConfigMap",
        "metadata:",
        "  name: afterglow-config",
        f"  namespace: {namespace}",
        "data:",
        f'  APP_REDIS_URL: "{REDIS_K8S}"',
        f'  APP_ORIGIN: "{app_origin}"',
        f'  PUBLIC_API_BASE: "{public_api_base}"',
        f"  FORWARDED_ALLOW_IPS: {_toml_str(cfg.get('app', {}).get('trusted_proxies', '127.0.0.1/32,::1/128'))}",
        f'  PUBLIC_S3_BASE: "{public_s3_base}"',
        f'  APP_GRAFANA_BASE: "{app_grafana_base}"',
        '  TRAFFIC_ANALYTICS_INGEST_URL: "http://backend:8000/api/v1/monitoring/traffic/events"',
        '  TRAFFIC_ANALYTICS_PEER_IS_SOCKET: "true"',
        "  afterglow.conf: |",
        indented_toml,
    ]
    ceph_conf_content = cfg.get("ceph", {}).get("rbd_conf_content", "")
    lines.extend(
        [
            "  ceph.conf: |",
            *(["    " + line for line in ceph_conf_content.splitlines()] if ceph_conf_content else ["    "]),
        ]
    )

    # config.gpu.toml (GPU 디바이스 맵이 있는 경우에만)
    gpu_content = render_gpu_toml(cfg)
    if gpu_content:
        indented_gpu = "\n".join("    " + line for line in gpu_content.splitlines())
        lines.extend(
            [
                "  config.gpu.toml: |",
                indented_gpu,
            ]
        )

    lines.append("")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# ingress.yaml 렌더링
# ─────────────────────────────────────────────────────────────────────────────


def render_ingress(cfg: dict, namespace: str = "afterglow") -> str:
    """Render host-bound MCP routes without rewriting paths or replacing the web fallback."""
    public_api_base = _derive_public_api_base_for_k8s(cfg)
    frontend_origin = (
        _origin_of(cfg.get("app", {}).get("frontend_base_url"))
        or _configured_cors_origin(cfg.get("cors", {}))
        or public_api_base
    )
    frontend_host = urlparse(frontend_origin).hostname
    api_host = urlparse(public_api_base).hostname
    # Slash-suffixed Prefix routes also preserve boundaries on default Traefik.
    web_paths = [
        ("/.well-known/", "Prefix", "backend", 8000),
        ("/api", "Prefix", "backend", 8000),
        ("/", "Prefix", "frontend", 3080),
    ]
    routes = {frontend_host: list(web_paths)}
    if api_host != frontend_host:
        routes[api_host] = [("/v1", "Prefix", "lumen", 8012), *web_paths]
    mcp_routes = None
    tls_hosts = list(routes)

    if cfg.get("services", {}).get("mcp", False):
        resource = cfg.get("mcp", {}).get("public_url") or f"{public_api_base}/api/v1/mcp"
        parsed = urlparse(resource)
        mcp_host = parsed.hostname
        mcp_path = parsed.path.rstrip("/") or "/"
        if not mcp_host:
            raise ValueError("mcp.public_url requires an absolute URL with a host")
        if mcp_path == "/" and mcp_host in routes:
            raise ValueError("mcp.public_url at an origin root requires a dedicated host; it cannot share the web or API host")
        mcp_paths = [
            (mcp_path, "Exact", "backend", 8000),
            ("/oauth/" if mcp_path == "/" else f"{mcp_path}/", "Prefix", "backend", 8000),
            ("/.well-known/", "Prefix", "backend", 8000),
        ]
        mcp_routes = {mcp_host: mcp_paths}
        if mcp_host not in tls_hosts:
            tls_hosts.append(mcp_host)

    profile = "dev" if namespace == "afterglow-dev" else "prod"
    documents = []
    ingress_definitions = [("afterglow-ingress", routes, None)]
    if mcp_routes:
        ingress_definitions.append(("afterglow-mcp-ingress", mcp_routes, "1000"))
    for name, host_routes, priority in ingress_definitions:
        lines = [
            "apiVersion: networking.k8s.io/v1",
            "kind: Ingress",
            "metadata:",
            f"  name: {name}",
            f"  namespace: {namespace}",
            "  annotations:",
            '    kubernetes.io/ingress.class: "traefik"',
            "    traefik.ingress.kubernetes.io/router.entrypoints: web,websecure",
            f"    traefik.ingress.kubernetes.io/service.serverstransport: {namespace}-backend-long-timeout@kubernetescrd",
        ]
        if priority:
            lines.append(f'    traefik.ingress.kubernetes.io/router.priority: "{priority}"')
        else:
            lines.append(f'    cert-manager.io/cluster-issuer: "letsencrypt-{profile}-traefik"')
        lines.extend([
            "spec:",
            "  tls:",
            "    - hosts:",
            *(f"        - {_yaml_str(host)}" for host in (list(host_routes) if priority else tls_hosts)),
            "      secretName: afterglow-tls",
            "  rules:",
        ])
        for host, paths in host_routes.items():
            lines.extend([f"    - host: {_yaml_str(host)}", "      http:", "        paths:"])
            for path, path_type, service, port in paths:
                lines.extend([
                    f"          - path: {_yaml_str(path)}",
                    f"            pathType: {path_type}",
                    "            backend:",
                    "              service:",
                    f"                name: {service}",
                    "                port:",
                    f"                  number: {port}",
                ])
        documents.append("\n".join(lines))
    return "\n---\n".join(documents) + "\n"


# ─────────────────────────────────────────────────────────────────────────────
# grafana-deployment.yaml 렌더링
# ─────────────────────────────────────────────────────────────────────────────


def render_grafana_deployment(cfg: dict, namespace: str = "afterglow") -> str:
    """grafana-deployment.yaml 생성.

    iframe 임베드(GF_SECURITY_ALLOW_EMBEDDING)와 익명 접근(auth.anonymous)을 설정한다.
    provisioning ConfigMap (datasource + dashboards)을 volumeMounts로 마운트한다.
    """
    mon = cfg.get("monitoring", {})
    admin_password = mon.get("grafana_admin_password", "admin")
    lines = [
        "apiVersion: apps/v1",
        "kind: Deployment",
        "metadata:",
        "  name: grafana",
        f"  namespace: {namespace}",
        "  labels:",
        "    app: grafana",
        "spec:",
        "  replicas: 1",
        "  selector:",
        "    matchLabels:",
        "      app: grafana",
        "  template:",
        "    metadata:",
        "      labels:",
        "        app: grafana",
        "    spec:",
        "      containers:",
        "        - name: grafana",
        "          image: grafana/grafana:11.0.0",
        "          ports:",
        "            - containerPort: 3000",
        "          env:",
        "            - name: GF_SECURITY_ADMIN_PASSWORD",
        f'              value: "{admin_password}"',
        "            - name: GF_USERS_ALLOW_SIGN_UP",
        '              value: "false"',
        "            - name: GF_SECURITY_ALLOW_EMBEDDING",
        '              value: "true"',
        "            - name: GF_AUTH_ANONYMOUS_ENABLED",
        '              value: "true"',
        "            - name: GF_AUTH_ANONYMOUS_ORG_ROLE",
        '              value: "Viewer"',
        "          volumeMounts:",
        "            - name: grafana-datasource",
        "              mountPath: /etc/grafana/provisioning/datasources",
        "            - name: grafana-dashboards-provider",
        "              mountPath: /etc/grafana/provisioning/dashboards",
        "            - name: grafana-dashboards",
        "              mountPath: /var/lib/grafana/dashboards",
        "          resources:",
        "            requests:",
        '              memory: "128Mi"',
        '              cpu: "100m"',
        "            limits:",
        '              memory: "256Mi"',
        '              cpu: "200m"',
        "      volumes:",
        "        - name: grafana-datasource",
        "          configMap:",
        "            name: grafana-datasource",
        "        - name: grafana-dashboards-provider",
        "          configMap:",
        "            name: grafana-dashboards-provider",
        "        - name: grafana-dashboards",
        "          configMap:",
        "            name: grafana-dashboards",
        "",
    ]
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# 파일 쓰기
# ─────────────────────────────────────────────────────────────────────────────


def _application_sources(template: Path) -> dict[str, str]:
    """Follow the existing local resource lists, never arbitrary checkout files."""
    files: dict[str, str] = {}

    def include(path: Path) -> None:
        relative = path.relative_to(template)
        if path.is_symlink() or ".." in relative.parts:
            raise ValueError("Unsafe application template path")
        if path.is_dir():
            include(path / "kustomization.yaml")
            return
        content = path.read_text(encoding="utf-8")
        files[str(relative)] = content
        if path.name != "kustomization.yaml":
            return
        resources = False
        for line in content.splitlines():
            if line == "resources:":
                resources = True
                continue
            if resources and line and not line.startswith((" ", "#")):
                resources = False
            if resources and line.lstrip().startswith("- "):
                name = line.strip()[2:].split(" #", 1)[0].strip()
                if ":" in name or Path(name).is_absolute() or ".." in Path(name).parts:
                    raise ValueError("Only local application template resources are supported")
                include(path.parent / name)

    include(template / "base")
    include(template / "monitoring")
    return files


def render_artifacts(cfg: dict, namespace: str = "afterglow") -> dict[str, str]:
    """Render a self-contained application Kustomize tree without deploying it.

    The existing application/monitoring templates remain authoritative; generated
    configuration and routing replace their placeholders. Cluster infrastructure
    (Traefik/cert-manager) remains an operator prerequisite, not an installer.
    """
    template = SCRIPT_DIR / "deploy" / "k8s-template"
    artifacts = _application_sources(template)
    secret = render_secret(cfg, namespace)
    grafana = render_grafana_deployment(cfg, namespace)
    artifacts.update({
        "secret.yaml": secret,
        "configmap.yaml": render_configmap(cfg, namespace),
        "ingress.yaml": render_ingress(cfg, namespace),
        "grafana-deployment.yaml": grafana,
        "monitoring/grafana/deployment.yaml": grafana,
        "middleware.yaml": (template / "middleware.yaml").read_text(encoding="utf-8"),
        "base/namespace.yaml": f"apiVersion: v1\nkind: Namespace\nmetadata:\n  name: {namespace}\n",
        "kustomization.yaml": (
            "apiVersion: kustomize.config.k8s.io/v1beta1\nkind: Kustomization\n"
            f"namespace: {namespace}\nresources:\n"
            "  - base\n  - secret.yaml\n  - configmap.yaml\n"
            "  - ingress.yaml\n  - middleware.yaml\n  - monitoring\n"
        ),
    })
    # Explicit env lists in both workloads must consume the dynamic registry keys.
    auth_keys = [f"AUTH__PROVIDERS__{key.upper()}__CLIENT_SECRET" for key in _auth_config(cfg).get("providers", {})]
    if auth_keys:
        artifacts["kustomization.yaml"] += "patches:\n"
        for workload in ("backend", "notion-worker"):
            path = f"auth-{workload}-env.yaml"
            artifacts["kustomization.yaml"] += (
                f"  - path: {path}\n    target:\n      kind: Deployment\n      name: {workload}\n"
            )
            lines = [
                "apiVersion: apps/v1", "kind: Deployment", "metadata:", f"  name: {workload}",
                "spec:", "  template:", "    spec:", "      containers:",
                f"        - name: {workload}", "          env:",
            ]
            for key in auth_keys:
                lines.extend((
                    f"            - name: {key}", "              valueFrom:",
                    "                secretKeyRef:", "                  name: afterglow-secrets",
                    f"                  key: {key}",
                    "                  optional: true",
                ))
            artifacts[path] = "\n".join(lines) + "\n"
    return artifacts


# ─────────────────────────────────────────────────────────────────────────────
# 진입점
# ─────────────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="afterglow.conf → K8s configmap/secret/ingress/grafana 매니페스트 변환기"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=default_config_path(),
        help="afterglow.conf 경로 (기본값: ./afterglow.conf)",
    )
    parser.add_argument(
        "--override",
        dest="override_paths",
        action="append",
        type=Path,
        default=[],
        metavar="PATH",
        help="환경별 afterglow.*.conf 오버라이드 파일 (반복 지정 가능)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path.cwd() / "deploy" / "k8s",
        help="출력 디렉토리 (기본값: ./deploy/k8s)",
    )
    parser.add_argument(
        "--namespace",
        choices=("afterglow", "afterglow-dev"),
        default="afterglow",
        help="대상 네임스페이스 (기본값: afterglow)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="파일을 쓰지 않고 내용만 출력",
    )
    args = parser.parse_args()

    config_path = args.config.resolve()
    output_dir = args.output_dir.resolve()
    try:
        text = prepare_config(config_path)
        cfg = merge_config(config_path, text, args.override_paths)
        artifacts = render_artifacts(cfg, args.namespace)
        if args.dry_run:
            # Never preview a Secret, credential-bearing deployment or private
            # config. Public renderers retain the closed projection boundary.
            print(render_configmap(cfg, args.namespace))
            print("---")
            print(render_ingress(cfg, args.namespace))
            return
        contents = {output_dir / name: content for name, content in artifacts.items()}
        sources = [config_path, *config_override_paths(config_path), *args.override_paths]
        if {path.resolve() for path in sources} & {path.resolve() for path in contents}:
            raise ValueError("Configuration inputs and artifact paths must be distinct")
        if not config_path.exists():
            contents[config_path] = text
        write_files(contents)
    except (OSError, ValueError):
        # Parser exceptions can contain the input literal; never echo it.
        print("Generation failed; check configuration and output permissions. No secrets displayed.", file=sys.stderr)
        sys.exit(1)
    print(f"Generated Kubernetes application artifacts in {output_dir}. No cluster changes performed.")


if __name__ == "__main__":
    main()
