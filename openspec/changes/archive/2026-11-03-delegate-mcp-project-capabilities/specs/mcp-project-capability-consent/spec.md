## ADDED Requirements

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
The consent page SHALL display the effective cloud read/write level and independent service permissions for every selected project before submitting approval, including all-project selection.

#### Scenario: Mixed permission preview
- **WHEN** all projects are selected with management access
- **THEN** each project shows its own read or write ceiling and four service capability states without implying write access for every project

#### Scenario: Policy unavailable or selection changed
- **WHEN** a service permission lookup fails or the caller/project selection changes
- **THEN** unavailable authority is distinguished from permission and stale preview results cannot authorize a different selection
