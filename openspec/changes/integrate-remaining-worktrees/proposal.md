## Why

Completed and partially integrated work remains in eight historical worktrees. The user requires reviewing every remaining result, merging applicable changes into the canonical shared `dev` checkout, and removing completed work directories without losing unrelated ongoing work or private configuration.

## What Changes

- Audit remaining committed and uncommitted results against current dev and its history; retain current behavior when an older alternative has been superseded, with concrete evidence.
- Integrate applicable model-ordering, localization, legacy UI/security, and archived release documentation results without restoring obsolete APIs or security contracts.
- Commit the mandatory canonical-dev integration, verification and worktree cleanup policy.
- Validate the integrated source, preserve the concurrent native-password-reset work and private settings, fast-forward the canonical shared dev safely, and remove completed worktrees only after integration evidence and protected backups exist.
- No production deployment, new release/tag, schema/native authority change, or main-branch merge.

## Capabilities

### New Capabilities

- `worktree-integration`: Mandatory canonical shared-dev integration, evidence-based historical reconciliation, verification and safe cleanup.

### Modified Capabilities

None. Existing application capabilities remain authoritative; this change completes integration rather than creating unrelated behavior.

## Impact

Development guidance and integration records; only application files with proven missing applicable changes. All eight historical worktrees and the canonical dev checkout are reviewed. Private files, concurrent changes, branch history and immutable release tags are preserved.
