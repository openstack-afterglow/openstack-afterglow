## Why

The user requests committing and pushing all accumulated public Afterglow source. The shared dev checkout is based on `aac6b9c5dc3e53fc3e430ca9ed96c30cacdbdb1e`; fetched `origin/dev` is `3c9af255f7047c25d5ea8bcbf3d37d357634a134`. Both contain intentional overlapping work. Publishing the old checkout directly would either fail the fast-forward check or discard newer dev behavior.

## What Changes

- Preserve a public-source snapshot without modifying the shared index/private inputs, then integrate the complete snapshot onto current upstream dev in an isolated local dev clone. Concurrent upstream/shared-source updates after capture remain untouched; do not reset them to the initial snapshot.
- Resolve overlapping identity/domain/enrollment, storage recovery, native telemetry/traffic/fabric, frontend lifecycle/chart/localization and deployment-configuration changes without weakening authorization or replay protections.
- Preserve upstream nine-language support, socket-peer/MMDB observation, native GPU fixes, route tuple deduplication and frozen frontend runtime dependency installation.
- Repair only demonstrated integration/gate failures. Record current verification independently from historical feature/release evidence.
- Commit the verified source and push normally to `origin/dev`. Do not create a release/version bump/tag/PR, merge main, deploy services, change shared IAM/data or publish private configuration.

## Capabilities

### New Capabilities

No new capability is designed by this integration request; previously requested local capabilities are preserved.

### Modified Capabilities

Existing contracts from both histories are reconciled at their shared API, UI, schema/config and test boundaries. Legacy Cloud Shell package/build ownership stays retired in favor of the independent openstack-client repository.

## Impact

Public backend/frontend/tests, generators/operator templates and their existing documentation/OpenSpec records. SQL090–098 remain source changes requiring separate approved rollout; this integration does not apply migrations or qualify production mixed-version compatibility. Private settings, credentials, running services, databases, volumes, existing keys and unrelated worktrees are preserved.
