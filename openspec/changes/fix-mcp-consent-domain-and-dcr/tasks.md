# Tasks

## 1. DCR registration

- [x] 1.1 Reproduce: `localhost` loopback redirect and non-list `grant_types` produced 500 (uncaught `McpOAuthError` and `TypeError`).
- [x] 1.2 Allow `localhost` loopback redirects; keep HTTPS and IP-literal rules.
- [x] 1.3 Map redirect and grant-type validation errors to `McpOAuthAuthorityError` (400 `invalid_request`).
- [x] 1.4 Tests: localhost accepted, non-loopback HTTP rejected with 400 through the app, non-string `grant_types` rejected.

## 2. Consent domain

- [x] 2.1 Return `domain_id` and `domain_name` from the consent GET and from the project list (list response only; `McpProjectView` unchanged so token responses keep their shape).
- [x] 2.2 Show the authorization domain on the consent client step and the project step, with a note that projects come from that domain only.
- [x] 2.3 Multi-domain selection: implemented without a project-less consent session. The consent page offers 「도메인 변경」 (only when more than one domain is available) that routes to `/select-domain`. A same-user pending ticket is rebound to the new session project on GET (`load_consent_ticket(rebind_project=True)`); approval still requires the exact owner project.
- [ ] 2.4 Browser proof of the domain-change → re-consent round trip not run (no live user session).

## 3. Native policy failure reason

- [x] 3.1 Classify failed policy reads into closed reason codes; fall back to `permission_check_unavailable` for project-level failures.
- [x] 3.2 Preview displays the specific reason and keeps the state `unavailable`; unknown codes use the generic text.
- [x] 3.3 Tests: backend reason mapping, snapshot, and updated expectations in existing service, preview and project-authority tests; vitest reason key mapping.
- [ ] 3.4 Root cause of a specific member's native failure: needs the reason code from a real preview in the user's browser session. Not established here.

## 4. Hermes

- [x] 4.1 Checked against published Hermes docs (secondary source; the Hermes source is not installed locally): Hermes uses a loopback `127.0.0.1` redirect and `auth: oauth`, tries CIMD before DCR, and requests `authorization_code` and `refresh_token`. The server supports all three. Device flow is not supported.
- [ ] 4.2 Live Hermes run against production not performed.

## 5. Verification and docs

- [x] 5.1 `uv run --extra dev pytest tests/test_mcp_oauth.py tests/test_service_policy_error_reasons.py tests/test_service_authorization.py tests/test_mcp_preview_native_http.py tests/test_mcp_project_authority.py tests/test_mcp_credentials.py`: 229 passed.
- [x] 5.2 `npm run test:unit:backend`: 14749 passed, 106 skipped.
- [x] 5.3 `npm run test:unit:frontend`: passed. `npm run test:contract`: 261 passed. `npm run test:orchestration` with the backend venv on PATH: passed.
- [x] 5.4 `npm run i18n:check`: 0 errors; `svelte-check --threshold error`: 0 errors; `npm run lint:backend`: passed; `npm run experience:catalog:check`: passed after regeneration.
- [x] 5.5 `docs/security.md`, `docs/api/auth.md`, `ARCHITECTURE.md`, `docs/testing.md` updated.
- [x] 5.6 `npm run test:gate` passes (exit 0) after the other work was reviewed and the architecture snapshot restamped. Covers docs:check, experience catalog, unit backend 14764 passed, unit frontend, contract 261, functional 284 passed, lint:backend. `test:orchestration` needs the backend venv on PATH (system python3 3.9 lacks `tomllib`). Remaining: 5.7 consent page vitest (3 tests added) passes 94/94 in `page.test.ts`.
- [ ] 5.7 Live verification of Claude Code DCR retry, Hermes OAuth, and member preview reason on production not performed.
