## Implementation Tasks

- [x] Map test Compose consumers and isolation requirements.
- [x] Integrate isolated functional MariaDB/PostgreSQL/Redis into the development test profile without requiring cloud credentials for test-only parsing.
- [x] Remove the standalone test manifest and migrate lifecycle callers, tests and documentation.
- [x] Exercise real development startup, successful/failing functional lifecycle and preservation of app containers, volumes and private configuration.
- [x] Complete regression gates and architecture freshness; archive the change.

## Verification evidence

- A temporary directory containing only the dev manifest, with no private config, .env, sibling source or cloud credentials, started exactly the three healthy test services. All three datastore paths use Docker tmpfs. `--no-start` passed 24 real-datastore tests and retained the external containers until the probe explicitly removed them.
- The canonical npm runner passed 24 functional tests with `--keep` and left all test services running. A subsequent real invalid-target failure returned exit 1 and removed only the three test services. An intentionally unselected container and an unused named volume declared by the dev manifest both survived. Those owned probes were then removed explicitly.
- All 18 existing development container IDs and the exact bytes of the private config, original config and secrets file survived these test lifecycles. No development data or remote OpenStack resource was changed.
- `npm run services:config` and `npm run services:up` succeeded against the canonical dev manifest. The final normal development stack has 14 running services, all defined health checks passing, and four successful migration/bootstrap jobs. Application mount identities and private configuration bytes remain unchanged.
- Lifecycle unit regressions passed (6 cases); the final `npm run test:gate` completed successfully. App backend/frontend source and production composition were not changed by this task. The existing upstream Nova 503 remains outside this consolidation; no cloud repair or provider completion was attempted.
- Actual frontend/backend health and normal login returned 200. Canonical authenticated Lumen models, Waygate discovery, Drover `/api/v1/k3s` discovery/clusters and Palimpsest Hub layer reads returned 200. No test containers remain after verification; the dev stack remains running.
- Architecture stamp and isolated-index `--staged` verification passed with source fingerprint `34fcdc3e8974955e2ad2e9830b9c0a98f93ed5b6a7d1e466bf52333d3edb8106` (2,001 files). The real Git index was byte-identical. Temporary manifest directory, preservation container and sentinel volume were removed. No commit or push was performed.
