# Tasks

- [x] 1.1 `listedRecoveryGroups` helper; both pages list only volumes with points; keep full groups for details.
- [x] 1.2 Empty-state strings `backupGroups.empty` / `snapshotGroups.empty` in 9 locales; search keeps `page.noMatches`.
- [x] 1.3 Tests: helper, page hides empty volumes but keeps them creatable, empty state.
- [x] 2.1 `cinder._caller_project` / `_recovery_origin` fill a hidden owner from `_afterglow_authenticated_project_id`.
- [x] 2.2 Tests: hidden owner on real SDK HTTP reads (backup and snapshot), logical workspace differing from token project, `all_projects`, missing proof, visible foreign owner.
- [x] 3.1 ARCHITECTURE.md, CHANGELOG.md.
- [ ] 3.2 Full `npm run test:gate`, commit on `dev`.
- [ ] 3.3 Patch release and production rollout (needs owner approval); member-session probe of the DMSLAB gitlab backup after rollout.
