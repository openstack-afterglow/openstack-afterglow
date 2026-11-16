## ADDED Requirements

### Requirement: Login workspace defaults to the last accessed workspace
The system SHALL reconnect a login to the last accessed domain and project when the user has not opted out. A user who opts out SHALL choose a fixed domain and project, which the system SHALL validate for current membership when saved and SHALL NOT overwrite on later workspace switches. A stored workspace that no longer validates SHALL fall back to the personal project.

#### Scenario: No preference stored
- **WHEN** a user without a stored preference switches to project P in domain D and later logs in
- **THEN** the login lands on D/P if the user is still a member of P

#### Scenario: Fixed default
- **WHEN** a user opts out and chooses D2/P2, then switches to D3/P3 and later logs in
- **THEN** the login lands on D2/P2

#### Scenario: Stale workspace
- **WHEN** the stored project is no longer accessible at login
- **THEN** the login lands on the personal project without error
