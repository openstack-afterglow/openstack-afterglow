## 1. Contract and source scope

- [x] 1.1 Inspect profile/public/admin password flows, authoritative native endpoints and current shared dev state; preserve other changes/index.
- [x] 1.2 Record user-requested SSO local-password policy, security boundaries, existing native103/v2 prerequisites and source-only scope.

## 2. Implementation

- [x] 2.1 Reuse profile same-user mailbox/fresh-SSO first-password creation and route native-absent SSO email recovery into it; retain existing-password reset.
- [x] 2.2 Replace administrator marker-only SSO denial with guarded state/revision-based native create/reset, retaining all dispatch/mail/authority boundaries.
- [x] 2.3 Update any affected UI explanation in all existing locales and retain current recovery/SSO continuation UX.

## 3. Verification and documentation

- [x] 3.1 Run focused route/security regressions and changed-path actual TCP/SDK smoke including absent creation, subsequent email reset, foreign/stale/changed identity and unsupported-native refusal. Final focused359passed; actual Uvicorn/Keystoneauth HTTP/SQLite public+profile create200, subsequent reset200, stale/foreign403, replay410, admin create/reset200 and unsupported409; native/provider/mail/Redis are synthetic.
- [x] 3.2 Exercise existing compiled profile/recovery/admin UI where affected and record synthetic/native/operational evidence boundaries. UI112passed; real Svelte components in isolated Vite/Chromium: profile email action, same-SSO continuation, create/reset submit, admin confirmation/success/refusal,9locale readiness text and390/1440px no overflow. Synthetic API/auth/navigation; no live provider/mailbox acceptance.
- [x] 3.3 Update existing API/security/deployment/testing documentation, architecture and changelog; run applicable gate/freshness and archive completed source change. Scoped359/UI112/TCP and working/staged architecture passed. Pre-email-management whole backend12571/frontend6500/contract183/functional167 passed; gate exit1 only at existing unrelated lumen/proxy.py format check, left untouched. Source-only; native deployment remains separately qualified.
