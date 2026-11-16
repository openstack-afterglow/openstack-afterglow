## ADDED Requirements

### Requirement: Consent domain selection happens in place
The consent screen SHALL select the connected domain by default, list it even when the session omits it, and change the working domain without leaving the permission step.

#### Scenario: Default domain
- **WHEN** the project step opens for a ticket authorized in domain A and the session lists only domain B
- **THEN** the select lists A and B with A selected

#### Scenario: Switching domains
- **WHEN** the user selects domain B
- **THEN** only the project area shows a loading state, the step and duration stay, the projects of B replace the list, and the decision uses the new session

#### Scenario: Failed switch
- **WHEN** the domain token request fails
- **THEN** the select returns to the connected domain, the old selection stays and an error is shown

### Requirement: Write operations imply read
Selecting create or update for a project SHALL also select read for it, SHALL keep read while a write operation is chosen, and the server SHALL store read with any write selection.

#### Scenario: Create without read
- **WHEN** read is cleared and create is selected
- **THEN** read is selected again and cannot be cleared until create and update are cleared

#### Scenario: Server normalization
- **WHEN** a request carries only update for a project
- **THEN** the stored operations are read and update

### Requirement: Palimpsest member tier
Palimpsest SHALL give a project member every package capability including key issue and revoke, SHALL keep package/layer/export deletion and project management with managers, and SHALL leave a reader with inventory, download and its own key list/revoke.

#### Scenario: Member capabilities
- **WHEN** a member's policy capabilities are read
- **THEN** inventory, download, publish, key issue and key revoke are present
