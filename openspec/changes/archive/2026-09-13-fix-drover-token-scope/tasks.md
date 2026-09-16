## Implementation Tasks

- [x] Separate actual Nova 503 from Drover 401 and prove caller scope loss.
- [x] Add failing behavioral regressions and preserve existing token scope in Drover authentication.
- [x] Require Drover availability in local dashboard smoke.
- [x] Rebuild affected local services and verify the affected user's real authenticated requests.
- [x] Run relevant regression gates and architecture guards, update documentation and archive this scoped fix.

The parent `consolidate-local-compose-runtime` change remains blocked on external Nova recovery even if this authentication fix completes.

## Runtime evidence

- The same affected non-admin DMSLAB session returned Drover 401 without `X-Project-Id` and 200 with it before the fix. The error detail was `A project-scoped Keystone token is required`. Direct Keystone introspection of that same token returned 200 and preserved DMSLAB.
- An administrator's DMSLAB-scoped token also demonstrated scope drift: token reauthentication without a requested project switched to `admin`; explicit rescope retained DMSLAB.
- Two new scope-preservation regressions failed before the source fix. After the fix, all six focused authentication cases and 24 auth/API/policy domain cases passed.
- Rebuilt and recreated only local Drover API/worker. The affected session now returns 200 and real `total`/`active` counts both with and without `X-Project-Id`; no password, role assignment, token revocation or cloud resource changed.
- Authenticated calls from the local Afterglow container using the affected DMSLAB session passed strict Cinder, Neutron and Manila quota reads. Nova's configured endpoint is `http://172.30.0.253:8774/v2.1`; server-list/quota/limits failures remain upstream 503. Host-header variation did not alter that response. Read-only controller SSH access was denied, so no remote service repair was performed.

## Final verification

- The actual deployed Afterglow dashboard handler using the affected session's Keystone-scoped connection returns `{"total":0,"active":0,"available":true}`. Both direct Drover header variants return 200 after deployment; the deployed authentication source hash matches the reviewed source.
- Full `npm run services:smoke` passes service/BFF/Lumen context checks and explicitly prints `Dashboard Drover stats: passed`. It exits 1 only for dashboard instances/quotas returning Nova 503. The owned temporary empty conversation used for context smoke was deleted with HTTP 204; no provider completion was called.
- Afterglow `npm run test:gate`: 2,725 backend, 1,285 frontend, 120 contract and 24 functional cases passed; orchestration and backend lint/format passed.
- Drover `uv run pytest tests -q`: 616 passed, 3 skipped; changed-file lint/format passed. Focused before-fix evidence was two failing scope-preservation regressions, followed by six focused and 24 domain cases passing after the fix.
- Current-source staged architecture guards passed through disposable indexes: Afterglow 2,005 files and Drover 208 files. Both real Git indexes remained byte-identical. No commit/push was performed.
- Attaching to the user's browser relay timed out. Verification therefore uses actual authenticated upstream HTTP requests, the deployed dashboard handler, and the full CLI smoke; no fresh visual/browser-success claim is made. The parent deployment change remains active for Nova availability.
