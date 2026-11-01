## Why
User requests current verified source committed, pushed, published as a new release and deployed.

## What Changes
- Patch release1.31.4 with current instance controls, backup read isolation, workspace display cache and optional default response.
- Gate exact source, push dev, wait exact-SHA CI, tag and verify published artifacts.
- Deploy via prescribed compute then control Kolla commands with backup/key/config preservation and public verification.

## Capabilities
### New Capabilities
None.
### Modified Capabilities
None; release qualification only.

## Impact
Release metadata and approved application rollout, no unapproved main merge or native resource mutation.
