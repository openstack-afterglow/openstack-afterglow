## Why

The public source integration was pushed to `origin/dev` at `c893591dc0904e46b78be84685e3b2ace6f4dbfe`, but the user's actual shared checkout stayed on `3c9af255f7047c25d5ea8bcbf3d37d357634a134` with its changes visible as modified/untracked. A concurrent approved local source reconciliation also supplied additional changes. The user now explicitly requests checking and committing every remaining change, including resolving the actual checkout's dirty state.

## What Changes

- Capture the exact current public tree and index outside the repository; compare every path with the original publication snapshot, current local HEAD and published dev.
- Preserve genuine post-capture fixes and translation improvements, while keeping published security/authority/proxy boundaries and newer regression fixes rather than reverting them to an older merge result.
- Integrate and verify in the existing isolated dev sandbox, then apply the exact qualified public result to the original checkout only after checking that captured inputs have not changed. Preserve private/ignored runtime files, other worktrees and services.
- Commit the final public source and reconcile the original dev checkout to that commit without force, broad cleanup, stash/reset, release or deployment. Normal dev push continues the already-authorized publication task.

## Capabilities

### New Capabilities

None. This is source/version-control reconciliation of previously requested changes.

### Modified Capabilities

No new capability is designed. Existing local improvements are reconciled with the stronger published contracts.

## Impact

Potential frontend metrics/topology/chart behaviors, nine-locale text, observation/config fixes and historical local-reconciliation evidence. Architecture and test evidence are updated for the final source. Actual native IAM, credentials, SQL migration, cloud resources, running services, tags, main branch and unrelated worktrees remain outside scope.
