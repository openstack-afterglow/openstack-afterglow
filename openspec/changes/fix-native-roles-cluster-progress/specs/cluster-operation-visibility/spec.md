## ADDED Requirements

### Requirement: Quota-aware cluster admission
The system SHALL inspect the selected project's actual Neutron security-group and rule limits, usage, reservations and required native default resources before creating a cluster, without automatically increasing existing project quotas.

#### Scenario: Insufficient available groups
- **WHEN** the selected project lacks the native quota required for cluster security groups
- **THEN** creation SHALL stop before its provider mutation and report the resource and required and available capacity.

### Requirement: Persistent honest operation progress
The interface SHALL show full-width initial progress and a stage-consistent estimated progress, and keep active operations available in a minimizable background status until an authoritative terminal state.

#### Scenario: Background operation continues after navigation
- **WHEN** the user minimizes an active cluster operation and navigates within the same verified project session
- **THEN** the operation remains available without dispatching a second mutation and updates from its original operation identifier.

#### Scenario: Stream closes or scope changes
- **WHEN** the stream disconnects or the verified user or project changes
- **THEN** the interface SHALL not infer success or disclose another scope's operation.

### Requirement: Native standard-member Waygate execution
Waygate SHALL admit authorized member operations when Keystone issues a valid Trust token whose expiration exceeds the independently enforced grant deadline, while preserving exact role, project, actor, revocation and deadline checks.

#### Scenario: Native Trust token expires later than grant
- **WHEN** Keystone issues an otherwise valid delegated token with a longer lifetime than its execution grant
- **THEN** execution remains bounded by the original grant and current Trust authority, without widening its privileges.

### Requirement: Administrator system information location
The administrator version information SHALL appear under System information rather than the administrator overview and remain protected by the existing current administrator authority.

#### Scenario: Administrator opens system information
- **WHEN** a verified system administrator opens the System information navigation entry
- **THEN** the existing version, runtime, dependency and revision information is displayed without a duplicate on the overview.
