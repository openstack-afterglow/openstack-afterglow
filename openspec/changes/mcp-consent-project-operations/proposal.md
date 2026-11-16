# MCP consent: per-project operations, domain-only switch, Palimpsest policy compatibility

## Why

- The OAuth consent screen offered one grant-wide access level (read or manage) and a separate project list. Users could not allow writes on one project and reads on another, and could not separate "create" from "change or delete".
- The project step listed every native service capability leaf (`drover-access_admin`, `waygate-clients_editor`, …) for each project. Drover, Waygate and Palimpsest already grant those capabilities to any project `member` and read capabilities to `reader`, so the list read as if extra service roles were required.
- Palimpsest 0.3.13+ returns only `actions` from `GET /v1/policy/capabilities` (the `capabilities` key was removed with the native-role cutover, palimpsest `f54a0d1`). Afterglow rejected that payload as `policy_invalid_response`, so the consent preview always showed "네이티브 정책 응답이 올바르지 않습니다" for Palimpsest, and every other Afterglow consumer of the Palimpsest policy read failed the same way.
- 「도메인 변경」 routed to the full `/select-domain` workspace browser (domain + project search, create domain/project). The consent page only needs the target domain; projects are chosen on the consent page itself.
- Hermes Agent and OpenClaw needed a verified connection path, including when the agent runs on another host and its loopback callback is unreachable from the browser.

## What Changes

- Grant model: each approved project stores `operations`, a non-empty subset of `read`, `create`, `update` (`update` covers changing and deleting existing resources). Write operations require the project's native write role and the client's `mcp:write` scope. Grants saved before this change keep their meaning: `read`, plus `create` and `update` when the grant is `manage` and the project was writable.
- Enforcement: every tool has an operation (`read` for read tools, `create` for `*_create`, `update` for every other mutation). Target binding, mutation claim and the final dispatch check require that exact operation on the target project.
- OAuth approval accepts `project_operations` (project id → operations). The grant's access level and scopes are derived from it.
- Consent page: one table, one row per project, with independent 읽기 / 생성 / 업데이트 checkboxes; create/update are disabled for read-only projects or when the client did not request `mcp:write`. Native service capability detail moves into a collapsed section.
- Consent page domain switch: an inline list of the user's available domains; selecting one re-scopes the session to that domain (existing `/api/v1/auth/token/domain`) and reloads the same consent ticket.
- Palimpsest policy compatibility: when `capabilities` is absent, Afterglow projects Palimpsest's native actions to its capability leaves (`packages:inventory` → `palimpsest-inventory_reader`, `packages:read` → `palimpsest-download_user`, `packages:write` → `palimpsest-publish_editor`, `keys:issue` → `palimpsest-keys_editor`, `keys:revoke` → `palimpsest-keys_admin`).
- Remote agents: when the redirect URI is a loopback address, the consent page explains how to finish authorization for an agent on another host (Hermes: paste the redirected URL; OpenClaw: `openclaw mcp login <name> --code <code>`).

## Explicit non-goals

- Personal API-key issuance keeps its grant-wide access level; its grants use the legacy derivation above.
- No change to native service policy evaluation, the Default-project exclusion, ongoing consent or role-ceiling checks.
- No device authorization grant: neither Hermes nor OpenClaw MCP clients implement it.

## Capabilities

### Modified Capabilities

- `mcp-project-capability-consent`

## Impact

Backend: `backend/app/services/mcp_control_plane/{authority,authentication,ledger,registry,transport,oauth_authority}.py`, `backend/app/api/mcp.py`, `backend/app/api/mcp_lumen.py`, `backend/app/services/service_proxy.py`. Frontend: `frontend/src/routes/oauth/mcp/authorize/+page.svelte`, `frontend/src/lib/components/account/McpPermissionPreview.svelte`, `frontend/src/lib/utils/mcpConsentPermissions.ts`, i18n `public-entry.json` in all nine locales. No schema migration: `approved_projects` is JSON.
