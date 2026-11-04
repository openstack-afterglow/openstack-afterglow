#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────────────────────────────
# afterglow × kolla-ansible integration uninstaller
# Usage: ./deploy/kolla/uninstall.sh
# ─────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${AFTERGLOW_REPO_DIR:-}"
if [[ -z "$REPO_DIR" && "$SCRIPT_DIR" == */deploy/kolla ]]; then
  REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
fi

log()  { echo "[afterglow-uninstall] $*"; }
warn() { echo "[afterglow-uninstall] WARNING: $*" >&2; }
die()  { echo "[afterglow-uninstall] ERROR: $*" >&2; exit 1; }
if [[ -n "$REPO_DIR" ]]; then
  [[ "$REPO_DIR" == /* ]] || die "AFTERGLOW_REPO_DIR must be an absolute checkout path."
  REPO_DIR="${REPO_DIR%/}"
fi

detect_kolla_dir() {
  if [[ -n "${KOLLA_ANSIBLE_DIR:-}" ]]; then
    echo "$KOLLA_ANSIBLE_DIR"
    return 0
  fi

  if [[ -n "${KOLLA_ANSIBLE_BIN:-}" ]]; then
    local bin_prefix
    bin_prefix=$(cd "$(dirname "$KOLLA_ANSIBLE_BIN")/.." && pwd)
    if [[ -d "$bin_prefix/share/kolla-ansible" ]]; then
      echo "$bin_prefix/share/kolla-ansible"
      return 0
    fi
    if [[ -d "$bin_prefix/local/share/kolla-ansible" ]]; then
      echo "$bin_prefix/local/share/kolla-ansible"
      return 0
    fi
  fi

  local py_path
  py_path=$(python3 -c "
import sys, os
for candidate in [
    '/etc/kolla/.venv/share/kolla-ansible',
    '/usr/local/share/kolla-ansible',
    '/usr/share/kolla-ansible',
]:
    if os.path.isdir(candidate):
        print(candidate)
        sys.exit(0)
sys.exit(1)
" 2>/dev/null) && echo "$py_path" && return 0

  for candidate in /etc/kolla/.venv/share/kolla-ansible /usr/local/share/kolla-ansible /usr/share/kolla-ansible; do
    if [[ -d "$candidate" ]]; then
      echo "$candidate"
      return 0
    fi
  done

  return 1
}

log "kolla-ansible 설치 경로 탐지 중..."
KOLLA_DIR=$(detect_kolla_dir) || die "kolla-ansible 설치 경로를 찾을 수 없습니다. KOLLA_ANSIBLE_DIR 환경변수를 설정하세요."
log "kolla-ansible 경로: $KOLLA_DIR"

remove_symlink_safe() {
  local target="$1"
  local link_path="$2"
  local desc="$3"

  log "$desc 심볼릭 링크 제거 확인 중: $link_path"

  if [[ ! -e "$link_path" && ! -L "$link_path" ]]; then
    log "대상 경로가 존재하지 않음 (skip): $link_path"
    return 0
  fi

  if [[ ! -L "$link_path" ]]; then
    die "제거 거부: $link_path 가 심볼릭 링크가 아닙니다."
  fi

  local current_target
  current_target=$(readlink "$link_path" || true)
  local current_real expected_real
  current_real=$(realpath "$link_path" 2>/dev/null || true)
  expected_real=$(realpath "$target" 2>/dev/null || true)

  if [[ "$current_target" != "$target" ]] && [[ -z "$expected_real" || "$current_real" != "$expected_real" ]]; then
    die "제거 거부: $link_path 가 예상 대상($target)을 가리키지 않습니다 (현재: $current_target)."
  fi

  rm "$link_path" || die "$link_path 심볼릭 링크 제거 실패"
  log "심볼릭 링크 제거 완료: $link_path"
}

ROLES_DIR="$KOLLA_DIR/ansible/roles"
KOLLA_PYTHON=$(command -v python3) || die "python3 실행 파일을 찾을 수 없습니다"
case "$KOLLA_DIR" in
  */local/share/kolla-ansible)
    candidate_kolla_python="${KOLLA_DIR%/local/share/kolla-ansible}/bin/python" ;;
  */share/kolla-ansible)
    candidate_kolla_python="${KOLLA_DIR%/share/kolla-ansible}/bin/python" ;;
  *) candidate_kolla_python="" ;;
esac
if [[ -x "$candidate_kolla_python" ]]; then
  KOLLA_PYTHON="$candidate_kolla_python"
elif [[ "${KOLLA_ANSIBLE_BIN:-}" == /* ]]; then
  candidate_kolla_python="$(dirname "$KOLLA_ANSIBLE_BIN")/python"
  [[ -x "$candidate_kolla_python" ]] && KOLLA_PYTHON="$candidate_kolla_python"
elif candidate_kolla_bin=$(command -v kolla-ansible); then
  candidate_kolla_python="$(dirname "$candidate_kolla_bin")/python"
  [[ -x "$candidate_kolla_python" ]] && KOLLA_PYTHON="$candidate_kolla_python"
fi
AFTERGLOW_PACKAGE_ROOT=$(
  "$KOLLA_PYTHON" -c 'import sysconfig; from pathlib import Path; print(Path(sysconfig.get_path("data")) / "share/afterglow/kolla")'
) || die "Unable to resolve the active Kolla environment's package data directory."
AFTERGLOW_ROLE_TARGET="$AFTERGLOW_PACKAGE_ROOT/ansible/roles/afterglow"
AFTERGLOW_SITE_TARGET="$AFTERGLOW_PACKAGE_ROOT/site.yml"
AFTERGLOW_LEGACY_ROLE_TARGET="${AFTERGLOW_LEGACY_ROLE_TARGET:-}"
AFTERGLOW_LEGACY_SITE_TARGET="${AFTERGLOW_LEGACY_SITE_TARGET:-}"
if [[ -n "$REPO_DIR" ]]; then
  AFTERGLOW_LEGACY_ROLE_TARGET="${AFTERGLOW_LEGACY_ROLE_TARGET:-$REPO_DIR/deploy/kolla/ansible/roles/afterglow}"
  AFTERGLOW_LEGACY_SITE_TARGET="${AFTERGLOW_LEGACY_SITE_TARGET:-$REPO_DIR/deploy/kolla/site.yml}"
fi
for legacy_target_name in AFTERGLOW_LEGACY_ROLE_TARGET AFTERGLOW_LEGACY_SITE_TARGET; do
  legacy_target="${!legacy_target_name}"
  [[ -z "$legacy_target" || "$legacy_target" == /* ]] ||
    die "$legacy_target_name must be an absolute exact legacy symlink target."
done

# Package contents belong to the package manager. Only remove stable wiring
# whose exact target is ours, or the explicitly identified legacy checkout.
check_afterglow_link() {
  local target="$1" link_path="$2" legacy_target="$3"
  if [[ -e "$link_path" || -L "$link_path" ]]; then
    [[ -L "$link_path" ]] || die "Refusing to remove foreign path: $link_path"
    local current_target
    current_target=$(readlink "$link_path")
    if [[ "$current_target" != "$target" ]] &&
       [[ -z "$legacy_target" || "$current_target" != "$legacy_target" ]]; then
      die "Refusing to remove foreign symlink: $link_path -> $current_target. Set AFTERGLOW_LEGACY_ROLE_TARGET and AFTERGLOW_LEGACY_SITE_TARGET to the exact known old targets, or AFTERGLOW_REPO_DIR for a single old checkout."
    fi
  fi
}

remove_afterglow_link() {
  local target="$1" link_path="$2" legacy_target="$3"
  check_afterglow_link "$target" "$link_path" "$legacy_target"
  if [[ -L "$link_path" ]]; then
    rm -- "$link_path" || die "Unable to remove Afterglow wiring: $link_path"
    log "Afterglow asset link removed: $link_path"
  fi
}

check_afterglow_link "$AFTERGLOW_ROLE_TARGET" "$ROLES_DIR/afterglow" "$AFTERGLOW_LEGACY_ROLE_TARGET"
check_afterglow_link "$AFTERGLOW_SITE_TARGET" "$KOLLA_DIR/ansible/afterglow-site.yml" "$AFTERGLOW_LEGACY_SITE_TARGET"

# Remove the site import before its target so an interruption can never leave a
# dangling import in Kolla's stock playbook.
KOLLA_CONFIG_DIR="${KOLLA_CONFIG_PATH:-/etc/kolla}"
MULTINODE_INVENTORY="$KOLLA_CONFIG_DIR/multinode"
DEFAULT_INVENTORY="$KOLLA_CONFIG_DIR/ansible/inventory/all-in-one"
PLUGIN_CONFIG_ROOT="$KOLLA_CONFIG_DIR/config/afterglow"
PLUGIN_GLOBALS="$PLUGIN_CONFIG_ROOT/globals.yml"
PLUGIN_SECRETS="$PLUGIN_CONFIG_ROOT/secrets.yml"
GLOBALS_D="$KOLLA_CONFIG_DIR/globals.d"
STOCK_SITE="$KOLLA_DIR/ansible/site.yml"

[[ -f "$STOCK_SITE" ]] || die "Kolla stock site.yml을 찾을 수 없습니다: $STOCK_SITE"
"$KOLLA_PYTHON" "$SCRIPT_DIR/patch_stock_site.py" remove "$STOCK_SITE" || \
  die "Afterglow stock site.yml import 제거 실패"

# Remove only stable symlinks after the stock import is gone. The private
# package-owned role and aggregate remain installed for future reinstallation.
remove_afterglow_link "$AFTERGLOW_SITE_TARGET" "$KOLLA_DIR/ansible/afterglow-site.yml" "$AFTERGLOW_LEGACY_SITE_TARGET"
remove_afterglow_link "$AFTERGLOW_ROLE_TARGET" "$ROLES_DIR/afterglow" "$AFTERGLOW_LEGACY_ROLE_TARGET"

remove_symlink_safe "$MULTINODE_INVENTORY" "$DEFAULT_INVENTORY" "Kolla default multinode inventory"
remove_symlink_safe "$KOLLA_CONFIG_DIR/group_vars" "$KOLLA_CONFIG_DIR/ansible/inventory/group_vars" "Kolla default group_vars"
remove_symlink_safe "$KOLLA_CONFIG_DIR/host_vars" "$KOLLA_CONFIG_DIR/ansible/inventory/host_vars" "Kolla default host_vars"
remove_symlink_safe "$PLUGIN_GLOBALS" "$GLOBALS_D/90-openstack-afterglow-globals.yml" "Afterglow globals.d override"
remove_symlink_safe "$PLUGIN_SECRETS" "$GLOBALS_D/91-openstack-afterglow-secrets.yml" "Afterglow secrets globals.d override"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Afterglow integration wiring removed."
echo " The installer-owned stock site.yml import, default inventory link, globals.d"
echo " links, and stable Afterglow role/aggregate links were removed."
echo " Package-owned Afterglow assets and sibling roles, multinode inventory,"
echo " plugin configuration, databases, containers, images, and source checkouts"
echo " remain UNTOUCHED."
