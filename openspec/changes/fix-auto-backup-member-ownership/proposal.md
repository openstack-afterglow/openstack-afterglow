# Auto backup: accept a proven exact-project member session whose Cinder hides the owner attribute

## Problem (observed in production after the 1.32.18 reconciler converged)

The managed system account received its exact `member` grant on DMSLAB, the scheduled backup of the `gitlab boot` volume was submitted, and Cinder created a real 500 GB backup (`creating`, volume `backing-up`). Afterglow's own journal then stayed `unknown`: `Backup acceptance or completion could not be confirmed; it will not be resubmitted.` with `backup_id: null`, and every later reconcile kept failing, so tracking, status, pruning and the next daily slot would never proceed.

Root cause (verified on the production container): Cinder's `backup:backup_project_attribute` defaults to `rule:admin_api` in this release. An admin session sees `project_id` on a backup; the project-scoped member the system account now uses sees `None`. `_owned()` requires `backup["project_id"] == project_id`, so every backup the member itself created or listed is "not owned". Earlier releases used an admin-role project connection, so the attribute was visible and the failure never appeared; fake-backed tests always supplied `project_id`.

## Change

- `_make_proxy` marks a connection `_afterglow_exact_project_scope` only after the existing exact-project proof (`prove_project_scope`, no operator binding).
- A new `_scoped()` view fills `project_id` from the proven scope only when the backup row has `None`, at the five backup read sites (prune list/get, reconcile list/get, create response). A visible foreign owner is never overwritten; connections without the proof keep the strict rule (None stays unowned); the snapshot lane is unchanged (its owner attribute is visible to owners).
- Tests: a member-session cloud with hidden owner attributes tracks the submitted backup and prunes only its own old backup (foreign owner kept); the same cloud without the proof stays `unknown` and prunes nothing; only the exact-project factory sets the marker. The new member test fails with the exact production symptom when the adoption is disabled.

## Non-goals

No change to account creation, role or quota reconciliation, snapshot lane, user-facing backup APIs or Cinder policy. No manual edit of production Redis journals: the stuck journal is expected to reconcile by name and volume once the fix is deployed.
