# Volume recovery list scope and hidden-owner classification

## Why

Owner review (2026-11-16) and a production observation after 1.32.22:

- 「볼륨 백업」 and 「볼륨 스냅샷」 listed every volume, including volumes that never had a recovery point. The owner wants only volumes that already have a backup (snapshot); creating one from the volume list makes the volume appear.
- Deployed 1.32.22 labels every automatic backup 「수동」 for non-admin members. DMS Lab Cinder hides the backup `project_id` from member sessions (`backup:backup_project_attribute` = `rule:admin_api`), so the exact scheduler ownership check failed and origin fell back to manual.

## What Changes

1. The two list pages show a volume card only when the volume has at least one recovery point. The complete group set stays available so `?volume=`, `?auto-backup=` and the post-create detail navigation open any volume. Empty-state copy explains how a volume appears (9 locales).
2. `cinder._recovery_origin` fills a hidden `project_id` with the token-scoped `_afterglow_authenticated_project_id` for reads without `all_projects`. A visible owner always wins; cross-project reads and connections without that proof are never filled. The logical workspace `_afterglow_project_id` is not used.
3. The volume list summary adds backup count/capacity and snapshot capacity. Capacity is the sum of the source-volume sizes Cinder reports, not consumed space.
4. Keyed rows animate on refresh with `rowMotion`: a new row fades in, a removed row fades out, a changed row flashes once; unchanged rows are untouched and replacements larger than six rows are instant. Siblings slide to their new place only for grid-block rows; `<tr>` rows never carry `animate:` because Svelte pins an outgoing animated row with `position: absolute`, which collapses table cells. Admin floating IPs and the admin users activity panel no longer swap a loaded list for a loader on each refresh.

## Capabilities

### Added Capabilities

- `volume-recovery-list` (list scope, owner classification)
