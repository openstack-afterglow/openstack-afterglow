## Tasks

- [x] Read migration failure and identify stale/missing workspace packaging before SQL execution.
- [x] Build current canonical Compose services with final Lumen packaging.
- [x] Verify affected Lumen images on linux/amd64 and linux/arm64.
- [x] Apply migrations safely and prove repeat execution succeeds with preserved data.
- [x] Start canonical services and verify health, worker readiness and authenticated runtime paths.
- [x] Record exact evidence, run repository gates/architecture checks and archive recovery.

## Verification evidence — 2026-09-24

- `npm run services:up` completed current-source builds and canonical local deployment. All 14 long-lived services run; every configured health check is healthy. All four migration/bootstrap one-offs exited 0. Workers without a configured Docker health check are not represented as independently healthy by that status alone.
- The rebuilt `lumen-migrate` and a second `run --rm --no-deps lumen-migrate` exited 0. Ledger 015/016 is present; prior conversation/message/run/model/provider counts were all zero and remained zero. Backup: private `.local-services/backups/lumen-before-plugin-recovery-20260924T064935Z.sql` (69484 bytes, 0600). Existing local volumes and keys were preserved.
- Lumen API/worker/controller shared-runtime targets built for amd64 and arm64; six network-disabled runtime probes imported all plugin distributions and all three entry-point modules. The controller was not enabled in Compose, and standalone sandbox cloud provisioning was not exercised.
- Real authenticated HTTP 200: chat model list; Lumen admin providers/models/plugins; Waygate, Drover and Palimpsest discovery and lists; OpenStack dashboard summary and quotas. Lumen worker DB registration: accepting=1, draining=0, capacity=4, heartbeat age=2 seconds at observation.
- `npm run test:gate` passed (including 27 datastore functional tests, Ruff and format checks). Focused Lumen migration/Kolla tests: 25 passed.
- Full `npm run services:smoke` is not claimed: it stops at missing active model and owned conversation for context preview. Real provider inference remains unverified without provider keys.
- Current independent Lumen development gates remain red: 1245 service tests pass but Ruff reports 46 findings; SDK has 125 passed/1 route-table coverage failure; default integration collection cannot import standalone lumen_sandbox, and service-only integration has 7 passed/1 failure/3 FK errors; process-system migration fails parsing runtime_config from EnvSettingsSource. Full evidence is in the sibling fix-plugin-image-packaging archive. These were not hidden by narrowing a green gate or changing unrelated development.
- This archive closes only the reported image/import/deployment recovery, not the original live-provider-model-onboarding change or the independent Lumen development gates. No commit, push or production deployment.
