## Why

The user supplied a successful login taking 22,657.87ms: resolve443.039ms, authenticate6389.926ms (password exchange334.828ms), password policy37.069ms, domain preparation12870.677ms, response publication2849.338ms. The current login repeats domain/subject/project/system authority and scopes a provisional project before final selection. Every nested admin-client construction repeats service authentication. After login the browser blocks dashboard readiness on a second /auth/me. Investigation of unchanged service functions with the installed SDK and synthetic loopback Keystone observed151 HTTP requests/33 service-password exchanges for readonly login phases, plus87/17 for a cold postlogin validation; mutation/policy/Redis/browser were excluded. These are local structural counts, not live counts.

## What Changes

- Reuse a bounded native directory client/read context within an authentication operation. No cross-request authority cache or TTL increase. Close resources; do not retain credentials globally. Clear/discard any read snapshot across native writes and final revalidation boundaries.
- Authenticate the password/subject without selecting an unnecessary provisional project. Preserve legacy domains, explicit project selection, disabled/no-project users, immutable home identity, Default reader enrollment and manager projection correctness. Issue and validate the final selected native scope once.
- Give existing users a verified no-mutation path for Default reader/projection correctness, acquiring the existing graph lease and performing fresh reads/writes only when a repair is actually required. Never silently skip stale manager projection cleanup or authenticate membership from cached role names.
- Publish a fully mapped fresh login response as in-memory verified UI state, avoiding an immediate /me roundtrip. Restored persisted credentials, unverified replacements and mock-to-real transitions must still verify; logout, stale-response, identity/scope ABA and refresh recovery boundaries remain intact.
- Preserve established consumer readiness atomically for exact one-use, owner-bound native refresh/rescope mappings. They do not gain current-token verification proof: `/me` still runs. Raw/copied/reused/stale replacements revoke readiness. This retains existing in-flight workspace operations and media drafts instead of treating a normal refresh as logout.

## Constraints

No weakening domain/project/system authorization, native role DAG/provenance, session CAS/expiry/blacklist/binding, fail-closed provider failure, restricted scope or mutation fencing. Do not cache native writes or replay them. Keep response schemas, authentication policy, membership guarantees, configuration and SQL schemas unchanged unless evidence makes a narrow adjustment necessary. No CORS changes: rejected unrelated preflights are not this latency cause. No private config/shared datastore/cloud writes, commit, push or production deployment.

## Acceptance and Evidence

- Behavioral regression for membership/revocation/projection, legacy/projectless/default selection, wrong subjects/scopes, concurrent request isolation, mutation invalidation and login-versus-restoration readiness.
- Actual unmodified application HTTP with installed SDK, disposable SQL/Redis and synthetic native HTTP; record login calls by type, service authentications, phase latency and correct domain/project/roles. Compare before/after same seeded state and latency-injected fixture. Report synthetic timings separately from user's live log.
- Actual compiled browser password login usable without /me; reload must verify /me, revoked/invalid restored session must not expose protected data; pending/stale/logout boundaries remain.
- Build affected canonical Dockerfile targets on all declared architectures, deploy using canonical dev Compose with a safe isolated override, wait health, execute real smoke. Preserve user's local services/volumes.
- Run exact regression then auth/access targets and affected integration checks; existing unrelated full-gate failures are reported, not re-run merely to reconfirm or silently repaired.

## Ownership

Parent owns integration, docs, architecture, OpenSpec, builds/deployment and final verification. Backend owns native directory/read preparation/login logic and backend behavioral regressions. Frontend owns transient login readiness and frontend regressions. Native harness owns isolated proof scripts only. No overlapping source ownership.
