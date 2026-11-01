## Context

The page starts policy, source-volume and backup reads concurrently. `api.post` deliberately retires all same-scope pending GETs before and after a mutation. Policy listing is read-only but uses POST, so completed HTTP 200 reads are rejected as AbortError and displayed as server/source errors. The apparent loading artwork after the alert is the successful-empty EmptyState glyph, not a pending loader. Recent local Docker logs show relevant HTTP 200s, but do not establish screenshot deployment identity.

## Goals / Non-Goals

**Goals:** use correct GET semantics, preserve reader/owner/project boundaries and actual mutation invalidation, cover the real API client and browser.

**Non-Goals:** authority bypass, global client exemptions, retries, new data persistence, service changes, native writes or production acceptance claims.

## Decisions

Use GET on the existing two-segment policy-list path rather than a POST exemption in the shared client. Its two segments do not collide with the one-segment backup-detail route; register it before the dynamic policy source route. Migrate all current callers/tests and remove old POST behavior, avoiding a compatibility shim. Suppress successful-empty backup presentation on errors while keeping existing rows visible on refresh failure.

## Risks / Trade-offs

- Method cutover requires matched backend/frontend release. No DB schema or writer compatibility changes.
- Synthetic identity/native fixtures prove application transport behavior only; actual deployed screenshot origin and native backup operations remain unqualified.
