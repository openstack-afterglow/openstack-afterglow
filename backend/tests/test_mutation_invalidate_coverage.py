"""AST-based static check: all mutation routers must call cache invalidation.

Scope: scans every *.py under app/api/ and flags POST/PUT/PATCH/DELETE
handlers that contain no invalidation call.

Exemption tiers:
- EXEMPT_ROUTERS  : file-level (relative path from app/api/) — pending phases or
                    truly no-cache domains.
- EXEMPT_HANDLERS : handler-level (function name) — individual functions that
                    genuinely do not touch any cached resource state.
- INVALIDATING_HELPERS : function names that are known to call invalidation
                    internally; any handler that delegates to one of these is
                    treated as covered (e.g. _simple_action).
"""

import ast
from pathlib import Path

import pytest

API_DIR = Path(__file__).parent.parent / "app" / "api"

# ---------------------------------------------------------------------------
# File-level exemptions (relative path from API_DIR, e.g. "compute/images.py")
# ---------------------------------------------------------------------------
EXEMPT_ROUTERS: set[str] = {
    # Infrastructure / not-a-mutation
    "deps.py",
    # Auth & session — no OS resource cache to invalidate
    "identity/auth.py",
    "identity/profile.py",
    "identity/profile_activity.py",
    # Health / callback — not user-facing resource mutations
    "k3s/health.py",
    "compute/instance_health.py",
    "k3s/callback.py",
    # Validation utility endpoint — not a state-mutating operation
    "common/libraries.py",
    # Admin-only operations — manage OS infra directly; user-facing cache keys
    # are scoped per-project and not affected by these admin actions.
    "identity/admin.py",
    "identity/admin_flavors.py",
    "identity/admin_identity.py",
    "identity/admin_images.py",
    "identity/admin_instances.py",
    "identity/admin_gpu.py",
    "identity/admin_notion.py",
    "identity/admin_orphans.py",
    "identity/admin_services.py",
    "identity/admin_dashboard.py",  # admin bulk action — manages OS infra directly, not per-project cache
    "identity/admin_worker_runtime.py",  # admin-only worker desired state; no per-project OS resource cache
    # ------------------------------------------------------------------
    # Phase C/D TODO — cache not yet wired up in these modules.
    # Remove each entry as the corresponding phase lands.
    # ------------------------------------------------------------------
    "compute/images.py",  # TODO: Phase C/D — image cache
    "container/clusters.py",  # TODO: Phase C/D — Magnum
    "container/containers.py",  # TODO: Phase C/D — Zun
    "database/instances.py",  # TODO: Phase C/D — Trove
    "k3s/clusters.py",  # TODO: Phase C/D — k3s
    "k3s/certificates.py",  # TODO: Phase C/D — k3s cert rotation, no k3s resource cache yet
    "k3s/configmaps.py",  # TODO: Phase C/D — k3s configmap ops
    "k3s/k3s_services.py",  # TODO: Phase C/D — k3s service ops
    "k3s/nodegroups.py",  # TODO: Phase C/D — k3s nodegroup ops
    "k3s/pods.py",  # TODO: Phase C/D — k3s pod ops
    "k3s/secrets.py",  # TODO: Phase C/D — k3s secret ops
    "k3s/shell.py",  # ephemeral shell ticket — no OS resource cache state
    "k3s/templates.py",  # TODO: Phase C/D — k3s cluster templates
    "k3s/workloads.py",  # TODO: Phase C/D — k3s workload ops
    "union/layers.py",  # TODO: Phase C/D — Union layers
    "union/layer_ops.py",  # TODO: Phase C/D — Union layer build/seal ops (캐시 무효화 미연동)
    "network/loadbalancers.py",  # TODO: Phase C/D — listener/pool/member sub-resources
    "network/networks.py",  # TODO: Phase C/D — floating_ip / subnet sub-resources
    "network/routers.py",  # TODO: Phase C/D — interface / gateway sub-resources
    "object_storage/containers.py",  # TODO: Phase C/D — Swift object storage
    "object_storage/upload.py",  # TODO: Phase C/D — Swift upload
    "storage/file_storage.py",  # TODO: Phase C/D — access rule sub-resources
    "storage/volumes.py",  # TODO: Phase C/D — volume transfer sub-resources
    "storage/volume_backups.py",  # TODO: Phase C/D — backup / restore
    # Permanent Waygate guest callbacks proxy into the extracted service and
    # therefore do not mutate Afterglow's OpenStack resource cache.
    "waygate/agent.py",
    # Palimpsest hub owns its own tables (palimpsest_hub_layers / _uploads) and a
    # content-addressed blob store. Nothing caches hub responses, so there is no
    # namespace to invalidate. Note the contrast with palimpsest/admin.py, whose
    # backfill DOES invalidate `afterglow:union_layer:*` because it mutates
    # layer_artifacts rows that the layer listing cache serves.
    "palimpsest/hub.py",
    # Admin resource policy routes own application data read directly from
    # their stores; no OpenStack cache key is affected.
    "identity/admin_resource_policies.py",
    # MCP OAuth/control-plane state is DB-backed and bypasses app resource caches.
    "mcp.py",
    "identity/mcp_access.py",
}

# ---------------------------------------------------------------------------
# Handler-level exemptions (function name) — individual functions in otherwise
# scoped files that legitimately do not need cache invalidation.
# ---------------------------------------------------------------------------
EXEMPT_HANDLERS: set[str] = {
    # QGA password reset via Nova compute API — does not alter any field that
    # is stored in the instance cache (status, metadata, etc.).
    "set_admin_password",
    # Project / invitation membership operations — identity state managed in
    # Keystone + DB. No per-project resource cache keys are keyed on membership
    # or invitation data, so cache invalidation is not applicable here.
    "create_project",
    "create_invitation",
    "revoke_invitation",
    "promote_manager",
    "demote_manager",
    "accept_invitation",
    "decline_invitation",
    # Barbican ACL / quota operations — state is owned by the Barbican service.
    # These mutations do not affect any local resource-cache keys, so local
    # cache invalidation is not applicable here.
    "set_project_quota",
    "delete_project_quota",
    "set_secret_acl",
    "delete_secret_acl",
    "set_container_acl",
    # Site branding POST/DELETE mutate DB-backed public branding assets, not a
    # per-project OpenStack resource cache tracked by mutation counts.
    "upload_site_branding_asset",
    "reset_site_branding_asset",
    # Announcements (admin CRUD + user read-receipt) mutate a DB-backed
    # resource read straight from the DB on every request (no cached_call /
    # app cache layer involved), not a per-project OpenStack resource cache
    # tracked by mutation counts — mirrors the site branding exemption above.
    "create_announcement_endpoint",
    "update_announcement_endpoint",
    "delete_announcement_endpoint",
    # Palimpsest inline Dockerfile build: the handler only creates a LayerImportJob
    # row. Artifacts and profiles appear later, inside run_dockerfile_import_job,
    # which is where `afterglow:union_layer:*` is invalidated. Invalidating at
    # request time would clear the cache before anything changed.
    "build_from_inline_dockerfile",
    # Plan preview is read-only despite being POST (the body carries the Dockerfile).
    "preview_inline_dockerfile_plan",
    "mark_announcement_read",
    # 사용자별 튜토리얼(투어) 진행 이력 upsert — DB에서 매 요청 직접 읽는 per-user 상태로,
    # cached_call/app 캐시 레이어를 거치지 않으며 per-project OpenStack 리소스 캐시와도
    # 무관하다(announcements 읽음표시와 동일 사유).
    "set_my_tutorial_status",
    # Chat agent, memory, and workspace mutations are DB-backed application
    # state read directly by their stores; no per-project OpenStack resource
    # cache or mutation-count key exists for them.
    "clone_agent",
    "create_agent",
    "delete_agent",
    "update_agent",
    "create_memory",
    "delete_memory",
    "update_memory",
    "create_workspace",
    "delete_workspace",
    "update_workspace",
    # Drover callback is a transparent service proxy. The Lumen internal
    # snapshot and preview endpoints are read-only; execute records its
    # authority state directly, outside the per-project OpenStack cache.
    "callback",
    "snapshot",
    "preview",
    "execute",
    # Internal K3s admission is read-only despite POST. Intent creation mutates
    # DB-backed orchestration state read directly, not an OpenStack cache.
    "k3s_gpu_admission",
    "create_k3s_provisioning_intent",
}

# ---------------------------------------------------------------------------
# Known invalidating helpers — handlers that *call* one of these functions
# are considered covered even if no direct invalidation call is visible.
# ---------------------------------------------------------------------------
INVALIDATING_HELPERS: set[str] = {
    "_simple_action",  # compute/instances.py — start/stop/reboot/shelve/unshelve
    "_invalidate_provisioning_caches",  # internal_k3s.py — Nova/Cinder submission
}

# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def get_http_methods(node: ast.AsyncFunctionDef) -> list[str]:
    """Return HTTP method decorators (post/put/patch/delete) on a function."""
    methods: list[str] = []
    for decorator in node.decorator_list:
        if isinstance(decorator, ast.Call):
            if isinstance(decorator.func, ast.Attribute):
                if decorator.func.attr in ("post", "put", "patch", "delete"):
                    methods.append(decorator.func.attr)
        elif isinstance(decorator, ast.Attribute):
            if decorator.attr in ("post", "put", "patch", "delete"):
                methods.append(decorator.attr)
    return methods


def has_invalidation_call(node: ast.AsyncFunctionDef) -> bool:
    """Return True if the function body contains a cache-invalidation call.

    Detects:
    - cache.invalidate(...)  / invalidate(...)
    - invalidate_tag(...)
    - bump_version(...)
    - invalidate_mutation_count(...)
    - write_through(...)  — terminal mutation direct-set (surgical write-through)
    - patch_list(...)     — terminal mutation list entry patch
    - Delegation to a known invalidating helper (e.g. _simple_action)
    """
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            if isinstance(child.func, ast.Attribute):
                if child.func.attr in (
                    "invalidate",
                    "invalidate_tag",
                    "bump_version",
                    "invalidate_mutation_count",
                    "write_through",
                    "patch_list",
                ):
                    return True
            elif isinstance(child.func, ast.Name):
                if child.func.id in (
                    "invalidate",
                    "invalidate_tag",
                    "bump_version",
                    "write_through",
                    "patch_list",
                    *INVALIDATING_HELPERS,
                ):
                    return True
    return False


def find_mutation_handlers_without_invalidation(filepath: Path) -> list[str]:
    """Return list of 'file:handler (methods)' strings for failing handlers."""
    source = filepath.read_text()
    tree = ast.parse(source)

    missing: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef):
            if node.name in EXEMPT_HANDLERS:
                continue
            http_methods = get_http_methods(node)
            if http_methods and not has_invalidation_call(node):
                missing.append(f"{filepath.name}:{node.name} ({', '.join(http_methods)})")
    return missing


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


def test_mutation_handlers_have_invalidation() -> None:
    """All POST/PUT/PATCH/DELETE handlers must call cache invalidation.

    Handlers in EXEMPT_ROUTERS / EXEMPT_HANDLERS are explicitly whitelisted
    with documented reasons above.
    """
    all_missing: list[str] = []

    for py_file in sorted(API_DIR.rglob("*.py")):
        if py_file.name.startswith("_"):
            continue

        rel_path = str(py_file.relative_to(API_DIR))
        if rel_path in EXEMPT_ROUTERS:
            continue

        missing = find_mutation_handlers_without_invalidation(py_file)
        all_missing.extend(missing)

    if all_missing:
        msg = (
            "Mutation handlers missing cache invalidation:\n"
            + "\n".join(f"  - {m}" for m in sorted(all_missing))
            + "\n\nFix: add `await invalidate(...)` + `await cache_invalidation"
            ".invalidate_mutation_count(...)` after the mutation succeeds, or"
            " add the handler to EXEMPT_HANDLERS with a documented reason."
        )
        pytest.fail(msg)
