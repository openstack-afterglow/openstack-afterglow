## ADDED Requirements

### Requirement: Separate administrator service navigation
The administrator sidebar and command palette MUST expose Drover, Lumen, Palimpsest, and Waygate under the administrator service context. Tenant Waygate MUST remain in the tenant Network context. An administrator Waygate destination MUST render an administrator-labeled workspace without silently switching to an all-project view.

#### Scenario: Navigate to an administrator service
- **WHEN** an administrator opens Palimpsest or Waygate from the service group or command palette
- **THEN** the matching administrator route is selected and the service group is active on desktop and in the responsive drawer

#### Scenario: Use tenant Waygate
- **WHEN** a project user opens Waygate from Network
- **THEN** the tenant route remains active and does not navigate to the administrator workspace

### Requirement: Bound Waygate data to the current project
Waygate workspace requests and displayed server, client, and attachment data MUST be scoped to the selected project. A scope change MUST invalidate in-flight responses and prior project selections; lack of a project MUST NOT trigger an implicit administrator all-project request.

#### Scenario: Change project during a delayed request
- **WHEN** a Waygate request for project A completes after selecting project B
- **THEN** the project A result is discarded and the workspace displays only project B data

#### Scenario: No selected project
- **WHEN** an administrator opens the Waygate workspace without a selected project
- **THEN** no server or client request is made and a project-selection state is displayed
