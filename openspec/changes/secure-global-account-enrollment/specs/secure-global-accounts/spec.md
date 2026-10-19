## ADDED Requirements

### Requirement: Existing-domain admission is invitation-gated and configuration-driven

The system SHALL require a valid invitation or current native membership before admitting a human account to an existing domain, unless the selected configured identity provider explicitly permits the verified exact email host for that domain. Provider selection, issuer/native binding and email-host exceptions SHALL come from configuration rather than domain names or a deployment hostname. A domain-level auto-join map SHALL replace the default map; an explicit empty map SHALL deny automatic admission. An exception SHALL grant only reader baseline on an already prepared canonical Default project, not ownership or manager authority.

#### Scenario: A configured organization permits verified external email hosts
- **WHEN** an operator selects a trusted GitLab provider and configures its `gmail.com` and `konkuk.ac.kr` exact-host exception for an exact domain ID
- **THEN** a verified identity from that selected provider may join with reader baseline without an invitation
- **AND** a different issuer/provider, unverified email, subdomain or lookalike host does not qualify through the exception

#### Scenario: An email match is not tenant admission
- **WHEN** an identity from an unapproved provider presents the same email as an existing account or member
- **THEN** email coincidence does not create an account, attach an identity or grant domain/project access

### Requirement: Public registration verifies email before provisioning a personal domain

Public registration SHALL be separately configured and SHALL begin with email delivery only. It SHALL NOT create a native user, password, domain or project before consuming a valid one-use email proof. A verified new human SHALL choose credentials and a personal domain; completion SHALL provision that personal domain and its canonical Default through the existing staged ownership workflow, rather than publicly joining an arbitrary existing organization. SMTP/readiness failures SHALL NOT be represented as successful enrollment.

#### Scenario: A new user follows public signup
- **WHEN** an eligible email is submitted without selecting an organization-specific provider login
- **THEN** no native account or personal domain exists before email verification
- **AND** successful proof redemption and credential/domain selection create one personal home and one Default for that account

#### Scenario: The verified email already belongs to an account
- **WHEN** a verified signup proof resolves to one existing canonical account
- **THEN** the user is offered original-home login or recovery and authorized account connection, not a second username/password/account creation form

### Requirement: All first-party human-account writers share canonical email ownership

Creation, invitation, registration, federation and profile/administrator email changes SHALL enforce one canonical human account per normalized email. Ownership decisions SHALL use a complete native account envelope and exact user metadata hydration, including immutable home identity. A missing, truncated, limited or paginated unresolved inventory SHALL fail closed as unavailable rather than establish absence. Historical duplicate emails SHALL be conflicts requiring reviewed consolidation, not an automatic selection or merge. Joining another working domain SHALL retain the original account ID, home, username, password and saved default-project preference.

#### Scenario: Native collection metadata omits an existing email
- **WHEN** an account collection omits the email but exact user metadata contains the submitted normalized email
- **THEN** the existing account is recognized and no duplicate is provisioned

#### Scenario: Historical duplicate ownership is ambiguous
- **WHEN** multiple native accounts have the same normalized email
- **THEN** account creation or linking fails with a conflict and no account is silently disabled, deleted, renamed or merged

### Requirement: External linking proves both accounts and preserves native identity

External linking SHALL bind a browser-bound, expiring, one-use provider proof to verified immutable issuer/subject and explicit original-account password or still-live authenticated native/application-session proof. Proof validation, fresh canonical ownership/admission checks and native attachment SHALL share the recovery identity-graph lease. Native federation SHALL use a stable-subject user-only mapping and return the same canonical native user/home; mutable username/email mappings and mapper group/project/role grants SHALL be rejected. No service-account user token substitution SHALL be used. Other native federation tuples and original credentials SHALL be preserved.

#### Scenario: Recovery revokes a session before it can link
- **WHEN** password recovery invalidates the originating native/application session before link proof obtains the shared lease
- **THEN** linking is denied and no persistent external identity is attached

#### Scenario: A legacy password account gains an external login
- **WHEN** a valid original password or live password-origin session proves the account and the external proof is valid
- **THEN** attachment preserves the original password/home and records proven local-password capability
- **AND** an external-only proof cannot manufacture local-password capability

#### Scenario: Confirmed linking requires a separate fresh login
- **WHEN** original-account proof and native attachment readback complete
- **THEN** both explicit link endpoints return only `{linked:true,domain_id,domain_name,provider_id}` and clear the one-use state cookie without federation, provider-verification stamping or application-session issuance
- **AND** the browser shows connection completion and an explicit fresh-login action for the selected configured domain without consuming invitation/MCP continuations or replacing an existing session
- **AND** only a separate new authorization/callback may exchange the native token, recheck the canonical user/home and issue the scoped application session
- **AND** failed or unconfirmed attachment, expired proof and transport timeout SHALL NOT be reported as successful connection or retried automatically

#### Scenario: Working domain differs from identity home
- **WHEN** a canonical account enters an authorized foreign working domain through a configured provider
- **THEN** immutable identity home, working domain and provider policy origin remain separate through issuance, refresh and rescope
- **AND** per-project child principals retain the exact native-validated identity home for subsequent authorization

### Requirement: Automatic entry respects user preference and Default ownership boundaries

Successful domain login SHALL enter the actual native-scoped project without an unnecessary workspace chooser. Selection SHALL prefer an explicit requested project, then an active currently accessible saved default project in that working domain, then canonical Default, then another currently accessible project. Default preparation SHALL NOT overwrite the saved preference. A new domain creator SHALL receive manager, project_owner and project_reader on its Default; first authorized bootstrap in an existing domain SHALL grant only owner/reader to the actual new-project creator, and later participants SHALL receive reader baseline. Existing Default ownership SHALL NOT be adopted or replaced. Owners SHALL delegate only server-authorized roles through the existing role graph and dedicated ownership-transfer boundaries.

#### Scenario: A saved work project differs from Default
- **WHEN** a valid saved default project is accessible in the selected domain
- **THEN** password and configured-provider login issue response, native scope, JWT and session for that saved project rather than forcing Default

#### Scenario: A new domain and subsequent participant are provisioned
- **WHEN** an authenticated creator creates a new domain and another authorized user later joins it
- **THEN** the creator owns its staged-and-verified Default with manager and reader authority
- **AND** the participant receives reader baseline without manager or ownership escalation

### Requirement: Username recovery discloses identity only after one-use email proof

Username recovery SHALL use a bounded email-delivered proof bound to the exact canonical user/home and current email. Public requests SHALL be non-enumerating. Only the owner who consumes a valid proof SHALL receive the username and home login information; replay SHALL fail. Operational/service and unsupported ambiguous identities SHALL NOT be selected as recovery fallbacks.

#### Scenario: An owner retrieves a forgotten username
- **WHEN** the owner consumes a valid username-recovery email proof
- **THEN** the exact original username/home is returned once
- **AND** another inspection of the consumed proof fails without creating or renaming an account

### Requirement: Password and email recovery are account-bound and non-replayable

Recovery proofs SHALL be stored as digests, expire after one hour and permit one native dispatch for the exact user/home/current-email binding. Public request responses SHALL not reveal existence, ambiguity, eligibility or delivery results and SHALL use IP/address rate budgets. Verified local human administrators MAY use email password recovery; configured operational/service and unproven external-only accounts SHALL remain excluded. Reset and verified email change SHALL invalidate captured application session families and revoke their captured native tokens. Unknown native write outcomes SHALL remain recorded and SHALL NOT be replayed. Only authenticated exact native already-invalid-token responses SHALL count as idempotent revocation; unrelated proxy, permission and transport failures SHALL remain failures.

#### Scenario: A password reset consumes its proof and old sessions
- **WHEN** an eligible account completes an email-proven password reset
- **THEN** the same native account receives the new password and captured sessions across its working domains are invalidated
- **AND** proof replay cannot dispatch another password write

#### Scenario: A native write commits but its reply is lost
- **WHEN** reset or email-change dispatch has an unknown native outcome
- **THEN** its durable one-dispatch state is retained for investigation rather than returning the proof to pending or replaying the write

### Requirement: Historical account and native-provider cutover requires preservation evidence

Deployment SHALL drain old enrollment and unverified email writers and prepare the required schema before new writers run. Existing shared native SSO mappings SHALL NOT be overwritten without their consumer inventory and approved cutover. Historical canonical-account consolidation SHALL require explicit identity proof and preserved grants, ownership, credentials, sessions and recovery evidence; unresolved resource ownership SHALL require user review. Local synthetic/runtime evidence SHALL NOT be reported as completed real GitLab authentication, mailbox delivery, production migration or rollout.

#### Scenario: A duplicate owns resources and uses a shared mutable-name mapping
- **WHEN** consolidation encounters unverified resource ownership or an existing shared mapper that provisions groups/projects from mutable claims
- **THEN** existing accounts, resources and shared mappings remain preserved until the reviewed ownership and stable-subject transition is ready
- **AND** the OpenSpec change remains active rather than being archived as fully accepted
