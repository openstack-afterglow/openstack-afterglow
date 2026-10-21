# Personal first-login provisioning and profile images

## Goal
Admin-created Accounts humans receive their personal project at first successful login, with durable recovery across failure/interruption. Personal project-management membership remains native member, while its human has all project-scoped Lumen, Drover, Palimpsest and Waygate actions without system authority. Add email-default Gravatar, generated avatar and raster upload management to profile and header. Investigate reported Accounts native password-exchange 401 using evidence; never add legacy-domain fallback or reset credentials implicitly.

## Constraints
Preserve concurrent uncommitted work, existing identities/credentials/resources/grants, original canonical-link homes, shared index/private config, journals and uncertain-write fences. No commit, push, release, deployment or production IAM/schema mutation. Reuse exact operator-owned Accounts/Personal topology and existing service-local policy enforcement. Unknown native writes must be reconciled rather than blindly replayed. Profile images must be bounded/decoded raster with no arbitrary URL fetch or active SVG upload. All authenticated image/update results must retain logical-session/lifecycle fences.

## Acceptance
- Admin create persists identity without creating personal project; first successful password/provider login provisions once.
- Safe failed steps resume; uncertain calls reconcile matching provenance and never duplicate. User can retry/restart through an authenticated recovery flow with explicit unsafe-state handling.
- Personal membership APIs reject other project-management roles; native services enforce personal-owner project permissions without global/system escalation, and preserve operator-policy deny, key ceilings and ownership checks.
- Profile defaults to current email Gravatar and offers persisted Gravatar/generated/upload choices; header replaces ID text with accessible image at all breakpoints.
- Login investigation identifies verified cause or exact missing evidence, without treating surrounding OPTIONS/worker errors as cause.
- Current-source targeted tests, actual HTTP and browser smoke, docs and architecture evidence distinguish synthetic/local/live limits.
