## Why

`AGENTS.md` is over 30 KB. Repeated CI history, deployment implementation notes, and security details obscure the rules an agent needs at task start. `CLAUDE.md` is a symlink to it; a short entrypoint can serve both without losing the repository-specific contracts.

## What Changes

- Limit the real root instruction file to 2,000 Unicode characters; keep the `CLAUDE.md` symlink.
- Separate durable workflow, deployment, API/security, and CI requirements into focused OpenSpec specifications with observable scenarios. Link them from the short entrypoint and keep implementation details in `ARCHITECTURE.md`, `DESIGN.md`, and `docs/` rather than repeating them.
- Preserve `dev` branch ownership, architecture freshness, non-destructive Compose operations, `/api/v1` and legacy callback exceptions, tenant/secret boundaries, CI release gates and public-PR runner protections.
- Do not change application behavior, user work, or existing active changes.

## Capabilities

### New Capabilities

- `agent-workflow`: concise entrypoint, evidence discipline, architecture and design review.
- `agent-runtime-security`: environment separation, API, configuration and tenant safety.
- `agent-ci-safety`: measurable CI changes, reliable test/release gating and PR isolation.

### Modified Capabilities

- None. Existing product specifications remain unchanged.

## Impact

Documentation only: `AGENTS.md`, linked OpenSpec specs and this change record. `CLAUDE.md` remains a symlink; no source, config, test, container, or workflow changes. Existing detailed implementation documentation stays authoritative.