# Checklist

- [x] Existing user/session UI, identity role DAG, repository development/design rules reviewed.
- [x] Implement administrator-only user effective permissions API and behavioral regression tests.
- [x] Display permissions alongside sessions with loading/error/empty states and response fencing; translate all four locales.
- [x] Run focused backend/frontend tests, checks and actual local HTTP/browser smoke.
- [x] Update API/architecture/changelog documentation with actual evidence and limitations; archive this change.

## Verification and limits
Backend permission/identity selectors: 161 passed; canonical access backend selectors: 276 passed (same source/selectors, `/tmp` cwd avoids a pre-existing local TOML parse failure at line 10, column 9). User modal: 22 passed; neighboring role UI: 15 passed. Scoped backend Ruff, frontend check (0 errors, 1 existing DocCodeBlock warning), i18n check/scan, production build passed. Actual FastAPI + installed SDK + loopback Keystone fixture proved 2-page role/scope output, implication expansion, 403 and 404. Actual Chromium proved independent error/retry/empty/user transition and 24 locale/theme/viewport layouts including long IDs/names/role chips, zero horizontal overflow and reachable action buttons. Cloud identity/API data is synthetic; no production mutation, deployment, commit or push. Full test:gate was not exercised.

## Final inheritance correction
- [x] Reproduce actual effective inherited scope through the installed SDK and loopback Keystone HTTP: project plus retained `OS-INHERIT:inherited_to="projects"` failed with 503 before the fix.
- [x] Validate exactly one project/domain/system scope and separately validate marker value and project target; retain malformed-marker/mixed-scope/unknown-metadata rejection.
- [x] Final permission/identity 167 and canonical access selectors 276 passed; scoped Ruff passed. Actual Uvicorn HTTP → installed SDK → loopback Keystone returned 200 with destination project and implied role. Synthetic admin authentication only, no operational mutation or deployment.
- [x] Final isolated source overlay9 architecture staged digest/review passed: `943f2b28c4eb3e4cf984e02b219200f2f0a22dce9e7ba386fa2c9e76aa0f3c55`, 2,531 source files; real shared index/review block unchanged. Earlier 161/source digest evidence is historical, not final.
