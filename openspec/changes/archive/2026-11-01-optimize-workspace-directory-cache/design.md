## Context

The chooser already owns 30-second memory display snapshots, 16-domain bounds, logical-session identity and synchronous scope/authority invalidation. The backend uses NativeOperation for directory and workspace browse authorization. These are existing correctness boundaries, not replaceable by cached capabilities.

## Goals / Non-Goals

Goals: reduce repeated visible loading across chooser opens and same-tab reloads; reduce backend display hydration on authorized warm reads; retain explicit fresh refresh and failure isolation.

Non-goals: cache authorization verdicts, extend tokens, share inventory between users, persist credentials, deploy services or change database schema.

## Decisions

Extend the existing display cache rather than adding a parallel generic client cache. Persist only bounded successful display payloads with original expiry and exact owner metadata in sessionStorage. Reuse only after the verified owner matches. Backend caching must remain behind fresh authority checks and use existing scoped Redis/invalidation conventions. Explicit refresh remains fresh at both layers. Final implementation-specific TTLs/keys and measured native-call savings are documented with verification evidence.

## Risks / Trade-offs

Display metadata may be briefly stale within a bounded TTL; it cannot authorize scope commit/create. Browser storage is tab-scoped and best effort. Native authorization latency remains intentionally live. Cache failure must fall back to authoritative reads, not a successful empty inventory.

## Verification

Use regression tests for TTL/owner/refresh/invalidation/races, actual isolated browser reload/reopen probes and real HTTP fixtures that count native work. No production performance claim without deployed measurements.
