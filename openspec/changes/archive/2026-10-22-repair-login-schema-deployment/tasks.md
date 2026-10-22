## Implementation Tasks

- [x] Identify exact configured DB/server, actual local/deployed writers, schema drift and rollback identities without exposing secrets.
- [x] Create a protected consistent Afterglow database backup; restore it to an isolated matching-engine database and prove original data can be read.
- [x] Apply only missing manifest-owned093/096/098/099 schema/data postconditions to the restore; verify column definitions, row/journal preservation and the formerly failing ORM query.
- [x] Drain affected live Afterglow writers, capture final backup/state, apply reviewed missing changes with bounded lock time, and verify database/native preservation.
- [x] Restore the same services/images/configuration, exercise the repaired login preparation/HTTP surface, and distinguish any unavailable user credential proof.
- [x] Verify the actual deployment schema prerequisites and existing canonical bootstrap path; do not claim create_all or image health performs migrations.
- [x] Update architecture/deployment/testing/changelog with observed recovery evidence and limitations; validate/archive this change and preserve shared index/concurrent work.
