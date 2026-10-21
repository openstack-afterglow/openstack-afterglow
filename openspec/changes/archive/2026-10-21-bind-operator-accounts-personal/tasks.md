## Implementation
- [x] Resolve operator Accounts/Personal with no auto-creation; preserve historical recovery.
- [x] Update creation fixtures and meaningful failure-boundary regressions.
- [x] Restrict public password login to Accounts and preserve separate canonical link proof.
- [x] Exercise actual service entry points, run related tests, and record verification limits.
- [x] Update deployment/architecture/changelog and archive the change.

## Verification
- Installed SDK over loopback native HTTP: supplied domain UUIDs, GET-only resolution, Accounts-only user inventory, outside-only alias rejected.
- Affected backend645 passed; full configuration-isolated backend unit8697 passed/94 skipped; frontend4801 passed and final LoginPage60 passed.
- Frontend build and Svelte check0errors/16warnings; i18n0errors/37warnings; Ruff check and format714 passed.
- Repo-cwd broad tests were contaminated by private deployment config; network guard remained active. External isolated cwd used unchanged source and full selectors. See docs/testing.md and ~/.local/share/afterglow-proofs/operator-domains-20261021/.
- Full test:gate, DB functional and live OpenStack not run; no commit/push/deploy/native mapping/account migration.
