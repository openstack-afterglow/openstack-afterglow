## Why
The preceding local feature qualification proved Keystone system-token exchange but not Nova authorization. Stock Nova2025.2 server all-tenants, hypervisor and flavor-access rules declare project scope; system tokens fail with scope enforcement enabled. A personal/member token also cannot become native provider admin from an Afterglow system-admin flag.

## What Changes
- Restore caller-native get_os_conn transport for projectful consumers, credential/telemetry boundaries and ordinary directory operations; retain legacy projectless Keystone-only system path.
- Add explicit get_admin_os_conn: fresh native require_admin followed by the existing fixed configured admin-project executor. Force authentication, verify actual native project scope/admin role/explicit is_admin_project, preserve actor/logical personal context separately and close exactly once. No caller grant or workspace changes and no arbitrary execution project from request.
- Use it for cloud-provider admin inventory/hypervisors/flavor ACL/Placement and their selected-domain ownership directory. Preserve explicitly caller-bound credential and telemetry APIs.
- Verify login through real routers/JWT/SDK/HTTP to a synthetic native cloud that evaluates exact upstream Nova2025.2 policy defaults with real oslo.policy enforce_scope=True; include all-tenants inventory, hypervisors, private flavor ACL add/list/remove and fresh caller revocation.
- Correct prior architecture/docs/receipt claims and qualify final source with unchanged canonical gate and isolated-index architecture guard.

## Impact
Afterglow local source only. No native grants, credentials, operational quota/schema/config/runtime/deployment or commit/push. Reuse existing configured executor and owned disposable fixtures. Native service permission/configuration remains a real deployment prerequisite, not an automatic grant or token-scope fallback.
