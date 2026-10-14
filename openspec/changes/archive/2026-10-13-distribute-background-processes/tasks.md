## 1. Process inventory and ownership contract

- [x] 1.1 Inventory Notion sync and Trove cron target discovery/execution and durable outcome boundaries.
- [x] 1.2 Inventory every Drover API/worker background task and preserve native job/operation claims.
- [x] 1.3 Inventory all remaining Afterglow, Lumen, Waygate and Palimpsest background entrypoints, including explicit local/request/broker roles, and finalize integration seams.

## 2. Afterglow implementation

- [x] 2.1 Generalize the proven dispatcher with role eligibility/balancing, renewable work fences and supervised drain/rejoin; migrate Cinder imports without a compatibility shim. (`WorkDispatcher`; leader-gap TTL defect fixed with real-Redis proof.)
- [x] 2.2 Partition Notion targets and legacy sync across worker processes while preserving global enable, intervals, per-process catalog and overlapping-output safety.
- [x] 2.3 Partition Trove scheduled backup targets with accepted/unknown slot authority and closed SDK connections.
- [x] 2.4 Divide API shared maintenance roles and scope host-local runtime reconciliation; own and drain every launched background task. (Worker runtime keyed by Docker Engine ID/Kubernetes Deployment UID with scale preconditions.)
- [x] 2.5 Make library/layer-build/import admissions durable and target-claimed, with leader-only safe recovery and no replay of submitted/unknown work. (Includes pending cancellation cleanup and SQL-decided optional consumer failure.)

## 3. Native service implementation

- [x] 3.1 Create and apply a native Drover change for missing role/cluster-target ownership without weakening SQL job/operation claims. (`isolate-service-execution-credentials` section 5; 5.6 checked.)
- [x] 3.2 Apply missing Lumen controller/worker ownership or retain evidenced native queue/lease ownership under its service-local change workflow. (Archived `2026-10-13-balanced-infrastructure-controller`.)
- [x] 3.3 Apply missing Waygate worker ownership or retain evidenced native ownership under its service-local change workflow. (Archived `2026-10-13-renewable-job-ownership`.)
- [x] 3.4 Apply missing Palimpsest Hub/worker ownership or retain evidenced native/local ownership under its service-local change workflow. (Archived `2026-10-13-lease-native-worker-maintenance`.)

## 4. Verification and delivery

- [x] 4.1 Exercise meaningful affected consumers and local real-Redis independent-process role/target balancing, stale-owner rejection, slow-work heartbeat, crash handoff and unknown non-replay. (`evidence/verification.json`, `docs/testing.md`.)
- [x] 4.2 Run affected targets/style and isolated source architecture guards, reporting concurrent outside-scope failures and unexercised production/container boundaries. (Guard `98e79ca0…`/2847 files; 11 outside-scope `test_instance_storage_delete.py` failures reported.)
- [x] 4.3 Update complete process ownership/deployment/testing/architecture/changelog records with actual evidence and archive completed repo-local changes. (Drover's bundled change is fully checked but left for its owner to archive with the credential cutover.)
