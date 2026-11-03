# mcp-project-capability-consent Specification

## Purpose
Define least-privilege mixed-project MCP grants, independent native service authority, and project-specific permission disclosure before access is granted.
## Requirements
### Requirement: Mixed all-project authority
The system SHALL allow management consent over all accessible projects while preserving each project's authenticated read/write ceiling. It SHALL NOT require every project to be writable.

#### Scenario: Mixed reader and member projects
- **WHEN** a user approves management across all accessible reader-only and member-authorized projects
- **THEN** the grant includes both, reader projects accept reads only, and writes to reader projects are rejected before provider mutation

#### Scenario: Explicit read attenuation
- **WHEN** the user approves read-only access despite holding member or service editor authority
- **THEN** the delegated client cannot perform mutation in any included project

### Requirement: Independent native service authority
The system SHALL authorize Drover, Palimpsest, Waygate and Lumen through their respective native service policies. Generic cloud member/admin authority SHALL NOT independently authorize these services.

#### Scenario: Cloud writer without service entitlement
- **WHEN** a cloud member lacks a required native service permission
- **THEN** that service action is denied even though cloud writes are permitted

#### Scenario: Missing or revoked service authority
- **WHEN** native policy cannot be established or removes a previously available capability
- **THEN** the preview does not show it as allowed and execution does not use stale preview authority to bypass native denial

### Requirement: Before-approval project capability preview
OAuth consent and personal API-key issuance SHALL display effective cloud read/write level and independent service permissions for every selected project before grant submission, including all-project selection. They SHALL share permission projection semantics and SHALL distinguish unknown authority from permission.

#### Scenario: Mixed permission preview on both grant forms
- **WHEN** all projects are selected with management access in OAuth consent or personal-key issuance
- **THEN** each project shows its own read/write ceiling and four independent service states before approval or creation

#### Scenario: Policy unavailable or selection changed
- **WHEN** a policy lookup fails or caller/project selection changes
- **THEN** unavailable authority is not shown as allowed and stale preview cannot authorize a different caller or selection

### Requirement: Cheap membership discovery and isolated preview failures
The system SHALL keep default project membership discovery independent of native service-policy lookup. Enriched permission preview SHALL be explicit, bounded in concurrency and time, and preserve successful projects/services when another becomes unavailable.

#### Scenario: Read-only issuance while service policy is unavailable
- **WHEN** authenticated membership discovery succeeds but native service preview fails or is pending
- **THEN** read-only key creation remains available with service authority explicitly unknown and management is not enabled from missing metadata

#### Scenario: One project or policy fails
- **WHEN** one project cannot be re-scoped or one service policy times out
- **THEN** only that project or service is marked permission_check_unavailable and healthy project/service outcomes remain visible

#### Scenario: Bounded independent preview workers
- **WHEN** several projects are previewed
- **THEN** project workers use independently owned authenticated SDK sessions with at most3concurrent workers, service-policy checks have5second deadlines, and cancellation drains/closes owned connections
