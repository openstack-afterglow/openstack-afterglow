## Why

The read-only security review found retryable expired browser sessions, concurrent refresh rotation, uncancelled MCP SDK work and inaccurate destructive annotations. Related gaps include concurrency lease accounting, GitLab origin binding, optional OAuth refresh client binding, cacheable one-time credentials, stale invocation status and persistent browser credentials/inline scripts.

## What Changes

- Keep immutable browser session lifetime across refresh/rescope and atomically consume rotated sessions; bind federated login origins and report revocation failures.
- Fence SDK dispatch after cancellation/deadline, retain slots for running work, use ownership-safe concurrency leases and truthful tool annotations.
- Require OAuth refresh client binding, disable caching of PAT issuance, and reconcile expired mutation leases to unknown without resending.
- Remove long-lived localStorage credentials and script unsafe-inline using supported SvelteKit CSP generation.
- Add behavior regressions, update architecture/security/API contracts, and obtain independent review.

## Capabilities

### New Capabilities

None. This patch strengthens existing authentication and MCP contracts.

### Modified Capabilities

Browser authentication, MCP OAuth/consumer execution, browser credential handling and response cache/CSP policies.

## Impact

Current local dev source only. No branch switch, release/version bump, commit, push or production deployment. OAuth clients must send their issuing client_id on refresh. Existing persistent browser credentials are discarded; newly issued credentials use tab-scoped sessionStorage. Synthetic identity/cloud boundaries and real datastore/browser checks will be reported separately.


## Verification Receipt

- Base dev and freshly fetched origin/dev: c210f5018ba9928dee6b0def9ed0cd61c7813f5e.
- Final source SHA-256: 1029b79c96c1effef9de9abe4760e8502a8aafbcdc7e1f48fcb9f158e6fdb7ff; original and private-config-free isolated clone match.
- Final npm run test:gate exit 0: backend 4,458; frontend 2,577 in 334 files; contracts 154; real datastore functional 43 (9 deselected); Ruff check/format pass.
- Real Redis Lua rotation/expiry/slot ownership and real MariaDB OAuth/ledger concurrency checks pass. Loopback MCP SDK/HTTP and Chromium checks use synthetic identity/cloud boundaries.
- Final isolated frontend check and production build exit 0; no errors and one pre-existing accessibility warning.
- Independent reviewer approved the complete patch after correcting queued logout ordering; additional missing-origin and invalid-mode regressions approved. No source authored by reviewer.
- Earlier gate failures are retained as failed evidence; fixture/setup issues were fixed, a frontend catalog timeout passed on exact recheck and final gate. Documents duplicate files were avoided with a new private tmp clone.
- No commit, push, version bump or deployment performed. Real Keystone/cloud behavior and production runtime remain outside this local patch verification.
