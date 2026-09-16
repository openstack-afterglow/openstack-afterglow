## Implementation Tasks

- [x] Trace default discovery, explicit override priority and SDK consumers.
- [x] Apply existing own-service settings to SDK connection routing without affecting core OpenStack services.
- [x] Make dev/base/prod endpoints configurable and preserve generated environment precedence.
- [x] Update configuration examples, deployment rules and consumer regression contracts.
- [x] Verify real local runtime plus SDK/BFF/env/TOML/catalog boundaries and regression gate.
- [x] Finalize architecture evidence and archive the change.

## Verification evidence

- Actual Compose config and runner: six base/prod unset/explicit/empty cases and six dev DNS/TOML/.env/shell/empty cases passed. Backend and Notion agree; Lumen API/worker/migration share the selected reverse URL. Generated env is 0600 and preserves literal dollars in an actual disposable container. Temporary artifacts removed.
- SDK regressions: 8 passed, exercising root/versioned endpoints, configured/catalog selection and real serialized user/admin project authentication. All dashboard/admin/MCP callers use lazy adapters bound to conn.session; core connections do not eagerly allocate owned-service proxies.
- Focused affected consumer tests: 109 passed. Named config/contracts/k3s/waygate targets passed.
- Final npm run test:gate passed: 2729 backend unit, 1285 frontend, 124 contract, 24 functional; backend Ruff check and format passed (484 files).
- Live backend rebuilt and recreated alone. Real authenticated Waygate/Drover SDK GETs reached local service DNS with HTTP 200. BFF Waygate servers, Drover clusters, Lumen models, Palimpsest layers and dashboard k3s-stats returned 200; stats available=true. Session refresh returned 200.
- Core compute destination was read from the authenticated remote catalog without calling Nova. No remote Kolla/catalog changes or cloud resource mutations. Existing upstream Nova 503 remains outside this change; this is not a full dashboard-health claim.
- All 18 existing service mounts retained; all non-backend container IDs unchanged. Original .env, afterglow.conf, private snapshot and keys unchanged. Architecture --staged guard passed against an isolated index; real index unchanged. No commit or push.
