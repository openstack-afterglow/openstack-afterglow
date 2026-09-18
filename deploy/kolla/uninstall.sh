#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────────────────────────────
# afterglow × kolla-ansible integration uninstaller
# Usage: ./deploy/kolla/uninstall.sh
# ─────────────────────────────────────────────────────────────────────────────

REPO_DIR="${AFTERGLOW_REPO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd ../.. && pwd)}"

log()  { echo "[afterglow-uninstall] $*"; }
warn() { echo "[afterglow-uninstall] WARNING: $*" >&2; }
die()  { echo "[afterglow-uninstall] ERROR: $*" >&2; exit 1; }

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
python3 "$REPO_DIR/deploy/kolla/patch_stock_site.py" remove "$STOCK_SITE" || \
  die "Afterglow stock site.yml import 제거 실패"

# Remove aggregate playbook link after its stock import is gone.
remove_symlink_safe "$REPO_DIR/deploy/kolla/site.yml" "$KOLLA_DIR/ansible/afterglow-site.yml" "aggregate afterglow-site.yml playbook"

# Remove the Afterglow source role link (Drover, Lumen, Waygate, and Palimpsest roles are package-installed via their kolla packages).
remove_symlink_safe "$REPO_DIR/deploy/kolla/ansible/roles/afterglow" "$ROLES_DIR/afterglow" "afterglow role"

remove_symlink_safe "$MULTINODE_INVENTORY" "$DEFAULT_INVENTORY" "Kolla default multinode inventory"
remove_symlink_safe "$KOLLA_CONFIG_DIR/group_vars" "$KOLLA_CONFIG_DIR/ansible/inventory/group_vars" "Kolla default group_vars"
remove_symlink_safe "$KOLLA_CONFIG_DIR/host_vars" "$KOLLA_CONFIG_DIR/ansible/inventory/host_vars" "Kolla default host_vars"
remove_symlink_safe "$PLUGIN_GLOBALS" "$GLOBALS_D/90-openstack-afterglow-globals.yml" "Afterglow globals.d override"
remove_symlink_safe "$PLUGIN_SECRETS" "$GLOBALS_D/91-openstack-afterglow-secrets.yml" "Afterglow secrets globals.d override"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Afterglow integration wiring removed."
echo " The installer-owned stock site.yml import, default inventory link, globals.d"
echo " links, and Afterglow source role link were removed."
echo " Package-installed root roles (drover, lumen, waygate, palimpsest-local),"
echo " multinode inventory, plugin configuration, databases, containers, images,"
echo " and source checkouts remain UNTOUCHED."
