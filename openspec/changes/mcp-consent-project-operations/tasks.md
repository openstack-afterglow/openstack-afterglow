# Tasks

## 1. Grant operations

- [x] 1.1 Registry entries expose `operation` (`read`, `create` for `*_create`, `update` otherwise).
- [x] 1.2 Approved project metadata stores `operations`; legacy rows derive them from access level and `can_write`.
- [x] 1.3 `validate_grant_project`, `lock_principal_grant`, `resolve_principal_target` and `authorize_mutation_dispatch` require the exact operation.
- [x] 1.4 OAuth approval accepts `project_operations`; access level and scopes are derived; write operations require native write roles and `mcp:write`.
- [x] 1.5 Tests for the operation matrix, legacy derivation and approval validation (DB-lane approval test added, not run locally: no MariaDB/Docker).

## 2. Palimpsest policy compatibility

- [x] 2.1 Project Palimpsest `actions` to capability leaves when `capabilities` is absent.
- [x] 2.2 Test with the exact Palimpsest 0.3.29 payload shape.

## 3. Consent UI

- [x] 3.1 Per-project table with 읽기 / 생성 / 업데이트 checkboxes and column select-all.
- [x] 3.2 Native service detail collapsed; effective access shows the chosen operations.
- [x] 3.3 Inline domain list; selecting a domain re-scopes the session and reloads the ticket.
- [x] 3.4 Loopback redirect help for agents on another host.
- [x] 3.5 Component tests and i18n in all nine locales.

## 4. Clients

- [x] 4.1 Hermes Agent 0.19.0 (`hermes-agent[mcp]`, mcp 1.26.0) and OpenClaw 2026.11.4 run against a loopback mock that validates with Afterglow's own registration, scope, PKCE and resource checks: both register as public clients (`token_endpoint_auth_method: none`, `authorization_code`+`refresh_token`), request `mcp:read mcp:write`, send S256 PKCE and the exact resource. All checks pass. Headless completion: Hermes accepts the pasted redirect URL; OpenClaw accepts `--code`.
- [x] 4.2 Live login against production (deployed 1.32.21, before this change) with user approval from an interactive terminal: `hermes mcp test afterglow` listed the tools, `openclaw mcp probe` reported 63 tools, and Hermes' token read `afterglow_projects_list` and `afterglow_vm_list`. Both test grants were then revoked (revoke 200; refresh `invalid_grant`; access 401). Per-project operation enforcement is not live-verified until deployment.

## 5. Verification and docs

- [ ] 5.1 Backend unit 15233 passed (1 pre-existing sandbox failure), contract 262, frontend 8015, Ruff, svelte-check, i18n passed. Full `npm run test:gate` not green here: orchestration test and DB lane need Docker.
- [ ] 5.2 Browser check of the consent page (light/dark, mobile/desktop): blocked, no browser can launch in this environment.
- [x] 5.3 `ARCHITECTURE.md`, `docs/security.md`, `docs/api/auth.md`, `docs/testing.md`, `CHANGELOG.md`.
