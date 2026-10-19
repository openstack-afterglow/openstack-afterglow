## ADDED Requirements

### Requirement: Administrator native authority
The system SHALL authorize all telemetry administration with fresh system-administrator authority and the caller's native session, and SHALL return private no-store responses without substituting service credentials.

#### Scenario: Native service missing or denied
- **WHEN** the catalog lacks Aodh/Gnocchi or the native policy denies a request
- **THEN** the page distinguishes not configured, forbidden and unavailable while existing resource monitoring stays usable.

#### Scenario: Authority changes during a request
- **WHEN** user, token, project or administrator authority changes before a read or mutation completes
- **THEN** the UI clears private drafts/data and discards late responses, including same-tick ABA transitions.

### Requirement: Aodh dashboard and settings
The system SHALL provide paged alarm states and history plus explicit native create, edit, enable/disable, repeat-actions and delete operations, preserving rule and time constraints on edit.

#### Scenario: Alarm lifecycle
- **WHEN** an administrator creates or changes a native alarm and rereads it
- **THEN** the saved name, rule, severity, enabled flag, repeat flag and all three state-action lists are represented faithfully.

#### Scenario: Uncertain mutation result
- **WHEN** a native mutation times out or loses its response
- **THEN** the UI reports uncertainty and requires rereading rather than automatically replaying the mutation.

### Requirement: Native notification action configuration
The system SHALL allow upstream webhook, trust webhook, log, Zaqar, trust Zaqar and trust Heat action URLs for alarm, ok and insufficient-data transitions without fetching those URLs itself. It SHALL distinguish documented upstream methods from actually installed plugins and successful delivery.

#### Scenario: Delegated or secret-bearing action
- **WHEN** an administrator edits actions
- **THEN** trust delegation is explained, injected native trust IDs are not exposed or resubmitted, unsupported direct mail schemes are rejected, and secrets are not persisted or logged.

### Requirement: Gnocchi independent inspection
The system SHALL expose independently evaluated API capabilities, processing backlog, archive policies/rules and resource types, paged resources/metrics and bounded raw measures, without native write operations.

#### Scenario: Partial service visibility
- **WHEN** processing status is denied but archive policies are readable
- **THEN** readable policies remain visible and processing status is explicitly unknown/denied, not healthy zero.

#### Scenario: Raw measurement inspection
- **WHEN** an administrator selects a metric and bounded time range
- **THEN** samples preserve unit, timestamp and granularity; measured zero differs from empty data and truncation is disclosed.

### Requirement: Responsive localized administration
The system SHALL expose the same inspection/settings actions through existing administrator navigation and primitives in Korean, English, Japanese and Simplified Chinese at mobile, tablet and desktop widths.

#### Scenario: Narrow viewport
- **WHEN** an administrator opens forms or tables on mobile
- **THEN** required states and actions remain reachable and horizontal overflow is confined to named table regions.
