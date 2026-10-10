## Implementation Tasks

- [x] 1. Preserve exact explicit MCP resource URLs (including an origin root) across backend/frontend/deployment consumers while retaining the unset fallback.
- [x] 2. Reuse personal-key issuance/management and provide placeholder plus one-time authenticated HTTP configuration and token/config copy actions in the account UI.
- [x] 3. Add owner-bound browser-only verification using an actual bounded MCP initialization and tool-list handshake; reject invalid/foreign/expired/revoked keys and prevent redirect credential leakage.
- [x] 4. Add account verification input/result UX with late-response fencing and secret teardown.
- [x] 5. Add localized `/docs/mcp`, inbound/outbound connector distinctions, key lifecycle, supported formats and troubleshooting, linked from the account screen.
- [x] 6. Run focused regression tests and actual HTTP/browser smoke for the changed paths; document identity/cloud/live boundaries and any unrelated integration blockers.
- [x] 7. Own this change's four MCP guide Korean source/lookup-key findings with exact-line allowlist reasons; do not classify them as unrelated.
- [x] 8. Localize stable verification failure codes and HTTP 429; document 502/503/504/429 in all guide languages.
- [x] 9. Limit dedicated origin-root Helm routing to exact `/`, `/oauth` and `/.well-known`, excluding unrelated backend API paths.
- [x] 10. Rebuild corrected frontend images, rerun affected regression/type/i18n and browser smoke, and refresh scoped architecture evidence before `--skip-specs` archival.

## Verification Record (2026-10-08, local only)

- Backend focused MCP/config/ingress/inventory/Kolla renderer selection: 90 passed; changed-file Ruff check/format passed. The protocol fixture now enters and exits the SDK task group in the same test task.
- Initial frontend account/docs/server-config: 4 files/40 tests passed; Svelte check 2,338 files/0 errors with only the existing `DocCodeBlock` warning; i18n check 0 errors. The initial `i18n:scan` failure (3,840 Korean lines in 988 files) included this change's four MCP guide files, which this change owns. Reopened corrections explicitly allowlist only their exact canonical-source/translation-key lines; other findings remain outside scope.
- Canonical `docker-compose.dev.yml` backend/frontend targets were built for linux/arm64 and linux/amd64; amd64 executed Python `x86_64` and Node `x64`. An isolated Compose project used test-profile MariaDB/Redis without host ports and became healthy.
- Actual HTTP against that project, the installed MCP SDK and MariaDB: exact origin-root site-config/metadata, one-time key, hash/prefix-only storage, owner-only list/check, 18 tools via verification and independent SDK client, foreign user/project 400 without probe, cross-site 403, root 401 challenge, revoke then 400 and MCP 401, `mcp_grant.verify` audits and 429 rate limit.
- Chromium: issuance dialog JSON/root URL, actual clipboard config copy, issued/saved checks, invalid key error, dialog/input teardown, user-B isolation, account 390–1440px dark/light without overflow; `/docs/mcp` four languages at 390/768/1024/1440px with exact example, account link and hub search.
- Boundaries: browser/Keystone identity and application-credential provider were synthetic; no real OpenStack tool call, external AI client, production DNS/TLS/routing, Kolla deployment or live credential was exercised. `https://mcp.cloud.dmslab.re.kr` remained an operator prerequisite.
- Broader layers in the shared checkout: backend unit 4,238, consumer contract 154 and functional 28 passed. Frontend unit had 27 failures in 14 files outside the changed modules (none import MCP/account/docs/server-config code) plus the existing hard-coded Korean guard; full `lint:backend` stops on the out-of-scope `tests/test_vm_github_ssh_history.py` I001; `docs:check`/`test:gate` cannot run while the shared index has 335 unmerged entries.
- Scoped architecture proof on HEAD plus this change's current files (including the uncommitted docs-catalog dependency) passed `--stamp`, `--staged` and working checks at `source_sha256=14aef923…c9516` (2,406 files); the shared index and review block were not modified.

## Reopened Advisory Corrections (2026-10-08, local only)

- Ownership: all four MCP guide files now have reasoned exact-line entries (56 unique lines each) in `hardcoded-text-allowlist.json`; the scanner finds 0 in these files and 3,619 elsewhere. Exact-line freshness and translation-catalog tests passed. The full guard was deliberately excluded from the affected test command, not reported as passing.
- Frontend: 6 files, 45 passed, 1 full-source hard-coded guard test skipped; includes API string-code validation, localized verification failures and rate limiting, docs and server config. `i18n:check`: 0 errors/0 warnings, 9,247 messages; Svelte: 2,338 files/0 errors/1 existing docs warning.
- Backend: 46 affected MCP/config/ingress tests passed; changed test Ruff check/format passed. Running from repository root first hit composite `.env` Settings validation; the canonical backend cwd avoids that unrelated environment input. Removed source/comment-string assertions instead of re-pinning wording; rendered Helm paths remain covered.
- Corrected canonical frontend images built for arm64 and amd64; Node executed `arm64` and `x64`. Isolated Compose frontend became healthy. Chromium on that build exercised 7 stable codes plus 429 in all four languages (32 interactions), rejecting raw detail display and clearing each saved credential input; 390px screenshot confirmed the localized error surface. Four-language docs rendered the new 502/503/504/429 troubleshooting without mobile horizontal overflow. This corrective browser pass used synthetic API responses and is not backend-auth or production proof.
- Helm template rendered exact `/`, Prefix `/oauth` and Prefix `/.well-known` for the dedicated origin-root host; `/api/*` is not routed there. No Kubernetes ingress-controller deployment was performed.
- Final scoped architecture proof: detached HEAD plus feature files and typed docs dependencies, 2,415 source files; `--stamp`, working and `--staged` checks passed at `fd7fae087059548cfce1d78d1f6ce44e13ccde65eefae628110762bf47ac9dc2`. Shared unmerged index/review block stayed untouched; this is not a full integration gate pass.
- Optional gbrain sync unavailable (`command -v gbrain` found no CLI); shared agent guidance was not changed. Production DNS/TLS/routing and live-client/OpenStack verification remain outside the local proof.
