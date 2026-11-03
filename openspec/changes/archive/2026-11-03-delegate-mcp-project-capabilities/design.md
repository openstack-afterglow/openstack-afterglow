## Context
The existing restricted-credential grant already persists per-project can_write, but manage preparation rejects a mixed membership. Service grades are independent native-policy entitlements, not consequences of member or system-admin status. The consent project list currently exposes only IDs/names.

## Goals / Non-Goals
Goals: mixed all-project consent, enforceable project ceilings, independent four-service authority and accurate before-approval preview.
Non-goals: new cloud operations, native role changes, schema migration, production deployment, automatic grant upgrades or retrying ambiguous writes.

## Decisions
- Reuse approved_projects and per-target restricted credentials rather than create a new global write authority. Management grants advertise a grant ceiling while each target retains its own can_write. Explicit read consent still clamps all writes.
- For all selection, retain reader-only projects without rejecting writable peers. Preserve explicit selected/current refusal semantics unless required to maintain accurate consent.
- Extend project discovery with can_write, service_permissions (exact native action leaves), service_errors. Resolve current target authority using existing native policy evaluators. No local grade expansion or member/admin shortcut for independent services.
- Show the complete selected-project permission matrix before submit, including unavailable/not-authorized service states, using existing UI primitives and nine locale catalogs. No credential or raw policy errors in the browser.
- Preview is advisory: approval re-reads exact authority and runtime native policies remain authoritative. Stored ceilings prevent added roles from silently expanding old grants; revoked authority must be rejected.

## Risks / Trade-offs
- Per-project native policy reads cost additional bounded I/O; use existing policy helpers and explicit failure states rather than error-to-empty success.
- Policy may change between preview and approval: approval and provider dispatch revalidate; no preview creates credentials.
- Existing grants are not silently upgraded. Current production acceptance needs a separately authorized release/rollout.
