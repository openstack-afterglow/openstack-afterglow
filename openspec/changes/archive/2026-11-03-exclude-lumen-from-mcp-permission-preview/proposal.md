## Why

MCP does not expose Lumen control or API-key tools, but its project authorization preview misleadingly queries and displays Lumen permissions including key management. The user requires MCP not to control Lumen.

## What Changes

Exclude Lumen from MCP-only service preview queries, output, consent/account projection and tutorial mock; preserve shared native Lumen permissions and the reverse-direction Lumen→cloud MCP bridge. Keep MCP registry closed and verify no registered entry targets Lumen. Preserve other independently evaluated services, unknown states and project authority.

## Capabilities

### Modified Capabilities
- MCP project permission preview exposes no Lumen policy/key/control capabilities.

## Impact

Scoped backend preview/snapshot filter, frontend preview projection, mocks, tests/docs only; no native policy, database, configuration, deployment or cloud mutations.
