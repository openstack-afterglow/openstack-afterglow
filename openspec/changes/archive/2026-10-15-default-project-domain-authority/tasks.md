## Implementation Tasks

- [x] Scope current authentication/IAM paths and confirm Default-common managers, read-only baseline, cross-domain accounts, creator authority and signup-mode creation with user.
- [x] Restore exact effective system:all admin recognition without project/domain escalation.
- [x] Restore domain-step Enter submission.
- [x] Restore username/password-step Enter submission.
- [x] Create Default automatically with every new domain.
- [x] Grant verified domain-login users Default project_reader baseline.
- [x] Grant the actual domain creator Default manager, including external identity-domain creators.
- [x] Preserve at least one active effective common manager and the Default anchor across account/group/grant/graph mutations.
- [x] Give Default managers real native read access to all projects in the same domain.
- [x] Reject manager and manager-implying assignments on non-Default projects.
- [x] Restrict user IAM to current Default effective managers independently of selected project.
- [x] Preserve project_owner/admin/member/reader delegation and effective direct/group/scope-inherited/role-inferred roles.
- [x] Expose IAM in user-mode left navigation with current authority.
- [x] Separate identity domain from working domain in authentication, refresh, rescope and session rotation; support domain selection after login and later switching.
- [x] Allow ordinary and newly verified users to create domains under existing signup-enabled policy; closed mode requires current systemadmin.
- [x] Provide explicit administrator bootstrap for legacy domains without inventing creator authority on login.
- [x] Exercise API regressions and actual installed-SDK/HTTP/Redis runtime boundary cases.
- [x] Exercise compiled browser login, domain selection/creation, IAM/admin navigation and responsive/localized states.
- [x] Build all affected canonical images for declared architectures, deploy authorized local target and verify health/runtime.
- [x] Update architecture/detail/design/changelog with exact evidence and limits; validate and archive this change.

## Qualification boundaries

- `verification.json` and `docs/testing.md` retain the exact final proof and original full-gate failure. Native production Keystone policy, SMTP/OIDC, mixed-version/restore and VM boot are not certified.
- Final corrected affected tests342 and contracts177 pass; the whole gate was not rerun to relabel the existing11 storage failures as green. Unrelated format6 and known Svelte type error remain.
- `openspec status --change default-project-domain-authority --json` reports both rapid artifacts done. Generic strict validation rejects the absence of deltas; this repository intentionally has no specs layer and archives with `--skip-specs`, not invented delta specs.
- Build/runtime evidence belongs to the named frozen source. Concurrent `HubArtifactsPanel.svelte` changes and the original persistent development stack are not silently included in that image qualification.
