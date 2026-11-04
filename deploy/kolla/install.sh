#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────────────────────────────
# afterglow × kolla-ansible integration installer
# Usage: ./deploy/kolla/install.sh
# ─────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${AFTERGLOW_REPO_DIR:-}"
if [[ -z "$REPO_DIR" && "$SCRIPT_DIR" == */deploy/kolla ]]; then
  REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
fi

log()  { echo "[afterglow-install] $*"; }
warn() { echo "[afterglow-install] WARNING: $*" >&2; }
die()  { echo "[afterglow-install] ERROR: $*" >&2; exit 1; }
if [[ -n "$REPO_DIR" ]]; then
  [[ "$REPO_DIR" == /* ]] || die "AFTERGLOW_REPO_DIR must be an absolute checkout path."
  REPO_DIR="${REPO_DIR%/}"
fi

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

# Resolve private package assets using the active Kolla interpreter. The wheel
# never writes into Kolla's stable symlink paths or an operator's checkout.
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
elif [[ "$KOLLA_ANSIBLE_BIN" == /* ]]; then
  candidate_kolla_python="$(dirname "$KOLLA_ANSIBLE_BIN")/python"
  [[ -x "$candidate_kolla_python" ]] && KOLLA_PYTHON="$candidate_kolla_python"
fi
AFTERGLOW_PACKAGE_ROOT=$(
  "$KOLLA_PYTHON" - <<'PY'
import os
import sysconfig
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path

root = Path(sysconfig.get_path("data")) / "share/afterglow/kolla"
try:
    distribution("openstack-afterglow")
except PackageNotFoundError:
    pass
else:
    raise SystemExit(
        "Legacy openstack-afterglow distribution is still installed. "
        "It shares private assets with afterglow-kolla; uninstalling it later can delete the new package's files. "
        "Uninstall openstack-afterglow from this Kolla environment, then force-reinstall "
        "afterglow-kolla from the intended release or source before rerunning install.sh."
    )
dist = distribution("afterglow-kolla")
owned = {Path(os.path.abspath(dist.locate_file(item))) for item in dist.files or ()}
required = (
    "ansible/roles/afterglow/tasks/main.yml",
    "ansible/roles/afterglow/tasks/deploy.yml",
    "ansible/roles/afterglow/defaults/main.yml",
    "ansible/roles/afterglow/templates/afterglow.conf.j2",
    "site.yml",
    "read_locked_version.py",
    "normalize_stock_globals.py",
    "patch_stock_site.py",
    "operator/uv.lock",
)
for relative in required:
    path = root / relative
    if path not in owned or not path.is_file():
        raise SystemExit(f"afterglow-kolla distribution does not own installed asset: {path}")
    for ancestor in (path, *path.parents):
        if ancestor.is_symlink():
            raise SystemExit(f"Refusing symlinked package asset: {ancestor}")
        if ancestor == root:
            break
print(root)
PY
) || die "Install the root afterglow-kolla package into the active Kolla environment with no legacy openstack-afterglow distribution remaining before running install.sh."
AFTERGLOW_ROLE_TARGET="$AFTERGLOW_PACKAGE_ROOT/ansible/roles/afterglow"
AFTERGLOW_SITE_TARGET="$AFTERGLOW_PACKAGE_ROOT/site.yml"
AFTERGLOW_ROLE_LINK="$ROLES_DIR/afterglow"
AFTERGLOW_SITE_LINK="$KOLLA_DIR/ansible/afterglow-site.yml"
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
OPERATOR_LOCK="${AFTERGLOW_OPERATOR_LOCK:-}"
[[ -n "$OPERATOR_LOCK" && -r "$OPERATOR_LOCK" ]] || die "Set AFTERGLOW_OPERATOR_LOCK to the readable operator uv.lock used to sync this Kolla environment."

get_locked_version() {
  local dist="$1"
  local ver
  ver=$("$KOLLA_PYTHON" "$AFTERGLOW_PACKAGE_ROOT/read_locked_version.py" "$OPERATOR_LOCK" "$dist" 2>/dev/null || true)
  if [[ -z "$ver" ]]; then
    die "Failed to determine expected version for $dist from $OPERATOR_LOCK"
  fi
  echo "$ver"
}

DROVER_ROLE_DIR="$ROLES_DIR/drover"
DROVER_LEGACY_ROLE_TARGET="$REPO_DIR/deploy/kolla/ansible/roles/drover"
DROVER_VERSION=$(get_locked_version "drover")
if [[ -L "$DROVER_ROLE_DIR" ]]; then
  current_drover_target=$(readlink "$DROVER_ROLE_DIR" || true)
  if [[ "$current_drover_target" == "$DROVER_LEGACY_ROLE_TARGET" ]]; then
    die "Legacy Afterglow-owned Drover role symlink detected at $DROVER_ROLE_DIR. Verify it points to $DROVER_LEGACY_ROLE_TARGET, remove only that symlink with 'rm -- $DROVER_ROLE_DIR', then run 'UV_PROJECT_ENVIRONMENT=/etc/kolla/.venv uv sync --inexact --no-install-project' in deploy/kolla/operator before rerunning install.sh."
  fi
  die "Unexpected Drover role symlink at $DROVER_ROLE_DIR -> $current_drover_target. Refusing to replace or remove it."
elif [[ ! -d "$DROVER_ROLE_DIR" ||
        ! -f "$DROVER_ROLE_DIR/tasks/main.yml" ||
        ! -f "$DROVER_ROLE_DIR/tasks/deploy.yml" ||
        ! -f "$DROVER_ROLE_DIR/defaults/main.yml" ||
        ! -f "$DROVER_ROLE_DIR/templates/drover.conf.j2" ]]; then
  die "Drover role missing or invalid at $DROVER_ROLE_DIR. Install drover==$DROVER_VERSION into the active Kolla environment with 'UV_PROJECT_ENVIRONMENT=/etc/kolla/.venv uv sync --inexact --no-install-project' in deploy/kolla/operator."
fi
installed_drover_version=$(
  "$KOLLA_PYTHON" -c 'from importlib.metadata import version; print(version("drover"))' 2>/dev/null || true
)
[[ "$installed_drover_version" == "$DROVER_VERSION" ]] ||
  die "Expected drover==$DROVER_VERSION in the active Kolla environment, found '${installed_drover_version:-not installed}'."
log "Drover role verified at $DROVER_ROLE_DIR (drover==$installed_drover_version)"

LUMEN_ROLE_DIR="$ROLES_DIR/lumen"
LUMEN_LEGACY_ROLE_TARGET="$REPO_DIR/deploy/kolla/ansible/roles/lumen"
LUMEN_VERSION=$(get_locked_version "lumen")
if [[ -L "$LUMEN_ROLE_DIR" ]]; then
  current_lumen_target=$(readlink "$LUMEN_ROLE_DIR" || true)
  if [[ "$current_lumen_target" == "$LUMEN_LEGACY_ROLE_TARGET" ]]; then
    die "Legacy Afterglow-owned Lumen role symlink detected at $LUMEN_ROLE_DIR. Verify it points to $LUMEN_LEGACY_ROLE_TARGET, remove only that symlink with 'rm -- $LUMEN_ROLE_DIR', then run 'UV_PROJECT_ENVIRONMENT=/etc/kolla/.venv uv sync --inexact --no-install-project' in deploy/kolla/operator before rerunning install.sh."
  fi
  die "Unexpected Lumen role symlink at $LUMEN_ROLE_DIR -> $current_lumen_target. Refusing to replace or remove it."
elif [[ ! -d "$LUMEN_ROLE_DIR" ||
        ! -f "$LUMEN_ROLE_DIR/tasks/main.yml" ||
        ! -f "$LUMEN_ROLE_DIR/tasks/deploy.yml" ||
        ! -f "$LUMEN_ROLE_DIR/defaults/main.yml" ||
        ! -f "$LUMEN_ROLE_DIR/templates/lumen.conf.j2" ]]; then
  die "Lumen role missing or invalid at $LUMEN_ROLE_DIR. Install lumen==$LUMEN_VERSION into the active Kolla environment with 'UV_PROJECT_ENVIRONMENT=/etc/kolla/.venv uv sync --inexact --no-install-project' in deploy/kolla/operator."
fi
installed_lumen_version=$(
  "$KOLLA_PYTHON" -c 'from importlib.metadata import version; print(version("lumen"))' 2>/dev/null || true
)
[[ "$installed_lumen_version" == "$LUMEN_VERSION" ]] ||
  die "Expected lumen==$LUMEN_VERSION in the active Kolla environment, found '${installed_lumen_version:-not installed}'."
log "Lumen role verified at $LUMEN_ROLE_DIR (lumen==$installed_lumen_version)"

WAYGATE_ROLE_DIR="$ROLES_DIR/waygate"
WAYGATE_LEGACY_ROLE_TARGET="$REPO_DIR/deploy/kolla/ansible/roles/waygate"
WAYGATE_VERSION=$(get_locked_version "waygate")
if [[ -L "$WAYGATE_ROLE_DIR" ]]; then
  current_waygate_target=$(readlink "$WAYGATE_ROLE_DIR" || true)
  if [[ "$current_waygate_target" == "$WAYGATE_LEGACY_ROLE_TARGET" ]]; then
    die "Legacy Afterglow-owned Waygate role symlink detected at $WAYGATE_ROLE_DIR. Verify it points to $WAYGATE_LEGACY_ROLE_TARGET, remove only that symlink with 'rm -- $WAYGATE_ROLE_DIR', then run 'UV_PROJECT_ENVIRONMENT=/etc/kolla/.venv uv sync --inexact --no-install-project' in deploy/kolla/operator before rerunning install.sh."
  fi
  die "Unexpected Waygate role symlink at $WAYGATE_ROLE_DIR -> $current_waygate_target. Refusing to replace or remove it."
elif [[ ! -d "$WAYGATE_ROLE_DIR" ||
        ! -f "$WAYGATE_ROLE_DIR/tasks/main.yml" ||
        ! -f "$WAYGATE_ROLE_DIR/tasks/deploy.yml" ||
        ! -f "$WAYGATE_ROLE_DIR/defaults/main.yml" ||
        ! -f "$WAYGATE_ROLE_DIR/templates/waygate.conf.j2" ]]; then
  die "Waygate role missing or invalid at $WAYGATE_ROLE_DIR. Install waygate==$WAYGATE_VERSION into the active Kolla environment with 'UV_PROJECT_ENVIRONMENT=/etc/kolla/.venv uv sync --inexact --no-install-project' in deploy/kolla/operator."
fi
installed_waygate_version=$(
  "$KOLLA_PYTHON" -c 'from importlib.metadata import version; print(version("waygate"))' 2>/dev/null || true
)
[[ "$installed_waygate_version" == "$WAYGATE_VERSION" ]] ||
  die "Expected waygate==$WAYGATE_VERSION in the active Kolla environment, found '${installed_waygate_version:-not installed}'."
log "Waygate role verified at $WAYGATE_ROLE_DIR (waygate==$installed_waygate_version)"

PALIMPSEST_ROLE_DIR="$ROLES_DIR/palimpsest"
PALIMPSEST_LEGACY_ROLE_TARGET="$REPO_DIR/deploy/kolla/ansible/roles/palimpsest"
PALIMPSEST_VERSION=$(get_locked_version "palimpsest-client")
# palimpsest-client replaced palimpsest-local and installs the same role files.
# A leftover old distribution would later delete them on uninstall, so refuse it.
legacy_palimpsest_version=$(
  "$KOLLA_PYTHON" -c 'from importlib.metadata import version; print(version("palimpsest-local"))' 2>/dev/null || true
)
[[ -z "$legacy_palimpsest_version" ]] ||
  die "Retired distribution palimpsest-local==$legacy_palimpsest_version is still installed in the active Kolla environment and shares the Palimpsest role files. Run 'uv pip uninstall --python $KOLLA_PYTHON palimpsest-local', then 'UV_PROJECT_ENVIRONMENT=/etc/kolla/.venv uv sync --locked --inexact --no-install-project --reinstall-package palimpsest-client' in deploy/kolla/operator before rerunning install.sh."
if [[ -L "$PALIMPSEST_ROLE_DIR" ]]; then
  current_palimpsest_target=$(readlink "$PALIMPSEST_ROLE_DIR" || true)
  if [[ "$current_palimpsest_target" == "$PALIMPSEST_LEGACY_ROLE_TARGET" ]]; then
    die "Legacy Afterglow-owned Palimpsest role symlink detected at $PALIMPSEST_ROLE_DIR. Verify it points to $PALIMPSEST_LEGACY_ROLE_TARGET, remove only that symlink with 'rm -- $PALIMPSEST_ROLE_DIR', then run 'UV_PROJECT_ENVIRONMENT=/etc/kolla/.venv uv sync --inexact --no-install-project' in deploy/kolla/operator before rerunning install.sh."
  fi
  die "Unexpected Palimpsest role symlink at $PALIMPSEST_ROLE_DIR -> $current_palimpsest_target. Refusing to replace or remove it."
elif [[ ! -d "$PALIMPSEST_ROLE_DIR" ||
        ! -f "$PALIMPSEST_ROLE_DIR/tasks/main.yml" ||
        ! -f "$PALIMPSEST_ROLE_DIR/tasks/deploy.yml" ||
        ! -f "$PALIMPSEST_ROLE_DIR/defaults/main.yml" ||
        ! -f "$PALIMPSEST_ROLE_DIR/templates/palimpsest.conf.j2" ]]; then
  die "Palimpsest role missing or invalid at $PALIMPSEST_ROLE_DIR. Install palimpsest-client==$PALIMPSEST_VERSION into the active Kolla environment with 'UV_PROJECT_ENVIRONMENT=/etc/kolla/.venv uv sync --inexact --no-install-project' in deploy/kolla/operator."
fi
installed_palimpsest_version=$(
  "$KOLLA_PYTHON" -c 'from importlib.metadata import version; print(version("palimpsest-client"))' 2>/dev/null || true
)
[[ "$installed_palimpsest_version" == "$PALIMPSEST_VERSION" ]] ||
  die "Expected palimpsest-client==$PALIMPSEST_VERSION in the active Kolla environment, found '${installed_palimpsest_version:-not installed}'."
log "Palimpsest role verified at $PALIMPSEST_ROLE_DIR (palimpsest-client==$installed_palimpsest_version)"

# Preflight both stable paths before changing either. Match link text exactly:
# an unrelated link that happens to resolve to the same file is not ours.
check_afterglow_link() {
  local target="$1" link_path="$2" legacy_target="$3"
  if [[ -e "$link_path" || -L "$link_path" ]]; then
    [[ -L "$link_path" ]] || die "Refusing to replace foreign path: $link_path"
    local current_target
    current_target=$(readlink "$link_path")
    if [[ "$current_target" != "$target" ]] &&
       [[ -z "$legacy_target" || "$current_target" != "$legacy_target" ]]; then
      die "Refusing to replace foreign symlink: $link_path -> $current_target. Set AFTERGLOW_LEGACY_ROLE_TARGET and AFTERGLOW_LEGACY_SITE_TARGET to the exact known old targets, or AFTERGLOW_REPO_DIR for a single old checkout."
    fi
  fi
}

install_afterglow_link() {
  local target="$1" link_path="$2" legacy_target="$3"
  check_afterglow_link "$target" "$link_path" "$legacy_target"
  if [[ -L "$link_path" && "$(readlink "$link_path")" == "$target" ]]; then
    log "Package asset link already installed: $link_path"
    return 0
  fi
  # os.replace replaces the symlink itself, including a link to a directory;
  # portable mv implementations can instead follow that directory symlink.
  "$KOLLA_PYTHON" - "$target" "$link_path" "$legacy_target" <<'PY'
import os
import sys
import tempfile
from pathlib import Path

target, link, legacy = sys.argv[1:]
with tempfile.TemporaryDirectory(prefix=".afterglow-link-", dir=Path(link).parent) as directory:
    temporary = Path(directory) / "link"
    os.symlink(target, temporary)
    if os.path.lexists(link):
        if not os.path.islink(link) or os.readlink(link) not in {target, legacy}:
            raise SystemExit(f"Refusing changed foreign path: {link}")
    os.replace(temporary, link)
PY
  log "Package asset link installed: $link_path -> $target"
}

check_afterglow_link "$AFTERGLOW_ROLE_TARGET" "$AFTERGLOW_ROLE_LINK" "$AFTERGLOW_LEGACY_ROLE_TARGET"
check_afterglow_link "$AFTERGLOW_SITE_TARGET" "$AFTERGLOW_SITE_LINK" "$AFTERGLOW_LEGACY_SITE_TARGET"
install_afterglow_link "$AFTERGLOW_ROLE_TARGET" "$AFTERGLOW_ROLE_LINK" "$AFTERGLOW_LEGACY_ROLE_TARGET"
install_afterglow_link "$AFTERGLOW_SITE_TARGET" "$AFTERGLOW_SITE_LINK" "$AFTERGLOW_LEGACY_SITE_TARGET"

# A prior manual installation appended the complete plugin globals as a second
# YAML document. Kolla accepts only one document for -e @globals.yml. Remove
# that exact duplicate only after proving it matches the plugin-owned source.
"$KOLLA_PYTHON" "$AFTERGLOW_PACKAGE_ROOT/normalize_stock_globals.py" \
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
"$KOLLA_PYTHON" "$AFTERGLOW_PACKAGE_ROOT/patch_stock_site.py" install "$STOCK_SITE" || \
  die "Afterglow stock site.yml import 설치 실패"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Afterglow and sibling package-owned Kolla assets integrated."
echo " The installer owns only its marked stock site.yml import, default"
echo " inventory link, globals.d links, and stable Afterglow role/playbook links."
echo " All service role contents and the aggregate playbook are package-owned."
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
