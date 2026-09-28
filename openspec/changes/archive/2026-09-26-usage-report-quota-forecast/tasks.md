## Implementation Tasks

- [x] 0. Confirm `dev`, preserve existing worktree changes, and create this rapid OpenSpec change.
- [x] 1. Preserve Nova usage flavor, timestamps and uptime in `nova.get_project_usage`.
- [x] 2. Read Nova's `total_vcpus_usage` in usage-stats.
- [x] 3. Rebuild usage-report aggregation, quota blocks and pure forecast helpers.
- [x] 4. Replace stale backend mocks and add Nova, endpoint and forecast regression tests.
- [x] 5. Extend frontend dashboard quota types for existing inventory fields.
- [x] 6. Recompose the usage-report page with KPI, forecast, instance usage and project inventory sections.
- [x] 7. Update mockup transport to the new usage-report contract.
- [x] 8. Add frontend usage-report behavior tests.

## Verification Tasks

- [x] Run exact backend/frontend selectors and the design target.
- [x] Build affected images for declared architectures and redeploy local Compose with volumes preserved.
- [x] Exercise authenticated usage-report API and responsive browser views.
- [x] Update architecture/API docs, stamp architecture, run `npm run test:gate`, and archive this change.

## Verification Evidence

- Exact backend selectors: Nova service 2, report 16, dashboard 12, usage-stats 4 tests passed. Frontend report 3 tests passed; design 109 and mockup 31 tests passed. Related instances target: backend 270/frontend 35 passed; access target: 136 passed.
- Final full gate passed: architecture/docs guard, orchestration 137 tests, backend unit 2,995, frontend 1,459 (250 files), contracts 132, real-datastore functional 27 (3 deselected), and Ruff check/format (506 files). Final Svelte check: 2,063 files, 0 errors/warnings. `check_architecture.py --staged` passed without staging changes.
- Authenticated local API: 30d returned real GPU flavor names (no `unknown`), 16,973.5 vCPU·h, 67,894 RAM GB·h, 2,121.69 GPU·h, and 30 allocation samples. Compute quota was 8/64 vCPU and 32,768/393,216 MB; Cinder was 7,600/10,000 GB. Response was HTTP 200 with `Cache-Control: private, max-age=60`.
- 90d returned a 90-day date span and 90 samples, including an additional CPU flavor. Usage-stats returned the same 16,973.5 vCPU·h as the 30d report. Existing full quotas returned network/storage/compute/Manila inventory plus Swift and Trove statistics.
- Responsive browser checks at 390, 767, 768, 900, 1023, 1024, 1280px: no document/main horizontal overflow; tables scroll inside TableShell. KPI columns change 2→3; inventory columns 1→2→3; flavor/forecast panels split at desktop. Real 7d/90d range interaction and zero-byte display verified; browser console had no errors.
- Backend and frontend built for linux/amd64 (declared CI target) and linux/arm64 (local runtime). Local deployment used canonical `docker-compose.dev.yml`, project `afterglow-local-services`, and the launcher's private env sources with targeted `--no-deps up --build --wait`; existing volumes and sibling services were preserved. Both application containers became healthy. Backend image smoke confirmed x86_64/aarch64 and the real forecast helper output (slope 1, projected 100%, limit in 16 days).
- Final frontend image receipts: local arm64 `sha256:11f3e9c2f911173ea1772b46a3c2bdfd90eb2850c54a8c39036d555b1a5115e2`; amd64 `sha256:169112282cb9e7b155fa18c75c18f29c33a9512b698bfd8fd5378c6ad813f6e7`. The amd64 runtime reported Node v20.20.2/x64 and included the actual usage-report route. Final authenticated 900px/390px screenshots confirmed the user-scoped keypair limit (20), zero horizontal overflow, and no browser errors.

## Decisions and Verification Gaps

- Shared usage-report dependency mocks live in `backend/tests/conftest.py` instead of duplicating the same five-source context manager in two test files.
- Nova project quota does not provide user-scoped keypair usage. The inventory shows its user limit rather than a misleading zero-use project bar. Swift's zero bytes explicitly render `0 B`; the forecast spark fills its row and keeps min/max below it at narrow desktop widths.
- GPU flavor hours are verified against live OpenStack. GPU quota/type forecast bars are covered by backend/frontend tests but not live data: existing local GPU quota DB access raises `GpuQuotaUnavailable` (`afterglow-mariadb` is not the current local Compose DB service). Both existing full quotas and the report correctly return `gpu_available=false`; the UI shows the warning. No DB/env configuration was changed.
- Existing Lumen checkpointer startup failure remains untouched; the AI chat usage card is unchanged. Block storage intentionally has no historical forecast. Deleted flavor GPU type/count recovery remains limited to existing flavor-name fallback.
- No commit, push, production deployment, or volume deletion was performed.
- Build dependency installation emitted an existing moderate-severity audit warning; dependency versions were not changed. Optional gbrain synchronization was unavailable because the local CLI is not installed; repository guidance was not modified for it.
