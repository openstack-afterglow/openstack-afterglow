# personal-domain-enrollment Specification

## Purpose
Define personal identity ownership for new email and external humans, independently authorized organization membership, durable administrator approval, future-only quota policy, and fail-closed provisioning and continuation boundaries while preserving existing canonical accounts.

## Requirements
### Requirement: New humans share an identity-only accounts home and own personal projects
The system SHALL create every new email, administrator-created, invited, OIDC, or GitHub human through the shared durable enrollment path with an identity in the operator-provisioned native `Accounts` domain and a personal project in the operator-provisioned native `Personal` domain. Enrollment SHALL resolve exact enabled native names, accept absent management metadata but reject conflicting kinds, and SHALL NOT create or mutate shared domains. The personal project name SHALL contain the normalized username, a hyphen, eight cryptographically random lowercase letters and eight random decimal digits within the native 64-character limit, and SHALL be frozen before native dispatch. Its only newly granted direct native role SHALL be `member`; Accounts SHALL receive no Default project, domain manager or project grant. Organization participation SHALL remain separately authorized by a verified invitation or trusted provider admission, and SHALL NOT change an existing account's canonical user ID, home, password, federation tuple or unrelated bindings. Existing personal names, project IDs, owner-based grants and shared-domain journals SHALL NOT be migrated or rebound by this cutover.

#### Scenario: First external login joins an authorized organization
- **GIVEN** a verified external subject with no canonical human and valid target organization admission
- **WHEN** automatic enrollment or an exact approved request permits creation
- **THEN** the account receives an accounts identity and a personal member project, receives only the authorized reader baseline in the organization's Default project, and the final native exchange preserves its exact canonical user ID and identity home while entering its personal primary scope

#### Scenario: Existing human accepts organization membership
- **GIVEN** an existing enabled canonical human with a verified invitation
- **WHEN** that human accepts using current account proof
- **THEN** membership is additive and no replacement account, personal domain, or new signup approval is created

#### Scenario: Administrator creates a user while observing an organization
- **GIVEN** a current system administrator observing any existing directory domain
- **WHEN** the administrator creates a human
- **THEN** the selected domain is observation context only, the human receives an activated Accounts identity and a same-token/name frozen-quota deferred personal intent without a project/grant; the response has `personal_project_deferred:true`, a null project ID and the reserved project name, and no selected-domain or Accounts Default grant is added

#### Scenario: First successful login consumes the deferred personal intent
- **GIVEN** an accepted administrator-created human and its exact deferred personal intent
- **WHEN** fresh native password or provider proof succeeds and existing login policies admit the human
- **THEN** the same intent/name/quota is prepared once as a disabled Personal project with only the human's direct member grant and verified quota/provenance before activation and token publication; disabled identities cannot bypass native login, and repeated successful logins reuse the project

#### Scenario: Existing markerless human administrator starts in personal
- **GIVEN** a freshly authenticated interactive system administrator with no personal project or deferred managed enrollment
- **WHEN** native human qualification succeeds and no service-role automation authority applies
- **THEN** the existing durable provisioning path creates and verifies exactly one personal member primary without changing identity/home/password or existing grants/resources, and fresh publication selects that personal project before dashboard or explicit continuation

#### Scenario: Native automation retains projectless administrator recovery
- **GIVEN** a freshly authenticated system administrator with verified native service authority
- **WHEN** no personal project is provisioned and the server returns a projectless context in an exact visible non-account domain
- **THEN** the frontend preserves immutable identity and opens the chooser; invisible or unverified foreign project landing remains rejected

#### Scenario: User explicitly resumes safe first-login preparation
- **GIVEN** safe confirmed or not-sent personal provisioning progress after successful native proof
- **WHEN** the user supplies a fresh `{username,password}` proof to `POST /api/v1/auth/personal-project/recovery`
- **THEN** the normal Accounts credential/subject/login-policy guards precede resumption and JWT publication, while the browser clears the old password and requires re-entry; an unknown dispatched native outcome instead requires explicit system-administrator settlement and is never blindly replayed

#### Scenario: Existing personal ownership is preserved
- **GIVEN** a canonical human with an existing home and owner-based personal workspace
- **WHEN** the human logs in or accepts separately authorized organization membership
- **THEN** the original identity, password, federation tuple, personal name and project ID and native grants are preserved rather than rewritten to the new enrollment shape

### Requirement: System administrators persist future enrollment policy
The system SHALL expose revisioned public-email-signup, auto/admin approval, and sparse personal quota policy at system-admin-only APIs and settings. Every request SHALL require current native system authority. Policy updates SHALL use compare-and-swap and affect future creation only. Only an absent row MAY use source defaults of2 vCPU,4096MiB RAM and1024GiB Cinder with supporting counts. Existing stored customization and frozen intent SHALL remain unchanged; storage failure SHALL fail closed. Existing project changes SHALL require a separate provenance/usage-checked preview and explicit apply.

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
The system SHALL freeze the personal quota template in the enrollment journal before native effects and apply and read back native project quotas while the personal project is disabled. Immediate enrollment SHALL also keep the new human disabled until completion; deferred administrator creation SHALL preserve the already accepted identity's enabled state and require fresh native login proof instead of disabling or resetting it. Exact owned project metadata, the user's direct member assignment and complete raw/effective role provenance SHALL be verified before project activation; new personal provisioning SHALL NOT require or create project_owner, project_reader, a personal Default, domain manager or a shared domain allocation budget. A native member implication reaching owner or manager authority SHALL fail closed. Blank quota entries SHALL mean native defaults, zero SHALL mean no allocation, and minus one SHALL mean unlimited. Disabled Manila entries SHALL be preserved in the template and explicitly omitted from the active policy. Unsupported or uncertain native results SHALL prevent successful activation or publication and require recovery rather than an automatic mutation replay.

#### Scenario: A later policy edit does not alter an existing personal allocation
- **GIVEN** a personal enrollment completed using one frozen quota snapshot
- **WHEN** an administrator saves different future quota defaults
- **THEN** existing native project quotas, shared domain budgets and the completed enrollment snapshot remain unchanged

#### Scenario: External enrollment finalization is uncertain
- **GIVEN** an external human has an enrollment provenance marker but its exact user/home journal is not accepted
- **WHEN** a fresh provider callback finds that native human
- **THEN** it fails closed without exchanging or publishing a session or creating another account, even if activation occurred before the earlier failure

### Requirement: Existing personal quota application is explicit and journaled
The system SHALL enumerate every native Personal project with bounded cursor paging and SHALL require current system authority, exact enabled ownership/provenance, current usage plus reservations, and an unchanged policy/preview fingerprint before applying limits. Native member-only projects SHALL NOT require project-owner role presets. Historical native-owner primaries MAY retain their existing provenance. Unknown writes SHALL reuse durable quota-operation fences and settlement; frozen provisioning intent, grants and resources SHALL NOT be rewritten.

#### Scenario: Existing usage exceeds proposed default
- **GIVEN** a verified personal project whose usage plus reservations exceeds a finite proposed limit
- **WHEN** an administrator previews or tries to apply current policy
- **THEN** preview identifies the blocked fields and apply is rejected without deleting resources or lowering the native quota

### Requirement: Remembered login workspace is opt-in and never authority
Every supported human SHALL default to a verified personal primary, including system administrators. Only an explicit exact-user/identity-home preference MAY restore a last workspace after fresh native domain/project authority checks. Revoked/deleted/disabled targets SHALL fall back to personal; directory/store failures and substituted native proof SHALL remain errors. Fresh remembered metadata SHALL exactly match the published session. Projectless/failed/stale login SHALL preserve explicit invitation/MCP continuation intent.

#### Scenario: Administrator observes global inventory while logged into personal
- **GIVEN** a human with verified system authority and a personal project member token
- **WHEN** native administrator inventory is requested
- **THEN** fresh system authority gates the configured fixed native admin-project executor required by project-only provider policy, while logical personal workspace/actor/home and actual execution project remain distinct; no human project grant is added, and consumer/credential/telemetry caller boundaries remain intact


### Requirement: Approval continuation uses fresh proof without credential replay
The browser SHALL show localized pending and rejected states without retaining or replaying blocked credentials. Email approvals SHALL continue with a new verification link when public signup is enabled, or explicit verified-invitation reopening when it is disabled. External applicants SHALL start fresh provider authentication after approval. A restored authenticated callback SHALL wait for root-owned readiness before its sole code exchange and SHALL abandon late results after owner, scope, readiness, logout, unmount, or ABA transitions.

#### Scenario: Invitation-only applicant completes after approval
- **GIVEN** public email signup is disabled and a new invited human is approved
- **WHEN** the applicant explicitly reopens the verified invitation
- **THEN** only a GET refresh is performed, credential fields are blank, and completion creates the accounts identity and personal member project before the authorized organization membership

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

### Requirement: Personal member authority remains project-local
Generic membership APIs SHALL preserve the Personal human's direct native member on primary and additional projects and SHALL reject additional project/service roles. Lumen, Drover, Waygate and Palimpsest SHALL derive personal-owner authority independently from fresh exact enabled native user/home/project/domain and complete raw/effective direct-member provenance; the domain kind SHALL be absent or exactly personal, not an explicit null or malformed value. Registered service policy SHALL admit project actions without inventing Keystone roles or system authority. Original scope, explicit operator deny, reduced-credential/key ceilings, ownership and provider-send revalidation SHALL remain authoritative. Hub package metadata deletion MAY be allowed for an exact owned-project personal human, but SHALL NOT be delegable to package keys or expand shared CAS deletion, GC, builds or system actions.

#### Scenario: Personal membership cannot become a platform administrator
- **GIVEN** a freshly verified Personal owner holding only the direct native member grant
- **WHEN** local service project actions are requested or generic project roles are edited
- **THEN** eligible project actions are allowed according to service policy, other-role additions and required-member removal are denied, and neither a permissive operator rule nor the personal predicate bypasses system, original-scope or reduced-credential ceilings

### Requirement: Profile image choices persist under exact-self authority
Authenticated humans SHALL receive an email-derived Gravatar default and MAY select generated or bounded raster-upload images. Only fixed-origin Gravatar email hashes or normalized PNG data SHALL render; no arbitrary remote URL or active SVG upload SHALL be accepted. Reads SHALL prove exact native self, and image writes SHALL preserve stock native user-update policy through a bounded service writer that verifies enabled exact user/home, changes only the image extra key, preserves other metadata, reads back and closes connections. Header and profile SHALL share the image and clear late owner/scope/authority/logout/ABA results. Existing schema and credentials SHALL remain unchanged.

#### Scenario: An uploaded profile image survives a fresh login
- **GIVEN** a human uploads a permitted raster within byte/dimension/pixel/native-metadata bounds
- **WHEN** normalization, exact-self bounded write and fresh readback complete, followed by reload or a fresh login
- **THEN** profile and accessible header render the same persisted metadata-free PNG; malformed/oversized/active input is rejected without replacing the previous image, and another user's late response cannot become visible


