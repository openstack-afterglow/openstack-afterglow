## Implementation Tasks

- [x] Map both owned Compose projects, obsolete application images and preserved data.
- [x] Trace dashboard 503 to its actual upstream/configuration boundary.
- [x] Use one private current-source Compose project on conventional loopback ports.
- [x] Remove obsolete owned containers/application images without deleting volumes or unrelated workloads.
- [x] Rebuild current source images and complete migrations before API/worker readiness.
- [ ] Verify real login, dashboard summary/quotas, service BFFs and Lumen administrator billing contract.
- [ ] Run relevant regression gate, update architecture/deployment records and archive the change.

## Observed deployment evidence

- Removed 27 containers belonging to `afterglow` and `afterglow-local-services`, 145 obsolete application image references and the empty legacy network. Preserved ten named volumes, private encryption keys, the original config, and unrelated workloads. No global Docker prune or volume deletion was used.
- Rebuilt sibling/Afterglow source images; one private project now serves loopback 3080/8000/8010/8011/8012/8020/6379. Four migration/bootstrap containers exited successfully; APIs passed health checks and workers are running. Backend/frontend were explicitly recreated and their running image IDs matched current tags.
- The copied Kubernetes public OpenStack path caused browser login to hit the 30-second request deadline. A read-only internal-catalog authentication probe completed auth in 1.89s plus user lookup in 1.30s. After backing up and correcting only the private snapshot, real browser login returned 200 in 8.347s and opened the dashboard.
- Real administrator models/providers/bulk billing GETs returned 200 with no billing UI alert. PATCH of `billing_admin_key: null` on the owned, already-keyless local verification provider returned 200; no fake key or user's existing credential was saved/changed. This proves the request contract, not external provider key validity.
- Authenticated Waygate/Drover/Palimpsest BFF checks and Lumen model/context checks passed. Sonar remains 128,000 tokens with a reconciled context breakdown.

## Historical Nova failure and remaining full-smoke gap

- DMSLAB dashboard overview summary and quotas both return 503. The initial Drover stats check established HTTP 200 only, not affected-user availability. Follow-up `fix-drover-token-scope` found the affected user's valid scoped token received upstream 401 while Afterglow returned `available: false`; administrator/default-project checks had missed this distinction.
- Nova returns 503 and `No server is available to handle this request` at the public catalog URL and the internal `http://172.30.0.253:8774/v2.1` endpoint. TLS/SNI routing through the internal VIP also returned 503. Backend traces identify failed Nova server-list and quota requests, not a frontend or local-container routing failure.
- `npm run services:smoke` deliberately exits 1 on these dashboard failures after other local service checks pass. No empty-success fallback or timeout inflation was added.
- A later current-source rebuild verified authenticated dashboard summary/quotas 200 and Drover statistics `available: true` in the selected local session. This supersedes the claim that every current dashboard read still fails, but does not replace the original full DMSLAB smoke. Keep this parent change active until that complete scoped smoke, including its configured Lumen model/conversation prerequisites, passes. Remote cloud services were not modified by the local rebuild.

## Final regression and documentation evidence

- `npm run test:gate` passed against working source fingerprint `394ac866bff0db875fcd80e9c6557c509dee4a6a83b630cf55b16f5815f0d17a`: 2,725 backend unit tests, 1,285 frontend tests, 120 contracts and 24 real-datastore functional tests; orchestration and backend lint/format checks passed. Deprecation warnings remain non-failing.
- Updated the root and detailed architecture documents, local deployment instructions and changelog. Current-source architecture checks passed with 2,005 Afterglow files and 279 Lumen files. `--staged` was exercised using disposable indexes populated from the reviewed current worktrees, and both real Git index byte snapshots remained unchanged.
- Final recreated backend/frontend are healthy and all owned source application image IDs match their current tags. Browser billing returned 200 again after recreation. The current-image smoke still exits 1 only after reporting the dashboard summary/quotas 503 errors.
- Private config comparison against its backup confirms only OpenStack `auth_url` and `interface` changed; private config and key-file permissions remain 0600. The dedicated verification browser was stopped. The canonical local application stack remains running.
- No commit, push or remote OpenStack repair was performed. The final checklist item is incomplete only because archiving would incorrectly imply the blocked dashboard acceptance criterion passed.
- Subsequent `separate-compose-deployment-modes` work replaced the local overlays with canonical `docker-compose.dev.yml`, reduced the base manifest to frontend/backend, and added pull-only TLS/catalog production mode. The same project, private configuration, keys and volume identities remain in use. The current full gate passes with 2,721 backend unit tests after removal of four source-pinned tests; 1,285 frontend, 120 contracts and 24 functional tests pass. A fresh DMSLAB browser session still displays Nova-backed instance/quota failures while trend and corrected Drover stats return 200. This does not satisfy or close the remaining parent dashboard criterion.
- Pre-push correction verification passed the final gate (2729 backend unit, 1303 frontend, 124 contracts, 24 functional). Config snapshot permissions are now 0640 with a narrowly mapped supplemental GID; the private directory remains 0700 and keys/compose.env remain 0600. Actual container config reads and local Drover Redis PING passed; key values and mounted volume identities were preserved. Live quota navigation also survived a real browser token refresh. These results do not claim a provider completion or full configured Lumen context smoke.
