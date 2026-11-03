## Context

Profile creation, public recovery and native conditional credential endpoints already exist. Public recovery currently admits existing passwords only; administrator randomized reset blocks federated users without a marker and otherwise uses stock PATCH. Stock Keystone cannot safely create a federated shadow user's first local password. Shared dev has unrelated active frontend/chat work and must retain its index.

## Goals / Non-Goals

**Goals:** Reuse existing SSO creation and email reset UI/API; enable registered-mailbox initiation when native password is absent; allow fresh system administrators to create/reset SSO credentials with exact native state/revision. Preserve identity UUID/home/email/federation and one-dispatch safety.

**Non-Goals:** No weakening of mailbox uniqueness, service-user exclusion or provider/session fences; no new credential aliases, IdP password changes, forced expiry, schema/dependency changes, publication or production deployment.

## Decisions

1. Reuse native first-password-galera-v2 snapshots, not local-password markers. Absent SSO mailbox recovery issues password_create and requires the existing fresh same-owner provider login at redemption; existing credentials issue password and use conditional reset. An address alone never creates an SSO password.
2. Keep public responses non-enumerating accepted202 on unknown/ambiguous/ineligible/unavailable cases. Do not send links for service accounts, disabled/ambiguous identities, forbidden password policy or unsettled creation operations.
3. Administrator reset retains current live system-admin, executor binding, unique registered address, TLS mail, cooldown, SQL audit fence and strict revocation. For external identities obtain service-owned capability/snapshot before fence and choose conditional create for absent or reset for existing, with the exact domain/email/revision body. Refresh binding before dispatch. Never fall back to PATCH for an external identity or trust marker true as native state.
4. Preserve ordinary local administrator PATCH behavior. Existing conditional transport disables redirects, reauthentication, retries and body logging. Only explicit pre-write refusal avoids revocation; unknown outcomes consume proof/fence and are never retried or mailed as success.

## Risks / Trade-offs

- Local passwords bypass IdP MFA/deactivation: retain existing explicit warning and record that this is the requested policy, not an IdP credential reset.
- Native extension/schema and Afterglow103 must already be qualified before operational activation. Source/local proof is not deployment acceptance; unsupported native must fail before mutation.
- Email links prove mailbox access; first creation additionally requires fresh same-account SSO. Admin generated-password mail retains its existing mailbox exposure tradeoff and explicit confirmation.
- SQL, native credentials and SMTP are separate systems: retain partial/unknown effect reporting rather than fake rollback.
