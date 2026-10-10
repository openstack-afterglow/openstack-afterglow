#!/usr/bin/env python3
"""afterglow 설정 마법사

사용법:
    python3 setup.py

afterglow.conf, k8s/secret.yaml, k8s/configmap.yaml을 대화형으로 생성합니다.
Python 3.12+ 표준 라이브러리만 사용합니다.
"""

import getpass
import os
import re
import secrets
import sys
import tempfile
import tomllib
import urllib.parse
from datetime import datetime
from pathlib import Path

# ──────────────────────────────────────────────
# 상수
# ──────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent.resolve()
CONFIG_EXAMPLE = SCRIPT_DIR / "afterglow.conf.example"

DEPLOY_DOCKER = 1
DEPLOY_K8S = 2
DEPLOY_BOTH = 3

REDIS_DOCKER = "redis://redis:6379/0"
REDIS_K8S = "redis://redis.afterglow.svc.cluster.local:6379/0"

# ANSI 색상 (Windows에서는 비활성화)
_USE_COLOR = os.name != "nt" or os.environ.get("FORCE_COLOR")

def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _USE_COLOR else text

def green(t: str) -> str: return _c("32", t)
def yellow(t: str) -> str: return _c("33", t)
def red(t: str) -> str: return _c("31", t)
def bold(t: str) -> str: return _c("1", t)
def dim(t: str) -> str: return _c("2", t)
def cyan(t: str) -> str: return _c("36", t)


# ──────────────────────────────────────────────
# 검증 함수
# ──────────────────────────────────────────────

def validate_url(value: str, schemes: tuple = ("http", "https")) -> str | None:
    """유효한 URL이면 None, 아니면 오류 메시지 반환."""
    try:
        r = urllib.parse.urlparse(value)
        if r.scheme not in schemes or not r.netloc:
            return f"유효한 URL을 입력하세요 (예: http://keystone.example.com:5000/v3). 허용 스킴: {', '.join(schemes)}"
    except Exception:
        return "유효한 URL 형식이 아닙니다."
    return None


def validate_redis_url(value: str) -> str | None:
    return validate_url(value, schemes=("redis", "rediss"))


def validate_port(value: str) -> str | None:
    try:
        p = int(value)
        if not (1 <= p <= 65535):
            return "포트 번호는 1~65535 범위여야 합니다."
    except ValueError:
        return "숫자를 입력하세요."
    return None


# ──────────────────────────────────────────────
# 입력 헬퍼
# ──────────────────────────────────────────────

def ask(prompt: str, default: str = "", validator=None, required: bool = False) -> str:
    """단일 값 입력. 빈 입력이면 default 반환."""
    hint = f" [{dim(default)}]" if default else ""
    while True:
        try:
            raw = input(f"  {prompt}{hint}: ").strip()
        except EOFError:
            raw = ""
        value = raw if raw else default
        if required and not value:
            print(f"  {red('값을 입력해야 합니다.')}")
            continue
        if validator and value:
            err = validator(value)
            if err:
                print(f"  {red(err)}")
                continue
        return value


def ask_password(prompt: str) -> str:
    """비밀번호 입력 (숨김). 빈 입력 불허."""
    while True:
        try:
            value = getpass.getpass(f"  {prompt}: ").strip()
        except (EOFError, KeyboardInterrupt):
            raise
        if value:
            return value
        print(f"  {red('비밀번호는 비워둘 수 없습니다.')}")


def ask_bool(prompt: str, default: bool = False) -> bool:
    """Y/N 입력."""
    hint = "(Y/n)" if default else "(y/N)"
    while True:
        try:
            raw = input(f"  {prompt} {dim(hint)}: ").strip().lower()
        except EOFError:
            raw = ""
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        if raw == "":
            return default
        print(f"  {red('y 또는 n을 입력하세요.')}")


def ask_int(prompt: str, default: int, min_val: int | None = None, max_val: int | None = None) -> int:
    """정수 입력."""
    while True:
        raw = ask(prompt, str(default))
        try:
            v = int(raw)
        except ValueError:
            print(f"  {red('정수를 입력하세요.')}")
            continue
        if min_val is not None and v < min_val:
            print(f"  {red(f'{min_val} 이상의 값을 입력하세요.')}")
            continue
        if max_val is not None and v > max_val:
            print(f"  {red(f'{max_val} 이하의 값을 입력하세요.')}")
            continue
        return v


def ask_choice(prompt: str, options: list[str], default: int = 1) -> int:
    """번호 선택. 1-indexed 선택 번호 반환."""
    for i, opt in enumerate(options, 1):
        marker = green("▶") if i == default else " "
        print(f"  {marker} {i}) {opt}")
    while True:
        raw = ask(prompt, str(default))
        try:
            v = int(raw)
            if 1 <= v <= len(options):
                return v
        except ValueError:
            pass
        print(f"  {red(f'1~{len(options)} 중에서 선택하세요.')}")


# ──────────────────────────────────────────────
# UI 헬퍼
# ──────────────────────────────────────────────

_TOTAL_SECTIONS = 12
_current_section = 0

def section_header(title: str):
    global _current_section
    _current_section += 1
    width = 52
    print()
    print(cyan("═" * width))
    progress = f"  {_current_section}/{_TOTAL_SECTIONS}  "
    print(cyan("║") + bold(f"{progress}{title}"))
    print(cyan("═" * width))


def print_banner():
    print()
    print(cyan("╔" + "═" * 50 + "╗"))
    print(cyan("║") + bold("        afterglow 설정 마법사 v1.0              ") + cyan("║"))
    print(cyan("║") + dim("  afterglow.conf · secret.yaml · configmap.yaml") + cyan("  ║"))
    print(cyan("╚" + "═" * 50 + "╝"))
    print()
    print("각 항목에서 Enter를 누르면 기본값이 사용됩니다.")
    print(f"{yellow('주의')}: 비밀번호 등 민감 정보는 afterglow.conf에 평문으로 저장됩니다.")
    print(f"       afterglow.conf를 .gitignore에 추가하세요.")
    print()


# ──────────────────────────────────────────────
# 섹션 수집 함수
# ──────────────────────────────────────────────

def collect_deploy_mode() -> int:
    section_header("배포 환경 선택")
    print()
    return ask_choice(
        "배포 환경을 선택하세요",
        [
            "Docker Compose  (afterglow.conf 생성)",
            "Kubernetes      (afterglow.conf + k8s/secret.yaml + k8s/configmap.yaml 생성)",
            "둘 다           (모든 파일 생성)",
        ],
        default=1,
    )


def collect_openstack() -> dict:
    section_header("OpenStack 인증 설정")
    print()
    auth_url = ask("Keystone URL", "http://keystone.example.com:5000/v3",
                   validator=validate_url, required=True)
    project_name = ask("프로젝트 이름", "admin")
    project_domain_name = ask("프로젝트 도메인", "Default")
    user_domain_name = ask("사용자 도메인", "Default")
    region_name = ask("리전", "RegionOne")
    username = ask("관리자 계정", "admin")
    password = ask_password("관리자 비밀번호")

    print()
    insecure = ask_bool("자체 서명 인증서 사용 (insecure=true)?", default=False)
    cacert = ""
    if not insecure:
        cacert = ask("CA 인증서 경로 (없으면 Enter)", "")

    return {
        "auth_url": auth_url,
        "project_name": project_name,
        "project_domain_name": project_domain_name,
        "user_domain_name": user_domain_name,
        "region_name": region_name,
        "username": username,
        "password": password,
        "insecure": insecure,
        "cacert": cacert,
    }


def collect_manila_ceph() -> dict:
    section_header("Manila / Ceph 설정 (파일 스토리지)")
    print()
    configure = ask_bool("Manila/Ceph 파일 스토리지를 설정하시겠습니까?", default=False)
    if not configure:
        return {
            "manila_endpoint": "",
            "manila_share_network_id": "",
            "manila_share_type": "cephfs",
            "manila_nfs_share_type": "nfstype",
            "ceph_monitors": "",
        }
    print()
    manila_endpoint = ask("Manila 엔드포인트 URL (서비스 카탈로그 사용 시 Enter)", "",
                          validator=lambda v: validate_url(v) if v else None)
    manila_share_network_id = ask("Manila Share Network ID", "")
    manila_share_type = ask("Manila Share Type (CephFS용)", "cephfs")
    manila_nfs_share_type = ask("Manila Share Type (NFS용)", "nfstype")
    ceph_monitors = ask(
        "Ceph 모니터 주소 (쉼표 구분, 예: 192.168.1.10:6789,192.168.1.11:6789)", ""
    )
    return {
        "manila_endpoint": manila_endpoint,
        "manila_share_network_id": manila_share_network_id,
        "manila_share_type": manila_share_type,
        "manila_nfs_share_type": manila_nfs_share_type,
        "ceph_monitors": ceph_monitors,
    }


def collect_app() -> dict:
    section_header("앱 기본 설정")
    print()

    # secret_key
    auto_key = ask_bool("secret_key를 자동 생성하시겠습니까? (권장)", default=True)
    if auto_key:
        secret_key = secrets.token_hex(32)
        print(f"  {green('✓')} secret_key 자동 생성됨: {dim(secret_key[:8] + '...' + secret_key[-8:])}")
    else:
        while True:
            secret_key = ask("secret_key (최소 16자)", required=True)
            if len(secret_key) >= 16:
                break
            print(f"  {red('16자 이상이어야 합니다.')}")

    print()
    site_name = ask("사이트 이름", "afterglow")
    site_description = ask("사이트 설명", "OpenStack VM + OverlayFS 배포 플랫폼")
    backend_port = ask_int("백엔드 포트", 8000, 1, 65535)
    frontend_port = ask_int("프론트엔드 포트", 3080, 1, 65535)
    refresh_interval_ms = ask_int("대시보드 자동 새로고침 간격 (ms)", 5000, 1000, 60000)

    return {
        "secret_key": secret_key,
        "site_name": site_name,
        "site_description": site_description,
        "backend_port": backend_port,
        "frontend_port": frontend_port,
        "refresh_interval_ms": refresh_interval_ms,
        "logo_path": "/afterglow-logo.svg",
        "favicon_path": "/favicon.svg",
    }


def collect_cache(deploy_mode: int) -> dict:
    section_header("Redis / 캐시 설정")
    print()

    if deploy_mode == DEPLOY_DOCKER:
        default_redis = REDIS_DOCKER
    elif deploy_mode == DEPLOY_K8S:
        default_redis = REDIS_K8S
    else:  # BOTH — afterglow.conf는 Docker용
        default_redis = REDIS_DOCKER
        print(f"  {dim('afterglow.conf에는 Docker Redis URL, configmap에는 K8s Redis URL이 사용됩니다.')}")

    redis_url = ask("Redis URL", default_redis, validator=validate_redis_url)

    print()
    customize_ttl = ask_bool("TTL 값을 커스터마이즈하시겠습니까? (기본값 권장)", default=False)
    if customize_ttl:
        ttl_fast = ask_int("ttl_fast (인스턴스·볼륨·플로팅IP, 초)", 15, 1)
        ttl_normal = ask_int("ttl_normal (네트워크·대시보드, 초)", 30, 1)
        ttl_slow = ask_int("ttl_slow (키페어·보안그룹, 초)", 60, 1)
        ttl_static = ask_int("ttl_static (이미지·플레이버·토큰, 초)", 300, 1)
    else:
        ttl_fast, ttl_normal, ttl_slow, ttl_static = 15, 30, 60, 300

    return {
        "redis_url": redis_url,
        "ttl_fast": ttl_fast,
        "ttl_normal": ttl_normal,
        "ttl_slow": ttl_slow,
        "ttl_static": ttl_static,
    }


def collect_session() -> dict:
    section_header("세션 설정")
    print()
    timeout_seconds = ask_int("세션 유지 시간 (초, Keystone 토큰 만료보다 짧게)", 3600, 60)
    warning_before_seconds = ask_int("만료 경고 시작 시간 (초 전)", 300, 30)
    return {
        "timeout_seconds": timeout_seconds,
        "warning_before_seconds": warning_before_seconds,
    }


def collect_nova() -> dict:
    section_header("Nova 컴퓨트 설정")
    print()
    default_network_id = ask("기본 네트워크 ID (OpenStack 네트워크 UUID)", "")
    default_availability_zone = ask("기본 가용 영역", "nova")
    boot_volume_size_gb = ask_int("부팅 볼륨 크기 (GB)", 20, 1)
    upper_volume_size_gb = ask_int("최대 볼륨 크기 (GB)", 50, boot_volume_size_gb)
    return {
        "default_network_id": default_network_id,
        "default_availability_zone": default_availability_zone,
        "boot_volume_size_gb": boot_volume_size_gb,
        "upper_volume_size_gb": upper_volume_size_gb,
    }


def collect_services() -> dict:
    section_header("선택적 OpenStack 서비스")
    print(f"  {dim('비활성화된 서비스는 라우터에 등록되지 않고 사이드바에서 숨겨집니다.')}")
    print()
    manila = ask_bool("Manila (공유 파일 시스템) 활성화?", default=False)
    magnum = ask_bool("Magnum (K8s 클러스터) 활성화?", default=False)
    zun = ask_bool("Zun (컨테이너) 활성화?", default=False)
    k3s = ask_bool("k3s (자체 관리 Kubernetes) 활성화?", default=False)
    return {"manila": manila, "magnum": magnum, "zun": zun, "k3s": k3s}


def collect_k3s() -> dict:
    section_header("k3s Kubernetes 설정")
    print()
    version = ask("k3s 버전", "v1.31.4+k3s1")
    server_flavor_id = ask("컨트롤 플레인 노드 Flavor ID", "")
    default_agent_flavor_id = ask("워커 노드 기본 Flavor ID", "")
    server_image_id = ask("서버 이미지 ID (Ubuntu 22.04+)", "")
    callback_base_url = ask(
        "콜백 URL (VM이 접근할 백엔드 URL, 예: http://10.0.0.1:8000)", "",
        validator=lambda v: validate_url(v) if v else None,
    )
    print()
    auto_key = ask_bool("kubeconfig 암호화 키를 자동 생성하시겠습니까? (권장)", default=True)
    if auto_key:
        kubeconfig_encryption_key = secrets.token_hex(32)
        print(f"  {green('✓')} 암호화 키 자동 생성됨")
    else:
        kubeconfig_encryption_key = ask("kubeconfig 암호화 키 (openssl rand -hex 32)", required=True)
    boot_volume_size_gb = ask_int("k3s 노드 부팅 볼륨 크기 (GB)", 30, 10)
    return {
        "version": version,
        "server_flavor_id": server_flavor_id,
        "default_agent_flavor_id": default_agent_flavor_id,
        "server_image_id": server_image_id,
        "callback_base_url": callback_base_url,
        "kubeconfig_encryption_key": kubeconfig_encryption_key,
        "boot_volume_size_gb": boot_volume_size_gb,
    }


def collect_cors(frontend_port: int) -> dict:
    section_header("CORS 설정")
    print()
    default_origins = f"http://localhost:{frontend_port},http://localhost"
    origins = ask("허용 Origin (쉼표 구분)", default_origins)
    return {"origins": origins}


def collect_gitlab_oidc(frontend_port: int) -> dict:
    section_header("GitLab OIDC SSO 설정 (선택)")
    print()
    enabled = ask_bool("GitLab OIDC 로그인을 활성화하시겠습니까?", default=False)
    if not enabled:
        return {
            "enabled": False,
            "gitlab_url": "https://gitlab.example.com",
            "client_id": "",
            "client_secret": "",
            "idp_id": "gitlab",
            "protocol_id": "openid",
            "redirect_uri": f"http://localhost:{frontend_port}/auth/gitlab/callback",
            "scopes": "openid email profile read_user",
        }
    print()
    gitlab_url = ask("GitLab 인스턴스 URL", "https://gitlab.example.com",
                     validator=validate_url, required=True)
    client_id = ask("OAuth2 Client ID", required=True)
    client_secret = ask_password("OAuth2 Client Secret")
    idp_id = ask("Keystone IDP ID", "gitlab")
    protocol_id = ask("Keystone Protocol ID", "openid")
    redirect_uri = ask(
        "콜백 URL",
        f"http://localhost:{frontend_port}/auth/gitlab/callback",
        validator=validate_url,
    )
    scopes = ask("OAuth2 Scope", "openid email profile read_user")
    return {
        "enabled": True,
        "gitlab_url": gitlab_url,
        "client_id": client_id,
        "client_secret": client_secret,
        "idp_id": idp_id,
        "protocol_id": protocol_id,
        "redirect_uri": redirect_uri,
        "scopes": scopes,
    }


def collect_gpu_devices() -> list[dict]:
    section_header("GPU 디바이스 맵")
    print()
    if not CONFIG_EXAMPLE.exists():
        print(f"  {yellow('경고')}: afterglow.conf.example을 찾을 수 없습니다.")
        print(f"  GPU 디바이스 맵은 빈 상태로 생성됩니다. 나중에 직접 수정하세요.")
        return []

    with open(CONFIG_EXAMPLE, "rb") as f:
        example = tomllib.load(f)
    devices = example.get("gpu", {}).get("devices", [])
    print(f"  {green('✓')} afterglow.conf.example에서 GPU {len(devices)}개 로드됨")
    use_default = ask_bool("기본 GPU 디바이스 맵을 사용하시겠습니까?", default=True)
    if use_default:
        return devices
    print(f"  GPU 디바이스 맵을 비워둡니다. 나중에 afterglow.conf에서 [[gpu.devices]] 항목을 직접 추가하세요.")
    return []


# ──────────────────────────────────────────────
# 파일 렌더러
# ──────────────────────────────────────────────

def _toml_str(v: str) -> str:
    """TOML 문자열 값 이스케이프."""
    return '"' + v.replace('\\', '\\\\').replace('"', '\\"') + '"'


def _toml_bool(v: bool) -> str:
    return "true" if v else "false"


def _toml_list(items: list[str]) -> str:
    return "[" + ", ".join(_toml_str(i) for i in items) + "]"


def render_config_toml(cfg: dict, for_k8s: bool = False) -> str:
    """전체 afterglow.conf 렌더링. for_k8s=True이면 비밀 값 제외."""
    os_cfg = cfg["openstack"]
    app = cfg["app"]
    manila = cfg["manila_ceph"]
    cache = cfg["cache"]
    sess = cfg["session"]
    nova = cfg["nova"]
    svc = cfg["services"]
    k3s = cfg.get("k3s") or {}
    cors = cfg["cors"]
    oidc = cfg["gitlab_oidc"]
    gpu_devices: list[dict] = cfg["gpu_devices"]

    redis_url = REDIS_K8S if for_k8s else cache["redis_url"]
    password_line = (
        '# password는 secret.yaml의 OS_PASSWORD 환경변수로 주입됩니다'
        if for_k8s else
        f'password = {_toml_str(os_cfg["password"])}'
    )
    secret_key_line = (
        '# secret_key는 secret.yaml의 SECRET_KEY 환경변수로 주입됩니다'
        if for_k8s else
        f'secret_key = {_toml_str(app["secret_key"])}'
    )
    client_secret_line = (
        '# client_secret은 secret.yaml의 GITLAB_OIDC_CLIENT_SECRET 환경변수로 주입됩니다'
        if for_k8s else
        f'client_secret = {_toml_str(oidc["client_secret"])}'
    )

    lines = []
    lines.append("# afterglow 통합 설정 파일")
    lines.append("# 이 파일을 수정하면 백엔드와 프론트엔드 전체 설정이 변경됩니다.")
    lines.append("# 우선순위: 환경변수 > afterglow.conf (프로젝트 루트) > 기본값")
    lines.append("")

    # [DEFAULT]
    lines.append("[DEFAULT]")
    lines.append(f"debug = {_toml_bool(cfg.get('DEFAULT', {}).get('debug', False))}")
    lines.append("")

    # [openstack]
    lines.append("[openstack]")
    lines.append(f'auth_url = {_toml_str(os_cfg["auth_url"])}')
    lines.append(f'project_name = {_toml_str(os_cfg["project_name"])}')
    lines.append(f'project_domain_name = {_toml_str(os_cfg["project_domain_name"])}')
    lines.append(f'user_domain_name = {_toml_str(os_cfg["user_domain_name"])}')
    lines.append(f'region_name = {_toml_str(os_cfg["region_name"])}')
    lines.append(f'username = {_toml_str(os_cfg["username"])}')
    lines.append(password_line)
    if os_cfg["insecure"]:
        lines.append("insecure = true")
    if os_cfg["cacert"]:
        lines.append(f'cacert = {_toml_str(os_cfg["cacert"])}')
    lines.append("")
    lines.append("# Manila 설정")
    lines.append(f'manila_endpoint = {_toml_str(manila["manila_endpoint"])}')
    lines.append(f'manila_share_network_id = {_toml_str(manila["manila_share_network_id"])}')
    lines.append(f'manila_share_type = {_toml_str(manila["manila_share_type"])}')
    lines.append(f'manila_nfs_share_type = {_toml_str(manila["manila_nfs_share_type"])}')
    lines.append("")
    lines.append("# Ceph 모니터 (cloud-init CephFS 마운트용, 콤마 구분)")
    lines.append(f'ceph_monitors = {_toml_str(manila["ceph_monitors"])}')
    lines.append("")

    # [app]
    lines.append("[app]")
    lines.append(f'backend_port = {app["backend_port"]}')
    lines.append(f'frontend_port = {app["frontend_port"]}')
    lines.append(secret_key_line)
    lines.append("")
    lines.append("# 사이트 표시 이름 및 설명")
    lines.append(f'site_name = {_toml_str(app["site_name"])}')
    lines.append(f'site_description = {_toml_str(app["site_description"])}')
    lines.append("")
    lines.append("# 로고 및 파비콘 경로 (frontend/static/ 기준)")
    lines.append(f'logo_path = {_toml_str(app["logo_path"])}')
    lines.append(f'favicon_path = {_toml_str(app["favicon_path"])}')
    lines.append("")
    lines.append("# 프론트엔드 대시보드 자동 새로고침 간격 (밀리초)")
    lines.append(f'refresh_interval_ms = {app["refresh_interval_ms"]}')
    lines.append("")

    # [cache]
    lines.append("[cache]")
    lines.append(f'redis_url = {_toml_str(redis_url)}')
    lines.append("# TTL 티어 (초)")
    lines.append(f'ttl_fast = {cache["ttl_fast"]}      # 인스턴스, 볼륨, 플로팅IP')
    lines.append(f'ttl_normal = {cache["ttl_normal"]}    # 네트워크, 라우터, 대시보드')
    lines.append(f'ttl_slow = {cache["ttl_slow"]}      # 키페어, 보안그룹')
    lines.append(f'ttl_static = {cache["ttl_static"]}   # 이미지, 플레이버, 토큰 검증')
    lines.append("")

    # [session]
    lines.append("[session]")
    lines.append(f'timeout_seconds = {sess["timeout_seconds"]}')
    lines.append(f'warning_before_seconds = {sess["warning_before_seconds"]}')
    lines.append("")

    # [nova]
    lines.append("[nova]")
    lines.append(f'default_network_id = {_toml_str(nova["default_network_id"])}')
    lines.append(f'default_availability_zone = {_toml_str(nova["default_availability_zone"])}')
    lines.append(f'boot_volume_size_gb = {nova["boot_volume_size_gb"]}')
    lines.append(f'upper_volume_size_gb = {nova["upper_volume_size_gb"]}')
    lines.append("")

    # [gpu] + [[gpu.devices]]
    lines.append("[gpu]")
    lines.append("# GPU 디바이스 맵 (vendor_id/device_id: lspci -nn 출력의 PCI ID)")
    lines.append("")
    for dev in gpu_devices:
        lines.append("[[gpu.devices]]")
        lines.append(f'vendor_id = {_toml_str(dev.get("vendor_id", ""))}')
        lines.append(f'device_id = {_toml_str(dev.get("device_id", ""))}')
        lines.append(f'name = {_toml_str(dev.get("name", ""))}')
        lines.append(f'is_audio = {_toml_bool(dev.get("is_audio", False))}')
        aliases = dev.get("aliases", [])
        if aliases:
            lines.append(f'aliases = {_toml_list(aliases)}')
        lines.append("")

    # [services]
    lines.append("[services]")
    lines.append(f'magnum = {_toml_bool(svc["magnum"])}')
    lines.append(f'manila = {_toml_bool(svc["manila"])}')
    lines.append(f'zun = {_toml_bool(svc["zun"])}')
    lines.append(f'k3s = {_toml_bool(svc["k3s"])}')
    lines.append("")

    # [k3s]
    lines.append("[k3s]")
    lines.append(f'version = {_toml_str(k3s.get("version", "v1.31.4+k3s1"))}')
    lines.append(f'server_flavor_id = {_toml_str(k3s.get("server_flavor_id", ""))}')
    lines.append(f'default_agent_flavor_id = {_toml_str(k3s.get("default_agent_flavor_id", ""))}')
    lines.append(f'server_image_id = {_toml_str(k3s.get("server_image_id", ""))}')
    lines.append(f'callback_base_url = {_toml_str(k3s.get("callback_base_url", ""))}')
    if for_k8s:
        lines.append('# kubeconfig_encryption_key는 secret.yaml에서 주입됩니다')
    else:
        lines.append(f'kubeconfig_encryption_key = {_toml_str(k3s.get("kubeconfig_encryption_key", ""))}')
    lines.append(f'boot_volume_size_gb = {k3s.get("boot_volume_size_gb", 30)}')
    lines.append("")

    # [cors]
    lines.append("[cors]")
    lines.append(f'origins = {_toml_str(cors["origins"])}')
    lines.append("")

    # [gitlab_oidc]
    lines.append("[gitlab_oidc]")
    lines.append(f'enabled = {_toml_bool(oidc["enabled"])}')
    lines.append(f'gitlab_url = {_toml_str(oidc["gitlab_url"])}')
    lines.append(f'client_id = {_toml_str(oidc["client_id"])}')
    lines.append(client_secret_line)
    lines.append(f'idp_id = {_toml_str(oidc["idp_id"])}')
    lines.append(f'protocol_id = {_toml_str(oidc["protocol_id"])}')
    lines.append(f'redirect_uri = {_toml_str(oidc["redirect_uri"])}')
    lines.append(f'scopes = {_toml_str(oidc["scopes"])}')
    lines.append("")

    return "\n".join(lines)


def render_k8s_secret(cfg: dict) -> str:
    os_cfg = cfg["openstack"]
    app = cfg["app"]
    oidc = cfg["gitlab_oidc"]

    lines = [
        "apiVersion: v1",
        "kind: Secret",
        "metadata:",
        "  name: afterglow-secrets",
        "  namespace: afterglow",
        "type: Opaque",
        "stringData:",
        "  # OpenStack 관리자 계정 비밀번호",
        f'  OS_PASSWORD: {_yaml_str(os_cfg["password"])}',
        "",
        "  # FastAPI 세션/JWT 서명용 시크릿 키",
        "  # 생성: python3 -c \"import secrets; print(secrets.token_hex(32))\"",
        f'  SECRET_KEY: {_yaml_str(app["secret_key"])}',
    ]

    if oidc["enabled"] and oidc["client_secret"]:
        lines.extend([
            "",
            "  # GitLab OIDC Client Secret",
            f'  GITLAB_OIDC_CLIENT_SECRET: {_yaml_str(oidc["client_secret"])}',
        ])

    k3s = cfg.get("k3s") or {}
    if cfg["services"]["k3s"] and k3s.get("kubeconfig_encryption_key"):
        lines.extend([
            "",
            "  # k3s kubeconfig 암호화 키",
            f'  K3S_KUBECONFIG_ENCRYPTION_KEY: {_yaml_str(k3s["kubeconfig_encryption_key"])}',
        ])

    lines.append("")
    return "\n".join(lines)


def _yaml_str(v: str) -> str:
    """YAML 스칼라 값을 따옴표로 감싸서 안전하게 렌더링."""
    # 특수문자가 있으면 큰따옴표로 감쌈
    if any(c in v for c in ('"', "'", ":", "#", "\n", "\\", "{")):
        escaped = v.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return f'"{v}"'


def render_k8s_configmap(cfg: dict) -> str:
    app = cfg["app"]
    frontend_port = app["frontend_port"]

    # afterglow.conf 내용 생성 (비밀 제외)
    afterglow_toml = render_config_toml(cfg, for_k8s=True)
    # 4칸 들여쓰기
    indented = "\n".join("    " + line for line in afterglow_toml.splitlines())

    # APP_ORIGIN 추론: CORS origins의 첫 번째 값 또는 기본값
    origins = cfg["cors"]["origins"].split(",")
    app_origin = origins[0].strip() if origins else f"http://localhost:{frontend_port}"

    lines = [
        "apiVersion: v1",
        "kind: ConfigMap",
        "metadata:",
        "  name: afterglow-config",
        "  namespace: afterglow",
        "data:",
        f'  APP_REDIS_URL: "{REDIS_K8S}"',
        f'  # 실제 서비스 도메인으로 변경 필요 (예: https://afterglow.example.com)',
        f'  APP_ORIGIN: "{app_origin}"',
        f'  FORWARDED_ALLOW_IPS: {_yaml_str(app.get("trusted_proxies", "127.0.0.1/32,::1/128"))}',
        "  afterglow.conf: |",
        indented,
        "",
    ]
    return "\n".join(lines)


# ──────────────────────────────────────────────
# 요약 출력
# ──────────────────────────────────────────────

def _mask(v: str) -> str:
    """비밀값 마스킹: 앞 2자 + **** + 뒤 2자."""
    if len(v) <= 4:
        return "****"
    return v[:2] + "****" + v[-2:]


def print_summary(cfg: dict, deploy_mode: int):
    os_cfg = cfg["openstack"]
    app = cfg["app"]
    svc = cfg["services"]
    oidc = cfg["gitlab_oidc"]

    deploy_labels = {DEPLOY_DOCKER: "Docker Compose", DEPLOY_K8S: "Kubernetes", DEPLOY_BOTH: "둘 다"}
    files = ["afterglow.conf"]
    if deploy_mode in (DEPLOY_K8S, DEPLOY_BOTH):
        files += ["k8s/secret.yaml", "k8s/configmap.yaml"]

    print()
    print(bold("═" * 52))
    print(bold("  설정 요약"))
    print(bold("═" * 52))
    print(f"  배포 환경    : {cyan(deploy_labels[deploy_mode])}")
    print(f"  생성 파일    : {', '.join(green(f) for f in files)}")
    print()
    print(bold("  [OpenStack]"))
    print(f"    auth_url   : {os_cfg['auth_url']}")
    print(f"    username   : {os_cfg['username']}")
    print(f"    password   : {yellow(_mask(os_cfg['password']))}")
    print(f"    project    : {os_cfg['project_name']} / {os_cfg['region_name']}")
    print(f"    insecure   : {os_cfg['insecure']}")
    print()
    print(bold("  [App]"))
    print(f"    site_name  : {app['site_name']}")
    print(f"    secret_key : {yellow(_mask(app['secret_key']))}")
    print(f"    ports      : backend={app['backend_port']}, frontend={app['frontend_port']}")
    print()
    print(bold("  [Services]"))
    for svc_name, enabled in svc.items():
        status = green("✓ 활성화") if enabled else dim("✗ 비활성화")
        print(f"    {svc_name:10}: {status}")
    print()
    print(bold("  [GitLab OIDC]"))
    if oidc["enabled"]:
        print(f"    gitlab_url  : {oidc['gitlab_url']}")
        print(f"    client_id   : {oidc['client_id']}")
        print(f"    client_secret: {yellow(_mask(oidc['client_secret']))}")
    else:
        print(f"    {dim('비활성화')}")
    print()
    print(f"  GPU 디바이스 : {len(cfg['gpu_devices'])}개")
    print(bold("═" * 52))


# ──────────────────────────────────────────────
# 파일 쓰기
# ──────────────────────────────────────────────

def backup_file(path: Path) -> Path | None:
    if not path.exists():
        return None
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_suffix(f".bak.{ts}")
    path.rename(backup)
    return backup


def write_atomic(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=".afterglow_setup_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, path)
    except Exception:
        os.unlink(tmp_path)
        raise


def write_files(cfg: dict, deploy_mode: int):
    print()
    print(bold("파일 생성 중..."))

    # 모든 콘텐츠를 먼저 렌더링 (실패 시 쓰기 전에 중단)
    config_toml_content = render_config_toml(cfg)
    secret_content = render_k8s_secret(cfg) if deploy_mode in (DEPLOY_K8S, DEPLOY_BOTH) else None
    configmap_content = render_k8s_configmap(cfg) if deploy_mode in (DEPLOY_K8S, DEPLOY_BOTH) else None

    # afterglow.conf
    config_path = SCRIPT_DIR / "afterglow.conf"
    backup = backup_file(config_path)
    if backup:
        print(f"  {dim(f'기존 afterglow.conf → {backup.name} 백업됨')}")
    write_atomic(config_path, config_toml_content)
    print(f"  {green('✓')} afterglow.conf 생성됨")

    # k8s 파일
    if secret_content:
        secret_path = SCRIPT_DIR / "k8s" / "secret.yaml"
        backup = backup_file(secret_path)
        if backup:
            print(f"  {dim(f'기존 secret.yaml → {backup.name} 백업됨')}")
        write_atomic(secret_path, secret_content)
        print(f"  {green('✓')} k8s/secret.yaml 생성됨")

    if configmap_content:
        configmap_path = SCRIPT_DIR / "k8s" / "configmap.yaml"
        backup = backup_file(configmap_path)
        if backup:
            print(f"  {dim(f'기존 configmap.yaml → {backup.name} 백업됨')}")
        write_atomic(configmap_path, configmap_content)
        print(f"  {green('✓')} k8s/configmap.yaml 생성됨")


def print_completion(deploy_mode: int, app: dict):
    print()
    print(bold(green("✓ 설정 완료!")))
    print()
    print(bold("다음 단계:"))
    if deploy_mode in (DEPLOY_DOCKER, DEPLOY_BOTH):
        print(f"  {cyan('Docker Compose')}")
        print("    docker compose up -d")
        print(f"    # Frontend: http://localhost:{app['frontend_port']}")
        print(f"    # Backend:  http://localhost:{app['backend_port']}/api/v1/health")
    if deploy_mode in (DEPLOY_K8S, DEPLOY_BOTH):
        print(f"  {cyan('Kubernetes')}")
        print("    kubectl apply -f k8s/namespace.yaml")
        print("    kubectl apply -f k8s/secret.yaml")
        print("    kubectl apply -f k8s/configmap.yaml")
        print("    kubectl apply -f k8s/")
    print()
    print(f"  {yellow('보안 주의사항')}:")
    print("  · afterglow.conf는 .gitignore에 추가하세요 (비밀번호 평문 포함)")
    print("  · k8s/secret.yaml을 git에 커밋하지 마세요")
    print()


# ──────────────────────────────────────────────
# 진입점
# ──────────────────────────────────────────────

def main():
    print_banner()

    try:
        deploy_mode = collect_deploy_mode()
        openstack = collect_openstack()
        manila_ceph = collect_manila_ceph()
        app = collect_app()
        cache = collect_cache(deploy_mode)
        session = collect_session()
        nova = collect_nova()
        services = collect_services()

        k3s = None
        if services["k3s"]:
            k3s = collect_k3s()
        else:
            # k3s 섹션 번호도 카운트
            global _current_section
            _current_section += 1

        cors = collect_cors(app["frontend_port"])
        gitlab_oidc = collect_gitlab_oidc(app["frontend_port"])
        gpu_devices = collect_gpu_devices()

    except KeyboardInterrupt:
        print(f"\n\n{yellow('설정 마법사가 취소되었습니다.')}")
        sys.exit(0)

    cfg = {
        "openstack": openstack,
        "manila_ceph": manila_ceph,
        "app": app,
        "cache": cache,
        "session": session,
        "nova": nova,
        "services": services,
        "k3s": k3s,
        "cors": cors,
        "gitlab_oidc": gitlab_oidc,
        "gpu_devices": gpu_devices,
    }

    print_summary(cfg, deploy_mode)

    try:
        proceed = ask_bool("위 설정으로 파일을 생성하시겠습니까?", default=True)
    except KeyboardInterrupt:
        print(f"\n{yellow('취소되었습니다.')}")
        sys.exit(0)

    if not proceed:
        print(f"{yellow('취소되었습니다. 파일이 생성되지 않았습니다.')}")
        sys.exit(0)

    try:
        write_files(cfg, deploy_mode)
    except Exception as e:
        print(f"\n{red('오류')}: 파일 생성에 실패했습니다: {e}")
        sys.exit(1)

    print_completion(deploy_mode, app)


if __name__ == "__main__":
    main()
