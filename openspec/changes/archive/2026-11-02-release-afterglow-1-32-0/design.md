## Context

Existing release1.31.4 is immutable. Current dev includes later CI-only commits and pending resize/auth/IAM improvements. User authorizes inclusion of all current changes; unrelated secrets/private deployment inputs remain excluded.

## Goals / Non-Goals

**Goals:** publish reviewed, gate-tested1.32.0 source and images with accurate notes.

**Non-Goals:** main merge, controller recovery, production native/schema/service cutover.

## Decisions

Use root package.json plus scripts/sync-version.js, preserving this repository SemVer convention. Commit only after fullgate and smoke, wait exact pushedSHA CI before immutable tag. Verify tag images/revisions/latest and Helm release. Retain existing production-hold record.

## Risks / Trade-offs

Concurrent edits may change gate inputs: compare source fingerprint before commit and rerun affected checks if changed. GitHub publication is not production qualification. Native first-password artifact remains its separately qualified digest; do not relabel it as rebuilt1.32.0 native code.
