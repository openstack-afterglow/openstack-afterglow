# Tasks

## 1. Instance detail

- [x] 1.1 Expiry date and action under the creation date (desktop and compact card).
- [x] 1.2 「기간 연장」 header button opens the usage editor dialog; reminder hash opens it once.
- [x] 1.3 Failed usage read shows an error with retry in the panel.
- [x] 1.4 Remove file-storage access and Afterglow information sections and their i18n keys.
- [x] 1.5 Tests: usage editor through a controller harness, panel dialog and failure retry, Waygate lock without the removed section.

## 2. Login workspace default

- [x] 2.1 Absent preference reconnects to the last workspace; opt-out requires a validated fixed domain+project.
- [x] 2.2 Tests for record/opt-out race, fixed default validation and login fallback.

## 3. Default SSH key

- [x] 3.1 Per-user default keypair endpoint and SSH key page control.
- [x] 3.2 Wizard preselects the default when it exists, including after GitHub SSH round trips and post-create resets.

## 4. Sessions

- [x] 4.1 Browser and major version from the User-Agent.
- [x] 4.2 IP country from GeoIP when available.

## 5. Account activity

- [x] 5.1 User endpoint returns only intentional resource changes; pagination over filtered rows; admin views unchanged.
- [x] 5.2 Native notification echoes excluded; MariaDB REGEXP dialect covered by `test_activity_log_db.py`.

## 6. Workspace selector latency

- [x] 6.1 Per-action native call analysis.
- [x] 6.2 Safe parallelization with tests; every authorization check still runs.

## 7. Volume backups and snapshots

- [x] 7.1 Backup and snapshot pages list source volumes first; per-volume detail shows creation time, automatic/manual with tier, method and creator.
- [x] 7.2 Manual backup create offers full/incremental; incremental requires an existing full. Snapshots are labelled incremental (copy-on-write) only.
- [x] 7.3 Automatic backup policy: daily incremental with chain length bounded by daily retention, weekly/monthly full, dependency-first retention.
- [x] 7.4 Chain rotation follow-up: judge chains only after the latest owned full; bounded drain of asynchronous deletes that never treats a pending delete as deleted; terminal receipts survive a user deleting the new backup during drain.

## 8. Verification and docs

- [x] 8.1 Full `npm run test:gate` stages including the MariaDB DB lane; 3 backend failures reproduce on the baseline with the shared operator `afterglow.conf` (see `docs/testing.md`).
- [x] 8.2 `ARCHITECTURE.md`, `docs/testing.md`, `CHANGELOG.md`, architecture stamp.
