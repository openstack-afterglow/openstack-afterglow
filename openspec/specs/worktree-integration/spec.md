# worktree-integration Specification

## Purpose
TBD - created by archiving change integrate-remaining-worktrees. Update Purpose after archive.
## Requirements
### Requirement: Canonical dev is the completion target

Development performed in a worktree or isolated directory MUST be integrated into the canonical shared dev checkout and verified there before being reported complete. A commit existing only on a work branch MUST NOT be treated as completed integration.

#### Scenario: Worktree development finishes
- **WHEN** an implementation is ready for completion
- **THEN** its applicable result is normally merged into canonical dev, the integrated source is verified, and the completion report identifies the dev commit

### Requirement: Reconcile historical results without regressions

Historical worktrees MUST be compared with current dev and its history. Applicable missing changes MUST be integrated; an obsolete alternative MUST have concrete supersession evidence rather than being silently discarded or blindly restored.

#### Scenario: An old implementation differs from newer dev
- **WHEN** historical source differs from current source
- **THEN** the actual behavioral delta and modern implementation are compared and its integration or supersession disposition is recorded

### Requirement: Preserve unrelated work and protected data

Integration MUST preserve concurrent tracked/index changes, untracked work, private configuration, keys and active consumers. It MUST NOT use unapproved stash/reset, force-push, empty-content merges or deletion of unintegrated results as a substitute for completion.

#### Scenario: Shared checkout contains unrelated in-flight changes
- **WHEN** a worktree result is integrated
- **THEN** unrelated changes remain present and are neither committed as part of this integration nor overwritten

### Requirement: Clean up completed work directories

After verified integration the agent MUST remove its completed worktrees and isolated directories. It MUST inspect unique commits, working changes, ignored data and active consumers first and preserve protected recovery data where needed.

#### Scenario: A worktree has been reconciled and verified
- **WHEN** canonical dev contains its applicable result and protected recovery evidence exists
- **THEN** its worktree directory is removed and its disposition and any retained exceptions are reported
