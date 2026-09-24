## Tasks

- [x] Trace Keystone refresh classification, browser lifecycle and explicit logout failures.
- [x] Reproduce invalid-token, transient outage and invisible background failures with focused regressions.
- [x] Normalize invalid-token failures without treating arbitrary 404 as invalid credentials.
- [x] Expose a fenced recovery dialog and terminal background logout; preserve drafts and retry cooldown.
- [x] Prove logout cleanup survives rejected pending refresh and unavailable revocation.
- [x] Verify focused regressions and real responsive browser recovery flows.
- [x] Build frontend/backend for supported architectures and deploy canonical local services safely.
- [x] Run required gates, update docs/architecture and archive with exact evidence.

## Verification

- Invalid-token refresh and invisible background-401 regressions failed before the fix. Final token classification regression: three cases passed (`Failed to validate token` and `Could not recognize Fernet token` → 401; arbitrary resource 404 → 503 with recoverable session).
- Final `npm run test:gate` passed: backend unit 2,905, frontend 1,444 across 248 files, consumer contract 132, disposable MariaDB/PostgreSQL/Redis functional 27; backend Ruff check and formatting passed. `npm run check` reported zero errors/warnings. Known dependency deprecation and short-test-key warnings remain.
- Actual Chromium fault injection on the real root shell: 503 displays a non-dismissible gate, cooldown-aware retry restores the same draft and removes inert isolation, terminal background 401 clears credentials and reaches login, and failed pending refresh plus failed server revocation still clears local credentials and reports unconfirmed revocation. Responsive bounds passed at 390, 767, 768, 1023, 1024, 1280 and 1440 pixels; no horizontal overflow.
- Built root Dockerfile backend, frontend and copied-source worker targets for both linux/amd64 and linux/arm64. Executed backend normalization, frontend handler import and worker runtime/crypto smoke in the images. Canonical `docker-compose.dev.yml` build and targeted `up --no-deps --no-build --force-recreate --wait backend frontend` left both services healthy; unrelated services/volumes were preserved. Ran worker crypto smoke via an ephemeral Compose worker without starting scheduled Notion writes.
- Deployed backend on 127.0.0.1:8000: real Keystone login, `/auth/me`, and rotating refresh returned 200. Only a newly created smoke session's upstream-token snapshot was replaced with an invalid token: actual Keystone returned `Could not recognize Fernet token`, reproduced the remaining 503, then returned terminal 401 after the final fix/redeployment. Existing user sessions were untouched.
- Deployed browser at 127.0.0.1:3080: actual login reached dashboard, lifecycle refresh and `/auth/me` returned 200 without response mocks, project/resource content loaded, and explicit logout returned 200 and cleared browser credentials.
- Architecture working stamp and required `--staged` guard passed for source SHA-256 `6486ec5fad118d1836299d1757a7449c9ef86296d39551802ac16b5006ccddd8`. The staged check used an isolated temporary index; the user's real index was unchanged. No commit, push or production deployment.
