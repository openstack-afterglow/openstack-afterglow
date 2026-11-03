## MODIFIED Requirements

### Requirement: Before-approval project capability preview
OAuth consent and personal API-key issuance SHALL display effective cloud read/write level and independent service permissions for every selected project before grant submission, including all-project selection. They SHALL share permission projection semantics and SHALL distinguish unknown authority from permission.

#### Scenario: Mixed permission preview on both grant forms
- **WHEN** all projects are selected with management access in OAuth consent or personal-key issuance
- **THEN** each project shows its own read/write ceiling and four independent service states before approval or creation

#### Scenario: Policy unavailable or selection changed
- **WHEN** a policy lookup fails or caller/project selection changes
- **THEN** unavailable authority is not shown as allowed and stale preview cannot authorize a different caller or selection

## ADDED Requirements

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
