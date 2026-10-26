## Why
Users report slow backend/list responses, slower GitLab SSO, involuntary logout within the intended one-day refresh window, repeated dashboard polling, and need administrator cross-domain/project volume transfer and key-based acceptance. Prior source-only storage/topology/Lumen fixes and concurrent changes must be preserved.

## What Changes
1. Measure frontend-to-backend overhead, backend execution and OpenStack round trips separately. Fix reproduced redundant work, blocking work and response/cache inefficiency without weakening current authority.
2. Trace password and GitLab login critical paths and remove proven avoidable latency while preserving native mapping and account validation.
3. Restore legitimate automatic refresh within the configured one-day session ceiling, including background resume and token rotation races, preserving explicit revocation and transient outage semantics.
4. Inventory all dashboard/admin list polling families; improve shared request scheduling/coalescing/cache and mutation invalidation. Preserve owner/scope/ABA isolation and observable failure/partial states.
5. Replace header-only administrator Cinder acceptance with verified source and actual destination-project scope. Offer selected domain/project transfer, once-only generated-key recovery/copy and supplied-key acceptance under native policy.

## Constraints
Source changes on dev only. No staging/commit/push/release/deploy, production config/IAM changes or live volume mutation. No authority caching, arbitrary stale successes, POST retries or header impersonation. Preserve shared index, keys, settings, data and existing source work.

## Acceptance
Record before/after measurements and call counts with exact real/synthetic boundaries; exercise all five changes through actual HTTP/compiled UI; run focused and named checks plus canonical gate where feasible. Update affected architecture/API/testing documents and archive with evidence. Actual human GitLab callback, live transfer or production rollout remain unclaimed unless exercised with existing authorized prerequisites.
