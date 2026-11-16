# Tasks

## 1. Instance detail

- [x] 1.1 Expiry date and action under the creation date (desktop and compact card).
- [x] 1.2 「기간 연장」 header button opens the usage editor dialog; reminder hash opens it once.
- [x] 1.3 Failed usage read shows an error with retry in the panel.
- [x] 1.4 Remove file-storage access and Afterglow information sections and their i18n keys.
- [x] 1.5 Tests: usage editor through a controller harness, panel dialog and failure retry, Waygate lock without the removed section.

## 2. Login workspace default

- [ ] 2.1 Absent preference reconnects to the last workspace; opt-out requires a validated fixed domain+project.
- [ ] 2.2 Tests for record/opt-out race, fixed default validation and login fallback.

## 3. Default SSH key

- [ ] 3.1 Per-user default keypair endpoint and SSH key page control.
- [ ] 3.2 Wizard preselects the default when it exists.

## 4. Sessions

- [ ] 4.1 Browser and major version from the User-Agent.
- [ ] 4.2 IP country from GeoIP when available.

## 5. Account activity

- [ ] 5.1 User endpoint returns only intentional resource changes; pagination over filtered rows; admin views unchanged.

## 6. Workspace selector latency

- [ ] 6.1 Per-action native call analysis.
- [ ] 6.2 Safe parallelization with tests; every authorization check still runs.

## 7. Verification and docs

- [ ] 7.1 Backend and frontend unit suites, contract, Ruff, svelte-check, i18n.
- [ ] 7.2 `ARCHITECTURE.md`, `docs/testing.md`, `CHANGELOG.md`, architecture stamp.
