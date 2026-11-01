## 1. Browser
- [x] 1.1 Extend owner-fenced display snapshots to bounded browser session reuse.
- [x] 1.2 Preserve explicit refresh, scope/login/authority and late-response fences.

## 2. Backend
- [x] 2.1 Cache expensive nonmanager project candidates behind current native authorization; manager/domain directory remain live.
- [x] 2.2 Preserve refresh and failure behavior; fresh per-row revocation checks, bounded TTL and explicit post-create refresh.

## 3. Verification
- [x] 3.1 Focused backend415 and final HTTP smoke1; frontend73 regressions pass.
- [x] 3.2 Actual isolated browser2/0/0/2 request counts and native HTTP26/23/26; revocation verified.
- [x] 3.3 Architecture/testing docs updated; strict OpenSpec validation/archive and architecture stamp run at completion.
