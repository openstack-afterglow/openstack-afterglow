## Why

Nova POST normally omits attachment_id. The attach handler compares Cinder's ID only with that absent POST field, and compares raw GET only with POST; therefore contradictory genuine Nova GET/Cinder attachment IDs currently return success.

## What Changes

Compare the corroborating original Nova GET attachment_id against any observed Cinder binding attachment_id before success. Keep volume UUID and Cinder attachment UUID namespaces separate; preserve asynchronous empty-binding behavior and all current owner/state checks. On post-dispatch contradiction retain unknown and prohibit same/new-key replay via unchanged ledger.

## Capabilities

### Modified Capabilities
- Correct corroborated VM data-volume attachment identity proof, no registry/schema/permission/config changes.

## Impact

Only storage attach proof, native HTTP behavior regression and existing docs/changelog. Reproduce before fix with normal POST omission and differing GET/Cinder IDs for matching project/server/volume. Exercise actual MCP/Lumen invocation and installed SDK/local native HTTP, then focused/full gate. Synthetic identity/storage authority remains explicitly synthetic. No production operations, deployment, commit or index changes.
