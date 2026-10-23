# GitLab first-login Accounts confirmation

## Why
User completed upstream GitLab authentication but callback displays generic provider-changed error. Read-only production: controller cfg revisions equal, discovery binding succeeds, stable native mapping passed. Two callback409s observed. One normalized-email Accounts/Default pair exists; Default owns stable GitLab issuer/sub plus gitlab/mapped native tuple. Production directory with that exact stored tuple reproduces account_email_conflict. UI maps every409 to providerChanged, concealing ownership conflict.

## What Changes
For operator-owned cfg OIDC only: signed verified email selects one enabled Accounts human by normalized email. Unbound first login issues encrypted one-use browser/provider-revision-bound entry ticket; connect-existing confirmation needs no local password; no Accounts match gives create-new confirmation. Bound Accounts identities log in normally. Never select Default as login target. SQL/GitHub retain existing explicit proof; no new tenant email trust.

Same-email enabled exact canonical Default source holding BOTH stable issuer/sub and exact native tuple is the sole supported legacy transfer. Explicit confirmation discloses login-binding-only transfer; never merge users or move home/password/preferences/grants/resources. Under existing IAM lease, freshly verify source/target exact state, persist encrypted bearer-free SQL102 journal before native writes, detach only exact association, attach Accounts target, read back both, verify native token UUID/home. Only known-confirmed association writes can automatically compensate after a later native-token failure. Uncertain writes/process death remain recovery_required until the operator confirms native calls have stopped and invokes exact snapshot reconciliation with native_writes_settled=True; fresh OAuth alone cannot settle them. Other homes/emails/ambiguous/disabled/native-only conflicts remain fail closed. Preserve Personal provisioning, admission/approval/quota and all unrelated native data.

## API/UI
Callback409 account_entry_required payload {entry_token,domain_id,action:connect|create,email,username?,transfer_existing?}. POST /api/v1/auth/providers/entry {entry_token,action} returns LoginResponse via existing _finish_provider_login. Tickets memory-only client, encrypted Redis600s one-use server. Cancel/back no mutation. Known conflicts have specific localized messages; unknown409 not providerChanged.

## Scope and safety
Backend service/API/models + SQL102/manifest + callback UI/types/nine locales + regressions. Read-only live IdP/protocol/mapping/domain/tuple checks only. No deployment, publishing, operational schema/config/IAM/grant changes or unrelated Cloud Shell changes. Preserve existing dirty docs and private data.

## Acceptance
Exact ownership conflict reproduced read-only; source fails-before from recorded production directory; explicit Accounts-confirm/create and exact native binding through real HTTP/installed SDK/SQL/JWT + browser with synthetic native/IdP; regressions and auth target pass. Real MariaDB102 rehearsal. Document production-vs-synthetic boundary; new schema requires separately approved rollout.
