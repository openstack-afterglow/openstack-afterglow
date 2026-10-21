## Implementation Tasks

- [x] Inspect current immutable identity/working-domain, enrollment/quota journal, provider admission and active OpenSpec contracts; finalize shared implementation interfaces and preservation boundaries.
- [x] Create every new email/invite/system-admin/provider human in shared account and provision a journaled username+random primary project in shared personal with project-only owner/reader and quota readback before activation.
- [x] Support existing human login with preserved native identity/credentials/grants and a safely provisioned separate personal primary project; exclude service/bootstrap identities.
- [x] Enforce account identity-only and personal project-only isolation across domain/workspace/default bootstrap/manager/IAM/project membership/user directory/quota and generic native mutation paths.
- [x] Separate user-created organization policy from public signup and create organization domains with creator-manager bootstrap and current-native authority fences.
- [x] Implement trusted OIDC issuer/organization binding, explicit manager-subject bootstrap, additive membership and durable uncertain native creation fencing; preserve stable-sub account linking and origin-policy checks.
- [x] Restrict organization admission to manager invitations or configured OIDC, removing direct human creation and credential/membership/group bypasses while preserving explicit system administration.
- [x] Cut over API DTOs and all affected frontend onboarding/admin/IAM/project/workspace/session consumers and all supported locales without weakening owner/ABA/logout/scope fences.
- [x] Verify exact regressions, auth/access/config related targets and project gate, recording any unrelated failures without suppressing or narrowing checks.
- [x] Exercise actual API/native SDK/SQL boundaries and compiled browser account/personal/organization flows with explicit synthetic/live boundaries and preservation evidence.
- [x] Update architecture/auth/IAM/deployment/testing/security/config/changelog documentation, stamp current source architecture and archive after observable implementation acceptance; retain external/production qualification as an explicit operator prerequisite.

## Verification

- Final Afterglow `npm run test:gate` exit0 at source `2a563789902e6f79d136d063ad971b7dcc8840ede58f7cc268b101b5495262e1`/3393files. Backend8618passed/95skipped, frontend4801passed, contracts159passed, DB functional166passed; Ruff check and713-file format pass.
- Auth backend770/frontend440, access1137/181 and config507/12 related targets passed; config has1skip. Selectors overlap and are not additive. Earlier harness/consumer failures remain in the raw logs.
- Actual TCP BFF/native SDK/SQL registration→personal-first login→manager invitation201→acceptance200→explicit organization scope200 preserves identity home and avoids service-leaf expansion. Compiled account/role modal and arm64/amd64 image evidence are separately scoped in `docs/testing.md`.
- Receipt root: `~/.local/share/afterglow-proofs/account-topology-20261020-019qotth/`. No production mailbox/IdP/Keystone/Nova acceptance, deployment/IAM mutation, commit/push or original-user index/config replacement.
