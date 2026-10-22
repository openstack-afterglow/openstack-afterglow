# verified-account-entry Specification

## Purpose
Define domain-free public login, mandatory delivered-email proof and unique signup identifiers, and operator-trusted OIDC association to preserved native Accounts identities without elevating tenant-managed providers or migrating legacy account ownership.

## Requirements

### Requirement: Public login hides identity-domain internals
The login form SHALL ask only for username or email and password and SHALL NOT display the Accounts-domain identifier help paragraph. All supported locales SHALL remove the retired help entry without changing native form submit, IME, autofill or session-owner fences.

#### Scenario: User opens login
- **WHEN** a signed-out user opens login in any supported locale
- **THEN** credential fields and provider actions remain available without the Accounts-domain help paragraph

### Requirement: Public signup requires verified unique identity
Public self-signup SHALL require a delivered, pending, unexpired, one-use random email verification token before account creation. Final acceptance SHALL reject an existing normalized username or email, including username/email cross-alias collisions and concurrent requests, before native creation and without modifying an existing human. Token-bearing signup proof SHALL NOT accept a client-substituted email. Unverified/expired/undelivered/replayed proof and incomplete directory inventory SHALL fail closed. Public email requests SHALL remain non-enumerating.

#### Scenario: Attacker skips verification
- **WHEN** account creation is requested with missing, guessed, undelivered, expired or previously accepted proof
- **THEN** no native account, grant or personal resource is created

#### Scenario: Another signup wins the same identity
- **WHEN** two verified requests choose the same normalized username or email
- **THEN** at most one native human is created and the loser receives conflict without replacing credentials

### Requirement: Verified OIDC email associates one Accounts human
For an allowed operator-owned registry OIDC provider, the system SHALL automatically attach a newly verified immutable issuer/subject to the unique enabled human whose normalized email matches inside the exact operator-resolved Accounts domain, without requiring another local password. Tenant-managed SQL providers SHALL require explicit canonical account proof for a first association because organization administration is not global mailbox authority. A provider-verified boolean email claim and existing signed-token/browser/issuer/audience/nonce/PKCE guards SHALL precede matching or native writes. Stable and native tuple ownership SHALL be checked globally; ambiguous Accounts ownership, conflicting external ownership, incomplete inventory and changed canonical proof SHALL be rejected. Legacy identity ownership and organization admission SHALL NOT be implicitly migrated or granted.

#### Scenario: OIDC email matches unique Accounts human
- **WHEN** a fresh verified OIDC callback has no conflicting external owner and matches one enabled Accounts human
- **THEN** it preserves that human's UUID/home/password/preferences/metadata and existing federation tuples, attaches and reads back the exact new association, and issues login only if native federation returns the same canonical human

#### Scenario: Email is not verified or native identity conflicts
- **WHEN** the claim is absent/false/non-boolean, Accounts matches are ambiguous, or the issuer/subject/native tuple belongs to another human
- **THEN** no automatic association or replacement human is created and no session is published

#### Scenario: Organization manager configures an issuer that claims another member's email
- **WHEN** a tenant-managed provider claims a verified email belonging to an Accounts human who is already a member of that organization
- **THEN** existing organization membership cannot authorize automatic account attachment or login and explicit canonical account proof is required before native writes

### Requirement: Deployment uses the same verified enrollment invariants
Compose, Kubernetes, Helm and Kolla application deployments SHALL use the production backend invariants without a local-only automatic-link flag or signup-verification bypass. Existing provider allowlists, stable-sub user-only native mapping, SMTP readiness, SQL prerequisites and operator signup opt-in SHALL remain authoritative. Before starting a changed enrollment reader or writer, the deployment operator SHALL verify its required schema against the exact effective database rather than infer an upgrade from health or ORM table creation. Shared-database repair SHALL preserve a protected backup proven by isolated restoration, drain all identified affected writers, apply only reviewed manifest-owned missing postconditions and verify existing data, identity and runtime-configuration preservation. Schema readiness SHALL NOT be reported as fresh-user login or new-release acceptance.

#### Scenario: Application is configured for production
- **WHEN** the normal deployment paths render existing provider and SMTP configuration
- **THEN** the same verified signup and OIDC matching rules apply without weakening native authentication or silently enabling public signup

#### Scenario: A new login reader encounters an existing table missing enrollment columns
- **WHEN** native password proof succeeds but the selected shared database lacks required enrollment columns
- **THEN** the operator repairs the exact schema prerequisite through protected backup/restore and an affected-writer maintenance window without changing credentials, native ownership, grants, existing rows or unresolved journals

#### Scenario: An operator qualifies schema readiness after repair
- **WHEN** all required model tables/columns and the formerly failing query pass against the actual repaired database and normal bootstrap passes on its isolated restored snapshot
- **THEN** the receipt identifies the exact database, unchanged runtime/configuration and restoration evidence, and keeps unexercised fresh-user login, mixed-version semantics and new image rollout acceptance separate
