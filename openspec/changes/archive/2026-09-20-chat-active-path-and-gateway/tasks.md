## 1. Active-path persistence

- [x] 1.1 Add MariaDB active-path schema migration and immutable manifest checksum
- [x] 1.2 Add ORM projection models, integrity helpers, and locked backfill command
- [x] 1.3 Move append, completion, retry, regeneration, fork, and branch writes to shared transactional projection helpers
- [x] 1.4 Replace normal active-path reads with indexed projection queries and branch/concurrency regressions

## 2. History API and browser

- [x] 2.1 Replace the message route and Lumen SDK contract with revision-fenced opaque cursor pages
- [x] 2.2 Migrate Afterglow to 40-message pages, a three-page/120-message cap, explicit edges, and stale-response guards
- [x] 2.3 Preserve prepend position, resolve latest before old-window sends, and expose new-response behavior away from latest
- [x] 2.4 Use projected sibling metadata and server-side descend for branch switching

## 3. Compatibility protocols

- [x] 3.1 Add OpenAI Responses request, non-stream response, SSE event, auth, discovery, and OpenAPI contracts
- [x] 3.2 Preserve native Anthropic Messages blocks/errors/streams and add count-tokens
- [x] 3.3 Reject provider selector conflicts and forward caller-supplied positive generation/thinking budgets unchanged
- [x] 3.4 Add exact protocol pings/terminals and drain admitted provider streams without client-cancellation coupling

## 4. Claude Gateway authorization

- [x] 4.1 Add hashed device-grant and expiring Gateway credential schema
- [x] 4.2 Implement public device issuance, throttled polling, Keystone-authenticated approval/denial, and one-time consumption
- [x] 4.3 Enforce fixed scopes, Gateway credential kind, 24-hour expiry, dual-header conflict rejection, and configured route ownership
- [x] 4.4 Add Afterglow public authorization shell, login return marker, authenticated BFF, and discovery-owned setup guidance

## 5. Deployment and documentation

- [x] 5.1 Add Gateway configuration validation and discovery metadata in Lumen
- [x] 5.2 Update Lumen Compose/system Compose/Kolla/example configuration with safe defaults and production prechecks
- [x] 5.3 Update Lumen and Afterglow API, integration, operations, security, and user guidance
- [x] 5.4 Update both root architecture snapshots and Afterglow design hierarchy for ownership, pagination, and device authorization

## 6. Verification and completion

- [x] 6.1 Run focused Lumen migration, conversation, compatibility, Gateway, SDK, and deployment contract tests
- [x] 6.2 Run focused Afterglow BFF/chat/Gateway tests, full frontend unit suite, and Svelte diagnostics
- [x] 6.3 Run Lumen contract, integration, and process-stack system gates
- [x] 6.4 Run the actual Afterglow history surface at mobile/tablet/desktop cutovers in light/dark and verify controls, retention, live-edge return, and viewport stability
- [x] 6.5 Run Afterglow `npm run test:gate`
- [x] 6.6 Stamp both architecture guards, validate isolated staged snapshots, update changelog/evidence, and archive the change
