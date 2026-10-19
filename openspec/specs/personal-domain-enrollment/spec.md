# personal-domain-enrollment Specification

## Purpose
Define personal identity ownership for new email and external humans, independently authorized organization membership, durable administrator approval, future-only quota policy, and fail-closed provisioning and continuation boundaries while preserving existing canonical accounts.

## Requirements
### Requirement: New humans own personal identity domains
The system SHALL create every new email, OIDC, or GitHub human through the shared durable enrollment path with a personal identity domain and a personal Default project. The personal owner SHALL receive manager, project_owner, and project_reader on that Default. Organization participation SHALL remain separately authorized by a verified invitation or trusted provider admission, and SHALL NOT change an existing account's canonical user ID, home, password, or unrelated bindings.

#### Scenario: First external login joins an authorized organization
- **GIVEN** a verified external subject with no canonical human and valid target organization admission
- **WHEN** automatic enrollment or an exact approved request permits creation
- **THEN** the account owns a new personal home and Default, receives only the authorized reader baseline in the organization, and the final native exchange preserves its exact canonical user ID and home

#### Scenario: Existing human accepts organization membership
- **GIVEN** an existing enabled canonical human with a verified invitation
- **WHEN** that human accepts using current account proof
- **THEN** membership is additive and no replacement account, personal domain, or new signup approval is created

### Requirement: System administrators persist future enrollment policy
The system SHALL expose revisioned public-email-signup, auto/admin approval, and sparse personal quota policy at system-admin-only APIs and a system administrator settings panel. Every request SHALL require current native system administrator authority. Updates SHALL use compare-and-swap revision checks and affect future personal-domain creation only. Only an absent policy row MAY bootstrap from configuration, automatic approval, and conservative zero core quotas; unavailable policy storage SHALL fail closed.

#### Scenario: A stale policy edit cannot replace current policy
- **GIVEN** a persisted policy and an editor holding an older revision
- **WHEN** the editor saves
- **THEN** the request fails with conflict and the saved policy is unchanged until an explicit reload and new edit

#### Scenario: Cached administrator authority is revoked
- **GIVEN** an ordinary user or a session whose cached administrator flag no longer has native authority
- **WHEN** any enrollment policy or signup review API is requested
- **THEN** access is denied and no policy, request, or native resource is mutated

### Requirement: Verified secret-free signup review precedes provisioning
In administrator approval mode the system SHALL persist a request only after delivered email proof or fresh validated external identity proof. Requests SHALL bind source, normalized email and exact external identity/target/provider context without storing passwords, OAuth codes, bearer tokens, or reusable provider credentials. Pending and rejected decisions SHALL prevent native provisioning and login publication. Approved decisions SHALL be consumed only after successful enrollment. Mode changes and email case or IDNA spelling changes SHALL NOT bypass an existing decision. Review SHALL be bounded, pending-only, durable and non-replayed.

#### Scenario: Verified signup waits without a native account
- **GIVEN** administrator approval is required and a new applicant presents verified proof
- **WHEN** enrollment is requested
- **THEN** a durable pending request is returned as a blocked approval state before native account, domain, project, grant, quota write, or login session creation

#### Scenario: Rejection remains effective after enabling automatic approval
- **GIVEN** a rejected request for an exact verified identity
- **WHEN** automatic approval is enabled or the applicant changes email case or IDNA spelling
- **THEN** the existing rejection is retained and native enrollment does not proceed

#### Scenario: Signup approval notification fails after commit
- **GIVEN** an administrator approves a pending email request
- **WHEN** the subsequent notification cannot be confirmed
- **THEN** the decision remains approved, an explicit notification failure is returned, and repeating approval does not resend or reverse the decision

### Requirement: Frozen quotas are verified before activation
The system SHALL freeze the personal quota template in the enrollment journal before native effects, seed the new personal domain's allocation ceilings and defaults from that snapshot, and apply and read back native project quotas while the human and personal Default are disabled. Blank quota entries SHALL mean native defaults, zero SHALL mean no allocation, and minus one SHALL mean unlimited. Disabled Manila entries SHALL be preserved in the template and explicitly omitted from the active policy. Unsupported or uncertain native results SHALL prevent successful activation or publication and require recovery rather than an automatic mutation replay.

#### Scenario: A later policy edit does not alter an existing personal allocation
- **GIVEN** a personal enrollment completed using one frozen quota snapshot
- **WHEN** an administrator saves different future quota defaults
- **THEN** the existing domain allocation policy, native quota and completed enrollment snapshot remain unchanged

#### Scenario: External enrollment finalization is uncertain
- **GIVEN** an external human has an enrollment provenance marker but its exact user/home journal is not accepted
- **WHEN** a fresh provider callback finds that native human
- **THEN** it fails closed without exchanging or publishing a session or creating another account, even if activation occurred before the earlier failure

### Requirement: Approval continuation uses fresh proof without credential replay
The browser SHALL show localized pending and rejected states without retaining or replaying blocked credentials. Email approvals SHALL continue with a new verification link when public signup is enabled, or explicit verified-invitation reopening when it is disabled. External applicants SHALL start fresh provider authentication after approval. A restored authenticated callback SHALL wait for root-owned readiness before its sole code exchange and SHALL abandon late results after owner, scope, readiness, logout, unmount, or ABA transitions.

#### Scenario: Invitation-only applicant completes after approval
- **GIVEN** public email signup is disabled and a new invited human is approved
- **WHEN** the applicant explicitly reopens the verified invitation
- **THEN** only a GET refresh is performed, credential fields are blank, and completion creates a personal home before the authorized organization membership

#### Scenario: A restored session is verified while a provider callback loads
- **GIVEN** the callback has a restored logical session whose root verification is pending
- **WHEN** the same owner becomes ready
- **THEN** exactly one provider code exchange is performed without a second authentication verification, while any intervening owner/scope/readiness loss makes the callback terminal

### Requirement: Enrollment schema precedes all new writers
Migration 098 SHALL add the revisioned policy, credential-free request queue and nullable frozen enrollment quota snapshot before new writers start. Existing signup writers SHALL be drained at cutover. Migration SHALL preserve existing canonical humans, domains, grants and enrollment journals and SHALL NOT seed a policy row or migrate Default-domain identities.

#### Scenario: An existing enrollment schema is upgraded twice
- **GIVEN** an older supported enrollment schema containing a historical invitation
- **WHEN** the additive migrations and migration 098 are applied, including a repeated 098 application
- **THEN** the historical domain/status is preserved, its new quota snapshot is nullable, and no persisted policy is invented

