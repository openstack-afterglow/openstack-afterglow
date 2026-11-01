## Implementation Tasks

- [x] Bind issuance, consumption, provisioning and terminal monitoring to current immutable login-family authority without disrupting ordinary refresh.
- [x] Track and explicitly revoke exact shell-derived tokens across abandoned tickets, revoked sessions, failures, disconnects and reconciliation; preserve cleanup receipts on uncertainty.
- [x] Implement pinned native Zun pre-execution CPU/PID/rootfs/tmpfs/log/network enforcement and lifecycle rechecks, without breaking the setuid bootstrap.
- [x] Require exact native runtime proof and isolated security-group admission; synchronize blocked-CIDR configuration across all renderers.
- [x] Exclude WebSocket query tickets from proxy/access logs and redact them through the existing sanitizer.
- [x] Run focused security regressions and actual isolated API/Redis/native driver/runtime smoke, then affected targets and architecture/build checks.
- [x] Update existing Cloud Shell/API/deployment/security/testing documentation, ARCHITECTURE.md and CHANGELOG.md with source evidence and explicit rollout/production limits.

## Verification Boundary

- Local proof:216 core backend,1165 auth-target,55 real-Redis schedules,77 actual config/proxy contracts; installed pinned Zun57 cases on each architecture; actual Linux namespace/cgroup and four workload-image setuid/CLI cases; frontend5772 tests/474 files plus Node9, check0errors/16warnings and real managed Chromium owner/login/ordinary-refresh lifecycle.
- Canonical backend/worker/frontend targets built on arm64/amd64 offline with verified dependency/cache-only restoration; changed app stages executed, no old app substituted. Native integration/holder images built on both architectures. Full startup evidence retains its pre-format image/supervisor signal-exit qualification; final image imports/source/tool proofs are separate. Cold dependency acquisition and production fleet acceptance are not claimed.
- Whole-suite attempts retain their exact failures/fixture prerequisites in `docs/testing.md` and private proof receipts. No `test:gate`, commit/push, production/IAM/resource changes or user-home deletion. Unrelated concurrent source/index is preserved.
- Before operational activation: qualify every eligible native compute/Kuryr/rootwrap/PID namespace, actual management CIDRs, immutable holder/workload pulls, storage/user-namespace policies and external ingress/WAF logs; drain stock sessions and coordinate cutover. Emulated holder137 and existing initial xterm-output loss remain explicitly unqualified/out of scope, not silently fixed.
