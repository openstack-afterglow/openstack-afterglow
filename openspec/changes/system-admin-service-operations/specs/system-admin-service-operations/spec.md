## ADDED Requirements

### Requirement: System administrator alternative
The system SHALL authorize Lumen, Drover, Waygate and Palimpsest administrative resource operations when the human caller holds either the existing required project service capability or currently verified Keystone system:all admin authority. A verified system administrator SHALL NOT require target-project membership or detailed service roles.

#### Scenario: Administrator without target service leaves
- **WHEN** a current system administrator selects an enabled project and requests inspection, creation or deletion without target-project membership or detailed service roles
- **THEN** BFF and native action authorization SHALL accept system authority instead of requiring those leaves
- **AND** native provider and resource state safety checks SHALL still apply

#### Scenario: Project administrator is not a system administrator
- **WHEN** a project or domain administrator lacks the required service capability and has no current system:all admin authority
- **THEN** the operation SHALL be rejected

### Requirement: Caller and target identity remain distinct
The system SHALL preserve the caller's original authenticated identity and connection project separately from the explicitly selected logical target and any dedicated native provider executor, without impersonating an owner or granting caller project membership.

#### Scenario: Cross-project system administrator request
- **WHEN** an authorized system administrator operates on a different selected project
- **THEN** native requests SHALL carry the connection project in X-Project-Id and the logical target in X-Target-Project-Id
- **AND** the native service SHALL independently validate the caller, target and current administrator authority

#### Scenario: Original system or unscoped administrator
- **WHEN** a human administrator has no original project and supplies an explicit logical target
- **THEN** the empty original connection project SHALL remain empty instead of being forged or rescoped to the target
- **AND** the selected target and current administrator authority SHALL be independently validated

#### Scenario: Forged target or inactive project
- **WHEN** a caller forges a target without current system authority or selects a disabled, absent or outside-selected-domain target
- **THEN** the BFF SHALL reject the operation before upstream mutation

### Requirement: Fresh authority and credential bounds
The system SHALL fail closed when current system authority is revoked or cannot be established, and SHALL preserve all machine/API-key scope attenuation and caller-bound durable execution checks.

#### Scenario: Revoked administrator after cached authentication
- **WHEN** cached authentication reports administrator but fresh native authority has been revoked
- **THEN** the request SHALL be rejected without executing the administrative action

#### Scenario: Directory outage
- **WHEN** fresh authority cannot be established because the directory is unavailable
- **THEN** the request SHALL report unavailability instead of granting access or returning a successful empty inventory

#### Scenario: Ordinary entitled caller
- **WHEN** a caller has the existing required project service capability and no system authority
- **THEN** existing authorized behavior SHALL remain available with the same ownership and credential limits

#### Scenario: Effective-system view omits a valid raw grant
- **WHEN** effective-system assignments are empty but complete raw exact-system user or current-group grants reach canonical global admin through the trusted role-ID graph
- **THEN** current system authority SHALL be recognized without requiring target service roles
- **AND** removing a grant, membership or implication edge SHALL remove that authority on the next fresh check

#### Scenario: Incomplete authority collections
- **WHEN** native group, assignment, role catalog or inference metadata is unavailable, malformed, truncated or paginated without proven completeness
- **THEN** the native service SHALL report authority unavailable instead of authorizing from an incomplete view

#### Scenario: Original reduced token does not borrow owner administration
- **WHEN** an original Trust, application credential or otherwise reduced credential belongs to a user who currently has human system administration
- **THEN** its original identity/source and issued-role-ID ceiling SHALL survive validation and any exchange
- **AND** it SHALL NOT gain the human cross-project administrator alternative or broader machine-key scopes
- **AND** persisted new-I/O execution SHALL retain the admitted restriction while completed-result recovery and settlement remain available

#### Scenario: Disabled native identity or target domain
- **WHEN** the requester home domain or selected target project's native domain becomes disabled
- **THEN** fresh administrative work and existing administrator-issued-key use SHALL be denied without relying on stale domain names

### Requirement: Explicit administrator provider execution
Drover and Waygate SHALL support actual provider operations for a system administrator with zero target membership using an explicitly configured dedicated executor whose real native credential is valid for that target. Admission and every new durable provider send SHALL check current requester system authority, enabled requester/executor/target, exact target and permitted provider roles. Caller and executor identities SHALL be recorded separately. Normal caller delegation SHALL remain unchanged.

#### Scenario: No caller target member
- **WHEN** a verified system administrator has no target roles and the dedicated executor has valid target provider credentials
- **THEN** create/delete and other admitted provider operations SHALL execute in the selected target and retain the real requester audit identity

#### Scenario: Missing or revoked executor
- **WHEN** executor credentials, target provider membership or requester system authority are missing or revoked
- **THEN** admission or new durable I/O SHALL fail closed without substituting service credentials, automatically granting roles or falsely claiming success

### Requirement: Human Palimpsest administrator management
Palimpsest SHALL permit freshly verified human system administrators to manage known package/layer/upload/download/publish/key-management/build operations without target service roles or membership. Native package key scopes and protected machine principal restrictions SHALL remain in force.

#### Scenario: Human administrator versus package key
- **WHEN** the same management operation is requested using a current human system administrator token or an attenuated package key
- **THEN** the human administrator alternative SHALL apply only to the token, while the package key SHALL still require its own stored scope and current owner authority
