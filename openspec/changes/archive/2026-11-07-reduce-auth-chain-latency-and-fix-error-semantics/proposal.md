# OpenSpec Proposal: reduce-auth-chain-latency-and-fix-error-semantics

## Why
Follow-up audit of the `cloud.dmslab.re.kr` latency report found a cost shared by every authenticated request:
trivial endpoints (`auth/me`, `announcements/unread-count`, `tutorials/status`, ...) took 2.3-2.6 s sequentially
(no concurrency) while unauthenticated `site-config` took 34 ms; admin routes took about twice that.
A synthetic reproduction (real `get_token_info`, real JWT/Redis, injected per-call native latency) showed 19 serial
native reads for one member request, dominated by an N+1 in `domain_projects._accessible_domains`
(one `projects.get` and `domains.get` per workspace, in turn). The same audit found object listing mapping every
provider error to an unlogged 500, and the latency harness recording expired-token 401s as latency samples.

## What Changes
1. `domain_projects._warm_exact` prefetches independent project/domain exact reads concurrently into the
   operation-local read memo, capped at 4 workers per request (`run_parallel(max_workers=)`). The ordered judgment loop
   is unchanged; failed prefetches are not stored, so the loop re-reads and reports them in its own order. No
   cross-request cache. The shared native socket pool is sized explicitly (`_POOL_MAXSIZE = 32`, requests default 10)
   after a real-socket loopback measurement showed uncapped fan-out on a 10-socket pool multiplied new TCP connections.
2. `Server-Timing` gains `auth;dur=` (the `get_token_info` span, including rejected responses).
3. `GET /object-storage/{container}/objects` uses `native_resource_read_failure` (404/403/401 -> 404, otherwise 503)
   and logs a warning. One existing test's incidental `500` assertion is updated to the 503 contract.
4. Latency harness: 401 is never a latency sample; preflight probe, single-flight `refreshAuth`, `aborted`/`INVALID`
   reporting, and an API budget cannot pass when the lane aborted.
5. Tests: scoped-credential negative cases (role set change, missing/short/expired lifetime, different source token),
   `_accessible_domains` concurrency/failure/disabled cases, Server-Timing, list-objects failure statuses, harness 401 guard and report.

## Non-Goals (documented, not done)
- Concurrent prefetch of the remaining independent auth phases (needs single-flight memo + ordered error evaluation).
- Skipping `require_admin`'s repeated chain on read-only admin routes (security policy decision).
- Per-project `_sources` reads for group-based assignments remain serial.
- No deployment and no live before/after re-measurement; real Keystone/HAProxy connection and TLS impact of the cap/pool values is unmeasured (open risk).
