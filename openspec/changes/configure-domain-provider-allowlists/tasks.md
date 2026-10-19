## 1. Configuration and authority

- [x] 1.1 Replace selector fields with validated optional allow_providers; reject retired fields and unknown registry references while accepting exact SQL provider UUIDs.
- [x] 1.2 Implement exact-domain/default/all fallback and consistent file/SQL listing, authorization, callback, refresh, verification and SQL last-method enforcement.

## 2. Deployment and consumer coverage

- [x] 2.1 Preserve omitted/empty/explicit allowlists through shared K8s/Helm TOML rendering and migrate existing configuration consumer tests.
- [x] 2.2 Cover unrestricted same-kind instances, overriding/inherited/empty lists, ordered deduplication, SQL isolation and pending/session denial with deterministic consumer regressions.

## 3. Verification and documentation

- [x] 3.1 Run scoped tests and actual HTTP, Kustomize/Helm and responsive browser smoke against the changed runtime; record synthetic/live boundaries.
- [ ] 3.2 Finalize example configuration, auth/deployment docs, architecture and changelog; record architecture evidence and archive only after required deployment acceptance clears. Documentation and local evidence are updated, but the earlier archive was premature and is reopened because the required gate failed.

## 4. Canonical deployment acceptance correction

- [ ] 4.1 Canonical local Compose backend/worker runtime is exercised, including actual health 200, live worker Redis membership, real MariaDB/Redis/installed native SDK HTTP, and unrestricted/default-replacement/empty allowlist and denied authorization smoke. Deployment qualification remains BLOCKED: `npm run test:gate` exited 1 with backend 8,129 passed/18 failed/91 skipped; downstream frontend, contracts, functional and backend lint were not run. Preserve `canonical-deployment.json` and `canonical-required-gate-receipt.json`; do not treat module-only execution or runtime smoke as a passing required gate.

## 5. Current local GitLab enablement request

- [x] 5.1 Migrate the existing private legacy GitLab credentials to the current auth registry, preserve password login and existing keys/data, and verify the actual local Default login surface and upstream authorization start. Native read-only preflight found only enabled `gitlab/openid` bound to Default and no SQL providers. The actual Default button reaches live GitLab sign-in; user authentication/code exchange is not verified. Evidence: `domain-gitlab-current-20261017T073458Z`.
- [x] 5.2 After explicit user approval, select the already-present `gitlab/mapped → sso_oidc_dmslab_mapping` for dmslab without changing native federation, and add only `http://localhost:3080/auth/callback` to existing GitLab application25 while preserving all old callbacks and client credentials. Default/openid and dmslab/mapped each return one provider and authorize200; opposite-domain provider IDs are404. Actual buttons in both domains reach live GitLab sign-in; native domain semantics and three-controller bearer protection are observed. No account/grant/native mutation or completed user login is claimed.
- [ ] 5.3 Complete real-user GitLab consent/code exchange, generic callback and Keystone session acceptance for both identity domains. Current owned browser is anonymous and no user credential or consent was supplied; upstream sign-in screens alone are not end-to-end authentication proof. Existing required gate failures also remain unresolved.

## 6. Configuration-driven connection extensibility

- [x] 6.1 Audit generic selection, protocol binding and frontend consumers; preserve the existing schema instead of adding deployment-specific code or a second registry. Current runtime already reads instance metadata/native bindings from auth configuration, uses exact-domain allowlists and renders server-returned provider IDs/names; no Default/dmslab/GitLab-host branch or application-source change is needed.
- [x] 6.2 Add consumer regressions for same-issuer independent domain/protocol bindings and mismatched native identity rejection; update operator examples and supported-kind extension instructions. Final focused auth/config/generator/Helm consumers:308passed including5new cases; changed-test Ruff check/format check and OpenSpec strict validation pass.
- [x] 6.3 Exercise actual runtime HTTP with file-loaded configuration, multiple domain/protocol bindings and a configuration-only additional login option; record evidence and live-provider limits without clearing historical acceptance blockers. Arbitrary domains/shared issuer use independent protocols, a third GitHub instance is added by TOML/Secret and restart with existing revisions preserved, public callbacks reject3native mismatch conditions and state replay, and compiled desktop/mobile login shows configured buttons. Upstream/native/fakeredis are synthetic; positive completion stops at the service boundary, not real-user/cloud/browser session acceptance. Evidence:configurable-login-20261017T091014Z; existing private connections and shared infrastructure are unchanged.
