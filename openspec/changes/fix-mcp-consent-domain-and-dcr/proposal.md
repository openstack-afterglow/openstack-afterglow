# Fix MCP consent domain display, DCR loopback registration, and policy failure reasons

## Why

- Claude Code's dynamic client registration returned HTTP 500 `내부 서버 오류`. `validate_redirect_uris` raised `McpOAuthError` (a `ValueError`), which `oauth_register` did not catch, and loopback registration allowed only `127.0.0.1` and `[::1]` while Claude Code registers `http://localhost:<port>/callback`. A `grant_types` value that was not a list also raised `TypeError` (500).
- The consent screen never named the authorization domain, so an operator could not tell which domain's project was being connected.
- Native policy read failures for Drover, Palimpsest and Waygate all collapsed to `permission_check_unavailable`, shown as "권한 확인 불가", so a member could not tell a native 403 from a timeout or outage.

## What Changes

- `oauth.py`: loopback HTTP redirects accept `localhost`, `127.0.0.1` and `[::1]`; the error names the accepted hosts.
- `oauth_authority.py`: redirect validation failures and non-list or non-string `grant_types` raise `McpOAuthAuthorityError`, so registration returns 400 `invalid_request`.
- `service_authorization.py`: failed native policy reads carry a closed reason code (`policy_unauthorized`, `policy_forbidden`, `policy_unavailable`, `policy_invalid_response`, `policy_timeout`, fallback `permission_check_unavailable`). Upstream text is never included.
- `mcp_access.py` and `mcp.py`: project list and consent details carry the authorization domain id and name from the session token.
- Consent page and account preview: show the authorization domain; show the specific failure reason instead of the generic message.

## Explicit non-goals

- No multi-domain picker. Candidate projects come from `_caller_scope`, which binds the session to one working domain. Switching domains requires a new session, so cross-domain approval is not supported by this change. The screen states this.
- No change to native policy evaluation, to the Default-project exclusion rule, or to the ongoing-consent checks.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. Behavior is recorded in `docs/security.md`, `docs/api/auth.md`, `ARCHITECTURE.md`, and `docs/testing.md`. This project has no capability spec for MCP consent.

## Impact

Backend: `backend/app/services/mcp_control_plane/oauth.py`, `oauth_authority.py`, `backend/app/services/service_authorization.py`, `backend/app/api/mcp.py`, `backend/app/api/identity/mcp_access.py`. Frontend: `frontend/src/routes/oauth/mcp/authorize/+page.svelte`, `frontend/src/lib/utils/mcpConsentPermissions.ts`, `frontend/src/lib/components/account/McpPermissionPreview.svelte`, i18n `public-entry.json` in all nine locales. Tests: `backend/tests/test_mcp_oauth.py`, `backend/tests/test_service_policy_error_reasons.py`, `frontend/src/lib/utils/mcpConsentPermissions.test.ts`. No schema, migration, or deployment change.
