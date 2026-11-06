## ADDED Requirements

### Requirement: Account-owned MCP inventory
The system SHALL list all non-revoked personal MCP keys and OAuth grants owned by the exact authenticated user independently of the selected project/domain, including when no working project is selected. It SHALL NOT list another user's records based on domain membership.

#### Scenario: Switch workspace
- **WHEN** the owner opens MCP settings from another project or working domain
- **THEN** their saved connections remain listed with their original approved projects and issuance origin

#### Scenario: No selected project
- **WHEN** an authenticated owner has no working project
- **THEN** their saved connection inventory remains available and workspace-dependent issuance is not granted

#### Scenario: Another user
- **WHEN** another user in the same domain opens MCP settings
- **THEN** they cannot list or revoke the original owner's connections

### Requirement: Origin-safe revocation
Revocation SHALL resolve exact-user ownership and use the stored original project for serialization, audit and native cleanup, without expanding cloud authority.

#### Scenario: Revoke from another workspace
- **WHEN** an owner revokes a connection issued under another project
- **THEN** the exact saved grant is revoked under its original owner lock and any native cleanup remains subject to existing policy

### Requirement: Single-domain multiproject authority
OAuth and personal-key issuance SHALL restrict selected or all-project snapshots to currently authorized projects in one working domain. Account inventory visibility SHALL NOT modify existing approved project/role ceilings.

#### Scenario: Multiple selected projects
- **WHEN** the owner approves several authorized projects within one domain
- **THEN** the grant retains that fixed set and does not acquire projects in another domain or projects joined later
