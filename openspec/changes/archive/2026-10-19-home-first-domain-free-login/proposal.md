## Why

사용자가 로그인 전에 작업 도메인을 입력하는 현재 경로는 계정의 immutable home과 조직 workspace를 혼동하게 한다. 사용자는 새 human 계정이 반드시 개인 도메인을 소유하고, 도메인 입력 없이 원 소속으로 인증한 뒤 접근할 작업 도메인/프로젝트를 선택하기를 요청했다.

## What Changes

- Public password login accepts username (globally unique email recommended) and password only. Resolve exactly one canonical native account before one password attempt, enforce its original home policy, and issue the initial session only in that home. Reject ambiguous legacy names/emails; never cycle credentials across homes.
- Public login-options exposes only currently offered, enabled server provider registrations with their exact origin-domain handles; no username/email lookup, secret, issuer discovery or client-side registry. Existing same-site/browser-bound authorize paths pin the selected registration and revision.
- OIDC/GitHub still verifies exact issuer/subject, provider-origin policy, approval, personal enrollment completion and independently authorized organization admission, but the initial session belongs to the canonical account home, not the provider-origin organization. Preserve provider origin for later verification/revocation.
- Every successful fresh password/provider login opens the existing WorkspaceBrowser at /select-domain with the home active. Explicit authorized selection commits domain/project atomically. Invitation/MCP continuation runs after selection; existing-session navigation/refresh does not repeatedly force the chooser.
- New email/OIDC/admin-created human accounts continue using mandatory personal-domain enrollment, approval and frozen-quota safeguards. Existing native users, home IDs, credentials, bindings and grants are not migrated/deleted or silently cloned.
- Remove obsolete domain-entry UI, login domain query hints and request fields from all in-repo consumers. Preserve reauthentication, IME/native form submit, one-use callback readiness and stale-response fences.

## Capabilities

### New Capabilities

- home-first-domain-free-login: domain-free credential entry with canonical-home initial sessions and explicit post-login workspace selection.

### Modified Capabilities

- Canonical federation, personal-domain enrollment and public/admin onboarding retain existing authority boundaries while separating provider origin, immutable home and selected workspace.

## Impact

Backend auth request/API/provider listing and session issuance; frontend login/callback/onboarding/session routing and shared workspace continuation; affected consumer tests/docs. No native account migration, live credential mutation, new persistence schema or deployment is authorized. Password API cutover intentionally rejects obsolete domain/project request fields; coordinate API/frontend deployment. Qualification uses isolated HTTP/native fixtures and a real browser, not shared cloud identities or running user services.
