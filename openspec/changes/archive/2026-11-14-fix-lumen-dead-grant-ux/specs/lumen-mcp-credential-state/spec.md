# Lumen MCP credential observation

## ADDED Requirements

### Requirement: Detect invalid application credentials only at authentication

The consumer connection SHALL classify Keystone authentication HTTP 401 and 404, including a missing referenced role, as `McpCredentialInvalidError` while retaining the existing public message and cause. It SHALL NOT classify Forbidden, native resource 404, network, timeout or 5xx failures as invalid.

#### Scenario: Authentication rejects a stored grant

- WHEN a real Lumen execute call encounters the classified failure
- THEN one structured warning with truncated identifiers is emitted
- AND a best-effort full-grant-ID Redis flag lasts seven days
- AND the execute HTTP status and response body remain unchanged.

### Requirement: Inform without changing authority

The cloud-tools catalogue SHALL return `credential_state` as `invalid` only for a retained selected-grant observation, otherwise `ok`, including Redis failure. It SHALL preserve `enabled` and existing fields and SHALL NOT call Keystone for this observation or revoke/reissue a grant.

#### Scenario: User views a broken built-in connection

- WHEN the selected grant has an invalid observation
- THEN the built-in row shows a warning pill and localized disable-then-enable guidance
- AND existing actions remain explicit user actions
- AND disabling removes the retained observation best effort.
