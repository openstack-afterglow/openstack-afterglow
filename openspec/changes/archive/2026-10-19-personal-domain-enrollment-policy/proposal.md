## Why

The user requires all newly registered humans, including first OIDC/GitLab login, to own a personal identity domain and participate in organization domains as the same account. They also require system-administrator controls for future personal-domain quota defaults and automatic versus administrator-approved enrollment. Existing native homes cannot be moved in place and are outside this change.

## What Changes

- Reuse the durable personal-domain enrollment lifecycle for external-only users, preserving verified stable issuer/subject, canonical global email ownership, native federation, organization admission and external-only/no-password boundaries.
- Persist an administrator-owned revisioned enrollment policy: public email registration enablement, auto/admin approval mode for new email and external accounts, and future-personal-domain quota template. Existing configuration provides initial email gate; auto is compatibility default; core personal resource limits default to zero.
- Seed each new personal domain's allocation ceiling and project defaults from a frozen template before activating its Default project. Existing domains and organization budgets are not modified. Quotas remain Afterglow-managed native project allocation budgets, not an invented cloud-wide per-user usage cap.
- Require verified email/OIDC ownership before recording a bounded, secret-free administrator approval request. Pending/rejected applicants receive no native user/domain/project/token. Approvals require a fresh proof to complete enrollment, never saved passwords/bearers/OAuth codes. Approval does not grant organization admission or privileged roles.
- Add system-admin settings/review UI and localized pending/rejected onboarding states, with revision conflict, authority/generation fences and no OAuth/native mutation replay.

## Capabilities

### New Capabilities

- System-administrator enrollment policy and account-approval queue.
- Administrator-selected future-personal-domain allocation/default quotas.

### Modified Capabilities

- OIDC/GitHub first-user creation uses a personal home plus separately authorized organization participation.
- Email and external new-account enrollment obey the same review mode without affecting existing canonical logins.

## Impact

Backend onboarding/external identity services, SQL policy/request persistence and enrollment quota snapshot migration, protected admin APIs, existing quota orchestration, public/admin Svelte UI and four locale catalogs, behavioral regressions, auth/admin/deployment/testing documentation and architecture/changelog. New schema requires old-writer drain and migration-before-new-writer rollout qualification. No current account migration, Default removal, native/shared mapper change, production DB inspection, config mutation, commit/push or deployment is authorized by this feature request.
