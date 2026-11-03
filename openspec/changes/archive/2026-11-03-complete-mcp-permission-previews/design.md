## Context
Personal API key creation uses the same all/selected/read/manage grant contract but did not disclose project outcomes. Eager serial native-policy preview made even basic membership discovery depend on up to30s service reads and a35s global deadline.

## Goals / Non-Goals
Goals: complete both grant surfaces, reuse presentation, isolate failures and keep cheap read-only key creation available.
Non-goals: relaxing service policy, creating production grants, deploying native changes, new MCP service APIs or schema.

## Decisions
- Default project list remains cheap authenticated membership discovery. Explicit preview=true selects enriched metadata. OAuth always requests enriched; account owns an independent preview request and never lets it clear the cheap membership list.
- Reuse one matrix and mcpConsentPermissions helpers across OAuth/account. A read choice attenuates locally. Management requires known cloud ceilings; unknown service authority is shown as unknown, never allowed.
- Use at most3 independent project SDK connections; do not concurrently share the original session. Each native service preview gets a5s deadline. Project rescope/role failure yields can_write:null and sanitized per-service unknown metadata for that row. Membership discovery errors remain request failures, never empty success.
- Keep current restricted application-credential runtime policy checks and provider dispatch fences. Preview failure does not grant any service authority. Do not bypass delegated-token interoperability errors.

## Risks / Trade-offs
-35s final endpoint deadline remains a last-resort limit for very large or slow membership sets, though individual services/projects are isolated.
- Native service compatibility requires separate live qualification: deployed Waygate was observed rejecting delegated-token exchange and current Drover policy endpoint acceptance with restricted credentials has not been verified.
- All native identity/policy choices in local qualification are synthetic; actual HTTP/TLS/browser execution is not production acceptance.
