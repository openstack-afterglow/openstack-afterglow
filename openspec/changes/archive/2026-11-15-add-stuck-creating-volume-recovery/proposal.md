# Stalled creation-stage volume recovery

## Why
The administrator's all-volume list can display an unattached `creating` boot volume indefinitely, while ordinary delete rejects that status and the detail panel does not expose deletion diagnostics. Reuse the existing admin Cinder/Ceph recovery pipeline instead of introducing a second deletion path.

## What Changes
Add conservative, read-only diagnosis for `creating` and `downloading`, explicit state-recovery and destructive pipeline modes, exact resource/status confirmation, watcher liveness gates, full safety rechecks, localized dashboard actions, and service/endpoint/controller/component tests. Preserve existing error-state callers and admin authority, Redis lock, audit, cache and backend/quota verification boundaries.

## Exclusions
No production writes, native database edits, direct RBD image deletion, owner-service cancellation, new settings/schema, deployment, release, push or merge into shared dev. Existing error-state consistent-backend watcher policy is unchanged. Work remains on `feat/stuck-creating-volume-recovery` in its dedicated worktree.
