## Why

A verified email address is not sufficient authority to enter an existing tenant or silently merge identities from different providers. The user requests invitation-gated domains, explicit trusted-provider/email-domain exceptions, email-first public enrollment with a personal identity domain, one canonical account reused across domains, and email-based username/password recovery.

Read-only inspection of the currently running local backend's configured native directory confirmed one duplicate-email group: `pieroot` in Default and `jung-geun` in dmslab. The former has a native system-wide role assignment; the latter has independent project assignments. Both configured GitLab protocols currently have mappings that dynamically provision a user in their respective target domains. No native account, mapping, grant, credential, resource, or runtime configuration was mutated during this inspection.

## What Changes

- Existing-domain admission requires an invitation or an explicitly configured trusted external identity provider and verified exact email-domain exception. dmslab's requested exception is GitLab issuer `https://git.dmslab.re.kr` and verified `gmail.com` or `konkuk.ac.kr`; names/hostnames must not become source-code branches.
- Ordinary public signup starts with email delivery only. A valid one-use verification link authorizes credential selection and creation of a personal identity domain and its canonical Default project. It does not automatically join an unrelated pre-existing domain.
- Existing normalized email ownership prevents creating a second human account. A verified existing account is connected additively to another authorized working domain, retaining native user ID and original credentials. External account linking must prove both the existing account and the external subject; email coincidence alone cannot authorize it.
- Username recovery verifies email and returns account information only to its owner. Password recovery uses a bounded, hashed, one-use email link, binds the exact native account, prevents account enumeration, and revokes prior sessions after a successful reset. External-only and privileged/operational account recovery policies require an explicit supported disposition.
- Source/API/UI/configuration/migration/documentation consumers must change together, preserving the existing canonical-project selection priority and manager/owner/reader policy.

## Capabilities

### New Capabilities

- Configured invitation or trusted-provider admission across working domains.
- Email-first global signup that creates only the user's personal domain.
- Explicit existing-account domain/provider connection without duplicate identities.
- Email username recovery and one-use password reset.

### Modified Capabilities

- Domain-specific registration no longer provides a public-email shortcut into an invitation-only tenant.
- Login distinguishes the canonical identity namespace from the selected working domain without substituting service-account credentials for user authentication.
- Every first-party human email writer, including profile changes and federation, participates in canonical ownership checks.

## Impact

Backend auth, enrollment, native federation integration, identity/email persistence and migrations; public auth and invitation UI and localization; operator auth configuration and Kubernetes/Helm serialization; security, auth API, deployment/testing and architecture documentation.

User-reviewed security decisions:

1. The user approved including the actual existing duplicate consolidation and native GitLab mapping cutover. Preserve `pieroot`'s native ID and original password; first inventory `jung-geun`'s grants and ownership, then transfer only the exact approved identity bindings and rights and disable the duplicate. Unprovable ownership requires another user review. No email-only automatic merge or silent deletion.
2. Canonical external-login binding uses stable `(issuer, subject)` and explicit existing-account authentication. Existing shared Keystone mappings and non-Afterglow consumers must be inventoried before cutover; do not assume an application-only change establishes native capability.
3. The user explicitly authorized email-based password reset for system administrators, noting the need for a practical lost-admin recovery path. Implement one-use bounded account-bound verification, non-enumerating requests and prior-session invalidation for administrators too. Configured operational/service identities and external-only users remain excluded; email recovery must not manufacture local passwords for an unproven federated account.

SMTP is configured as enabled with host/from/frontend URL in the current runtime; actual email delivery and mailbox acceptance have not been exercised. Native read-only inspection is not proof of new enrollment/link/recovery behavior. No feature implementation, deployment, tests, or account consolidation is claimed by this proposal.
