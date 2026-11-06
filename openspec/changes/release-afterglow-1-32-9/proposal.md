## Why
Publish the user's current reviewed Afterglow changes as the explicitly requested patch version 1.32.9, including account-owned MCP inventory and the completed current UI/instance-safety changes.

## What Changes
- Freeze the current public working snapshot; exclude later concurrent changes and ignored private inputs.
- Synchronize canonical 1.32.9 version metadata and record the delta from immutable 1.32.8.
- Run the required complete gate and real runtime smoke; fix only demonstrated release blockers.
- Commit on shared dev, push normally, require exact-SHA CI success, then publish immutable numeric tag, bilingual release, images/aliases and Helm.

## Capabilities
### New Capabilities
None beyond the frozen existing changes.
### Modified Capabilities
Release qualification and artifact version only.

## Impact
No production deployment, native role/schema changes, existing-tag movement, main merge, force push or unrelated secret/configuration inclusion. Preserve shared checkout/index and concurrent work.
