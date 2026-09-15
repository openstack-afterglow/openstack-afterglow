## Why

The administrative GPU flavor quota and usage surfaces can hide GPU flavor names, consume the wrong inventory scope, and mishandle legacy quota rows. Cached public flavor payloads omit `extra_specs`, authority-resolution failures are converted to zero usage, admin usage can count all projects regardless of caller scope, and nullable or duplicate historical quota rows can make reads and mutations inconsistent.

## What Changes

- Rehydrate cached public flavor payloads with authoritative Nova flavor metadata before applying visibility policy.
- Preserve unresolved-authority states as explicit blockers instead of converting them into valid zero counts.
- Select global or project-scoped Nova inventory according to system-admin versus project-admin scope.
- Normalize GPU quota reads and writes across nullable and duplicate historical rows, then add migration ledger coverage for PostgreSQL and MariaDB normalization.
- Add focused endpoint, service, migration, documentation, and live deployment verification for the corrected behavior.

## Capabilities

### New Capabilities

- Deterministic normalization of legacy GPU quota rows during migration.

### Modified Capabilities

- Public flavor cache reads recover authoritative `extra_specs` before GPU visibility policy.
- GPU usage reports represent authority failures honestly and use the caller's authorized inventory scope.
- GPU quota reads and mutations operate on effective normalized records rather than incidental physical rows.

## Impact

Backend flavor and GPU quota endpoints, GPU quota service logic, migration SQL/ledger tests, GPU quota API documentation, and the architecture review stamp change. No new service boundary, API route, deployment topology, or ownership model is introduced.
