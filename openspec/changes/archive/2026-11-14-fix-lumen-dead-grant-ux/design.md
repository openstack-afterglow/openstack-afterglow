# Design

## Authentication boundary

`McpCredentialInvalidError` extends `McpConsumerConnectionError` and retains the existing public message and exception cause. Classification belongs to application-credential authentication, not general provider dispatch: only Keystone Unauthorized/NotFound (HTTP 401/404) qualify. Forbidden, resource-not-found, network errors, timeouts and 5xx do not prove a dead credential.

## Observation, not authority

The real Lumen execute path logs `mcp_credential_invalid` once per classified failure with only eight-character grant/project/user prefixes. A small async helper uses the same Redis factory as rate limiting. The flag is keyed by the full grant ID and expires after 604800 seconds. Redis failure must not change execute or catalogue behavior. The catalogue reads only this observation and defaults to `ok` on unavailable Redis; `ok` means no retained invalid observation, not a successful live authentication test. Disable deletes the observation for hygiene. New grants have distinct IDs.

## Catalogue and recovery

`GET /api/v1/chat/cloud-tools` adds `credential_state` while preserving every existing field, selection and `enabled` semantics. No Keystone probe or grant write occurs on this GET. The built-in MCP row replaces its active success pill with a warning pill and explains that the user must disable then enable. Existing buttons and consent/owner fences remain unchanged. Nine locale catalogs contain matching keys; new translations are drafts, not human-reviewed claims.

## Compatibility and limits

No schema/configuration/dependency/version changes. Old API/frontend cohorts remain additive-compatible; old frontends ignore the new field and new frontends tolerate its absence. Redis expiry or outage can remove the warning until another real failed execution observes it. This change does not repair credentials or prove production recovery.
