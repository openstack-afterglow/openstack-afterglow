## ADDED Requirements

### Requirement: Authenticated domain login prepares a real landing project

The system SHALL prepare the unique enabled canonical `Default` project when an authenticated active user logs into an authorized enabled domain with no Default. Provisioning SHALL recheck current membership and absence under the existing shared native mutation lease, stage a disabled project, verify native authority and quotas before activation, and never provision from ordinary directory reads. Repeated or concurrent logins SHALL reuse an existing Default without changing its owner.

#### Scenario: First login without any project
- **WHEN** a verified password or configured-provider user first logs into their authorized domain without a Default or accessible project
- **THEN** one Default is created, native project scope is exchanged for that project, and a scoped session is issued rather than an empty selector

#### Scenario: Concurrent and repeated participants
- **WHEN** another authorized user logs in after a first attempt has created Default
- **THEN** the existing project's identity and ownership are preserved, and the participant receives direct project_reader access

#### Scenario: Invalid or unavailable authority
- **WHEN** membership, domain state, canonical role hierarchy, project identity, creation outcome, quota application or final native token cannot be verified
- **THEN** authentication fails without a browser session or a fabricated fallback scope, and ambiguous native resources are not replayed or deleted by name

### Requirement: Default creation separates project ownership from domain management

Every newly created Default SHALL give its verified creator the canonical project_owner role and direct project_reader baseline. A new domain's actual creator SHALL additionally receive the existing manager-on-Default domain authority, including personal-domain enrollment. First login to a pre-existing domain SHALL NOT grant manager or adopt an existing project's ownership. Setup SHALL preserve existing native role identities and SHALL NOT seed global role graphs implicitly.

#### Scenario: Domain creator
- **WHEN** a user successfully creates a new domain through a supported domain creation or verified personal enrollment path
- **THEN** that domain contains an enabled Default, the creator has verified project_owner and project_reader grants there, and the creator has manager domain authority

#### Scenario: Legacy domain first login
- **WHEN** an authorized participant creates the absent Default during login to a pre-existing domain
- **THEN** they own only the new project and receive no new manager or system authority

#### Scenario: Enrollment failure
- **WHEN** personal-domain ownership provisioning is rejected or its outcome is uncertain
- **THEN** the existing enrollment grant journal and exact-resource recovery retain the failure, no active incomplete Default is published, and redemption does not report success

### Requirement: Login enters the selected domain's native scoped project

Password and configured-provider authentication SHALL enter the server-selected domain's scoped project directly, regardless of other available domains. Explicit authorized project requests and pending invitation/consent continuations SHALL retain their existing meaning. A default-project hint alone SHALL NOT be interpreted as a completed native project scope. Users SHALL retain deliberate workspace switching through the current resource selector.

#### Scenario: Multiple available domains
- **WHEN** login succeeds with a scoped project in the domain chosen before authentication and another domain is available
- **THEN** the browser enters the scoped project's dashboard without forcing another domain selection

#### Scenario: No native project scope
- **WHEN** a response has only a default_project_id hint but no scoped project_id
- **THEN** the browser does not publish the hinted project as an authenticated active scope

### Requirement: Project owner delegates participant roles without escalation

A project's current verified project_owner SHALL be able to manage eligible participant project and service roles through the existing native role-management API and UI. Participants start as project_reader; they SHALL NOT gain manager, owner, system admin or service-write authority merely by joining. Existing immutable reader baseline, explicit ownership transfer, current graph safety and last-owner protections SHALL remain in effect.

#### Scenario: Owner grants ordinary participant access
- **WHEN** the verified owner selects a safe project_member or project_admin role for an eligible project_reader participant
- **THEN** the native direct assignment is changed and published under the current project/domain authority checks

#### Scenario: Reader attempts delegation
- **WHEN** a project_reader calls the same membership mutation or targets a foreign domain
- **THEN** the operation is rejected without changing native grants
