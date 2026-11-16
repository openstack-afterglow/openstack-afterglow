# Tasks

- [x] 1.1 `listedRecoveryGroups` helper; both pages list only volumes with points; keep full groups for details.
- [x] 1.2 Empty-state strings `backupGroups.empty` / `snapshotGroups.empty` in 9 locales; search keeps `page.noMatches`.
- [x] 1.3 Tests: helper, page hides empty volumes but keeps them creatable, empty state.
- [x] 2.1 `cinder._caller_project` / `_recovery_origin` fill a hidden owner from `_afterglow_authenticated_project_id`.
- [x] 2.2 Tests: hidden owner on real SDK HTTP reads (backup and snapshot), logical workspace differing from token project, `all_projects`, missing proof, visible foreign owner.
- [x] 3.1 ARCHITECTURE.md, CHANGELOG.md.
- [x] 4.1 Volume list summary: backup count/capacity and snapshot capacity (`volumesController.fetchBackups`, `VolumeSummaryCards`), 9 locales, tests.
- [x] 4.2 `$lib/utils/rowMotion` (enter/exit/reflow/changed, batch limit) and its tests; applied to keyed table rows across dashboard/admin tables; jsdom `getAnimations` stub.
- [x] 4.3 Refresh no longer swaps a loaded list for a loader: admin floating IPs, admin users recent activity; stable keys for unkeyed rows.
- [x] 4.4 Real-browser check in tutorial mode: no row/loader churn on a manual refresh of eight list pages; a deleted row fades out (opacity 1→0) then leaves.
- [x] 4.5 `<tr>` rows drop `animate:rowReflow` (Svelte pinned outgoing rows with `position: absolute`, collapsing cells); real-browser check of a `<tr>` outro/intro and a grid-row outro (width and 9 columns kept, siblings slide).
- [x] 5.1 Full gate (3 known environment-only backend failures), commit on `dev`.
- [x] 5.2 Patch release 1.32.23 (tag `1.32.23` on `0d114029`, images, Helm, KO/EN Release) and DMS Lab Kolla rollout (rc0, 9 containers restarted, digests match); receipt in `docs/testing.md`.
- [x] 5.3 Production check with the managed backup account (role member/reader, read-only, in `afterglow_backend`): raw `project_id` hidden, classified `manual` without the proof and `auto`/`daily` with it. A human member browser session and the `get_os_conn` wiring were not observed.
