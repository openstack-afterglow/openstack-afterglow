# Design

## Authentication boundary

`McpCredentialInvalidError` extends `McpConsumerConnectionError` and retains the existing public message and exception cause. Classification belongs to application-credential authentication, not general provider dispatch: only Keystone Unauthorized/NotFound (HTTP 401/404) qualify. Forbidden, resource-not-found, network errors, timeouts and 5xx do not prove a dead credential.

## Observation, not authority

The real Lumen execute path logs `mcp_credential_invalid` once per classified failure with only eight-character grant/project/user prefixes. A small async helper uses the same Redis factory as rate limiting. The flag is keyed by the full grant ID and expires after 604800 seconds. Successful native-authenticated read or mutation dispatch clears an existing flag best effort; `EXISTS` precedes `DELETE` so healthy calls without a flag do not write. A dispatch-scoped context observation records only connections that passed native authentication and current-role validation. Local-only success, preview, mutation replay and failed dispatch do not establish recovery. Redis failure must not change execute or catalogue behavior. The catalogue defaults to `ok` on unavailable Redis; `ok` means no retained invalid observation, not a successful live authentication probe. Disable also deletes the observation for hygiene. New grants have distinct IDs.

## Catalogue and recovery

`GET /api/v1/chat/cloud-tools` adds `credential_state` while preserving every existing field, selection and `enabled` semantics. No Keystone probe or grant write occurs on this GET. The built-in MCP row replaces its active success pill with a warning pill and explains that the user must disable then enable. Existing buttons and consent/owner fences remain unchanged. Nine locale catalogs contain matching keys; new translations are drafts, not human-reviewed claims.

## Compatibility and limits

No schema/configuration/dependency/version changes. Old API/frontend cohorts remain additive-compatible; old frontends ignore the new field and new frontends tolerate its absence. Redis expiry or outage can remove the warning until another real failed execution observes it. This change does not repair credentials or prove production recovery.

The catalogue retains the existing first-by-grant-ID representative selection across all sources. A non-first invalid selected grant is not displayed. A first selected personal token also receives the current internal-Lumen disable-then-enable guidance, although disabling retires only internal Lumen grants and preserves personal-token selections. These multi-grant/PAT recovery UX paths remain untested limitations, not completed recovery behavior.
