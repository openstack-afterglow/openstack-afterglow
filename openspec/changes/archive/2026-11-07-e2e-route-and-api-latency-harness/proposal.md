# OpenSpec proposal: e2e-route-and-api-latency-harness

## Context and motivation
Afterglow lacks an automated end-to-end harness that can audit both the full set of web routes and any API endpoint for latency:
- How long an API endpoint takes from issue to final body byte, separated from the authentication phase.
- How long concurrent requests take to return as a batch wall-clock duration under concurrency ramps (1, 5, 10, 20).
- How long each real web route takes in Chromium from navigation start until page-ready (DOM load fired, no in-flight `/api/*` calls, and quiet window elapsed), plus the per-page `/api/*` waterfall.

## Scope and design
- **Implementation**: Node 24 native ESM harness under `scripts/latency/` with zero new external dependencies.
  - `core.mjs`: Linear-interpolation percentile math, SvelteKit `+page.svelte` scan (160 routes in repo), dynamic route regex and fixtures, URL redaction (stripping credentials, fragments, and sensitive query keys), endpoint templating (`:id`), and strict safety policy (remote target allow-list, read-only methods with only login/logout mutations allowed).
  - `api-lane.mjs`: Authentication phase timing (`POST /api/v1/auth/login` rate-limit-aware sampling), sequential warm-token endpoint measurement, concurrency ramp measuring batch wall-clock durations and throughput, and `/openapi.json` discovery.
  - `browser-lane.mjs`: Chromium driven over Chrome DevTools Protocol (CDP) via Node's global `WebSocket`, authenticating through the real login form, visiting routes in cold/warm passes, and detecting page readiness by network and DOM quiescence.
  - `report.mjs`: Structured JSON artifact + Markdown table rendering with percentiles, slowest pages, and opt-in budget evaluation.
  - `run.mjs`: CLI with environment-only credentials, dry-run mode, and filter/fixture support.
- **Test coverage**:
  - `core.test.mjs`: Percentile math, route inventory/matching, URL redaction, safety assertions.
  - `api-lane.test.mjs`: Verification against loopback HTTP fixture with artificial delays (auth separated from request time, 10 concurrent requests overlapping within ~1x delay rather than serial, SSE stream short-circuiting, 500 error recording).
  - `browser-lane.test.mjs`: Real Chromium against local fixture page with delayed fetch, long-polling hang detection (`not_ready`), client-side redirect tracking, blank page detection, and cold/warm pass order.
  - `run.test.mjs`: CLI parsing, budget validation, dry-run against real repository routes tree.

## Non-goals and risks
- Latency thresholds are not enforced by default in CI gates to avoid flakiness on shared runners; `--budget-ready-p95-ms` and `--budget-api-p95-ms` are strictly opt-in.
- The harness is read-only. It never mutates resources; only its own login/logout sessions are created and cleaned up.
- Browser lane tests are wired to `npm run test:latency` (requires Chrome). Non-browser latency tests are wired into `npm run test:orchestration`.
