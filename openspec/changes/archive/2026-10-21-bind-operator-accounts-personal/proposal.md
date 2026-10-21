## Why
The operator precreated native Accounts and Personal domains. Enrollment must use these real names without display-name mapping or creating replacement shared domains.

## What Changes
- Resolve enabled exact native Accounts and Personal; accept operator-managed rows without Afterglow metadata, reject conflicting kinds and ambiguous names.
- Stop automatic shared domain creation. Preserve historical creation journals and recovery without rebinding them.
- Preserve UUID-based identity, member-only personal projects, quota staging and opaque web organization names.

## Capabilities
### New Capabilities
- `operator-shared-domains`: operator-owned fixed native domain resolution.
### Modified Capabilities
None.

## Impact
Shared topology service, creation-path fixtures, deployment and architecture documentation. No schema or configuration additions; no live IAM changes or account migration.
