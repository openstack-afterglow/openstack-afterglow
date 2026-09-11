#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────────────────────────────
# afterglow × kolla-ansible integration installer
# Usage: ./deploy/kolla/install.sh
# ─────────────────────────────────────────────────────────────────────────────

REPO_DIR="${AFTERGLOW_REPO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd ../.. && pwd)}"

log()  { echo "[afterglow-install] $*"; }
warn() { echo "[afterglow-install] WARNING: $*" >&2; }
die()  { echo "[afterglow-install] ERROR: $*" >&2; exit 1; }

# ── 1. kolla-ansible 설치 경로 및 실행 파일 탐지 ─────────────────────────────
detect_kolla_bin() {
  if [[ -n "${KOLLA_ANSIBLE_BIN:-}" ]]; then
    echo "$KOLLA_ANSIBLE_BIN"
    return 0
  fi

  local candidate
  candidate=$(command -v kolla-ansible || true)
  if [[ -n "$candidate" && -x "$candidate" ]]; then
    echo "$candidate"
    return 0
  fi

  for bin_path in /etc/kolla/.venv/bin/kolla-ansible /usr/local/bin/kolla-ansible /usr/bin/kolla-ansible; do
    if [[ -x "$bin_path" ]]; then
      echo "$bin_path"
      return 0
    fi
  done

  return 1
}

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

log "kolla-ansible 탐지 중..."
KOLLA_ANSIBLE_BIN=$(detect_kolla_bin) || warn "kolla-ansible 실행 파일을 자동으로 찾지 못했습니다. KOLLA_ANSIBLE_BIN을 직접 지정할 수 있습니다."
if [[ -n "${KOLLA_ANSIBLE_BIN:-}" && -x "$KOLLA_ANSIBLE_BIN" ]]; then
  log "kolla-ansible 실행 파일: $KOLLA_ANSIBLE_BIN"
fi

KOLLA_DIR=$(detect_kolla_dir) || die "kolla-ansible 설치 경로를 찾을 수 없습니다. KOLLA_ANSIBLE_DIR 환경변수를 설정하세요."
log "kolla-ansible 경로: $KOLLA_DIR"

ROLES_DIR="$KOLLA_DIR/ansible/roles"
if [[ ! -d "$ROLES_DIR" ]]; then
  die "kolla-ansible roles 디렉토리를 찾을 수 없습니다: $ROLES_DIR"
fi

# ── 2. 심볼릭 링크 생성 및 Role 검증 ─────────────────────────────────────────
#
# 규칙: 대상 경로가 이미 존재하는 경우,
#   - 심볼릭 링크이고 정산 대상($expected_target)을 가리키면 유지 (skip)
#   - 심볼릭 링크가 아니거나 타겟이 다르면 교체 없이 실패 (die)

create_symlink_safe() {
  local target="$1"
  local link_path="$2"
  local desc="$3"

  log "$desc 심볼릭 링크 확인 중: $link_path -> $target"

  if [[ -e "$link_path" || -L "$link_path" ]]; then
    if [[ -L "$link_path" ]]; then
      local current_target
      current_target=$(readlink "$link_path" || true)
      local current_real expected_real
      current_real=$(realpath "$link_path" 2>/dev/null || true)
      expected_real=$(realpath "$target" 2>/dev/null || true)

      if [[ "$current_target" == "$target" ]] || [[ -n "$expected_real" && "$current_real" == "$expected_real" ]]; then
        log "기존 심볼릭 링크가 정상 가리킴: $link_path"
        return 0
      fi
    fi
    die "충돌 발생: $link_path 가 이미 존재하며 예상 대상($target)을 가리키는 심볼릭 링크가 아닙니다."
  fi

  ln -s "$target" "$link_path" || die "$link_path 심볼릭 링크 생성 실패"
  log "심볼릭 링크 생성 완료: $link_path -> $target"
}


# Standard Kolla invocation wiring. Kolla resolves its default inventory as
# /etc/kolla/ansible/inventory/all-in-one and always loads globals.d after the
# stock globals/passwords files. Keep the plugin-owned files authoritative.
KOLLA_CONFIG_DIR="${KOLLA_CONFIG_PATH:-/etc/kolla}"
MULTINODE_INVENTORY="$KOLLA_CONFIG_DIR/multinode"
DEFAULT_INVENTORY="$KOLLA_CONFIG_DIR/ansible/inventory/all-in-one"
PLUGIN_CONFIG_ROOT="$KOLLA_CONFIG_DIR/config/afterglow"
PLUGIN_GLOBALS="$PLUGIN_CONFIG_ROOT/globals.yml"
PLUGIN_SECRETS="$PLUGIN_CONFIG_ROOT/secrets.yml"
GLOBALS_D="$KOLLA_CONFIG_DIR/globals.d"
STOCK_SITE="$KOLLA_DIR/ansible/site.yml"

[[ -r "$MULTINODE_INVENTORY" ]] || die "Kolla multinode inventory를 읽을 수 없습니다: $MULTINODE_INVENTORY"
[[ -r "$PLUGIN_GLOBALS" ]] || die "Afterglow globals를 읽을 수 없습니다: $PLUGIN_GLOBALS"
[[ -r "$PLUGIN_SECRETS" ]] || die "Afterglow secrets를 읽을 수 없습니다: $PLUGIN_SECRETS"
[[ -r "$KOLLA_CONFIG_DIR/globals.yml" ]] || die "Kolla globals.yml을 읽을 수 없습니다: $KOLLA_CONFIG_DIR/globals.yml"
[[ -f "$STOCK_SITE" ]] || die "Kolla stock site.yml을 찾을 수 없습니다: $STOCK_SITE"

# Verify the package-installed Drover role and its distribution metadata.
KOLLA_PYTHON=$(command -v python3) || die "python3 실행 파일을 찾을 수 없습니다"
if [[ "$KOLLA_ANSIBLE_BIN" == /* ]]; then
  candidate_kolla_python="$(dirname "$KOLLA_ANSIBLE_BIN")/python"
  [[ -x "$candidate_kolla_python" ]] && KOLLA_PYTHON="$candidate_kolla_python"
fi

DROVER_ROLE_DIR="$ROLES_DIR/drover"
DROVER_LEGACY_ROLE_TARGET="$REPO_DIR/deploy/kolla/ansible/roles/drover"
DROVER_KOLLA_VERSION="0.2.19"
if [[ -L "$DROVER_ROLE_DIR" ]]; then
  current_drover_target=$(readlink "$DROVER_ROLE_DIR" || true)
  if [[ "$current_drover_target" == "$DROVER_LEGACY_ROLE_TARGET" ]]; then
    die "Legacy Afterglow-owned Drover role symlink detected at $DROVER_ROLE_DIR. Verify it points to $DROVER_LEGACY_ROLE_TARGET, remove only that symlink with 'rm -- $DROVER_ROLE_DIR', then run 'UV_PROJECT_ENVIRONMENT=/etc/kolla/.venv uv sync --frozen --inexact --no-install-project' in deploy/kolla/operator before rerunning install.sh."
  fi
  die "Unexpected Drover role symlink at $DROVER_ROLE_DIR -> $current_drover_target. Refusing to replace or remove it."
elif [[ ! -d "$DROVER_ROLE_DIR" ||
        ! -f "$DROVER_ROLE_DIR/tasks/main.yml" ||
        ! -f "$DROVER_ROLE_DIR/tasks/deploy.yml" ||
        ! -f "$DROVER_ROLE_DIR/defaults/main.yml" ||
        ! -f "$DROVER_ROLE_DIR/templates/drover.conf.j2" ]]; then
  die "Drover role missing or invalid at $DROVER_ROLE_DIR. Install drover-kolla==$DROVER_KOLLA_VERSION into the active Kolla environment with 'UV_PROJECT_ENVIRONMENT=/etc/kolla/.venv uv sync --frozen --inexact --no-install-project' in deploy/kolla/operator."
fi
installed_drover_kolla_version=$(
  "$KOLLA_PYTHON" -c 'from importlib.metadata import version; print(version("drover-kolla"))' 2>/dev/null || true
)
[[ "$installed_drover_kolla_version" == "$DROVER_KOLLA_VERSION" ]] ||
  die "Expected drover-kolla==$DROVER_KOLLA_VERSION in the active Kolla environment, found '${installed_drover_kolla_version:-not installed}'."
log "Drover role verified at $DROVER_ROLE_DIR (drover-kolla==$installed_drover_kolla_version)"

LUMEN_ROLE_DIR="$ROLES_DIR/lumen"
LUMEN_LEGACY_ROLE_TARGET="$REPO_DIR/deploy/kolla/ansible/roles/lumen"
LUMEN_KOLLA_VERSION="0.2.0"
if [[ -L "$LUMEN_ROLE_DIR" ]]; then
  current_lumen_target=$(readlink "$LUMEN_ROLE_DIR" || true)
  if [[ "$current_lumen_target" == "$LUMEN_LEGACY_ROLE_TARGET" ]]; then
    die "Legacy Afterglow-owned Lumen role symlink detected at $LUMEN_ROLE_DIR. Verify it points to $LUMEN_LEGACY_ROLE_TARGET, remove only that symlink with 'rm -- $LUMEN_ROLE_DIR', then run 'UV_PROJECT_ENVIRONMENT=/etc/kolla/.venv uv sync --frozen --inexact --no-install-project' in deploy/kolla/operator before rerunning install.sh."
  fi
  die "Unexpected Lumen role symlink at $LUMEN_ROLE_DIR -> $current_lumen_target. Refusing to replace or remove it."
elif [[ ! -d "$LUMEN_ROLE_DIR" ||
        ! -f "$LUMEN_ROLE_DIR/tasks/main.yml" ||
        ! -f "$LUMEN_ROLE_DIR/tasks/deploy.yml" ||
        ! -f "$LUMEN_ROLE_DIR/defaults/main.yml" ||
        ! -f "$LUMEN_ROLE_DIR/templates/lumen.conf.j2" ]]; then
  die "Lumen role missing or invalid at $LUMEN_ROLE_DIR. Install lumen-kolla==$LUMEN_KOLLA_VERSION into the active Kolla environment with 'UV_PROJECT_ENVIRONMENT=/etc/kolla/.venv uv sync --frozen --inexact --no-install-project' in deploy/kolla/operator."
fi
installed_lumen_kolla_version=$(
  "$KOLLA_PYTHON" -c 'from importlib.metadata import version; print(version("lumen-kolla"))' 2>/dev/null || true
)
[[ "$installed_lumen_kolla_version" == "$LUMEN_KOLLA_VERSION" ]] ||
  die "Expected lumen-kolla==$LUMEN_KOLLA_VERSION in the active Kolla environment, found '${installed_lumen_kolla_version:-not installed}'."
log "Lumen role verified at $LUMEN_ROLE_DIR (lumen-kolla==$installed_lumen_kolla_version)"

# Role symlinks (Afterglow, Waygate, Palimpsest)
create_symlink_safe "$REPO_DIR/deploy/kolla/ansible/roles/afterglow" "$ROLES_DIR/afterglow" "afterglow role"
create_symlink_safe "$REPO_DIR/deploy/kolla/ansible/roles/waygate" "$ROLES_DIR/waygate" "waygate role"
create_symlink_safe "$REPO_DIR/deploy/kolla/ansible/roles/palimpsest" "$ROLES_DIR/palimpsest" "palimpsest role"

# Aggregate playbook symlink (afterglow-site.yml)
create_symlink_safe "$REPO_DIR/deploy/kolla/site.yml" "$KOLLA_DIR/ansible/afterglow-site.yml" "aggregate afterglow-site.yml playbook"

# A prior manual installation appended the complete plugin globals as a second
# YAML document. Kolla accepts only one document for -e @globals.yml. Remove
# that exact duplicate only after proving it matches the plugin-owned source.
"$KOLLA_PYTHON" "$REPO_DIR/deploy/kolla/normalize_stock_globals.py" \
  "$KOLLA_CONFIG_DIR/globals.yml" \
  "$PLUGIN_GLOBALS" \
  "$KOLLA_CONFIG_DIR/globals.yml.before-afterglow-dedup" || \
  die "Kolla globals.yml 중복 Afterglow 문서 정리 실패"
mkdir -p "$KOLLA_CONFIG_DIR/ansible/inventory"

# Preserve Kolla's normal inventory-relative host_vars/group_vars discovery
# when its default all-in-one path is redirected to the multinode file.
for inventory_vars_dir in group_vars host_vars; do
  source_vars_dir="$KOLLA_CONFIG_DIR/$inventory_vars_dir"
  target_vars_dir="$KOLLA_CONFIG_DIR/ansible/inventory/$inventory_vars_dir"
  if [[ -d "$source_vars_dir" ]]; then
    create_symlink_safe "$source_vars_dir" "$target_vars_dir" "Kolla default $inventory_vars_dir"
  elif [[ -e "$target_vars_dir" || -L "$target_vars_dir" ]]; then
    die "Kolla default $inventory_vars_dir exists but $source_vars_dir is absent"
  fi
done
mkdir -p "$(dirname "$DEFAULT_INVENTORY")" "$GLOBALS_D"
create_symlink_safe "$MULTINODE_INVENTORY" "$DEFAULT_INVENTORY" "Kolla default multinode inventory"
create_symlink_safe "$PLUGIN_GLOBALS" "$GLOBALS_D/90-openstack-afterglow-globals.yml" "Afterglow globals.d override"
create_symlink_safe "$PLUGIN_SECRETS" "$GLOBALS_D/91-openstack-afterglow-secrets.yml" "Afterglow secrets globals.d override"
python3 "$REPO_DIR/deploy/kolla/patch_stock_site.py" install "$STOCK_SITE" || \
  die "Afterglow stock site.yml import 설치 실패"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Afterglow, Waygate, Drover (package-installed), Lumen (package-installed), and Palimpsest integration wiring installed."
echo " The installer owns only its marked stock site.yml import, default"
echo " inventory link, globals.d links, source role links (afterglow, waygate,"
echo " palimpsest), and aggregate playbook link. Drover and Lumen roles are package-owned."
echo ""
echo " Activate the Kolla virtualenv, then from $KOLLA_CONFIG_DIR deploy with:"
echo " kolla-ansible deploy -i multinode"
echo " Custom service and HAProxy plays request sudo; CLI --become is not required."
echo ""
echo " For a service-scoped configuration update, use:"
echo " kolla-ansible reconfigure \\"
echo "   -i $MULTINODE_INVENTORY \\"
echo "   --tags afterglow"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
