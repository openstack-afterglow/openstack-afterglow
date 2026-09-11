## Why

Afterglow, Drover, Lumen, Waygate, and Palimpsest need repository-local architecture references that describe the implementation that exists now rather than historical plans. Developers and AI agents also need a deterministic check that forces every source snapshot to receive an explicit architecture review before completion.

## What Changes

- Add a Korean, source-linked root `ARCHITECTURE.md` to all five repositories with a common structure, explicit ownership boundaries, implementation status, verification evidence, runtime flows, security boundaries, and maintenance guidance.
- Add the same standalone Python/Git architecture snapshot guard and repository-specific regression tests to each repository.
- Connect the guard to agent instructions, pre-commit, CI, and existing project verification entrypoints.
- Align stale architecture and integration documentation with current code while preserving historical plans and user-owned dirty work.
- Stamp each architecture document only after reviewing the final intended source snapshot.

## Capabilities

### New Capabilities

- Living architecture documentation for the five-project Afterglow system.
- Reproducible working-tree and staged-source architecture freshness checks.
- Explicit source-review stamps that record a content digest, UTC review time, and human-readable impact summary.

### Modified Capabilities

- Existing documentation, contributor entrypoints, pre-commit hooks, CI jobs, and test gates discover and enforce the architecture maintenance contract.

## Impact

The change touches documentation, repository policy files, Python test suites, CI workflows, and Afterglow's test orchestration only. It does not change browser UI, service APIs, cloud resources, provider calls, VM guest code, deployment behavior, or runtime schemas. The guard uses only Python's standard library and Git, does not mutate the index, and does not depend on sibling checkouts or a network service.
