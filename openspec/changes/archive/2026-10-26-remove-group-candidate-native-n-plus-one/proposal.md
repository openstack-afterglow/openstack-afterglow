## Why

Explicit Accounts-home candidates currently perform a sequential exact user GET for every native LIST row. Accounts contains all human identities, so directory load latency grows by one round trip per account. Fresh graph-locked PUT already independently proves the exact user/home/enabled state and current administrator authority.

## What Changes

- Project candidates directly from the exact source-domain native LIST, validating unique nonempty IDs, exact home, strict enabled boolean and name/email types.
- Keep exact enabled group/target/source-domain proofs, system-admin guards, no-store behavior, deterministic ordering and whole-request failure for malformed/provider errors.
- Treat displayed rows as list-time candidates, not admission authority. Preserve the fresh exact user/home check inside the membership graph lease.
- Prove a 500-account directory requires zero candidate-specific user GETs and rejects deleted/disabled/moved users on subsequent admission.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

Explicit administrator group candidate lookup avoids per-row native reads; response and write contracts remain unchanged.

## Impact

One backend route and its behavior regressions, plus architecture/API/testing/changelog documentation. No frontend, dependencies, configuration, migration, shared runtime, native IAM or release change. Server-side search/caps/pagination are outside this fix; the existing complete source-home directory remains available.
