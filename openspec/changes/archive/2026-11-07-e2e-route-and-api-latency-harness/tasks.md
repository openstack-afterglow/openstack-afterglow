# Tasks: e2e-route-and-api-latency-harness

- [x] Discovery: audit existing test layers, root package.json scripts, frontend routes (160 +page.svelte files), and auth/client contracts.
- [x] Implement core primitives: percentile math, route inventory/plan, redaction, templating, and safety policy (`scripts/latency/core.mjs`).
- [x] Implement API lane: login timing, sequential endpoint measurement, concurrency ramp with batch wall-clock durations, OpenAPI discovery (`scripts/latency/api-lane.mjs`).
- [x] Implement Browser lane: CDP over Node 24 WebSocket, real UI login, cold/warm passes, network-quiescence page readiness detection (`scripts/latency/browser-lane.mjs`).
- [x] Implement report generator: JSON record + Markdown tables + opt-in budget checks (`scripts/latency/report.mjs`).
- [x] Implement CLI and orchestration runner (`scripts/latency/run.mjs`).
- [x] Unit test suites: core (`scripts/latency/core.test.mjs`), API fixture (`scripts/latency/api-lane.test.mjs`), browser fixture (`scripts/latency/browser-lane.test.mjs`), runner (`scripts/latency/run.test.mjs`).
- [x] Wire `latency` and `test:latency` scripts into `package.json`, and non-browser latency suites into `test:orchestration`.
- [x] Add `latency-reports/` and `output/latency/` to `.gitignore`.
- [x] End-to-end smoke test against loopback fixture stack.
- [x] Documentation updates: `docs/testing.md`, `ARCHITECTURE.md`, `CHANGELOG.md`.
- [x] Archive OpenSpec change.
- [x] Run test gate verification.
