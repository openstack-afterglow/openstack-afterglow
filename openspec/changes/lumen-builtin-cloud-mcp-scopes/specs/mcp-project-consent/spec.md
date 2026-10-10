## ADDED Requirements

### Requirement: Explicit access and project selection
Personal token creation and OAuth approval SHALL offer read/manage access and either all currently accessible projects or a nonempty explicit subset. The server SHALL validate current ownership, target memberships and actual target-project permissions before issuing exact-project restricted credentials.

#### Scenario: Selected projects
- **WHEN** a user approves a read grant for projects A and B
- **THEN** only read tools are visible and execute in A or B; project C and writes are rejected before cloud I/O

#### Scenario: All currently accessible projects
- **WHEN** the user selects all
- **THEN** the server saves the enabled accessible project set at issuance and does not add later projects implicitly

### Requirement: OAuth scope attenuation
Approved OAuth scopes SHALL be bounded by the original client request and saved on the grant/code/token family; refresh SHALL NOT restore declined write access.

#### Scenario: User declines requested management
- **WHEN** a write-capable client request is approved as read
- **THEN** code exchange, access tokens and refresh remain read-only

#### Scenario: Client requested only read
- **WHEN** approval asks for management for a read-only client request
- **THEN** approval is rejected and no management grant is created

### Requirement: Complete project authority lifecycle
Tool schemas SHALL expose optional target project selection and an authenticated listing of saved projects. Every execution, preview, mutation claim and credential connection SHALL enforce the saved target set. Revocation/expiry/cleanup SHALL cover all delegated credentials and existing single-project grants SHALL remain single-project.

#### Scenario: Cross-project idempotency
- **WHEN** the same mutation key is reused for a different target project
- **THEN** the canonical invocation conflicts rather than replaying or dispatching in the new project

#### Scenario: Revocation
- **WHEN** a multi-project grant is revoked
- **THEN** every target is immediately nondispatchable and upstream cleanup covers every credential
