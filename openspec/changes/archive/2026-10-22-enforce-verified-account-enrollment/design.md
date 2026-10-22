## Context

The current public registration already sends an expiring random email token, stores only its digest, verifies delivered/pending status and serializes acceptance with the identity graph lease. Native duplicate lookups are complete and hydrated. Current OIDC signed email_verified checks are correct, but every unbound existing-email collision requires a second local-password linking step. Login help exposes Accounts implementation details.

## Goals / Non-Goals

Goals: no domain knowledge on login; mandatory delivered-email signup; duplicate username/email prevention at final native dispatch, not just UI; automatic verified OIDC email attachment to one exact Accounts human in all deployments. Preserve UUID/home/password/federation/grants/resources, approval and uncertain-write fences.

Non-goals: deploy/restart, send real email, alter native IdP mappings, migrate or merge legacy identities, rewrite established external bindings, relax organization admission or create passwordless native tokens with an executor.

## Decisions

1. Remove the help element and all unused locale entries, keeping Username or email label and native submit/autofill/IME fences.
2. Reuse delivered one-use registration token and graph lease; strengthen only uncovered username/email cross-alias or normalized collision edges. Public email request remains non-enumerating202; duplicate ownership is shown only after mailbox proof. SMTP unavailable fails closed. Administrator creation is not public self-signup.
3. Trust operator-owned file-registry OIDC (`cfg:`) for normalized verified-email association to exact Accounts, while globally checking issuer/sub and native tuple ownership. Tenant-managed SQL providers retain explicit first-link proof: an organization manager may operate an issuer but cannot assert ownership of another platform member's mailbox. Provider visibility and existing organization membership do not promote that trust. Same-email legacy identities are not merged/selected and conflicting stable/native owners require reconciliation.
4. Call existing attach/readback then the existing canonical native federation exchange; maintain issuer/sub, IdP/protocol, enabled home/user, provider revision, browser state, nonce/PKCE and organization pre-admission guards. No local-password marker is synthesized.
5. The behavior is backend invariant, not a dev flag. Existing TOML/SQL provider selection, bootstrap signup flag and SMTP readiness remain shared by Compose/K8s/Helm/Kolla. Document prerequisites and verify generated configuration does not introduce bypass flags. Existing schema is reused; all old writers must be drained before activation because they retain older linking behavior.

## Risks / Trade-offs

- Only operator-owned registry OIDC providers are trusted for verified mailbox ownership; never trust a tenant-defined issuer, plain email, email_verified string or unsigned claims for global first association.
- A native tuple already belonging to another user cannot be silently moved by email. Block and report rather than merge identities or lose resource ownership.
- Native PATCH outcome can be unknown; existing durable association readback/conflict fences remain. No retry/fallback identity.
- Synthetic IdP/SMTP/native proof is not live production provider/mailbox acceptance; source rollout remains a separately approved operation.
